"""Session transports for live turns and byte-faithful replay.

The invariant enforced here is that the operator engine receives structured
observations from the session boundary.  Replay records those observations,
including tool calls and touched-file bytes, so it never reconstructs facts
from an agent transcript sentence; live mode uses the same message-in,
structured-turn-out protocol.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
import os
from pathlib import Path
import select
import signal
import subprocess
from typing import Any, Protocol

from dp_scenarios.knobs import EndpointObservation, WorkflowSwitchEvidence, WorkflowSwitchPlan
from dp_scenarios.failure_reasons import (
    CHILD_EXITED_EARLY,
    CHILD_NO_TERMINAL_RESULT,
    classify_failure_reason,
)
from dp_scenarios.operator.transport import (
    Attachment,
    OperatorMessage,
    ToolCall,
    Transport,
    TouchedFile,
    TurnResult,
)


#: Cap on one stderr drain.  Ample for the tail both callers keep, and small
#: enough that a child writing faster than the parent reads cannot hold the
#: drain open past the turn deadline it is being asked to explain.
_STDERR_DRAIN_BYTES = 64 * 1024


class SessionError(RuntimeError):
    """Raised when a session cannot satisfy the structured transport contract."""


class ReplayMismatch(SessionError):
    """Raised when a replay receives a different operator message."""


# These names are written by the harness from supervisor/source observations.
# An agent must not be able to manufacture an oracle by reporting a touched
# file with the same name.
_RESERVED_HARNESS_ARTIFACT_NAMES = frozenset(
    {
        "row-count-oracle.json",
        "row_counts.json",
        "route-fidelity.json",
        "route_fidelity.json",
        "ledger-extra.json",
        "ledger_rows.json",
    }
)


def _encode(value: object) -> object:
    if isinstance(value, bytes):
        return {"__bytes__": base64.b64encode(value).decode("ascii")}
    if isinstance(value, Path):
        return {"__path__": str(value)}
    if isinstance(value, Mapping):
        return {str(key): _encode(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_encode(item) for item in value]
    return value


def _decode(value: object) -> object:
    if isinstance(value, Mapping):
        if set(value) == {"__bytes__"} and isinstance(value["__bytes__"], str):
            try:
                return base64.b64decode(value["__bytes__"], validate=True)
            except (ValueError, base64.binascii.Error) as exc:
                raise SessionError("recorded bytes value is not valid base64") from exc
        if set(value) == {"__path__"} and isinstance(value["__path__"], str):
            return Path(value["__path__"])
        return {str(key): _decode(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_decode(item) for item in value]
    return value


def operator_message_to_dict(message: OperatorMessage) -> dict[str, object]:
    """Serialize the exact message sent across the operator boundary."""

    return {
        "text": message.text,
        "attachments": [
            {"name": item.name, "content": _encode(item.content), "kind": item.kind}
            for item in message.attachments
        ],
    }


def operator_message_from_dict(value: Mapping[str, object]) -> OperatorMessage:
    """Decode a recorded operator message with strict attachment fields."""

    text = value.get("text")
    raw_attachments = value.get("attachments", [])
    if not isinstance(text, str) or not isinstance(raw_attachments, Sequence) or isinstance(raw_attachments, (str, bytes)):
        raise SessionError("recorded operator message has an invalid shape")
    attachments: list[Attachment] = []
    for raw in raw_attachments:
        if not isinstance(raw, Mapping) or not isinstance(raw.get("name"), str) or not isinstance(raw.get("kind", "file"), str):
            raise SessionError("recorded operator message has an invalid attachment")
        content = _decode(raw.get("content", {"__bytes__": ""}))
        if not isinstance(content, bytes):
            raise SessionError("recorded attachment content is not bytes")
        attachments.append(Attachment(raw["name"], content, raw.get("kind", "file")))
    return OperatorMessage(text, tuple(attachments))


def turn_result_to_dict(result: TurnResult) -> dict[str, object]:
    """Serialize every structured observation returned by one session turn."""

    return {
        "transcript_delta": _encode(result.transcript_delta),
        "agent_message": _encode(result.agent_message),
        "tool_calls": [
            {"name": call.name, "arguments": _encode(call.arguments), "result": _encode(call.result)}
            for call in result.tool_calls
        ],
        "tool_results": _encode(list(result.tool_results)),
        "files_touched": [
            {"path": _encode(item.path), "content": _encode(item.content)}
            for item in result.files_touched
        ],
        "approval_artifact": _encode(result.approval_artifact),
        "build_failed": result.build_failed,
        "build_failure_count": result.build_failure_count,
        "reported": result.reported,
        "environment_wedged": result.environment_wedged,
        "turn_timed_out": result.turn_timed_out,
        "environment_detail": result.environment_detail,
        "failure_reason": result.failure_reason,
        "last_mcp_call": result.last_mcp_call,
        "session_id": result.session_id,
    }


def turn_result_from_dict(value: Mapping[str, object]) -> TurnResult:
    """Decode a structured result without deriving fields from prose."""

    allowed = set(TurnResult.__dataclass_fields__)  # type: ignore[attr-defined]
    unknown = set(value) - allowed
    if unknown:
        raise SessionError("recorded turn has unknown field(s): " + ", ".join(sorted(map(str, unknown))))
    raw_calls = value.get("tool_calls", [])
    raw_files = value.get("files_touched", [])
    if not isinstance(raw_calls, Sequence) or isinstance(raw_calls, (str, bytes)):
        raise SessionError("recorded tool_calls must be a list")
    if not isinstance(raw_files, Sequence) or isinstance(raw_files, (str, bytes)):
        raise SessionError("recorded files_touched must be a list")
    calls: list[ToolCall] = []
    for raw in raw_calls:
        if not isinstance(raw, Mapping) or not isinstance(raw.get("name"), str):
            raise SessionError("recorded tool call has an invalid shape")
        calls.append(ToolCall(raw["name"], _decode(raw.get("arguments")), _decode(raw.get("result"))))
    files: list[TouchedFile] = []
    for raw in raw_files:
        if not isinstance(raw, Mapping):
            raise SessionError("recorded touched file has an invalid shape")
        path = _decode(raw.get("path"))
        if not isinstance(path, (str, Path)):
            raise SessionError("recorded touched file path is not text")
        files.append(TouchedFile(path, _decode(raw.get("content"))))
    tool_results = _decode(value.get("tool_results", []))
    if not isinstance(tool_results, list):
        raise SessionError("recorded tool_results must be a list")
    return TurnResult(
        transcript_delta=_decode(value.get("transcript_delta", "")),  # type: ignore[arg-type]
        agent_message=_decode(value.get("agent_message", "")),  # type: ignore[arg-type]
        tool_calls=tuple(calls),
        tool_results=tuple(tool_results),
        files_touched=tuple(files),
        approval_artifact=_decode(value.get("approval_artifact")),  # type: ignore[arg-type]
        build_failed=bool(value.get("build_failed", False)),
        build_failure_count=int(value.get("build_failure_count", 0)),
        reported=bool(value.get("reported", False)),
        environment_wedged=bool(value.get("environment_wedged", False)),
        turn_timed_out=bool(value.get("turn_timed_out", False)),
        environment_detail=value.get("environment_detail") if isinstance(value.get("environment_detail"), str) else None,
        failure_reason=value.get("failure_reason") if isinstance(value.get("failure_reason"), str) else None,
        last_mcp_call=value.get("last_mcp_call") if isinstance(value.get("last_mcp_call"), str) else None,
        session_id=value.get("session_id") if isinstance(value.get("session_id"), str) else None,
    )


@dataclass(frozen=True, slots=True)
class RecordedTurn:
    """One input/output pair in a replayable session artifact."""

    operator_message: OperatorMessage
    result: TurnResult

    def to_dict(self) -> dict[str, object]:
        return {
            "operator_message": operator_message_to_dict(self.operator_message),
            "result": turn_result_to_dict(self.result),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> "RecordedTurn":
        message = value.get("operator_message")
        result = value.get("result")
        if not isinstance(message, Mapping) or not isinstance(result, Mapping):
            raise SessionError("recorded turn requires operator_message and result objects")
        return cls(operator_message_from_dict(message), turn_result_from_dict(result))


@dataclass(frozen=True, slots=True)
class ReplayRecording:
    """A complete replay artifact, including structured observations and pins."""

    turns: tuple[RecordedTurn, ...]
    manifest: Mapping[str, object] | None = None
    supervisor_facts: Mapping[str, object] | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.turns:
            raise SessionError("a replay recording must contain at least one turn")

    def to_dict(self) -> dict[str, object]:
        return {
            "format_version": 1,
            "turns": [turn.to_dict() for turn in self.turns],
            "manifest": _encode(self.manifest) if self.manifest is not None else None,
            "supervisor_facts": _encode(self.supervisor_facts) if self.supervisor_facts is not None else None,
            "metadata": _encode(dict(self.metadata)),
        }

    def to_report_dict(self) -> dict[str, object]:
        """Serialize a replay while excluding touched-file contents from reports.

        The live grader still uses :meth:`to_dict` and the in-memory recording
        for byte-faithful replay.  A retained report only needs the paths and
        a stable content identity; raw closure bytes may contain credentials
        copied from a source URL or generated configuration.
        """

        document = self.to_dict()
        raw_turns = document["turns"]
        if isinstance(raw_turns, list):
            for turn, raw_turn in zip(self.turns, raw_turns, strict=True):
                if not isinstance(raw_turn, Mapping):
                    continue
                raw_result = raw_turn.get("result")
                if not isinstance(raw_result, Mapping):
                    continue
                raw_files = raw_result.get("files_touched")
                if not isinstance(raw_files, list):
                    continue
                for touched, raw_file in zip(turn.result.files_touched, raw_files, strict=True):
                    if touched.content is None or not isinstance(raw_file, dict):
                        continue
                    content = (
                        touched.content.encode("utf-8")
                        if isinstance(touched.content, str)
                        else touched.content
                    )
                    if not isinstance(content, bytes):
                        continue
                    raw_file["content"] = {
                        "redacted": True,
                        "sha256": hashlib.sha256(content).hexdigest(),
                        "size_bytes": len(content),
                    }
        metadata = document.get("metadata")
        if isinstance(metadata, dict):
            metadata["touched_file_contents_redacted"] = True
        return document

    def write(self, path: str | Path) -> Path:
        """Write the replay artifact with stable JSON formatting."""

        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        return target

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> "ReplayRecording":
        if value.get("format_version", 1) != 1:
            raise SessionError("unsupported replay recording format")
        raw_turns = value.get("turns")
        if not isinstance(raw_turns, Sequence) or isinstance(raw_turns, (str, bytes)):
            raise SessionError("replay recording turns must be a list")
        turns = tuple(RecordedTurn.from_dict(item) for item in raw_turns if isinstance(item, Mapping))
        if len(turns) != len(raw_turns):
            raise SessionError("every replay turn must be an object")
        manifest = _decode(value.get("manifest"))
        facts = _decode(value.get("supervisor_facts"))
        metadata = _decode(value.get("metadata", {}))
        if manifest is not None and not isinstance(manifest, Mapping):
            raise SessionError("replay manifest must be an object")
        if facts is not None and not isinstance(facts, Mapping):
            raise SessionError("replay supervisor_facts must be an object")
        if not isinstance(metadata, Mapping):
            raise SessionError("replay metadata must be an object")
        return cls(turns, manifest, facts, metadata)

    @classmethod
    def read(cls, path: str | Path) -> "ReplayRecording":
        target = Path(path)
        try:
            raw = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise SessionError(f"could not read replay recording {target}: {exc}") from exc
        if not isinstance(raw, Mapping):
            raise SessionError(f"replay recording {target} is not an object")
        return cls.from_dict(raw)


def _message_equal(left: OperatorMessage, right: OperatorMessage) -> bool:
    return operator_message_to_dict(left) == operator_message_to_dict(right)


def _relative_touched_path(path: str | Path, sandbox_home: Path | None) -> Path:
    """Return a contained, replay-portable touched-file path.

    Live adapters commonly report the absolute path inside the session home.
    Recording that path would make the artifact machine-specific and would
    also fail replay's artifact-root containment check.  Normalize it at the
    session boundary while retaining the same fail-closed containment rule for
    relative paths such as ``../outside``.
    """

    candidate = Path(path)
    if candidate.is_absolute():
        if sandbox_home is None:
            raise SessionError(f"absolute touched-file path requires a sandbox home: {candidate}")
        home = sandbox_home.resolve()
        resolved = candidate.resolve()
        try:
            relative = resolved.relative_to(home)
        except ValueError as exc:
            raise SessionError(f"touched-file path escapes sandbox home: {candidate}") from exc
    else:
        relative = candidate

    if relative.is_absolute():
        raise SessionError(f"touched-file path must be relative: {relative}")
    if sandbox_home is not None:
        home = sandbox_home.resolve()
        target = (home / relative).resolve()
        if home not in target.parents and target != home:
            raise SessionError(f"touched-file path escapes sandbox home: {path}")
    return Path(relative.as_posix())


def _normalized_turn_result(result: TurnResult, sandbox_home: Path | None) -> TurnResult:
    """Copy a turn result with all touched paths made replay-portable."""

    files: list[TouchedFile] = []
    for item in result.files_touched:
        relative = _relative_touched_path(item.path, sandbox_home)
        content = item.content
        if content is None and sandbox_home is not None:
            source = (sandbox_home.resolve() / relative).resolve()
            if source.is_file():
                content = source.read_bytes()
        files.append(TouchedFile(relative.as_posix(), content))
    return replace(result, files_touched=files)


def _materialize_touched_files(
    result: TurnResult,
    artifact_root: Path,
    *,
    source_root: Path | None = None,
) -> None:
    """Materialize structured file observations into the grading root."""

    root = artifact_root.resolve()
    for touched in result.files_touched:
        relative = _relative_touched_path(touched.path, None)
        if relative.name in _RESERVED_HARNESS_ARTIFACT_NAMES:
            raise SessionError(
                f"touched-file path is reserved for harness-owned evidence: {relative}"
            )
        target = (root / relative).resolve()
        if root not in target.parents and target != root:
            raise SessionError(f"touched-file path escapes artifact root: {relative}")
        content = touched.content
        if content is None and source_root is not None:
            source = (source_root.resolve() / relative).resolve()
            home = source_root.resolve()
            if home not in source.parents and source != home:
                raise SessionError(f"touched-file path escapes sandbox home: {relative}")
            if source.is_file():
                content = source.read_bytes()
        if content is None:
            continue
        content = content.encode("utf-8") if isinstance(content, str) else content
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)


class ReplaySession:
    """Replay structured turns and materialize recorded files into a sandbox."""

    def __init__(self, recording: ReplayRecording | str | Path, *, artifact_root: str | Path | None = None) -> None:
        self.recording = recording if isinstance(recording, ReplayRecording) else ReplayRecording.read(recording)
        self.artifact_root = Path(artifact_root).resolve() if artifact_root is not None else None
        self._index = 0
        self._session_counter = 0
        self.sent_messages: list[OperatorMessage] = []

    def start_fresh_session(self) -> str:
        self._session_counter += 1
        return f"replay-session-{self._session_counter}"

    start_fresh = start_fresh_session

    def resume_session(self, session_id: str | None = None) -> str | None:
        return session_id

    resume = resume_session

    @property
    def remaining_turns(self) -> int:
        """Return recorded turns that the operator has not consumed."""

        return len(self.recording.turns) - self._index

    def _materialize(self, result: TurnResult) -> None:
        if self.artifact_root is None:
            return
        for touched in result.files_touched:
            if touched.content is None:
                continue
            raw_path = Path(touched.path)
            if raw_path.is_absolute():
                raise SessionError(f"replay touched-file path must be relative: {raw_path}")
            if raw_path.name in _RESERVED_HARNESS_ARTIFACT_NAMES:
                raise SessionError(
                    f"touched-file path is reserved for harness-owned evidence: {raw_path}"
                )
            target = (self.artifact_root / raw_path).resolve()
            if self.artifact_root not in target.parents and target != self.artifact_root:
                raise SessionError(f"replay touched-file path escapes artifact root: {raw_path}")
            content = touched.content.encode("utf-8") if isinstance(touched.content, str) else touched.content
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)

    def send_message(self, message: OperatorMessage | str) -> TurnResult:
        if isinstance(message, str):
            message = OperatorMessage(message)
        if self._index >= len(self.recording.turns):
            raise SessionError("replay transcript exhausted before the operator script ended")
        expected = self.recording.turns[self._index]
        self.sent_messages.append(message)
        if not _message_equal(message, expected.operator_message):
            raise ReplayMismatch(
                f"replay operator message differs at turn {self._index + 1}: "
                f"expected={expected.operator_message.text!r}, received={message.text!r}"
            )
        self._index += 1
        self._materialize(expected.result)
        return expected.result

    send = send_message


ResponseHandler = Callable[[OperatorMessage], TurnResult]

WorkflowRestart = Callable[[str], Transport]
WorkflowObserver = Callable[[OperatorMessage, TurnResult, str], EndpointObservation]
WorkflowEvidenceSink = Callable[[WorkflowSwitchEvidence, int], None]


class DesktopSessionLifecycle(Protocol):
    """The small lifecycle seam owned by the shared desktop substrate."""

    def ensure_started(self) -> Any: ...

    def attach_process(self, process: Any) -> None: ...

    def cleanup(self) -> None: ...


class LiveSession:
    """Drive a headless JSONL session without exposing harness state to it.

    A callable handler is useful for an authenticated local adapter.  When a
    command is supplied, the child process receives one JSON request per line
    and must return one JSON object containing the explicit ``TurnResult``
    fields per line; no agent prose is interpreted as an observation.
    """

    def __init__(
        self,
        command: Sequence[str] | None = None,
        *,
        environment: Mapping[str, str] | None = None,
        cwd: str | Path | None = None,
        timeout: float = 300.0,
        handler: ResponseHandler | None = None,
        desktop_session: DesktopSessionLifecycle | None = None,
    ) -> None:
        if command is None and handler is None:
            raise SessionError("live session requires a command or structured response handler")
        if command is not None and not command:
            raise SessionError("live session command must not be empty")
        if timeout <= 0:
            raise SessionError("live session timeout must be positive")
        self.command = tuple(command) if command is not None else None
        self.environment = dict(environment or {})
        self.cwd = str(cwd) if cwd is not None else None
        self.timeout = timeout
        self.handler = handler
        # The shared DesktopStdioSession is the owner of a live process group
        # when this session was created by DesktopStdioTransport.  The
        # protocol keeps replay and handler-backed sessions independent of the
        # substrate while making the lifecycle contract explicit.
        self.desktop_session = desktop_session
        self._process: subprocess.Popen[str] | None = None
        self._session_counter = 0

    def start_fresh_session(self) -> str:
        self._session_counter += 1
        if self.handler is None:
            if self._process is not None:
                # A fresh session must discard the persistent child, not just
                # mint a new harness label over the same conversation.
                self._stop_process(wait_timeout=min(self.timeout, 5.0))
            if self.desktop_session is not None:
                self.desktop_session.ensure_started()
            assert self.command is not None
            self._process = subprocess.Popen(
                list(self.command),
                cwd=self.cwd,
                env=self.environment,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                start_new_session=True,
            )
            if self.desktop_session is not None:
                self.desktop_session.attach_process(self._process)
        return f"live-session-{self._session_counter}"

    start_fresh = start_fresh_session

    def resume_session(self, session_id: str | None = None) -> str | None:
        return session_id

    resume = resume_session

    def send_message(self, message: OperatorMessage | str) -> TurnResult:
        if isinstance(message, str):
            message = OperatorMessage(message)
        if self.handler is not None:
            result = self.handler(message)
            if not isinstance(result, TurnResult):
                raise SessionError("live response handler returned no TurnResult")
            return result
        if self._process is None or self._process.stdin is None or self._process.stdout is None:
            self.start_fresh_session()
        assert self._process is not None and self._process.stdin is not None and self._process.stdout is not None
        request = {"type": "turn", "message": operator_message_to_dict(message)}
        self._process.stdin.write(json.dumps(request, ensure_ascii=False, sort_keys=True) + "\n")
        self._process.stdin.flush()
        ready, _, _ = select.select([self._process.stdout], [], [], self.timeout)
        if not ready:
            detail = f"live session exceeded the {self.timeout:.3f}s turn timeout"
            # Return a structured wedge so RecordingSession and TierRunner can
            # persist the partial replay, ledger, and final report. Raising
            # here loses the completed earlier turns and makes a live timeout
            # look like a graded failure instead of an infrastructure crash.
            # Read whatever the child already wrote to stderr without
            # blocking on EOF: a provider limit is usually announced there,
            # and it is the difference between "the scenario stalled" and
            # "the account cannot start another turn".
            stderr_tail = self._drain_stderr_nonblocking()
            reason = classify_failure_reason(stderr_tail) or CHILD_NO_TERMINAL_RESULT
            if stderr_tail:
                detail += f": {stderr_tail[-500:]}"
            self.close(wait_timeout=min(self.timeout, 5.0))
            return TurnResult(
                turn_timed_out=True,
                environment_wedged=False,
                environment_detail=detail,
                failure_reason=reason,
                session_id=f"live-session-{self._session_counter}",
            )
        line = self._process.stdout.readline()
        if not line:
            stderr = self._drain_stderr_nonblocking()
            detail = "live session ended without a structured turn result"
            if stderr:
                detail += f": {stderr[-500:]}"
            self.close(wait_timeout=min(self.timeout, 5.0))
            return TurnResult(
                environment_wedged=True,
                environment_detail=detail,
                failure_reason=classify_failure_reason(stderr) or CHILD_EXITED_EARLY,
                session_id=f"live-session-{self._session_counter}",
            )
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SessionError("live session returned a non-JSON turn result") from exc
        if not isinstance(raw, Mapping):
            raise SessionError("live session turn result is not an object")
        nested = raw.get("result", raw)
        if not isinstance(nested, Mapping):
            raise SessionError("live session result member is not an object")
        return turn_result_from_dict(nested)

    send = send_message

    def _drain_stderr_nonblocking(self) -> str:
        """Return whatever the child has already written to stderr.

        ``stderr.read()`` blocks until EOF, and a wedged child keeps the pipe
        open -- on the timeout path that turned a bounded turn deadline into
        an unbounded parent hang.

        The drain is capped rather than run to exhaustion.  Reading unblocks a
        child stalled on a full pipe, which lets it write more, so a child
        logging retries faster than the parent drains would keep this loop
        alive past the very deadline it is reporting.  Both callers keep only
        the last 500 characters, so the cap costs no diagnostic.
        """

        budget = _STDERR_DRAIN_BYTES

        process = self._process
        if process is None or process.stderr is None:
            return ""
        chunks: list[str] = []
        stream = process.stderr
        try:
            descriptor = stream.fileno()
        except (OSError, ValueError):
            return ""
        while budget > 0:
            ready, _, _ = select.select([descriptor], [], [], 0)
            if not ready:
                break
            try:
                chunk = os.read(descriptor, min(65536, budget))
            except OSError:
                break
            if not chunk:
                break
            budget -= len(chunk)
            chunks.append(chunk.decode("utf-8", errors="replace"))
        return "".join(chunks)

    def _stop_process(self, *, wait_timeout: float) -> None:
        """Stop this session's process group without closing shared Desktop."""

        process = self._process
        if process is None:
            return
        if process.poll() is None:
            with contextlib.suppress(OSError):
                os.killpg(process.pid, signal.SIGTERM)
            with contextlib.suppress(OSError):
                process.terminate()
            try:
                process.wait(timeout=wait_timeout)
            except subprocess.TimeoutExpired:
                with contextlib.suppress(OSError):
                    os.killpg(process.pid, signal.SIGKILL)
                with contextlib.suppress(OSError):
                    process.kill()
                with contextlib.suppress(subprocess.TimeoutExpired):
                    process.wait(timeout=5)
        self._process = None

    def close(self, *, wait_timeout: float | None = None) -> None:
        """Stop the child, using a short grace period after a turn timeout."""

        if self._process is None:
            if self.desktop_session is not None:
                self.desktop_session.cleanup()
            return
        shutdown_timeout = self.timeout if wait_timeout is None else wait_timeout
        try:
            if self.desktop_session is not None:
                # DesktopStdioSession owns the process group and its bounded
                # reap path.  This also runs when turn parsing raised.
                self.desktop_session.cleanup()
            else:
                self._stop_process(wait_timeout=shutdown_timeout)
        finally:
            self._process = None

    def __enter__(self) -> "LiveSession":
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.close()


