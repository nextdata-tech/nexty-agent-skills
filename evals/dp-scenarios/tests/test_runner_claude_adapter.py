"""Contract tests for the local Claude Code transport bridge."""

import io
import json
import dataclasses
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid

import pytest

from _repo_paths import REPO_ROOT

import dp_scenarios.runner.claude_adapter as adapter_module
from dp_scenarios.runner.claude_adapter import ClaudeCodeAdapter, _update_machine_artifacts, parse_claude_events
from dp_scenarios.operator.transport import TouchedFile, ToolCall, TurnResult
from dp_scenarios.runner.session import turn_result_to_dict
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

    assert result.turn_timed_out is False
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
    repo_root = REPO_ROOT
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
    monkeypatch.chdir(agent_dir)
    repo_root = REPO_ROOT
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
        # The budget is total wall time from the first read, so it has to
        # cover the child interpreter's start-up as well as the turn. At 0.5s
        # a loaded machine can expire the deadline before the child prints its
        # first event, and the partial-retention assertion below then fails
        # for a reason that has nothing to do with retention. The child sleeps
        # far past this, so a wider budget still times the turn out.
        timeout_s=2.0,
        max_budget_usd=None,
        append_system_prompt="test",
    )

    try:
        result = adapter.send({"type": "turn", "message": {"text": "hello", "attachments": []}})
    finally:
        adapter.close()

    assert result.turn_timed_out is True
    assert result.environment_wedged is False
    assert "did not complete" in (result.environment_detail or "")
    assert result.tool_calls[0].name == "mcp__nxd-desktop__build_data_product"
    assert result.build_failure_count == 0
    assert result.files_touched == ()


def test_an_early_exit_stays_an_environment_wedge_and_is_not_reported_as_a_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The negative half of the timeout split.

    ``send`` classifies its retained partial turn off the *exception type*, so
    a branch that always reported a timeout -- or always reported a wedge --
    would still satisfy the timeout test alone.  A child that exits before its
    result event raises a plain ``ClaudeAdapterError`` and must stay a wedge.
    """

    fake_claude = tmp_path / "quitting-fake-claude.py"
    fake_claude.write_text(
        f"#!{sys.executable}\n"
        """
import json
import sys

