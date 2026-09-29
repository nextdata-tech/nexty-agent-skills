"""Deterministic tests for the terminal Desktop stdio substrate.

These tests deliberately use a fake JSON-RPC child. They prove config
isolation, proxy forwarding/redaction, Claude flag wiring, and process cleanup
without a Desktop binary, an MCP SDK, or provider credentials.
"""

from __future__ import annotations

import json
import os
import select
import signal
import socket
import stat
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

EVALS_DIR = Path(__file__).resolve().parents[1]
if str(EVALS_DIR) not in sys.path:
    sys.path.insert(0, str(EVALS_DIR))

import desktop_stdio as ds  # noqa: E402
import eval_backends as eb  # noqa: E402


FAKE_SERVER = r"""
import json, sys
for raw in sys.stdin:
    msg = json.loads(raw)
    print(json.dumps({"jsonrpc": "2.0", "id": msg.get("id"),
                      "result": {"authorization": "Bearer live-token",
                                 "echo": msg.get("method")}}), flush=True)
"""

TIMEOUT_SERVER = r"""
import json, sys, threading, time

def respond(message):
    method = message.get("method")
    operation = method
    if method == "tools/call":
        operation = message.get("params", {}).get("name")
    if operation == "build_data_product":
        time.sleep(0.25)
        result = {"state": "terminal", "run_id": "run-1"}
    elif operation == "inspect_run":
        result = {"state": "terminal", "run_id": "run-1", "duplicate_builds": 0}
    else:
        result = {"method": method}
    print(json.dumps({"jsonrpc": "2.0", "id": message.get("id"), "result": result}), flush=True)

for raw in sys.stdin:
    message = json.loads(raw)
    threading.Thread(target=respond, args=(message,)).start()
"""

FAKE_CLAUDE = r"""
import json, os, sys
args = sys.argv[1:]
path = os.environ["ARGS_FILE"]
open(path, "w").write(json.dumps(args))
print(json.dumps({"type": "assistant", "message": {"content": [
    {"type": "tool_use", "name": "mcp__nxd-desktop__build_data_product",
     "input": {"authorization": "Bearer live-token"}}
]}}), flush=True)
print(json.dumps({"type": "result", "result": "done", "is_error": False,
                  "num_turns": 1, "usage": {}}), flush=True)
"""

HOLDING_SERVER = r"""
import os, pathlib, time
pathlib.Path(os.environ["PID_FILE"]).write_text(str(os.getpid()))
time.sleep(60)
"""

REVIEW_GUARD_SERVER = r"""
import json, sys, time

for raw in sys.stdin:
    request = json.loads(raw)
    operation = request.get("params", {}).get("name", request.get("method"))
    arguments = request.get("params", {}).get("arguments", {})
    action = arguments.get("action", {})
    if request.get("method") == "tools/list":
        result = {"tools": [{"name": "advance_workflow", "inputSchema": {}}]}
    elif operation == "advance_workflow" and action.get("type") == "capture":
        time.sleep(0.1)
        result = {
            "revision": 4,
            "invalidation_epoch": 0,
            "requirements": {
                "review": {
                    "status": "pending",
                    "review_input": {
                        "request_id": "review-1",
                        "retained_capture_root": "PLACEHOLDER_CAPTURE",
                        "retained_blueprint_path": "PLACEHOLDER_BLUEPRINT",
                    },
                }
            },
            "next_actions": [
                {
                    "type": "report_requirement",
                    "code": "workflow/review_pending",
                    "requirement_id": "review",
                    "generation": 1,
                    "subject_sha256": "subject-1",
                    "dependency_evidence_sha256": "evidence-1",
                }
            ],
        }
    elif operation == "advance_workflow" and action.get("type") == "report_requirement":
        result = {
            "code": "workflow/review_findings",
            "events": [{"code": "workflow/review_findings"}],
            "requirements": {"review": {"status": "rejected"}},
        }
    else:
        result = {"forwarded_operation": operation}
    print(json.dumps({"jsonrpc": "2.0", "id": request.get("id"), "result": result}), flush=True)
"""

REVIEW_READER_SERVER = r"""
import json, sys

for raw in sys.stdin:
    request = json.loads(raw)
    if request.get("method") == "tools/list":
        result = {"tools": [{"name": "supervisor_tool", "inputSchema": {}}]}
    elif request.get("method") == "tools/call":
        result = {"forwarded_tool": request.get("params", {}).get("name")}
    else:
        result = {"method": request.get("method")}
    print(json.dumps({"jsonrpc": "2.0", "id": request.get("id"), "result": result}), flush=True)
"""


def _script(path: Path, body: str) -> Path:
    path.write_text("#!/usr/bin/env python3\n" + body, encoding="utf-8")
    path.chmod(0o755)
    return path


def _procargs2(
    argv: tuple[str, ...], *, environment_in_used_length: bool = False
) -> tuple[bytearray, int]:
    data = bytearray(struct.pack("=i", len(argv)))
    data.extend(b"/opt/python/bin/Python\0")
    while len(data) % 8:
        data.append(0)
    for argument in argv:
        data.extend(os.fsencode(argument) + b"\0")
    if environment_in_used_length:
        data.extend(b"API_TOKEN=must-not-be-copied\0")
    used_length = len(data)
    if not environment_in_used_length:
        data.extend(b"API_TOKEN=must-not-be-parsed\0\0")
    return data, used_length


def test_darwin_procargs2_parser_reads_five_args_and_ignores_environment():
    argv = (
        "/opt/python/bin/Python",
        "/repo/desktop_stdio.py",
        "--proxy",
        "--spec",
        "/private/tmp/server spec.json",
    )
    data, used_length = _procargs2(argv, environment_in_used_length=True)
    assert b"API_TOKEN=must-not-be-copied" in data[:used_length]

    parsed = ds._parse_darwin_procargs2(
        data,
        used_length,
        allowed_argv0=(b"/opt/python/bin/Python",),
        expected_argv_tail=argv[1:],
    )

    assert parsed == argv
    assert all("API_TOKEN" not in argument for argument in parsed)


def test_darwin_procargs2_parser_does_not_copy_shifted_environment(monkeypatch):
    argv = (
        "",
        "/opt/python/bin/Python",
        str(ds.PROXY_MODULE),
        "--proxy",
        "--spec",
    )
    data, used_length = _procargs2(argv, environment_in_used_length=True)
    assert b"API_TOKEN=must-not-be-copied" in data[:used_length]
    decoded: list[bytes] = []
    original_fsdecode = os.fsdecode

    def record_decode(value):
        decoded.append(value)
        return original_fsdecode(value)

    monkeypatch.setattr(ds.os, "fsdecode", record_decode)

    assert ds._parse_darwin_procargs2(
        data,
        used_length,
        allowed_argv0=(b"/opt/python/bin/Python",),
        expected_argv_tail=(str(ds.PROXY_MODULE), "--proxy", "--spec", "/private/tmp/spec.json"),
    ) is None
    assert decoded == []


@pytest.mark.parametrize(
    ("argv", "allowed_argv0"),
    [
        (("/opt/python/bin/Python", "script", "--proxy", "--spec"), (b"/opt/python/bin/Python",)),
        (("", "script", "--proxy", "--spec", "spec"), (b"/opt/python/bin/Python",)),
        (("/other/python", "script", "--proxy", "--spec", "spec"), (b"/opt/python/bin/Python",)),
    ],
)
def test_darwin_procargs2_parser_rejects_wrong_argc_or_argv0(argv, allowed_argv0):
    data, used_length = _procargs2(argv)

    assert ds._parse_darwin_procargs2(
        data,
        used_length,
        allowed_argv0=allowed_argv0,
        expected_argv_tail=(str(ds.PROXY_MODULE), "--proxy", "--spec", "spec"),
    ) is None


def test_darwin_procargs2_parser_rejects_truncated_arguments():
    argv = (
        "/opt/python/bin/Python", "/repo/desktop_stdio.py", "--proxy",
        "--spec", "server.json",
    )
    data, used_length = _procargs2(argv)

    assert ds._parse_darwin_procargs2(
        data,
        used_length - 1,
        allowed_argv0=(argv[0].encode(),),
        expected_argv_tail=(str(ds.PROXY_MODULE), "--proxy", "--spec", "server.json"),
    ) is None


def test_linux_process_stat_parser_uses_last_comm_parenthesis():
    pid = 4312
    fields = [b"S", b"321"] + [b"1"] * 17 + [b"98765"]
    raw = (
        f"{pid} (worker) S 1 (hostile comm) with spaces) ".encode()
        + b" ".join(fields)
        + b"\n"
    )

    assert ds._parse_linux_process_stat(pid, raw) == (321, 98765)
    assert ds._parse_linux_process_stat(pid + 1, raw) is None
    assert ds._parse_linux_process_stat(pid, b"truncated") is None


def test_linux_process_cmdline_preserves_empty_argv0_and_requires_nul():
    assert ds._parse_linux_process_cmdline(
        b"\0/repo/desktop_stdio.py\0--proxy\0--spec\0spec.json\0"
    ) == ("", "/repo/desktop_stdio.py", "--proxy", "--spec", "spec.json")
    assert ds._parse_linux_process_cmdline(b"python\0script.py") is None


def _configure_nex_proxy_auth(monkeypatch, session, *, argv=None, executable=None, parent=None):
    session._server_spec_path = Path("/private/tmp/server-spec.json")
    session._attached = [SimpleNamespace(pid=4100)]
    interpreter = "/opt/python/bin/Python"
    valid_argv = (
        interpreter,
        str(ds.PROXY_MODULE),
        "--proxy",
        "--spec",
        str(session._server_spec_path),
    )
    monkeypatch.setattr(ds, "_unix_peer_credentials", lambda _connection: (4200, os.getuid()))
    monkeypatch.setattr(ds, "_proxy_interpreter_paths", lambda: (interpreter,))
    monkeypatch.setattr(
        ds,
        "_proxy_peer_identity",
        lambda _pid, *, allowed_argv0, expected_argv_tail: ds._ProxyPeerIdentity(
            parent_pid=4300 if parent is None else parent,
            executable=interpreter if executable is None else executable,
            argv=valid_argv if argv is None else argv,
        ),
    )
    monkeypatch.setattr(ds, "_process_parent", lambda _pid: 4100)
    return valid_argv


def test_nex_proxy_auth_accepts_exact_peer_argv_and_claude_ancestry(tmp_path, monkeypatch):
    session = ds.DesktopStdioSession(
        [sys.executable, "-c", "pass"], root=tmp_path / "session"
    )
    _configure_nex_proxy_auth(monkeypatch, session)

    assert session._authenticate_nex_proxy(object()) is True
    assert session._nex_connection_count == 1
    assert session._nex_authenticated_peer["claude_pid"] == 4100


@pytest.mark.parametrize("change", ["module", "switches", "spec", "shape", "executable", "ancestry"])
def test_nex_proxy_auth_rejects_wrong_peer_identity(tmp_path, monkeypatch, change):
    session = ds.DesktopStdioSession(
        [sys.executable, "-c", "pass"], root=tmp_path / "session"
    )
    valid_argv = _configure_nex_proxy_auth(monkeypatch, session)
    if change == "module":
        values = list(valid_argv)
        values[1] = "/tmp/other_proxy.py"
        _configure_nex_proxy_auth(monkeypatch, session, argv=tuple(values))
    elif change == "switches":
        values = list(valid_argv)
        values[2:4] = ("--spec", "--proxy")
        _configure_nex_proxy_auth(monkeypatch, session, argv=tuple(values))
    elif change == "spec":
        values = list(valid_argv)
        values[4] = "/tmp/other.json"
        _configure_nex_proxy_auth(monkeypatch, session, argv=tuple(values))
    elif change == "shape":
        _configure_nex_proxy_auth(monkeypatch, session, argv=valid_argv[:-1])
    elif change == "executable":
        _configure_nex_proxy_auth(monkeypatch, session, executable="/tmp/other-python")
    else:
        _configure_nex_proxy_auth(monkeypatch, session, parent=9999)
        monkeypatch.setattr(ds, "_process_parent", lambda _pid: None)

    assert session._authenticate_nex_proxy(object()) is False
    assert session._nex_connection_count == 0


