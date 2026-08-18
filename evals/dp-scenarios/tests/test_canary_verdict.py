"""Fail-closed verdict matrix tests."""

from __future__ import annotations

import pytest

from dp_scenarios.canary.claims import Claim
from dp_scenarios.canary.verdict import UnknownFindingState, aggregate_verdict


def _claim(
    *,
    claim_id: str = "claim-1",
    code: str = "structure/known",
    direction: str = "documented-supported",
    probe_id: str = "kitchen-sink",
) -> Claim:
    return Claim(
        claim_id=claim_id,
        skill_file="/fixture/SKILL.md",
        line=7,
        quote="documented sentence",
        content_hash="sha256:span",
        expected_finding_code=code,
        direction=direction,
        probe_id=probe_id,
    )


def _report(*, stage: str = "structure", status: str = "pass", code: str = "structure/known") -> dict:
    return {
        "outcome": status if status in {"pass", "warn", "fail", "skip"} else "fail",
        "stages": [
            {
                "stage": stage,
                "status": status,
                "checks": [{"code": code, "status": status, "detail": "fixture"}],
            }
        ],
    }


@pytest.mark.parametrize("stage", ["structure", "runtime", "contract", "semantic"])
def test_skip_in_any_stage_is_blocking(stage: str) -> None:
    verdict = aggregate_verdict(_report(stage=stage, status="skip", code=f"{stage}/not_examined"), [_claim()])

    assert verdict.outcome == "blocked"
    assert any("skipped" in issue.message for issue in verdict.issues)


def test_unknown_finding_state_raises() -> None:
    report = _report(status="pass")
    report["stages"][0]["checks"][0]["status"] = "future-state"

    with pytest.raises(UnknownFindingState, match="future-state"):
        aggregate_verdict(report, [_claim()])


def test_documented_unsupported_without_finding_is_reverse_drift() -> None:
    claim = _claim(
        claim_id="median-unsupported",
        code="structure/spec_compile_failed",
        direction="documented-unsupported",
    )
    verdict = aggregate_verdict(_report(status="pass", code="structure/closure_pinned"), [claim])

    assert verdict.outcome == "drift"
    assert verdict.issues[0].kind == "reverse-drift"
    assert "median-unsupported → structure/spec_compile_failed → /fixture/SKILL.md:7" in verdict.issues[0].message


def test_known_finding_code_maps_to_claim_line() -> None:
    claim = _claim(code="runtime/secret_shape")
    verdict = aggregate_verdict(
        _report(stage="runtime", status="fail", code="runtime/secret_shape"),
        [claim],
    )

    assert verdict.outcome == "drift"
    assert "claim-1 → runtime/secret_shape → /fixture/SKILL.md:7" in verdict.issues[0].message


def test_claim_matching_is_scoped_to_the_probe_under_test() -> None:
    report = _report(stage="structure", status="fail", code="structure/spec_compile_failed")
    kitchen = _claim(claim_id="kitchen", code="structure/other")
    negative = _claim(
        claim_id="negative",
        code="structure/spec_compile_failed",
        direction="documented-unsupported",
        probe_id="unsupported-median",
    )

    kitchen_verdict = aggregate_verdict(report, [kitchen, negative], probe_id="kitchen-sink")
    negative_verdict = aggregate_verdict(report, [kitchen, negative], probe_id="unsupported-median")

    assert kitchen_verdict.outcome == "blocked"
    assert negative_verdict.outcome == "clean"


def test_unclaimed_warning_is_an_advisory_not_a_stage_blanket() -> None:
    verdict = aggregate_verdict(
        _report(stage="runtime", status="warn", code="runtime/optional_dependency"),
        [_claim(code="runtime/import_failed")],
    )

    assert verdict.outcome == "clean"
    assert verdict.issues == ()
    assert verdict.advisories[0].code == "runtime/optional_dependency"


def test_spec_compile_failure_is_blocking_even_when_claimed_unsupported() -> None:
    report = {
        "outcome": "fail",
        "stages": [
            {
                "stage": "structure",
                "status": "fail",
                "checks": [
                    {
                        "code": "structure/spec_compile_failed",
                        "status": "fail",
                        "detail": "fixture compile failure",
                    }
                ],
            },
            *[
                {
                    "stage": stage,
                    "status": "pass",
                    "checks": [{"code": f"{stage}/ok", "status": "pass", "detail": "fixture"}],
                }
                for stage in ("runtime", "contract", "semantic")
            ],
        ],
    }
    claim = _claim(
        claim_id="median-unsupported",
        code="structure/spec_compile_failed",
        direction="documented-unsupported",
    )

    verdict = aggregate_verdict(report, [claim])

    assert verdict.outcome == "blocked"
    assert any(issue.kind == "blocked" for issue in verdict.issues)


def test_spec_compile_failure_blocks_when_probe_also_has_supported_claims() -> None:
    report = _report(stage="structure", status="fail", code="structure/spec_compile_failed")
    claims = [
        _claim(claim_id="supported-other", code="structure/other"),
        _claim(
            claim_id="unsupported-construct",
            code="structure/spec_compile_failed",
            direction="documented-unsupported",
        ),
    ]

    verdict = aggregate_verdict(report, claims)

    assert verdict.outcome == "blocked"
    assert any(
        issue.code == "structure/spec_compile_failed"
        and "no approved interpretation exists for this probe" in issue.message
        for issue in verdict.issues
    )


def test_expected_negative_does_not_suppress_an_unexamined_skip() -> None:
    report = {
        "outcome": "fail",
        "stages": [
            {
                "stage": "structure",
                "status": "fail",
                "checks": [
                    {"code": "structure/spec_compile_failed", "status": "fail"},
                ],
            },
            {
                "stage": "runtime",
                "status": "skip",
                "checks": [{"code": "runtime/not_examined", "status": "skip"}],
            },
        ],
    }
    claim = _claim(
        claim_id="unsupported-construct",
        code="structure/spec_compile_failed",
        direction="documented-unsupported",
        probe_id="unsupported-construct",
    )

    verdict = aggregate_verdict(report, [claim])

    assert verdict.outcome == "blocked"
    assert any(issue.code == "runtime/not_examined" for issue in verdict.issues)
