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


def test_run_one_preserves_judge_overrides_without_cli_explicit_flags(
    harness, tmp_path, monkeypatch
):
    harness(net_refunds=True)
    seen = {}

    def capture_judge(*args, **kwargs):
        seen["model"] = args[5]
        seen["effort"] = kwargs["effort"]
        return {"overall_pass": True, "summary": "captured"}

    monkeypatch.setattr(run, "run_judge", capture_judge)
    res = run.run_one(
        _skill_set(),
        SCENARIO,
        _args(tmp_path, judge_model="caller-model", judge_effort="low"),
    )

    assert res.ok is True, res.error
    assert seen == {"model": "caller-model", "effort": "low"}


def _nex_export_fixture(tmp_path: Path, content: bytes):
    import hashlib

    workspace = tmp_path / "ws"
    workspace.mkdir()
    archive = str(workspace.resolve() / "export.zip")
    Path(archive).write_bytes(content)
    payload = json.dumps({"archive_path": archive})
    trace = [
        {
            "direction": "request", "operation": "export_data_product", "jsonrpc_id": 7,
            "message": {"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {
                "name": "export_data_product", "arguments": {"destination": archive},
            }},
        },
        {
            "direction": "response", "operation": "export_data_product", "jsonrpc_id": 7,
            "message": {"jsonrpc": "2.0", "id": 7, "result": {
                "content": [{"type": "text", "text": payload}],
            }},
        },
    ]
    frozen = {
        run._desktop_rpc_id_key(7): {
            "archive_path": archive, "content": content,
            "sha256": hashlib.sha256(content).hexdigest(), "size": len(content),
        }
    }
    return workspace, archive, trace, frozen


def test_nex890_untouched_export_grades_frozen_bytes(tmp_path):
    workspace, archive, trace, frozen = _nex_export_fixture(tmp_path, b"archive")
    assert run._nex890_frozen_exports(trace, workspace, frozen_exports=frozen) == {
        archive: b"archive"
    }


def test_nex890_export_tampered_after_response_fails_closed(tmp_path):
    workspace, archive, trace, frozen = _nex_export_fixture(tmp_path, b"archive")
    Path(archive).write_bytes(b"rewritten by the agent")
    assert run._nex890_frozen_exports(trace, workspace, frozen_exports=frozen) == {}


@pytest.mark.parametrize("variant", ["missing", "error", "none", "other-path"])
def test_nex890_export_without_a_valid_freeze_fails_closed(tmp_path, variant):
    workspace, archive, trace, frozen = _nex_export_fixture(tmp_path, b"archive")
    key = run._desktop_rpc_id_key(7)
    if variant == "missing":
        frozen = {}
    elif variant == "error":
        frozen = {key: {"archive_path": archive, "error": "archive could not be read"}}
    elif variant == "none":
        frozen = None
    else:
        frozen[key] = {**frozen[key], "archive_path": archive + ".other"}
    assert run._nex890_frozen_exports(trace, workspace, frozen_exports=frozen) == {}
