"""``run_one`` must enforce the deterministic gate, not merely report it.

The checker itself is exercised in ``test_deterministic_check.py``. These tests
cover the harness side: that a wrong-number closure is mechanically failed even
when the judge says pass, that a cached replay records an explicit skip instead
of a silent pass, and that scenarios which do not opt in are untouched.
"""

from __future__ import annotations

import json
import types
from pathlib import Path

import pytest

from test_deterministic_check import (  # noqa: PLC2701 - shared closure builders
    SCENARIO,
    _land_totals,
    _write_closure,
    run,
)


class _StubAgent:
    """Lands a closure into the workspace instead of driving a real agent."""

    name = "claude"

    def __init__(self, net_refunds: bool):
        self.net_refunds = net_refunds

    def run_agent(self, ws: Path, *_args, **_kwargs):
        _write_closure(ws)
        _land_totals(ws, net_refunds=self.net_refunds)
        return True, "stub transcript", {"final_answer": "done"}


class _PassingJudge:
    """Always passes, so any failure observed is the deterministic gate."""

    name = "claude"

    def run_judge(self, *_args, **_kwargs):
        return {"overall_pass": True, "summary": "judge said yes", "checks": []}


def _args(tmp_path: Path, **over):
    base = dict(
        agent_backend="claude", judge_backend="claude", agent_model="m",
        judge_model="m", agent_effort="", judge_effort="", agent_timeout=60,
        judge_timeout=60, docs_base="https://example.invalid", cache_dir=None,
    )
    base.update(over)
    return types.SimpleNamespace(**base)


@pytest.fixture
def harness(monkeypatch):
    def install(net_refunds: bool):
        monkeypatch.setattr(run, "get_agent_backend", lambda _n: _StubAgent(net_refunds))
        monkeypatch.setattr(run, "get_judge_backend", lambda _n: _PassingJudge())
    return install


def _skill_set():
    return run.SkillSet(name="stub", description="stub skill set", skills=[])


def test_wrong_numbers_fail_the_cell_despite_a_passing_judge(harness, tmp_path):
    harness(net_refunds=False)
    res = run.run_one(_skill_set(), SCENARIO, _args(tmp_path))

    assert res.ok is True, res.error
    assert res.verdict["overall_pass"] is False
    assert res.metrics["deterministic_check"] == "failed"
    assert "charges-only" in res.metrics["deterministic_check_detail"]
    assert run.DETERMINISTIC_CHECK_FAILED in res.verdict["summary"]


def test_correct_numbers_leave_the_judge_verdict_alone(harness, tmp_path):
    harness(net_refunds=True)
    res = run.run_one(_skill_set(), SCENARIO, _args(tmp_path))

    assert res.ok is True, res.error
    assert res.verdict["overall_pass"] is True
    assert res.metrics["deterministic_check"] == "passed"


def test_cached_replay_records_an_explicit_skip(harness, tmp_path):
    """A replay has no workspace, so the gate cannot run — and must not pass."""
    harness(net_refunds=True)
    cache = tmp_path / "cache"
    args = _args(tmp_path, cache_dir=str(cache))

    first = run.run_one(_skill_set(), SCENARIO, args)
    assert first.metrics["deterministic_check"] == "passed"

    second = run.run_one(_skill_set(), SCENARIO, args)
    assert second.metrics.get("cached") is True
    assert second.metrics["deterministic_check"] == "skipped: cached transcript, no workspace"
    assert "deterministic_check_detail" not in second.metrics
    assert any("DETERMINISTIC CHECK: UNAVAILABLE" in f for f in second.facts)


def test_cached_facts_do_not_replay_a_stale_pass(harness, tmp_path):
    """The pass belongs to the run that produced the workspace, not to the cache."""
    harness(net_refunds=True)
    cache = tmp_path / "cache"
    args = _args(tmp_path, cache_dir=str(cache))
    run.run_one(_skill_set(), SCENARIO, args)

    entry = json.loads(next(cache.glob("agent-*.json")).read_text(encoding="utf-8"))
    assert not any(
        f.startswith(run.DETERMINISTIC_CHECK_PREFIX) for f in entry.get("facts", [])
    )


def test_scenario_without_the_opt_in_is_untouched(harness, tmp_path, monkeypatch):
    harness(net_refunds=False)
    scenario = tmp_path / "no-opt-in"
    (scenario / "fixtures").mkdir(parents=True)
    checks = json.loads((SCENARIO / "checks.json").read_text(encoding="utf-8"))
    checks.pop("deterministic_check")
    (scenario / "checks.json").write_text(json.dumps(checks), encoding="utf-8")
    (scenario / "prompt.md").write_text(
        (SCENARIO / "prompt.md").read_text(encoding="utf-8"), encoding="utf-8"
    )

    res = run.run_one(_skill_set(), scenario, _args(tmp_path))

    assert res.ok is True, res.error
    assert "deterministic_check" not in res.metrics
    assert res.verdict["overall_pass"] is True
