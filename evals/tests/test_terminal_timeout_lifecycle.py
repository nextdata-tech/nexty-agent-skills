"""Contract tests for the terminal timeout/lifecycle scenario."""

from __future__ import annotations

import importlib
import json
import os
import stat
import subprocess
import sys
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCENARIO = ROOT / "evals/public/terminal-timeout-lifecycle"
CHECKER = SCENARIO / "fixtures/check_terminal_timeout_lifecycle.py"
PROFILE_BUILDER = SCENARIO / "fixtures/prepare_stdio_profile.py"
if str(ROOT / "evals") not in sys.path:
    sys.path.insert(0, str(ROOT / "evals"))
eval_run = importlib.import_module("run")


def _record(direction: str, message: dict, **metadata: object) -> dict:
    return {
        "source": "runner",
        "protocol": "mcp",
        "direction": direction,
        "message": message,
        **metadata,
    }


def _trace(
    tmp_path: Path,
    *,
    include_late: bool = True,
    include_resume: bool = True,
    duplicate_field: str = "duplicate_builds",
    duplicate_value: object = 0,
) -> Path:
    build_request = _record(
        "request",
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "build_data_product", "arguments": {"workflow": "terminal-timeout-lifecycle"}}},
    )
    timeout = _record(
        "response",
        {"jsonrpc": "2.0", "id": 1, "error": {"code": -32098, "message": "client deadline exceeded", "data": {"method": "build_data_product", "timeout_ms": 80}}},
        synthetic=True,
        timeout_fault=True,
        forwarded=True,
    )
    inspect_request = _record(
        "request",
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "inspect_run", "arguments": {}}},
    )
    inspect_response = _record(
        "response",
        {"jsonrpc": "2.0", "id": 2, "result": {"content": [{"type": "text", "text": json.dumps({
            "run_id": "run-1",
            duplicate_field: duplicate_value,
            "state": "continued",
            "configured_budget_ms": 3000,
            "elapsed_ms": 90,
            "active_stage": "pagination",
            "resource": "events",
            "retry_count": 0,
            "page_count": 2,
            "request_count": 2,
        })}]}},
        forwarded=True,
    )
    pre_publish_list_request = _record(
        "request",
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "list_data_products", "arguments": {}}},
    )
    pre_publish_list_response = _record(
        "response",
        {"jsonrpc": "2.0", "id": 3, "result": {"content": [{"type": "text", "text": json.dumps({"products": []})}]}},
        forwarded=True,
    )
    retry_request = _record(
        "request",
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "build_data_product", "arguments": {"workflow": "terminal-timeout-lifecycle", "budget_ms": 6000}}},
    )
    retry_response = _record(
        "response",
        {"jsonrpc": "2.0", "id": 4, "result": {"content": [{"type": "text", "text": json.dumps({"run_id": "run-2", "state": "terminal", "published": True})}]}},
        forwarded=True,
    )
    post_retry_inspect_request = _record(
        "request",
        {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "inspect_run", "arguments": {"run_id": "run-2"}}},
    )
    post_retry_inspect_response = _record(
        "response",
        {"jsonrpc": "2.0", "id": 5, "result": {"content": [{"type": "text", "text": json.dumps({
            "run_id": "run-2", duplicate_field: duplicate_value,
            "state": "terminal",
            "configured_budget_ms": 6000, "elapsed_ms": 180,
            "active_stage": "read-back", "resource": "events", "retry_count": 1,
            "page_count": 3, "request_count": 3,
        })}]}},
        forwarded=True,
    )
    post_publish_list_request = _record(
        "request",
        {"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "list_data_products", "arguments": {}}},
    )
    post_publish_list_response = _record(
        "response",
        {"jsonrpc": "2.0", "id": 6, "result": {"content": [{"type": "text", "text": json.dumps({"products": [{"workflow": "terminal-timeout-lifecycle", "artifact_status": "available", "publish_seq": 1}]})}]}},
        forwarded=True,
    )
    resume_request = _record(
        "request",
        {"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": "resume_data_product", "arguments": {"workflow": "terminal-timeout-lifecycle"}}},
    )
    resume_response = _record(
        "response",
        {"jsonrpc": "2.0", "id": 7, "result": {"content": [{"type": "text", "text": json.dumps({"workflow": "terminal-timeout-lifecycle", "semantic_endpoint": "http://127.0.0.1:9999/mcp", "bearer_token": "<redacted>"})}]}},
        forwarded=True,
    )
    failed_build_request = _record(
        "request",
        {"jsonrpc": "2.0", "id": 8, "method": "tools/call", "params": {"name": "build_data_product", "arguments": {"workflow": "terminal-timeout-lifecycle-failed"}}},
    )
    failed_build_response = _record(
        "response",
        {"jsonrpc": "2.0", "id": 8, "result": {"isError": True, "content": [{"type": "text", "text": json.dumps({"status": "failed", "code": "runtime/transform_failed"})}]}},
        forwarded=True,
    )
    failed_inspect_request = _record(
        "request",
        {"jsonrpc": "2.0", "id": 9, "method": "tools/call", "params": {"name": "inspect_run", "arguments": {"run_id": "run-failed"}}},
    )
    failed_inspect_response = _record(
        "response",
        {"jsonrpc": "2.0", "id": 9, "result": {"content": [{"type": "text", "text": json.dumps({"run_id": "run-failed", "state": "failed"})}]}},
        forwarded=True,
    )
    failed_listing_request = _record(
        "request",
        {"jsonrpc": "2.0", "id": 10, "method": "tools/call", "params": {"name": "list_data_products", "arguments": {}}},
    )
    failed_listing_response = _record(
        "response",
        {"jsonrpc": "2.0", "id": 10, "result": {"content": [{"type": "text", "text": json.dumps({"products": [{"workflow": "terminal-timeout-lifecycle", "artifact_status": "available", "publish_seq": 1}]})}]}},
        forwarded=True,
    )
    records = [
        build_request,
        timeout,
        inspect_request,
        inspect_response,
        pre_publish_list_request,
        pre_publish_list_response,
        retry_request,
        retry_response,
        post_retry_inspect_request,
        post_retry_inspect_response,
        post_publish_list_request,
        post_publish_list_response,
        failed_build_request,
        failed_build_response,
        failed_inspect_request,
        failed_inspect_response,
        failed_listing_request,
        failed_listing_response,
    ]
    if include_resume:
        records[12:12] = [resume_request, resume_response]
    if include_late:
        records.append(
            _record(
                "response",
                {"jsonrpc": "2.0", "id": 1, "result": {"content": [{"type": "text", "text": "late"}]}},
                forwarded=False,
                late=True,
            )
        )
    path = tmp_path / "trace.jsonl"
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")
    return path


