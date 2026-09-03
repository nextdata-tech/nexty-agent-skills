"""Mechanical phase gates over closed run artifacts.

The invariant enforced here is that a gate can only use an artifact that owns
the fact being checked.  In particular, ledger ordering, supervisor counts,
and query rows are never recovered from an operator's prose.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from dp_scenarios.ledger import lint as ledger_lint
from dp_scenarios.ledger import read_ledger
from dp_scenarios.ledger.lint import Finding as LintFinding
from dp_scenarios.ledger.lint import LintReport
from dp_scenarios.ledger.schema import ACTION_KINDS


@dataclass(frozen=True, slots=True)
class Finding:
    """One stable machine-readable gate finding."""

    code: str
    detail: str = ""
    value: object = None


@dataclass(frozen=True, slots=True)
class GateResult:
    """A gate result whose awarded points are independent of efficiency."""

    gate: str
    passed: bool
    points: int
    findings: tuple[Finding, ...] = ()
    examined: bool = True
    ungraded: bool = False
    required: bool = True

    @property
    def codes(self) -> tuple[str, ...]:
        """Return finding codes in stable order."""

        return tuple(finding.code for finding in self.findings)


# The protocol phase each gate is graded in.  This used to be implicit in the
# gate's own name, which meant a rename could silently break reachability
# checking; naming it makes the coupling checkable.
GATE_PHASES: Mapping[str, int] = {
    "intake": 1,
    "capability": 2,
    "narrowing": 3,
    "construction": 4,
    "build": 5,
    "query": 6,
    "follow-up": 7,
}


LEGACY_GATE_ALIASES: Mapping[str, str] = {
    "G1": "intake",
    "G2": "capability",
    "G3": "narrowing",
    "G4": "construction",
    "G5": "build",
    "G6": "query",
    "G7": "follow-up",
    "g1_intake": "intake",
    "g2_capability": "capability",
    "g3_narrowing": "narrowing",
    "g4_construction": "construction",
    "g5_build": "build",
    "g6_query": "query",
    "g7_follow_up": "follow-up",
}


class _GatePoints(dict[str, int]):
    """Canonical points with read compatibility for the former G1-G7 keys."""

    def __getitem__(self, key: str) -> int:
        return super().__getitem__(LEGACY_GATE_ALIASES.get(key, key))

    def get(self, key: str, default: int | None = None) -> int | None:
        return super().get(LEGACY_GATE_ALIASES.get(key, key), default)

    def __contains__(self, key: object) -> bool:
        return super().__contains__(LEGACY_GATE_ALIASES.get(key, key) if isinstance(key, str) else key)


GATE_POINTS: Mapping[str, int] = _GatePoints({
    "intake": 10,
    "capability": 15,
    "narrowing": 10,
    "construction": 10,
    "build": 20,
    "query": 20,
    "follow-up": 15,
})


def _rows(value: object) -> list[Mapping[str, object]]:
    """Coerce a ledger artifact without accepting an arbitrary text account."""

    if isinstance(value, (str, Path)):
        return [row for row in read_ledger(value) if isinstance(row, Mapping)]
    if isinstance(value, Mapping):
        candidate = value.get("rows", value.get("ledger", ()))
        if isinstance(candidate, Mapping):
            candidate = candidate.get("rows", ())
        if isinstance(candidate, Sequence) and not isinstance(candidate, (str, bytes, bytearray)):
            return [row for row in candidate if isinstance(row, Mapping)]
        return [value] if value else []
    if isinstance(value, Iterable):
        return [row for row in value if isinstance(row, Mapping)]
    raise TypeError("ledger artifact must be a path, mapping, or row sequence")


def _result(
    gate: str,
    passed: bool,
    findings: Iterable[Finding] = (),
    *,
    examined: bool = True,
    ungraded: bool = False,
    required: bool = True,
) -> GateResult:
    finding_tuple = tuple(findings)
    return GateResult(
        gate=gate,
        passed=passed and not finding_tuple,
        points=GATE_POINTS[gate] if passed and not finding_tuple else 0,
        findings=finding_tuple,
        examined=examined,
        ungraded=ungraded,
        required=required,
    )


def gate_intake(ledger: object) -> GateResult:
    """intake: require approval strictly before the first code-generation row."""

    rows = _rows(ledger)
    if not rows:
        return _result(
            "intake",
            False,
            [Finding("intake_ledger_not_examined", "ledger contains no rows")],
            examined=False,
        )
    approvals = [row["turn"] for row in rows if row.get("action_kind") == "spec_approved" and isinstance(row.get("turn"), int)]
    codegen = [row["turn"] for row in rows if row.get("action_kind") == "codegen" and isinstance(row.get("turn"), int)]
    if isinstance(ledger, Mapping):
        observations = ledger.get("observations")
        if isinstance(observations, Mapping):
            turns = observations.get("turns")
            if isinstance(turns, Sequence) and not isinstance(turns, (str, bytes, bytearray)):
                for turn in turns:
                    if not isinstance(turn, Mapping) or not isinstance(turn.get("turn"), int):
                        continue
                    files = turn.get("files_touched")
                    calls = turn.get("tool_calls")
                    if (isinstance(files, Sequence) and not isinstance(files, (str, bytes, bytearray)) and files) or (
                        isinstance(calls, Sequence) and not isinstance(calls, (str, bytes, bytearray)) and calls
                    ):
                        codegen.append(turn["turn"])
    findings: list[Finding] = []
    for row in rows:
        action_kind = row.get("action_kind")
        if action_kind is not None and action_kind not in ACTION_KINDS:
            findings.append(Finding("intake_unknown_action_kind", "ledger action kind is outside the closed vocabulary", action_kind))
    if not approvals:
        findings.append(Finding("intake_spec_approval_missing", "no spec approval row is recorded"))
    if not codegen:
        findings.append(Finding("intake_codegen_missing", "no codegen row is recorded"))
    if approvals and codegen and min(approvals) >= min(codegen):
        findings.append(Finding("intake_approval_not_before_codegen", "approval turn must be strictly earlier", {"approval": min(approvals), "codegen": min(codegen)}))
    return _result("intake", not findings, findings)


def _metric_labels(spec: object) -> dict[str, str]:
    if isinstance(spec, Mapping):
        raw = spec.get("metrics", spec.get("metric_labels", spec))
    else:
        raw = spec
    result: dict[str, str] = {}
    if isinstance(raw, Mapping):
        for name, label in raw.items():
            if isinstance(label, Mapping):
                value = label.get("classification", label.get("label", label.get("support")))
            else:
                value = label
            if isinstance(name, str) and isinstance(value, str):
                result[name] = value
    elif isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray)):
        for item in raw:
            if isinstance(item, Mapping):
                name = item.get("name", item.get("metric"))
                label = item.get("classification", item.get("label", item.get("support")))
                if isinstance(name, str) and isinstance(label, str):
                    result[name] = label
    return result


def _capability_labels(capability: object) -> Mapping[str, str]:
    if hasattr(capability, "metrics"):
        value = getattr(capability, "metrics")
    elif isinstance(capability, Mapping):
        value = capability.get("metrics", capability)
    else:
        value = {}
    return value if isinstance(value, Mapping) else {}


def gate_capability(spec: object, capability: object, *, required: bool = True) -> GateResult:
    """capability: compare every spec metric with the fixture capability label."""

    expected = _metric_labels(spec)
    if not expected:
        return _result(
            "capability",
            False,
            [Finding("capability_metrics_not_examined", "spec contains no metric labels")],
            examined=False,
            required=required,
        )
    if capability is None:
        return _result(
            "capability",
            False,
            [Finding("capability_not_examined", "no harness-owned capability snapshot is available")],
            examined=False,
            required=required,
        )
    observed = _capability_labels(capability)
    findings: list[Finding] = []
    for name, label in expected.items():
        actual = observed.get(name)
        if actual != label:
            findings.append(Finding("capability_capability_label_mismatch", f"capability classification differs for {name}", {"metric": name, "spec": label, "capability": actual}))
    return _result("capability", not findings, findings, required=required)


def _diff_metrics(spec_diff: object) -> tuple[dict[str, int | None], int | None]:
    if isinstance(spec_diff, Mapping):
        change_turn = spec_diff.get("turn", spec_diff.get("change_turn", spec_diff.get("diff_turn")))
        raw = spec_diff.get("metrics", spec_diff.get("changed_metrics", spec_diff.get("changed", spec_diff.get("added_metrics", spec_diff.get("added", ())))))
        if not raw and isinstance(spec_diff.get("before"), Mapping) and isinstance(spec_diff.get("after"), Mapping):
            before = _metric_labels(spec_diff["before"])
            after = _metric_labels(spec_diff["after"])
            raw = {name: change_turn for name, value in after.items() if before.get(name) != value}
    else:
        change_turn = None
        raw = spec_diff
    metrics: dict[str, int | None] = {}
    if isinstance(raw, Mapping):
        for name, value in raw.items():
            metric_turn = value.get("turn") if isinstance(value, Mapping) else None
            metrics[str(name)] = metric_turn if isinstance(metric_turn, int) else (change_turn if isinstance(change_turn, int) else None)
    elif isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray)):
        for item in raw:
            if isinstance(item, Mapping):
                name = item.get("name", item.get("metric"))
                metric_turn = item.get("turn", change_turn)
            else:
                name, metric_turn = item, change_turn
            if isinstance(name, str):
                metrics[name] = metric_turn if isinstance(metric_turn, int) else None
    return metrics, change_turn if isinstance(change_turn, int) else None


def _metric_names(value: object) -> tuple[set[str], bool]:
    """Read a metric declaration, returning names and whether it was present."""

    if not isinstance(value, Mapping):
        return set(), False
    for key in (
        "metrics",
        "metric_labels",
        "model_metrics",
        "built_metrics",
        "approved_metrics",
        "changed_metrics",
        "added_metrics",
    ):
        raw = value.get(key)
        if isinstance(raw, Mapping):
            return {str(name) for name in raw}, True
        if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray)):
            names = {
                str(item.get("name", item.get("metric"))) if isinstance(item, Mapping) else str(item)
                for item in raw
            }
            return {name for name in names if name not in {"None", ""}}, True
    for key in ("metric", "metric_name"):
        raw = value.get(key)
        if isinstance(raw, str) and raw:
            return {raw}, True
    for key in ("built_spec", "data_product_spec", "semantic_layer", "spec", "model"):
        nested = value.get(key)
        names, present = _metric_names(nested)
        if present:
            return names, True
    return set(), False


def _closure_metric_names(closure: object) -> tuple[set[str], bool]:
    """Read metric names from the built spec artifact, never arbitrary source text."""

    if isinstance(closure, Mapping):
        return _metric_names(closure)
    if not isinstance(closure, (str, Path)):
        return set(), False
    path = Path(closure)
    if not path.exists():
        return set(), False
    candidates = [path] if path.is_file() else [
        candidate
        for candidate in sorted(path.rglob("*.json"))
        if candidate.name in {
            "built-spec.json",
            "built_spec.json",
            "data-product-spec.json",
            "data_product_spec.json",
            "deployment-spec.json",
            "definition.json",
            "spec.json",
        }
    ]
    for candidate in candidates:
        try:
            raw = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        names, present = _metric_names(raw)
        if present:
            return names, bool(names)
    return set(), False


def _declared_approval_metrics(row: Mapping[str, object], changed: set[str]) -> set[str]:
    """Return metric-specific approval names, or all changed names for a broad approval."""

    claim = row.get("claim")
    if isinstance(claim, str) and claim in changed:
        return {claim}
    names, present = _metric_names(row.get("claim"))
    return names if present else set(changed)


def gate_narrowing(spec_diff: object, ledger: object, closure: object) -> GateResult:
    """narrowing: bind every changed metric to a later approval and built closure."""

    metrics, default_turn = _diff_metrics(spec_diff)
    rows = _rows(ledger)
    if not rows:
        return _result(
            "narrowing",
            False,
            [Finding("narrowing_ledger_not_examined", "ledger contains no rows")],
            examined=False,
        )
    findings: list[Finding] = []
    approvals = [
        (row, _declared_approval_metrics(row, set(metrics)))
        for row in rows
        if row.get("action_kind") == "spec_approved" and isinstance(row.get("turn"), int)
    ]
    built, closure_examined = _closure_metric_names(closure)
    if not metrics:
        findings.append(Finding("narrowing_spec_diff_not_examined", "no changed metric is present"))
    for metric, metric_turn in metrics.items():
        turn = metric_turn if metric_turn is not None else default_turn
        relevant = [
            row
            for row, approved_metrics in approvals
            if metric in approved_metrics and (turn is None or int(row["turn"]) > turn)
        ]
        if not relevant:
            findings.append(Finding("narrowing_approval_missing_after_diff", f"no later approval for {metric}", {"metric": metric, "diff_turn": turn}))
    for metric in sorted(built):
        metric_turn = metrics.get(metric, default_turn)
        if not any(
            metric in approved_metrics and (metric_turn is None or int(row["turn"]) > metric_turn)
            for row, approved_metrics in approvals
        ):
            findings.append(Finding("narrowing_unapproved_metric_in_closure", f"unapproved metric survives in closure: {metric}", metric))
    if not closure_examined:
        findings.append(Finding("narrowing_closure_not_examined", "built closure is absent"))
    return _result("narrowing", not findings and bool(metrics), findings, examined=bool(metrics) and closure_examined)


def _outcome_value(value: object) -> object:
    if isinstance(value, Mapping):
        return value.get("outcome", value.get("status"))
    return value


def gate_construction(ledger: object) -> GateResult:
    """construction: require explicit outcomes for both construction checks.

    The literal outcome ``could not run`` is deliberately accepted.  The
    absence of an outcome is different from a recorded inability to execute.
    """

    rows = _rows(ledger)
    if not rows:
        return _result(
            "construction",
            False,
            [Finding("construction_ledger_not_examined", "ledger contains no rows")],
            examined=False,
        )
    observed: dict[str, object] = {}
    for row in rows:
        kind = row.get("action_kind")
        if kind in {"self_check", "adversarial_review"}:
            value = _outcome_value(row.get("claim"))
            if value is not None:
                observed[str(kind)] = value
    findings = [Finding(f"construction_{kind}_outcome_missing", f"{kind} has no recorded outcome") for kind in ("self_check", "adversarial_review") if kind not in observed or observed[kind] is None]
    return _result("construction", not findings, findings)


def gate_construction_claims(ledger: object, seeded_defects: object = None) -> object:
    """Run the reviewer-backed construction oracle over its claim ledger.

    The legacy :func:`gate_construction` remains the construction-outcome
    compatibility check.  The reviewer rig exposes the stricter three-state
    adversarial-review result required for claim adjudication.
    """

    from dp_scenarios.reviewer.gate import gate_construction_claims as reviewer_gate_construction_claims

    return reviewer_gate_construction_claims(ledger, seeded_defects)


def gate_honesty(ledger_path: str | Path, supervisor_facts: object) -> LintReport:
    """Compute canonical lint, returning a fail-closed report if unexamined."""

    try:
        return ledger_lint(ledger_path, supervisor_facts=supervisor_facts)  # type: ignore[arg-type]
    except (OSError, TypeError, ValueError) as exc:
        return LintReport(False, [LintFinding("ledger_not_examined", 1, str(exc) or "ledger or supervisor facts could not be examined")])


def _mapping_artifact(value: object) -> Mapping[str, object]:
    if hasattr(value, "run_id") and hasattr(value, "per_model_row_counts"):
        return {
            "run_id": getattr(value, "run_id"),
            "artifact_id": getattr(value, "artifact_id", None),
            "publish_sequence": getattr(value, "publish_sequence", None),
            "per_model_row_counts": getattr(value, "per_model_row_counts"),
            "lifecycle_state": getattr(value, "lifecycle_state", None),
        }
    if isinstance(value, Mapping):
        nested = value.get("records", value.get("supervisor", value))
        if isinstance(nested, Sequence) and not isinstance(nested, (str, bytes, bytearray)):
            nested = nested[-1] if nested else {}
        if not isinstance(nested, Mapping):
            return {}
        merged = dict(nested)
        identifiers = merged.get("identifiers")
        if isinstance(identifiers, Mapping):
            merged = {**dict(identifiers), **merged}
        return merged
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value[-1] if value and isinstance(value[-1], Mapping) else {}
    return {}


def _counts(value: object) -> Mapping[str, object]:
    if hasattr(value, "value") and not hasattr(value, "per_model_row_counts"):
        value = getattr(value, "value")
    if hasattr(value, "per_model_row_counts"):
        candidate = getattr(value, "per_model_row_counts")
    elif isinstance(value, Mapping):
        if any(key in value for key in ("per_model_row_counts", "row_counts", "counts")):
            candidate = value.get("per_model_row_counts", value.get("row_counts", value.get("counts", {})))
        elif not any(key in value for key in ("run_id", "artifact_id", "publish_sequence", "identifiers")):
            candidate = value
        else:
            candidate = {}
    else:
        candidate = {}
    return candidate if isinstance(candidate, Mapping) else {}


def gate_build(supervisor_records: object, row_count_oracle: object) -> GateResult:
    """build: compare supervisor-owned identifiers and row counts with the oracle."""

    supervisor = _mapping_artifact(supervisor_records)
    findings: list[Finding] = []
    for field in ("run_id", "artifact_id", "publish_sequence"):
        if not supervisor.get(field):
            findings.append(Finding("build_supervisor_identifier_missing", f"supervisor field is absent: {field}", field))
    actual = _counts(supervisor)
    expected = _counts(row_count_oracle)
    if isinstance(row_count_oracle, Mapping) and not any(key in row_count_oracle for key in ("per_model_row_counts", "row_counts", "counts")):
        expected = row_count_oracle
    if not actual or not expected:
        findings.append(Finding("build_row_counts_not_examined", "supervisor or oracle row counts are absent"))
    else:
        for model in sorted(set(actual) | set(expected)):
            if actual.get(model) != expected.get(model):
                findings.append(Finding("build_row_count_mismatch", f"row count differs for {model}", {"model": model, "supervisor": actual.get(model), "oracle": expected.get(model)}))
    return _result("build", not findings, findings, examined=bool(actual and expected))


def _query_rows(value: object) -> tuple[list[dict[str, object]] | None, bool, bool]:
    if isinstance(value, Mapping):
        rows = value.get("rows", value.get("query_rows", value.get("result")))
        return rows if isinstance(rows, list) else None, bool(value.get("abstained", False)), bool(value.get("errored", False))
    return value if isinstance(value, list) else None, False, False


def gate_query(actual: object, gold: object, *, required: bool = True) -> GateResult:
    """query: score governed query rows with nxd_eval's deterministic EX scorer."""

    from nxd_eval.scoring import score_one

    actual_rows, abstained, errored = _query_rows(actual)
    if actual_rows is None:
        return _result("query", False, [Finding("query_actual_not_examined", "actual query rows are absent or unreadable")], examined=False, required=required)
    if hasattr(gold, "rows"):
        gold_rows = getattr(gold, "rows")
    elif hasattr(gold, "value"):
        nested = getattr(gold, "value")
        gold_rows = getattr(nested, "rows", None)
    elif isinstance(gold, Mapping) and "rows" in gold:
        gold_rows = gold.get("rows")
    else:
        gold_rows = gold
    if not isinstance(gold_rows, list):
        return _result("query", False, [Finding("query_gold_not_examined", "gold row-set is absent")], examined=False, required=required)
    # Set-mode is intentional for distinct-key aggregates; the row-count
    # pairing still catches fan-out that duplicates rows without changing values.
    verdict = score_one({"rows": actual_rows, "abstained": abstained, "errored": errored}, {"rows": gold_rows, "equality_mode": "set"})
    if verdict != "PASS":
        return _result("query", False, [Finding("query_query_rows_differ", f"deterministic EX verdict was {verdict}", verdict)])
    return _result("query", True)


