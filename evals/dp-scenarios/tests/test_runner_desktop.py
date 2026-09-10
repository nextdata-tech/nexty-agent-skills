"""Proofs for the live adapter around the shared desktop stdio substrate.

The substrate cleans registered process groups.  A turn child that calls
``setsid()`` creates a new session and can escape that group cleanup, so the
detached-grandchild test below pins that documented boundary and terminates
the escaped process explicitly.
"""

from __future__ import annotations

import hashlib
import json
import os
import signal
from dataclasses import replace
from pathlib import Path
import subprocess
import sys
import time

import pytest

import desktop_stdio as shared_desktop_stdio
from dp_scenarios.runner.desktop import DesktopStdioTransport, _resolved_supervisor_identity
from dp_scenarios.runner.environment import EnvironmentError, RunEnvironment
from test_runner_environment import make_scenario, pins


MARKER = "DESKTOP-SESSION-UNIQUE-BEARER-MARKER"


def _script(path: Path, body: str) -> Path:
    path.write_text("#!/usr/bin/env python3\n" + body, encoding="utf-8")
    path.chmod(0o755)
    return path


def _wait_gone(pid: int) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.01)
    raise AssertionError(f"process {pid} survived cleanup")


def _terminate_pid(pid: int) -> None:
    """Terminate a deliberately detached test process and wait for its exit."""

    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.01)
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    _wait_gone(pid)


