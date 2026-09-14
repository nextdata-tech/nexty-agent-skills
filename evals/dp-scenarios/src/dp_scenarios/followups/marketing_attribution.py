"""Follow-up grading for B3 marketing attribution evidence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from ..support import ScenarioError, _mapping, _string
from . import FollowUpContext, FollowUpKind, _ungraded, register


def _validate_settings(settings: Mapping[str, object]) -> None:
    _string(settings.get("decision_id"), "follow-up.decision_id")
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
    """Compare attribution, durable match facts, and the CPA policy."""

    del context
    if not isinstance(target, Mapping):
        return _not_examined("marketing_attribution_not_examined")
    expected = scenario.raw_gold("attribution")
    diagnostics_gold = scenario.raw_gold("diagnostics")
    if not isinstance(expected, Mapping) or not isinstance(diagnostics_gold, Mapping):
        return _ungraded("marketing_attribution_gold_unreadable")
    landed = target.get("landed")
    matching = target.get("matching")
    diagnostics = target.get("diagnostics")
    promise = target.get("promise")
    decisions = target.get("decision_history")
    if not isinstance(landed, Mapping):
        return _not_examined("attribution_landed_not_examined")
    if not isinstance(matching, Mapping):
        return _not_examined("attribution_matching_not_examined")
    if not isinstance(diagnostics, Mapping):
        return _not_examined("attribution_diagnostics_not_examined")
    if not isinstance(promise, Mapping):
        return _not_examined("attribution_promise_not_examined")
    if not isinstance(decisions, Sequence) or isinstance(decisions, (str, bytes, bytearray)):
        return _not_examined("attribution_decision_history_not_examined")

    findings: list[str] = []
    if landed != expected.get("landed"):
        findings.append("attribution_landed_disagrees_with_independent_reference")
    if matching != expected.get("matching"):
        findings.append("attribution_matching_disagrees_with_independent_reference")
    for key, value in diagnostics_gold.items():
        if diagnostics.get(key) != value:
            findings.append(f"attribution_diagnostics_mismatch:{key}")
    for key, value in _mapping(settings["promise_fields"], "follow-up.promise_fields").items():
        if promise.get(key) != value:
            findings.append(f"attribution_promise_mismatch:{key}")
    decision_id = _string(settings.get("decision_id"), "follow-up.decision_id")
    if not any(
        isinstance(entry, Mapping)
        and entry.get("id") == decision_id
        and entry.get("decision") == "matched_conversions_only"
        for entry in decisions
    ):
        findings.append("unmatched_cpa_denominator_decision_not_declared")
    return {"status": "examined", "passed": not findings, "findings": findings}


KIND = register(
    FollowUpKind(
        name="marketing_attribution",
        gold_keys=frozenset({"attribution", "diagnostics"}),
        handler=check,
        evidence_contract={
            "landed": (
                "object with rows of campaign_key, spend_cents, conversions, and cpa_cents; "
                "include only safely matched campaign pairs"
            ),
            "matching": (
                "object with ordered matches (spend_id, conversion_id, match_method), "
                "unmatched_spend_ids, and unmatched_conversion_ids"
            ),
            "diagnostics": (
                "source row counts, matched and unmatched counts, side-specific row match rates "
                "in basis points, and safe-match-method counts"
            ),
            "promise": (
                "casefold_whitespace='approved', unique_50_character_truncation='approved', "
                "fuzzy_matching='rejected', and unmatched_cpa_denominator='matched_conversions_only'"
            ),
            "decision_history": (
                "array containing {id: 'b3-unmatched-cpa-denominator', "
                "decision: 'matched_conversions_only'}"
            ),
        },
        validate_settings=_validate_settings,
        gold_reproducible_from_fixture=True,
    )
)
