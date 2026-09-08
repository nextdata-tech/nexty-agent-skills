"""Deterministic coverage for a terminal stdio session with a local HTTP stub."""

from __future__ import annotations

import contextlib
import importlib
import json
import os
import subprocess
import sys
from types import SimpleNamespace
import urllib.error
import urllib.request
from pathlib import Path

import pytest

EVALS_DIR = Path(__file__).resolve().parents[1]
if str(EVALS_DIR) not in sys.path:
    sys.path.insert(0, str(EVALS_DIR))

ds = importlib.import_module("desktop_stdio")
run = importlib.import_module("run")


SUPERVISOR_SCENARIO = (
    EVALS_DIR / "public" / "authenticated-api-source-supervisor"
)

FAKE_SERVER = r"""
import json, sys
for raw in sys.stdin:
    message = json.loads(raw)
    print(json.dumps({
        "jsonrpc": "2.0",
        "id": message.get("id"),
        "result": {"authorization": "Bearer live-token", "echo": message.get("method")},
    }), flush=True)
"""


def _script(path: Path, body: str) -> Path:
    path.write_text("#!/usr/bin/env python3\n" + body, encoding="utf-8")
    path.chmod(0o755)
    return path


def _stdio_spec() -> dict:
    return {
        "server_name": "nxd-desktop",
        "profile_builder": "unused-profile-builder.py",
        "allowed_tools": ["mcp__nxd-desktop__*"],
    }


def test_combined_runtime_owns_endpoint_trace_and_cleanup(tmp_path, monkeypatch):
    """The two runner-owned transports share one run without sharing state."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    runtime_tmp = tmp_path / "runtime"
    runtime_tmp.mkdir()
    bin_dir = runtime_tmp / "bin"
    bin_dir.mkdir()
    _script(bin_dir / "nxd-desktop-supervisor", FAKE_SERVER)

    monkeypatch.setattr(
        run,
        "_desktop_runtime",
        lambda _scenario, _tmp: (bin_dir, {}, sys.executable),
    )

    def prepare_profile(_scenario, _spec, _workspace, output, _python):
        output.write_text("{}\n", encoding="utf-8")

    monkeypatch.setattr(run, "_prepare_stdio_profile", prepare_profile)
    http_spec = run.scenario_needs_http_stub(SUPERVISOR_SCENARIO)
    assert http_spec is not None
    before_observation_env = os.environ.get(run.STUB_OBSERVATIONS_ENV)
    proxy = None

    with run.desktop_stdio_runtime(
        SUPERVISOR_SCENARIO,
        workspace,
        runtime_tmp,
        _stdio_spec(),
        http_spec,
        "claude",
    ) as (_bin_dir, _env, _python, session, observations):
        assert session.setup_result.status == "passed"
        assert observations is not None
        assert workspace.joinpath("ENDPOINT_URL").read_text().strip().startswith(
            "http://127.0.0.1:"
        )
        assert os.environ.get(run.STUB_OBSERVATIONS_ENV) == before_observation_env
        assert not observations.is_relative_to(workspace)

        proxy = subprocess.Popen(
            [
                sys.executable,
                str(ds.PROXY_MODULE),
                "--proxy",
                "--spec",
                str(session.root / "server-spec.json"),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        session.attach_process(proxy)
        assert proxy.stdin is not None and proxy.stdout is not None
        proxy.stdin.write(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {"authorization": "Bearer live-token"},
                }
            )
            + "\n"
        )
        proxy.stdin.flush()
        assert json.loads(proxy.stdout.readline())["result"]["echo"] == "initialize"

        endpoint = workspace.joinpath("ENDPOINT_URL").read_text().strip()
        with pytest.raises(urllib.error.HTTPError):
            urllib.request.urlopen(endpoint + "/v1/monitors", timeout=5)
        trace = session.trace_path.read_text(encoding="utf-8")
        assert "live-token" not in trace
        assert ds.REDACTED in trace
        assert observations.read_text(encoding="utf-8").count("authorized") == 1

    assert proxy is not None and proxy.poll() is not None
    assert not (runtime_tmp / "stdio-session" / "mcp-config.json").exists()


def test_combined_http_setup_failure_stays_setup_failure(tmp_path, monkeypatch):
    """A bad HTTP fixture must not be reported as an agent or server failure."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    runtime_tmp = tmp_path / "runtime"
    runtime_tmp.mkdir()
    called = False

    def unexpected_stdio_setup(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("stdio setup ran after HTTP setup failed")

    monkeypatch.setattr(run, "_desktop_stdio_session", unexpected_stdio_setup)
    bad_http_spec = {
        "module": "missing-fixture",
        "start": "start_server",
        "stop": "stop_server",
        "endpoint_file": "ENDPOINT_URL",
    }

    with (
        pytest.raises(run.HttpStubSetupError, match="module not found"),
        run.desktop_stdio_runtime(
            SUPERVISOR_SCENARIO,
            workspace,
            runtime_tmp,
            _stdio_spec(),
            bad_http_spec,
            "claude",
        ),
    ):
        pass
    assert called is False


def test_http_stub_wraps_module_and_start_failures_as_setup(tmp_path):
    scenario = tmp_path / "scenario"
    fixtures = scenario / "fixtures"
    fixtures.mkdir(parents=True)
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    module = fixtures / "broken.py"
    module.write_text(
        "raise RuntimeError('module boom')\n",
        encoding="utf-8",
    )
    with pytest.raises(run.HttpStubSetupError, match="RuntimeError: module boom"):
        with run.http_stub_server(
            scenario, workspace, {"module": "broken"}, "claude"
        ):
            pass

    module.write_text(
        "def start_server():\n"
        "    raise OSError('bind boom')\n"
        "\n"
        "def stop_server(_server, _thread):\n"
        "    pass\n",
        encoding="utf-8",
    )
    with pytest.raises(run.HttpStubSetupError, match="OSError: bind boom"):
        with run.http_stub_server(
            scenario, workspace, {"module": "broken"}, "claude"
        ):
            pass


def test_http_stub_wraps_stop_failure_as_teardown(tmp_path):
    scenario = tmp_path / "scenario"
    fixtures = scenario / "fixtures"
    fixtures.mkdir(parents=True)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (fixtures / "broken.py").write_text(
        "def start_server():\n"
        "    return object(), 43210, object()\n"
        "\n"
        "def stop_server(_server, _thread):\n"
        "    raise RuntimeError('stop boom')\n",
        encoding="utf-8",
    )

    with pytest.raises(run.HttpStubTeardownError, match="RuntimeError: stop boom"):
        with run.http_stub_server(
            scenario, workspace, {"module": "broken"}, "claude"
        ):
            pass


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        ("raise KeyboardInterrupt('import interrupt')", KeyboardInterrupt),
        (
            "def start_server():\n"
            "    raise SystemExit('start exit')\n"
            "\n"
            "def stop_server(_server, _thread):\n"
            "    pass\n",
            SystemExit,
        ),
    ],
)
def test_http_stub_preserves_control_flow_during_setup(tmp_path, failure, expected):
    scenario = tmp_path / "scenario"
    fixtures = scenario / "fixtures"
    fixtures.mkdir(parents=True)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (fixtures / "broken.py").write_text(failure, encoding="utf-8")

    with pytest.raises(expected):
        with run.http_stub_server(
            scenario, workspace, {"module": "broken"}, "claude"
        ):
            pass


