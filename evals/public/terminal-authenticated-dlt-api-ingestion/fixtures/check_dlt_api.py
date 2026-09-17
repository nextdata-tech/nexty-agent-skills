"""Runner-side oracle for terminal authenticated DLT API ingestion."""

from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import os
import re
import stat
import sys
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Any

TOOLS_DIR = Path(__file__).resolve().parents[3] / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from api_connector_gate import (  # noqa: E402
    find_closure,
    headers_built_from_secrets,
    uses_rest_api_resources,
)


WORKFLOW = "terminal-authenticated-dlt-api-ingestion"
EXPECTED_CASES = {
    "unauthorized-401": ("auth", ("401", "unauthorized")),
    "forbidden-403": ("auth", ("403", "forbidden")),
    "unknown-endpoint-404": ("source", ("404", "not_found", "unknown endpoint")),
    "malformed-companion": ("closure", ("companion", "invalid", "malformed")),
    "omitted-companion": ("closure", ("companion", "missing", "no such file")),
    "hard-coded-endpoint": ("closure", ("endpoint", "transform", "hard-coded")),
}
PAGE_ROWS = {1: 10, 2: 10, 3: 3}
FILTERED_PAGE_TOTAL = 16
FILTERED_PAGE_ROWS = {1: 10, 2: 6}
REQUIRED_USER_AGENT = "nexty-dlt-client/1.0"
REQUIRED_TOOLS = {
    "get_workflow_capabilities",
    "check_data_product",
    "prepare_workflow",
    "advance_workflow",
    "inspect_workflow",
    "inspect_run",
    "list_data_products",
    "resume_data_product",
    "describe_models",
    "run_semantic_query",
    "export_data_product",
}
NON_TOOL_METHODS = {
    "initialize",
    "notifications/initialized",
    "tools/list",
    "resources/list",
    "resources/read",
    "ping",
}


def _jsonl(path: Path, failures: list[str], label: str) -> list[Any]:
    records: list[Any] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        failures.append(f"{label}/unreadable")
        return records
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            failures.append(f"{label}/malformed-json-line-{number}")
    return records


