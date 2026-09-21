"""Focused contract tests for the Codex live-session bridge."""

from __future__ import annotations

import json
from pathlib import Path
import stat
import time
from collections import deque
from types import SimpleNamespace

import pytest

from _repo_paths import REPO_ROOT

from dp_scenarios.runner.codex_adapter import (
    CODEX_SYSTEM_PROMPT,
    CodexAdapter,
    CodexAdapterError,
    _COLLAB_FAILURE_STATUSES,
    _update_reviewer_deadline,
    _load_mcp_server,
    parse_codex_events,
)
from dp_scenarios.runner.review_guard import REVIEW_DEADLINE_MS


def _identity(value):
    return value


def test_codex_system_prompt_preserves_workflow_v2_action_discipline() -> None:
    assert "treat every supervisor response as authoritative" in CODEX_SYSTEM_PROMPT
    assert "Do not use Bash, curl, WebFetch" in CODEX_SYSTEM_PROMPT
    assert "source observations must come from the" in CODEX_SYSTEM_PROMPT
    assert "If a shell command" in CODEX_SYSTEM_PROMPT and "rejected" in CODEX_SYSTEM_PROMPT
    assert "Complete closure authoring in this parent" in CODEX_SYSTEM_PROMPT
    assert "do not use destructive" in CODEX_SYSTEM_PROMPT
    assert "Do not use `spawnAgent` for closure authoring" in CODEX_SYSTEM_PROMPT
    assert "do not call prepare_workflow, get_workflow_capabilities, or" in CODEX_SYSTEM_PROMPT
    assert "Dispatch exactly one provider-native" in CODEX_SYSTEM_PROMPT
    assert "built-in Codex collaboration child via spawnAgent" in CODEX_SYSTEM_PROMPT
    assert "exact review_input" in CODEX_SYSTEM_PROMPT
    assert "never fabricate the review outcome yourself" in CODEX_SYSTEM_PROMPT
    assert "CODEX_REVIEW_CHILD" in CODEX_SYSTEM_PROMPT
    assert "never a JSON-encoded" in CODEX_SYSTEM_PROMPT
    assert "never omit" in CODEX_SYSTEM_PROMPT and "`session_ref`" in CODEX_SYSTEM_PROMPT
    assert "findings" in CODEX_SYSTEM_PROMPT and "entries have exactly the keys" in CODEX_SYSTEM_PROMPT
    assert "`id`," in CODEX_SYSTEM_PROMPT and "`severity`," in CODEX_SYSTEM_PROMPT
    assert "do not forward reviewer-only fields" in CODEX_SYSTEM_PROMPT
    assert "retry with the exact same current binding" in CODEX_SYSTEM_PROMPT
    assert "Do not edit the closure, blueprint, or review record" in CODEX_SYSTEM_PROMPT
    assert "stale subject or dependency" in CODEX_SYSTEM_PROMPT
    assert "close that same child with" in CODEX_SYSTEM_PROMPT
    assert "threads remain allocated to the app-server" in CODEX_SYSTEM_PROMPT
    assert "captured inputs are immutable" in CODEX_SYSTEM_PROMPT
    assert "only a clear report authorizes" in CODEX_SYSTEM_PROMPT
    assert "end the" in CODEX_SYSTEM_PROMPT
    assert "same turn" in CODEX_SYSTEM_PROMPT
    assert "immediately using the returned receiver thread id" in CODEX_SYSTEM_PROMPT
    assert "Only use\ninspect_prepare_recovery" in CODEX_SYSTEM_PROMPT
    assert "the next supervisor action must be that report" in CODEX_SYSTEM_PROMPT
    assert "Do not call reset_workflow, list_data_products, inspect_workflow," in CODEX_SYSTEM_PROMPT
    assert '"workflow already exists" and active-workflow' in CODEX_SYSTEM_PROMPT
    assert "errors are non-retryable" in CODEX_SYSTEM_PROMPT


def test_codex_reviewer_terminal_statuses_include_timeout_and_cancellation() -> None:
    assert {
        "timedOut",
        "timed_out",
        "timeout",
        "cancelled",
        "canceled",
    } <= _COLLAB_FAILURE_STATUSES


