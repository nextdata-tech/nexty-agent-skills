"""Guard tests for report truthfulness and score/efficiency separation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dp_scenarios.canary import load_claims
from dp_scenarios.canary.verdict import Verdict
from dp_scenarios.operator import OperatorEngine
from dp_scenarios.operator.transport import InMemoryTransport, TurnResult
from dp_scenarios.runner import CanaryResult, PinnedVersions, RecordingSession, ReplayRecording, TierError, TierRunner
from dp_scenarios.runner.report import _stable_document, human_summary, machine_report, write_report
from dp_scenarios.runner.cli import _canary_from_mapping

from test_runner_tier import clean_canary, make_scenario, pins, recording_for, responses_for


def test_demonstrated_once_is_not_rendered_as_a_rate() -> None:
    scenario = make_scenario("one-shot")
    recording = recording_for(scenario, responses_for(scenario))
    result = TierRunner([scenario], pins=pins(), canary=clean_canary(), replay_recordings={scenario.id: recording}).run()
    document = machine_report(result)
    summary = human_summary(result)

    repeatability = document["scenarios"][0]["repeatability"]
    assert "rates" not in repeatability
    assert repeatability["demonstrated_once"]["state"] == "demonstrated-once"
    assert "no rate is rendered" in summary


def test_clean_tier_definition_and_unexamined_gate_status_are_pinned() -> None:
    scenario = make_scenario("report-honesty")
    recording = recording_for(scenario, responses_for(scenario))
    result = TierRunner([scenario], pins=pins(), canary=clean_canary(), replay_recordings={scenario.id: recording}).run()
    document = machine_report(result)
    summary = human_summary(result)

    assert document["clean_tier_means"] == (
        "the canary found no drift in its claims, the scenarios' gates passed against their oracles, and the ledger lint was clean; "
        "this does not mean the unkeyed ledger chain is cryptographically intact"
    )
    assert "clean_tier_means" in document
    assert "unkeyed" in document["clean_tier_means"]
    assert "capability=UNEXAMINED" in summary
    assert "UNEXAMINED" in summary


def test_efficiency_is_sibling_to_scored_fields_and_never_inside_score(tmp_path: Path) -> None:
    scenario = make_scenario("efficiency")
    recording = recording_for(scenario, responses_for(scenario))
    result = TierRunner([scenario], pins=pins(), canary=clean_canary(), replay_recordings={scenario.id: recording}).run()
    document = machine_report(result)
    run = document["scenarios"][0]["runs"][0]

    assert "efficiency" in run
    assert "efficiency" not in run["score"]
    machine_path, summary_path = write_report(result, json_path=tmp_path / "tier.json", summary_path=tmp_path / "tier.txt")
    assert json.loads(machine_path.read_text(encoding="utf-8"))["efficiency_is_reported_only"] is True
    assert summary_path is not None and summary_path.read_text(encoding="utf-8")


def test_canary_block_report_contains_claim_code_and_line(tmp_path: Path) -> None:
    from dp_scenarios.canary.verdict import VerdictIssue

    canary = CanaryResult(Verdict("blocked", (VerdictIssue("drift", "wrong", "claim-1", "structure/changed", "skills/SKILL.md", 42),), ()))
    result = TierRunner([make_scenario("blocked")], pins=pins(), canary=canary, session_factory=lambda: None).run()
    summary = human_summary(result)
    assert "claim=claim-1" in summary
    assert "code=structure/changed" in summary
    assert "skills/SKILL.md:42" in summary
    assert "Scenarios: none ran" in summary


def test_replayed_canary_hash_is_bound_to_the_loaded_claims_file() -> None:
    claims_path = Path(__file__).parents[1] / "scenarios/drift-canary/claims.json"
    expected = load_claims(claims_path).baseline.approves_claims_hash
    document = {"verdict": {"outcome": "clean"}, "claims_hash": expected}

    with pytest.raises(TierError, match="requires a probe"):
        _canary_from_mapping(
            document,
            canary_dir=claims_path.parent,
            skills_root=claims_path.parent,
            expected_claims_hash=expected,
        )
    with pytest.raises(Exception, match="claims_hash"):
        _canary_from_mapping(
            {"verdict": {"outcome": "clean"}, "claims_hash": "arbitrary"},
            canary_dir=claims_path.parent,
            skills_root=claims_path.parent,
            expected_claims_hash=expected,
        )


def test_stable_document_removes_all_non_reproducible_keys_and_keeps_format_version() -> None:
    value = {
        "wall_clock": "discard-wall_clock",
        "wall_clock_seconds": "discard-wall_clock_seconds",
        "total_wall_clock_seconds": "discard-total_wall_clock_seconds",
        "observed_wall_clock_seconds": "discard-observed_wall_clock_seconds",
        "ledger_path": "discard-ledger_path",
        "fixture_dir": "discard-fixture_dir",
        "supervisor": "discard-supervisor",
        "closure": "discard-closure",
        "command": "discard-command",
        "stable": {
            "nested": [
                {
                    "wall_clock": True,
                    "wall_clock_seconds": True,
                    "total_wall_clock_seconds": True,
                    "observed_wall_clock_seconds": True,
                    "ledger_path": True,
                    "fixture_dir": True,
                    "supervisor": True,
                    "closure": True,
                    "command": True,
                },
                {"keep": 1},
            ]
        },
    }

    filtered = _stable_document(value)
    assert filtered == {"stable": {"nested": [{}, {"keep": 1}]}}

    result = machine_report(TierRunner([], pins=pins(), canary=clean_canary()).run())
    assert result["report_format_version"] == 1