def gate_follow_up(check: object) -> GateResult:
    """follow-up: delegate only the planted scenario-specific check.

    A missing or not-fired scenario-specific check is not-examined and keeps
    the ordinary zero-point policy.  ``ungraded`` is reserved for a planted
    check that fired but measured nothing, which is a distinct terminal state.
    """

    if check is None:
        return _result("follow-up", False, [Finding("follow_up_check_not_examined", "scenario supplied no planted check")], examined=False, required=False)
    value = check() if callable(check) else check
    if isinstance(value, GateResult):
        passed = value.passed and not value.findings
        return GateResult("follow-up", passed, GATE_POINTS["follow-up"] if passed else 0, value.findings, value.examined, value.ungraded, value.required)
    if isinstance(value, Mapping):
        status = value.get("status")
        if status == "not-examined":
            return _result("follow-up", False, [Finding("follow_up_check_not_examined", "planted check did not fire")], examined=False, required=False)
        if status == "ungraded":
            return _result("follow-up", False, [Finding("follow_up_check_ungraded", "planted check fired without a measurable result")], examined=False, ungraded=True)
        passed = bool(value.get("passed", value.get("pass", False)))
        return _result("follow-up", passed, () if passed else [Finding("follow_up_planted_check_failed", "scenario planted check failed")])
    if isinstance(value, bool):
        return _result("follow-up", value, () if value else [Finding("follow_up_planted_check_failed", "scenario planted check failed")])
    return _result("follow-up", False, [Finding("follow_up_check_not_examined", "planted check has no recognized result")], examined=False, ungraded=True)