def test_codex_reviewer_deadline_is_armed_and_cleared_by_close() -> None:
    spawn = {
        "type": "item.completed",
        "item": {
            "type": "collab_agent_tool_call",
            "tool": "spawnAgent",
            "receiverThreadIds": ["child-1"],
        },
    }
    receiver_ids, deadline = _update_reviewer_deadline(
        spawn, set(), None, now=10.0
    )
    assert receiver_ids == {"child-1"}
    assert deadline == pytest.approx(10.0 + REVIEW_DEADLINE_MS / 1000.0)

    close = {
        "type": "item.completed",
        "item": {
            "type": "collab_agent_tool_call",
            "tool": "closeAgent",
            "receiverThreadId": "child-1",
        },
    }
    assert _update_reviewer_deadline(
        close, receiver_ids, deadline, now=20.0
    ) == (set(), None)


def test_parse_codex_events_preserves_mcp_calls_and_terminal_facts() -> None:
    result, observations = parse_codex_events(
        [
            {"type": "thread.started", "thread_id": "thread-1"},
            {
                "type": "item.completed",
                "item": {"type": "agent_message", "text": "I inspected the source."},
            },
            {
                "type": "item.started",
                "item": {
                    "id": "call-1",
                    "type": "mcp_tool_call",
                    "server": "nxd-desktop",
                    "tool": "advance_workflow",
                    "arguments": {"workflow": "crm-pipeline", "action": {"type": "start_run"}},
                },
            },
            {
                "type": "item.completed",
                "item": {
                    "id": "call-1",
                    "type": "mcp_tool_call",
                    "server": "nxd-desktop",
                    "tool": "advance_workflow",
                    "arguments": {"workflow": "crm-pipeline", "action": {"type": "start_run"}},
                    "result": {"structured_content": {"admission": {"run_id": "run-1"}}},
                },
            },
            {"type": "turn.completed", "usage": {"input_tokens": 3, "output_tokens": 2}},
        ],
        redact_json_rpc=_identity,
        redact_text=lambda value: value,
        session_id=None,
    )

    assert result.session_id == "thread-1"
    assert result.agent_message == "I inspected the source."
    assert result.terminal_result_count == 1
    assert result.terminal_result_subtype == "success"
    assert result.terminal_result_is_error is False
    assert result.last_mcp_call == "advance_workflow:ok"
    assert result.tool_calls[0].name == "mcp__nxd-desktop__advance_workflow"
    assert observations[0]["tool"] == "advance_workflow"
    assert observations[0]["result"] == {"admission": {"run_id": "run-1"}}


def test_parse_codex_events_marks_unanswered_mcp_call_as_wedged() -> None:
    result, observations = parse_codex_events(
        [
            {
                "type": "item.started",
                "item": {
                    "id": "call-1",
                    "type": "mcp_tool_call",
                    "server": "nxd-desktop",
                    "tool": "inspect_run",
                    "arguments": {"run_id": "run-1"},
                },
            }
        ],
        redact_json_rpc=_identity,
        redact_text=lambda value: value,
        session_id="thread-1",
    )

    assert result.environment_wedged is True
    assert result.last_mcp_call == "inspect_run:unanswered"
    assert observations[0]["answered"] is False
    assert result.terminal_result_count == 0


def test_parse_codex_events_maps_completed_collaboration_reviewer() -> None:
    events = [
        {
            "method": "item/started",
            "params": {
                "item": {
                    "type": "collabAgentToolCall",
                    "id": "agent-call-1",
                    "tool": "spawnAgent",
                    "prompt": "Load and follow nxd-review-closure.\nNXD_REVIEW_DISPATCH {}",
                    "status": "inProgress",
                }
            },
        },
        {
            "method": "item/completed",
            "params": {
                "item": {
                    "type": "collabAgentToolCall",
                    "id": "agent-call-1",
                    "tool": "spawnAgent",
                    "status": "completed",
                    "agentsStates": {
                        "child-1": {"status": "completed", "message": "claims"}
                    },
                }
            },
        },
        {
            "method": "turn/completed",
            "params": {"turn": {"id": "turn-1", "status": "completed"}},
        },
    ]

    result, _ = parse_codex_events(
        events,
        redact_json_rpc=lambda value: value,
        redact_text=lambda value: value,
        session_id="thread-1",
    )

    assert len(result.tool_calls) == 1
    call = result.tool_calls[0]
    assert call.name == "Agent"
    assert call.arguments["subagent_type"] == "general-purpose"
    assert call.result == {"is_error": False, "content": ["claims"]}
    assert result.terminal_result_subtype == "success"