@pytest.mark.skipif(
    not (sys.platform.startswith("linux") or sys.platform == "darwin"),
    reason="live peer identity is implemented only for Linux and macOS",
)
def test_nex_proxy_auth_accepts_live_peer_with_quoted_parent_argv(tmp_path):
    bridge_path = Path("/tmp") / (
        f"n890-{os.getpid()}-{time.monotonic_ns()}.sock"
    )
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.settimeout(10)

    result_path = tmp_path / "proxy-result.json"
    spec_path = tmp_path / "server-spec.json"
    pid_path = tmp_path / "proxy.pid"
    wrapper_pid_path = tmp_path / "proxy-parent.pid"
    proxy_parent_script = (
        "import os, signal, subprocess, sys, time\n"
        "proxy = None\n"
        "def unblock_proxy_sigterm():\n"
        "    signal.pthread_sigmask(signal.SIG_UNBLOCK, {signal.SIGTERM})\n"
        "def stop(*_args):\n"
        "    if proxy is not None:\n"
        "        try: os.killpg(proxy.pid, signal.SIGTERM)\n"
        "        except ProcessLookupError: pass\n"
        "        try: proxy.wait(timeout=5)\n"
        "        except subprocess.TimeoutExpired:\n"
        "            os.killpg(proxy.pid, signal.SIGKILL); proxy.wait()\n"
        "    raise SystemExit(0)\n"
        "signal.signal(signal.SIGTERM, stop)\n"
        "signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGTERM})\n"
        "proxy = subprocess.Popen([sys.executable, sys.argv[1], '--proxy', '--spec', sys.argv[2]], "
        "stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, "
        "start_new_session=True, preexec_fn=unblock_proxy_sigterm)\n"
        "signal.pthread_sigmask(signal.SIG_UNBLOCK, {signal.SIGTERM})\n"
        "temporary = sys.argv[3] + '.tmp'\n"
        "with open(temporary, 'w') as pid_file: pid_file.write(str(proxy.pid))\n"
        "os.replace(temporary, sys.argv[3])\n"
        "time.sleep(60)\n"
    )
    parent_script = (
        "import os, signal, subprocess, sys, time\n"
        "wrapper = None\n"
        "def stop(*_args):\n"
        "    if wrapper is not None:\n"
        "        try: wrapper.wait(timeout=6)\n"
        "        except subprocess.TimeoutExpired:\n"
        "            wrapper.kill(); wrapper.wait()\n"
        "    raise SystemExit(0)\n"
        "signal.signal(signal.SIGTERM, stop)\n"
        "signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGTERM})\n"
        "wrapper = subprocess.Popen([sys.executable, '-c', sys.argv[1], *sys.argv[2:]], "
        "stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)\n"
        "signal.pthread_sigmask(signal.SIG_UNBLOCK, {signal.SIGTERM})\n"
        "temporary = sys.argv[5] + '.tmp'\n"
        "with open(temporary, 'w') as pid_file: pid_file.write(str(wrapper.pid))\n"
        "os.replace(temporary, sys.argv[5])\n"
        "time.sleep(60)\n"
    )
    parent = None
    connection = None
    proxy_pid = None
    session = ds.DesktopStdioSession(
        [sys.executable, "-c", "pass"], root=tmp_path / "session"
    )
    session._server_spec_path = spec_path
    expected_proxy_interpreters = ds._proxy_interpreter_paths()
    expected_proxy_argv0 = tuple(
        os.fsencode(path) for path in expected_proxy_interpreters
    )
    expected_proxy_argv_tail = (
        str(ds.PROXY_MODULE), "--proxy", "--spec", str(spec_path)
    )

    def live_proxy_identity():
        if proxy_pid is None:
            return None
        identity = ds._proxy_peer_identity(
            proxy_pid,
            allowed_argv0=expected_proxy_argv0,
            expected_argv_tail=expected_proxy_argv_tail,
        )
        if (
            identity is None
            or len(identity.argv) != 5
            or identity.argv[0] not in expected_proxy_interpreters
            or not any(
                ds._same_executable(identity.executable, path)
                for path in expected_proxy_interpreters
            )
            or identity.argv[1:] != expected_proxy_argv_tail
        ):
            return None
        return identity

    try:
        listener.bind(str(bridge_path))
        listener.listen(1)
        spec_path.write_text(
            json.dumps(
                {
                    "bridge_path": str(bridge_path),
                    "server_process_result_path": str(tmp_path / "server-process.json"),
                    "result_path": str(result_path),
                    "trace_path": str(tmp_path / "trace.jsonl"),
                    "review_allowlist_path": str(tmp_path / "review-allowlist.json"),
                    "nex_mode": False,
                }
            ),
            encoding="utf-8",
        )
        parent = subprocess.Popen(
            [
                sys.executable,
                "-c",
                parent_script,
                proxy_parent_script,
                str(ds.PROXY_MODULE),
                str(spec_path),
                str(pid_path),
                str(wrapper_pid_path),
                "it's an unmatched ancestor quote",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        session._attached = [parent]
        deadline = time.monotonic() + 10
        while (
            not (pid_path.exists() and wrapper_pid_path.exists())
            and time.monotonic() < deadline
        ):
            if parent.poll() is not None:
                raise AssertionError("proxy parent exited before starting the child")
            time.sleep(0.01)
        assert pid_path.exists() and wrapper_pid_path.exists(), (
            "proxy process tree did not publish both child PIDs"
        )
        proxy_pid = int(pid_path.read_text(encoding="utf-8"))
        wrapper_pid = int(wrapper_pid_path.read_text(encoding="utf-8"))
        connection, _address = listener.accept()

        assert ds._process_parent(proxy_pid) == wrapper_pid
        assert ds._process_parent(wrapper_pid) == parent.pid
        assert session._authenticate_nex_proxy(connection) is True
        assert session._nex_authenticated_peer["pid"] == proxy_pid
        assert session._nex_authenticated_peer["claude_pid"] == parent.pid
    finally:
        if connection is not None:
            connection.close()
        listener.close()
        if parent is not None:
            try:
                os.killpg(parent.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                parent.communicate(timeout=8)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(parent.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                parent.communicate(timeout=5)
        if live_proxy_identity() is not None:
            try:
                os.killpg(proxy_pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            deadline = time.monotonic() + 1
            while (
                time.monotonic() < deadline
                and live_proxy_identity() is not None
            ):
                time.sleep(0.02)
            if live_proxy_identity() is not None:
                try:
                    os.killpg(proxy_pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        bridge_path.unlink(missing_ok=True)


def test_session_writes_private_strict_config_and_mcp_allowlist(tmp_path):
    session = ds.DesktopStdioSession(
        [sys.executable, "/tmp/fake-server.py"],
        server_env={"API_TOKEN": "secret"},
        root=tmp_path / "session",
    )
    session.start()
    try:
        config = json.loads(session.config_path.read_text())
        server = config["mcpServers"]["nxd-desktop"]
        assert config["mcpServers"].keys() == {"nxd-desktop"}
        assert server["command"] == sys.executable
        assert "--proxy" in server["args"]
        assert session.strict_mcp_config is True
        assert session.allowed_tools_csv == "mcp__nxd-desktop__*"
        assert session.setup_result.status == "passed"
        assert "secret" not in session.config_path.read_text()
        spec_text = (session.root / "server-spec.json").read_text()
        assert "secret" not in spec_text
        assert "NXD_EVAL_SOURCE_TOKEN" not in spec_text
        assert "NXD_DESKTOP_TRUSTED_CREDENTIAL_ENVS" not in spec_text
        assert stat.S_IMODE(session.root.stat().st_mode) == 0o700
        for private_file in (
            session.config_path,
            session.root / "server-spec.json",
            session.trace_path,
            session.server_result_path,
        ):
            assert stat.S_IMODE(private_file.stat().st_mode) == 0o600
    finally:
        session.cleanup()
    assert not (tmp_path / "session" / "mcp-config.json").exists()


def test_proxy_forwards_and_redacts_json_rpc_trace(tmp_path):
    child = _script(tmp_path / "server.py", FAKE_SERVER)
    session = ds.DesktopStdioSession(
        [sys.executable, str(child)],
        root=tmp_path / "session",
        server_env={"API_TOKEN": "secret"},
    ).start()
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
    try:
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"authorization": "Bearer live-token"},
        }
        assert proxy.stdin is not None and proxy.stdout is not None
        proxy.stdin.write(json.dumps(request) + "\n")
        proxy.stdin.flush()
        response = json.loads(proxy.stdout.readline())
        assert response["result"]["echo"] == "initialize"
        second_request = {"jsonrpc": "2.0", "id": 2, "method": "ping"}
        proxy.stdin.write(json.dumps(second_request) + "\n")
        proxy.stdin.flush()
        second_response = json.loads(proxy.stdout.readline())
        assert second_response["result"]["echo"] == "ping"
        proxy.stdin.close()
        assert proxy.wait(timeout=10) == 0
        trace = session.trace_path.read_text()
        assert "live-token" not in trace
        assert "secret" not in trace
        records = [json.loads(line) for line in trace.splitlines()]
        assert {record["direction"] for record in records} == {"request", "response"}
        request_records = [
            record for record in records if record["direction"] == "request"
        ]
        response_records = [
            record for record in records if record["direction"] == "response"
        ]
        assert len(request_records) == 2
        assert [record["message"]["method"] for record in request_records] == [
            "initialize",
            "ping",
        ]
        assert len(response_records) == 2
        assert all(record["message"] for record in records)
        result = json.loads(session.server_result_path.read_text())
        assert result["status"] == "passed"
    finally:
        if proxy.poll() is None:
            proxy.kill()
            proxy.wait()
        session.cleanup()


def test_codex_review_guard_returns_mcp_error_and_survives_report(tmp_path):
    child = _script(tmp_path / "review-guard-server.py", REVIEW_GUARD_SERVER)
    capture_dir = tmp_path / "retained-capture"
    capture_dir.mkdir()
    (capture_dir / "summary.json").write_text('{"status":"ready"}\n')
    blueprint = tmp_path / "retained-blueprint.md"
    blueprint.write_text("# Blueprint\n")
    server_text = REVIEW_GUARD_SERVER.replace(
        "PLACEHOLDER_CAPTURE", str(capture_dir)
    ).replace("PLACEHOLDER_BLUEPRINT", str(blueprint))
    child.write_text("#!/usr/bin/env python3\n" + server_text, encoding="utf-8")
    child.chmod(0o755)
    session = ds.DesktopStdioSession(
        [sys.executable, str(child)],
        root=tmp_path / "session",
        workflow_action_guard=True,
    ).start()
    proxy_env = dict(os.environ)
    proxy_env["PYTHONUNBUFFERED"] = "1"
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
        env=proxy_env,
        start_new_session=True,
    )

    def send(request):
        assert proxy.stdin is not None and proxy.stdout is not None
        proxy.stdin.write(json.dumps(request) + "\n")
        proxy.stdin.flush()

    def receive():
        assert proxy.stdout is not None
        return json.loads(proxy.stdout.readline())

    def call(request):
        send(request)
        return receive()

    try:
        send(
            {
                "jsonrpc": "2.0", "id": 1, "method": "tools/call",
                "params": {"name": "advance_workflow", "arguments": {
                    "workflow": "crm-pipeline", "action": {"type": "capture"}
                }},
            }
        )
        send({
            "jsonrpc": "2.0", "id": 9, "method": "tools/call",
            "params": {"name": "run_semantic_query", "arguments": {"query": "SELECT 1"}},
        })
        initial_responses = {response["id"]: response for response in (receive(), receive())}
        capture = initial_responses[1]
        concurrent_block = initial_responses[9]
        assert capture["result"]["next_actions"][0]["code"] == "workflow/review_pending"
        assert concurrent_block["result"]["isError"] is True
        assert concurrent_block["result"]["structuredContent"]["code"] == "runner/review_pending"

        initialized = call({
            "jsonrpc": "2.0", "id": 8, "method": "initialize", "params": {}
        })
        assert initialized["result"]["forwarded_operation"] == "initialize"

        # Protocol inventory remains available during review so the proxy can
        # advertise the runner-owned reader to the reviewer child.
        listed = call({"jsonrpc": "2.0", "id": 5, "method": "tools/list", "params": {}})
        assert {tool["name"] for tool in listed["result"]["tools"]} >= {
            "advance_workflow", "read_review_input"
        }

        reader = call({
            "jsonrpc": "2.0", "id": 6, "method": "tools/call",
            "params": {"name": "read_review_input", "arguments": {
                "path": str(capture_dir), "operation": "list"
            }},
        })
        assert reader["result"]["isError"] is False

        blocked_unlisted = call({
            "jsonrpc": "2.0", "id": 10, "method": "tools/call",
            "params": {"name": "run_semantic_query", "arguments": {"query": "SELECT 1"}},
        })
        assert blocked_unlisted["result"]["isError"] is True
        assert blocked_unlisted["result"]["structuredContent"]["code"] == "runner/review_pending"

        blocked = call(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "reset_workflow",
                    "arguments": {"workflow": "crm-pipeline"},
                },
            }
        )
        blocked_result = blocked["result"]
        assert blocked_result["isError"] is True
        assert blocked_result["structuredContent"]["code"] == "runner/review_pending"
        assert blocked_result["structuredContent"]["required_action"]["type"] == "report_requirement"
        assert blocked_result["structuredContent"]["required_action"]["parameters"]["requirement_id"] == "review"

        blocked_capture = call({
            "jsonrpc": "2.0", "id": 7, "method": "tools/call",
            "params": {"name": "advance_workflow", "arguments": {
                "workflow": "crm-pipeline",
                "action": {"type": "capture"}
            }},
        })
        assert blocked_capture["result"]["isError"] is True

        report = call(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "advance_workflow",
                    "arguments": {
                        "workflow": "crm-pipeline",
                        "action": {
                            "type": "report_requirement",
                            "parameters": {
                                "requirement_id": "review",
                                "generation": 1,
                                "subject_sha256": "subject-1",
                                "dependency_evidence_sha256": "evidence-1",
                            },
                        },
                    },
                },
            }
        )
        assert report["result"]["code"] == "workflow/review_findings"

        forwarded = call(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "reset_workflow",
                    "arguments": {"workflow": "crm-pipeline"},
                },
            }
        )
        assert forwarded["result"]["forwarded_operation"] == "reset_workflow"
        if proxy.stdin is not None:
            proxy.stdin.close()
        assert proxy.wait(timeout=10) == 0
    finally:
        if proxy.poll() is None:
            proxy.kill()
            proxy.wait()
        session.cleanup()


@pytest.mark.parametrize(
    "action",
    [
        {"type": "report_requirement", "parameters": {"requirement_id": "review"}},
        {"type": "report_requirement", "requirement_id": "review"},
    ],
)
def test_review_guard_accepts_canonical_and_legacy_report_envelopes(action):
    assert ds._is_review_requirement_report(action)
    assert ds._review_guard_decision(
        action, nex_mode=True, review_child_returned=True
    ) == (False, False)


def test_review_guard_rejects_conflicting_or_wrong_requirement_ids():
    conflicting = {
        "type": "report_requirement",
        "requirement_id": "review",
        "parameters": {"requirement_id": "validation"},
    }
    wrong = {
        "type": "report_requirement",
        "parameters": {"requirement_id": "validation"},
    }
    for action in (conflicting, wrong):
        assert not ds._is_review_requirement_report(action)
        assert ds._review_guard_decision(
            action, nex_mode=True, review_child_returned=True
        ) == (True, False)


def test_nex_review_report_before_child_return_blocks_and_invalidates():
    action = {
        "type": "report_requirement",
        "parameters": {"requirement_id": "review"},
    }
    assert ds._review_guard_decision(
        action, nex_mode=True, review_child_returned=False
    ) == (True, True)


def test_nex_validation_guard_recognizes_workflow_v2_requirement():
    request = {
        "method": "tools/call",
        "params": {
            "name": "advance_workflow",
            "arguments": {
                "action": {
                    "type": "start_requirement",
                    "parameters": {"requirement_id": "validation"},
                }
            },
        },
    }
    assert ds._is_nex_validation_advance(request)
    request["params"]["arguments"]["action"]["parameters"]["requirement_id"] = "review"
    assert not ds._is_nex_validation_advance(request)
    request["params"]["arguments"]["action"]["parameters"]["requirement_id"] = "validation"
    request["params"]["arguments"]["action"]["requirement_id"] = "other"
    assert not ds._is_nex_validation_advance(request)


