"""Deterministic coverage for a terminal stdio session with a local HTTP stub."""

from __future__ import annotations

import contextlib
import importlib
import json
import os
import subprocess
import sys
import traceback
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
        "    raise RuntimeError('authorization=stop-secret')\n",
        encoding="utf-8",
    )

    with pytest.raises(run.HttpStubTeardownError, match="RuntimeError: authorization=<redacted>") as caught:
        with run.http_stub_server(
            scenario, workspace, {"module": "broken"}, "claude"
        ):
            pass
    assert "stop-secret" not in "".join(traceback.format_exception(caught.value))


def test_http_stub_does_not_use_stale_outer_exception_for_teardown(tmp_path):
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

    # Keep an unrelated exception active in an outer handler while the context
    # exits. The context must track its own body exception state rather than
    # consulting the ambient sys.exc_info().
    try:
        raise ValueError("unrelated")
    except ValueError:
        with pytest.raises(run.HttpStubTeardownError, match="stop boom"):
            with run.http_stub_server(
                scenario, workspace, {"module": "broken"}, "claude"
            ):
                pass


def test_http_stub_endpoint_setup_failure_keeps_teardown_failure_attached(tmp_path):
    scenario = tmp_path / "scenario"
    fixtures = scenario / "fixtures"
    fixtures.mkdir(parents=True)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    endpoint_target = workspace / "ENDPOINT_URL"
    endpoint_target.mkdir()
    (fixtures / "broken.py").write_text(
        "def start_server():\n"
        "    return object(), 43210, object()\n"
        "\n"
        "def stop_server(_server, _thread):\n"
        "    raise RuntimeError('stop boom')\n",
        encoding="utf-8",
    )

    with pytest.raises(run.HttpStubSetupError, match="IsADirectoryError") as caught:
        with run.http_stub_server(
            scenario, workspace, {"module": "broken"}, "claude"
        ):
            pass

    assert any("stop boom" in note for note in caught.value.__notes__)


def test_http_stub_setup_cleanup_does_not_mask_original_failure(tmp_path, monkeypatch):
    scenario = tmp_path / "scenario"
    fixtures = scenario / "fixtures"
    fixtures.mkdir(parents=True)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (fixtures / "broken.py").write_text(
        "def set_observations_path(_path):\n"
        "    pass\n"
        "\n"
        "def start_server():\n"
        "    raise RuntimeError('authorization=setup-secret')\n"
        "\n"
        "def stop_server(_server, _thread):\n"
        "    pass\n",
        encoding="utf-8",
    )

    class BrokenTemporaryDirectory:
        def __init__(self, **_kwargs):
            self.name = str(tmp_path / "observations")
            Path(self.name).mkdir()

        def cleanup(self):
            raise RuntimeError("authorization=cleanup-secret")

    monkeypatch.setattr(run.tempfile, "TemporaryDirectory", BrokenTemporaryDirectory)

    with pytest.raises(run.HttpStubSetupError) as caught:
        with run.http_stub_server(
            scenario,
            workspace,
            {"module": "broken", "observations": True},
            "claude",
            ):
                pass
    assert "setup-secret" not in str(caught.value)
    assert "authorization=<redacted>" in str(caught.value)
    assert caught.value.__cause__ is None
    assert "cleanup-secret" not in "".join(traceback.format_exception(caught.value))
    assert any("cleanup failed" in note for note in caught.value.__notes__)


