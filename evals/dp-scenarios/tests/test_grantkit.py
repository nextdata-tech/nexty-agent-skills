from __future__ import annotations

import json
import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import pytest

from dp_scenarios.grantkit import (
    FieldMapperUnavailable,
    GrantLedger,
    ScriptedGrantOperator,
    check_cumulative_budgets,
    grant_identity,
    make_grant_fixture,
    write_synthetic_evaluation_profile,
)


SPEC_PATH = Path(__file__).resolve().parents[1] / "../public/terminal-field-mapper-adapter-contract/fixtures/reference-closure/contracts/mapper_spec.json"


@dataclass(frozen=True)
class _GrantLike:
    mapper_spec_id: str = "sha256:spec"
    provider: str = "recorded"
    model: str = "test-model"
    source_path: str | None = None
    max_calls: int = 2
    max_tokens: int = 50
    max_usd: float = 1.0


@pytest.fixture
def nxd_repo_root(monkeypatch: pytest.MonkeyPatch) -> Path:
    configured = os.environ.get("EVAL_NXD_REPO_ROOT")
    if not configured:
        if os.environ.get("EVAL_REQUIRE_LIVE_FIXTURE") == "1":
            raise FieldMapperUnavailable(
                "field-mapper integration requires EVAL_NXD_REPO_ROOT"
            )
        pytest.skip(
            "SKIP_FIELD_MAPPER_DEPENDENCY: set EVAL_NXD_REPO_ROOT to an NXD checkout",
            allow_module_level=False,
        )
    root = Path(configured)
    if not (root / "components/nxd_py/data_product/nxd/experimental/field_mapper/__init__.py").is_file():
        if os.environ.get("EVAL_REQUIRE_LIVE_FIXTURE") == "1":
            raise FieldMapperUnavailable(
                "field-mapper integration requires a compatible EVAL_NXD_REPO_ROOT checkout"
            )
        pytest.skip(
            "SKIP_FIELD_MAPPER_DEPENDENCY: set EVAL_NXD_REPO_ROOT to an NXD checkout",
            allow_module_level=False,
        )
    monkeypatch.setenv("EVAL_NXD_REPO_ROOT", str(root))
    return root


@pytest.mark.field_mapper
def test_absent_field_mapper_is_a_distinct_fail_closed_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("EVAL_NXD_REPO_ROOT", raising=False)
    with pytest.raises(FieldMapperUnavailable, match="EVAL_NXD_REPO_ROOT"):
        make_grant_fixture(tmp_path / "missing-spec.json")


@pytest.mark.field_mapper
def test_native_grant_fixture_is_bound_and_path_independent(nxd_repo_root: Path) -> None:
    fixture = make_grant_fixture(SPEC_PATH)
    assert fixture.initial.mapper_spec_id == fixture.mapper_spec_id
    assert fixture.expanded.mapper_spec_id == fixture.mapper_spec_id
    assert fixture.initial.expires_at is not None
    assert fixture.initial.expires_at.year == 2099

    from dataclasses import replace

    moved = replace(fixture.initial, source_path="/another/run/path/grant.json")
    assert grant_identity(moved) == fixture.initial_id
    assert fixture.initial_id != fixture.expanded_id


@pytest.mark.field_mapper
def test_operator_expansion_records_both_grant_identities(nxd_repo_root: Path, tmp_path: Path) -> None:
    fixture = make_grant_fixture(SPEC_PATH)
    ledger = GrantLedger(tmp_path / "run", run_id="run-1", run_set_id="set-1")
    operator = ScriptedGrantOperator(fixture, expansion_turn=2)
    assert operator.install(ledger) == fixture.initial
    assert operator.grant_for_turn(1, ledger) == fixture.initial
    assert operator.grant_for_turn(2, ledger) == fixture.expanded
    with pytest.raises(ValueError, match="more than once"):
        operator.grant_for_turn(2, ledger)
    ledger.close()

    events = [json.loads(line) for line in ledger.events_path.read_text().splitlines()]
    expansion = next(item for item in events if item["event"] == "grant_expanded")
    assert expansion["previous_grant_id"] == fixture.initial_id
    assert expansion["grant_id"] == fixture.expanded_id
    assert expansion["previous_grant"] != expansion["grant"]


