"""Enforce the workflow-v2 conversation-review handoff for live eval runs.

The guard is installed as a run-scoped Claude Code hook.  It is intentionally
small and dependency-free: the hook process receives one JSON event on stdin,
updates a state file outside the agent workspace, and returns the documented
PreToolUse/PostToolUse/Stop decision shape.

Only the owning conversation is constrained.  Tool calls belonging to the
single retained-capture reviewer are identified by their parent tool use (and,
when present, a different ``agent_id``), so the reviewer keeps its read-only
inspection tools.
"""

from __future__ import annotations

import json
import os
from pathlib import Path, PurePosixPath
import sys
from typing import Any

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows is not a supported live host.
    fcntl = None  # type: ignore[assignment]


STATE_ENV = "NXD_EVAL_REVIEW_GUARD_STATE"
STATE_VERSION = 1
REVIEW_DEADLINE_MS = 120_000
NORMAL = "normal"
REVIEW_DISPATCH_PENDING = "review_dispatch_pending"
RELAY_PENDING = "relay_pending"
REPORT_IN_FLIGHT = "report_in_flight"

REVIEW_REQUIREMENT = "review"
REPORT_ACTION = "report_requirement"
REVIEW_MARKER_PREFIX = "NXD_REVIEW_DISPATCH "
REVIEW_MARKER_KEYS = frozenset(
    {"closure_path", "request_contract", "return", "review_round_index"}
)
REVIEW_RECORD = "review-record.json"
ATTESTATIONS = "agent-attestations.json"
SANITIZED_REQUEST_LABEL = "Sanitized original request:"
# Runner-owned protocol line: the accepted child must see the same absolute
# wall-clock bound that the transport enforces.
REVIEW_BUDGET_LINE = f"review_time_budget_seconds: {REVIEW_DEADLINE_MS / 1000:.0f}"
REVIEW_SKILL_INSTRUCTION = "Load and follow nxd-review-closure."
REVIEW_ALLOWED_SUBAGENT_TYPES = frozenset({"general-purpose"})
REVIEW_METADATA_STATUSES = frozenset(
    {"async_launched", "queued", "running", "completed", "success", "succeeded"}
)
REVIEW_CONTENT_KEYS = frozenset({"content", "text", "result", "output"})
REVIEW_CHILD_TOOLS = frozenset({"read", "glob", "grep", "skill"})
DESKTOP_ADVANCE = "mcp__nxd-desktop__advance_workflow"
REVIEW_SKILL_NAMES = frozenset(
    {"nxd-review-closure", "nexty-agent-skills:nxd-review-closure"}
)


class GuardError(RuntimeError):
    """Raised for malformed or unavailable guard state."""


def write_initial_state(path: Path, *, workspace_root: Path | None = None) -> None:
    """Create a fresh state file owned by the runner, never by the agent."""

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        raise GuardError("review guard state already exists")
    payload: dict[str, object] = {
        "version": STATE_VERSION,
        "state": NORMAL,
    }
    if workspace_root is not None:
        payload["workspace_root"] = str(workspace_root.resolve())
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    no_follow = getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags | no_follow, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
    except Exception:
        # The descriptor is owned by fdopen after the context is entered.
        raise


def settings_payload(*, python: str | Path, script: str | Path) -> dict[str, object]:
    """Return isolated settings that install the guard for one Claude run."""

    import shlex

    command = f"{shlex.quote(str(python))} {shlex.quote(str(script))}"
    hook = {"type": "command", "command": command, "timeout": 5}
    return {
        "hooks": {
            "PreToolUse": [{"matcher": "*", "hooks": [hook]}],
            "PostToolUse": [{"matcher": "*", "hooks": [hook]}],
            "Stop": [{"matcher": "*", "hooks": [hook]}],
        }
    }


def _state_path() -> Path:
    value = os.environ.get(STATE_ENV)
    if not value:
        raise GuardError("review guard state path is not configured")
    path = Path(value)
    if not path.is_absolute() or path.is_symlink():
        raise GuardError("review guard state path is not a runner-owned file")
    return path