for line in sys.stdin:
    json.loads(line)
    print(json.dumps({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": "build-1", "name": "mcp__nxd-desktop__build_data_product", "input": {}}
    ]}}), flush=True)
    sys.exit(3)
        """.strip()
        + "\n",
        encoding="utf-8",
    )
    fake_claude.chmod(0o700)
    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir()
    fixture_dir = tmp_path / "fixture"
    fixture_dir.mkdir()
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    monkeypatch.chdir(agent_dir)
    adapter = ClaudeCodeAdapter(
        claude=fake_claude,
        model="test",
        effort="low",
        plugin_dir=plugin_dir,
        repo_root=REPO_ROOT,
        fixture_dir=fixture_dir,
        artifact_dir=tmp_path / "artifacts",
        desktop_supervisor=Path("/usr/bin/true"),
        desktop_python=Path(sys.executable),
        claude_config_dir=None,
        timeout_s=30.0,
        max_budget_usd=None,
        append_system_prompt="test",
    )

    try:
        result = adapter.send({"type": "turn", "message": {"text": "hello", "attachments": []}})
    finally:
        adapter.close()

    assert result.turn_timed_out is False
    assert result.environment_wedged is True
    assert "exited before a result event" in (result.environment_detail or "")
    assert result.tool_calls[0].name == "mcp__nxd-desktop__build_data_product"


@pytest.mark.parametrize(
    ("raised", "expect_timeout"),
    [(adapter_module.ClaudeTurnTimeout, True), (adapter_module.ClaudeAdapterError, False)],
)
def test_the_jsonl_loop_reports_a_timeout_and_a_wedge_as_different_results(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    raised: type[Exception],
    expect_timeout: bool,
) -> None:
    """The subprocess entry point owns its own copy of the split.

    ``LiveSession`` never sees the adapter object -- it only sees this loop's
    JSONL line -- so a loop that hardcoded ``environment_wedged=True`` would
    erase the distinction for every live run while every in-process test
    stayed green.
    """

    class _StubAdapter:
        def __init__(self, **_kwargs: object) -> None:
            self._session_id = "stub-session"

        def send(self, _request: object) -> TurnResult:
            raise raised("boom")

        def close(self) -> None:
            return None

    monkeypatch.setattr(adapter_module, "ClaudeCodeAdapter", _StubAdapter)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"type": "turn"}) + "\n"))

    code = adapter_module.main(
        [
            "--claude", sys.executable,
            "--model", "test",
            "--effort", "low",
            "--plugin-dir", ".",
            "--repo-root", ".",
            "--fixture-dir", ".",
            "--artifact-dir", ".",
            "--desktop-supervisor", sys.executable,
            "--desktop-python", sys.executable,
        ]
    )

    assert code == 1
    payload = json.loads(capsys.readouterr().out.strip())["result"]
    assert payload["turn_timed_out"] is expect_timeout
    assert payload["environment_wedged"] is not expect_timeout
    assert payload["environment_detail"] == "boom"
    assert payload["session_id"] == "stub-session"


def test_turn_result_fields_are_serialized_and_preserved_by_adapter_reconstruction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = TurnResult(
        transcript_delta=b"delta",
        agent_message=b"answer",
        tool_calls=(ToolCall("Read", {"path": "spec"}, {"ok": True}),),
        tool_results=({"rows": 2},),
        files_touched=(TouchedFile("closure/spec.json", b"{}"),),
        approval_artifact=b"approval",
        build_failed=True,
        build_failure_count=2,
        reported=True,
        environment_wedged=False,
        turn_timed_out=True,
        environment_detail="timeout detail",
        session_id="session-1",
    )
    assert {field.name for field in dataclasses.fields(TurnResult)} <= set(turn_result_to_dict(TurnResult()))

    adapter = object.__new__(ClaudeCodeAdapter)
    adapter.artifact_dir = tmp_path / "artifacts"
    adapter.artifact_dir.mkdir()
    adapter._before = {}
    adapter._facts = {}
    adapter._build_context = {}
    adapter._session_id = "session-1"
    adapter._stdio = None
    adapter._redact_json_rpc = lambda value: value
    adapter._redact_text = lambda value: value
    monkeypatch.setattr(adapter_module, "parse_claude_events", lambda *args, **kwargs: (source, []))
    monkeypatch.setattr(adapter_module, "_snapshot_workspace", lambda *args, **kwargs: {})
    monkeypatch.setattr(adapter_module, "_changed_files", lambda *args, **kwargs: source.files_touched)
    monkeypatch.setattr(adapter_module, "_update_machine_artifacts", lambda *args, **kwargs: None)
    monkeypatch.setattr(adapter, "_approval_artifact", lambda _snapshot: source.approval_artifact)

    assert adapter._finish_turn([{"type": "result"}]) == source


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
    repo_root = REPO_ROOT
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


def _spawned_claude_argv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    allow_bash: bool,
) -> list[str]:
    """Return the argv the adapter really hands to ``subprocess.Popen``."""

    claude = tmp_path / "claude"
    claude.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    claude.chmod(0o700)
    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir(exist_ok=True)
    fixture_dir = tmp_path / "fixture"
    fixture_dir.mkdir(exist_ok=True)
    mcp_config = tmp_path / "mcp.json"
    mcp_config.write_text("{}", encoding="utf-8")
    workspace = tmp_path / "agent"
    workspace.mkdir(exist_ok=True)
    monkeypatch.chdir(workspace)

    captured: dict[str, list[str]] = {}

    class FakeProcess:
        stdout = None
        stderr = None
        stdin = None
        pid = 0

        def poll(self) -> int:
            return 0

    def fake_popen(command, **kwargs):
        captured["argv"] = list(command)
        return FakeProcess()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    adapter = ClaudeCodeAdapter(
        claude=claude,
        model="test",
        effort="low",
        plugin_dir=plugin_dir,
        repo_root=REPO_ROOT,
        fixture_dir=fixture_dir,
        artifact_dir=tmp_path / "artifacts",
        desktop_supervisor=Path("/usr/bin/true"),
        desktop_python=Path(sys.executable),
        claude_config_dir=None,
        timeout_s=5,
        max_budget_usd=None,
        append_system_prompt="test",
        allow_bash=allow_bash,
        mcp_config=mcp_config,
        allowed_tools="mcp__nxd-desktop__build_data_product",
    )
    adapter.start()
    return captured["argv"]


def _flag_values(argv: list[str], flag: str) -> list[str]:
    return [argv[index + 1] for index, value in enumerate(argv) if value == flag]


def test_withheld_bash_is_denied_on_the_spawned_argv_not_merely_left_unlisted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Omitting a tool from --allowedTools does not withhold it; only deny does.

    ``--allowedTools`` is Claude Code's auto-approval list.  A tool absent
    from it remains available -- a project settings source or a permission
    mode can approve it -- which is how an ``--allow-host-home`` run that
    documented "Bash removed" still made five Bash calls against the real
    host HOME.  The guarantee has to be spelled on ``--disallowedTools``.
    """

    argv = _spawned_claude_argv(tmp_path, monkeypatch, allow_bash=False)

    denied = _flag_values(argv, "--disallowedTools")
    assert denied, "no --disallowedTools flag: an unlisted tool is not a denied tool"
    denied_tools = {tool for value in denied for tool in value.split(",")}
    assert {"Bash", "BashOutput", "KillShell"} <= denied_tools
    allowed_tools = {
        tool for value in _flag_values(argv, "--allowedTools") for tool in value.split(",")
    }
    assert "Bash" not in allowed_tools


