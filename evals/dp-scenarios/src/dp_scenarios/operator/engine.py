"""Stateful deterministic operator engine.

The engine owns turn order, phases, budgets, event firing, and monitors.  It
never invents an operator sentence: every message is a resolved script turn or
fixed matcher output, so the resulting run can be repeated byte-for-byte.

``phase_by_turn`` is an explicit scenario declaration, not a turn-index phase
inference.  Ledger rows therefore retain the scenario's protocol gate even
when a run repeats a gate or asks for approval after the opening phase.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

from dp_scenarios.ledger.lint import PHASE_ACTION_KINDS
from dp_scenarios.failure_reasons import (
    INTERRUPTED_UNCLASSIFIED,
    REVIEWER_DEADLINE_EXCEEDED,
)

from .answer_sheet import AnswerSheet
from .appender import (
    AppenderError,
    LedgerWriter,
    StaticSupervisorRecordReader,
    SupervisorRecordReader,
    TurnEvidence,
    append_turn_row,
    row_payload,
)
from .events import EventInjection, EventSchedule, event_from_mapping, inject_event
from .driver import (
    DriverBeat,
    DriverOperator,
    DriverRender,
    DriverViolation,
    DriverView,
    beat_violation,
    leading_violation,
    repeat_violation,
)
from .generated import GeneratedOperator, OperatorView
from .matcher import Category, MatchResult, MatcherBank, MatcherError, asks_for_a_choice
from .text_match import term_present
from .persona import PersonaCard
from .transport import Attachment, OperatorMessage, Transport, TurnResult, TouchedFile, ToolCall


class TerminalState(str, Enum):
    """The engine's terminal observation, before a separate grading pass."""

    COMPLETED = "completed"
    SCRIPT_EXHAUSTED = "script_exhausted"
    SENTINEL_TRIP = "sentinel_trip"
    ENVIRONMENT_WEDGE = "environment_wedge"
    TURN_TIMEOUT = "turn_timeout"


FAILURE_MODES = frozenset(
    {
        "sentinel_trip",
        "environment_wedge",
        "turn_timeout",
        "one_obstacle_per_turn",
        "intake_failure",
        "turn_budget_exceeded",
        "operator_fallback",
    }
)


class CounterReader(Protocol):
    """Injected server-side counter or call-proxy snapshot collaborator."""

    def snapshot(self) -> Mapping[str, object]:
        """Return a JSON-ready point-in-time snapshot."""


@dataclass(frozen=True, slots=True, init=False)
class ScriptTurn:
    """One declared operator turn, its substitution policy, and its role.

    ``approval`` declares that transmitting this turn *is* the operator
    approving the spec. Approval is an act of the operator, so the ledger row
    must be minted from what the operator sent, not from whether the agent
    happened to echo the word "approved" on the turn that followed. Keying it
    on the agent's wording made the intake gate measure vocabulary: an agent
    that asked for approval at the natural moment and then said "Building it
    now." was recorded as never having been approved.
    """

    text: str
    substitute_reply: bool
    approval: bool

    def __init__(
        self,
        text: str,
        substitute_reply: bool = True,
        *,
        use_reply: bool | None = None,
        approval: bool = False,
    ) -> None:
        if use_reply is not None:
            if not isinstance(use_reply, bool):
                raise TypeError("ScriptTurn.use_reply must be a boolean")
            substitute_reply = use_reply
        if not isinstance(text, str) or not text:
            raise ValueError("ScriptTurn.text must be a non-empty string")
        if not isinstance(substitute_reply, bool):
            raise TypeError("ScriptTurn.substitute_reply must be a boolean")
        if not isinstance(approval, bool):
            raise TypeError("ScriptTurn.approval must be a boolean")
        object.__setattr__(self, "text", text)
        object.__setattr__(self, "substitute_reply", substitute_reply)
        object.__setattr__(self, "approval", approval)

    @property
    def use_reply(self) -> bool:
        """Compatibility spelling for the substitution switch."""

        return self.substitute_reply

    @classmethod
    def from_value(cls, value: object) -> "ScriptTurn":
        """Normalize a string, ScriptTurn, or explicit mapping declaration."""

        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            return cls(value)
        if isinstance(value, Mapping):
            allowed = {"text", "message", "substitute_reply", "use_reply", "approval"}
            unknown = set(value) - allowed
            if unknown:
                names = ", ".join(sorted(str(name) for name in unknown))
                raise ValueError(f"script turn contains unknown key(s): {names}")
            if "text" in value and "message" in value:
                raise ValueError("script turn declares both text and message")
            text = value.get("text", value.get("message"))
            if "substitute_reply" in value and "use_reply" in value:
                raise ValueError("script turn declares both substitute_reply and use_reply")
            switch = value.get("substitute_reply", value.get("use_reply", True))
            approval = value.get("approval", False)
            if not isinstance(approval, bool):
                raise TypeError("script turn approval must be a boolean")
            return cls(text, switch, approval=approval)  # type: ignore[arg-type]
        raise TypeError("script turns must be strings, ScriptTurn values, or mappings")

    def to_mapping(self) -> dict[str, object]:
        """Return the canonical runtime-affecting declaration."""

        return {
            "text": self.text,
            "substitute_reply": self.substitute_reply,
            "approval": self.approval,
        }


@dataclass(frozen=True, slots=True)
class OperatorScript:
    """Fully resolved fixture consumed by one engine run.

    ``turn_budget`` is the declared operator-turn budget. It records when the
    fixture contains more operator turns than that budget; it does not bound
    agent calls or infer agent effort, which require transport observations.
    """

    persona: PersonaCard
    answer_sheet: AnswerSheet
    events: EventSchedule = field(default_factory=lambda: EventSchedule(()))
    turns: tuple[ScriptTurn | str | Mapping[str, object], ...] = ()
    turn_budget: int = 0  # Operator turns only; not an agent-call budget.
    sentinel: bytes | None = None
    obstacle_terms: tuple[str, ...] = ()
    phase_by_turn: Mapping[int, int] = field(default_factory=dict)
    required_plants: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        turns = self.turns or self.answer_sheet.turns
        resolved_turns = tuple(ScriptTurn.from_value(turn) for turn in turns)
        object.__setattr__(self, "turns", resolved_turns)
        if not resolved_turns:
            raise ValueError("operator script requires at least one turn")
        if resolved_turns[0].text != self.answer_sheet.opening_message:
            raise ValueError("operator script turn one must be the answer-sheet opening")
        if isinstance(self.turn_budget, bool) or not isinstance(self.turn_budget, int) or self.turn_budget < 1:
            raise ValueError("operator script turn_budget must be a positive integer")
        if self.sentinel is not None:
            marker = self.sentinel.encode("utf-8") if isinstance(self.sentinel, str) else self.sentinel
            if not isinstance(marker, bytes) or not marker:
                raise ValueError("operator script sentinel must be non-empty bytes")
            object.__setattr__(self, "sentinel", marker)
        object.__setattr__(self, "obstacle_terms", tuple(self.obstacle_terms))
        object.__setattr__(self, "required_plants", frozenset(self.required_plants) | self.events.planted_card_ids())
        _validate_plant_deliverability(self.events, resolved_turns)
        normalized_phases = {int(key): int(value) for key, value in dict(self.phase_by_turn).items()}
        if any(key < 1 or value < 1 or value > 7 for key, value in normalized_phases.items()):
            raise ValueError("phase_by_turn must map positive turns to phases 1 through 7")
        expected_turns = set(range(1, len(resolved_turns) + 1))
        if set(normalized_phases) != expected_turns:
            raise ValueError("phase_by_turn must declare exactly one phase for every operator turn")
        object.__setattr__(self, "phase_by_turn", normalized_phases)

    @classmethod
    def from_components(
        cls,
        persona: PersonaCard,
        answer_sheet: AnswerSheet,
        *,
        events: EventSchedule | Sequence[Any] = (),
        turns: Sequence[ScriptTurn | str | Mapping[str, object]] | None = None,
        turn_budget: int,
        sentinel: bytes | str | None = None,
        obstacle_terms: Sequence[str] = (),
        phase_by_turn: Mapping[int, int] | None = None,
        required_plants: Sequence[str] = (),
    ) -> "OperatorScript":
        """Build a resolved script from already validated fixture data."""

        if phase_by_turn is None:
            raise ValueError("phase_by_turn is required for every operator script")
        if isinstance(events, EventSchedule):
            schedule = events
        else:
            resolved_events = tuple(
                event_from_mapping(item) if isinstance(item, Mapping) else item for item in events
            )
            schedule = EventSchedule(resolved_events)
        return cls(
            persona=persona,
            answer_sheet=answer_sheet,
            events=schedule,
            turns=tuple(turns) if turns is not None else answer_sheet.turns,
            turn_budget=turn_budget,
            sentinel=sentinel.encode("utf-8") if isinstance(sentinel, str) else sentinel,
            obstacle_terms=tuple(obstacle_terms),
            phase_by_turn=phase_by_turn,
            required_plants=frozenset(required_plants),
        )

    def to_mapping(self) -> dict[str, object]:
        """Return only resolved script content for stable hashing."""

        answer_sheet = self.answer_sheet.to_mapping()
        # The resolved turn list below is authoritative; hashing the sheet's
        # source turn list as well would make an explicit script override count twice.
        answer_sheet.pop("turns", None)
        return {
            "persona": {
                "reply_bank": {key: list(value) for key, value in self.persona.reply_bank.items()},
                "fallback": self.persona.fallback,
                # An engine input, so script identity -- the same argument that
                # puts ``gap_stance`` in the answer sheet's mapping. Flipping a
                # persona from ``ask_back`` to ``assert_default`` changes what
                # every undeclared-answer turn says to the agent; without this
                # the paired-comparison guard would treat the two runs as the
                # same script. ``label``, ``vocabulary`` and ``behaviors`` stay
                # out: they are prompt colour, not a branch the engine takes.
                "stance_when_unknown": self.persona.stance_when_unknown,
            },
            "answer_sheet": answer_sheet,
            "events": self.events.to_mapping(),
            "turns": [
                {
                    # Every turn's text is hashed. It used to be elided for a
                    # substitutable turn on the premise that such text is never
                    # transmitted -- true until the yield rule, which sends the
                    # scripted line whenever the agent asked for nothing. Two
                    # scripts differing only in a room turn then hashed
                    # identically, so the repeatability contract did not cover
                    # bytes that actually go out.
                    "text": turn.text,
                    "substitute_reply": turn.substitute_reply,
                    "approval": turn.approval,
                }
                for index, turn in enumerate(self.turns)
            ],
            "turn_budget": self.turn_budget,
            "sentinel": _digest(self.sentinel),
            "obstacle_terms": list(self.obstacle_terms),
            "phase_by_turn": {str(key): value for key, value in self.phase_by_turn.items()},
            "required_plants": sorted(self.required_plants),
        }


