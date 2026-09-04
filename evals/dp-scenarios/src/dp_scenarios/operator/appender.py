"""Append operator observations without trusting agent-authored facts.

Supervisor-owned values enter the ledger only through an injected record
reader.  Turn prose is kept in the detail field, while action kinds and fact
keys remain closed and machine-readable.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from dp_scenarios.ledger import ACTION_KINDS, SupervisorFacts
from dp_scenarios.ledger.lint import _MISSING as LEDGER_MISSING


class AppenderError(ValueError):
    """Raised when evidence lacks the supervisor-owned input it requires."""


class LedgerWriter(Protocol):
    """Minimal append collaborator accepted by the appender."""

    def append(self, row: object) -> None:
        """Append one typed or mapping-shaped row."""


class SupervisorRecordReader(Protocol):
    """Source of supervisor facts; agent text is deliberately absent."""

    def read_facts(self) -> SupervisorFacts:
        """Read the supervisor's own immutable run record."""


@dataclass(frozen=True, slots=True)
class StaticSupervisorRecordReader:
    """Small test and local-run adapter around a fixed supervisor snapshot."""

    facts: SupervisorFacts

    def read_facts(self) -> SupervisorFacts:
        """Return the fixed snapshot without consulting agent prose."""

        return self.facts

    def read(self) -> SupervisorFacts:
        """Compatibility alias for record-reader collaborators."""

        return self.read_facts()


@dataclass(frozen=True, slots=True)
class TurnEvidence:
    """Structured observations for one operator turn."""

    run_id: str
    scenario_id: str
    turn: int
    phase: int
    action_kind: str
    detail: str
    matched_rule_id: str | None = None
    event_ids: tuple[str, ...] = ()
    artifact_ref: str | None = None
    claim: object = None
    evidence_ref: str | None = None
    qualification: str | None = None
    phase_status: str = "executed"
    phase_status_reason: str | None = None
    fact_key: str | None = None
    supersedes: int | None = None
    term: str | None = None


def _read_supervisor(reader: SupervisorRecordReader | None) -> SupervisorFacts:
    if reader is None:
        raise AppenderError("supervisor-owned evidence requires a supervisor record reader")
    if hasattr(reader, "read_facts"):
        facts = reader.read_facts()
    elif hasattr(reader, "read"):
        facts = reader.read()  # type: ignore[attr-defined]
    else:
        raise AppenderError("supervisor record reader has no read_facts method")
    if not isinstance(facts, SupervisorFacts):
        raise AppenderError("supervisor record reader returned no SupervisorFacts")
    return facts


_SUPERVISOR_CLAIM_KEYS = frozenset(
    {"run_id", "artifact_id", "publish_sequence", "per_model_row_counts", "lifecycle_state"}
)
_NON_FACT_CLAIM_KEYS = frozenset(
    {
        "approval_without_artifact",
        "approval_out_of_phase",
        "counter_snapshots",
        "event_outcomes",
        "events_not_transmitted",
        "open_decision_marker",
        "outcome",
        "session_gap_seconds",
        "operator_unmatched",
        "operator_answered_from_ground_truth",
        "operator_repeat_suppressed",
        "operator_mode",
        "operator_beat_id",
        "driver_leading_rejected",
        "driver_obstacle_rejected",
        "driver_repeat_rejected",
        "driver_beat_substituted",
    }
)


def _iter_supervisor_claims(value: object) -> tuple[tuple[str, object], ...]:
    found: list[tuple[str, object]] = []
    if isinstance(value, Mapping):
        for key, nested in value.items():
            name = str(key)
            if name in _SUPERVISOR_CLAIM_KEYS or name.startswith("per_model_row_counts."):
                found.append((name, nested))
            found.extend(_iter_supervisor_claims(nested))
    elif isinstance(value, (list, tuple)):
        for nested in value:
            found.extend(_iter_supervisor_claims(nested))
    return tuple(found)


def _json_bytes(value: object) -> bytes:
    if isinstance(value, Mapping):
        value = {str(key): value[key] for key in sorted(value, key=str)}
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=dict).encode("utf-8")