def test_proxy_exposes_bounded_runner_owned_review_reader(tmp_path):
    child = _script(tmp_path / "review-reader-server.py", REVIEW_READER_SERVER)
    capture = tmp_path / "capture"
    capture.mkdir()
    (capture / "build-record.json").write_text('{"status":"ok"}\n')
    transform = capture / "transform"
    transform.mkdir()
    source_path = transform / "main.py"
    source_path.write_text("ENDPOINT = '/v1/orders'\n")
    (capture / ".env").write_text("TOKEN=must-not-be-read\n")
    (capture / ".env.local").write_text("TOKEN=must-not-be-read\n")
    blueprint = tmp_path / "blueprint.md"
    blueprint.write_text("# Approved blueprint\n")
    outside = tmp_path / "outside-review-secret.txt"
    outside.write_text("OUTSIDE_REVIEW_SECRET\n")
    escape_link = capture / "outside-link.txt"
    escape_link.symlink_to(outside)
    session = ds.DesktopStdioSession(
        [sys.executable, str(child)],
        root=tmp_path / "session",
    ).start()
    session._write_review_allowlist(
        {
            "review_input": {
                "retained_capture_root": str(capture),
                "retained_blueprint_path": str(blueprint),
            }
        }
    )
    proxy = subprocess.Popen(
        [sys.executable, str(ds.PROXY_MODULE), "--proxy", "--spec", str(session.root / "server-spec.json")],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )

    def call(request):
        assert proxy.stdin is not None and proxy.stdout is not None
        proxy.stdin.write(json.dumps(request) + "\n")
        proxy.stdin.flush()
        return json.loads(proxy.stdout.readline())

    try:
        listed = call({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        assert any(
            tool.get("name") == ds._REVIEW_READER_TOOL
            for tool in listed["result"]["tools"]
        )
        read = call(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": ds._REVIEW_READER_TOOL,
                    "arguments": {
                        "path": str(blueprint),
                        "operation": "read",
                    },
                },
            }
        )
        assert read["id"] == 2
        assert read["result"]["isError"] is False
        assert "Approved blueprint" in read["result"]["content"][0]["text"]
        assert read["result"]["structuredContent"]["path"] == str(blueprint)
        trace_text_after_read = session.trace_path.read_text()
        trace_records = [json.loads(line) for line in trace_text_after_read.splitlines()]
        reader_summaries = [
            record
            for record in trace_records
            if record.get("direction") == "summary"
            and record.get("message", {}).get("params", {}).get("name")
            == ds._REVIEW_READER_TOOL
        ]
        assert len(reader_summaries) == 1
        assert reader_summaries[0]["synthetic"] is True
        assert reader_summaries[0]["message"]["params"] == {
            "name": ds._REVIEW_READER_TOOL
        }
        assert "arguments" not in json.dumps(reader_summaries[0])
        assert "Approved blueprint" not in trace_text_after_read
        assert str(blueprint) not in trace_text_after_read
        assert not any(
            record.get("direction") in {"request", "response"}
            and record.get("message", {}).get("id") == 2
            for record in trace_records
        )
        source_read = call({
            "jsonrpc": "2.0", "id": 2.25, "method": "tools/call",
            "params": {"name": ds._REVIEW_READER_TOOL, "arguments": {
                "path": str(source_path), "operation": "read",
            }},
        })
        assert source_read["result"]["isError"] is False
        assert "ENDPOINT = '/v1/orders'" in source_read["result"]["content"][0]["text"]
        traversal = call({
            "jsonrpc": "2.0", "id": 2.3, "method": "tools/call",
            "params": {"name": ds._REVIEW_READER_TOOL, "arguments": {
                "path": str(capture / "transform" / ".." / "build-record.json"),
                "operation": "read",
            }},
        })
        assert traversal["result"]["isError"] is True
        escaped = call({
            "jsonrpc": "2.0", "id": 2.4, "method": "tools/call",
            "params": {"name": ds._REVIEW_READER_TOOL, "arguments": {
                "path": str(escape_link), "operation": "read",
            }},
        })
        assert escaped["result"]["isError"] is True
        bounded_read = call(
            {
                "jsonrpc": "2.0",
                "id": 2.5,
                "method": "tools/call",
                "params": {
                    "name": ds._REVIEW_READER_TOOL,
                    "arguments": {
                        "path": str(blueprint),
                        "operation": "read",
                        "max_lines": 250,
                        "max_bytes": 20000,
                    },
                },
            }
        )
        assert bounded_read["id"] == 2.5
        assert bounded_read["result"]["isError"] is False
        trace_records_after_bounded = [
            json.loads(line) for line in session.trace_path.read_text().splitlines()
        ]
        bounded_summaries = [
            record
            for record in trace_records_after_bounded
            if record.get("direction") == "summary"
            and record.get("message", {}).get("params", {}).get("name")
            == ds._REVIEW_READER_TOOL
        ]
        # Every reader attempt is represented by a safe summary, including
        # rejected traversal and symlink reads; raw arguments stay out of trace.
        assert len(bounded_summaries) == 5
        assert all(
            record["message"]["params"] == {"name": ds._REVIEW_READER_TOOL}
            for record in bounded_summaries
        )
        assert all(
            "arguments" not in json.dumps(record) for record in bounded_summaries
        )
        assert not any(
            record.get("direction") in {"request", "response"}
            and record.get("message", {}).get("id") == 2.5
            for record in trace_records_after_bounded
        )
        listing = call(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": ds._REVIEW_READER_TOOL,
                    "arguments": {"path": str(capture), "operation": "list"},
                },
            }
        )
        assert "build-record.json" in listing["result"]["content"][0]["text"]
        assert listing["result"]["structuredContent"]["path"] == str(capture)
        listed_paths = {
            entry["path"]
            for entry in listing["result"]["structuredContent"]["entries"]
        }
        assert str(capture / "build-record.json") in listed_paths
        assert ".env" not in listing["result"]["content"][0]["text"]
        assert ".env.local" not in listing["result"]["content"][0]["text"]
        outside = call(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": ds._REVIEW_READER_TOOL,
                    "arguments": {"path": str(tmp_path), "operation": "list"},
                },
            }
        )
        assert outside["result"]["isError"] is True
        forwarded = call(
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {
                    "name": "supervisor_tool",
                    "arguments": {},
                },
            }
        )
        assert forwarded["result"]["forwarded_tool"] == "supervisor_tool"
        trace_text = session.trace_path.read_text()
        assert "must-not-be-read" not in trace_text
        assert "Approved blueprint" not in trace_text
        assert str(blueprint) not in trace_text
        assert str(capture) not in trace_text
        reader_summaries = [
            json.loads(line)["review_reader_summary"]
            for line in trace_text.splitlines()
            if '"review_reader_summary"' in line
        ]
        assert len(reader_summaries) == 7
        assert any(
            summary["operation"] == "read"
            and summary["path_class"] == "blueprint"
            and summary["error_code"] == "ok"
            and summary["output_bytes"] > 0
            for summary in reader_summaries
        )
        assert any(
            summary["path_class"] == "outside_allowlist"
            and summary["error_code"] == "path_outside_allowlist"
            for summary in reader_summaries
        )
        assert "OUTSIDE_REVIEW_SECRET" not in trace_text
        if proxy.stdin is not None:
            proxy.stdin.close()
        assert proxy.wait(timeout=10) == 0
    finally:
        if proxy.poll() is None:
            proxy.kill()
            proxy.wait()
        session.cleanup()


def test_review_reader_preserves_allowlisted_root_spelling_and_rejects_unsafe_paths(
    tmp_path,
):
    capture = tmp_path / "capture"
    capture.mkdir()
    (capture / "notes.txt").write_text("safe notes\n")
    (capture / ".env.private").write_text("not a credential\n")
    alias = tmp_path / "capture-alias"
    alias.symlink_to(capture, target_is_directory=True)
    outside = tmp_path / "outside.txt"
    outside.write_text("outside\n")
    (capture / "escape.txt").symlink_to(outside)
    (capture / "sensitive-alias.txt").symlink_to(capture / ".env.private")
    allowlist = tmp_path / "allowlist.json"
    allowlist.write_text(json.dumps({"retained_capture_root": str(alias)}))

    read = ds._review_reader_result(
        {
            "params": {
                "arguments": {"path": str(alias / "notes.txt"), "operation": "read"}
            }
        },
        allowlist,
    )
    assert read["isError"] is False
    assert read["structuredContent"]["path"] == str(alias / "notes.txt")

    listing = ds._review_reader_result(
        {
            "params": {
                "arguments": {"path": str(alias), "operation": "list"}
            }
        },
        allowlist,
    )
    listed_paths = {
        entry["path"] for entry in listing["structuredContent"]["entries"]
    }
    assert str(alias / "notes.txt") in listed_paths
    assert str(outside) not in listed_paths
    assert str(alias / "escape.txt") not in listed_paths
    assert str(alias / "sensitive-alias.txt") not in listed_paths

    for unsafe in (
        str(alias / ".." / "outside.txt"),
        str(alias / ".env.private"),
        str(alias / "notes.txt") + "\x00suffix",
    ):
        result = ds._review_reader_result(
            {"params": {"arguments": {"path": unsafe, "operation": "read"}}},
            allowlist,
        )
        assert result["isError"] is True


def _review_reader_call(allowlist, path, operation, **arguments):
    return ds._review_reader_result(
        {
            "params": {
                "arguments": {
                    "path": str(path),
                    "operation": operation,
                    **arguments,
                }
            }
        },
        allowlist,
    )


def _review_reader_list_fixture(tmp_path):
    capture = tmp_path / "capture"
    capture.mkdir()
    (capture / ".env").write_text("not a credential\n")
    for name in ("a.txt", "b.txt", "c.txt", "d.txt"):
        (capture / name).write_text(f"{name}\n")
    clean = capture / "clean"
    clean.mkdir()
    (clean / "one.txt").write_text("one\n")
    token_dir = capture / "token is"
    token_dir.mkdir()
    (token_dir / "child-sentinel.txt").write_text("SENTINEL-BODY\n")
    (capture / "zz.pem").write_text("not a credential\n")
    allowlist = tmp_path / "allowlist.json"
    allowlist.write_text(json.dumps({"retained_capture_root": str(capture)}))
    return capture, allowlist


def test_review_reader_rejects_symlink_whose_display_path_redacts(tmp_path):
    capture = tmp_path / "capture"
    secret_dir = capture / "token is"
    nested = secret_dir / "inner"
    nested.mkdir(parents=True)
    (secret_dir / "child-sentinel.txt").write_text("SENTINEL-BODY\n")
    (nested / "inner-sentinel.txt").write_text("INNER-SENTINEL-BODY\n")
    alias = capture / "alias"
    alias.symlink_to("token is", target_is_directory=True)
    (capture / "link").symlink_to("token is/child-sentinel.txt")
    allowlist = tmp_path / "allowlist.json"
    allowlist.write_text(json.dumps({"retained_capture_root": str(capture)}))

    request_paths = (
        capture,
        alias,
        alias / "child-sentinel.txt",
        alias / "inner",
        capture / "link",
    )
    for request_path in request_paths:
        assert ds.redact_text(str(request_path)) == str(request_path)
    # The list-entry symlink itself is safe to name, but its resolved display
    # path is not; the root listing below must withhold it.
    assert ds.redact_text(str(capture / "link")) == str(capture / "link")
    assert ds.redact_text(str(secret_dir / "child-sentinel.txt")) != str(
        secret_dir / "child-sentinel.txt"
    )
    assert ds.redact_text(str(nested)) != str(nested)

    read_alias = _review_reader_call(
        allowlist, alias / "child-sentinel.txt", "read"
    )
    list_alias_inner = _review_reader_call(allowlist, alias / "inner", "list")
    expected_error = {"error": "requested review path cannot be shown verbatim"}
    for response in (read_alias, list_alias_inner):
        assert response["isError"] is True
        assert response["structuredContent"] == expected_error
        assert json.loads(response["content"][0]["text"]) == expected_error

    list_alias = _review_reader_call(allowlist, alias, "list")
    assert list_alias["isError"] is False
    assert list_alias["structuredContent"]["path"] == str(secret_dir)
    assert list_alias["structuredContent"]["entries"] == []
    assert list_alias["structuredContent"]["omitted"] == {
        "total": 2,
        "withheld": 2,
        "max_lines": 0,
        "max_bytes": 0,
    }

    # A visible symlink name is not sufficient: the emitted target path must
    # also pass the same verbatim check as a direct request.
    list_capture = _review_reader_call(allowlist, capture, "list")
    assert list_capture["isError"] is False
    entries = list_capture["structuredContent"]["entries"]
    assert {entry["name"] for entry in entries} == {"alias", "token is"}
    assert list_capture["structuredContent"]["omitted"] == {
        "total": 1,
        "withheld": 1,
        "max_lines": 0,
        "max_bytes": 0,
    }
    for response in (read_alias, list_alias_inner, list_alias, list_capture):
        channels = response["content"][0]["text"] + json.dumps(
            response["structuredContent"], sort_keys=True
        )
        assert "child-sentinel" not in channels
        assert "inner-sentinel" not in channels
        assert "SENTINEL-BODY" not in channels


def test_review_reader_trace_metadata_uses_reader_validation_order(tmp_path):
    capture = tmp_path / "capture"
    sensitive_parent = capture / "token is"
    inner = sensitive_parent / "inner"
    inner.mkdir(parents=True)
    (sensitive_parent / "child-sentinel.txt").write_text("SENTINEL-BODY")
    (inner / "inner-sentinel.txt").write_text("INNER-SENTINEL")
    alias = capture / "alias"
    alias.symlink_to("token is", target_is_directory=True)
    allowlist = tmp_path / "allowlist.json"
    allowlist.write_text(json.dumps({"retained_capture_root": str(capture)}))

    cases = (
        (str(capture / "bad\x00path"), "invalid", "path_invalid_character"),
        ("relative\x00path", "invalid", "path_invalid_character"),
        ("relative/path", "relative", "relative_path"),
        (str(capture / ".." / "outside"), "invalid", "path_parent_traversal"),
        (
            str(sensitive_parent / "child-sentinel.txt"),
            "invalid",
            "path_not_verbatim",
        ),
        (
            str(alias / "child-sentinel.txt"),
            "invalid",
            "path_not_verbatim",
        ),
    )
    for path, expected_class, expected_code in cases:
        request = {"params": {"arguments": {"path": path, "operation": "read"}}}
        result = ds._review_reader_result(request, allowlist)
        summary = ds._review_reader_trace_metadata(
            request, result, allowlist, elapsed_ms=0.25
        )
        assert (summary["path_class"], summary["error_code"]) == (
            expected_class,
            expected_code,
        )
        assert str(capture) not in json.dumps(summary, sort_keys=True)
        assert "SENTINEL" not in json.dumps(summary, sort_keys=True)