def _canonical_json(value: object) -> bytes:
    # Canonical JSON's sort_keys option is the single mapping-order guarantee.
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(value: bytes | None) -> str | None:
    return hashlib.sha256(value).hexdigest() if value is not None else None


def operator_script_hash(
    script: OperatorScript | None = None,
    *,
    persona: PersonaCard | None = None,
    answer_sheet: AnswerSheet | None = None,
    events: EventSchedule | None = None,
    turns: Sequence[ScriptTurn | str | Mapping[str, object]] | None = None,
    turn_budget: int | None = None,
    sentinel: bytes | str | None = None,
    obstacle_terms: Sequence[str] = (),
    phase_by_turn: Mapping[int, int] | None = None,
    required_plants: Sequence[str] = (),
) -> str:
    """Hash resolved fixture content, independent of unrelated files."""

    if script is not None:
        if any(value is not None for value in (persona, answer_sheet, events, turns, phase_by_turn)):
            raise ValueError("provide either script or its component values")
        material = script.to_mapping()
    else:
        if persona is None or answer_sheet is None:
            raise ValueError("persona and answer_sheet are required without a script")
        if turn_budget is None:
            raise ValueError("turn_budget is required when hashing script components")
        resolved = OperatorScript.from_components(
            persona,
            answer_sheet,
            events=events or EventSchedule(()),
            turns=turns,
            turn_budget=turn_budget,
            sentinel=sentinel,
            obstacle_terms=obstacle_terms,
            phase_by_turn=phase_by_turn,
            required_plants=required_plants,
        )
        material = resolved.to_mapping()
    return hashlib.sha256(_canonical_json(material)).hexdigest()


@dataclass(frozen=True, slots=True)
class TurnRecord:
    """Evidence captured for one completed agent turn."""

    turn: int
    phase: int
    operator_message: OperatorMessage
    agent_message: str | bytes
    transcript_delta: str | bytes
    match: MatchResult
    event_ids: tuple[str, ...]
    event_outcomes: tuple[str, ...]
    tool_calls: tuple[ToolCall, ...]
    files_touched: tuple[TouchedFile, ...]
    approval_artifact: str | bytes | None
    approval_open_decision_marker: bool
    counter_snapshots: tuple[Mapping[str, object], ...]
    build_failure_count: int
    reported: bool
    intake_failure: bool
    operator_repeat_suppressed: bool = False
    operator_mode: str = "scripted"
    operator_directive: str = "answer"
    """What this turn was for; see :meth:`OperatorEngine._resolve_directive`.

    Recorded because the mechanism is otherwise invisible to the one process
    that has ever found a defect here: reading the transcript. Without it a
    room turn sent because the agent asked nothing is byte-identical to one
    sent because a substitutable turn had no reply, and a yield caused by a
    missed question looks exactly like a deliberate pause.
    """
    operator_beat_id: str | None = None
    driver_leading_rejected: bool = False
    driver_obstacle_rejected: bool = False
    driver_repeat_rejected: bool = False
    driver_beat_substituted: bool = False
    driver_fallback_reason: str | None = None
    driver_skip_reason: str | None = None
    driver_forbidden_terms_in_force: int = 0
    driver_forbidden_terms_exempted: int = 0
    terminal_result_count: int = 0
    terminal_result_subtype: str | None = None
    terminal_result_is_error: bool | None = None
    backend: str | None = None
    provider_model_calls: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class RunResult:
    """Complete engine result, including distinct grading state and evidence."""

    terminal_state: TerminalState
    script_hash: str
    turns: tuple[TurnRecord, ...]
    ledger_rows: tuple[Mapping[str, object], ...]
    failure_modes: tuple[str, ...]
    fired_event_ids: tuple[str, ...]
    fired_plant_ids: tuple[str, ...]
    ungraded_criteria: frozenset[str]
    intake_failure: bool
    stop_reason: str
    operator_mode: str = "scripted"
    driver_identity: Mapping[str, object] | None = None
    #: Closed-vocabulary reason from the transport turn that ended the run,
    #: and the sanitized text and last MCP call that went with it.  Without
    #: these an interrupted live run reaches the report as "ungraded" and
    #: nothing else, which cannot be told apart from a scenario defect.
    failure_reason: str | None = None
    failure_detail: str | None = None
    last_mcp_call: str | None = None

    @property
    def approval_records(self) -> tuple[Mapping[str, object], ...]:
        """Return approval observations, including unresolved-marker state."""

        return tuple(
            {
                "turn": record.turn,
                "artifact": record.approval_artifact,
                "open_decision_marker": record.approval_open_decision_marker,
            }
            for record in self.turns
            if record.match.category is Category.APPROVAL_REQUEST
        )

    @property
    def gradeable(self) -> bool:
        """Return whether a grader may score the run."""

        return self.terminal_state is not TerminalState.ENVIRONMENT_WEDGE

    @property
    def operator_message_bytes(self) -> bytes:
        """Return canonical operator messages for deterministic comparisons."""

        values = [
            {
                "text": message.operator_message.text,
                "attachments": [
                    {"name": item.name, "kind": item.kind, "content_sha256": hashlib.sha256(item.content).hexdigest()}
                    for item in (message.operator_message.attachments)
                ],
            }
            for message in self.turns
        ]
        return _canonical_json(values)

    @property
    def ledger_bytes(self) -> bytes:
        """Return canonical in-memory ledger rows for repeated-run checks."""

        return _canonical_json(list(self.ledger_rows))


def _as_bytes(value: object) -> tuple[bytes, ...]:
    """Extract bytes recursively without normalizing or case-folding."""

    if value is None:
        return ()
    if isinstance(value, bytes):
        return (value,)
    if isinstance(value, str):
        return (value.encode("utf-8"),)
    if isinstance(value, Path):
        try:
            return (value.read_bytes(),)
        except OSError:
            return (str(value).encode("utf-8"),)
    if isinstance(value, TouchedFile):
        return _as_bytes(value.path) + _as_bytes(value.content)
    if isinstance(value, ToolCall):
        return _as_bytes(value.name) + _as_bytes(value.arguments) + _as_bytes(value.result)
    if isinstance(value, Mapping):
        pieces: list[bytes] = []
        for key in sorted(value, key=str):
            pieces.extend(_as_bytes(key))
            pieces.extend(_as_bytes(value[key]))
        return tuple(pieces)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        pieces = []
        for item in value:
            pieces.extend(_as_bytes(item))
        return tuple(pieces)
    return (str(value).encode("utf-8"),)


