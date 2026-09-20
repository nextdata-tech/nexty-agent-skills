"""Bridge the dp-scenarios transport to the Codex app server.

The local live runner has a provider-neutral turn boundary. This adapter keeps
that boundary intact while using one persistent ``codex app-server --stdio``
child, with the runner-owned Desktop MCP server configured through Codex TOML
overrides. Supervisor facts continue to come from structured MCP results and
the runner-owned release directory; no agent prose is used as oracle data.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import tempfile
import time
from collections import deque
from collections.abc import Mapping, Sequence
from typing import Any

from dp_scenarios.failure_reasons import (
    CHILD_EXITED_EARLY,
    CHILD_NO_TERMINAL_RESULT,
    classify_failure_reason,
    first_reason,
)
from dp_scenarios.operator.transport import ToolCall, TouchedFile, TurnResult
from dp_scenarios.runner.claude_adapter import (
    _advance_action_type,
    _changed_files,
    _load_desktop_stdio,
    _mcp_name,
    _payload_from_call,
    _snapshot_workspace,
    _update_from_state_dir,
    _update_machine_artifacts,
    _write_supervisor_facts,
)


class CodexAdapterError(RuntimeError):
    """The Codex bridge could not satisfy one turn."""

    def __init__(self, message: str, *, reason: str | None = None) -> None:
        super().__init__(message)
        self.reason = reason


CODEX_SYSTEM_PROMPT = """You are the agent under test in a local DP-scenarios run.

Work only in the current workspace. Read scenario-evidence-contract.json,
infra-profile.yaml when present, and the relevant skill files under the
provided skill-pack directory before acting. Use the runner-owned nxd-desktop
MCP server for supervisor operations; do not invent supervisor results from
your own prose. Keep the authored closure in closure/ and do not create or
edit artifacts/ files. Follow every conduct rule in the evidence contract.
Respond directly to each operator turn and continue the workflow until the
operator's next message arrives.

Reviewer-child role: when a parent labels your prompt
`CODEX_REVIEW_CHILD`, you are the read-only review child, not the workflow
runner. Do not call nxd-desktop, do not spawn/resume/wait for another child,
do not create or edit files, and do not follow the parent-run admission or
publication sequence. Inspect only the closure and review inputs named by the
parent and return concise review claims/findings to the parent.

Workflow-v2 control: treat every supervisor response as authoritative. After
each response, use only its current revision, invalidation_epoch, and
next_actions. Once a successful capture returns a report_requirement action
with review_input, do not call prepare_workflow, get_workflow_capabilities, or
inspect_workflow as recovery. Dispatch exactly one provider-native,
read-only reviewer using that matching review_input. In this backend, that
means the built-in Codex collaboration child via spawnAgent, followed by
waiting for the child to complete; do not substitute an inline self-review,
an authored review-record.json/agent-attestations.json, or an OS process. The
required sequence is: call spawnAgent with the exact review_input and a
read-only review request whose prompt begins with `CODEX_REVIEW_CHILD`, wait
for that child until its state is completed, then pass the child's returned
claims and the exact review_input fields to
report_requirement. The `parameters.report` value must be the JSON object
`{"schema":"nxd-conversation-review-v1","verdict":"clear","findings":[],"rejection_code":null}`
or the corresponding exact findings/rejection object, never a JSON-encoded
string or Markdown. If the child cannot be started or completed, report an
incomplete result; never fabricate the review outcome yourself. After a clear
report, call the returned self-check/validation action and inspect its result
before following the returned admission, start_run, and query actions. Only use
inspect_prepare_recovery when the immediately preceding
pre-admission prepare_workflow response returned a prepare_recovery_id.
After capture, never edit the retained closure or blueprint before reporting
the child review; the captured inputs are immutable. If the supervisor returns
a report verdict of `findings`, `rejected`, or `indeterminate`, relay it to the
operator and stop for adjudication. Do not reset, edit, recapture, validate,
admit, or start a run for a non-clear report; only a clear report authorizes
the returned next actions.
When the supervisor returns report_requirement or workflow/review_pending after
capture, the next supervisor action must be that report after the one child
completes. Do not call reset_workflow, list_data_products, inspect_workflow,
check_data_product, prepare_workflow, or get_workflow_capabilities in that
state. Reset is for an explicitly requested blueprint replacement, not a way
to avoid the pending review. "workflow already exists" and active-workflow
errors are non-retryable; do not retry them or treat local closure files as
admission evidence. If no legal current action remains, report an incomplete
result rather than inventing a recovery path.
"""


def _toml_string(value: str) -> str:
    """Encode one string as a TOML basic string for ``codex -c``."""

    return json.dumps(value, ensure_ascii=False)


def _toml_array(values: Sequence[str]) -> str:
    return "[" + ", ".join(_toml_string(value) for value in values) + "]"


def _toml_table(values: Mapping[str, str]) -> str:
    return "{" + ", ".join(f"{_toml_string(str(key))} = {_toml_string(str(value))}" for key, value in values.items()) + "}"


def _load_mcp_server(config_path: Path, *, strict: bool) -> tuple[str, tuple[str, ...], dict[str, str]]:
    """Read the one runner-owned server from the Desktop JSON config."""

    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CodexAdapterError(f"runner-owned MCP config is unreadable: {config_path}") from exc
    servers = raw.get("mcpServers") if isinstance(raw, Mapping) else None
    if not isinstance(servers, Mapping):
        raise CodexAdapterError("runner-owned MCP config has no mcpServers mapping")
    if strict and set(servers) != {"nxd-desktop"}:
        raise CodexAdapterError("strict MCP config must contain exactly nxd-desktop")
    server = servers.get("nxd-desktop")
    if not isinstance(server, Mapping):
        raise CodexAdapterError("runner-owned MCP config has no nxd-desktop server")
    command = server.get("command")
    args = server.get("args", [])
    environment = server.get("env", {})
    if not isinstance(command, str) or not command:
        raise CodexAdapterError("nxd-desktop MCP command is missing")
    if not isinstance(args, Sequence) or isinstance(args, (str, bytes, bytearray)) or not all(isinstance(item, str) for item in args):
        raise CodexAdapterError("nxd-desktop MCP args are malformed")
    if not isinstance(environment, Mapping) or not all(isinstance(key, str) and isinstance(value, str) for key, value in environment.items()):
        raise CodexAdapterError("nxd-desktop MCP environment is malformed")
    return command, tuple(args), dict(environment)


def _decode_mcp_value(value: object) -> object:
    """Extract structured JSON from common Codex MCP result envelopes."""

    if isinstance(value, Mapping):
        for key in ("structured_content", "structuredContent"):
            structured = value.get(key)
            if isinstance(structured, Mapping):
                return structured
        if "content" in value:
            return _decode_mcp_value(value.get("content"))
        if "result" in value and len(value) <= 2:
            return _decode_mcp_value(value.get("result"))
        return value
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        texts: list[str] = []
        for item in value:
            if isinstance(item, Mapping) and isinstance(item.get("text"), str):
                texts.append(item["text"])
            elif isinstance(item, str):
                texts.append(item)
        if len(texts) == 1:
            try:
                return json.loads(texts[0])
            except json.JSONDecodeError:
                return texts[0]
        return list(value)
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _codex_mcp_name(item: Mapping[str, object]) -> str | None:
    """Normalize Codex's server/tool fields to the harness MCP vocabulary."""

    name = item.get("name")
    if isinstance(name, str) and name.startswith("mcp__"):
        return name
    server = item.get("server")
    tool = item.get("tool") or name
    if isinstance(server, str) and isinstance(tool, str) and server and tool:
        return f"mcp__{server}__{tool}"
    return None


