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
    CODEX_FILE_CHANGE_FAILURE,
    CodexAdapter,
    CodexAdapterError,
    _COLLAB_FAILURE_STATUSES,
    _event_debug_tail,
    _codex_timeout_failure_reason,
    _review_pending_after_observations,
    _reviewer_wait_without_target,
    _turn_sandbox_policy,
    _update_reviewer_deadline,
    _update_reviewer_deadline_from_events,
    _load_mcp_server,
    parse_codex_events,
)
from dp_scenarios.failure_reasons import (
    CHILD_NO_TERMINAL_RESULT,
    CODEX_ROOT_TURN_NO_TERMINAL_RESULT,
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
    assert "bounded per retained capture" in CODEX_SYSTEM_PROMPT
    assert "the per-capture limit resets" in CODEX_SYSTEM_PROMPT
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
    assert "exact receiver thread id in its `target` argument" in CODEX_SYSTEM_PROMPT
    assert "wait` reports the child as completed but returns no non-empty message" in CODEX_SYSTEM_PROMPT
    assert "issue `wait` once more with the same target" in CODEX_SYSTEM_PROMPT
    assert "missing child claims" in CODEX_SYSTEM_PROMPT
    assert "threads remain allocated to the app-server" in CODEX_SYSTEM_PROMPT
    assert "captured inputs are immutable" in CODEX_SYSTEM_PROMPT
    assert "only a clear report authorizes" in CODEX_SYSTEM_PROMPT
    assert "end that turn with a direct question" in CODEX_SYSTEM_PROMPT
    assert "specific authorization" in CODEX_SYSTEM_PROMPT
    assert "end the" in CODEX_SYSTEM_PROMPT
    assert "same turn" in CODEX_SYSTEM_PROMPT
    assert "immediately using the returned receiver thread id" in CODEX_SYSTEM_PROMPT
    assert "Do not call `sendInput` or `resumeAgent`" in CODEX_SYSTEM_PROMPT
    assert "exactly one `message` string" in CODEX_SYSTEM_PROMPT
    assert "Never send both `message` and `items`" in CODEX_SYSTEM_PROMPT
    assert "same supervisor response under" in CODEX_SYSTEM_PROMPT
    assert "Do not call `list_mcp_resources`" in CODEX_SYSTEM_PROMPT
    assert "owning parent’s one-shot reviewer lifecycle" in CODEX_SYSTEM_PROMPT
    assert "reviewer child\nmay use only its allowed read-only inspection tools" in CODEX_SYSTEM_PROMPT
    assert "mcp__nxd-desktop__read_review_input" in CODEX_SYSTEM_PROMPT
    assert "bounded read/list surface" in CODEX_SYSTEM_PROMPT
    assert "sensitive files" in CODEX_SYSTEM_PROMPT
    assert "return an incomplete blocker" in CODEX_SYSTEM_PROMPT
    assert "Review-repair discipline" in CODEX_SYSTEM_PROMPT
    assert "an unchanged closure for another review" in CODEX_SYSTEM_PROMPT
    assert "do not call Bash" in CODEX_SYSTEM_PROMPT
    assert "do not call Bash, codex_file_change" not in CODEX_SYSTEM_PROMPT
    assert "exact `*** Begin Patch`" in CODEX_SYSTEM_PROMPT
    assert "partial evidenced claims" in CODEX_SYSTEM_PROMPT
    assert "prefix every changed line" in CODEX_SYSTEM_PROMPT
    assert "`+`" in CODEX_SYSTEM_PROMPT and "`-`" in CODEX_SYSTEM_PROMPT
    assert "Only use\ninspect_prepare_recovery" in CODEX_SYSTEM_PROMPT
    assert "the next supervisor action must be that report" in CODEX_SYSTEM_PROMPT
    assert "Do not call reset_workflow, list_data_products, inspect_workflow," in CODEX_SYSTEM_PROMPT
    assert '"workflow already exists" and active-workflow' in CODEX_SYSTEM_PROMPT
    assert "errors are non-retryable" in CODEX_SYSTEM_PROMPT
    assert "supplied source export for a\nfile-backed scenario" in CODEX_SYSTEM_PROMPT
    assert "NXD_EVAL_FIXTURE_DIR" in CODEX_SYSTEM_PROMPT
    assert "file-backed scenario is not expected to have an `infra-profile.yaml`" in CODEX_SYSTEM_PROMPT
    assert "do not invoke or simulate a shell `apply_patch` command" in CODEX_SYSTEM_PROMPT
    assert "bare dependency, YAML, or JSON line as a patch header" in CODEX_SYSTEM_PROMPT
    assert "treat that as an edit-syntax failure" in CODEX_SYSTEM_PROMPT
    assert "retry once with a complete valid file-change operation" in CODEX_SYSTEM_PROMPT
    assert "do not report an environment" in CODEX_SYSTEM_PROMPT
    assert "corrected operation is rejected too" in CODEX_SYSTEM_PROMPT


def test_review_child_prompt_describes_the_runtime_read_only_boundary() -> None:
    assert "enforced read-only sandbox" in CODEX_SYSTEM_PROMPT
    assert "network access disabled" in CODEX_SYSTEM_PROMPT


def test_capture_review_pending_switches_the_next_turn_to_read_only() -> None:
    capture = {
        "tool": "mcp__nxd-desktop__advance_workflow",
        "arguments": {"action": {"type": "capture"}},
        "result": {
            "requirements": [
                {"id": "review", "status": "pending", "review_input": {}},
            ]
        },
        "is_error": False,
    }
    assert _review_pending_after_observations((capture,), False) is True
    assert _turn_sandbox_policy(True, ("/workspace",)) == {"type": "readOnly"}


def test_successful_review_report_restores_workspace_write_for_follow_up_turn() -> None:
    report = {
        "tool": "mcp__nxd-desktop__advance_workflow",
        "arguments": {
            "action": {"type": "report_requirement", "requirement_id": "review"}
        },
        "result": {"status": "clear"},
        "is_error": False,
    }
    assert _review_pending_after_observations((report,), True) is False
    assert _turn_sandbox_policy(False, ("/workspace", "/skills")) == {
        "type": "workspaceWrite",
        "writableRoots": ["/workspace", "/skills"],
    }


def test_non_review_requirement_report_does_not_clear_review_lock() -> None:
    report = {
        "tool": "mcp__nxd-desktop__advance_workflow",
        "arguments": {
            "action": {"type": "report_requirement", "requirement_id": "capture"}
        },
        "result": {"status": "complete"},
        "is_error": False,
    }
    assert _review_pending_after_observations((report,), True) is True


def test_codex_turn_prompt_names_the_run_local_fixture_root(tmp_path: Path) -> None:
    adapter = object.__new__(CodexAdapter)
    adapter.fixture_dir = tmp_path / "fixture"

    prompt = adapter._prompt("Inspect the supplied source.", ())

    assert f"NXD_EVAL_FIXTURE_DIR={adapter.fixture_dir}" in prompt
    assert "read only the supplied input files" in prompt
    assert "do not use oracle or gold files" in prompt
    assert "Parent-thread file-change reminder" in prompt
    assert "never forward this paragraph" in prompt
    assert "one complete Add File operation" in prompt
    assert "raw file contents in patch metadata" in prompt
    assert "correct the patch envelope" in prompt
    assert "corrected operation is rejected too" in prompt
    assert "report the blocker rather than retrying malformed patch syntax" not in prompt


def test_codex_reviewer_terminal_statuses_include_timeout_and_cancellation() -> None:
    assert {
        "timedOut",
        "timed_out",
        "timeout",
        "cancelled",
        "canceled",
    } <= _COLLAB_FAILURE_STATUSES


def test_codex_reviewer_deadline_is_armed_on_spawn_start_with_receiver_id() -> None:
    spawn = {
        "type": "item.started",
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


def test_codex_reviewer_deadline_started_without_ids_merges_completion_ids() -> None:
    started = {
        "type": "item.started",
        "item": {
            "type": "collab_agent_tool_call",
            "tool": "spawnAgent",
        },
    }
    receiver_ids, deadline = _update_reviewer_deadline(
        started, set(), None, now=10.0
    )
    assert receiver_ids == set()
    assert deadline == pytest.approx(10.0 + REVIEW_DEADLINE_MS / 1000.0)

    completed = {
        "type": "item.completed",
        "item": {
            "type": "collab_agent_tool_call",
            "tool": "spawnAgent",
            "receiverThreadIds": ["child-1"],
        },
    }
    receiver_ids, completed_deadline = _update_reviewer_deadline(
        completed, receiver_ids, deadline, now=20.0
    )
    assert receiver_ids == {"child-1"}
    assert completed_deadline == deadline


def test_codex_reviewer_deadline_uses_configured_timeout() -> None:
    spawn = {
        "type": "item.started",
        "item": {
            "type": "collabAgentToolCall",
            "tool": "spawnAgent",
            "receiverThreadIds": ["child-1"],
        },
    }

    receiver_ids, deadline = _update_reviewer_deadline(
        spawn,
        set(),
        None,
        now=10.0,
        review_deadline_ms=2_500.0,
    )

    assert receiver_ids == {"child-1"}
    assert deadline == pytest.approx(12.5)


def test_codex_reviewer_deadline_arms_on_pending_init_without_receiver_id() -> None:
    completed = {
        "type": "item.completed",
        "item": {
            "type": "collab_agent_tool_call",
            "tool": "spawnAgent",
            "status": "completed",
            "agentsStates": {"pending": {"status": "pendingInit"}},
        },
    }

    receiver_ids, deadline = _update_reviewer_deadline(
        completed, set(), None, now=10.0
    )

    assert receiver_ids == set()
    assert deadline == pytest.approx(10.0 + REVIEW_DEADLINE_MS / 1000.0)


def test_codex_reviewer_deadline_processes_events_buffered_with_turn_start() -> None:
    events = [
        {
            "method": "item/started",
            "params": {
                "item": {
                    "type": "collabAgentToolCall",
                    "tool": "spawnAgent",
                    "receiverThreadIds": ["child-1"],
                }
            },
        }
    ]

    receiver_ids, deadline = _update_reviewer_deadline_from_events(
        events,
        set(),
        None,
        now=10.0,
    )

    assert receiver_ids == {"child-1"}
    assert deadline == pytest.approx(10.0 + REVIEW_DEADLINE_MS / 1000.0)


def test_codex_reviewer_deadline_stays_armed_when_close_precedes_claims() -> None:
    receiver_ids = {"child-1"}
    deadline = 10.0 + REVIEW_DEADLINE_MS / 1000.0
    close = {
        "type": "item.completed",
        "item": {
            "type": "collab_agent_tool_call",
            "tool": "closeAgent",
            "receiverThreadId": "child-1",
        },
    }
    assert _update_reviewer_deadline(close, receiver_ids, deadline, now=20.0) == (
        receiver_ids,
        deadline,
    )


def test_reviewer_wait_without_target_is_fail_closed() -> None:
    wait = {
        "type": "item.completed",
        "item": {
            "type": "collab_agent_tool_call",
            "tool": "wait",
        },
    }
    # A completed wait item can be an intermediate app-server spelling that
    # has not yet carried the child target or terminal state.  The turn-level
    # pending-child check remains fail-closed at the actual turn boundary.
    assert _reviewer_wait_without_target(wait, True) is False
    assert _reviewer_wait_without_target(wait, False) is False


def test_reviewer_wait_without_target_is_fatal_only_with_explicit_failure() -> None:
    wait = {
        "type": "item.completed",
        "item": {
            "type": "collab_agent_tool_call",
            "tool": "wait",
            "status": "failed",
        },
    }
    assert _reviewer_wait_without_target(wait, True) is True
def test_codex_reviewer_deadline_wins_when_stream_read_reaches_it(monkeypatch) -> None:
    adapter = object.__new__(CodexAdapter)
    adapter.timeout_s = 1000.0
    adapter._read_until_response = lambda *_args, **_kwargs: (
        {"result": {"turn": {"id": "root-turn"}}},
        [],
    )
    adapter._is_server_request = lambda _event: False

    spawn_started = {
        "method": "item/started",
        "params": {
            "item": {
                "type": "collabAgentToolCall",
                "tool": "spawnAgent",
                "receiverThreadIds": ["child-1"],
            }
        },
    }
    reads = iter((spawn_started, TimeoutError("stream deadline")))

    def read_streams(_deadline):
        value = next(reads)
        if isinstance(value, BaseException):
            raise value
        return value

    adapter._read_streams = read_streams
    clock = iter((0.0, 0.0, 0.0, REVIEW_DEADLINE_MS / 1000.0 + 1.0))
    monkeypatch.setattr(
        "dp_scenarios.runner.codex_adapter.time.monotonic", lambda: next(clock)
    )

    with pytest.raises(TimeoutError, match="reviewer deadline"):
        adapter._collect_turn(1, "", [])


def test_codex_reviewer_deadline_wins_for_spawn_buffered_with_turn_start(monkeypatch) -> None:
    adapter = object.__new__(CodexAdapter)
    adapter.timeout_s = 1000.0
    spawn_started = {
        "method": "item/started",
        "params": {
            "item": {
                "type": "collabAgentToolCall",
                "tool": "spawnAgent",
                "receiverThreadIds": ["child-1"],
            }
        },
    }
    adapter._read_until_response = lambda *_args, **_kwargs: (
        {"result": {"turn": {"id": "root-turn"}}},
        [spawn_started],
    )
    adapter._is_server_request = lambda _event: False

    def read_streams(_deadline):
        raise TimeoutError("stream deadline")

    adapter._read_streams = read_streams
    clock = iter((0.0, 0.0, 0.0, REVIEW_DEADLINE_MS / 1000.0 + 1.0))
    monkeypatch.setattr(
        "dp_scenarios.runner.codex_adapter.time.monotonic", lambda: next(clock)
    )

    with pytest.raises(TimeoutError, match="reviewer deadline"):
        adapter._collect_turn(1, "", [])


def test_codex_turn_deadline_wins_when_nonterminal_events_keep_arriving(monkeypatch) -> None:
    adapter = object.__new__(CodexAdapter)
    adapter.timeout_s = 1.0
    adapter._read_until_response = lambda *_args, **_kwargs: (
        {"result": {"turn": {"id": "root-turn"}}},
        [],
    )
    adapter._is_server_request = lambda _event: False
    adapter._read_streams = lambda _deadline: {
        "method": "thread/tokenUsage/updated",
        "params": {},
    }
    clock = iter((0.0, 0.0, 2.0, 2.0, 2.0))
    monkeypatch.setattr(
        "dp_scenarios.runner.codex_adapter.time.monotonic", lambda: next(clock)
    )

    with pytest.raises(TimeoutError, match="turn deadline"):
        adapter._collect_turn(1, "", [])


def test_codex_root_turn_timeout_is_not_reported_as_a_child_timeout() -> None:
    assert (
        _codex_timeout_failure_reason(
            TimeoutError("Codex app-server turn deadline expired"),
            "",
            root_turn_id="root-turn",
        )
        == CODEX_ROOT_TURN_NO_TERMINAL_RESULT
    )


def test_codex_reviewer_timeout_keeps_the_child_timeout_reason() -> None:
    assert (
        _codex_timeout_failure_reason(
            TimeoutError("Codex reviewer child did not complete before the 300.0-second reviewer deadline"),
            "",
            root_turn_id="root-turn",
        )
        == CHILD_NO_TERMINAL_RESULT
    )


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
    assert result.provider_model_calls == 1
    assert result.input_tokens == 3
    assert result.output_tokens == 2
    assert result.last_mcp_call == "advance_workflow:ok"
    assert result.tool_calls[0].name == "mcp__nxd-desktop__advance_workflow"
    assert observations[0]["tool"] == "advance_workflow"
    assert observations[0]["result"] == {"admission": {"run_id": "run-1"}}


def test_parse_codex_file_change_rejection_is_recoverable_without_raw_error() -> None:
    result, observations = parse_codex_events(
        [
            {
                "type": "item.completed",
                "item": {
                    "type": "file_change",
                    "status": "failed",
                    "error": "raw patch content must not become a diagnostic",
                },
            },
            {"type": "turn.completed", "turn_id": "root-turn", "is_error": False},
        ],
        redact_json_rpc=_identity,
        redact_text=_identity,
        session_id="session-1",
        root_turn_id="root-turn",
    )

    assert observations == []
    assert result.environment_wedged is False
    assert result.environment_detail is None
    assert CODEX_FILE_CHANGE_FAILURE in result.transcript_delta
    assert result.tool_calls[0].result == {"status": "failed", "is_error": True}


def test_parse_codex_events_counts_only_root_turn_completion() -> None:
    result, _ = parse_codex_events(
        [
            {
                "method": "turn/completed",
                "params": {"turn": {"id": "child-turn", "status": "completed"}},
            },
            {
                "method": "turn/completed",
                "params": {"turn": {"id": "root-turn", "status": "completed"}},
            },
        ],
        redact_json_rpc=_identity,
        redact_text=lambda value: value,
        session_id="thread-1",
        root_turn_id="root-turn",
    )

    assert result.terminal_result_count == 1
    assert result.terminal_result_subtype == "success"
    assert result.terminal_result_is_error is False


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
    assert "status=completed" in (result.environment_detail or "")
    assert "child_status=running" in (result.environment_detail or "")


def test_event_debug_tail_keeps_reviewer_lifecycle_when_tail_has_later_events() -> None:
    detail = _event_debug_tail(
        [
            {
                "method": "item/completed",
                "params": {
                    "item": {
                        "type": "collabAgentToolCall",
                        "tool": "spawnAgent",
                        "status": "completed",
                        "agentsStates": {
                            "child-1": {"status": "running", "message": None}
                        },
                    }
                },
            },
            *[
                {"method": "thread/tokenUsage/updated", "params": {}}
                for _ in range(12)
            ],
        ],
        limit=3,
    )

    assert detail is not None
    assert "reviewer=tool=spawnAgent,status=completed,child_status=running" in detail


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
    assert adapter.review_timeout_seconds == pytest.approx(REVIEW_DEADLINE_MS / 1000.0)

    app_command = adapter._app_server_command()
    assert app_command[:3] == ["/bin/true", "app-server", "--stdio"]
    assert app_command[3:5] == ["--enable", "multi_agent"]
    assert 'mcp_servers.nxd-desktop.command="/bin/echo"' in app_command
    assert 'mcp_servers.nxd-desktop.args=["--proxy", "server-spec.json"]' in app_command
    assert 'mcp_servers.nxd-desktop.default_tools_approval_mode="approve"' in app_command
    assert "mcp_servers.nxd-desktop.required=true" in app_command
    assert "mcp_servers.nxd-desktop.startup_timeout_sec=30" in app_command

    v2_adapter = CodexAdapter(
        codex=Path("/bin/true"),
        model="gpt-5.6-sol",
        effort="ultra",
        skill_pack_root=REPO_ROOT,
        repo_root=REPO_ROOT,
        fixture_dir=tmp_path,
        artifact_dir=tmp_path / "artifacts-v2",
        desktop_supervisor=Path("/bin/true"),
        desktop_python=Path("/bin/true"),
        timeout_s=5,
        append_system_prompt="test",
        mcp_config=config_path,
        strict_mcp_config=True,
        supervisor_data_dir=tmp_path,
        multi_agent_v2=True,
    )
    v2_command = v2_adapter._app_server_command()
    assert v2_command[3:7] == ["--enable", "multi_agent_v2", "--enable", "multi_agent"]


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
    assert turn_params["input"][0]["type"] == "text"
    assert turn_params["input"][0]["text"].startswith("hello\n\nRun-local source handoff:")
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

    import dp_scenarios.runner.codex_adapter as codex_adapter_module

    original_snapshot = codex_adapter_module._snapshot_workspace
    snapshot_calls = 0

    def snapshot_once(*args, **kwargs):
        nonlocal snapshot_calls
        snapshot_calls += 1
        if snapshot_calls > 1:
            raise AssertionError("timeout finalization performed an unbounded workspace scan")
        return original_snapshot(*args, **kwargs)

    monkeypatch.setattr(codex_adapter_module, "_snapshot_workspace", snapshot_once)

    result = adapter.send({"message": {"text": "one", "attachments": []}})
    adapter.close()

    assert result.turn_timed_out is True
    assert result.failure_reason == CODEX_ROOT_TURN_NO_TERMINAL_RESULT
    assert result.session_id == "00000000-0000-4000-8000-000000000020"
    assert result.agent_message == "partial"
    assert result.last_mcp_call == "inspect_run:unanswered"
    assert "event_tail=item/started[mcpToolCall]:nxd-desktop/inspect_run=inProgress" in (
        result.environment_detail or ""
    )
