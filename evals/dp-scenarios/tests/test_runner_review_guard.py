"""Unit tests for the run-scoped workflow-v2 review handoff guard."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import dp_scenarios.runner.review_guard as guard_module
from dp_scenarios.runner.review_guard import (
    NORMAL,
    RELAY_PENDING,
    REVIEW_BUDGET_LINE,
    REVIEW_DISPATCH_PENDING,
    REVIEW_INSPECTION_CUTOFF_MS,
    REVIEW_INSPECTION_CUTOFF_LINE,
    handle_event,
    review_budget_line,
    review_inspection_cutoff_line,
    settings_payload,
    validate_review_timeout_seconds,
    write_initial_state,
)


RETAINED_CAPTURE_ROOT = "/supervisor/retained/sales/capture"
RETAINED_BLUEPRINT_PATH = "/supervisor/retained/sales/dp-blueprint.approved.md"


def _state(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _capture_event(
    *,
    retained_capture_root: str = RETAINED_CAPTURE_ROOT,
    retained_blueprint_path: str = RETAINED_BLUEPRINT_PATH,
) -> dict[str, object]:
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
                            "retained_capture_root": retained_capture_root,
                            "retained_blueprint_path": retained_blueprint_path,
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
        "Load and follow nxd-review-closure.\n"
        f"{REVIEW_BUDGET_LINE}\n"
        f"{REVIEW_INSPECTION_CUTOFF_LINE}\n"
        f"Sanitized original request: {sanitized_request}"
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
    assert _state(state_path)["completed_review_tool_use_id"] == "review-tool"


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


def test_reviewer_reads_are_cut_off_with_time_for_terminal_claims(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_path = tmp_path / "guard-state.json"
    workspace = tmp_path / "agent"
    workspace.mkdir()
    write_initial_state(state_path, workspace_root=workspace)
    clock = 100.0
    monkeypatch.setattr(guard_module.time, "monotonic", lambda: clock)
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

    before_cutoff = handle_event(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Read",
            "agent_id": "review-agent",
            "session_id": "review-session",
            "tool_input": {"file_path": "/captured/closure"},
        },
        state_path=state_path,
    )
    assert before_cutoff == {}

    clock += REVIEW_INSPECTION_CUTOFF_MS / 1000.0 + 0.1
    after_cutoff = handle_event(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Read",
            "agent_id": "review-agent",
            "session_id": "review-session",
            "tool_input": {"file_path": "/captured/closure"},
        },
        state_path=state_path,
    )
    assert after_cutoff["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "inspection window ended" in after_cutoff["hookSpecificOutput"]["permissionDecisionReason"]

    # The reserve still allows the already-running child to return its claims.
    assert handle_event(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Skill",
            "agent_id": "review-agent",
            "session_id": "review-session",
            "tool_input": {"skill": "nxd-review-closure"},
        },
        state_path=state_path,
    ) == {}


def test_normal_agent_is_not_constrained_before_a_review_is_pending(tmp_path: Path) -> None:
    state_path = tmp_path / "guard-state.json"
    workspace = tmp_path / "agent"
    workspace.mkdir()
    write_initial_state(state_path, workspace_root=workspace)

    decision = handle_event(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Agent",
            "tool_use_id": "ordinary-agent",
            "tool_input": {
                "subagent_type": "general-purpose",
                "prompt": "Do the ordinary workflow helper step.",
            },
        },
        state_path=state_path,
    )

    assert decision == {}
    assert _state(state_path)["state"] == NORMAL


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


def test_live_capture_rejects_missing_or_stale_retained_paths(tmp_path: Path) -> None:
    state_path = tmp_path / "guard-state.json"
    workspace = tmp_path / "agent"
    workspace.mkdir()
    captures = tmp_path / "supervisor" / "captures"
    blueprints = tmp_path / "supervisor" / "blueprints"
    captures.mkdir(parents=True)
    blueprints.mkdir(parents=True)
    write_initial_state(
        state_path,
        workspace_root=workspace,
        review_roots=(captures, blueprints),
    )

    fresh_capture = captures / "current" / "capture"
    fresh_capture.mkdir(parents=True)
    fresh_blueprint = blueprints / "current" / "approved-blueprint.md"
    fresh_blueprint.parent.mkdir(parents=True)
    fresh_blueprint.write_text("approved\n", encoding="utf-8")
    handle_event(
        _capture_event(
            retained_capture_root=str(fresh_capture),
            retained_blueprint_path=str(fresh_blueprint),
        ),
        state_path=state_path,
    )
    assert _state(state_path)["state"] == REVIEW_DISPATCH_PENDING
    assert "review_input_error" not in _state(state_path)

    missing_state = tmp_path / "missing-state.json"
    write_initial_state(
        missing_state,
        workspace_root=workspace,
        review_roots=(captures, blueprints),
    )
    handle_event(
        _capture_event(
            retained_capture_root=str(captures / "missing" / "capture"),
            retained_blueprint_path=str(fresh_blueprint),
        ),
        state_path=missing_state,
    )
    assert _state(missing_state)["review_input_error"] == "paths_unavailable"

    outside_state = tmp_path / "outside-state.json"
    outside_capture = tmp_path / "older-capture"
    outside_capture.mkdir()
    outside_blueprint = tmp_path / "older-blueprint.md"
    outside_blueprint.write_text("older\n", encoding="utf-8")
    write_initial_state(
        outside_state,
        workspace_root=workspace,
        review_roots=(captures, blueprints),
    )
    handle_event(
        _capture_event(
            retained_capture_root=str(outside_capture),
            retained_blueprint_path=str(outside_blueprint),
        ),
        state_path=outside_state,
    )
    assert _state(outside_state)["review_input_error"] == "review_input_outside_configured_roots"


def test_missing_supervisor_retained_roots_get_a_distinct_diagnostic(tmp_path: Path) -> None:
    state_path = tmp_path / "guard-state.json"
    workspace = tmp_path / "agent"
    workspace.mkdir()
    captures = tmp_path / "supervisor" / "captures"
    blueprints = tmp_path / "supervisor" / "blueprints"
    write_initial_state(
        state_path,
        workspace_root=workspace,
        review_roots=(captures, blueprints),
    )

    handle_event(_capture_event(), state_path=state_path)
    assert _state(state_path)["review_input_error"] == "review_roots_unavailable"


def test_live_reviewer_reads_only_the_current_capture_and_blueprint(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "guard-state.json"
    workspace = tmp_path / "agent"
    workspace.mkdir()
    captures = tmp_path / "supervisor" / "captures"
    blueprints = tmp_path / "supervisor" / "blueprints"
    fresh_capture = captures / "current" / "capture"
    fresh_capture.mkdir(parents=True)
    (fresh_capture / "models.py").write_text("# current\n", encoding="utf-8")
    fresh_blueprint = blueprints / "current" / "approved-blueprint.md"
    fresh_blueprint.parent.mkdir(parents=True)
    fresh_blueprint.write_text("approved\n", encoding="utf-8")
    older_capture = captures / "older" / "capture"
    older_capture.mkdir(parents=True)
    (older_capture / "models.py").write_text("# old\n", encoding="utf-8")
    captures.mkdir(parents=True, exist_ok=True)
    blueprints.mkdir(parents=True, exist_ok=True)
    write_initial_state(
        state_path,
        workspace_root=workspace,
        review_roots=(captures, blueprints),
    )
    handle_event(
        _capture_event(
            retained_capture_root=str(fresh_capture),
            retained_blueprint_path=str(fresh_blueprint),
        ),
        state_path=state_path,
    )

    assert handle_event(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Agent",
            "tool_use_id": "review-tool",
            "tool_input": {
                "subagent_type": "general-purpose",
                "prompt": _review_prompt(
                    retained_capture_root=str(fresh_capture),
                    retained_blueprint_path=str(fresh_blueprint),
                ),
            },
        },
        state_path=state_path,
    ) == {}

    for tool_name in ("Glob", "Grep"):
        defaulted = handle_event(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": tool_name,
                "parent_tool_use_id": "review-tool",
                "tool_input": {"pattern": "**/*"},
            },
            state_path=state_path,
        )
        assert defaulted["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "current supervisor-retained capture" in defaulted["hookSpecificOutput"]["permissionDecisionReason"]

    escaped_glob = handle_event(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Glob",
            "parent_tool_use_id": "review-tool",
            "tool_input": {"pattern": "../**/*", "path": str(fresh_capture)},
        },
        state_path=state_path,
    )
    assert escaped_glob["hookSpecificOutput"]["permissionDecision"] == "deny"

    for tool_name, tool_input in (
        ("Read", {"file_path": str(fresh_capture / "models.py")}),
        ("Glob", {"pattern": "**/*", "path": str(fresh_capture)}),
        ("Read", {"file_path": str(fresh_blueprint)}),
    ):
        assert handle_event(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": tool_name,
                "parent_tool_use_id": "review-tool",
                "tool_input": tool_input,
            },
            state_path=state_path,
        ) == {}

    denied = handle_event(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Read",
            "parent_tool_use_id": "review-tool",
            "tool_input": {"file_path": str(older_capture / "models.py")},
        },
        state_path=state_path,
    )
    assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_live_reviewer_rechecks_paths_immediately_before_dispatch(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "guard-state.json"
    workspace = tmp_path / "agent"
    workspace.mkdir()
    captures = tmp_path / "supervisor" / "captures"
    blueprints = tmp_path / "supervisor" / "blueprints"
    fresh_capture = captures / "current" / "capture"
    fresh_capture.mkdir(parents=True)
    fresh_blueprint = blueprints / "current" / "approved-blueprint.md"
    fresh_blueprint.parent.mkdir(parents=True)
    fresh_blueprint.write_text("approved\n", encoding="utf-8")
    write_initial_state(
        state_path,
        workspace_root=workspace,
        review_roots=(captures, blueprints),
    )
    handle_event(
        _capture_event(
            retained_capture_root=str(fresh_capture),
            retained_blueprint_path=str(fresh_blueprint),
        ),
        state_path=state_path,
    )
    fresh_blueprint.unlink()
    decision = handle_event(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Agent",
            "tool_use_id": "review-tool",
            "tool_input": {
                "subagent_type": "general-purpose",
                "prompt": _review_prompt(
                    retained_capture_root=str(fresh_capture),
                    retained_blueprint_path=str(fresh_blueprint),
                ),
            },
        },
        state_path=state_path,
    )
    assert decision["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert _state(state_path)["review_input_error"] == "paths_unavailable"


def test_owner_cannot_modify_supervisor_retained_roots(tmp_path: Path) -> None:
    state_path = tmp_path / "guard-state.json"
    workspace = tmp_path / "agent"
    workspace.mkdir()
    captures = tmp_path / "supervisor" / "captures"
    blueprints = tmp_path / "supervisor" / "blueprints"
    captures.mkdir(parents=True)
    blueprints.mkdir(parents=True)
    write_initial_state(
        state_path,
        workspace_root=workspace,
        review_roots=(captures, blueprints),
    )

    for tool_name, path in (
        ("Write", captures / "current" / "models.py"),
        ("Edit", blueprints / "current" / "approved-blueprint.md"),
    ):
        decision = handle_event(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": tool_name,
                "tool_input": {"file_path": str(path)},
            },
            state_path=state_path,
        )
        assert decision["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "supervisor-retained" in decision["hookSpecificOutput"]["permissionDecisionReason"]

    notebook_decision = handle_event(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "NotebookEdit",
            "tool_input": {"notebook_path": str(captures / "current" / "notes.ipynb")},
        },
        state_path=state_path,
    )
    assert notebook_decision["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "supervisor-retained" in notebook_decision["hookSpecificOutput"]["permissionDecisionReason"]


def test_owner_cannot_inspect_supervisor_retained_roots(tmp_path: Path) -> None:
    state_path = tmp_path / "guard-state.json"
    workspace = tmp_path / "agent"
    workspace.mkdir()
    captures = tmp_path / "supervisor" / "captures"
    blueprints = tmp_path / "supervisor" / "blueprints"
    captures.mkdir(parents=True)
    blueprints.mkdir(parents=True)
    write_initial_state(
        state_path,
        workspace_root=workspace,
        review_roots=(captures, blueprints),
    )

    for tool_name, tool_input in (
        ("Read", {"file_path": str(blueprints)}),
        ("Glob", {"path": str(captures), "pattern": "**/*"}),
        ("Grep", {"path": str(captures), "pattern": "needle"}),
    ):
        decision = handle_event(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": tool_name,
                "tool_input": tool_input,
            },
            state_path=state_path,
        )
        assert decision["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "may not inspect" in decision["hookSpecificOutput"]["permissionDecisionReason"]

    state = _state(state_path)
    state["completed_review_tool_use_id"] = "review-tool"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    bash_decision = handle_event(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": f"cat {captures}"},
        },
        state_path=state_path,
    )
    assert bash_decision["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "may not use shell access" in bash_decision["hookSpecificOutput"]["permissionDecisionReason"]
    relative_bash_decision = handle_event(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "cat ../supervisor/captures"},
        },
        state_path=state_path,
    )
    assert relative_bash_decision["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_incomplete_retained_input_handoff_can_stop_cleanly(tmp_path: Path) -> None:
    state_path = tmp_path / "guard-state.json"
    write_initial_state(state_path)
    state = _state(state_path)
    state.update(
        {
            "state": REVIEW_DISPATCH_PENDING,
            "review_input_error": "paths_unavailable",
        }
    )
    state_path.write_text(json.dumps(state), encoding="utf-8")

    assert handle_event({"hook_event_name": "Stop"}, state_path=state_path) == {}


@pytest.mark.parametrize("tool_name", ["Write", "Edit"])
def test_owner_write_without_review_roots_does_not_require_workspace_root(
    tmp_path: Path, tool_name: str
) -> None:
    state_path = tmp_path / "guard-state.json"
    write_initial_state(state_path)

    decision = handle_event(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": tool_name,
            "tool_input": {"file_path": "review-record.json"},
        },
        state_path=state_path,
    )
    assert decision == {}


def test_live_capture_accepts_documented_requirement_view_shape(tmp_path: Path) -> None:
    state_path = tmp_path / "guard-state.json"
    workspace = tmp_path / "agent"
    workspace.mkdir()
    captures = tmp_path / "supervisor" / "captures"
    blueprints = tmp_path / "supervisor" / "blueprints"
    capture = captures / "retained" / "capture"
    capture.mkdir(parents=True)
    blueprint = blueprints / "retained" / "approved-blueprint.md"
    blueprint.parent.mkdir(parents=True)
    blueprint.write_text("approved\n", encoding="utf-8")
    write_initial_state(
        state_path,
        workspace_root=workspace,
        review_roots=(captures, blueprints),
    )
    event = _capture_event(
        retained_capture_root=str(capture),
        retained_blueprint_path=str(blueprint),
    )
    handle_event(event, state_path=state_path)
    state = _state(state_path)
    assert state["state"] == REVIEW_DISPATCH_PENDING
    assert "review_input_error" not in state


def test_new_capture_clears_a_previous_review_handoff(tmp_path: Path) -> None:
    state_path = tmp_path / "guard-state.json"
    workspace = tmp_path / "agent"
    workspace.mkdir()
    write_initial_state(state_path, workspace_root=workspace)

    handle_event(_capture_event(), state_path=state_path)
    assert _state(state_path)["state"] == REVIEW_DISPATCH_PENDING

    replacement = _capture_event()
    requirements = replacement["tool_result"]["content"]["requirements"]
    assert isinstance(requirements, list)
    assert isinstance(requirements[0], dict)
    requirements[0]["review_input"] = {
        "retained_capture_root": RETAINED_CAPTURE_ROOT,
    }
    handle_event(replacement, state_path=state_path)

    state = _state(state_path)
    assert state["state"] == REVIEW_DISPATCH_PENDING
    assert state["review_input_error"] == "missing_or_malformed"
    assert "retained_capture_root" not in state
    assert "retained_blueprint_path" not in state
    assert "review_tool_use_id" not in state

    replacement["tool_result"]["content"]["next_actions"] = []
    handle_event(replacement, state_path=state_path)
    assert _state(state_path)["state"] == NORMAL


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
    assert handle_event({"hook_event_name": "Stop"}, state_path=state_path) == {}


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


@pytest.mark.parametrize(
    "malformed_line",
    [
        "Sanitized original request (operator-provided): request",
        "sanitized original request: request",
        "Sanitized original request:   ",
        "Sanitized original request: first\nSanitized original request: second",
        "- Sanitized original request: request",
    ],
)
def test_owner_dispatch_rejects_noncanonical_or_ambiguous_request_labels(
    tmp_path: Path, malformed_line: str
) -> None:
    state_path = tmp_path / "guard-state.json"
    workspace = tmp_path / "agent"
    workspace.mkdir()
    write_initial_state(state_path, workspace_root=workspace)
    handle_event(_capture_event(), state_path=state_path)

    prompt = _review_prompt()
    prompt = prompt[: prompt.index("Sanitized original request:")] + malformed_line
    decision = handle_event(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Agent",
            "tool_use_id": "malformed-review",
            "tool_input": {"subagent_type": "general-purpose", "prompt": prompt},
        },
        state_path=state_path,
    )

    assert decision["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert _state(state_path)["state"] == REVIEW_DISPATCH_PENDING


def test_owner_dispatch_requires_the_canonical_reviewer_skill_instruction(tmp_path: Path) -> None:
    state_path = tmp_path / "guard-state.json"
    workspace = tmp_path / "agent"
    workspace.mkdir()
    write_initial_state(state_path, workspace_root=workspace)
    handle_event(_capture_event(), state_path=state_path)

    decision = handle_event(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Agent",
            "tool_use_id": "review-tool",
            "tool_input": {
                "subagent_type": "general-purpose",
                "prompt": _review_prompt().replace(
                    "Load and follow nxd-review-closure.",
                    "Use nxd-review-closure.",
                ),
            },
        },
        state_path=state_path,
    )

    assert decision["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert _state(state_path)["state"] == REVIEW_DISPATCH_PENDING


def test_owner_dispatch_requires_the_declared_review_budget(tmp_path: Path) -> None:
    state_path = tmp_path / "guard-state.json"
    workspace = tmp_path / "agent"
    workspace.mkdir()
    write_initial_state(state_path, workspace_root=workspace)
    handle_event(_capture_event(), state_path=state_path)

    decision = handle_event(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Agent",
            "tool_use_id": "review-tool",
            "tool_input": {
                "subagent_type": "general-purpose",
                "prompt": _review_prompt().replace(f"{REVIEW_BUDGET_LINE}\n", ""),
            },
        },
        state_path=state_path,
    )

    assert decision["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert _state(state_path)["state"] == REVIEW_DISPATCH_PENDING


def test_owner_dispatch_accepts_the_configured_review_budget(tmp_path: Path) -> None:
    state_path = tmp_path / "guard-state.json"
    workspace = tmp_path / "agent"
    workspace.mkdir()
    write_initial_state(state_path, workspace_root=workspace)
    handle_event(_capture_event(), state_path=state_path)

    prompt = _review_prompt()
    prompt = prompt.replace(REVIEW_BUDGET_LINE, review_budget_line(600))
    prompt = prompt.replace(
        REVIEW_INSPECTION_CUTOFF_LINE, review_inspection_cutoff_line(600)
    )
    decision = handle_event(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Agent",
            "tool_use_id": "review-tool",
            "tool_input": {
                "subagent_type": "general-purpose",
                "prompt": prompt,
            },
        },
        state_path=state_path,
        review_timeout_seconds=600,
    )

    assert decision == {}
    assert _state(state_path)["review_tool_use_id"] == "review-tool"


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf"), "not-a-number"])
def test_review_timeout_validation_rejects_non_positive_or_non_finite_values(
    value: object,
) -> None:
    with pytest.raises(ValueError, match="positive finite"):
        validate_review_timeout_seconds(value)


def test_owner_dispatch_explains_each_missing_protocol_line(tmp_path: Path) -> None:
    state_path = tmp_path / "guard-state.json"
    workspace = tmp_path / "agent"
    workspace.mkdir()
    write_initial_state(state_path, workspace_root=workspace)
    handle_event(_capture_event(), state_path=state_path)

    prompt = _review_prompt()
    prompt = prompt.replace("Load and follow nxd-review-closure.\n", "")
    prompt = prompt.replace(f"{REVIEW_BUDGET_LINE}\n", "")
    prompt = prompt.replace(f"{REVIEW_INSPECTION_CUTOFF_LINE}\n", "")
    decision = handle_event(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Agent",
            "tool_use_id": "review-tool",
            "tool_input": {
                "subagent_type": "general-purpose",
                "prompt": prompt,
            },
        },
        state_path=state_path,
    )

    reason = decision["hookSpecificOutput"]["permissionDecisionReason"]
    assert "Load and follow nxd-review-closure." in reason
    assert REVIEW_BUDGET_LINE in reason
    assert REVIEW_INSPECTION_CUTOFF_LINE in reason
    assert RETAINED_CAPTURE_ROOT not in reason
    assert RETAINED_BLUEPRINT_PATH not in reason
    assert _state(state_path)["state"] == REVIEW_DISPATCH_PENDING


@pytest.mark.parametrize(
    ("change", "expected_fragment"),
    [
        (
            lambda prompt: prompt.replace(
                "Sanitized original request:",
                "Sanitized original request: keep this label out of prose.\nSanitized original request:",
                1,
            ),
            "'Sanitized original request:' must occur exactly once",
        ),
        (
            lambda prompt: prompt.replace(
                f"{REVIEW_BUDGET_LINE}\n",
                f"{REVIEW_BUDGET_LINE}\n{REVIEW_BUDGET_LINE}\n",
            ),
            f"{REVIEW_BUDGET_LINE} must occur exactly once",
        ),
        (
            lambda prompt: prompt.replace(
                "Sanitized original request: Review the captured sales closure.",
                "Sanitized original request:   ",
            ),
            "'Sanitized original request:' line must contain a non-empty sanitized request",
        ),
    ],
)
def test_owner_dispatch_diagnostics_match_validator_for_retryable_shapes(
    tmp_path: Path, change: object, expected_fragment: str
) -> None:
    state_path = tmp_path / "guard-state.json"
    workspace = tmp_path / "agent"
    workspace.mkdir()
    write_initial_state(state_path, workspace_root=workspace)
    handle_event(_capture_event(), state_path=state_path)

    prompt = change(_review_prompt())
    decision = handle_event(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Agent",
            "tool_use_id": "review-tool",
            "tool_input": {
                "subagent_type": "general-purpose",
                "prompt": prompt,
            },
        },
        state_path=state_path,
    )

    reason = decision["hookSpecificOutput"]["permissionDecisionReason"]
    assert expected_fragment in reason
    assert "canonical review prompt is invalid" not in reason
    assert "Review the captured sales closure." not in reason
    assert not reason.startswith("Reviewer dispatch rejected: add ")
    assert _state(state_path)["state"] == REVIEW_DISPATCH_PENDING


def test_owner_dispatch_does_not_invite_retry_when_supervisor_paths_are_absent(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "guard-state.json"
    workspace = tmp_path / "agent"
    workspace.mkdir()
    write_initial_state(state_path, workspace_root=workspace)
    state = _state(state_path)
    state["state"] = REVIEW_DISPATCH_PENDING
    state_path.write_text(json.dumps(state), encoding="utf-8")

    decision = handle_event(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Agent",
            "tool_use_id": "review-tool",
            "tool_input": {
                "subagent_type": "general-purpose",
                "prompt": _review_prompt(),
            },
        },
        state_path=state_path,
    )

    reason = decision["hookSpecificOutput"]["permissionDecisionReason"]
    assert "supervisor-retained paths are unavailable" in reason
    assert "add these exact review-prompt lines" not in reason
    assert _state(state_path)["state"] == REVIEW_DISPATCH_PENDING


def test_settings_install_all_three_hook_phases() -> None:
    settings = settings_payload(python="/usr/bin/python3", script="/tmp/review_guard.py")
    assert set(settings["hooks"]) == {"PreToolUse", "PostToolUse", "Stop"}
    assert settings["hooks"]["PreToolUse"][0]["matcher"] == "*"
    assert "review_guard.py" in settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"]


def test_settings_carries_the_configured_review_timeout() -> None:
    settings = settings_payload(
        python="/usr/bin/python3",
        script="/tmp/review_guard.py",
        review_timeout_seconds=600,
    )
    command = settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert "--review-timeout 600" in command