def _item_arguments(item: Mapping[str, object]) -> object:
    return item.get("arguments", item.get("input", {}))


def _item_result(item: Mapping[str, object]) -> object:
    if "result" in item:
        return item.get("result")
    if "output" in item:
        return item.get("output")
    return item.get("content")


def _collab_agent_result(item: Mapping[str, object]) -> Mapping[str, object]:
    """Project a completed Codex child state into the shared Agent shape."""

    states = item.get("agentsStates")
    messages: list[object] = []
    child_statuses: list[str] = []
    if isinstance(states, Mapping):
        for state in states.values():
            if not isinstance(state, Mapping):
                continue
            status = state.get("status")
            if isinstance(status, str):
                child_statuses.append(status)
            if state.get("message") is not None:
                messages.append(state.get("message"))
    status = item.get("status")
    return {
        "is_error": (
            status not in {"completed", "success", "succeeded"}
            or any(
                child_status not in {"completed", "success", "succeeded"}
                for child_status in child_statuses
            )
        ),
        "content": messages,
    }


_COLLAB_SUCCESS_STATUSES = {"completed", "success", "succeeded"}
_COLLAB_FAILURE_STATUSES = {"failed", "errored", "interrupted", "shutdown", "notFound"}


def _collab_states(item: Mapping[str, object]) -> tuple[tuple[str, ...], list[object]]:
    """Return child statuses and non-empty child messages from one collab item."""

    states = item.get("agentsStates")
    statuses: list[str] = []
    messages: list[object] = []
    if not isinstance(states, Mapping):
        return (), messages
    for state in states.values():
        if not isinstance(state, Mapping):
            continue
        status = state.get("status")
        if isinstance(status, str):
            statuses.append(status)
        message = state.get("message")
        if isinstance(message, str) and message.strip():
            messages.append(message)
    return tuple(statuses), messages


def _collab_result_ready(item: Mapping[str, object]) -> bool:
    """Whether a collab item contains a terminal child outcome to grade."""

    status = item.get("status")
    child_statuses, messages = _collab_states(item)
    if status in _COLLAB_FAILURE_STATUSES or any(
        child_status in _COLLAB_FAILURE_STATUSES for child_status in child_statuses
    ):
        return True
    if status not in _COLLAB_SUCCESS_STATUSES:
        return False
    # ``spawnAgent`` completing means the request was accepted, not that the
    # child answered.  The child state and its message are required before the
    # adapter emits the shared Agent observation.  A later ``wait`` item may
    # carry that state.
    return bool(child_statuses) and all(value in _COLLAB_SUCCESS_STATUSES for value in child_statuses) and bool(messages)


def _merge_collab_item(
    base: Mapping[str, object], update: Mapping[str, object]
) -> dict[str, object]:
    """Merge a later wait/update snapshot into its original spawn item."""

    merged = dict(base)
    for key in ("status", "agentsStates", "receiverThreadIds"):
        if key in update:
            merged[key] = update[key]
    return merged


def _collab_receiver_ids(item: Mapping[str, object]) -> set[str]:
    values = item.get("receiverThreadIds")
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        return set()
    return {value for value in values if isinstance(value, str) and value}


def _normalise_app_server_event(event: Mapping[str, object]) -> Mapping[str, object]:
    """Map one app-server notification to the adapter's event vocabulary."""

    method = event.get("method")
    params = event.get("params")
    if not isinstance(method, str) or not isinstance(params, Mapping):
        return event
    if method == "thread/started":
        thread = params.get("thread")
        thread_id = thread.get("id") if isinstance(thread, Mapping) else None
        return {"type": "thread.started", "thread_id": thread_id}
    if method == "turn/completed":
        turn = params.get("turn")
        status = turn.get("status") if isinstance(turn, Mapping) else None
        event_type = {
            "completed": "turn.completed",
            "interrupted": "turn.interrupted",
        }.get(status, "turn.failed")
        return {
            "type": event_type,
            "is_error": status != "completed",
            "error": turn.get("error") if isinstance(turn, Mapping) else None,
        }
    if method == "turn/started":
        return {"type": "turn.started"}
    if method == "item/agentMessage/delta":
        return {"type": "agent_message_delta", "delta": params.get("delta", "")}
    if method == "mcpServer/startupStatus/updated":
        if params.get("status") != "failed":
            return {"type": "mcp_server_status"}
        return {
            "type": "mcp_server_failed",
            "server": params.get("name"),
            "error": params.get("error") or params.get("failureReason") or "startup failed",
        }
    if method in {"item/started", "item/completed"}:
        item = params.get("item")
        if not isinstance(item, Mapping):
            return {"type": method}
        item_type = item.get("type")
        if item_type == "agentMessage":
            return {
                "type": method.replace("/", "."),
                "item": {"type": "agent_message", "text": item.get("text", "")},
            }
        if item_type == "mcpToolCall":
            normalized = dict(item)
            normalized["type"] = "mcp_tool_call"
            normalized["is_error"] = item.get("status") == "failed"
            return {"type": method.replace("/", "."), "item": normalized}
        if item_type == "commandExecution":
            normalized = dict(item)
            normalized["type"] = "command_execution"
            if "aggregatedOutput" in normalized and "aggregated_output" not in normalized:
                normalized["aggregated_output"] = normalized["aggregatedOutput"]
            return {"type": method.replace("/", "."), "item": normalized}
        if item_type == "fileChange":
            normalized = dict(item)
            normalized["type"] = "file_change"
            return {"type": method.replace("/", "."), "item": normalized}
        if item_type in {"collabAgentToolCall", "collab_tool_call"}:
            normalized = dict(item)
            normalized["type"] = "collab_agent_tool_call"
            if "agents_states" in normalized and "agentsStates" not in normalized:
                normalized["agentsStates"] = normalized.pop("agents_states")
            if "receiver_thread_ids" in normalized and "receiverThreadIds" not in normalized:
                normalized["receiverThreadIds"] = normalized.pop("receiver_thread_ids")
            tool = normalized.get("tool")
            if tool == "spawn_agent":
                normalized["tool"] = "spawnAgent"
            status = normalized.get("status")
            if status == "in_progress":
                normalized["status"] = "inProgress"
            return {"type": method.replace("/", "."), "item": normalized}
        return {"type": method.replace("/", "."), "item": dict(item)}
    return event