def _validate_plant_deliverability(
    events: EventSchedule,
    turns: Sequence[ScriptTurn],
) -> None:
    """Reject a planted beat that no run could ever transmit.

    A planted card whose resolution yields neither text nor an attachment
    carries its beat only on the scripted turn it fires with.  When that turn
    is substitutable, a matcher reply replaces the authored line and the beat
    is silently undeliverable -- so the combination is a fixture error, caught
    when the script is built rather than discovered as a missing beat at the
    end of a paid live run.
    """

    for card in events.cards:
        if not card.plant:
            continue
        injection = inject_event(card)
        if injection.messages or injection.attachments:
            continue
        index = card.trigger_turn - 1
        if index < 0 or index >= len(turns):
            continue
        if card.trigger_turn > 1 and turns[index].substitute_reply:
            raise ValueError(
                f"planted event {card.card_id!r} has no content of its own and fires on "
                f"substitutable turn {card.trigger_turn}: the beat can never be transmitted"
            )


def _injection_delivered(
    injection: EventInjection,
    message: OperatorMessage,
    scripted_text: str,
) -> bool:
    """Return whether this card's beat is present in the transmitted message.

    Delivery is read off the message that actually goes to the agent, never
    off the intention to fire.  Declared ``required_terms`` are authoritative
    when present; otherwise the card's own resolved material (its text, or the
    attachment that stands in for it) must be there, and a card that carries
    no material of its own rides on the authored scripted line.
    """

    text = message.text
    if injection.required_terms:
        folded = text.casefold()
        return all(term.casefold() in folded for term in injection.required_terms)
    expected_messages = (
        () if (injection.replace_message and injection.attachments) else injection.messages
    )
    if expected_messages:
        return all(part in text for part in expected_messages)
    if injection.attachments:
        names = {item.name for item in message.attachments}
        return all(item.name in names for item in injection.attachments)
    return scripted_text in text


_SUPPRESSIBLE_RULE_PREFIXES = (
    "ground_truth.",
    "source.answer.",
    "status.answer.",
)


def _served_reply_key(rule_id: str) -> str | None:
    """Return the answer-sheet key of a match that states a declared fact.

    Source, ground-truth, and status answer-sheet lookups are suppressible. A
    declared decision answer is deliberately excluded: a fresh review
    generation may ask for the same authorization again and must receive the
    same answer. Persona replies (``persona.approval_request``) and fallbacks
    (``fallback.no-leading``) are not facts either: repeating "go ahead" or
    the no-leading deflection is in character. Memory is keyed to the
    *selected* sheet key, not to the text that went out, because a generated
    operator paraphrases the reply -- no fact text survives as a substring,
    so a text scan would leave the memory permanently empty and the
    suppression inert.
    """

    return rule_id if rule_id.startswith(_SUPPRESSIBLE_RULE_PREFIXES) else None


def _operator_context(value: str | bytes, sentinels: Sequence[bytes]) -> str:
    """Redact planted sentinel values before context reaches a provider."""

    text = value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value
    for marker in sentinels:
        decoded = marker.decode("utf-8", errors="replace")
        if decoded:
            text = text.replace(decoded, "<redacted-sentinel>")
    return text


def _snapshot(reader: object) -> Mapping[str, object]:
    if callable(reader):
        value = reader()
    elif hasattr(reader, "snapshot"):
        value = reader.snapshot()  # type: ignore[attr-defined]
    elif hasattr(reader, "read"):
        value = reader.read()  # type: ignore[attr-defined]
    else:
        raise TypeError("counter collaborator must provide snapshot(), read(), or be callable")
    if not isinstance(value, Mapping):
        raise TypeError("counter snapshot must be a mapping")
    return dict(value)


def _artifact_text(artifact: str | bytes | None) -> str:
    """Return an approval artifact as text, empty when the agent supplied none."""

    if isinstance(artifact, bytes):
        return artifact.decode("utf-8", errors="replace")
    return artifact or ""


def _qualification_for(
    match: MatchResult | None,
    claim: Mapping[str, object] | None,
    *,
    operator_approval: bool = False,
) -> str | None:
    """Return the evidence qualification a row's claim requires.

    The lint rejects any claim-bearing row without a qualification from the closed
    vocabulary, so every path that attaches a claim must supply one. An approval is
    an operator act observed directly, so it is ``strong``; an event outcome or a
    counter snapshot describes only the attempt that produced it, so it is
    ``strong-for-this-attempt``. A row with no claim carries no qualification.
    """
    if operator_approval:
        return "strong"
    if match is not None and match.approval_requested:
        return "strong"
    if claim:
        return "strong-for-this-attempt"
    return None


#: Words too common to be evidence that a fact was conveyed.
_CONVEYANCE_STOPWORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "in", "on", "of", "to", "that", "this",
    "it", "its", "and", "or", "not", "for", "you", "your", "i", "my", "me", "do",
    "have", "any", "there", "those", "their", "them", "they", "as", "at", "by",
    "with", "from", "be", "has", "had", "one", "no", "if", "so", "but", "we",
    "us", "our", "can", "will", "would", "should", "must", "may", "when",
    "where", "what", "which", "who", "how",
})

#: A fact counts as conveyed when the authored turn carries at least three of
#: the reply's distinctive words *and* at least this fraction of them.
#: Calibrated against real driven turns: genuine restatements scored 0.45-0.89
#: while deflections and bare echoes scored 0.00.
#:
#: The three-word floor is what does the work almost everywhere -- the ratio
#: only becomes the stricter of the two at nine distinctive words, where a
#: third first exceeds three. Below that, three words is the whole rule.
_CONVEYANCE_RATIO = 0.34

#: Three, not two. A deflection tends to pick up a couple of the reply's words
#: incidentally, and with a two-word floor the ratio did not bind until six --
#: so at four and five distinctive words a two-word deflection cleared both and
#: consumed the fact. Three is above what an incidental mention produces and
#: below what a genuine restatement carries: the real driven turns this was
#: calibrated on carried five, eight and nine. It also subsumes the special
#: case short replies used to need -- with a three-word floor, three
#: distinctive words already require all three.
_CONVEYANCE_MINIMUM = 3


def _content_words(text: str) -> set[str]:
    return {
        word
        for word in re.findall(r"[a-z0-9]+", (text or "").casefold())
        if len(word) > 2 and word not in _CONVEYANCE_STOPWORDS
    }


def _authored_text_conveys(reply: str, agent_message: str, authored: str) -> bool:
    """Whether an authored turn actually carried the selected reply's substance.

    The distinctive words are the reply's own, *minus* everything already in
    the agent's message. That subtraction is what makes this safe: a fact's
    trigger terms come from the question, so a driver that merely echoes the
    agent -- "the owner field? you tell me" -- shares nothing with what is left
    and scores zero, which is exactly the deflection case that must not consume
    the fact.
    """

    # A short reply needs no guard of its own: ``carried`` is a subset of
    # ``distinctive``, so the minimum below already refuses anything smaller
    # than it. That includes the empty set, where the ``and`` short-circuits
    # before the ratio would divide by zero -- keep the minimum as the first
    # operand.
    distinctive = _content_words(reply) - _content_words(agent_message)
    carried = distinctive & _content_words(authored)
    return len(carried) >= _CONVEYANCE_MINIMUM and len(carried) / len(distinctive) >= _CONVEYANCE_RATIO


