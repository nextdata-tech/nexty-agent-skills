"""Contract tests for the terminal authenticated DLT API scenario."""

from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCENARIO = ROOT / "evals/public/terminal-authenticated-dlt-api-ingestion"
CHECKER = SCENARIO / "fixtures/check_dlt_api.py"
BUILDER = SCENARIO / "fixtures/prepare_stdio_profile.py"
SECRET = "nex890-opaque-synthetic-secret-9a3c"
DEFINITION_ID = "sha256:" + "a" * 64


def _write_valid_closure(root: Path) -> None:
    (root / "transform").mkdir(parents=True)
    (root / "transform/main.py").write_text(
        "import dlt\n"
        "from pathlib import Path\n"
        "from dlt.sources.rest_api import rest_api_resources\n"
        "\n"
        "PHYSICAL_MODELS = ('orders',)\n"
        "\n"
        "def source(secrets):\n"
        "    root = Path(__import__('os').environ['NXD_TRANSFORM_ROOT'])\n"
        "    endpoints = (root / 'api-source-endpoints').read_text()\n"
        "    endpoint = endpoints.strip().split('=', 1)[1]\n"
        "    headers = {'User-Agent': secrets['header_user_agent']}\n"
        "    paginator = {'type': 'page_number', 'base_page': 1, 'page_param': 'page', 'total_path': 'pages'}\n"
        "    endpoint_options = {'data_selector': 'data', 'params': {'per_page': 10}, 'paginator': paginator}\n"
        "    paid_options = {'data_selector': 'data', 'params': {'status': 'paid', 'per_page': 10}, 'paginator': paginator}\n"
        "    return rest_api_resources({'client': {'base_url': secrets['base_url'], 'auth': {'type': 'bearer', 'token': secrets['auth_token']}, 'headers': headers}, 'resources': [{'name': 'orders', 'endpoint': {'path': endpoint, **endpoint_options}}, {'name': 'paid_orders', 'endpoint': {'path': endpoint, **paid_options}}]})\n"
        "\n"
        "def ingest(duckdb, secrets):\n"
        "    pipeline = dlt.pipeline(destination=dlt.destinations.duckdb(credentials=duckdb.path), dataset_name=duckdb.schema)\n"
        "    pipeline.run(source(secrets), write_disposition='replace')\n",
        encoding="utf-8",
    )
    profile = root / "infra-profile.yaml"
    profile.write_text(
        "services:\n"
        "  - name: api-source\n"
        "    attributes:\n"
        "      - key: base_url\n"
        "        value: http://127.0.0.1:1\n"
        "        public: true\n"
        "      - key: auth_type\n"
        "        value: bearer\n"
        "        public: true\n"
        "      - key: auth_token\n"
        f"        value: {SECRET}\n"
        "        public: false\n"
        "      - key: header_user_agent\n"
        "        value: nexty-dlt-client/1.0\n"
        "        public: true\n",
        encoding="utf-8",
    )
    profile.chmod(0o600)
    (root / "companion-files").write_text("api-source-endpoints\n", encoding="utf-8")
    (root / "api-source-endpoints").write_text("orders=/v1/orders\n", encoding="utf-8")
    cases = {
        "unauthorized-401": ("validation", "scratch_transform_failed"),
        "forbidden-403": ("validation", "scratch_transform_failed"),
        "unknown-endpoint-404": ("validation", "scratch_transform_failed"),
        "malformed-companion": ("validation", "scratch_transform_failed"),
        "omitted-companion": ("closure", "structure/companion_files_invalid"),
        "hard-coded-endpoint": ("review", "endpoint_not_companion_derived"),
    }
    for case, (phase, code) in cases.items():
        case_dir = root / ".eval-cases" / case
        case_dir.mkdir(parents=True)
        (case_dir / "failure.json").write_text(
            json.dumps({"status": "failed", "phase": phase, "code": code}),
            encoding="utf-8",
        )
    hardcoded_transform = root / ".eval-cases" / "hard-coded-endpoint" / "transform"
    hardcoded_transform.mkdir()
    (hardcoded_transform / "main.py").write_text(
        "from dlt.sources.rest_api import rest_api_resources\n"
        "def source():\n"
        "    return rest_api_resources({'resources': [{'name': 'orders', 'endpoint': {'path': '/v1/orders'}}]})\n",
        encoding="utf-8",
    )
    (root / "exports").mkdir()
    with zipfile.ZipFile(root / "exports" / "nex890.zip", "w") as bundle:
        bundle.writestr("IMPORT.md", "refill auth_token")
        bundle.writestr("export.json", json.dumps({"redacted": ["auth_token"]}))
        bundle.writestr("infra-profile.yaml", "auth_token: <REDACTED>\n")
        bundle.writestr("companion-files", "api-source-endpoints\n")
        bundle.writestr("api-source-endpoints", "orders=/v1/orders\n")


