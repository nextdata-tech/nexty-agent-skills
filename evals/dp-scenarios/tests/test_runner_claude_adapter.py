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
from collections.abc import Mapping

import pytest

from _repo_paths import REPO_ROOT

import dp_scenarios.runner.claude_adapter as adapter_module
from dp_scenarios.runner.claude_adapter import (
    ClaudeAdapterError,
    ClaudeCodeAdapter,
    _update_from_state_dir,
    _update_machine_artifacts,
    parse_claude_events,
)
from dp_scenarios.operator.transport import TouchedFile, ToolCall, TurnResult
from dp_scenarios.failure_reasons import (
    CHILD_EXITED_EARLY,
    CHILD_NO_TERMINAL_RESULT,
    PROVIDER_SESSION_LIMIT,
)
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


def test_parse_stream_events_preserves_exact_terminal_completion_facts() -> None:
    result, _ = parse_claude_events(
        [{"type": "result", "result": "done", "subtype": "success", "is_error": False}],
        redact_json_rpc=_identity,
        redact_text=lambda value: value,
        session_id="claude-session",
    )

    assert result.terminal_result_count == 1
    assert result.terminal_result_subtype == "success"
    assert result.terminal_result_is_error is False
    assert result.agent_message == "done"


def test_multiple_terminal_results_are_retained_as_ambiguous_completion_evidence() -> None:
    result, _ = parse_claude_events(
        [
            {"type": "result", "result": "first", "subtype": "success", "is_error": False},
            {"type": "result", "result": "second", "subtype": "success", "is_error": False},
        ],
        redact_json_rpc=_identity,
        redact_text=lambda value: value,
        session_id="claude-session",
    )

    assert result.terminal_result_count == 2


def test_real_build_result_shape_keeps_identity_while_redacting_bearer_values() -> None:
    def redact(value: object, *, key: str = "") -> object:
        if "bearer" in key.casefold():
            return "<redacted>"
        if isinstance(value, Mapping):
            return {str(name): redact(item, key=str(name)) for name, item in value.items()}
        if isinstance(value, list):
            return [redact(item, key=key) for item in value]
        return value

    events = [
        {
            "type": "assistant",
            "message": {"content": [{
                "type": "tool_use",
                "id": "build-1",
                "name": "mcp__nxd-desktop__build_data_product",
                "input": {"definition": "./closure"},
            }]},
        },
        {
            "type": "user",
            "message": {"content": [{
                "type": "tool_result",
                "tool_use_id": "build-1",
                "content": [{"type": "text", "text": json.dumps({
                    "run_id": "run-1",
                    "artifact_id": "artifact-1",
                    "bearer_token": "secret-value",
                })}],
            }]},
        },
        {"type": "result", "result": "done", "is_error": False},
    ]

    result, observations = parse_claude_events(
        events,
        redact_json_rpc=redact,
        redact_text=lambda value: value.replace("secret-value", "<redacted>"),
        session_id="claude-session",
    )

    assert observations[0]["result"] == {
        "run_id": "run-1",
        "artifact_id": "artifact-1",
        "bearer_token": "<redacted>",
    }
    assert "secret-value" not in json.dumps(turn_result_to_dict(result))


def test_default_prompt_describes_channels_and_review_dispatch_mechanics_not_scenario_conduct() -> None:
    prompt = adapter_module.DEFAULT_SYSTEM_PROMPT
    collapsed = " ".join(prompt.split())
    canonical_marker = (
        'NXD_REVIEW_DISPATCH {"closure_path":"closure",'
        '"request_contract":"sanitized_original_request",'
        '"return":"claims_only","review_round_index":0}'
    )

    assert "agent-attestations.json at your workspace root" in collapsed
    assert "a non-authoritative attestation channel" in collapsed
    assert "optional, non-authoritative attestation channel" not in collapsed
    assert "root JSON array (not an object wrapper)" in collapsed
    assert '"action_kind": "self_check"' in prompt
    assert '"review_round_index": 0' in prompt
    example = prompt.split("for example:\n", 1)[1].split("\nThe live self_check object", 1)[0]
    documented = json.loads(example)
    assert all("turn" not in value for value in documented)
    assert "legacy turn field may be included as informational metadata" in collapsed
    assert "review_round_index is a non-negative JSON integer, never a boolean" in collapsed
    assert "#self_check" in collapsed
    assert "#review_rounds/<review_round_index>" in collapsed
    assert "write the complete caller-authored typed proposal JSON" in collapsed
    assert "omitting source_hash" in collapsed
    assert "dp-blueprint.proposal.json" in collapsed
    assert "include the same object inline as typed_proposal" in collapsed
    assert "Only the returned session_decision consent action is approval" in collapsed
    assert "Supervisor capture materializes and verifies" in collapsed
    assert "dp-blueprint.proposal.approved.json" in collapsed
    assert "do not hand-author hashes" in collapsed
    assert "supervisor owns the canonical source_hash" in collapsed
    assert "Background execution is disabled" in collapsed
    assert prompt.splitlines().count(canonical_marker) == 1
    assert (
        "Replace only closure_path and review_round_index: use a relative closure path "
        "and the next zero-based index; keep the other constants unchanged."
    ) in collapsed
    assert "ask the operator for explicit approval" not in collapsed
    assert "do not report numeric or status results" not in collapsed
    assert "must not invoke Skill(nxd-review-closure)" not in collapsed
    assert "do not call Skill, Read, Glob, or another review tool" not in collapsed
    assert "[CREDENTIAL:" not in collapsed


def test_default_prompt_documents_the_bounded_review_report_protocol() -> None:
    prompt = adapter_module.DEFAULT_SYSTEM_PROMPT
    collapsed = " ".join(prompt.split())

    for phrase in (
        "rich review ledger in the job-level review-record.json",
        "action.parameters.report",
        '"schema": "nxd-conversation-review-v1"',
        '"verdict": "clear"',
        '"findings": []',
        '"rejection_code": null',
        "clear has an empty findings list and no rejection code",
        "findings has one or more projected findings and no rejection code",
        'rejected has an empty findings list and uses rejection_code: "scope_refused"',
        "indeterminate has no rejection code and may preserve bounded partial findings",
        'exactly {"id", "severity", "description"}',
        "HIGH or MEDIUM claims to blocking",
        "LOW claims to advisory",
        'report severity values must be the lowercase wire literals "blocking" or "advisory"',
        "never send reviewer values HIGH, MEDIUM, or LOW",
        "Never send claims, high_severity_count, or outcome directly",
        "action.parameters",
        "requirement_id, generation, subject_sha256, dependency_evidence_sha256, and session_ref as siblings of report",
        "do not put those binding fields inside report",
        "values returned by the supervisor",
        "supervisor derives evidence identity from its current binding",
        "caller-provided claims are not execution authority",
    ):
        assert phrase in collapsed

    report_example = prompt.split(
        "That value must be an object with exactly this\nschema and no other keys:\n",
        1,
    )[1].split("\nUse these exact combinations:", 1)[0]
    assert json.loads(report_example) == {
        "schema": "nxd-conversation-review-v1",
        "verdict": "clear",
        "findings": [],
        "rejection_code": None,
    }
    assert "claims, high_severity_count, or outcome" in collapsed
    assert "hidden gold" not in collapsed
    assert "ask the operator for explicit approval" not in collapsed
    assert "do not report numeric or status results" not in collapsed


