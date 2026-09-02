"""Guard tests for structured live/replay session observations."""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

from dp_scenarios.operator.transport import ToolCall, TouchedFile, TurnResult
from dp_scenarios.runner.session import (
    LiveSession,
    RecordedTurn,
    RecordingSession,
    ReplayMismatch,
    ReplayRecording,
    ReplaySession,
)
from dp_scenarios.operator.transport import InMemoryTransport, OperatorMessage


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


def test_replay_rejects_a_changed_operator_message(tmp_path: Path) -> None:
    recording = ReplayRecording((RecordedTurn(OperatorMessage("expected"), TurnResult()),))
    replay = ReplaySession(recording)
    replay.start_fresh_session()

    with pytest.raises(ReplayMismatch, match="turn 1"):
        replay.send_message("different")


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


def test_live_timeout_returns_a_recordable_environment_wedge() -> None:
    session = LiveSession(
        [sys.executable, "-c", "import sys; sys.stdin.readline()"],
        timeout=0.01,
    )
    try:
        session.start_fresh_session()
        result = session.send_message("expected")
    finally:
        session.close()

    assert result.environment_wedged
    assert result.environment_detail == "live session exceeded the 0.010s turn timeout"
    assert result.session_id == "live-session-1"