def test_http_stub_control_flow_keeps_cleanup_failure_note(tmp_path, monkeypatch):
    scenario = tmp_path / "scenario"
    fixtures = scenario / "fixtures"
    fixtures.mkdir(parents=True)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (fixtures / "broken.py").write_text(
        "def set_observations_path(_path):\n"
        "    pass\n"
        "\n"
        "def start_server():\n"
        "    raise GeneratorExit('setup exit')\n"
        "\n"
        "def stop_server(_server, _thread):\n"
        "    pass\n",
        encoding="utf-8",
    )

    class BrokenTemporaryDirectory:
        def __init__(self, **_kwargs):
            self.name = str(tmp_path / "observations")
            Path(self.name).mkdir()

        def cleanup(self):
            raise RuntimeError("authorization=cleanup-secret")

    monkeypatch.setattr(run.tempfile, "TemporaryDirectory", BrokenTemporaryDirectory)

    with pytest.raises(GeneratorExit) as caught:
        with run.http_stub_server(
            scenario, workspace, {"module": "broken", "observations": True}, "claude"
        ):
            pass

    assert any("cleanup failed" in note for note in caught.value.__notes__)
    assert "cleanup-secret" not in "".join(traceback.format_exception(caught.value))


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


def test_a_leaked_fixture_literal_is_reported_and_never_cached(tmp_path, monkeypatch):
    """A redaction failure must not be laundered by the agent cache.

    What lands in the cache is the REDACTED transcript, so a later cache hit
    finds no literal and would replay the run as clean — turning a real
    redaction failure into a pass on the second run.
    """
    scenario = tmp_path / "scenario"
    fixtures = scenario / "fixtures"
    fixtures.mkdir(parents=True)
    (scenario / "prompt.md").write_text("Do the thing.\n", encoding="utf-8")
    (scenario / "checks.json").write_text(
        json.dumps({
            "deterministic_check": {
                "script": "unused.py",
                "deps": [],
                "redaction_markers": ["synthetic-secret-marker"],
            }
        }),
        encoding="utf-8",
    )
    (fixtures / "desktop_stdio.json").write_text("{}\n", encoding="utf-8")

    trace_path = tmp_path / "trace.jsonl"
    trace_path.write_text("{}\n", encoding="utf-8")
    session = SimpleNamespace(trace_path=trace_path)

    class FakeBackend:
        name = "fake"
        supports_multi_turn = False

        def run_agent(self, *_args, **_kwargs):
            return True, "echoed synthetic-secret-marker", {"final_answer": "done"}

    @contextlib.contextmanager
    def fake_runtime(_scenario, _workspace, _tmp, _desktop_spec, _http_spec, _backend):
        yield tmp_path / "bin", {}, sys.executable, session, None

    monkeypatch.setattr(run, "get_agent_backend", lambda _name: FakeBackend())
    monkeypatch.setattr(run, "get_judge_backend", lambda _name: object())
    monkeypatch.setattr(run, "desktop_stdio_runtime", fake_runtime)
    monkeypatch.setattr(
        run, "deterministic_check_fact",
        lambda *_args, **_kwargs: run.DETERMINISTIC_CHECK_PREFIX + json.dumps({"passed": True}),
    )
    monkeypatch.setattr(run, "run_judge", lambda *_args, **_kwargs: {"overall_pass": True})

    cache_dir = tmp_path / "cache"
    args = _run_one_args()
    args.cache_dir = str(cache_dir)

    result = run.run_one(run.SkillSet("none", "", []), scenario, args)

    assert "synthetic-secret-marker" not in result.transcript
    assert "<redacted>" in result.transcript
    assert any("AGENT FIXTURE REDACTION: FAIL" in fact for fact in result.facts)
    assert not cache_dir.exists() or not list(cache_dir.glob("agent-*.json"))


