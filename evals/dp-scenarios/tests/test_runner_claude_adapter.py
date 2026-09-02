"""Contract tests for the local Claude Code transport bridge."""

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid

import pytest

from dp_scenarios.runner.claude_adapter import ClaudeCodeAdapter, _update_machine_artifacts, parse_claude_events
from dp_scenarios.runner.local import FileSupervisorRecordReader, LocalRunnerError


def _identity(value: object) -> object:
    return value


def test_parse_stream_events_keeps_tool_observations_structured() -> None:
    events = [
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "text", "text": "Use the approved source."},
                    {"type": "tool_use", "id": "build-1", "name": "mcp__nxd-desktop__build_data_product", "input": {"definition": "/tmp/closure", "workflow": "zero-row-optional-output"}},
                ]
            },
        },
        {
            "type": "user",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "build-1",
                        "content": [{"type": "text", "text": '{"run_id":"run-1","artifact_id":"artifact-1","bearer_token":"secret"}'}],
                    }
                ]
            },
        },
        {"type": "result", "result": "Use the approved source.", "is_error": False},
    ]

    result, observations = parse_claude_events(
        events,
        redact_json_rpc=_identity,
        redact_text=lambda value: value,
        session_id="claude-session",
    )

    assert result.agent_message == "Use the approved source."
    assert result.session_id == "claude-session"
    assert [call.name for call in result.tool_calls] == ["mcp__nxd-desktop__build_data_product"]
    assert result.tool_calls[0].result["content"]["run_id"] == "run-1"  # type: ignore[index]
    assert observations[0]["tool"] == "build_data_product"
    assert observations[0]["result"]["run_id"] == "run-1"  # type: ignore[index]
    assert result.reported is False


def test_unpaired_mcp_tool_use_is_an_environment_wedge_not_a_build_failure() -> None:
    result, observations = parse_claude_events(
        [
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "build-1",
                            "name": "mcp__nxd-desktop__build_data_product",
                            "input": {},
                        }
                    ]
                },
            },
            {"type": "result", "result": "stream ended", "is_error": False},
        ],
        redact_json_rpc=_identity,
        redact_text=lambda value: value,
        session_id="claude-session",
    )

    assert result.environment_wedged is True
    assert result.build_failed is False
    assert result.build_failure_count == 0
    assert result.reported is False
    assert "no matching result" in (result.environment_detail or "")
    assert observations[0]["is_error"] is True


