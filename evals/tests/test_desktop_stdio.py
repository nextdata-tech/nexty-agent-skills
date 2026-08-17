"""Deterministic tests for the terminal Desktop stdio substrate.

These tests deliberately use a fake JSON-RPC child. They prove config
isolation, proxy forwarding/redaction, Claude flag wiring, and process cleanup
without a Desktop binary, an MCP SDK, or provider credentials.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

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


def _script(path: Path, body: str) -> Path:
    path.write_text("#!/usr/bin/env python3\n" + body, encoding="utf-8")
    path.chmod(0o755)
    return path


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
        proxy.stdin.close()
        assert proxy.wait(timeout=10) == 0
        trace = session.trace_path.read_text()
        assert "live-token" not in trace
        assert "secret" not in trace
        records = [json.loads(line) for line in trace.splitlines()]
        assert {record["direction"] for record in records} == {"request", "response"}
        assert all(record["message"] for record in records)
        result = json.loads(session.server_result_path.read_text())
        assert result["status"] == "passed"
    finally:
        if proxy.poll() is None:
            proxy.kill()
            proxy.wait()
        session.cleanup()


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


@pytest.mark.parametrize(
    "payload",
    [
        {"password": "hunter2", "nested": {"access_token": "abc"}},
        {"text": "Bearer abc.def", "url": "https://u:p@example.test/?token=xyz"},
    ],
)
def test_redaction_is_recursive_and_fail_closed(payload):
    value = json.dumps(ds.redact_json_rpc(payload))
    assert all(secret not in value for secret in ("hunter2", "abc", "xyz", "u:p"))
    assert ds.REDACTED in value