def test_default_prompt_returns_control_after_non_clear_review_reports() -> None:
    prompt = adapter_module.DEFAULT_SYSTEM_PROMPT
    collapsed = " ".join(prompt.split())

    assert (
        "After a report_requirement result, inspect its report verdict before using the "
        "returned next_actions. For findings, rejected, or indeterminate, relay the "
        "bounded report to the operator and return control for user adjudication."
    ) in collapsed
    assert (
        "In that same turn, do not reset, edit the closure, recapture, re-review, "
        "validate, admit, or start_run."
    ) in collapsed
    assert "Only a clear report permits following the returned next_actions toward validation and admission" in collapsed
    assert "not permission to auto-fix" in collapsed
    assert "never turn claims into permission or suppress the findings" in collapsed


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
        _start_run_observation(
            "run-6", "artifact-6", workflow="parent-child-grain-trap"
        ),
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
        "rows": [{"region": "north", "regional_revenue": 10.0}],
        "queries": [{
            "columns": ["region", "regional_revenue"],
            "rows": [{"region": "north", "regional_revenue": 10.0}],
        }],
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
        timeout_s=5.0,
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
    adapter._last_mcp_call = None
    adapter._lifecycles = {}
    adapter._built_runs = set()
    adapter._query_history = []
    adapter._state_dir = None
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
    supervisor_data_dir: Path | None = None,
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
    if supervisor_data_dir is None:
        supervisor_data_dir = tmp_path / "desktop-state"
    supervisor_data_dir.mkdir(exist_ok=True)
    (supervisor_data_dir / "captures").mkdir(exist_ok=True)
    (supervisor_data_dir / "blueprints").mkdir(exist_ok=True)
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
        supervisor_data_dir=supervisor_data_dir,
    )
    adapter.start()
    return captured["argv"]


def test_spawned_claude_can_read_only_supervisor_retained_content_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    supervisor_data_dir = tmp_path / "desktop-state"
    argv = _spawned_claude_argv(
        tmp_path,
        monkeypatch,
        allow_bash=False,
        supervisor_data_dir=supervisor_data_dir,
    )

    add_dirs = [Path(value) for value in _flag_values(argv, "--add-dir")]
    assert add_dirs[-2:] == [
        supervisor_data_dir / "captures",
        supervisor_data_dir / "blueprints",
    ]
    assert supervisor_data_dir not in add_dirs


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
    # Delegation is deliberately NOT denied with the shell. Withholding it
    # withheld the mechanism nxd-generate-data-product step 6b mandates -- a
    # read-only nxd-review-closure subagent -- which gate_construction then
    # graded as an agent failure, making that gate unpassable on every
    # OAuth run. Safe because the shell denial is inherited: a Task subagent
    # under this argv cannot reach Bash (verified against the CLI, with a
    # control that succeeded when Bash was permitted).
    # Delegation itself stays available -- step 6b needs it -- but the
    # background-child plumbing does not: subagents now run inline.
    assert not ({"Task", "Agent"} & denied_tools)
    assert {"TaskOutput", "TaskStop"} <= denied_tools
    allowed_tools = {
        tool for value in _flag_values(argv, "--allowedTools") for tool in value.split(",")
    }
    assert "Bash" not in allowed_tools


@pytest.mark.parametrize("allow_bash", [False, True])
def test_session_tools_are_denied_on_spawned_argv_for_both_bash_branches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    allow_bash: bool,
) -> None:
    """Session tools are denied by the actual CLI flag, not tuple membership."""

    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    argv = _spawned_claude_argv(tmp_path, monkeypatch, allow_bash=allow_bash)
    denied = {
        tool for value in _flag_values(argv, "--disallowedTools") for tool in value.split(",")
    }

    from dp_scenarios.runner.claude_adapter import SESSION_TOOLS, SHELL_TOOLS

    assert set(SESSION_TOOLS) <= denied
    if allow_bash:
        assert not (set(SHELL_TOOLS) & denied)
    else:
        assert set(SHELL_TOOLS) <= denied


def test_spawned_claude_receives_run_scoped_review_guard_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    argv = _spawned_claude_argv(tmp_path, monkeypatch, allow_bash=False)
    settings_paths = _flag_values(argv, "--settings")
    assert len(settings_paths) == 1
    assert Path(settings_paths[0]).name == "settings.json"
    assert "--include-hook-events" in argv
    assert "--forward-subagent-text" in argv


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
    supervisor_data_dir = tmp_path / "desktop-state"
    supervisor_data_dir.mkdir(exist_ok=True)
    (supervisor_data_dir / "captures").mkdir(exist_ok=True)
    (supervisor_data_dir / "blueprints").mkdir(exist_ok=True)
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
        supervisor_data_dir=supervisor_data_dir,
    )
    adapter.start()
    return captured["env"]


def test_mcp_config_requires_supervisor_data_dir_before_spawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    claude = tmp_path / "claude"
    claude.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    claude.chmod(0o700)
    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir()
    fixture_dir = tmp_path / "fixture"
    fixture_dir.mkdir()
    mcp_config = tmp_path / "mcp.json"
    mcp_config.write_text("{}\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

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
        mcp_config=mcp_config,
    )

    with pytest.raises(ClaudeAdapterError, match="supervisor-data-dir"):
        adapter.start()


def test_external_supervisor_data_dir_must_already_have_retained_input_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    claude = tmp_path / "claude"
    claude.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    claude.chmod(0o700)
    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir()
    fixture_dir = tmp_path / "fixture"
    fixture_dir.mkdir()
    mcp_config = tmp_path / "mcp.json"
    mcp_config.write_text("{}\n", encoding="utf-8")
    supervisor_data_dir = tmp_path / "desktop-state"
    supervisor_data_dir.mkdir()
    monkeypatch.chdir(tmp_path)

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
        mcp_config=mcp_config,
        supervisor_data_dir=supervisor_data_dir,
    )

    with pytest.raises(ClaudeAdapterError, match="captures.*blueprints"):
        adapter.start()


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
    assert environment["CLAUDE_CODE_DISABLE_BACKGROUND_TASKS"] == "1"
    assert environment["NXD_EVAL_REVIEW_GUARD_STATE"].endswith("/state.json")


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

    # An OAuth token forces the shell off even when the caller asked for it,
    # because the token lives in this process's environment.
    argv = _spawned_claude_argv(tmp_path, monkeypatch, allow_bash=True)
    denied = {tool for value in _flag_values(argv, "--disallowedTools") for tool in value.split(",")}
    assert {"Bash", "BashOutput", "KillShell"} <= denied
    # Delegation stays available: the deny list is inherited by subagents, so
    # Task cannot be used to reach the shell or the token behind it.
    assert not ({"Task", "Agent"} & denied)