def test_machine_artifacts_require_structured_mcp_facts(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifacts"
    observations = [
        {
            "tool": "build_data_product",
            "arguments": {"workflow": "parent-child-grain-trap"},
            "result": {"run_id": "run-6", "artifact_id": "artifact-6"},
            "is_error": False,
        },
        {
            "tool": "list_data_products",
            "arguments": {},
            "result": {
                "products": [
                    {
                        "workflow": "parent-child-grain-trap",
                        "run_id": "run-6",
                        "artifact_id": "artifact-6",
                        "publish_seq": 3,
                        "artifact_status": "available",
                        "models": [{"dataset": "main", "table": "orders", "row_count": 5}],
                    }
                ]
            },
            "is_error": False,
        },
        {
            "tool": "inspect_run",
            "arguments": {"run_id": "run-6"},
            "result": {"run": {"run_id": "run-6", "lifecycle": "published"}},
            "is_error": False,
        },
        {
            "tool": "run_semantic_query",
            "arguments": {},
            "result": {"rows": [{"region": "north", "regional_revenue": 10.0}]},
            "is_error": False,
        },
    ]
    facts: dict[str, object] = {}

    _update_machine_artifacts(observations, artifact_dir=artifact_dir, facts=facts, build_context={})

    assert json.loads((artifact_dir / "supervisor-facts.json").read_text()) == {
        "run_id": "run-6",
        "artifact_id": "artifact-6",
        "publish_sequence": "3",
        "per_model_row_counts": {"main.orders": "5"},
        "lifecycle_state": "published",
    }
    assert json.loads((artifact_dir / "query-results.json").read_text()) == {
        "rows": [{"region": "north", "regional_revenue": 10.0}]
    }


def test_machine_artifacts_do_not_create_facts_from_build_only(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifacts"
    _update_machine_artifacts(
        [
            {
                "tool": "build_data_product",
                "arguments": {"workflow": "zero-row-optional-output"},
                "result": {"run_id": "run-5", "artifact_id": "artifact-5"},
                "is_error": False,
            }
        ],
        artifact_dir=artifact_dir,
        facts={},
        build_context={},
    )

    assert not (artifact_dir / "supervisor-facts.json").exists()


def test_machine_artifacts_require_observed_lifecycle_state(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifacts"
    _update_machine_artifacts(
        [
            {
                "tool": "build_data_product",
                "arguments": {"workflow": "zero-row-optional-output"},
                "result": {"run_id": "run-5", "artifact_id": "artifact-5"},
                "is_error": False,
            },
            {
                "tool": "list_data_products",
                "arguments": {},
                "result": {
                    "products": [
                        {
                            "workflow": "zero-row-optional-output",
                            "run_id": "run-5",
                            "artifact_id": "artifact-5",
                            "publish_seq": 4,
                            "models": [{"dataset": "main", "table": "orders", "row_count": 5}],
                        }
                    ]
                },
                "is_error": False,
            },
        ],
        artifact_dir=artifact_dir,
        facts={},
        build_context={},
    )

    assert not (artifact_dir / "supervisor-facts.json").exists()


def test_file_supervisor_reader_is_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "supervisor-facts.json"
    path.write_text(
        json.dumps(
            {
                "run_id": "run-1",
                "artifact_id": "artifact-1",
                "publish_sequence": "1",
                "per_model_row_counts": {"main.model": "5"},
                "lifecycle_state": "published",
            }
        )
    )
    facts = FileSupervisorRecordReader(path).read_facts()
    assert facts.run_id == "run-1"
    assert facts.per_model_row_counts == {"main.model": "5"}

    path.write_text(json.dumps({"run_id": "run-1"}))
    with pytest.raises((LocalRunnerError, ValueError)):
        FileSupervisorRecordReader(path).read_facts()


def test_adapter_drives_a_long_lived_stream_and_snapshots_agent_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_claude = tmp_path / "fake-claude.py"
    fake_claude.write_text(
        f"#!{sys.executable}\n"
        """
import json
from pathlib import Path
import sys

closure = Path.cwd() / "closure"
closure.mkdir(exist_ok=True)
closure.joinpath("spec.json").write_text('{"metrics": {"revenue": "sum"}}')
for line in sys.stdin:
    json.loads(line)
    print(json.dumps({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": "tool-1", "name": "Read", "input": {"file_path": "closure/spec.json"}},
        {"type": "text", "text": "Use the approved source."}
    ]}}), flush=True)
    print(json.dumps({"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": "tool-1", "content": "ok"}
    ]}}), flush=True)
    print(json.dumps({"type": "result", "result": "Use the approved source.", "is_error": False}), flush=True)
        """.strip()
        + "\n",
        encoding="utf-8",
    )
    fake_claude.chmod(0o700)
    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir()
    fixture_dir = tmp_path / "fixture"
    fixture_dir.mkdir()
    artifact_dir = tmp_path / "artifacts"
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    monkeypatch.chdir(agent_dir)
    repo_root = Path(__file__).resolve().parents[3]
    adapter = ClaudeCodeAdapter(
        claude=fake_claude,
        model="test",
        effort="low",
        plugin_dir=plugin_dir,
        repo_root=repo_root,
        fixture_dir=fixture_dir,
        artifact_dir=artifact_dir,
        desktop_supervisor=Path("/usr/bin/true"),
        desktop_python=Path(sys.executable),
        claude_config_dir=None,
        timeout_s=10,
        max_budget_usd=None,
        append_system_prompt="test",
    )
    try:
        first = adapter.send({"type": "turn", "message": {"text": "hello", "attachments": []}})
        second = adapter.send({"type": "turn", "message": {"text": "continue", "attachments": []}})
    finally:
        adapter.close()

    assert first.agent_message == second.agent_message == "Use the approved source."
    assert first.session_id is not None
    assert uuid.UUID(first.session_id).version == 4
    assert first.files_touched[0].path == "closure/spec.json"
    assert second.files_touched == ()


def test_adapter_timeout_retains_partial_stream_observations(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_claude = tmp_path / "slow-fake-claude.py"
    fake_claude.write_text(
        f"#!{sys.executable}\n"
        """
import json
import sys
import time

for line in sys.stdin:
    json.loads(line)
    print(json.dumps({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": "build-1", "name": "mcp__nxd-desktop__build_data_product", "input": {}}
    ]}}), flush=True)
    time.sleep(1)
        """.strip()
        + "\n",
        encoding="utf-8",
    )
    fake_claude.chmod(0o700)
    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir()
    fixture_dir = tmp_path / "fixture"
    fixture_dir.mkdir()
    artifact_dir = tmp_path / "artifacts"
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    monkeypatch.chdir(agent_dir)
    repo_root = Path(__file__).resolve().parents[3]
    adapter = ClaudeCodeAdapter(
        claude=fake_claude,
        model="test",
        effort="low",
        plugin_dir=plugin_dir,
        repo_root=repo_root,
        fixture_dir=fixture_dir,
        artifact_dir=artifact_dir,
        desktop_supervisor=Path("/usr/bin/true"),
        desktop_python=Path(sys.executable),
        claude_config_dir=None,
        timeout_s=0.5,
        max_budget_usd=None,
        append_system_prompt="test",
    )

    try:
        result = adapter.send({"type": "turn", "message": {"text": "hello", "attachments": []}})
    finally:
        adapter.close()

    assert result.environment_wedged is True
    assert "did not complete" in (result.environment_detail or "")
    assert result.tool_calls[0].name == "mcp__nxd-desktop__build_data_product"
    assert result.build_failure_count == 0
    assert result.files_touched == ()


def test_adapter_signal_cleanup_reaps_its_claude_child(tmp_path: Path) -> None:
    fake_claude = tmp_path / "blocking-fake-claude.py"
    fake_claude.write_text(
        f"#!{sys.executable}\n"
        """
from pathlib import Path
import os
import sys
import time

Path.cwd().joinpath("child.pid").write_text(str(os.getpid()))
for line in sys.stdin:
    time.sleep(60)
        """.strip()
        + "\n",
        encoding="utf-8",
    )
    fake_claude.chmod(0o700)
    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir()
    fixture_dir = tmp_path / "fixture"
    fixture_dir.mkdir()
    artifact_dir = tmp_path / "artifacts"
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    repo_root = Path(__file__).resolve().parents[3]
    adapter_command = [
        sys.executable,
        "-m",
        "dp_scenarios.runner.claude_adapter",
        "--claude",
        str(fake_claude),
        "--model",
        "test",
        "--effort",
        "low",
        "--plugin-dir",
        str(plugin_dir),
        "--repo-root",
        str(repo_root),
        "--fixture-dir",
        str(fixture_dir),
        "--artifact-dir",
        str(artifact_dir),
        "--desktop-supervisor",
        "/usr/bin/true",
        "--desktop-python",
        sys.executable,
        "--timeout",
        "5",
    ]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(repo_root / "evals/dp-scenarios/src")
    process = subprocess.Popen(
        adapter_command,
        cwd=agent_dir,
        env=environment,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdin is not None
        process.stdin.write(json.dumps({"type": "turn", "message": {"text": "hello"}}) + "\n")
        process.stdin.flush()
        child_pid_path = agent_dir / "child.pid"
        deadline = time.monotonic() + 5
        while not child_pid_path.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert child_pid_path.exists()
        child_pid = int(child_pid_path.read_text())
        os.kill(process.pid, signal.SIGTERM)
        assert process.wait(timeout=5) == 143
        with pytest.raises(ProcessLookupError):
            os.kill(child_pid, 0)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
