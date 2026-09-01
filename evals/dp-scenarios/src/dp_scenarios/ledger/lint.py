"""Fail-closed linting for evidence, provenance, and protocol coverage.

The lint gate consumes a closed row vocabulary. Supervisor facts can enter the
gate only through ``action_kind=supervisor_fact`` and an explicit ``fact_key``;
free prose is never parsed as evidence. Every phase must be accounted for,
ledgers with an executed build phase must carry all five supervisor fact
categories, and all row identity and supersession references are checked
against the manifest and store-assigned row IDs.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterator

from .manifest import Manifest, ManifestError
from .schema import ACTION_KINDS, LedgerRow, PROTOCOL_PHASES, QUALIFICATIONS, SchemaError
from .store import LedgerFormatError, _read_json_lines, _read_verified


CLAIM_WITHOUT_EVIDENCE = "claim_without_evidence"
INVALID_QUALIFICATION = "invalid_qualification"
SUPERVISOR_FACT_MISMATCH = "supervisor_fact_mismatch"
SUPERVISOR_FACT_NOT_STRING = "supervisor_fact_not_string"
SUPERVISOR_FACT_ABSENT = "supervisor_fact_absent"
INCOMPLETE_SUPERVISOR_FACTS = "incomplete_supervisor_facts"
INVALID_MANIFEST = "invalid_manifest"
SENTINEL_NOT_PERMITTED_FOR_TIER = "sentinel_not_permitted_for_tier"
TURN_DECREASED = "turn_decreased"
ROW_MANIFEST_MISMATCH = "row_manifest_mismatch"
INVALID_SUPERSESSION = "invalid_supersession"
PHASE_UNACCOUNTED = "phase_unaccounted"
PHASE_NOT_APPLICABLE_WITHOUT_REASON = "phase_not_applicable_without_reason"
LEDGER_EMPTY = "ledger_empty"
INVALID_MATCHED_RULE_ID = "invalid_matched_rule_id"
INVALID_EVENT_ID = "invalid_event_id"

FACT_CATEGORIES = (
    "run_id",
    "artifact_id",
    "publish_sequence",
    "per_model_row_counts",
    "lifecycle_state",
)
SCALAR_FACT_KEYS = frozenset({"run_id", "artifact_id", "publish_sequence", "lifecycle_state"})
MATCHED_RULE_ID_RE = re.compile(
    r"(?:fallback\.no-leading|persona\.(?:source_question|approval_request|decision_request|status_query|other)|"
    r"(?:source|decision|status)\.answer\.[A-Za-z0-9][A-Za-z0-9_.-]*)\Z"
)
EVENT_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*\Z")

# A syntactically valid row with no protocol meaning is unsafe to certify.
PHASE_ACTION_KINDS: dict[int, frozenset[str]] = {
    1: frozenset({"intake"}),
    2: frozenset({"capability_probe"}),
    3: frozenset({"narrowing", "spec_presented", "spec_approved"}),
    4: frozenset({"codegen", "self_check", "adversarial_review", "spec_presented", "spec_approved"}),
    5: frozenset({"self_check", "build", "publish", "supervisor_fact", "spec_presented", "spec_approved"}),
    6: frozenset({"serve", "query", "supervisor_fact", "spec_presented", "spec_approved"}),
    7: frozenset({"follow_up", "supersession", "supervisor_fact", "spec_presented", "spec_approved"}),
}


class UnhandledSituationError(LedgerFormatError):
    """Raised when a row matches no closed action-kind/phase branch."""


class IncompleteSupervisorFactsError(ValueError):
    """Raised when supervisor input cannot represent a complete fact set."""

    def __init__(self, message: str, *, field: str, value: object) -> None:
        super().__init__(message)
        self.field = field
        self.value = value


@dataclass(frozen=True, slots=True)
class SupervisorFacts:
    """Closed representation of values copied from supervisor inspection."""

    run_id: object
    artifact_id: object
    publish_sequence: object
    per_model_row_counts: Mapping[str, object]
    lifecycle_state: object

    def __post_init__(self) -> None:
        for field_name in SCALAR_FACT_KEYS:
            value = getattr(self, field_name)
            if value is None:
                raise IncompleteSupervisorFactsError(
                    f"supervisor fact field {field_name} must be present and non-null",
                    field=field_name,
                    value=value,
                )
            if isinstance(value, str) and not value:
                raise IncompleteSupervisorFactsError(
                    f"supervisor fact field {field_name} must be a non-empty string when textual",
                    field=field_name,
                    value=value,
                )
        if not isinstance(self.per_model_row_counts, Mapping):
            raise TypeError("per_model_row_counts must be a mapping")
        if not self.per_model_row_counts:
            raise IncompleteSupervisorFactsError(
                "supervisor fact field per_model_row_counts must not be empty",
                field="per_model_row_counts",
                value=self.per_model_row_counts,
            )
        normalized_counts = dict(self.per_model_row_counts)
        for model, count in normalized_counts.items():
            if not isinstance(model, str) or not model:
                raise TypeError("per_model_row_counts keys must be non-empty strings")
            if count is None:
                raise IncompleteSupervisorFactsError(
                    f"supervisor fact per_model_row_counts.{model} must be non-null",
                    field=f"per_model_row_counts.{model}",
                    value=count,
                )
            if isinstance(count, str) and not count:
                raise IncompleteSupervisorFactsError(
                    f"supervisor fact per_model_row_counts.{model} must be a non-empty string when textual",
                    field=f"per_model_row_counts.{model}",
                    value=count,
                )
        object.__setattr__(self, "per_model_row_counts", MappingProxyType(normalized_counts))

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "SupervisorFacts":
        """Load only the five canonical fact categories, without aliases."""

        if not isinstance(value, Mapping):
            raise TypeError("supervisor_facts must be a SupervisorFacts or mapping")
        unknown = set(value) - set(FACT_CATEGORIES)
        if unknown:
            names = ", ".join(sorted(str(name) for name in unknown))
            raise TypeError(f"unknown supervisor fact field(s): {names}")
        missing = [category for category in FACT_CATEGORIES if category not in value]
        if missing:
            category = missing[0]
            raise IncompleteSupervisorFactsError(
                f"supervisor facts are missing category {category}",
                field=category,
                value=None,
            )
        return cls(
            run_id=value["run_id"],
            artifact_id=value["artifact_id"],
            publish_sequence=value["publish_sequence"],
            per_model_row_counts=value["per_model_row_counts"],  # type: ignore[arg-type]
            lifecycle_state=value["lifecycle_state"],
        )

    def value_for(self, fact_key: str) -> object:
        """Return one canonical fact or the missing sentinel."""

        if fact_key in SCALAR_FACT_KEYS:
            return getattr(self, fact_key)
        if fact_key.startswith("per_model_row_counts."):
            model = fact_key.removeprefix("per_model_row_counts.")
            if model:
                return self.per_model_row_counts.get(model, _MISSING)
        return _MISSING


@dataclass(frozen=True, slots=True)
class Finding:
    """One machine-readable lint finding and its offending value."""

    code: str
    line_number: int
    value: object
    field: str | None = None

    @property
    def line(self) -> int:
        return self.line_number

    @property
    def offending_value(self) -> object:
        return self.value

    @property
    def offending_field(self) -> str | None:
        return self.field


@dataclass(frozen=True, slots=True)
class LintReport:
    """Only a fully accounted, finding-free run is clean."""

    clean: bool
    findings: list[Finding]

    @property
    def dirty(self) -> bool:
        return not self.clean

    @property
    def is_clean(self) -> bool:
        return self.clean


@dataclass(frozen=True, slots=True)
class SupersessionResult:
    """A prior declared-term claim and its append-only correction status."""

    row: dict[str, object]
    has_superseding_row: bool

    @property
    def superseded(self) -> bool:
        return self.has_superseding_row

    def __iter__(self) -> Iterator[object]:
        yield self.row
        yield self.has_superseding_row


def lint(
    ledger_path: str | Path,
    *,
    supervisor_facts: SupervisorFacts | Mapping[str, object],
) -> LintReport:
    """Lint one complete, closed ledger against canonical supervisor facts.

    This non-locking reader must run only after all appends and terminal-anchor
    updates are complete; callers must not lint a ledger while it is open for
    append.
    """

    path = Path(ledger_path)
    incomplete_fact_finding: Finding | None = None
    try:
        facts = supervisor_facts if isinstance(supervisor_facts, SupervisorFacts) else SupervisorFacts.from_mapping(supervisor_facts)
    except IncompleteSupervisorFactsError as exc:
        facts = None
        incomplete_fact_finding = Finding(INCOMPLETE_SUPERVISOR_FACTS, 1, exc.value, field=exc.field)
    records = _load_records(path)
    findings: list[Finding] = []
    if not records:
        return LintReport(False, [Finding(INVALID_MANIFEST, 1, "missing row 0", field="manifest")])

    manifest: Manifest | None = None
    try:
        manifest = Manifest.from_record(records[0], replay=None)
    except ManifestError as exc:
        code = SENTINEL_NOT_PERMITTED_FOR_TIER if exc.code == SENTINEL_NOT_PERMITTED_FOR_TIER else INVALID_MANIFEST
        findings.append(Finding(code, 1, exc.value, field=exc.field))

    parsed_rows: list[LedgerRow] = []
    if manifest is not None:
        records, _raw_lines, parsed_rows = _read_verified(path)
    else:
        for line_number, record in enumerate(records[1:], start=2):
            try:
                parsed_rows.append(LedgerRow.from_mapping(record, stored=False))
            except (SchemaError, TypeError, KeyError) as exc:
                raise LedgerFormatError(f"malformed ledger {path} at line {line_number}: {exc}") from exc

    if not parsed_rows:
        findings.append(Finding(LEDGER_EMPTY, 1, "no evidence rows", field="rows"))
    if incomplete_fact_finding is not None:
        findings.insert(0, incomplete_fact_finding)
    if manifest is not None and facts is not None and incomplete_fact_finding is None:
        _lint_rows(path, manifest, parsed_rows, facts, findings)
    return LintReport(clean=not findings, findings=findings)


def _lint_rows(
    path: Path,
    manifest: Manifest,
    rows: list[LedgerRow],
    facts: SupervisorFacts,
    findings: list[Finding],
) -> None:
    previous_turn: int | None = None
    accounted_phases: set[int] = set()
    fact_rows: dict[str, list[LedgerRow]] = {category: [] for category in FACT_CATEGORIES}
    row_by_id = {row.row_id: row for row in rows}

    for index, row in enumerate(rows, start=2):
        _classify_row(path, index, row)
        accounted_phases.add(row.phase)
        if row.phase_status == "not-applicable" and not row.phase_status_reason:
            findings.append(Finding(PHASE_NOT_APPLICABLE_WITHOUT_REASON, index, row.phase_status_reason, field="phase_status_reason"))
        if row.run_id != manifest.run_id or row.scenario_id != manifest.scenario_id:
            findings.append(Finding(ROW_MANIFEST_MISMATCH, index, {"run_id": row.run_id, "scenario_id": row.scenario_id}, field="run_id/scenario_id"))
        if row.matched_rule_id is not None and MATCHED_RULE_ID_RE.fullmatch(row.matched_rule_id) is None:
            findings.append(Finding(INVALID_MATCHED_RULE_ID, index, row.matched_rule_id, field="matched_rule_id"))
        for event_id in row.event_ids or ():
            if EVENT_ID_RE.fullmatch(event_id) is None:
                findings.append(Finding(INVALID_EVENT_ID, index, event_id, field="event_ids"))

        if row.action_kind == "supervisor_fact":
            if not row.evidence_ref:
                findings.append(Finding(CLAIM_WITHOUT_EVIDENCE, index, row.claim, field="evidence_ref"))
            if row.qualification not in QUALIFICATIONS:
                findings.append(Finding(INVALID_QUALIFICATION, index, row.qualification, field="qualification"))
        elif _has_claim(row.claim):
            if not row.evidence_ref:
                findings.append(Finding(CLAIM_WITHOUT_EVIDENCE, index, row.claim, field="evidence_ref"))
            if row.action_kind == "spec_approved" and row.qualification != "strong":
                findings.append(Finding(INVALID_QUALIFICATION, index, row.qualification, field="qualification"))
            elif row.qualification not in QUALIFICATIONS:
                findings.append(Finding(INVALID_QUALIFICATION, index, row.qualification, field="qualification"))
        elif row.qualification not in (None, "") and row.qualification not in QUALIFICATIONS:
            findings.append(Finding(INVALID_QUALIFICATION, index, row.qualification, field="qualification"))

        if previous_turn is not None and row.turn < previous_turn:
            findings.append(Finding(TURN_DECREASED, index, row.turn, field="turn"))
        previous_turn = row.turn

        category = _fact_category(row.fact_key) if row.action_kind == "supervisor_fact" else None
        if category is not None:
            fact_rows[category].append(row)
            _lint_supervisor_fact(index, row, facts, findings)
        _lint_supersession(index, row, row_by_id, findings)

    for phase in sorted(PROTOCOL_PHASES - accounted_phases):
        findings.append(Finding(PHASE_UNACCOUNTED, 1, phase, field="phase"))
    if any(row.phase == 5 and row.phase_status == "executed" for row in rows):
        for category in FACT_CATEGORIES:
            if not fact_rows[category]:
                findings.append(Finding(SUPERVISOR_FACT_ABSENT, _first_build_line(rows), category, field="fact_key"))
        if fact_rows["per_model_row_counts"]:
            observed_models = {
                row.fact_key.removeprefix("per_model_row_counts.")
                for row in fact_rows["per_model_row_counts"]
                if row.fact_key is not None
            }
            for model in facts.per_model_row_counts:
                if model not in observed_models:
                    findings.append(Finding(SUPERVISOR_FACT_ABSENT, _first_build_line(rows), model, field="fact_key"))


def _classify_row(path: Path, line_number: int, row: LedgerRow) -> None:
    if row.action_kind not in ACTION_KINDS:
        raise UnhandledSituationError(f"unhandled ledger situation in {path} at line {line_number}: action_kind {row.action_kind!r}")
    if row.action_kind not in PHASE_ACTION_KINDS[row.phase]:
        raise UnhandledSituationError(f"unhandled ledger situation in {path} at line {line_number}: {row.action_kind!r} in phase {row.phase}")
    if row.action_kind == "supervisor_fact" and _fact_category(row.fact_key) is None:
        raise UnhandledSituationError(f"unhandled ledger situation in {path} at line {line_number}: invalid or absent fact_key")


def _lint_supervisor_fact(line_number: int, row: LedgerRow, facts: SupervisorFacts, findings: list[Finding]) -> None:
    assert row.fact_key is not None
    expected = facts.value_for(row.fact_key)
    if expected is _MISSING:
        findings.append(Finding(SUPERVISOR_FACT_MISMATCH, line_number, row.claim, field=row.fact_key))
        return
    if isinstance(expected, str) and not isinstance(row.claim, str):
        findings.append(Finding(SUPERVISOR_FACT_NOT_STRING, line_number, row.claim, field=row.fact_key))
        return
    if _json_token(row.claim) != _json_token(expected):
        findings.append(Finding(SUPERVISOR_FACT_MISMATCH, line_number, row.claim, field=row.fact_key))


def _lint_supersession(line_number: int, row: LedgerRow, row_by_id: Mapping[int | None, LedgerRow], findings: list[Finding]) -> None:
    if row.supersedes is not None and row.action_kind != "supersession":
        findings.append(Finding(INVALID_SUPERSESSION, line_number, row.supersedes, field="supersedes"))
        return
    if row.action_kind == "supersession" and not _has_claim(row.claim):
        findings.append(Finding(INVALID_SUPERSESSION, line_number, row.claim, field="claim"))
    if row.action_kind == "supersession" and row.supersedes is None:
        findings.append(Finding(INVALID_SUPERSESSION, line_number, row.supersedes, field="supersedes"))
        return
    if row.supersedes is None:
        return
    target = row_by_id.get(row.supersedes)
    if target is None or target.row_id is None or row.row_id is None or target.row_id >= row.row_id or target.turn > row.turn:
        findings.append(Finding(INVALID_SUPERSESSION, line_number, row.supersedes, field="supersedes"))


def supersession_diff(ledger_path: str | Path, *, term: str, change_turn: int) -> list[SupersessionResult]:
    """Return pre-change claims whose declared term exactly matches ``term``."""

    if not isinstance(term, str) or not term:
        raise ValueError("term must be a non-empty string")
    if isinstance(change_turn, bool) or not isinstance(change_turn, int) or change_turn < 1:
        raise ValueError("change_turn must be a positive integer")
    path = Path(ledger_path)
    _records, _raw_lines, rows = _read_verified(path)
    candidates = [row for row in rows if row.turn < change_turn and row.action_kind != "supersession" and row.term == term and _has_claim(row.claim)]
    results: list[SupersessionResult] = []
    for candidate in candidates:
        assert candidate.row_id is not None
        superseded = any(later.turn > candidate.turn and later.supersedes == candidate.row_id for later in rows)
        results.append(SupersessionResult(candidate.to_dict(), superseded))
    return results


def _load_records(path: Path) -> list[Any]:
    return _read_json_lines(path)


def _fact_category(fact_key: str | None) -> str | None:
    if fact_key in SCALAR_FACT_KEYS:
        return fact_key
    if fact_key is not None and fact_key.startswith("per_model_row_counts.") and fact_key.removeprefix("per_model_row_counts."):
        return "per_model_row_counts"
    return None


def _has_claim(value: object) -> bool:
    return value is not None and value != ""


def _json_token(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _first_build_line(rows: list[LedgerRow]) -> int:
    for index, row in enumerate(rows, start=2):
        if row.phase == 5:
            return index
    return 1


_MISSING = object()