def _published_after_timeout_trace(tmp_path: Path) -> Path:
    def response(request_id: int, payload: dict, **metadata: object) -> dict:
        return _record(
            "response",
            {"jsonrpc": "2.0", "id": request_id, "result": {"content": [{"type": "text", "text": json.dumps(payload)}]}},
            forwarded=True,
            **metadata,
        )

    records = [
        _record(
            "request",
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
                "name": "build_data_product",
                "arguments": {"workflow": "terminal-timeout-lifecycle"},
            }},
        ),
        _record(
            "response",
            {"jsonrpc": "2.0", "id": 1, "error": {
                "code": -32098,
                "message": "client deadline exceeded",
                "data": {"method": "build_data_product", "timeout_ms": 80},
            }},
            synthetic=True,
            timeout_fault=True,
            forwarded=True,
        ),
        _record(
            "response",
            {"jsonrpc": "2.0", "id": 1, "result": {"published": True}},
            forwarded=False,
            late=True,
        ),
        _record(
            "request",
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
                "name": "inspect_run", "arguments": {},
            }},
        ),
        response(2, {"run": {
            "run_id": "run-1",
            "workflow": "terminal-timeout-lifecycle",
            "status": "Published",
            "lifecycle": "terminal",
            "publish_seq": 1,
        }}),
        _record(
            "request",
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
                "name": "list_data_products", "arguments": {},
            }},
        ),
        response(3, {"products": [{
            "workflow": "terminal-timeout-lifecycle",
            "artifact_status": "available",
            "publish_seq": 1,
        }]}),
        _record(
            "request",
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {
                "name": "resume_data_product",
                "arguments": {"workflow": "terminal-timeout-lifecycle"},
            }},
        ),
        response(4, {
            "workflow": "terminal-timeout-lifecycle",
            "run_id": "run-1",
            "publish_seq": 1,
            "semantic_endpoint": "http://127.0.0.1:9999/mcp",
        }),
        _record(
            "request",
            {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {
                "name": "build_data_product",
                "arguments": {"workflow": "terminal-timeout-failed-build"},
            }},
        ),
        _record(
            "response",
            {"jsonrpc": "2.0", "id": 5, "result": {
                "isError": True,
                "content": [{"type": "text", "text": json.dumps({"status": "failed"})}],
            }},
            forwarded=True,
        ),
        _record(
            "request",
            {"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {
                "name": "inspect_run", "arguments": {"run_id": "run-failed"},
            }},
        ),
        response(6, {"run": {
            "run_id": "run-failed",
            "workflow": "terminal-timeout-failed-build",
            "status": "Failed",
            "lifecycle": "terminal",
        }}),
        _record(
            "request",
            {"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {
                "name": "list_data_products", "arguments": {},
            }},
        ),
        response(7, {"products": [{
            "workflow": "terminal-timeout-lifecycle",
            "artifact_status": "available",
            "publish_seq": 1,
        }]}),
    ]
    path = tmp_path / "published-after-timeout-trace.jsonl"
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")
    return path