def test_granting_bash_denies_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A normal run must not acquire a deny rule that blocks its own shell."""

    argv = _spawned_claude_argv(tmp_path, monkeypatch, allow_bash=True)

    denied_tools = {
        tool for value in _flag_values(argv, "--disallowedTools") for tool in value.split(",")
    }
    assert "Bash" not in denied_tools
    allowed_tools = {
        tool for value in _flag_values(argv, "--allowedTools") for tool in value.split(",")
    }
    assert "Bash" in allowed_tools


def _spawned_claude_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, str]:
    """Return the ``env=`` mapping the adapter really hands to ``Popen``."""

    claude = tmp_path / "claude"
    claude.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    claude.chmod(0o700)
    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir(exist_ok=True)
    fixture_dir = tmp_path / "fixture"
    fixture_dir.mkdir(exist_ok=True)
    mcp_config = tmp_path / "mcp.json"
    mcp_config.write_text("{}", encoding="utf-8")
    workspace = tmp_path / "agent"
    workspace.mkdir(exist_ok=True)
    monkeypatch.chdir(workspace)

    captured: dict[str, dict[str, str]] = {}

    class FakeProcess:
        stdout = None
        stderr = None
        stdin = None
        pid = 0

        def poll(self) -> int:
            return 0

    def fake_popen(command, **kwargs):
        captured["env"] = dict(kwargs["env"])
        return FakeProcess()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    adapter = ClaudeCodeAdapter(
        claude=claude,
        model="test",
        effort="low",
        plugin_dir=plugin_dir,
        repo_root=REPO_ROOT,
        fixture_dir=fixture_dir,
        artifact_dir=tmp_path / "artifacts",
        desktop_supervisor=Path("/usr/bin/true"),
        desktop_python=Path(sys.executable),
        claude_config_dir=None,
        timeout_s=5,
        max_budget_usd=None,
        append_system_prompt="test",
        allow_bash=False,
        mcp_config=mcp_config,
        allowed_tools="mcp__nxd-desktop__build_data_product",
    )
    adapter.start()
    return captured["env"]


def test_openai_key_is_stripped_from_the_spawned_agent_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The agent process must never inherit the operator driver's key.

    ``RunEnvironment.agent_environment`` withholds it by allowlist on the
    harness path, but this adapter is also runnable directly as
    ``python -m dp_scenarios.runner.claude_adapter``, and on that path the
    child would otherwise inherit the whole parent environment.
    """

    monkeypatch.setenv("OPENAI_API_KEY", "sk-live-operator-key")
    monkeypatch.setenv("DP_ADAPTER_ENV_CANARY", "present")

    environment = _spawned_claude_environment(tmp_path, monkeypatch)
    # Bind the names first and assert against those. Asserting against the
    # mapping renders every host environment *value* into pytest's failure
    # output -- in the one test whose whole subject is keeping a credential
    # out of a log.
    variable_names = set(environment)

    assert "OPENAI_API_KEY" not in variable_names
    assert all("sk-live-operator-key" not in value for value in environment.values())
    # The strip is targeted, not a blanket environment reset.
    assert environment["DP_ADAPTER_ENV_CANARY"] == "present"


def test_the_adapter_environment_is_unchanged_when_no_key_is_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("DP_ADAPTER_ENV_CANARY", "present")

    environment = _spawned_claude_environment(tmp_path, monkeypatch)
    variable_names = set(environment)

    assert "OPENAI_API_KEY" not in variable_names
    assert environment["DP_ADAPTER_ENV_CANARY"] == "present"


def test_oauth_token_reaches_claude_and_withholds_bash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "oauth-test-token")
    monkeypatch.setenv("DP_ADAPTER_ENV_CANARY", "present")

    environment = _spawned_claude_environment(tmp_path, monkeypatch)

    assert environment["CLAUDE_CODE_OAUTH_TOKEN"] == "oauth-test-token"
    assert environment["DP_ADAPTER_ENV_CANARY"] == "present"

    argv = _spawned_claude_argv(tmp_path, monkeypatch, allow_bash=True)
    denied = {tool for value in _flag_values(argv, "--disallowedTools") for tool in value.split(",")}
    assert {"Bash", "BashOutput", "KillShell"} <= denied