def _event_debug_tail(events: Sequence[Mapping[str, object]], *, limit: int = 12) -> str | None:
    """Return a bounded, value-free event tail for timeout diagnostics."""

    labels: list[str] = []
    for event in events[-limit:]:
        method = event.get("method")
        if not isinstance(method, str):
            event_type = event.get("type")
            method = event_type if isinstance(event_type, str) else "event"
        params = event.get("params")
        if isinstance(params, Mapping):
            item = params.get("item")
            if isinstance(item, Mapping):
                item_type = item.get("type")
                if isinstance(item_type, str):
                    method += f"[{item_type}]"
                if item_type == "mcpToolCall":
                    server = item.get("server")
                    tool = item.get("tool")
                    if isinstance(server, str) and isinstance(tool, str):
                        method += f":{server}/{tool}"
                status = item.get("status")
                if isinstance(status, str):
                    method += f"={status}"
            turn = params.get("turn")
            if isinstance(turn, Mapping):
                status = turn.get("status")
                if isinstance(status, str):
                    method += f"={status}"
        labels.append(method)
    return ", ".join(labels) if labels else None


def parse_codex_events(
    events: Sequence[Mapping[str, object]],
    *,
    redact_json_rpc: Any,
    redact_text: Any,
    session_id: str | None,
) -> tuple[TurnResult, list[dict[str, object]]]:
    """Convert one Codex JSONL turn into structured harness observations."""

    transcript: list[str] = []
    final_answer = ""
    calls: list[ToolCall] = []
    flat_results: list[object] = []
    observations: list[dict[str, object]] = []
    pending: dict[str, tuple[str, object]] = {}
    pending_collab: dict[str, Mapping[str, object]] = {}
    terminal_count = 0
    terminal_subtype: str | None = None
    terminal_is_error: bool | None = None
    thread_id = session_id
    build_failures = 0
    environment_details: list[str] = []
    partial_answer: list[str] = []

    def record_collab_call(
        started: Mapping[str, object], completed: Mapping[str, object]
    ) -> None:
        prompt = started.get("prompt", completed.get("prompt", ""))
        arguments = {
            # Codex's built-in spawnAgent is the provider-native equivalent
            # of the general-purpose Agent/Task child required by the
            # workflow contract. The mapping is emitted only for an
            # observed, completed child; it is not agent prose.
            "subagent_type": "general-purpose",
            "prompt": prompt,
        }
        result_value = _collab_agent_result(completed)
        calls.append(ToolCall("Agent", redact_json_rpc(arguments), result_value))
        flat_results.append(redact_json_rpc(result_value))
        transcript.append(
            "[tool_use:Agent] "
            + redact_text(json.dumps(arguments, default=str)[:600])
        )
        transcript.append(
            "[tool_result] "
            + redact_text(json.dumps(result_value, default=str)[:1500])
        )

    for event in events:
        event = _normalise_app_server_event(event)
        event_type = event.get("type")
        if event_type == "thread.started":
            value = event.get("thread_id")
            if isinstance(value, str) and value:
                thread_id = value
            continue
        if event_type == "turn.failed":
            terminal_count += 1
            terminal_subtype = "failed"
            terminal_is_error = True
            error = event.get("error")
            detail = error if isinstance(error, str) else json.dumps(error, default=str)
            environment_details.append(detail)
            continue
        if event_type == "turn.interrupted":
            terminal_count += 1
            terminal_subtype = "interrupted"
            terminal_is_error = True
            continue
        if event_type == "turn.completed":
            terminal_count += 1
            # The shared operator contract uses Claude's terminal vocabulary:
            # a normal provider completion is a successful turn. Keeping
            # Codex's wire word (``completed``) here makes an otherwise
            # healthy full run look like ``script_exhausted``.
            terminal_subtype = "success"
            raw_error = event.get("is_error")
            terminal_is_error = raw_error if isinstance(raw_error, bool) else False
            continue
        if event_type == "mcp_server_failed":
            environment_details.append(
                f"MCP server {event.get('server', 'unknown')} failed: {event.get('error', 'startup failed')}"
            )
            continue
        if event_type == "agent_message_delta":
            delta = event.get("delta")
            if isinstance(delta, str) and delta:
                partial_answer.append(delta)
            continue
        if event_type not in {"item.started", "item.completed"}:
            continue
        item = event.get("item")
        if not isinstance(item, Mapping):
            continue
        item_type = item.get("type")
        if item_type == "agent_message":
            text = item.get("text")
            if isinstance(text, str) and text.strip():
                final_answer = text.strip()
                transcript.append("[assistant] " + redact_text(final_answer))
            continue
        if item_type == "command_execution" and event_type == "item.completed":
            command = str(item.get("command", ""))
            result = item.get("aggregated_output", item.get("output"))
            calls.append(ToolCall("Bash", command, result))
            transcript.append("[tool_use:Bash] " + redact_text(command[:600]))
            transcript.append("[tool_result] " + redact_text(str(result)[:1500]))
            continue
        if item_type in {"file_change", "patch", "apply_patch"} and event_type == "item.completed":
            calls.append(ToolCall("codex_file_change", redact_json_rpc(dict(item)), None))
            transcript.append("[tool_use:file_change] " + redact_text(json.dumps(dict(item), default=str)[:600]))
            continue
        if item_type == "collab_agent_tool_call":
            tool = item.get("tool")
            key = str(item.get("id") or f"Agent:{len(calls)}")
            if tool == "spawnAgent" and event_type == "item.started":
                pending_collab[key] = item
                continue
            if tool == "spawnAgent" and event_type == "item.completed":
                started = pending_collab.get(key, item)
                candidate = _merge_collab_item(started, item)
                if not _collab_result_ready(candidate):
                    # A completed spawn request only means that the child was
                    # accepted. Keep it until a later wait item reports the
                    # child's terminal state and response.
                    pending_collab[key] = candidate
                    continue
                pending_collab.pop(key, None)
                record_collab_call(started, candidate)
                continue
            if tool == "wait" and event_type == "item.completed":
                wait_ids = _collab_receiver_ids(item)
                matches = [
                    pending_key
                    for pending_key, pending_item in pending_collab.items()
                    if wait_ids & _collab_receiver_ids(pending_item)
                ]
                if not matches and len(pending_collab) == 1:
                    matches = [next(iter(pending_collab))]
                for pending_key in matches:
                    started = pending_collab[pending_key]
                    candidate = _merge_collab_item(started, item)
                    if not _collab_result_ready(candidate):
                        pending_collab[pending_key] = candidate
                        continue
                    pending_collab.pop(pending_key, None)
                    record_collab_call(started, candidate)
            continue
        if item_type not in {"mcp_tool_call", "mcp_tool_result"}:
            continue
        name = _codex_mcp_name(item)
        if name is None:
            continue
        key = str(item.get("id") or f"{name}:{len(calls)}")
        arguments = _item_arguments(item)
        if event_type == "item.started":
            pending[key] = (name, arguments)
            continue
        pending.pop(key, None)
        raw_result = _item_result(item)
        is_error = bool(item.get("is_error", False) or item.get("error") or item.get("status") == "failed")
        if raw_result is None and is_error:
            # A completed MCP error is still an answered call.  Leaving it as
            # ``None`` makes the shared checkpoint transport classify the call
            # as in-flight and defer turn 1, which then makes the next turn
            # look like an invalid first checkpoint.
            raw_result = {"error": item.get("error") or "MCP tool returned an error"}
        elif raw_result is None and event_type == "item.completed":
            # A successful void MCP result is still an answered call. Keep a
            # structured sentinel so checkpoint transport does not classify it
            # as an in-flight tool use.
            raw_result = {}
        result = _decode_mcp_value(raw_result)
        safe_arguments = redact_json_rpc(arguments)
        safe_result = redact_json_rpc(result)
        calls.append(ToolCall(name, safe_arguments, safe_result))
        flat_results.append(safe_result)
        transcript.append("[tool_use:" + name + "] " + redact_text(json.dumps(safe_arguments, default=str)[:600]))
        transcript.append("[tool_result] " + redact_text(json.dumps(safe_result, default=str)[:1500]))
        mcp_tool = _mcp_name(name)
        if mcp_tool is None:
            continue
        observation = {
            "tool": mcp_tool,
            "arguments": arguments,
            "result": result,
            "is_error": is_error,
            "answered": True,
        }
        observations.append(observation)
        if mcp_tool == "advance_workflow" and _advance_action_type(arguments) == "start_run" and is_error:
            build_failures += 1

    for name, arguments in pending.values():
        calls.append(ToolCall(name, redact_json_rpc(arguments), None))
        mcp_tool = _mcp_name(name)
        if mcp_tool is not None:
            observations.append({"tool": mcp_tool, "arguments": arguments, "result": None, "is_error": True, "answered": False})
            environment_details.append(f"MCP tool use had no matching result: {mcp_tool}")

    for item in pending_collab.values():
        arguments = {
            "subagent_type": "general-purpose",
            "prompt": item.get("prompt", ""),
        }
        calls.append(
            ToolCall(
                "Agent",
                redact_json_rpc(arguments),
                {"is_error": True, "content": []},
            )
        )
        environment_details.append("Codex reviewer child had no matching completion")

    if not final_answer and partial_answer:
        final_answer = "".join(partial_answer)
        transcript.append("[assistant] " + redact_text(final_answer))
    last_mcp_call: str | None = None
    if observations:
        last = observations[-1]
        last_mcp_call = f"{last['tool']}:{'unanswered' if not last['answered'] else 'error' if last['is_error'] else 'ok'}"
    result = TurnResult(
        transcript_delta="\n".join(transcript),
        agent_message=redact_text(final_answer),
        tool_calls=tuple(calls),
        tool_results=tuple(flat_results),
        build_failed=build_failures > 0,
        build_failure_count=build_failures,
        environment_wedged=bool(environment_details) or terminal_is_error is True,
        environment_detail=redact_text(" | ".join(environment_details)) if environment_details else None,
        failure_reason=classify_failure_reason(" | ".join(environment_details)),
        last_mcp_call=last_mcp_call,
        session_id=thread_id,
        terminal_result_count=terminal_count,
        terminal_result_subtype=terminal_subtype,
        terminal_result_is_error=terminal_is_error,
    )
    return result, observations


