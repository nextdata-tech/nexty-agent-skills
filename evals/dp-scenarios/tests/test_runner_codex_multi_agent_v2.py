"""Codex multi-agent v2 reviewer collaboration, from recorded live-run shapes.

``gpt-6-luna`` declares ``multi_agent_version: v2`` in the Codex catalog. Its
collaboration tools are ``spawn_agent``/``wait_agent``: the child lifecycle is
reported as ``subAgentActivity`` items, ``wait_agent`` accepts only
``timeout_ms`` and names no receivers, the child's claims are delivered to the
parent as an inter-agent message, and the spawn message is provider-encrypted.
The fixture holds the recorded shapes; see its ``source`` field.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dp_scenarios.grading.gates import _completed_review_delegation
from dp_scenarios.runner.codex_adapter import (
    CODEX_SYSTEM_PROMPT,
    MODEL_CATALOG_FILENAME,
    CodexAdapter,
    CodexAdapterError,
    _normalise_app_server_event,
    _update_reviewer_deadline,
    _write_multi_agent_v1_catalog,
    parse_codex_events,
)

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "codex-multi-agent-v2-reviewer.json").read_text(
        encoding="utf-8"
    )
)
PARENT = FIXTURE["parent_thread_id"]
TURN = FIXTURE["turn_id"]
CHILD = FIXTURE["child_thread_id"]
CLAIMS = FIXTURE["child_turns_list"]["data"][0]["items"][-1]["text"]


def _identity(value):
    return value


def _parse(events):
    return parse_codex_events(
        events,
        redact_json_rpc=_identity,
        redact_text=_identity,
        session_id=PARENT,
        root_turn_id=TURN,
    )


def _result_event(status: str = "completed", message: str | None = CLAIMS) -> dict:
    return {
        "type": "codex_subagent_result",
        "agentThreadId": CHILD,
        "status": status,
        "message": message,
    }


def test_v2_subagent_activity_is_normalized_from_stream_and_rollout_spellings() -> None:
    stream = _normalise_app_server_event(FIXTURE["notifications"][0])
    rollout = _normalise_app_server_event(
        {"method": "item/completed", "params": {"item": FIXTURE["rollout_subagent_item"]}}
    )

    for normalized in (stream, rollout):
        assert normalized["item"]["type"] == "sub_agent_activity"
        assert normalized["item"]["kind"] == "started"
        assert normalized["item"]["agentThreadId"] == CHILD
        assert normalized["item"]["agentPath"] == FIXTURE["child_agent_path"]


def test_v2_reviewer_records_child_id_and_terminal_claims_from_the_child_thread() -> None:
    result, _ = _parse([*FIXTURE["notifications"], _result_event()])

    agents = [call for call in result.tool_calls if call.name == "Agent"]
    assert len(agents) == 1
    call = agents[0]
    assert call.arguments["subagent_type"] == "general-purpose"
    assert call.arguments["codex_collaboration"] == "multi_agent_v2"
    assert call.arguments["codex_child_thread_id"] == CHILD
    assert call.arguments["codex_agent_path"] == FIXTURE["child_agent_path"]
    assert call.result == {"is_error": False, "content": [CLAIMS]}
    assert result.environment_detail is None
    assert result.terminal_result_subtype == "success"


def test_v2_reviewer_prompt_is_not_invented_so_the_dispatch_gate_stays_closed() -> None:
    """The v2 spawn message is encrypted; the canonical gate must not credit it."""

    assert FIXTURE["model_function_calls"]["spawn_agent"]["arguments"]["message"].startswith(
        "gAAAA"
    )
    result, _ = _parse([*FIXTURE["notifications"], _result_event()])
    call = next(call for call in result.tool_calls if call.name == "Agent")

    assert call.arguments["prompt"] is None
    assert call.arguments["prompt_observable"] is False
    assert (
        _completed_review_delegation(
            {"arguments": call.arguments, "result": call.result},
            position=None,  # type: ignore[arg-type]
        )
        is None
    )


def test_v2_child_without_claims_is_recorded_as_an_incomplete_handoff() -> None:
    for extra in ([], [_result_event(status="unavailable", message=None)]):
        result, _ = _parse([*FIXTURE["notifications"], *extra])

        call = next(call for call in result.tool_calls if call.name == "Agent")
        assert call.result == {"is_error": True, "content": []}
        assert "Codex reviewer child had no matching completion" in (
            result.environment_detail or ""
        )
        assert "multi_agent_v2" in (result.environment_detail or "")


def test_v2_result_for_a_child_not_started_on_this_turn_is_ignored() -> None:
    unrelated = {**_result_event(), "agentThreadId": "some-other-thread"}
    result, _ = _parse([FIXTURE["notifications"][-1], unrelated])

    assert [call for call in result.tool_calls if call.name == "Agent"] == []


def test_v2_reviewer_deadline_arms_at_spawn_and_clears_at_child_completion() -> None:
    receivers: set[str] = set()
    deadline = None
    armed = None
    for offset, event in enumerate(FIXTURE["notifications"]):
        receivers, deadline = _update_reviewer_deadline(
            _normalise_app_server_event(event),
            receivers,
            deadline,
            now=100.0 + offset,
            review_deadline_ms=600_000.0,
        )
        if offset == 0:
            armed = deadline
        if event["method"] == "item/started" and event["params"]["item"].get("tool") == "wait":
            # A v2 wait names no receivers; it neither clears nor re-arms.
            assert deadline == armed

    assert armed == 100.0 + 600.0
    assert deadline is None
    assert receivers == set()


def test_v2_wait_without_receivers_completes_the_turn_instead_of_failing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = object.__new__(CodexAdapter)
    adapter.timeout_s = 1000.0
    adapter._review_deadline_ms = 600_000.0
    adapter.review_timeout_seconds = 600.0
    adapter._thread_id = PARENT
    adapter._read_until_response = lambda *_args, **_kwargs: (
        {"result": {"turn": {"id": TURN}}},
        [],
    )
    adapter._is_server_request = lambda _event: False
    reads = iter(FIXTURE["notifications"])
    adapter._read_streams = lambda _deadline: next(reads)
    monkeypatch.setattr(
        "dp_scenarios.runner.codex_adapter.time.monotonic", lambda: 10.0
    )

    events = adapter._collect_turn(1, "", [])

    assert events[-1]["type"] == "turn.completed"
    assert events[-1]["turn_id"] == TURN


def _reading_adapter(responses: dict[str, object]) -> CodexAdapter:
    adapter = object.__new__(CodexAdapter)
    adapter._thread_id = PARENT
    calls: list[tuple[str, dict]] = []

    def rpc(method, params):
        calls.append((method, dict(params)))
        value = responses.get(method)
        return value() if callable(value) else value

    adapter._subagent_rpc = rpc
    adapter.calls = calls
    return adapter


def test_v2_child_claims_are_read_from_the_recorded_child_thread() -> None:
    adapter = _reading_adapter(
        {
            "thread/read": FIXTURE["child_thread_read"],
            "thread/turns/list": FIXTURE["child_turns_list"],
        }
    )

    results = adapter._subagent_results(FIXTURE["notifications"])

    assert results == [_result_event()]
    assert adapter.calls[0] == ("thread/read", {"threadId": CHILD, "includeTurns": False})
    assert adapter.calls[1][0] == "thread/turns/list"
    assert adapter.calls[1][1]["threadId"] == CHILD
    assert adapter.calls[1][1]["itemsView"] == "full"


def test_v2_child_thread_of_another_parent_is_not_bound() -> None:
    foreign = json.loads(json.dumps(FIXTURE["child_thread_read"]))
    foreign["thread"]["parentThreadId"] = "another-parent"
    adapter = _reading_adapter(
        {"thread/read": foreign, "thread/turns/list": FIXTURE["child_turns_list"]}
    )

    [result] = adapter._subagent_results(FIXTURE["notifications"])

    assert result["status"] == "unrelated"
    assert result["message"] is None
    assert [method for method, _ in adapter.calls] == ["thread/read"]


def test_v2_child_still_running_or_unreadable_yields_no_claims() -> None:
    running = {"data": [{"id": "t", "status": "inProgress", "items": []}]}
    adapter = _reading_adapter(
        {"thread/read": FIXTURE["child_thread_read"], "thread/turns/list": running}
    )
    [result] = adapter._subagent_results(FIXTURE["notifications"])
    assert (result["status"], result["message"]) == ("running", None)

    def unreadable():
        raise TimeoutError("Codex app-server response deadline expired")

    adapter = _reading_adapter({"thread/read": unreadable})
    [result] = adapter._subagent_results(FIXTURE["notifications"])
    assert (result["status"], result["message"]) == ("unavailable", None)


def test_codex_prompt_describes_the_v2_collaboration_schema() -> None:
    prompt = " ".join(CODEX_SYSTEM_PROMPT.split())

    assert "`spawn_agent` and `wait_agent` in the `collaboration` namespace" in prompt
    assert "no v2 collaboration tool accepts a `targets` argument" in prompt
    assert (
        '`{"task_name":"<lowercase_with_underscores>","fork_turns":"none","message":"<complete review request>"}`'
        in prompt
    )
    assert 'call `wait_agent` with only `{"timeout_ms":<milliseconds>}`' in prompt
    assert "never with `targets`, `target`, `ids`, or a task name" in prompt
    assert "`FINAL_ANSWER` message" in prompt
    assert "apply only to the v1 runtime" in prompt


def test_codex_base_instructions_state_the_reviewer_deadline(tmp_path: Path) -> None:
    adapter = object.__new__(CodexAdapter)
    adapter.append_system_prompt = CODEX_SYSTEM_PROMPT
    adapter.skill_pack_root = tmp_path
    adapter.review_timeout_seconds = 600.0

    assert "reviewer deadline for this run is 600000 milliseconds" in (
        adapter._base_instructions()
    )


def _host_catalog(tmp_path: Path) -> Path:
    host = tmp_path / "host-codex-home"
    host.mkdir()
    (host / "models_cache.json").write_text(
        json.dumps(
            {
                "fetched_at": "2026-09-27T00:00:00Z",
                "etag": "x",
                "models": [
                    {"slug": "gpt-6-luna", "multi_agent_version": "v2", "tool_mode": "code_mode_only"},
                    {"slug": "gpt-6-sol", "multi_agent_version": "v2"},
                ],
            }
        ),
        encoding="utf-8",
    )
    return host


def test_forced_v1_catalog_changes_only_the_selected_models_runtime(tmp_path: Path) -> None:
    host = _host_catalog(tmp_path)
    home = tmp_path / "run-codex-home"
    home.mkdir()

    path = _write_multi_agent_v1_catalog(str(host), home, model="gpt-6-luna")

    assert path == home / MODEL_CATALOG_FILENAME
    assert path.stat().st_mode & 0o077 == 0
    catalog = json.loads(path.read_text(encoding="utf-8"))
    assert catalog == {
        "models": [
            {"slug": "gpt-6-luna", "multi_agent_version": "v1", "tool_mode": "code_mode_only"},
            {"slug": "gpt-6-sol", "multi_agent_version": "v2"},
        ]
    }


def test_forced_v1_catalog_fails_closed_without_a_host_entry(tmp_path: Path) -> None:
    host = _host_catalog(tmp_path)
    home = tmp_path / "run-codex-home"
    home.mkdir()

    with pytest.raises(CodexAdapterError, match="no entry for model"):
        _write_multi_agent_v1_catalog(str(host), home, model="gpt-7")
    with pytest.raises(CodexAdapterError, match="host CODEX_HOME"):
        _write_multi_agent_v1_catalog(None, home, model="gpt-6-luna")
    with pytest.raises(CodexAdapterError, match="unreadable"):
        _write_multi_agent_v1_catalog(str(tmp_path / "missing"), home, model="gpt-6-luna")


def test_forced_v1_catalog_reaches_the_app_server_command(tmp_path: Path) -> None:
    adapter = object.__new__(CodexAdapter)
    adapter.codex = Path("/usr/bin/codex")
    adapter.effort = "xhigh"
    adapter.multi_agent_v2 = False
    adapter._model_catalog_path = tmp_path / MODEL_CATALOG_FILENAME
    adapter._mcp_server_config = lambda: {"command": "python3", "args": [], "env": {}}

    command = adapter._app_server_command()

    flag = f'model_catalog_json="{tmp_path / MODEL_CATALOG_FILENAME}"'
    assert command[command.index(flag) - 1] == "-c"

    adapter._model_catalog_path = None
    assert not any("model_catalog_json" in part for part in adapter._app_server_command())


def test_forced_v1_and_multi_agent_v2_are_mutually_exclusive(tmp_path: Path) -> None:
    with pytest.raises(CodexAdapterError, match="cannot be combined"):
        CodexAdapter(
            codex=tmp_path / "codex",
            model="gpt-6-luna",
            effort="xhigh",
            skill_pack_root=tmp_path,
            repo_root=Path(__file__).resolve().parents[3],
            fixture_dir=tmp_path,
            artifact_dir=tmp_path,
            desktop_supervisor=tmp_path / "supervisor",
            desktop_python=tmp_path / "python",
            timeout_s=60.0,
            append_system_prompt="",
            multi_agent_v2=True,
            force_multi_agent_v1=True,
        )
