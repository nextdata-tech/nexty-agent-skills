"""Deterministic tests for the terminal Desktop stdio substrate.

These tests deliberately use a fake JSON-RPC child. They prove config
isolation, proxy forwarding/redaction, Claude flag wiring, and process cleanup
without a Desktop binary, an MCP SDK, or provider credentials.
"""

from __future__ import annotations

import json
import os
import select
import stat
import subprocess
import sys
import threading
import time
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
