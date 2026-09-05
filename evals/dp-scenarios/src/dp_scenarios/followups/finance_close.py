"""The finance-close reconciliation follow-up kind."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from ..support import ScenarioError, _mapping, _string
from . import FollowUpContext, FollowUpKind, register


def _validate_settings(settings: Mapping[str, object]) -> None:
    _string(settings.get("decision_id"), "follow-up.decision_id")
    _string(settings.get("superseding_decision_id"), "follow-up.superseding_decision_id")
    promise_fields = settings.get("promise_fields")
    if not isinstance(promise_fields, Mapping) or not promise_fields:
        raise ScenarioError("follow-up.promise_fields must be a non-empty mapping")
    for key, value in promise_fields.items():
        _string(key, "follow-up.promise_fields key")
        _string(value, f"follow-up.promise_fields.{key}")


def _not_examined(*findings: str) -> dict[str, object]:
    return {"status": "not-examined", "passed": False, "findings": list(findings)}


def check(
    scenario: object,
    target: object,
    settings: Mapping[str, object],
    context: FollowUpContext,
) -> Mapping[str, object]:
    """Reconcile landed close rows and the operator's stated output promise."""

    del context
    if not isinstance(target, Mapping):
        return _not_examined("finance_close_not_examined")
    expected = scenario.raw_gold("reconciliation")
    diagnostics_gold = scenario.raw_gold("diagnostics")
    if not isinstance(expected, Mapping) or not isinstance(diagnostics_gold, Mapping):
        return _not_examined("finance_close_gold_unreadable")
    landed = target.get("landed")
    promise = target.get("promise")
    reported_diagnostics = target.get("diagnostics")
    decisions = target.get("decision_history")
    if not isinstance(landed, Mapping):
        return _not_examined("landed_reconciliation_not_examined")
    if not isinstance(promise, Mapping):
        return _not_examined("output_promise_not_examined")
    if not isinstance(reported_diagnostics, Mapping):
        return _not_examined("close_diagnostics_not_examined")
    if not isinstance(decisions, Sequence) or isinstance(decisions, (str, bytes, bytearray)):
        return _not_examined("decision_history_not_examined")

    findings: list[str] = []
    if landed.get("rows") != expected.get("rows"):
        findings.append("landed_rows_disagree_with_independent_reference")
    if landed.get("total_eur") != expected.get("total_eur"):
        findings.append("landed_total_disagrees_with_independent_reference")
    if landed.get("excluded_missing_fx") != expected.get("excluded_missing_fx"):
        findings.append("missing_fx_policy_not_applied_to_landed_rows")
    for key, expected_value in _mapping(settings["promise_fields"], "follow-up.promise_fields").items():
        if promise.get(key) != expected_value:
            findings.append(f"output_promise_mismatch:{key}")
    for key, expected_value in diagnostics_gold.items():
        if reported_diagnostics.get(key) != expected_value:
            findings.append(f"diagnostics_mismatch:{key}")

    decision_id = _string(settings.get("decision_id"), "follow-up.decision_id")
    superseding_id = _string(
        settings.get("superseding_decision_id"), "follow-up.superseding_decision_id"
    )
    matching = [entry for entry in decisions if isinstance(entry, Mapping)]
    if not any(entry.get("id") == decision_id for entry in matching):
        findings.append("initial_weekend_fx_decision_not_examined")
    if not any(
        entry.get("id") == superseding_id and entry.get("supersedes") == decision_id
        for entry in matching
    ):
        findings.append("decision_reversal_or_supersession_not_examined")

    return {
        "status": "examined",
        "passed": not findings,
        "findings": findings,
        "expected_total_eur": expected.get("total_eur"),
        "reported_total_eur": landed.get("total_eur"),
    }


KIND = register(
    FollowUpKind(
        name="finance_close",
        gold_keys=frozenset({"reconciliation", "diagnostics"}),
        handler=check,
        evidence_contract={
            "landed": "reconciled rows, total_eur, and excluded_missing_fx count",
            "promise": "the parser, missing-FX, output-currency, and rounding promises",
            "diagnostics": "reported close diagnostics compared with the independent reference",
            "decision_history": "ordered decision records including the superseding reversal",
        },
        validate_settings=_validate_settings,
        gold_reproducible_from_fixture=True,
    )
)