class CodexAdapter:
    """One Codex thread resumed across the scripted operator turns."""

    MCP_STARTUP_TIMEOUT_S = 30.0

    def __init__(
        self,
        *,
        codex: Path,
        model: str,
        effort: str,
        skill_pack_root: Path,
        repo_root: Path,
        fixture_dir: Path,
        artifact_dir: Path,
        desktop_supervisor: Path,
        desktop_python: Path,
        timeout_s: float,
        append_system_prompt: str,
        mcp_config: Path | None = None,
        strict_mcp_config: bool = False,
        allowed_tools: str | None = None,
        supervisor_data_dir: Path | None = None,
        native_continuation: bool = False,
        resume_session_id: str | None = None,
    ) -> None:
        self.codex = codex
        self.model = model
        self.effort = effort
        self.skill_pack_root = skill_pack_root
        self.repo_root = repo_root
        self.fixture_dir = fixture_dir
        self.artifact_dir = artifact_dir
        self.desktop_supervisor = desktop_supervisor
        self.desktop_python = desktop_python
        self.timeout_s = timeout_s
        self.append_system_prompt = append_system_prompt
        self.mcp_config = mcp_config
        self.strict_mcp_config = strict_mcp_config
        self.allowed_tools = allowed_tools
        self.supervisor_data_dir = supervisor_data_dir
        self.native_continuation = bool(native_continuation)
        self._thread_id = resume_session_id
        self._started = False
        self._before: dict[str, bytes] = {}
        self._facts: dict[str, object] = {}
        self._build_context: dict[str, object] = {}
        self._lifecycles: dict[str, str] = {}
        self._built_runs: set[str] = set()
        self._query_history: list[dict[str, object]] = []
        self._last_mcp_call: str | None = None
        self._redact_json_rpc, self._redact_text = self._load_redactors()
        self._process: subprocess.Popen[bytes] | None = None
        self._rpc_id = 0
        self._stdout_buffer = b""
        self._stdout_events: deque[Mapping[str, object]] = deque()
        self._stderr_tail: deque[str] = deque(maxlen=80)
        self._stderr_open = True
        self._startup_events: list[Mapping[str, object]] = []
        self._mcp_status: tuple[Mapping[str, object], ...] = ()
        self._codex_home_temp: tempfile.TemporaryDirectory[str] | None = None
        if resume_session_id is not None and not native_continuation:
            raise CodexAdapterError("--resume-session-id requires native continuation mode")
        if resume_session_id is not None:
            if not isinstance(resume_session_id, str) or not resume_session_id.strip():
                raise CodexAdapterError("Codex session identity must be a non-empty opaque string")

    def _load_redactors(self) -> tuple[Any, Any]:
        _stdio_type, redact_json_rpc, redact_text = _load_desktop_stdio(self.repo_root)
        return redact_json_rpc, redact_text

    @property
    def last_mcp_call(self) -> str | None:
        return self._last_mcp_call

    def start(self) -> None:
        if self._started:
            return
        for path, label in (
            (self.codex, "codex executable"),
            (self.skill_pack_root, "skill-pack root"),
            (self.artifact_dir, "artifact directory"),
        ):
            if label == "artifact directory":
                path.mkdir(parents=True, exist_ok=True)
            elif not path.exists():
                raise CodexAdapterError(f"{label} does not exist: {path}")
        if self.mcp_config is None:
            raise CodexAdapterError("Codex adapter requires the runner-owned --mcp-config")
        if self.supervisor_data_dir is None or not self.supervisor_data_dir.is_dir():
            raise CodexAdapterError("Codex adapter requires an existing --supervisor-data-dir")
        self._before = _snapshot_workspace(Path.cwd(), artifact_dir=self.artifact_dir)
        environment = dict(os.environ)
        for key in (
            "OPENAI_API_KEY",
            "CLAUDE_CODE_OAUTH_TOKEN",
            "NXD_EVAL_SOURCE_TOKEN",
            "NXD_DESKTOP_TRUSTED_CREDENTIAL_ENVS",
        ):
            environment.pop(key, None)
        self._codex_home_temp = self._isolated_codex_home(environment)
        if self._codex_home_temp is not None:
            environment["CODEX_HOME"] = self._codex_home_temp.name
        try:
            self._process = subprocess.Popen(
                self._app_server_command(),
                cwd=Path.cwd(),
                env=environment,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
            self._initialize_app_server()
        except Exception:
            if self._process is not None:
                self._terminate(self._process)
                self._process = None
            if self._codex_home_temp is not None:
                self._codex_home_temp.cleanup()
                self._codex_home_temp = None
            raise
        self._started = True

    def _isolated_codex_home(self, environment: Mapping[str, str]) -> tempfile.TemporaryDirectory[str]:
        """Stage only the host Codex auth handle into a disposable home.

        ``app-server`` has no ``--ignore-user-config`` flag. Keeping its
        state/config home separate prevents host MCP configuration and plugin
        state from entering a benchmark run. The auth file is symlinked, not
        read or copied, so the provider credential stays in the host-owned
        store and never enters run artifacts.
        """

        temporary = tempfile.TemporaryDirectory(prefix="dp-scenario-codex-home-")
        home = Path(temporary.name)
        (home / "config.toml").write_text(
            "# dp-scenarios app-server home; MCP is supplied by the runner.\n",
            encoding="utf-8",
        )
        source_value = environment.get("CODEX_HOME")
        if isinstance(source_value, str) and source_value:
            auth = Path(source_value).expanduser() / "auth.json"
            if auth.is_file():
                os.symlink(auth, home / "auth.json")
        return temporary

    def _app_server_command(self) -> list[str]:
        """Build the long-lived Codex app-server command."""

        server = self._mcp_server_config()
        command = [
            str(self.codex),
            "app-server",
            "--stdio",
            "--enable",
            "multi_agent",
            "-c",
            'approval_policy="never"',
            "-c",
            f"model_reasoning_effort={_toml_string(self.effort)}",
        ]
        command.extend(
            (
                "-c",
                f"mcp_servers.nxd-desktop.command={_toml_string(str(server['command']))}",
                "-c",
                f"mcp_servers.nxd-desktop.args={_toml_array(tuple(server['args']))}",
                "-c",
                f"mcp_servers.nxd-desktop.default_tools_approval_mode={_toml_string('approve')}",
                "-c",
                "mcp_servers.nxd-desktop.required=true",
                "-c",
                "mcp_servers.nxd-desktop.startup_timeout_sec=30",
            )
        )
        if server["env"]:
            command.extend(("-c", f"mcp_servers.nxd-desktop.env={_toml_table(server['env'])}"))
        return command

    def _mcp_server_config(self) -> dict[str, object]:
        assert self.mcp_config is not None
        command, args, environment = _load_mcp_server(self.mcp_config, strict=self.strict_mcp_config)
        return {
            "command": command,
            "args": list(args),
            "env": environment,
            "default_tools_approval_mode": "approve",
            "required": True,
            "startup_timeout_sec": 30,
        }

    def _thread_config(self) -> dict[str, object]:
        return {
            "approval_policy": "never",
            "model_reasoning_effort": self.effort,
            "mcp_servers": {"nxd-desktop": self._mcp_server_config()},
        }

    def _base_instructions(self) -> str:
        return (
            self.append_system_prompt
            + "\n\nThe skill pack is available at: "
            + str(self.skill_pack_root)
            + "\nRead the relevant SKILL.md and reference files from that path."
        )

    def _thread_params(self) -> dict[str, object]:
        return {
            "model": self.model,
            "cwd": str(Path.cwd()),
            "sandbox": "workspace-write",
            "approvalPolicy": "never",
            "runtimeWorkspaceRoots": [str(Path.cwd()), str(self.skill_pack_root)],
            "config": self._thread_config(),
            "baseInstructions": self._base_instructions(),
        }

    def _resume_params(self) -> dict[str, object]:
        assert self._thread_id is not None
        return {
            "threadId": self._thread_id,
            "model": self.model,
            "cwd": str(Path.cwd()),
            "sandbox": "workspace-write",
            "approvalPolicy": "never",
            "runtimeWorkspaceRoots": [str(Path.cwd()), str(self.skill_pack_root)],
            "config": self._thread_config(),
            "baseInstructions": self._base_instructions(),
            "excludeTurns": True,
        }

    @staticmethod
    def _decode_app_server_line(raw: bytes) -> Mapping[str, object]:
        """Decode one app-server JSONL frame and reject non-object values."""

        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CodexAdapterError("Codex app-server emitted malformed JSON") from exc
        if not isinstance(value, Mapping):
            raise CodexAdapterError("Codex app-server emitted a non-object JSON event")
        return value

    def _write_rpc(self, method: str, params: Mapping[str, object], *, request_id: int | None = None) -> int | None:
        process = self._process
        if process is None or process.stdin is None:
            raise CodexAdapterError("Codex app-server is not running")
        payload: dict[str, object] = {"jsonrpc": "2.0", "method": method, "params": dict(params)}
        if request_id is not None:
            payload["id"] = request_id
        process.stdin.write((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
        process.stdin.flush()
        return request_id

    def _next_rpc_id(self) -> int:
        self._rpc_id += 1
        return self._rpc_id

    def _read_streams(self, deadline: float) -> Mapping[str, object]:
        process = self._process
        if process is None or process.stdout is None or process.stderr is None:
            raise CodexAdapterError("Codex app-server streams are unavailable")
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Codex app-server response deadline expired")
            if self._stdout_events:
                return self._stdout_events.popleft()
            streams = [process.stdout]
            if self._stderr_open:
                streams.append(process.stderr)
            ready, _, _ = select.select(streams, (), (), remaining)
            if not ready:
                raise TimeoutError("Codex app-server response deadline expired")
            for stream in ready:
                if stream.fileno() == process.stderr.fileno():
                    chunk = os.read(process.stderr.fileno(), 65536)
                    if chunk:
                        text = chunk.decode("utf-8", errors="replace")
                        self._stderr_tail.extend(text.splitlines())
                    else:
                        # EOF is readable forever on a pipe. Remove stderr
                        # from the selector or a quiet provider child can
                        # bypass the response deadline indefinitely.
                        self._stderr_open = False
                    continue
                chunk = os.read(process.stdout.fileno(), 65536)
                if not chunk:
                    detail = "\n".join(self._stderr_tail)[-2000:]
                    raise CodexAdapterError(
                        "Codex app-server exited before returning an event"
                        + (f": {detail}" if detail else "")
                    )
                self._stdout_buffer += chunk
                while b"\n" in self._stdout_buffer:
                    raw, self._stdout_buffer = self._stdout_buffer.split(b"\n", 1)
                    if not raw.strip():
                        continue
                    self._stdout_events.append(self._decode_app_server_line(raw))
            if self._stdout_events:
                return self._stdout_events.popleft()

    def _read_until_response(
        self,
        request_id: int,
        deadline: float,
        collected: list[Mapping[str, object]] | None = None,
    ) -> tuple[Mapping[str, object], list[Mapping[str, object]]]:
        events: list[Mapping[str, object]] = []
        while True:
            event = self._read_streams(deadline)
            if self._is_server_request(event):
                self._reject_server_request(event)
                continue
            if event.get("id") == request_id:
                return event, events
            if collected is None:
                events.append(event)
            else:
                collected.append(event)

    @staticmethod
    def _is_server_request(event: Mapping[str, object]) -> bool:
        return isinstance(event.get("method"), str) and "id" in event

    def _reject_server_request(self, event: Mapping[str, object]) -> None:
        """Fail closed when app-server asks the non-interactive runner to approve."""

        process = self._process
        request_id = event.get("id")
        method = event.get("method")
        if process is not None and process.stdin is not None and request_id is not None:
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32001,
                    "message": "dp-scenarios Codex runner cannot answer interactive server requests",
                },
            }
            process.stdin.write((json.dumps(response) + "\n").encode("utf-8"))
            process.stdin.flush()
        raise CodexAdapterError(f"Codex app-server requested unsupported interaction: {method}")

    def _initialize_app_server(self) -> None:
        initialize_id = self._next_rpc_id()
        self._write_rpc(
            "initialize",
            {
                "clientInfo": {
                    "name": "dp-scenarios-codex-runner",
                    "title": "dp-scenarios Codex runner",
                    "version": "1",
                },
                "capabilities": {"experimentalApi": True},
            },
            request_id=initialize_id,
        )
        response, events = self._read_until_response(initialize_id, time.monotonic() + self.timeout_s)
        if "error" in response:
            raise CodexAdapterError(f"Codex app-server initialize failed: {response['error']}")
        self._startup_events.extend(events)
        self._write_rpc("initialized", {})
        request_method = "thread/resume" if self._thread_id is not None else "thread/start"
        request_id = self._next_rpc_id()
        params = self._resume_params() if self._thread_id is not None else self._thread_params()
        self._write_rpc(request_method, params, request_id=request_id)
        response, events = self._read_until_response(request_id, time.monotonic() + self.timeout_s)
        if "error" in response:
            raise CodexAdapterError(f"Codex app-server {request_method} failed: {response['error']}")
        self._startup_events.extend(events)
        result = response.get("result")
        thread = result.get("thread") if isinstance(result, Mapping) else None
        thread_id = thread.get("id") if isinstance(thread, Mapping) else None
        if not isinstance(thread_id, str) or not thread_id:
            raise CodexAdapterError(f"Codex app-server {request_method} returned no thread identity")
        self._thread_id = thread_id

        # A thread can start successfully while an MCP server is still absent
        # from the model's tool catalog. Query the app-server's authoritative
        # inventory before spending a turn on a run that cannot exercise the
        # supervisor. Keep only the non-sensitive status projection in the
        # adapter so diagnostics never include server configuration or auth.
        status_deadline = time.monotonic() + min(
            self.timeout_s, self.MCP_STARTUP_TIMEOUT_S
        )
        last_status = "no server status"
        while True:
            status_id = self._next_rpc_id()
            self._write_rpc(
                "mcpServerStatus/list",
                {"threadId": self._thread_id, "detail": "toolsAndAuthOnly"},
                request_id=status_id,
            )
            response, events = self._read_until_response(
                status_id, min(status_deadline, time.monotonic() + self.timeout_s)
            )
            self._startup_events.extend(events)
            if "error" in response:
                raise CodexAdapterError(f"Codex app-server MCP status failed: {response['error']}")
            result = response.get("result")
            data = result.get("data") if isinstance(result, Mapping) else None
            if not isinstance(data, list):
                raise CodexAdapterError("Codex app-server MCP status returned no server list")
            statuses = tuple(item for item in data if isinstance(item, Mapping))
            self._mcp_status = statuses
            server = next((item for item in statuses if item.get("name") == "nxd-desktop"), None)
            tools = server.get("tools") if server is not None else None
            runtime_status = server.get("runtimeStatus") if server is not None else None
            tool_count = len(tools) if isinstance(tools, Mapping) else 0
            if runtime_status == "connected" and tool_count > 0:
                return
            last_status = (
                f"runtime_status={runtime_status!r}, tools={tool_count}"
            )
            if time.monotonic() >= status_deadline:
                raise CodexAdapterError(
                    "Codex app-server nxd-desktop MCP is not ready: " + last_status
                )
            time.sleep(min(0.1, max(0.0, status_deadline - time.monotonic())))

    def _collect_turn(
        self,
        request_id: int,
        prompt: str,
        events: list[Mapping[str, object]],
    ) -> list[Mapping[str, object]]:
        response, before_turn = self._read_until_response(
            request_id,
            time.monotonic() + self.timeout_s,
            collected=events,
        )
        if "error" in response:
            raise CodexAdapterError(f"Codex app-server turn/start failed: {response['error']}")
        events.extend(before_turn)
        result = response.get("result")
        turn = result.get("turn") if isinstance(result, Mapping) else None
        turn_id = turn.get("id") if isinstance(turn, Mapping) else None
        if not isinstance(turn_id, str) or not turn_id:
            raise CodexAdapterError("Codex app-server turn/start returned no turn identity")
        deadline = time.monotonic() + self.timeout_s
        while True:
            event = self._read_streams(deadline)
            if self._is_server_request(event):
                self._reject_server_request(event)
                continue
            events.append(event)
            normalized = _normalise_app_server_event(event)
            if normalized.get("type") in {"turn.completed", "turn.interrupted", "turn.failed"}:
                params = event.get("params")
                completed_turn = params.get("turn") if isinstance(params, Mapping) else None
                completed_id = completed_turn.get("id") if isinstance(completed_turn, Mapping) else None
                if completed_id != turn_id:
                    continue
                break
        return events

    def _prompt(self, text: str, attachment_paths: Sequence[str]) -> str:
        if attachment_paths:
            text += "\n\nAttached files are available at:\n" + "\n".join(f"- {path}" for path in attachment_paths)
        return text

    def _terminate(self, process: subprocess.Popen[bytes]) -> None:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.killpg(process.pid, signal.SIGKILL)
            with contextlib.suppress(subprocess.TimeoutExpired):
                process.wait(timeout=3)

    def _finish(
        self,
        events: Sequence[Mapping[str, object]],
        *,
        environment_detail: str | None = None,
        turn_timed_out: bool = False,
        failure_reason: str | None = None,
    ) -> TurnResult:
        parsed, observations = parse_codex_events(
            events,
            redact_json_rpc=self._redact_json_rpc,
            redact_text=self._redact_text,
            session_id=self._thread_id,
        )
        if parsed.session_id:
            self._thread_id = parsed.session_id
        if parsed.last_mcp_call:
            self._last_mcp_call = parsed.last_mcp_call
        after = _snapshot_workspace(Path.cwd(), artifact_dir=self.artifact_dir)
        changed = _changed_files(self._before, after)
        self._before = after
        _update_machine_artifacts(
            observations,
            artifact_dir=self.artifact_dir,
            facts=self._facts,
            build_context=self._build_context,
            lifecycles=self._lifecycles,
            built_runs=self._built_runs,
            query_history=self._query_history,
        )
        workflow = self._build_context.get("workflow")
        _update_from_state_dir(
            self.supervisor_data_dir,
            facts=self._facts,
            built_runs=self._built_runs,
            workflow=workflow if isinstance(workflow, str) and workflow else None,
        )
        _write_supervisor_facts(self._facts, artifact_dir=self.artifact_dir)
        details = [value for value in (parsed.environment_detail, environment_detail) if value]
        safe_detail = self._redact_text(" | ".join(dict.fromkeys(details))) if details else None
        return TurnResult(
            transcript_delta=parsed.transcript_delta,
            agent_message=parsed.agent_message,
            tool_calls=parsed.tool_calls,
            tool_results=parsed.tool_results,
            files_touched=changed,
            approval_artifact=None,
            build_failed=parsed.build_failed,
            build_failure_count=parsed.build_failure_count,
            environment_wedged=(parsed.environment_wedged or environment_detail is not None) and not turn_timed_out,
            turn_timed_out=parsed.turn_timed_out or turn_timed_out,
            environment_detail=safe_detail,
            failure_reason=first_reason((failure_reason, parsed.failure_reason)),
            last_mcp_call=parsed.last_mcp_call or self._last_mcp_call,
            session_id=self._thread_id,
            terminal_result_count=parsed.terminal_result_count,
            terminal_result_subtype=parsed.terminal_result_subtype,
            terminal_result_is_error=parsed.terminal_result_is_error,
        )

    def send(self, request: Mapping[str, object]) -> TurnResult:
        self.start()
        message = request.get("message")
        if not isinstance(message, Mapping):
            raise CodexAdapterError("turn request has no message object")
        text = str(message.get("text", ""))
        attachments = message.get("attachments", [])
        attachment_paths: list[str] = []
        if isinstance(attachments, Sequence) and not isinstance(attachments, (str, bytes, bytearray)):
            incoming = Path.cwd() / "incoming"
            for index, attachment in enumerate(attachments, start=1):
                if not isinstance(attachment, Mapping):
                    raise CodexAdapterError("turn attachment is not an object")
                encoded = attachment.get("content")
                if not isinstance(encoded, Mapping) or not isinstance(encoded.get("__bytes__"), str):
                    raise CodexAdapterError("turn attachment content is not encoded bytes")
                try:
                    content = base64.b64decode(encoded["__bytes__"], validate=True)
                except (ValueError, base64.binascii.Error) as exc:
                    raise CodexAdapterError("turn attachment content is not valid bytes") from exc
                name = Path(str(attachment.get("name", f"attachment-{index}"))).name or f"attachment-{index}"
                target = incoming / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
                attachment_paths.append(target.relative_to(Path.cwd()).as_posix())
        prompt = self._prompt(text, attachment_paths)
        process = self._process
        if process is None:
            raise CodexAdapterError("Codex app-server is not running")
        request_id = self._next_rpc_id()
        events: list[Mapping[str, object]] = list(self._startup_events)
        self._startup_events.clear()
        try:
            self._write_rpc(
                "turn/start",
                {
                    "threadId": self._thread_id,
                    "input": [{"type": "text", "text": prompt}],
                    "cwd": str(Path.cwd()),
                    "model": self.model,
                    "approvalPolicy": "never",
                    "effort": self.effort,
                    "sandboxPolicy": {
                        "type": "workspaceWrite",
                        # The second root is a disposable staged plugin, not
                        # the source checkout. App-server 0.153 exposes only
                        # writable roots for workspaceWrite turns.
                        "writableRoots": [str(Path.cwd()), str(self.skill_pack_root)],
                    },
                },
                request_id=request_id,
            )
            events = self._collect_turn(request_id, prompt, events)
        except TimeoutError as exc:
            detail = "\n".join(self._stderr_tail)[-2000:]
            event_tail = _event_debug_tail(events)
            self._terminate(process)
            self._process = None
            return self._finish(
                events,
                environment_detail=(
                    f"Codex did not complete the turn within {self.timeout_s:.1f}s"
                    + (f"; stderr={detail}" if detail else "")
                    + (f"; event_tail={event_tail}" if event_tail else "")
                ),
                turn_timed_out=True,
                failure_reason=classify_failure_reason(str(exc) + detail) or CHILD_NO_TERMINAL_RESULT,
            )
        except (CodexAdapterError, OSError, ValueError) as exc:
            detail = "\n".join(self._stderr_tail)[-2000:]
            self._terminate(process)
            self._process = None
            return self._finish(
                events,
                environment_detail=f"Codex app-server turn failed: {exc}" + (f"; stderr={detail}" if detail else ""),
                failure_reason=classify_failure_reason(str(exc) + detail) or CHILD_EXITED_EARLY,
            )
        return self._finish(events)

    def resume_session(self, session_id: str | None = None) -> str:
        if not self.native_continuation:
            raise CodexAdapterError("native Codex continuation is not enabled")
        if not isinstance(session_id, str) or not session_id:
            raise CodexAdapterError("native continuation requires a session id")
        self._thread_id = session_id
        return session_id

    def close(self) -> None:
        if self._process is not None:
            self._terminate(self._process)
            self._process = None
        if self._codex_home_temp is not None:
            self._codex_home_temp.cleanup()
            self._codex_home_temp = None
        self._started = False


def _write_result(value: TurnResult) -> None:
    from dp_scenarios.runner.session import turn_result_to_dict

    sys.stdout.write(json.dumps({"result": turn_result_to_dict(value)}, ensure_ascii=False, sort_keys=True) + "\n")
    sys.stdout.flush()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bridge dp-scenarios to local Codex")
    parser.add_argument("--codex", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--effort", default="medium")
    parser.add_argument("--skill-pack-root", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--fixture-dir", type=Path, required=True)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--desktop-supervisor", type=Path, required=True)
    parser.add_argument("--desktop-python", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--mcp-config", type=Path, required=True)
    parser.add_argument("--strict-mcp-config", action="store_true")
    parser.add_argument("--supervisor-data-dir", type=Path, required=True)
    parser.add_argument("--allowedTools")
    parser.add_argument("--native-continuation", action="store_true")
    parser.add_argument("--resume-session-id")
    parser.add_argument("--append-system-prompt", default=CODEX_SYSTEM_PROMPT)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    adapter = CodexAdapter(
        codex=args.codex.expanduser().resolve(),
        model=args.model,
        effort=args.effort,
        skill_pack_root=args.skill_pack_root.expanduser().resolve(),
        repo_root=args.repo_root.expanduser().resolve(),
        fixture_dir=args.fixture_dir.expanduser().resolve(),
        artifact_dir=args.artifact_dir.expanduser().resolve(),
        desktop_supervisor=args.desktop_supervisor.expanduser().resolve(),
        desktop_python=args.desktop_python.expanduser().resolve(),
        timeout_s=args.timeout,
        append_system_prompt=args.append_system_prompt,
        mcp_config=args.mcp_config.expanduser().resolve(),
        strict_mcp_config=args.strict_mcp_config,
        allowed_tools=args.allowedTools,
        supervisor_data_dir=args.supervisor_data_dir.expanduser().resolve(),
        native_continuation=args.native_continuation,
        resume_session_id=args.resume_session_id,
    )

    def terminate_on_signal(signum: int, _frame: Any) -> None:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, terminate_on_signal)
    signal.signal(signal.SIGINT, terminate_on_signal)
    try:
        for line in sys.stdin:
            if not line.strip():
                continue
            try:
                request = json.loads(line)
                if not isinstance(request, Mapping):
                    raise CodexAdapterError("request must be a JSON object")
                _write_result(adapter.send(request))
            except (CodexAdapterError, OSError, ValueError) as exc:
                _write_result(
                    TurnResult(
                        environment_wedged=True,
                        environment_detail=str(exc),
                        failure_reason=first_reason((getattr(exc, "reason", None), classify_failure_reason(str(exc)))),
                        last_mcp_call=adapter.last_mcp_call,
                        session_id=adapter._thread_id,
                    )
                )
    finally:
        adapter.close()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