def test_parse_codex_events_maps_reviewer_after_waiting_for_spawned_child() -> None:
    events = [
        {
            "method": "item/completed",
            "params": {
                "item": {
                    "type": "collabAgentToolCall",
                    "id": "agent-call-1",
                    "tool": "spawnAgent",
                    "prompt": "review closure",
                    "status": "completed",
                    "receiverThreadIds": ["child-1"],
                    "agentsStates": {"child-1": {"status": "running", "message": None}},
                }
            },
        },
        {
            "method": "item/completed",
            "params": {
                "item": {
                    "type": "collabAgentToolCall",
                    "id": "wait-call-1",
                    "tool": "wait",
                    "status": "completed",
                    "receiverThreadIds": ["child-1"],
                    "agentsStates": {"child-1": {"status": "completed", "message": "claims"}},
                }
            },
        },
        {"method": "turn/completed", "params": {"turn": {"status": "completed"}}},
    ]

    result, _ = parse_codex_events(
        events,
        redact_json_rpc=lambda value: value,
        redact_text=lambda value: value,
        session_id="thread-1",
    )

    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "Agent"
    assert result.tool_calls[0].result == {"is_error": False, "content": ["claims"]}


def test_parse_codex_events_accepts_legacy_collaboration_field_names() -> None:
    result, _ = parse_codex_events(
        [
            {
                "method": "item/completed",
                "params": {
                    "item": {
                        "type": "collab_tool_call",
                        "id": "agent-call-1",
                        "tool": "spawn_agent",
                        "prompt": "review closure",
                        "status": "completed",
                        "receiver_thread_ids": ["child-1"],
                        "agents_states": {"child-1": {"status": "completed", "message": "claims"}},
                    }
                },
            },
            {"method": "turn/completed", "params": {"turn": {"status": "completed"}}},
        ],
        redact_json_rpc=lambda value: value,
        redact_text=lambda value: value,
        session_id="thread-1",
    )

    assert result.tool_calls[0].name == "Agent"
    assert result.tool_calls[0].result == {"is_error": False, "content": ["claims"]}


def test_parse_codex_events_does_not_credit_spawn_without_child_completion() -> None:
    result, _ = parse_codex_events(
        [
            {
                "method": "item/completed",
                "params": {
                    "item": {
                        "type": "collabAgentToolCall",
                        "id": "agent-call-1",
                        "tool": "spawnAgent",
                        "prompt": "review closure",
                        "status": "completed",
                        "receiverThreadIds": ["child-1"],
                        "agentsStates": {"child-1": {"status": "running", "message": None}},
                    }
                },
            },
            {"method": "turn/completed", "params": {"turn": {"status": "completed"}}},
        ],
        redact_json_rpc=lambda value: value,
        redact_text=lambda value: value,
        session_id="thread-1",
    )

    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "Agent"
    assert result.tool_calls[0].result == {"is_error": True, "content": []}


def test_parse_codex_events_keeps_completed_mcp_error_answered() -> None:
    result, observations = parse_codex_events(
        [
            {
                "type": "item.completed",
                "item": {
                    "id": "call-1",
                    "type": "mcp_tool_call",
                    "server": "nxd-desktop",
                    "tool": "get_workflow_capabilities",
                    "status": "failed",
                    "error": "approval denied",
                },
            },
            {"type": "turn.completed"},
        ],
        redact_json_rpc=_identity,
        redact_text=lambda value: value,
        session_id="thread-1",
    )

    assert result.environment_wedged is False
    assert result.tool_calls[0].result == {"error": "approval denied"}
    assert observations[0]["answered"] is True


