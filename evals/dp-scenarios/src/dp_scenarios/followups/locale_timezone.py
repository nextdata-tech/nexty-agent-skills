"""Follow-up grader for the C6 locale and timezone-boundary drill."""

from __future__ import annotations

from collections.abc import Mapping

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
        return _not_examined("locale_timezone_not_examined")
    policy = target.get("time_policy")
    comparison = target.get("daily_comparison")
    unicode_query = target.get("unicode_query")
    decision = target.get("decision")
    if not isinstance(policy, Mapping):
        return _not_examined("timezone_policy_not_examined")
    if not isinstance(comparison, Mapping):
        return _not_examined("daily_boundary_comparison_not_examined")
    if not isinstance(unicode_query, Mapping):
        return _not_examined("unicode_query_not_examined")
    if not isinstance(decision, Mapping):
        return _not_examined("timezone_decision_not_examined")

    expected = scenario.raw_gold("reconciliation")
    diagnostics = scenario.raw_gold("diagnostics")
    if not isinstance(expected, Mapping) or not isinstance(diagnostics, Mapping):
        return _not_examined("locale_timezone_gold_not_examined")
    findings: list[str] = []
    if policy.get("source_timezone") != expected.get("source_timezone"):
        findings.append("source_timezone_not_preserved")
    if policy.get("daily_boundary") != "source_local":
        findings.append("daily_boundary_policy_wrong")
    if policy.get("utc_conversion") != "retain_utc_for_audit":
        findings.append("utc_audit_policy_missing")
    for key in ("source_local_total", "utc_total"):
        if comparison.get(key) != expected.get(key):
            findings.append(f"timezone_total_mismatch:{key}")
    if comparison.get("totals_invariant") is not True:
        findings.append("timezone_total_invariance_not_stated")
    for key in ("boundary_shift_rows", "boundary_shift_fraction"):
        if comparison.get(key) != expected.get(key):
            findings.append(f"boundary_shift_mismatch:{key}")
    if comparison.get("source_local_daily") != expected.get("local_daily"):
        findings.append("source_local_daily_rows_mismatch")
    if comparison.get("utc_daily") != expected.get("utc_daily"):
        findings.append("utc_daily_rows_mismatch")
    if unicode_query.get("category") != diagnostics.get("query_category"):
        findings.append("unicode_query_category_not_preserved")
    if unicode_query.get("row_count") != diagnostics.get("query_row_count"):
        findings.append("unicode_query_row_count_mismatch")
    if decision.get("id") != _string(settings.get("decision_id"), "follow-up.decision_id"):
        findings.append("timezone_decision_id_missing")
    if decision.get("status") not in {"proposed", "confirmed"}:
        findings.append("timezone_decision_not_governed")
    reporting_definition = decision.get("reporting_definition")
    if not isinstance(reporting_definition, Mapping) or reporting_definition != {
        "day_boundary": "source_local",
        "utc_role": "audit",
    }:
        findings.append("timezone_reporting_definition_missing")

    return {
        "status": "examined",
        "passed": not findings,
        "findings": findings,
        "expected_shift_rows": expected["boundary_shift_rows"],
        "reported_shift_rows": comparison.get("boundary_shift_rows"),
    }


KIND = register(
    FollowUpKind(
        name="locale_timezone",
        gold_keys=frozenset({"answer", "reconciliation", "diagnostics"}),
        handler=check,
        evidence_contract={
            "time_policy": (
                "object with source_timezone='America/New_York', daily_boundary='source_local', "
                "and utc_conversion='retain_utc_for_audit'"
            ),
            "daily_comparison": (
                "object with exactly source_local_total and utc_total as two-decimal "
                "strings, totals_invariant as a boolean, boundary_shift_rows as an "
                "integer, boundary_shift_fraction rounded to eight decimal places, "
                "and source_local_daily and utc_daily arrays; each array is ascending "
                "by day and each entry has exactly day (YYYY-MM-DD), row_count "
                "(integer), and total_amount (two-decimal string); do not add other "
                "fields"
            ),
            "unicode_query": (
                "object with exactly category='契約' and row_count as an integer; "
                "do not add other fields"
            ),
            "decision": (
                "object with exactly id='c6-source-local-day', status proposed or "
                "confirmed, and reporting_definition exactly "
                "{day_boundary:'source_local', utc_role:'audit'}; do not add "
                "other fields"
            ),
        },
        validate_settings=_validate_settings,
        gold_reproducible_from_fixture=True,
    )
)