def _run_checker(
    tmp_path: Path,
    *,
    include_late: bool = True,
    trace: Path | None = None,
    observation_records: list[object] | None = None,
    observation_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    trace = trace or _trace(tmp_path, include_late=include_late)
    observations = tmp_path / "observations.jsonl"
    if observation_records is None:
        observation_records = [
            {
                "path": f"/v1/events?page={page}&per_page=10",
                "status": 200,
                "authorized": True,
                "page": page,
                "rows": rows,
                "total": 23,
            }
            for page, rows in ((1, 10), (2, 10), (3, 3))
        ]
    observations.write_text(
        observation_text
        if observation_text is not None
        else "\n".join(json.dumps(record) for record in observation_records) + "\n",
        encoding="utf-8",
    )
    return subprocess.run(
        [sys.executable, str(CHECKER), "--fixtures", str(SCENARIO / "fixtures"), "--root", str(tmp_path), "--trace", str(trace)],
        capture_output=True,
        text=True,
        env={**os.environ, "NXD_STUB_OBSERVATIONS": str(observations)},
        check=False,
    )


def test_scenario_wires_one_shot_timeout_fault_and_withheld_checker() -> None:
    checks = json.loads((SCENARIO / "checks.json").read_text(encoding="utf-8"))
    stdio = json.loads((SCENARIO / "fixtures/desktop_stdio.json").read_text(encoding="utf-8"))
    run_text = (ROOT / "evals/run.py").read_text(encoding="utf-8")
    assert checks["deterministic_check"]["trace_source"] == "runner_mcp"
    assert stdio["request_timeout_faults"]["build_data_product"] == {
        "after_ms": 80,
        "once": True,
        "workflow": "terminal-timeout-lifecycle",
    }
    assert stdio["profile_builder"] == "prepare_stdio_profile.py"
    assert "terminal-timeout-lifecycle" in run_text
    assert (SCENARIO / "fixtures/check_terminal_timeout_lifecycle.py").is_file()


def test_profile_builder_does_not_stage_mapper_reference_closure(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    output = tmp_path / "stdio-profile.json"
    result = subprocess.run(
        [
            sys.executable,
            str(PROFILE_BUILDER),
            "--workspace",
            str(workspace),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert list(workspace.iterdir()) == []
    profile = json.loads(output.read_text(encoding="utf-8"))
    assert profile["schema"] == "nxd-synthetic-evaluation-profile-v1"
    assert stat.S_IMODE(output.stat().st_mode) == 0o444
    assert "reference-closure" not in PROFILE_BUILDER.read_text(encoding="utf-8")


def test_source_token_is_runner_injected_not_brief_literal() -> None:
    spec = json.loads((SCENARIO / "fixtures/http_stub.json").read_text(encoding="utf-8"))
    agent_env = eval_run._http_stub_agent_env(SCENARIO, spec)
    assert agent_env["NXD_EVAL_SOURCE_TOKEN"]
    brief = (SCENARIO / "fixtures/BRIEF.md").read_text(encoding="utf-8")
    assert "$NXD_EVAL_SOURCE_TOKEN" in brief
    assert "nex888-opaque-synthetic-secret-2d4c" not in brief


def test_http_fixture_keeps_page_size_fixed(tmp_path: Path) -> None:
    spec = json.loads((SCENARIO / "fixtures/http_stub.json").read_text(encoding="utf-8"))
    token = eval_run._http_stub_agent_env(SCENARIO, spec)["NXD_EVAL_SOURCE_TOKEN"]
    with eval_run.http_stub_server(SCENARIO, tmp_path, spec, "claude") as (base, _log):
        request = urllib.request.Request(
            f"{base}/v1/events?page=1&per_page=23",
            headers={"Authorization": f"Bearer {token}"},
        )
        payload = json.loads(urllib.request.urlopen(request, timeout=5).read())
    assert payload["per_page"] == 10
    assert payload["pages"] == 3
    assert len(payload["data"]) == 10


def test_runner_redacts_injected_secret_from_agent_artifacts() -> None:
    trace, metrics, leaked = eval_run._redact_agent_artifacts(
        "[tool_result] value: nex888-opaque-synthetic-secret-2d4c",
        {"final_answer": "nex888-opaque-synthetic-secret-2d4c"},
        ("nex888-opaque-synthetic-secret-2d4c",),
    )
    assert leaked is True
    assert "nex888-opaque-synthetic-secret-2d4c" not in trace
    assert "nex888-opaque-synthetic-secret-2d4c" not in json.dumps(metrics)
    assert "<redacted>" in trace


def test_checker_never_echoes_a_secret_marker(tmp_path: Path) -> None:
    (tmp_path / "leak.txt").write_text(
        "nex888-opaque-synthetic-secret-2d4c\n", encoding="utf-8"
    )
    result = _run_checker(tmp_path)
    assert result.returncode != 0
    assert "redaction/marker-" in result.stdout
    assert "nex888-opaque-synthetic-secret-2d4c" not in result.stdout


def test_checker_accepts_timeout_then_authoritative_inspect(tmp_path: Path) -> None:
    result = _run_checker(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ALL CHECKS PASSED" in result.stdout


def test_checker_accepts_not_published_timeout_without_resume(tmp_path: Path) -> None:
    trace = _trace(tmp_path, include_resume=False)
    result = _run_checker(tmp_path, trace=trace)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ALL CHECKS PASSED" in result.stdout


@pytest.mark.parametrize(
    "duplicate_field", ["duplicate_builds", "duplicate_build_count", "duplicates"]
)
def test_checker_accepts_zero_duplicate_count_aliases(
    tmp_path: Path, duplicate_field: str
) -> None:
    result = _run_checker(
        tmp_path,
        trace=_trace(tmp_path, duplicate_field=duplicate_field),
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_checker_rejects_nonzero_duplicate_count_alias(tmp_path: Path) -> None:
    result = _run_checker(
        tmp_path,
        trace=_trace(
            tmp_path,
            duplicate_field="duplicate_build_count",
            duplicate_value=1,
        ),
    )
    assert result.returncode != 0
    assert "retry/duplicate-build-count-not-zero" in result.stdout


def test_checker_accepts_float_zero_duplicate_count(tmp_path: Path) -> None:
    result = _run_checker(
        tmp_path,
        trace=_trace(tmp_path, duplicate_value=0.0),
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _trace_with_message_mutation(
    tmp_path: Path, *, record_index: int, message: object
) -> Path:
    source = _trace(tmp_path)
    records = [
        json.loads(line)
        for line in source.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    records[record_index]["message"] = message
    mutated = tmp_path / f"mutated-{record_index}.jsonl"
    mutated.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )
    return mutated


def _trace_with_post_retry_published(tmp_path: Path) -> Path:
    source = _trace(tmp_path, include_resume=False)
    records = [
        json.loads(line)
        for line in source.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    for record in records:
        message = record.get("message", {})
        if record.get("direction") != "response" or message.get("id") != 5:
            continue
        payload = json.loads(message["result"]["content"][0]["text"])
        payload["status"] = "Published"
        message["result"]["content"][0]["text"] = json.dumps(payload)
        break
    mutated = tmp_path / "post-retry-published-trace.jsonl"
    mutated.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )
    return mutated


def _trace_with_invalid_inspect_id(
    tmp_path: Path, *, value: object, filename: str
) -> Path:
    source = _trace(tmp_path)
    records = [
        json.loads(line)
        for line in source.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    records[2]["message"]["id"] = value
    mutated = tmp_path / filename
    mutated.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )
    return mutated


def _trace_with_unhashable_inspect_id(tmp_path: Path) -> Path:
    return _trace_with_invalid_inspect_id(
        tmp_path, value=[], filename="unhashable-inspect-id-trace.jsonl"
    )


def _trace_with_delayed_inspect_response(tmp_path: Path) -> Path:
    source = _trace(tmp_path, include_resume=False)
    records = [
        json.loads(line)
        for line in source.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    delayed = next(
        record
        for record in records
        if record.get("direction") == "response"
        and record.get("message", {}).get("id") == 2
    )
    records.remove(delayed)
    retry_inspect_response_index = next(
        index
        for index, record in enumerate(records)
        if record.get("direction") == "response"
        and record.get("message", {}).get("id") == 5
    )
    records.insert(retry_inspect_response_index + 1, delayed)
    mutated = tmp_path / "delayed-inspect-response-trace.jsonl"
    mutated.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )
    return mutated


def _trace_with_second_pre_retry_published_inspection(
    tmp_path: Path, *, include_workflow: bool
) -> Path:
    source = _trace(tmp_path, include_resume=False)
    records = [
        json.loads(line)
        for line in source.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    payload = {
        "run_id": "run-1",
        "status": "Published",
        "state": "terminal",
    }
    if include_workflow:
        payload["workflow"] = "terminal-timeout-lifecycle"
    records[6:6] = [
        _record(
            "request",
            {
                "jsonrpc": "2.0",
                "id": 11,
                "method": "tools/call",
                "params": {"name": "inspect_run", "arguments": {"run_id": "run-1"}},
            },
        ),
        _record(
            "response",
            {
                "jsonrpc": "2.0",
                "id": 11,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(
                                {
                                    **payload,
                                }
                            ),
                        }
                    ]
                },
            },
            forwarded=True,
        ),
    ]
    mutated = tmp_path / "second-pre-retry-published-inspection-trace.jsonl"
    mutated.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )
    return mutated


def _trace_with_unrelated_pre_retry_inspection(tmp_path: Path) -> Path:
    source = _trace(tmp_path, include_resume=False)
    records = [
        json.loads(line)
        for line in source.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    records[2:2] = [
        _record(
            "request",
            {
                "jsonrpc": "2.0",
                "id": 12,
                "method": "tools/call",
                "params": {
                    "name": "inspect_run",
                    "arguments": {"run_id": "run-unrelated"},
                },
            },
        ),
        _record(
            "response",
            {
                "jsonrpc": "2.0",
                "id": 12,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps({
                                "run_id": "run-unrelated",
                                "status": "Published",
                                "state": "terminal",
                            }),
                        }
                    ]
                },
            },
            forwarded=True,
        ),
    ]
    mutated = tmp_path / "unrelated-pre-retry-inspection-trace.jsonl"
    mutated.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )
    return mutated


def _trace_with_post_retry_publication_response(tmp_path: Path) -> Path:
    source = _trace(tmp_path, include_resume=False)
    records = [
        json.loads(line)
        for line in source.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    delayed = next(
        record
        for record in records
        if record.get("direction") == "response"
        and record.get("message", {}).get("id") == 3
    )
    delayed["message"]["result"]["content"][0]["text"] = json.dumps({
        "products": [{
            "workflow": "terminal-timeout-lifecycle",
            "artifact_status": "available",
            "publish_seq": 1,
        }]
    })
    records.remove(delayed)
    retry_response_index = next(
        index
        for index, record in enumerate(records)
        if record.get("direction") == "response"
        and record.get("message", {}).get("id") == 4
    )
    records.insert(retry_response_index + 1, delayed)
    mutated = tmp_path / "post-retry-publication-response-trace.jsonl"
    mutated.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )
    return mutated


def _trace_with_explicit_primary_inspection(tmp_path: Path) -> Path:
    source = _trace(tmp_path, include_resume=False)
    records = [
        json.loads(line)
        for line in source.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    records[2]["message"]["params"]["arguments"] = {"run_id": "run-1"}
    mutated = tmp_path / "explicit-primary-inspection-trace.jsonl"
    mutated.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )
    return mutated


def _trace_with_mixed_workflow_listing(tmp_path: Path) -> Path:
    source = _trace(tmp_path, include_resume=False)
    records = [
        json.loads(line)
        for line in source.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    listing = next(
        record
        for record in records
        if record.get("direction") == "response"
        and record.get("message", {}).get("id") == 3
    )
    listing["message"]["result"]["content"][0]["text"] = json.dumps({
        "products": [
            {"workflow": "terminal-timeout-lifecycle", "status": "in_progress"},
            {"workflow": "other-workflow", "artifact_status": "available"},
        ]
    })
    mutated = tmp_path / "mixed-workflow-listing-trace.jsonl"
    mutated.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )
    return mutated


def _trace_with_nested_inspect_diagnostics(tmp_path: Path) -> Path:
    source = _trace(tmp_path, include_resume=False)
    records = [
        json.loads(line)
        for line in source.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    response = next(
        record
        for record in records
        if record.get("direction") == "response"
        and record.get("message", {}).get("id") == 2
    )
    payload = json.loads(response["message"]["result"]["content"][0]["text"])
    diagnostic_fields = {
        field: payload.pop(field)
        for field in (
            "configured_budget_ms",
            "elapsed_ms",
            "active_stage",
            "resource",
            "retry_count",
            "page_count",
            "request_count",
        )
    }
    payload["diagnostics"] = diagnostic_fields
    response["message"]["result"]["content"][0]["text"] = json.dumps(payload)
    mutated = tmp_path / "nested-inspect-diagnostics-trace.jsonl"
    mutated.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )
    return mutated


def _trace_with_nested_publication_metadata(tmp_path: Path) -> Path:
    source = _trace(tmp_path, include_resume=False)
    records = [
        json.loads(line)
        for line in source.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    listing = next(
        record
        for record in records
        if record.get("direction") == "response"
        and record.get("message", {}).get("id") == 6
    )
    listing["message"]["result"]["content"][0]["text"] = json.dumps({
        "products": [{
            "workflow": "terminal-timeout-lifecycle",
            "artifact": {"artifact_status": "available", "publish_seq": 1},
        }]
    })
    mutated = tmp_path / "nested-publication-metadata-trace.jsonl"
    mutated.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )
    return mutated


def _trace_with_nested_inspect_branch_metadata(
    tmp_path: Path, *, field: str, value: object, arguments: dict[str, object] | None = None
) -> Path:
    source = _trace(tmp_path, include_resume=False)
    records = [
        json.loads(line)
        for line in source.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    response = next(
        record
        for record in records
        if record.get("direction") == "response"
        and record.get("message", {}).get("id") == 2
    )
    payload = json.loads(response["message"]["result"]["content"][0]["text"])
    payload[field] = value
    response["message"]["result"]["content"][0]["text"] = json.dumps(payload)
    if arguments is not None:
        request = next(
            record
            for record in records
            if record.get("direction") == "request"
            and record.get("message", {}).get("id") == 2
        )
        request["message"]["params"]["arguments"] = arguments
    mutated = tmp_path / f"nested-inspect-{field}-trace.jsonl"
    mutated.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )
    return mutated


def _trace_with_nested_listing_history(
    tmp_path: Path, *, status_field: str, status_value: str, history: dict[str, object]
) -> Path:
    source = _trace(tmp_path, include_resume=False)
    records = [
        json.loads(line)
        for line in source.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    response = next(
        record
        for record in records
        if record.get("direction") == "response"
        and record.get("message", {}).get("id") == 3
    )
    response["message"]["result"]["content"][0]["text"] = json.dumps({
        "products": [{
            "workflow": "terminal-timeout-lifecycle",
            status_field: status_value,
            **history,
        }]
    })
    mutated = tmp_path / f"nested-listing-{status_field}-history-trace.jsonl"
    mutated.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )
    return mutated


def _trace_with_ambiguous_explicit_inspections(tmp_path: Path) -> Path:
    source = _trace_with_unrelated_pre_retry_inspection(tmp_path)
    records = [
        json.loads(line)
        for line in source.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    primary_request = next(
        record
        for record in records
        if record.get("direction") == "request"
        and record.get("message", {}).get("id") == 2
    )
    primary_request["message"]["params"]["arguments"] = {"run_id": "run-1"}
    mutated = tmp_path / "ambiguous-explicit-inspections-trace.jsonl"
    mutated.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )
    return mutated


def _trace_with_name_identified_failed_publication(tmp_path: Path) -> Path:
    source = _trace(tmp_path, include_resume=False)
    records = [
        json.loads(line)
        for line in source.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    response = next(
        record
        for record in records
        if record.get("direction") == "response"
        and record.get("message", {}).get("id") == 10
    )
    response["message"]["result"]["content"][0]["text"] = json.dumps({
        "products": [{
            "name": "terminal-timeout-lifecycle-failed",
            "artifact_status": "available",
            "publish_seq": 1,
        }]
    })
    mutated = tmp_path / "name-identified-failed-publication-trace.jsonl"
    mutated.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )
    return mutated


def test_checker_grades_non_object_json_rpc_message_without_crashing(
    tmp_path: Path,
) -> None:
    result = _run_checker(
        tmp_path,
        trace=_trace_with_message_mutation(
            tmp_path, record_index=1, message=[{"jsonrpc": "2.0"}]
        ),
    )
    assert result.returncode != 0
    assert "Traceback" not in result.stderr
    assert "trace/non-object-json-rpc-message" in result.stdout


def test_checker_grades_positional_json_rpc_params_without_crashing(
    tmp_path: Path,
) -> None:
    result = _run_checker(
        tmp_path,
        trace=_trace_with_message_mutation(
            tmp_path,
            record_index=2,
            message={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": ["inspect_run", {}],
            },
        ),
    )
    assert result.returncode != 0
    assert "Traceback" not in result.stderr
    assert "trace/positional-json-rpc-params" in result.stdout


def test_checker_accepts_null_json_rpc_params_without_crashing(tmp_path: Path) -> None:
    result = _run_checker(
        tmp_path,
        trace=_trace_with_message_mutation(
            tmp_path,
            record_index=2,
            message={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": None,
            },
        ),
    )
    assert result.returncode != 0
    assert "trace/positional-json-rpc-params" not in result.stdout
    assert "Traceback" not in result.stderr


def test_checker_binds_branch_to_pre_retry_inspection(tmp_path: Path) -> None:
    result = _run_checker(tmp_path, trace=_trace_with_post_retry_published(tmp_path))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ALL CHECKS PASSED" in result.stdout


def test_checker_rejects_unhashable_json_rpc_id_without_crashing(
    tmp_path: Path,
) -> None:
    result = _run_checker(
        tmp_path, trace=_trace_with_unhashable_inspect_id(tmp_path)
    )
    assert result.returncode != 0
    assert "Traceback" not in result.stderr
    assert "trace/invalid-json-rpc-id" in result.stdout


@pytest.mark.parametrize("invalid_id", [float("nan"), float("inf")])
def test_checker_rejects_nonfinite_json_rpc_id(
    tmp_path: Path, invalid_id: float
) -> None:
    result = _run_checker(
        tmp_path,
        trace=_trace_with_invalid_inspect_id(
            tmp_path,
            value=invalid_id,
            filename="nonfinite-inspect-id-trace.jsonl",
        ),
    )
    assert result.returncode != 0
    assert "Traceback" not in result.stderr
    assert "trace/invalid-json-rpc-id" in result.stdout


def test_checker_rejects_inspect_response_arriving_after_retry(
    tmp_path: Path,
) -> None:
    result = _run_checker(
        tmp_path, trace=_trace_with_delayed_inspect_response(tmp_path)
    )
    assert result.returncode != 0
    assert "lifecycle/authoritative-inspect-response-missing" in result.stdout


@pytest.mark.parametrize("include_workflow", [False, True])
def test_checker_uses_all_pre_retry_inspections_for_branch_selection(
    tmp_path: Path, include_workflow: bool
) -> None:
    result = _run_checker(
        tmp_path,
        trace=_trace_with_second_pre_retry_published_inspection(
            tmp_path, include_workflow=include_workflow
        ),
    )
    assert result.returncode != 0
    assert "resume/resume-request-missing" in result.stdout


def test_checker_does_not_bind_an_unrelated_inspection_as_primary(
    tmp_path: Path,
) -> None:
    result = _run_checker(
        tmp_path,
        trace=_trace_with_unrelated_pre_retry_inspection(tmp_path),
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_checker_accepts_an_explicit_primary_inspection(tmp_path: Path) -> None:
    result = _run_checker(
        tmp_path,
        trace=_trace_with_explicit_primary_inspection(tmp_path),
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_checker_ignores_listing_response_arriving_after_retry(
    tmp_path: Path,
) -> None:
    result = _run_checker(
        tmp_path,
        trace=_trace_with_post_retry_publication_response(tmp_path),
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_checker_keeps_listing_publication_bound_to_the_primary_workflow(
    tmp_path: Path,
) -> None:
    result = _run_checker(
        tmp_path,
        trace=_trace_with_mixed_workflow_listing(tmp_path),
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_checker_accepts_nested_publication_metadata(tmp_path: Path) -> None:
    result = _run_checker(
        tmp_path,
        trace=_trace_with_nested_publication_metadata(tmp_path),
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_checker_accepts_nested_inspect_diagnostics(tmp_path: Path) -> None:
    result = _run_checker(
        tmp_path,
        trace=_trace_with_nested_inspect_diagnostics(tmp_path),
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    ("field", "value", "arguments"),
    [
        ("semantic_model", {"status": "published"}, {}),
        ("semantic_model", {"status": "published"}, {"run_id": "run-1"}),
        (
            "semantic_model",
            {"status": "published"},
            {"workflow": "terminal-timeout-lifecycle"},
        ),
        ("workflow_counters", {"duplicate_builds": 2}, {}),
        ("workflow_counters", {"duplicate_builds": 2}, {"run_id": "run-1"}),
    ],
)
def test_checker_ignores_nested_inspect_branch_metadata(
    tmp_path: Path,
    field: str,
    value: object,
    arguments: dict[str, object],
) -> None:
    result = _run_checker(
        tmp_path,
        trace=_trace_with_nested_inspect_branch_metadata(
            tmp_path, field=field, value=value, arguments=arguments
        ),
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    ("status_field", "status_value", "history"),
    [
        ("status", "in_progress", {"previous_version": {"status": "published"}}),
        (
            "artifact_status",
            "building",
            {"last_published": {"artifact_status": "available"}},
        ),
        (
            "status",
            "in_progress",
            {
                "previous_version": {
                    "name": "terminal-timeout-lifecycle",
                    "status": "published",
                }
            },
        ),
    ],
)
def test_checker_ignores_nested_listing_publication_history(
    tmp_path: Path,
    status_field: str,
    status_value: str,
    history: dict[str, object],
) -> None:
    result = _run_checker(
        tmp_path,
        trace=_trace_with_nested_listing_history(
            tmp_path,
            status_field=status_field,
            status_value=status_value,
            history=history,
        ),
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_checker_does_not_guess_between_ambiguous_explicit_inspections(
    tmp_path: Path,
) -> None:
    result = _run_checker(
        tmp_path,
        trace=_trace_with_ambiguous_explicit_inspections(tmp_path),
    )
    assert result.returncode != 0
    assert "lifecycle/authoritative-inspect-response-missing" in result.stdout


def test_checker_catches_failed_publication_with_name_identity(tmp_path: Path) -> None:
    result = _run_checker(
        tmp_path,
        trace=_trace_with_name_identified_failed_publication(tmp_path),
    )
    assert result.returncode != 0
    assert "failure/failed-workflow-was-published" in result.stdout


def test_checker_accepts_published_timeout_and_resume_without_rebuild(tmp_path: Path) -> None:
    result = _run_checker(tmp_path, trace=_published_after_timeout_trace(tmp_path))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ALL CHECKS PASSED" in result.stdout


def test_checker_marker_list_matches_the_scenario_configuration() -> None:
    checks = json.loads((SCENARIO / "checks.json").read_text(encoding="utf-8"))
    configured = checks["deterministic_check"]["redaction_markers"]
    checker = CHECKER.read_text(encoding="utf-8")
    # The checker's hardcoded set is only a standalone fallback; if it drifts
    # from checks.json a local invocation scans for the wrong literal.
    for marker in configured:
        assert marker in checker
    stub = (SCENARIO / "fixtures/stub_slow_paginated_api.py").read_text(encoding="utf-8")
    # Every configured marker must be a literal the fixture can actually put
    # in front of the agent, or the scan reports a clean result from a check
    # that could never fail.
    for marker in configured:
        assert marker in stub


def test_checker_fails_closed_on_an_empty_marker_file(tmp_path: Path) -> None:
    marker_file = tmp_path / "markers.txt"
    marker_file.write_text("\n", encoding="utf-8")
    trace = _trace(tmp_path)
    result = subprocess.run(
        [sys.executable, str(CHECKER), "--fixtures", str(SCENARIO / "fixtures"),
         "--root", str(tmp_path), "--trace", str(trace),
         "--secret-marker-file", str(marker_file)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "redaction/marker-file-unusable" in result.stdout


def test_checker_requires_sensitive_profile_mode_0600(tmp_path: Path) -> None:
    profile = tmp_path / "infra-profile.yaml"
    profile.write_text("token: <redacted>\n", encoding="utf-8")
    profile.chmod(0o644)
    result = _run_checker(tmp_path)
    assert result.returncode != 0
    assert "redaction/infra-profile-not-mode-0600" in result.stdout


def test_checker_grades_malformed_observations_without_crashing(tmp_path: Path) -> None:
    result = _run_checker(
        tmp_path,
        observation_records=[
            {
                "path": "/v1/events?page=1",
                "status": 200,
                "authorized": True,
                "page": "not-a-number",
                "rows": 10,
            },
            ["not an observation object"],
        ],
    )
    assert result.returncode != 0
    assert "Traceback" not in result.stderr
    assert "observations/invalid-page" in result.stdout
    assert "observations/non-object-record" in result.stdout


def test_checker_grades_malformed_observation_json_without_crashing(tmp_path: Path) -> None:
    result = _run_checker(
        tmp_path,
        observation_text='{"status": 200}\nnot-json\n',
    )
    assert result.returncode != 0
    assert "Traceback" not in result.stderr
    assert "observations/malformed-json" in result.stdout


def test_checker_rejects_missing_late_response_evidence(tmp_path: Path) -> None:
    result = _run_checker(tmp_path, include_late=False)
    assert result.returncode != 0
    assert "timeout/late-server-response-not-traced-and-suppressed" in result.stdout
