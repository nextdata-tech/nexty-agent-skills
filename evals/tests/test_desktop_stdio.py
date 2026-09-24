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

REVIEW_GUARD_SERVER = r"""
import json, sys

for raw in sys.stdin:
    request = json.loads(raw)
    operation = request.get("params", {}).get("name", request.get("method"))
    arguments = request.get("params", {}).get("arguments", {})
    action = arguments.get("action", {})
    if operation == "advance_workflow" and action.get("type") == "capture":
        result = {
            "revision": 4,
            "invalidation_epoch": 0,
            "requirements": {
                "review": {
                    "status": "pending",
                    "review_input": {"request_id": "review-1"},
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

    def call(request):
        assert proxy.stdin is not None and proxy.stdout is not None
        proxy.stdin.write(json.dumps(request) + "\n")
        proxy.stdin.flush()
        return json.loads(proxy.stdout.readline())

    try:
        capture = call(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "advance_workflow",
                    "arguments": {
                        "workflow": "crm-pipeline",
                        "action": {"type": "capture"},
                    },
                },
            }
        )
        assert capture["result"]["next_actions"][0]["code"] == "workflow/review_pending"

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
                            "requirement_id": "review",
                            "generation": 1,
                            "subject_sha256": "subject-1",
                            "dependency_evidence_sha256": "evidence-1",
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


def test_proxy_exposes_bounded_runner_owned_review_reader(tmp_path):
    child = _script(tmp_path / "review-reader-server.py", REVIEW_READER_SERVER)
    capture = tmp_path / "capture"
    capture.mkdir()
    (capture / "build-record.json").write_text('{"status":"ok"}\n')
    (capture / ".env").write_text("TOKEN=must-not-be-read\n")
    (capture / ".env.local").write_text("TOKEN=must-not-be-read\n")
    blueprint = tmp_path / "blueprint.md"
    blueprint.write_text("# Approved blueprint\n")
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
        assert len(bounded_summaries) == 2
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
        assert len(reader_summaries) == 4
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
            "code": "workflow/requirement_satisfied",
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