def _write_run(
    run_dir: Path,
    fixture: object,
    *,
    run_id: str,
    run_set_id: str,
    calls: int,
    claimed_calls: int | None = None,
) -> None:
    ledger = GrantLedger(run_dir, run_id=run_id, run_set_id=run_set_id)
    grant = fixture.initial  # type: ignore[attr-defined]
    ledger.issue(grant)
    for turn in range(1, calls + 1):
        response = ledger.dispatch(
            grant,
            lambda: {"provider": "recorded"},
            turn=turn,
            input_tokens=10,
            output_tokens=10,
            usd="0.001",
        )
        assert response["provider"] == "recorded"
    ledger.write_summary(claimed_provider_calls=claimed_calls)


@pytest.mark.field_mapper
def test_cumulative_checker_catches_cross_run_breach(nxd_repo_root: Path, tmp_path: Path) -> None:
    fixture = make_grant_fixture(SPEC_PATH, initial_max_calls=2, initial_max_tokens=50, initial_max_usd=0.003)
    first = tmp_path / "run-1"
    second = tmp_path / "run-2"
    _write_run(first, fixture, run_id="run-1", run_set_id="set-1", calls=2)
    _write_run(second, fixture, run_id="run-2", run_set_id="set-1", calls=2)

    report = check_cumulative_budgets([first, second], run_set_id="set-1")
    usage = report.usage[fixture.initial_id]
    assert usage.calls == 4
    assert usage.calls > usage.max_calls  # each individual run was at its ceiling
    assert "max_calls" in usage.breached
    assert usage.total_tokens == 80
    assert "max_tokens" in usage.breached
    assert usage.total_usd == Decimal("0.004")
    assert "max_usd" in usage.breached
    assert any(item.code == "cumulative_calls_exceeded" for item in report.findings)
    assert any(item.code == "cumulative_tokens_exceeded" for item in report.findings)
    assert any(item.code == "cumulative_spend_exceeded" for item in report.findings)
    assert not report.passed


@pytest.mark.field_mapper
def test_checker_does_not_trust_zero_call_run_claim(nxd_repo_root: Path, tmp_path: Path) -> None:
    fixture = make_grant_fixture(SPEC_PATH)
    run = tmp_path / "run"
    _write_run(run, fixture, run_id="run-1", run_set_id="set-1", calls=1, claimed_calls=0)
    report = check_cumulative_budgets([run], run_set_id="set-1")
    assert report.usage[fixture.initial_id].calls == 1
    assert any(item.code == "claimed_call_count_mismatch" for item in report.findings)


def test_dispatch_records_failed_provider_attempt(tmp_path: Path) -> None:
    """The ledger boundary records a failed attempted dispatch without a provider dependency."""

    # This test only exercises the durable boundary. Native-grant construction
    # remains covered by the marked tests above; the production ledger itself
    # accepts only a dataclass-shaped native Grant through grant_identity().
    ledger = GrantLedger(tmp_path / "run", run_id="run-1")
    grant = _GrantLike(max_calls=1, max_tokens=100)
    ledger.issue(grant)
    with pytest.raises(RuntimeError, match="provider failed"):
        ledger.dispatch(
            grant,
            lambda: (_ for _ in ()).throw(RuntimeError("provider failed")),
            turn=1,
            input_tokens=1,
            output_tokens=1,
            usd="0.001",
        )
    ledger.close()
    records = [json.loads(line) for line in ledger.transcript_path.read_text().splitlines()]
    assert [item["event"] for item in records] == ["provider_call_started", "provider_call"]
    assert records[-1]["status"] == "error"