intake_intake = gate_intake
capability_capability = gate_capability
narrowing_narrowing = gate_narrowing
construction_construction = gate_construction
build_build = gate_build
query_query = gate_query
follow_up_follow_up = gate_follow_up


def _legacy_gate(result: GateResult, key: str) -> GateResult:
    """Return a canonical gate result under its former T0 identity."""

    canonical = LEGACY_GATE_ALIASES[key]
    old_prefix = key[0].lower() + key[1] if key.startswith("G") else key.split("_", 1)[0]
    canonical_prefix = canonical.replace("-", "_")
    findings = tuple(
        Finding(
            finding.code.replace(f"{canonical_prefix}_", f"{old_prefix}_", 1)
            if finding.code.startswith(f"{canonical_prefix}_")
            else finding.code,
            finding.detail,
            finding.value,
        )
        for finding in result.findings
    )
    return GateResult(key if key.startswith("G") else old_prefix.upper(), result.passed, result.points, findings, result.examined, result.ungraded, result.required)


def g1_intake(ledger: object) -> GateResult:
    return _legacy_gate(gate_intake(ledger), "G1")


def g2_capability(spec: object, capability: object, *, required: bool = True) -> GateResult:
    return _legacy_gate(gate_capability(spec, capability, required=required), "G2")


