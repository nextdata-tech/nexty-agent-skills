"""Unit tests for the run-scoped workflow-v2 review handoff guard."""

from __future__ import annotations

import json
from pathlib import Path

from dp_scenarios.runner.review_guard import (
    NORMAL,
    RELAY_PENDING,
    REVIEW_DISPATCH_PENDING,
    handle_event,
    settings_payload,
    write_initial_state,
)


def _state(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _capture_event() -> dict[str, object]:
    return {
        "hook_event_name": "PostToolUse",
        "tool_name": "mcp__nxd-desktop__advance_workflow",
        "session_id": "owner-session",
        "tool_input": {
            "workflow": "sales",
            "expected_revision": 7,
            "action": {"type": "capture", "parameters": {"requirement_id": "capture"}},
        },
        "tool_result": {
            "is_error": False,
            "content": {
                "workflow": "sales",
                "revision": 8,
                "next_actions": [
                    {
                        "action": "report_requirement",
                        "requirement_id": "review",
                        "generation": 4,
                        "subject_sha256": "sha256:subject",
                        "dependency_evidence_sha256": "sha256:dependency",
                    }
                ],
            },
        },
    }


def _marker() -> str:
    return (
        'NXD_REVIEW_DISPATCH {"closure_path":"closure",'
        '"request_contract":"sanitized_original_request",'
        '"return":"claims_only","review_round_index":0}'
    )


def _report_input() -> dict[str, object]:
    return {
        "workflow": "sales",
        "expected_revision": 8,
        "action": {
            "type": "report_requirement",
            "parameters": {
                "requirement_id": "review",
                "generation": 4,
                "subject_sha256": "sha256:subject",
                "dependency_evidence_sha256": "sha256:dependency",
                "session_ref": "review-session",
                "message_ref": None,
                "report": {
                    "schema": "nxd-conversation-review-v1",
                    "verdict": "clear",
                    "findings": [],
                },
            },
        },
    }


def test_capture_to_report_is_owner_scoped_and_clears_only_on_matching_response(tmp_path: Path) -> None:
    state_path = tmp_path / "guard-state.json"
    workspace = tmp_path / "agent"
    workspace.mkdir()
    write_initial_state(state_path, workspace_root=workspace)

    assert handle_event(_capture_event(), state_path=state_path) == {}
    assert _state(state_path)["state"] == REVIEW_DISPATCH_PENDING

    dispatch = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Agent",
        "tool_use_id": "review-tool",
        "tool_input": {"subagent_type": "general-purpose", "prompt": _marker()},
    }
    dispatch_decision = handle_event(dispatch, state_path=state_path)
    assert dispatch_decision == {}

    owner_parallel = handle_event(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Read",
            "session_id": "owner-session",
            "tool_input": {"file_path": "/captured/closure"},
        },
        state_path=state_path,
    )
    assert owner_parallel["hookSpecificOutput"]["permissionDecision"] == "deny"

    child_read = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Read",
        "agent_id": "review-agent",
        "session_id": "review-session",
        "tool_input": {"file_path": "/captured/closure"},
    }
    assert handle_event(child_read, state_path=state_path) == {}

    child_skill = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Skill",
        "agent_id": "review-agent",
        "session_id": "review-session",
        "tool_input": {"skill": "nxd-review-closure"},
    }
    assert handle_event(child_skill, state_path=state_path) == {}

    nested_dispatch = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Agent",
        "agent_id": "review-agent",
        "session_id": "review-session",
        "tool_input": {"subagent_type": "general-purpose", "prompt": _marker()},
    }
    nested_decision = handle_event(nested_dispatch, state_path=state_path)
    assert nested_decision["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "another conversation child" in nested_decision["hookSpecificOutput"]["permissionDecisionReason"]

    child_workflow = {
        "hook_event_name": "PreToolUse",
        "tool_name": "mcp__nxd-desktop__advance_workflow",
        "agent_id": "review-agent",
        "session_id": "review-session",
        "tool_input": {},
    }
    assert handle_event(child_workflow, state_path=state_path)["hookSpecificOutput"]["permissionDecision"] == "deny"

    child_result = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Agent",
        "tool_use_id": "review-tool",
        "tool_result": {"is_error": False, "content": "bounded claims"},
    }
    assert handle_event(child_result, state_path=state_path) == {}
    assert _state(state_path)["state"] == RELAY_PENDING

    denied = handle_event(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Read",
            "agent_id": "owner-agent",
            "tool_input": {"file_path": "/captured/closure"},
        },
        state_path=state_path,
    )
    assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"

    review_record = workspace / "nxd-jobs" / "sales" / "review-record.json"
    assert handle_event(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "agent_id": "owner-agent",
            "tool_input": {"file_path": str(review_record), "content": "{}"},
        },
        state_path=state_path,
    ) == {}
    assert handle_event(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "agent_id": "owner-agent",
            "tool_input": {"file_path": str(workspace / "closure" / "review-record.json")},
        },
        state_path=state_path,
    )["hookSpecificOutput"]["permissionDecision"] == "deny"

    report = _report_input()
    report["tool_use_id"] = "report-tool"
    report_pre = {
        "hook_event_name": "PreToolUse",
        "tool_name": "mcp__nxd-desktop__advance_workflow",
        "tool_use_id": "report-tool",
        "agent_id": "owner-agent",
        "tool_input": _report_input(),
    }
    assert handle_event(report_pre, state_path=state_path) == {}
    assert _state(state_path)["state"] != NORMAL

    report_post = {
        "hook_event_name": "PostToolUse",
        "tool_name": "mcp__nxd-desktop__advance_workflow",
        "tool_use_id": "report-tool",
        "agent_id": "owner-agent",
        "tool_input": _report_input(),
        "tool_result": {
            "is_error": False,
            "content": {
                "operation": {
                    "operation_id": "op-1",
                    "workflow": "sales",
                    "status": "succeeded",
                    "binding": {
                        "requirement_id": "review",
                        "generation": 4,
                        "subject_sha256": "sha256:subject",
                        "dependency_evidence_sha256": "sha256:dependency",
                    },
                },
                "events": [
                    {"operation_id": "op-1", "code": "workflow/review_satisfied"}
                ],
            },
        },
    }
    assert handle_event(report_post, state_path=state_path) == {}
    assert _state(state_path)["state"] == NORMAL