def test_marker_redaction_applies_to_a_fresh_non_stdio_run(tmp_path, monkeypatch):
    scenario = tmp_path / "scenario"
    fixtures = scenario / "fixtures"
    fixtures.mkdir(parents=True)
    (scenario / "prompt.md").write_text("Do the thing.\n", encoding="utf-8")
    marker = "synthetic-non-stdio-marker"
    (scenario / "checks.json").write_text(
        json.dumps({
            "deterministic_check": {
                "script": "unused.py",
                "deps": [],
                "redaction_markers": [marker],
            }
        }),
        encoding="utf-8",
    )

    calls = 0

    class FakeBackend:
        name = "fake"
        supports_multi_turn = False

        def run_agent(self, *_args, **_kwargs):
            nonlocal calls
            calls += 1
            return True, f"echoed {marker}", {"final_answer": marker}

    monkeypatch.setattr(run, "get_agent_backend", lambda _name: FakeBackend())
    monkeypatch.setattr(run, "get_judge_backend", lambda _name: object())
    monkeypatch.setattr(
        run,
        "deterministic_check_fact",
        lambda *_args, **_kwargs: run.DETERMINISTIC_CHECK_PREFIX + json.dumps(
            {"passed": True}
        ),
    )
    monkeypatch.setattr(run, "run_judge", lambda *_args, **_kwargs: {"overall_pass": True})

    cache_dir = tmp_path / "cache"
    args = _run_one_args()
    args.cache_dir = str(cache_dir)

    first = run.run_one(run.SkillSet("none", "", []), scenario, args)
    second = run.run_one(run.SkillSet("none", "", []), scenario, args)

    for result in (first, second):
        assert marker not in result.transcript
        assert "<redacted>" in result.transcript
        assert any("AGENT FIXTURE REDACTION: FAIL" in fact for fact in result.facts)
    assert calls == 2
    assert not cache_dir.exists() or not list(cache_dir.glob("agent-*.json"))


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
        "    raise RuntimeError('authorization=stop-secret')\n",
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
    assert result.error == (
        "http stub teardown failed: RuntimeError: authorization=<redacted>"
    )
    assert "stop-secret" not in result.error


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


def test_no_log_deterministic_checker_does_not_inherit_parent_observations(
    tmp_path, monkeypatch
):
    scenario = tmp_path / "scenario"
    fixtures = scenario / "fixtures"
    fixtures.mkdir(parents=True)
    (fixtures / "check.py").write_text(
        "import os\n"
        f"if os.environ.get({run.STUB_OBSERVATIONS_ENV!r}):\n"
        "    print('FAIL inherited observation path')\n"
        "    raise SystemExit(1)\n"
        "print('ALL CHECKS PASSED')\n",
        encoding="utf-8",
    )
    monkeypatch.setenv(run.STUB_OBSERVATIONS_ENV, str(tmp_path / "parent.jsonl"))

    fact = run.deterministic_check_fact(
        scenario, tmp_path / "workspace", {"script": "check.py", "deps": []}
    )

    assert run.deterministic_check_passed([fact])


def test_no_log_desktop_verifier_does_not_inherit_parent_observations(
    tmp_path, monkeypatch
):
    scenario = tmp_path / "scenario"
    fixtures = scenario / "fixtures"
    fixtures.mkdir(parents=True)
    (fixtures / "check.py").write_text("", encoding="utf-8")
    captured: dict[str, object] = {}

    class _Proc:
        returncode, stdout, stderr = 0, '{"passed": true}\n', ""

    def fake_run(_cmd, **kwargs):
        captured["env"] = kwargs["env"]
        return _Proc()

    monkeypatch.setenv(run.STUB_OBSERVATIONS_ENV, str(tmp_path / "parent.jsonl"))
    monkeypatch.setattr(run.subprocess, "run", fake_run)

    fact = run.desktop_harness_fact(
        scenario, tmp_path / "workspace", sys.executable, "workflow", tmp_path, {},
        verifier="check.py",
    )

    assert json.loads(fact.split(": ", 1)[1])["passed"] is True
    assert run.STUB_OBSERVATIONS_ENV not in captured["env"]


