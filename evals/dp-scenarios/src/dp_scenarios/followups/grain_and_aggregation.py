"""The grain-and-aggregation follow-up kind."""

from __future__ import annotations

from collections.abc import Mapping

from ..support import _MISSING, _lookup, _read_document, _string
from . import FollowUpContext, FollowUpKind, register


def check(
    scenario: object,
    closure: object,
    settings: Mapping[str, object],
    context: FollowUpContext,
) -> Mapping[str, object]:
    document = _read_document(closure, _string(settings.get("document"), "follow-up.document"))
    if document is _MISSING:
        return {"status": "not-examined", "passed": False, "findings": ["closure_not_examined"]}
    grain_path = _string(settings.get("grain_path"), "follow-up.grain_path")
    aggregation_path = _string(settings.get("aggregation_path"), "follow-up.aggregation_path")
    expected_grain = _string(settings.get("expected_grain"), "follow-up.expected_grain")
    expected_aggregation = _string(settings.get("expected_aggregation"), "follow-up.expected_aggregation")
    observed_grain = _lookup(document, grain_path)
    observed_aggregation = _lookup(document, aggregation_path)
    findings: list[str] = []
    if observed_grain is _MISSING:
        findings.append("grain_not_declared")
    elif observed_grain != expected_grain:
        findings.append("grain_mismatch")
    if observed_aggregation is _MISSING:
        findings.append("aggregation_not_declared")
    elif observed_aggregation != expected_aggregation:
        findings.append("aggregation_mismatch")
    return {
        "status": "examined",
        "passed": not findings,
        "findings": findings,
        "grain": observed_grain if observed_grain is not _MISSING else None,
        "aggregation": observed_aggregation if observed_aggregation is not _MISSING else None,
    }


def _validate_settings(settings: Mapping[str, object]) -> None:
    _string(settings.get("document"), "gates.follow-up.document")


KIND = register(
    FollowUpKind(
        name="grain_and_aggregation",
        gold_keys=frozenset({"answer", "control_total", "diagnostics"}),
        handler=check,
        certification_gold={"query": "answer"},
        validate_settings=_validate_settings,
    )
)
