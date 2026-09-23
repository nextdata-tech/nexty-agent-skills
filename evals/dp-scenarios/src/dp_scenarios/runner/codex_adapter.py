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
import hashlib
import json
import os
from pathlib import Path
import re
import select
import signal
import stat
import subprocess
import sys
import tempfile
import time
import tomllib
from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any

from dp_scenarios.failure_reasons import (
    CHILD_EXITED_EARLY,
    CHILD_NO_TERMINAL_RESULT,
    CODEX_PROVIDER_ERROR,
    CODEX_PROVIDER_RETRY_PENDING,
    CODEX_ROOT_TURN_NO_TERMINAL_RESULT,
    PROVIDER_SESSION_LIMIT,
    classify_failure_reason,
    first_reason,
)
from dp_scenarios.operator.transport import ToolCall, TouchedFile, TurnResult
from dp_scenarios.runner.claude_adapter import (
    _advance_action_type,
    _advance_requirement_id,
    _changed_files,
    _load_desktop_stdio,
    _mcp_name,
    _snapshot_workspace,
    _update_from_state_dir,
    _update_machine_artifacts,
    _write_supervisor_facts,
)
from dp_scenarios.runner.review_guard import (
    REVIEW_DEADLINE_MS,
    validate_review_timeout_seconds,
)