def _objects(value: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []

    def walk(current: Any) -> None:
        if isinstance(current, dict):
            found.append(current)
            for child in current.values():
                walk(child)
        elif isinstance(current, list):
            for child in current:
                walk(child)
        elif isinstance(current, str):
            try:
                decoded = json.loads(current)
            except json.JSONDecodeError:
                return
            if isinstance(decoded, (dict, list)):
                walk(decoded)

    walk(value)
    return found


def _strings(value: Any) -> list[str]:
    result: list[str] = []
    for obj in _objects(value):
        for item in obj.values():
            if isinstance(item, str):
                result.append(item)
    if isinstance(value, str):
        result.append(value)
    return result


def _record_message(record: Any) -> dict[str, Any] | None:
    message = record.get("message") if isinstance(record, dict) else None
    return message if isinstance(message, dict) else None


def _id_key(value: Any) -> str:
    return json.dumps([type(value).__name__, value], sort_keys=True)


def _trace_calls(trace: list[Any], failures: list[str]) -> list[dict[str, Any]]:
    requests: list[dict[str, Any]] = []
    request_ids: set[str] = set()
    responses: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    for index, record in enumerate(trace):
        if not isinstance(record, dict):
            failures.append("trace/non-object-record")
            continue
        if record.get("source") != "runner":
            failures.append("trace/non-runner-source")
        if record.get("protocol") != "mcp":
            failures.append("trace/non-mcp-protocol")
        direction = record.get("direction")
        message = _record_message(record)
        if direction not in {"request", "response"}:
            failures.append("trace/invalid-direction")
        if message is None:
            failures.append("trace/non-object-json-rpc-message")
            continue
        if message.get("jsonrpc") != "2.0":
            failures.append("trace/jsonrpc-version-missing")
        if direction == "request":
            method = message.get("method")
            if method in NON_TOOL_METHODS:
                continue
            params = message.get("params")
            if method != "tools/call" or not isinstance(params, dict):
                failures.append("trace/public-tools-call-invalid")
                continue
            name = params.get("name")
            if not isinstance(name, str):
                failures.append("trace/tool-name-missing")
                continue
            request_id = _id_key(message.get("id"))
            if request_id in request_ids:
                failures.append("trace/duplicate-request-id")
            request_ids.add(request_id)
            requests.append({
                "index": index,
                "id": request_id,
                "name": name,
                "arguments": params.get("arguments", {}),
                "message": message,
            })
        elif direction == "response":
            responses.setdefault(_id_key(message.get("id")), []).append((index, message))

    calls: list[dict[str, Any]] = []
    for request in requests:
        matching = [item for item in responses.get(request["id"], []) if item[0] > request["index"]]
        response = matching[0][1] if matching else None
        if response is None:
            failures.append(f"trace/missing-response/{request['name']}")
        calls.append({**request, "response": response})
    return calls


def _call_text(call: dict[str, Any]) -> str:
    response = call.get("response")
    return json.dumps(response or {}, sort_keys=True)


def _call_objects(call: dict[str, Any]) -> list[dict[str, Any]]:
    response = call.get("response")
    return _objects(response or {})


def _call_has_error(call: dict[str, Any]) -> bool:
    response = call.get("response")
    if not isinstance(response, dict):
        return True
    if "error" in response:
        return True
    result = response.get("result")
    return isinstance(result, dict) and result.get("isError") is True


def _call_success(call: dict[str, Any]) -> bool:
    return call.get("response") is not None and not _call_has_error(call)


def _call_args_text(call: dict[str, Any]) -> str:
    return json.dumps(call.get("arguments", {}), sort_keys=True)


def _redacted_keys(call: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for obj in _call_objects(call):
        values = obj.get("redacted")
        if not isinstance(values, list):
            continue
        for value in values:
            if isinstance(value, str):
                keys.add(value)
            elif isinstance(value, dict) and isinstance(value.get("key"), str):
                keys.add(value["key"])
    return keys


def _query_has_expected_paid_count(call: dict[str, Any]) -> bool:
    return any(
        obj.get("row_count") == 1
        and isinstance(obj.get("rows"), list)
        and len(obj["rows"]) == 1
        and isinstance(obj["rows"][0], list)
        and len(obj["rows"][0]) == 1
        and obj["rows"][0][0] == FILTERED_PAGE_TOTAL
        for obj in _call_objects(call)
    )


def _contains_value(calls: list[dict[str, Any]], key: str, expected: Any) -> bool:
    return any(
        obj.get(key) == expected
        for call in calls
        for obj in _call_objects(call)
    )


def _has_digest(calls: list[dict[str, Any]]) -> bool:
    digest = re.compile(r"(?:sha256(?:-v\d+)?[:_-])[0-9a-f]{64}", re.IGNORECASE)
    return any(digest.search(text) for call in calls for text in _strings(call.get("response", {})))


def _code_in_call(call: dict[str, Any], code: str) -> bool:
    return any(obj.get("code") == code for obj in _call_objects(call))


def _code_in_text(call: dict[str, Any], code: str) -> bool:
    return code in _call_text(call)


def _case_in_call(call: dict[str, Any], case: str) -> bool:
    return case in _call_args_text(call) or case in _call_text(call)


def _call_has_structured_failure(call: dict[str, Any]) -> bool:
    if _call_has_error(call):
        return True
    text = _call_text(call).lower()
    if any(obj.get("outcome") in {"fail", "failed"} for obj in _call_objects(call)):
        return True
    if any(obj.get("status") in {"fail", "failed", "error"} for obj in _call_objects(call)):
        return True
    if "transform_error" in text:
        return True
    return any(
        isinstance(obj.get("code"), str)
        and obj.get("code") not in {"", "ok", "success"}
        for obj in _call_objects(call)
    )


def _read_markers(path: Path, failures: list[str]) -> list[str]:
    try:
        markers = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except OSError:
        failures.append("redaction/marker-file-unreadable")
        return []
    if not markers or any(len(marker) < 8 for marker in markers):
        failures.append("redaction/marker-file-unusable")
    return markers


def _non_doc_string_literals(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return []
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if body and isinstance(body[0], ast.Expr):
            value = body[0].value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                docstrings.add(id(value))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]


def _profile_fields(profile: Path) -> dict[str, str]:
    fields: dict[str, str] = {}
    current: str | None = None
    for line in profile.read_text(encoding="utf-8", errors="replace").splitlines():
        key = re.match(r"^\s*-?\s*key:\s*(\S+)", line)
        if key:
            current = key.group(1)
            continue
        value = re.match(r"^\s*value:\s*(.+?)\s*$", line)
        if value and current:
            fields[current] = value.group(1).strip("'\"")
    return fields


def _companion_paths(root: Path) -> tuple[list[str], list[str]]:
    manifest = root / "companion-files"
    if not manifest.is_file():
        return [], []
    entries = [
        line.strip()
        for line in manifest.read_text(encoding="utf-8", errors="replace").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    return entries, [entry for entry in entries if (root / entry).is_file()]


def _observe(path: Path, failures: list[str]) -> list[dict[str, Any]]:
    if not path.is_file():
        failures.append("observations/log-missing")
        return []
    records = _jsonl(path, failures, "observations")
    valid: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            failures.append("observations/non-object-record")
        else:
            valid.append(record)
    return valid


def _check_observations(observations: list[dict[str, Any]], failures: list[str]) -> None:
    for status, marker in ((401, "auth/401-not-observed"), (403, "auth/403-not-observed"), (404, "source/404-not-observed")):
        if not any(record.get("status") == status for record in observations):
            failures.append(marker)

    full = [
        record for record in observations
        if record.get("status") == 200 and not record.get("status_filter")
    ]
    by_page = {record.get("page"): record for record in full}
    if set(by_page) != set(PAGE_ROWS) or len(full) != 3:
        failures.append("landed/unfiltered-pages-not-distinct")
    for page, rows in PAGE_ROWS.items():
        record = by_page.get(page)
        if not isinstance(record, dict):
            continue
        if record.get("rows") != rows or record.get("total") != 23 or record.get("pages") != 3:
            failures.append(f"landed/unfiltered-page-{page}-shape")
        if record.get("per_page") != 10:
            failures.append(f"landed/unfiltered-page-{page}-unbounded")
        if not record.get("authorized") or record.get("user_agent") != REQUIRED_USER_AGENT:
            failures.append(f"wire/unfiltered-page-{page}-auth")

    filtered = [
        record for record in observations
        if record.get("status") == 200 and record.get("status_filter") == "paid"
    ]
    filtered_by_page = {record.get("page"): record for record in filtered}
    if set(filtered_by_page) != set(FILTERED_PAGE_ROWS) or len(filtered) != 2:
        failures.append("query/paid-pages-not-distinct")
    for page, rows in FILTERED_PAGE_ROWS.items():
        record = filtered_by_page.get(page)
        if not isinstance(record, dict):
            continue
        if record.get("rows") != rows or record.get("total") != FILTERED_PAGE_TOTAL:
            failures.append(f"query/paid-page-{page}-shape")
        if record.get("per_page") != 10 or record.get("pages") != 2:
            failures.append(f"query/paid-page-{page}-unbounded")
        if not record.get("authorized") or record.get("user_agent") != REQUIRED_USER_AGENT:
            failures.append(f"wire/paid-page-{page}-auth")


_REPLAY_SCRIPT = r'''
import os
import sys
import types
from dataclasses import dataclass

@dataclass
class DuckDbOutput:
    path: str
    schema: str
    model_tables: dict

nxd = types.ModuleType("nxd")
core = types.ModuleType("nxd.core")
ctx = types.ModuleType("nxd.core.context")
ctx.DuckDbOutput = DuckDbOutput
nxd.data_product = types.SimpleNamespace(
    on_transform=lambda *args, **kwargs: (lambda fn: fn),
    main=lambda: None,
)
nxd.core = core
core.context = ctx
sys.modules.update({"nxd": nxd, "nxd.core": core, "nxd.core.context": ctx})

closure, base_url, token, user_agent, db_path = sys.argv[1:]
os.environ["NXD_TRANSFORM_ROOT"] = closure
sys.path.insert(0, closure)
from transform import main

models = tuple(getattr(main, "PHYSICAL_MODELS", ("orders",)))
out = DuckDbOutput(db_path, "main", {model: model for model in models})
main.ingest(
    duckdb=out,
    secrets={
        "base_url": base_url,
        "auth_type": "bearer",
        "auth_token": token,
        "header_user_agent": user_agent,
    },
)
'''


def _runner_replay_observations(
    fixtures: Path, closure: Path, marker: str, failures: list[str]
) -> list[dict[str, Any]]:
    """Re-run the landed transform against a fresh runner-owned stub.

    The agent's request log is useful for negative-wire cases, but a successful
    source log can be forged by issuing the same HTTP requests from Bash. This
    replay happens after the agent session and invokes the landed DLT transform
    itself, so the positive pagination/filter observations are independent of
    the agent's process and workspace.
    """
    stub_path = fixtures / "stub_dlt_api.py"
    spec = importlib.util.spec_from_file_location("nex890_replay_stub", stub_path)
    if spec is None or spec.loader is None:
        failures.append("replay/stub-unavailable")
        return []
    stub = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(stub)
    except Exception:
        failures.append("replay/stub-load-failed")
        return []

    with tempfile.TemporaryDirectory(prefix="nex890-dlt-replay-") as replay_dir:
        replay_root = Path(replay_dir)
        observation_path = replay_root / "observations.jsonl"
        observation_path.write_text("", encoding="utf-8")
        stub.set_observations_path(observation_path)
        try:
            server, port, thread = stub.start_server()
        except Exception:
            stub.set_observations_path(None)
            failures.append("replay/stub-start-failed")
            return []
        try:
            db_path = replay_root / "replay.duckdb"
            script_path = replay_root / "replay.py"
            script_path.write_text(_REPLAY_SCRIPT, encoding="utf-8")
            proc = subprocess.run(
                [
                    "uv", "run", "--no-project", "--with", "dlt[duckdb]==1.28.2",
                    "python", str(script_path), str(closure),
                    f"http://127.0.0.1:{port}", marker, REQUIRED_USER_AGENT,
                    str(db_path),
                ],
                cwd=closure,
                capture_output=True,
                text=True,
                timeout=180,
                env={**os.environ, "PYTHONPATH": ""},
                check=False,
            )
            if proc.returncode != 0:
                failures.append("replay/dlt-transform-failed")
                return []
            records = _jsonl(observation_path, failures, "replay-observations")
            if not records:
                failures.append("replay/no-dlt-requests")
            elif not any(record.get("status") == 200 for record in records if isinstance(record, dict)):
                statuses = sorted({record.get("status") for record in records if isinstance(record, dict)})
                failures.append(f"replay/no-successful-dlt-page/{statuses}")
            return [record for record in records if isinstance(record, dict)]
        except (OSError, subprocess.SubprocessError):
            failures.append("replay/dlt-transform-unavailable")
            return []
        finally:
            try:
                stub.stop_server(server, thread)
            finally:
                stub.set_observations_path(None)


def _check_architecture(root: Path, markers: list[str], failures: list[str]) -> Path:
    closure = find_closure(root)
    ok, detail = uses_rest_api_resources(closure)
    if not ok:
        failures.append("ingestion/dlt-rest-connector-invalid")
        if detail:
            failures.append("ingestion/dlt-rest-connector-detail")

    transform_files = sorted((closure / "transform").glob("*.py")) if (closure / "transform").is_dir() else []
    source_literals = [literal for path in transform_files for literal in _non_doc_string_literals(path)]
    if any(re.search(r"(?:https?://|127\.0\.0\.1|/v1/orders|ENDPOINT_URL)", literal) for literal in source_literals):
        failures.append("ingestion/hard-coded-topology")
    source_text = "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in transform_files)
    if "NXD_TRANSFORM_ROOT" not in source_text or "api-source-endpoints" not in source_text:
        failures.append("companion/runtime-materialization-read-missing")
    headers_ok, _ = headers_built_from_secrets(closure, REQUIRED_USER_AGENT)
    if not headers_ok:
        failures.append("profile/header-not-built-from-secrets")

    manifest = closure / "companion-files"
    endpoint_file = closure / "api-source-endpoints"
    entries, materialized = _companion_paths(closure)
    if "api-source-endpoints" not in entries:
        failures.append("companion/manifest-declaration-missing")
    if not endpoint_file.is_file() or "api-source-endpoints" not in materialized:
        failures.append("companion/endpoint-file-missing")
    elif endpoint_file.read_text(encoding="utf-8", errors="replace").strip() != "orders=/v1/orders":
        failures.append("companion/endpoint-map-invalid")

    profile = closure / "infra-profile.yaml"
    if not profile.is_file():
        failures.append("profile/missing")
    else:
        try:
            mode = stat.S_IMODE(profile.stat().st_mode)
        except OSError:
            mode = 0
        if mode != 0o600:
            failures.append("redaction/infra-profile-not-mode-0600")
        fields = _profile_fields(profile)
        for key in ("base_url", "auth_type", "auth_token", "header_user_agent"):
            if key not in fields:
                failures.append(f"profile/{key}-missing")
        if fields.get("auth_type") != "bearer":
            failures.append("profile/auth-type-invalid")
        if fields.get("auth_token") not in markers:
            failures.append("profile/auth-token-not-runner-injected")
        if any(key.startswith("endpoint_") for key in fields):
            failures.append("profile/endpoint-topology-must-be-companion")

    if manifest.is_file() and any(marker in manifest.read_text(encoding="utf-8", errors="replace") for marker in markers):
        failures.append("redaction/marker-in-companion-manifest")
    if endpoint_file.is_file() and any(marker in endpoint_file.read_text(encoding="utf-8", errors="replace") for marker in markers):
        failures.append("redaction/marker-in-companion")
    return closure


def _check_redaction(root: Path, closure: Path, markers: list[str], trace_path: Path, calls: list[dict[str, Any]], failures: list[str]) -> None:
    trace_bytes = trace_path.read_bytes()
    if any(marker.encode("utf-8") in trace_bytes for marker in markers):
        failures.append("redaction/marker-in-trace")

    allowed_profiles = {
        path
        for path in root.rglob("infra-profile.yaml")
        if path.is_file()
        and stat.S_IMODE(path.stat().st_mode) == 0o600
        and any(marker in path.read_text(encoding="utf-8", errors="replace") for marker in markers)
    }
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path in allowed_profiles:
            continue
        try:
            payload = path.read_bytes()
        except OSError:
            failures.append("redaction/artifact-unreadable")
            continue
        if any(marker.encode("utf-8") in payload for marker in markers):
            failures.append("redaction/marker-in-generated-artifact")

    export_calls = [call for call in calls if call["name"] == "export_data_product" and _call_success(call)]
    if not export_calls:
        failures.append("export/archive-not-trace-bound")
        return
    archives: list[Path] = []
    for call in export_calls:
        destination = call.get("arguments", {}).get("destination")
        returned = next(
            (
                obj.get("archive_path")
                for obj in _call_objects(call)
                if isinstance(obj.get("archive_path"), str)
            ),
            None,
        )
        if not isinstance(destination, str) or not isinstance(returned, str):
            continue
        definition = call.get("arguments", {}).get("definition")
        if not isinstance(definition, str):
            failures.append("export/definition-not-trace-bound")
        else:
            definition_path = Path(definition)
            if not definition_path.is_absolute():
                definition_path = root / definition_path
            if definition_path.resolve() != closure.resolve():
                failures.append("export/definition-not-trace-bound")
        destination_path = Path(destination)
        returned_path = Path(returned)
        if not destination_path.is_absolute():
            destination_path = root / destination_path
        if not returned_path.is_absolute():
            returned_path = root / returned_path
        if destination_path.resolve() != returned_path.resolve():
            failures.append("export/archive-path-mismatch")
            continue
        archive = returned_path.resolve()
        if not archive.is_relative_to(root.resolve()):
            failures.append("export/archive-outside-workspace")
        elif archive.is_file() and archive.suffix == ".zip":
            archives.append(archive)
    if not archives:
        failures.append("export/archive-not-trace-bound")
    if not any("auth_token" in _redacted_keys(call) for call in export_calls):
        failures.append("export/auth-token-redaction-record-missing")
    for archive in archives:
        try:
            with zipfile.ZipFile(archive) as bundle:
                names = set(bundle.namelist())
                required = {"IMPORT.md", "export.json", "infra-profile.yaml", "companion-files", "api-source-endpoints"}
                if not required.issubset(names):
                    failures.append("export/archive-closure-entries-missing")
                for entry in bundle.infolist():
                    if any(marker.encode("utf-8") in bundle.read(entry) for marker in markers):
                        failures.append("redaction/marker-in-export-entry")
        except (OSError, zipfile.BadZipFile, RuntimeError):
            failures.append("export/archive-unreadable")


def _check_lifecycle(calls: list[dict[str, Any]], failures: list[str]) -> None:
    names = {call["name"] for call in calls}
    missing = sorted(REQUIRED_TOOLS - names)
    for name in missing:
        failures.append(f"trace/required-tool-missing/{name}")
    if not any(call["name"] == "get_workflow_capabilities" and _call_success(call) and _contains_value([call], "execution_enabled", True) for call in calls):
        failures.append("lifecycle/capability-gate-missing")
    if not any(call["name"] == "check_data_product" and _call_success(call) and any(obj.get("outcome") in {"pass", "warn"} for obj in _call_objects(call)) for call in calls):
        failures.append("lifecycle/preflight-success-missing")
    if not any(call["name"] == "prepare_workflow" and _call_success(call) and WORKFLOW in _call_args_text(call) for call in calls):
        failures.append("lifecycle/prepare-success-missing")
    advances = [call for call in calls if call["name"] == "advance_workflow"]
    if len([call for call in advances if _call_success(call)]) < 3:
        failures.append("lifecycle/advance-sequence-incomplete")
    start_calls = [call for call in advances if _call_success(call) and "start_run" in _call_args_text(call)]
    if not start_calls:
        failures.append("lifecycle/start-run-action-missing")
    run_ids = {
        obj.get("run_id")
        for call in start_calls
        for obj in _call_objects(call)
        if isinstance(obj.get("run_id"), str)
    }
    definition_ids = {
        obj.get("definition_id")
        for call in start_calls
        for obj in _call_objects(call)
        if isinstance(obj.get("definition_id"), str)
    }
    run_id = next(iter(run_ids), None)
    definition_id = next(iter(definition_ids), None)
    if not run_id or not definition_id:
        failures.append("lifecycle/start-run-identities-missing")

    inspect_calls = [call for call in calls if call["name"] == "inspect_workflow" and _call_success(call)]
    if not inspect_calls or not any(
        WORKFLOW in _call_text(call)
        and any(obj.get("run_id") == run_id for obj in _call_objects(call))
        and any(obj.get("definition_id") == definition_id for obj in _call_objects(call))
        for call in inspect_calls
    ):
        failures.append("lifecycle/inspect-workflow-evidence-missing")
    run_inspections = [call for call in calls if call["name"] == "inspect_run" and _call_success(call)]
    if not run_inspections or not any(
        any(
            obj.get("run_id") == run_id
            and obj.get("definition_id") == definition_id
            and obj.get("workflow") == WORKFLOW
            for obj in _call_objects(call)
        )
        for call in run_inspections
    ):
        failures.append("lifecycle/inspect-run-evidence-missing")
    if not _has_digest(calls):
        failures.append("materialization/definition-digest-missing")

    listing = [call for call in calls if call["name"] == "list_data_products" and _call_success(call)]
    if not any(
        any(obj.get("artifact_status") == "available" and obj.get("workflow") == WORKFLOW for obj in _call_objects(call))
        and any(obj.get("row_count") == 23 for obj in _call_objects(call))
        and any(obj.get("run_id") == run_id for obj in _call_objects(call))
        and any(obj.get("definition_id") == definition_id for obj in _call_objects(call))
        for call in listing
    ):
        failures.append("publication/available-product-row-count-missing")
    resume_calls = [
        call for call in calls
        if call["name"] == "resume_data_product"
        and _call_success(call)
        and WORKFLOW in _call_args_text(call)
    ]
    resume_identity = next(
        (
            (
                next((obj.get("semantic_endpoint") for obj in _call_objects(call) if isinstance(obj.get("semantic_endpoint"), str)), None),
                next((obj.get("bearer_token") for obj in _call_objects(call) if isinstance(obj.get("bearer_token"), str)), None),
            )
            for call in resume_calls
        ),
        (None, None),
    )
    resume_endpoint, resume_token = resume_identity
    if not resume_calls:
        failures.append("publication/resume-missing")
    if not resume_endpoint or not resume_token:
        failures.append("publication/resume-identity-missing")
    if not any(
        any(
            obj.get("run_id") == run_id and obj.get("definition_id") == definition_id
            for obj in _call_objects(call)
        )
        for call in resume_calls
    ):
        failures.append("publication/resume-lifecycle-identity-mismatch")
    if not any(call["name"] == "describe_models" and _call_success(call) for call in calls):
        failures.append("query/describe-models-missing")
    describe_calls = [call for call in calls if call["name"] == "describe_models" and _call_success(call)]
    if not any(
        call.get("arguments", {}).get("endpoint") == resume_endpoint
        and call.get("arguments", {}).get("token") == resume_token
        for call in describe_calls
    ):
        failures.append("query/describe-identity-mismatch")
    query_calls = [call for call in calls if call["name"] == "run_semantic_query"]
    valid_paid_query = any(
        _call_success(call)
        and isinstance(call.get("arguments"), dict)
        and call["arguments"].get("endpoint") == resume_endpoint
        and call["arguments"].get("token") == resume_token
        and isinstance(call["arguments"].get("measures"), list)
        and any(
            isinstance(item, dict)
            and item.get("dimension") == "status"
            and item.get("op") == "="
            and item.get("value") == "paid"
            for item in call["arguments"].get("filters", [])
        )
        and _query_has_expected_paid_count(call)
        for call in query_calls
    )
    if not valid_paid_query:
        failures.append("query/governed-paid-query-missing")
    if not any(call["name"] == "export_data_product" and _call_success(call) for call in calls):
        failures.append("export/public-export-missing")

    first_index = {}
    for index, call in enumerate(calls):
        first_index.setdefault(call["name"], index)
    lifecycle_order = [
        "get_workflow_capabilities",
        "check_data_product",
        "prepare_workflow",
        "advance_workflow",
        "inspect_workflow",
        "inspect_run",
        "list_data_products",
        "resume_data_product",
        "describe_models",
        "run_semantic_query",
        "export_data_product",
    ]
    positions = [first_index[name] for name in lifecycle_order if name in first_index]
    if positions != sorted(positions):
        failures.append("lifecycle/public-call-order-invalid")


def _hard_coded_case_is_runner_rejected(root: Path) -> bool:
    case_root = find_closure(root / ".eval-cases" / "hard-coded-endpoint")
    transform_files = sorted((case_root / "transform").glob("*.py")) if (case_root / "transform").is_dir() else []
    if not transform_files:
        return False
    source_literals = [literal for path in transform_files for literal in _non_doc_string_literals(path)]
    has_literal_topology = any(
        re.search(r"(?:https?://|127\.0\.0\.1|/v1/orders|ENDPOINT_URL)", literal)
        for literal in source_literals
    )
    return has_literal_topology and "api-source-endpoints" not in "\n".join(
        path.read_text(encoding="utf-8", errors="replace") for path in transform_files
    )


def _check_negative_cases(root: Path, calls: list[dict[str, Any]], observations: list[dict[str, Any]], failures: list[str]) -> None:
    records: dict[str, dict[str, Any]] = {}
    cases_root = root / ".eval-cases"
    for path in sorted(cases_root.glob("*/failure.json")) if cases_root.is_dir() else []:
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            failures.append(f"negative/{path.parent.name}-malformed-record")
            continue
        if isinstance(record, dict):
            records[path.parent.name] = record

    for case, (phase, needles) in EXPECTED_CASES.items():
        record = records.get(case)
        code = record.get("code") if isinstance(record, dict) else None
        if not isinstance(record, dict) or record.get("status") != "failed" or record.get("phase") != phase or not isinstance(code, str) or not code:
            failures.append(f"negative/{case}-missing-structured-code")
        linked = [
            call for call in calls
            if _case_in_call(call, case)
            and call["name"] in {"check_data_product", "prepare_workflow", "advance_workflow", "inspect_workflow", "inspect_run"}
        ]
        linked_text = " ".join(_call_text(call).lower() for call in linked)
        if not linked or not any(_call_has_structured_failure(call) for call in linked):
            failures.append(f"negative/{case}-not-trace-linked")
        runner_owned_code = case == "hard-coded-endpoint" and _hard_coded_case_is_runner_rejected(root)
        if case == "hard-coded-endpoint" and not runner_owned_code:
            failures.append(f"negative/{case}-runner-static-rejection-missing")
        if isinstance(code, str) and code and code.lower() not in linked_text and not runner_owned_code:
            failures.append(f"negative/{case}-record-code-not-in-trace")
        if not any(needle.lower() in linked_text for needle in needles):
            failures.append(f"negative/{case}-failure-signature-missing")

    for status, case in ((401, "unauthorized-401"), (403, "forbidden-403"), (404, "unknown-endpoint-404")):
        if not any(record.get("status") == status for record in observations):
            failures.append(f"negative/{case}-wire-status-missing")


def check(root: Path, trace_path: Path, marker_path: Path, fixtures: Path) -> list[str]:
    failures: list[str] = []
    markers = _read_markers(marker_path, failures)
    trace = _jsonl(trace_path, failures, "trace")
    calls = _trace_calls(trace, failures)
    if not calls:
        failures.append("trace/public-mcp-tools-call-missing")
    _check_lifecycle(calls, failures)
    closure = _check_architecture(root, markers, failures)

    observation_path = os.environ.get("NXD_STUB_OBSERVATIONS", "")
    runner_observations = _observe(Path(observation_path), failures) if observation_path else []
    replay_observations = _runner_replay_observations(
        fixtures, closure, markers[0] if markers else "", failures
    )
    observations = replay_observations + [
        record for record in runner_observations if record.get("status") in {401, 403, 404}
    ]
    _check_observations(runner_observations, failures)
    _check_observations(observations, failures)
    _check_negative_cases(root, calls, runner_observations, failures)
    _check_redaction(root, closure, markers, trace_path, calls, failures)

    if not failures:
        print("ALL CHECKS PASSED")
    else:
        for failure in sorted(set(failures)):
            print(f"FAIL {failure}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--secret-marker-file", type=Path, required=True)
    args = parser.parse_args()
    return 1 if check(args.root, args.trace, args.secret_marker_file, args.fixtures) else 0


if __name__ == "__main__":
    raise SystemExit(main())
