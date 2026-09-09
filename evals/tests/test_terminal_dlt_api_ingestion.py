"""Contract tests for the terminal authenticated DLT API scenario."""

from __future__ import annotations

import json
import os
import importlib.util
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCENARIO = ROOT / "evals/public/terminal-authenticated-dlt-api-ingestion"
CHECKER = SCENARIO / "fixtures/check_dlt_api.py"
SECRET = "nex890-opaque-synthetic-secret-9a3c"


def _write_valid_closure(root: Path) -> None:
    (root / "transform").mkdir(parents=True)
    (root / "transform/main.py").write_text(
        "from dlt.sources.rest_api import rest_api_resources\n"
        "def source(secrets):\n"
        "    return rest_api_resources()\n",
        encoding="utf-8",
    )
    (root / "infra-profile.yaml").write_text(
        "services:\n"
        "  - name: api-source\n"
        "    attributes:\n"
        "      - key: base_url\n"
        "        value: http://127.0.0.1:1\n"
        "        public: true\n"
        "      - key: endpoint_orders\n"
        "        value: /v1/orders\n"
        "        public: true\n"
        "      - key: auth_token\n"
        f"        value: {SECRET}\n"
        "        public: false\n",
        encoding="utf-8",
    )
    (root / ".eval-cases").mkdir()
    for case, code in {
        "unauthorized-401": "auth/unauthorized",
        "forbidden-403": "auth/forbidden",
        "unknown-endpoint-404": "source/not_found",
        "malformed-profile": "closure/profile_malformed",
        "omitted-profile": "closure/profile_missing",
        "retired-companion": "closure/retired_endpoint_companion",
        "hard-coded-endpoint": "closure/endpoint_not_profile_derived",
    }.items():
        case_dir = root / ".eval-cases" / case
        case_dir.mkdir()
        (case_dir / "failure.json").write_text(
            json.dumps({"status": "failed", "code": code}), encoding="utf-8"
        )


def _trace(tmp_path: Path, *, leaked: bool = False) -> Path:
    request = {
        "source": "runner",
        "direction": "request",
        "message": {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "build_data_product", "arguments": {}},
        },
    }
    response = {
        "source": "runner",
        "direction": "response",
        "message": {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"content": [{"type": "text", "text": "published"}]},
        },
    }
    if leaked:
        response["message"]["result"]["content"][0]["text"] = SECRET
    path = tmp_path / "trace.jsonl"
    path.write_text("\n".join(json.dumps(item) for item in (request, response)) + "\n", encoding="utf-8")
    return path


def _run_checker(tmp_path: Path, *, leaked: bool = False) -> subprocess.CompletedProcess[str]:
    root = tmp_path / "closure"
    root.mkdir()
    _write_valid_closure(root)
    trace = _trace(tmp_path, leaked=leaked)
    marker = tmp_path / "marker.txt"
    marker.write_text(SECRET + "\n", encoding="utf-8")
    observations = tmp_path / "observations.jsonl"
    observations.write_text(
        "\n".join(
            json.dumps({"path": f"/v1/orders?page={page}", "authorized": True, "user_agent": "nexty-dlt-client/1.0", "status": 200, "rows": rows, "total": 23})
            for page, rows in ((1, 10), (2, 10), (3, 3))
        ) + "\n",
        encoding="utf-8",
    )
    env = {**os.environ, "NXD_STUB_OBSERVATIONS": str(observations)}
    return subprocess.run(
        [
            sys.executable,
            str(CHECKER),
            "--fixtures",
            str(SCENARIO / "fixtures"),
            "--root",
            str(root),
            "--trace",
            str(trace),
            "--secret-marker-file",
            str(marker),
        ],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def test_scenario_wires_runner_owned_stdio_http_and_withheld_checker() -> None:
    checks = json.loads((SCENARIO / "checks.json").read_text(encoding="utf-8"))
    stdio = json.loads((SCENARIO / "fixtures/desktop_stdio.json").read_text(encoding="utf-8"))
    http = json.loads((SCENARIO / "fixtures/http_stub.json").read_text(encoding="utf-8"))
    run_text = (ROOT / "evals/run.py").read_text(encoding="utf-8")
    assert checks["deterministic_check"]["trace_source"] == "runner_mcp"
    assert stdio["workflow"] == "terminal-authenticated-dlt-api-ingestion"
    assert http["observations"] is True
    assert "terminal-authenticated-dlt-api-ingestion" in run_text
    assert (SCENARIO / "fixtures/check_dlt_api.py").is_file()
    assert (SCENARIO / "fixtures/../../terminal-self-check-provenance/fixtures/prepare_stdio_profile.py").is_file()


def test_stub_exposes_auth_matrix_and_three_pages(tmp_path: Path) -> None:
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
        assert all(page["total"] == 23 and page["pages"] == 3 for page in pages)
    finally:
        module.stop_server(server, thread)


def test_checker_accepts_complete_local_contract(tmp_path: Path) -> None:
    result = _run_checker(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ALL CHECKS PASSED" in result.stdout


def test_checker_rejects_secret_leak_in_runner_trace(tmp_path: Path) -> None:
    result = _run_checker(tmp_path, leaked=True)
    assert result.returncode != 0
    assert "redaction/secret-in-trace" in result.stdout


def test_checker_rejects_hand_written_http_and_missing_negative_case(tmp_path: Path) -> None:
    root = tmp_path / "closure"
    root.mkdir()
    _write_valid_closure(root)
    transform = root / "transform/main.py"
    transform.write_text("import requests\nrequests.get('http://literal')\n", encoding="utf-8")
    (root / ".eval-cases/forbidden-403/failure.json").unlink()
    trace = _trace(tmp_path)
    marker = tmp_path / "marker.txt"
    marker.write_text(SECRET + "\n", encoding="utf-8")
    observations = tmp_path / "observations.jsonl"
    observations.write_text(
        "\n".join(
            json.dumps({"path": f"/v1/orders?page={page}", "authorized": True, "user_agent": "nexty-dlt-client/1.0", "status": 200, "rows": rows, "total": 23})
            for page, rows in ((1, 10), (2, 10), (3, 3))
        ) + "\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, str(CHECKER), "--fixtures", str(SCENARIO / "fixtures"), "--root", str(root), "--trace", str(trace), "--secret-marker-file", str(marker)],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "NXD_STUB_OBSERVATIONS": str(observations)},
    )
    assert result.returncode != 0
    assert "ingestion/hand-written-http-loop" in result.stdout
    assert "negative/forbidden-403-missing-structured-code" in result.stdout