class CodexAdapterError(RuntimeError):
    """The Codex bridge could not satisfy one turn."""

    def __init__(
        self,
        message: str,
        *,
        reason: str | None = None,
        safe_diagnostic: bool = False,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.safe_diagnostic = safe_diagnostic


class CodexAppServerEOF(CodexAdapterError):
    """The app-server process closed stdout before returning another event."""


CODEX_FILE_CHANGE_FAILURE = "codex_file_change_failed"
_CODEX_PROVIDER_FAILURE_REASONS = frozenset(
    {CODEX_PROVIDER_ERROR, CODEX_PROVIDER_RETRY_PENDING, PROVIDER_SESSION_LIMIT}
)
_FILE_CHANGE_FAILURE_STATUSES = frozenset(
    {"failed", "error", "rejected", "cancelled", "canceled"}
)
_CHECKER_SKEW_SCHEMA = "nxd-checker-skew-v1"
_CHECKER_SKEW_MAX_BYTES = 1024 * 1024


def _codex_timeout_failure_reason(
    error: TimeoutError,
    detail: str,
    *,
    root_turn_id: str | None,
) -> str:
    """Classify a Codex timeout without changing provider-neutral fallbacks."""

    if CODEX_PROVIDER_RETRY_PENDING in str(error):
        return CODEX_PROVIDER_RETRY_PENDING
    classified = classify_failure_reason(str(error) + detail)
    if classified is not None:
        return classified
    if "Codex reviewer child did not complete" in str(error):
        return CHILD_NO_TERMINAL_RESULT
    if root_turn_id is not None:
        return CODEX_ROOT_TURN_NO_TERMINAL_RESULT
    return CHILD_NO_TERMINAL_RESULT


CODEX_SYSTEM_PROMPT = """You are the agent under test in a local DP-scenarios run.

Work only in the current workspace. Read scenario-evidence-contract.json,
infra-profile.yaml when present, and the relevant skill files under the
provided skill-pack directory before acting. Use the runner-owned nxd-desktop
MCP server for supervisor operations; do not invent supervisor results from
your own prose. The generated fixture is the supplied source export for a
file-backed scenario and is available at the path in `NXD_EVAL_FIXTURE_DIR`;
read those source files only to wire the closure's file connector or derived
transform, then use the governed workflow/query for user-facing results. A
file-backed scenario is not expected to have an `infra-profile.yaml` before
the closure authors one. For an API-backed scenario, use the supplied
infra-profile and generated connector runtime instead. Keep the authored
closure in closure/ and do not create or edit artifacts/ files. Follow every
conduct rule in the evidence contract.
Do not use Bash, curl, WebFetch, or another direct HTTP/client probe to inspect
an API scenario or its credentials; API source observations must come from the
generated connector runtime and the supervisor MCP workflow. For a
file-backed scenario, read only the exact supplied CSV/file inputs under
`NXD_EVAL_FIXTURE_DIR`; never read oracle/gold files or use a raw fixture row
as a substitute for the governed query. Bash is for local closure authoring,
reading the exact fixture path, or reading the supplied skill files only, and
must never print credential values or environment-file contents. If a shell command is
rejected, do not retry the same command shape; return to the declared MCP and
skill flow or report the blocker.
Complete closure authoring in this parent turn. Use the native file-change tool
for text changes and keep Bash to simple workspace-relative inspection or
setup commands; do not invoke or simulate a shell `apply_patch` command. For a
new text file, submit one complete Add File operation with every content line
encoded as an added line; for an existing file, use a valid Update File
operation with an `@@` hunk and explicit context/add/remove prefixes. Never
submit a bare dependency, YAML, or JSON line as a patch header. If the native
file-change tool rejects an edit, treat that as an edit-syntax failure: correct
the patch envelope and retry once with a complete valid file-change operation.
Do not make the guidance scenario-specific.
Do not resend the same malformed payload, and do not report an environment
blocker unless the corrected operation is also rejected; do not use destructive
commands such as `rm`/`rm -f`, shell
command chains, pipelines, redirects, or a custom working directory. If a
command cannot start or is rejected, stop issuing that command shape and switch
to the file tool or report the blocker; do not spend the turn retrying it.
Collaboration is bounded per retained capture in this harness. Do not use `spawnAgent` for closure authoring,
source exploration, shell helpers, validation debugging, or any other work before capture. After a successful
capture returns its matching `report_requirement` review action, use exactly
one provider-native collaboration child for that retained-capture review;
wait for that child before reporting. Do not launch background
helpers or a second child while the same captured review binding is current.
If a required repair or reset produces a new successful capture and a new
`review_input` binding, that new capture authorizes exactly one fresh reviewer;
the per-capture limit resets, but the parent must still repair the closure
itself and recapture rather than using another child for the old capture.
Respond directly to each operator turn and continue the workflow until the
operator's next message arrives.

Reviewer-child role: when a parent labels your prompt
`CODEX_REVIEW_CHILD`, you are the read-only review child, not the workflow
runner. Do not call nxd-desktop, do not spawn/resume/wait for another child,
do not call Bash, do not create or edit files, and do not call
codex_file_change, apply_patch, or any other write-capable tool, even if a
loaded skill or the parent prompt mentions file authoring. Use only the
runner-owned `mcp__nxd-desktop__read_review_input` tool for the exact retained
capture root and blueprint path named by the matching supervisor `review_input`.
It is a bounded read/list surface; it rejects other paths, writes, execution,
network access, sensitive files, and credential values. The runner starts the
review turn in an enforced read-only sandbox with network access disabled; do
not try to change that boundary. Do not follow the parent-run admission or
publication sequence. Inspect only the closure and review inputs named by the
parent, complete within the retained review deadline, and return concise review
claims/findings to the parent. If the named paths or reader tool are genuinely
unavailable, return an incomplete blocker immediately instead of waiting or
inventing evidence.

If the inspection is incomplete at the review cutoff, stop reading and return
the partial evidenced claims plus a concise blocker immediately; never wait
for more context or leave the child running past the deadline.

Review-repair discipline: after a non-clear review report, wait for the next
operator message and then repair the parent-owned closure itself before any
reset or recapture. Address every blocking finding that the operator
authorized, and verify that the relevant files actually changed. Never submit
an unchanged closure for another review; if no authorized repair is possible,
report that blocker instead of repeating reset/capture.

Collaboration tool argument discipline: for `spawnAgent`, send the complete
review request in exactly one `message` string; do not also send `items`.
Never send both `message` and `items` in one collaboration call. For the
owning parent’s one-shot reviewer lifecycle, use only `spawnAgent` and `wait`;
never use `sendInput`, `resumeAgent`, or `closeAgent`. The reviewer child
may use only its allowed read-only inspection tools, but may not call another
collaboration or supervisor tool. If a collaboration call is rejected, do
not repeat the rejected argument shape; report an incomplete handoff. If
`spawnAgent` returns no receiver thread id or leaves the child in
`pendingInit`, do not call `wait` with an empty id set; report an incomplete
handoff immediately.

File-edit discipline: use the file-change tool for edits. If an apply-patch
operation is used, every patch must have the exact `*** Begin Patch`, file
operation, hunk, and `*** End Patch` structure; never combine JSON, prose, or
another patch format inside it. If the patch is rejected, do not retry the
same malformed patch: correct its envelope and use the file-change tool once
more. Report a blocker only if the corrected operation is rejected too. In an
update hunk, start with an `@@` header and prefix every changed line with `+`
or `-` and every context line with a space; never paste raw YAML/JSON lines
into a patch hunk. Prefer one file per change call and validate the exact
patch envelope before submitting it.

Workflow-v2 control: treat every supervisor response as authoritative. After
each response, use only its current revision, invalidation_epoch, and
next_actions. Once a successful capture returns a report_requirement action
with review_input, do not call prepare_workflow, get_workflow_capabilities, or
inspect_workflow as recovery. Dispatch exactly one provider-native,
read-only reviewer using that matching review_input. In this backend, that
means the built-in Codex collaboration child via spawnAgent, followed by
waiting for the child to complete; do not substitute an inline self-review,
an authored review-record.json/agent-attestations.json, or an OS process. The
matching review_input is in the same supervisor response under
`requirements` for the `id` `review`, even when `next_actions` names only the
`report_requirement` action; extract those exact fields from that response and
dispatch the child immediately. Do not call `list_mcp_resources` or any other
resource-discovery tool to locate retained inputs. The owning parent must not
call `mcp__nxd-desktop__read_review_input`; that runner-owned reader is exposed
only for the `CODEX_REVIEW_CHILD` handoff. The
required sequence is: call spawnAgent with the exact review_input and a
read-only review request whose prompt begins with `CODEX_REVIEW_CHILD`, wait
for that child immediately using the returned receiver thread id. The native
collaboration argument shapes are strict: call `wait` as
`{"targets":["<exact non-empty receiver thread id>"]}` (use the `targets`
array key, never `target` or `ids`, and never an empty array). Do not make
another Bash/MCP call or produce a final answer before that wait completes.
If `wait` reports the child as completed but returns no non-empty message, do
not treat that as terminal claims: issue `wait` once more with the same `targets` array.
If the repeated wait is still empty, leave the review incomplete and report
the missing child claims rather than closing the child or fabricating a result.
Do not call `sendInput`, `resumeAgent`, or `closeAgent` for this one-shot
reviewer: its spawn prompt is final, and `wait` is the only follow-up
operation. After the wait returns terminal claims, pass the child's returned
claims and the exact review_input fields to
report_requirement. Copy every field from the current review_input as a
sibling of `report` in the action parameters: `requirement_id`, `generation`,
`subject_sha256`, `dependency_evidence_sha256`, `session_ref`, and
`message_ref` (use the exact current value, including `null`; never omit
`session_ref`). The `parameters.report` value must be the JSON object
`{"schema":"nxd-conversation-review-v1","verdict":"clear","findings":[],"rejection_code":null}`
or the corresponding exact findings/rejection object, never a JSON-encoded
string or Markdown. Its `findings` entries have exactly the keys `id`,
`severity`, and `description`; use lower-case `blocking` or `advisory` for
severity and do not forward reviewer-only fields such as `claim`, `evidence`,
or `why_it_matters`. Use `rejection_code: null` for a clear or findings
report; use the documented rejection code only for a rejected or indeterminate
report. Before the first report, finish any required review-record update for
the current captured inputs. If the supervisor rejects a report for malformed
parameters or deserialization, retry with the exact same current binding
fields and captured revision; change only the in-memory report projection.
Do not edit the closure, blueprint, or review record, and do not make another
supervisor call between those report retries. If the supervisor reports a
stale subject or dependency, stop and relay that authoritative result rather
than attempting to repair it locally. If the child cannot be started or
completed, report an incomplete result; never fabricate the review outcome yourself.
After a clear
report, call the returned self-check/validation action and inspect its result
before following the returned admission, start_run, and query actions. Only use
inspect_prepare_recovery when the immediately preceding
pre-admission prepare_workflow response returned a prepare_recovery_id.
After capture, never edit the retained closure or blueprint before reporting
the child review; the captured inputs are immutable. If the supervisor returns
a report verdict of `findings`, `rejected`, or `indeterminate`, relay it to the
operator and stop for adjudication. When a finding changes behavior or requires
operator authority, end that turn with a direct question asking for the
specific authorization; do not merely report that you are blocked and wait
silently. Do not reset, edit, recapture, validate, admit, or start a run for a
non-clear report; only a clear report authorizes the returned next actions.
After a non-clear or indeterminate `report_requirement` result, end the
current turn immediately and wait for the next operator message; do not reset
or make another supervisor call in that same turn.
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


def _walk_json_values(value: object) -> list[object]:
    """Flatten nested MCP values, decoding embedded JSON text once."""

    values = [value]
    if isinstance(value, Mapping):
        for child in value.values():
            values.extend(_walk_json_values(child))
    elif isinstance(value, list):
        for child in value:
            values.extend(_walk_json_values(child))
    elif isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith(("{", "[")):
            with contextlib.suppress(json.JSONDecodeError):
                decoded = json.loads(stripped)
                if decoded != value:
                    values.extend(_walk_json_values(decoded))
    return values


def _response_requires_review(value: object) -> bool:
    """Return whether a supervisor response leaves the review requirement pending."""

    for item in _walk_json_values(value):
        if not isinstance(item, Mapping):
            continue
        if item.get("code") == "workflow/review_pending":
            return True
        if (
            item.get("type", item.get("action")) == "report_requirement"
            and item.get("requirement_id") == "review"
        ):
            return True
        requirements = item.get("requirements")
        if isinstance(requirements, Mapping):
            review = requirements.get("review")
            if isinstance(review, Mapping) and review.get("status") == "pending":
                return True
        elif isinstance(requirements, list) and any(
            isinstance(review, Mapping)
            and review.get("id") == "review"
            and review.get("status") == "pending"
            for review in requirements
        ):
            return True
    return False


def _review_pending_after_observations(
    observations: Sequence[Mapping[str, object]], previous: bool
) -> bool:
    """Track the supervisor review state across operator turns."""

    pending = previous
    for observation in observations:
        if observation.get("tool") != "mcp__nxd-desktop__advance_workflow":
            continue
        arguments = observation.get("arguments")
        action = _advance_action_type(arguments)
        if observation.get("is_error") is True:
            continue
        result = observation.get("result")
        if action == "capture" and _response_requires_review(result):
            pending = True
        elif action == "report_requirement" and _advance_requirement_id(arguments) == "review":
            pending = False
    return pending


def _turn_sandbox_policy(
    review_pending: bool, writable_roots: Sequence[str]
) -> dict[str, object]:
    """Select the enforced policy for the next parent/reviewer turn."""

    if review_pending:
        return {"type": "readOnly"}
    return {"type": "workspaceWrite", "writableRoots": list(writable_roots)}


def _read_regular_file_beneath(root: Path, parts: Sequence[str]) -> bytes | None:
    """Read one regular file through no-follow descriptors, with a hard cap."""

    nofollow = getattr(os, "O_NOFOLLOW", None)
    directory_flag = getattr(os, "O_DIRECTORY", None)
    if nofollow is None or directory_flag is None or not parts:
        return None
    if any(
        not isinstance(part, str)
        or not part
        or part in {".", ".."}
        or "/" in part
        or "\x00" in part
        for part in parts
    ):
        return None

    directory_fd: int | None = None
    file_fd: int | None = None
    try:
        if not root.is_absolute():
            return None
        directory_flags = os.O_RDONLY | directory_flag | nofollow
        # The supplied root is trusted and already canonicalized by the caller.
        # Keep its final component under O_NOFOLLOW too; resolving it here would
        # silently accept a symlinked captures directory.
        directory_fd = os.open(root, directory_flags)
        for part in parts[:-1]:
            next_fd = os.open(part, directory_flags, dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = next_fd
        file_fd = os.open(
            parts[-1],
            os.O_RDONLY
            | nofollow
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NONBLOCK", 0),
            dir_fd=directory_fd,
        )
        if not stat.S_ISREG(os.fstat(file_fd).st_mode):
            return None
        remaining = _CHECKER_SKEW_MAX_BYTES + 1
        chunks: list[bytes] = []
        while remaining:
            chunk = os.read(file_fd, min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        return data if len(data) <= _CHECKER_SKEW_MAX_BYTES else None
    except (OSError, RuntimeError, ValueError):
        return None
    finally:
        if file_fd is not None:
            os.close(file_fd)
        if directory_fd is not None:
            os.close(directory_fd)


def _checker_skew_marker(
    observation: Mapping[str, object],
    *,
    skill_pack_root: Path,
    supervisor_data_dir: Path | None,
) -> dict[str, object] | None:
    """Hash trusted and retained checkers for one successful capture response."""

    if (
        observation.get("tool") != "advance_workflow"
        or observation.get("is_error") is not False
        or not observation.get("answered")
        or _advance_action_type(observation.get("arguments")) != "capture"
    ):
        return None
    result = observation.get("result")
    requirements = result.get("requirements") if isinstance(result, Mapping) else None
    if not isinstance(requirements, Sequence) or isinstance(
        requirements, (str, bytes, bytearray)
    ):
        return None
    retained_root: object = None
    present = False
    for requirement in requirements:
        if not isinstance(requirement, Mapping) or requirement.get("id") != "review":
            continue
        review_input = requirement.get("review_input")
        if isinstance(review_input, Mapping) and "retained_capture_root" in review_input:
            retained_root = review_input["retained_capture_root"]
            present = True
            break
    if not present:
        return None

    def marker(
        status: str,
        source_digest: str | None = None,
        retained_digest: str | None = None,
    ) -> dict[str, object]:
        value: dict[str, object] = {
            "kind": "checker_skew",
            "schema": _CHECKER_SKEW_SCHEMA,
            "status": status,
        }
        if source_digest is not None and retained_digest is not None:
            value["source_sha256"] = source_digest
            value["retained_sha256"] = retained_digest
        return value

    if (
        not isinstance(retained_root, str)
        or not retained_root
        or "\x00" in retained_root
    ):
        return marker("malformed")
    capture_path = Path(retained_root)
    if not capture_path.is_absolute() or ".." in capture_path.parts:
        return marker("malformed")
    if supervisor_data_dir is None:
        return marker("unreadable")
    try:
        trusted_data_root = supervisor_data_dir.resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        return marker("unreadable")
    captures_root = trusted_data_root / "captures"
    try:
        # Keep the supervisor-provided spelling and walk every component with
        # O_NOFOLLOW below. Resolving the candidate first would mask symlinks.
        relative_capture = capture_path.relative_to(captures_root)
    except ValueError:
        # On macOS, the supervisor may report the same data directory through
        # /var while the runner has canonicalized it to /private/var. Accept
        # only the supervisor's fixed captures/sha256/<digest> suffix, and
        # prove that its parent resolves to the trusted root. The suffix stays
        # unresolved and is still walked with O_NOFOLLOW below.
        capture_parts = capture_path.parts
        suffix = capture_parts[-3:]
        if (
            len(capture_parts) < 4
            or suffix[:2] != ("captures", "sha256")
            or len(suffix[2]) != 64
            or any(character not in "0123456789abcdef" for character in suffix[2])
        ):
            return marker("malformed")
        try:
            reported_data_root = Path(*capture_parts[:-3]).resolve(strict=True)
        except (OSError, RuntimeError, ValueError):
            return marker("unreadable")
        if reported_data_root != trusted_data_root:
            return marker("malformed")
        relative_capture = Path(*suffix[1:])
    if not relative_capture.parts:
        return marker("malformed")

    source_root = skill_pack_root
    source_parts = ("src", "nxd-run-job-loop", "scripts", "self_check.py")
    retained_parts = (*relative_capture.parts, "self_check.py")
    source_bytes = _read_regular_file_beneath(source_root, source_parts)
    retained_bytes = _read_regular_file_beneath(captures_root, retained_parts)
    if source_bytes is None or retained_bytes is None:
        return marker("unreadable")
    source_digest = hashlib.sha256(source_bytes).hexdigest()
    retained_digest = hashlib.sha256(retained_bytes).hexdigest()
    return marker(
        "match" if source_digest == retained_digest else "mismatch",
        source_digest,
        retained_digest,
    )


def _attach_checker_skew_markers(
    tool_calls: Sequence[ToolCall],
    observations: Sequence[Mapping[str, object]],
    *,
    skill_pack_root: Path,
    supervisor_data_dir: Path | None,
) -> tuple[ToolCall, ...]:
    """Attach automatic checker observations to successful capture calls."""

    captures = iter(
        observation
        for observation in observations
        if observation.get("tool") == "advance_workflow"
        and _advance_action_type(observation.get("arguments")) == "capture"
    )
    result: list[ToolCall] = []
    for call in tool_calls:
        if (
            _mcp_name(call.name) == "advance_workflow"
            and _advance_action_type(call.arguments) == "capture"
        ):
            observation = next(captures, None)
            if observation is not None:
                marker = _checker_skew_marker(
                    observation,
                    skill_pack_root=skill_pack_root,
                    supervisor_data_dir=supervisor_data_dir,
                )
                if marker is not None:
                    call = replace(call, observation=marker)
        result.append(call)
    return tuple(result)


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


def _provider_usage(value: object) -> tuple[int | None, int | None]:
    """Read bounded provider token counters without retaining raw responses."""

    usage = value.get("usage") if isinstance(value, Mapping) else None
    if not isinstance(usage, Mapping):
        return None, None
    values: list[int | None] = []
    for key in ("input_tokens", "output_tokens"):
        candidate = usage.get(key)
        values.append(
            candidate
            if isinstance(candidate, int) and not isinstance(candidate, bool) and candidate >= 0
            else None
        )
    return values[0], values[1]


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
_COLLAB_FAILURE_STATUSES = {
    "failed",
    "errored",
    "interrupted",
    "shutdown",
    "notFound",
    "timedOut",
    "timed_out",
    "timeout",
    "cancelled",
    "canceled",
}


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


def _collab_debug_label(item: Mapping[str, object]) -> str:
    """Return value-free lifecycle state for interruption diagnostics."""

    parts: list[str] = []
    tool = item.get("tool")
    if isinstance(tool, str) and tool:
        parts.append(f"tool={tool}")
    status = item.get("status")
    if isinstance(status, str) and status:
        parts.append(f"status={status}")
    child_statuses, _ = _collab_states(item)
    if child_statuses:
        parts.append("child_status=" + ",".join(child_statuses))
    parts.append("keys=" + ",".join(sorted(str(key) for key in item)))
    parts.append(f"receiver_count={len(_collab_receiver_ids(item))}")
    return ",".join(parts) if parts else "state=unknown"


def _merge_collab_item(
    base: Mapping[str, object],
    update: Mapping[str, object],
    *,
    receiver_ids: set[str] | None = None,
) -> dict[str, object]:
    """Merge only one spawn's child state from a later wait snapshot."""

    receiver_scoped = receiver_ids is not None
    merged = dict(base)
    # A wait item's status is aggregate across all of its targets. Copying it
    # onto each spawn can turn a still-running child into a failure (or mark a
    # successful child failed because a sibling failed).
    if receiver_ids is None and "status" in update:
        merged["status"] = update["status"]

    if receiver_ids is None:
        receiver_ids = _collab_receiver_ids(base) | _collab_receiver_ids(update)
    base_states = base.get("agentsStates")
    update_states = update.get("agentsStates")
    if isinstance(base_states, Mapping) or isinstance(update_states, Mapping):
        if receiver_ids:
            states = {
                receiver_id: base_states[receiver_id]
                for receiver_id in receiver_ids
                if isinstance(base_states, Mapping) and receiver_id in base_states
            }
            if isinstance(update_states, Mapping):
                states.update(
                    {
                        receiver_id: update_states[receiver_id]
                        for receiver_id in receiver_ids
                        if receiver_id in update_states
                    }
                )
        else:
            # Some spawn completions provide child state before a receiver id
            # is available. Preserve that one spawn's own snapshot until a
            # later singleton wait can bind it safely.
            states = dict(base_states) if isinstance(base_states, Mapping) else {}
            if isinstance(update_states, Mapping):
                states.update(update_states)
        merged["agentsStates"] = states
        if receiver_scoped and states:
            child_statuses = [
                state.get("status")
                for state in states.values()
                if isinstance(state, Mapping) and isinstance(state.get("status"), str)
            ]
            if any(status in _COLLAB_FAILURE_STATUSES for status in child_statuses):
                merged["status"] = "failed"
            elif child_statuses and all(
                status in _COLLAB_SUCCESS_STATUSES for status in child_statuses
            ):
                merged["status"] = "completed"
            elif child_statuses:
                merged["status"] = "inProgress"

    merged.pop("receiverThreadId", None)
    if receiver_ids:
        merged["receiverThreadIds"] = sorted(receiver_ids)
    else:
        merged.pop("receiverThreadIds", None)
    return merged


def _collab_receiver_ids(item: Mapping[str, object]) -> set[str]:
    values = item.get("receiverThreadIds")
    result: set[str] = set()
    if isinstance(values, Sequence) and not isinstance(values, (str, bytes)):
        result.update(value for value in values if isinstance(value, str) and value)
    singular = item.get("receiverThreadId")
    if isinstance(singular, str) and singular:
        result.add(singular)
    return result


def _collab_status_label(item: Mapping[str, object]) -> str:
    """Return only allow-listed child lifecycle labels, never ids or messages."""

    states = item.get("agentsStates", item.get("agents_states"))
    if not isinstance(states, Mapping):
        return "unreported"
    allowed = {
        "pendingInit",
        "running",
        "completed",
        "failed",
        "errored",
        "stopped",
        "cancelled",
        "canceled",
    }
    labels: set[str] = set()
    for state in states.values():
        if not isinstance(state, Mapping):
            labels.add("other")
            continue
        status = state.get("status")
        labels.add(status if isinstance(status, str) and status in allowed else "other")
    return ",".join(sorted(labels)) if labels else "unreported"


def _completed_reviewer_wait_ids(
    event: Mapping[str, object], receiver_ids: set[str]
) -> set[str]:
    """Return only tracked reviewers with their own terminal wait result."""

    if event.get("type") != "item.completed":
        return set()
    item = event.get("item")
    if (
        not isinstance(item, Mapping)
        or item.get("type") not in {"collabAgentToolCall", "collab_agent_tool_call"}
        or item.get("tool") != "wait"
    ):
        return set()
    matched_ids = receiver_ids & _collab_receiver_ids(item)
    states = item.get("agentsStates")
    if not isinstance(states, Mapping):
        return set()
    completed: set[str] = set()
    for receiver_id in matched_ids:
        state = states.get(receiver_id)
        if not isinstance(state, Mapping):
            continue
        status = state.get("status")
        if status in _COLLAB_FAILURE_STATUSES:
            completed.add(receiver_id)
            continue
        message = state.get("message")
        if (
            status in _COLLAB_SUCCESS_STATUSES
            and isinstance(message, str)
            and message.strip()
        ):
            completed.add(receiver_id)
    return completed


def _update_reviewer_deadline(
    event: Mapping[str, object],
    receiver_ids: set[str],
    deadline_at: float | None,
    *,
    now: float,
    review_deadline_ms: float = REVIEW_DEADLINE_MS,
) -> tuple[set[str], float | None]:
    """Arm reviewer time at spawn and clear it after matching terminal claims."""

    if event.get("type") not in {"item.started", "item.completed"}:
        return receiver_ids, deadline_at
    item = event.get("item")
    if not isinstance(item, Mapping) or item.get("type") not in {
        "collabAgentToolCall",
        "collab_agent_tool_call",
    }:
        return receiver_ids, deadline_at
    tool = item.get("tool")
    ids = _collab_receiver_ids(item)
    if tool == "spawnAgent":
        # App-server runs can report the spawn as started or completed before
        # they know the receiver thread id (for example, child_status=pendingInit).
        # Arm the absolute deadline for either lifecycle event, then merge any
        # ids that arrive later without extending the deadline.
        receiver_ids |= ids
        if deadline_at is None:
            deadline_at = now + review_deadline_ms / 1000.0
        return receiver_ids, deadline_at
    completed_ids = _completed_reviewer_wait_ids(event, receiver_ids)
    if completed_ids:
        receiver_ids.difference_update(completed_ids)
        if not receiver_ids:
            deadline_at = None
    # ``closeAgent`` only reports that the collaboration handle was closed;
    # it does not prove that the child returned terminal claims.
    return receiver_ids, deadline_at


def _update_reviewer_deadline_from_events(
    events: Sequence[Mapping[str, object]],
    receiver_ids: set[str],
    deadline_at: float | None,
    *,
    now: float,
    review_deadline_ms: float = REVIEW_DEADLINE_MS,
) -> tuple[set[str], float | None]:
    """Apply reviewer-deadline detection to already-buffered app-server events.

    ``turn/start`` can return notifications alongside its response.  Those
    notifications are handed to ``_collect_turn`` as ``before_turn`` events;
    ignoring them leaves a retained reviewer without its 300-second deadline
    and lets the outer turn timeout wait the full 90% budget instead.
    """

    for event in events:
        normalized = _normalise_app_server_event(event)
        receiver_ids, deadline_at = _update_reviewer_deadline(
            normalized,
            receiver_ids,
            deadline_at,
            now=now,
            review_deadline_ms=review_deadline_ms,
        )
    return receiver_ids, deadline_at


def _codex_timeout_detail(error: TimeoutError, *, parent_turn_limit_s: float) -> str:
    """Report the deadline that actually fired, while preserving the parent limit."""

    message = str(error).strip() or "Codex app-server operation deadline expired"
    return f"{message}; parent_turn_limit={parent_turn_limit_s:.1f}s"


def _codex_turn_progress_detail(
    *,
    turn_started_at: float,
    now: float,
    last_event_at: float,
    last_event_label: str,
    reviewer_spawned_at: float | None,
    reviewer_wait_started_at: float | None,
    reviewer_completed_at: float | None,
    reviewer_result_ready: bool,
    reviewer_deadline_at: float | None,
    reviewer_wait_count: int,
    reviewer_wait_target: str,
    reviewer_child_status: str,
    reviewer_child_started: bool,
) -> str:
    """Summarize timeout timing without including event arguments or results."""

    elapsed = max(0.0, now - turn_started_at)
    idle = max(0.0, now - last_event_at)
    last_event_offset = max(0.0, last_event_at - turn_started_at)
    if reviewer_completed_at is not None:
        phase = "completed"
    elif reviewer_wait_started_at is not None:
        phase = "waiting"
    elif reviewer_spawned_at is not None:
        phase = "spawned"
    else:
        phase = "not_started"
    reviewer = [f"phase={phase}"]
    if reviewer_spawned_at is not None:
        reviewer.append(f"spawn_at=+{max(0.0, reviewer_spawned_at - turn_started_at):.1f}s")
    if reviewer_wait_started_at is not None:
        reviewer.append(
            f"wait_at=+{max(0.0, reviewer_wait_started_at - turn_started_at):.1f}s"
        )
    if reviewer_completed_at is not None:
        reviewer.append(
            f"complete_at=+{max(0.0, reviewer_completed_at - turn_started_at):.1f}s"
        )
        reviewer.append(f"result_ready={str(reviewer_result_ready).lower()}")
    if reviewer_deadline_at is None:
        reviewer.append("deadline=cleared" if reviewer_completed_at is not None else "deadline=not_armed")
    else:
        reviewer.append(
            f"deadline_at=+{max(0.0, reviewer_deadline_at - turn_started_at):.1f}s"
        )
    reviewer.extend(
        (
            f"wait_calls={reviewer_wait_count}",
            f"wait_target={reviewer_wait_target}",
            f"child_status={reviewer_child_status}",
            f"child_started={str(reviewer_child_started).lower()}",
        )
    )
    return (
        f"turn_elapsed={elapsed:.1f}s; idle_for={idle:.1f}s; "
        f"last_event={last_event_label}@+{last_event_offset:.1f}s; "
        "reviewer=" + ",".join(reviewer)
    )


def _validate_persistent_codex_config(
    config_path: Path, *, workspace: Path
) -> None:
    """Allow only Codex's local trust marker in a persisted native home."""

    try:
        payload = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, tomllib.TOMLDecodeError) as exc:
        raise CodexAdapterError(
            "native Codex continuation config is unreadable or invalid"
        ) from exc
    if set(payload) - {"projects"}:
        raise CodexAdapterError(
            "native Codex continuation config contains unexpected settings"
        )
    projects = payload.get("projects", {})
    if not isinstance(projects, Mapping):
        raise CodexAdapterError(
            "native Codex continuation project trust config is malformed"
        )
    allowed_projects = {str(workspace.resolve())}
    for project, settings in projects.items():
        if project not in allowed_projects:
            raise CodexAdapterError(
                "native Codex continuation config contains an unapproved project"
            )
        if not isinstance(settings, Mapping) or dict(settings) != {
            "trust_level": "trusted"
        }:
            raise CodexAdapterError(
                "native Codex continuation project trust config is unexpected"
            )