def test_http_stub_preserves_control_flow_during_teardown(tmp_path):
    scenario = tmp_path / "scenario"
    fixtures = scenario / "fixtures"
    fixtures.mkdir(parents=True)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (fixtures / "broken.py").write_text(
        "def start_server():\n"
        "    return object(), 43210, object()\n"
        "\n"
        "def stop_server(_server, _thread):\n"
        "    raise KeyboardInterrupt('stop interrupt')\n",
        encoding="utf-8",
    )

    with pytest.raises(KeyboardInterrupt):
        with run.http_stub_server(
            scenario, workspace, {"module": "broken"}, "claude"
        ):
            pass


def _run_one_args():
    return SimpleNamespace(
        agent_backend="fake",
        judge_backend="fake",
        agent_model="fake-agent",
        judge_model="fake-judge",
        agent_effort="",
        judge_effort="",
        agent_timeout=1,
        judge_timeout=1,
        docs_base="https://docs.example/",
        cache_dir=None,
    )


def test_run_one_combined_runtime_passes_http_marker_and_checks_in_context(
    tmp_path, monkeypatch
):
    scenario = tmp_path / "scenario"
    fixtures = scenario / "fixtures"
    fixtures.mkdir(parents=True)
    (scenario / "prompt.md").write_text(
        "# Scenario\n\n## Task for the agent\n\nDo the thing.\n",
        encoding="utf-8",
    )
    (scenario / "checks.json").write_text(
        json.dumps({"deterministic_check": {"script": "unused.py", "deps": []}}),
        encoding="utf-8",
    )
    http_marker = {
        "module": "stub",
        "start": "start_server",
        "stop": "stop_server",
        "endpoint_file": "ENDPOINT_URL",
    }
    (fixtures / "desktop_stdio.json").write_text("{}\n", encoding="utf-8")
    (fixtures / "http_stub.json").write_text(
        json.dumps(http_marker), encoding="utf-8"
    )

    trace_path = tmp_path / "trace.jsonl"
    trace_path.write_text("{}\n", encoding="utf-8")
    session = SimpleNamespace(trace_path=trace_path)
    seen: dict[str, object] = {}

    class FakeBackend:
        name = "fake"
        supports_multi_turn = False

        def run_agent(self, _ws, _prompt, _model, _timeout, **kwargs):
            assert kwargs["stdio_session"] is session
            return True, "agent trace", {"final_answer": "done"}

    @contextlib.contextmanager
    def fake_runtime(_scenario, _workspace, _tmp, _desktop_spec, http_spec, _backend):
        seen["http_spec"] = http_spec
        seen["active"] = True
        observations = tmp_path / "observations.jsonl"
        observations.write_text("{}\n", encoding="utf-8")
        try:
            yield tmp_path / "bin", {}, sys.executable, session, observations
        finally:
            seen["active"] = False

    def fake_deterministic_check(_scenario, _ws, _cfg, _trace, *, env_overrides=None):
        assert seen["active"] is True
        assert env_overrides == {run.STUB_OBSERVATIONS_ENV: str(tmp_path / "observations.jsonl")}
        seen["checked"] = True
        return run.DETERMINISTIC_CHECK_PREFIX + json.dumps({"passed": True})

    monkeypatch.setattr(run, "get_agent_backend", lambda _name: FakeBackend())
    monkeypatch.setattr(run, "get_judge_backend", lambda _name: object())
    monkeypatch.setattr(run, "desktop_stdio_runtime", fake_runtime)
    monkeypatch.setattr(run, "deterministic_check_fact", fake_deterministic_check)
    monkeypatch.setattr(run, "run_judge", lambda *_args, **_kwargs: {"overall_pass": True})

    result = run.run_one(run.SkillSet("none", "", []), scenario, _run_one_args())

    assert result.ok is True
    assert result.metrics["deterministic_check"] == "passed"
    assert seen == {
        "http_spec": http_marker,
        "active": False,
        "checked": True,
    }


