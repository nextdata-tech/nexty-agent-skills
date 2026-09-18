"""Unit tests for the per-case MCP session isolation runner."""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from nxd_eval import Case, Suite
from nxd_eval.session_isolation import _fold_eval_log, SessionIsolationError, run_suite_isolated
from nxd_eval.task import run_suite


def _log(case_id: str):
    return SimpleNamespace(
        samples=[SimpleNamespace(id=case_id, error=None)],
        eval=SimpleNamespace(dataset=SimpleNamespace(samples=1, sample_ids=[case_id])),
        stats=None,
        status="success",
        error=None,
        reductions=None,
        results=SimpleNamespace(total_samples=1, completed_samples=1, scores={"accuracy": 1}),
    )


def test_isolated_runner_uses_one_case_per_run_and_collates_completed_logs(
    monkeypatch, tmp_path
):
    logs = {"a": _log("a"), "c": _log("c")}
    written = []
    inspect_log = ModuleType("inspect_ai.log")
    inspect_log.read_eval_log = lambda path: logs[path.rsplit("/", 1)[-1].removesuffix(".eval")]

    def write_eval_log(log, path, **_kwargs):
        written.append(log)
        Path(path).touch()

    inspect_log.write_eval_log = write_eval_log
    monkeypatch.setitem(sys.modules, "inspect_ai.log", inspect_log)

    calls: list[list[str]] = []

    def run_one(suite, **_kwargs):
        calls.append([case.id for case in suite.cases])
        case_id = suite.cases[0].id
        if case_id == "b":
            raise RuntimeError("simulated MCP failure")
        return tmp_path / f"{case_id}.eval"

    suite = Suite(
        name="stateful-server",
        cases=[
            Case(id="a", question="first", expect="clarify"),
            Case(id="b", question="second", expect="clarify"),
            Case(id="c", question="third", expect="clarify"),
        ],
    )
    with pytest.raises(SessionIsolationError, match="b: RuntimeError: simulated MCP failure") as exc:
        run_suite_isolated(
            suite,
            run_one=run_one,
            variant="current_pack",
            mcp_url="http://example.test/mcp",
            server_factory=None,
            agent_prompt=None,
            agent_model="mockllm/model",
            authorization=None,
            grader_model=None,
            epochs=1,
            epochs_reducer="pass_at",
            log_dir=tmp_path,
            display="none",
        )

    assert calls == [["a"], ["b"], ["c"]]
    assert exc.value.log_path.exists()
    assert [sample.id for sample in written[-1].samples] == ["a", "c"]
    assert len(written) == 1


def test_fold_eval_log_merges_nullable_usage_and_clears_stale_scores():
    class Usage:
        def __init__(self, **values):
            self.__dict__.update(values)

        def model_dump(self):
            return self.__dict__.copy()

    base = _log("a")
    base.stats = SimpleNamespace(
        started_at="2026-04-05T02:30:00+10:00",
        completed_at="2026-04-05T02:31:00+10:00",
        model_usage={"model": Usage(input_tokens=3, reasoning_tokens=None)},
    )
    addition = _log("b")
    addition.stats = SimpleNamespace(
        started_at="2026-04-05T02:45:00+11:00",
        completed_at="2026-04-05T03:00:00+10:00",
        model_usage={"model": Usage(input_tokens=5, reasoning_tokens=7)},
    )

    result = _fold_eval_log(base, addition)

    assert result.stats.started_at == "2026-04-05T02:45:00+11:00"
    assert result.stats.completed_at == "2026-04-05T03:00:00+10:00"
    assert result.stats.model_usage["model"].input_tokens == 8
    assert result.stats.model_usage["model"].reasoning_tokens == 7
    assert result.results.scores == []


def test_fold_eval_log_preserves_non_success_status():
    base = _log("a")
    cancelled = _log("b")
    cancelled.status = "cancelled"
    cancelled.error = "timed out"

    result = _fold_eval_log(base, cancelled)

    assert result.status == "cancelled"
    assert result.error == "timed out"


def test_isolated_runner_raises_session_error_when_every_case_fails(monkeypatch, tmp_path):
    inspect_log = ModuleType("inspect_ai.log")
    inspect_log.read_eval_log = lambda _path: pytest.fail("no log should be read")
    inspect_log.write_eval_log = lambda *_args, **_kwargs: pytest.fail("no log should be written")
    monkeypatch.setitem(sys.modules, "inspect_ai.log", inspect_log)
    suite = Suite(name="unavailable", cases=[Case(id="a", question="q", expect="clarify")])

    with pytest.raises(SessionIsolationError, match="no partial log was written") as exc:
        run_suite_isolated(
            suite,
            run_one=lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("down")),
            variant="current_pack",
            mcp_url="http://example.test/mcp",
            server_factory=None,
            agent_prompt=None,
            agent_model="mockllm/model",
            authorization=None,
            grader_model=None,
            epochs=1,
            epochs_reducer="pass_at",
            log_dir=tmp_path,
            display="none",
        )

    assert exc.value.log_path is None


def test_public_run_suite_passes_isolation_options_to_library_runner(monkeypatch, tmp_path):
    captured = {}

    def isolated(suite, **kwargs):
        captured["suite"] = suite
        captured.update(kwargs)
        return tmp_path / "collated.eval"

    monkeypatch.setattr("nxd_eval.session_isolation.run_suite_isolated", isolated)
    suite = Suite(name="stateful-server", cases=[Case(id="a", question="q", expect="clarify")])
    factory = lambda: object()

    result = run_suite(
        suite,
        mcp_url="http://example.test/mcp",
        server_factory=factory,
        agent_model="mockllm/model",
        isolate_sessions=True,
    )

    assert result == tmp_path / "collated.eval"
    assert captured["suite"] is suite
    assert captured["run_one"].__name__ == "_run_suite_once"
    assert captured["mcp_url"] == "http://example.test/mcp"
    assert captured["server_factory"] is factory