def _validate_non_fact_claim(value: object) -> None:
    """Keep non-fact claims structured so prose cannot launder supervisor facts."""

    if not isinstance(value, Mapping):
        raise AppenderError("non-supervisor claims must use the closed structured claim shape")
    unknown = set(value) - _NON_FACT_CLAIM_KEYS
    if unknown:
        names = ", ".join(sorted(str(name) for name in unknown))
        raise AppenderError(f"non-supervisor claim contains unknown key(s): {names}")
    if "open_decision_marker" in value and not isinstance(value["open_decision_marker"], bool):
        raise AppenderError("open_decision_marker must be a boolean")
    if "approval_without_artifact" in value and not isinstance(value["approval_without_artifact"], bool):
        raise AppenderError("approval_without_artifact must be a boolean")
    if "approval_out_of_phase" in value and not isinstance(value["approval_out_of_phase"], bool):
        raise AppenderError("approval_out_of_phase must be a boolean")
    if "operator_unmatched" in value and not isinstance(value["operator_unmatched"], bool):
        raise AppenderError("operator_unmatched must be a boolean")
    if "operator_answered_from_ground_truth" in value and not isinstance(
        value["operator_answered_from_ground_truth"], bool
    ):
        raise AppenderError("operator_answered_from_ground_truth must be a boolean")
    if "operator_repeat_suppressed" in value and not isinstance(value["operator_repeat_suppressed"], bool):
        raise AppenderError("operator_repeat_suppressed must be a boolean")
    for key in (
        "driver_leading_rejected",
        "driver_obstacle_rejected",
        "driver_repeat_rejected",
        "driver_beat_substituted",
    ):
        if key in value and not isinstance(value[key], bool):
            raise AppenderError(f"{key} must be a boolean")
    if "operator_mode" in value and not isinstance(value["operator_mode"], str):
        raise AppenderError("operator_mode must be a string")
    if "operator_beat_id" in value and not isinstance(value["operator_beat_id"], str):
        raise AppenderError("operator_beat_id must be a string")
    if "outcome" in value and not isinstance(value["outcome"], str):
        raise AppenderError("outcome must be a string")
    if "event_outcomes" in value:
        outcomes = value["event_outcomes"]
        if not isinstance(outcomes, (list, tuple)) or any(not isinstance(item, str) for item in outcomes):
            raise AppenderError("event_outcomes must be a list of strings")
    if "events_not_transmitted" in value:
        undelivered = value["events_not_transmitted"]
        if not isinstance(undelivered, (list, tuple)) or any(not isinstance(item, str) for item in undelivered):
            raise AppenderError("events_not_transmitted must be a list of strings")
    if "counter_snapshots" in value:
        snapshots = value["counter_snapshots"]
        if not isinstance(snapshots, (list, tuple)) or any(not isinstance(item, Mapping) for item in snapshots):
            raise AppenderError("counter_snapshots must be a list of mappings")
    if "session_gap_seconds" in value:
        gap = value["session_gap_seconds"]
        if isinstance(gap, bool) or not isinstance(gap, int) or gap < 0:
            raise AppenderError("session_gap_seconds must be a non-negative integer")


def _expected_fact(facts: SupervisorFacts, key: str) -> object:
    if key == "per_model_row_counts":
        return facts.per_model_row_counts
    return facts.value_for(key)


def row_payload(evidence: TurnEvidence, *, _supervisor_claims_validated: bool = False) -> dict[str, object]:
    """Build a ledger row payload without storage-owned fields.

    The runner uses this helper without a ledger writer, so it also enforces
    the closed non-fact claim shape on that path. Supervisor-owned claims may
    bypass the local rejection only after ``append_turn_row`` has compared
    them with a supervisor reader.
    """

    if evidence.action_kind not in ACTION_KINDS:
        raise AppenderError(f"unknown ledger action kind: {evidence.action_kind!r}")
    if evidence.action_kind == "supervisor_fact" and not _supervisor_claims_validated:
        raise AppenderError("supervisor facts require a supervisor record reader")
    if evidence.action_kind != "supervisor_fact" and not _supervisor_claims_validated:
        supervisor_claims = _iter_supervisor_claims(evidence.claim)
        if supervisor_claims:
            raise AppenderError("supervisor-owned claims require a supervisor record reader")
        if evidence.claim is not None:
            _validate_non_fact_claim(evidence.claim)
    payload: dict[str, object] = {
        "run_id": evidence.run_id,
        "scenario_id": evidence.scenario_id,
        "turn": evidence.turn,
        "phase": evidence.phase,
        "phase_status": evidence.phase_status,
        "phase_status_reason": evidence.phase_status_reason,
        "action_kind": evidence.action_kind,
        "action": evidence.detail,
        "artifact_ref": evidence.artifact_ref,
        "claim": evidence.claim,
        "evidence_ref": evidence.evidence_ref,
        "qualification": evidence.qualification,
        "supersedes": evidence.supersedes,
        "term": evidence.term,
        "fact_key": evidence.fact_key,
        "event_ids": list(evidence.event_ids) if evidence.event_ids else None,
    }
    # Canonical row shape uses null for every absent optional observation.
    payload["matched_rule_id"] = evidence.matched_rule_id
    return payload


