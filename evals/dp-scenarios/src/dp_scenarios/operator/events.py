"""Strict event cards and deterministic turn-time injections.

An event is data with a declared trigger and recorded outcome. Fixed events
fire by turn number. Publication-triggered events use only runner-owned
``run-records.status_history`` observations from turns before the current one.
"""

from __future__ import annotations

import base64
import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any

import yaml


class EventError(ValueError):
    """Raised when an event card cannot be resolved deterministically."""


class EventType(str, Enum):
    """The fixed event vocabulary available to scenario authors."""

    SCREENSHOT = "screenshot"
    CREDENTIAL_FUMBLE = "credential_fumble"
    BACK_AFTER_LUNCH = "back_after_lunch"
    SPREADSHEET_DISAGREEMENT = "spreadsheet_disagreement"
    SCOPE_CREEP = "scope_creep"
    DEADLINE_PRESSURE = "deadline_pressure"
    WRONG_FILE = "wrong_file"
    DECISION_REVERSAL = "decision_reversal"
    MISDIAGNOSIS = "misdiagnosis"
    RAW_ROWS_REQUEST = "raw_rows_request"

    @classmethod
    def parse(cls, value: object) -> "EventType":
        if not isinstance(value, str):
            raise EventError("event.type must be a string")
        normalized = value.strip().casefold().replace("-", "_").replace(" ", "_")
        aliases = {"raw_rows": cls.RAW_ROWS_REQUEST, "raw_rows_dump": cls.RAW_ROWS_REQUEST}
        if normalized in aliases:
            return aliases[normalized]
        try:
            return cls(normalized)
        except ValueError as exc:
            raise EventError(f"unknown event type: {value!r}") from exc


EVENT_KEYS = frozenset(
    {
        "version",
        "id",
        "trigger_turn",
        "after_published",
        "after_event",
        "type",
        "content",
        "outcome",
        "attachment_name",
        "attachment_bytes",
        "attachment_base64",
        "wrong_key",
        "right_secret",
        "sentinel",
        "gap_seconds",
        "fresh_session",
        "replace_message",
        "metadata",
        "plant",
        "required_terms",
        "delivers_decision",
    }
)