class _LockedState:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.handle: Any = None

    def __enter__(self) -> dict[str, object]:
        if self.path.is_symlink():
            raise GuardError("review guard state is a symlink")
        try:
            self.handle = self.path.open("r+", encoding="utf-8")
        except OSError as exc:
            raise GuardError("review guard state cannot be opened") from exc
        if fcntl is not None:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX)
        try:
            value = json.load(self.handle)
        except (OSError, ValueError) as exc:
            raise GuardError("review guard state is not valid JSON") from exc
        if not isinstance(value, dict) or value.get("version") != STATE_VERSION:
            raise GuardError("review guard state has an unsupported version")
        self.value = value
        return value

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self.handle is None:
            return
        try:
            if exc_type is None:
                self.handle.seek(0)
                json.dump(self.value, self.handle, sort_keys=True, separators=(",", ":"))
                self.handle.write("\n")
                self.handle.truncate()
                self.handle.flush()
                os.fsync(self.handle.fileno())
        finally:
            if fcntl is not None:
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            self.handle.close()

def locked_state(path: Path | None = None) -> _LockedState:
    """Return a locked state context."""

    return _LockedState(path or _state_path())


def _walk(value: object, *, depth: int = 0) -> list[object]:
    """Walk hook payloads, decoding the JSON strings used by MCP results."""

    if depth > 6:
        return []
    result = [value]
    if isinstance(value, dict):
        for child in value.values():
            result.extend(_walk(child, depth=depth + 1))
    elif isinstance(value, list):
        for child in value:
            result.extend(_walk(child, depth=depth + 1))
    elif isinstance(value, str) and len(value) <= 2_000_000:
        stripped = value.strip()
        if stripped.startswith(("{", "[")):
            try:
                result.extend(_walk(json.loads(stripped), depth=depth + 1))
            except (TypeError, ValueError):
                pass
    return result


def _event_tool_name(event: dict[str, object]) -> str:
    value = event.get("tool_name", event.get("name", ""))
    return value.casefold() if isinstance(value, str) else ""


def _event_tool_input(event: dict[str, object]) -> dict[str, object]:
    value = event.get("tool_input", event.get("input", {}))
    return value if isinstance(value, dict) else {}


