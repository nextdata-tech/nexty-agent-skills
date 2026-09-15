"""Unit tests for the run-scoped workflow-v2 review handoff guard."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dp_scenarios.runner.review_guard import (
    NORMAL,
    RELAY_PENDING,
    REVIEW_DISPATCH_PENDING,
    handle_event,
    settings_payload,
    write_initial_state,
)


RETAINED_CAPTURE_ROOT = "/supervisor/retained/sales/capture"
RETAINED_BLUEPRINT_PATH = "/supervisor/retained/sales/dp-blueprint.approved.md"


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
                "requirements": [
                    {
                        "id": "review",
                        "status": "pending",
                        "review_input": {
                            "retained_capture_root": RETAINED_CAPTURE_ROOT,
                            "retained_blueprint_path": RETAINED_BLUEPRINT_PATH,
                        },
                    }
                ],
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


def _review_prompt(
    *,
    retained_capture_root: str = RETAINED_CAPTURE_ROOT,
    retained_blueprint_path: str = RETAINED_BLUEPRINT_PATH,
    sanitized_request: str = "Review the captured sales closure.",
) -> str:
    return (
        f"{_marker()}\n"
        f"retained_capture_root: {retained_capture_root}\n"
        f"retained_blueprint_path: {retained_blueprint_path}\n"
        f"Sanitized original request (operator-provided): {sanitized_request}"
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
        "tool_input": {"subagent_type": "general-purpose", "prompt": _review_prompt()},
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
            "tool_input": {"subagent_type": "general-purpose", "prompt": _review_prompt()},
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


def test_empty_content_in_completion_metadata_does_not_satisfy_the_review_dispatch(
    tmp_path: Path,
) -> None:
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
            "tool_input": {"subagent_type": "general-purpose", "prompt": _review_prompt()},
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
                "status": "completed",
                "content": [],
                "message": "Agent completed successfully",
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
            "tool_input": {"subagent_type": "general-purpose", "prompt": _review_prompt()},
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
                "prompt": _review_prompt(),
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
                "prompt": _review_prompt().replace('"closure_path":"closure"', '"closure_path":"/tmp/closure"'),
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


def test_capture_persists_supervisor_retained_review_input(tmp_path: Path) -> None:
    state_path = tmp_path / "guard-state.json"
    workspace = tmp_path / "agent"
    workspace.mkdir()
    write_initial_state(state_path, workspace_root=workspace)

    handle_event(_capture_event(), state_path=state_path)

    state = _state(state_path)
    assert state["retained_capture_root"] == RETAINED_CAPTURE_ROOT
    assert state["retained_blueprint_path"] == RETAINED_BLUEPRINT_PATH


@pytest.mark.parametrize("malformation", ["missing", "malformed"])
def test_malformed_or_missing_review_input_fails_closed(tmp_path: Path, malformation: str) -> None:
    state_path = tmp_path / "guard-state.json"
    workspace = tmp_path / "agent"
    workspace.mkdir()
    write_initial_state(state_path, workspace_root=workspace)
    capture = _capture_event()
    requirements = capture["tool_result"]["content"]["requirements"]
    assert isinstance(requirements, list)
    review = requirements[0]
    assert isinstance(review, dict)
    if malformation == "missing":
        review.pop("review_input")
    else:
        review["review_input"] = {"retained_capture_root": RETAINED_CAPTURE_ROOT}

    handle_event(capture, state_path=state_path)
    state = _state(state_path)
    assert state["state"] == REVIEW_DISPATCH_PENDING
    assert state["review_input_error"] == "missing_or_malformed"

    decision = handle_event(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Agent",
            "tool_use_id": "review-tool",
            "tool_input": {"subagent_type": "general-purpose", "prompt": _review_prompt()},
        },
        state_path=state_path,
    )
    assert decision["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert handle_event({"hook_event_name": "Stop"}, state_path=state_path)["decision"] == "block"


@pytest.mark.parametrize("tool_name", ["Agent", "Task"])
def test_owner_dispatch_requires_exact_retained_paths_and_sanitized_request_line(
    tmp_path: Path, tool_name: str
) -> None:
    state_path = tmp_path / f"{tool_name.lower()}-guard-state.json"
    workspace = tmp_path / "agent"
    workspace.mkdir()
    write_initial_state(state_path, workspace_root=workspace)
    handle_event(_capture_event(), state_path=state_path)

    prompts = (
        _review_prompt(retained_capture_root="/wrong/capture"),
        _review_prompt(retained_blueprint_path="/wrong/blueprint.md"),
        _marker() + f"\nretained_capture_root: {RETAINED_CAPTURE_ROOT}\nretained_blueprint_path: {RETAINED_BLUEPRINT_PATH}\nSanitized original request:   ",
    )
    for prompt in prompts:
        decision = handle_event(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": tool_name,
                "tool_use_id": f"{tool_name.lower()}-review",
                "tool_input": {"subagent_type": "general-purpose", "prompt": prompt},
            },
            state_path=state_path,
        )
        assert decision["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert _state(state_path)["state"] == REVIEW_DISPATCH_PENDING

    allowed = handle_event(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": tool_name,
            "tool_use_id": f"{tool_name.lower()}-review-valid",
            "tool_input": {"subagent_type": "general-purpose", "prompt": _review_prompt()},
        },
        state_path=state_path,
    )
    assert allowed == {}


def test_settings_install_all_three_hook_phases() -> None:
    settings = settings_payload(python="/usr/bin/python3", script="/tmp/review_guard.py")
    assert set(settings["hooks"]) == {"PreToolUse", "PostToolUse", "Stop"}
    assert settings["hooks"]["PreToolUse"][0]["matcher"] == "*"
    assert "review_guard.py" in settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
