"""Regression guards for the live-source provenance contract."""

import json
from pathlib import Path


PUBLIC = Path(__file__).parents[1] / "public"


def _check(scenario: str, check_id: str) -> str:
    checks = json.loads((PUBLIC / scenario / "checks.json").read_text(encoding="utf-8"))
    return next(check["check"] for check in checks["checks"] if check["id"] == check_id)


def test_lastupdated_is_runtime_build_evidence_not_approved_spec_content():
    prompt = (PUBLIC / "worldbank-live" / "prompt.md").read_text(encoding="utf-8")
    disclosure = _check("worldbank-live", "context-discloses-as-of-fetch")

    for text in (prompt, disclosure):
        assert "evidence.source_state" in text
        assert "lastupdated" in text
    assert "must not be frozen into `dp-blueprint.approved.md`" in disclosure


def test_context_retirement_keeps_plan_rules_and_runtime_records_separate():
    """All affected live-supervisor scenarios name the new closure contract."""
    treasury = _check("treasury-yield-curve", "closure-python-only-fileset")
    assert "CONTEXT.md" not in treasury
    assert "dp-blueprint.approved.md" in treasury
    assert "dp-blueprint.lock.json" in treasury
    assert "build-record.json" in treasury

    country_checks = (
        _check("country-income-trajectory", "year-subset-selection-disclosed"),
        _check("country-income-trajectory", "aggregate-exclusion-ruling-landed"),
        _check("country-income-trajectory", "current-classification-scope-disclosed"),
    )
    assert all("CONTEXT.md" not in check for check in country_checks)
    assert "dp-blueprint.approved.md" in country_checks[0]
    assert "dp-blueprint.approved.md" in country_checks[1]
    assert "dp-blueprint.approved.md" in country_checks[2]

    for scenario in ("treasury-yield-curve", "country-income-trajectory"):
        prompt = (PUBLIC / scenario / "prompt.md").read_text(encoding="utf-8")
        assert "build-record.json" in prompt
        assert "runtime facts" in prompt
