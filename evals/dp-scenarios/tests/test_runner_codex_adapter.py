"""Focused contract tests for the Codex live-session bridge."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import time
from collections import deque
from io import StringIO
from types import SimpleNamespace

import pytest

from _repo_paths import REPO_ROOT

from dp_scenarios.runner.codex_adapter import (
    CODEX_SYSTEM_PROMPT,
    CODEX_FILE_CHANGE_FAILURE,
    CodexAppServerEOF,
    CodexAdapter,
    CodexAdapterError,
    _COLLAB_FAILURE_STATUSES,
    _attach_checker_skew_markers,
    _checker_skew_marker,
    _codex_timeout_detail,
    _event_debug_tail,
    _codex_timeout_failure_reason,
    _codex_provider_error,
    _codex_provider_error_reason,
    _codex_root_progress_event,
    _normalise_app_server_event,
    _review_pending_after_observations,
    _reviewer_wait_without_target,
    _turn_sandbox_policy,
    _validate_persistent_codex_config,
    _update_reviewer_deadline,
    _update_reviewer_deadline_from_events,
    _load_mcp_server,
    parse_codex_events,
    _write_result,
)
from dp_scenarios.runner import codex_adapter as codex_adapter_module
from dp_scenarios.failure_reasons import (
    CHILD_EXITED_EARLY,
    CHILD_NO_TERMINAL_RESULT,
    CODEX_PROVIDER_ERROR,
    CODEX_PROVIDER_RETRY_PENDING,
    CODEX_ROOT_TURN_NO_TERMINAL_RESULT,
    PROVIDER_SESSION_LIMIT,
)
from dp_scenarios.operator.transport import TurnResult
from dp_scenarios.runner.review_guard import REVIEW_DEADLINE_MS


def _identity(value):
    return value


def _codex_provider_error_event(
    *,
    thread_id: str = "root-thread",
    turn_id: str = "root-turn",
    will_retry: bool = False,
    codex_error_info: object = "internalError",
) -> dict[str, object]:
    return {
        "method": "error",
        "params": {
            "threadId": thread_id,
            "turnId": turn_id,
            "willRetry": will_retry,
            "error": {
                "message": "PROVIDER_PRIVATE_MESSAGE_SENTINEL",
                "codexErrorInfo": codex_error_info,
                "additionalDetails": "PROVIDER_PRIVATE_DETAILS_SENTINEL",
                "misalignment": "PROVIDER_PRIVATE_MISALIGNMENT_SENTINEL",
            },
        },
    }


def _stub_turn_collector(
    reads,
    *,
    timeout_s: float = 20.0,
    before_turn=(),
    stamp_root_identity: bool = True,
) -> CodexAdapter:
    adapter = object.__new__(CodexAdapter)
    adapter.timeout_s = timeout_s
    adapter.review_timeout_seconds = 300.0
    adapter._review_deadline_ms = 300_000.0
    adapter._thread_id = "root-thread"
    def stamp(event):
        if not stamp_root_identity or not isinstance(event, dict):
            return event
        method = event.get("method")
        if method not in {
            "error",
            "turn/started",
            "turn/completed",
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
            return event
        params = dict(event.get("params", {}))
        params.setdefault("threadId", "root-thread")
        if method in {"turn/started", "turn/completed"}:
            turn = dict(params.get("turn", {}))
            turn.setdefault("id", "root-turn")
            params["turn"] = turn
        else:
            params.setdefault("turnId", "root-turn")
        return {**event, "params": params}

    adapter._read_until_response = lambda *_args, **_kwargs: (
        {"result": {"turn": {"id": "root-turn"}}},
        [stamp(event) for event in before_turn],
    )
    adapter._is_server_request = lambda _event: False

    def read_streams(_deadline):
        event = next(reads)
        if isinstance(event, BaseException):
            raise event
        return stamp(event)

    adapter._read_streams = read_streams
    return adapter


def test_codex_provider_error_events_are_reduced_before_report_parsing() -> None:
    event = _codex_provider_error_event(
        codex_error_info={"httpStatusCode": 429}
    )

    assert _normalise_app_server_event(event) == {"type": "provider_error"}
    parsed, _observations = parse_codex_events(
        (event,),
        redact_json_rpc=_identity,
        redact_text=_identity,
        session_id="root-thread",
        root_turn_id="root-turn",
    )
    serialized = (parsed.environment_detail or "") + parsed.transcript_delta
    assert "PROVIDER_PRIVATE_MESSAGE_SENTINEL" not in serialized
    assert "PROVIDER_PRIVATE_DETAILS_SENTINEL" not in serialized
    assert "PROVIDER_PRIVATE_MISALIGNMENT_SENTINEL" not in serialized
    assert "root-thread" not in serialized
    assert "root-turn" not in serialized


def test_unknown_provider_error_variant_uses_nested_http_status() -> None:
    event = _codex_provider_error_event(
        codex_error_info={"responseTooManyFailedAttempts": {"httpStatusCode": 429}}
    )

    projected = _codex_provider_error(event)

    assert projected is not None
    assert projected["variant"] == "http_error"
    assert projected["http_status"] == 429
    assert _codex_provider_error_reason(projected) == PROVIDER_SESSION_LIMIT


@pytest.mark.parametrize(
    ("method", "params"),
    [
        (
            "turn/started",
            {"threadId": "root-thread", "turn": {"id": "root-turn"}},
        ),
        (
            "item/reasoning/textDelta",
            {"threadId": "root-thread", "turnId": "root-turn", "delta": "x"},
        ),
        (
            "item/reasoning/summaryTextDelta",
            {"threadId": "root-thread", "turnId": "root-turn", "delta": "x"},
        ),
        (
            "item/reasoning/summaryPartAdded",
            {"threadId": "root-thread", "turnId": "root-turn"},
        ),
        (
            "item/commandExecution/outputDelta",
            {"threadId": "root-thread", "turnId": "root-turn", "delta": "x"},
        ),
        (
            "item/mcpToolCall/progress",
            {"threadId": "root-thread", "turnId": "root-turn", "message": "x"},
        ),
        (
            "thread/tokenUsage/updated",
            {"threadId": "root-thread", "turnId": "root-turn"},
        ),
        (
            "turn/diff/updated",
            {"threadId": "root-thread", "turnId": "root-turn", "diff": "x"},
        ),
        (
            "turn/plan/updated",
            {"threadId": "root-thread", "turnId": "root-turn", "plan": []},
        ),
    ],
)
def test_codex_root_progress_matches_current_app_server_event_shapes(
    method: str, params: dict[str, object]
) -> None:
    assert _codex_root_progress_event(
        {"method": method, "params": params},
        thread_id="root-thread",
        turn_id="root-turn",
    )


@pytest.mark.parametrize(
    ("params", "thread_id", "turn_id"),
    [
        (
            {"threadId": "root-thread", "turn": {"id": "child-turn"}},
            "root-thread",
            "root-turn",
        ),
        (
            {"threadId": "child-thread", "turn": {"id": "root-turn"}},
            "root-thread",
            "root-turn",
        ),
        (
            {"threadId": "root-thread", "turnId": "root-turn"},
            "root-thread",
            "root-turn",
        ),
    ],
)
def test_codex_turn_started_progress_rejects_nonmatching_identity(
    params: dict[str, object], thread_id: str, turn_id: str
) -> None:
    assert not _codex_root_progress_event(
        {"method": "turn/started", "params": params},
        thread_id=thread_id,
        turn_id=turn_id,
    )


def test_codex_retryable_provider_error_is_nonterminal_but_not_ungrounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = _codex_provider_error_event(
        will_retry=True,
        codex_error_info="rateLimitExceeded",
    )
    adapter = _stub_turn_collector(iter((event, TimeoutError("stream deadline"))))
    clock = iter((0.0, 0.0, 0.1, 20.0))
    monkeypatch.setattr(
        "dp_scenarios.runner.codex_adapter.time.monotonic", lambda: next(clock)
    )

    with pytest.raises(TimeoutError) as exc_info:
        adapter._collect_turn(1, "", [])

    detail = str(exc_info.value)
    assert "codex_provider_retry_pending" in detail
    assert "variant=rateLimitExceeded" in detail
    assert "PROVIDER_PRIVATE_" not in detail
    assert "root-thread" not in detail
    assert "root-turn" not in detail
    assert (
        _codex_timeout_failure_reason(
            exc_info.value, "", root_turn_id="root-turn"
        )
        == CODEX_PROVIDER_RETRY_PENDING
    )


def test_codex_retryable_error_is_cleared_by_later_root_progress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = _codex_provider_error_event(
        will_retry=True,
        codex_error_info="rateLimitExceeded",
    )
    progress = {
        "method": "item/agentMessage/delta",
        "params": {
            "threadId": "root-thread",
            "turnId": "root-turn",
            "delta": "still working",
        },
    }
    adapter = _stub_turn_collector(
        iter((event, progress, TimeoutError("stream deadline")))
    )
    clock = iter((0.0, 0.0, 0.1, 0.2, 20.0))
    monkeypatch.setattr(
        "dp_scenarios.runner.codex_adapter.time.monotonic", lambda: next(clock)
    )

    with pytest.raises(TimeoutError) as exc_info:
        adapter._collect_turn(1, "", [])

    assert "codex_provider_retry_pending" not in str(exc_info.value)
    assert (
        _codex_timeout_failure_reason(
            exc_info.value, "", root_turn_id="root-turn"
        )
        == CODEX_ROOT_TURN_NO_TERMINAL_RESULT
    )


def test_idless_progress_does_not_clear_root_retryable_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = _codex_provider_error_event(
        will_retry=True, codex_error_info="rateLimitExceeded"
    )
    idless_progress = {
        "method": "item/agentMessage/delta",
        "params": {"delta": "possibly from a child"},
    }
    adapter = _stub_turn_collector(
        iter((error, idless_progress, TimeoutError("reviewer deadline"))),
        stamp_root_identity=False,
    )
    clock = iter((0.0, 0.0, 0.1, 0.2, 20.0))
    monkeypatch.setattr(
        "dp_scenarios.runner.codex_adapter.time.monotonic", lambda: next(clock)
    )

    with pytest.raises(TimeoutError) as exc_info:
        adapter._collect_turn(1, "", [])

    assert CODEX_PROVIDER_RETRY_PENDING in str(exc_info.value)


@pytest.mark.parametrize(
    ("timeout_s", "expected_read_deadlines", "terminal_arrives"),
    [
        (20.0, (20.0, 1.1, 1.8), True),
        (1.3, (1.3, 1.1, 1.3), False),
    ],
)
def test_terminal_provider_error_grace_tracks_root_progress_and_parent_cap(
    monkeypatch,
    timeout_s: float,
    expected_read_deadlines: tuple[float, float, float],
    terminal_arrives: bool,
) -> None:
    provider_error = _codex_provider_error_event(
        codex_error_info="internalError"
    )
    progress = {
        "method": "item/agentMessage/delta",
        "params": {
            "threadId": "root-thread",
            "turnId": "root-turn",
            "delta": "finishing teardown",
        },
    }
    terminal = {
        "method": "turn/completed",
        "params": {
            "threadId": "root-thread",
            "turn": {"id": "root-turn", "status": "completed"},
        },
    }
    timed_events = iter(
        ((0.1, provider_error), (0.8, progress), (1.5, terminal))
    )
    read_deadlines: list[float] = []
    adapter = _stub_turn_collector((), timeout_s=timeout_s)

    def read_streams(read_deadline: float) -> object:
        read_deadlines.append(read_deadline)
        event_at, event = next(timed_events)
        if event_at > read_deadline:
            raise TimeoutError("read reached supplied deadline")
        return event

    adapter._read_streams = read_streams
    clock = iter((0.0, 0.0, 0.1, 0.8, 1.5, 1.5))
    monkeypatch.setattr(
        "dp_scenarios.runner.codex_adapter.time.monotonic", lambda: next(clock)
    )

    if terminal_arrives:
        events = adapter._collect_turn(1, "", [])
        assert events[-1]["type"] == "turn.completed"
    else:
        with pytest.raises(CodexAdapterError) as exc_info:
            adapter._collect_turn(1, "", [])
        assert exc_info.value.reason == CODEX_PROVIDER_ERROR

    assert read_deadlines == pytest.approx(expected_read_deadlines)


@pytest.mark.parametrize(
    "progress_kind", ["child", "wrong_thread", "wrong_turn", "idless"]
)
def test_unrelated_progress_does_not_extend_terminal_provider_grace(
    monkeypatch, progress_kind: str
) -> None:
    provider_error = _codex_provider_error_event(codex_error_info="internalError")
    identity = {
        "child": {"threadId": "child-thread", "turnId": "child-turn"},
        "wrong_thread": {"threadId": "child-thread", "turnId": "root-turn"},
        "wrong_turn": {"threadId": "root-thread", "turnId": "child-turn"},
        "idless": {},
    }[progress_kind]
    progress = {
        "method": "item/agentMessage/delta",
        "params": {**identity, "delta": "possibly from a child"},
    }
    terminal = {
        "method": "turn/completed",
        "params": {
            "threadId": "root-thread",
            "turn": {"id": "root-turn", "status": "completed"},
        },
    }
    timed_events = iter(
        ((0.1, provider_error), (0.8, progress), (1.5, terminal))
    )
    read_deadlines: list[float] = []
    adapter = _stub_turn_collector((), timeout_s=20.0)

    def read_streams(read_deadline: float) -> object:
        read_deadlines.append(read_deadline)
        event_at, event = next(timed_events)
        if event_at > read_deadline:
            raise TimeoutError("read reached supplied deadline")
        return event

    adapter._read_streams = read_streams
    clock = iter((0.0, 0.0, 0.1, 0.8, 1.5, 1.5))
    monkeypatch.setattr(
        "dp_scenarios.runner.codex_adapter.time.monotonic", lambda: next(clock)
    )

    with pytest.raises(CodexAdapterError) as exc_info:
        adapter._collect_turn(1, "", [])

    assert exc_info.value.reason == CODEX_PROVIDER_ERROR
    assert read_deadlines == pytest.approx((20.0, 1.1, 1.1))


def test_codex_child_thread_progress_does_not_clear_root_retryable_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = _codex_provider_error_event(
        will_retry=True, codex_error_info="rateLimitExceeded"
    )
    child_progress = {
        "method": "item/agentMessage/delta",
        "params": {
            "threadId": "child-thread",
            "turnId": "child-turn",
            "delta": "child is working",
        },
    }
    adapter = _stub_turn_collector(
        iter((error, child_progress, TimeoutError("reviewer deadline")))
    )
    clock = iter((0.0, 0.0, 0.1, 0.2, 20.0))
    monkeypatch.setattr(
        "dp_scenarios.runner.codex_adapter.time.monotonic", lambda: next(clock)
    )

    with pytest.raises(TimeoutError) as exc_info:
        adapter._collect_turn(1, "", [])

    assert CODEX_PROVIDER_RETRY_PENDING in str(exc_info.value)


@pytest.mark.parametrize(
    ("failure_kind", "expected_reason"),
    [
        ("timeout", PROVIDER_SESSION_LIMIT),
        ("protocol", PROVIDER_SESSION_LIMIT),
        ("retry_after_exit", CHILD_EXITED_EARLY),
        ("safe_terminal_provider", CODEX_PROVIDER_ERROR),
    ],
)
def test_provider_diagnostics_never_copy_stderr_into_turn_result(
    failure_kind: str, expected_reason: str
) -> None:
    adapter = _stub_turn_collector(iter(()))
    adapter.start = lambda: None
    adapter._process = SimpleNamespace(pid=123)
    adapter._startup_events = []
    adapter._stderr_tail = ["HTTP status=429 PRIVATE_STDERR_SENTINEL"]
    adapter._review_pending = False
    adapter.fixture_dir = Path.cwd()
    adapter.skill_pack_root = REPO_ROOT
    adapter.model = "gpt-5.6-luna"
    adapter.effort = "high"
    adapter._next_rpc_id = lambda: 1
    adapter._write_rpc = lambda *_args, **_kwargs: None
    def fail_turn(*_args, **_kwargs):
        if failure_kind == "timeout":
            raise TimeoutError("PRIVATE_EXCEPTION_SENTINEL")
        if failure_kind == "protocol":
            raise CodexAdapterError("PRIVATE_EXCEPTION_SENTINEL")
        if failure_kind == "retry_after_exit":
            raise CodexAdapterError(
                "Codex app-server exited before a terminal result after "
                "codex_provider_retry_pending "
                "(variant=rateLimitExceeded, http_status=unknown)",
                reason=CHILD_EXITED_EARLY,
                safe_diagnostic=True,
            )
        if failure_kind == "safe_terminal_provider":
            raise CodexAdapterError(
                "Codex app-server reported a non-retryable provider error "
                "(variant=internalError, http_status=503, "
                "details_present=true, misalignment_present=false)",
                reason=CODEX_PROVIDER_ERROR,
                safe_diagnostic=True,
            )

    adapter._collect_turn = fail_turn
    adapter._terminate = lambda _process: None
    adapter._finish = lambda _events, **kwargs: kwargs

    result = adapter.send({"message": {"text": "test"}})

    assert result["failure_reason"] == expected_reason
    assert "PRIVATE_" not in result["environment_detail"]
    if failure_kind == "retry_after_exit":
        assert "variant=rateLimitExceeded" in result["environment_detail"]
    elif failure_kind == "safe_terminal_provider":
        assert "variant=internalError" in result["environment_detail"]


@pytest.mark.parametrize("will_retry", [False, True])
@pytest.mark.parametrize("arrival", ["event", "timeout"])
def test_root_provider_error_is_not_hidden_by_reviewer_deadline(
    monkeypatch: pytest.MonkeyPatch, will_retry: bool, arrival: str
) -> None:
    now = [0.0]
    adapter = _stub_turn_collector(iter(()), timeout_s=1000.0)
    adapter._review_deadline_ms = 200.0
    adapter.review_timeout_seconds = 0.2
    spawn = {
        "method": "item/started",
        "params": {
            "threadId": "root-thread",
            "turnId": "root-turn",
            "item": {
                "type": "collabAgentToolCall",
                "tool": "spawnAgent",
                "receiverThreadIds": ["child-1"],
            }
        },
    }
    provider_error = _codex_provider_error_event(
        will_retry=will_retry, codex_error_info="internalError"
    )
    if arrival == "event":
        reads = iter((spawn, provider_error))

        def read_streams(read_deadline: float):
            event = next(reads)
            if event is provider_error:
                # Like an already-buffered production event, a frame available
                # at the deadline is drained before the timeout check.
                assert read_deadline == pytest.approx(0.2)
                now[0] = read_deadline
            return event
    else:
        reads = iter((spawn, provider_error))

        def read_streams(read_deadline: float):
            try:
                event = next(reads)
            except StopIteration:
                now[0] = read_deadline
                raise TimeoutError("read reached supplied deadline")
            if event is provider_error:
                now[0] = 0.1
                return event
            now[0] = 0.0
            return event

    adapter._read_streams = read_streams
    monkeypatch.setattr(
        "dp_scenarios.runner.codex_adapter.time.monotonic", lambda: now[0]
    )

    if will_retry:
        with pytest.raises(TimeoutError) as exc_info:
            adapter._collect_turn(1, "", [])
        assert CODEX_PROVIDER_RETRY_PENDING in str(exc_info.value)
        assert (
            _codex_timeout_failure_reason(
                exc_info.value, "", root_turn_id="root-turn"
            )
            == CODEX_PROVIDER_RETRY_PENDING
        )
    else:
        with pytest.raises(CodexAdapterError) as exc_info:
            adapter._collect_turn(1, "", [])
        assert exc_info.value.reason == CODEX_PROVIDER_ERROR


def test_retryable_provider_error_does_not_relabel_protocol_failure_or_expose_stderr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider_error = _codex_provider_error_event(
        will_retry=True, codex_error_info="rateLimitExceeded"
    )
    protocol_failure = CodexAppServerEOF(
        "Codex app-server exited before returning an event: retained-stderr-sentinel",
        reason=CHILD_EXITED_EARLY,
    )
    adapter = _stub_turn_collector(iter((provider_error, protocol_failure)))
    clock = iter((0.0, 0.0, 0.1))
    monkeypatch.setattr(
        "dp_scenarios.runner.codex_adapter.time.monotonic", lambda: next(clock)
    )

    with pytest.raises(CodexAdapterError) as exc_info:
        adapter._collect_turn(1, "", [])

    assert "Codex app-server exited before a terminal result after" in str(
        exc_info.value
    )
    assert "retained-stderr-sentinel" not in str(exc_info.value)
    assert "variant=rateLimitExceeded" in str(exc_info.value)
    assert exc_info.value.reason == CHILD_EXITED_EARLY
    assert exc_info.value.reason != CODEX_PROVIDER_RETRY_PENDING
    assert exc_info.value.safe_diagnostic is True


def test_retryable_provider_error_does_not_call_malformed_frame_a_process_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider_error = _codex_provider_error_event(
        will_retry=True, codex_error_info="rateLimitExceeded"
    )
    malformed_frame = CodexAdapterError("Codex app-server emitted malformed JSON")
    adapter = _stub_turn_collector(iter((provider_error, malformed_frame)))
    clock = iter((0.0, 0.0, 0.1))
    monkeypatch.setattr(
        "dp_scenarios.runner.codex_adapter.time.monotonic", lambda: next(clock)
    )

    with pytest.raises(CodexAdapterError) as exc_info:
        adapter._collect_turn(1, "", [])

    assert exc_info.value is malformed_frame
    assert exc_info.value.reason is None
    assert "exited before a terminal result" not in str(exc_info.value)
    assert CODEX_PROVIDER_RETRY_PENDING not in str(exc_info.value)


def test_terminal_provider_error_wins_over_select_timeout_before_grace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider_error = _codex_provider_error_event(codex_error_info="internalError")
    now = [0.0]
    adapter = _stub_turn_collector(iter((provider_error,)), timeout_s=20.0)

    # First deliver the root error, then model select timing out 200 ms before
    # the provider grace expires. A known terminal cause must remain primary.
    reads = iter((provider_error,))

    def read_streams(read_deadline: float):
        try:
            event = next(reads)
        except StopIteration:
            now[0] = read_deadline - 0.2
            raise TimeoutError("select returned slightly before its deadline")
        now[0] = 0.1
        return event

    adapter._read_streams = read_streams
    monkeypatch.setattr(
        "dp_scenarios.runner.codex_adapter.time.monotonic", lambda: now[0]
    )

    with pytest.raises(CodexAdapterError) as exc_info:
        adapter._collect_turn(1, "", [])

    assert exc_info.value.reason == CODEX_PROVIDER_ERROR
    assert "non-retryable provider error" in str(exc_info.value)


def test_terminal_provider_error_still_allows_a_normal_terminal_turn_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider_error = _codex_provider_error_event(codex_error_info="internalError")
    terminal = {
        "method": "turn/completed",
        "params": {
            "turn": {
                "id": "root-turn",
                "status": "failed",
                "error": {"codexErrorInfo": "internalError"},
            }
        },
    }
    adapter = _stub_turn_collector(iter((provider_error, terminal)))
    clock = iter((0.0, 0.0, 0.1, 0.8))
    monkeypatch.setattr(
        "dp_scenarios.runner.codex_adapter.time.monotonic", lambda: next(clock)
    )

    events = adapter._collect_turn(1, "", [])

    assert events[-1]["type"] == "turn.failed"
    assert adapter._turn_failure_reason == CODEX_PROVIDER_ERROR


@pytest.mark.parametrize(
    ("prior_variant", "failed_error", "expected_reason"),
    [
        (
            "rateLimitExceeded",
            "codex_provider_error (variant=internalError)",
            PROVIDER_SESSION_LIMIT,
        ),
        ("internalError", "HTTP status=429", PROVIDER_SESSION_LIMIT),
    ],
)
def test_failed_turn_preserves_specific_provider_classification(
    monkeypatch: pytest.MonkeyPatch,
    prior_variant: str,
    failed_error: str,
    expected_reason: str,
) -> None:
    prior_error = _codex_provider_error_event(
        will_retry=True, codex_error_info=prior_variant
    )
    failed_turn = {
        "type": "turn.failed",
        "turn_id": "root-turn",
        "error": failed_error,
    }
    adapter = _stub_turn_collector(iter((prior_error, failed_turn)))
    clock = iter((0.0, 0.0, 0.1, 0.2))
    monkeypatch.setattr(
        "dp_scenarios.runner.codex_adapter.time.monotonic", lambda: next(clock)
    )

    adapter._collect_turn(1, "", [])

    assert adapter._turn_failure_reason == expected_reason


@pytest.mark.parametrize("protocol_failure_at", [0.2, 1.2])
def test_terminal_provider_error_keeps_safe_classification_on_protocol_failure(
    monkeypatch: pytest.MonkeyPatch, protocol_failure_at: float
) -> None:
    provider_error = _codex_provider_error_event(codex_error_info="internalError")
    protocol_failure = CodexAdapterError(
        "Codex app-server exited before returning an event: private stderr"
    )
    adapter = _stub_turn_collector(iter((provider_error, protocol_failure)))
    clock = iter((0.0, 0.0, 0.1, protocol_failure_at))
    monkeypatch.setattr(
        "dp_scenarios.runner.codex_adapter.time.monotonic", lambda: next(clock)
    )

    with pytest.raises(CodexAdapterError) as exc_info:
        adapter._collect_turn(1, "", [])

    assert exc_info.value.reason == CODEX_PROVIDER_ERROR
    assert "private stderr" not in str(exc_info.value)
    assert "non-retryable provider error" in str(exc_info.value)


@pytest.mark.parametrize(
    "variants",
    [
        ("usageLimitExceeded", "internalError"),
        ("internalError", "rateLimitExceeded"),
    ],
)
def test_terminal_provider_error_keeps_the_most_specific_cause(
    monkeypatch: pytest.MonkeyPatch, variants: tuple[str, str]
) -> None:
    errors = tuple(
        _codex_provider_error_event(codex_error_info=variant)
        for variant in variants
    )
    adapter = _stub_turn_collector(iter((*errors, TimeoutError("grace elapsed"))))
    clock = iter((0.0, 0.0, 0.1, 0.2, 1.3))
    monkeypatch.setattr(
        "dp_scenarios.runner.codex_adapter.time.monotonic", lambda: next(clock)
    )

    with pytest.raises(CodexAdapterError) as exc_info:
        adapter._collect_turn(1, "", [])

    assert exc_info.value.reason == PROVIDER_SESSION_LIMIT
    if variants[0] == "usageLimitExceeded":
        assert "variant=usageLimitExceeded" in str(exc_info.value)
    else:
        assert "variant=rateLimitExceeded" in str(exc_info.value)


@pytest.mark.parametrize("buffered", [False, True])
@pytest.mark.parametrize("terminal_status", ["interrupted", "failed"])
def test_provider_cause_survives_interrupted_or_failed_root_turn(
    monkeypatch: pytest.MonkeyPatch,
    buffered: bool,
    terminal_status: str,
) -> None:
    provider_error = _codex_provider_error_event(
        will_retry=True, codex_error_info="rateLimitExceeded"
    )
    terminal = {
        "method": "turn/completed",
        "params": {"turn": {"id": "root-turn", "status": terminal_status}},
    }
    reads = iter(()) if buffered else iter((provider_error, terminal))
    adapter = _stub_turn_collector(
        reads,
        before_turn=(provider_error, terminal) if buffered else (),
    )
    clock = iter((0.0, 0.0, 0.1, 0.2))
    monkeypatch.setattr(
        "dp_scenarios.runner.codex_adapter.time.monotonic", lambda: next(clock)
    )

    events = adapter._collect_turn(1, "", [])

    assert adapter._turn_failure_reason == PROVIDER_SESSION_LIMIT
    assert events[-1]["type"] == f"turn.{terminal_status}"
    parsed, _observations = parse_codex_events(
        events,
        redact_json_rpc=_identity,
        redact_text=_identity,
        session_id="root-thread",
        root_turn_id="root-turn",
    )
    detail = parsed.environment_detail or ""
    assert "codex_provider_retry_pending" in detail
    assert "variant=rateLimitExceeded" in detail
    assert "PROVIDER_PRIVATE_" not in detail


@pytest.mark.parametrize(
    ("codex_error_info", "http_status", "expected_reason"),
    [
        ("rateLimitExceeded", None, PROVIDER_SESSION_LIMIT),
        ({"httpStatusCode": 503}, None, CODEX_PROVIDER_ERROR),
        ({"httpStatusCode": 429}, None, PROVIDER_SESSION_LIMIT),
        ("futureProviderVariant", None, CODEX_PROVIDER_ERROR),
    ],
)
def test_codex_nonretryable_provider_error_ends_after_short_grace(
    monkeypatch: pytest.MonkeyPatch,
    codex_error_info: object,
    http_status: int | None,
    expected_reason: str,
) -> None:
    event = _codex_provider_error_event(codex_error_info=codex_error_info)
    if http_status is not None:
        params = event["params"]
        assert isinstance(params, dict)
        error = params["error"]
        assert isinstance(error, dict)
        error["httpStatusCode"] = http_status
    adapter = _stub_turn_collector(iter((event, TimeoutError("grace elapsed"))))
    clock = iter((0.0, 0.0, 0.1, 1.2))
    monkeypatch.setattr(
        "dp_scenarios.runner.codex_adapter.time.monotonic", lambda: next(clock)
    )

    with pytest.raises(CodexAdapterError) as exc_info:
        adapter._collect_turn(1, "", [])

    assert exc_info.value.reason == expected_reason
    assert "non-retryable provider error" in str(exc_info.value)
    assert "PROVIDER_PRIVATE_" not in str(exc_info.value)
    assert "root-thread" not in str(exc_info.value)
    assert "root-turn" not in str(exc_info.value)


@pytest.mark.parametrize(
    ("thread_id", "turn_id"),
    [("other-thread", "root-turn"), ("root-thread", "other-turn")],
)
def test_codex_child_or_mismatched_provider_error_does_not_end_root_turn(
    monkeypatch: pytest.MonkeyPatch,
    thread_id: str,
    turn_id: str,
) -> None:
    unrelated_error = _codex_provider_error_event(
        thread_id=thread_id,
        turn_id=turn_id,
    )
    terminal = {
        "method": "turn/completed",
        "params": {"turn": {"id": "root-turn", "status": "completed"}},
    }
    adapter = _stub_turn_collector(iter((unrelated_error, terminal)))
    clock = iter((0.0, 0.0, 0.1, 0.2))
    monkeypatch.setattr(
        "dp_scenarios.runner.codex_adapter.time.monotonic", lambda: next(clock)
    )

    events = adapter._collect_turn(1, "", [])
    parsed, _observations = parse_codex_events(
        events,
        redact_json_rpc=_identity,
        redact_text=_identity,
        session_id="root-thread",
        root_turn_id="root-turn",
    )

    assert parsed.terminal_result_count == 1
    assert parsed.terminal_result_subtype == "success"
    assert parsed.failure_reason is None
    assert "PROVIDER_PRIVATE_" not in (parsed.environment_detail or "")
    assert "PROVIDER_PRIVATE_" not in parsed.transcript_delta


@pytest.mark.parametrize(
    "errors",
    [
        (
            _codex_provider_error_event(codex_error_info="internalError"),
            _codex_provider_error_event(
                will_retry=True, codex_error_info="rateLimitExceeded"
            ),
        ),
        (
            _codex_provider_error_event(
                will_retry=True, codex_error_info="rateLimitExceeded"
            ),
            _codex_provider_error_event(codex_error_info="internalError"),
        ),
    ],
)
def test_codex_nonretryable_provider_error_is_sticky(
    monkeypatch: pytest.MonkeyPatch,
    errors: tuple[dict[str, object], dict[str, object]],
) -> None:
    adapter = _stub_turn_collector(
        iter((*errors, TimeoutError("grace elapsed")))
    )
    clock = iter((0.0, 0.0, 0.1, 0.2, 1.3))
    monkeypatch.setattr(
        "dp_scenarios.runner.codex_adapter.time.monotonic", lambda: next(clock)
    )

    with pytest.raises(CodexAdapterError) as exc_info:
        adapter._collect_turn(1, "", [])

    assert exc_info.value.reason == CODEX_PROVIDER_ERROR
    assert "PROVIDER_PRIVATE_" not in str(exc_info.value)


def test_codex_terminal_completion_at_deadline_wins_over_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    terminal = {
        "method": "turn/completed",
        "params": {"turn": {"id": "root-turn", "status": "completed"}},
    }
    adapter = _stub_turn_collector(iter((terminal,)), timeout_s=20.0)
    clock = iter((0.0, 0.0, 20.0))
    monkeypatch.setattr(
        "dp_scenarios.runner.codex_adapter.time.monotonic", lambda: next(clock)
    )

    events = adapter._collect_turn(1, "", [])
    parsed, _observations = parse_codex_events(
        events,
        redact_json_rpc=_identity,
        redact_text=_identity,
        session_id="root-thread",
        root_turn_id="root-turn",
    )

    assert parsed.terminal_result_count == 1
    assert parsed.terminal_result_subtype == "success"


def test_nonretryable_root_provider_error_survives_completed_terminal_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider_error = _codex_provider_error_event(
        will_retry=False, codex_error_info="internalError"
    )
    terminal = {
        "method": "turn/completed",
        "params": {
            "threadId": "root-thread",
            "turn": {"id": "root-turn", "status": "completed"},
        },
    }
    adapter = _stub_turn_collector(iter((provider_error, terminal)))
    clock = iter((0.0, 0.0, 0.1, 0.2))
    monkeypatch.setattr(
        "dp_scenarios.runner.codex_adapter.time.monotonic", lambda: next(clock)
    )

    events = adapter._collect_turn(1, "", [])

    assert events[-1]["type"] == "turn.completed"
    assert adapter._turn_failure_reason == CODEX_PROVIDER_ERROR


def test_stale_wait_does_not_clear_deadline_for_a_new_idless_reviewer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_spawn = {
        "method": "item/completed",
        "params": {
            "item": {
                "type": "collabAgentToolCall",
                "id": "spawn-first",
                "tool": "spawnAgent",
                "status": "completed",
                "receiverThreadIds": ["child-1"],
                "agentsStates": {"child-1": {"status": "running"}},
            }
        },
    }
    first_wait = {
        "method": "item/completed",
        "params": {
            "item": {
                "type": "collabAgentToolCall",
                "id": "wait-first",
                "tool": "wait",
                "status": "completed",
                "receiverThreadIds": ["child-1"],
                "agentsStates": {
                    "child-1": {"status": "completed", "message": "first claims"}
                },
            }
        },
    }
    second_spawn = {
        "method": "item/completed",
        "params": {
            "item": {
                "type": "collabAgentToolCall",
                "id": "spawn-second",
                "tool": "spawnAgent",
                "status": "completed",
                "agentsStates": {"pending": {"status": "pendingInit"}},
            }
        },
    }
    stale_wait_started = {
        "method": "item/started",
        "params": {
            "item": {
                "type": "collabAgentToolCall",
                "id": "stale-wait-started",
                "tool": "wait",
                "receiverThreadIds": ["child-1"],
            }
        },
    }
    stale_wait_completed = {
        "method": "item/completed",
        "params": {
            "item": {
                "type": "collabAgentToolCall",
                "id": "stale-wait-completed",
                "tool": "wait",
                "status": "completed",
                "receiverThreadIds": ["child-1"],
                "agentsStates": {
                    "child-1": {"status": "completed", "message": "stale claims"}
                },
            }
        },
    }
    adapter = _stub_turn_collector(
        iter((TimeoutError("reviewer deadline"),)),
        timeout_s=10.0,
        before_turn=(
            first_spawn,
            first_wait,
            second_spawn,
            stale_wait_started,
            stale_wait_completed,
        ),
    )
    adapter._review_deadline_ms = 200.0
    adapter.review_timeout_seconds = 0.2
    now = [0.0]
    read_streams = adapter._read_streams

    def time_out_after_stale_wait(deadline: float):
        try:
            return read_streams(deadline)
        except TimeoutError:
            now[0] = 1.0
            raise

    adapter._read_streams = time_out_after_stale_wait
    monkeypatch.setattr(
        "dp_scenarios.runner.codex_adapter.time.monotonic", lambda: now[0]
    )

    with pytest.raises(TimeoutError) as exc_info:
        adapter._collect_turn(1, "", [])

    detail = str(exc_info.value)
    assert "reviewer child did not complete" in detail
    assert "reviewer=phase=waiting" in detail
    assert "deadline_at=+0.2s" in detail
    assert "deadline=cleared" not in detail


def test_codex_failed_turn_error_is_sanitized_and_uses_prior_provider_classification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider_error = _codex_provider_error_event(
        codex_error_info="rateLimitExceeded"
    )
    failed_turn = {
        "method": "turn/completed",
        "params": {
            "turn": {
                "id": "root-turn",
                "status": "failed",
                "error": {
                    "message": "TURN_PRIVATE_MESSAGE_SENTINEL",
                    "additionalDetails": "TURN_PRIVATE_DETAILS_SENTINEL",
                },
            }
        },
    }
    adapter = _stub_turn_collector(iter((provider_error, failed_turn)))
    clock = iter((0.0, 0.0, 0.1, 0.2))
    monkeypatch.setattr(
        "dp_scenarios.runner.codex_adapter.time.monotonic", lambda: next(clock)
    )

    events = adapter._collect_turn(1, "", [])
    parsed, _observations = parse_codex_events(
        events,
        redact_json_rpc=_identity,
        redact_text=_identity,
        session_id="root-thread",
        root_turn_id="root-turn",
    )

    assert adapter._turn_failure_reason == PROVIDER_SESSION_LIMIT
    assert parsed.terminal_result_count == 1
    assert "TURN_PRIVATE_" not in (parsed.environment_detail or "")
    assert "TURN_PRIVATE_" not in parsed.transcript_delta


def test_codex_system_prompt_preserves_workflow_v2_action_discipline() -> None:
    assert "treat every supervisor response as authoritative" in CODEX_SYSTEM_PROMPT
    assert "Do not use Bash, curl, WebFetch" in CODEX_SYSTEM_PROMPT
    assert "source observations must come from the" in CODEX_SYSTEM_PROMPT
    assert "If a shell command" in CODEX_SYSTEM_PROMPT and "rejected" in CODEX_SYSTEM_PROMPT
    assert "Complete closure authoring in this parent" in CODEX_SYSTEM_PROMPT
    assert "do not use destructive" in CODEX_SYSTEM_PROMPT
    assert "Do not use `spawnAgent` for closure authoring" in CODEX_SYSTEM_PROMPT


def test_codex_adapter_result_identifies_its_backend(capsys: pytest.CaptureFixture[str]) -> None:
    _write_result(TurnResult(agent_message="ready"), backend="codex")
    payload = json.loads(capsys.readouterr().out)
    assert payload["result"]["backend"] == "codex"
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
    assert "never use `sendInput`, `resumeAgent`, or `closeAgent`" in CODEX_SYSTEM_PROMPT
    assert "wait` reports the child as completed but returns no non-empty message" in CODEX_SYSTEM_PROMPT
    assert "issue `wait` once more with the same `targets` array" in CODEX_SYSTEM_PROMPT
    assert "missing child claims" in CODEX_SYSTEM_PROMPT
    assert "captured inputs are immutable" in CODEX_SYSTEM_PROMPT
    assert "only a clear report authorizes" in CODEX_SYSTEM_PROMPT
    assert "end that turn with a direct question" in CODEX_SYSTEM_PROMPT
    assert "specific authorization" in CODEX_SYSTEM_PROMPT
    assert "end the" in CODEX_SYSTEM_PROMPT
    assert "same turn" in CODEX_SYSTEM_PROMPT
    assert "immediately using the returned receiver thread id" in CODEX_SYSTEM_PROMPT
    assert '`wait` as `{"targets":["<exact non-empty receiver thread id>"]}`' in " ".join(CODEX_SYSTEM_PROMPT.split())
    assert "use the `targets`" in CODEX_SYSTEM_PROMPT
    assert "never an empty array" in CODEX_SYSTEM_PROMPT
    assert "`wait` is the only follow-up" in CODEX_SYSTEM_PROMPT
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
    assert "exact `path` values returned by the reader verbatim" in CODEX_SYSTEM_PROMPT


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


def test_codex_timeout_detail_names_fired_deadline_and_parent_limit() -> None:
    detail = _codex_timeout_detail(
        TimeoutError(
            "Codex reviewer child did not complete before the "
            "300.0-second reviewer deadline"
        ),
        parent_turn_limit_s=810.0,
    )
    assert "300.0-second reviewer deadline" in detail
    assert "parent_turn_limit=810.0s" in detail
    assert "did not complete the turn within 810.0s" not in detail


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


def test_codex_reviewer_deadline_clears_after_matching_wait_returns_result() -> None:
    receiver_ids = {"child-1"}
    deadline = 310.0
    wait = {
        "type": "item.completed",
        "item": {
            "type": "collab_agent_tool_call",
            "tool": "wait",
            "status": "completed",
            "receiverThreadIds": ["child-1"],
            "agentsStates": {
                "child-1": {"status": "completed", "message": "review result"}
            },
        },
    }

    remaining_ids, remaining_deadline = _update_reviewer_deadline(
        wait, receiver_ids, deadline, now=100.0
    )

    assert remaining_ids == set()
    assert remaining_deadline is None


def test_codex_reviewer_deadline_stays_armed_for_wait_without_result() -> None:
    receiver_ids = {"child-1"}
    deadline = 310.0
    wait = {
        "type": "item.completed",
        "item": {
            "type": "collab_agent_tool_call",
            "tool": "wait",
            "status": "completed",
            "receiverThreadIds": ["child-1"],
            "agentsStates": {"child-1": {"status": "completed"}},
        },
    }

    remaining_ids, remaining_deadline = _update_reviewer_deadline(
        wait, receiver_ids, deadline, now=100.0
    )

    assert remaining_ids == receiver_ids
    assert remaining_deadline == deadline


@pytest.mark.parametrize(
    "completed_state",
    [
        {"status": "failed"},
        {"status": "completed", "message": "review result"},
    ],
)
def test_codex_reviewer_wait_completes_only_terminal_children(
    completed_state: dict[str, str],
) -> None:
    receiver_ids = {"child-1", "child-2"}
    deadline = 310.0
    wait = {
        "type": "item.completed",
        "item": {
            "type": "collab_agent_tool_call",
            "tool": "wait",
            "status": "completed",
            "receiverThreadIds": ["child-1", "child-2"],
            "agentsStates": {
                "child-1": completed_state,
                "child-2": {"status": "running", "message": "still working"},
            },
        },
    }

    remaining_ids, remaining_deadline = _update_reviewer_deadline(
        wait, receiver_ids, deadline, now=100.0
    )

    assert remaining_ids == {"child-2"}
    assert remaining_deadline == deadline

    second_wait = {
        "type": "item.completed",
        "item": {
            "type": "collab_agent_tool_call",
            "tool": "wait",
            "status": "completed",
            "receiverThreadIds": ["child-2"],
            "agentsStates": {
                "child-2": {"status": "completed", "message": "second result"}
            },
        },
    }
    remaining_ids, remaining_deadline = _update_reviewer_deadline(
        second_wait, remaining_ids, remaining_deadline, now=150.0
    )

    assert remaining_ids == set()
    assert remaining_deadline is None


def test_codex_reviewer_deadline_binds_a_single_idless_spawn_to_its_wait() -> None:
    spawn = {
        "method": "item/started",
        "params": {
            "item": {
                "type": "collabAgentToolCall",
                "id": "spawn-idless",
                "tool": "spawnAgent",
                "status": "inProgress",
                "agentsStates": {"pending": {"status": "pendingInit"}},
            }
        },
    }
    wait = {
        "method": "item/completed",
        "params": {
            "item": {
                "type": "collabAgentToolCall",
                "id": "wait-one",
                "tool": "wait",
                "status": "completed",
                "receiverThreadIds": ["child-1"],
                "agentsStates": {
                    "child-1": {"status": "completed", "message": "claims"}
                },
            }
        },
    }
    terminal = {
        "method": "turn/completed",
        "params": {"turn": {"id": "root-turn", "status": "completed"}},
    }
    adapter = _stub_turn_collector(iter((spawn, wait, terminal)))

    events = adapter._collect_turn(1, "", [])
    result, _ = parse_codex_events(
        events,
        redact_json_rpc=_identity,
        redact_text=_identity,
        session_id="root-thread",
        root_turn_id="root-turn",
    )

    assert result.terminal_result_subtype == "success"
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].result == {"is_error": False, "content": ["claims"]}


def test_codex_reviewer_respawn_gets_fresh_diagnostic_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spawn_one = {
        "method": "item/started",
        "params": {
            "item": {
                "type": "collabAgentToolCall",
                "tool": "spawnAgent",
                "receiverThreadIds": ["child-1"],
            }
        },
    }
    wait_one = {
        "method": "item/completed",
        "params": {
            "item": {
                "type": "collabAgentToolCall",
                "tool": "wait",
                "status": "completed",
                "receiverThreadIds": ["child-1"],
                "agentsStates": {
                    "child-1": {"status": "completed", "message": "first result"}
                },
            }
        },
    }
    spawn_two = {
        "method": "item/started",
        "params": {
            "item": {
                "type": "collabAgentToolCall",
                "tool": "spawnAgent",
                "receiverThreadIds": ["child-2"],
            }
        },
    }
    adapter = _stub_turn_collector(
        iter((spawn_one, wait_one, spawn_two, TimeoutError("reviewer deadline"))),
        timeout_s=100.0,
    )
    adapter._review_deadline_ms = 1_000.0
    adapter.review_timeout_seconds = 1.0
    clock = iter((0.0, 0.0, 0.1, 0.2, 0.3, 1.4, 1.4))
    monkeypatch.setattr(
        "dp_scenarios.runner.codex_adapter.time.monotonic", lambda: next(clock)
    )

    with pytest.raises(TimeoutError) as exc_info:
        adapter._collect_turn(1, "", [])

    assert "reviewer=phase=spawned" in str(exc_info.value)
    assert "spawn_at=+0.3s" in str(exc_info.value)
    assert "complete_at=" not in str(exc_info.value)


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
    now = [0.0]

    def read_streams(read_deadline):
        value = next(reads)
        if isinstance(value, BaseException):
            now[0] = read_deadline
            raise value
        return value

    adapter._read_streams = read_streams
    monkeypatch.setattr(
        "dp_scenarios.runner.codex_adapter.time.monotonic", lambda: now[0]
    )

    with pytest.raises(TimeoutError, match="reviewer deadline"):
        adapter._collect_turn(1, "", [])


def test_codex_pending_init_snapshot_keeps_the_configured_reviewer_deadline(monkeypatch) -> None:
    adapter = object.__new__(CodexAdapter)
    adapter.timeout_s = 1000.0
    spawn_started = {
        "method": "item/started",
        "params": {
            "item": {
                "type": "collabAgentToolCall",
                "tool": "spawnAgent",
                "receiverThreadIds": ["child-1"],
                "agentsStates": {"child-1": {"status": "pendingInit"}},
            }
        },
    }
    adapter._read_until_response = lambda *_args, **_kwargs: (
        {"result": {"turn": {"id": "root-turn"}}},
        [spawn_started],
    )
    adapter._is_server_request = lambda _event: False

    now = [0.0]

    def read_streams(read_deadline):
        now[0] = read_deadline
        raise TimeoutError("stream deadline")

    adapter._read_streams = read_streams
    monkeypatch.setattr(
        "dp_scenarios.runner.codex_adapter.time.monotonic", lambda: now[0]
    )

    with pytest.raises(TimeoutError, match="reviewer deadline"):
        adapter._collect_turn(1, "", [])


def test_codex_reviewer_timeout_reports_target_match_and_safe_child_state(monkeypatch) -> None:
    adapter = object.__new__(CodexAdapter)
    adapter.timeout_s = 1000.0
    adapter._review_deadline_ms = 300_000.0
    adapter.review_timeout_seconds = 300.0
    adapter._read_until_response = lambda *_args, **_kwargs: (
        {"result": {"turn": {"id": "root-turn"}}},
        [],
    )
    adapter._is_server_request = lambda _event: False
    spawn = {
        "method": "item/started",
        "params": {
            "item": {
                "type": "collabAgentToolCall",
                "tool": "spawnAgent",
                "receiverThreadIds": ["child-private-id"],
                "agentsStates": {"child-private-id": {"status": "pendingInit"}},
            }
        },
    }
    wait = {
        "method": "item/started",
        "params": {
            "item": {
                "type": "collabAgentToolCall",
                "tool": "wait",
                "receiverThreadIds": ["unrelated-private-id"],
                "agentsStates": {"child-private-id": {"status": "pendingInit"}},
            }
        },
    }
    reads = iter((spawn, wait, TimeoutError("stream deadline")))

    def read_streams(_deadline):
        event = next(reads)
        if isinstance(event, BaseException):
            raise event
        return event

    adapter._read_streams = read_streams
    clock = iter((0.0, 0.0, 1.0, 2.0, 301.0))
    monkeypatch.setattr(
        "dp_scenarios.runner.codex_adapter.time.monotonic", lambda: next(clock)
    )

    with pytest.raises(TimeoutError) as exc_info:
        adapter._collect_turn(1, "", [])

    detail = str(exc_info.value)
    assert "wait_calls=1" in detail
    assert "wait_target=mismatched" in detail
    assert "child_status=pendingInit" in detail
    assert "child_started=false" in detail
    assert "child-private-id" not in detail
    assert "unrelated-private-id" not in detail


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
    clock = iter((0.0, 0.0, 2.0))
    monkeypatch.setattr(
        "dp_scenarios.runner.codex_adapter.time.monotonic", lambda: next(clock)
    )

    with pytest.raises(TimeoutError, match="turn deadline"):
        adapter._collect_turn(1, "", [])


def test_codex_completed_reviewer_can_continue_past_review_deadline(monkeypatch) -> None:
    adapter = object.__new__(CodexAdapter)
    adapter.timeout_s = 1000.0
    adapter._review_deadline_ms = 300_000.0
    adapter.review_timeout_seconds = 300.0
    adapter._read_until_response = lambda *_args, **_kwargs: (
        {"result": {"turn": {"id": "root-turn"}}},
        [],
    )
    adapter._is_server_request = lambda _event: False
    spawn = {
        "method": "item/started",
        "params": {
            "item": {
                "type": "collabAgentToolCall",
                "tool": "spawnAgent",
                "receiverThreadIds": ["child-1"],
            }
        },
    }
    wait = {
        "method": "item/completed",
        "params": {
            "item": {
                "type": "collabAgentToolCall",
                "tool": "wait",
                "status": "completed",
                "receiverThreadIds": ["child-1"],
                "agentsStates": {
                    "child-1": {"status": "completed", "message": "review result"}
                },
            }
        },
    }
    late_progress = {"method": "thread/tokenUsage/updated", "params": {}}
    terminal = {
        "method": "turn/completed",
        "params": {"turn": {"id": "root-turn", "status": "completed"}},
    }
    reads = iter((spawn, wait, late_progress, terminal))
    adapter._read_streams = lambda _deadline: next(reads)
    clock = iter((0.0, 0.0, 0.0, 100.0, 400.0, 450.0))
    monkeypatch.setattr(
        "dp_scenarios.runner.codex_adapter.time.monotonic", lambda: next(clock)
    )

    events = adapter._collect_turn(1, "", [])

    assert events[-1]["type"] == "turn.completed"
    assert events[-1]["turn_id"] == "root-turn"


def test_codex_root_timeout_reports_timing_and_reviewer_phase(monkeypatch) -> None:
    adapter = object.__new__(CodexAdapter)
    adapter.timeout_s = 810.0
    adapter._review_deadline_ms = 300_000.0
    adapter.review_timeout_seconds = 300.0
    adapter._read_until_response = lambda *_args, **_kwargs: (
        {"result": {"turn": {"id": "root-turn"}}},
        [],
    )
    adapter._is_server_request = lambda _event: False
    spawn = {
        "method": "item/started",
        "params": {
            "item": {
                "type": "collabAgentToolCall",
                "tool": "spawnAgent",
                "receiverThreadIds": ["child-1"],
            }
        },
    }
    wait_started = {
        "method": "item/started",
        "params": {
            "item": {
                "type": "collabAgentToolCall",
                "tool": "wait",
                "receiverThreadIds": ["child-1"],
            }
        },
    }
    wait_completed = {
        "method": "item/completed",
        "params": {
            "item": {
                "type": "collabAgentToolCall",
                "tool": "wait",
                "status": "completed",
                "receiverThreadIds": ["child-1"],
                "agentsStates": {
                    "child-1": {"status": "completed", "message": "review result"}
                },
            }
        },
    }
    reset = {
        "method": "item/completed",
        "params": {
            "item": {
                "type": "mcpToolCall",
                "server": "nxd-desktop",
                "tool": "reset_workflow",
                "status": "completed",
            }
        },
    }
    reads = iter((spawn, wait_started, wait_completed, reset, TimeoutError("stream deadline")))
    def read_streams(_deadline):
        event = next(reads)
        if isinstance(event, BaseException):
            raise event
        return event

    adapter._read_streams = read_streams
    clock = iter((0.0, 0.0, 520.0, 650.0, 700.0, 720.0, 810.0))
    monkeypatch.setattr(
        "dp_scenarios.runner.codex_adapter.time.monotonic", lambda: next(clock)
    )

    with pytest.raises(TimeoutError) as exc_info:
        adapter._collect_turn(1, "", [])

    detail = str(exc_info.value)
    assert "turn_elapsed=810.0s" in detail
    assert "idle_for=90.0s" in detail
    assert "reset_workflow=completed@+720.0s" in detail
    assert "reviewer=phase=completed" in detail
    assert "spawn_at=+520.0s" in detail
    assert "wait_at=+650.0s" in detail
    assert "complete_at=+700.0s" in detail
    assert "result_ready=true" in detail
    assert "deadline=cleared" in detail
    assert "wait_calls=1" in detail
    assert "wait_target=matched" in detail
    assert "child_status=completed" in detail
    assert "child_started=true" in detail


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
            {"type": "thread.started", "thread_id": "child-thread"},
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


def test_codex_capture_gets_checker_marker_without_calling_review_reader(tmp_path: Path) -> None:
    pack = tmp_path / "pack"
    checker = pack / "src" / "nxd-run-job-loop" / "scripts" / "self_check.py"
    checker.parent.mkdir(parents=True)
    checker.write_bytes(b"trusted checker bytes\n")
    supervisor = tmp_path / "supervisor"
    capture = supervisor / "captures" / "workflow-a" / "review"
    capture.mkdir(parents=True)
    (capture / "self_check.py").write_bytes(checker.read_bytes())
    arguments = {"workflow": "workflow-a", "action": {"type": "capture"}}
    events = [
        {
            "type": "item.started",
            "item": {
                "id": "capture-call",
                "type": "mcp_tool_call",
                "server": "nxd-desktop",
                "tool": "advance_workflow",
                "arguments": arguments,
            },
        },
        {
            "type": "item.completed",
            "item": {
                "id": "capture-call",
                "type": "mcp_tool_call",
                "server": "nxd-desktop",
                "tool": "advance_workflow",
                "arguments": arguments,
                "result": {
                    "structured_content": {
                        "requirements": [
                            {
                                "id": "review",
                                "status": "pending",
                                "review_input": {
                                    "retained_capture_root": str(capture),
                                    "retained_blueprint_path": str(capture / "blueprint.md"),
                                },
                            }
                        ]
                    }
                },
            },
        },
        {"type": "turn.completed"},
    ]

    parsed, observations = parse_codex_events(
        events,
        redact_json_rpc=_identity,
        redact_text=lambda value: value,
        session_id="thread-a",
    )
    assert parsed.tool_calls[0].observation is None
    assert not any(call.name.endswith("read_review_input") for call in parsed.tool_calls)
    marked = _attach_checker_skew_markers(
        parsed.tool_calls,
        observations,
        skill_pack_root=pack,
        supervisor_data_dir=supervisor,
    )
    assert marked[0].observation == {
        "kind": "checker_skew",
        "schema": "nxd-checker-skew-v1",
        "status": "match",
        "source_sha256": hashlib.sha256(checker.read_bytes()).hexdigest(),
        "retained_sha256": hashlib.sha256(checker.read_bytes()).hexdigest(),
    }
    assert str(capture) not in json.dumps(marked[0].observation)
    assert "trusted checker bytes" not in json.dumps(marked[0].observation)


def test_checker_skew_accepts_macos_data_dir_symlink_spelling(tmp_path: Path) -> None:
    pack = tmp_path / "pack"
    checker = pack / "src" / "nxd-run-job-loop" / "scripts" / "self_check.py"
    checker.parent.mkdir(parents=True)
    checker.write_bytes(b"trusted checker bytes\n")
    supervisor = tmp_path / "supervisor"
    digest = "a" * 64
    capture = supervisor / "captures" / "sha256" / digest
    capture.mkdir(parents=True)
    (capture / "self_check.py").write_bytes(checker.read_bytes())
    supervisor_alias = tmp_path / "supervisor-alias"
    supervisor_alias.symlink_to(supervisor, target_is_directory=True)
    observation = {
        "tool": "advance_workflow",
        "arguments": {"action": {"type": "capture"}},
        "result": {
            "requirements": [
                {
                    "id": "review",
                    "review_input": {
                        "retained_capture_root": str(
                            supervisor_alias / "captures" / "sha256" / digest
                        )
                    },
                }
            ]
        },
        "is_error": False,
        "answered": True,
    }

    marker = _checker_skew_marker(
        observation,
        skill_pack_root=pack,
        supervisor_data_dir=supervisor,
    )

    assert marker is not None
    assert marker["status"] == "match"


@pytest.mark.parametrize(
    ("root_kind", "source_kind", "expected_status"),
    [
        ("different", "regular", "mismatch"),
        ("missing", "regular", "unreadable"),
        ("symlink", "regular", "unreadable"),
        ("symlink-directory", "regular", "unreadable"),
        ("fifo", "regular", "unreadable"),
        ("regular", "symlink", "unreadable"),
        ("outside", "regular", "malformed"),
        ("valid-suffix-outside", "regular", "malformed"),
    ],
)
def test_checker_skew_fails_closed_for_bad_sources_and_capture_paths(
    tmp_path: Path, root_kind: str, source_kind: str, expected_status: str
) -> None:
    pack = tmp_path / "pack"
    source = pack / "src" / "nxd-run-job-loop" / "scripts" / "self_check.py"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"trusted\n")
    supervisor = tmp_path / "supervisor"
    captures = supervisor / "captures"
    capture = captures / "workflow"
    capture.mkdir(parents=True)
    retained = capture / "self_check.py"
    retained.write_bytes(b"trusted\n")
    root_value = str(capture)
    if root_kind == "different":
        retained.write_bytes(b"changed\n")
    elif root_kind == "missing":
        retained.unlink()
    elif root_kind == "symlink":
        retained.unlink()
        outside_file = tmp_path / "outside-checker.py"
        outside_file.write_bytes(b"trusted\n")
        retained.symlink_to(outside_file)
    elif root_kind == "symlink-directory":
        alias = captures / "workflow-alias"
        alias.symlink_to(capture, target_is_directory=True)
        root_value = str(alias)
    elif root_kind == "fifo":
        retained.unlink()
        os.mkfifo(retained)
    elif root_kind == "outside":
        root_value = str(tmp_path / "outside-capture")
    elif root_kind == "valid-suffix-outside":
        outside_capture = (
            tmp_path
            / "outside-supervisor"
            / "captures"
            / "sha256"
            / ("b" * 64)
        )
        outside_capture.mkdir(parents=True)
        root_value = str(outside_capture)
    if source_kind == "symlink":
        source.unlink()
        outside_source = tmp_path / "trusted-checker.py"
        outside_source.write_bytes(b"trusted\n")
        source.symlink_to(outside_source)
    observation = {
        "tool": "advance_workflow",
        "arguments": {"action": {"type": "capture"}},
        "result": {
            "requirements": [
                {"id": "review", "review_input": {"retained_capture_root": root_value}}
            ]
        },
        "is_error": False,
        "answered": True,
    }

    marker = _checker_skew_marker(
        observation,
        skill_pack_root=pack,
        supervisor_data_dir=supervisor,
    )
    assert marker is not None
    assert marker["status"] == expected_status
    if expected_status in {"unreadable", "malformed"}:
        assert "source_sha256" not in marker
        assert "retained_sha256" not in marker


def test_checker_skew_over_cap_is_unreadable(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "dp_scenarios.runner.codex_adapter._CHECKER_SKEW_MAX_BYTES", 4
    )
    pack = tmp_path / "pack"
    source = pack / "src" / "nxd-run-job-loop" / "scripts" / "self_check.py"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"ok")
    supervisor = tmp_path / "supervisor"
    capture = supervisor / "captures" / "workflow"
    capture.mkdir(parents=True)
    (capture / "self_check.py").write_bytes(b"too long")
    observation = {
        "tool": "advance_workflow",
        "arguments": {"action": {"type": "capture"}},
        "result": {
            "requirements": [
                {"id": "review", "review_input": {"retained_capture_root": str(capture)}}
            ]
        },
        "is_error": False,
        "answered": True,
    }

    marker = _checker_skew_marker(
        observation,
        skill_pack_root=pack,
        supervisor_data_dir=supervisor,
    )
    assert marker == {
        "kind": "checker_skew",
        "schema": "nxd-checker-skew-v1",
        "status": "unreadable",
    }


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
                "params": {
                    "threadId": "child-thread",
                    "turn": {"id": "child-turn", "status": "completed"},
                },
            },
            {
                "method": "turn/completed",
                "params": {
                    "threadId": "thread-1",
                    "turn": {"id": "root-turn", "status": "completed"},
                },
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


def test_parse_codex_events_ignores_child_thread_items_even_with_active_root_turn() -> None:
    child_tool_call = {
        "method": "item/completed",
        "params": {
            "threadId": "child-thread",
            "turnId": "child-turn",
            "item": {
                "type": "mcpToolCall",
                "id": "child-call",
                "server": "nxd-desktop",
                "tool": "advance_workflow",
                "status": "completed",
                "arguments": {"workflow": "wrong-thread"},
                "result": {"structuredContent": {"admission": {"run_id": "fake"}}},
            },
        },
    }
    child_message = {
        "method": "item/completed",
        "params": {
            "threadId": "child-thread",
            "turnId": "child-turn",
            "item": {"type": "agentMessage", "text": "child output"},
        },
    }
    root_message = {
        "method": "item/completed",
        "params": {
            "threadId": "root-thread",
            "turnId": "root-turn",
            "item": {"type": "agentMessage", "text": "root output"},
        },
    }
    root_terminal = {
        "method": "turn/completed",
        "params": {
            "threadId": "root-thread",
            "turn": {"id": "root-turn", "status": "completed"},
        },
    }

    result, observations = parse_codex_events(
        (child_tool_call, child_message, root_message, root_terminal),
        redact_json_rpc=_identity,
        redact_text=_identity,
        session_id="root-thread",
        root_turn_id="root-turn",
    )

    assert observations == []
    assert result.tool_calls == ()
    assert result.agent_message == "root output"
    assert "child output" not in result.transcript_delta
    assert result.terminal_result_count == 1


def test_turn_failed_without_error_does_not_emit_json_null() -> None:
    result, _observations = parse_codex_events(
        ({"type": "turn.failed", "turn_id": "root-turn", "error": None},),
        redact_json_rpc=_identity,
        redact_text=_identity,
        session_id="root-thread",
        root_turn_id="root-turn",
    )

    assert result.environment_wedged is True
    assert result.environment_detail is None
    assert result.failure_reason is None


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


@pytest.mark.parametrize(
    ("aggregate_status", "child_b_status", "later_status"),
    [
        ("failed", "running", "completed"),
        ("failed", "running", "failed"),
        ("failed", "failed", None),
    ],
)
def test_mixed_wait_results_stay_scoped_per_child_through_collect_and_parse(
    aggregate_status: str,
    child_b_status: str,
    later_status: str | None,
) -> None:
    events = [
        {
            "method": "item/completed",
            "params": {
                "item": {
                    "type": "collabAgentToolCall",
                    "id": "spawn-a",
                    "tool": "spawnAgent",
                    "prompt": "review child A",
                    "status": "completed",
                    "receiverThreadIds": ["child-a"],
                    "agentsStates": {
                        "child-a": {"status": "running", "message": None}
                    },
                }
            },
        },
        {
            "method": "item/completed",
            "params": {
                "item": {
                    "type": "collabAgentToolCall",
                    "id": "spawn-b",
                    "tool": "spawnAgent",
                    "prompt": "review child B",
                    "status": "completed",
                    "receiverThreadIds": ["child-b"],
                    "agentsStates": {
                        "child-b": {"status": "running", "message": None}
                    },
                }
            },
        },
        {
            "method": "item/completed",
            "params": {
                "item": {
                    "type": "collabAgentToolCall",
                    "id": "wait-a-b",
                    "tool": "wait",
                    "status": aggregate_status,
                    "receiverThreadIds": ["child-a", "child-b"],
                    "agentsStates": {
                        "child-a": {"status": "completed", "message": "claims A"},
                        "child-b": {
                            "status": child_b_status,
                            "message": "failure B" if child_b_status == "failed" else None,
                        },
                    },
                }
            },
        },
    ]
    if later_status is not None:
        events.append(
            {
                "method": "item/completed",
                "params": {
                    "item": {
                        "type": "collabAgentToolCall",
                        "id": "wait-b",
                        "tool": "wait",
                        "status": "completed",
                        "receiverThreadIds": ["child-b"],
                        "agentsStates": {
                            "child-b": {
                                "status": later_status,
                                "message": "claims B" if later_status == "completed" else "failure B",
                            }
                        },
                    }
                },
            }
        )
    events.append(
        {
            "method": "turn/completed",
            "params": {"turn": {"id": "root-turn", "status": "completed"}},
        }
    )
    adapter = _stub_turn_collector(iter(()), before_turn=events)
    collected = adapter._collect_turn(1, "", [])

    result, _ = parse_codex_events(
        collected,
        redact_json_rpc=_identity,
        redact_text=_identity,
        session_id="thread-1",
    )

    assert len(result.tool_calls) == 2
    assert result.tool_calls[0].result == {"is_error": False, "content": ["claims A"]}
    if child_b_status == "failed":
        assert result.tool_calls[1].result == {
            "is_error": True,
            "content": ["failure B"],
        }
    elif later_status == "completed":
        assert result.tool_calls[1].result == {
            "is_error": False,
            "content": ["claims B"],
        }
    elif child_b_status == "failed" or later_status == "failed":
        assert result.tool_calls[1].result == {
            "is_error": True,
            "content": ["failure B"],
        }


def test_mixed_wait_binds_one_fresh_target_to_one_idless_spawn() -> None:
    events = [
        {
            "method": "item/completed",
            "params": {
                "item": {
                    "type": "collabAgentToolCall",
                    "id": "spawn-known",
                    "tool": "spawnAgent",
                    "prompt": "review A",
                    "status": "completed",
                    "receiverThreadIds": ["child-a"],
                    "agentsStates": {"child-a": {"status": "running"}},
                }
            },
        },
        {
            "method": "item/completed",
            "params": {
                "item": {
                    "type": "collabAgentToolCall",
                    "id": "spawn-idless",
                    "tool": "spawnAgent",
                    "prompt": "review B",
                    "status": "completed",
                    "agentsStates": {"pending": {"status": "pendingInit"}},
                }
            },
        },
        {
            "method": "item/completed",
            "params": {
                "item": {
                    "type": "collabAgentToolCall",
                    "id": "wait-both",
                    "tool": "wait",
                    "status": "completed",
                    "receiverThreadIds": ["child-a", "child-b"],
                    "agentsStates": {
                        "child-a": {"status": "completed", "message": "claims A"},
                        "child-b": {"status": "completed", "message": "claims B"},
                    },
                }
            },
        },
        {"method": "turn/completed", "params": {"turn": {"status": "completed"}}},
    ]
    adapter = _stub_turn_collector(iter(()), before_turn=events)

    collected = adapter._collect_turn(1, "", [])
    result, _observations = parse_codex_events(
        collected,
        redact_json_rpc=_identity,
        redact_text=_identity,
        session_id="root-thread",
        root_turn_id="root-turn",
    )

    assert [call.result for call in result.tool_calls] == [
        {"is_error": False, "content": ["claims A"]},
        {"is_error": False, "content": ["claims B"]},
    ]


def test_parse_codex_events_binds_idless_spawn_only_to_singleton_wait() -> None:
    events = [
        {
            "method": "item/completed",
            "params": {
                "item": {
                    "type": "collabAgentToolCall",
                    "id": "spawn-idless",
                    "tool": "spawnAgent",
                    "prompt": "review closure",
                    "status": "completed",
                    "agentsStates": {"pending": {"status": "pendingInit"}},
                }
            },
        },
        {
            "method": "item/completed",
            "params": {
                "item": {
                    "type": "collabAgentToolCall",
                    "id": "wait-one",
                    "tool": "wait",
                    "status": "completed",
                    "receiverThreadIds": ["child-1"],
                    "agentsStates": {
                        "child-1": {"status": "completed", "message": "claims"}
                    },
                }
            },
        },
        {"method": "turn/completed", "params": {"turn": {"status": "completed"}}},
    ]

    result, _ = parse_codex_events(
        events,
        redact_json_rpc=_identity,
        redact_text=_identity,
        session_id="thread-1",
    )

    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].result == {"is_error": False, "content": ["claims"]}


def test_parse_codex_events_does_not_reuse_a_stale_receiver_for_idless_spawn() -> None:
    events = [
        {
            "method": "item/completed",
            "params": {
                "item": {
                    "type": "collabAgentToolCall",
                    "id": "spawn-first",
                    "tool": "spawnAgent",
                    "prompt": "review first closure",
                    "status": "completed",
                    "receiverThreadIds": ["child-1"],
                    "agentsStates": {"child-1": {"status": "running"}},
                }
            },
        },
        {
            "method": "item/completed",
            "params": {
                "item": {
                    "type": "collabAgentToolCall",
                    "id": "wait-first",
                    "tool": "wait",
                    "status": "completed",
                    "receiverThreadIds": ["child-1"],
                    "agentsStates": {
                        "child-1": {"status": "completed", "message": "first claims"}
                    },
                }
            },
        },
        {
            "method": "item/completed",
            "params": {
                "item": {
                    "type": "collabAgentToolCall",
                    "id": "spawn-second",
                    "tool": "spawnAgent",
                    "prompt": "review second closure",
                    "status": "completed",
                    "agentsStates": {"pending": {"status": "pendingInit"}},
                }
            },
        },
        {
            "method": "item/completed",
            "params": {
                "item": {
                    "type": "collabAgentToolCall",
                    "id": "stale-wait",
                    "tool": "wait",
                    "status": "completed",
                    "receiverThreadIds": ["child-1"],
                    "agentsStates": {
                        "child-1": {"status": "completed", "message": "stale claims"}
                    },
                }
            },
        },
        {"type": "turn.completed", "turn_id": "root-turn"},
    ]

    result, _ = parse_codex_events(
        events,
        redact_json_rpc=_identity,
        redact_text=_identity,
        session_id="root-thread",
    )

    successful = [call for call in result.tool_calls if call.result["is_error"] is False]
    assert len(successful) == 1
    assert successful[0].result == {"is_error": False, "content": ["first claims"]}
    assert "stale claims" not in result.transcript_delta


def test_parse_codex_events_keeps_multiple_idless_spawns_ungraded() -> None:
    events = [
        {
            "method": "item/completed",
            "params": {
                "item": {
                    "type": "collabAgentToolCall",
                    "id": spawn_id,
                    "tool": "spawnAgent",
                    "prompt": "review a closure",
                    "status": "completed",
                    "agentsStates": {"pending": {"status": "pendingInit"}},
                }
            },
        }
        for spawn_id in ("spawn-a", "spawn-b")
    ]
    events.extend(
        (
            {
                "method": "item/completed",
                "params": {
                    "item": {
                        "type": "collabAgentToolCall",
                        "id": "wait-one",
                        "tool": "wait",
                        "status": "completed",
                        "receiverThreadIds": ["child-1"],
                        "agentsStates": {
                            "child-1": {"status": "completed", "message": "ambiguous claims"}
                        },
                    }
                },
            },
            {"type": "turn.completed", "turn_id": "root-turn"},
        )
    )

    result, _ = parse_codex_events(
        events,
        redact_json_rpc=_identity,
        redact_text=_identity,
        session_id="root-thread",
    )

    assert len(result.tool_calls) == 2
    assert all(call.result["is_error"] is True for call in result.tool_calls)
    assert "ambiguous claims" not in result.transcript_delta


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
    assert params["config"]["sandbox_workspace_write"] == {
        "exclude_slash_tmp": True,
        "exclude_tmpdir_env_var": True,
    }
    assert adapter.review_timeout_seconds == pytest.approx(REVIEW_DEADLINE_MS / 1000.0)

    app_command = adapter._app_server_command()
    assert app_command[:3] == ["/bin/true", "app-server", "--stdio"]
    assert app_command[3:5] == ["--enable", "multi_agent"]
    assert "sandbox_workspace_write.exclude_slash_tmp=true" in app_command
    assert "sandbox_workspace_write.exclude_tmpdir_env_var=true" in app_command
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
        "        print(json.dumps({'method': 'item/completed', 'params': {'threadId': thread_id, 'turnId': turn_id, 'item': item}}), flush=True)\n"
        "        turn = {'id': turn_id, 'status': 'completed'}\n"
        "        print(json.dumps({'method': 'turn/completed', 'params': {'threadId': thread_id, 'turn': turn}}), flush=True)\n"
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


def test_native_codex_home_survives_adapter_restart_and_reuses_rollout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_root = tmp_path / "native-run" / "crm-pipeline" / "epoch-1"
    workspace = run_root / "agent"
    workspace.mkdir(parents=True)
    fixture_dir = tmp_path / "fixture"
    fixture_dir.mkdir()
    supervisor_dir = tmp_path / "supervisor"
    supervisor_dir.mkdir()
    host_home = tmp_path / "host-codex"
    host_home.mkdir()
    (host_home / "auth.json").write_text("synthetic-auth-sentinel", encoding="utf-8")
    monkeypatch.setenv("CODEX_HOME", str(host_home))
    monkeypatch.chdir(workspace)

    fake = tmp_path / "fake-codex"
    fake.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "thread_id = '00000000-0000-4000-8000-000000000031'\n"
        "rollout = Path(os.environ['CODEX_HOME']) / 'sessions' / 'rollout.jsonl'\n"
        "for line in sys.stdin:\n"
        "    request = json.loads(line)\n"
        "    method = request.get('method')\n"
        "    if method == 'initialize':\n"
        "        print(json.dumps({'id': request['id'], 'result': {}}), flush=True)\n"
        "    elif method == 'thread/start':\n"
        "        rollout.parent.mkdir(parents=True, exist_ok=True)\n"
        "        rollout.write_text('synthetic rollout state', encoding='utf-8')\n"
        "        print(json.dumps({'id': request['id'], 'result': {'thread': {'id': thread_id}}}), flush=True)\n"
        "    elif method == 'thread/resume':\n"
        "        if rollout.is_file():\n"
        "            print(json.dumps({'id': request['id'], 'result': {'thread': {'id': thread_id}}}), flush=True)\n"
        "        else:\n"
        "            print(json.dumps({'id': request['id'], 'error': {'code': -32600, 'message': 'no rollout found'}}), flush=True)\n"
        "    elif method == 'mcpServerStatus/list':\n"
        "        print(json.dumps({'id': request['id'], 'result': {'data': [{'name': 'nxd-desktop', 'runtimeStatus': 'connected', 'tools': {'list_data_products': {}}}]}}), flush=True)\n",
        encoding="utf-8",
    )
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    config_path = tmp_path / "mcp.json"
    config_path.write_text(
        json.dumps({"mcpServers": {"nxd-desktop": {"command": "/bin/echo", "args": []}}}),
        encoding="utf-8",
    )
    state_dir = run_root / "provider-state" / "codex-home"

    def adapter(resume_session_id: str | None = None) -> CodexAdapter:
        return CodexAdapter(
            codex=fake,
            model="gpt-5.6-luna",
            effort="medium",
            skill_pack_root=REPO_ROOT,
            repo_root=REPO_ROOT,
            fixture_dir=fixture_dir,
            artifact_dir=run_root / "artifacts",
            desktop_supervisor=Path("/bin/true"),
            desktop_python=Path("/bin/true"),
            timeout_s=5,
            append_system_prompt="test",
            mcp_config=config_path,
            supervisor_data_dir=supervisor_dir,
            native_continuation=True,
            resume_session_id=resume_session_id,
            native_state_dir=state_dir,
        )

    first = adapter()
    first.start()
    first.close()

    auth_link = state_dir / "auth.json"
    rollout = state_dir / "sessions" / "rollout.jsonl"
    assert state_dir.is_dir()
    assert state_dir.stat().st_mode & 0o077 == 0
    assert auth_link.is_symlink()
    assert auth_link.readlink() == host_home / "auth.json"
    assert rollout.is_file()
    assert not state_dir.is_relative_to(workspace)
    assert not (run_root / "artifacts" / "codex-home").exists()

    config = state_dir / "config.toml"
    config.write_text(
        f"[projects.{json.dumps(str(workspace))}]\ntrust_level = \"trusted\"\n",
        encoding="utf-8",
    )
    config.chmod(0o600)
    project_config_dir = workspace / ".codex"
    project_config_dir.mkdir()
    (project_config_dir / "config.toml").write_text(
        'approval_policy = "never"\nsandbox_mode = "danger-full-access"\n',
        encoding="utf-8",
    )
    with pytest.raises(CodexAdapterError, match="workspace-local Codex project config"):
        adapter("00000000-0000-4000-8000-000000000031").start()
    (project_config_dir / "config.toml").unlink()
    project_config_dir.rmdir()

    resumed = adapter("00000000-0000-4000-8000-000000000031")
    resumed.start()
    resumed.close()


def test_native_codex_config_rejects_unapproved_persisted_settings(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    workspace = tmp_path / "workspace"
    skill_pack_root = tmp_path / "skills"
    config.write_text('[mcp_servers.other]\nrequired = true\n', encoding="utf-8")

    with pytest.raises(CodexAdapterError, match="unexpected settings"):
        _validate_persistent_codex_config(
            config, workspace=workspace
        )

    config.write_text(
        f"[projects.{json.dumps(str(skill_pack_root))}]\ntrust_level = \"trusted\"\n",
        encoding="utf-8",
    )
    with pytest.raises(CodexAdapterError, match="unapproved project"):
        _validate_persistent_codex_config(config, workspace=workspace)


def test_codex_adapter_rejects_non_object_app_server_events() -> None:
    with pytest.raises(CodexAdapterError, match="non-object JSON event"):
        CodexAdapter._decode_app_server_line(b"[]")


def test_codex_adapter_drains_queued_events_before_checking_deadline() -> None:
    adapter = object.__new__(CodexAdapter)
    adapter._process = SimpleNamespace(stdout=object(), stderr=object())
    queued = {"method": "notification"}
    adapter._stdout_events = deque([queued])

    assert adapter._read_streams(time.monotonic() - 1) == queued


def test_main_suppresses_private_startup_exception_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    written = []

    class StartupFailure:
        _thread_id = "root-thread"
        last_mcp_call = None

        def __init__(self, **_kwargs) -> None:
            pass

        def send(self, _request):
            raise CodexAppServerEOF(
                "startup failed PRIVATE_STARTUP_SENTINEL",
                reason=CHILD_EXITED_EARLY,
            )

        def close(self) -> None:
            pass

    monkeypatch.setattr(codex_adapter_module, "CodexAdapter", StartupFailure)
    monkeypatch.setattr(
        codex_adapter_module,
        "_write_result",
        lambda result, **_kwargs: written.append(result),
    )
    monkeypatch.setattr(sys, "stdin", StringIO('{"message":{"text":"test"}}\n'))
    monkeypatch.setattr(codex_adapter_module.signal, "signal", lambda *_args: None)

    exit_code = codex_adapter_module.main(
        [
            "--codex",
            str(tmp_path / "codex"),
            "--model",
            "gpt-5.6-luna",
            "--skill-pack-root",
            str(REPO_ROOT),
            "--repo-root",
            str(REPO_ROOT),
            "--fixture-dir",
            str(tmp_path),
            "--artifact-dir",
            str(tmp_path / "artifacts"),
            "--desktop-supervisor",
            str(tmp_path / "supervisor"),
            "--desktop-python",
            str(tmp_path / "python"),
            "--mcp-config",
            str(tmp_path / "mcp.json"),
            "--supervisor-data-dir",
            str(tmp_path / "supervisor-data"),
        ]
    )

    assert exit_code == 0
    assert len(written) == 1
    result = written[0]
    assert result.failure_reason == CHILD_EXITED_EARLY
    assert "PRIVATE_STARTUP_SENTINEL" not in result.environment_detail
    assert result.environment_detail == (
        "Codex app-server exited before returning an event (child_exited_early)"
    )


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
        "        print(json.dumps({'method': 'item/started', 'params': {'threadId': thread_id, 'turnId': turn_id, 'item': call}}), flush=True)\n"
        "        call['status'] = 'completed'\n"
        "        call['result'] = {'structuredContent': {'page': turn_number}}\n"
        "        print(json.dumps({'method': 'item/completed', 'params': {'threadId': thread_id, 'turnId': turn_id, 'item': call}}), flush=True)\n"
        "        message = {'type': 'agentMessage', 'id': f'msg-{turn_number}', 'text': f'turn {turn_number}'}\n"
        "        print(json.dumps({'method': 'item/completed', 'params': {'threadId': thread_id, 'turnId': turn_id, 'item': message}}), flush=True)\n"
        "        print(json.dumps({'method': 'turn/completed', 'params': {'threadId': thread_id, 'turn': {'id': turn_id, 'status': 'completed'}}}), flush=True)\n",
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
        "        print(json.dumps({'method': 'item/started', 'params': {'threadId': thread_id, 'turnId': '00000000-0000-4000-8000-000000000021', 'item': call}}), flush=True)\n"
        "        print(json.dumps({'method': 'item/agentMessage/delta', 'params': {'threadId': thread_id, 'turnId': '00000000-0000-4000-8000-000000000021', 'delta': 'partial'}}), flush=True)\n"
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
