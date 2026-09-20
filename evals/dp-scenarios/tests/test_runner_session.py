"""Guard tests for structured live/replay session observations."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys
from dataclasses import FrozenInstanceError

import pytest

from dp_scenarios.operator.transport import ToolCall, TouchedFile, TurnResult
from dp_scenarios.runner.session import (
    LiveSession,
    NativeResumeSession,
    RecordedTurn,
    RecordingSession,
    ReplayMismatch,
    ReplayRecording,
    ReplaySession,
    SessionError,
    turn_result_from_dict,
    turn_result_to_dict,
)
from dp_scenarios.operator.transport import InMemoryTransport, OperatorMessage
from dp_scenarios.runner.checkpoint import CheckpointError, CheckpointStore


@pytest.mark.parametrize("count", [True, 1.5, "1"])
def test_turn_result_rejects_non_integer_terminal_result_counts(count: object) -> None:
    with pytest.raises(TypeError, match="terminal_result_count must be an integer"):
        TurnResult(terminal_result_count=count)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("terminal_result_count", True),
        ("terminal_result_count", "1"),
        ("terminal_result_count", -1),
        ("terminal_result_subtype", []),
        ("terminal_result_is_error", 0),
    ],
)
def test_replay_rejects_malformed_terminal_result_facts(field: str, value: object) -> None:
    encoded = turn_result_to_dict(TurnResult())
    encoded[field] = value

    with pytest.raises(SessionError, match=field):
        turn_result_from_dict(encoded)


def test_replay_missing_terminal_facts_remains_completion_incapable() -> None:
    encoded = turn_result_to_dict(TurnResult(agent_message="done"))
    for field in (
        "terminal_result_count",
        "terminal_result_subtype",
        "terminal_result_is_error",
    ):
        encoded.pop(field)

    decoded = turn_result_from_dict(encoded)

    assert decoded.terminal_result_count == 0
    assert decoded.terminal_result_subtype is None
    assert decoded.terminal_result_is_error is None


def test_recording_round_trip_preserves_structured_observations_and_files(tmp_path: Path) -> None:
    response = TurnResult(
        transcript_delta="delta",
        agent_message="What is the source?",
        tool_calls=(ToolCall("read", {"path": "spec.json"}, {"ok": True}),),
        tool_results=({"rows": 4},),
        files_touched=(TouchedFile("closure/spec.json", b'{"metric":"m"}'),),
        approval_artifact="artifact://spec",
        reported=True,
        session_id="session-1",
    )
    message = OperatorMessage("Improve visibility.")
    recording = ReplayRecording((RecordedTurn(message, response),), metadata={"mode": "test"})
    path = recording.write(tmp_path / "recording.json")

    replay_root = tmp_path / "replayed-artifacts"
    replay = ReplaySession(path, artifact_root=replay_root)
    replay.start_fresh_session()
    observed = replay.send_message(message)

    assert observed == response
    assert (replay_root / "closure/spec.json").read_bytes() == b'{"metric":"m"}'
    assert replay.sent_messages == [message]


def test_recording_transport_captures_observations_not_just_agent_text() -> None:
    message = OperatorMessage("Ask")
    result = TurnResult(agent_message="narrative", tool_calls=(ToolCall("query"),), reported=True)
    recorder = RecordingSession(InMemoryTransport([result]))
    recorder.start_fresh_session()
    assert recorder.send_message(message) is result
    saved = recorder.recording()

    assert saved.turns[0].result.tool_calls == (ToolCall("query"),)
    assert saved.turns[0].result.reported is True


def test_live_recording_relativizes_absolute_paths_and_collects_artifacts(tmp_path: Path) -> None:
    home = tmp_path / "home"
    artifact_root = tmp_path / "artifacts"
    result = TurnResult(
        files_touched=(TouchedFile(home / "closure/spec.json", b'{"metric":"m"}'),),
    )
    recorder = RecordingSession(
        LiveSession(handler=lambda message: result),
        artifact_root=artifact_root,
        sandbox_home=home,
    )
    recorder.start_fresh_session()
    recorder.send_message("expected")
    saved = recorder.recording()

    assert saved.turns[0].result.files_touched[0].path == "closure/spec.json"
    assert (artifact_root / "closure/spec.json").read_bytes() == b'{"metric":"m"}'

    replay = ReplaySession(saved, artifact_root=tmp_path / "replayed")
    replay.start_fresh_session()
    replay.send_message("expected")
    assert (tmp_path / "replayed/closure/spec.json").read_bytes() == b'{"metric":"m"}'


def test_recording_turn_callback_receives_complete_ordered_immutable_snapshots(tmp_path: Path) -> None:
    snapshots: list[tuple[ReplayRecording, int]] = []
    artifact_root = tmp_path / "artifacts"
    responses = [
        TurnResult(
            agent_message="first",
            tool_calls=(ToolCall("first", {"step": 1}),),
            files_touched=(TouchedFile("first.txt", b"first"),),
        ),
        TurnResult(
            agent_message="second",
            tool_calls=(ToolCall("second", {"step": 2}),),
            files_touched=(TouchedFile("second.txt", b"second"),),
        ),
    ]

    def on_turn_complete(snapshot: ReplayRecording, turn_number: int) -> None:
        snapshots.append((snapshot, turn_number))
        assert snapshot.turns[-1].result.files_touched[0].path == f"{['first', 'second'][turn_number - 1]}.txt"
        assert (artifact_root / f"{['first', 'second'][turn_number - 1]}.txt").is_file()
        assert tuple(turn.operator_message.text for turn in snapshot.turns) == tuple(
            ["first message", "second message"][:turn_number]
        )
        assert isinstance(snapshot.turns, tuple)
        with pytest.raises(FrozenInstanceError):
            snapshot.turns = ()  # type: ignore[misc]
        with pytest.raises(TypeError):
            snapshot.turns[-1].result.tool_calls[0].arguments["mutated"] = True  # type: ignore[index]

    recorder = RecordingSession(
        InMemoryTransport(responses),
        artifact_root=artifact_root,
        on_turn_complete=on_turn_complete,
    )
    recorder.start_fresh_session()
    recorder.send_message("first message")
    recorder.send_message("second message")

    assert [turn_number for _, turn_number in snapshots] == [1, 2]
    assert [len(snapshot.turns) for snapshot, _ in snapshots] == [1, 2]
    assert len(snapshots[0][0].turns) == 1
    assert len(snapshots[1][0].turns) == 2
    assert snapshots[0][0] is not snapshots[1][0]


def test_recording_turn_callback_failure_is_reported_as_session_error() -> None:
    calls = 0

    def on_turn_complete(snapshot: ReplayRecording, turn_number: int) -> None:
        nonlocal calls
        calls += 1
        raise ValueError("checkpoint write failed")

    recorder = RecordingSession(
        InMemoryTransport([TurnResult(agent_message="complete")]),
        on_turn_complete=on_turn_complete,
    )
    recorder.start_fresh_session()

    with pytest.raises(SessionError, match="turn-complete callback failed"):
        recorder.send_message("expected")

    assert calls == 1
    assert len(recorder.turns) == 1
    assert recorder.turns[0].result.agent_message == "complete"


def test_recording_does_not_emit_a_checkpoint_for_an_inflight_mcp_call() -> None:
    checkpoints: list[int] = []
    recorder = RecordingSession(
        InMemoryTransport(
            [
                TurnResult(
                    tool_calls=(ToolCall("mcp__nxd-desktop__advance_workflow"),),
                    last_mcp_call="advance_workflow:unanswered",
                    environment_wedged=True,
                )
            ]
        ),
        on_turn_complete=lambda _snapshot, turn_number: checkpoints.append(turn_number),
    )
    recorder.start_fresh_session()

    result = recorder.send_message("expected")

    assert result.environment_wedged
    assert len(recorder.turns) == 1
    assert checkpoints == []


def test_replay_rejects_a_changed_operator_message(tmp_path: Path) -> None:
    recording = ReplayRecording((RecordedTurn(OperatorMessage("expected"), TurnResult()),))
    replay = ReplaySession(recording)
    replay.start_fresh_session()

    with pytest.raises(ReplayMismatch, match="turn 1"):
        replay.send_message("different")


def test_native_resume_replays_prefix_locally_and_continues_the_provider_session() -> None:
    prefix = ReplayRecording(
        (
            RecordedTurn(OperatorMessage("first"), TurnResult(agent_message="one")),
            RecordedTurn(OperatorMessage("second"), TurnResult(agent_message="two")),
        )
    )
    provider = InMemoryTransport(
        [TurnResult(agent_message="three"), TurnResult(agent_message="four")]
    )
    session_id = "00000000-0000-4000-8000-000000000001"
    resumed = NativeResumeSession(prefix, provider, session_id=session_id)

    assert resumed.start_fresh_session() == session_id
    assert resumed.send_message("first").agent_message == "one"
    assert resumed.send_message("second").agent_message == "two"
    assert resumed.send_message("third").agent_message == "three"
    assert resumed.send_message("fourth").agent_message == "four"
    assert provider.resumed == [session_id]
    assert provider.message_texts == ("third", "fourth")


def test_native_resume_rejects_a_prefix_message_mismatch_before_provider_use() -> None:
    prefix = ReplayRecording((RecordedTurn(OperatorMessage("expected"), TurnResult()),))
    provider = InMemoryTransport([TurnResult(agent_message="not-used")])
    resumed = NativeResumeSession(
        prefix,
        provider,
        session_id="00000000-0000-4000-8000-000000000001",
    )
    resumed.start_fresh_session()

    with pytest.raises(ReplayMismatch, match="turn 1"):
        resumed.send_message("different")
    assert provider.message_texts == ()


def test_native_resume_hydrates_redacted_prefix_files_from_the_retained_workspace(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "agent"
    content = b"private-but-retained"
    target = workspace / "closure" / "spec.json"
    target.parent.mkdir(parents=True)
    target.write_bytes(content)
    prefix = ReplayRecording(
        (
            RecordedTurn(
                OperatorMessage("first"),
                TurnResult(
                    files_touched=(
                        TouchedFile(
                            "closure/spec.json",
                            {
                                "redacted": True,
                                "sha256": hashlib.sha256(content).hexdigest(),
                                "size_bytes": len(content),
                            },
                        ),
                    )
                ),
            ),
        )
    )
    provider = InMemoryTransport([TurnResult(agent_message="next")])
    resumed = NativeResumeSession(
        prefix,
        provider,
        session_id="00000000-0000-4000-8000-000000000001",
        source_root=workspace,
    )

    resumed.start_fresh_session()
    result = resumed.send_message("first")

    assert result.files_touched[0].content == content
    assert provider.message_texts == ()

    target.write_bytes(b"changed")
    with pytest.raises(SessionError, match="bytes changed"):
        NativeResumeSession(
            prefix,
            InMemoryTransport([TurnResult(agent_message="not-used")]),
            session_id="00000000-0000-4000-8000-000000000001",
            source_root=workspace,
        )


def test_native_resume_hydrates_from_an_immutable_checkpoint_snapshot(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "agent"
    target = workspace / "closure" / "spec.json"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"later-turn-content")
    original = b"checkpoint-prefix-content"
    prefix = ReplayRecording(
        (
            RecordedTurn(
                OperatorMessage("first"),
                TurnResult(
                    files_touched=(
                        TouchedFile(
                            "closure/spec.json",
                            {
                                "redacted": True,
                                "sha256": hashlib.sha256(original).hexdigest(),
                                "size_bytes": len(original),
                            },
                        ),
                    )
                ),
            ),
        )
    )
    store = CheckpointStore(tmp_path / "checkpoints")
    store.write_source_snapshot("turn-000001", ((1, 0, "closure/spec.json", original),))

    source_snapshot = store.read_source_snapshot("turn-000001")
    assert source_snapshot == {(1, 0): ("closure/spec.json", original)}
    provider = InMemoryTransport([TurnResult(agent_message="next")])
    resumed = NativeResumeSession(
        prefix,
        provider,
        session_id="00000000-0000-4000-8000-000000000001",
        source_root=workspace,
        source_snapshot=source_snapshot,
    )

    resumed.start_fresh_session()
    assert resumed.send_message("first").files_touched[0].content == original

    private_file = (
        tmp_path
        / "checkpoints"
        / "source-snapshots"
        / "turn-000001"
        / "files"
        / "000000.bin"
    )
    private_file.write_bytes(b"tampered")
    with pytest.raises(CheckpointError, match="bytes changed"):
        store.read_source_snapshot("turn-000001")


def test_replay_rejects_touched_file_escape(tmp_path: Path) -> None:
    recording = ReplayRecording(
        (
            RecordedTurn(
                OperatorMessage("expected"),
                TurnResult(files_touched=(TouchedFile("../escape.txt", b"no"),)),
            ),
        )
    )
    replay = ReplaySession(recording, artifact_root=tmp_path / "artifacts")
    replay.start_fresh_session()

    with pytest.raises(Exception, match="escapes artifact root"):
        replay.send_message("expected")


def test_replay_rejects_agent_owned_harness_oracle_names(tmp_path: Path) -> None:
    recording = ReplayRecording(
        (
            RecordedTurn(
                OperatorMessage("expected"),
                TurnResult(
                    files_touched=(TouchedFile("row_counts.json", b'{"model": 1}'),),
                ),
            ),
        )
    )
    replay = ReplaySession(recording, artifact_root=tmp_path / "artifacts")
    replay.start_fresh_session()

    with pytest.raises(Exception, match="reserved for harness-owned evidence"):
        replay.send_message("expected")


def test_live_timeout_returns_a_recordable_turn_timeout() -> None:
    session = LiveSession(
        [sys.executable, "-c", "import sys; import time; sys.stdin.readline(); time.sleep(1)"],
        timeout=0.01,
    )
    try:
        session.start_fresh_session()
        result = session.send_message("expected")
    finally:
        session.close()

    assert result.turn_timed_out
    assert not result.environment_wedged
    assert result.environment_detail == "live session exceeded the 0.010s turn timeout"
    assert result.session_id == "live-session-1"
    encoded = turn_result_to_dict(result)
    assert turn_result_from_dict(encoded) == result
    legacy = dict(encoded)
    legacy.pop("turn_timed_out")
    assert turn_result_from_dict(legacy).turn_timed_out is False

    for field in (
        "terminal_result_count",
        "terminal_result_subtype",
        "terminal_result_is_error",
    ):
        legacy.pop(field, None)
    decoded_legacy = turn_result_from_dict(legacy)
    assert decoded_legacy.terminal_result_count == 0
    assert decoded_legacy.terminal_result_subtype is None
    assert decoded_legacy.terminal_result_is_error is None


def test_live_fresh_session_restarts_a_persistent_child() -> None:
    session = LiveSession(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        timeout=1.0,
    )
    try:
        first_session = session.start_fresh_session()
        assert session._process is not None
        first_pid = session._process.pid
        second_session = session.start_fresh_session()
        assert session._process is not None
        second_pid = session._process.pid
    finally:
        session.close()

    assert first_session == "live-session-1"
    assert second_session == "live-session-2"
    assert first_pid != second_pid


def test_live_session_resume_uses_an_explicit_resume_command_without_faking_a_prompt(
    tmp_path: Path,
) -> None:
    fresh = [sys.executable, "-c", "import time; time.sleep(60)"]
    resumed = [sys.executable, "-c", "import time; time.sleep(60)"]
    session = LiveSession(
        fresh,
        timeout=1.0,
        resume_command_builder=lambda session_id: [*resumed, session_id],
    )
    try:
        session_id = "00000000-0000-4000-8000-000000000001"
        assert session.resume_session(session_id) == session_id
        assert session._resume_command[-1] == session_id
        assert session._pending_resume_session_id == session_id
    finally:
        session.close()
