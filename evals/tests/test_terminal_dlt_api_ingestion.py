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
        "unauthorized-401": ("auth", "transform_error"),
        "forbidden-403": ("auth", "transform_error"),
        "unknown-endpoint-404": ("source", "transform_error"),
        "malformed-companion": ("closure", "structure/companion_files_invalid"),
        "omitted-companion": ("closure", "structure/companion_files_invalid"),
        "hard-coded-endpoint": ("closure", "structure/endpoint_not_companion_derived"),
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
        "ENDPOINT = '/v1/orders'\n",
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
        "unauthorized-401": ("auth", "transform_error"),
        "forbidden-403": ("auth", "transform_error"),
        "unknown-endpoint-404": ("source", "transform_error"),
        "malformed-companion": ("closure", "structure/companion_files_invalid"),
        "omitted-companion": ("closure", "structure/companion_files_invalid"),
        "hard-coded-endpoint": ("closure", "structure/endpoint_not_companion_derived"),
    }
    for case, (phase, code) in cases.items():
        if case == omit_case:
            continue
        signature = {
            "unauthorized-401": "401 unauthorized",
            "forbidden-403": "403 forbidden",
            "unknown-endpoint-404": "404 not_found",
            "malformed-companion": "companion invalid",
            "omitted-companion": "companion missing",
            "hard-coded-endpoint": "hard-coded endpoint transform",
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


def _run_checker(tmp_path: Path, *, trace: Path | None = None, observations: Path | None = None, root: Path | None = None) -> subprocess.CompletedProcess[str]:
    root = root or (tmp_path / "closure")
    if not root.exists():
        root.mkdir()
        _write_valid_closure(root)
    trace = trace or _trace(tmp_path)
    observations = observations or _observations(tmp_path)
    marker = tmp_path / "marker.txt"
    marker.write_text(SECRET + "\n", encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(CHECKER), "--fixtures", str(SCENARIO / "fixtures"), "--root", str(root), "--trace", str(trace), "--secret-marker-file", str(marker)],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "NXD_STUB_OBSERVATIONS": str(observations)},
    )


def test_scenario_wires_current_runner_contract() -> None:
    checks = json.loads((SCENARIO / "checks.json").read_text(encoding="utf-8"))
    stdio = json.loads((SCENARIO / "fixtures/desktop_stdio.json").read_text(encoding="utf-8"))
    http = json.loads((SCENARIO / "fixtures/http_stub.json").read_text(encoding="utf-8"))
    assert checks["deterministic_check"]["trace_source"] == "runner_mcp"
    assert stdio["profile_builder"] == "prepare_stdio_profile.py"
    assert http["agent_env"] == {"NXD_EVAL_SOURCE_TOKEN": "VALID_TOKEN"}
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