def test_codex_adapter_builds_app_server_protocol_configuration(tmp_path: Path) -> None:
    config_path = tmp_path / "mcp.json"
    config_path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "nxd-desktop": {
                        "command": "/bin/echo",
                        "args": ["--proxy", "server-spec.json"],
                        "env": {"PYTHONUNBUFFERED": "1"},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    assert _load_mcp_server(config_path, strict=True) == (
        "/bin/echo",
        ("--proxy", "server-spec.json"),
        {"PYTHONUNBUFFERED": "1"},
    )

    adapter = CodexAdapter(
        codex=Path("/bin/true"),
        model="gpt-5.6-luna",
        effort="xhigh",
        skill_pack_root=REPO_ROOT,
        repo_root=REPO_ROOT,
        fixture_dir=tmp_path,
        artifact_dir=tmp_path / "artifacts",
        desktop_supervisor=Path("/bin/true"),
        desktop_python=Path("/bin/true"),
        timeout_s=5,
        append_system_prompt="test",
        mcp_config=config_path,
        strict_mcp_config=True,
        supervisor_data_dir=tmp_path,
    )
    params = adapter._thread_params()
    assert params["sandbox"] == "workspace-write"
    assert params["approvalPolicy"] == "never"
    assert params["runtimeWorkspaceRoots"] == [str(Path.cwd()), str(REPO_ROOT)]
    assert params["baseInstructions"].startswith("test")
    assert params["config"]["mcp_servers"]["nxd-desktop"]["command"] == "/bin/echo"
    assert params["config"]["mcp_servers"]["nxd-desktop"]["required"] is True
    assert params["config"]["mcp_servers"]["nxd-desktop"]["startup_timeout_sec"] == 30

    app_command = adapter._app_server_command()
    assert app_command[:3] == ["/bin/true", "app-server", "--stdio"]
    assert app_command[3:5] == ["--enable", "multi_agent"]
    assert 'mcp_servers.nxd-desktop.command="/bin/echo"' in app_command
    assert 'mcp_servers.nxd-desktop.args=["--proxy", "server-spec.json"]' in app_command
    assert 'mcp_servers.nxd-desktop.default_tools_approval_mode="approve"' in app_command
    assert "mcp_servers.nxd-desktop.required=true" in app_command
    assert "mcp_servers.nxd-desktop.startup_timeout_sec=30" in app_command


def test_codex_adapter_runs_app_server_child_and_writes_thread_identity(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    fake = tmp_path / "fake-codex"
    request_log = tmp_path / "requests.json"
    fake.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "from pathlib import Path\n"
        f"request_log = {str(request_log)!r}\n"
        "requests = []\n"
        "status_calls = 0\n"
        "thread_id = '00000000-0000-4000-8000-000000000002'\n"
        "turn_id = '00000000-0000-4000-8000-000000000003'\n"
        "for line in sys.stdin:\n"
        "    request = json.loads(line)\n"
        "    requests.append(request)\n"
        "    Path(request_log).write_text(json.dumps(requests))\n"
        "    method = request.get('method')\n"
        "    if method == 'initialize':\n"
        "        print(json.dumps({'id': request['id'], 'result': {}}), flush=True)\n"
        "    elif method == 'thread/start':\n"
        "        thread = {'id': thread_id}\n"
        "        print(json.dumps({'id': request['id'], 'result': {'thread': thread}}), flush=True)\n"
        "        print(json.dumps({'method': 'thread/started', 'params': {'thread': thread}}), flush=True)\n"
        "    elif method == 'mcpServerStatus/list':\n"
        "        status_calls += 1\n"
        "        data = [] if status_calls == 1 else [{'name': 'nxd-desktop', 'runtimeStatus': 'connected', 'tools': {'list_data_products': {}}}]\n"
        "        print(json.dumps({'id': request['id'], 'result': {'data': data}}), flush=True)\n"
        "    elif method == 'turn/start':\n"
        "        print(json.dumps({'id': request['id'], 'result': {'turn': {'id': turn_id}}}), flush=True)\n"
        "        item = {'type': 'agentMessage', 'id': 'msg-1', 'text': 'done'}\n"
        "        print(json.dumps({'method': 'item/completed', 'params': {'item': item}}), flush=True)\n"
        "        turn = {'id': turn_id, 'status': 'completed'}\n"
        "        print(json.dumps({'method': 'turn/completed', 'params': {'turn': turn}}), flush=True)\n"
        "        sys.exit(0)\n",
        encoding="utf-8",
    )
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    config_path = tmp_path / "mcp.json"
    config_path.write_text(
        json.dumps({"mcpServers": {"nxd-desktop": {"command": "/bin/echo", "args": []}}}),
        encoding="utf-8",
    )
    artifact_dir = tmp_path / "artifacts"
    adapter = CodexAdapter(
        codex=fake,
        model="gpt-5.6-luna",
        effort="medium",
        skill_pack_root=REPO_ROOT,
        repo_root=REPO_ROOT,
        fixture_dir=tmp_path,
        artifact_dir=artifact_dir,
        desktop_supervisor=Path("/bin/true"),
        desktop_python=Path("/bin/true"),
        timeout_s=5,
        append_system_prompt="test",
        mcp_config=config_path,
        supervisor_data_dir=tmp_path,
    )

    result = adapter.send({"message": {"text": "hello", "attachments": []}})
    adapter.close()

    assert result.session_id == "00000000-0000-4000-8000-000000000002"
    assert result.agent_message == "done"
    assert result.terminal_result_count == 1
    requests = json.loads(request_log.read_text(encoding="utf-8"))
    assert [request["method"] for request in requests[:6]] == [
        "initialize",
        "initialized",
        "thread/start",
        "mcpServerStatus/list",
        "mcpServerStatus/list",
        "turn/start",
    ]
    thread_params = requests[2]["params"]
    assert thread_params["baseInstructions"].startswith("test")
    assert thread_params["runtimeWorkspaceRoots"] == [str(tmp_path), str(REPO_ROOT)]
    turn_params = requests[5]["params"]
    assert turn_params["input"] == [{"type": "text", "text": "hello"}]
    assert turn_params["sandboxPolicy"] == {
        "type": "workspaceWrite",
        "writableRoots": [str(tmp_path), str(REPO_ROOT)],
    }


def test_codex_home_is_disposable_even_without_host_auth(tmp_path: Path) -> None:
    host_home = tmp_path / "host-codex"
    host_home.mkdir()
    adapter = CodexAdapter(
        codex=Path("/bin/true"),
        model="gpt-5.6-luna",
        effort="medium",
        skill_pack_root=REPO_ROOT,
        repo_root=REPO_ROOT,
        fixture_dir=tmp_path,
        artifact_dir=tmp_path / "artifacts",
        desktop_supervisor=Path("/bin/true"),
        desktop_python=Path("/bin/true"),
        timeout_s=5,
        append_system_prompt="test",
        mcp_config=tmp_path / "mcp.json",
        supervisor_data_dir=tmp_path,
    )
    isolated = adapter._isolated_codex_home({"CODEX_HOME": str(host_home)})
    try:
        assert Path(isolated.name) != host_home
        assert (Path(isolated.name) / "config.toml").is_file()
        assert not (Path(isolated.name) / "auth.json").exists()
    finally:
        isolated.cleanup()


def test_codex_adapter_rejects_non_object_app_server_events() -> None:
    with pytest.raises(CodexAdapterError, match="non-object JSON event"):
        CodexAdapter._decode_app_server_line(b"[]")


def test_codex_adapter_checks_deadline_before_draining_queued_events() -> None:
    adapter = object.__new__(CodexAdapter)
    adapter._process = SimpleNamespace(stdout=object(), stderr=object())
    adapter._stdout_events = deque([{"method": "notification"}])

    with pytest.raises(TimeoutError, match="response deadline expired"):
        adapter._read_streams(time.monotonic() - 1)


def test_codex_adapter_keeps_one_app_server_and_mcp_observations_across_turns(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    fake = tmp_path / "fake-codex"
    fake.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "thread_id = '00000000-0000-4000-8000-000000000010'\n"
        "turn_number = 0\n"
        "for line in sys.stdin:\n"
        "    request = json.loads(line)\n"
        "    method = request.get('method')\n"
        "    if method == 'initialize':\n"
        "        print(json.dumps({'id': request['id'], 'result': {}}), flush=True)\n"
        "    elif method == 'thread/start':\n"
        "        thread = {'id': thread_id}\n"
        "        print(json.dumps({'id': request['id'], 'result': {'thread': thread}}), flush=True)\n"
        "    elif method == 'mcpServerStatus/list':\n"
        "        print(json.dumps({'id': request['id'], 'result': {'data': [{'name': 'nxd-desktop', 'runtimeStatus': 'connected', 'tools': {'list_data_products': {}}}]}}), flush=True)\n"
        "    elif method == 'turn/start':\n"
        "        turn_number += 1\n"
        "        turn_id = f'00000000-0000-4000-8000-00000000001{turn_number}'\n"
        "        print(json.dumps({'id': request['id'], 'result': {'turn': {'id': turn_id}}}), flush=True)\n"
        "        call = {'type': 'mcpToolCall', 'id': f'call-{turn_number}', 'server': 'nxd-desktop', 'tool': 'list_data_products', 'arguments': {'page': turn_number}, 'status': 'inProgress'}\n"
        "        print(json.dumps({'method': 'item/started', 'params': {'item': call}}), flush=True)\n"
        "        call['status'] = 'completed'\n"
        "        call['result'] = {'structuredContent': {'page': turn_number}}\n"
        "        print(json.dumps({'method': 'item/completed', 'params': {'item': call}}), flush=True)\n"
        "        message = {'type': 'agentMessage', 'id': f'msg-{turn_number}', 'text': f'turn {turn_number}'}\n"
        "        print(json.dumps({'method': 'item/completed', 'params': {'item': message}}), flush=True)\n"
        "        print(json.dumps({'method': 'turn/completed', 'params': {'turn': {'id': turn_id, 'status': 'completed'}}}), flush=True)\n",
        encoding="utf-8",
    )
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    config_path = tmp_path / "mcp.json"
    config_path.write_text(
        json.dumps({"mcpServers": {"nxd-desktop": {"command": "/bin/echo", "args": []}}}),
        encoding="utf-8",
    )
    adapter = CodexAdapter(
        codex=fake,
        model="gpt-5.6-luna",
        effort="medium",
        skill_pack_root=REPO_ROOT,
        repo_root=REPO_ROOT,
        fixture_dir=tmp_path,
        artifact_dir=tmp_path / "artifacts",
        desktop_supervisor=Path("/bin/true"),
        desktop_python=Path("/bin/true"),
        timeout_s=5,
        append_system_prompt="test",
        mcp_config=config_path,
        supervisor_data_dir=tmp_path,
    )
    try:
        first = adapter.send({"message": {"text": "one", "attachments": []}})
        second = adapter.send({"message": {"text": "two", "attachments": []}})
    finally:
        adapter.close()

    assert first.session_id == second.session_id == "00000000-0000-4000-8000-000000000010"
    assert first.last_mcp_call == second.last_mcp_call == "list_data_products:ok"
    assert first.tool_results == ({"page": 1},)
    assert second.tool_results == ({"page": 2},)
    assert first.agent_message == "turn 1"
    assert second.agent_message == "turn 2"


def test_codex_adapter_timeout_retains_partial_app_server_events(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    fake = tmp_path / "fake-codex"
    fake.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys, time\n"
        "thread_id = '00000000-0000-4000-8000-000000000020'\n"
        "for line in sys.stdin:\n"
        "    request = json.loads(line)\n"
        "    method = request.get('method')\n"
        "    if method == 'initialize':\n"
        "        print(json.dumps({'id': request['id'], 'result': {}}), flush=True)\n"
        "    elif method == 'thread/start':\n"
        "        print(json.dumps({'id': request['id'], 'result': {'thread': {'id': thread_id}}}), flush=True)\n"
        "    elif method == 'mcpServerStatus/list':\n"
        "        print(json.dumps({'id': request['id'], 'result': {'data': [{'name': 'nxd-desktop', 'runtimeStatus': 'connected', 'tools': {'inspect_run': {}}}]}}), flush=True)\n"
        "    elif method == 'turn/start':\n"
        "        print(json.dumps({'id': request['id'], 'result': {'turn': {'id': '00000000-0000-4000-8000-000000000021'}}}), flush=True)\n"
        "        call = {'type': 'mcpToolCall', 'id': 'call-1', 'server': 'nxd-desktop', 'tool': 'inspect_run', 'arguments': {'run_id': 'run-1'}, 'status': 'inProgress'}\n"
        "        print(json.dumps({'method': 'item/started', 'params': {'item': call}}), flush=True)\n"
        "        print(json.dumps({'method': 'item/agentMessage/delta', 'params': {'delta': 'partial'}}), flush=True)\n"
        "        os.close(2)\n"
        "        time.sleep(5)\n",
        encoding="utf-8",
    )
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    config_path = tmp_path / "mcp.json"
    config_path.write_text(
        json.dumps({"mcpServers": {"nxd-desktop": {"command": "/bin/echo", "args": []}}}),
        encoding="utf-8",
    )
    adapter = CodexAdapter(
        codex=fake,
        model="gpt-5.6-luna",
        effort="medium",
        skill_pack_root=REPO_ROOT,
        repo_root=REPO_ROOT,
        fixture_dir=tmp_path,
        artifact_dir=tmp_path / "artifacts",
        desktop_supervisor=Path("/bin/true"),
        desktop_python=Path("/bin/true"),
        timeout_s=1,
        append_system_prompt="test",
        mcp_config=config_path,
        supervisor_data_dir=tmp_path,
    )

    result = adapter.send({"message": {"text": "one", "attachments": []}})
    adapter.close()

    assert result.turn_timed_out is True
    assert result.session_id == "00000000-0000-4000-8000-000000000020"
    assert result.agent_message == "partial"
    assert result.last_mcp_call == "inspect_run:unanswered"
    assert "event_tail=item/started[mcpToolCall]:nxd-desktop/inspect_run=inProgress" in (
        result.environment_detail or ""
    )