def _record(direction: str, message: dict, **metadata: object) -> dict:
    return {
        "source": "runner",
        "protocol": "mcp",
        "direction": direction,
        "message": message,
        **metadata,
    }


def _trace(tmp_path: Path, *, omit_case: str | None = None) -> Path:
    records: list[dict] = []
    archive_path = tmp_path / "closure" / "exports" / "nex890.zip"

    def call(number: int, name: str, arguments: dict, payload: dict, *, error: bool = False) -> None:
        records.append(_record(
            "request",
            {"jsonrpc": "2.0", "id": number, "method": "tools/call", "params": {"name": name, "arguments": arguments}},
        ))
        content = {"type": "text", "text": json.dumps(payload)}
        result = {"isError": True, "content": [content]} if error else {"content": [content]}
        records.append(_record("response", {"jsonrpc": "2.0", "id": number, "result": result}))

    call(1, "get_workflow_capabilities", {}, {"execution_enabled": True, "schema": "v2"})
    call(2, "check_data_product", {"definition": "/workspace/closure", "workflow": "terminal-authenticated-dlt-api-ingestion"}, {"outcome": "pass", "provenance": {"definition_id": DEFINITION_ID}})
    call(3, "prepare_workflow", {"workflow": "terminal-authenticated-dlt-api-ingestion"}, {"workflow": "terminal-authenticated-dlt-api-ingestion", "next_actions": [{"type": "session_decision"}]})
    call(4, "advance_workflow", {"workflow": "terminal-authenticated-dlt-api-ingestion", "action": {"type": "session_decision"}}, {"workflow": "terminal-authenticated-dlt-api-ingestion", "next_actions": [{"type": "capture"}]})
    call(5, "advance_workflow", {"workflow": "terminal-authenticated-dlt-api-ingestion", "action": {"type": "capture"}}, {"workflow": "terminal-authenticated-dlt-api-ingestion", "next_actions": [{"type": "start_requirement"}]})
    call(6, "advance_workflow", {"workflow": "terminal-authenticated-dlt-api-ingestion", "action": {"type": "start_run"}}, {"workflow": "terminal-authenticated-dlt-api-ingestion", "run_id": "run-1", "definition_id": DEFINITION_ID, "status": "published"})
    call(7, "inspect_workflow", {"workflow": "terminal-authenticated-dlt-api-ingestion"}, {"workflow": "terminal-authenticated-dlt-api-ingestion", "run_id": "run-1", "definition_id": DEFINITION_ID, "status": "published"})
    call(8, "inspect_run", {"run_id": "run-1"}, {"run": {"workflow": "terminal-authenticated-dlt-api-ingestion", "run_id": "run-1", "definition_id": DEFINITION_ID, "outcome": "success"}})
    call(9, "list_data_products", {}, {"products": [{"workflow": "terminal-authenticated-dlt-api-ingestion", "artifact_status": "available", "publish_seq": 1, "run_id": "run-1", "definition_id": DEFINITION_ID, "models": [{"row_count": 23}]}]})
    call(10, "resume_data_product", {"workflow": "terminal-authenticated-dlt-api-ingestion"}, {"workflow": "terminal-authenticated-dlt-api-ingestion", "run_id": "run-1", "definition_id": DEFINITION_ID, "semantic_endpoint": "http://127.0.0.1:1/mcp", "bearer_token": "<redacted>"})
    call(11, "describe_models", {"endpoint": "http://127.0.0.1:1/mcp", "token": "<redacted>"}, {"models": [{"name": "orders"}]})
    call(12, "run_semantic_query", {"endpoint": "http://127.0.0.1:1/mcp", "token": "<redacted>", "measures": ["order_count"], "dimensions": [], "filters": [{"dimension": "status", "op": "=", "value": "paid"}], "limit": 200}, {"row_count": 1, "columns": ["count"], "rows": [[16]], "filtered": True})
    call(13, "export_data_product", {"definition": str(tmp_path / "closure"), "destination": str(archive_path), "import_notes": "synthetic"}, {"archive_path": str(archive_path), "redacted": ["auth_token"]})

    number = 20
    cases = {
        "unauthorized-401": ("validation", "scratch_transform_failed"),
        "forbidden-403": ("validation", "scratch_transform_failed"),
        "unknown-endpoint-404": ("validation", "scratch_transform_failed"),
        "malformed-companion": ("validation", "scratch_transform_failed"),
        "omitted-companion": ("closure", "structure/companion_files_invalid"),
        "hard-coded-endpoint": ("review", "endpoint_not_companion_derived"),
    }
    for case, (phase, code) in cases.items():
        if case == omit_case:
            continue
        signature = {
            "unauthorized-401": "scratch_transform_failed",
            "forbidden-403": "scratch_transform_failed",
            "unknown-endpoint-404": "scratch_transform_failed",
            "malformed-companion": "scratch_transform_failed",
            "omitted-companion": "companion missing",
            "hard-coded-endpoint": "review endpoint transform hard-coded",
        }[case]
        call(number, "check_data_product", {"definition": f"/workspace/.eval-cases/{case}", "workflow": case}, {"status": "failed", "phase": phase, "code": code, "detail": signature}, error=True)
        number += 1

    path = tmp_path / "trace.jsonl"
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")
    return path