def _adapter_against(fake_claude: Path, tmp_path: Path, *, timeout_s: float) -> ClaudeCodeAdapter:
    """Build an adapter whose only real child is ``fake_claude``."""

    fake_claude.chmod(0o700)
    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir(exist_ok=True)
    fixture_dir = tmp_path / "fixture"
    fixture_dir.mkdir(exist_ok=True)
    supervisor_data_dir = tmp_path / "desktop-state"
    supervisor_data_dir.mkdir(exist_ok=True)
    (supervisor_data_dir / "captures").mkdir(exist_ok=True)
    (supervisor_data_dir / "blueprints").mkdir(exist_ok=True)
    return ClaudeCodeAdapter(
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
        timeout_s=timeout_s,
        max_budget_usd=None,
        append_system_prompt="test",
        mcp_config=tmp_path / "mcp.json",
        supervisor_data_dir=supervisor_data_dir,
    )


def _write_review_deadline_fake(path: Path, *, mode: str) -> None:
    """Create a child that changes only the runner-owned guard fixture."""

    path.write_text(
        f"#!{sys.executable}\n"
        """
import json
import os
from pathlib import Path
import signal
import sys
import time

MODE = __MODE__

def set_guard_state(state):
    path = Path(os.environ["NXD_EVAL_REVIEW_GUARD_STATE"])
    value = json.loads(path.read_text(encoding="utf-8"))
    value.update({"state": state, "review_tool_use_id": "review-accepted"})
    path.write_text(json.dumps(value), encoding="utf-8")

def set_completed_state():
    path = Path(os.environ["NXD_EVAL_REVIEW_GUARD_STATE"])
    value = json.loads(path.read_text(encoding="utf-8"))
    value.update({"state": "normal", "completed_review_tool_use_id": "review-accepted"})
    value.pop("review_tool_use_id", None)
    path.write_text(json.dumps(value), encoding="utf-8")

if MODE == "late_provider":
    def write_provider_limit_and_exit(_signum, _frame):
        sys.stderr.write("Claude usage limit reached. Your limit will reset later.\\n")
        sys.stderr.flush()
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, write_provider_limit_and_exit)

for line in sys.stdin:
    json.loads(line)
    set_guard_state("review_dispatch_pending")
    print(json.dumps({"type": "assistant", "message": {"content": [
        {"type": "text", "text": "reviewer activity"}
    ]}}), flush=True)
    if MODE == "active":
        for index in range(20):
            print(json.dumps({"type": "assistant", "message": {"content": [
                {"type": "text", "text": f"inspection-{index}"}
            ]}}), flush=True)
            time.sleep(0.03)
        time.sleep(600)
    elif MODE == "complete":
        time.sleep(0.05)
        set_guard_state("relay_pending")
        print(json.dumps({"type": "result", "result": "review complete", "is_error": False}), flush=True)
    elif MODE == "report_in_flight":
        time.sleep(0.05)
        set_guard_state("report_in_flight")
        print(json.dumps({"type": "result", "result": "review reported", "is_error": False}), flush=True)
    elif MODE == "normal_after_completion":
        time.sleep(0.05)
        set_completed_state()
        print(json.dumps({"type": "result", "result": "review finalized", "is_error": False}), flush=True)
    else:
        time.sleep(600)
        """.replace("__MODE__", json.dumps(mode)).strip()
        + "\n",
        encoding="utf-8",
    )


def _run_review_deadline_fake(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    mode: str,
    stderr: str | None = None,
    timeout_s: float = 2.0,
) -> tuple[ClaudeCodeAdapter, TurnResult]:
    fake_claude = tmp_path / f"review-{mode}-fake-claude.py"
    _write_review_deadline_fake(fake_claude, mode=mode)
    if stderr is not None:
        fake_claude.write_text(
            fake_claude.read_text(encoding="utf-8").replace(
                '    set_guard_state("review_dispatch_pending")',
                f'    sys.stderr.write({stderr!r} + "\\n")\n'
                '    sys.stderr.flush()\n'
                '    set_guard_state("review_dispatch_pending")',
            ),
            encoding="utf-8",
        )
    (tmp_path / "mcp.json").write_text("{}", encoding="utf-8")
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    monkeypatch.chdir(agent_dir)
    adapter = _adapter_against(fake_claude, tmp_path, timeout_s=timeout_s)
    result = adapter.send({"type": "turn", "message": {"text": "hello", "attachments": []}})
    return adapter, result