def test_review_reader_symlink_loop_returns_structured_error_and_recovers(tmp_path):
    capture = tmp_path / "capture"
    capture.mkdir()
    safe_file = capture / "safe.txt"
    safe_file.write_text("still available\n")
    loop = capture / "loop"
    loop.symlink_to(loop)
    allowlist = tmp_path / "allowlist.json"
    allowlist.write_text(json.dumps({"retained_capture_root": str(capture)}))
    loop_request = {
        "params": {
            "arguments": {"path": str(loop / "notes.txt"), "operation": "read"}
        }
    }

    error = ds._review_reader_result(loop_request, allowlist)
    trace = ds._review_reader_trace_metadata(
        loop_request, error, allowlist, elapsed_ms=0
    )
    valid = ds._review_reader_result(
        {
            "params": {
                "arguments": {"path": str(safe_file), "operation": "read"}
            }
        },
        allowlist,
    )

    assert error["isError"] is True
    assert error["structuredContent"]["error"] == (
        "requested review path is unavailable"
    )
    assert trace["path_class"] == "unavailable"
    assert trace["error_code"] == "path_unavailable"
    assert valid["isError"] is False

    root_loop = tmp_path / "root-loop"
    root_loop.symlink_to(root_loop)
    root_loop_allowlist = tmp_path / "root-loop-allowlist.json"
    root_loop_allowlist.write_text(
        json.dumps({"retained_capture_root": str(root_loop)})
    )
    root_error = ds._review_reader_result(
        {
            "params": {
                "arguments": {"path": str(safe_file), "operation": "read"}
            }
        },
        root_loop_allowlist,
    )
    root_trace = ds._review_reader_trace_metadata(
        {
            "params": {
                "arguments": {"path": str(safe_file), "operation": "read"}
            }
        },
        root_error,
        root_loop_allowlist,
        elapsed_ms=0,
    )

    assert root_error["isError"] is True
    assert root_error["structuredContent"]["error"] == (
        "review input root is unavailable"
    )
    assert root_trace["error_code"] == "allowlist_root_unavailable"


def test_review_reader_trace_distinguishes_unavailable_sources(tmp_path):
    request_path = tmp_path / "capture" / "missing.txt"
    request = {
        "params": {
            "arguments": {"path": str(request_path), "operation": "read"}
        }
    }

    missing_allowlist = tmp_path / "missing-allowlist.json"
    unavailable_allowlist_result = ds._review_reader_result(request, missing_allowlist)
    unavailable_allowlist = ds._review_reader_trace_metadata(
        request, unavailable_allowlist_result, missing_allowlist, elapsed_ms=0
    )
    assert unavailable_allowlist["path_class"] == "invalid_allowlist"
    assert unavailable_allowlist["error_code"] == "allowlist_unavailable"

    unavailable_root_allowlist = tmp_path / "unavailable-root.json"
    unavailable_root_allowlist.write_text(
        json.dumps({"retained_capture_root": str(tmp_path / "gone")})
    )
    unavailable_root_result = ds._review_reader_result(
        request, unavailable_root_allowlist
    )
    unavailable_root = ds._review_reader_trace_metadata(
        request, unavailable_root_result, unavailable_root_allowlist, elapsed_ms=0
    )
    assert unavailable_root["path_class"] == "unavailable"
    assert unavailable_root["error_code"] == "allowlist_root_unavailable"

    capture = tmp_path / "capture"
    capture.mkdir()
    request_allowlist = tmp_path / "request-allowlist.json"
    request_allowlist.write_text(json.dumps({"retained_capture_root": str(capture)}))
    unavailable_path_result = ds._review_reader_result(request, request_allowlist)
    unavailable_path = ds._review_reader_trace_metadata(
        request, unavailable_path_result, request_allowlist, elapsed_ms=0
    )
    assert unavailable_path["path_class"] == "unavailable"
    assert unavailable_path["error_code"] == "path_unavailable"


def test_review_reader_read_stays_within_max_bytes_in_every_channel(tmp_path):
    capture = tmp_path / "capture"
    capture.mkdir()
    source = capture / "notes.txt"
    source.write_text("api_key=super-secret-value\n" + "é" * 300)
    allowlist = tmp_path / "allowlist.json"
    allowlist.write_text(json.dumps({"retained_capture_root": str(capture)}))
    max_bytes = 256

    response = _review_reader_call(
        allowlist, source, "read", max_bytes=max_bytes
    )
    assert response["isError"] is False
    content_text = response["content"][0]["text"]
    structured = response["structuredContent"]
    assert len(content_text.encode("utf-8")) <= max_bytes
    assert len(structured["text"].encode("utf-8")) <= max_bytes
    assert len(structured["path"].encode("utf-8")) <= max_bytes
    assert structured["truncated"] is True
    assert content_text.endswith(ds._REVIEW_READER_TRUNCATION_MARKER)
    assert "super-secret-value" not in content_text
    assert "super-secret-value" not in structured["text"]
    assert "api_key=<redacted>" in content_text
    assert "api_key=<redacted>" in structured["text"]


def test_review_reader_bounds_raw_source_and_drops_partial_secret_line(
    tmp_path, monkeypatch
):
    capture = tmp_path / "capture"
    capture.mkdir()
    source = capture / "notes.txt"
    source.write_bytes(
        b"safe heading\nhttps://user:"
        + b"sensitive-value-" * 100_000
        + b"@example.com\n"
    )
    allowlist = tmp_path / "allowlist.json"
    allowlist.write_text(json.dumps({"retained_capture_root": str(capture)}))

    original_open = Path.open
    read_sizes = []

    class ReadSpy:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.stream.close()

        def read(self, size=-1):
            read_sizes.append(size)
            return self.stream.read(size)

    def observed_open(path, mode="r", *args, **kwargs):
        stream = original_open(path, mode, *args, **kwargs)
        return ReadSpy(stream) if path == source.resolve() and mode == "rb" else stream

    monkeypatch.setattr(Path, "open", observed_open)
    response = _review_reader_call(allowlist, source, "read", max_bytes=2048)

    assert response["isError"] is False
    assert read_sizes == [ds._REVIEW_READER_MAX_SOURCE_BYTES + 1]
    structured = response["structuredContent"]
    assert structured["truncated"] is True
    assert structured["text"].startswith("safe heading\n")
    assert "sensitive-value" not in response["content"][0]["text"]
    assert "user:" not in response["content"][0]["text"]
    assert response["content"][0]["text"].endswith(ds._REVIEW_READER_TRUNCATION_MARKER)
    assert len(response["content"][0]["text"].encode("utf-8")) <= 2048

    source.write_bytes(b"x\n" * (ds._REVIEW_READER_MAX_SOURCE_BYTES // 2 + 1))
    read_sizes.clear()
    dense_response = _review_reader_call(allowlist, source, "read", max_bytes=2048)
    assert read_sizes == [ds._REVIEW_READER_MAX_SOURCE_BYTES + 1]
    dense_text = dense_response["structuredContent"]["text"]
    assert dense_response["structuredContent"]["truncated"] is True
    assert dense_text.count("x\n") <= ds._REVIEW_READER_MAX_LINES
    assert len(dense_text.encode("utf-8")) <= 2048


def test_review_reader_redacts_before_applying_the_byte_budget(tmp_path):
    capture = tmp_path / "capture"
    capture.mkdir()
    source = capture / "notes.txt"
    raw_body = "api_key=x\n" + "x" * 100
    source.write_text(raw_body)
    allowlist = tmp_path / "allowlist.json"
    allowlist.write_text(json.dumps({"retained_capture_root": str(capture)}))
    prefix_bytes = len(f"Path: {source}\n".encode("utf-8"))
    # The raw body fits, but redaction expands it. The output still has to
    # reserve the truncation marker and remain within the requested bytes.
    max_bytes = prefix_bytes + len(raw_body.encode("utf-8")) + 4

    response = _review_reader_call(
        allowlist, source, "read", max_bytes=max_bytes
    )
    assert response["isError"] is False
    assert response["structuredContent"]["truncated"] is True
    assert len(response["content"][0]["text"].encode("utf-8")) <= max_bytes
    assert len(response["structuredContent"]["text"].encode("utf-8")) <= max_bytes
    assert response["content"][0]["text"].endswith(
        ds._REVIEW_READER_TRUNCATION_MARKER
    )
    assert "api_key=<redacted>" in response["structuredContent"]["text"]
    assert "api_key=x" not in response["structuredContent"]["text"]


def test_review_reader_read_exact_fit_and_small_path_budget(tmp_path):
    capture = tmp_path / "capture"
    capture.mkdir()
    source = capture / "notes.txt"
    body = "x" * 40
    source.write_text(body)
    allowlist = tmp_path / "allowlist.json"
    allowlist.write_text(json.dumps({"retained_capture_root": str(capture)}))
    prefix = f"Path: {source}\n"
    prefix_bytes = len(prefix.encode("utf-8"))

    exact = _review_reader_call(
        allowlist,
        source,
        "read",
        max_bytes=prefix_bytes + len(body.encode("utf-8")),
    )
    assert exact["isError"] is False
    assert exact["content"][0]["text"] == prefix + body
    assert exact["structuredContent"]["truncated"] is False

    truncated_without_body_room = _review_reader_call(
        allowlist,
        source,
        "read",
        max_bytes=prefix_bytes
        + len(ds._REVIEW_READER_TRUNCATION_MARKER.encode("utf-8")),
    )
    assert truncated_without_body_room["isError"] is True
    assert truncated_without_body_room["structuredContent"] == {
        "error": "max_bytes too small for review path"
    }

    too_small = _review_reader_call(allowlist, source, "read", max_bytes=1)
    assert too_small["isError"] is True
    assert too_small["structuredContent"] == {
        "error": "max_bytes too small for review path"
    }


def test_review_reader_loads_roots_once_per_list(tmp_path, monkeypatch):
    capture, allowlist = _review_reader_list_fixture(tmp_path)
    original = ds._review_reader_roots
    calls = 0

    def counted(path):
        nonlocal calls
        calls += 1
        return original(path)

    monkeypatch.setattr(ds, "_review_reader_roots", counted)
    response = _review_reader_call(allowlist, capture, "list", max_lines=2)
    assert response["isError"] is False
    assert calls == 1


def test_review_reader_list_withholds_parent_context_children(tmp_path):
    capture, allowlist = _review_reader_list_fixture(tmp_path)
    token_dir = capture / "token is"
    response = _review_reader_call(allowlist, token_dir, "list")
    assert response["isError"] is False
    assert response["structuredContent"]["entries"] == []
    assert response["structuredContent"]["omitted"] == {
        "total": 1,
        "withheld": 1,
        "max_lines": 0,
        "max_bytes": 0,
    }
    assert response["content"][0]["text"] == (
        "[]\n[1 entries omitted: withheld=1 max_lines=0 max_bytes=0]"
    )
    assert "child-sentinel" not in json.dumps(response, sort_keys=True)


def test_review_reader_list_counts_entries_past_max_lines_once(tmp_path):
    capture, allowlist = _review_reader_list_fixture(tmp_path)
    response = _review_reader_call(
        allowlist, capture, "list", max_lines=2
    )
    assert response["isError"] is False
    structured = response["structuredContent"]
    assert [entry["name"] for entry in structured["entries"]] == ["a.txt", "b.txt"]
    assert structured["omitted"] == {
        "total": 6,
        "withheld": 2,
        "max_lines": 4,
        "max_bytes": 0,
    }
    assert len(structured["entries"]) + structured["omitted"]["total"] == 8
    assert ".env" not in response["content"][0]["text"]
    assert "zz.pem" not in response["content"][0]["text"]


def test_review_reader_list_byte_cut_is_exact_and_one_byte_short(tmp_path):
    capture, allowlist = _review_reader_list_fixture(tmp_path)
    all_candidates = [
        {"kind": "file", "name": name, "path": str(capture / name)}
        for name in ("a.txt", "b.txt")
    ]
    encoded_two = json.dumps(all_candidates, sort_keys=True)
    reserve = len(
        ds._review_list_trailer(total=8, withheld=8, max_lines=8, max_bytes=8).encode(
            "utf-8"
        )
    )
    exact_budget = len(encoded_two.encode("utf-8")) + reserve

    exact = _review_reader_call(
        allowlist,
        capture,
        "list",
        max_lines=ds._REVIEW_READER_MAX_LINES,
        max_bytes=exact_budget,
    )
    assert exact["isError"] is False
    assert exact["structuredContent"]["entries"] == all_candidates
    assert exact["structuredContent"]["omitted"] == {
        "total": 6,
        "withheld": 2,
        "max_lines": 0,
        "max_bytes": 4,
    }
    assert len(exact["content"][0]["text"].encode("utf-8")) == exact_budget
    actual_trailer = ds._review_list_trailer(
        total=6, withheld=2, max_lines=0, max_bytes=4
    )
    assert len(
        json.dumps(
            exact["structuredContent"]["entries"], sort_keys=True
        ).encode("utf-8")
    ) + len(actual_trailer.encode("utf-8")) <= exact_budget

    short = _review_reader_call(
        allowlist,
        capture,
        "list",
        max_lines=ds._REVIEW_READER_MAX_LINES,
        max_bytes=exact_budget - 1,
    )
    assert short["isError"] is False
    assert [entry["name"] for entry in short["structuredContent"]["entries"]] == [
        "a.txt"
    ]
    assert short["structuredContent"]["omitted"] == {
        "total": 7,
        "withheld": 2,
        "max_lines": 0,
        "max_bytes": 5,
    }


def test_review_reader_list_rejects_max_bytes_below_worst_case_trailer(tmp_path):
    capture, allowlist = _review_reader_list_fixture(tmp_path)
    response = _review_reader_call(allowlist, capture, "list", max_bytes=1)
    assert response["isError"] is True
    assert response["structuredContent"] == {
        "error": "max_bytes too small to list review directory"
    }


def test_review_reader_list_without_omissions_keeps_legacy_shape(tmp_path):
    capture, allowlist = _review_reader_list_fixture(tmp_path)
    clean = capture / "clean"
    response = _review_reader_call(allowlist, clean, "list")
    assert response["isError"] is False
    assert response["content"][0]["text"] == json.dumps(
        response["structuredContent"]["entries"], sort_keys=True
    )
    assert "omitted" not in response["structuredContent"]
    assert response["structuredContent"]["entries"] == [
        {"kind": "file", "name": "one.txt", "path": str(clean / "one.txt")}
    ]


def test_review_reader_is_advertised_but_fails_closed_without_a_live_allowlist(tmp_path):
    message = {"jsonrpc": "2.0", "id": 1, "result": {"tools": []}}
    listed = ds._augment_tools_list(
        message, allowlist_path=tmp_path / "missing-review-allowlist.json"
    )
    assert any(
        tool.get("name") == ds._REVIEW_READER_TOOL
        for tool in listed["result"]["tools"]
    )
    response = ds._review_reader_result(
        {
            "params": {
                "arguments": {
                    "path": str(tmp_path / "capture"),
                    "operation": "list",
                }
            }
        },
        tmp_path / "missing-review-allowlist.json",
    )
    assert response["isError"] is True


def test_review_reader_summarizes_malformed_calls_without_retaining_input(tmp_path):
    capture = tmp_path / "capture"
    capture.mkdir()
    allowlist = tmp_path / "allowlist.json"
    allowlist.write_text(
        json.dumps({"retained_capture_root": str(capture)}), encoding="utf-8"
    )
    request = {
        "params": {
            "arguments": {
                "path": str(capture),
                "operation": [],
            }
        }
    }

    result = ds._review_reader_result(request, allowlist)
    summary = ds._review_reader_trace_metadata(
        request, result, allowlist, elapsed_ms=1.25
    )

    assert result["isError"] is True
    assert summary["operation"] == "invalid"
    assert summary["path_class"] == "capture_root"
    assert summary["error_code"] == "invalid_operation"
    assert summary["elapsed_ms"] == 1.25


def test_review_reader_discovered_before_capture_works_after_allowlist_publish(tmp_path):
    child = _script(tmp_path / "review-reader-catalog-server.py", REVIEW_READER_SERVER)
    capture = tmp_path / "capture"
    capture.mkdir()
    (capture / "build-record.json").write_text('{"status":"ok"}\n')
    blueprint = tmp_path / "blueprint.md"
    blueprint.write_text("# Approved blueprint\n")
    session = ds.DesktopStdioSession(
        [sys.executable, str(child)],
        root=tmp_path / "session",
    ).start()
    proxy = subprocess.Popen(
        [sys.executable, str(ds.PROXY_MODULE), "--proxy", "--spec", str(session.root / "server-spec.json")],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )

    def call(request):
        assert proxy.stdin is not None and proxy.stdout is not None
        proxy.stdin.write(json.dumps(request) + "\n")
        proxy.stdin.flush()
        return json.loads(proxy.stdout.readline())

    try:
        listed = call({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        assert any(
            tool.get("name") == ds._REVIEW_READER_TOOL
            for tool in listed["result"]["tools"]
        )
        session._write_review_allowlist(
            {
                "review_input": {
                    "retained_capture_root": str(capture),
                    "retained_blueprint_path": str(blueprint),
                }
            }
        )
        read = call(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": ds._REVIEW_READER_TOOL,
                    "arguments": {
                        "path": str(blueprint),
                        "operation": "read",
                    },
                },
            }
        )
        assert read["result"]["isError"] is False
        assert "Approved blueprint" in read["result"]["content"][0]["text"]
    finally:
        if proxy.stdin is not None:
            proxy.stdin.close()
        if proxy.poll() is None:
            proxy.kill()
        proxy.wait()
        session.cleanup()


def test_review_reader_bounds_raw_source_and_drops_partial_credential_line(
    tmp_path, monkeypatch
):
    capture = tmp_path / "capture"
    capture.mkdir()
    source = capture / "evidence.txt"
    source.write_bytes(
        b"safe line\nhttps://reviewer:secret-"
        + b"x" * (ds._REVIEW_READER_MAX_SOURCE_BYTES + 32)
        + b"@example.invalid/path\n"
    )
    allowlist = tmp_path / "allowlist.json"
    allowlist.write_text(
        json.dumps({"retained_capture_root": str(capture)}), encoding="utf-8"
    )
    real_open = Path.open
    read_sizes = []

    class ReadSpy:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return self.stream.__exit__(*args)

        def read(self, size=-1):
            read_sizes.append(size)
            return self.stream.read(size)

    def tracking_open(path, mode="r", *args, **kwargs):
        stream = real_open(path, mode, *args, **kwargs)
        if path == source and mode == "rb":
            return ReadSpy(stream)
        return stream

    monkeypatch.setattr(Path, "open", tracking_open)
    response = ds._review_reader_result(
        {
            "params": {
                "arguments": {
                    "path": str(source),
                    "operation": "read",
                    "max_bytes": 2048,
                }
            }
        },
        allowlist,
    )

    output = response["content"][0]["text"]
    assert response["isError"] is False
    assert read_sizes == [ds._REVIEW_READER_MAX_SOURCE_BYTES + 1]
    assert output == (
        f"Path: {source}\n"
        + "safe line\n"
        + ds._REVIEW_READER_TRUNCATION_MARKER
    )
    assert "reviewer" not in output
    assert "secret" not in output
    assert "xxxx" not in output
    assert len(output.encode("utf-8")) <= 2048


def test_review_reader_symlink_loops_fail_closed(tmp_path):
    capture = tmp_path / "capture"
    capture.mkdir()
    loop = capture / "loop"
    loop.symlink_to(loop)
    allowlist = tmp_path / "allowlist.json"
    allowlist.write_text(
        json.dumps({"retained_capture_root": str(capture)}), encoding="utf-8"
    )

    response = ds._review_reader_result(
        {
            "params": {
                "arguments": {"path": str(loop), "operation": "list"}
            }
        },
        allowlist,
    )

    assert response["isError"] is True
    assert (
        response["structuredContent"]["error"]
        == "requested review path is unavailable"
    )


def test_review_allowlist_is_cleared_after_review_report(tmp_path):
    session = ds.DesktopStdioSession(
        [sys.executable, "/tmp/fake-server.py"], root=tmp_path / "session"
    ).start()
    try:
        state = {
            "review_input": {
                "retained_capture_root": str(tmp_path / "capture"),
                "retained_blueprint_path": str(tmp_path / "blueprint.md"),
            }
        }
        session._write_review_allowlist(state)
        assert json.loads(session.review_allowlist_path.read_text())
        session._write_review_allowlist(None)
        assert json.loads(session.review_allowlist_path.read_text()) == {}
    finally:
        session.cleanup()


def test_review_guard_recognizes_workflow_v2_action_shape():
    capture = {
        "result": {
            "revision": 4,
            "requirements": [
                {"id": "review", "status": "pending", "review_input": {}}
            ],
            "next_actions": [
                {
                    "action": "report_requirement",
                    "code": "workflow/review_pending",
                    "requirement_id": "review",
                }
            ],
        }
    }
    report = {
        "result": {
            "code": "workflow/review_satisfied",
            "requirement_id": "review",
            "requirements": [{"id": "review", "status": "complete"}],
        }
    }
    assert ds._response_requires_review(capture)
    assert ds._response_satisfies_review(report)


def test_review_guard_uses_non_null_review_input_view():
    response = {
        "result": {
            "requirements": [
                {"id": "capture", "review_input": None},
                {
                    "id": "review",
                    "review_input": {
                        "retained_capture_root": "/capture",
                        "retained_blueprint_path": "/blueprint.md",
                    },
                },
            ]
        }
    }
    snapshot = ds._review_guard_snapshot(response)
    assert ds._review_allowlist_payload(snapshot) == {
        "retained_capture_root": "/capture",
        "retained_blueprint_path": "/blueprint.md",
    }


def test_review_guard_allows_reset_after_findings_report():
    report = {
        "result": {
            "code": "workflow/review_findings",
            "events": [{"code": "workflow/review_findings"}],
            "requirements": {"review": {"status": "rejected"}},
        }
    }
    assert ds._response_satisfies_review(report)


def test_session_accepts_restarted_mcp_proxy_connections(tmp_path):
    """Codex clients may overlap while refreshing MCP tools."""

    child = _script(tmp_path / "server.py", FAKE_SERVER)
    session = ds.DesktopStdioSession(
        [sys.executable, str(child)],
        root=tmp_path / "session",
    ).start()
    proxies = []
    try:
        for request_id in (1, 2):
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
            proxies.append(proxy)
            assert proxy.stdin is not None and proxy.stdout is not None
            proxy.stdin.write(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "method": "initialize",
                        "params": {},
                    }
                )
                + "\n"
            )
            proxy.stdin.flush()

        for request_id, proxy in zip((1, 2), proxies):
            assert proxy.stdout is not None
            ready, _, _ = select.select([proxy.stdout], [], [], 5)
            assert ready, f"proxy {request_id} did not receive a response"
            response = json.loads(proxy.stdout.readline())
            assert response["id"] == request_id

        for proxy in proxies:
            assert proxy.stdin is not None
            proxy.stdin.close()
            assert proxy.wait(timeout=10) == 0
    finally:
        for proxy in proxies:
            if proxy.poll() is None:
                proxy.kill()
                proxy.wait()
        session.cleanup()