def _observations(tmp_path: Path, *, bypass: bool = False) -> Path:
    records = [
        {"path": "/v1/orders", "status": 401, "authorized": False, "user_agent": ""},
        {"path": "/v1/orders", "status": 403, "authorized": True, "user_agent": "wrong"},
        {"path": "/v1/unknown", "status": 404, "authorized": True, "user_agent": "nexty-dlt-client/1.0"},
    ]
    full_rows = {1: 23 if bypass else 10, 2: 0 if bypass else 10, 3: 0 if bypass else 3}
    records.extend({
        "path": f"/v1/orders?page={page}&per_page=10",
        "status": 200,
        "authorized": True,
        "user_agent": "nexty-dlt-client/1.0",
        "status_filter": None,
        "page": page,
        "per_page": 10,
        "pages": 3,
        "rows": rows,
        "total": 23,
    } for page, rows in full_rows.items())
    records.extend({
        "path": f"/v1/orders?status=paid&page={page}&per_page=10",
        "status": 200,
        "authorized": True,
        "user_agent": "nexty-dlt-client/1.0",
        "status_filter": "paid",
        "page": page,
        "per_page": 10,
        "pages": 2,
        "rows": rows,
        "total": 16,
    } for page, rows in ((1, 10), (2, 6)))
    path = tmp_path / "observations.jsonl"
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")
    return path


def _run_checker(
    tmp_path: Path,
    *,
    trace: Path | None = None,
    observations: Path | None = None,
    root: Path | None = None,
    terminal_route: bool = True,
) -> subprocess.CompletedProcess[str]:
    root = root or (tmp_path / "closure")
    if not root.exists():
        root.mkdir()
        _write_valid_closure(root)
    trace = trace or _trace(tmp_path)
    observations = observations or _observations(tmp_path)
    marker = tmp_path / "marker.txt"
    marker.write_text(SECRET + "\n", encoding="utf-8")
    checker_env = {**os.environ, "NXD_STUB_OBSERVATIONS": str(observations)}
    if terminal_route:
        checker_env["NXD_EVAL_TERMINAL_WORKFLOW_ROUTE"] = "terminal_workflow_review_v1"
    else:
        checker_env.pop("NXD_EVAL_TERMINAL_WORKFLOW_ROUTE", None)
    return subprocess.run(
        [sys.executable, str(CHECKER), "--fixtures", str(SCENARIO / "fixtures"), "--root", str(root), "--trace", str(trace), "--secret-marker-file", str(marker)],
        capture_output=True,
        text=True,
        check=False,
        env=checker_env,
    )