def _reviewer_wait_without_target(
    event: Mapping[str, object],
    reviewer_started: bool,
) -> bool:
    """Whether a reviewer wait was issued without a child target.

    A one-shot reviewer should be waited on by the receiver thread id returned
    by ``spawnAgent``.  App-server versions have emitted intermediate completed
    wait items before that target or the child terminal state was attached;
    those are diagnosed at the turn boundary instead of being treated as an
    immediate provider failure.  An explicit failed wait remains fatal.
    """

    if event.get("type") != "item.completed":
        return False
    item = event.get("item")
    if not isinstance(item, Mapping) or item.get("type") not in {
        "collabAgentToolCall",
        "collab_agent_tool_call",
    }:
        return False
    if item.get("tool") != "wait" or not reviewer_started:
        return False
    child_statuses, _ = _collab_states(item)
    status = item.get("status")
    return bool(
        not _collab_receiver_ids(item)
        and (
            item.get("is_error") is True
            or bool(item.get("error"))
            or status in _COLLAB_FAILURE_STATUSES
            or any(child in _COLLAB_FAILURE_STATUSES for child in child_statuses)
        )
    )


_CODEX_ERROR_VARIANTS = frozenset(
    {
        "usageLimitExceeded",
        "sessionBudgetExceeded",
        "rateLimitExceeded",
        "serverOverloaded",
        "unauthorized",
        "badRequest",
        "contextWindowExceeded",
        "internalError",
    }
)
_CODEX_LIMIT_VARIANTS = frozenset(
    {"usageLimitExceeded", "sessionBudgetExceeded", "rateLimitExceeded"}
)
_CODEX_PROVIDER_ERROR_GRACE_S = 1.0


