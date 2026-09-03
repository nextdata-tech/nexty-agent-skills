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
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

from dp_scenarios.ledger.lint import PHASE_ACTION_KINDS

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
from .events import EventInjection, EventSchedule, event_from_mapping
from .generated import GeneratedOperator, OperatorView
from .matcher import Category, MatchResult, MatcherBank
from .persona import PersonaCard
from .transport import Attachment, OperatorMessage, Transport, TurnResult, TouchedFile, ToolCall


class TerminalState(str, Enum):
    """The engine's terminal observation, before a separate grading pass."""

    SCRIPT_EXHAUSTED = "script_exhausted"
    SENTINEL_TRIP = "sentinel_trip"
    ENVIRONMENT_WEDGE = "environment_wedge"


FAILURE_MODES = frozenset(
    {
        "sentinel_trip",
        "environment_wedge",
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
    """One declared operator turn and its reply-substitution policy."""

    text: str
    substitute_reply: bool

    def __init__(
        self,
        text: str,
        substitute_reply: bool = True,
        *,
        use_reply: bool | None = None,
    ) -> None:
        if use_reply is not None:
            if not isinstance(use_reply, bool):
                raise TypeError("ScriptTurn.use_reply must be a boolean")
            substitute_reply = use_reply
        if not isinstance(text, str) or not text:
            raise ValueError("ScriptTurn.text must be a non-empty string")
        if not isinstance(substitute_reply, bool):
            raise TypeError("ScriptTurn.substitute_reply must be a boolean")
        object.__setattr__(self, "text", text)
        object.__setattr__(self, "substitute_reply", substitute_reply)

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
            allowed = {"text", "message", "substitute_reply", "use_reply"}
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
            return cls(text, switch)  # type: ignore[arg-type]
        raise TypeError("script turns must be strings, ScriptTurn values, or mappings")

    def to_mapping(self) -> dict[str, object]:
        """Return the canonical runtime-affecting declaration."""

        return {"text": self.text, "substitute_reply": self.substitute_reply}


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
            },
            "answer_sheet": answer_sheet,
            "events": self.events.to_mapping(),
            "turns": [
                {
                    # A substituting turn's authored text is never transmitted;
                    # keep the switch itself because it changes runtime behavior.
                    "text": turn.text if index == 0 or not turn.substitute_reply else None,
                    "substitute_reply": turn.substitute_reply,
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



def _qualification_for(match: MatchResult | None, claim: Mapping[str, object] | None) -> str | None:
    """Return the evidence qualification a row's claim requires.

    The lint rejects any claim-bearing row without a qualification from the closed
    vocabulary, so every path that attaches a claim must supply one. An approval is
    an operator act observed directly, so it is ``strong``; an event outcome or a
    counter snapshot describes only the attempt that produced it, so it is
    ``strong-for-this-attempt``. A row with no claim carries no qualification.
    """
    if match is not None and match.category is Category.APPROVAL_REQUEST:
        return "strong"
    if claim:
        return "strong-for-this-attempt"
    return None

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
    ) -> None:
        self.script = script
        self.transport = transport
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
        self.phase = 1
        self.turn_pointer = 0
        self.failure_modes: list[str] = []
        self.ledger_rows: list[Mapping[str, object]] = []

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
    ) -> None:
        detail = "operator response selected" if match is not None else (phase_status_reason or "phase not reached")
        action_kind = self._DEFAULT_ACTION_KIND_BY_PHASE[phase]
        artifact_ref: str | None = None
        if match is not None and match.category is Category.APPROVAL_REQUEST:
            if claim is None:
                claim = {"open_decision_marker": approval_marker}
            claim = dict(claim) if isinstance(claim, Mapping) else {}
            approval_artifact_text = (
                approval_artifact.decode("utf-8", errors="replace")
                if isinstance(approval_artifact, bytes)
                else approval_artifact or ""
            )
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
            qualification=_qualification_for(match, claim),
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
        next_reply: str | None = None
        previous_agent_message = ""
        prior_operator_messages: list[str] = []

        for index, scripted_turn in enumerate(self.script.turns, start=1):
            self.turn_pointer = index - 1
            injections = self.script.events.fire(index)
            for injection in injections:
                fired_events.append(injection.card_id)
                if injection.plant:
                    fired_plants.append(injection.card_id)
                if injection.sentinel_bytes is not None:
                    active_sentinels.append(injection.sentinel_bytes)
            if any(injection.fresh_session for injection in injections):
                self.transport.start_fresh_session()
            base = (
                scripted_turn.text
                if index == 1 or not scripted_turn.substitute_reply
                else (next_reply or scripted_turn.text)
            )
            if index > 1 and scripted_turn.substitute_reply and next_reply and self.generated_operator is not None:
                view = OperatorView.from_persona(
                    turn=index,
                    phase=self.phase,
                    persona=self.script.persona,
                    agent_message=_operator_context(previous_agent_message, active_sentinels),
                    selected_reply=next_reply,
                    prior_operator_messages=tuple(
                        _operator_context(message, active_sentinels)
                        for message in prior_operator_messages
                    ),
                    remaining_turns=len(self.script.turns) - index + 1,
                )
                rendered = self.generated_operator.render(
                    view,
                    fallback=next_reply,
                    validate=self.matcher.validate_generated_surface,
                )
                base = rendered.text
                if rendered.used_fallback and "operator_fallback" not in self.failure_modes:
                    self.failure_modes.append("operator_fallback")
            message = self._message_for(base, injections)
            self.matcher.validate_outgoing_message(message.text)
            prior_operator_messages.append(message.text)
            result = self.transport.send_message(message)
            if self._scan(result, tuple(active_sentinels)):
                self.failure_modes.append("sentinel_trip")
                sentinel_tripped = True
            if result.environment_wedged:
                self.failure_modes.append("environment_wedge")
                environment_wedged = True

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
            artifact_text = (
                approval_artifact.decode("utf-8", errors="replace")
                if isinstance(approval_artifact, bytes)
                else approval_artifact or ""
            )
            approval_marker = match.category is Category.APPROVAL_REQUEST and self.script.answer_sheet.contains_open_decision_marker(artifact_text)
            claim: dict[str, object] = {}
            if match.category is Category.APPROVAL_REQUEST:
                claim["open_decision_marker"] = approval_marker
            event_outcomes = tuple(injection.outcome for injection in injections)
            if event_outcomes:
                claim["event_outcomes"] = list(event_outcomes)
            if snapshots:
                claim["counter_snapshots"] = [dict(snapshot) for snapshot in snapshots]
            session_gap_seconds = sum(injection.gap_seconds for injection in injections)
            if session_gap_seconds:
                claim["session_gap_seconds"] = session_gap_seconds
            turn_record = TurnRecord(
                turn=index,
                phase=phase,
                operator_message=message,
                agent_message=result.agent_message,
                transcript_delta=result.transcript_delta,
                match=match,
                event_ids=tuple(injection.card_id for injection in injections),
                event_outcomes=tuple(injection.outcome for injection in injections),
                tool_calls=result.tool_calls,
                files_touched=result.files_touched,
                approval_artifact=approval_artifact,
                approval_open_decision_marker=approval_marker,
                counter_snapshots=snapshots,
                build_failure_count=failure_count,
                reported=reported,
                intake_failure=intake_failure,
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
            )
            next_reply = match.reply
            previous_agent_message = result.agent_message.decode("utf-8", errors="replace") if isinstance(result.agent_message, bytes) else result.agent_message
            if sentinel_tripped or environment_wedged:
                break

        if environment_wedged:
            terminal_state = TerminalState.ENVIRONMENT_WEDGE
            reason = "environment_wedge"
        elif sentinel_tripped:
            terminal_state = TerminalState.SENTINEL_TRIP
            reason = "sentinel_trip"
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
