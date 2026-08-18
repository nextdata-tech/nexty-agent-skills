"""Strict event cards and deterministic turn-time injections.

An event is data with a declared trigger and recorded outcome.  The schedule
fires by turn number, never by elapsed time or agent state, so a run cannot
silently skip a planted event.
"""

from __future__ import annotations

import base64
import hashlib
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
        }
        return result


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
    return EventCard(
        version=version,
        card_id=_string(raw["id"], "event.id"),
        trigger_turn=turn,
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

    def fire(self, turn: int) -> tuple[EventInjection, ...]:
        """Return every card declared for a turn, independent of agent state."""

        return tuple(inject_event(card) for card in self.cards if card.trigger_turn == turn)

    def planted_card_ids(self) -> frozenset[str]:
        """Return cards whose declared ceiling or plant must execute."""

        return frozenset(card.card_id for card in self.cards if card.plant)

    def to_mapping(self) -> list[dict[str, object]]:
        """Return cards in their stable schedule order."""

        return [card.to_mapping() for card in self.cards]


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
    "load_event_cards",
    "load_event_schedule",
]