def _mapping(value: object, location: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise EventError(f"{location} must be a mapping")
    return dict(value)


def _unknown(value: Mapping[str, object], allowed: set[str] | frozenset[str], location: str) -> None:
    unknown = sorted(set(value) - set(allowed))
    if unknown:
        raise EventError(f"{location} contains unknown key(s): {', '.join(unknown)}")


def _string(value: object, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EventError(f"{location} must be a non-empty string")
    return value


def _bool(value: object, location: str) -> bool:
    if not isinstance(value, bool):
        raise EventError(f"{location} must be a boolean")
    return value


def _bytes(raw: Mapping[str, Any], location: str) -> bytes | None:
    if "attachment_bytes" in raw and "attachment_base64" in raw:
        raise EventError(f"{location} must use only one attachment encoding")
    if "attachment_bytes" in raw:
        value = raw["attachment_bytes"]
        if isinstance(value, str):
            return value.encode("utf-8")
        if isinstance(value, bytes):
            return value
        raise EventError(f"{location}.attachment_bytes must be text or bytes")
    if "attachment_base64" in raw:
        value = _string(raw["attachment_base64"], f"{location}.attachment_base64")
        try:
            return base64.b64decode(value, validate=True)
        except (ValueError, base64.binascii.Error) as exc:
            raise EventError(f"{location}.attachment_base64 is not valid base64") from exc
    return None


def _digest(value: bytes | None) -> str | None:
    return hashlib.sha256(value).hexdigest() if value is not None else None


@dataclass(frozen=True, slots=True)
class EventCard:
    """One immutable event declaration.

    For screenshot and wrong-file cards, ``content`` is validated, included
    in obstacle scanning and script hashing, and retained as annotation-only
    metadata; the attachment replaces the event text at transmission time.
    """

    version: int
    card_id: str
    trigger_turn: int
    event_type: EventType
    content: str | None
    outcome: str
    attachment_name: str | None = None
    attachment_bytes: bytes | None = None
    wrong_key: str | None = None
    right_secret: str | None = None
    sentinel: bytes | None = None
    gap_seconds: int = 0
    fresh_session: bool = False
    replace_message: bool = False
    # default_factory, not a bare MappingProxyType: Python 3.12 accepts a
    # mappingproxy as an immutable dataclass default but 3.11 rejects it, and
    # this package supports 3.11.
    metadata: Mapping[str, object] = field(default_factory=lambda: MappingProxyType({}))
    plant: bool = False
    # Terms the *transmitted* operator message must contain for this beat to
    # count as delivered.  Declared as scenario data so the delivery check is
    # a property of the fixture, never a hardcoded predicate in the engine.
    required_terms: tuple[str, ...] = ()
    # Publication prerequisites are optional so legacy fixed-turn cards keep
    # their original constructor order and hash representation.
    after_published: str | None = None
    after_event: str | None = None
    # A card whose own text *is* the operator's ruling on a declared decision
    # (for example a reversal that states the revised rule) delivers that
    # decision when it is transmitted. The agent has no reason to ask for a
    # ruling it was just given, so grading must not require a second delivery.
    delivers_decision: str | None = None

    @property
    def id(self) -> str:
        """Return the stable card identity."""

        return self.card_id

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "EventCard":
        """Construct a card through the strict module validator."""

        return event_from_mapping(value)

    def to_mapping(self) -> dict[str, object]:
        """Return a canonical representation used by the operator hash."""

        result: dict[str, object] = {
            "version": self.version,
            "id": self.card_id,
            "trigger_turn": self.trigger_turn,
            "type": self.event_type.value,
            "content": self.content,
            "outcome": self.outcome,
            "attachment_name": self.attachment_name,
            "attachment_bytes": _digest(self.attachment_bytes),
            "wrong_key": self.wrong_key,
            "right_secret": self.right_secret,
            "sentinel": _digest(self.sentinel),
            "gap_seconds": self.gap_seconds,
            "fresh_session": self.fresh_session,
            "replace_message": self.replace_message,
            "metadata": dict(self.metadata),
            "plant": self.plant,
            "required_terms": list(self.required_terms),
        }
        if self.after_published is not None:
            result["after_published"] = self.after_published
        if self.after_event is not None:
            result["after_event"] = self.after_event
        if self.delivers_decision is not None:
            result["delivers_decision"] = self.delivers_decision
        return result

    @property
    def publication_triggered(self) -> bool:
        """Whether the card waits for a runner-observed prerequisite."""

        return self.after_published is not None or self.after_event is not None


@dataclass(frozen=True, slots=True)
class Attachment:
    """A deterministic file or screenshot presented to the agent."""

    name: str
    content: bytes
    kind: str


@dataclass(frozen=True, slots=True)
class EventInjection:
    """Resolved material fired for one trigger turn."""

    card_id: str
    trigger_turn: int
    event_type: EventType
    messages: tuple[str, ...]
    attachments: tuple[Attachment, ...]
    outcome: str
    fresh_session: bool
    gap_seconds: int
    sentinel_bytes: bytes | None
    plant: bool
    replace_message: bool
    required_terms: tuple[str, ...] = ()
    delivers_decision: str | None = None


def event_from_mapping(value: Mapping[str, object]) -> EventCard:
    """Validate and construct one event card."""

    raw = _mapping(value, "event")
    _unknown(raw, EVENT_KEYS, "event")
    required = {"version", "id", "trigger_turn", "type", "content", "outcome"}
    missing = sorted(required - set(raw))
    if missing:
        raise EventError(f"event is missing key(s): {', '.join(missing)}")
    version = raw["version"]
    if isinstance(version, bool) or not isinstance(version, int) or version != 1:
        raise EventError("event.version must be integer 1")
    turn = raw["trigger_turn"]
    if isinstance(turn, bool) or not isinstance(turn, int) or turn < 1:
        raise EventError("event.trigger_turn must be a positive integer")
    after_published = raw.get("after_published")
    if after_published is not None:
        if not isinstance(after_published, str) or after_published not in {"initial", "revised"}:
            raise EventError("event.after_published must be 'initial' or 'revised'")
    after_event = raw.get("after_event")
    if after_event is not None:
        after_event = _string(after_event, "event.after_event")
    content = raw["content"]
    if content is not None and not isinstance(content, str):
        raise EventError("event.content must be text or null")
    event_type = EventType.parse(raw["type"])
    gap = raw.get("gap_seconds", 0)
    if isinstance(gap, bool) or not isinstance(gap, int) or gap < 0:
        raise EventError("event.gap_seconds must be a non-negative integer")
    metadata = _mapping(raw.get("metadata", {}), "event.metadata")
    attachment = _bytes(raw, "event")
    name = raw.get("attachment_name")
    if name is not None:
        name = _string(name, "event.attachment_name")
    if attachment is not None and name is None:
        raise EventError("event.attachment_name is required with an attachment")
    wrong_key = raw.get("wrong_key")
    right_secret = raw.get("right_secret")
    sentinel = raw.get("sentinel")
    if wrong_key is not None:
        wrong_key = _string(wrong_key, "event.wrong_key")
    if right_secret is not None:
        right_secret = _string(right_secret, "event.right_secret")
    if sentinel is not None:
        sentinel_bytes = sentinel.encode("utf-8") if isinstance(sentinel, str) else sentinel
        if not isinstance(sentinel_bytes, bytes) or not sentinel_bytes:
            raise EventError("event.sentinel must be non-empty text or bytes")
    else:
        sentinel_bytes = right_secret.encode("utf-8") if event_type is EventType.CREDENTIAL_FUMBLE and right_secret else None
    if event_type is EventType.CREDENTIAL_FUMBLE and (wrong_key is None or right_secret is None):
        raise EventError("credential_fumble requires wrong_key and right_secret")
    if event_type is EventType.BACK_AFTER_LUNCH and gap == 0:
        raise EventError("back_after_lunch requires a positive gap_seconds")
    if event_type in {EventType.SCREENSHOT, EventType.WRONG_FILE} and attachment is None:
        raise EventError(f"{event_type.value} requires an attachment")
    fresh_session = raw.get("fresh_session", event_type is EventType.BACK_AFTER_LUNCH)
    replace_message = raw.get("replace_message", event_type in {EventType.SCREENSHOT, EventType.WRONG_FILE})
    plant = raw.get("plant", False)
    required_raw = raw.get("required_terms", ())
    if isinstance(required_raw, (str, bytes)) or not isinstance(required_raw, Sequence):
        raise EventError("event.required_terms must be a list of non-empty strings")
    required_terms = tuple(_string(item, "event.required_terms[]") for item in required_raw)
    delivers_decision = raw.get("delivers_decision")
    if delivers_decision is not None:
        delivers_decision = _string(delivers_decision, "event.delivers_decision")
    return EventCard(
        version=version,
        card_id=_string(raw["id"], "event.id"),
        trigger_turn=turn,
        after_published=after_published,
        after_event=after_event,
        event_type=event_type,
        content=content,
        outcome=_string(raw["outcome"], "event.outcome"),
        attachment_name=name,
        attachment_bytes=attachment,
        wrong_key=wrong_key,
        right_secret=right_secret,
        sentinel=sentinel_bytes,
        gap_seconds=gap,
        fresh_session=_bool(fresh_session, "event.fresh_session"),
        replace_message=_bool(replace_message, "event.replace_message"),
        metadata=MappingProxyType(metadata),
        plant=_bool(plant, "event.plant"),
        required_terms=required_terms,
        delivers_decision=delivers_decision,
    )


def inject_event(card: EventCard) -> EventInjection:
    """Resolve one card into fixed messages and attachments."""

    messages: list[str] = []
    if card.event_type is EventType.CREDENTIAL_FUMBLE:
        assert card.wrong_key is not None and card.right_secret is not None
        messages.extend((card.wrong_key, card.right_secret))
    elif card.content is not None:
        messages.append(card.content)
    attachments: tuple[Attachment, ...] = ()
    if card.attachment_bytes is not None and card.attachment_name is not None:
        kind = "screenshot" if card.event_type is EventType.SCREENSHOT else "file"
        attachments = (Attachment(card.attachment_name, card.attachment_bytes, kind),)
    return EventInjection(
        card_id=card.card_id,
        trigger_turn=card.trigger_turn,
        event_type=card.event_type,
        messages=tuple(messages),
        attachments=attachments,
        outcome=card.outcome,
        fresh_session=card.fresh_session,
        gap_seconds=card.gap_seconds,
        sentinel_bytes=card.sentinel,
        plant=card.plant,
        replace_message=card.replace_message,
        required_terms=card.required_terms,
        delivers_decision=card.delivers_decision,
    )


@dataclass(frozen=True, slots=True)
class EventSchedule:
    """Sorted event cards with deterministic trigger lookup."""

    cards: tuple[EventCard, ...]

    def __post_init__(self) -> None:
        cards = tuple(self.cards)
        object.__setattr__(self, "cards", cards)
        ids = [card.card_id for card in self.cards]
        if len(ids) != len(set(ids)):
            raise EventError("event card ids must be unique")
        if tuple(sorted(self.cards, key=lambda card: (card.trigger_turn, card.card_id))) != self.cards:
            raise EventError("event cards must be sorted by trigger_turn and id")
        by_id = {card.card_id: card for card in self.cards}
        for card in self.cards:
            if card.after_event is not None and card.after_event not in by_id:
                raise EventError(
                    f"event {card.card_id!r} references unknown after_event id {card.after_event!r}"
                )
            if card.after_event == card.card_id:
                raise EventError(f"event {card.card_id!r} cannot follow itself")
        # A dependency cycle can never produce a delivered predecessor. Catch
        # it during fixture loading instead of leaving the cards dormant.
        dependencies = {
            card.card_id: card.after_event
            for card in self.cards
            if card.after_event is not None
        }
        for card_id in dependencies:
            visited: set[str] = set()
            current: str | None = card_id
            while current in dependencies:
                if current in visited:
                    raise EventError("event after_event dependencies must not contain a cycle")
                visited.add(current)
                current = dependencies[current]

    def fire(
        self,
        turn: int,
        *,
        run_records: Mapping[str, object] | None = None,
        publication_history: Mapping[str, object] | None = None,
        delivered_event_turns: Mapping[str, int] | None = None,
        used_event_ids: Sequence[str] = (),
        fixed_beats_pending: bool = False,
        turn_texts: Sequence[tuple[int, str, str]] | None = None,
    ) -> tuple[EventInjection, ...]:
        """Resolve fixed events and at most one eligible publication card.

        ``run_records`` must be the harness-owned artifact with schema
        ``dp-scenario-run-records-v1``. A status observation only counts when
        its status-history turn is strictly before ``turn``. ``delivered_event_turns``
        contains actual operator delivery turns, never declared trigger turns.
        ``turn_texts`` holds ``(turn, agent_message, operator_message)`` rows and
        is only consulted to recognise an operator-authorized successor release
        (see :func:`is_revised_release`).
        """

        used = set(used_event_ids)
        fixed_due = tuple(
            card
            for card in self.cards
            if not card.publication_triggered
            and card.trigger_turn == turn
            and card.card_id not in used
        )
        if fixed_due:
            # Fixed cards keep their declared slot. Publication cards wait for
            # a later turn if a fixed card is due now.
            return tuple(inject_event(card) for card in fixed_due)
        if fixed_beats_pending:
            return ()

        event_turns = delivered_event_turns or {}
        publications = _published_runs(
            run_records,
            publication_history,
            before_turn=turn,
        )
        for card in self.cards:
            if not card.publication_triggered or card.trigger_turn > turn or card.card_id in used:
                continue
            event_turn = None
            if card.after_event is not None:
                candidate = event_turns.get(card.after_event)
                if (
                    not isinstance(candidate, int)
                    or isinstance(candidate, bool)
                    or candidate < 1
                    or candidate >= turn
                ):
                    continue
                event_turn = candidate
            if card.after_published == "initial":
                if not publications:
                    continue
            elif card.after_published == "revised":
                if not publications:
                    continue
                if not any(
                    is_revised_release(
                        initial_workflow_id=initial.workflow_id,
                        initial_run_id=initial.run_id,
                        initial_definition_id=initial.definition_id,
                        initial_published_turn=initial.published_turn,
                        workflow_id=revised.workflow_id,
                        run_id=revised.run_id,
                        definition_id=revised.definition_id,
                        published_turn=revised.published_turn,
                        floor_turn=event_turn,
                        turn_texts=turn_texts,
                        authorization_deadline=revised.published_turn,
                    )
                    for initial in publications
                    for revised in publications
                ):
                    continue
            return (inject_event(card),)
        return ()

    @property
    def publication_card_ids(self) -> frozenset[str]:
        """Stable ids of cards that need runner publication observations."""

        return frozenset(card.card_id for card in self.cards if card.publication_triggered)

    def planted_card_ids(self) -> frozenset[str]:
        """Return cards whose declared ceiling or plant must execute."""

        return frozenset(card.card_id for card in self.cards if card.plant)

    def to_mapping(self) -> list[dict[str, object]]:
        """Return cards in their stable schedule order."""

        return [card.to_mapping() for card in self.cards]


# The agent putting a new, separately versioned product to the operator. The
# shipped run-job-loop skill forbids revising a published workflow in place and
# requires exactly this shape: a new product under a new workflow id, after
# asking the user.
_SUCCESSOR_PRODUCT_ASK = re.compile(
    r"\b(?:new|separate|second)\s+(?:versioned\s+)?(?:product|workflow)\b"
    r"|\bnew\s+workflow\s+id\b|\bversioned\s+product\b",
    re.IGNORECASE,
)


def successor_authorization_turn(
    turn_texts: Sequence[tuple[int, str, str]] | None,
    *,
    after_turn: int,
    deadline_turn: int | None,
) -> int | None:
    """Return the operator turn that authorized a successor workflow, if any.

    Authorization is an agent turn ``A >= after_turn`` that puts a new or
    separately versioned product to the operator, followed by an operator
    message delivered on a later turn ``N`` with ``A < N <= deadline_turn``.
    Runner-owned turn records are the only source; the run's own claims are
    never consulted. A missing or unreadable transcript authorizes nothing.
    """

    if not turn_texts or deadline_turn is None:
        return None
    rows = sorted(
        (row for row in turn_texts if isinstance(row[0], int) and not isinstance(row[0], bool)),
        key=lambda row: row[0],
    )
    ask_turns = [
        turn for turn, agent, _ in rows
        if turn >= after_turn and isinstance(agent, str) and _SUCCESSOR_PRODUCT_ASK.search(agent)
    ]
    if not ask_turns:
        return None
    first_ask = min(ask_turns)
    for turn, _, operator in rows:
        if first_ask < turn <= deadline_turn and isinstance(operator, str) and operator.strip():
            return turn
    return None


def is_revised_release(
    *,
    initial_workflow_id: str,
    initial_run_id: str,
    initial_definition_id: str,
    initial_published_turn: int,
    workflow_id: str,
    run_id: str,
    definition_id: str,
    published_turn: int,
    floor_turn: int | None,
    turn_texts: Sequence[tuple[int, str, str]] | None,
    authorization_deadline: int | None,
) -> bool:
    """Whether a later Published run is the revised release of an initial one.

    A revised release is a later Published run with a different definition that
    is either the same workflow, or a successor workflow the operator
    authorized after the agent asked (the shipped skill forbids revising a
    published workflow in place). ``floor_turn`` is the delivered reversal
    event, when the card is gated on one; the revised publication must follow
    it. The authorization window starts at that event (or, when there is none,
    at the initial publication).
    """

    if (
        run_id == initial_run_id
        or definition_id == initial_definition_id
        or published_turn <= initial_published_turn
        or (floor_turn is not None and published_turn <= floor_turn)
    ):
        return False
    if workflow_id == initial_workflow_id:
        return True
    after = floor_turn if floor_turn is not None else initial_published_turn
    return successor_authorization_turn(
        turn_texts, after_turn=after, deadline_turn=authorization_deadline
    ) is not None


@dataclass(frozen=True, slots=True)
class _PublishedRun:
    workflow_id: str
    run_id: str
    definition_id: str
    published_turn: int


def _published_runs(
    run_records: Mapping[str, object] | None,
    publication_history: Mapping[str, object] | None,
    *,
    before_turn: int,
) -> tuple[_PublishedRun, ...]:
    """Cross-check Published status observations against exact release identity.

    ``publication-history.turn`` is deliberately ignored: it records run
    start, not the observed turn on which the run became Published.
    """

    if run_records is None or run_records.get("schema") != "dp-scenario-run-records-v1":
        return ()
    if (
        publication_history is None
        or publication_history.get("schema") != "dp-scenario-publication-history-v1"
    ):
        return ()
    raw_releases = publication_history.get("releases")
    if not isinstance(raw_releases, Sequence) or isinstance(raw_releases, (str, bytes, bytearray)):
        return ()
    released_ids = {
        (release.get("workflow_id"), release.get("run_id"), release.get("definition_id"))
        for release in raw_releases
        if isinstance(release, Mapping)
        and all(
            isinstance(release.get(key), str) and release.get(key).strip()
            for key in ("workflow_id", "run_id", "definition_id")
        )
    }
    raw_runs = run_records.get("runs")
    if not isinstance(raw_runs, Sequence) or isinstance(raw_runs, (str, bytes, bytearray)):
        return ()
    observed: list[_PublishedRun] = []
    seen_run_ids: set[tuple[str, str]] = set()
    for raw_run in raw_runs:
        if not isinstance(raw_run, Mapping):
            continue
        workflow_id = raw_run.get("workflow_id")
        run_id = raw_run.get("run_id")
        definition_id = raw_run.get("definition_id")
        history = raw_run.get("status_history")
        if not all(isinstance(value, str) and value.strip() for value in (workflow_id, run_id, definition_id)):
            continue
        if (workflow_id, run_id, definition_id) not in released_ids:
            continue
        run_key = (workflow_id, run_id)
        if run_key in seen_run_ids:
            # Duplicate identities make the association ambiguous; fail closed
            # for this id instead of choosing whichever copy appears first.
            observed = [item for item in observed if (item.workflow_id, item.run_id) != run_key]
            continue
        seen_run_ids.add(run_key)
        if not isinstance(history, Sequence) or isinstance(history, (str, bytes, bytearray)):
            continue
        turns = [
            entry.get("turn")
            for entry in history
            if isinstance(entry, Mapping)
            and entry.get("status") == "Published"
            and isinstance(entry.get("turn"), int)
            and not isinstance(entry.get("turn"), bool)
            and 0 < entry.get("turn") < before_turn
        ]
        if turns:
            observed.append(
                _PublishedRun(workflow_id, run_id, definition_id, min(turns))
            )
    return tuple(
        sorted(observed, key=lambda item: (item.published_turn, item.workflow_id, item.run_id, item.definition_id))
    )


def load_event_cards(path: str | Path) -> EventSchedule:
    """Load and validate a YAML list of event cards."""

    card_path = Path(path)
    try:
        raw = yaml.safe_load(card_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise EventError(f"could not read event schedule {card_path}: {exc}") from exc
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes, bytearray)):
        raise EventError("event schedule must be a list")
    cards = tuple(sorted((event_from_mapping(item) for item in raw), key=lambda item: (item.trigger_turn, item.card_id)))
    return EventSchedule(cards)


load_event_schedule = load_event_cards


__all__ = [
    "EVENT_KEYS",
    "Attachment",
    "EventCard",
    "EventError",
    "EventInjection",
    "EventSchedule",
    "EventType",
    "event_from_mapping",
    "inject_event",
    "is_revised_release",
    "load_event_cards",
    "load_event_schedule",
    "successor_authorization_turn",
]
