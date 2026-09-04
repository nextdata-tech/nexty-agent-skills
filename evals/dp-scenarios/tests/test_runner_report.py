"""Guard tests for report truthfulness and score/efficiency separation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dp_scenarios.canary import load_claims
from dp_scenarios.canary.verdict import Verdict
from dp_scenarios.operator.transport import OperatorMessage, TouchedFile, TurnResult
from dp_scenarios.runner import CanaryResult, ReplayRecording, TierError, TierRunner
from dp_scenarios.runner.report import _stable_document, human_summary, machine_report, write_report
from dp_scenarios.runner.cli import _canary_from_mapping
from dp_scenarios.runner.session import RecordedTurn

from test_runner_tier import (
    clean_canary,
    make_scenario,
    pins,
    populated_parent_child_recordings,
    recording_for,
    responses_for,
)


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
    machine_path, summary_path, _ = write_report(result, json_path=tmp_path / "tier.json", summary_path=tmp_path / "tier.txt")
    assert json.loads(machine_path.read_text(encoding="utf-8"))["efficiency_is_reported_only"] is True
    assert summary_path is not None and summary_path.read_text(encoding="utf-8")


def test_report_redacts_touched_file_contents_but_replay_stays_byte_faithful() -> None:
    secret_content = b"source_url=https://user:password@example.test/data"
    recording = ReplayRecording(
        (
            RecordedTurn(
                OperatorMessage("go"),
                TurnResult(files_touched=(TouchedFile("closure/spec.py", secret_content),)),
            ),
        )
    )

    report = recording.to_report_dict()
    report_content = report["turns"][0]["result"]["files_touched"][0]["content"]
    assert report_content == {
        "redacted": True,
        "sha256": "263a625f8a431698dd68458639a388143ee7106a8a93f4554af27a41c4b63cb7",
        "size_bytes": len(secret_content),
    }
    assert "password" not in json.dumps(report)
    assert recording.to_dict()["turns"][0]["result"]["files_touched"][0]["content"] == {
        "__bytes__": "c291cmNlX3VybD1odHRwczovL3VzZXI6cGFzc3dvcmRAZXhhbXBsZS50ZXN0L2RhdGE="
    }


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


def test_the_operator_surfaces_report_truncation_rather_than_calling_it_invalid(tmp_path: Path) -> None:
    """The rendered summary and report.json are the point of the truncation split.

    Everything below them was pinned at the RateReport level, but neither
    operator-facing surface was, so reverting the label or dropping the JSON key
    would have stayed green -- and the mislabeling would have come back
    silently. A truncated run scores PASSED with terminal_state=turn_timeout, so
    filing it under a heading that says "invalid" contradicts its own epoch line.
    """

    scenario, recordings = populated_parent_child_recordings(tmp_path, truncate_final_turn=True)
    result = TierRunner(
        [scenario],
        pins=pins(),
        canary=clean_canary(),
        replay_recordings={scenario.id: recordings},
    ).run()

    summary = human_summary(result)
    assert "runs excluded from rates (invalid or truncated): 1" in summary
    assert "(1 truncated)" in summary, "the reader cannot tell which exclusions were timeouts"
    assert "invalid runs excluded from rates" not in summary

    report = machine_report(result)
    repeatability = report["scenarios"][0]["repeatability"]
    assert repeatability["excluded_truncated"] == 1
    assert repeatability["excluded_invalid"] == 1


def test_an_unratable_batch_says_so_instead_of_printing_an_empty_header(tmp_path: Path) -> None:
    """A batch too truncated to rate must state that, not show a bare header."""

    scenario, recordings = populated_parent_child_recordings(tmp_path, truncate_every_epoch=True)
    result = TierRunner(
        [scenario],
        pins=pins(),
        canary=clean_canary(),
        replay_recordings={scenario.id: recordings},
    ).run()

    summary = human_summary(result)
    assert "too few epochs completed to rate this batch" in summary
    assert "- per-gate rates:\n" not in summary, "bare header with no rows beneath it"
    assert result.verdict == "ungraded"


def test_write_report_also_writes_a_readable_conversation(tmp_path: Path) -> None:
    """A transcript nobody knows to look for is a transcript nobody reads.

    The renderer existed but was never called from the runner, so seeing how a
    run actually went required knowing a separate script existed and handing it
    an `evidence/<scenario>/epoch-<n>` path. `summary.txt` gave gate codes and
    no conversation.

    Written beside the report rather than into the evidence bundle: the bundle's
    digest is computed when it is retained, so a file added afterwards would
    leave the recorded digest describing something the bundle no longer is.
    """

    scenario, recordings = populated_parent_child_recordings(tmp_path)
    result = TierRunner(
        [scenario],
        pins=pins(),
        canary=clean_canary(),
        replay_recordings={scenario.id: recordings},
        evidence_root=tmp_path / "evidence",
    ).run()

    out = tmp_path / "out"
    _, summary_target, transcripts_returned = write_report(
        result, json_path=out / "report.json", summary_path=out / "summary.txt"
    )

    transcripts = sorted(out.glob("conversation-*.md"))
    # Returned as well as written, so run_local_claude.py can name them on
    # stdout instead of the reader having to find summary.txt first.
    assert tuple(sorted(transcripts_returned)) == tuple(transcripts)
    assert transcripts, "no conversation was rendered next to the report"
    body = transcripts[0].read_text(encoding="utf-8")
    assert "OPERATOR>" in body and "AGENT>" in body, "the transcript has no conversation in it"

    # And the summary has to name them, or the reader still has to go looking.
    assert summary_target is not None
    summary = summary_target.read_text(encoding="utf-8")
    assert "Conversations:" in summary
    assert transcripts[0].name in summary

    # The digest recorded for the bundle must still describe the bundle.
    for run in result.scenario_runs:
        if run.evidence_bundle_dir:
            assert not list(Path(run.evidence_bundle_dir).glob("conversation-*.md"))


def test_a_failed_render_warns_and_still_returns_the_finished_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The fail-safe must not be silent.

    `transcript.py` states the rule for its own output -- "a renderer that
    silently drops a malformed turn is worse than one that crashes: the reader
    concludes the turn never happened" -- and it applies one level up. An
    absent transcript is otherwise indistinguishable from a run that retained
    no bundle, so a failure has to say so while the tier still completes.
    """

    from dp_scenarios.runner import report as report_module

    scenario, recordings = populated_parent_child_recordings(tmp_path)
    result = TierRunner(
        [scenario],
        pins=pins(),
        canary=clean_canary(),
        replay_recordings={scenario.id: recordings},
        evidence_root=tmp_path / "evidence",
    ).run()

    def explode(*_args: object, **_kwargs: object) -> str:
        raise RuntimeError("renderer exploded")

    monkeypatch.setattr(report_module, "render_epoch_conversation", explode)

    out = tmp_path / "out"
    machine_target, summary_target, conversations = report_module.write_report(
        result, json_path=out / "report.json", summary_path=out / "summary.txt"
    )

    # The run survives: both reports are written and the tier is not lost.
    assert machine_target.is_file()
    assert summary_target is not None and summary_target.is_file()
    assert conversations == ()

    warning = capsys.readouterr().err
    assert "could not render conversation" in warning
    assert "RuntimeError" in warning, "the operator cannot tell what failed"