def test_dispatch_returns_response_when_response_usage_is_malformed(tmp_path: Path) -> None:
    ledger = GrantLedger(tmp_path / "run", run_id="run-1")
    grant = _GrantLike()
    ledger.issue(grant)
    response = ledger.dispatch(
        grant,
        lambda: {"usage": {"input_tokens": "10", "output_tokens": 5}},
        turn=1,
    )
    assert response["usage"]["input_tokens"] == "10"
    ledger.close()
    records = [json.loads(line) for line in ledger.transcript_path.read_text().splitlines()]
    assert records[-1]["event"] == "provider_call"
    assert records[-1]["input_tokens"] is None
    assert records[-1]["usage_error"]


def _write_attempts_only_run(
    run_dir: Path,
    *,
    grant: _GrantLike | None = None,
    run_id: str = "run-1",
    count: int = 2,
) -> _GrantLike:
    grant = grant or _GrantLike()
    ledger = GrantLedger(run_dir, run_id=run_id, run_set_id="set-1")
    ledger.issue(grant)
    ledger.close()
    records = [
        {
            "attempt_id": f"{run_id}:attempt-{index}",
            "attempt_index": index - 1,
            "target_row_key": "row-1",
            "field": "field-1",
            "mapper_spec_id": grant.mapper_spec_id,
            "provider": grant.provider,
            "model": grant.model,
            "input_tokens": 10,
            "output_tokens": 10,
            "outcome": "success",
        }
        for index in range(1, count + 1)
    ]
    (run_dir / "attempts.jsonl").write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )
    (run_dir / "run-summary.json").write_text(
        json.dumps(
            {
                "schema": "nxd-eval-grant-run-summary-v1",
                "run_id": run_id,
                "run_set_id": "set-1",
                "claimed_provider_calls": count,
                "claimed_call_ids": [record["attempt_id"] for record in records],
            }
        ),
        encoding="utf-8",
    )
    return grant


def test_checker_reads_upstream_attempts_without_harness_transcript(tmp_path: Path) -> None:
    grant = _write_attempts_only_run(tmp_path / "run")
    report = check_cumulative_budgets([tmp_path / "run"], run_set_id="set-1")
    assert report.usage[grant_identity(grant)].calls == 2
    assert report.usage[grant_identity(grant)].total_tokens == 40
    assert not any(item.code == "malformed_run" for item in report.findings)
    assert any(item.code == "unknown_spend_usage" for item in report.findings)


def test_attempts_only_run_without_spend_ceiling_can_pass(tmp_path: Path) -> None:
    grant = _write_attempts_only_run(tmp_path / "run", grant=_GrantLike(max_usd=None))
    report = check_cumulative_budgets([tmp_path / "run"], run_set_id="set-1")
    usage = report.usage[grant_identity(grant)]
    assert report.passed
    assert usage.total_usd is None
    assert not any(item.code == "unknown_spend_usage" for item in report.findings)


@pytest.mark.parametrize(
    ("removed_attempt_indices", "finding_code"),
    [
        ([1], "noncontiguous_attempt_indices"),
        ([2, 3], "claimed_call_count_mismatch"),
    ],
    ids=["middle-attempt", "tail-attempts"],
)
def test_checker_rejects_upstream_attempt_deletions(
    tmp_path: Path,
    removed_attempt_indices: list[int],
    finding_code: str,
) -> None:
    grant = _write_attempts_only_run(
        tmp_path / "run",
        grant=_GrantLike(max_calls=10, max_tokens=1000, max_usd=None),
        count=4,
    )
    attempts_path = tmp_path / "run" / "attempts.jsonl"
    records = [json.loads(line) for line in attempts_path.read_text(encoding="utf-8").splitlines()]
    attempts_path.write_text(
        "".join(
            json.dumps(record) + "\n"
            for record in records
            if record["attempt_index"] not in removed_attempt_indices
        ),
        encoding="utf-8",
    )

    report = check_cumulative_budgets([tmp_path / "run"], run_set_id="set-1")

    assert any(item.code == finding_code for item in report.findings)
    assert report.usage[grant_identity(grant)].calls == 4 - len(removed_attempt_indices)


