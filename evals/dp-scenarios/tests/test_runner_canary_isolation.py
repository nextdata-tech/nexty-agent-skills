"""Concurrent live canary runs must not share one working directory.

The supervisor runs with the canary closure as its working directory and
writes run state beside it.  Two live runs pointed at the checked-in package
therefore shared one store, and the loser of the race reported "database is
locked" -- contention wearing the costume of a canary defect (issue #238).
"""

from __future__ import annotations

import concurrent.futures
import time
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace

import pytest

from dp_scenarios.canary import Verdict
from dp_scenarios.canary.probe import ProbeResult
from dp_scenarios.runner import tier as tier_module
from dp_scenarios.runner.tier import run_drift_canary

from _repo_paths import REPO_ROOT


CANARY_ROOT = REPO_ROOT / "evals/dp-scenarios/scenarios/drift-canary"
BOUND = 30.0


@pytest.fixture
def stubbed_supervisor(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """Record the closure each probe/build was handed, without a supervisor."""

    closures: list[Path] = []

    def fake_preflight(closure: Path, **kwargs: object) -> ProbeResult:
        closures.append(Path(closure))
        # Hold the directory briefly so concurrent callers genuinely overlap;
        # a serialized implementation would still pass a distinctness check.
        time.sleep(0.2)
        return ProbeResult("supervisor", str(closure), ("supervisor",), 0, {"probe_id": "kitchen-sink"}, "", "")

    def fake_build(closure: Path, **kwargs: object) -> Mapping[str, object]:
        closures.append(Path(closure))
        return {"returncode": 0, "closure": str(closure)}

    monkeypatch.setattr(tier_module, "run_preflight", fake_preflight)
    monkeypatch.setattr(tier_module, "run_build", fake_build)
    monkeypatch.setattr(tier_module, "extract_claims", lambda *a, **k: SimpleNamespace(drift=(), advisories=()))
    monkeypatch.setattr(tier_module, "aggregate_verdict", lambda report, claims, **k: Verdict("clean", (), ()))
    return closures


def test_a_live_canary_never_probes_the_checked_in_package_in_place(stubbed_supervisor: list[Path]) -> None:
    result = run_drift_canary(CANARY_ROOT, skills_root=CANARY_ROOT)

    assert result.verdict.outcome == "clean"
    assert stubbed_supervisor, "the live path did not reach the supervisor"
    for closure in stubbed_supervisor:
        assert closure != CANARY_ROOT
        assert CANARY_ROOT not in closure.parents
        # The copy carries the package's own name so supervisor diagnostics
        # still identify the closure they came from.
        assert closure.name == CANARY_ROOT.name


def test_the_temporary_closure_is_removed_when_the_canary_returns(stubbed_supervisor: list[Path]) -> None:
    run_drift_canary(CANARY_ROOT, skills_root=CANARY_ROOT)

    assert all(not closure.exists() for closure in stubbed_supervisor)


def test_three_concurrent_canaries_get_three_distinct_closures(stubbed_supervisor: list[Path]) -> None:
    started = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures = [
            pool.submit(run_drift_canary, CANARY_ROOT, skills_root=CANARY_ROOT)
            for _ in range(3)
        ]
        results = [future.result(timeout=BOUND) for future in futures]
    elapsed = time.monotonic() - started

    assert elapsed < BOUND
    assert all(result.verdict.outcome == "clean" for result in results)
    # Six recorded closures (probe + build per run) across three distinct
    # directories: no two runs ever shared a working directory.
    assert len(stubbed_supervisor) == 6
    assert len({str(closure) for closure in stubbed_supervisor}) == 3


def test_a_replayed_canary_still_reads_the_checked_in_package(monkeypatch: pytest.MonkeyPatch) -> None:
    """Copying is a live-path concern only; replay must stay byte-identical."""

    def refuse(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("a replayed canary must not start a supervisor")

    monkeypatch.setattr(tier_module, "run_preflight", refuse)
    monkeypatch.setattr(tier_module, "run_build", refuse)
    monkeypatch.setattr(tier_module, "extract_claims", lambda *a, **k: SimpleNamespace(drift=(), advisories=()))
    monkeypatch.setattr(tier_module, "aggregate_verdict", lambda report, claims, **k: Verdict("clean", (), ()))

    result = run_drift_canary(
        CANARY_ROOT,
        skills_root=CANARY_ROOT,
        probe={"returncode": 0, "report": {"probe_id": "kitchen-sink"}},
        build={"returncode": 0},
    )

    assert result.verdict.outcome == "clean"


def test_the_report_names_the_package_not_the_per_run_copy(stubbed_supervisor: list[Path]) -> None:
    """The copy's path is gone by the time anyone reads report.json.

    Recording it would also make two otherwise-identical canary blocks differ
    on every run.
    """

    result = run_drift_canary(CANARY_ROOT, skills_root=CANARY_ROOT)

    assert result.probe.closure == str(CANARY_ROOT)
    assert result.build["closure"] == str(CANARY_ROOT)
    # The supervisor still received the isolated copy.
    assert all(closure != CANARY_ROOT for closure in stubbed_supervisor)
