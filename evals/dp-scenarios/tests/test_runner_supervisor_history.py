"""Contract tests for runner-owned supervisor history artifacts."""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml

from _repo_paths import REPO_ROOT

import dp_scenarios.runner.claude_adapter as adapter_module
from dp_scenarios.runner.claude_adapter import (
    ClaudeCodeAdapter,
    _mcp_name,
    _payload_from_call,
    _update_from_state_dir,
    _update_machine_artifacts,
    _write_json,
    _write_supervisor_facts,
)
from dp_scenarios.runner.supervisor_history import (
    CAPTURE_FILE_LIMIT,
    CAPTURE_TOTAL_LIMIT,
    CAPTURES_SCHEMA,
    DEFINITION_EXPORT_SCHEMA,
    PUBLICATION_SCHEMA,
    QUERY_HISTORY_LIMIT,
    QUERY_HISTORY_SCHEMA,
    RUN_FAILURES_SCHEMA,
    RUN_RECORDS_SCHEMA,
    SupervisorHistory,
    TOOL_CALLS_SCHEMA,
    _safe_failure_facts,
)


FIXTURE_ROOT = (
    REPO_ROOT
    / "evals"
    / "dp-scenarios"
    / "tests"
    / "fixtures"
    / "supervisor-history-crm-pipeline"
)
STATE_FIXTURE = FIXTURE_ROOT / "desktop-state"
OBSERVATIONS_FIXTURE = FIXTURE_ROOT / "artifacts" / "operator-observations.json"
MANIFEST_FIXTURE = FIXTURE_ROOT / "MANIFEST.json"
RUN_CRM = "run-e96e6a40-43dd-4a8c-bd0a-d354cc3a86b9"
RUN_CRM_V2 = "run-03552f49-796b-4260-8dac-8cb911807137"
WORKFLOW_CRM = "crm-pipeline"
WORKFLOW_CRM_V2 = "crm-pipeline-current-v2"


def _copy_state(destination: Path) -> Path:
    """Copy the committed supervisor fixture before any test-side mutation."""

    return Path(shutil.copytree(STATE_FIXTURE, destination))


def _fixture_observations(turn_record: dict[str, object]) -> list[dict[str, object]]:
    """Convert fixture calls through the same decoded payload helper as Claude."""

    observations: list[dict[str, object]] = []
    calls = turn_record.get("tool_calls")
    if not isinstance(calls, list):
        return observations
    for call in calls:
        if not isinstance(call, dict):
            continue
        tool = _mcp_name(call.get("name"))
        if tool is None:
            continue
        result = call.get("result")
        if not isinstance(result, dict):
            continue
        observations.append(
            {
                "tool": tool,
                "arguments": call.get("arguments", {}),
                "result": _payload_from_call(result),
                "is_error": result.get("is_error") is True,
                "answered": True,
            }
        )
    return observations