def test_proxy_timeout_fault_allows_followup_and_suppresses_late_response(tmp_path):
    child = _script(tmp_path / "timeout-server.py", TIMEOUT_SERVER)
    session = ds.DesktopStdioSession(
        [sys.executable, str(child)],
        root=tmp_path / "session",
        request_timeout_faults={"build_data_product": {"after_ms": 50, "once": True}},
    ).start()
    proxy = subprocess.Popen(
        [sys.executable, str(ds.PROXY_MODULE), "--proxy", "--spec", str(session.root / "server-spec.json")],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        assert proxy.stdin is not None and proxy.stdout is not None
        proxy.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "build_data_product"}) + "\n")
        proxy.stdin.flush()
        timeout = json.loads(proxy.stdout.readline())
        assert timeout["id"] == 1
        assert timeout["error"]["code"] == -32098
        assert timeout["error"]["message"] == "client deadline exceeded"
        assert timeout["error"]["data"]["method"] == "build_data_product"
        assert timeout["error"]["data"]["timeout_ms"] == 50
        assert timeout["error"]["data"]["elapsed_ms"] >= 50

        proxy.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 2, "method": "inspect_run"}) + "\n")
        proxy.stdin.flush()
        inspect = json.loads(proxy.stdout.readline())
        assert inspect["id"] == 2
        assert inspect["result"]["duplicate_builds"] == 0
        proxy.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 3, "method": "build_data_product"}) + "\n")
        proxy.stdin.flush()
        second_build = json.loads(proxy.stdout.readline())
        assert second_build["id"] == 3
        assert "error" not in second_build
        proxy.stdin.close()
        assert proxy.wait(timeout=10) == 0

        records = [json.loads(line) for line in session.trace_path.read_text().splitlines()]
        assert any(
            record.get("synthetic") and record["message"].get("id") == 1
            for record in records
        )
        assert any(
            record.get("late") and not record["forwarded"] and record["message"].get("id") == 1
            for record in records
        )
        assert not any(
            record.get("late") and record["message"].get("id") == 1
            for record in records
            if record.get("forwarded")
        )
    finally:
        if proxy.poll() is None:
            proxy.kill()
            proxy.wait()
        session.cleanup()


def test_proxy_timeout_fault_targets_mcp_tool_and_workflow(tmp_path):
    child = _script(tmp_path / "timeout-server.py", TIMEOUT_SERVER)
    session = ds.DesktopStdioSession(
        [sys.executable, str(child)],
        root=tmp_path / "session",
        request_timeout_faults={
            "build_data_product": {
                "after_ms": 50,
                "once": True,
                "workflow": "target-workflow",
            }
        },
    ).start()
    proxy = subprocess.Popen(
        [sys.executable, str(ds.PROXY_MODULE), "--proxy", "--spec", str(session.root / "server-spec.json")],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        assert proxy.stdin is not None and proxy.stdout is not None
        unrelated = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "build_data_product", "arguments": {"workflow": "other-workflow"}},
        }
        proxy.stdin.write(json.dumps(unrelated) + "\n")
        proxy.stdin.flush()
        response = json.loads(proxy.stdout.readline())
        assert response["id"] == 1
        assert "error" not in response

        targeted = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "build_data_product", "arguments": {"workflow": "target-workflow"}},
        }
        proxy.stdin.write(json.dumps(targeted) + "\n")
        proxy.stdin.flush()
        timeout = json.loads(proxy.stdout.readline())
        assert timeout["id"] == 2
        assert timeout["error"]["code"] == -32098
        assert timeout["error"]["data"]["method"] == "build_data_product"
        proxy.stdin.close()
        assert proxy.wait(timeout=10) == 0
    finally:
        if proxy.poll() is None:
            proxy.kill()
            proxy.wait()
        session.cleanup()


def test_timeout_fault_rejects_duplicate_pending_ids_and_ignores_notifications(tmp_path):
    child = _script(tmp_path / "timeout-server.py", TIMEOUT_SERVER)
    session = ds.DesktopStdioSession(
        [sys.executable, str(child)],
        root=tmp_path / "session",
        request_timeout_faults={"build_data_product": {"after_ms": 40}},
    ).start()
    proxy = subprocess.Popen(
        [sys.executable, str(ds.PROXY_MODULE), "--proxy", "--spec", str(session.root / "server-spec.json")],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        assert proxy.stdin is not None and proxy.stdout is not None
        request = {"jsonrpc": "2.0", "id": "same", "method": "build_data_product"}
        proxy.stdin.write(json.dumps(request) + "\n")
        proxy.stdin.flush()
        assert json.loads(proxy.stdout.readline())["error"]["code"] == -32098
        proxy.stdin.write(json.dumps(request) + "\n")
        proxy.stdin.flush()
        assert json.loads(proxy.stdout.readline())["error"]["code"] == -32600
        proxy.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "build_data_product"}) + "\n")
        proxy.stdin.flush()
        time.sleep(0.08)
        assert proxy.stdin is not None
        proxy.stdin.close()
        assert proxy.wait(timeout=10) == 0
        records = [json.loads(line) for line in session.trace_path.read_text().splitlines()]
        assert not any(record.get("timeout_fault") and record["message"].get("id") is None for record in records)
    finally:
        if proxy.poll() is None:
            proxy.kill()
            proxy.wait()
        session.cleanup()


def test_one_shot_deadline_survives_a_notification_and_a_duplicate_id(tmp_path):
    """A request that cannot carry a deadline must not spend the ``once`` budget.

    A notification has no id and a duplicate is rejected without reaching the
    child, so neither can be timed out. If either consumed the budget, the one
    deadline the scenario depends on would silently never fire and the checker
    would report a missing timeout rather than the reason there was none.
    """
    child = _script(tmp_path / "timeout-server.py", TIMEOUT_SERVER)
    session = ds.DesktopStdioSession(
        [sys.executable, str(child)],
        root=tmp_path / "session",
        request_timeout_faults={"build_data_product": {"after_ms": 40, "once": True}},
    ).start()
    proxy = subprocess.Popen(
        [sys.executable, str(ds.PROXY_MODULE), "--proxy", "--spec", str(session.root / "server-spec.json")],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        assert proxy.stdin is not None and proxy.stdout is not None
        # A notification for the faulted operation: no id, so no deadline.
        proxy.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "build_data_product"}) + "\n")
        proxy.stdin.flush()
        time.sleep(0.12)
        # The real request still gets the one configured deadline.
        proxy.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "build_data_product"}) + "\n")
        proxy.stdin.flush()
        first = json.loads(proxy.stdout.readline())
        while "error" not in first:  # skip the notification's echoed reply
            first = json.loads(proxy.stdout.readline())
        assert first["id"] == 1
        assert first["error"]["code"] == -32098
        # ...and it is spent: the next build is forwarded untouched.
        proxy.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 2, "method": "build_data_product"}) + "\n")
        proxy.stdin.flush()
        second = json.loads(proxy.stdout.readline())
        while second.get("id") != 2:
            second = json.loads(proxy.stdout.readline())
        assert "error" not in second
        proxy.stdin.close()
        assert proxy.wait(timeout=10) == 0
        records = [json.loads(line) for line in session.trace_path.read_text().splitlines()]
        deadlines = [record for record in records if record.get("timeout_fault")]
        assert len(deadlines) == 1
        assert deadlines[0]["message"]["id"] == 1
    finally:
        if proxy.poll() is None:
            proxy.kill()
            proxy.wait()
        session.cleanup()