def append_turn_row(writer: LedgerWriter, evidence: TurnEvidence, *, supervisor_reader: SupervisorRecordReader | None = None) -> dict[str, object]:
    """Append one turn, rejecting supervisor-owned claims without provenance."""

    trusted_supervisor_claims = False
    if evidence.action_kind == "supervisor_fact":
        if not evidence.fact_key:
            raise AppenderError("supervisor_fact rows require an explicit fact_key")
        facts = _read_supervisor(supervisor_reader)
        expected = facts.value_for(evidence.fact_key)
        if expected is None or expected is LEDGER_MISSING:
            raise AppenderError(f"supervisor record has no value for fact_key {evidence.fact_key!r}")
        if evidence.claim is not None:
            raise AppenderError("supervisor fact claim must come from the supervisor reader")
        evidence = TurnEvidence(
            run_id=evidence.run_id,
            scenario_id=evidence.scenario_id,
            turn=evidence.turn,
            phase=evidence.phase,
            action_kind=evidence.action_kind,
            detail=evidence.detail,
            matched_rule_id=evidence.matched_rule_id,
            event_ids=evidence.event_ids,
            artifact_ref=evidence.artifact_ref,
            claim=expected,
            evidence_ref=evidence.evidence_ref,
            qualification=evidence.qualification,
            phase_status=evidence.phase_status,
            phase_status_reason=evidence.phase_status_reason,
            fact_key=evidence.fact_key,
            supersedes=evidence.supersedes,
            term=evidence.term,
        )
        trusted_supervisor_claims = True
    else:
        supervisor_claims = _iter_supervisor_claims(evidence.claim)
        if supervisor_claims:
            facts = _read_supervisor(supervisor_reader)
            for fact_key, claim in supervisor_claims:
                expected = _expected_fact(facts, fact_key)
                if expected is LEDGER_MISSING or _json_bytes(claim) != _json_bytes(expected):
                    raise AppenderError(f"supervisor-owned claim for {fact_key!r} must come from the supervisor reader")
            trusted_supervisor_claims = True
        elif evidence.claim is not None:
            _validate_non_fact_claim(evidence.claim)
    payload = row_payload(evidence, _supervisor_claims_validated=trusted_supervisor_claims)
    writer.append(payload)
    return payload


def append_supervisor_facts(
    writer: LedgerWriter,
    reader: SupervisorRecordReader | None,
    *,
    run_id: str,
    scenario_id: str,
    turn: int,
    phase: int,
    evidence_ref_prefix: str = "supervisor",
) -> tuple[dict[str, object], ...]:
    """Append all five canonical supervisor fact categories from one reader."""

    facts = _read_supervisor(reader)
    if facts.run_id is None or facts.artifact_id is None or facts.publish_sequence is None or facts.lifecycle_state is None:
        raise AppenderError("supervisor record is missing a canonical fact")
    if not facts.per_model_row_counts:
        raise AppenderError("supervisor record has no per-model row counts")
    entries: list[TurnEvidence] = [
        TurnEvidence(run_id, scenario_id, turn, phase, "supervisor_fact", "copied supervisor run id", fact_key="run_id", evidence_ref=f"{evidence_ref_prefix}#run_id", qualification="strong"),
        TurnEvidence(run_id, scenario_id, turn, phase, "supervisor_fact", "copied supervisor artifact id", fact_key="artifact_id", evidence_ref=f"{evidence_ref_prefix}#artifact_id", qualification="strong"),
        TurnEvidence(run_id, scenario_id, turn, phase, "supervisor_fact", "copied supervisor publish sequence", fact_key="publish_sequence", evidence_ref=f"{evidence_ref_prefix}#publish_sequence", qualification="strong"),
        *[
            TurnEvidence(run_id, scenario_id, turn, phase, "supervisor_fact", "copied supervisor row count", fact_key=f"per_model_row_counts.{model}", evidence_ref=f"{evidence_ref_prefix}#row_counts.{model}", qualification="strong")
            for model in sorted(facts.per_model_row_counts)
        ],
        TurnEvidence(run_id, scenario_id, turn, phase, "supervisor_fact", "copied supervisor lifecycle state", fact_key="lifecycle_state", evidence_ref=f"{evidence_ref_prefix}#lifecycle_state", qualification="strong"),
    ]
    return tuple(append_turn_row(writer, entry, supervisor_reader=reader) for entry in entries)


__all__ = [
    "AppenderError",
    "LedgerWriter",
    "StaticSupervisorRecordReader",
    "SupervisorRecordReader",
    "TurnEvidence",
    "append_supervisor_facts",
    "append_turn_row",
    "row_payload",
]