def _event_id(event: dict[str, object], *keys: str) -> str | None:
    for key in keys:
        value = event.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _string(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _exact_nonempty_string(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _canonical_closure(value: object) -> str | None:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        return None
    path = PurePosixPath(value)
    if path.is_absolute() or path.name != "closure":
        return None
    if any(part in {"", ".", ".."} for part in path.parts):
        return None
    normalized = path.as_posix()
    return normalized if normalized == value else None


def _marker(prompt: object) -> tuple[str, int] | None:
    if not isinstance(prompt, str):
        return None
    lines = [line for line in prompt.splitlines() if line.startswith("NXD_REVIEW_DISPATCH")]
    if len(lines) != 1 or not lines[0].startswith(REVIEW_MARKER_PREFIX):
        return None
    try:
        payload = json.loads(lines[0][len(REVIEW_MARKER_PREFIX) :])
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict) or set(payload) != REVIEW_MARKER_KEYS:
        return None
    closure = _canonical_closure(payload.get("closure_path"))
    index = _int(payload.get("review_round_index"))
    if closure is None or index is None or index < 0:
        return None
    canonical = REVIEW_MARKER_PREFIX + json.dumps(
        {
            "closure_path": closure,
            "request_contract": "sanitized_original_request",
            "return": "claims_only",
            "review_round_index": index,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return (closure, index) if lines[0] == canonical else None


def _is_child(event: dict[str, object], state: dict[str, object]) -> bool:
    if state.get("state") != REVIEW_DISPATCH_PENDING or not state.get("review_tool_use_id"):
        return False
    parent = _event_id(event, "parent_tool_use_id", "parentToolUseId")
    owner_tool = state.get("review_tool_use_id")
    if isinstance(parent, str) and parent and parent == owner_tool:
        return True
    # Claude supplies an agent_id for hook events on versions that do not put
    # parent_tool_use_id on every child event.  A different id is a child only
    # after the owner dispatch has been recorded.
    current_agent = _event_id(event, "agent_id", "agentId")
    owner_agent = state.get("owner_agent_id")
    if isinstance(current_agent, str):
        # The main conversation has no agent_id on Claude hook events; a
        # child does. If a future Claude version supplies both, require them
        # to differ so an owner event cannot be mistaken for child activity.
        return not isinstance(owner_agent, str) or current_agent != owner_agent
    current_session = _event_id(event, "session_id", "sessionId")
    owner_session = state.get("owner_session_id")
    if isinstance(current_session, str) and isinstance(owner_session, str):
        return current_session != owner_session
    # Do not infer child provenance from timing alone: an owner can issue a
    # parallel tool call while Agent is in flight. Pending identity-less
    # events therefore remain owner-scoped and fail closed.
    return False


def _result_value(event: dict[str, object]) -> object:
    # Claude Code calls this field ``tool_response`` in hook JSON.  The
    # ``tool_result`` spelling is retained for fixtures and older adapters.
    for key in ("tool_response", "tool_result", "result", "output"):
        if key in event:
            return event[key]
    return None


def _result_is_error(event: dict[str, object]) -> bool:
    value = _result_value(event)
    return any(isinstance(item, dict) and item.get("is_error") is True for item in _walk(value))


def _claim_text(value: object) -> list[str]:
    """Extract result text without treating async metadata as claims."""

    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        text: list[str] = []
        for item in value:
            text.extend(_claim_text(item))
        return text
    if isinstance(value, dict):
        # Agent launches can return a non-empty status/agent-id object before
        # any child result exists. Only content-bearing fields count as the
        # reviewer's returned claims.
        status = value.get("status")
        has_content = any(
            any(item.strip() for item in _claim_text(value[key]))
            for key in REVIEW_CONTENT_KEYS
            if key in value
        )
        if (
            isinstance(status, str)
            and status.casefold() in REVIEW_METADATA_STATUSES
            and not has_content
        ) or ("agent_id" in value and not has_content):
            return []
        text: list[str] = []
        for key in ("content", "text", "message", "result", "output"):
            if key in value:
                text.extend(_claim_text(value[key]))
        return text
    return []


def _nonempty_result(event: dict[str, object]) -> bool:
    value = _result_value(event)
    if value is None or _result_is_error(event):
        return False
    return any(
        item.strip() and "async agent launched" not in item.casefold()
        for item in _claim_text(value)
    )


def _capture_requirement(event: dict[str, object]) -> dict[str, object] | None:
    """Extract only the supervisor-owned review binding from capture output."""

    if _result_is_error(event):
        return None
    tool_input = _event_tool_input(event)
    workflow = _string(tool_input.get("workflow"))
    for item in _walk(_result_value(event)):
        if not isinstance(item, dict):
            continue
        actions = item.get("next_actions")
        if not isinstance(actions, list):
            continue
        for action in actions:
            if not isinstance(action, dict):
                continue
            if action.get("action") != REPORT_ACTION or action.get("requirement_id") != REVIEW_REQUIREMENT:
                continue
            record: dict[str, object] = {
                "workflow": workflow or _string(item.get("workflow")),
                "revision": _int(item.get("revision")),
                "generation": _int(action.get("generation")),
                "subject_sha256": _string(action.get("subject_sha256")),
                "dependency_evidence_sha256": _string(action.get("dependency_evidence_sha256")),
                "owner_agent_id": _event_id(event, "agent_id", "agentId"),
                "owner_session_id": _event_id(event, "session_id", "sessionId"),
            }
            requirements = item.get("requirements")
            if isinstance(requirements, dict):
                review = requirements.get(REVIEW_REQUIREMENT)
            elif isinstance(requirements, list):
                review = next(
                    (
                        requirement
                        for requirement in requirements
                        if isinstance(requirement, dict)
                        and requirement.get("id") == REVIEW_REQUIREMENT
                    ),
                    None,
                )
            else:
                review = None
            review_input = review.get("review_input") if isinstance(review, dict) else None
            review_status = review.get("status") if isinstance(review, dict) else None
            retained_capture_root = (
                review_input.get("retained_capture_root")
                if isinstance(review_input, dict)
                else None
            )
            retained_blueprint_path = (
                review_input.get("retained_blueprint_path")
                if isinstance(review_input, dict)
                else None
            )
            retained_capture_root = _exact_nonempty_string(retained_capture_root)
            retained_blueprint_path = _exact_nonempty_string(retained_blueprint_path)
            if (
                str(review_status or "").casefold() != "pending"
                or retained_capture_root is None
                or retained_blueprint_path is None
            ):
                record["review_input_error"] = "missing_or_malformed"
            else:
                record["retained_capture_root"] = retained_capture_root
                record["retained_blueprint_path"] = retained_blueprint_path
            return record
    return None


def _report_parameters(tool_input: dict[str, object]) -> tuple[dict[str, object], dict[str, object]] | None:
    action = tool_input.get("action")
    if not isinstance(action, dict) or action.get("type") != REPORT_ACTION:
        return None
    parameters = action.get("parameters")
    if not isinstance(parameters, dict):
        return None
    return action, parameters


def _report_matches(tool_input: dict[str, object], state: dict[str, object], event: dict[str, object]) -> bool:
    parsed = _report_parameters(tool_input)
    if parsed is None or _result_is_error(event):
        return False
    _, parameters = parsed
    if parameters.get("requirement_id") != REVIEW_REQUIREMENT:
        return False
    if tool_input.get("workflow") != state.get("workflow"):
        return False
    if tool_input.get("expected_revision") != state.get("revision"):
        return False
    for field in ("generation", "subject_sha256", "dependency_evidence_sha256"):
        if parameters.get(field) != state.get(field):
            return False
    if not _string(parameters.get("session_ref")) or not isinstance(parameters.get("report"), dict):
        return False
    expected_workflow = state.get("workflow")
    expected_generation = state.get("generation")
    expected_subject = state.get("subject_sha256")
    for item in _walk(_result_value(event)):
        if not isinstance(item, dict):
            continue
        operation = item.get("operation")
        events = item.get("events")
        if not isinstance(operation, dict) or not isinstance(events, list):
            continue
        binding = operation.get("binding")
        if not isinstance(binding, dict):
            continue
        if (
            operation.get("workflow") != expected_workflow
            or binding.get("requirement_id") != REVIEW_REQUIREMENT
            or binding.get("generation") != expected_generation
            or binding.get("subject_sha256") != expected_subject
            or binding.get("dependency_evidence_sha256") != state.get("dependency_evidence_sha256")
        ):
            continue
        operation_id = operation.get("operation_id")
        if not isinstance(operation_id, str) or not operation_id:
            continue
        codes = {
            event_item.get("code")
            for event_item in events
            if isinstance(event_item, dict) and event_item.get("operation_id") == operation_id
        }
        if "workflow/review_satisfied" in codes:
            return operation.get("status") == "succeeded"
        if "workflow/review_findings" in codes:
            return operation.get("status") == "failed"
    return False


def _workspace_root(state: dict[str, object]) -> Path:
    value = state.get("workspace_root")
    if not isinstance(value, str) or not Path(value).is_absolute():
        raise GuardError("review guard workspace is not configured")
    return Path(value).resolve()


def _safe_write_path(value: object, state: dict[str, object]) -> bool:
    if not isinstance(value, str) or not value:
        return False
    root = _workspace_root(state)
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        resolved = candidate.resolve(strict=False)
    except OSError:
        return False
    if root not in resolved.parents and resolved != root:
        return False
    if resolved.name == ATTESTATIONS and resolved.parent != root:
        return False
    if resolved.name != REVIEW_RECORD and resolved.name != ATTESTATIONS:
        return False
    if "closure" in resolved.parts:
        return False
    try:
        probe = Path(candidate.anchor)
        for part in candidate.parts[1:]:
            probe /= part
            if probe.is_symlink():
                return False
    except OSError:
        return False
    return True


def _allow(*, updated_input: dict[str, object] | None = None) -> dict[str, object]:
    if updated_input is None:
        return {}
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "updatedInput": updated_input,
        }
    }


def _deny(reason: str) -> dict[str, object]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        },
        "systemMessage": reason,
    }