def _fixture_turn_records() -> list[dict[str, object]]:
    document = json.loads(OBSERVATIONS_FIXTURE.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    turns = document.get("turns")
    assert isinstance(turns, list)
    return [turn for turn in turns if isinstance(turn, dict)]


def _replay(
    state_dir: Path,
    artifact_dir: Path,
    *,
    history: bool = True,
    secret_values: tuple[str, ...] = (),
) -> tuple[SupervisorHistory | None, dict[str, object], set[str]]:
    """Replay fixture turns through the adapter's existing harvest order."""

    supervisor_facts: dict[str, object] = {}
    build_context: dict[str, object] = {}
    lifecycles: dict[str, str] = {}
    built_runs: set[str] = set()
    query_history: list[dict[str, object]] = []
    history_writer = (
        SupervisorHistory(artifact_dir, secret_values=secret_values)
        if history
        else None
    )
    for turn_record in _fixture_turn_records():
        turn = turn_record.get("turn")
        assert isinstance(turn, int) and not isinstance(turn, bool)
        observations = _fixture_observations(turn_record)
        _update_machine_artifacts(
            observations,
            artifact_dir=artifact_dir,
            facts=supervisor_facts,
            build_context=build_context,
            lifecycles=lifecycles,
            built_runs=built_runs,
            query_history=query_history,
        )
        workflow = build_context.get("workflow")
        _update_from_state_dir(
            state_dir,
            facts=supervisor_facts,
            built_runs=built_runs,
            workflow=workflow if isinstance(workflow, str) else None,
        )
        _write_supervisor_facts(supervisor_facts, artifact_dir=artifact_dir)
        if history_writer is not None:
            history_writer.observe_turn(
                turn=turn,
                observations=observations,
                built_runs=built_runs,
                state_dir=state_dir,
            )
            history_writer.write()
    return history_writer, supervisor_facts, built_runs


def _read_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _read_only_tree(root: Path) -> dict[str, bytes]:
    """Capture source-tree paths and bytes except SQLite-managed sidecars."""

    result: dict[str, bytes] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.name.endswith(("-wal", "-shm")):
            continue
        result[path.relative_to(root).as_posix()] = path.read_bytes()
    return result


def _advance_start(
    *,
    workflow: str,
    request_id: str,
    run_id: str,
    answered: bool = True,
) -> dict[str, object]:
    """Create one narrow accepted start_run observation for unit cases."""

    admission = {"run_id": run_id, "artifact_id": f"artifact-{run_id}"}
    return {
        "tool": "advance_workflow",
        "arguments": {
            "workflow": workflow,
            "request_id": request_id,
            "action": {"type": "start_run"},
        },
        "result": (
            {"workflow": workflow, "admission": admission}
            if answered
            else None
        ),
        "is_error": not answered,
        "answered": answered,
    }


def _retry_turn_observations(
    *,
    workflow: str,
    run_id: str,
    request_id: str,
    query_value: str,
    exception_class: str,
    capture_digest: str,
) -> list[dict[str, object]]:
    """Create structured evidence that makes stale retry rows distinguishable."""

    return [
        {
            "tool": "advance_workflow",
            "arguments": {
                "workflow": workflow,
                "request_id": request_id,
                "action": {"type": "start_run"},
            },
            "result": {
                "workflow": workflow,
                "admission": {"run_id": run_id, "artifact_id": f"artifact-{run_id}"},
            },
            "is_error": False,
            "answered": True,
        },
        {
            "tool": "run_semantic_query",
            "arguments": {"endpoint": "http://127.0.0.1:1234/mcp/"},
            "result": {
                "workflow": workflow,
                "semantic_endpoint": "http://127.0.0.1:1234/mcp/",
                "columns": ["value"],
                "rows": [[query_value]],
            },
            "is_error": False,
            "answered": True,
        },
        {
            "tool": "inspect_run",
            "arguments": {"run_id": run_id},
            "result": {
                "run": {
                    "run_id": run_id,
                    "workflow": workflow,
                    "outcome": "failed",
                    "exception_class": exception_class,
                }
            },
            "is_error": False,
            "answered": True,
        },
        {
            "tool": "advance_workflow",
            "arguments": {
                "workflow": workflow,
                "request_id": f"capture-{request_id}",
                "action": {"type": "capture"},
            },
            "result": {
                "requirements": [
                    {
                        "id": "review",
                        "status": "pending",
                        "review_input": {
                            "retained_capture_root": (
                                f"/private/tmp/captures/sha256/{capture_digest}"
                            ),
                        },
                    }
                ]
            },
            "is_error": False,
            "answered": True,
        },
    ]


def test_fixture_publications_are_session_attributed_and_join_admission_links(
    tmp_path: Path,
) -> None:
    state_dir = _copy_state(tmp_path / "state")
    artifact_dir = tmp_path / "artifacts"
    _replay(state_dir, artifact_dir)

    document = _read_json(artifact_dir / "publication-history.json")
    assert document["schema"] == PUBLICATION_SCHEMA
    releases = document["releases"]
    assert isinstance(releases, list)
    assert len(releases) == 2
    by_run = {release["run_id"]: release for release in releases}
    fixture_manifest = json.loads(MANIFEST_FIXTURE.read_text(encoding="utf-8"))
    workflow_ids = fixture_manifest["ids"]["workflows"]

    for run_id, workflow, expected_turn in (
        (RUN_CRM, WORKFLOW_CRM, 4),
        (RUN_CRM_V2, WORKFLOW_CRM_V2, 14),
    ):
        item = by_run[run_id]
        expected = workflow_ids[workflow]
        assert item["turn"] == expected_turn
        assert item["workflow_id"] == workflow
        assert item["workflow_key"] == expected["workflow_key"]
        assert item["publish_sequence"] == "1"
        assert item["definition_id"] == expected["definition_id"]
        assert item["verification_outcome"] == "passed"
        assert item["attributed_by"] == "built_run"
        link_path = (
            state_dir
            / "workflows"
            / expected["workflow_key"]
            / "admission-links"
            / f"{item['release_basename']}.json"
        )
        link = json.loads(link_path.read_text(encoding="utf-8"))
        assert item["admission_id"] == link["admission_id"]


def test_attribution_excludes_stray_releases_and_supports_lost_start_results(
    tmp_path: Path,
) -> None:
    state_dir = _copy_state(tmp_path / "state")
    releases_dir = next((state_dir / "workflows").glob("*/releases"))
    original = json.loads(next(releases_dir.glob("release-*.json")).read_text())
    orphan = dict(original)
    orphan["run_id"] = "run-orphan-not-in-this-session"
    orphan["publish_seq"] = "99"
    orphan_path = releases_dir / "release-00000000000000000099-orphan.json"
    orphan_path.write_text(json.dumps(orphan), encoding="utf-8")

    empty_dir = tmp_path / "empty-artifacts"
    empty_history = SupervisorHistory(empty_dir)
    empty_history.observe_turn(
        turn=1,
        observations=[],
        built_runs=set(),
        state_dir=state_dir,
    )
    empty_history.write()
    assert _read_json(empty_dir / "publication-history.json")["releases"] == []
    assert _read_json(empty_dir / "run-records.json")["runs"] == []

    connection = sqlite3.connect(state_dir / "state.sqlite3")
    row = connection.execute(
        "SELECT dossier_json FROM wf_admissions WHERE run_id = ?",
        (RUN_CRM,),
    ).fetchone()
    assert row is not None
    dossier = json.loads(row[0])
    dossier["request_id"] = "lost-result-request"
    connection.execute(
        "UPDATE wf_admissions SET request_id = ?, dossier_json = ? WHERE run_id = ?",
        ("lost-result-request", json.dumps(dossier), RUN_CRM),
    )
    connection.commit()
    connection.close()

    lost_dir = tmp_path / "lost-artifacts"
    history = SupervisorHistory(lost_dir)
    built_runs: set[str] = set()
    history.observe_turn(
        turn=7,
        observations=[
            {
                "tool": "advance_workflow",
                "arguments": {
                    "workflow": WORKFLOW_CRM,
                    "request_id": "lost-result-request",
                    "action": {"type": "start_run"},
                },
                "result": None,
                "is_error": True,
                "answered": False,
            }
        ],
        built_runs=built_runs,
        state_dir=state_dir,
    )
    history.write()

    publication = _read_json(lost_dir / "publication-history.json")["releases"]
    assert isinstance(publication, list)
    attributed = [item for item in publication if item["run_id"] == RUN_CRM]
    assert len(attributed) == 1
    assert attributed[0]["attributed_by"] == "session_request"
    assert attributed[0]["turn"] == 7
    assert built_runs == set()
    run = next(
        row
        for row in _read_json(lost_dir / "run-records.json")["runs"]
        if row["run_id"] == RUN_CRM
    )
    assert run["start_turn"] == 7
    assert run["start_turn_source"] == "request"


def test_run_records_use_first_matching_request_and_track_status_transitions(
    tmp_path: Path,
) -> None:
    state_dir = _copy_state(tmp_path / "state")
    _replay(state_dir, tmp_path / "fixture-artifacts")
    manifest = json.loads(MANIFEST_FIXTURE.read_text(encoding="utf-8"))
    runs = _read_json(tmp_path / "fixture-artifacts" / "run-records.json")["runs"]
    assert isinstance(runs, list) and len(runs) == 2
    by_id = {item["run_id"]: item for item in runs}
    for run_id, workflow, expected_turn in (
        (RUN_CRM, WORKFLOW_CRM, 4),
        (RUN_CRM_V2, WORKFLOW_CRM_V2, 14),
    ):
        item = by_id[run_id]
        assert item["request_id"] == manifest["ids"]["workflows"][workflow][
            "admission_request_id"
        ]
        assert item["start_turn"] == expected_turn
        assert item["start_turn_source"] == "request"
        assert item["status"] == "Published"
        assert item["terminal"] is True

    connection = sqlite3.connect(state_dir / "state.sqlite3")
    connection.execute(
        "UPDATE runs SET status = 'Running' WHERE run_id = ?",
        (RUN_CRM,),
    )
    connection.commit()
    connection.close()
    artifact_dir = tmp_path / "transition-artifacts"
    history = SupervisorHistory(artifact_dir)
    run_request = manifest["ids"]["workflows"][WORKFLOW_CRM]["admission_request_id"]
    history.observe_turn(
        turn=1,
        observations=[
            _advance_start(
                workflow=WORKFLOW_CRM,
                request_id=run_request,
                run_id=RUN_CRM,
            )
        ],
        built_runs=set(),
        state_dir=state_dir,
    )
    history.write()

    connection = sqlite3.connect(state_dir / "state.sqlite3")
    connection.execute(
        "UPDATE runs SET status = 'Published' WHERE run_id = ?",
        (RUN_CRM,),
    )
    connection.commit()
    connection.close()
    history.observe_turn(
        turn=2,
        observations=[],
        built_runs=set(),
        state_dir=state_dir,
    )
    history.write()

    transitioned = next(
        item
        for item in _read_json(artifact_dir / "run-records.json")["runs"]
        if item["run_id"] == RUN_CRM
    )
    assert transitioned["status_history"] == [
        {"turn": 1, "status": "Running"},
        {"turn": 2, "status": "Published"},
    ]
    assert transitioned["terminal_turn"] == 2


def test_replay_writes_one_operation_diagnostic_and_structured_tool_failures(
    tmp_path: Path,
) -> None:
    state_dir = _copy_state(tmp_path / "state")
    artifact_dir = tmp_path / "artifacts"
    _replay(state_dir, artifact_dir)
    failures = _read_json(artifact_dir / "run-failures.json")["failures"]
    operation_failures = [
        item for item in failures if item["source"] == "operation_diagnostic"
    ]
    assert len(operation_failures) == 1
    operation = operation_failures[0]
    assert operation["workflow_id"] == WORKFLOW_CRM
    assert operation["request_id"] == "validate-crm-pipeline-2"
    assert operation["requirement_id"] == "validation"
    assert operation["turn"] == 13
    assert operation["code"] == "validation/existing_workflow_unsupported"
    assert operation["recovery"] == "stop"
    assert operation["phase"] == "supervisor_preflight"

    tool_failures = [
        item
        for item in failures
        if item["source"] == "tool_result"
        and item["tool"] == "advance_workflow"
    ]
    assert len(tool_failures) == 1
    assert tool_failures[0]["turn"] == 13
    encoded = (artifact_dir / "run-failures.json").read_text(encoding="utf-8")
    assert "rejected the retained closure" not in encoded
    assert '"detail"' not in encoded

    tool_artifacts = tmp_path / "tool-artifacts"
    history = SupervisorHistory(tool_artifacts)
    history.observe_turn(
        turn=1,
        observations=[
            {
                "tool": "inspect_run",
                "arguments": {"run_id": RUN_CRM},
                "result": {
                    "run": {
                        "run_id": RUN_CRM,
                        "workflow": WORKFLOW_CRM,
                        "outcome": "failed",
                        "code": "transform_error",
                        "error": "PRIVATE_ERROR_TEXT",
                        "failed_contracts": [
                            {
                                "contract": "deals-unique-id",
                                "model": "deals",
                                "failed_count": 2,
                            },
                            {
                                "contract": "",
                                "model": "deals",
                                "failed_count": 2,
                            },
                            {
                                "contract": "bad-count",
                                "model": "deals",
                                "failed_count": True,
                            },
                        ],
                        "exception_class": "decimal.ConversionSyntax",
                    }
                },
                "is_error": False,
                "answered": True,
            },
            {
                "tool": "assistant_text",
                "arguments": {},
                "result": "A failure and a token=secret were mentioned.",
                "is_error": False,
                "answered": True,
            },
        ],
        built_runs=set(),
        state_dir=None,
    )
    history.write()
    tool_failure_doc = _read_json(tool_artifacts / "run-failures.json")
    tool_failure_rows = tool_failure_doc["failures"]
    assert len(tool_failure_rows) == 1
    tool_failure = tool_failure_rows[0]
    assert tool_failure["source"] == "tool_result"
    assert tool_failure["tool"] == "inspect_run"
    assert tool_failure["failed_contracts"] == [
        {
            "contract": "deals-unique-id",
            "model": "deals",
            "failed_count": 2,
        }
    ]
    assert tool_failure["exception_class"] == "decimal.ConversionSyntax"
    encoded_tool = (tool_artifacts / "run-failures.json").read_text(
        encoding="utf-8"
    )
    assert "PRIVATE_ERROR_TEXT" not in encoded_tool
    assert "token=secret" not in encoded_tool


def _run_diagnostic(run_id: str, workflow_id: str) -> dict[str, object]:
    """Return the complete nxd-run-diagnostic-v5 record shape for a tmp DB row."""

    return {
        "schema": "nxd-run-diagnostic-v5",
        "run_id": run_id,
        "workflow_id": workflow_id,
        "started_at_unix_ms": 1,
        "recorded_at_unix_ms": 2,
        "outcome": "failed",
        "code": "transform_error",
        "timeout_phase": "transform_dispatched",
        "last_phase": "transform_dispatched",
        "error": "PRIVATE_DIAGNOSTIC_ERROR",
        "budget": None,
        "elapsed_ms": 12,
        "timed_out": False,
        "expired_budget": None,
        "expired_budget_secs": None,
        "transform_stage": None,
        "transform_http_status": 502,
        "failed_contracts": [
            {"contract": "deals-unique-id", "model": "deals", "failed_count": 1},
            {"contract": "bad contract", "model": "deals", "failed_count": 1},
            {"contract": "deals-no-pii", "model": "deals", "failed_count": True},
        ],
        "exception_class": "decimal.ConversionSyntax",
        "phases": [{"phase": "transform_dispatched", "at_ms": 1}],
        "child_pid": 123,
        "child_pgid": 123,
        "child_exit": "failed",
        "staging": {
            "staging_present": False,
            "staging_bytes": 0,
            "marker_present": False,
        },
        "stdout": {
            "total_bytes": 20,
            "truncated": False,
            "lines": ["PRIVATE_STDOUT_TEXT"],
        },
        "stderr": {
            "total_bytes": 20,
            "truncated": False,
            "lines": ["PRIVATE_STDERR_TEXT"],
        },
        "log_reference": "/private/customer/diagnostic.json",
    }


def test_run_diagnostic_v5_is_session_filtered_and_free_text_is_dropped(
    tmp_path: Path,
) -> None:
    state_dir = _copy_state(tmp_path / "state")
    connection = sqlite3.connect(state_dir / "state.sqlite3")
    for run_id, workflow_id in (
        (RUN_CRM, WORKFLOW_CRM),
        ("run-not-in-this-session", "other-workflow"),
    ):
        diagnostic = _run_diagnostic(run_id, workflow_id)
        connection.execute(
            """
            INSERT OR REPLACE INTO run_diagnostics
            (run_id, workflow_id, outcome, timeout_phase, recorded_at_unix_ms,
             summary, diagnostic_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                workflow_id,
                "failed",
                "transform_dispatched",
                "2",
                "PRIVATE_DIAGNOSTIC_SUMMARY",
                json.dumps(diagnostic),
            ),
        )
    connection.commit()
    connection.close()

    artifact_dir = tmp_path / "artifacts"
    _replay(state_dir, artifact_dir)
    failures = _read_json(artifact_dir / "run-failures.json")["failures"]
    run_failures = [item for item in failures if item["source"] == "run_diagnostic"]
    assert len(run_failures) == 1
    run_failure = run_failures[0]
    assert run_failure["turn"] == 4
    assert run_failure["run_id"] == RUN_CRM
    assert run_failure["failed_contracts"] == [
        {
            "contract": "deals-unique-id",
            "model": "deals",
            "failed_count": 1,
        }
    ]
    assert run_failure["exception_class"] == "decimal.ConversionSyntax"
    encoded = (artifact_dir / "run-failures.json").read_text(encoding="utf-8")
    for forbidden in (
        "PRIVATE_DIAGNOSTIC_ERROR",
        "PRIVATE_DIAGNOSTIC_SUMMARY",
        "PRIVATE_STDOUT_TEXT",
        "PRIVATE_STDERR_TEXT",
        "/private/customer",
    ):
        assert forbidden not in encoded


def test_builtin_exception_classes_survive_all_failure_fact_paths(
    tmp_path: Path,
) -> None:
    assert _safe_failure_facts({"exception_class": "KeyError"}) == ([], "KeyError")
    assert _safe_failure_facts(
        {"exception_class": "duckdb.CatalogException"}
    ) == ([], "duckdb.CatalogException")
    assert _safe_failure_facts({"exception_class": "A" * 128}) == ([], "A" * 128)
    assert _safe_failure_facts({"exception_class": "A" * 129}) == ([], None)
    assert _safe_failure_facts({"exception_class": "duckdb.Catalog-Exception"}) == (
        [],
        None,
    )

    state_dir = _copy_state(tmp_path / "state")
    connection = sqlite3.connect(state_dir / "state.sqlite3")
    diagnostic = _run_diagnostic(RUN_CRM, WORKFLOW_CRM)
    diagnostic["exception_class"] = "KeyError"
    connection.execute(
        """
        INSERT OR REPLACE INTO run_diagnostics
        (run_id, workflow_id, outcome, timeout_phase, recorded_at_unix_ms,
         summary, diagnostic_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            RUN_CRM,
            WORKFLOW_CRM,
            "failed",
            "transform_dispatched",
            "2",
            "PRIVATE_DIAGNOSTIC_SUMMARY",
            json.dumps(diagnostic),
        ),
    )
    connection.commit()
    connection.close()

    state_artifacts = tmp_path / "state-artifacts"
    _replay(state_dir, state_artifacts)
    run_diagnostic = next(
        item
        for item in _read_json(state_artifacts / "run-failures.json")["failures"]
        if item["source"] == "run_diagnostic"
    )
    assert run_diagnostic["exception_class"] == "KeyError"

    tool_artifacts = tmp_path / "tool-artifacts"
    history = SupervisorHistory(tool_artifacts)
    history.observe_turn(
        turn=1,
        observations=[
            {
                "tool": "inspect_run",
                "arguments": {"run_id": "run-inspect-key-error"},
                "result": {
                    "run": {
                        "run_id": "run-inspect-key-error",
                        "workflow": WORKFLOW_CRM,
                        "outcome": "failed",
                        "exception_class": "KeyError",
                    }
                },
                "is_error": False,
                "answered": True,
            },
            {
                "tool": "advance_workflow",
                "arguments": {
                    "workflow": WORKFLOW_CRM,
                    "request_id": "advance-key-error",
                    "action": {"type": "validate"},
                },
                "result": {
                    "workflow": WORKFLOW_CRM,
                    "operation": {
                        "operation_id": "operation-key-error",
                        "workflow": WORKFLOW_CRM,
                        "request_id": "advance-key-error",
                        "exception_class": "KeyError",
                    },
                },
                "is_error": False,
                "answered": True,
            },
        ],
        built_runs=set(),
        state_dir=None,
    )
    history.write()
    tool_failures = _read_json(tool_artifacts / "run-failures.json")["failures"]
    by_tool = {item["tool"]: item for item in tool_failures}
    assert by_tool["inspect_run"]["exception_class"] == "KeyError"
    assert by_tool["advance_workflow"]["exception_class"] == "KeyError"


def test_tool_calls_are_allowlisted_attributed_and_query_history_is_separate(
    tmp_path: Path,
) -> None:
    state_dir = _copy_state(tmp_path / "state")
    artifact_dir = tmp_path / "artifacts"
    _replay(state_dir, artifact_dir)

    call_doc = _read_json(artifact_dir / "tool-calls.json")
    assert call_doc["schema"] == TOOL_CALLS_SCHEMA
    calls = call_doc["calls"]
    assert isinstance(calls, list) and len(calls) == 93
    expected: list[tuple[int, int, str]] = []
    for turn_record in _fixture_turn_records():
        turn = turn_record["turn"]
        tool_index = 0
        for raw_call in turn_record.get("tool_calls", []):
            if not isinstance(raw_call, dict):
                continue
            tool = _mcp_name(raw_call.get("name"))
            if tool is None:
                continue
            expected.append((turn, tool_index, tool))
            tool_index += 1
    assert [
        (call["turn"], call["index"], call["tool"])
        for call in calls
    ] == expected
    assert call_doc["last_turn"] == 22
    assert call_doc["endpoints"]

    start_calls = [
        call for call in calls
        if call["tool"] == "advance_workflow"
        and call["action_type"] == "start_run"
    ]
    assert [
        (call["turn"], call["run_id"])
        for call in start_calls
    ] == [(4, RUN_CRM), (14, RUN_CRM_V2)]
    sticky_calls = [
        call for call in calls
        if call["tool"] == "advance_workflow"
        and call["turn"] > 4
        and call["action_type"] != "start_run"
    ]
    assert sticky_calls
    assert all(call["run_id"] is None for call in sticky_calls)
    semantic_queries = [
        call for call in calls if call["tool"] == "run_semantic_query"
    ]
    assert semantic_queries
    assert all(call["run_id"] is None for call in semantic_queries)
    assert all(
        call["workflow_id"] == WORKFLOW_CRM_V2
        for call in semantic_queries
        if call["turn"] in {14, 17}
    )
    assert all(
        set(call)
        == {
            "turn",
            "index",
            "tool",
            "is_error",
            "answered",
            "workflow_id",
            "request_id",
            "action_type",
            "requirement_id",
            "run_id",
            "endpoint",
        }
        for call in calls
    )
    encoded_calls = (artifact_dir / "tool-calls.json").read_text(encoding="utf-8")
    assert '"arguments"' not in encoded_calls
    assert '"token"' not in encoded_calls
    assert '"dimensions"' not in encoded_calls

    query_doc = _read_json(artifact_dir / "query-history.json")
    assert query_doc["schema"] == QUERY_HISTORY_SCHEMA
    queries = query_doc["queries"]
    assert isinstance(queries, list) and queries
    assert all(
        query["turn"] in {4, 14, 17}
        and query["workflow_id"] in {WORKFLOW_CRM, WORKFLOW_CRM_V2}
        and isinstance(query["endpoint"], str)
        and query["index"] >= 0
        for query in queries
    )
    assert any(query["run_id"] == RUN_CRM_V2 for query in queries)
    assert all(
        "query" not in query and "arguments" not in query
        for query in queries
    )


def test_explicit_run_arguments_take_precedence_over_structured_results(
    tmp_path: Path,
) -> None:
    artifact_dir = tmp_path / "artifacts"
    history = SupervisorHistory(artifact_dir)
    history.observe_turn(
        turn=1,
        observations=[
            {
                "tool": "advance_workflow",
                "arguments": {
                    "workflow": WORKFLOW_CRM,
                    "request_id": "request-start",
                    "run_id": "argument-start-run",
                    "action": {"type": "start_run"},
                },
                "result": {
                    "workflow": WORKFLOW_CRM,
                    "admission": {"run_id": "result-start-run"},
                },
                "is_error": False,
                "answered": True,
            },
            {
                "tool": "inspect_run",
                "arguments": {"run_id": "argument-inspect-run"},
                "result": {"run": {"run_id": "result-inspect-run"}},
                "is_error": False,
                "answered": True,
            },
            {
                "tool": "resume_data_product",
                "arguments": {
                    "workflow": WORKFLOW_CRM,
                    "run_id": "argument-resume-run",
                },
                "result": {
                    "workflow": WORKFLOW_CRM,
                    "run_id": "result-resume-run",
                    "semantic_endpoint": "http://127.0.0.1:9/query",
                },
                "is_error": False,
                "answered": True,
            },
        ],
        built_runs=set(),
        state_dir=None,
    )
    history.write()

    calls = _read_json(artifact_dir / "tool-calls.json")["calls"]
    assert isinstance(calls, list)
    assert [call["run_id"] for call in calls] == [
        "argument-start-run",
        "argument-inspect-run",
        "argument-resume-run",
    ]
    assert calls[2]["endpoint"] == "http://127.0.0.1:9/query"


def test_history_writers_leave_legacy_artifact_bytes_unchanged(tmp_path: Path) -> None:
    baseline_state = _copy_state(tmp_path / "baseline-state")
    p2_state = _copy_state(tmp_path / "p2-state")
    baseline_dir = tmp_path / "baseline-artifacts"
    p2_dir = tmp_path / "p2-artifacts"
    _replay(baseline_state, baseline_dir, history=False)
    _replay(p2_state, p2_dir, history=True)

    for filename in ("supervisor-facts.json", "query-results.json"):
        assert (baseline_dir / filename).read_bytes() == (
            p2_dir / filename
        ).read_bytes()

    fixture_golden = FIXTURE_ROOT / "artifacts" / "supervisor-facts.json"
    canonical_golden_dir = tmp_path / "canonical-golden"
    _write_json(
        canonical_golden_dir / "supervisor-facts.json",
        json.loads(fixture_golden.read_text(encoding="utf-8")),
    )
    assert (p2_dir / "supervisor-facts.json").read_bytes() == (
        canonical_golden_dir / "supervisor-facts.json"
    ).read_bytes()


def test_query_history_counts_evictions_and_resumes_without_duplicate_keys(
    tmp_path: Path,
) -> None:
    artifact_dir = tmp_path / "artifacts"
    history = SupervisorHistory(artifact_dir)
    for turn in range(1, QUERY_HISTORY_LIMIT + 3):
        history.observe_turn(
            turn=turn,
            observations=[
                {
                    "tool": "run_semantic_query",
                    "arguments": {
                        "workflow": WORKFLOW_CRM_V2,
                        "endpoint": "http://127.0.0.1:1234/mcp/",
                        "query": "SELECT private_value",
                        "token": "never-copy-this",
                    },
                    "result": {
                        "columns": ["value"],
                        "rows": [[turn]],
                    },
                    "is_error": False,
                    "answered": True,
                }
            ],
            built_runs=set(),
            state_dir=None,
        )
        history.write()
    query_doc = _read_json(artifact_dir / "query-history.json")
    assert query_doc["dropped"] == 2
    assert len(query_doc["queries"]) == QUERY_HISTORY_LIMIT
    assert query_doc["queries"][0]["turn"] == 3
    encoded = (artifact_dir / "query-history.json").read_text(encoding="utf-8")
    assert "SELECT private_value" not in encoded
    assert "never-copy-this" not in encoded

    resumed = SupervisorHistory(artifact_dir)
    assert resumed.last_turn == QUERY_HISTORY_LIMIT + 2
    resumed.observe_turn(
        turn=QUERY_HISTORY_LIMIT + 3,
        observations=[
            {
                "tool": "run_semantic_query",
                "arguments": {"endpoint": "http://127.0.0.1:1234/mcp/"},
                "result": {"columns": ["value"], "rows": [[65]]},
                "is_error": False,
                "answered": True,
            }
        ],
        built_runs=set(),
        state_dir=None,
    )
    resumed.write()
    query_doc = _read_json(artifact_dir / "query-history.json")
    assert query_doc["dropped"] == 3
    assert len(query_doc["queries"]) == QUERY_HISTORY_LIMIT
    assert len(
        {
            (query["turn"], query["index"])
            for query in query_doc["queries"]
        }
    ) == QUERY_HISTORY_LIMIT


def _turn_observations(number: int) -> list[dict[str, object]]:
    record = next(item for item in _fixture_turn_records() if item["turn"] == number)
    return _fixture_observations(record)


def _capture_result_turn(digest: str) -> int:
    for record in _fixture_turn_records():
        turn = record.get("turn")
        if not isinstance(turn, int) or isinstance(turn, bool):
            continue
        for observation in _fixture_observations(record):
            arguments = observation.get("arguments")
            action = arguments.get("action") if isinstance(arguments, dict) else None
            if (
                observation.get("tool") != "advance_workflow"
                or not isinstance(action, dict)
                or action.get("type") != "capture"
            ):
                continue
            payload = observation.get("result")
            requirements = payload.get("requirements") if isinstance(payload, dict) else None
            if not isinstance(requirements, list):
                continue
            for requirement in requirements:
                review_input = (
                    requirement.get("review_input")
                    if isinstance(requirement, dict)
                    else None
                )
                raw_root = (
                    review_input.get("retained_capture_root")
                    if isinstance(review_input, dict)
                    else None
                )
                if not isinstance(raw_root, str):
                    continue
                components = Path(raw_root).parts
                if (
                    len(components) >= 3
                    and components[-3:-1] == ("captures", "sha256")
                    and components[-1] == digest
                ):
                    return turn
    raise AssertionError(f"fixture has no capture result for digest {digest}")


def _capture_entry(artifact_dir: Path, digest: str) -> dict[str, object]:
    document = _read_json(artifact_dir / "supervisor-captures.json")
    assert document["schema"] == CAPTURES_SCHEMA
    entries = document["captures"]
    assert isinstance(entries, list)
    return next(
        entry
        for entry in entries
        if entry["capture_sha256"] == f"sha256:{digest}"
    )


def test_capture_snapshots_admissions_and_capture_results_with_file_policy(
    tmp_path: Path,
) -> None:
    state_dir = _copy_state(tmp_path / "state")
    artifact_dir = tmp_path / "artifacts"
    regression_digest = "d311b62892792fe9d8f16ca167a23968f405a45c0ffe842a1272a12f50c4db02"
    regression_root = state_dir / "captures" / "sha256" / regression_digest
    main_path = regression_root / "transform" / "main.py"
    main_regression_lines = (
        b"    has_password = parsed.password is not None\n"
        b'    missing_token_error = "token is required by this profile"\n'
        b'    bearer_flow_note = "... for this bearer flow"\n'
        b"    # refreshing the bearer token on a 401\n"
    )
    main_path.write_bytes(main_path.read_bytes() + main_regression_lines)
    approved_path = regression_root / "dp-blueprint.approved.md"
    prose_regression_lines = (
        b"\nThis prose mentions `has_password = parsed.password is not None`.\n"
        b'This prose mentions `missing_token_error = "token is required by this profile"`.\n'
        b"This prose mentions `... for this bearer flow`.\n"
        b"This prose mentions `refreshing the bearer token on a 401`.\n"
    )
    approved_path.write_bytes(approved_path.read_bytes() + prose_regression_lines)
    expected_main_bytes = main_path.read_bytes()
    expected_approved_bytes = approved_path.read_bytes()
    _replay(state_dir, artifact_dir)

    document = _read_json(artifact_dir / "supervisor-captures.json")
    entries = document["captures"]
    assert isinstance(entries, list)
    assert {entry["capture_sha256"] for entry in entries} == {
        "sha256:364357cc65421365af8ada2184af76420e5f065325e96c254bbef8fa3985fa84",
        "sha256:d311b62892792fe9d8f16ca167a23968f405a45c0ffe842a1272a12f50c4db02",
        "sha256:e034d41af65f2b6dcd3ad308594b0a00d79504710e02d47249e2ecbaefc85691",
    }
    for entry in entries:
        digest = entry["capture_sha256"].removeprefix("sha256:")
        source_root = state_dir / "captures" / "sha256" / digest
        snapshot_root = artifact_dir / "supervisor-captures" / digest
        assert entry["workflow_ids"]
        if digest == "364357cc65421365af8ada2184af76420e5f065325e96c254bbef8fa3985fa84":
            assert entry["sources"] == ["admission", "capture_result"]
            assert entry["first_turn"] == 4
            assert entry["run_ids"]
        elif digest == "e034d41af65f2b6dcd3ad308594b0a00d79504710e02d47249e2ecbaefc85691":
            assert "admission" in entry["sources"]
            assert entry["first_turn"] == 14
            assert entry["run_ids"]
        elif digest == "d311b62892792fe9d8f16ca167a23968f405a45c0ffe842a1272a12f50c4db02":
            assert entry["sources"] == ["capture_result"]
            capture_turn = _capture_result_turn(digest)
            assert capture_turn == 13
            assert entry["first_turn"] == capture_turn
            assert entry["workflow_ids"] == [WORKFLOW_CRM]
            assert entry["run_ids"] == []
        else:
            assert "admission" in entry["sources"]
            assert entry["run_ids"]
        for excluded in (
            "infra-profile.yaml",
            "SENSITIVE",
            "self_check.py",
            "connectivity_check.py",
            "csv-source-path",
        ):
            assert not any(
                path.relative_to(snapshot_root).as_posix().endswith(excluded)
                for path in snapshot_root.rglob("*")
                if path.is_file()
            )
        assert not (snapshot_root / "data").exists()
        for copied in entry["files"]:
            relative = copied["path"]
            source = source_root / relative
            snapshot = snapshot_root / relative
            content = source.read_bytes()
            assert snapshot.read_bytes() == content
            assert copied["size"] == len(content)
            assert copied["sha256"] == "sha256:" + hashlib.sha256(content).hexdigest()
        main_source = source_root / "transform" / "main.py"
        if main_source.is_file():
            assert (snapshot_root / "transform" / "main.py").read_bytes() == (
                main_source.read_bytes()
            )
        assert not {
            item["reason"]
            for item in entry["skipped"]
        } & {"secret_value", "credential_literal", "redacted_text"}
        skipped_paths = {item["path"] for item in entry["skipped"]}
        assert "infra-profile.yaml" in skipped_paths
        assert "SENSITIVE" in skipped_paths
        assert "self_check.py" in skipped_paths
        assert "connectivity_check.py" in skipped_paths
        assert "csv-source-path" in skipped_paths
        assert any(path.startswith("data/") for path in skipped_paths)
    regression_snapshot_root = artifact_dir / "supervisor-captures" / regression_digest
    assert (regression_snapshot_root / "transform" / "main.py").read_bytes() == expected_main_bytes
    assert (regression_snapshot_root / "dp-blueprint.approved.md").read_bytes() == (
        expected_approved_bytes
    )


def test_snapshotted_capture_only_grows_run_and_workflow_associations(
    tmp_path: Path,
) -> None:
    state_dir = _copy_state(tmp_path / "state")
    artifact_dir = tmp_path / "artifacts"
    digest = "364357cc65421365af8ada2184af76420e5f065325e96c254bbef8fa3985fa84"
    history = SupervisorHistory(artifact_dir)
    history.observe_turn(
        turn=4,
        observations=_turn_observations(4),
        built_runs=set(),
        state_dir=state_dir,
    )
    history.write()
    before = _capture_entry(artifact_dir, digest)

    connection = sqlite3.connect(state_dir / "state.sqlite3")
    row = connection.execute(
        "SELECT dossier_json FROM wf_admissions WHERE run_id = ?",
        (RUN_CRM_V2,),
    ).fetchone()
    assert row is not None
    dossier = json.loads(row[0])
    dossier["capture_sha256"] = f"sha256:{digest}"
    dossier["capture_id"] = "capture-second-run"
    connection.execute(
        "UPDATE wf_admissions SET dossier_json = ? WHERE run_id = ?",
        (json.dumps(dossier), RUN_CRM_V2),
    )
    connection.commit()
    connection.close()

    history.observe_turn(
        turn=14,
        observations=_turn_observations(14),
        built_runs={RUN_CRM_V2},
        state_dir=state_dir,
    )
    history.write()
    after = _capture_entry(artifact_dir, digest)
    assert after["files"] == before["files"]
    assert after["skipped"] == before["skipped"]
    assert after["truncated"] == before["truncated"]
    assert after["sources"] == before["sources"]
    assert after["first_turn"] == before["first_turn"]
    assert after["capture_id"] == before["capture_id"]
    assert after["run_ids"] == sorted([RUN_CRM, RUN_CRM_V2])
    assert after["workflow_ids"] == sorted([WORKFLOW_CRM, WORKFLOW_CRM_V2])


def test_capture_credential_literals_are_refused_and_placeholders_are_copied(
    tmp_path: Path,
) -> None:
    digest = "364357cc65421365af8ada2184af76420e5f065325e96c254bbef8fa3985fa84"
    state_dir = _copy_state(tmp_path / "credential-state")
    capture_root = state_dir / "captures" / "sha256" / digest
    refused = {
        "configured-value.py": b"source = 'fixture-secret-value'\n",
        "url-userinfo.py": b"dsn = 'postgresql://svc:S3cr3tPassw0rd@127.0.0.1:5432/db'\n",
        "bearer.py": b"auth = 'Bearer abcdefghijklmnopqrstuvwxyz1234'\n",
        "pem.py": b"-----BEGIN ENCRYPTED PRIVATE KEY-----\n",
        "jwt.py": b"token = 'eyJabcdefgh.abcdefgh.abcdefgh'\n",
        "sk.py": b"token = 'sk-abcdefghijklmnop'\n",
        "ghp.py": b"token = 'ghp_abcdefghijklmnop'\n",
        "github-pat.py": b"token = 'github_pat_abcdefghijklmnop'\n",
        "xoxb.py": b"token = 'xoxb-abcdefghijklmnop'\n",
        "xoxp.py": b"token = 'xoxp-abcdefghijklmnop'\n",
        "undecodable.py": b"invalid-utf8-\xff\n",
    }
    for filename, content in refused.items():
        target = capture_root / "transform" / filename
        target.write_bytes(content)
    placeholders = (
        "postgresql://{user}:{password}@host/db\n"
        "https://user:$PASSWORD@host\n"
        "https://user:{password}@example.invalid/a\n"
        "https://user:$PASSWORD@example.invalid/b\n"
        "https://user:%SECRET%@example.invalid/c\n"
        "https://user:<password>@example.invalid/d\n"
        "https://user:***@example.invalid/e\n"
        "https://user:PASSWORD@example.invalid/f\n"
        "https://user:Pass@example.invalid/g\n"
        "https://user:XxX@example.invalid/h\n"
    ).encode()
    prose = (
        b"This documentation discusses password= markers, bearer tokens, and "
        b"the placeholder URL https://user:password@example.invalid without "
        b"containing credentials.\n"
    )
    (capture_root / "transform" / "placeholders.py").write_bytes(placeholders)
    (capture_root / "transform" / "prose-regression.py").write_bytes(prose)
    (capture_root / "transform" / "short-value.py").write_bytes(b"short\n")

    history_dir = tmp_path / "credential-artifacts"
    history = SupervisorHistory(
        history_dir,
        secret_values=("fixture-secret-value", "short"),
    )
    history.observe_turn(
        turn=4,
        observations=_turn_observations(4),
        built_runs=set(),
        state_dir=state_dir,
    )
    history.write()
    entry = _capture_entry(history_dir, digest)
    skipped = {item["path"]: item["reason"] for item in entry["skipped"]}
    expected_reasons = {
        "transform/configured-value.py": "secret_value",
        **{
            f"transform/{filename}": "credential_literal"
            for filename in (
                "url-userinfo.py",
                "bearer.py",
                "pem.py",
                "jwt.py",
                "sk.py",
                "ghp.py",
                "github-pat.py",
                "xoxb.py",
                "xoxp.py",
            )
        },
        "transform/undecodable.py": "redacted_text",
    }
    assert {path: skipped[path] for path in expected_reasons} == expected_reasons
    snapshot_root = history_dir / "supervisor-captures" / digest
    copied = {item["path"] for item in entry["files"]}
    assert "transform/placeholders.py" in copied
    assert "transform/prose-regression.py" in copied
    assert "transform/short-value.py" in copied
    assert (snapshot_root / "transform" / "placeholders.py").read_bytes() == placeholders
    assert (snapshot_root / "transform" / "prose-regression.py").read_bytes() == prose
    assert (snapshot_root / "transform" / "short-value.py").read_bytes() == b"short\n"
    artifact_bytes = b"".join(
        path.read_bytes()
        for path in sorted(history_dir.rglob("*"))
        if path.is_file()
    )
    for content in refused.values():
        assert content not in artifact_bytes
        assert hashlib.sha256(content).hexdigest().encode() not in artifact_bytes

    symlink_state = _copy_state(tmp_path / "symlink-state")
    symlink_digest = "364357cc65421365af8ada2184af76420e5f065325e96c254bbef8fa3985fa84"
    capture = symlink_state / "captures" / "sha256" / symlink_digest
    outside = tmp_path / "outside-capture"
    outside.mkdir()
    shutil.rmtree(capture)
    capture.symlink_to(outside, target_is_directory=True)
    symlink_artifacts = tmp_path / "symlink-artifacts"
    symlink_history = SupervisorHistory(symlink_artifacts)
    symlink_history.observe_turn(
        turn=4,
        observations=_turn_observations(4),
        built_runs=set(),
        state_dir=symlink_state,
    )
    symlink_history.write()
    symlink_entry = _capture_entry(symlink_artifacts, symlink_digest)
    assert symlink_entry["files"] == []
    assert {
        item["reason"] for item in symlink_entry["skipped"]
    } == {"capture_path_refused"}


def _replace_retained_capture_root(
    observations: list[dict[str, object]], raw_root: str
) -> None:
    for observation in observations:
        if not isinstance(observation.get("result"), dict):
            continue
        payload = observation["result"]
        requirements = payload.get("requirements")
        if not isinstance(requirements, list):
            continue
        for requirement in requirements:
            if (
                isinstance(requirement, dict)
                and requirement.get("id") == "review"
                and isinstance(requirement.get("review_input"), dict)
            ):
                requirement["review_input"]["retained_capture_root"] = raw_root


def test_capture_result_only_uses_digest_suffix_and_ignores_invalid_or_missing_roots(
    tmp_path: Path,
) -> None:
    digest = "d311b62892792fe9d8f16ca167a23968f405a45c0ffe842a1272a12f50c4db02"
    outside_state = _copy_state(tmp_path / "outside-prefix-state")
    outside_artifacts = tmp_path / "outside-prefix-artifacts"
    outside_observations = _turn_observations(13)
    _replace_retained_capture_root(
        outside_observations,
        f"/untrusted/outside/prefix/captures/sha256/{digest}",
    )
    outside_history = SupervisorHistory(outside_artifacts)
    outside_history.observe_turn(
        turn=13,
        observations=outside_observations,
        built_runs=set(),
        state_dir=outside_state,
    )
    outside_history.write()
    outside_entry = _capture_entry(outside_artifacts, digest)
    assert outside_entry["sources"] == ["capture_result"]
    assert outside_entry["first_turn"] == 13
    assert outside_entry["workflow_ids"] == [WORKFLOW_CRM]
    assert outside_entry["run_ids"] == []
    source = outside_state / "captures" / "sha256" / digest / "transform" / "main.py"
    snapshot = outside_artifacts / "supervisor-captures" / digest / "transform" / "main.py"
    assert snapshot.read_bytes() == source.read_bytes()
    outside_bytes = b"".join(
        path.read_bytes()
        for path in sorted(outside_artifacts.rglob("*"))
        if path.is_file()
    )
    assert b"/untrusted/outside/prefix" not in outside_bytes

    for case, raw_root in (
        ("bad-suffix", f"/untrusted/captures/not-sha256/{digest}"),
        (
            "missing-root",
            "/untrusted/captures/sha256/"
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        ),
    ):
        state_dir = _copy_state(tmp_path / f"{case}-state")
        artifact_dir = tmp_path / f"{case}-artifacts"
        observations = _turn_observations(13)
        _replace_retained_capture_root(observations, raw_root)
        history = SupervisorHistory(artifact_dir)
        history.observe_turn(
            turn=13,
            observations=observations,
            built_runs=set(),
            state_dir=state_dir,
        )
        history.write()
        captures = _read_json(artifact_dir / "supervisor-captures.json")["captures"]
        assert all(item["capture_sha256"] != f"sha256:{digest}" for item in captures)
        if case == "missing-root":
            assert all(
                item["capture_sha256"]
                != "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
                for item in captures
            )


def test_missing_capture_result_root_does_not_add_source_to_admission_entry(
    tmp_path: Path,
) -> None:
    digest = "364357cc65421365af8ada2184af76420e5f065325e96c254bbef8fa3985fa84"
    state_dir = _copy_state(tmp_path / "missing-admission-capture-state")
    shutil.rmtree(state_dir / "captures" / "sha256" / digest)
    artifact_dir = tmp_path / "missing-admission-capture-artifacts"
    history = SupervisorHistory(artifact_dir)
    history.observe_turn(
        turn=4,
        observations=_turn_observations(4),
        built_runs=set(),
        state_dir=state_dir,
    )
    history.write()

    entry = _capture_entry(artifact_dir, digest)
    assert entry["sources"] == ["admission"]
    assert entry["run_ids"]
    assert entry["skipped"] == [
        {"path": ".", "reason": "missing_capture_root"}
    ]


@pytest.mark.parametrize("cap_kind", ["per_file", "total"])
def test_capture_size_caps_mark_the_snapshot_truncated(
    tmp_path: Path,
    cap_kind: str,
) -> None:
    state_dir = _copy_state(tmp_path / f"{cap_kind}-state")
    digest = "364357cc65421365af8ada2184af76420e5f065325e96c254bbef8fa3985fa84"
    capture_root = state_dir / "captures" / "sha256" / digest
    if cap_kind == "per_file":
        target = capture_root / "transform" / "oversized.py"
        target.write_bytes(b"x" * (CAPTURE_FILE_LIMIT + 1))
    else:
        target_dir = capture_root / "contracts" / "promises"
        target_dir.mkdir(parents=True, exist_ok=True)
        for index in range(5):
            (target_dir / f"cap-{index}.py").write_bytes(b"x" * 500_000)

    artifact_dir = tmp_path / f"{cap_kind}-artifacts"
    history = SupervisorHistory(artifact_dir)
    history.observe_turn(
        turn=4,
        observations=_turn_observations(4),
        built_runs=set(),
        state_dir=state_dir,
    )
    history.write()
    entry = _capture_entry(artifact_dir, digest)
    assert entry["truncated"] is True
    assert sum(item["size"] for item in entry["files"]) <= CAPTURE_TOTAL_LIMIT
    if cap_kind == "per_file":
        assert ("transform/oversized.py", "per_file_size_cap") in {
            (item["path"], item["reason"]) for item in entry["skipped"]
        }
    else:
        assert any(
            item["reason"] == "total_size_cap" for item in entry["skipped"]
        )


def _definition_dir(state_dir: Path, definition_id: str) -> Path:
    digest = definition_id.removeprefix("sha256-v1:")
    return state_dir / "definitions" / "sha256-v1" / digest


def test_definition_export_matches_both_compiled_manifests_and_inventory(
    tmp_path: Path,
) -> None:
    state_dir = _copy_state(tmp_path / "state")
    artifact_dir = tmp_path / "artifacts"
    _replay(state_dir, artifact_dir)

    document = _read_json(artifact_dir / "definition-export.json")
    assert document["schema"] == DEFINITION_EXPORT_SCHEMA
    definitions = document["definitions"]
    assert isinstance(definitions, list) and len(definitions) == 2
    fixture_manifest = json.loads(MANIFEST_FIXTURE.read_text(encoding="utf-8"))
    expected_names = sorted([
        "current-deals-non-deleted",
        "current-deals-no-owner-pii",
        "current-deals-no-ranking",
    ])
    expected_descriptions = {
        "current-deals-non-deleted": "Every output row is a current (non-deleted) deal.",
        "current-deals-no-owner-pii": (
            "No output row, and no other stored surface of this product, "
            "includes owner name or owner email."
        ),
        "current-deals-no-ranking": (
            "No row or field in this output represents a priority or attention ranking."
        ),
    }
    for workflow, identity in fixture_manifest["ids"]["workflows"].items():
        definition_id = identity["definition_id"]
        item = next(row for row in definitions if row["definition_id"] == definition_id)
        assert item["present"] is True
        assert item["inventory_valid"] is True
        assert item["workflow_ids"] == [workflow]
        assert item["run_ids"] == [identity["run_id"]]
        assert item["input_expectations"] == []
        assert item["model_promises"] == [
            {"port": "duckdb", "models": ["deals", "nxd_decisions"]}
        ]
        promises = item["output_promises"]
        assert [promise["name"] for promise in promises] == expected_names
        source_dir = _definition_dir(state_dir, definition_id)
        inventory = json.loads(
            (source_dir / "definition.json").read_text(encoding="utf-8")
        )
        hashes = {
            entry["path"]: entry["sha256"] for entry in inventory["files"]
        }
        for promise in promises:
            assert promise["port"] == "duckdb"
            assert promise["description"] == expected_descriptions[promise["name"]]
            assert promise["models"] == ["deals"]
            assert promise["source"] == (
                f"contracts/promises/{promise['name']}.py"
            )
            assert promise["verifier_kind"] == "script"
            assert promise["source_in_inventory"] is True
            assert promise["source_sha256"] == hashes[promise["source"]]
            assert promise["driver"] == "nxd:local/python/compute:0.1.0"

    corrupt_state = _copy_state(tmp_path / "corrupt-state")
    corrupt_id = fixture_manifest["ids"]["workflows"][WORKFLOW_CRM][
        "definition_id"
    ]
    (_definition_dir(corrupt_state, corrupt_id) / "manifest.yaml").write_text(
        ": [[",
        encoding="utf-8",
    )
    corrupt_artifacts = tmp_path / "corrupt-artifacts"
    _replay(corrupt_state, corrupt_artifacts)
    corrupt_definitions = _read_json(
        corrupt_artifacts / "definition-export.json"
    )["definitions"]
    corrupt_entry = next(
        row for row in corrupt_definitions if row["definition_id"] == corrupt_id
    )
    assert corrupt_entry["present"] is True
    assert corrupt_entry["inventory_valid"] is True
    assert corrupt_entry["output_promises"] == []
    assert corrupt_entry["model_promises"] == []


def test_invalid_definition_id_is_not_exported(tmp_path: Path) -> None:
    state_dir = _copy_state(tmp_path / "state")
    connection = sqlite3.connect(state_dir / "state.sqlite3")
    connection.execute(
        "UPDATE runs SET definition_id = 'invalid-definition-id' WHERE run_id = ?",
        (RUN_CRM,),
    )
    connection.commit()
    connection.close()
    workflow_key = "wf-sha256-v1-d3fcb896676640e8597596f0aea71dcfbcb460aa2f48f5849c28ad79b1d65b2f"
    release = next(
        (state_dir / "workflows" / workflow_key / "releases").glob("release-*.json")
    )
    release_doc = json.loads(release.read_text(encoding="utf-8"))
    release_doc["definition_id"] = "invalid-definition-id"
    release.write_text(json.dumps(release_doc), encoding="utf-8")

    artifact_dir = tmp_path / "artifacts"
    _replay(state_dir, artifact_dir)
    definitions = _read_json(artifact_dir / "definition-export.json")["definitions"]
    assert all(
        item["definition_id"] != "invalid-definition-id"
        for item in definitions
    )
    assert len(definitions) == 1


def test_history_replay_is_byte_deterministic_and_contains_no_host_paths(
    tmp_path: Path,
) -> None:
    first_state = _copy_state(tmp_path / "state-one")
    second_state = _copy_state(tmp_path / "state-two")
    first_artifacts = tmp_path / "artifacts-one"
    second_artifacts = tmp_path / "artifacts-two"
    _replay(first_state, first_artifacts)
    _replay(second_state, second_artifacts)

    first = _read_only_tree(first_artifacts)
    second = _read_only_tree(second_artifacts)
    assert first == second
    forbidden = (
        str(tmp_path).encode(),
        b"/private/",
        b"/Users/",
        b"/Volumes/",
    )
    for content in first.values():
        assert all(marker not in content for marker in forbidden)


def test_history_restart_continues_turns_and_keeps_keys_unique(
    tmp_path: Path,
) -> None:
    state_dir = _copy_state(tmp_path / "state")
    artifact_dir = tmp_path / "artifacts"
    history, _facts, _built = _replay(state_dir, artifact_dir)
    assert history is not None
    assert history.last_turn == 22
    before_calls = len(_read_json(artifact_dir / "tool-calls.json")["calls"])
    before_releases = len(
        _read_json(artifact_dir / "publication-history.json")["releases"]
    )
    before_runs = len(_read_json(artifact_dir / "run-records.json")["runs"])

    resumed = SupervisorHistory(artifact_dir)
    assert resumed.last_turn == 22
    resumed.observe_turn(
        turn=resumed.last_turn + 1,
        observations=[],
        built_runs=set(),
        state_dir=state_dir,
    )
    resumed.write()

    calls = _read_json(artifact_dir / "tool-calls.json")
    assert calls["last_turn"] == 23
    assert len(calls["calls"]) == before_calls
    releases = _read_json(artifact_dir / "publication-history.json")["releases"]
    runs = _read_json(artifact_dir / "run-records.json")["runs"]
    assert len(releases) == before_releases == 2
    assert len(runs) == before_runs == 2
    assert len(
        {
            (item["workflow_id"], item["publish_sequence"], item["run_id"])
            for item in releases
        }
    ) == 2


def test_native_resume_replaces_timed_out_turn_history_without_shifting_turns(
    tmp_path: Path,
) -> None:
    state_dir = _copy_state(tmp_path / "state")
    artifact_dir = tmp_path / "artifacts"
    history = SupervisorHistory(artifact_dir)
    history.observe_turn(
        turn=1,
        observations=[
            {
                "tool": "run_semantic_query",
                "arguments": {"endpoint": "http://127.0.0.1:1234/mcp/"},
                "result": {"columns": ["value"], "rows": [["turn-one"]]},
                "is_error": False,
                "answered": True,
            }
        ],
        built_runs=set(),
        state_dir=None,
    )
    history.write()

    first_capture = "364357cc65421365af8ada2184af76420e5f065325e96c254bbef8fa3985fa84"
    second_capture = "e034d41af65f2b6dcd3ad308594b0a00d79504710e02d47249e2ecbaefc85691"
    timed_out = SupervisorHistory(artifact_dir)
    timed_out.observe_turn(
        turn=2,
        observations=[
            *_retry_turn_observations(
                workflow=WORKFLOW_CRM,
                run_id=RUN_CRM,
                request_id="crm-retry-two",
                query_value="aborted-turn-two",
                exception_class="ValueError",
                capture_digest=first_capture,
            ),
            {
                "tool": "assistant_text",
                "arguments": {},
                "result": "aborted attempt only",
                "is_error": False,
                "answered": True,
            },
        ],
        built_runs={RUN_CRM},
        state_dir=state_dir,
    )
    timed_out.write()

    resumed = SupervisorHistory(artifact_dir)
    assert resumed.last_turn == 2
    adapter = object.__new__(ClaudeCodeAdapter)
    adapter.artifact_dir = artifact_dir
    adapter._history = resumed
    adapter._turn = 2
    adapter._process = SimpleNamespace(stdin=io.BytesIO())
    adapter._read_until_result = lambda: []  # type: ignore[method-assign]
    adapter._finish_turn = lambda _events: None  # type: ignore[method-assign]
    adapter.send(
        {
            "type": "turn",
            "turn": 2,
            "message": {"text": "native resume retry", "attachments": []},
        }
    )
    assert _read_json(artifact_dir / "tool-calls.json")["last_turn"] == 1
    assert _read_json(artifact_dir / "run-records.json")["runs"] == []
    assert _read_json(artifact_dir / "run-failures.json")["failures"] == []
    assert _read_json(artifact_dir / "supervisor-captures.json")["captures"] == []

    resumed.observe_turn(
        turn=2,
        observations=_retry_turn_observations(
            workflow=WORKFLOW_CRM,
            run_id=RUN_CRM,
            request_id="crm-retry-two",
            query_value="retry-turn-two",
            exception_class="KeyError",
            capture_digest=first_capture,
        ),
        built_runs={RUN_CRM},
        state_dir=state_dir,
    )
    resumed.write()
    resumed.observe_turn(
        turn=3,
        observations=_retry_turn_observations(
            workflow=WORKFLOW_CRM_V2,
            run_id=RUN_CRM_V2,
            request_id="crm-retry-three",
            query_value="turn-three",
            exception_class="TypeError",
            capture_digest=second_capture,
        ),
        built_runs={RUN_CRM_V2},
        state_dir=state_dir,
    )
    resumed.write()

    calls = _read_json(artifact_dir / "tool-calls.json")
    assert calls["last_turn"] == 3
    assert [call["turn"] for call in calls["calls"]].count(2) == 4
    assert [call["turn"] for call in calls["calls"]].count(3) == 4
    assert all(call["tool"] != "assistant_text" for call in calls["calls"])

    queries = _read_json(artifact_dir / "query-history.json")["queries"]
    assert [
        (query["turn"], query["rows"][0]["value"])
        for query in queries
    ] == [(1, "turn-one"), (2, "retry-turn-two"), (3, "turn-three")]

    runs = _read_json(artifact_dir / "run-records.json")["runs"]
    assert {
        item["run_id"]: item["start_turn"] for item in runs
    } == {RUN_CRM: 2, RUN_CRM_V2: 3}
    failures = _read_json(artifact_dir / "run-failures.json")["failures"]
    retry_failures = [
        item for item in failures if item["source"] == "tool_result"
    ]
    assert {(item["turn"], item["exception_class"]) for item in retry_failures} == {
        (2, "KeyError"),
        (3, "TypeError"),
    }
    captures = _read_json(artifact_dir / "supervisor-captures.json")["captures"]
    assert {
        item["capture_sha256"]: item["first_turn"] for item in captures
    } == {
        f"sha256:{first_capture}": 2,
        f"sha256:{second_capture}": 3,
    }


def test_state_directory_is_read_only_and_locked_or_corrupt_sqlite_degrades(
    tmp_path: Path,
) -> None:
    state_dir = _copy_state(tmp_path / "state")
    before = _read_only_tree(state_dir)
    artifact_dir = tmp_path / "artifacts"
    _replay(state_dir, artifact_dir)
    after = _read_only_tree(state_dir)
    assert after == before

    locked_state = _copy_state(tmp_path / "locked-state")
    locked_history = SupervisorHistory(tmp_path / "locked-artifacts")
    locker = sqlite3.connect(locked_state / "state.sqlite3")
    locker.execute("BEGIN EXCLUSIVE")
    try:
        locked_history.observe_turn(
            turn=1,
            observations=[],
            built_runs=set(),
            state_dir=locked_state,
        )
        locked_history.write()
    finally:
        locker.rollback()
        locker.close()

    corrupt_state = tmp_path / "corrupt-state"
    corrupt_state.mkdir()
    (corrupt_state / "state.sqlite3").write_bytes(b"not a sqlite database")
    corrupt_history = SupervisorHistory(tmp_path / "corrupt-artifacts")
    corrupt_history.observe_turn(
        turn=1,
        observations=[],
        built_runs=set(),
        state_dir=corrupt_state,
    )
    corrupt_history.write()
    assert _read_json(
        tmp_path / "corrupt-artifacts" / "run-records.json"
    )["runs"] == []


def test_snapshot_workspace_skips_every_new_history_artifact(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    artifact_dir = tmp_path / "runner-artifacts"
    filenames = (
        "publication-history.json",
        "run-records.json",
        "run-failures.json",
        "tool-calls.json",
        "query-history.json",
        "supervisor-captures.json",
        "definition-export.json",
    )
    for filename in filenames:
        (workspace / filename).write_text("runner evidence", encoding="utf-8")
    capture_tree = workspace / "supervisor-captures"
    capture_tree.mkdir()
    (capture_tree / "digest" / "spec.py").parent.mkdir(parents=True)
    (capture_tree / "digest" / "spec.py").write_text("agent-looking file")

    snapshot = adapter_module._snapshot_workspace(
        workspace,
        artifact_dir=artifact_dir,
    )
    assert snapshot == {}


def _make_adapter(artifact_dir: Path) -> ClaudeCodeAdapter:
    """Construct the transport adapter without starting a child process."""

    return ClaudeCodeAdapter(
        claude=Path("/usr/bin/false"),
        model="test-model",
        effort="low",
        plugin_dir=REPO_ROOT,
        repo_root=REPO_ROOT,
        fixture_dir=FIXTURE_ROOT,
        artifact_dir=artifact_dir,
        desktop_supervisor=Path("/usr/bin/false"),
        desktop_python=Path("/usr/bin/python3"),
        claude_config_dir=None,
        timeout_s=1,
        max_budget_usd=None,
        append_system_prompt="",
        supervisor_data_dir=None,
    )


def test_adapter_turn_counter_resumes_and_finish_hook_writes_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact_dir = tmp_path / "adapter-artifacts"
    adapter = _make_adapter(artifact_dir)
    adapter._process = SimpleNamespace(stdin=io.BytesIO())
    adapter._read_until_result = lambda: []  # type: ignore[method-assign]
    adapter._finish_turn = lambda events, **kwargs: None  # type: ignore[method-assign]
    adapter.send({"turn": 5, "message": {"text": "first"}})
    assert adapter._turn == 5
    adapter.send({"message": {"text": "second"}})
    assert adapter._turn == 6

    history = SupervisorHistory(artifact_dir)
    adapter._history = history
    history.observe_turn(
        turn=adapter._turn,
        observations=[],
        built_runs=set(),
        state_dir=None,
    )
    history.write()
    restarted = _make_adapter(artifact_dir)
    assert restarted._turn == 6

    actual = _make_adapter(tmp_path / "finish-artifacts")
    actual._turn = 1
    monkeypatch.setattr(
        adapter_module,
        "_snapshot_workspace",
        lambda *args, **kwargs: {},
    )
    actual._finish_turn([])
    assert _read_json(
        tmp_path / "finish-artifacts" / "tool-calls.json"
    )["last_turn"] == 1
    assert _read_json(
        tmp_path / "finish-artifacts" / "query-history.json"
    )["schema"] == QUERY_HISTORY_SCHEMA


def test_adapter_history_uses_current_credential_env_values_without_persisting_them(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_value = "source-secret-value"
    trusted_value = "trusted-metrics-secret"
    api_token_value = "my-api-token-secret-value"
    short_value = "brief"
    monkeypatch.setenv("NXD_EVAL_SOURCE_TOKEN", source_value)
    monkeypatch.setenv(
        "NXD_DESKTOP_TRUSTED_CREDENTIAL_ENVS",
        "metrics=TRUSTED_METRICS_TOKEN",
    )
    monkeypatch.setenv("TRUSTED_METRICS_TOKEN", trusted_value)
    monkeypatch.setenv("MY_API_TOKEN", api_token_value)
    monkeypatch.setenv("NXD_SHORT_API_TOKEN", short_value)

    state_dir = _copy_state(tmp_path / "adapter-secret-state")
    digest = "d311b62892792fe9d8f16ca167a23968f405a45c0ffe842a1272a12f50c4db02"
    capture_root = state_dir / "captures" / "sha256" / digest / "transform"
    refused_contents = {
        "source-value.py": f"token = '{source_value}'\n".encode(),
        "trusted-value.py": f"token = '{trusted_value}'\n".encode(),
        "api-value.py": f"token = '{api_token_value}'\n".encode(),
    }
    for filename, content in refused_contents.items():
        (capture_root / filename).write_bytes(content)
    short_content = f"example = '{short_value}'\n".encode()
    (capture_root / "short-value.py").write_bytes(short_content)

    actual = _make_adapter(tmp_path / "adapter-secret-artifacts")
    monkeypatch.setattr(adapter_module, "_snapshot_workspace", lambda *args, **kwargs: {})
    actual._state_dir = state_dir
    actual._turn = 13
    actual._finish_turn([])

    assert actual._history is not None
    actual._history.observe_turn(
        turn=13,
        observations=_turn_observations(13),
        built_runs=set(),
        state_dir=state_dir,
    )
    actual._history.write()
    expected = {source_value, trusted_value, api_token_value}
    secret_values = set(actual._history._secret_values)
    assert {
        value.encode("utf-8") for value in expected
    } <= secret_values
    assert short_value.encode("utf-8") not in secret_values
    entry = _capture_entry(actual.artifact_dir, digest)
    skipped = {item["path"]: item["reason"] for item in entry["skipped"]}
    assert {
        path: skipped[path] for path in (
            "transform/source-value.py",
            "transform/trusted-value.py",
            "transform/api-value.py",
        )
    } == {
        "transform/source-value.py": "secret_value",
        "transform/trusted-value.py": "secret_value",
        "transform/api-value.py": "secret_value",
    }
    assert "transform/short-value.py" in {
        item["path"] for item in entry["files"]
    }
    short_snapshot = (
        actual.artifact_dir
        / "supervisor-captures"
        / digest
        / "transform"
        / "short-value.py"
    )
    assert short_snapshot.read_bytes() == short_content
    artifact_bytes = b"".join(
        path.read_bytes()
        for path in sorted(actual.artifact_dir.rglob("*"))
        if path.is_file()
    )
    for value in (source_value, trusted_value, api_token_value):
        encoded = value.encode("utf-8")
        assert encoded not in artifact_bytes
        assert hashlib.sha256(encoded).hexdigest().encode() not in artifact_bytes
    assert hashlib.sha256(short_value.encode()).hexdigest().encode() not in artifact_bytes


def test_adapter_ignores_invalid_trusted_credential_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("NXD_EVAL_SOURCE_TOKEN", raising=False)
    monkeypatch.setenv(
        "NXD_DESKTOP_TRUSTED_CREDENTIAL_ENVS",
        "metrics=FIRST_RUNTIME_VALUE,metrics=SECOND_RUNTIME_VALUE",
    )
    monkeypatch.setenv("FIRST_RUNTIME_VALUE", "first-trusted-secret")
    monkeypatch.setenv("SECOND_RUNTIME_VALUE", "second-trusted-secret")

    values = set(adapter_module._supervisor_history_secret_values(REPO_ROOT))
    assert "first-trusted-secret" not in values
    assert "second-trusted-secret" not in values
