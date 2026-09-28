"""Codex MCP and reviewer evidence must obey the shared Claude contracts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dp_scenarios.grading.gates import canonical_review_dispatch_marker
from dp_scenarios.ledger import SupervisorFacts
from dp_scenarios.runner.claude_adapter import parse_claude_events
from dp_scenarios.runner.codex_adapter import (
    CodexAdapter,
    CodexAdapterError,
    _codex_review_capture,
    _codex_review_dispatch_error,
    _review_pending_after_observations,
    parse_codex_events,
)
from dp_scenarios.runner.review_guard import (
    review_budget_line,
    review_inspection_cutoff_line,
)
from dp_scenarios.runner.tier import (
    _checker_skew_outcome,
    _published_closure,
    _review_input_from_capture,
)
from dp_scenarios.grading.gates import _successful_unbound_check_positions


def _identity(value: object) -> object:
    return value


def _codex_event(
    tool: str, arguments: dict[str, object], content: dict[str, object], *, error: bool = False
) -> dict[str, object]:
    # Native B3/B5 rollouts emit McpToolCall items with a status and an MCP
    # result containing isError plus JSON text blocks in content.
    return {
        "method": "item/completed",
        "params": {
            "item": {
                "type": "mcpToolCall",
                "id": "call-1",
                "server": "nxd-desktop",
                "tool": tool,
                "arguments": arguments,
                "status": "failed" if error else "completed",
                "result": {
                    "isError": error,
                    "content": [{"type": "text", "text": json.dumps(content)}],
                },
            }
        },
    }


def _claude_events(
    tool: str, arguments: dict[str, object], content: dict[str, object], *, error: bool
) -> list[dict[str, object]]:
    return [
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "call-1",
                        "name": f"mcp__nxd-desktop__{tool}",
                        "input": arguments,
                    }
                ]
            },
        },
        {
            "type": "user",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "call-1",
                        "is_error": error,
                        "content": [{"type": "text", "text": json.dumps(content)}],
                    }
                ]
            },
        },
        {"type": "result", "result": "done", "is_error": False},
    ]


_WORKFLOW = "sample-workflow"
_REVIEW_INPUT = {
    "retained_capture_root": "/retained/capture",
    "retained_blueprint_path": "/retained/blueprint.md",
}
_CAPTURE = {
    "workflow": _WORKFLOW,
    "next_actions": [
        {"action": "report_requirement", "requirement_id": "review", "generation": 1}
    ],
    "requirements": [{"id": "review", "status": "pending", "review_input": _REVIEW_INPUT}],
}
_CHECK = {
    "workflow": _WORKFLOW,
    "outcome": "pass",
    "provenance": {"definition_id": "definition-1", "closure_path": "closure"},
    "stages": [
        {"stage": stage, "status": "pass"}
        for stage in ("structure", "runtime", "contract", "semantic")
    ],
}
_REVIEW = {"workflow": _WORKFLOW, "requirements": [{"id": "review", "status": "satisfied"}]}
_START = {
    "workflow": _WORKFLOW,
    "admission": {
        "run_id": "run-1",
        "artifact_id": "artifact-1",
        "definition_id": "definition-1",
    },
}


@pytest.mark.parametrize("error", [False, True])
@pytest.mark.parametrize(
    ("tool", "arguments", "content"),
    [
        (
            "advance_workflow",
            {"workflow": _WORKFLOW, "action": {"type": "capture", "parameters": {"authoring_root": "closure"}}},
            _CAPTURE,
        ),
        ("check_data_product", {"workflow": _WORKFLOW, "definition": "closure"}, _CHECK),
        (
            "advance_workflow",
            {"workflow": _WORKFLOW, "action": {"type": "report_requirement", "parameters": {"requirement_id": "review"}}},
            _REVIEW,
        ),
        (
            "advance_workflow",
            {"workflow": _WORKFLOW, "action": {"type": "start_run", "parameters": {}}},
            _START,
        ),
    ],
)
def test_native_codex_mcp_envelope_matches_claude(
    tool: str, arguments: dict[str, object], content: dict[str, object], error: bool
) -> None:
    codex, _ = parse_codex_events(
        [_codex_event(tool, arguments, content, error=error), {"type": "turn.completed"}],
        redact_json_rpc=_identity,
        redact_text=_identity,
        session_id="codex-session",
    )
    claude, _ = parse_claude_events(
        _claude_events(tool, arguments, content, error=error),
        redact_json_rpc=_identity,
        redact_text=_identity,
        session_id="claude-session",
    )
    expected = {
        "is_error": error,
        "content": content,
    }
    assert codex.tool_calls[0].result == expected
    assert {key: claude.tool_calls[0].result[key] for key in expected} == expected


@pytest.mark.parametrize("backend", ["claude", "codex"])
@pytest.mark.parametrize(
    ("status", "source_digest", "retained_digest", "expected"),
    [
        ("match", "a" * 64, "a" * 64, ("match", ())),
        ("mismatch", "a" * 64, "b" * 64, ("mismatch", ("checker_skew_mismatch",))),
        ("unreadable", None, None, ("ungraded", ("checker_skew_unreadable",))),
    ],
)
def test_checker_skew_reads_successful_capture_envelopes_for_both_backends(
    backend: str,
    status: str,
    source_digest: str | None,
    retained_digest: str | None,
    expected: tuple[str | None, tuple[str, ...]],
) -> None:
    arguments = {
        "workflow": _WORKFLOW,
        "action": {"type": "capture", "parameters": {}},
    }
    if backend == "claude":
        parsed, _ = parse_claude_events(
            _claude_events("advance_workflow", arguments, _CAPTURE, error=False),
            redact_json_rpc=_identity,
            redact_text=_identity,
            session_id="claude-session",
        )
    else:
        parsed, _ = parse_codex_events(
            [
                _codex_event("advance_workflow", arguments, _CAPTURE),
                {"type": "turn.completed"},
            ],
            redact_json_rpc=_identity,
            redact_text=_identity,
            session_id="codex-session",
        )

    marker: dict[str, object] = {
        "kind": "checker_skew",
        "schema": "nxd-checker-skew-v1",
        "status": status,
    }
    if status in {"match", "mismatch"}:
        marker["source_sha256"] = source_digest
        marker["retained_sha256"] = retained_digest
    call = parsed.tool_calls[0]
    observations = {
        "turns": [
            {
                "backend": backend,
                "tool_calls": [
                    {
                        "name": call.name,
                        "arguments": call.arguments,
                        "result": call.result,
                        "observation": marker,
                    }
                ],
            }
        ]
    }
    # B3 run2 stores the review requirement under result.content.requirements.
    assert {key: call.result[key] for key in ("is_error", "content")} == {
        "is_error": False,
        "content": _CAPTURE,
    }
    assert _checker_skew_outcome(observations) == expected


def test_codex_mcp_error_flag_is_authoritative_even_with_completed_status() -> None:
    event = _codex_event("check_data_product", {"workflow": _WORKFLOW}, _CHECK)
    item = event["params"]["item"]
    item["result"]["isError"] = True
    parsed, observations = parse_codex_events(
        [event], redact_json_rpc=_identity, redact_text=_identity, session_id="s"
    )
    assert parsed.tool_calls[0].result["is_error"] is True
    assert observations[0]["is_error"] is True


def test_codex_envelope_preserves_strict_capture_check_review_and_publication(
    tmp_path: Path,
) -> None:
    capture_args = {"workflow": _WORKFLOW, "action": {"type": "capture", "parameters": {"authoring_root": "closure"}}}
    check_args = {"workflow": _WORKFLOW, "definition": "closure"}
    report_args = {"workflow": _WORKFLOW, "action": {"type": "report_requirement", "parameters": {"requirement_id": "review"}}}
    start_args = {"workflow": _WORKFLOW, "action": {"type": "start_run", "parameters": {}}}

    for error in (False, True):
        events = [
            _codex_event("advance_workflow", capture_args, _CAPTURE, error=error),
            _codex_event("check_data_product", check_args, _CHECK, error=error),
            _codex_event("advance_workflow", report_args, _REVIEW, error=error),
            _codex_event("advance_workflow", start_args, _START, error=error),
        ]
        calls = [
            parse_codex_events([event], redact_json_rpc=_identity, redact_text=_identity, session_id="s")[0].tool_calls[0]
            for event in events
        ]
        observed = [
            {"name": call.name, "arguments": call.arguments, "result": call.result}
            for call in calls
        ]
        observations = {"turns": [{"turn": 1, "tool_calls": observed}]}
        assert (_review_input_from_capture(observed[0]) is not None) is not error
        assert bool(_successful_unbound_check_positions(observations, desktop_server_name="nxd-desktop")) is not error
        capture_observations = parse_codex_events(
            [events[0]], redact_json_rpc=_identity, redact_text=_identity, session_id="s"
        )[1]
        report_observations = parse_codex_events(
            [events[2]], redact_json_rpc=_identity, redact_text=_identity, session_id="s"
        )[1]
        assert _review_pending_after_observations(capture_observations, False) is not error
        assert _review_pending_after_observations(report_observations, True) is error
        facts = SupervisorFacts(
            run_id="run-1",
            artifact_id="artifact-1",
            publish_sequence="1",
            per_model_row_counts={"main.model": "1"},
            lifecycle_state="published",
        )
        assert (_published_closure(observations, facts, agent_root=tmp_path) is not None) is not error


def test_fresh_non_review_capture_clears_the_previous_review_state() -> None:
    arguments = {"workflow": _WORKFLOW, "action": {"type": "capture", "parameters": {}}}
    event = _codex_event("advance_workflow", arguments, {"workflow": _WORKFLOW})
    _, observations = parse_codex_events(
        [event], redact_json_rpc=_identity, redact_text=_identity, session_id="s"
    )
    assert _review_pending_after_observations(observations, True) is False
    assert _codex_review_capture([event], {"retained_capture_root": "/old"}) is None


def test_turn_handoff_supplies_the_current_session_reference(tmp_path: Path) -> None:
    adapter = object.__new__(CodexAdapter)
    adapter.fixture_dir = tmp_path
    adapter._thread_id = "current-codex-session"
    prompt = adapter._prompt("Continue the current workflow.", ())
    assert "Current owning-session reference for workflow actions: current-codex-session" in prompt


def test_codex_dispatch_reuses_canonical_review_guard_checks(tmp_path: Path) -> None:
    captures = tmp_path / "captures"
    blueprints = tmp_path / "blueprints"
    retained = captures / "capture-1"
    retained.mkdir(parents=True)
    blueprints.mkdir()
    blueprint = blueprints / "blueprint.md"
    blueprint.write_text("approved", encoding="utf-8")
    content = {
        **_CAPTURE,
        "requirements": [{"id": "review", "status": "pending", "review_input": {
            "retained_capture_root": str(retained),
            "retained_blueprint_path": str(blueprint),
        }}],
    }
    capture = _codex_review_capture(
        [_codex_event("advance_workflow", {"workflow": _WORKFLOW, "action": {"type": "capture", "parameters": {}}}, content)],
        None,
    )
    assert capture is not None
    prompt = "\n".join(
        (
            "CODEX_REVIEW_CHILD",
            f"retained_capture_root: {retained}",
            f"retained_blueprint_path: {blueprint}",
            "Load and follow nxd-review-closure.",
            "Sanitized original request: summarize the retained closure",
            review_budget_line(300),
            review_inspection_cutoff_line(300),
            canonical_review_dispatch_marker("closure", 0),
        )
    )
    roots = (captures, blueprints)
    assert _codex_review_dispatch_error(
        {"prompt": prompt}, capture, review_timeout_seconds=300, review_roots=roots
    ) is None
    for malformed in (
        prompt.replace("Sanitized original request: ", "Request: "),
        prompt.replace(str(retained), str(captures / "other")),
        prompt.replace("Load and follow nxd-review-closure.\n", ""),
        prompt + "\n" + review_budget_line(300),
        prompt.replace("NXD_REVIEW_DISPATCH", "OTHER_REVIEW_DISPATCH"),
    ):
        assert _codex_review_dispatch_error(
            {"prompt": malformed}, capture, review_timeout_seconds=300, review_roots=roots
        ) is not None
    assert _codex_review_dispatch_error(
        {"prompt": None}, capture, review_timeout_seconds=300, review_roots=roots
    ) is not None


def test_codex_rejects_malformed_dispatch_at_spawn_start(tmp_path: Path) -> None:
    retained = tmp_path / "captures" / "capture-1"
    retained.mkdir(parents=True)
    blueprint = tmp_path / "blueprints" / "blueprint.md"
    blueprint.parent.mkdir()
    blueprint.write_text("approved", encoding="utf-8")
    adapter = object.__new__(CodexAdapter)
    adapter.timeout_s = 5.0
    adapter.review_timeout_seconds = 300.0
    adapter._thread_id = "root-thread"
    adapter._review_pending = True
    adapter.supervisor_data_dir = tmp_path
    adapter._review_capture = {
        "retained_capture_root": str(retained),
        "retained_blueprint_path": str(blueprint),
    }
    adapter._read_until_response = lambda *_args, **_kwargs: (
        {"result": {"turn": {"id": "root-turn"}}},
        [],
    )
    adapter._is_server_request = lambda _event: False
    adapter._read_streams = lambda _deadline: {
        "method": "item/started",
        "params": {
            "threadId": "root-thread",
            "turnId": "root-turn",
            "item": {"type": "collabAgentToolCall", "tool": "spawnAgent", "prompt": "CODEX_REVIEW_CHILD"},
        },
    }
    with pytest.raises(CodexAdapterError, match="canonical NXD_REVIEW_DISPATCH marker"):
        adapter._collect_turn(1, "", [])