def _block_stop(reason: str) -> dict[str, object]:
    return {"decision": "block", "reason": reason}


def _is_review_skill(value: object) -> bool:
    skill = _string(value)
    return skill in REVIEW_SKILL_NAMES


def _review_prompt_has_required_input(prompt: object, state: dict[str, object]) -> bool:
    if not isinstance(prompt, str):
        return False
    retained_capture_root = state.get("retained_capture_root")
    retained_blueprint_path = state.get("retained_blueprint_path")
    if not isinstance(retained_capture_root, str) or not retained_capture_root.strip():
        return False
    if not isinstance(retained_blueprint_path, str) or not retained_blueprint_path.strip():
        return False
    lines = prompt.splitlines()
    # These are protocol lines, not prose labels.  Requiring each exact line
    # once prevents a child from receiving a sibling path or a second,
    # ambiguous binding disguised as a bullet or a differently-cased field.
    if lines.count(f"retained_capture_root: {retained_capture_root}") != 1:
        return False
    if lines.count(f"retained_blueprint_path: {retained_blueprint_path}") != 1:
        return False
    # The real built-in reviewer is selected by this explicit instruction,
    # not by inventing a custom subagent type. Keep it canonical so replayed
    # observations and live hook enforcement agree about what was dispatched.
    if lines.count(REVIEW_SKILL_INSTRUCTION) != 1:
        return False
    if lines.count(REVIEW_BUDGET_LINE) != 1:
        return False
    # The request is caller-authored and must never be reconstructed by the
    # hook.  Require exactly one exact label and only check that its value is
    # nonblank; sanitization itself remains the dispatcher's responsibility.
    if prompt.count(SANITIZED_REQUEST_LABEL) != 1:
        return False
    request_lines = [line for line in lines if line.startswith(SANITIZED_REQUEST_LABEL)]
    return len(request_lines) == 1 and bool(
        request_lines[0][len(SANITIZED_REQUEST_LABEL) :].strip()
    )