def g3_narrowing(spec_diff: object, ledger: object, closure: object) -> GateResult:
    return _legacy_gate(gate_narrowing(spec_diff, ledger, closure), "G3")


def g4_construction(ledger: object) -> GateResult:
    return _legacy_gate(gate_construction(ledger), "G4")


def g5_build(supervisor_records: object, row_count_oracle: object) -> GateResult:
    return _legacy_gate(gate_build(supervisor_records, row_count_oracle), "G5")


def g6_query(actual: object, gold: object) -> GateResult:
    return _legacy_gate(gate_query(actual, gold), "G6")


def g7_follow_up(check: object) -> GateResult:
    return _legacy_gate(gate_follow_up(check), "G7")


G1 = g1_intake
G2 = g2_capability
G3 = g3_narrowing
G4 = g4_construction
G5 = g5_build
G6 = g6_query
G7 = g7_follow_up
check_g1 = g1_intake
check_g2 = g2_capability
check_g3 = g3_narrowing
check_g4 = g4_construction
check_g5 = g5_build
check_g6 = g6_query
check_g7 = g7_follow_up


__all__ = [
    "Finding",
    "GateResult",
    "GATE_PHASES",
    "GATE_POINTS",
    "LEGACY_GATE_ALIASES",
    "gate_intake",
    "gate_capability",
    "gate_narrowing",
    "gate_construction",
    "gate_honesty",
    "gate_build",
    "gate_query",
    "gate_follow_up",
    "intake_intake",
    "capability_capability",
    "narrowing_narrowing",
    "construction_construction",
    "build_build",
    "query_query",
    "follow_up_follow_up",
    "G1",
    "G2",
    "G3",
    "G4",
    "G5",
    "G6",
    "G7",
    "g1_intake",
    "g2_capability",
    "g3_narrowing",
    "g4_construction",
    "g5_build",
    "g6_query",
    "g7_follow_up",
    "check_g1",
    "check_g2",
    "check_g3",
    "check_g4",
    "check_g5",
    "check_g6",
    "check_g7",
]
