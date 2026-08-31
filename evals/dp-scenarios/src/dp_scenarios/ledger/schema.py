"""Closed, typed shapes for immutable evidence rows.

Rows contain both the protocol observation and the explicit structure needed
by the hard gate: action vocabulary, phase applicability, supervisor fact
keys, declared supersession targets, and the storage-chain predecessor digest.
``row_id`` and ``prev_digest`` are storage-owned fields.  They are materialized
when a row is written or read, but cannot be supplied by an append caller.  The
field order is part of the current ledger wire format, so adding the evidence
fields changed chain digests; an absent event list is serialized as JSON null.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import ClassVar


LEDGER_FIELDS = (
    "row_id",
    "run_id",
    "scenario_id",
    "turn",
    "phase",
    "phase_status",
    "phase_status_reason",
    "action_kind",
    "action",
    "matched_rule_id",
    "event_ids",
    "artifact_ref",
    "claim",
    "evidence_ref",
    "qualification",
    "supersedes",
    "term",
    "fact_key",
    "prev_digest",
)

ACTION_KINDS = frozenset(
    {
        "intake",
        "spec_presented",
        "spec_approved",
        "capability_probe",
        "narrowing",
        "codegen",
        "self_check",
        "adversarial_review",
        "build",
        "publish",
        "serve",
        "query",
        "supervisor_fact",
        "follow_up",
        "supersession",
    }
)

PHASE_STATUSES = frozenset({"executed", "not-applicable"})
QUALIFICATIONS = frozenset(
    {
        "strong",
        "strong-for-this-attempt",
        "demonstrated-once",
        "not-claimed",
    }
)
PROTOCOL_PHASES = frozenset(range(1, 8))

ClaimValue = str | int | float | bool | None | list[object] | dict[str, object]


class SchemaError(ValueError):
    """Raised when a value cannot be represented as a ledger row."""


@dataclass(frozen=True, slots=True)
class LedgerRow:
    """One append-only evidence observation after the manifest row."""

    row_id: int | None = field(default=None, init=False)
    run_id: str = ""
    scenario_id: str = ""
    turn: int = 0
    phase: int = 0
    phase_status: str = "executed"
    phase_status_reason: str | None = None
    action_kind: str = ""
    action: str = ""
    matched_rule_id: str | None = None
    event_ids: tuple[str, ...] | None = None
    artifact_ref: str | None = None
    claim: ClaimValue = None
    evidence_ref: str | None = None
    qualification: str | None = None
    supersedes: int | None = None
    term: str | None = None
    fact_key: str | None = None
    prev_digest: str | None = field(default=None, init=False)

    fields: ClassVar[tuple[str, ...]] = LEDGER_FIELDS

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, str) or not self.run_id:
            raise SchemaError("run_id must be a non-empty string")
        if not isinstance(self.scenario_id, str) or not self.scenario_id:
            raise SchemaError("scenario_id must be a non-empty string")
        if isinstance(self.turn, bool) or not isinstance(self.turn, int) or self.turn < 1:
            raise SchemaError("turn must be a positive integer")
        if isinstance(self.phase, bool) or not isinstance(self.phase, int) or self.phase not in PROTOCOL_PHASES:
            raise SchemaError("phase must be an integer from 1 through 7")
        if self.phase_status not in PHASE_STATUSES:
            raise SchemaError("phase_status must be executed or not-applicable")
        if self.phase_status_reason is not None and not isinstance(self.phase_status_reason, str):
            raise SchemaError("phase_status_reason must be a string or null")
        if not isinstance(self.action_kind, str) or not self.action_kind:
            raise SchemaError("action_kind must be a non-empty string")
        if not isinstance(self.action, str):
            raise SchemaError("action must be a string")
        if self.matched_rule_id is not None and (
            not isinstance(self.matched_rule_id, str) or not self.matched_rule_id
        ):
            raise SchemaError("matched_rule_id must be a non-empty string or null")
        if self.event_ids is not None:
            if not isinstance(self.event_ids, Sequence) or isinstance(self.event_ids, (str, bytes, bytearray)):
                raise SchemaError("event_ids must be a sequence of strings or null")
            if any(not isinstance(event_id, str) or not event_id for event_id in self.event_ids):
                raise SchemaError("event_ids must contain only non-empty strings")
            object.__setattr__(self, "event_ids", tuple(self.event_ids))
        for field_name in ("artifact_ref", "evidence_ref", "qualification", "term", "fact_key"):
            value = getattr(self, field_name)
            if value is not None and not isinstance(value, str):
                raise SchemaError(f"{field_name} must be a string or null")
        if self.supersedes is not None and (
            isinstance(self.supersedes, bool)
            or not isinstance(self.supersedes, int)
            or self.supersedes < 1
        ):
            raise SchemaError("supersedes must be a positive integer or null")

    def to_dict(self) -> dict[str, object]:
        """Return every row field, including storage-owned nulls if unassigned."""

        return {
            field_name: list(getattr(self, field_name)) if field_name == "event_ids" and getattr(self, field_name) is not None else getattr(self, field_name)
            for field_name in self.fields
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, object], *, stored: bool = False) -> "LedgerRow":
        """Build a row; ``stored`` controls whether chain fields are required."""

        if not isinstance(value, Mapping):
            raise SchemaError("ledger row must be a JSON object")
        unknown = set(value) - set(cls.fields)
        if unknown:
            names = ", ".join(sorted(str(name) for name in unknown))
            raise SchemaError(f"unknown ledger row field(s): {names}")
        if not stored and ("row_id" in value or "prev_digest" in value):
            raise SchemaError("row_id and prev_digest are assigned by LedgerStore")
        required = ("run_id", "scenario_id", "turn", "phase", "action_kind", "action")
        missing = [field_name for field_name in required if field_name not in value]
        if missing:
            raise SchemaError(f"missing ledger row field(s): {', '.join(missing)}")
        if stored:
            missing_storage = [field_name for field_name in ("row_id", "prev_digest") if field_name not in value]
            if missing_storage:
                raise SchemaError(f"missing ledger row field(s): {', '.join(missing_storage)}")
            row_id = value["row_id"]
            prev_digest = value["prev_digest"]
            if isinstance(row_id, bool) or not isinstance(row_id, int) or row_id < 1:
                raise SchemaError("row_id must be a positive integer")
            if not isinstance(prev_digest, str) or not prev_digest:
                raise SchemaError("prev_digest must be a non-empty string")
        row = cls(
            run_id=value["run_id"],  # type: ignore[arg-type]
            scenario_id=value["scenario_id"],  # type: ignore[arg-type]
            turn=value["turn"],  # type: ignore[arg-type]
            phase=value["phase"],  # type: ignore[arg-type]
            phase_status=value.get("phase_status", "executed"),  # type: ignore[arg-type]
            phase_status_reason=value.get("phase_status_reason"),  # type: ignore[arg-type]
            action_kind=value["action_kind"],  # type: ignore[arg-type]
            action=value["action"],  # type: ignore[arg-type]
            matched_rule_id=value.get("matched_rule_id"),  # type: ignore[arg-type]
            event_ids=value.get("event_ids"),  # type: ignore[arg-type]
            artifact_ref=value.get("artifact_ref"),  # type: ignore[arg-type]
            claim=value.get("claim"),  # type: ignore[arg-type]
            evidence_ref=value.get("evidence_ref"),  # type: ignore[arg-type]
            qualification=value.get("qualification"),  # type: ignore[arg-type]
            supersedes=value.get("supersedes"),  # type: ignore[arg-type]
            term=value.get("term"),  # type: ignore[arg-type]
            fact_key=value.get("fact_key"),  # type: ignore[arg-type]
        )
        if stored:
            object.__setattr__(row, "row_id", row_id)
            object.__setattr__(row, "prev_digest", prev_digest)
        return row

    def __getitem__(self, field_name: str) -> object:
        """Provide mapping-style access to parsed rows."""

        if field_name not in self.fields:
            raise KeyError(field_name)
        return getattr(self, field_name)

    def get(self, field_name: str, default: object = None) -> object:
        """Return a field value using mapping-style convenience."""

        if field_name not in self.fields:
            return default
        return getattr(self, field_name)