def _child_pre(event: dict[str, object]) -> dict[str, object]:
    """Keep the retained-input reviewer read-only and single-level."""

    tool = _event_tool_name(event)
    if tool in {"read", "glob", "grep"}:
        return _allow()
    if tool == "skill":
        tool_input = _event_tool_input(event)
        skill = _string(tool_input.get("skill", tool_input.get("name")))
        if _is_review_skill(skill):
            return _allow()
        return _deny("The retained-capture reviewer may load only nxd-review-closure.")
    if tool in {"agent", "task"}:
        return _deny("The retained-capture reviewer must inspect the capture itself; do not dispatch another conversation child.")
    return _deny("The retained-capture reviewer is read-only and may not use workflow, file-write, or other tools.")


def _owner_pre(event: dict[str, object], state: dict[str, object]) -> dict[str, object]:
    tool = _event_tool_name(event)
    if _is_child(event, state):
        return _child_pre(event)
    if state["state"] == REVIEW_DISPATCH_PENDING:
        if tool not in {"agent", "task"}:
            return _deny(
                "A captured review is pending: dispatch exactly one general-purpose reviewer with the canonical NXD_REVIEW_DISPATCH marker."
            )
        if state.get("review_tool_use_id"):
            return _deny("The captured review already has a dispatcher; use its returned claims and relay the report.")
        if state.get("review_input_error"):
            return _deny("Reviewer dispatch rejected: supervisor review_input is missing or malformed.")
        tool_input = _event_tool_input(event)
        subagent_type = _string(tool_input.get("subagent_type"))
        if subagent_type not in REVIEW_ALLOWED_SUBAGENT_TYPES:
            return _deny("The retained-capture reviewer must be a single general-purpose conversation child.")
        marker = _marker(tool_input.get("prompt"))
        if marker is None:
            return _deny(
                "Reviewer dispatch rejected: use one canonical relative closure marker (for example closure), sanitized_original_request, and claims_only."
            )
        if tool_input.get("run_in_background") is True:
            return _deny("The retained-capture reviewer must run inline in this turn.")
        if not _review_prompt_has_required_input(tool_input.get("prompt"), state):
            return _deny(
                "Reviewer dispatch rejected: include the exact supervisor-retained paths and a non-empty 'Sanitized original request:' line."
            )
        state["review_tool_use_id"] = _event_id(event, "tool_use_id", "toolUseId")
        state["review_round_index"] = marker[1]
        # The adapter disables background tasks for the whole Claude process.
        # Do not mutate the Agent input here: recent Claude Code versions omit
        # ``run_in_background`` from the in-process schema entirely when that
        # mode is disabled, and an injected field can turn an otherwise valid
        # synchronous child into an empty tool result.
        return _allow()
    if state["state"] == RELAY_PENDING:
        if tool in {"write", "edit"}:
            path = _event_tool_input(event).get("file_path", _event_tool_input(event).get("path"))
            return _allow() if _safe_write_path(path, state) else _deny(
                "Review relay permits only review-record.json or agent-attestations.json inside the agent workspace."
            )
        if tool == DESKTOP_ADVANCE.casefold():
            tool_input = _event_tool_input(event)
            if not _report_parameters(tool_input):
                return _deny("Review relay permits only the captured report_requirement workflow action.")
            if not _report_matches(tool_input, state, {"tool_result": {}}):
                # The response is checked in PostToolUse. PreToolUse still
                # validates all caller-controlled binding fields.
                parsed = _report_parameters(tool_input)
                assert parsed is not None
                _, parameters = parsed
                if (
                    tool_input.get("workflow") != state.get("workflow")
                    or tool_input.get("expected_revision") != state.get("revision")
                    or parameters.get("requirement_id") != REVIEW_REQUIREMENT
                    or any(parameters.get(field) != state.get(field) for field in ("generation", "subject_sha256", "dependency_evidence_sha256"))
                    or not _string(parameters.get("session_ref"))
                    or not isinstance(parameters.get("report"), dict)
                ):
                    return _deny("Review report binding does not match the supervisor-captured requirement.")
            state["state"] = REPORT_IN_FLIGHT
            state["report_tool_use_id"] = _event_id(event, "tool_use_id", "toolUseId")
            return _allow()
        return _deny("After the reviewer returns, relay its bounded report; do not inspect, review, reset, or launch another tool.")
    if state["state"] == REPORT_IN_FLIGHT:
        return _deny("The review report is in flight; wait for the supervisor response before taking another action.")
    return _allow()