def test_checker_tally_is_invariant_when_definition_is_in_a_later_directory(tmp_path: Path) -> None:
    grant = _GrantLike(max_calls=10, max_tokens=1000, max_usd=None)
    usage_dir = tmp_path / "a-usage"
    definition_dir = tmp_path / "z-definition"
    _write_attempts_only_run(usage_dir, grant=grant, run_id="run-usage", count=1)
    _write_attempts_only_run(definition_dir, grant=grant, run_id="run-definition", count=0)

    events_path = usage_dir / "grant-events.jsonl"
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]
    events_path.write_text(
        "".join(json.dumps(event) + "\n" for event in events if event.get("event") != "grant_issued"),
        encoding="utf-8",
    )

    first_order = check_cumulative_budgets([usage_dir, definition_dir], run_set_id="set-1")
    second_order = check_cumulative_budgets([definition_dir, usage_dir], run_set_id="set-1")

    assert first_order.usage == second_order.usage
    assert first_order.findings == second_order.findings
    assert first_order.usage[grant_identity(grant)].calls == 1
    assert first_order.passed


def test_checker_rejects_run_that_inflates_its_own_grant_ceiling(tmp_path: Path) -> None:
    grant = _GrantLike()
    ledger = GrantLedger(tmp_path / "run", run_id="run-1", run_set_id="set-1")
    ledger.issue(grant)
    ledger.dispatch(grant, lambda: {"provider": "recorded"}, input_tokens=10, output_tokens=10, usd="0.001")
    ledger.close()
    lines = [json.loads(line) for line in ledger.events_path.read_text().splitlines()]
    for event in lines:
        if event.get("event") in {"grant_issued", "grant_expanded"}:
            event["grant"]["max_calls"] = 1_000_000_000
            event["grant"]["max_tokens"] = 1_000_000_000
            event["grant"]["max_usd"] = 1_000_000_000.0
    ledger.events_path.write_text("".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8")
    report = check_cumulative_budgets([ledger.run_dir], run_set_id="set-1")
    assert any(item.code == "grant_identity_mismatch" for item in report.findings)
    assert not any(item.max_calls == 1_000_000_000 for item in report.usage.values())


def test_checker_fails_closed_on_malformed_recorded_ceilings(tmp_path: Path) -> None:
    grant = _GrantLike()
    ledger = GrantLedger(tmp_path / "run", run_id="run-1", run_set_id="set-1")
    ledger.issue(grant)
    ledger.dispatch(grant, lambda: {"provider": "recorded"}, input_tokens=10, output_tokens=10, usd="0.001")
    ledger.close()
    lines = [json.loads(line) for line in ledger.events_path.read_text().splitlines()]
    for event in lines:
        if event.get("event") == "grant_issued":
            event["grant"]["max_calls"] = 1.0
            event["grant"]["max_tokens"] = "10"
    ledger.events_path.write_text("".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8")
    report = check_cumulative_budgets([ledger.run_dir], run_set_id="set-1")
    malformed = [item for item in report.findings if item.code == "malformed_grant_ceiling"]
    assert len(malformed) == 2


def test_checker_rejects_a_gap_in_sequential_grantkit_call_ids(tmp_path: Path) -> None:
    grant = _GrantLike(max_calls=10, max_tokens=1000)
    ledger = GrantLedger(tmp_path / "run", run_id="run-1", run_set_id="set-1")
    ledger.issue(grant)
    for turn in range(1, 4):
        ledger.dispatch(grant, lambda: {"provider": "recorded"}, turn=turn, input_tokens=1, output_tokens=1, usd="0.001")
    ledger.close()
    records = [json.loads(line) for line in ledger.transcript_path.read_text().splitlines()]
    ledger.transcript_path.write_text(
        "".join(json.dumps(record) + "\n" for record in records if "call-2" not in record["call_id"]),
        encoding="utf-8",
    )
    events = [json.loads(line) for line in ledger.events_path.read_text().splitlines()]
    ledger.events_path.write_text(
        "".join(
            json.dumps(event) + "\n"
            for event in events
            if not (event.get("event") == "provider_call_reserved" and event.get("call_id") == "run-1:call-2")
        ),
        encoding="utf-8",
    )
    ledger.write_summary(claimed_provider_calls=2, claimed_call_ids=["run-1:call-1", "run-1:call-3"])
    report = check_cumulative_budgets([ledger.run_dir], run_set_id="set-1")
    assert any(item.code == "noncontiguous_call_ids" for item in report.findings)


def test_checker_rejects_tail_deletion_using_append_only_call_reservations(tmp_path: Path) -> None:
    grant = _GrantLike(max_calls=10, max_tokens=1000)
    ledger = GrantLedger(tmp_path / "run", run_id="run-1", run_set_id="set-1")
    ledger.issue(grant)
    for turn in range(1, 4):
        ledger.dispatch(grant, lambda: {"provider": "recorded"}, turn=turn, input_tokens=1, output_tokens=1, usd="0.001")
    ledger.close()
    records = [json.loads(line) for line in ledger.transcript_path.read_text().splitlines()]
    ledger.transcript_path.write_text(
        "".join(json.dumps(record) + "\n" for record in records if "call-3" not in record["call_id"]),
        encoding="utf-8",
    )
    ledger.write_summary(claimed_provider_calls=2, claimed_call_ids=["run-1:call-1", "run-1:call-2"])
    report = check_cumulative_budgets([ledger.run_dir], run_set_id="set-1")
    assert any(item.code == "incomplete_provider_call" for item in report.findings)


def test_profile_writer_delegates_to_importable_builder(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    builder = tmp_path / "prepare_stdio_profile.py"
    builder.write_text(
        "import argparse, json\n"
        "from pathlib import Path\n"
        "def main():\n"
        "    parser = argparse.ArgumentParser()\n"
        "    parser.add_argument('--workspace')\n"
        "    parser.add_argument('--output')\n"
        "    args = parser.parse_args()\n"
        "    Path(args.output).write_text(json.dumps({'schema': 'nxd-synthetic-evaluation-profile-v1'}))\n"
        "    return 0\n",
        encoding="utf-8",
    )
    output = write_synthetic_evaluation_profile(workspace, tmp_path / "external" / "profile.json", builder=builder)
    assert json.loads(output.read_text())["schema"] == "nxd-synthetic-evaluation-profile-v1"
    assert output.stat().st_mode & 0o222 == 0


@pytest.mark.field_mapper
def test_profile_writer_uses_the_checked_in_upstream_builder(nxd_repo_root: Path, tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    closure = SPEC_PATH.resolve().parents[1]
    output = write_synthetic_evaluation_profile(
        workspace,
        tmp_path / "external" / "profile.json",
        closure=closure,
    )
    assert json.loads(output.read_text())["schema"] == "nxd-synthetic-evaluation-profile-v1"
    assert output.stat().st_mode & 0o222 == 0


@pytest.mark.field_mapper
def test_profile_writer_isolates_workspace_and_binds_fixture_grant(nxd_repo_root: Path, tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    sentinel = workspace / "my_scenario.txt"
    sentinel.write_text("caller-owned scenario", encoding="utf-8")
    closure = SPEC_PATH.resolve().parents[1]
    fixture = make_grant_fixture(SPEC_PATH, initial_max_calls=2, initial_max_tokens=40, initial_max_usd=0.02)
    output = write_synthetic_evaluation_profile(
        workspace,
        tmp_path / "external" / "profile.json",
        closure=closure,
        grant_fixture=fixture,
        workflow="my-scenario-workflow",
    )
    assert sentinel.read_text(encoding="utf-8") == "caller-owned scenario"
    profile = json.loads(output.read_text())
    assert profile["approval"]["events"][0]["workflow"] == "my-scenario-workflow"
    assert output.stat().st_mode & 0o222 == 0