def test_scenario_wires_current_runner_contract() -> None:
    checks = json.loads((SCENARIO / "checks.json").read_text(encoding="utf-8"))
    stdio = json.loads((SCENARIO / "fixtures/desktop_stdio.json").read_text(encoding="utf-8"))
    http = json.loads((SCENARIO / "fixtures/http_stub.json").read_text(encoding="utf-8"))
    assert checks["deterministic_check"]["trace_source"] == "runner_mcp"
    assert stdio["profile_builder"] == "prepare_stdio_profile.py"
    assert stdio["supported_agent_backends"] == ["claude"]
    assert stdio["nex_mode"] is True
    assert "codex_app_server_route" not in stdio
    assert "agent_env" not in http
    assert http["trusted_server_env"] == {"NXD_EVAL_SOURCE_TOKEN": "VALID_TOKEN"}
    assert (SCENARIO / "fixtures/prepare_stdio_profile.py").is_file()


def test_profile_builder_is_scenario_local_and_does_not_stage_mapper_files(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    output = tmp_path / "stdio-profile.json"
    result = subprocess.run([sys.executable, str(BUILDER), "--workspace", str(workspace), "--output", str(output)], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert list(workspace.iterdir()) == []
    assert json.loads(output.read_text(encoding="utf-8"))["schema"] == "nxd-synthetic-evaluation-profile-v1"
    assert stat.S_IMODE(output.stat().st_mode) == 0o444


def test_stub_exposes_auth_fixed_pages_and_filter(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location("nex890_stub", SCENARIO / "fixtures/stub_dlt_api.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    server, port, thread = module.start_server()
    try:
        base = f"http://127.0.0.1:{port}"

        def get(path: str, headers: dict[str, str]) -> tuple[int, dict]:
            request = urllib.request.Request(base + path, headers=headers)
            try:
                with urllib.request.urlopen(request) as response:
                    return response.status, json.loads(response.read())
            except urllib.error.HTTPError as error:
                return error.code, json.loads(error.read())

        assert get("/v1/orders", {})[0] == 401
        assert get("/v1/orders", {"Authorization": f"Bearer {module.VALID_TOKEN}"})[0] == 403
        valid = {"Authorization": f"Bearer {module.VALID_TOKEN}", "User-Agent": module.REQUIRED_USER_AGENT}
        assert get("/v1/unknown", valid)[0] == 404
        pages = [get(f"/v1/orders?page={page}&per_page=10", valid)[1] for page in (1, 2, 3)]
        assert [len(page["data"]) for page in pages] == [10, 10, 3]
        paid = [get(f"/v1/orders?status=paid&page={page}&per_page=10", valid)[1] for page in (1, 2)]
        assert [len(page["data"]) for page in paid] == [10, 6]
        assert get("/v1/orders?page=1&per_page=23", valid)[0] == 400
    finally:
        module.stop_server(server, thread)


def test_checker_accepts_complete_contract(tmp_path: Path) -> None:
    result = _run_checker(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ALL CHECKS PASSED" in result.stdout


def test_checker_parses_supervisor_text_payload_and_nested_review_requirement() -> None:
    spec = importlib.util.spec_from_file_location("nex890_checker_payload", CHECKER)
    assert spec is not None and spec.loader is not None
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    payload = {
        "requirements": [
            {"id": "consent", "generation": 1, "review_input": None},
            {
                "id": "review",
                "generation": 7,
                "review_input": {"retained_capture_root": "/state/capture"},
            },
        ]
    }
    response = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {"content": [{"type": "text", "text": json.dumps(payload)}]},
    }

    parsed = checker._nex_structured_content(response)
    review = checker._nex_requirement(parsed, "review")
    assert review["generation"] == 7
    assert review["review_input"] == {"retained_capture_root": "/state/capture"}
    assert checker._nex_requirement(parsed, "missing") == {}
    assert checker._nex_structured_content({
        "result": {"content": [
            {"type": "text", "text": json.dumps(payload)},
            {"type": "text", "text": "{}"},
        ]}
    }) == {}
    assert checker._nex_structured_content({
        "result": {
            "structuredContent": payload,
            "content": [{"type": "text", "text": json.dumps(payload)}],
        }
    }) == {}


def test_checker_reads_only_known_nested_operation_diagnostic_and_selfcheck_failure() -> None:
    spec = importlib.util.spec_from_file_location("nex890_checker_diagnostics", CHECKER)
    assert spec is not None and spec.loader is not None
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    diagnostic = {
        "phase": "scratch_transform",
        "code": "validation/scratch_transform_failed",
        "http_status": 401,
    }
    response = {
        "result": {"content": [{"type": "text", "text": json.dumps({
            "operation": {"diagnostic": diagnostic},
            "operations": [{"diagnostic": {"code": "ignored", "phase": "ignored"}}],
        })}]}
    }
    assert checker._nex_direct_diagnostics(response) == [diagnostic]
    assert checker._nex_direct_diagnostics({
        "result": {"content": [{"type": "text", "text": "diagnostic code=foo phase=bar"}]}
    }) == []
    assert checker._nex_direct_diagnostics({
        "result": {"content": [{"type": "text", "text": json.dumps({
            "code": "validation/scratch_transform_failed",
            "phase": "scratch_transform",
            "diagnostic": diagnostic,
        })}]}
    }) == []
    assert checker._nex_selfcheck_failed({
        "outcome": "fail",
        "stages": [{"checks": [{"status": "fail", "code": "structure/invalid"}]}],
    })
    assert not checker._nex_selfcheck_failed({
        "outcome": "fail",
        "stages": [{"checks": [{"status": "pass", "detail": "validation failed"}]}],
    })


def test_checker_maps_workflow_v2_session_decision_to_consent_stage() -> None:
    spec = importlib.util.spec_from_file_location("nex890_checker", CHECKER)
    assert spec is not None and spec.loader is not None
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    consent = {
        "workflow": "nex890-positive",
        "operation": "advance_workflow",
        "arguments": {
            "action": {
                "type": "session_decision",
                "parameters": {"requirement_id": "consent"},
            }
        },
    }

    assert checker._nex_case_action_calls([consent], "nex890-positive", "consent") == [consent]


@pytest.mark.parametrize("flat", [False, True])
def test_checker_maps_workflow_v2_validation_requirement(flat: bool) -> None:
    spec = importlib.util.spec_from_file_location("nex890_checker", CHECKER)
    assert spec is not None and spec.loader is not None
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    action = {"type": "start_requirement"}
    if flat:
        action["requirement_id"] = "validation"
    else:
        action["parameters"] = {"requirement_id": "validation"}
    validation = {
        "workflow": "nex890-positive",
        "operation": "advance_workflow",
        "arguments": {"action": action},
    }

    assert checker._nex_case_action_calls([validation], "nex890-positive", "validate") == [validation]


def test_checker_distinguishes_missing_and_duplicate_validation() -> None:
    spec = importlib.util.spec_from_file_location("nex890_checker", CHECKER)
    assert spec is not None and spec.loader is not None
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)

    assert checker._nex_validation_cardinality_failure("nex890-positive", []) == (
        "cycle/nex890-positive/validation-missing"
    )
    assert checker._nex_validation_cardinality_failure("nex890-positive", [{}]) is None
    assert checker._nex_validation_cardinality_failure("nex890-positive", [{}, {}]) == (
        "cycle/nex890-positive/validation-duplicate"
    )


def test_checker_reports_review_verdict_and_returned_validation_action() -> None:
    spec = importlib.util.spec_from_file_location("nex890_checker", CHECKER)
    assert spec is not None and spec.loader is not None
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    report_call = {
        "arguments": {
            "action": {
                "type": "report_requirement",
                "parameters": {
                    "requirement_id": "review",
                    "report": {"verdict": "clear", "findings": [], "rejection_code": None},
                },
            }
        }
    }
    # The supervisor's WorkflowResponse shape: flat next actions keyed by
    # "action", serialised as one text block.
    report_response = {
        "result": {"content": [{"type": "text", "text": json.dumps({
            "next_actions": [{
                "action": "start_requirement",
                "requirement_id": "validation",
                "code": "workflow/requirement_pending",
                "generation": 1,
            }]
        })}]}
    }

    assert checker._nex_report_verdict(report_call) == "clear"
    finding_call = {
        "arguments": {
            "action": {
                "type": "report_requirement",
                "parameters": {
                    "report": {
                        "verdict": "findings",
                        "findings": [{
                            "id": "wrong-endpoint",
                            "severity": "blocking",
                            "description": "description must not enter the diagnostic",
                        }],
                    }
                },
            }
        }
    }
    assert checker._nex_report_finding_labels(finding_call) == [
        "wrong-endpoint-blocking"
    ]
    long_id_call = {
        "arguments": {
            "action": {
                "type": "report_requirement",
                "parameters": {
                    "report": {
                        "verdict": "findings",
                        "findings": [
                            {"id": "Not A Slug", "severity": "advisory", "description": "x"},
                            {"id": "paid_filter_unverified", "severity": "blocking", "description": "x"},
                        ],
                    }
                },
            }
        }
    }
    assert checker._nex_report_finding_labels(long_id_call) == [
        "finding-id-unavailable-advisory",
        "paid-filter-unverified-blocking",
    ]
    rejected_call = {
        "arguments": {
            "action": {
                "type": "report_requirement",
                "parameters": {
                    "report": {
                        "verdict": "rejected",
                        "findings": [],
                        "rejection_code": "scope_refused",
                    }
                },
            }
        }
    }
    assert checker._nex_report_rejection_code(rejected_call) == "scope_refused"
    assert checker._nex_validation_action_returned(report_response)
    assert not checker._nex_validation_action_returned({
        "result": {"content": [{"type": "text", "text": json.dumps({"next_actions": []})}]}
    })


def test_checker_flags_rpc_errors_only_on_evidence_calls() -> None:
    spec = importlib.util.spec_from_file_location("nex890_checker", CHECKER)
    assert spec is not None and spec.loader is not None
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    error = {"jsonrpc": "2.0", "id": 1, "error": {"code": -32602, "message": "stale revision"}}
    ok = {"jsonrpc": "2.0", "id": 1, "result": {"content": []}}
    validation = {"workflow": "nex890-401", "response_message": error}
    refused = {"workflow": "nex890-401", "response_message": error}
    static = {"workflow": "__static__", "response_message": error}
    validated = {"nex890-401": validation}

    assert checker._nex_evidence_call_rpc_error(validation, validated)
    assert checker._nex_evidence_call_rpc_error(static, validated)
    assert not checker._nex_evidence_call_rpc_error(refused, validated)
    assert not checker._nex_evidence_call_rpc_error(
        {"workflow": "nex890-401", "response_message": ok}, {"nex890-401": validation}
    )
    assert not checker._nex_evidence_call_rpc_error(
        {"workflow": "__static__", "response_message": ok}, validated
    )


def test_checker_counts_only_accepted_actions_after_the_last_reset() -> None:
    spec = importlib.util.spec_from_file_location("nex890_checker", CHECKER)
    assert spec is not None and spec.loader is not None
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    ok = {"jsonrpc": "2.0", "id": 1, "result": {"content": []}}
    refused = {"jsonrpc": "2.0", "id": 1, "error": {"code": -32602, "message": "stale revision"}}

    def consent(response: dict) -> dict:
        return {
            "workflow": "nex890-positive",
            "operation": "advance_workflow",
            "arguments": {"action": {"type": "session_decision"}},
            "response_message": response,
        }

    def reset(response: dict) -> dict:
        return {
            "workflow": "nex890-positive",
            "operation": "reset_workflow",
            "arguments": {"workflow": "nex890-positive"},
            "response_message": response,
        }

    before, after = consent(ok), consent(ok)
    assert checker._nex_case_action_calls(
        [before, reset(ok), after], "nex890-positive", "consent"
    ) == [after]
    assert checker._nex_case_action_calls(
        [before, reset(refused), after], "nex890-positive", "consent"
    ) == [before, after]
    retried = consent(ok)
    assert checker._nex_case_action_calls(
        [consent(refused), retried], "nex890-positive", "consent"
    ) == [retried]


def test_checker_transform_walk_tolerates_expression_bodies(tmp_path: Path) -> None:
    # A DLT response hook is usually a lambda or uses a conditional
    # expression; their ``body`` is one node, not a statement list.
    spec = importlib.util.spec_from_file_location("nex890_checker", CHECKER)
    assert spec is not None and spec.loader is not None
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    for source in (b"hook = lambda response: response\n", b"x = 1 if True else 2\n"):
        assert checker._nex_transform_contract({"transform/main.py": source}) in (True, False)
        path = tmp_path / "main.py"
        path.write_bytes(source)
        checker._non_doc_string_literals(path)


def _nex890_checker():
    spec = importlib.util.spec_from_file_location("nex890_checker", CHECKER)
    assert spec is not None and spec.loader is not None
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    return checker


def test_hard_coded_endpoint_ast_sees_a_config_dict_bound_to_a_name() -> None:
    checker = _nex890_checker()
    config_dict = (
        b"from dlt.sources.rest_api import rest_api_resources\n"
        b"config = {'client': {'base_url': base}, 'resources': [{'name': 'orders',"
        b" 'endpoint': {'path': '/v1/orders'}}]}\n"
        b"resources = rest_api_resources(config)\n"
    )
    from_profile = (
        b"from dlt.sources.rest_api import rest_api_resources\n"
        b"config = {'resources': [{'endpoint': {'path': secrets['endpoint_orders']}}]}\n"
        b"resources = rest_api_resources(config)\n"
    )

    assert checker._nex_hardcoded_endpoint_ast({"transform/main.py": config_dict})
    assert not checker._nex_hardcoded_endpoint_ast({"transform/main.py": from_profile})


_TEMPLATE_TRANSFORM = """\
import os
from dlt.sources.rest_api import rest_api_resources


def _headers_from(secrets):
    return {k[len("header_"):]: v for k, v in secrets.items() if k.startswith("header_")}


def build(secrets, models):
    token = os.environ[secrets["credential_env"]]
    for m in models:
        path = secrets[f"endpoint_{m}"]
        if path.startswith(("http://", "https://")):
            raise ValueError("endpoint must be a path")
    return rest_api_resources({"client": {"headers": _headers_from(secrets), "auth": token}})
"""


def test_transform_contract_accepts_the_skill_template_shape() -> None:
    checker = _nex890_checker()

    assert checker._nex_transform_contract({"transform/main.py": _TEMPLATE_TRANSFORM.encode()})
    hard_coded = _TEMPLATE_TRANSFORM.replace(
        'secrets[f"endpoint_{m}"]', '"http://127.0.0.1:8000/v1/orders"'
    )
    assert not checker._nex_transform_contract({"transform/main.py": hard_coded.encode()})


def test_checker_requires_the_review_requirement_id() -> None:
    spec = importlib.util.spec_from_file_location("nex890_checker", CHECKER)
    assert spec is not None and spec.loader is not None
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    report = {
        "workflow": "nex890-positive",
        "operation": "advance_workflow",
        "arguments": {
            "action": {
                "type": "report_requirement",
                "parameters": {"requirement_id": "review"},
            }
        },
    }
    wrong_requirement = {
        **report,
        "arguments": {
            "action": {
                "type": "report_requirement",
                "parameters": {"requirement_id": "validation"},
            }
        },
    }
    conflicting_ids = {
        **report,
        "arguments": {
            "action": {
                "type": "report_requirement",
                "requirement_id": "review",
                "parameters": {"requirement_id": "validation"},
            }
        },
    }

    assert checker._nex_case_action_calls([report], "nex890-positive", "report_requirement") == [report]
    assert checker._nex_case_action_calls([wrong_requirement], "nex890-positive", "report_requirement") == []
    assert checker._nex_case_action_calls([conflicting_ids], "nex890-positive", "report_requirement") == []


def test_non_codex_checker_does_not_use_codex_route_phases(tmp_path: Path) -> None:
    result = _run_checker(tmp_path, terminal_route=False)
    assert result.returncode != 0
    assert "negative/unauthorized-401-missing-structured-code" in result.stdout


def test_hard_coded_endpoint_oracle_keeps_legacy_rule_and_tightens_codex_rule(
    tmp_path: Path, monkeypatch
) -> None:
    spec = importlib.util.spec_from_file_location("nex890_checker", CHECKER)
    assert spec is not None and spec.loader is not None
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    transform = tmp_path / ".eval-cases/hard-coded-endpoint/transform/main.py"
    transform.parent.mkdir(parents=True)
    transform.write_text("ENDPOINT = '/v1/orders'\n", encoding="utf-8")

    monkeypatch.delenv("NXD_EVAL_TERMINAL_WORKFLOW_ROUTE", raising=False)
    assert checker._hard_coded_case_is_runner_rejected(tmp_path)

    transform.write_text(
        "from dlt.sources.rest_api import rest_api_resources\n"
        "ENDPOINT_URL = 'http://127.0.0.1/v1/orders'\n"
        "source = rest_api_resources({'client': {'base_url': ENDPOINT_URL}})\n",
        encoding="utf-8",
    )
    monkeypatch.setenv(
        "NXD_EVAL_TERMINAL_WORKFLOW_ROUTE", "terminal_workflow_review_v1"
    )
    assert checker._hard_coded_case_is_runner_rejected(tmp_path)

    transform.write_text(
        transform.read_text(encoding="utf-8")
        + "# api-source-endpoints was retained\n",
        encoding="utf-8",
    )
    assert not checker._hard_coded_case_is_runner_rejected(tmp_path)


def test_checker_rejects_missing_lifecycle_evidence(tmp_path: Path) -> None:
    trace = _trace(tmp_path)
    records = [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines()]
    records = [record for record in records if record.get("message", {}).get("params", {}).get("name") != "export_data_product"]
    trace.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")
    result = _run_checker(tmp_path, trace=trace)
    assert result.returncode != 0
    assert "export/public-export-missing" in result.stdout


def test_checker_rejects_fabricated_negative_records(tmp_path: Path) -> None:
    result = _run_checker(tmp_path, trace=_trace(tmp_path, omit_case="hard-coded-endpoint"))
    assert result.returncode != 0
    assert "negative/hard-coded-endpoint-not-trace-linked" in result.stdout


def test_checker_rejects_pagination_bypass(tmp_path: Path) -> None:
    result = _run_checker(tmp_path, observations=_observations(tmp_path, bypass=True))
    assert result.returncode != 0
    assert "landed/unfiltered-page-1-shape" in result.stdout


def test_checker_rejects_hard_coded_http_transform(tmp_path: Path) -> None:
    root = tmp_path / "closure"
    root.mkdir()
    _write_valid_closure(root)
    (root / "transform/main.py").write_text("import requests\nrequests.get('http://literal')\n", encoding="utf-8")
    result = _run_checker(tmp_path, root=root)
    assert result.returncode != 0
    assert "ingestion/dlt-rest-connector-invalid" in result.stdout
    assert "ingestion/hard-coded-topology" in result.stdout


def test_checker_scans_export_entries_for_secret_leaks(tmp_path: Path) -> None:
    root = tmp_path / "closure"
    root.mkdir()
    _write_valid_closure(root)
    with zipfile.ZipFile(root / "exports" / "nex890.zip", "w") as bundle:
        bundle.writestr("infra-profile.yaml", SECRET)
    result = _run_checker(tmp_path)
    assert result.returncode != 0
    assert "redaction/marker-in-export-entry" in result.stdout