def _read_pid(path: Path) -> int | None:
    try:
        return int(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


FAKE_SERVER = r'''
import json, sys
for raw in sys.stdin:
    request = json.loads(raw)
    print(json.dumps({"jsonrpc": "2.0", "id": request.get("id"),
                      "result": {"authorization": "Bearer DESKTOP-SESSION-UNIQUE-BEARER-MARKER"}}), flush=True)
'''


HOLDING_TURN = r'''
import os, pathlib, time
grandchild = os.fork()
if grandchild == 0:
    os.setsid()
    pathlib.Path(os.environ["GRANDCHILD_PID_FILE"]).write_text(str(os.getpid()))
    while True:
        time.sleep(60)
pathlib.Path(os.environ["PID_FILE"]).write_text(str(os.getpid()))
for _line in os.sys.stdin:
    time.sleep(60)
'''


def _argv_builder(config_path: Path, strict_mcp_config: bool, allowed_tools_csv: str) -> list[str]:
    command = [sys.executable, "turn-protocol-child", "--mcp-config", str(config_path)]
    if strict_mcp_config:
        command.append("--strict-mcp-config")
    command.extend(("--allowedTools", allowed_tools_csv))
    return command


ARGV_CAPTURE = r'''
import json, os, pathlib, sys, time
output_path = os.environ.get("ARGV_FILE") or sys.argv[1]
pathlib.Path(output_path).write_text(
    json.dumps({"argv": sys.argv[1:], "mcp_config_env": os.environ.get("MCP_CONFIG")}),
    encoding="utf-8",
)
for _line in sys.stdin:
    time.sleep(60)
'''


def test_live_child_receives_the_isolated_mcp_configuration(tmp_path: Path) -> None:
    turn = _script(tmp_path / "turn.py", ARGV_CAPTURE)
    args_file = tmp_path / "argv.json"
    server = _script(tmp_path / "server.py", "for _line in __import__('sys').stdin: pass\n")
    adapter = DesktopStdioTransport.create(
        lambda config_path, strict_mcp_config, allowed_tools_csv: [
            sys.executable,
            str(turn),
            "--mcp-config",
            str(config_path),
            *( ["--strict-mcp-config"] if strict_mcp_config else [] ),
            "--allowedTools",
            allowed_tools_csv,
        ],
        environment={"ARGV_FILE": str(args_file)},
        cwd=tmp_path,
        server_command=[sys.executable, str(server)],
        root=tmp_path / "session",
    )
    live = adapter.live_session()
    try:
        live.start_fresh_session()
        deadline = time.monotonic() + 5
        while not args_file.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        observed = json.loads(args_file.read_text(encoding="utf-8"))
        assert str(adapter.config_path) in observed["argv"]
        assert "--strict-mcp-config" in observed["argv"]
        assert "--allowedTools" in observed["argv"]
        assert adapter.session.allowed_tools_csv in observed["argv"]
        assert observed["mcp_config_env"] is None
    finally:
        live.close()


def test_production_builder_injects_isolated_mcp_configuration(tmp_path: Path) -> None:
    turn = _script(tmp_path / "turn.py", ARGV_CAPTURE)
    args_file = tmp_path / "production-argv.json"
    server = _script(tmp_path / "server.py", "for _line in __import__('sys').stdin: pass\n")
    allowed_tools = ("mcp__nxd-desktop__advance_workflow",)
    with RunEnvironment(
        make_scenario(),
        pins(),
        root=tmp_path,
        live_command=(sys.executable, str(turn), str(args_file)),
        supervisor_command=(sys.executable, str(server)),
        desktop_allowed_tools=allowed_tools,
        supervisor_environment={
            "NXD_DESKTOP_PYTHON": "/tmp/desktop-python",
            "HOME": "/host-home",
            "USERPROFILE": "/host-profile",
        },
    ) as environment:
        assert environment.live_transport.session.server_command[-2:] == ("mcp", "serve")
        assert environment.live_transport.session.server_command[-4] == "--data-dir"
        assert environment.live_transport.session.server_env["NXD_DESKTOP_PYTHON"] == "/tmp/desktop-python"
        assert environment.live_transport.session.server_env["HOME"] == str(environment.home)
        assert environment.live_transport.session.server_env["USERPROFILE"] == str(environment.home)
        live = environment.live_session()
        config_path = environment.live_transport.config_path
        try:
            live.start_fresh_session()
            deadline = time.monotonic() + 5
            while not args_file.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            assert args_file.exists()
            observed = json.loads(args_file.read_text(encoding="utf-8"))
        finally:
            live.close()

    argv = observed["argv"]
    config_index = argv.index("--mcp-config")
    assert argv[config_index + 1] == str(config_path)
    assert "--strict-mcp-config" in argv
    assert argv[argv.index("--allowedTools") + 1] == ",".join(allowed_tools)
    assert observed["mcp_config_env"] is None


def test_adapter_pins_session_artifacts_and_uses_substrate_redaction(tmp_path: Path) -> None:
    server = _script(tmp_path / "server.py", FAKE_SERVER)
    adapter = DesktopStdioTransport.create(
        _argv_builder,
        environment={},
        cwd=tmp_path,
        server_command=[sys.executable, str(server)],
        root=tmp_path / "session",
    )
    adapter.start()
    assert type(adapter.session) is shared_desktop_stdio.DesktopStdioSession
    proxy = subprocess.Popen(
        [
            sys.executable,
            str(adapter.session.PROXY_MODULE),
            "--proxy",
            "--spec",
            str(adapter.root / "server-spec.json"),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    adapter.attach_process(proxy)
    try:
        assert proxy.stdin is not None and proxy.stdout is not None
        proxy.stdin.write(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {"authorization": f"Bearer {MARKER}"},
                }
            )
            + "\n"
        )
        proxy.stdin.flush()
        assert json.loads(proxy.stdout.readline())["id"] == 1
        proxy.stdin.close()
        assert proxy.wait(timeout=5) == 0

        assert MARKER not in adapter.trace_path.read_text(encoding="utf-8")
        metrics = adapter.result_metrics()
        assert metrics["server_result"]["status"] == "passed"
        paths = adapter.artifact_paths
        assert paths == {
            "config": str(adapter.config_path),
            "trace": str(adapter.trace_path),
            "server_result": str(adapter.server_result_path),
        }
    finally:
        adapter.cleanup()


def test_supervisor_identity_handles_module_and_configured_launchers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    package = tmp_path / "demo_supervisor"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    module = package / "supervisor.py"
    module.write_text("VALUE = 1\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))

    module_identity = _resolved_supervisor_identity((sys.executable, "-m", "demo_supervisor.supervisor"))
    assert module_identity.startswith("module:demo_supervisor.supervisor:")
    assert hashlib.sha256(module.read_bytes()).hexdigest() in module_identity

    config = tmp_path / "supervisor.yaml"
    config.write_text("timeout: 5\n", encoding="utf-8")
    script = _script(tmp_path / "server.py", "pass\n")
    configured_identity = _resolved_supervisor_identity(("/usr/bin/env", "--config", str(config), str(script)))
    assert configured_identity.startswith(f"{script.resolve()}#sha256:")


def test_live_session_cleanup_reaps_turn_child_after_protocol_error(tmp_path: Path) -> None:
    turn = _script(tmp_path / "turn.py", HOLDING_TURN)
    pid_file = tmp_path / "turn.pid"
    grandchild_pid_file = tmp_path / "grandchild.pid"
    server = _script(tmp_path / "server.py", "for _line in __import__('sys').stdin: pass\n")
    adapter = DesktopStdioTransport.create(
        lambda config_path, strict_mcp_config, allowed_tools_csv: [
            sys.executable,
            str(turn),
            "--mcp-config",
            str(config_path),
            "--strict-mcp-config",
            "--allowedTools",
            allowed_tools_csv,
        ],
        environment={
            "PID_FILE": str(pid_file),
            "GRANDCHILD_PID_FILE": str(grandchild_pid_file),
        },
        cwd=tmp_path,
        server_command=[sys.executable, str(server)],
        root=tmp_path / "session",
    )
    live = adapter.live_session(timeout=0.1)
    assert live.desktop_session is adapter.session
    child_pid: int | None = None
    grandchild_pid: int | None = None
    try:
        live.start_fresh_session()
        deadline = time.monotonic() + 5
        while not pid_file.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert pid_file.exists()
        deadline = time.monotonic() + 5
        while not grandchild_pid_file.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert grandchild_pid_file.exists()
        child_pid = int(pid_file.read_text(encoding="utf-8"))
        grandchild_pid = int(grandchild_pid_file.read_text(encoding="utf-8"))
        result = live.send_message("mid-session failure")
        # A per-turn deadline is a timeout, not a wedged environment: the
        # artifacts the agent already authored stay gradeable.
        assert result.turn_timed_out
        assert not result.environment_wedged
        assert result.environment_detail == "live session exceeded the 0.100s turn timeout"
        live.close()
        _wait_gone(child_pid)
        assert os.getpgid(grandchild_pid) == grandchild_pid
        assert os.kill(grandchild_pid, 0) is None, "detached grandchild unexpectedly joined cleanup"
    finally:
        live.close()
        if child_pid is None:
            child_pid = _read_pid(pid_file)
        if grandchild_pid is None:
            grandchild_pid = _read_pid(grandchild_pid_file)
        if child_pid is not None:
            _terminate_pid(child_pid)
        if grandchild_pid is not None:
            _terminate_pid(grandchild_pid)


def test_live_environment_manifest_records_adapter_identity(tmp_path: Path) -> None:
    server = _script(tmp_path / "server.py", "for _line in __import__('sys').stdin: pass\n")
    turn = _script(tmp_path / "turn.py", "for _line in __import__('sys').stdin: pass\n")
    with RunEnvironment(
        make_scenario(),
        pins(),
        root=tmp_path,
        live_command=(sys.executable, str(turn)),
        supervisor_command=(sys.executable, str(server)),
    ) as environment:
        manifest = environment.manifest.to_dict()
        assert manifest["validation_mode"] == "live"
        config_bytes = environment.live_transport.config_path.read_bytes()
        supervisor_digest = hashlib.sha256(server.read_bytes()).hexdigest()
        assert manifest["supervisor_binary_path"] == f"{server.resolve()}#sha256:{supervisor_digest}"
        assert str(Path(sys.executable).resolve()) not in manifest["supervisor_binary_path"]
        assert manifest["session_root"] == str(environment.live_transport.root)
        assert manifest["session_config_path"] == str(environment.live_transport.config_path)
        assert manifest["session_trace_path"] == str(environment.live_transport.trace_path)
        assert manifest["session_server_result_path"] == str(environment.live_transport.server_result_path)
        assert manifest["session_config_sha256"] != "sha256:" + hashlib.sha256(config_bytes).hexdigest()
        ledger_manifest = json.loads(environment.ledger_path.read_text(encoding="utf-8").splitlines()[0])[
            "manifest"
        ]
        assert ledger_manifest["validation_mode"] == "live"
        assert ledger_manifest["session_trace_path"] == manifest["session_trace_path"]


def test_session_digest_changes_when_supervisor_spec_changes(tmp_path: Path) -> None:
    server = _script(tmp_path / "server.py", "for _line in __import__('sys').stdin: pass\n")
    root = tmp_path / "session"
    first = DesktopStdioTransport.create(
        _argv_builder,
        environment={},
        cwd=tmp_path,
        server_command=[sys.executable, str(server)],
        server_environment={"SUPERVISOR_MODE": "one"},
        root=root,
    ).start()
    first_digest = first.session_config_sha256
    first.cleanup()

    second = DesktopStdioTransport.create(
        _argv_builder,
        environment={},
        cwd=tmp_path,
        server_command=[sys.executable, str(server)],
        server_environment={"SUPERVISOR_MODE": "two"},
        root=root,
    ).start()
    try:
        assert second.session_config_sha256 != first_digest
    finally:
        second.cleanup()


def test_session_digest_ignores_per_run_paths_but_tracks_semantic_inputs(tmp_path: Path) -> None:
    server = _script(tmp_path / "server.py", "for _line in __import__('sys').stdin: pass\n")
    digests: list[str] = []
    for session_root in (tmp_path / "first" / "session", tmp_path / "second" / "session"):
        adapter = DesktopStdioTransport.create(
            _argv_builder,
            environment={},
            cwd=tmp_path,
            server_command=[sys.executable, str(server)],
            server_environment={"HOME": str(session_root.parent / "home"), "MODE": "same"},
            root=session_root,
            allowed_tools=("mcp__nxd-desktop__read",),
        ).start()
        try:
            digests.append(adapter.session_config_sha256)
        finally:
            adapter.cleanup()
    assert digests[0] == digests[1]


def test_session_digest_normalizes_only_mock_source_port(tmp_path: Path) -> None:
    server = _script(tmp_path / "server.py", "for _line in __import__('sys').stdin: pass\n")

    def digest(name: str, source_url: str | None) -> str:
        adapter = DesktopStdioTransport.create(
            _argv_builder,
            environment={},
            cwd=tmp_path,
            server_command=[sys.executable, str(server)],
            server_environment=(
                {"NXD_EVAL_SOURCE_URL": source_url} if source_url is not None else {}
            ),
            root=tmp_path / name / "session",
        ).start()
        try:
            return adapter.session_config_sha256
        finally:
            adapter.cleanup()

    first = digest("first", "http://127.0.0.1:58898/source")
    second = digest("second", "http://127.0.0.1:58902/source")
    assert first == second
    assert first != digest("absent", None)
    assert first != digest("different-path", "http://127.0.0.1:58902/other")
    assert first != digest("different-host", "http://localhost:58902/source")


def test_live_manifests_same_scenario_are_comparable(tmp_path: Path) -> None:
    server = _script(tmp_path / "server.py", "for _line in __import__('sys').stdin: pass\n")
    turn = _script(tmp_path / "turn.py", "for _line in __import__('sys').stdin: pass\n")
    route_config = {
        "version": 1,
        "routes": [{"path": "/items", "response": {"json": []}}],
    }
    with RunEnvironment(
        make_scenario(),
        pins(),
        root=tmp_path,
        route_config=route_config,
        live_command=(sys.executable, str(turn)),
        supervisor_command=(sys.executable, str(server)),
    ) as first:
        first_manifest = first.manifest
    with RunEnvironment(
        make_scenario(),
        pins(),
        root=tmp_path,
        route_config=route_config,
        live_command=(sys.executable, str(turn)),
        supervisor_command=(sys.executable, str(server)),
    ) as second:
        second_manifest = second.manifest

    comparison = first_manifest.comparable_to(second_manifest)
    assert comparison.kind.value == "IDENTICAL"
    assert comparison.differing_fields == set()


def test_live_manifest_can_be_replayed_without_reacquiring_desktop(tmp_path: Path) -> None:
    server = _script(tmp_path / "server.py", "for _line in __import__('sys').stdin: pass\n")
    turn = _script(tmp_path / "turn.py", "for _line in __import__('sys').stdin: pass\n")
    with RunEnvironment(
        make_scenario(),
        pins(),
        root=tmp_path,
        live_command=(sys.executable, str(turn)),
        supervisor_command=(sys.executable, str(server)),
    ) as live_environment:
        recorded_manifest = live_environment.manifest.to_dict()

    with RunEnvironment(
        make_scenario(),
        replace(
            pins(),
            supervisor_binary_path=recorded_manifest["supervisor_binary_path"],
            session_config_sha256=recorded_manifest["session_config_sha256"],
        ),
        root=tmp_path,
        manifest_override=recorded_manifest,
    ) as replay_environment:
        assert replay_environment.manifest.to_dict() == recorded_manifest
        with pytest.raises(EnvironmentError, match="no live desktop transport"):
            replay_environment.live_transport


@pytest.mark.parametrize("field", ("session_config_sha256", "supervisor_binary_path"))
def test_replay_rejects_tampered_stable_desktop_identity(tmp_path: Path, field: str) -> None:
    server = _script(tmp_path / "server.py", "for _line in __import__('sys').stdin: pass\n")
    turn = _script(tmp_path / "turn.py", "for _line in __import__('sys').stdin: pass\n")
    with RunEnvironment(
        make_scenario(),
        pins(),
        root=tmp_path,
        live_command=(sys.executable, str(turn)),
        supervisor_command=(sys.executable, str(server)),
    ) as live_environment:
        recorded_manifest = live_environment.manifest.to_dict()

    replay_pins = replace(
        pins(),
        supervisor_binary_path=recorded_manifest["supervisor_binary_path"],
        session_config_sha256=recorded_manifest["session_config_sha256"],
    )
    tampered = dict(recorded_manifest)
    tampered[field] = f"tampered-{field}"
    with pytest.raises(EnvironmentError, match=f"replay manifest mismatch in {field}"):
        with RunEnvironment(
            make_scenario(),
            replay_pins,
            root=tmp_path,
            manifest_override=tampered,
        ):
            pass