def test_async_agent_launch_does_not_satisfy_the_review_dispatch(tmp_path: Path) -> None:
    state_path = tmp_path / "guard-state.json"
    workspace = tmp_path / "agent"
    workspace.mkdir()
    write_initial_state(state_path, workspace_root=workspace)
    handle_event(_capture_event(), state_path=state_path)
    handle_event(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Agent",
            "tool_use_id": "review-tool",
            "session_id": "owner-session",
            "tool_input": {"subagent_type": "general-purpose", "prompt": _marker()},
        },
        state_path=state_path,
    )

    result = handle_event(
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "Agent",
            "tool_use_id": "review-tool",
            "session_id": "owner-session",
            "tool_response": {
                "status": "async_launched",
                "agent_id": "review-agent",
            },
        },
        state_path=state_path,
    )

    assert result == {}
    assert _state(state_path)["state"] == REVIEW_DISPATCH_PENDING


def test_qualified_review_skill_name_is_allowed_but_other_forms_are_rejected(tmp_path: Path) -> None:
    state_path = tmp_path / "guard-state.json"
    workspace = tmp_path / "agent"
    workspace.mkdir()
    write_initial_state(state_path, workspace_root=workspace)
    handle_event(_capture_event(), state_path=state_path)
    handle_event(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Agent",
            "tool_use_id": "review-tool",
            "session_id": "owner-session",
            "tool_input": {"subagent_type": "general-purpose", "prompt": _marker()},
        },
        state_path=state_path,
    )

    qualified = handle_event(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Skill",
            "agent_id": "review-agent",
            "session_id": "review-session",
            "tool_input": {"skill": "nexty-agent-skills:nxd-review-closure"},
        },
        state_path=state_path,
    )
    assert qualified == {}

    for skill in (
        "nexty-agent-skills:other-skill",
        "other-plugin:nxd-review-closure",
        "plugin:one:nxd-review-closure",
    ):
        rejected = handle_event(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Skill",
                "agent_id": "review-agent",
                "session_id": "review-session",
                "tool_input": {"skill": skill},
            },
            state_path=state_path,
        )
        assert rejected["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_explicit_background_dispatch_is_rejected(tmp_path: Path) -> None:
    state_path = tmp_path / "guard-state.json"
    workspace = tmp_path / "agent"
    workspace.mkdir()
    write_initial_state(state_path, workspace_root=workspace)
    handle_event(_capture_event(), state_path=state_path)

    decision = handle_event(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Agent",
            "tool_use_id": "background-review",
            "agent_id": "owner-agent",
            "tool_input": {
                "subagent_type": "general-purpose",
                "run_in_background": True,
                "prompt": _marker(),
            },
        },
        state_path=state_path,
    )

    assert decision["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "run inline" in decision["hookSpecificOutput"]["permissionDecisionReason"]
    assert _state(state_path)["state"] == REVIEW_DISPATCH_PENDING


def test_malformed_marker_is_denied_and_stop_is_blocked_while_pending(tmp_path: Path) -> None:
    state_path = tmp_path / "guard-state.json"
    workspace = tmp_path / "agent"
    workspace.mkdir()
    write_initial_state(state_path, workspace_root=workspace)
    handle_event(_capture_event(), state_path=state_path)

    malformed = handle_event(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Agent",
            "tool_use_id": "bad-review",
            "agent_id": "owner-agent",
            "tool_input": {
                "subagent_type": "general-purpose",
                "prompt": _marker().replace('"closure_path":"closure"', '"closure_path":"/tmp/closure"'),
            },
        },
        state_path=state_path,
    )
    assert malformed["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert _state(state_path)["state"] == REVIEW_DISPATCH_PENDING

    stop = handle_event({"hook_event_name": "Stop"}, state_path=state_path)
    assert stop["decision"] == "block"


def test_claude_post_tool_response_spelling_arms_the_guard(tmp_path: Path) -> None:
    state_path = tmp_path / "guard-state.json"
    workspace = tmp_path / "agent"
    workspace.mkdir()
    write_initial_state(state_path, workspace_root=workspace)
    event = _capture_event()
    event["tool_response"] = event.pop("tool_result")
    handle_event(event, state_path=state_path)
    assert _state(state_path)["state"] == REVIEW_DISPATCH_PENDING


def test_settings_install_all_three_hook_phases() -> None:
    settings = settings_payload(python="/usr/bin/python3", script="/tmp/review_guard.py")
    assert set(settings["hooks"]) == {"PreToolUse", "PostToolUse", "Stop"}
    assert settings["hooks"]["PreToolUse"][0]["matcher"] == "*"
    assert "review_guard.py" in settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