class OperatorEngine:
    """Run one resolved script against an injected offline transport."""

    _DEFAULT_ACTION_KIND_BY_PHASE = {
        1: "intake",
        2: "capability_probe",
        3: "narrowing",
        4: "codegen",
        5: "build",
        6: "query",
        7: "follow_up",
    }

    def __init__(
        self,
        script: OperatorScript,
        transport: Transport,
        *,
        ledger_writer: LedgerWriter | None = None,
        supervisor_reader: SupervisorRecordReader | None = None,
        counter_readers: Sequence[object] = (),
        generated_operator: GeneratedOperator | None = None,
        driver: DriverOperator | None = None,
        extra_sentinels: Sequence[bytes | str] = (),
    ) -> None:
        if generated_operator is not None and driver is not None:
            raise ValueError("an engine takes a generated operator or a driver, never both")
        if driver is not None and not script.answer_sheet.driver_forbidden_terms:
            # Fail closed at construction, not on the first authored turn.
            # Without a declared vocabulary the leading check has nothing to
            # test, so a driver would be free to hand the agent the answer and
            # the run would still be recorded as evidence.
            raise ValueError(
                "a driver requires the answer sheet key driver_forbidden_terms; it is missing or empty"
            )
        self.script = script
        self.transport = transport
        self.driver = driver
        self.ledger_writer = ledger_writer
        self.supervisor_reader = supervisor_reader
        self._run_id: str | None = None
        self._ledger_supervisor_reader: SupervisorRecordReader | None = None
        if ledger_writer is not None:
            if supervisor_reader is None:
                raise AppenderError("ledger writes require a supervisor record reader")
            if hasattr(supervisor_reader, "read_facts"):
                facts = supervisor_reader.read_facts()
            elif hasattr(supervisor_reader, "read"):
                facts = supervisor_reader.read()  # type: ignore[attr-defined]
            else:
                raise AppenderError("supervisor record reader has no read_facts method")
            if not hasattr(facts, "run_id") or not isinstance(facts.run_id, str) or not facts.run_id:
                raise AppenderError("supervisor record reader returned no non-empty run_id")
            self._run_id = facts.run_id
            self._ledger_supervisor_reader = StaticSupervisorRecordReader(facts)
        self.counter_readers = tuple(counter_readers)
        self.generated_operator = generated_operator
        # Planted markers live in the generated fixture, not in the scenario's
        # operator block: a scenario may declare no ``operator.sentinel`` and
        # still plant PII the agent can echo back.  These widen redaction
        # before an external provider only; ``_scan`` keeps tripping on the
        # declared sentinels alone, since a marker in a read tool result is
        # something the agent may legitimately see and must not fail a run.
        self.extra_sentinels = tuple(
            value.encode("utf-8") if isinstance(value, str) else bytes(value)
            for value in extra_sentinels
            if value
        )
        event_material: list[str | bytes] = []
        for card in script.events.cards:
            event_material.extend(
                value
                for value in (card.content, card.attachment_name, card.wrong_key, card.right_secret, card.attachment_bytes)
                if value is not None
            )
        self.matcher = MatcherBank(
            script.persona,
            script.answer_sheet,
            obstacle_terms=(*script.obstacle_terms, *script.answer_sheet.obstacle_terms),
            extra_material=event_material,
        )
        self._script_declares_approval = any(turn.approval for turn in script.turns)
        self.phase = 1
        self.turn_pointer = 0
        self.failure_modes: list[str] = []
        self.ledger_rows: list[Mapping[str, object]] = []

    def _provider_view(
        self,
        *,
        turn: int,
        active_sentinels: Sequence[bytes],
        pending_sentinels: Sequence[bytes],
        previous_agent_message: str,
        prior_agent_messages: Sequence[str],
        prior_operator_messages: Sequence[str],
        selected_reply: str,
        known_facts: Sequence[tuple[str, str]] = (),
        facts_already_stated: Sequence[str] = (),
        beat: DriverBeat | None = None,
        forbidden_terms: Sequence[str] = (),
        rejection_notice: str | None = None,
        directive: str = "answer",
    ) -> OperatorView | DriverView:
        """Build the one redacted view shared by generated and driver paths."""

        markers = self._redaction_markers((*active_sentinels, *pending_sentinels))
        context = lambda value: _operator_context(value, markers)
        common = {
            "turn": turn,
            "phase": self.phase,
            "persona": self.script.persona,
            "agent_message": context(previous_agent_message),
            "selected_reply": context(selected_reply),
            "prior_operator_messages": tuple(context(message) for message in prior_operator_messages),
            "remaining_turns": len(self.script.turns) - turn + 1,
        }
        if self.driver is None:
            return OperatorView.from_persona(**common)  # type: ignore[arg-type]
        return DriverView(
            turn=common["turn"],
            phase=common["phase"],
            persona_id=self.script.persona.id,
            persona_label=self.script.persona.label,
            persona_vocabulary=tuple(self.script.persona.vocabulary),
            persona_behaviors=tuple(
                sorted(str(key) for key, value in self.script.persona.behaviors.items() if value)
            ),
            agent_message=common["agent_message"],
            selected_reply=common["selected_reply"],
            prior_operator_messages=common["prior_operator_messages"],
            remaining_turns=common["remaining_turns"],
            prior_agent_messages=tuple(context(message) for message in prior_agent_messages[-2:]),
            known_facts=tuple((key, context(fact)) for key, fact in known_facts),
            facts_already_stated=tuple(facts_already_stated),
            beat=beat,
            forbidden_terms=tuple(forbidden_terms),
            rejection_notice=rejection_notice,
            directive=directive,
        )

    def _driver_facts(self) -> tuple[tuple[str, str], ...]:
        """Offer the whole ground-truth brief to the driver.

        This used to filter the brief by keyword-matching each fact's
        ``terms`` against the current agent message, which starved the driver
        precisely when a question was phrased unexpectedly: a live 15-turn run
        was handed zero facts on four turns and a single fact -- always the
        same one, because ``owner`` is a common word -- on four more.

        Filtering here was the wrong place for two reasons. A fact's ``terms``
        trigger the *question*, so matching them against one message asks
        whether the agent used the author's vocabulary, not whether the fact
        is relevant. And the brief is not secret: every entry is something
        this operator genuinely knows and would say if asked. What must not
        happen is the operator *volunteering* an unasked fact, and that is a
        prompt rule, enforced by the same forbidden-term scan every authored
        message already passes -- not a retrieval problem.
        """

        return tuple(
            (key, fact.fact)
            for key, fact in sorted(self.script.answer_sheet.ground_truth.items())
        )

    def _facts_triggered_by(
        self,
        agent_message: str,
        *,
        markers: Sequence[bytes],
    ) -> tuple[str, ...]:
        """Return facts whose declared ``terms`` this message actually asks for.

        This is the old ``_driver_facts`` filter, kept for the one job it was
        always right for: deciding which forbidden terms to exempt. A fact the
        agent asked for may be stated even when it contains graded vocabulary,
        because the agent has already reached that vocabulary itself. A fact
        nobody asked about may not -- stating it unprompted *is* the leading
        the guard exists to catch.

        Separating the two is what makes offering the whole brief safe.
        Exempting from every offered fact instead would have retired
        ``driver_forbidden_terms`` altogether the moment the brief was widened,
        silently: the leading scan would still run, with nothing left in it.
        """

        redacted = _operator_context(agent_message, markers).casefold()
        return tuple(
            fact.fact
            for _, fact in sorted(self.script.answer_sheet.ground_truth.items())
            if fact.terms and all(term_present(term, redacted) for term in fact.terms)
        )

    def _resolve_directive(
        self,
        match: "MatchResult | None",
        *,
        answer_available: bool,
        agent_message: str = "",
    ) -> str:
        """Compose the operator's job for this turn from scenario and persona.

        The two axes are asymmetric on purpose. The scenario owns what a gap
        *means* here -- whether the source is genuinely short or the operator
        is merely uninformed -- because only the answer sheet can be checked
        against the gold the run is graded on. The persona owns the *tactic*
        for handing a decision back, because that is voice and carries no
        factual claim. Neither file has to know the other's half.

        ``answer`` is the only value under which the driver is handed
        ``selected_reply`` as substance to convey. Everything else describes
        a turn where the operator has nothing declared to say, and the whole
        point is that those turns are no longer indistinguishable from one
        another -- previously they all arrived as a persona stock sentence
        the driver was told to paraphrase.
        """

        if match is None:
            return "answer"
        # ``answer_available`` is false when the reply was repeat-suppressed:
        # the fact is declared but has already been given, so this turn has
        # nothing to convey. Reading ``substantive_answer`` alone handed the
        # driver ``directive="answer"`` with an empty ``selected_reply`` --
        # substance the prompt says is there and is not -- which is an
        # invitation to invent one.
        if answer_available and match.substantive_answer:
            return "answer"
        if not match.solicits_operator:
            return "yield"
        # A choice is a choice whatever else the message mentions. The rule
        # bank is first-match-wins with ``source.question`` first, and that
        # rule fires on vocabulary too common to be evidence of anything, so
        # "Which path should I take? Both are in the data." arrives here
        # classified as a source question. Answering "I do not have that"
        # leaves the choice unmade, which is the stall this whole change is
        # about.
        # Obstacle first, before the choice override. "Which option: request
        # write permission, or proceed read-only?" is choice-shaped, but
        # handing it to a persona whose stance is ``assert_default`` asks for a
        # firm opinion about infrastructure -- the one thing the no-leading
        # guard exists to prevent. It is also not a claim the answer sheet ever
        # made about the source, so the scenario's gap stance does not apply
        # here either: this operator simply does not know.
        if match.obstacle_question:
            return "unknown_fact:operator_is_uninformed"
        # ``decision.request`` fires on a bare "?" (``matcher._RULES``), so the
        # category alone is not evidence that a decision was put to the
        # operator: "What is the status?" lands there. Require the choice
        # vocabulary, or an explicit approval ask, whose verbs are unambiguous.
        if asks_for_a_choice(agent_message) or match.category is Category.APPROVAL_REQUEST:
            return f"decision:{self.script.persona.stance_when_unknown}"
        if match.category is Category.SOURCE_QUESTION:
            return f"unknown_fact:{self.script.answer_sheet.gap_stance}"
        # A status question ("is it done on your side?") and a miscellaneous
        # one are never about what the *source* can supply, so the scenario's
        # gap stance does not apply: this operator simply does not know.
        return "unknown_fact:operator_is_uninformed"

    def _driver_check(
        self,
        text: str,
        *,
        forbidden: Sequence[str],
        exempt_texts: Sequence[str],
        prior_base_texts: Sequence[str],
        beat: DriverBeat | None,
        sentinels: Sequence[bytes] = (),
    ) -> DriverViolation | None:
        """Apply the driver rejection ladder in its contractual order."""

        for marker in sentinels:
            decoded = marker.decode("utf-8", errors="replace")
            # Redaction keeps markers out of the view, so an authored one is
            # either a coincidence or a provider that saw it elsewhere; either
            # way the operator's own turn must not carry a planted marker into
            # the transcript, the ledger, or the next turn's provider context.
            # The detail is deliberately marker-free: it is echoed back to the
            # provider as the rejection notice.
            if decoded and decoded in text:
                return DriverViolation("obstacle", "authored message repeats a planted marker")
        try:
            self.matcher.validate_generated_surface(text)
        except MatcherError as exc:
            return DriverViolation("obstacle", str(exc))
        detail = leading_violation(text, forbidden_terms=forbidden, exempt_texts=exempt_texts)
        if detail is not None:
            return DriverViolation("leading", detail)
        detail = repeat_violation(text, prior_base_texts)
        if detail is not None:
            return DriverViolation("repeat", detail)
        detail = beat_violation(text, beat)
        if detail is not None:
            return DriverViolation("beat", detail)
        return None

    def _message_for(self, base: str, injections: tuple[EventInjection, ...]) -> OperatorMessage:
        attachments = tuple(
            Attachment(item.name, item.content, item.kind)
            for injection in injections
            for item in injection.attachments
        )
        message_parts = [
            message
            for injection in injections
            for message in injection.messages
            # Replacement belongs to the event card: its attachment stands in
            # for that card's text, never for the operator's scripted message.
            if not (injection.replace_message and injection.attachments)
        ]
        text = "\n".join((base, *message_parts)) if message_parts else base
        return OperatorMessage(text, attachments)

    def _redaction_markers(self, active_sentinels: Sequence[bytes]) -> tuple[bytes, ...]:
        """Return every marker that must be redacted out of provider context.

        This is deliberately wider than the set ``_scan`` trips on: the trip
        gate is graded against the tier's leakable-surface policy (a marker in
        a *read* result is not a leak), while redaction is unconditional --
        nothing planted may be forwarded to an external model provider.
        """

        markers = list(active_sentinels)
        markers.extend(marker for marker in self.extra_sentinels if marker not in markers)
        return tuple(markers)

    def _scan(self, result: TurnResult, markers: Sequence[bytes]) -> bool:
        if not markers:
            return False
        values: list[object] = [result.agent_message, result.transcript_delta, result.tool_results, result.tool_calls, result.files_touched]
        for value in values:
            for marker in markers:
                if any(marker in bytes_value for bytes_value in _as_bytes(value)):
                    return True
        return False

    def _turn_phase(self, turn: int) -> int:
        value = self.script.phase_by_turn[turn]
        self.phase = value
        return value

    def _append_row(
        self,
        turn: int,
        phase: int,
        match: MatchResult | None,
        event_ids: tuple[str, ...],
        approval_artifact: str | bytes | None,
        approval_marker: bool,
        *,
        claim: object = None,
        phase_status: str = "executed",
        phase_status_reason: str | None = None,
        operator_approval: bool = False,
        operator_approval_text: str | None = None,
        operator_mode: str = "scripted",
        operator_directive: str = "answer",
        operator_beat_id: str | None = None,
        driver_leading_rejected: bool = False,
        driver_obstacle_rejected: bool = False,
        driver_repeat_rejected: bool = False,
        driver_beat_substituted: bool = False,
    ) -> None:
        detail = "operator response selected" if match is not None else (phase_status_reason or "phase not reached")
        action_kind = self._DEFAULT_ACTION_KIND_BY_PHASE[phase]
        artifact_ref: str | None = None
        if operator_approval:
            # The operator approved. The evidence is what the operator
            # transmitted, which is why this row does not consult the match at
            # all: what the agent said on this turn cannot make an approval
            # that was sent stop counting, nor manufacture one that was not.
            claim = dict(claim) if isinstance(claim, Mapping) else {}
            if "spec_approved" in PHASE_ACTION_KINDS[phase]:
                action_kind = "spec_approved"
            else:
                claim["approval_out_of_phase"] = True
            detail = "operator approved the spec"
            artifact_ref = operator_approval_text or None
            # Whether the operator approved and whether the agent had anything
            # to approve are two different facts, and the row must carry both.
            # Keying this claim on the operator's own sentence would make it
            # unreachable -- an approval turn always has text, or
            # validate_outgoing_message would have rejected it before send --
            # and a run where the agent presented nothing at all would then be
            # indistinguishable from one that presented a spec.
            if not _artifact_text(approval_artifact):
                claim["approval_without_artifact"] = True
        elif match is not None and match.approval_requested and not self._script_declares_approval:
            # Legacy path: the script never declares who approves, so the only
            # available signal is the agent soliciting approval. A script that
            # declares its own approval turn owns approval outright and this
            # branch is off, so the row can never key on agent vocabulary.
            if claim is None:
                claim = {"open_decision_marker": approval_marker}
            claim = dict(claim) if isinstance(claim, Mapping) else {}
            approval_artifact_text = _artifact_text(approval_artifact)
            if "spec_approved" in PHASE_ACTION_KINDS[phase]:
                action_kind = "spec_approved"
            else:
                claim["approval_out_of_phase"] = True
            if approval_artifact_text:
                artifact_ref = approval_artifact_text
            else:
                detail = "approval without artifact"
                claim["approval_without_artifact"] = True
        matched_rule_id = match.rule_id if match is not None else None
        if operator_mode != "scripted":
            claim = dict(claim) if isinstance(claim, Mapping) else {}
            claim["operator_mode"] = operator_mode
        if operator_directive != "answer":
            claim = dict(claim) if isinstance(claim, Mapping) else {}
            claim["operator_directive"] = operator_directive
        if operator_beat_id is not None:
            claim = dict(claim) if isinstance(claim, Mapping) else {}
            claim["operator_beat_id"] = operator_beat_id
        for name, value in (
            ("driver_leading_rejected", driver_leading_rejected),
            ("driver_obstacle_rejected", driver_obstacle_rejected),
            ("driver_repeat_rejected", driver_repeat_rejected),
            ("driver_beat_substituted", driver_beat_substituted),
        ):
            if value:
                claim = dict(claim) if isinstance(claim, Mapping) else {}
                claim[name] = True
        evidence = TurnEvidence(
            run_id=self._run_id or "",
            scenario_id=self.script.answer_sheet.scenario_id,
            turn=turn,
            phase=phase,
            action_kind=action_kind,
            detail=detail,
            matched_rule_id=matched_rule_id,
            event_ids=event_ids,
            artifact_ref=artifact_ref,
            claim=claim,
            evidence_ref=f"operator#turn-{turn}" if match is not None else f"operator#phase-{phase}-not-applicable",
            qualification=_qualification_for(match, claim, operator_approval=operator_approval),
            phase_status=phase_status,
            phase_status_reason=phase_status_reason,
        )
        if self.ledger_writer is not None:
            payload = append_turn_row(self.ledger_writer, evidence, supervisor_reader=self._ledger_supervisor_reader)
        else:
            payload = row_payload(evidence)
        self.ledger_rows.append(dict(payload))

    def _append_not_applicable_rows(self, records: Sequence[TurnRecord], terminal_state: str) -> None:
        """Account for every protocol phase that the run did not reach."""

        reached = {record.phase for record in records}
        terminal_turn = records[-1].turn if records else 1
        last_phase = records[-1].phase if records else "none"
        reason = f"phase not reached; last phase reached: {last_phase}; terminal state: {terminal_state}"
        for phase in range(1, 8):
            if phase in reached:
                continue
            self._append_row(
                terminal_turn,
                phase,
                None,
                (),
                None,
                False,
                phase_status="not-applicable",
                phase_status_reason=reason,
            )

    def run(self) -> RunResult:
        """Execute every resolved turn and return a full grading record.

        The opening turn is an intake contract: a first agent response that is
        not a source question records ``intake_failure``, including a decision
        question. The scripted operator-turn budget is observed independently
        from agent-call effort.
        """

        script_hash = operator_script_hash(self.script)
        self.transport.start_fresh_session()
        records: list[TurnRecord] = []
        fired_events: list[str] = []
        fired_plants: list[str] = []
        active_sentinels: list[bytes] = [self.script.sentinel] if self.script.sentinel is not None else []
        pending_failure = False
        sentinel_tripped = False
        environment_wedged = False
        turn_timed_out = False
        failure_reason: str | None = None
        failure_detail: str | None = None
        last_mcp_call: str | None = None
        next_reply: str | None = None
        next_match: MatchResult | None = None
        pending_sheet_key: str | None = None
        served_reply_keys: set[str] = set()
        previous_agent_message = ""
        prior_agent_messages: list[str] = []
        prior_base_texts: list[str] = []
        prior_operator_messages: list[str] = []

        for index, scripted_turn in enumerate(self.script.turns, start=1):
            self.turn_pointer = index - 1
            injections = self.script.events.fire(index)
            # A card's sentinel arms the trip scan only once the card is
            # actually transmitted; an intention to fire cannot plant anything
            # the agent could leak, and scanning for it can only manufacture a
            # false trip. Redaction stays keyed to intention (below), because
            # it is unconditional: nothing planted may reach a provider.
            pending_sentinels = tuple(
                injection.sentinel_bytes
                for injection in injections
                if injection.sentinel_bytes is not None
            )
            if any(injection.fresh_session for injection in injections):
                self.transport.start_fresh_session()
                served_reply_keys.clear()
            # The ``spec_approved`` row's ``artifact_ref`` is minted from what
            # the operator actually sent, so an approval turn transmits its
            # declared line: substituting a matcher reply there would record
            # some unrelated sentence -- or a refusal -- as the approval.
            directive = self._resolve_directive(
                next_match,
                answer_available=next_reply is not None,
                # Assigned at the foot of the previous iteration, so this is
                # the message the pending reply was selected from.
                agent_message=previous_agent_message,
            )
            # Turn one, a non-substitutable turn and an approval turn all
            # transmit their declared line whatever the directive says, so
            # recording one there would put a value in the ledger that governed
            # nothing -- and it changed the ``spec_approved`` row's claim shape,
            # which is evidence other things read.
            #
            # Without a driver the same is true of every value except
            # ``yield``: the matcher's reply goes out unchanged, so a
            # ``decision:*`` on a scripted row would tell a reader the operator
            # handed a decision back when it did nothing of the kind. Scripted
            # is the default mode, so that is most rows of most runs -- and the
            # whole reason to record the field is that reading these lines is
            # what finds defects here.
            yielding = directive == "yield"
            directive_governs = (
                index > 1
                and scripted_turn.substitute_reply
                and not scripted_turn.approval
                and (self.driver is not None or yielding)
            )
            recorded_directive = directive if directive_governs else "answer"
            # The yield rule is not driver-specific, and applying it only
            # there would leave the scripted operator answering a status
            # update with a refusal. When the agent asked for nothing, the
            # author's own script is what the turn is for: "Keep going,
            # please." / "Take your time." were written as room to let the
            # agent work, and until now they were unreachable text, because
            # ``next_reply`` is falsy only after a repeat suppression and the
            # matcher always returns something.
            base = (
                scripted_turn.text
                if index == 1
                or not scripted_turn.substitute_reply
                or scripted_turn.approval
                or yielding
                else (next_reply or scripted_turn.text)
            )
            selected_base = base
            operator_mode = "scripted"
            operator_beat_id: str | None = None
            driver_leading_rejected = False
            driver_obstacle_rejected = False
            driver_repeat_rejected = False
            driver_beat_substituted = False
            driver_fallback_reason: str | None = None
            driver_skip_reason: str | None = None
            driver_forbidden_terms_in_force = 0
            driver_forbidden_terms_exempted = 0
            driver_render: DriverRender | None = None
            driver_known_facts: tuple[tuple[str, str], ...] = ()
            driver_fallback_transmitted = False
            driver_selected_reply: str | None = None

            authorable = (
                self.driver is not None
                and index > 1
                and scripted_turn.substitute_reply
                and not scripted_turn.approval
            )
            if self.driver is not None and not authorable:
                driver_skip_reason = (
                    "turn_one"
                    if index == 1
                    else "approval"
                    if scripted_turn.approval
                    else "non_substitutable"
                )
            if authorable:
                redaction_markers = self._redaction_markers((*active_sentinels, *pending_sentinels))
                driver_known_facts = self._driver_facts()
                # Only a declared answer is handed over as substance to
                # convey. A persona stock line is a placeholder the scripted
                # operator uses to fill a turn; passing it as
                # ``selected_reply`` made the driver paraphrase it under the
                # prompt's "say that substance in your own words" rule, which
                # is how "I am not deciding that." became seven distinct
                # refusals in one run. When there is nothing declared, the
                # directive says what kind of turn this is and the driver
                # authors it in the persona's voice.
                driver_selected_reply = next_reply if directive == "answer" else None
                forbidden = tuple(dict.fromkeys(self.script.answer_sheet.driver_forbidden_terms))
                exempt_texts = (
                    _operator_context(previous_agent_message, redaction_markers),
                    *(
                        _operator_context(fact, redaction_markers)
                        for fact in self._facts_triggered_by(
                            previous_agent_message, markers=redaction_markers
                        )
                    ),
                    _operator_context(driver_selected_reply or "", redaction_markers),
                )
                exempted = tuple(
                    term for term in forbidden
                    if any(term_present(term, text.casefold()) for text in exempt_texts)
                )
                effective_forbidden = tuple(term for term in forbidden if term not in exempted)
                beat = (
                    DriverBeat(
                        beat_id="+".join(injection.card_id for injection in injections),
                        required_terms=tuple(
                            dict.fromkeys(
                                term
                                for injection in injections
                                for term in injection.required_terms
                            )
                        ),
                    )
                    if injections
                    else None
                )
                operator_beat_id = beat.beat_id if beat is not None else None
                driver_forbidden_terms_in_force = len(effective_forbidden)
                driver_forbidden_terms_exempted = len(exempted)
                view = self._provider_view(
                    turn=index,
                    active_sentinels=active_sentinels,
                    pending_sentinels=pending_sentinels,
                    previous_agent_message=previous_agent_message,
                    prior_agent_messages=prior_agent_messages,
                    prior_operator_messages=prior_operator_messages,
                    selected_reply=driver_selected_reply or "",
                    known_facts=driver_known_facts,
                    facts_already_stated=tuple(sorted(served_reply_keys)),
                    beat=beat,
                    forbidden_terms=effective_forbidden,
                    directive=directive,
                )
                assert self.driver is not None
                # A rejected authored turn falls back to the author's script
                # rather than to a persona stock line, for the same reason the
                # driver is not handed one: the scripted turn is what the
                # scenario was written to say here.
                fallback = driver_selected_reply or scripted_turn.text
                driver_render = self.driver.author(
                    view,  # type: ignore[arg-type]
                    fallback=fallback,
                    check=lambda text: self._driver_check(
                        text,
                        forbidden=forbidden,
                        exempt_texts=exempt_texts,
                        prior_base_texts=prior_base_texts,
                        beat=beat,
                        sentinels=redaction_markers,
                    ),
                )
                base = driver_render.text
                operator_mode = "driver_fallback" if driver_render.used_fallback else "driver"
                driver_fallback_reason = driver_render.reason
                driver_leading_rejected = driver_render.reason == "driver_leading_rejected"
                driver_obstacle_rejected = driver_render.reason == "driver_obstacle_rejected"
                driver_repeat_rejected = driver_render.reason == "driver_repeat_rejected"
                # A beat rejection already selected the safe scripted line;
                # record that substitution just like a post-composition beat
                # repair below.
                driver_beat_substituted = driver_render.reason == "driver_beat_rejected"
                driver_fallback_transmitted = driver_render.used_fallback
                if driver_render.used_fallback and "operator_fallback" not in self.failure_modes:
                    self.failure_modes.append("operator_fallback")
            elif (
                index > 1
                and scripted_turn.substitute_reply
                # An approval turn transmits its declared line on this
                # path too.  ``authorable`` and ``base`` both honour
                # that; this branch did not, so a scenario declaring an
                # approval turn without overriding ``substitute_reply``
                # (which defaults to True) would record a paraphrase of
                # some unrelated matcher reply -- or a refusal -- as the
                # approval, and that text becomes the ``spec_approved``
                # ledger row's ``artifact_ref``.
                and not scripted_turn.approval
                and next_reply
                # The yield rule is path-independent: a rendered persona line
                # is still a refusal nobody asked for.
                and not yielding
                and self.generated_operator is not None
            ):
                view = self._provider_view(
                    turn=index,
                    active_sentinels=active_sentinels,
                    pending_sentinels=pending_sentinels,
                    previous_agent_message=previous_agent_message,
                    prior_agent_messages=prior_agent_messages,
                    prior_operator_messages=prior_operator_messages,
                    selected_reply=next_reply,
                )
                rendered = self.generated_operator.render(
                    view,
                    fallback=next_reply,
                    validate=self.matcher.validate_generated_surface,
                )
                base = rendered.text
                operator_mode = "generated_surface" if not rendered.used_fallback else "scripted"
                if rendered.used_fallback and "operator_fallback" not in self.failure_modes:
                    self.failure_modes.append("operator_fallback")
            message = self._message_for(base, injections)
            # A card counts as fired only once its beat is in the text that
            # actually goes out; an intention to fire is not a transmission.
            delivered = tuple(
                injection
                for injection in injections
                if _injection_delivered(injection, message, scripted_turn.text)
            )
            delivered_ids = {injection.card_id for injection in delivered}
            undelivered_ids = tuple(
                injection.card_id for injection in injections if injection.card_id not in delivered_ids
            )
            if authorable and driver_render is not None and not driver_render.used_fallback and undelivered_ids:
                # A provider may pass the pure beat check for a content-only
                # card whose resolved material has no declared terms.  Give
                # the deterministic engine's delivery predicate the final
                # word and repair from the scripted composition.
                base = driver_selected_reply or scripted_turn.text
                message = self._message_for(base, injections)
                driver_beat_substituted = True
                driver_fallback_transmitted = True
                operator_mode = "driver_fallback"
                # This is an operator fallback by every other signal it sets --
                # the authored words were replaced by the scripted line -- but
                # it was the one fallback path that never recorded the failure
                # mode.  The run-level summary reads ``failure_modes`` to decide
                # whether the driver spoke on every substitutable turn, so
                # omitting it here made that line claim a fully authored run
                # while a turn had gone out scripted.
                if "operator_fallback" not in self.failure_modes:
                    self.failure_modes.append("operator_fallback")
                delivered = tuple(
                    injection
                    for injection in injections
                    if _injection_delivered(injection, message, scripted_turn.text)
                )
                delivered_ids = {injection.card_id for injection in delivered}
                undelivered_ids = tuple(
                    injection.card_id for injection in injections if injection.card_id not in delivered_ids
                )
            # Driver-authored words are never scanned for a fact's ``terms``.
            # ``_authored_text_conveys`` reads the reply's own content instead,
            # for the reason set out here: a
            # ground-truth fact's ``terms`` are the *question*'s trigger terms
            # (``AnswerSheet.answer_for_ground_truth`` matches them against the
            # agent's message), not the fact's content, so scanning authored
            # text for them marks a fact served whenever the driver echoes the
            # agent's own word -- "which endpoint do you mean?" would record
            # the endpoint answer as given and suppress it for the rest of the
            # run. Memory stays keyed to a *selected* sheet key that was
            # actually transmitted, which is the rule the block below applies
            # on every path.
            #
            # A fact counts as served when it is actually transmitted, not
            # when it is selected. ``selected_base is next_reply`` is the one
            # test for that on every path: a reply selected on the turn before
            # a ``substitute_reply: false`` ask, or before an approval turn,
            # is never sent, and marking it here would suppress an answer the
            # agent has still never been given.
            #
            # On the driver path the scripted sentence never goes out, so
            # transmission is decided by whether the authored turn carried the
            # reply's substance. Leaving that unmeasured -- the previous
            # behaviour -- kept the memory empty for a whole driven run: a live
            # 15-turn run re-selected one fact ten times and another six, with
            # zero suppressions, while the agent answered "already done" four
            # turns running. That is the operator-repeats-itself failure the
            # driver exists to remove, reproduced by the driver.
            #
            # A driver that authors the turn is handed ``selected_reply`` and
            # told to convey it, and ``_authored_text_conveys`` is what checks
            # that it did.  Consuming the key on driver success *alone* would
            # be wrong -- a driver is free to deflect ("I am not sure about the
            # grain, ask me later"), and since only a ``fresh_session`` card
            # clears ``served_reply_keys``, marking the fact there would
            # stonewall the agent on that question for the rest of the run.
            # That is why the check subtracts the agent's own message: a fact's
            # terms trigger the *question*, so an echo carries none of what is
            # left.  Do not replace it with a bare ``not used_fallback``.
            driver_conveyed = (
                authorable
                and driver_render is not None
                and not driver_render.used_fallback
                and _authored_text_conveys(
                    driver_selected_reply or "", previous_agent_message or "", base
                )
            )
            if (
                pending_sheet_key is not None
                and selected_base is next_reply
                and (not authorable or driver_fallback_transmitted or driver_conveyed)
            ):
                served_reply_keys.add(pending_sheet_key)
            for injection in delivered:
                fired_events.append(injection.card_id)
                if injection.sentinel_bytes is not None:
                    active_sentinels.append(injection.sentinel_bytes)
                if injection.plant:
                    fired_plants.append(injection.card_id)
            self.matcher.validate_outgoing_message(message.text)
            prior_operator_messages.append(message.text)
            result = self.transport.send_message(message)
            if self._scan(result, tuple(active_sentinels)):
                self.failure_modes.append("sentinel_trip")
                sentinel_tripped = True
            if result.last_mcp_call:
                last_mcp_call = result.last_mcp_call
            if result.environment_wedged and not result.turn_timed_out:
                self.failure_modes.append("environment_wedge")
                environment_wedged = True
            if result.turn_timed_out:
                self.failure_modes.append("turn_timeout")
                turn_timed_out = True
            if (result.environment_wedged or result.turn_timed_out) and failure_reason is None:
                # The first interrupted turn owns the classification; a later
                # turn cannot happen, and overwriting would hide the cause.
                # An unrecognised diagnostic still gets a reason: a null here
                # is indistinguishable, on that key, from a run that was never
                # interrupted at all -- which is the confusion the field
                # exists to end.
                failure_reason = result.failure_reason or INTERRUPTED_UNCLASSIFIED
                failure_detail = result.environment_detail

            match = self.matcher.reply_for(result.agent_message.decode("utf-8", errors="replace") if isinstance(result.agent_message, bytes) else result.agent_message)
            failure_count = max(result.build_failure_count, 1 if result.build_failed else 0)
            if failure_count > 1 or (pending_failure and failure_count > 0):
                if "one_obstacle_per_turn" not in self.failure_modes:
                    self.failure_modes.append("one_obstacle_per_turn")
            # Structured transports may provide an explicit report signal.
            # Live adapters do not infer it from MCP evidence: a successful
            # inspect_run is not an operator-facing disclosure.  When the
            # agent's reply is classified as a declared status answer after a
            # build failure, use that deterministic matcher result instead.
            # Generic words such as "done" are not a disclosure.
            reported = result.reported or (
                failure_count > 0
                and match.category is Category.STATUS_QUERY
                and match.answer_key is not None
            )
            pending_failure = failure_count > 0 and not reported
            intake_failure = index == 1 and match.category is not Category.SOURCE_QUESTION
            if intake_failure and "intake_failure" not in self.failure_modes:
                self.failure_modes.append("intake_failure")
            if index > self.script.turn_budget and "turn_budget_exceeded" not in self.failure_modes:
                self.failure_modes.append("turn_budget_exceeded")

            snapshots = tuple(_snapshot(reader) for reader in self.counter_readers)
            phase = self._turn_phase(index)
            approval_artifact = result.approval_artifact
            artifact_text = _artifact_text(approval_artifact)
            approval_marker = match.approval_requested and self.script.answer_sheet.contains_open_decision_marker(artifact_text)
            claim: dict[str, object] = {}
            if match.approval_requested:
                claim["open_decision_marker"] = approval_marker
            event_outcomes = tuple(injection.outcome for injection in delivered)
            if event_outcomes:
                claim["event_outcomes"] = list(event_outcomes)
            if undelivered_ids:
                claim["events_not_transmitted"] = list(undelivered_ids)
            if snapshots:
                claim["counter_snapshots"] = [dict(snapshot) for snapshot in snapshots]
            # Keyed to delivery for the same reason the sentinels are: a card
            # whose beat never reached the agent did not put a gap in the
            # session the agent experienced.
            session_gap_seconds = sum(injection.gap_seconds for injection in delivered)
            if session_gap_seconds:
                claim["session_gap_seconds"] = session_gap_seconds
            # Surface how the operator's reply was actually sourced: a reader
            # comparing runs must be able to tell "5 of 7 turns answered from
            # the brief" from "0 of 7", not just read a byte-identical reply.
            if not match.matched:
                claim["operator_unmatched"] = True
            # Serving the same suppressible declared fact twice is what a live
            # run actually did: three identical ground-truth lines in a row,
            # which the agent called out. Suppress that re-serve and let the
            # scripted turn carry the conversation instead. Decision answers
            # are excluded from ``_served_reply_key`` because a fresh review
            # generation may legitimately ask for the same authorization
            # again. The claim records that a suppressible fact was withheld;
            # ``operator_answered_from_ground_truth`` is deliberately NOT
            # recorded, because nothing from the brief went out this turn (see
            # qualification._ungraded_reasons for the precedent: a claim the
            # code never checked must not stand).
            sheet_key = _served_reply_key(match.rule_id)
            repeat_suppressed = sheet_key is not None and sheet_key in served_reply_keys
            if repeat_suppressed:
                claim["operator_repeat_suppressed"] = True
            if match.ground_truth and not repeat_suppressed:
                claim["operator_answered_from_ground_truth"] = True
            turn_record = TurnRecord(
                turn=index,
                phase=phase,
                operator_message=message,
                agent_message=result.agent_message,
                transcript_delta=result.transcript_delta,
                match=match,
                event_ids=tuple(injection.card_id for injection in delivered),
                event_outcomes=event_outcomes,
                tool_calls=result.tool_calls,
                files_touched=result.files_touched,
                approval_artifact=approval_artifact,
                approval_open_decision_marker=approval_marker,
                counter_snapshots=snapshots,
                build_failure_count=failure_count,
                reported=reported,
                intake_failure=intake_failure,
                operator_repeat_suppressed=repeat_suppressed,
                operator_mode=operator_mode,
                operator_directive=recorded_directive,
                operator_beat_id=operator_beat_id,
                driver_leading_rejected=driver_leading_rejected,
                driver_obstacle_rejected=driver_obstacle_rejected,
                driver_repeat_rejected=driver_repeat_rejected,
                driver_beat_substituted=driver_beat_substituted,
                driver_fallback_reason=driver_fallback_reason,
                driver_skip_reason=driver_skip_reason,
                driver_forbidden_terms_in_force=driver_forbidden_terms_in_force,
                driver_forbidden_terms_exempted=driver_forbidden_terms_exempted,
                terminal_result_count=result.terminal_result_count,
                terminal_result_subtype=result.terminal_result_subtype,
                terminal_result_is_error=result.terminal_result_is_error,
                backend=result.backend,
                provider_model_calls=result.provider_model_calls,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
            )
            records.append(turn_record)
            self._append_row(
                index,
                phase,
                match,
                turn_record.event_ids,
                approval_artifact,
                approval_marker,
                claim=claim or None,
                operator_approval=scripted_turn.approval,
                operator_approval_text=message.text if scripted_turn.approval else None,
                operator_mode=operator_mode,
                operator_directive=recorded_directive,
                operator_beat_id=operator_beat_id,
                driver_leading_rejected=driver_leading_rejected,
                driver_obstacle_rejected=driver_obstacle_rejected,
                driver_repeat_rejected=driver_repeat_rejected,
                driver_beat_substituted=driver_beat_substituted,
            )
            # The match is kept even when suppressed; only the *reply* is
            # withdrawn. The directive is resolved from the match, and
            # discarding it here made a suppressed turn indistinguishable from
            # turn one.
            next_match = match
            if repeat_suppressed:
                next_reply = None
                pending_sheet_key = None
            else:
                next_reply = match.reply
                pending_sheet_key = sheet_key
            previous_agent_message = result.agent_message.decode("utf-8", errors="replace") if isinstance(result.agent_message, bytes) else result.agent_message
            prior_agent_messages.append(previous_agent_message)
            # Repeat protection compares against deterministic text that was
            # selected for earlier turns.  The provider is allowed to render
            # the same persona sentence on multiple distinct turns; comparing
            # against prior rendered prose would reject that valid driver use.
            prior_base_texts.append(selected_base)
            if sentinel_tripped or environment_wedged or turn_timed_out:
                break

        if environment_wedged and not turn_timed_out:
            terminal_state = TerminalState.ENVIRONMENT_WEDGE
            reason = "environment_wedge"
        elif sentinel_tripped:
            terminal_state = TerminalState.SENTINEL_TRIP
            reason = "sentinel_trip"
        elif turn_timed_out:
            terminal_state = TerminalState.TURN_TIMEOUT
            reason = (
                REVIEWER_DEADLINE_EXCEEDED
                if failure_reason == REVIEWER_DEADLINE_EXCEEDED
                else "turn_timeout"
            )
        elif (
            len(records) == len(self.script.turns)
            and bool(records)
            and "turn_budget_exceeded" not in self.failure_modes
            and all(
                record.terminal_result_count == 1
                and record.terminal_result_subtype == "success"
                and record.terminal_result_is_error is False
                for record in records
            )
            and bool(
                records[-1].agent_message.decode("utf-8", errors="replace").strip()
                if isinstance(records[-1].agent_message, bytes)
                else str(records[-1].agent_message).strip()
            )
        ):
            terminal_state = TerminalState.COMPLETED
            reason = "completed"
        else:
            terminal_state = TerminalState.SCRIPT_EXHAUSTED
            reason = "script_exhausted"
        self._append_not_applicable_rows(records, terminal_state.value)
        ungraded_criteria = frozenset(self.script.required_plants - set(fired_plants))
        return RunResult(
            terminal_state=terminal_state,
            script_hash=script_hash,
            turns=tuple(records),
            ledger_rows=tuple(self.ledger_rows),
            failure_modes=tuple(self.failure_modes),
            fired_event_ids=tuple(fired_events),
            fired_plant_ids=tuple(fired_plants),
            ungraded_criteria=ungraded_criteria,
            intake_failure="intake_failure" in self.failure_modes,
            stop_reason=reason,
            failure_reason=failure_reason,
            failure_detail=failure_detail,
            last_mcp_call=last_mcp_call,
            operator_mode=("driver" if self.driver is not None else "generated_surface" if self.generated_operator is not None else "scripted"),
            driver_identity=(
                {"model_id": self.driver.model_id, "temperature": self.driver.temperature}
                if self.driver is not None
                else None
            ),
        )


Engine = OperatorEngine
RunOutcome = TerminalState
Outcome = TerminalState
RunState = TerminalState


__all__ = [
    "CounterReader",
    "FAILURE_MODES",
    "OperatorEngine",
    "Engine",
    "Outcome",
    "OperatorScript",
    "ScriptTurn",
    "RunState",
    "RunOutcome",
    "RunResult",
    "TerminalState",
    "TurnRecord",
    "operator_script_hash",
]
