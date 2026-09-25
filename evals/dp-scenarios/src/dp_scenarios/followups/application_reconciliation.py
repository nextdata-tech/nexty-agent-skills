"""Follow-up grader for the C2 wrong-number lineage dispute."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from ..support import _string
from . import FollowUpContext, FollowUpKind, register


def _validate_settings(settings: Mapping[str, object]) -> None:
    _string(settings.get("decision_id"), "follow-up.decision_id")


def _not_examined(*findings: str) -> dict[str, object]:
    return {"status": "not-examined", "passed": False, "findings": list(findings)}


def check(
    scenario: object,
    target: object,
    settings: Mapping[str, object],
    context: FollowUpContext,
) -> Mapping[str, object]:
    del context
    if not isinstance(target, Mapping):
        return _not_examined("application_reconciliation_not_examined")
    reconciliation = target.get("reconciliation")
    lineage = target.get("lineage")
    query = target.get("governed_query")
    decision = target.get("decision")
    if not isinstance(reconciliation, Mapping):
        return _not_examined("reconciliation_evidence_not_examined")
    if not isinstance(lineage, Mapping):
        return _not_examined("lineage_evidence_not_examined")
    if not isinstance(query, Mapping):
        return _not_examined("governed_query_not_examined")
    if not isinstance(decision, Mapping):
        return _not_examined("dispute_decision_not_examined")

    expected = scenario.raw_gold("dispute")
    expected_lineage = scenario.raw_gold("lineage")
    if not isinstance(expected, Mapping) or not isinstance(expected_lineage, Mapping):
        return _not_examined("application_reconciliation_gold_not_examined")
    findings: list[str] = []
    for key, expected_value in expected.items():
        if reconciliation.get(key) != expected_value:
            findings.append(f"reconciliation_mismatch:{key}")
    if lineage.get("source_table") != expected_lineage.get("source_table"):
        findings.append("lineage_source_not_named")
    if lineage.get("dashboard_table") != expected_lineage.get("dashboard_table"):
        findings.append("lineage_dashboard_not_named")
    expected_clauses = expected_lineage.get("clauses")
    reported_clauses = lineage.get("clauses")
    if not isinstance(expected_clauses, Sequence) or isinstance(expected_clauses, (str, bytes, bytearray)):
        return _not_examined("lineage_gold_clauses_not_examined")
    if not isinstance(reported_clauses, Sequence) or isinstance(reported_clauses, (str, bytes, bytearray)):
        findings.append("lineage_clauses_not_examined")
    else:
        expected_by_id = {
            clause.get("id"): clause
            for clause in expected_clauses
            if isinstance(clause, Mapping)
        }
        reported_by_id = {
            clause.get("id"): clause
            for clause in reported_clauses
            if isinstance(clause, Mapping)
        }
        if set(reported_by_id) != set(expected_by_id):
            findings.append("lineage_clause_ids_mismatch")
        for clause_id, expected_clause in expected_by_id.items():
            reported_clause = reported_by_id.get(clause_id)
            if not isinstance(reported_clause, Mapping):
                continue
            for field in ("predicate", "excludes"):
                if reported_clause.get(field) != expected_clause.get(field):
                    findings.append(f"lineage_clause_mismatch:{clause_id}:{field}")
    if lineage.get("disjoint_exclusion_total") != expected_lineage.get("disjoint_exclusion_total"):
        findings.append("lineage_exclusions_not_reconciled")

    if query.get("grain") != "reconciliation_metric":
        findings.append("governed_query_grain_missing")
    filters = query.get("filters")
    if not isinstance(filters, Sequence) or isinstance(filters, (str, bytes, bytearray)):
        findings.append("governed_query_filters_not_examined")
    else:
        required_filters = {"status = active", "tombstoned = false"}
        if not required_filters.issubset({str(value) for value in filters}):
            findings.append("governed_query_filters_incomplete")
    expected_metrics = {
        "export_applications": expected["export_count"],
        "dashboard_active_applications": expected["dashboard_active_count"],
        "difference": expected["difference"],
        "status_filter_exclusions": expected["status_filter_exclusions"],
        "tombstone_exclusions": expected["tombstone_exclusions"],
    }
    if query.get("metrics") != expected_metrics:
        findings.append("governed_query_metrics_mismatch")
    if decision.get("id") != _string(settings.get("decision_id"), "follow-up.decision_id"):
        findings.append("dispute_decision_id_missing")
    if decision.get("status") not in {"proposed", "confirmed"}:
        findings.append("dispute_decision_not_governed")
    population = decision.get("population_definition")
    if not isinstance(population, Mapping) or population != {
        "status": "active",
        "tombstoned": "false",
    }:
        findings.append("dispute_population_definition_missing")

    return {
        "status": "examined",
        "passed": not findings,
        "findings": findings,
        "expected_difference": expected["difference"],
        "reported_difference": reconciliation.get("difference"),
    }


KIND = register(
    FollowUpKind(
        name="application_reconciliation",
        gold_keys=frozenset({"answer", "dispute", "lineage"}),
        handler=check,
        evidence_contract={
            "reconciliation": (
                "object with exactly integer fields export_count, "
                "dashboard_active_count, difference, status_filter_exclusions, "
                "and tombstone_exclusions; derive their values from the supplied "
                "source and do not include other fields"
            ),
            "lineage": (
                "object with exactly source_table='applications', "
                "dashboard_table='dashboard_snapshot', clauses, and "
                "disjoint_exclusion_total; clauses is an array with exactly two "
                "objects: {id:'active_status', predicate:'status != active', "
                "excludes: integer} and {id:'tombstone_filter', predicate:"
                "'status = active AND tombstoned = true', excludes: integer}; "
                "do not add other fields"
            ),
            "governed_query": (
                "object with exactly grain='reconciliation_metric', filters "
                "reflecting the operator-approved population definition, and a "
                "metrics object with exactly the integer keys "
                "export_applications, dashboard_active_applications, "
                "difference, status_filter_exclusions, and "
                "tombstone_exclusions"
            ),
            "decision": (
                "object with exactly id (string), status (string), and "
                "population_definition with exactly status (string) and "
                "tombstoned (string); use the ID and values supplied by the "
                "operator when the decision is presented, and do not infer or "
                "prepopulate a decision"
            ),
        },
        validate_settings=_validate_settings,
        gold_reproducible_from_fixture=True,
    )
)