def test_duplicate_id_is_rejected_after_the_one_shot_deadline_is_spent(tmp_path):
    """Duplicate detection must not depend on the fault budget still existing.

    The first request is already pending and timed out, so the child's eventual
    reply is suppressed. If the duplicate were only screened while a deadline
    was still available, it would be forwarded, and its reply would be consumed
    as the suppressed late response — leaving the client with no answer at all.
    """
    child = _script(tmp_path / "timeout-server.py", TIMEOUT_SERVER)
    session = ds.DesktopStdioSession(
        [sys.executable, str(child)],
        root=tmp_path / "session",
        request_timeout_faults={"build_data_product": {"after_ms": 40, "once": True}},
    ).start()
    proxy = subprocess.Popen(
        [sys.executable, str(ds.PROXY_MODULE), "--proxy", "--spec", str(session.root / "server-spec.json")],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        assert proxy.stdin is not None and proxy.stdout is not None
        request = {"jsonrpc": "2.0", "id": "same", "method": "build_data_product"}
        proxy.stdin.write(json.dumps(request) + "\n")
        proxy.stdin.flush()
        assert json.loads(proxy.stdout.readline())["error"]["code"] == -32098
        # The budget is spent, but the duplicate must still be rejected by the
        # proxy rather than forwarded to the child.
        proxy.stdin.write(json.dumps(request) + "\n")
        proxy.stdin.flush()
        assert json.loads(proxy.stdout.readline())["error"]["code"] == -32600
        proxy.stdin.close()
        assert proxy.wait(timeout=10) == 0
        records = [json.loads(line) for line in session.trace_path.read_text().splitlines()]
        assert len([r for r in records if r.get("timeout_fault")]) == 1
    finally:
        if proxy.poll() is None:
            proxy.kill()
            proxy.wait()
        session.cleanup()


def test_proxy_server_environment_is_allowlisted_and_secret_keys_removed(tmp_path):
    child = _script(
        tmp_path / "env-server.py",
        "import json, os, sys\n"
        "print(json.dumps({'env': dict(os.environ)}), flush=True)\n"
        "for _line in sys.stdin: pass\n",
    )
    session = ds.DesktopStdioSession(
        [sys.executable, str(child)],
        root=tmp_path / "session",
        server_env={
            "NXD_DESKTOP_PYTHON": "/tmp/eval-python",
            "EVAL_MARKER": "allowed",
            "ANTHROPIC_API_KEY": "must-not-pass",
            "NXD_DESKTOP_TRUSTED_CREDENTIAL_ENVS": "api-source=NXD_EVAL_SOURCE_TOKEN",
            "NXD_EVAL_SOURCE_TOKEN": "trusted-source-token",
        },
    ).start()
    old = os.environ.get("ANTHROPIC_API_KEY")
    os.environ["ANTHROPIC_API_KEY"] = "runner-secret"
    proxy = subprocess.Popen(
        [sys.executable, str(ds.PROXY_MODULE), "--proxy", "--spec", str(session.root / "server-spec.json")],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        assert proxy.stdout is not None
        child_env = json.loads(proxy.stdout.readline())["env"]
        assert child_env["NXD_DESKTOP_PYTHON"] == "/tmp/eval-python"
        assert child_env["EVAL_MARKER"] == "allowed"
        assert "ANTHROPIC_API_KEY" not in child_env
        assert child_env["NXD_EVAL_SOURCE_TOKEN"] == "trusted-source-token"
        assert (
            child_env["NXD_DESKTOP_TRUSTED_CREDENTIAL_ENVS"]
            == "api-source=NXD_EVAL_SOURCE_TOKEN"
        )
        spec_text = (session.root / "server-spec.json").read_text()
        assert "trusted-source-token" not in spec_text
        assert "NXD_EVAL_SOURCE_TOKEN" not in spec_text
        assert "NXD_DESKTOP_TRUSTED_CREDENTIAL_ENVS" not in spec_text
        if proxy.stdin is not None:
            proxy.stdin.close()
        proxy.wait(timeout=10)
    finally:
        if old is None:
            os.environ.pop("ANTHROPIC_API_KEY", None)
        else:
            os.environ["ANTHROPIC_API_KEY"] = old
        if proxy.poll() is None:
            proxy.kill()
            proxy.wait()
        session.cleanup()


@pytest.mark.parametrize(
    "mapping",
    [
        "api-source=literal-secret",
        "warehouse=sk_live_abc123",
        "api-source=OTHER_SOURCE_TOKEN",
        "warehouse=WAREHOUSE_TOKEN,other=ABSENT_TOKEN",
    ],
)
def test_proxy_drops_invalid_or_unavailable_trusted_credential_mapping(
    tmp_path, mapping
):
    child = _script(
        tmp_path / "env-server.py",
        "import json, os, sys\n"
        "print(json.dumps({'env': dict(os.environ)}), flush=True)\n"
        "for _line in sys.stdin: pass\n",
    )
    session = ds.DesktopStdioSession(
        [sys.executable, str(child)],
        root=tmp_path / "session",
        server_env={
            "NXD_DESKTOP_TRUSTED_CREDENTIAL_ENVS": mapping,
            "WAREHOUSE_TOKEN": "test-only-placeholder",
            "OTHER_SOURCE_TOKEN": "test-only-placeholder",
        },
    ).start()
    proxy = subprocess.Popen(
        [sys.executable, str(ds.PROXY_MODULE), "--proxy", "--spec", str(session.root / "server-spec.json")],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        assert proxy.stdout is not None
        child_env = json.loads(proxy.stdout.readline())["env"]
        if mapping.startswith("warehouse=WAREHOUSE_TOKEN"):
            assert (
                child_env["NXD_DESKTOP_TRUSTED_CREDENTIAL_ENVS"]
                == "warehouse=WAREHOUSE_TOKEN"
            )
            assert child_env["WAREHOUSE_TOKEN"] == "test-only-placeholder"
        else:
            assert "NXD_DESKTOP_TRUSTED_CREDENTIAL_ENVS" not in child_env
            assert "WAREHOUSE_TOKEN" not in child_env
        assert "OTHER_SOURCE_TOKEN" not in child_env
        if proxy.stdin is not None:
            proxy.stdin.close()
        assert proxy.wait(timeout=10) == 0
    finally:
        if proxy.poll() is None:
            proxy.kill()
            proxy.wait()
        session.cleanup()


def test_proxy_rejects_trusted_credential_mapping_limits():
    available = {f"TOKEN_{index}" for index in range(17)}
    exact_entries = ",".join(
        f"service{index}=TOKEN_{index}" for index in range(16)
    )
    assert len(ds._safe_trusted_credential_mappings(exact_entries, available)) == 16
    too_many = ",".join(
        f"service{index}=TOKEN_{index}" for index in range(17)
    )
    assert ds._safe_trusted_credential_mappings(too_many, available) == []
    assert (
        ds._safe_trusted_credential_mappings(
            "service=TOKEN_0,service=TOKEN_1", available
        )
        == []
    )
    assert (
        ds._safe_trusted_credential_mappings(
            "service=TOKEN_0,malformed-entry", available
        )
        == []
    )
    assert (
        ds._safe_trusted_credential_mappings(
            "evil=NXD_EVAL_SOURCE_TOKEN", {"NXD_EVAL_SOURCE_TOKEN"}
        )
        == []
    )

    exact_length = f"{'s' * 4088}=TOKEN_0"
    assert len(exact_length) == 4096
    assert ds._safe_trusted_credential_mappings(exact_length, available)
    too_long = f"{'s' * 4089}=TOKEN_0"
    assert len(too_long) == 4097
    assert ds._safe_trusted_credential_mappings(too_long, available) == []


def test_claude_stdio_agent_environment_drops_provider_credentials(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "runner-secret")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "oauth-secret")
    env = eb.ClaudeBackend._agent_env(
        {"NXD_SYNTHETIC_EVALUATION_PROFILE": "/tmp/profile.json"},
        None,
        credential_isolation=True,
    )
    assert env["NXD_SYNTHETIC_EVALUATION_PROFILE"] == "/tmp/profile.json"
    assert "ANTHROPIC_API_KEY" not in env
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in env


def test_multi_turn_claude_agent_environment_drops_reserved_source_credentials(
    monkeypatch,
):
    monkeypatch.setenv("NXD_EVAL_SOURCE_TOKEN", "source-only-in-test")
    monkeypatch.setenv(
        "NXD_DESKTOP_TRUSTED_CREDENTIAL_ENVS", "api-source=NXD_EVAL_SOURCE_TOKEN"
    )
    env = eb.ClaudeBackend._agent_env(
        None,
        None,
        credential_isolation=True,
    )
    assert "NXD_EVAL_SOURCE_TOKEN" not in env
    assert "NXD_DESKTOP_TRUSTED_CREDENTIAL_ENVS" not in env


def test_claude_backend_passes_private_mcp_flags_and_isolated_tools(tmp_path):
    args_file = tmp_path / "args.json"
    claude = _script(tmp_path / "claude", FAKE_CLAUDE)
    session = ds.DesktopStdioSession(
        [sys.executable, "/tmp/fake-server.py"], root=tmp_path / "session"
    ).start()
    try:
        ok, trace, metrics = eb.ClaudeBackend().run_agent(
            tmp_path,
            "use the MCP server",
            "sonnet",
            10,
            executable=str(claude),
            env_overrides={"ARGS_FILE": str(args_file)},
            stdio_session=session,
            allowed_tools="Bash,Read,mcp__other__danger",
        )
        assert ok, metrics
        assert "[tool_use:mcp__nxd-desktop__build_data_product]" in trace
        args = json.loads(args_file.read_text())
        assert "--mcp-config" in args
        assert "--strict-mcp-config" in args
        assert args[args.index("--mcp-config") + 1] == str(session.config_path)
        allowed = args[args.index("--allowedTools") + 1]
        assert "mcp__nxd-desktop__*" in allowed
        assert "mcp__other__danger" not in allowed
        assert metrics["setup_result"]["status"] == "passed"
        assert metrics["agent_result"]["status"] == "passed"
        assert metrics["server_result"]["status"] in {"unknown", "not_started"}
    finally:
        session.cleanup()


def test_isolated_mcp_allowlist_drops_other_namespaces():
    assert eb.isolated_mcp_allowed_tools(
        "Bash,mcp__nxd-desktop__build_data_product,mcp__other__secret"
    ) == "Bash,mcp__nxd-desktop__*"
    default = eb.isolated_mcp_allowed_tools(None)
    assert "Skill" in default.split(",")
    assert "mcp__nxd-desktop__*" in default.split(",")


def test_session_cleanup_kills_attached_process_group(tmp_path):
    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        start_new_session=True,
    )
    session = ds.DesktopStdioSession(
        [sys.executable, "/tmp/fake-server.py"], root=tmp_path / "session"
    ).start()
    session.attach_process(child)
    session.cleanup()
    assert child.poll() is not None


def test_session_context_always_cleans_up_after_agent_exception(tmp_path, monkeypatch):
    session = ds.DesktopStdioSession(
        [sys.executable, "-c", "pass"], root=tmp_path / "session"
    )
    session._root = tmp_path / "session"
    session._root.mkdir()
    monkeypatch.setattr(session, "start", lambda: session)

    with pytest.raises(RuntimeError, match="incomplete agent"):
        with session:
            raise RuntimeError("incomplete agent")

    assert session._closed is True


def test_session_cleanup_kills_proxy_server_child(tmp_path):
    child = _script(tmp_path / "holding-server.py", HOLDING_SERVER)
    pid_file = tmp_path / "server.pid"
    session = ds.DesktopStdioSession(
        [sys.executable, str(child)],
        server_env={"PID_FILE": str(pid_file)},
        root=tmp_path / "session",
    ).start()
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
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        deadline = time.monotonic() + 5
        while not pid_file.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert pid_file.exists(), "proxy did not start the server child"
        server_pid = int(pid_file.read_text())
        session.cleanup()
        proxy.wait(timeout=5)
        with pytest.raises(ProcessLookupError):
            os.kill(server_pid, 0)
    finally:
        if proxy.poll() is None:
            proxy.kill()
            proxy.wait()
        session.cleanup()


@pytest.mark.parametrize(
    "payload",
    [
        {"password": "hunter2", "nested": {"access_token": "abc"}},
        {"text": "Bearer abc.def", "url": "https://u:p@example.test/?token=xyz"},
        {"dsn": "postgres://svc:S3cr3tPw@db.internal:5432/prod"},
        {"text": "PGPASSWORD=hunter2 psql --host db"},
        {"text": "aws_secret_access_key is AKIAIOSFODNN7EXAMPLE"},
    ],
)
def test_redaction_is_recursive_and_fail_closed(payload):
    value = json.dumps(ds.redact_json_rpc(payload))
    assert all(secret not in value for secret in ("hunter2", "abc", "xyz", "u:p"))
    assert all(secret not in value for secret in ("S3cr3tPw", "AKIAIOSFODNN7EXAMPLE"))
    assert ds.REDACTED in value


def test_nex_agent_facing_payload_redacts_source_credential(tmp_path):
    secret = "synthetic-source-credential-for-redaction"
    session = ds.DesktopStdioSession(
        [sys.executable, "-c", "pass"],
        nex_mode=True,
        server_env={
            "NXD_EVAL_SOURCE_TOKEN": secret,
            "NXD_DESKTOP_TRUSTED_CREDENTIAL_ENVS": "api-source=NXD_EVAL_SOURCE_TOKEN",
        },
    )
    message = {
        "jsonrpc": "2.0",
        "id": 12,
        "result": {
            "content": [{"type": "text", "text": f"server reflected {secret}"}],
            "rows": [{secret: "row value"}],
            "profile": {
                "credential_env": "NXD_EVAL_SOURCE_TOKEN",
                "auth_type": "bearer",
            },
        },
    }
    safe_message = session._redact_nex_payload(message)
    redacted = json.dumps(safe_message)
    assert secret not in redacted
    assert ds.REDACTED in redacted
    assert ds.REDACTED in safe_message["result"]["rows"][0]
    assert safe_message["result"]["profile"] == {
        "credential_env": "NXD_EVAL_SOURCE_TOKEN",
        "auth_type": "bearer",
    }

    redacted_text, leaked = session.redact_nex_text(
        f"malformed server response: {secret}"
    )
    assert leaked is True
    assert secret not in redacted_text
    assert session.result_metrics()["nex_bridge_secret_leak"] is True
    _trace, evidence_error = session.nex_evidence()
    assert "trusted source credential" in evidence_error


_NEX_READER_TOKEN = "synthNEX7q2Zk9pLwV"
_NEX_READER_ROOT = "/nex-reader-capture/root"


def _nex_reader_session(files, directories=()):
    """Install an immutable review snapshot directly; no socket is started."""

    session = ds.DesktopStdioSession(
        [sys.executable, "-c", "pass"],
        nex_mode=True,
        server_env={
            "NXD_EVAL_SOURCE_TOKEN": _NEX_READER_TOKEN,
            "NXD_DESKTOP_TRUSTED_CREDENTIAL_ENVS": "api-source=NXD_EVAL_SOURCE_TOKEN",
        },
    )
    snapshot = {f"{_NEX_READER_ROOT}/{name}": data for name, data in files.items()}
    dirs = {_NEX_READER_ROOT, *(f"{_NEX_READER_ROOT}/{name}" for name in directories)}
    session._nex_review_snapshot = snapshot
    session._nex_review_directories = dirs
    session._nex_review_aliases = {
        session._nex_path_key(path): path for path in [*snapshot, *dirs]
    }
    return session


def _nex_read(session, path, operation="read", **bounds):
    return session._nex_reader_response({
        "method": "tools/call",
        "params": {"arguments": {"path": path, "operation": operation, **bounds}},
    })


def _nex_reader_text(result):
    assert result["isError"] is False
    (block,) = result["content"]
    return block["text"]


def test_nex_reader_returns_exactly_max_lines_without_marker():
    content = "".join(f"line {index}\n" for index in range(500))
    session = _nex_reader_session({"f.txt": content.encode()})

    text = _nex_reader_text(_nex_read(session, f"{_NEX_READER_ROOT}/f.txt"))

    assert text == content
    assert ds._REVIEW_READER_TRUNCATION_MARKER not in text
    assert session._nex_bridge_secret_leak is False


def test_nex_reader_marks_line_truncation_within_byte_cap():
    lines = [f"line {index}\n" for index in range(501)]
    session = _nex_reader_session({"f.txt": "".join(lines).encode()})

    text = _nex_reader_text(_nex_read(session, f"{_NEX_READER_ROOT}/f.txt"))

    assert text == "".join(lines[:500]) + ds._REVIEW_READER_TRUNCATION_MARKER
    assert len(text.encode("utf-8")) <= ds._REVIEW_READER_MAX_BYTES
    assert session._nex_bridge_secret_leak is False


def test_nex_reader_redacts_before_utf8_safe_byte_clip_and_flags_leak():
    # Raw, the byte cutoff would fall inside the token; redacted first, it
    # falls inside the multibyte character that follows the placeholder.
    content = "é" * 10 + " " + _NEX_READER_TOKEN + " " + "é" * 30 + "\n"
    session = _nex_reader_session({"f.txt": content.encode("utf-8")})
    max_bytes = 60

    text = _nex_reader_text(
        _nex_read(session, f"{_NEX_READER_ROOT}/f.txt", max_bytes=max_bytes)
    )

    encoded = text.encode("utf-8")
    assert len(encoded) <= max_bytes
    assert encoded.decode("utf-8") == text and "�" not in text
    assert text.endswith(ds._REVIEW_READER_TRUNCATION_MARKER)
    assert text == "é" * 10 + " " + ds.REDACTED + " " + ds._REVIEW_READER_TRUNCATION_MARKER
    assert _NEX_READER_TOKEN not in text
    assert _NEX_READER_TOKEN[:6] not in text
    assert session._nex_bridge_secret_leak is True


def _nex_list_entries(text, *, truncated):
    marker = ds._REVIEW_READER_TRUNCATION_MARKER
    if truncated:
        assert text.endswith(marker)
        text = text[: -len(marker)]
    else:
        assert marker not in text
    return json.loads(text)


def test_nex_reader_list_truncates_whole_entries_by_lines_and_bytes():
    files = {name: b"x" for name in ("a.txt", "b.txt", "d.txt", "e.txt")}
    session = _nex_reader_session(files, directories=("c",))
    expected = [
        {"kind": "file", "name": "a.txt"},
        {"kind": "file", "name": "b.txt"},
        {"kind": "directory", "name": "c"},
        {"kind": "file", "name": "d.txt"},
        {"kind": "file", "name": "e.txt"},
    ]

    full = _nex_reader_text(_nex_read(session, _NEX_READER_ROOT, "list"))
    assert _nex_list_entries(full, truncated=False) == expected

    by_lines = _nex_reader_text(_nex_read(session, _NEX_READER_ROOT, "list", max_lines=2))
    assert _nex_list_entries(by_lines, truncated=True) == expected[:2]

    # One byte short of three entries plus the marker: exactly two survive.
    three_entries = json.dumps(expected[:3], sort_keys=True)
    max_bytes = len(three_entries) + len(ds._REVIEW_READER_TRUNCATION_MARKER) - 1
    by_bytes = _nex_reader_text(
        _nex_read(session, _NEX_READER_ROOT, "list", max_bytes=max_bytes)
    )
    assert len(by_bytes.encode("utf-8")) <= max_bytes
    assert _nex_list_entries(by_bytes, truncated=True) == expected[:2]
    assert session._nex_bridge_secret_leak is False


def test_nex_reader_list_redacts_names_inside_valid_json():
    session = _nex_reader_session({
        "token=abc": b"x",
        f"token={_NEX_READER_TOKEN}": b"x",
        "plain.txt": b"x",
    })

    text = _nex_reader_text(_nex_read(session, _NEX_READER_ROOT, "list"))

    entries = _nex_list_entries(text, truncated=False)
    assert [entry["name"] for entry in entries] == [
        "plain.txt", f"token={ds.REDACTED}", f"token={ds.REDACTED}",
    ]
    assert {entry["kind"] for entry in entries} == {"file"}
    assert "abc" not in text and _NEX_READER_TOKEN not in text
    assert session._nex_bridge_secret_leak is True


def test_nex_reader_errors_when_marker_cannot_fit():
    session = _nex_reader_session({"f.txt": b"x" * 64}, directories=("sub",))
    too_small = len(ds._REVIEW_READER_TRUNCATION_MARKER) - 1

    read = _nex_read(session, f"{_NEX_READER_ROOT}/f.txt", max_bytes=too_small)
    listed = _nex_read(session, _NEX_READER_ROOT, "list", max_lines=1, max_bytes=too_small)

    assert read["isError"] is True
    assert listed["isError"] is True


def test_nex_result_metrics_expose_only_per_workflow_review_return_status():
    session = ds.DesktopStdioSession(
        [sys.executable, "-c", "pass"],
        nex_mode=True,
    )
    session._nex_children_by_workflow.update({
        "nex890-positive": 1,
        "nex890-401": 2,
    })
    session._nex_child_returned_by_workflow.update({
        "nex890-positive": True,
    })

    assert session.result_metrics()["nex_review_children"] == {
        "nex890-positive": {"count": 1, "returned": True},
        "nex890-401": {"count": 2, "returned": False},
        "nex890-403": {"count": 0, "returned": False},
        "nex890-404": {"count": 0, "returned": False},
    }


SILENT_SERVER = r"""
import sys
for _raw in sys.stdin:
    pass
"""

UNMATCHED_SERVER = r"""
import json, sys
print(json.dumps({"jsonrpc": "2.0", "id": 9999, "result": {}}), flush=True)
print("supervisor banner", flush=True)
for _raw in sys.stdin:
    pass
"""


def _nex_bridge_harness(tmp_path, server_body):
    """Serve one NEX bridge connection over a socketpair; proxy auth is skipped."""
    root = tmp_path / "bridge-root"
    root.mkdir()
    server = _script(tmp_path / "server.py", server_body)
    session = ds.DesktopStdioSession(
        [sys.executable, str(server)], nex_mode=True, shutdown_timeout_s=2.0,
    )
    session._root = root  # the bridge publishes its process result here
    proxy_side, bridge_side = socket.socketpair()
    proxy_side.settimeout(5.0)
    worker = threading.Thread(
        target=session._serve_connection, args=(bridge_side,), daemon=True
    )
    with session._bridge_state_lock:
        session._bridge_connections.add(bridge_side)
        session._bridge_workers.add(worker)
    worker.start()
    return session, proxy_side


def _nex_send(proxy_side, message):
    proxy_side.sendall(json.dumps(message).encode() + b"\n")


def _nex_diagnostics(session):
    return session.result_metrics()["nex_bridge_diagnostics"]


def _wait_until(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, "bridge diagnostics did not settle"
        time.sleep(0.02)


def _nex_bridge_finish(session, proxy_side):
    proxy_side.shutdown(socket.SHUT_WR)
    return session.finish_nex_cell()


def test_nex_diagnostics_show_unanswered_initialize_at_exit_and_after_drain(tmp_path):
    session, proxy_side = _nex_bridge_harness(tmp_path, SILENT_SERVER)
    try:
        _nex_send(proxy_side, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        _wait_until(lambda: _nex_diagnostics(session)["forwarded_requests"] == 1)
        session.record_agent(status="passed")
        _trace, evidence_error = _nex_bridge_finish(session, proxy_side)
    finally:
        proxy_side.close()
        session.cleanup()

    diagnostics = _nex_diagnostics(session)
    for snapshot in (diagnostics["agent_exit"], diagnostics["after_drain"]):
        assert snapshot["pending_count"] == 1
        assert snapshot["pending_methods"] == {"initialize": 1}
        assert isinstance(snapshot["oldest_pending_age_s"], float)
    assert diagnostics["agent_exit"]["supervisor_stdout_eof"] is False
    assert diagnostics["after_drain"]["supervisor_stdout_eof"] is True
    assert diagnostics["supervisor_shutdown_requested_at_eof"] is True
    assert isinstance(diagnostics["supervisor_exit_code"], int)
    assert diagnostics["matched_responses"] == 0
    assert evidence_error is not None


def test_nex_diagnostics_pair_answered_request_without_changing_evidence(tmp_path):
    session, proxy_side = _nex_bridge_harness(tmp_path, FAKE_SERVER)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    session.nex_workspace = workspace.resolve()
    session._prepare_nex_security_files()
    # The harness skips proxy authentication and runs no review children, so
    # seed the counters a passing cell would have produced. The trace itself is
    # only what the bridge records.
    with session._bridge_state_lock:
        session._nex_connection_count = 1
        for workflow in ds._NEX_WORKFLOWS:
            session._nex_children_by_workflow[workflow] = 1
            session._nex_child_returned_by_workflow[workflow] = True
    try:
        _nex_send(proxy_side, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        _wait_until(lambda: _nex_diagnostics(session)["matched_responses"] == 1)
        reply = json.loads(proxy_side.makefile("rb").readline())
        session.record_agent(status="passed")
        trace, evidence_error = _nex_bridge_finish(session, proxy_side)
    finally:
        proxy_side.close()
        session.cleanup()

    assert reply["id"] == 1 and reply["result"]["echo"] == "initialize"
    assert evidence_error is None
    diagnostics = _nex_diagnostics(session)
    assert diagnostics["forwarded_requests"] == 1
    assert diagnostics["unmatched_responses"] == 0
    for snapshot in (diagnostics["agent_exit"], diagnostics["after_drain"]):
        assert snapshot["pending_count"] == 0
        assert snapshot["pending_methods"] == {}
        assert snapshot["oldest_pending_age_s"] is None
    assert diagnostics["after_drain"]["quiesced"] is True
    # Diagnostics are read-only with respect to the fail-closed verdict and trace.
    assert session.nex_evidence() == (trace, None)
    assert {record["direction"] for record in trace} == {"request", "response"}
    assert "pending" not in json.dumps(trace)


def test_nex_diagnostics_freeze_whole_payload_when_handler_survives_teardown(tmp_path):
    root = tmp_path / "bridge-root"
    root.mkdir()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    server = _script(tmp_path / "server.py", SILENT_SERVER)
    session = ds.DesktopStdioSession(
        [sys.executable, str(server)], nex_mode=True, shutdown_timeout_s=0.2,
    )
    session._root = root
    session.nex_workspace = workspace.resolve()
    session._prepare_nex_security_files()
    # Seed a passing cell so the only invalidation is the surviving handler.
    with session._bridge_state_lock:
        session._nex_connection_count = 1
        for workflow in ds._NEX_WORKFLOWS:
            session._nex_children_by_workflow[workflow] = 1
            session._nex_child_returned_by_workflow[workflow] = True
    release = threading.Event()

    def blocked_handler():
        # Outlives both bounded joins, then records one late supervisor line.
        release.wait(timeout=5.0)
        session._nex_note_supervisor_line({"jsonrpc": "2.0", "id": 1, "result": {}}, False)

    handler = threading.Thread(target=blocked_handler, daemon=True)
    with session._bridge_state_lock:
        session._bridge_workers.add(handler)
    handler.start()
    try:
        session.record_agent(status="passed")
        _trace, evidence_error = session.finish_nex_cell()
        frozen = _nex_diagnostics(session)
        release.set()
        handler.join(timeout=5.0)
        assert not handler.is_alive()
    finally:
        release.set()
        session.cleanup()

    assert evidence_error == "NEX-890 bridge handler did not drain after Claude exited"
    assert frozen["after_drain"]["live_handlers"] == 1
    assert frozen["after_drain"]["quiesced"] is False
    assert frozen["unmatched_responses"] == 0
    # The late handler did mutate live state, but not the published payload.
    with session._bridge_state_lock:
        assert session._nex_bridge_counts["unmatched_responses"] == 1
    assert _nex_diagnostics(session) == frozen
    assert session.nex_evidence()[1] == evidence_error


def test_nex_diagnostics_count_unmatched_and_non_json_supervisor_lines(tmp_path):
    session, proxy_side = _nex_bridge_harness(tmp_path, UNMATCHED_SERVER)
    try:
        _wait_until(
            lambda: _nex_diagnostics(session)["unmatched_responses"] == 1
            and _nex_diagnostics(session)["non_json_response_lines"] == 1
        )
        session.record_agent(status="passed")
        _nex_bridge_finish(session, proxy_side)
    finally:
        proxy_side.close()
        session.cleanup()

    diagnostics = _nex_diagnostics(session)
    assert diagnostics["forwarded_requests"] == 0
    assert diagnostics["matched_responses"] == 0
    assert diagnostics["unmatched_responses"] == 1
    assert diagnostics["non_json_response_lines"] == 1


def test_nex_diagnostics_label_unknown_methods_other_without_payload_details(tmp_path):
    request_id = "req-diagnostic-id-4242"
    private_path = str(tmp_path / "private-params-path")
    session, proxy_side = _nex_bridge_harness(tmp_path, SILENT_SERVER)
    try:
        _nex_send(proxy_side, {
            "jsonrpc": "2.0", "id": request_id, "method": "custom/private-method",
            "params": {"path": private_path},
        })
        _wait_until(lambda: _nex_diagnostics(session)["forwarded_requests"] == 1)
        supervisor_pid = session._server_process.pid
        session.record_agent(status="passed")
        _nex_bridge_finish(session, proxy_side)
    finally:
        proxy_side.close()
        session.cleanup()

    metrics = session.result_metrics()
    diagnostics = metrics["nex_bridge_diagnostics"]
    assert diagnostics["agent_exit"]["pending_methods"] == {"other": 1}
    assert diagnostics["after_drain"]["pending_methods"] == {"other": 1}
    serialized = json.dumps(diagnostics)
    for forbidden in (
        request_id, "custom/private-method", "private-params-path",
        private_path, str(tmp_path), str(supervisor_pid),
    ):
        assert forbidden not in serialized


def test_nex_result_payload_decodes_only_one_unambiguous_json_text_block():
    payload = {"archive_path": "/workspace/exports/product.zip", "generation": 7}
    message = {
        "result": {
            "content": [{"type": "text", "text": json.dumps(payload)}],
        }
    }
    assert ds._nex_result_payload(message) == payload
    assert ds._nex_result_payload({
        "result": {"content": [{"type": "text", "text": "not JSON: {}"}]}
    }) == {}
    assert ds._nex_result_payload({
        "result": {"content": [
            {"type": "text", "text": json.dumps(payload)},
            {"type": "text", "text": "{}"},
        ]}
    }) == {}
    assert ds._nex_result_payload({
        "result": {"content": [{"type": "text", "text": '{"generation":1,"generation":2}'}]}
    }) == {}
    assert ds._nex_result_payload({
        "result": {
            "structuredContent": payload,
            "content": [{"type": "text", "text": json.dumps(payload)}],
        }
    }) == {}


def _tool_results(*blocks):
    return {"type": "user", "message": {"content": list(blocks)}}


def test_nex_preflight_records_malformed_result_ids_and_only_redacted_bounded_text():
    session = ds.DesktopStdioSession(
        [sys.executable, "-c", "pass"], nex_mode=True, nex_preflight_mode=True
    )
    session.observe_claude_stream_event(_tool_results(
        {"type": "tool_result", "tool_use_id": 7, "is_error": True, "content": "x"},
        {
            "type": "tool_result", "tool_use_id": "long", "is_error": True,
            "content": [{"type": "text", "text": "y" * 2500}],
        },
        {
            "type": "tool_result", "tool_use_id": "redacted",
            "content": "api_key=" + "s" * 2100,
        },
    ))

    malformed, long, redacted = session.nex_preflight_events()
    assert malformed["id"] is None and malformed["malformed_id"] is True
    assert long["malformed_id"] is False and long["is_error"] is True
    assert long["content"] == "y" * 2000 and long["content_truncated"] is True
    # Truncation is measured after redaction shrinks the secret away.
    assert redacted["content"] == "api_key=<redacted>"
    assert redacted["content_truncated"] is False
    assert all("s" * 50 not in json.dumps(event) for event in session.nex_preflight_events())


def test_nex_preflight_distinguishes_absent_empty_and_malformed_permission_denials():
    session = ds.DesktopStdioSession(
        [sys.executable, "-c", "pass"], nex_mode=True, nex_preflight_mode=True
    )
    for event in (
        {"type": "result", "is_error": False},
        {"type": "result", "is_error": False, "permission_denials": []},
        {"type": "result", "is_error": False, "permission_denials": "bad"},
    ):
        session.observe_claude_stream_event(event)

    absent, empty, malformed = session.nex_preflight_events()
    assert (absent["permission_denials_present"], absent["permission_denials"]) == (False, None)
    assert (empty["permission_denials_present"], empty["permission_denials"]) == (True, [])
    assert (malformed["permission_denials_present"], malformed["permission_denials"]) == (True, "bad")


def test_regular_nex_stream_handling_is_unchanged_outside_preflight():
    session = ds.DesktopStdioSession([sys.executable, "-c", "pass"], nex_mode=True)
    session.observe_claude_stream_event({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": "u1", "name": "mcp__nxd-desktop__inspect_run", "input": {}},
    ]}})
    session.observe_claude_stream_event(_tool_results(
        {"type": "tool_result", "tool_use_id": 7, "is_error": True, "content": "x"},
        {"type": "tool_result", "tool_use_id": "u1", "content": "ok"},
    ))
    session.observe_claude_stream_event({"type": "result", "is_error": False})

    assert session.nex_preflight_events() == []
    assert session._nex_invalid_reason is None
    assert session._nex_stream_uses[0]["tool_result"] is True
    assert session._nex_stream_uses[0]["tool_result_success"] is True


def test_trace_writes_remain_parseable_under_concurrency(tmp_path):
    path = tmp_path / "trace.jsonl"
    payload = json.dumps({"text": "x" * 20_000}).encode()

    def write_records(direction: str) -> None:
        for _ in range(20):
            ds._trace_line(path, direction, payload)

    threads = [
        threading.Thread(target=write_records, args=(direction,))
        for direction in ("request", "response")
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    records = [json.loads(line) for line in path.read_text().splitlines()]
    assert len(records) == 40


def test_review_clear_accepts_requirement_satisfied_for_review():
    """Main's supervisor code still clears the review guard."""
    report = {
        "result": {
            "code": "workflow/requirement_satisfied",
            "requirement_id": "review",
        }
    }
    assert ds._response_satisfies_review(report)
    other = {"result": {"code": "workflow/requirement_satisfied", "requirement_id": "capture"}}
    assert not ds._response_satisfies_review(other)


def test_review_clear_accepts_review_satisfied_code():
    assert ds._response_satisfies_review({"result": {"code": "workflow/review_satisfied"}})


def _nex_stream_tool_use(session, *uses):
    session.observe_claude_stream_event({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": identifier, "name": f"mcp__nxd-desktop__{name}", "input": arguments}
        for identifier, name, arguments in uses
    ]}})


def _nex_call(request_id, name, arguments):
    return {
        "jsonrpc": "2.0", "id": request_id, "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }


def test_nex_identical_tool_uses_match_fifo():
    session = ds.DesktopStdioSession([sys.executable, "-c", "pass"], nex_mode=True)
    _nex_stream_tool_use(
        session,
        ("u1", "inspect_run", {"workflow": "w"}),
        ("u2", "inspect_run", {"workflow": "w"}),
    )
    first, error = session._nex_match_tool_call(_nex_call(1, "inspect_run", {"workflow": "w"}))
    assert error is None and first["id"] == "u1"
    second, error = session._nex_match_tool_call(_nex_call(2, "inspect_run", {"workflow": "w"}))
    assert error is None and second["id"] == "u2"
    assert session._nex_invalid_reason is None


def test_nex_fifo_skips_identical_use_already_answered_client_side():
    session = ds.DesktopStdioSession([sys.executable, "-c", "pass"], nex_mode=True)
    _nex_stream_tool_use(
        session,
        ("u1", "inspect_run", {}),
        ("u2", "inspect_run", {}),
    )
    # u1 was answered (e.g. denied) without ever reaching the bridge.
    session.observe_claude_stream_event(_tool_results(
        {"type": "tool_result", "tool_use_id": "u1", "is_error": True, "content": "denied"},
    ))
    use, error = session._nex_match_tool_call(_nex_call(1, "inspect_run", {}))
    assert error is None and use["id"] == "u2"


def test_nex_differing_arguments_are_not_conflated_by_fifo():
    session = ds.DesktopStdioSession([sys.executable, "-c", "pass"], nex_mode=True)
    _nex_stream_tool_use(
        session,
        ("u1", "inspect_run", {"workflow": "a"}),
        ("u2", "inspect_run", {"workflow": "b"}),
    )
    use, error = session._nex_match_tool_call(_nex_call(1, "inspect_run", {"workflow": "b"}))
    assert error is None and use["id"] == "u2"


def test_nex_capture_and_validation_snapshots_share_one_entry_filter(tmp_path):
    capture = tmp_path / "capture"
    (capture / "transform").mkdir(parents=True)
    (capture / "secrets").mkdir()
    (capture / "transform" / "main.py").write_text("print(1)\n")
    (capture / "infra-profile.yaml").write_text("profile: x\n")
    (capture / "transform" / ".env").write_text("TOKEN=x\n")
    (capture / "transform" / "client.pem").write_text("pem\n")
    (capture / "secrets" / "token.txt").write_text("x\n")
    (capture / "transform" / "big.bin").write_bytes(b"0" * (ds._NEX_MAX_SNAPSHOT_FILE_BYTES + 1))
    blueprint = capture / "dp-blueprint.md"
    blueprint.write_text("# blueprint\n")
    capture_resolved = capture.resolve()
    session = ds.DesktopStdioSession([sys.executable, "-c", "pass"], nex_mode=True)
    session.nex_workspace = tmp_path.resolve()
    authoring = str(tmp_path / "authoring")
    capture_request = _nex_call(1, "advance_workflow", {
        "workflow": "nex890-positive", "authoring_root": authoring,
        "action": {"type": "capture"},
    })
    capture_response = {"jsonrpc": "2.0", "id": 1, "result": {"requirements": [{
        "id": "review",
        "review_input": {
            "retained_capture_root": str(capture_resolved),
            "retained_blueprint_path": str(blueprint.resolve()),
        },
    }]}}
    session._nex_snapshot_review_input(capture_request, capture_response)
    assert session._nex_invalid_reason is None
    session._nex_snapshot_validation(_nex_call(2, "advance_workflow", {
        "workflow": "nex890-positive", "authoring_root": authoring,
    }))
    assert session._nex_invalid_reason is None
    case = session.nex_file_snapshots()["nex890-positive"]
    capture_files = set(case["files"])
    validation_files = set(case["validation"]["files"])
    names = {Path(path).name for path in capture_files}
    assert "main.py" in names and "infra-profile.yaml" in names
    assert not names & {".env", "client.pem", "token.txt", "big.bin"}
    assert validation_files == capture_files
    for path in capture_files:
        assert case["files"][path] == case["validation"]["files"][path]


EXPORT_SERVER = r"""
import json, sys
for raw in sys.stdin:
    message = json.loads(raw)
    if message.get("method") == "tools/call":
        archive = message["params"]["arguments"]["destination"]
        with open(archive, "wb") as handle:
            handle.write(b"frozen-archive-bytes")
        payload = {"archive_path": archive}
        print(json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": {
            "content": [{"type": "text", "text": json.dumps(payload)}],
        }}), flush=True)
"""


def test_nex_export_archive_is_frozen_before_the_response_is_forwarded(tmp_path):
    session, proxy_side = _nex_bridge_harness(tmp_path, EXPORT_SERVER)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    session.nex_workspace = workspace.resolve()
    archive = str(workspace.resolve() / "export.zip")
    _nex_stream_tool_use(session, ("u1", "export_data_product", {"destination": archive}))
    try:
        _nex_send(proxy_side, _nex_call(7, "export_data_product", {"destination": archive}))
        reply = json.loads(proxy_side.makefile("rb").readline())
        # The agent may rewrite the workspace only after seeing the response.
        Path(archive).write_bytes(b"tampered")
        frozen = session.nex_frozen_exports()
    finally:
        proxy_side.close()
        session.cleanup()
    assert reply["id"] == 7
    entry = frozen[ds._rpc_id_key(7)]
    assert entry["archive_path"] == archive
    assert entry["content"] == b"frozen-archive-bytes"
    import hashlib
    assert entry["sha256"] == hashlib.sha256(b"frozen-archive-bytes").hexdigest()


def test_nex_review_reader_request_does_not_leave_stale_request_context(tmp_path, monkeypatch):
    session, proxy_side = _nex_bridge_harness(tmp_path, SILENT_SERVER)
    seen = {}
    original_reader = session._nex_reader_response
    monkeypatch.setattr(session, "_nex_match_tool_call", lambda request: ({"id": "u"}, None))

    def reader(request):
        seen["called"] = True
        return original_reader(request)

    monkeypatch.setattr(session, "_nex_reader_response", reader)
    try:
        request = _nex_call(5, ds._REVIEW_READER_TOOL, {"path": "/nope", "operation": "read"})
        _nex_send(proxy_side, request)
        json.loads(proxy_side.makefile("rb").readline())
        # Reusing the id after the synthesized reply must not be treated as a
        # duplicate in-flight request.
        _nex_send(proxy_side, request)
        second = json.loads(proxy_side.makefile("rb").readline())
    finally:
        proxy_side.close()
        session.cleanup()
    assert seen["called"]
    assert second["id"] == 5
    assert "duplicate in-flight" not in (session._nex_invalid_reason or "")


def _nex_reader_tool_result(session, use, *, response_success, is_error):
    use.update({"name": ds._REVIEW_READER_TOOL, "response_success": response_success,
                "parent_tool_use_id": "child-1"})
    session._nex_stream_uses.append(use)
    session.observe_claude_stream_event({
        "type": "user",
        "message": {"content": [{
            "type": "tool_result", "tool_use_id": use["id"],
            "is_error": is_error, "content": "reader reply",
        }]},
    })


def test_nex_refused_review_read_does_not_invalidate_the_cell(tmp_path):
    session, proxy_side = _nex_bridge_harness(tmp_path, SILENT_SERVER)
    try:
        _nex_reader_tool_result(session, {"id": "r1"}, response_success=False, is_error=True)
        assert session._nex_invalid_reason is None
        assert not session._nex_review_read_success
    finally:
        proxy_side.close()
        session.cleanup()


def test_nex_served_review_read_with_failed_stream_result_still_invalidates(tmp_path):
    session, proxy_side = _nex_bridge_harness(tmp_path, SILENT_SERVER)
    try:
        _nex_reader_tool_result(session, {"id": "r2"}, response_success=True, is_error=True)
        assert session._nex_invalid_reason == (
            "review reader response or stream tool_result was unsuccessful (siblings=-1)"
        )
    finally:
        proxy_side.close()
        session.cleanup()


def test_nex_rootless_call_binds_to_its_own_workflow_root(tmp_path, monkeypatch):
    session, proxy_side = _nex_bridge_harness(tmp_path, SILENT_SERVER)
    roots = {}
    monkeypatch.setattr(
        session, "_nex_trace_record",
        lambda direction, message, **kw: roots.__setitem__(kw.get("workflow"), kw.get("root")),
    )
    try:
        session._nex_workflow_roots["nex890-positive"] = "/ws/positive"
        session._nex_active_workflow = "nex890-positive"
        for request_id, workflow in ((1, "nex890-401"), (2, "nex890-positive")):
            request = {"jsonrpc": "2.0", "id": request_id, "method": "tools/call",
                       "params": {"name": "prepare_workflow",
                                  "arguments": {"workflow": workflow}}}
            session._nex_record_response(
                request, {"jsonrpc": "2.0", "id": request_id, "result": {"content": []}}
            )
    finally:
        proxy_side.close()
        session.cleanup()
    assert roots["nex890-401"] is None
    assert roots["nex890-positive"] == "/ws/positive"