class RecordingSession:
    """Capture a live transport's structured messages and observations."""

    def __init__(
        self,
        transport: Transport,
        *,
        artifact_root: str | Path | None = None,
        sandbox_home: str | Path | None = None,
        workflow_switch: WorkflowSwitchPlan | None = None,
        workflow_restart: WorkflowRestart | None = None,
        workflow_observer: WorkflowObserver | None = None,
        workflow_evidence: WorkflowEvidenceSink | None = None,
    ) -> None:
        self.transport = transport
        self.artifact_root = Path(artifact_root).resolve() if artifact_root is not None else None
        self.sandbox_home = Path(sandbox_home).resolve() if sandbox_home is not None else None
        if self.artifact_root is not None:
            self.artifact_root.mkdir(parents=True, exist_ok=True)
        self.turns: list[RecordedTurn] = []
        self.workflow_switch = workflow_switch
        self.workflow_restart = workflow_restart
        self.workflow_observer = workflow_observer
        self.workflow_evidence = workflow_evidence
        self._session_started = False
        self._workflow_switched = False
        self._workflow_observation_pending = False

        if workflow_switch is not None and (workflow_restart is None or workflow_observer is None):
            raise SessionError(
                "workflow switching requires a restart factory and endpoint observer"
            )

    def start_fresh_session(self) -> str | None:
        if self.workflow_switch is not None and self._session_started and not self._workflow_switched:
            current = self.transport
            close = getattr(current, "close", None)
            if callable(close):
                close()
            assert self.workflow_restart is not None
            self.transport = self.workflow_restart(self.workflow_switch.to_workflow)
            self._workflow_switched = True
            self._workflow_observation_pending = True
        self._session_started = True
        return self.transport.start_fresh_session()

    start_fresh = start_fresh_session

    def resume_session(self, session_id: str | None = None) -> str | None:
        return self.transport.resume_session(session_id)

    resume = resume_session

    def send_message(self, message: OperatorMessage | str) -> TurnResult:
        if isinstance(message, str):
            message = OperatorMessage(message)
        result = self.transport.send_message(message)
        if not isinstance(result, TurnResult):
            raise SessionError("recorded transport returned no TurnResult")
        if self._workflow_observation_pending:
            assert self.workflow_switch is not None
            assert self.workflow_observer is not None
            observation = self.workflow_observer(message, result, self.workflow_switch.to_workflow)
            if not isinstance(observation, EndpointObservation):
                raise SessionError("workflow observer returned no EndpointObservation")
            if observation.requested_workflow != self.workflow_switch.to_workflow:
                raise SessionError("post-switch call used the wrong requested workflow")
            if observation.answered_workflow != self.workflow_switch.to_workflow:
                raise SessionError(
                    "post-switch call was served by a stale workflow: "
                    f"{observation.answered_workflow!r}"
                )
            evidence = WorkflowSwitchEvidence(
                from_workflow=self.workflow_switch.from_workflow,
                to_workflow=self.workflow_switch.to_workflow,
                answered_workflow=observation.answered_workflow,
                answered_endpoint=observation.answered_endpoint,
                stale_endpoint_rejected=True,
            )
            if self.workflow_evidence is not None:
                self.workflow_evidence(evidence, len(self.turns) + 1)
            self._workflow_observation_pending = False
        normalized = _normalized_turn_result(result, self.sandbox_home)
        if self.artifact_root is not None:
            _materialize_touched_files(normalized, self.artifact_root, source_root=self.sandbox_home)
        self.turns.append(RecordedTurn(message, normalized))
        return result

    send = send_message

    def recording(
        self,
        *,
        manifest: Mapping[str, object] | None = None,
        supervisor_facts: Mapping[str, object] | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> ReplayRecording:
        """Return a replay artifact containing observations, not just prose."""

        return ReplayRecording(tuple(self.turns), manifest, supervisor_facts, metadata or {})

    def close(self) -> None:
        """Close the wrapped live transport when it owns a process or socket."""

        close = getattr(self.transport, "close", None)
        if callable(close):
            close()


SessionTransport = Transport
ReplayTransport = ReplaySession
LiveTransport = LiveSession
RecordedSession = RecordingSession


__all__ = [
    "LiveSession",
    "LiveTransport",
    "RecordedSession",
    "RecordedTurn",
    "RecordingSession",
    "ReplayMismatch",
    "ReplayRecording",
    "ReplaySession",
    "ReplayTransport",
    "SessionError",
    "SessionTransport",
    "operator_message_from_dict",
    "operator_message_to_dict",
    "turn_result_from_dict",
    "turn_result_to_dict",
]