def test_ordinary_quiet_stream_waits_past_a_polling_slice_and_returns_normally(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_claude = tmp_path / "quiet-fake-claude.py"
    fake_claude.write_text(
        f"#!{sys.executable}\n"
        """
import json
import sys
import time

for line in sys.stdin:
    json.loads(line)
    time.sleep(0.35)
    print(json.dumps({"type": "result", "result": "quiet complete", "is_error": False}), flush=True)
        """.strip()
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "mcp.json").write_text("{}", encoding="utf-8")
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    monkeypatch.chdir(agent_dir)
    adapter = _adapter_against(fake_claude, tmp_path, timeout_s=0.8)

    started = time.monotonic()
    try:
        result = adapter.send({"type": "turn", "message": {"text": "hello", "attachments": []}})
    finally:
        adapter.close()

    assert time.monotonic() - started >= 0.3
    assert result.turn_timed_out is False
    assert result.agent_message == "quiet complete"


def test_accepted_review_dispatch_uses_a_silent_child_deadline_and_reaps_the_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(adapter_module, "REVIEW_DEADLINE_MS", 200)
    started = time.monotonic()
    adapter, result = _run_review_deadline_fake(tmp_path, monkeypatch, mode="silent")

    assert 0.15 <= time.monotonic() - started < 1.5
    assert result.turn_timed_out is True
    assert result.environment_wedged is False
    assert result.failure_reason == CHILD_NO_TERMINAL_RESULT
    assert "reviewer activity" in result.transcript_delta
    assert adapter._process is None
    adapter.close()


def test_outer_deadline_beats_a_still_pending_reviewer_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(adapter_module, "REVIEW_DEADLINE_MS", 1_000)
    started = time.monotonic()
    adapter, result = _run_review_deadline_fake(
        tmp_path,
        monkeypatch,
        mode="silent",
        timeout_s=0.3,
    )

    assert time.monotonic() - started >= 0.25
    assert result.turn_timed_out is True
    assert result.failure_reason == CHILD_NO_TERMINAL_RESULT
    assert "Claude did not complete the turn within 0.3s" in (result.environment_detail or "")
    assert "retained-capture reviewer" not in (result.environment_detail or "")
    adapter.close()


def test_review_inspection_activity_does_not_extend_the_accepted_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(adapter_module, "REVIEW_DEADLINE_MS", 200)
    started = time.monotonic()
    adapter, result = _run_review_deadline_fake(tmp_path, monkeypatch, mode="active")

    assert 0.15 <= time.monotonic() - started < 1.5
    assert result.turn_timed_out is True
    assert result.environment_wedged is False
    assert result.failure_reason == CHILD_NO_TERMINAL_RESULT
    assert "inspection-0" in result.transcript_delta
    assert adapter._process is None
    adapter.close()


def test_review_completion_disarms_the_deadline_and_returns_normally(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(adapter_module, "REVIEW_DEADLINE_MS", 200)
    adapter, result = _run_review_deadline_fake(tmp_path, monkeypatch, mode="complete")
    try:
        assert result.turn_timed_out is False
        assert result.environment_wedged is False
        assert result.terminal_result_count == 1
        assert result.agent_message == "review complete"
    finally:
        adapter.close()


@pytest.mark.parametrize(
    ("mode", "message"),
    (
        ("report_in_flight", "review reported"),
        ("normal_after_completion", "review finalized"),
    ),
)
def test_valid_post_dispatch_guard_states_disarm_before_a_terminal_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    message: str,
) -> None:
    monkeypatch.setattr(adapter_module, "REVIEW_DEADLINE_MS", 200)
    adapter, result = _run_review_deadline_fake(tmp_path, monkeypatch, mode=mode)
    try:
        assert result.turn_timed_out is False
        assert result.agent_message == message
        assert adapter._review_deadline_at is None
    finally:
        adapter.close()


def test_provider_reason_wins_when_the_accepted_review_deadline_expires(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(adapter_module, "REVIEW_DEADLINE_MS", 200)
    adapter, result = _run_review_deadline_fake(
        tmp_path,
        monkeypatch,
        mode="silent",
        stderr="Claude usage limit reached. Your limit will reset later.",
    )
    try:
        assert result.turn_timed_out is True
        assert result.environment_wedged is False
        assert result.failure_reason == PROVIDER_SESSION_LIMIT
    finally:
        adapter.close()


def test_late_provider_stderr_during_reap_beats_generic_review_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(adapter_module, "REVIEW_DEADLINE_MS", 200)
    adapter, result = _run_review_deadline_fake(
        tmp_path,
        monkeypatch,
        mode="late_provider",
    )
    try:
        assert result.turn_timed_out is True
        assert result.failure_reason == PROVIDER_SESSION_LIMIT
    finally:
        adapter.close()


def test_eof_before_either_deadline_is_child_exited_early(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_claude = tmp_path / "eof-fake-claude.py"
    fake_claude.write_text(
        f"#!{sys.executable}\n"
        """
import json
import sys

for line in sys.stdin:
    json.loads(line)
    print(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "partial"}]}}), flush=True)
    break
        """.strip()
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "mcp.json").write_text("{}", encoding="utf-8")
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    monkeypatch.chdir(agent_dir)
    adapter = _adapter_against(fake_claude, tmp_path, timeout_s=0.8)

    try:
        result = adapter.send({"type": "turn", "message": {"text": "hello", "attachments": []}})
    finally:
        adapter.close()

    assert result.turn_timed_out is False
    assert result.failure_reason == CHILD_EXITED_EARLY
    assert "partial" in result.transcript_delta


def test_zero_event_eof_is_typed_early_exit_and_reaps_the_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_claude = tmp_path / "zero-event-eof-fake-claude.py"
    fake_claude.write_text(
        f"#!{sys.executable}\n"
        """
import sys

sys.stdin.readline()
raise SystemExit(3)
        """.strip()
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "mcp.json").write_text("{}", encoding="utf-8")
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    monkeypatch.chdir(agent_dir)
    adapter = _adapter_against(fake_claude, tmp_path, timeout_s=0.8)

    result = adapter.send({"type": "turn", "message": {"text": "hello", "attachments": []}})

    assert result.turn_timed_out is False
    assert result.failure_reason == CHILD_EXITED_EARLY
    assert adapter._process is None
    adapter.close()


def test_unreadable_guard_snapshot_cannot_reset_an_armed_reviewer_deadline(
    tmp_path: Path
) -> None:
    fake_claude = tmp_path / "unused-fake-claude.py"
    fake_claude.write_text(f"#!{sys.executable}\n", encoding="utf-8")
    (tmp_path / "mcp.json").write_text("{}", encoding="utf-8")
    adapter = _adapter_against(fake_claude, tmp_path, timeout_s=2.0)
    state = tmp_path / "review-state.json"
    adapter._review_guard_state = state
    state.write_text(
        json.dumps(
            {
                "version": 1,
                "state": "review_dispatch_pending",
                "review_tool_use_id": "accepted-review",
            }
        ),
        encoding="utf-8",
    )

    started = 100.0
    initial = adapter._refresh_review_deadline(started)
    armed_at = adapter._review_deadline_at
    assert initial is not None and armed_at is not None
    state.write_text('{"version":', encoding="utf-8")

    preserved = adapter._refresh_review_deadline(started + 0.1)
    assert preserved is not None
    assert adapter._review_deadline_at == armed_at
    state.write_text(
        json.dumps(
            {
                "version": 1,
                "state": "report_in_flight",
                "review_tool_use_id": "accepted-review",
            }
        ),
        encoding="utf-8",
    )
    assert adapter._refresh_review_deadline(started + 0.2) is None

    state.write_text(
        json.dumps(
            {
                "version": 1,
                "state": "review_dispatch_pending",
                "review_tool_use_id": "accepted-review",
            }
        ),
        encoding="utf-8",
    )
    assert adapter._refresh_review_deadline(started + 0.3) is not None
    state.write_text(
        json.dumps(
            {
                "version": 1,
                "state": "normal",
                "completed_review_tool_use_id": "accepted-review",
            }
        ),
        encoding="utf-8",
    )
    assert adapter._refresh_review_deadline(started + 0.4) is None


def test_new_pending_reviewer_id_cannot_restart_absolute_deadline(tmp_path: Path) -> None:
    fake_claude = tmp_path / "unused-fake-claude.py"
    fake_claude.write_text(f"#!{sys.executable}\n", encoding="utf-8")
    (tmp_path / "mcp.json").write_text("{}", encoding="utf-8")
    adapter = _adapter_against(fake_claude, tmp_path, timeout_s=2.0)
    state = tmp_path / "review-state.json"
    adapter._review_guard_state = state
    state.write_text(
        json.dumps(
            {
                "version": 1,
                "state": "review_dispatch_pending",
                "review_tool_use_id": "accepted-review",
            }
        ),
        encoding="utf-8",
    )

    started = 100.0
    assert adapter._refresh_review_deadline(started) is not None
    armed_at = adapter._review_deadline_at
    assert armed_at is not None

    state.write_text(
        json.dumps(
            {
                "version": 1,
                "state": "review_dispatch_pending",
                "review_tool_use_id": "different-review",
            }
        ),
        encoding="utf-8",
    )
    assert adapter._refresh_review_deadline(started + 0.1) is not None
    assert adapter._review_deadline_at == armed_at
    assert adapter._review_deadline_id == "accepted-review"

    state.write_text(
        json.dumps(
            {
                "version": 1,
                "state": "report_in_flight",
                "review_tool_use_id": "accepted-review",
            }
        ),
        encoding="utf-8",
    )
    assert adapter._refresh_review_deadline(started + 0.2) is None
    adapter.close()


def test_new_capture_without_a_reviewer_id_disarms_the_previous_deadline(
    tmp_path: Path,
) -> None:
    fake_claude = tmp_path / "unused-fake-claude.py"
    fake_claude.write_text(f"#!{sys.executable}\n", encoding="utf-8")
    (tmp_path / "mcp.json").write_text("{}", encoding="utf-8")
    adapter = _adapter_against(fake_claude, tmp_path, timeout_s=2.0)
    state = tmp_path / "review-state.json"
    adapter._review_guard_state = state
    state.write_text(
        json.dumps(
            {
                "version": 1,
                "state": "review_dispatch_pending",
                "review_tool_use_id": "accepted-review",
            }
        ),
        encoding="utf-8",
    )

    started = 100.0
    assert adapter._refresh_review_deadline(started) is not None
    state.write_text(
        json.dumps({"version": 1, "state": "review_dispatch_pending"}),
        encoding="utf-8",
    )
    assert adapter._refresh_review_deadline(started + 0.1) is None
    assert adapter._review_deadline_id is None
    assert adapter._review_deadline_at is None
    adapter.close()


def test_cleanup_kills_a_term_ignoring_descendant_after_its_leader_exits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_claude = tmp_path / "term-ignoring-child-fake-claude.py"
    fake_claude.write_text(
        f"#!{sys.executable}\n"
        """
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

def exit_leader(_signum, _frame):
    raise SystemExit(0)

signal.signal(signal.SIGTERM, exit_leader)
for line in sys.stdin:
    json.loads(line)
    child = subprocess.Popen([
        sys.executable,
        "-c",
        "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(600)",
    ])
    Path("child.pid").write_text(str(child.pid), encoding="utf-8")
    print(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "child launched"}]}}), flush=True)
    time.sleep(600)
        """.strip()
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "mcp.json").write_text("{}", encoding="utf-8")
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    monkeypatch.chdir(agent_dir)
    # Allow interpreter startup plus child creation before exercising group
    # teardown; the assertion concerns post-SIGTERM cleanup, not startup.
    adapter = _adapter_against(fake_claude, tmp_path, timeout_s=0.8)

    result = adapter.send({"type": "turn", "message": {"text": "hello", "attachments": []}})
    child_pid = int((agent_dir / "child.pid").read_text(encoding="utf-8"))

    assert result.turn_timed_out is True
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.02)
    else:
        pytest.fail("term-ignoring descendant survived adapter group cleanup")
    adapter.close()


def test_review_timeout_keeps_partial_events_without_forging_review_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(adapter_module, "REVIEW_DEADLINE_MS", 200)
    adapter, result = _run_review_deadline_fake(tmp_path, monkeypatch, mode="silent")
    try:
        assert result.turn_timed_out is True
        assert result.reported is False
        assert result.tool_results == ()
        assert not (tmp_path / "artifacts" / "review-record.json").exists()
        assert not (tmp_path / "artifacts" / "agent-attestations.json").exists()
    finally:
        adapter.close()


def test_a_child_that_stalls_past_the_deadline_names_the_missing_terminal_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The deadline already existed; the structured reason did not.

    Without it a stalled child and a Claude account that refused another turn
    produce the same report, which is exactly the confusion issue #238 is
    about.
    """

    fake_claude = tmp_path / "stalling-fake-claude.py"
    fake_claude.write_text(
        f"#!{sys.executable}\n"
        """
import json
import sys
import time

for line in sys.stdin:
    json.loads(line)
    print(json.dumps({"type": "assistant", "message": {"content": [
        {"type": "text", "text": "thinking"}
    ]}}), flush=True)
    time.sleep(600)
        """.strip()
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "mcp.json").write_text("{}", encoding="utf-8")
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    monkeypatch.chdir(agent_dir)
    adapter = _adapter_against(fake_claude, tmp_path, timeout_s=2.0)

    try:
        result = adapter.send({"type": "turn", "message": {"text": "hello", "attachments": []}})
    finally:
        adapter.close()

    assert result.turn_timed_out is True
    assert result.failure_reason == CHILD_NO_TERMINAL_RESULT
    # The partial turn is still retained: the reason explains the stop, it
    # does not replace the evidence.
    assert "thinking" in result.transcript_delta


def test_a_provider_ceiling_on_the_childs_stderr_outranks_a_bare_stall(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_claude = tmp_path / "limited-fake-claude.py"
    fake_claude.write_text(
        f"#!{sys.executable}\n"
        """
import json
import sys
import time

for line in sys.stdin:
    json.loads(line)
    sys.stderr.write("Claude usage limit reached. Your limit will reset at 4pm.\\n")
    sys.stderr.flush()
    time.sleep(600)
        """.strip()
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "mcp.json").write_text("{}", encoding="utf-8")
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    monkeypatch.chdir(agent_dir)
    adapter = _adapter_against(fake_claude, tmp_path, timeout_s=2.0)

    try:
        result = adapter.send({"type": "turn", "message": {"text": "hello", "attachments": []}})
    finally:
        adapter.close()

    assert result.turn_timed_out is True
    assert result.failure_reason == PROVIDER_SESSION_LIMIT


def test_the_last_mcp_call_is_retained_on_the_turn_that_stopped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """"Where did it get to" is the first question about an incomplete run."""

    fake_claude = tmp_path / "mcp-then-stall-fake-claude.py"
    fake_claude.write_text(
        f"#!{sys.executable}\n"
        """
import json
import sys
import time

for line in sys.stdin:
    json.loads(line)
    print(json.dumps({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": "b1", "name": "mcp__nxd-desktop__build_data_product", "input": {}}
    ]}}), flush=True)
    print(json.dumps({"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": "b1", "is_error": True, "content": "boom"}
    ]}}), flush=True)
    time.sleep(600)
        """.strip()
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "mcp.json").write_text("{}", encoding="utf-8")
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    monkeypatch.chdir(agent_dir)
    adapter = _adapter_against(fake_claude, tmp_path, timeout_s=2.0)

    try:
        result = adapter.send({"type": "turn", "message": {"text": "hello", "attachments": []}})
    finally:
        adapter.close()

    assert result.turn_timed_out is True
    assert result.last_mcp_call == "build_data_product:error"


# --------------------------------------------------------------------------
# Harvesting supervisor evidence from the shapes the real supervisor sends.
#
# Every payload below is the shape captured from a live crm-pipeline run on
# 2026-09-05, where the agent built, published release 6 and queried
# successfully, and the harness still graded build and query "not examined"
# because it could not read either answer.


def _observation(tool: str, content: object, *, arguments: object = None, is_error: bool = False) -> dict[str, object]:
    return {"tool": tool, "arguments": arguments or {}, "result": content, "is_error": is_error}


def _start_run_observation(
    run_id: str,
    artifact_id: str,
    *,
    workflow: str = "crm-deals-pipeline",
) -> dict[str, object]:
    return _observation(
        "advance_workflow",
        {
            "workflow": workflow,
            "admission": {"run_id": run_id, "artifact_id": artifact_id},
        },
        arguments={
            "workflow": workflow,
            "action": {
                "type": "start_run",
                "parameters": {"expected_invalidation_epoch": 0},
            },
        },
    )


def _verified_release(*, run_id: str, artifact_id: str, publish_seq: int, counts: dict[str, int]) -> dict[str, object]:
    """The resource payload the supervisor labels ``artifact_verified``."""

    document = {
        "schema": "nxd-desktop-verified-v1",
        "trust": "artifact_verified",
        "release": {
            "workflow": "crm-deals-pipeline",
            "publish_seq": publish_seq,
            "run_id": run_id,
            "artifact_id": artifact_id,
        },
        "evidence": {
            "model_tables": [
                {"dataset": dataset_table.split(".")[0], "table": dataset_table.split(".")[1], "row_count": count}
                for dataset_table, count in counts.items()
            ]
        },
    }
    return {"contents": [{"mimeType": "text", "text": json.dumps(document), "uri": "nxd://x"}]}


def _harvest(observations: list[dict[str, object]], tmp_path: Path) -> tuple[dict[str, object], Path]:
    facts: dict[str, object] = {}
    _update_machine_artifacts(observations, artifact_dir=tmp_path, facts=facts, build_context={})
    return facts, tmp_path


def test_positional_query_rows_are_read_through_their_column_header(tmp_path: Path) -> None:
    """The supervisor answers with positional rows, not a list of objects.

    Requiring mappings discarded every row of a query that had run correctly,
    and the query gate then read not-examined no matter what the agent did.
    """

    _harvest(
        [
            _observation(
                "run_semantic_query",
                {
                    "columns": ["stage", "status", "deal_count", "total_amount"],
                    "rows": [["closed_won", "active", 1, 72300.0], ["prospecting", "active", 1, 9100.0]],
                    "row_count": 2,
                },
            )
        ],
        tmp_path,
    )

    written = json.loads((tmp_path / "query-results.json").read_text(encoding="utf-8"))
    assert written == {
        "rows": [
            {"stage": "closed_won", "status": "active", "deal_count": 1, "total_amount": 72300.0},
            {"stage": "prospecting", "status": "active", "deal_count": 1, "total_amount": 9100.0},
        ],
        "queries": [{
            "columns": ["stage", "status", "deal_count", "total_amount"],
            "rows": [
                {"stage": "closed_won", "status": "active", "deal_count": 1, "total_amount": 72300.0},
                {"stage": "prospecting", "status": "active", "deal_count": 1, "total_amount": 9100.0},
            ],
        }],
    }


def test_mapping_query_rows_are_still_accepted(tmp_path: Path) -> None:
    """The replay fixtures send objects; both shapes have to keep working."""

    _harvest([_observation("run_semantic_query", {"rows": [{"stage": "closed_won", "n": 1}]})], tmp_path)

    assert json.loads((tmp_path / "query-results.json").read_text(encoding="utf-8")) == {
        "rows": [{"stage": "closed_won", "n": 1}],
        "queries": [{"columns": ["stage", "n"], "rows": [{"stage": "closed_won", "n": 1}]}],
    }


def test_a_row_that_does_not_fit_its_header_is_dropped_rather_than_zipped(tmp_path: Path) -> None:
    """Truncating to the shorter side would invent a row the supervisor never sent."""

    _harvest(
        [_observation("run_semantic_query", {"columns": ["a", "b", "c"], "rows": [["only", "two"]]})],
        tmp_path,
    )

    assert not (tmp_path / "query-results.json").exists()


def test_supervisor_facts_come_from_the_verified_release_the_agent_published(tmp_path: Path) -> None:
    """``list_data_products`` answered ``{"products": []}`` while release 6 existed.

    The verified release resource is the only payload carrying the published
    identifiers and the per-model row counts together, so the build gate has
    to be able to read it.
    """

    facts, _ = _harvest(
        [
            _start_run_observation("run-701f", "artifact-cdb6"),
            _observation("inspect_run", {"run": {"run_id": "run-701f", "lifecycle": "terminal"}}),
            _observation(
                "read_data_product_resource",
                _verified_release(run_id="run-701f", artifact_id="artifact-cdb6", publish_seq=6, counts={"main.deals": 6, "main.nxd_decisions": 2}),
            ),
        ],
        tmp_path,
    )

    assert json.loads((tmp_path / "supervisor-facts.json").read_text(encoding="utf-8")) == {
        "run_id": "run-701f",
        "artifact_id": "artifact-cdb6",
        "publish_sequence": "6",
        "lifecycle_state": "terminal",
        "per_model_row_counts": {"main.deals": "6", "main.nxd_decisions": "2"},
    }
    assert facts["publish_sequence"] == "6"


def test_workflow_start_run_supplies_the_published_run_identity(tmp_path: Path) -> None:
    facts, _ = _harvest(
        [
            _observation(
                "advance_workflow",
                {
                    "workflow": "crm-deals-pipeline",
                    "admission": {
                        "run_id": "run-v2",
                        "artifact_id": "artifact-v2",
                    },
                },
                arguments={
                    "workflow": "crm-deals-pipeline",
                    "action": {
                        "type": "start_run",
                        "parameters": {"expected_invalidation_epoch": 0},
                    },
                },
            ),
            _observation(
                "inspect_run",
                {"run": {"run_id": "run-v2", "lifecycle": "terminal"}},
            ),
            _observation(
                "read_data_product_resource",
                _verified_release(
                    run_id="run-v2",
                    artifact_id="artifact-v2",
                    publish_seq=8,
                    counts={"main.deals": 6},
                ),
            ),
        ],
        tmp_path,
    )

    assert facts == {
        "run_id": "run-v2",
        "artifact_id": "artifact-v2",
        "publish_sequence": "8",
        "lifecycle_state": "terminal",
        "per_model_row_counts": {"main.deals": "6"},
    }


def test_a_release_from_a_run_this_session_never_built_is_refused(tmp_path: Path) -> None:
    """Attribution is the whole point: a leftover release must not supply facts.

    Without this a stale artifact from an abandoned job could hand the build
    gate identifiers and row counts the agent never produced.
    """

    _harvest(
        [
            _observation("inspect_run", {"run": {"run_id": "run-mine", "lifecycle": "terminal"}}),
            _observation(
                "read_data_product_resource",
                _verified_release(run_id="run-someone-else", artifact_id="artifact-stale", publish_seq=9, counts={"main.deals": 999}),
            ),
        ],
        tmp_path,
    )

    assert not (tmp_path / "supervisor-facts.json").exists()


def test_the_highest_publish_sequence_wins_when_several_releases_are_read(tmp_path: Path) -> None:
    """An earlier release is a superseded attempt, not the shipped product."""

    facts, _ = _harvest(
        [
            _start_run_observation("run-a", "artifact-a"),
            _start_run_observation("run-b", "artifact-b"),
            _observation("inspect_run", {"run": {"run_id": "run-b", "lifecycle": "terminal"}}),
            _observation("read_data_product_resource", _verified_release(run_id="run-b", artifact_id="artifact-b", publish_seq=7, counts={"main.deals": 6})),
            _observation("read_data_product_resource", _verified_release(run_id="run-a", artifact_id="artifact-a", publish_seq=5, counts={"main.deals": 4})),
        ],
        tmp_path,
    )

    assert facts["publish_sequence"] == "7"
    assert facts["per_model_row_counts"] == {"main.deals": "6"}


def test_an_errored_resource_read_contributes_nothing(tmp_path: Path) -> None:
    _harvest(
        [
            _start_run_observation("run-a", "artifact-a"),
            _observation("inspect_run", {"run": {"run_id": "run-a", "lifecycle": "terminal"}}),
            _observation(
                "read_data_product_resource",
                _verified_release(run_id="run-a", artifact_id="artifact-a", publish_seq=6, counts={"main.deals": 6}),
                is_error=True,
            ),
        ],
        tmp_path,
    )

    assert not (tmp_path / "supervisor-facts.json").exists()


def test_a_query_that_matched_nothing_is_an_answer_not_an_unreadable_payload(tmp_path: Path) -> None:
    """Zero rows is a documented outcome of a filtered query.

    Rejecting it put the run back in the not-examined state this reader exists
    to remove -- and for a scenario whose gold answer set is itself empty it
    would turn a pass into an ungraded run.
    """

    _harvest([_observation("run_semantic_query", {"columns": ["stage"], "rows": [], "row_count": 0})], tmp_path)

    assert json.loads((tmp_path / "query-results.json").read_text(encoding="utf-8")) == {
        "rows": [],
        "queries": [{"columns": ["stage"], "rows": []}],
    }


def test_a_later_empty_query_still_supersedes_an_earlier_one(tmp_path: Path) -> None:
    """Latest-wins has to survive the empty case, or stale rows outlive it."""

    _harvest(
        [
            _observation("run_semantic_query", {"rows": [{"stage": "closed_won"}]}),
            _observation("run_semantic_query", {"columns": ["stage"], "rows": []}),
        ],
        tmp_path,
    )

    assert json.loads((tmp_path / "query-results.json").read_text(encoding="utf-8")) == {
        "rows": [],
        "queries": [
            {"columns": ["stage"], "rows": [{"stage": "closed_won"}]},
            {"columns": ["stage"], "rows": []},
        ],
    }


def test_query_history_survives_separate_turn_harvests(tmp_path: Path) -> None:
    history: list[dict[str, object]] = []
    facts: dict[str, object] = {}
    first = [_observation("run_semantic_query", {"rows": [{"category": "契約", "row_count": 7}]})]
    second = [_observation("run_semantic_query", {"rows": [{"category": "Renovación", "row_count": 7}]})]

    _update_machine_artifacts(first, artifact_dir=tmp_path, facts=facts, build_context={}, query_history=history)
    _update_machine_artifacts(second, artifact_dir=tmp_path, facts=facts, build_context={}, query_history=history)

    assert json.loads((tmp_path / "query-results.json").read_text(encoding="utf-8")) == {
        "rows": [{"category": "Renovación", "row_count": 7}],
        "queries": [
            {"columns": ["category", "row_count"], "rows": [{"category": "契約", "row_count": 7}]},
            {"columns": ["category", "row_count"], "rows": [{"category": "Renovación", "row_count": 7}]},
        ],
    }


def test_query_history_is_capped_without_dropping_the_latest_result(tmp_path: Path) -> None:
    history: list[dict[str, object]] = []
    facts: dict[str, object] = {}
    observations = [
        _observation("run_semantic_query", {"columns": ["value"], "rows": [{"value": index}]} )
        for index in range(33)
    ]

    _update_machine_artifacts(observations, artifact_dir=tmp_path, facts=facts, build_context={}, query_history=history)

    written = json.loads((tmp_path / "query-results.json").read_text(encoding="utf-8"))
    assert len(written["queries"]) == 32
    assert written["queries"][0]["rows"] == [{"value": 1}]
    assert written["queries"][-1]["rows"] == [{"value": 32}]
    assert written["rows"] == [{"value": 32}]


def test_repeated_column_names_are_refused_rather_than_collapsed(tmp_path: Path) -> None:
    """``dict(zip(...))`` would keep one value under a repeated name."""

    _harvest(
        [_observation("run_semantic_query", {"columns": ["deal_count", "deal_count"], "rows": [[1, 2]]})],
        tmp_path,
    )

    assert not (tmp_path / "query-results.json").exists()


def test_an_mcp_call_that_never_returned_is_not_reported_as_an_error() -> None:
    """"Where did it get to" cannot be answered by a flattened error flag.

    A stall mid-build and a build that failed are opposite answers, and an
    operator reading ``build_data_product:error`` acts on the wrong one.
    """

    events = [
        {
            "type": "assistant",
            "message": {"content": [{"type": "tool_use", "id": "b1", "name": "mcp__nxd-desktop__build_data_product", "input": {}}]},
        }
    ]
    result, _ = parse_claude_events(events, redact_json_rpc=lambda v: v, redact_text=lambda v: v, session_id="s")

    assert result.last_mcp_call == "build_data_product:unanswered"


def test_lifecycle_is_paired_with_the_run_whose_identifiers_are_published(tmp_path: Path) -> None:
    """Ledger lint compares this value against the agent's own claim.

    Publishing run-b's identifiers beside run-a's lifecycle would make a
    correct agent claim read as drift.
    """

    facts, _ = _harvest(
        [
            _start_run_observation("run-a", "artifact-a"),
            _start_run_observation("run-b", "artifact-b"),
            _observation("inspect_run", {"run": {"run_id": "run-a", "lifecycle": "failed"}}),
            _observation("inspect_run", {"run": {"run_id": "run-b", "lifecycle": "terminal"}}),
            _observation("read_data_product_resource", _verified_release(run_id="run-b", artifact_id="artifact-b", publish_seq=7, counts={"main.deals": 6})),
        ],
        tmp_path,
    )

    assert facts["run_id"] == "run-b"
    assert facts["lifecycle_state"] == "terminal"


def test_a_lifecycle_from_an_earlier_turn_is_not_published_beside_a_later_run(tmp_path: Path) -> None:
    """Keying alone was per-call; `facts` persists for the whole run.

    Failed-then-repaired is a designed sequence -- the conduct rules tell the
    agent to inspect a failed run once and retry -- so a turn that observes
    run-a's lifecycle and a later turn that publishes run-b's identifiers is
    the ordinary path, not a contrived one. No gate reads the value today, but
    supervisor-facts.json is the harness's statement about one run, and a
    record mixing two runs is wrong whether or not anything grades it yet.
    """

    facts: dict[str, object] = {}
    build_context: dict[str, object] = {}
    lifecycles: dict[str, str] = {}

    # Turn n: build run-a, inspect it, no release published yet.
    _update_machine_artifacts(
        [
            _start_run_observation("run-a", "artifact-a"),
            _observation("inspect_run", {"run": {"run_id": "run-a", "lifecycle": "failed"}}),
        ],
        artifact_dir=tmp_path,
        facts=facts,
        build_context=build_context,
        lifecycles=lifecycles,
    )
    assert facts.get("lifecycle_state") == "failed"

    # Turn n+1: repair, rebuild as run-b, read its verified release. No
    # inspect_run this turn.
    _update_machine_artifacts(
        [
            _start_run_observation("run-b", "artifact-b"),
            _observation("read_data_product_resource", _verified_release(run_id="run-b", artifact_id="artifact-b", publish_seq=7, counts={"main.deals": 6})),
        ],
        artifact_dir=tmp_path,
        facts=facts,
        build_context=build_context,
        lifecycles=lifecycles,
    )

    assert facts["run_id"] == "run-b"
    # run-a's "failed" must not ride along with run-b's identifiers.
    assert "lifecycle_state" not in facts
    assert not (tmp_path / "supervisor-facts.json").exists()

    # Once run-b's own lifecycle is observed, the facts complete.
    _update_machine_artifacts(
        [_observation("inspect_run", {"run": {"run_id": "run-b", "lifecycle": "terminal"}})],
        artifact_dir=tmp_path,
        facts=facts,
        build_context=build_context,
        lifecycles=lifecycles,
    )
    assert facts["lifecycle_state"] == "terminal"
    written = json.loads((tmp_path / "supervisor-facts.json").read_text(encoding="utf-8"))
    assert written["run_id"] == "run-b"
    assert written["lifecycle_state"] == "terminal"


def _release_record(*, run_id: str, artifact_id: str, publish_seq: int, counts: dict[str, int]) -> dict[str, object]:
    """The record the supervisor writes under its own data directory."""

    return {
        "schema": "nxd-release-v1",
        "workflow_id": "crm-deals",
        "publish_seq": str(publish_seq),
        "run_id": run_id,
        "artifact_id": artifact_id,
        "verification": {
            "schema": "nxd-verification-v1",
            "outcome": "passed",
            "row_counts": {table: str(count) for table, count in counts.items()},
        },
    }


def _write_release(state_dir: Path, record: dict[str, object]) -> None:
    releases = state_dir / "workflows" / "wf-sha256-v1-abc" / "releases"
    releases.mkdir(parents=True, exist_ok=True)
    (releases / f"release-{record['publish_seq']:0>20}-{record['run_id']}.json").write_text(
        json.dumps(record), encoding="utf-8"
    )


def test_build_facts_come_from_the_runners_own_copy_of_the_release(tmp_path: Path) -> None:
    """`build` is required for every scenario, so it cannot depend on tool choice.

    Two identical live runs differed only in whether the agent volunteered
    `read_data_product_resource`, and only one of them had its build examined.
    The release record lives under the runner's data directory, which the
    agent has no shell and no path to reach.
    """

    state_dir = tmp_path / "state"
    _write_release(state_dir, _release_record(run_id="run-a", artifact_id="artifact-a", publish_seq=3, counts={"main.deals": 6, "main.orders": 2}))

    facts: dict[str, object] = {}
    _update_from_state_dir(state_dir, facts=facts, built_runs={"run-a"})

    assert facts == {
        "run_id": "run-a",
        "artifact_id": "artifact-a",
        "publish_sequence": "3",
        "per_model_row_counts": {"main.deals": "6", "main.orders": "2"},
        "lifecycle_state": "terminal",
    }


def test_a_release_for_a_run_this_session_did_not_build_is_still_refused(tmp_path: Path) -> None:
    """Attribution does not weaken because the harness reads the record itself."""

    state_dir = tmp_path / "state"
    _write_release(state_dir, _release_record(run_id="run-someone-else", artifact_id="artifact-x", publish_seq=9, counts={"main.deals": 999}))

    facts: dict[str, object] = {}
    _update_from_state_dir(state_dir, facts=facts, built_runs={"run-mine"})

    assert facts == {}


def test_the_highest_published_release_wins_on_disk_too(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    _write_release(state_dir, _release_record(run_id="run-a", artifact_id="artifact-a", publish_seq=2, counts={"main.deals": 4}))
    _write_release(state_dir, _release_record(run_id="run-b", artifact_id="artifact-b", publish_seq=5, counts={"main.deals": 6}))

    facts: dict[str, object] = {}
    _update_from_state_dir(state_dir, facts=facts, built_runs={"run-a", "run-b"})

    assert facts["publish_sequence"] == "5"
    assert facts["run_id"] == "run-b"


def test_a_missing_or_unreadable_state_dir_contributes_nothing(tmp_path: Path) -> None:
    facts: dict[str, object] = {}
    _update_from_state_dir(tmp_path / "absent", facts=facts, built_runs={"run-a"})
    assert facts == {}

    state_dir = tmp_path / "state"
    releases = state_dir / "workflows" / "wf-x" / "releases"
    releases.mkdir(parents=True)
    (releases / "release-0001-run-a.json").write_text("{not json", encoding="utf-8")
    _update_from_state_dir(state_dir, facts=facts, built_runs={"run-a"})
    assert facts == {}


def test_the_shipped_workflows_release_wins_not_the_furthest_along(tmp_path: Path) -> None:
    """`publish_seq` is allocated per workflow, so cross-workflow max is wrong.

    A session that switches workflows would otherwise report whichever one
    happened to have published more often, rather than the one it shipped.
    """

    state_dir = tmp_path / "state"
    other = _release_record(run_id="run-a", artifact_id="artifact-a", publish_seq=9, counts={"main.old": 1})
    other["workflow_id"] = "previous-workflow"
    _write_release(state_dir, other)
    shipped = _release_record(run_id="run-b", artifact_id="artifact-b", publish_seq=1, counts={"main.deals": 6})
    shipped["workflow_id"] = "crm-deals"
    _write_release(state_dir, shipped)

    facts: dict[str, object] = {}
    _update_from_state_dir(state_dir, facts=facts, built_runs={"run-a", "run-b"}, workflow="crm-deals")

    assert facts["run_id"] == "run-b"
    assert facts["publish_sequence"] == "1"
    assert facts["per_model_row_counts"] == {"main.deals": "6"}
