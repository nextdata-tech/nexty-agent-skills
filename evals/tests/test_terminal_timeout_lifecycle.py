"""Contract tests for the terminal timeout/lifecycle scenario."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCENARIO = ROOT / "evals/public/terminal-timeout-lifecycle"
CHECKER = SCENARIO / "fixtures/check_terminal_timeout_lifecycle.py"
PROFILE_BUILDER = SCENARIO / "fixtures/prepare_stdio_profile.py"
if str(ROOT / "evals") not in sys.path:
    sys.path.insert(0, str(ROOT / "evals"))
import run as eval_run  # noqa: E402


def _record(direction: str, message: dict, **metadata: object) -> dict:
    return {
        "source": "runner",
        "protocol": "mcp",
        "direction": direction,
        "message": message,
        **metadata,
    }


def _trace(tmp_path: Path, *, include_late: bool = True) -> Path:
    build_request = _record(
        "request",
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "build_data_product", "arguments": {}}},
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
            "duplicate_builds": 0,
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
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "build_data_product", "arguments": {"budget_ms": 6000}}},
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
            "run_id": "run-2", "duplicate_builds": 0, "state": "terminal",
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
        resume_request,
        resume_response,
        failed_build_request,
        failed_build_response,
        failed_inspect_request,
        failed_inspect_response,
        failed_listing_request,
        failed_listing_response,
    ]
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
) -> subprocess.CompletedProcess[str]:
    trace = trace or _trace(tmp_path, include_late=include_late)
    observations = tmp_path / "observations.jsonl"
    observations.write_text(
        "\n".join(
            json.dumps({
                "path": f"/v1/events?page={page}&per_page=10",
                "status": 200,
                "authorized": True,
                "page": page,
                "rows": rows,
                "total": 23,
            })
            for page, rows in ((1, 10), (2, 10), (3, 3))
        ) + "\n",
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


def test_checker_rejects_missing_late_response_evidence(tmp_path: Path) -> None:
    result = _run_checker(tmp_path, include_late=False)
    assert result.returncode != 0
    assert "timeout/late-server-response-not-traced-and-suppressed" in result.stdout