def _handle(event: dict[str, object], state: dict[str, object]) -> dict[str, object]:
    event_name = _string(event.get("hook_event_name", event.get("event", "")))
    event_name = (event_name or "").casefold()
    tool = _event_tool_name(event)
    child = _is_child(event, state)

    if event_name == "posttooluse":
        # The parent Agent/Task result can carry the child agent_id on some
        # Claude versions.  Match its tool-use id before applying the child
        # exemption, otherwise the owner would remain stuck in dispatching.
        if (
            state.get("state") == REVIEW_DISPATCH_PENDING
            and tool in {"agent", "task"}
            and _event_id(event, "tool_use_id", "toolUseId") == state.get("review_tool_use_id")
        ):
            if _nonempty_result(event):
                state["state"] = RELAY_PENDING
            return _allow()
        if child:
            return _allow()
        if (
            state.get("state") == REPORT_IN_FLIGHT
            and tool == DESKTOP_ADVANCE.casefold()
            and _event_id(event, "tool_use_id", "toolUseId") == state.get("report_tool_use_id")
        ):
            if _report_matches(_event_tool_input(event), state, event):
                state["state"] = NORMAL
                # Preserve the completed dispatcher identity just long
                # enough for the runner to observe a valid terminal state.
                # A fresh capture clears it before accepting another review.
                state["completed_review_tool_use_id"] = state.get("review_tool_use_id")
                for key in ("review_tool_use_id", "report_tool_use_id", "review_round_index"):
                    state.pop(key, None)
            else:
                state["state"] = RELAY_PENDING
            return _allow()
        if tool == DESKTOP_ADVANCE.casefold():
            tool_input = _event_tool_input(event)
            action = tool_input.get("action")
            if isinstance(action, dict) and action.get("type") == "capture":
                capture = _capture_requirement(event)
                if capture is not None:
                    state.pop("review_input_error", None)
                    state.pop("completed_review_tool_use_id", None)
                    state.update(capture)
                    state["state"] = REVIEW_DISPATCH_PENDING
                return _allow()
        return _allow()

    if event_name == "stop":
        if state.get("state") in {REVIEW_DISPATCH_PENDING, RELAY_PENDING, REPORT_IN_FLIGHT}:
            return _block_stop("The captured workflow review has not been relayed; finish the reviewer handoff before stopping.")
        return _allow()

    if event_name == "pretooluse":
        return _owner_pre(event, state)
    return _allow()


def handle_event(event: dict[str, object], *, state_path: Path | None = None) -> dict[str, object]:
    """Process one hook event and persist the new state."""

    if not isinstance(event, dict):
        raise GuardError("hook event is not an object")
    with locked_state(state_path) as state:
        return _handle(event, state)


def main() -> int:
    event: object = None
    try:
        event = json.load(sys.stdin)
        if not isinstance(event, dict):
            raise GuardError("hook event is not an object")
        decision = handle_event(event)
    except Exception:
        # A hook process failure must never silently permit a pending relay.
        # Keep the diagnostic generic: event payloads can contain user data.
        if isinstance(event, dict) and _string(event.get("hook_event_name")) == "Stop":
            decision = _block_stop("workflow review guard failed closed; finish cannot continue")
        else:
            decision = _deny("workflow review guard failed closed; finish cannot continue")
    sys.stdout.write(json.dumps(decision, separators=(",", ":")) + "\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised by Claude hooks.
    raise SystemExit(main())


__all__ = [
    "ATTESTATIONS",
    "DESKTOP_ADVANCE",
    "NORMAL",
    "REVIEW_DEADLINE_MS",
    "REVIEW_BUDGET_LINE",
    "REPORT_IN_FLIGHT",
    "RELAY_PENDING",
    "REVIEW_DISPATCH_PENDING",
    "REVIEW_SKILL_INSTRUCTION",
    "SANITIZED_REQUEST_LABEL",
    "handle_event",
    "settings_payload",
    "write_initial_state",
]