def test_run_one_combined_http_teardown_is_not_desktop_setup(tmp_path, monkeypatch):
    scenario = tmp_path / "scenario"
    fixtures = scenario / "fixtures"
    fixtures.mkdir(parents=True)
    (scenario / "prompt.md").write_text("Do the thing.\n", encoding="utf-8")
    (scenario / "checks.json").write_text("{}\n", encoding="utf-8")
    (fixtures / "desktop_stdio.json").write_text("{}\n", encoding="utf-8")
    (fixtures / "http_stub.json").write_text(
        json.dumps({"module": "broken", "endpoint_file": "ENDPOINT_URL"}),
        encoding="utf-8",
    )
    (fixtures / "broken.py").write_text(
        "def start_server():\n"
        "    return object(), 43211, object()\n"
        "\n"
        "def stop_server(_server, _thread):\n"
        "    raise RuntimeError('stop boom')\n",
        encoding="utf-8",
    )
    trace_path = tmp_path / "trace.jsonl"
    trace_path.write_text("{}\n", encoding="utf-8")

    class FakeSession:
        def __init__(self, trace):
            self.trace_path = trace

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class FakeBackend:
        name = "fake"
        supports_multi_turn = False

        def run_agent(self, *_args, **_kwargs):
            return True, "agent trace", {"final_answer": "done"}

    monkeypatch.setattr(run, "get_agent_backend", lambda _name: FakeBackend())
    monkeypatch.setattr(run, "get_judge_backend", lambda _name: object())
    monkeypatch.setattr(
        run,
        "_desktop_stdio_session",
        lambda *_args: (tmp_path / "bin", {}, sys.executable, FakeSession(trace_path)),
    )
    monkeypatch.setattr(run, "run_judge", lambda *_args, **_kwargs: {"overall_pass": True})

    result = run.run_one(run.SkillSet("none", "", []), scenario, _run_one_args())

    assert result.ok is False
    assert result.error == "http stub teardown failed: RuntimeError: stop boom"


def test_deterministic_checker_receives_observations_without_process_leak(tmp_path):
    """The request log is visible to the verifier, never to the parent runner."""
    scenario = tmp_path / "scenario"
    fixtures = scenario / "fixtures"
    fixtures.mkdir(parents=True)
    checker = fixtures / "check.py"
    checker.write_text(
        "import os, sys\n"
        "expected = os.environ.get('EXPECTED_LOG')\n"
        "actual = os.environ.get('NXD_STUB_OBSERVATIONS')\n"
        "if actual != expected:\n"
        "    print('FAIL observation path missing')\n"
        "    raise SystemExit(1)\n"
        "print('ALL CHECKS PASSED')\n",
        encoding="utf-8",
    )
    log = tmp_path / "observations.jsonl"
    log.write_text("{}\n", encoding="utf-8")
    before = os.environ.get(run.STUB_OBSERVATIONS_ENV)

    fact = run.deterministic_check_fact(
        scenario,
        tmp_path / "workspace",
        {"script": "check.py", "deps": []},
        env_overrides={
            run.STUB_OBSERVATIONS_ENV: str(log),
            "EXPECTED_LOG": str(log),
        },
    )

    assert run.deterministic_check_passed([fact])
    assert os.environ.get(run.STUB_OBSERVATIONS_ENV) == before