def _safe_http_status(value: object) -> int | None:
    if type(value) is int and 100 <= value <= 599:
        return value
    return None


def _codex_error_payload(error: Mapping[str, object]) -> dict[str, object]:
    """Extract only recognized variant/status metadata from a Codex error."""

    info = error.get("codexErrorInfo")
    variant = "unknown"
    status_containers: list[Mapping[str, object]] = []
    if isinstance(info, str) and info in _CODEX_ERROR_VARIANTS:
        variant = info
    elif isinstance(info, Mapping):
        status_containers.append(info)
        for key in ("kind", "type", "code"):
            candidate = info.get(key)
            if isinstance(candidate, str) and candidate in _CODEX_ERROR_VARIANTS:
                variant = candidate
                break
        if variant == "unknown":
            for key, value in info.items():
                if key in _CODEX_ERROR_VARIANTS:
                    variant = key
                    if isinstance(value, Mapping):
                        status_containers.append(value)
                    break
                if isinstance(value, Mapping):
                    status_containers.append(value)
    status_containers.append(error)
    status = next(
        (
            safe_status
            for container in status_containers
            if (safe_status := _safe_http_status(container.get("httpStatusCode")))
            is not None
        ),
        None,
    )
    if variant == "unknown" and status is not None:
        variant = "http_error"
    return {
        "variant": variant,
        "http_status": status,
        "details_present": "additionalDetails" in error,
        "misalignment_present": "misalignment" in error,
    }


def _codex_provider_error(event: Mapping[str, object]) -> dict[str, object] | None:
    """Project an app-server error notification onto safe, allow-listed fields.

    Thread and turn identities are returned only for an in-memory equality
    check in ``_collect_turn``. Provider prose, details and misalignment data
    are never copied into the projection.
    """

    if event.get("method") != "error":
        return None
    params = event.get("params")
    if not isinstance(params, Mapping):
        return None
    error = params.get("error")
    if not isinstance(error, Mapping):
        error = {}
    return {
        "thread_id": params.get("threadId") if isinstance(params.get("threadId"), str) else None,
        "turn_id": params.get("turnId") if isinstance(params.get("turnId"), str) else None,
        "will_retry": params.get("willRetry") if isinstance(params.get("willRetry"), bool) else None,
        **_codex_error_payload(error),
    }


def _codex_provider_error_matches_root(
    error: Mapping[str, object], *, thread_id: str | None, turn_id: str
) -> bool:
    """Require both app-server identities to match before affecting the root."""

    return bool(
        isinstance(thread_id, str)
        and error.get("thread_id") == thread_id
        and error.get("turn_id") == turn_id
    )


def _codex_root_progress_event(
    event: Mapping[str, object], *, thread_id: str | None, turn_id: str
) -> bool:
    """Whether a notification is progress on the active root turn."""

    if event.get("method") not in {
        "turn/started",
        "item/started",
        "item/completed",
        "item/agentMessage/delta",
        "item/reasoning/textDelta",
        "item/reasoning/summaryTextDelta",
        "item/reasoning/summaryPartAdded",
        "item/commandExecution/outputDelta",
        "item/mcpToolCall/progress",
        "thread/tokenUsage/updated",
        "turn/diff/updated",
        "turn/plan/updated",
    }:
        return False
    params = event.get("params")
    if not isinstance(params, Mapping):
        return False
    reported_thread = params.get("threadId")
    if event.get("method") == "turn/started":
        turn = params.get("turn")
        reported_turn = turn.get("id") if isinstance(turn, Mapping) else None
    else:
        reported_turn = params.get("turnId")
    return bool(
        isinstance(thread_id, str)
        and reported_thread == thread_id
        and reported_turn == turn_id
    )


def _codex_event_matches_root_turn(
    event: Mapping[str, object], *, thread_id: str | None, turn_id: str
) -> bool:
    """Reject raw app-server events not scoped to the active root thread/turn."""

    method = event.get("method")
    if method == "error":
        error = _codex_provider_error(event)
        return error is not None and _codex_provider_error_matches_root(
            error, thread_id=thread_id, turn_id=turn_id
        )
    if method == "turn/completed":
        params = event.get("params")
        turn = params.get("turn") if isinstance(params, Mapping) else None
        return bool(
            isinstance(thread_id, str)
            and isinstance(params, Mapping)
            and params.get("threadId") == thread_id
            and isinstance(turn, Mapping)
            and turn.get("id") == turn_id
        )
    if method in {
        "turn/started",
        "item/started",
        "item/completed",
        "item/agentMessage/delta",
        "item/reasoning/textDelta",
        "item/reasoning/summaryTextDelta",
        "item/reasoning/summaryPartAdded",
        "item/commandExecution/outputDelta",
        "item/mcpToolCall/progress",
        "thread/tokenUsage/updated",
        "turn/diff/updated",
        "turn/plan/updated",
    }:
        return _codex_root_progress_event(
            event, thread_id=thread_id, turn_id=turn_id
        )
    # Startup notifications and legacy, already-normalized test events are not
    # root-turn scoped and remain available to their existing handlers.
    return True


def _safe_turn_failure_detail(error: object) -> str | None:
    """Keep only an exact adapter-generated provider diagnostic or a code."""

    if not isinstance(error, str) or not error.strip():
        return None
    safe_variants = "|".join(
        re.escape(value) for value in sorted(_CODEX_ERROR_VARIANTS | {"http_error", "unknown"})
    )
    pattern = (
        r"(?:Codex app-server reported a non-retryable provider error "
        r"|codex_provider_retry_pending )"
        rf"\(variant=(?:{safe_variants}), http_status=(?:unknown|[1-5][0-9]{{2}}), "
        r"details_present=(?:true|false), misalignment_present=(?:true|false)\)"
    )
    if re.fullmatch(pattern, error):
        return error
    reason = classify_failure_reason(error)
    if reason is not None:
        return f"Codex app-server turn failed ({reason})"
    return "Codex app-server turn failed"


def _codex_provider_error_reason(error: Mapping[str, object]) -> str:
    if error.get("variant") in _CODEX_LIMIT_VARIANTS or error.get("http_status") == 429:
        return PROVIDER_SESSION_LIMIT
    return CODEX_PROVIDER_ERROR