def test_http_only_deterministic_check_runs_after_stub_teardown(tmp_path, monkeypatch):
    scenario = tmp_path / "scenario"
    fixtures = scenario / "fixtures"
    fixtures.mkdir(parents=True)
    (scenario / "prompt.md").write_text("Do the thing.\n", encoding="utf-8")
    (scenario / "checks.json").write_text(
        json.dumps({"deterministic_check": {"script": "unused.py", "deps": []}}),
        encoding="utf-8",
    )
    (fixtures / "http_stub.json").write_text(
        json.dumps({"module": "stub", "endpoint_file": "ENDPOINT_URL"}),
        encoding="utf-8",
    )
    (fixtures / "stub.py").write_text("", encoding="utf-8")
    seen: dict[str, object] = {}

    @contextlib.contextmanager
    def fake_http_stub(*_args, **_kwargs):
        seen["active"] = True
        try:
            yield "http://127.0.0.1:1", None
        finally:
            seen["active"] = False
            seen["teardown"] = True

    class FakeBackend:
        name = "fake"
        supports_multi_turn = False

        def run_agent(self, *_args, **_kwargs):
            return True, "agent trace", {"final_answer": "done"}

    def fake_deterministic_check(*_args, **_kwargs):
        assert seen == {"active": False, "teardown": True}
        return run.DETERMINISTIC_CHECK_PREFIX + json.dumps({"passed": True})

    monkeypatch.setattr(run, "get_agent_backend", lambda _name: FakeBackend())
    monkeypatch.setattr(run, "get_judge_backend", lambda _name: object())
    monkeypatch.setattr(run, "http_stub_server", fake_http_stub)
    monkeypatch.setattr(run, "deterministic_check_fact", fake_deterministic_check)
    monkeypatch.setattr(run, "run_judge", lambda *_args, **_kwargs: {"overall_pass": True})

    result = run.run_one(run.SkillSet("none", "", []), scenario, _run_one_args())

    assert result.ok is True
    assert result.metrics["deterministic_check"] == "passed"


def test_http_teardown_failure_preserves_evidence_and_skips_cache(tmp_path, monkeypatch):
    scenario = tmp_path / "scenario"
    fixtures = scenario / "fixtures"
    fixtures.mkdir(parents=True)
    (scenario / "prompt.md").write_text("Do the thing.\n", encoding="utf-8")
    (scenario / "checks.json").write_text(
        json.dumps({"workspace_files": {"files": []}}), encoding="utf-8"
    )
    (fixtures / "http_stub.json").write_text(
        json.dumps({"module": "stub", "endpoint_file": "ENDPOINT_URL"}),
        encoding="utf-8",
    )
    (fixtures / "stub.py").write_text("", encoding="utf-8")

    @contextlib.contextmanager
    def failing_http_stub(*_args, **_kwargs):
        yield "http://127.0.0.1:1", None
        raise run.HttpStubTeardownError("authorization=teardown-secret")

    class FakeBackend:
        name = "fake"
        supports_multi_turn = False

        def run_agent(self, *_args, **_kwargs):
            return True, "agent trace", {"final_answer": "done", "kept": 7}

    monkeypatch.setattr(run, "get_agent_backend", lambda _name: FakeBackend())
    monkeypatch.setattr(run, "get_judge_backend", lambda _name: object())
    monkeypatch.setattr(run, "http_stub_server", failing_http_stub)
    monkeypatch.setattr(run, "workspace_files_fact", lambda *_args: "WORKSPACE FACT")
    monkeypatch.setattr(
        run, "run_judge", lambda *_args, **_kwargs: {"overall_pass": True, "summary": "graded"}
    )
    cache_dir = tmp_path / "cache"
    args = _run_one_args()
    args.cache_dir = str(cache_dir)

    result = run.run_one(run.SkillSet("none", "", []), scenario, args)

    assert result.ok is False
    assert result.error == (
        "http stub teardown failed: authorization=<redacted>"
    )
    assert result.transcript == "agent trace"
    assert result.metrics["kept"] == 7
    assert result.facts == ["WORKSPACE FACT"]
    assert result.verdict == {"overall_pass": True, "summary": "graded"}
    assert not cache_dir.exists() or not list(cache_dir.glob("agent-*.json"))