def _codex_provider_error_detail(
    error: Mapping[str, object], *, retry_pending: bool = False
) -> str:
    variant = error.get("variant")
    safe_variants = _CODEX_ERROR_VARIANTS | {"http_error", "unknown"}
    safe_variant = (
        variant if isinstance(variant, str) and variant in safe_variants else "unknown"
    )
    status = error.get("http_status")
    status_text = str(status) if _safe_http_status(status) is not None else "unknown"
    prefix = (
        "codex_provider_retry_pending"
        if retry_pending
        else "Codex app-server reported a non-retryable provider error"
    )
    return (
        f"{prefix} (variant={safe_variant}, http_status={status_text}, "
        f"details_present={str(error.get('details_present') is True).lower()}, "
        f"misalignment_present={str(error.get('misalignment_present') is True).lower()})"
    )


def _normalise_app_server_event(event: Mapping[str, object]) -> Mapping[str, object]:
    """Map one app-server notification to the adapter's event vocabulary."""

    method = event.get("method")
    params = event.get("params")
    if not isinstance(method, str) or not isinstance(params, Mapping):
        return event
    if method == "error":
        # Never pass provider messages, details, identifiers or misalignment
        # payloads into transcript/report parsing.
        return {"type": "provider_error"}
    if method == "thread/started":
        thread = params.get("thread")
        thread_id = thread.get("id") if isinstance(thread, Mapping) else None
        return {"type": "thread.started", "thread_id": thread_id}
    if method == "turn/completed":
        turn = params.get("turn")
        turn_id = turn.get("id") if isinstance(turn, Mapping) else None
        status = turn.get("status") if isinstance(turn, Mapping) else None
        usage = turn.get("usage") if isinstance(turn, Mapping) else params.get("usage")
        raw_error = turn.get("error") if isinstance(turn, Mapping) else None
        safe_error = None
        if raw_error is not None:
            safe_payload = (
                raw_error if isinstance(raw_error, Mapping) else {}
            )
            safe_error = _codex_provider_error_detail(
                _codex_error_payload(safe_payload)
            )
        event_type = {
            "completed": "turn.completed",
            "interrupted": "turn.interrupted",
        }.get(status, "turn.failed")
        return {
            "type": event_type,
            "turn_id": turn_id,
            "is_error": status != "completed",
            "error": safe_error,
            "usage": usage,
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
            "error": "MCP server startup failed",
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
            normalized["is_error"] = bool(
                item.get("is_error")
                or item.get("error")
                or item.get("status") in _FILE_CHANGE_FAILURE_STATUSES
            )
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
    reviewer_labels: list[str] = []
    for event in events:
        normalized = _normalise_app_server_event(event)
        if normalized.get("type") not in {"item.started", "item.completed"}:
            continue
        item = normalized.get("item")
        if isinstance(item, Mapping) and item.get("type") in {
            "collabAgentToolCall",
            "collab_agent_tool_call",
        }:
            reviewer_labels.append(_collab_debug_label(item))
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
    if reviewer_labels:
        labels.append("reviewer=" + ";".join(reviewer_labels[-3:]))
    return ", ".join(labels) if labels else None


def parse_codex_events(
    events: Sequence[Mapping[str, object]],
    *,
    redact_json_rpc: Any,
    redact_text: Any,
    session_id: str | None,
    root_turn_id: str | None = None,
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
    input_tokens_total = 0
    output_tokens_total = 0
    token_usage_seen = False
    thread_id = session_id
    build_failures = 0
    environment_details: list[str] = []
    partial_answer: list[str] = []
    seen_collab_receiver_ids: set[str] = set()

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
        if root_turn_id is not None and not _codex_event_matches_root_turn(
            event, thread_id=thread_id, turn_id=root_turn_id
        ):
            continue
        event = _normalise_app_server_event(event)
        event_type = event.get("type")
        if event_type == "thread.started":
            value = event.get("thread_id")
            if isinstance(value, str) and value and not thread_id:
                thread_id = value
            continue
        if event_type == "turn.failed":
            if root_turn_id is not None and event.get("turn_id") != root_turn_id:
                continue
            terminal_count += 1
            terminal_subtype = "failed"
            terminal_is_error = True
            error = event.get("error")
            detail = _safe_turn_failure_detail(error)
            if detail is not None:
                environment_details.append(detail)
            continue
        if event_type == "turn.interrupted":
            if root_turn_id is not None and event.get("turn_id") != root_turn_id:
                continue
            terminal_count += 1
            terminal_subtype = "interrupted"
            terminal_is_error = True
            error = event.get("error")
            if isinstance(error, str) and error.strip():
                environment_details.append(redact_text(error))
            continue
        if event_type == "turn.completed":
            if root_turn_id is not None and event.get("turn_id") != root_turn_id:
                continue
            terminal_count += 1
            # The shared operator contract uses Claude's terminal vocabulary:
            # a normal provider completion is a successful turn. Keeping
            # Codex's wire word (``completed``) here makes an otherwise
            # healthy full run look like ``script_exhausted``.
            terminal_subtype = "success"
            raw_error = event.get("is_error")
            terminal_is_error = raw_error if isinstance(raw_error, bool) else False
            input_tokens, output_tokens = _provider_usage(event)
            if input_tokens is not None:
                input_tokens_total += input_tokens
                token_usage_seen = True
            if output_tokens is not None:
                output_tokens_total += output_tokens
                token_usage_seen = True
            continue
        if event_type == "mcp_server_failed":
            environment_details.append("MCP server startup failed")
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
            is_error = bool(
                item.get("is_error")
                or item.get("error")
                or item.get("status") in _FILE_CHANGE_FAILURE_STATUSES
            )
            result = {
                "status": item.get("status"),
                "is_error": is_error,
            }
            calls.append(
                ToolCall("codex_file_change", redact_json_rpc(dict(item)), result)
            )
            transcript.append(
                "[tool_use:file_change] "
                + redact_text(json.dumps(dict(item), default=str)[:600])
            )
            if is_error:
                # A rejected patch is an agent/tool result, not proof that the
                # app-server or supervisor wedged. Keep the turn alive so the
                # parent can correct the operation; if it never recovers, the
                # normal turn deadline classifies the incomplete turn.
                transcript.append("[tool_result:file_change] " + CODEX_FILE_CHANGE_FAILURE)
            continue
        if item_type == "collab_agent_tool_call":
            tool = item.get("tool")
            key = str(item.get("id") or f"Agent:{len(calls)}")
            if tool == "spawnAgent" and event_type == "item.started":
                seen_collab_receiver_ids.update(_collab_receiver_ids(item))
                pending_collab[key] = item
                continue
            if tool == "spawnAgent" and event_type == "item.completed":
                seen_collab_receiver_ids.update(_collab_receiver_ids(item))
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
                fresh_wait_ids = wait_ids - seen_collab_receiver_ids
                matches: dict[str, set[str]] = {}
                unidentified: list[str] = []
                for pending_key, pending_item in pending_collab.items():
                    pending_ids = _collab_receiver_ids(pending_item)
                    matched_ids = wait_ids & pending_ids
                    if matched_ids:
                        matches[pending_key] = matched_ids
                    elif not pending_ids:
                        unidentified.append(pending_key)
                if len(unidentified) == 1 and len(fresh_wait_ids) == 1:
                    matches[unidentified[0]] = set(fresh_wait_ids)
                    seen_collab_receiver_ids.update(fresh_wait_ids)
                for pending_key, matched_ids in matches.items():
                    started = pending_collab[pending_key]
                    candidate = _merge_collab_item(
                        started, item, receiver_ids=matched_ids
                    )
                    if not _collab_result_ready(candidate):
                        pending_collab[pending_key] = candidate
                        continue
                    pending_collab.pop(pending_key, None)
                    record_collab_call(started, candidate)
                seen_collab_receiver_ids.update(wait_ids)
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
        environment_details.append(
            "Codex reviewer child had no matching completion ("
            + _collab_debug_label(item)
            + ")"
        )

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
        provider_model_calls=terminal_count,
        input_tokens=input_tokens_total if token_usage_seen else None,
        output_tokens=output_tokens_total if token_usage_seen else None,
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
        multi_agent_v2: bool = False,
        review_timeout_seconds: float | None = None,
        native_continuation: bool = False,
        resume_session_id: str | None = None,
        native_state_dir: Path | None = None,
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
        self.multi_agent_v2 = bool(multi_agent_v2)
        self.review_timeout_seconds = validate_review_timeout_seconds(
            REVIEW_DEADLINE_MS / 1000.0
            if review_timeout_seconds is None
            else review_timeout_seconds
        )
        self._review_deadline_ms = self.review_timeout_seconds * 1000.0
        self.native_continuation = bool(native_continuation)
        self.native_state_dir = native_state_dir
        self._thread_id = resume_session_id
        self._active_turn_id: str | None = None
        self._started = False
        self._before: dict[str, bytes] = {}
        self._facts: dict[str, object] = {}
        self._build_context: dict[str, object] = {}
        self._lifecycles: dict[str, str] = {}
        self._built_runs: set[str] = set()
        self._query_history: list[dict[str, object]] = []
        self._last_mcp_call: str | None = None
        self._review_pending = False
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
        if native_continuation and native_state_dir is None:
            raise CodexAdapterError("native Codex continuation requires a private persistent state directory")
        if native_state_dir is not None and not native_continuation:
            raise CodexAdapterError("--native-state-dir requires native continuation mode")

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
        if self.native_continuation:
            assert self.native_state_dir is not None
            codex_home = self._persistent_native_codex_home(
                self.native_state_dir,
                environment,
                resuming=self._thread_id is not None,
            )
            environment["CODEX_HOME"] = str(codex_home)
        else:
            self._codex_home_temp = self._isolated_codex_home(environment)
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

    def _persistent_native_codex_home(
        self,
        state_dir: Path,
        environment: Mapping[str, str],
        *,
        resuming: bool,
    ) -> Path:
        """Open private app-server state that survives adapter process restarts.

        This directory is a sibling of the agent workspace, scoped to one
        persistent scenario/epoch root. The provider may keep transcripts and
        tool results here, so the directory is private and is never bundled
        with report evidence. Only the host-owned auth handle is symlinked.
        """

        workspace = Path.cwd().resolve()
        run_root = workspace.parent
        expected = run_root / "provider-state" / "codex-home"
        selected = state_dir.expanduser().absolute()
        if selected != expected or selected.is_relative_to(workspace):
            raise CodexAdapterError(
                "native Codex state must be the runner-owned private directory beside the agent workspace"
            )
        parent = expected.parent
        if parent.is_symlink():
            raise CodexAdapterError("native Codex state parent must not be a symlink")
        if resuming:
            if not parent.is_dir() or not expected.is_dir() or expected.is_symlink():
                raise CodexAdapterError("native Codex continuation state directory is missing or unsafe")
            if parent.stat().st_mode & 0o077 or expected.stat().st_mode & 0o077:
                raise CodexAdapterError("native Codex continuation state must be owner-only")
            project_config_dir = workspace / ".codex"
            if project_config_dir.exists() or project_config_dir.is_symlink():
                raise CodexAdapterError(
                    "native Codex continuation refuses workspace-local Codex project config"
                )
            config = expected / "config.toml"
            if config.is_symlink() or not config.is_file():
                raise CodexAdapterError("native Codex continuation config is missing or unsafe")
            if config.stat().st_mode & 0o077:
                raise CodexAdapterError("native Codex continuation config must be owner-only")
            _validate_persistent_codex_config(
                config,
                workspace=workspace,
            )
        else:
            if expected.exists() or expected.is_symlink():
                raise CodexAdapterError("native Codex state directory is already occupied")
            if parent.exists() and (not parent.is_dir() or any(parent.iterdir())):
                raise CodexAdapterError("native Codex state parent is occupied or unsafe")
            parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            parent.chmod(0o700)
            expected.mkdir(mode=0o700)
            config = expected / "config.toml"
            config.write_text(
                "# dp-scenarios app-server home; MCP is supplied by the runner.\n",
                encoding="utf-8",
            )
            config.chmod(0o600)

        source_value = environment.get("CODEX_HOME")
        host_auth = (
            Path(source_value).expanduser().absolute() / "auth.json"
            if isinstance(source_value, str) and source_value
            else None
        )
        auth_link = expected / "auth.json"
        if host_auth is not None and host_auth.is_file():
            if resuming:
                if not auth_link.is_symlink() or os.readlink(auth_link) != str(host_auth):
                    raise CodexAdapterError("native Codex auth handle differs from the host-owned link")
            else:
                auth_link.symlink_to(host_auth)
        elif auth_link.is_symlink() or auth_link.exists():
            raise CodexAdapterError("native Codex auth handle is unavailable or unsafe")
        return expected

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
            "sandbox_workspace_write.exclude_slash_tmp=true",
            "-c",
            "sandbox_workspace_write.exclude_tmpdir_env_var=true",
            "-c",
            f"model_reasoning_effort={_toml_string(self.effort)}",
        ]
        if self.multi_agent_v2:
            command[3:3] = ["--enable", "multi_agent_v2"]
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
            "sandbox_workspace_write": {
                "exclude_slash_tmp": True,
                "exclude_tmpdir_env_var": True,
            },
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
            if self._stdout_events:
                return self._stdout_events.popleft()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Codex app-server response deadline expired")
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
                    raise CodexAppServerEOF(
                        "Codex app-server exited before returning an event",
                        reason=CHILD_EXITED_EARLY,
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
            raise CodexAdapterError("Codex app-server initialize request failed")
        self._startup_events.extend(events)
        self._write_rpc("initialized", {})
        request_method = "thread/resume" if self._thread_id is not None else "thread/start"
        request_id = self._next_rpc_id()
        params = self._resume_params() if self._thread_id is not None else self._thread_params()
        self._write_rpc(request_method, params, request_id=request_id)
        response, events = self._read_until_response(request_id, time.monotonic() + self.timeout_s)
        if "error" in response:
            raise CodexAdapterError(f"Codex app-server {request_method} request failed")
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
                raise CodexAdapterError("Codex app-server MCP status request failed")
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
        )
        if "error" in response:
            raise CodexAdapterError("Codex app-server turn/start request failed")
        result = response.get("result")
        turn = result.get("turn") if isinstance(result, Mapping) else None
        turn_id = turn.get("id") if isinstance(turn, Mapping) else None
        if not isinstance(turn_id, str) or not turn_id:
            raise CodexAdapterError("Codex app-server turn/start returned no turn identity")
        self._active_turn_id = turn_id
        self._turn_failure_reason = None
        root_thread_id = getattr(self, "_thread_id", None)

        def is_root_event(event: Mapping[str, object]) -> bool:
            # A successfully initialized production adapter always has a
            # thread id. Keeping synthetic object.__new__ tests usable does
            # not weaken the real app-server path.
            return not isinstance(root_thread_id, str) or _codex_event_matches_root_turn(
                event, thread_id=root_thread_id, turn_id=turn_id
            )

        turn_started_at = time.monotonic()
        deadline = turn_started_at + self.timeout_s
        review_deadline_ms = getattr(self, "_review_deadline_ms", float(REVIEW_DEADLINE_MS))
        review_timeout_seconds = getattr(
            self, "review_timeout_seconds", review_deadline_ms / 1000.0
        )
        reviewer_receiver_ids: set[str] = set()
        seen_reviewer_receiver_ids: set[str] = set()
        unidentified_reviewer_spawn_ids: set[str] = set()
        reviewer_deadline_at: float | None = None
        reviewer_spawned_at: float | None = None
        reviewer_wait_started_at: float | None = None
        reviewer_completed_at: float | None = None
        reviewer_result_ready = False
        reviewer_wait_count = 0
        reviewer_wait_target = "unobserved"
        reviewer_child_status = "unreported"
        reviewer_child_started = False
        retryable_provider_error: dict[str, object] | None = None
        terminal_provider_error: dict[str, object] | None = None
        provider_error_grace_deadline: float | None = None
        last_event_at = turn_started_at
        last_event_label = "turn/start"

        def record_reviewer_lifecycle(
            event: Mapping[str, object], event_at: float
        ) -> None:
            nonlocal reviewer_spawned_at
            nonlocal reviewer_wait_started_at
            nonlocal reviewer_completed_at
            nonlocal reviewer_result_ready
            nonlocal reviewer_wait_count
            nonlocal reviewer_wait_target
            nonlocal reviewer_child_status
            nonlocal reviewer_child_started

            item = event.get("item")
            if not isinstance(item, Mapping) or item.get("type") not in {
                "collabAgentToolCall",
                "collab_agent_tool_call",
            }:
                return
            tool = item.get("tool")
            if tool == "spawnAgent":
                seen_reviewer_receiver_ids.update(_collab_receiver_ids(item))
                spawn_item_id = item.get("id")
                if isinstance(spawn_item_id, str) and spawn_item_id:
                    if _collab_receiver_ids(item):
                        unidentified_reviewer_spawn_ids.discard(spawn_item_id)
                    else:
                        unidentified_reviewer_spawn_ids.add(spawn_item_id)
            if tool == "spawnAgent" and reviewer_deadline_at is None:
                # A later reviewer is a new bounded child lifecycle. Clear the
                # prior review's timestamps and summary before recording this
                # spawn, otherwise a previous completion masks its deadline.
                reviewer_spawned_at = event_at
                reviewer_wait_started_at = None
                reviewer_completed_at = None
                reviewer_result_ready = False
                reviewer_wait_count = 0
                reviewer_wait_target = "unobserved"
                reviewer_child_status = "unreported"
                reviewer_child_started = False
            status_label = _collab_status_label(item)
            if status_label != "unreported":
                reviewer_child_status = status_label
                reviewer_child_started = reviewer_child_started or bool(
                    set(status_label.split(","))
                    & {
                        "running",
                        "completed",
                        "failed",
                        "errored",
                        "stopped",
                        "cancelled",
                        "canceled",
                    }
                )
            if tool == "spawnAgent" and reviewer_spawned_at is None:
                reviewer_spawned_at = event_at
            elif tool == "wait":
                if event.get("type") == "item.started":
                    reviewer_wait_count += 1
                targets = _collab_receiver_ids(item)
                unassigned_targets = targets - reviewer_receiver_ids
                fresh_targets = targets - seen_reviewer_receiver_ids
                if (
                    len(unidentified_reviewer_spawn_ids) == 1
                    and len(unassigned_targets) == 1
                    and len(fresh_targets) == 1
                ):
                    # A wait can reveal the receiver id omitted by one spawn.
                    # Bind only a singleton-to-singleton case; multiple
                    # candidates remain ungraded rather than cross-attributed.
                    reviewer_receiver_ids.update(fresh_targets)
                    seen_reviewer_receiver_ids.update(fresh_targets)
                    unidentified_reviewer_spawn_ids.clear()
                # Remember even unmatched targets so a stale wait cannot later
                # be rebound to a new id-less spawn.
                seen_reviewer_receiver_ids.update(targets)
                if not targets:
                    reviewer_wait_target = "missing"
                elif not reviewer_receiver_ids:
                    reviewer_wait_target = "unknown"
                elif reviewer_receiver_ids <= targets:
                    reviewer_wait_target = "matched"
                elif reviewer_receiver_ids & targets:
                    reviewer_wait_target = "partial"
                else:
                    reviewer_wait_target = "mismatched"
                if (
                    event.get("type") == "item.started"
                    and reviewer_spawned_at is not None
                    and reviewer_wait_started_at is None
                ):
                    reviewer_wait_started_at = event_at
                completed_ids = _completed_reviewer_wait_ids(
                    event, reviewer_receiver_ids
                )
                if completed_ids and completed_ids == reviewer_receiver_ids:
                    reviewer_completed_at = event_at
                    reviewer_result_ready = True

        def record_provider_error(
            event: Mapping[str, object], event_at: float
        ) -> None:
            nonlocal retryable_provider_error
            nonlocal terminal_provider_error
            nonlocal provider_error_grace_deadline

            error = _codex_provider_error(event)
            if error is None:
                if _codex_root_progress_event(
                    event, thread_id=getattr(self, "_thread_id", None), turn_id=turn_id
                ):
                    if terminal_provider_error is not None:
                        # Keep the terminal provider diagnosis, but allow an
                        # active root turn to finish its teardown/terminal
                        # notification. The grace is an idle bound, capped by
                        # the parent turn deadline.
                        provider_error_grace_deadline = min(
                            deadline, event_at + _CODEX_PROVIDER_ERROR_GRACE_S
                        )
                    elif retryable_provider_error is not None:
                        retryable_provider_error = None
                return
            if not _codex_provider_error_matches_root(
                error, thread_id=self._thread_id, turn_id=turn_id
            ):
                return
            if terminal_provider_error is not None:
                existing_reason = _codex_provider_error_reason(terminal_provider_error)
                new_reason = _codex_provider_error_reason(error)
                if error.get("will_retry") is False and (
                    existing_reason != PROVIDER_SESSION_LIMIT
                    or new_reason == PROVIDER_SESSION_LIMIT
                ):
                    terminal_provider_error = error
                return
            if error.get("will_retry") is True:
                retryable_provider_error = error
            elif error.get("will_retry") is False:
                retryable_provider_error = None
                terminal_provider_error = error
                provider_error_grace_deadline = min(
                    deadline, event_at + _CODEX_PROVIDER_ERROR_GRACE_S
                )

        def observed_provider_reason() -> str | None:
            error = terminal_provider_error or retryable_provider_error
            return _codex_provider_error_reason(error) if error is not None else None

        def observed_provider_detail() -> str | None:
            if terminal_provider_error is not None:
                return _codex_provider_error_detail(terminal_provider_error)
            if retryable_provider_error is not None:
                return _codex_provider_error_detail(
                    retryable_provider_error, retry_pending=True
                )
            return None

        def failed_turn_reason(error: str) -> str:
            classified = classify_failure_reason(error)
            observed = observed_provider_reason()
            if classified == CODEX_PROVIDER_ERROR and observed is not None:
                return observed
            return classified or observed or CODEX_PROVIDER_ERROR

        if before_turn:
            for buffered_event in before_turn:
                if not is_root_event(buffered_event):
                    continue
                normalized_buffered = _normalise_app_server_event(buffered_event)
                record_provider_error(buffered_event, turn_started_at)
                last_event_label = _event_debug_tail([buffered_event], limit=1) or "buffered_event"
                record_reviewer_lifecycle(normalized_buffered, turn_started_at)
                reviewer_receiver_ids, reviewer_deadline_at = _update_reviewer_deadline(
                    normalized_buffered,
                    reviewer_receiver_ids,
                    reviewer_deadline_at,
                    now=turn_started_at,
                    review_deadline_ms=review_deadline_ms,
                )
                if (
                    normalized_buffered.get("type") == "turn.failed"
                    and normalized_buffered.get("turn_id") == turn_id
                ):
                    terminal_error = normalized_buffered.get("error")
                    safe_terminal_error = (
                        terminal_error if isinstance(terminal_error, str) else ""
                    )
                    self._turn_failure_reason = failed_turn_reason(safe_terminal_error)
                    observed_detail = observed_provider_detail()
                    if observed_detail is not None and (
                        not safe_terminal_error
                        or classify_failure_reason(safe_terminal_error)
                        == CODEX_PROVIDER_ERROR
                    ):
                        normalized_buffered = {
                            **normalized_buffered,
                            "error": observed_detail,
                        }
                elif (
                    normalized_buffered.get("type") == "turn.interrupted"
                    and normalized_buffered.get("turn_id") == turn_id
                ):
                    self._turn_failure_reason = observed_provider_reason()
                    observed_detail = observed_provider_detail()
                    if observed_detail is not None:
                        normalized_buffered = {
                            **normalized_buffered,
                            "error": observed_detail,
                        }
                elif (
                    normalized_buffered.get("type") == "turn.completed"
                    and normalized_buffered.get("turn_id") == turn_id
                    and terminal_provider_error is not None
                ):
                    self._turn_failure_reason = observed_provider_reason()
                events.append(
                    normalized_buffered
                    if normalized_buffered.get("type")
                    in {"provider_error", "turn.completed", "turn.interrupted", "turn.failed"}
                    else buffered_event
                )
                if normalized_buffered.get("type") in {
                    "turn.completed",
                    "turn.interrupted",
                    "turn.failed",
                } and normalized_buffered.get("turn_id") == turn_id:
                    return events
        while True:
            read_deadline = deadline
            if reviewer_deadline_at is not None:
                read_deadline = min(read_deadline, reviewer_deadline_at)
            if provider_error_grace_deadline is not None:
                read_deadline = min(read_deadline, provider_error_grace_deadline)
            try:
                event = self._read_streams(read_deadline)
            except TimeoutError as exc:
                now = time.monotonic()
                progress = _codex_turn_progress_detail(
                    turn_started_at=turn_started_at,
                    now=now,
                    last_event_at=last_event_at,
                    last_event_label=last_event_label,
                    reviewer_spawned_at=reviewer_spawned_at,
                    reviewer_wait_started_at=reviewer_wait_started_at,
                    reviewer_completed_at=reviewer_completed_at,
                    reviewer_result_ready=reviewer_result_ready,
                    reviewer_deadline_at=reviewer_deadline_at,
                    reviewer_wait_count=reviewer_wait_count,
                    reviewer_wait_target=reviewer_wait_target,
                    reviewer_child_status=reviewer_child_status,
                    reviewer_child_started=reviewer_child_started,
                )
                if terminal_provider_error is not None:
                    raise CodexAdapterError(
                        _codex_provider_error_detail(terminal_provider_error),
                        reason=_codex_provider_error_reason(terminal_provider_error),
                        safe_diagnostic=True,
                    ) from exc
                if retryable_provider_error is not None:
                    raise TimeoutError(
                        _codex_provider_error_detail(
                            retryable_provider_error, retry_pending=True
                        )
                        + f"; {progress}"
                    ) from exc
                if (
                    reviewer_deadline_at is not None
                    and now >= reviewer_deadline_at
                ):
                    raise TimeoutError(
                        "Codex reviewer child did not complete before the "
                        f"{review_timeout_seconds:.1f}-second reviewer deadline; {progress}"
                    ) from exc
                raise TimeoutError(f"{exc}; {progress}") from exc
            except CodexAdapterError as exc:
                if terminal_provider_error is not None:
                    raise CodexAdapterError(
                        _codex_provider_error_detail(terminal_provider_error),
                        reason=_codex_provider_error_reason(terminal_provider_error),
                        safe_diagnostic=True,
                    ) from exc
                if (
                    retryable_provider_error is not None
                    and isinstance(exc, CodexAppServerEOF)
                ):
                    raise CodexAdapterError(
                        "Codex app-server exited before a terminal result after "
                        + _codex_provider_error_detail(
                            retryable_provider_error, retry_pending=True
                        ),
                        reason=CHILD_EXITED_EARLY,
                        safe_diagnostic=True,
                    ) from exc
                raise
            if self._is_server_request(event):
                self._reject_server_request(event)
                continue
            if not is_root_event(event):
                continue
            normalized = _normalise_app_server_event(event)
            event_received_at = time.monotonic()
            record_provider_error(event, event_received_at)
            if (
                normalized.get("type") == "turn.failed"
                and normalized.get("turn_id") == turn_id
            ):
                terminal_error = normalized.get("error")
                safe_terminal_error = (
                    terminal_error if isinstance(terminal_error, str) else ""
                )
                self._turn_failure_reason = failed_turn_reason(safe_terminal_error)
                observed_detail = observed_provider_detail()
                if observed_detail is not None and (
                    not safe_terminal_error
                    or classify_failure_reason(safe_terminal_error)
                    == CODEX_PROVIDER_ERROR
                ):
                    normalized = {
                        **normalized,
                        "error": observed_detail,
                    }
            elif (
                normalized.get("type") == "turn.interrupted"
                and normalized.get("turn_id") == turn_id
            ):
                self._turn_failure_reason = observed_provider_reason()
                observed_detail = observed_provider_detail()
                if observed_detail is not None:
                    normalized = {**normalized, "error": observed_detail}
            events.append(
                normalized
                if normalized.get("type")
                in {"provider_error", "turn.completed", "turn.interrupted", "turn.failed"}
                else event
            )
            last_event_at = event_received_at
            last_event_label = _event_debug_tail([event], limit=1) or "unclassified_event"
            record_reviewer_lifecycle(normalized, event_received_at)
            if _reviewer_wait_without_target(
                normalized, reviewer_deadline_at is not None
            ):
                raise CodexAdapterError(
                    "Codex reviewer wait had no receiver target after a reviewer "
                    "was started; ending the turn with an incomplete handoff",
                    reason=CHILD_NO_TERMINAL_RESULT,
                )
            reviewer_receiver_ids, reviewer_deadline_at = _update_reviewer_deadline(
                normalized,
                reviewer_receiver_ids,
                reviewer_deadline_at,
                now=event_received_at,
                review_deadline_ms=review_deadline_ms,
            )
            if normalized.get("type") in {
                "turn.completed",
                "turn.interrupted",
                "turn.failed",
            }:
                if normalized.get("turn_id") != turn_id:
                    continue
                if normalized.get("type") == "turn.failed":
                    self._turn_failure_reason = (
                        self._turn_failure_reason or CODEX_PROVIDER_ERROR
                    )
                elif (
                    normalized.get("type") == "turn.completed"
                    and terminal_provider_error is not None
                ):
                    # The authoritative terminal frame can still say
                    # "completed" after a non-retryable provider notification.
                    # Preserve that observed failure classification for reports.
                    self._turn_failure_reason = observed_provider_reason()
                break
            if reviewer_deadline_at is not None and event_received_at >= reviewer_deadline_at:
                progress = _codex_turn_progress_detail(
                    turn_started_at=turn_started_at,
                    now=event_received_at,
                    last_event_at=last_event_at,
                    last_event_label=last_event_label,
                    reviewer_spawned_at=reviewer_spawned_at,
                    reviewer_wait_started_at=reviewer_wait_started_at,
                    reviewer_completed_at=reviewer_completed_at,
                    reviewer_result_ready=reviewer_result_ready,
                    reviewer_deadline_at=reviewer_deadline_at,
                    reviewer_wait_count=reviewer_wait_count,
                    reviewer_wait_target=reviewer_wait_target,
                    reviewer_child_status=reviewer_child_status,
                    reviewer_child_started=reviewer_child_started,
                )
                if terminal_provider_error is not None:
                    raise CodexAdapterError(
                        _codex_provider_error_detail(terminal_provider_error),
                        reason=_codex_provider_error_reason(terminal_provider_error),
                        safe_diagnostic=True,
                    )
                if retryable_provider_error is not None:
                    raise TimeoutError(
                        _codex_provider_error_detail(
                            retryable_provider_error, retry_pending=True
                        )
                        + f"; {progress}"
                    )
                raise TimeoutError(
                    "Codex reviewer child did not complete before the "
                    f"{review_timeout_seconds:.1f}-second reviewer deadline; {progress}"
                )
            if event_received_at >= deadline:
                progress = _codex_turn_progress_detail(
                    turn_started_at=turn_started_at,
                    now=event_received_at,
                    last_event_at=last_event_at,
                    last_event_label=last_event_label,
                    reviewer_spawned_at=reviewer_spawned_at,
                    reviewer_wait_started_at=reviewer_wait_started_at,
                    reviewer_completed_at=reviewer_completed_at,
                    reviewer_result_ready=reviewer_result_ready,
                    reviewer_deadline_at=reviewer_deadline_at,
                    reviewer_wait_count=reviewer_wait_count,
                    reviewer_wait_target=reviewer_wait_target,
                    reviewer_child_status=reviewer_child_status,
                    reviewer_child_started=reviewer_child_started,
                )
                if terminal_provider_error is not None:
                    raise CodexAdapterError(
                        _codex_provider_error_detail(terminal_provider_error),
                        reason=_codex_provider_error_reason(terminal_provider_error),
                        safe_diagnostic=True,
                    )
                if retryable_provider_error is not None:
                    raise TimeoutError(
                        _codex_provider_error_detail(
                            retryable_provider_error, retry_pending=True
                        )
                        + f"; {progress}"
                    )
                raise TimeoutError(
                    "Codex app-server turn deadline expired; "
                    + progress
                )
        return events

    def _prompt(self, text: str, attachment_paths: Sequence[str]) -> str:
        text += (
            "\n\nRun-local source handoff:\n"
            f"- NXD_EVAL_FIXTURE_DIR={self.fixture_dir}\n"
            "- For a file-backed source, read only the supplied input files under "
            "that directory and wire them into the closure; do not use oracle or "
            "gold files as source data.\n"
            "- For an API-backed source, use the workspace infra-profile.yaml and "
            "the generated connector runtime.\n"
        )
        if attachment_paths:
            text += "\n\nAttached files are available at:\n" + "\n".join(f"- {path}" for path in attachment_paths)
        text += (
            "\n\nParent-thread file-change reminder (never forward this paragraph "
            "to a reviewer child): use one complete Add File operation for "
            "each new text file, or a correctly structured Update File hunk for "
            "an existing file. Never place raw file contents in patch metadata "
            "or use a bare content line as a hunk header. If an edit is rejected, "
            "treat it as an edit-syntax failure: correct the patch envelope and "
            "retry once with a complete valid file-change operation. Do not resend "
            "the same malformed payload or report an environment blocker unless "
            "the corrected operation is rejected too."
        )
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
        lightweight: bool = False,
    ) -> TurnResult:
        parsed, observations = parse_codex_events(
            events,
            redact_json_rpc=self._redact_json_rpc,
            redact_text=self._redact_text,
            session_id=self._thread_id,
            root_turn_id=self._active_turn_id,
        )
        if parsed.session_id:
            self._thread_id = parsed.session_id
        if parsed.last_mcp_call:
            self._last_mcp_call = parsed.last_mcp_call
        self._review_pending = _review_pending_after_observations(
            observations, self._review_pending
        )
        changed: tuple[TouchedFile, ...] = ()
        if not lightweight:
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
        tool_calls = _attach_checker_skew_markers(
            parsed.tool_calls,
            observations,
            skill_pack_root=self.skill_pack_root,
            supervisor_data_dir=self.supervisor_data_dir,
        )
        return TurnResult(
            transcript_delta=parsed.transcript_delta,
            agent_message=parsed.agent_message,
            tool_calls=tool_calls,
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
        self._active_turn_id = None
        process = self._process
        if process is None:
            raise CodexAdapterError("Codex app-server is not running")
        request_id = self._next_rpc_id()
        events: list[Mapping[str, object]] = list(self._startup_events)
        self._startup_events.clear()
        try:
            sandbox_policy = _turn_sandbox_policy(
                self._review_pending,
                [str(Path.cwd()), str(self.skill_pack_root)],
            )
            self._write_rpc(
                "turn/start",
                {
                    "threadId": self._thread_id,
                    "input": [{"type": "text", "text": prompt}],
                    "cwd": str(Path.cwd()),
                    "model": self.model,
                    "approvalPolicy": "never",
                    "effort": self.effort,
                    "sandboxPolicy": sandbox_policy,
                },
                request_id=request_id,
            )
            events = self._collect_turn(request_id, prompt, events)
        except TimeoutError as exc:
            failure_reason = _codex_timeout_failure_reason(
                exc,
                "\n".join(self._stderr_tail)[-2000:],
                root_turn_id=self._active_turn_id,
            )
            detail = (
                ""
                if failure_reason in _CODEX_PROVIDER_FAILURE_REASONS
                else "\n".join(self._stderr_tail)[-2000:]
            )
            event_tail = _event_debug_tail(events)
            if failure_reason in _CODEX_PROVIDER_FAILURE_REASONS:
                if (
                    failure_reason == CODEX_PROVIDER_RETRY_PENDING
                    and str(exc).startswith(f"{CODEX_PROVIDER_RETRY_PENDING} (")
                ):
                    timeout_summary = _codex_timeout_detail(
                        exc, parent_turn_limit_s=self.timeout_s
                    )
                else:
                    timeout_summary = (
                        f"Codex provider failure ({failure_reason}); "
                        f"parent_turn_limit={self.timeout_s:.1f}s"
                    )
            else:
                timeout_summary = _codex_timeout_detail(
                    exc, parent_turn_limit_s=self.timeout_s
                )
            self._terminate(process)
            self._process = None
            return self._finish(
                events,
                environment_detail=(
                    timeout_summary
                    + (f"; stderr={detail}" if detail else "")
                    + (f"; event_tail={event_tail}" if event_tail else "")
                ),
                turn_timed_out=True,
                failure_reason=failure_reason,
                lightweight=True,
            )
        except (CodexAdapterError, OSError, ValueError) as exc:
            raw_stderr = "\n".join(self._stderr_tail)[-2000:]
            safe_diagnostic = getattr(exc, "safe_diagnostic", False) is True
            diagnostic_reason = (
                None
                if safe_diagnostic
                else classify_failure_reason(str(exc), raw_stderr)
            )
            explicit_reason = getattr(exc, "reason", None)
            if diagnostic_reason in _CODEX_PROVIDER_FAILURE_REASONS:
                reason = diagnostic_reason
            else:
                reason = first_reason((explicit_reason, diagnostic_reason))
            provider_failure = reason in _CODEX_PROVIDER_FAILURE_REASONS
            detail = "" if provider_failure or safe_diagnostic else raw_stderr
            if safe_diagnostic or (
                provider_failure and explicit_reason in _CODEX_PROVIDER_FAILURE_REASONS
            ):
                error_summary = f"Codex app-server turn failed: {exc}"
            elif provider_failure:
                error_summary = f"Codex app-server turn failed ({reason})"
            else:
                error_summary = f"Codex app-server turn failed: {exc}"
            self._terminate(process)
            self._process = None
            return self._finish(
                events,
                environment_detail=error_summary + (f"; stderr={detail}" if detail else ""),
                failure_reason=first_reason(
                    (
                        reason,
                        classify_failure_reason(str(exc), detail),
                        CHILD_EXITED_EARLY,
                    )
                ),
            )
        return self._finish(
            events,
            failure_reason=getattr(self, "_turn_failure_reason", None),
        )

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


def _write_result(value: TurnResult, *, backend: str | None = None) -> None:
    from dp_scenarios.runner.session import turn_result_to_dict

    if backend is not None:
        value = replace(value, backend=backend)
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
    parser.add_argument(
        "--review-timeout",
        type=float,
        default=None,
        help="maximum seconds for the retained-capture reviewer",
    )
    parser.add_argument("--mcp-config", type=Path, required=True)
    parser.add_argument("--strict-mcp-config", action="store_true")
    parser.add_argument("--supervisor-data-dir", type=Path, required=True)
    parser.add_argument(
        "--multi-agent-v2",
        action="store_true",
        help="enable Codex's experimental multi-agent-v2 collaboration backend",
    )
    parser.add_argument("--allowedTools")
    parser.add_argument("--native-continuation", action="store_true")
    parser.add_argument("--native-state-dir", type=Path)
    parser.add_argument("--resume-session-id")
    parser.add_argument("--append-system-prompt", default=CODEX_SYSTEM_PROMPT)
    return parser


def _safe_adapter_failure_detail(error: BaseException) -> str:
    """Summarize startup failures without serializing stderr/provider text."""

    if isinstance(error, CodexAppServerEOF):
        summary = "Codex app-server exited before returning an event"
    elif isinstance(error, TimeoutError):
        summary = "Codex app-server operation deadline expired"
    elif isinstance(error, OSError):
        summary = "Codex app-server process or pipe operation failed"
    elif isinstance(error, ValueError):
        summary = "Codex adapter received invalid input"
    else:
        summary = "Codex adapter could not start or complete the turn"
    reason = first_reason(
        (getattr(error, "reason", None), classify_failure_reason(str(error)))
    )
    return f"{summary} ({reason})" if reason is not None else summary


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
        multi_agent_v2=args.multi_agent_v2,
        review_timeout_seconds=args.review_timeout,
        native_continuation=args.native_continuation,
        resume_session_id=args.resume_session_id,
        native_state_dir=(
            args.native_state_dir.expanduser().resolve()
            if args.native_state_dir is not None
            else None
        ),
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
                _write_result(adapter.send(request), backend="codex")
            except (CodexAdapterError, OSError, ValueError) as exc:
                _write_result(
                    TurnResult(
                        environment_wedged=True,
                        environment_detail=_safe_adapter_failure_detail(exc),
                        failure_reason=first_reason(
                            (
                                getattr(exc, "reason", None),
                                classify_failure_reason(str(exc)),
                            )
                        ),
                        last_mcp_call=adapter.last_mcp_call,
                        session_id=adapter._thread_id,
                    ),
                    backend="codex",
                )
    finally:
        adapter.close()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
