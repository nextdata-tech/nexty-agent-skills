"""Runner-side oracle for terminal authenticated DLT API ingestion."""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import io
import json
import os
import re
import stat
import sys
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Mapping

TOOLS_DIR = Path(__file__).resolve().parents[3] / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from api_connector_gate import (  # noqa: E402
    find_closure,
    headers_built_from_secrets,
    uses_rest_api_resources,
)


WORKFLOW = "terminal-authenticated-dlt-api-ingestion"
LEGACY_EXPECTED_CASES = {
    "unauthorized-401": ("auth", ("401", "unauthorized")),
    "forbidden-403": ("auth", ("403", "forbidden")),
    "unknown-endpoint-404": ("source", ("404", "not_found", "unknown endpoint")),
    "malformed-companion": ("closure", ("companion", "invalid", "malformed")),
    "omitted-companion": ("closure", ("companion", "missing", "no such file")),
    "hard-coded-endpoint": ("closure", ("endpoint", "transform", "hard-coded")),
}
TERMINAL_ROUTE_EXPECTED_CASES = {
    # Runtime source faults intentionally share the public validation envelope;
    # the runner-owned wire log distinguishes 401/403/404 below.
    "unauthorized-401": ("validation", ("scratch_transform_failed",)),
    "forbidden-403": ("validation", ("scratch_transform_failed",)),
    "unknown-endpoint-404": ("validation", ("scratch_transform_failed",)),
    "malformed-companion": ("validation", ("scratch_transform_failed",)),
    "omitted-companion": ("closure", ("companion", "invalid", "missing", "no such file")),
    "hard-coded-endpoint": ("review", ("endpoint", "transform", "hard-coded", "review")),
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
    except (SyntaxError, ValueError):
        return []
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list) and body and isinstance(body[0], ast.Expr):
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
    closure = _positive_closure(root)
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


# The NEX-890 Claude route uses this in-process checker.  Its inputs are frozen
# by the runner; unlike ``check`` below, this API never opens failure.json,
# observations files, or the live workspace.
_NEX_CASES = {
    "nex890-positive": 200,
    "nex890-401": 401,
    "nex890-403": 403,
    "nex890-404": 404,
}
_NEX_USER_AGENT = REQUIRED_USER_AGENT
_NEX_ENDPOINT = "/v1/orders"
_NEX_SECRET_ENV = "NXD_EVAL_SOURCE_TOKEN"
_NEX_FORBIDDEN_DIAGNOSTIC_TERMS = ("coordinator", "stale", "dependency", "unsupported")
_NEX_REVIEW_VERDICTS = {"clear", "findings", "rejected", "indeterminate"}


def _nex_id_key(value: Any) -> str:
    """Type-sensitive, deterministic JSON-RPC id key."""
    try:
        return json.dumps([type(value).__name__, value], sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        return "<invalid-id>"


def _nex_timestamp(record: Mapping[str, Any]) -> int | None:
    value = record.get("timestamp_monotonic_ns")
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _nex_action(call: Mapping[str, Any]) -> tuple[str | None, Mapping[str, Any]]:
    arguments = call.get("arguments")
    if not isinstance(arguments, Mapping):
        return None, {}
    action = arguments.get("action")
    if not isinstance(action, Mapping):
        return None, {}
    action_type = action.get("type", action.get("action"))
    parameters = action.get("parameters")
    return (action_type if isinstance(action_type, str) else None,
            parameters if isinstance(parameters, Mapping) else {})


def _nex_response_ok(message: Mapping[str, Any]) -> bool:
    if "error" in message:
        return False
    result = message.get("result")
    return isinstance(result, Mapping) and result.get("isError") is not True


def _nex_structured_content(message: Mapping[str, Any]) -> Mapping[str, Any]:
    result = message.get("result")
    if not isinstance(result, Mapping):
        return {}
    if "structuredContent" in result:
        return {}
    content = result.get("content")
    if not isinstance(content, list) or len(content) != 1:
        return {}
    block = content[0]
    if not isinstance(block, Mapping) or block.get("type") != "text":
        return {}
    text = block.get("text")
    if not isinstance(text, str):
        return {}

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate JSON object key")
            value[key] = item
        return value

    try:
        payload = json.loads(text, object_pairs_hook=unique_object)
    except (TypeError, ValueError):
        return {}
    return payload if isinstance(payload, Mapping) else {}


def _nex_requirement(
    payload: Mapping[str, Any], requirement_id: str
) -> Mapping[str, Any]:
    requirements = payload.get("requirements")
    if not isinstance(requirements, list):
        return {}
    matches = [
        item for item in requirements
        if isinstance(item, Mapping) and item.get("id") == requirement_id
    ]
    return matches[0] if len(matches) == 1 else {}


def _nex_selfcheck_failed(payload: Mapping[str, Any]) -> bool:
    """Require a structured self-check failure, never a textual claim."""
    if payload.get("outcome") != "fail":
        return False
    stages = payload.get("stages")
    if not isinstance(stages, list):
        return False
    return any(
        isinstance(stage, Mapping)
        and isinstance(stage.get("checks"), list)
        and any(
            isinstance(check, Mapping) and check.get("status") == "fail"
            for check in stage["checks"]
        )
        for stage in stages
    )


def _nex_structured_objects(message: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Walk structured maps/lists, including one decoded JSON text payload."""
    found: list[Mapping[str, Any]] = []

    def walk(value: Any) -> None:
        if isinstance(value, Mapping):
            found.append(value)
            for child in value.values():
                if isinstance(child, (Mapping, list, tuple)):
                    walk(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                if isinstance(child, (Mapping, list, tuple)):
                    walk(child)

    walk(_nex_structured_content(message))
    return found


def _nex_pair_trace(trace: Any, failures: list[str]) -> list[dict[str, Any]]:
    """Pair the runner bridge's request/response records, failing closed."""
    if not isinstance(trace, list):
        failures.append("trace/not-a-list")
        return []
    requests: dict[str, dict[str, Any]] = {}
    responses: dict[str, dict[str, Any]] = {}
    protocol_requests: dict[str, dict[str, Any]] = {}
    protocol_responses: dict[str, dict[str, Any]] = {}
    seen_timestamps: set[int] = set()
    for record in trace:
        if not isinstance(record, Mapping):
            failures.append("trace/non-object-record")
            continue
        timestamp = _nex_timestamp(record)
        if timestamp is None or timestamp in seen_timestamps:
            failures.append("trace/invalid-or-duplicate-timestamp")
            continue
        seen_timestamps.add(timestamp)
        direction = record.get("direction")
        message = record.get("message")
        if direction not in {
            "request", "response", "server_request", "client_response", "notification"
        } or not isinstance(message, Mapping):
            failures.append("trace/record-shape-invalid")
            continue
        record_id = record.get("jsonrpc_id")
        message_id = message.get("id")
        if _nex_id_key(record_id) != _nex_id_key(message_id):
            failures.append("trace/id-binding-invalid")
            continue
        # Keep server protocol traffic in the runner trace while excluding it
        # from the evaluated tool-call ledger. Pair request/response traffic
        # separately and accept valid notifications without ids.
        if direction == "notification":
            if record_id is not None or "method" not in message:
                failures.append("trace/notification-shape-invalid")
            continue
        if direction in {"server_request", "client_response"}:
            if record_id is None:
                failures.append("trace/server-protocol-id-missing")
                continue
            key = _nex_id_key(record_id)
            target = protocol_requests if direction == "server_request" else protocol_responses
            if key in target:
                failures.append("trace/duplicate-server-protocol-id")
                continue
            target[key] = dict(record)
            continue
        if record_id is None:
            if direction == "response":
                failures.append("trace/response-without-id")
            continue
        key = _nex_id_key(record_id)
        target = requests if direction == "request" else responses
        if key in target:
            failures.append("trace/duplicate-jsonrpc-id")
            continue
        target[key] = dict(record)

    calls: list[dict[str, Any]] = []
    for key, request in protocol_requests.items():
        response = protocol_responses.pop(key, None)
        if response is None:
            failures.append("trace/server-protocol-request-unanswered")
            continue
        if _nex_timestamp(response) <= _nex_timestamp(request):
            failures.append("trace/server-protocol-order-invalid")
    if protocol_responses:
        failures.append("trace/unmatched-client-protocol-response")
    for key, request in requests.items():
        response = responses.pop(key, None)
        if response is None:
            failures.append("trace/request-without-response")
            continue
        req_message = request["message"]
        resp_message = response["message"]
        req_time, resp_time = _nex_timestamp(request), _nex_timestamp(response)
        if req_time is None or resp_time is None or resp_time <= req_time:
            failures.append("trace/response-order-invalid")
            continue
        if response.get("direction") != "response":
            failures.append("trace/response-direction-invalid")
            continue
        operation = request.get("operation")
        workflow = request.get("workflow")
        root = request.get("root")
        if not isinstance(operation, str):
            operation = None
        if not isinstance(workflow, str):
            workflow = None
        if not isinstance(root, str):
            root = None
        for field in ("operation", "workflow"):
            before, after = request.get(field), response.get(field)
            if before is not None and after is not None and before != after:
                failures.append(f"trace/{field}-binding-invalid")
        response_root = response.get("root")
        if root is not None and response_root is not None and root != response_root:
            failures.append("trace/root-binding-invalid")
        params = req_message.get("params")
        arguments = params.get("arguments") if isinstance(params, Mapping) else None
        if not isinstance(arguments, Mapping):
            arguments = {}
        calls.append({
            "id": key,
            "jsonrpc_id": req_message.get("id"),
            "request": request,
            "response_record": response,
            "request_message": req_message,
            "response_message": resp_message,
            "operation": operation,
            "workflow": workflow or response.get("workflow"),
            "root": root or (response_root if isinstance(response_root, str) else None),
            "arguments": arguments,
            "request_ns": req_time,
            "response_ns": resp_time,
        })
    if responses:
        failures.append("trace/unmatched-response")
    calls.sort(key=lambda call: (call["request_ns"], call["response_ns"]))
    return calls


def _nex_profile_fields(text: str) -> dict[str, list[tuple[str | None, bool | None]]]:
    """Read flat api-source attributes without interpreting arbitrary YAML."""
    fields: dict[str, list[tuple[str | None, bool | None]]] = {}
    in_service = False
    service_indent = -1
    in_attributes = False
    current_key: str | None = None
    current_value: str | None = None
    current_public: bool | None = None

    def commit() -> None:
        nonlocal current_key, current_value, current_public
        if current_key is not None:
            fields.setdefault(current_key, []).append((current_value, current_public))
        current_key, current_value, current_public = None, None, None

    for line in text.splitlines():
        indent = len(line) - len(line.lstrip())
        service = re.match(r"^\s*-\s*name:\s*['\"]?api-source['\"]?\s*(?:#.*)?$", line)
        next_service = re.match(r"^\s*-\s*name:\s*", line)
        if service:
            commit()
            in_service = True
            service_indent = indent
            in_attributes = False
            continue
        if in_service and next_service and indent <= service_indent:
            commit()
            in_service = False
            in_attributes = False
        if not in_service:
            continue
        if re.match(r"^\s*attributes:\s*(?:#.*)?$", line):
            commit()
            in_attributes = True
            continue
        if not in_attributes:
            continue
        key_match = re.match(r"^\s*-\s*key:\s*([^#\s]+)\s*(?:#.*)?$", line)
        if key_match:
            commit()
            current_key = key_match.group(1).strip("'\"")
            continue
        value_match = re.match(r"^\s*value:\s*(.*?)\s*(?:#.*)?$", line)
        if value_match and current_key is not None:
            current_value = value_match.group(1).strip().strip("'\"")
            continue
        public_match = re.match(r"^\s*public:\s*(true|false)\s*(?:#.*)?$", line, re.I)
        if public_match and current_key is not None:
            current_public = public_match.group(1).lower() == "true"
    commit()
    return fields


def _nex_snapshot_files(snapshot: Mapping[str, Any], failures: list[str], label: str) -> tuple[str | None, dict[str, tuple[bytes, int | None]]]:
    root = snapshot.get("root")
    if not isinstance(root, str) or not root or not os.path.isabs(root):
        failures.append(f"snapshot/{label}-root-invalid")
        root = None
    files = snapshot.get("files")
    if not isinstance(files, Mapping):
        failures.append(f"snapshot/{label}-files-invalid")
        return root, {}
    normalized_root = os.path.normpath(root) if root else None
    result: dict[str, tuple[bytes, int | None]] = {}
    for canonical, entry in files.items():
        if not isinstance(canonical, str) or not os.path.isabs(canonical):
            failures.append(f"snapshot/{label}-path-invalid")
            continue
        canonical_norm = os.path.normpath(canonical)
        try:
            relative = os.path.relpath(canonical_norm, normalized_root) if normalized_root else ".."
        except (OSError, ValueError):
            relative = ".."
        if relative == ".." or relative.startswith(".." + os.sep):
            failures.append(f"snapshot/{label}-path-outside-root")
            continue
        mode: int | None = None
        content: Any = entry
        if isinstance(entry, Mapping):
            content = entry.get("content")
            raw_mode = entry.get("mode")
            if isinstance(raw_mode, int) and not isinstance(raw_mode, bool):
                mode = raw_mode
        if isinstance(content, str):
            data = content.encode("utf-8")
        elif isinstance(content, bytes):
            data = content
        else:
            failures.append(f"snapshot/{label}-content-invalid")
            continue
        relative = relative.replace(os.sep, "/")
        if relative in result:
            failures.append(f"snapshot/{label}-duplicate-relative-path")
            continue
        result[relative] = (data, mode)
    return normalized_root, result


def _nex_snapshot_hash_matches(snapshot: Mapping[str, Any]) -> bool:
    """Verify bytes are bound to the runner's JSON-RPC id and generation."""
    raw_files = snapshot.get("files")
    if not isinstance(raw_files, Mapping):
        return False
    manifest: list[dict[str, Any]] = []
    for path, entry in sorted(raw_files.items(), key=lambda item: str(item[0])):
        if not isinstance(path, str) or not isinstance(entry, Mapping):
            return False
        content = entry.get("content")
        mode = entry.get("mode", 0)
        if isinstance(content, str):
            content = content.encode("utf-8")
        if not isinstance(content, bytes) or not isinstance(mode, int) or isinstance(mode, bool):
            return False
        manifest.append({
            "path": os.path.normpath(path),
            "sha256": hashlib.sha256(content).hexdigest(),
            "mode": mode,
        })
    identifier = snapshot.get("jsonrpc_id", snapshot.get("capture_jsonrpc_id"))
    binding = {
        "jsonrpc_id": _nex_id_key(identifier),
        "workflow": snapshot.get("workflow"),
        "root": os.path.normpath(str(snapshot.get("root", ""))),
        "generation": snapshot.get("generation"),
        "expected_base_url": snapshot.get("expected_base_url"),
        "files": manifest,
    }
    try:
        encoded = json.dumps(
            binding, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    except (TypeError, ValueError):
        return False
    digest = hashlib.sha256(encoded).hexdigest()
    return snapshot.get("snapshot_sha256") == digest


def _nex_python_files(files: Mapping[str, tuple[bytes, int | None]], prefix: str = "transform/") -> dict[str, bytes]:
    return {
        path: data
        for path, (data, _mode) in files.items()
        if path.startswith(prefix) and not path.endswith("/")
    }


def _nex_non_message_constants(tree: ast.AST) -> list[str]:
    """String constants that are neither docstrings nor raise/assert messages."""
    excluded: set[int] = set()
    for parent in ast.walk(tree):
        body = getattr(parent, "body", None)
        if isinstance(body, list) and body and isinstance(body[0], ast.Expr):
            value = body[0].value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                excluded.add(id(value))
        message = parent.exc if isinstance(parent, ast.Raise) else parent.msg if isinstance(parent, ast.Assert) else None
        if message is not None:
            excluded.update(id(child) for child in ast.walk(message))
    return [
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in excluded
    ]


def _nex_hardcoded_endpoint_ast(transform_files: Mapping[str, bytes]) -> bool:
    """Whether a DLT REST transform carries a literal endpoint in its code.

    The case exists only to plant that literal, so any non-message string
    matching the fixture topology counts, however it reaches the connector
    (a name, a dict slot, a helper's return value).
    """
    pattern = r"(?:https?://|127\.0\.0\.1|/v1/orders)"
    rest_call = False
    literal = False
    for path, payload in transform_files.items():
        if not path.endswith(".py"):
            continue
        try:
            tree = ast.parse(payload.decode("utf-8", errors="replace"))
        except (SyntaxError, ValueError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = node.func
                name = fn.id if isinstance(fn, ast.Name) else fn.attr if isinstance(fn, ast.Attribute) else ""
                rest_call = rest_call or name in {"rest_api_resources", "rest_api_source"}
        literal = literal or any(re.search(pattern, value) for value in _nex_non_message_constants(tree))
    return rest_call and literal


def _nex_fstring_prefix(node: ast.AST, prefix: str) -> bool:
    """Whether ``node`` is an f-string whose literal head starts with ``prefix``."""
    return (
        isinstance(node, ast.JoinedStr) and bool(node.values)
        and isinstance(node.values[0], ast.Constant)
        and isinstance(node.values[0].value, str)
        and node.values[0].value.startswith(prefix)
    )


def _nex_transform_contract(files: Mapping[str, bytes]) -> bool:
    return not _nex_transform_contract_gaps(files)


def _nex_transform_contract_gaps(files: Mapping[str, bytes]) -> list[str]:
    """Name each unmet transform-contract condition (fixed labels, no content)."""
    if not files or not any(path.endswith(".py") for path in files):
        return ["no-python-transform"]
    found_rest_connector = False
    found_env_reference = False
    found_profile_header = False
    found_endpoint_attribute = False
    mentions_old_companion = False
    forbidden_http_import = False
    hardcoded_topology = False
    topology_kinds: set[str] = set()
    for path, payload in files.items():
        if not path.endswith(".py"):
            continue
        source = payload.decode("utf-8", errors="replace")
        mentions_old_companion = mentions_old_companion or "api-source-endpoints" in source
        try:
            tree = ast.parse(source)
        except (SyntaxError, ValueError):
            return ["unparseable"]
        docstrings: set[int] = set()
        for parent in ast.walk(tree):
            body = getattr(parent, "body", None)
            if isinstance(body, list) and body and isinstance(body[0], ast.Expr):
                value = body[0].value
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    docstrings.add(id(value))
        # Diagnostic text is not topology: strings inside a raised exception or
        # an assert message never reach the connector.
        for parent in ast.walk(tree):
            message = parent.exc if isinstance(parent, ast.Raise) else parent.msg if isinstance(parent, ast.Assert) else None
            if message is not None:
                docstrings.update(id(child) for child in ast.walk(message))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                if any(alias.name.split(".", 1)[0] in {"requests", "urllib", "httpx"} for alias in node.names):
                    forbidden_http_import = True
            elif isinstance(node, ast.ImportFrom) and (node.module or "").split(".", 1)[0] in {"requests", "urllib", "httpx"}:
                forbidden_http_import = True
            if isinstance(node, ast.Call):
                fn = node.func
                name = fn.id if isinstance(fn, ast.Name) else fn.attr if isinstance(fn, ast.Attribute) else ""
                if name in {"rest_api_resources", "rest_api_source"}:
                    found_rest_connector = True
                if name in {"get", "urlopen", "urlretrieve", "request", "Session"} and isinstance(fn, ast.Attribute):
                    owner = fn.value
                    if isinstance(owner, ast.Name) and owner.id in {"requests", "httpx", "urllib"}:
                        forbidden_http_import = True
            if isinstance(node, ast.Subscript):
                outer = node.value
                sl = node.slice
                if (
                    isinstance(outer, ast.Attribute)
                    and isinstance(outer.value, ast.Name) and outer.value.id == "os"
                    and outer.attr == "environ"
                    and isinstance(sl, ast.Subscript)
                    and isinstance(sl.value, ast.Name) and sl.value.id == "secrets"
                    and isinstance(sl.slice, ast.Constant) and sl.slice.value == "credential_env"
                ):
                    found_env_reference = True
                if (
                    isinstance(outer, ast.Name) and outer.id == "secrets"
                    and isinstance(sl, ast.Constant) and sl.value == "header_user_agent"
                ):
                    found_profile_header = True
                if (
                    isinstance(outer, ast.Name) and outer.id == "secrets"
                    and (
                        isinstance(sl, ast.Constant) and sl.value == "endpoint_orders"
                        or _nex_fstring_prefix(sl, "endpoint_")
                    )
                ):
                    found_endpoint_attribute = True
            # The skill's template builds headers by looping over every
            # ``header_*`` profile attribute instead of naming each one.
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute) and node.func.attr == "startswith"
                and any(isinstance(arg, ast.Constant) and arg.value == "header_" for arg in node.args)
            ):
                found_profile_header = True
            # Topology means a concrete host or the fixture path; a bare scheme
            # prefix in a "must be a path" guard is not an endpoint.
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
                for kind, pattern in (
                    ("url-host", r"https?://[A-Za-z0-9\[]"),
                    ("loopback", r"127\.0\.0\.1|localhost"),
                    ("fixture-path", r"/v1/orders"),
                ):
                    if re.search(pattern, node.value):
                        hardcoded_topology = True
                        topology_kinds.add(kind)
    gaps = [
        label for label, missing in (
            ("rest-connector-missing", not found_rest_connector),
            ("credential-env-reference-missing", not found_env_reference),
            ("profile-header-missing", not found_profile_header),
            ("endpoint-attribute-missing", not found_endpoint_attribute),
            ("old-companion-reference", mentions_old_companion),
            ("direct-http-client", forbidden_http_import),
            ("hard-coded-topology", hardcoded_topology),
        )
        if missing
    ]
    gaps.extend(f"hard-coded-topology-{kind}" for kind in sorted(topology_kinds))
    return gaps


def _nex_direct_diagnostics(message: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Extract only workflow-operation diagnostics from their typed fields."""
    structured = _nex_structured_content(message)
    operation = structured.get("operation")
    if isinstance(operation, Mapping):
        diagnostic = operation.get("diagnostic")
        if isinstance(diagnostic, Mapping):
            return [diagnostic]
    operations = structured.get("operations")
    if isinstance(operations, list):
        return [
            operation["diagnostic"]
            for operation in operations
            if isinstance(operation, Mapping)
            and isinstance(operation.get("diagnostic"), Mapping)
        ]
    return []


def _nex_accepted(call: Mapping[str, Any]) -> bool:
    """Whether the supervisor accepted a call; unrecorded responses count."""
    response = call.get("response_message")
    return not isinstance(response, Mapping) or _nex_response_ok(response)


def _nex_current_generation_calls(calls: list[dict[str, Any]], workflow: str) -> list[dict[str, Any]]:
    """Calls after the workflow's last successful ``reset_workflow``.

    A reset discards the prior prepare, consent, capture and review, so only
    the lifecycle that follows it is the workflow's evidence. The job-loop
    skill prescribes a reset after any post-consent blueprint edit.
    """
    start = 0
    for index, call in enumerate(calls):
        if (
            call.get("workflow") == workflow
            and call.get("operation") == "reset_workflow"
            and _nex_response_ok(call.get("response_message") or {})
        ):
            start = index + 1
    return calls[start:]


def _nex_case_action_calls(calls: list[dict[str, Any]], workflow: str, action_type: str) -> list[dict[str, Any]]:
    # The logical consent stage is recorded by workflow-v2 as a
    # subject-bound session_decision action.
    action_type = "session_decision" if action_type == "consent" else action_type
    calls = _nex_current_generation_calls(calls, workflow)
    if action_type == "validate":
        return [
            call for call in calls
            if call.get("workflow") == workflow
            and call.get("operation") == "advance_workflow"
            and _nex_action(call)[0] == "start_requirement"
            and _nex_action_requirement_id(call) == "validation"
        ]
    if action_type == "report_requirement":
        return [
            call for call in calls
            if call.get("workflow") == workflow
            and call.get("operation") == "advance_workflow"
            and _nex_action(call)[0] == "report_requirement"
            and _nex_action_requirement_id(call) == "review"
            and _nex_accepted(call)
        ]
    # A consent or capture the supervisor rejected (a JSON-RPC refusal or a
    # tool-level error) changed nothing; only the accepted one counts.
    return [
        call for call in calls
        if call.get("workflow") == workflow
        and call.get("operation") == "advance_workflow"
        and _nex_action(call)[0] == action_type
        and _nex_accepted(call)
    ]


def _nex_validation_cardinality_failure(workflow: str, calls: list[dict[str, Any]]) -> str | None:
    if not calls:
        return f"cycle/{workflow}/validation-missing"
    if len(calls) > 1:
        return f"cycle/{workflow}/validation-duplicate"
    return None


def _nex_report_verdict(call: Mapping[str, Any]) -> str | None:
    _action_type, parameters = _nex_action(call)
    report = parameters.get("report")
    if not isinstance(report, Mapping):
        return None
    verdict = report.get("verdict")
    return verdict if isinstance(verdict, str) and verdict in _NEX_REVIEW_VERDICTS else None


def _nex_report_finding_labels(call: Mapping[str, Any]) -> list[str]:
    _action_type, parameters = _nex_action(call)
    report = parameters.get("report")
    findings = report.get("findings") if isinstance(report, Mapping) else None
    if not isinstance(findings, list):
        return []
    labels: set[str] = set()
    for finding in findings:
        if not isinstance(finding, Mapping):
            continue
        finding_id = finding.get("id")
        severity = finding.get("severity")
        # Keep the severity even when the id is not a safe slug: it is what
        # separates a blocking claim from an owner who misreported an advisory.
        severity_label = (
            severity if isinstance(severity, str) and severity in {"blocking", "advisory"}
            else "severity-unavailable"
        )
        if (
            isinstance(finding_id, str)
            and re.fullmatch(r"[a-z][a-z0-9]*(?:[-_][a-z0-9]+){0,9}", finding_id)
            and severity_label != "severity-unavailable"
        ):
            labels.add(f"{finding_id.replace('_', '-')}-{severity}")
        else:
            labels.add(f"finding-id-unavailable-{severity_label}")
    return sorted(labels)[:8]


def _nex_report_rejection_code(call: Mapping[str, Any]) -> str | None:
    _action_type, parameters = _nex_action(call)
    report = parameters.get("report")
    if not isinstance(report, Mapping):
        return None
    code = report.get("rejection_code")
    return code if code == "scope_refused" else None


def _nex_validation_action_returned(message: Mapping[str, Any]) -> bool:
    actions = _nex_structured_content(message).get("next_actions")
    if not isinstance(actions, list):
        return False
    for action in actions:
        # The supervisor serialises each next action flat, keyed by "action".
        if not isinstance(action, Mapping) or action.get("action", action.get("type")) != "start_requirement":
            continue
        parameters = action.get("parameters")
        if isinstance(parameters, Mapping) and parameters.get("requirement_id") == "validation":
            return True
        if action.get("requirement_id") == "validation":
            return True
    return False


def _nex_evidence_call_rpc_error(
    call: Mapping[str, Any], validated_calls: Mapping[str, Mapping[str, Any]]
) -> bool:
    """Whether an evidence-bearing call was answered with a JSON-RPC error.

    Only the static preflight cases and each cycle's matched validation must
    answer with a tool result. Other workflow calls may be refused with a
    JSON-RPC error (stale revision, invalid request) and recovered from
    without invalidating the cycle.
    """
    workflow = call.get("workflow")
    if workflow != "__static__" and call is not validated_calls.get(str(workflow)):
        return False
    error = call["response_message"].get("error")
    return isinstance(error, Mapping) and isinstance(error.get("code"), int)


def _nex_action_requirement_id(call: Mapping[str, Any]) -> Any:
    arguments = call.get("arguments")
    action = arguments.get("action") if isinstance(arguments, Mapping) else None
    if not isinstance(action, Mapping):
        return None
    parameters = action.get("parameters")
    if isinstance(parameters, Mapping) and "requirement_id" in parameters:
        nested = parameters.get("requirement_id")
        if "requirement_id" in action and action.get("requirement_id") != nested:
            return None
        return nested
    return action.get("requirement_id")


def _nex_observation_header(observation: Mapping[str, Any]) -> tuple[str | None, bool]:
    agent = observation.get("user_agent")
    headers = observation.get("headers")
    if isinstance(headers, Mapping):
        if any(str(key).lower() == "authorization" for key in headers):
            return agent if isinstance(agent, str) else None, True
        if agent is None:
            agent = next((value for key, value in headers.items() if str(key).lower() == "user-agent"), None)
    return (agent if isinstance(agent, str) else None), False


def _nex_observation_path(observation: Mapping[str, Any]) -> str | None:
    value = observation.get("path")
    if not isinstance(value, str):
        return None
    return value.split("?", 1)[0]


def check_nex890(
    trace: Any,
    frozen_stub_observations: Any,
    file_snapshots: Any,
    redaction_markers: Any,
) -> dict[str, Any]:
    """Grade Claude NEX-890 using only runner-frozen in-memory evidence.

    ``file_snapshots`` is a mapping keyed by expected workflow/case label. Each
    workflow snapshot envelope must contain ``jsonrpc_id`` (or
    ``capture_jsonrpc_id``), ``workflow``, exact ``root``, ``generation``, and
    ``files``. ``files`` maps canonical absolute paths to bytes/text or to
    ``{"content": bytes|str, "mode": int}``. Optional ``outputs`` may hold
    runner-frozen post-run artifact bytes. The key and any HTTP ``X-Eval-Case``
    value are hints only; capture ID, workflow, root, interval, and timestamp
    checks establish provenance.

    The return value is JSON-serializable and intentionally contains no input
    values: ``passed``, stable failure codes, and per-contract booleans.
    """
    failures: list[str] = []
    checks: list[dict[str, Any]] = []

    def mark(code: str, passed: bool) -> None:
        checks.append({"id": code, "passed": bool(passed)})
        if not passed:
            failures.append(code)

    calls = _nex_pair_trace(trace, failures)
    snapshots = file_snapshots if isinstance(file_snapshots, Mapping) else {}
    if not isinstance(file_snapshots, Mapping):
        failures.append("snapshot/not-a-mapping")

    marker_list = redaction_markers if isinstance(redaction_markers, (list, tuple)) else []
    markers = [item.encode("utf-8") for item in marker_list if isinstance(item, str) and item]
    if len(markers) != len(marker_list) or not markers or any(len(item) < 8 for item in markers):
        failures.append("redaction/markers-invalid")
    try:
        trace_bytes = json.dumps(trace, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    except (TypeError, ValueError):
        trace_bytes = b""
        failures.append("trace/not-serializable")
    if any(marker in trace_bytes for marker in markers):
        failures.append("redaction/marker-in-trace")

    workflow_calls: dict[str, list[dict[str, Any]]] = {name: [] for name in _NEX_CASES}
    static_call_ids: set[str] = set()
    workflow_operations = {
        "check_data_product", "prepare_workflow", "advance_workflow",
        "get_workflow_capabilities",
        "inspect_workflow", "inspect_run", "list_data_products",
        "resume_data_product", "describe_models", "run_semantic_query",
        "export_data_product", "read_review_input", "reset_workflow",
    }
    for call in calls:
        workflow = call.get("workflow")
        operation = call.get("operation")
        if isinstance(workflow, str):
            if workflow not in workflow_calls:
                if workflow == "__static__" and operation in {"check_data_product", "prepare_workflow"}:
                    static_call_ids.add(call["id"])
                else:
                    failures.append("trace/extra-workflow")
            else:
                workflow_calls[workflow].append(call)
                if operation not in workflow_operations:
                    failures.append("trace/extra-workflow-operation")
        elif operation in workflow_operations and operation not in {
            "get_workflow_capabilities", "list_data_products",
        }:
            failures.append("trace/workflow-missing")
            failures.append(f"trace/workflow-missing/{operation}")
    # Evidence comes only from each workflow's current generation: a successful
    # reset_workflow discards what came before it. Trace hygiene above still
    # covers every call.
    current_calls: dict[str, list[dict[str, Any]]] = {
        name: [
            call for call in _nex_current_generation_calls(calls, name)
            if call.get("workflow") == name
        ]
        for name in _NEX_CASES
    }

    case_intervals: dict[str, tuple[int, int, str]] = {}
    capture_calls: dict[str, dict[str, Any]] = {}
    validated_calls: dict[str, dict[str, Any]] = {}
    positive_query_calls = [
        call for call in current_calls.get("nex890-positive", [])
        if call.get("operation") == "run_semantic_query"
    ]
    paid_query_call = None
    if len(positive_query_calls) == 1:
        candidate = positive_query_calls[0]
        filters = candidate.get("arguments", {}).get("filters")
        if isinstance(filters, list) and any(
            isinstance(item, Mapping)
            and item.get("dimension") == "status"
            and item.get("op") == "="
            and item.get("value") == "paid"
            for item in filters
        ):
            paid_query_call = candidate
    positive_start_run_calls = [
        call for call in current_calls.get("nex890-positive", [])
        if call.get("operation") == "advance_workflow"
        and _nex_action(call)[0] == "start_run"
    ]
    review_reader_ids: set[str] = set()
    workflow_roots: dict[str, str] = {}
    bound_snapshots: dict[str, tuple[
        str,
        dict[str, tuple[bytes, int | None]],
        dict[str, tuple[bytes, int | None]],
        Mapping[str, Any],
    ]] = {}

    for workflow in _NEX_CASES:
        scoped = current_calls[workflow]
        actions = {
            action: _nex_case_action_calls(calls, workflow, action)
            for action in ("consent", "capture", "report_requirement", "validate")
        }
        for action, found in actions.items():
            mark(f"cycle/{workflow}/{action}-unique", len(found) == 1)
        validation_cardinality_failure = _nex_validation_cardinality_failure(
            workflow, actions["validate"]
        )
        if validation_cardinality_failure is not None:
            failures.append(validation_cardinality_failure)
        if len(actions["report_requirement"]) == 1:
            report_call = actions["report_requirement"][0]
            report_verdict = _nex_report_verdict(report_call)
            if report_verdict is None:
                failures.append(f"review/{workflow}/report-verdict-invalid")
            elif report_verdict != "clear":
                failures.append(f"review/{workflow}/report-verdict-{report_verdict}")
                finding_labels = _nex_report_finding_labels(report_call)
                failures.extend(
                    f"review/{workflow}/finding-{label}" for label in finding_labels
                )
                rejection_code = _nex_report_rejection_code(report_call)
                if rejection_code == "scope_refused":
                    failures.append(f"review/{workflow}/rejection-{rejection_code}")
            mark(
                f"review/{workflow}/validation-action-returned",
                _nex_validation_action_returned(report_call["response_message"]),
            )
        consent, capture, report, validation = (actions["consent"], actions["capture"], actions["report_requirement"], actions["validate"])
        if len(capture) != 1 or len(validation) != 1 or len(report) != 1 or len(consent) != 1:
            continue
        capture, validation, report, consent = capture[0], validation[0], report[0], consent[0]
        capture_calls[workflow] = capture
        validated_calls[workflow] = validation
        consent_type, _ = _nex_action(consent)
        cap_type, cap_params = _nex_action(capture)
        report_type, _ = _nex_action(report)
        valid_type, _ = _nex_action(validation)
        mark(f"cycle/{workflow}/action-order", consent["request_ns"] < capture["request_ns"] < report["request_ns"] < validation["request_ns"])
        mark(f"cycle/{workflow}/action-types", (consent_type, cap_type, report_type, valid_type) == ("session_decision", "capture", "report_requirement", "start_requirement"))

        args = capture.get("arguments", {})
        authoring_root = cap_params.get("authoring_root")
        if not isinstance(authoring_root, str):
            authoring_root = args.get("authoring_root") if isinstance(args, Mapping) else None
        if not isinstance(authoring_root, str) or not os.path.isabs(authoring_root):
            failures.append(f"cycle/{workflow}/authoring-root-invalid")
            continue
        authoring_root_norm = os.path.normpath(authoring_root)
        workflow_roots[workflow] = authoring_root_norm
        for call in scoped:
            if (
                call["request"].get("workflow") != workflow
                or call["response_record"].get("workflow") != workflow
            ):
                failures.append(f"trace/{workflow}/workflow-binding-invalid")
            call_root = call.get("root")
            # A rejected call changed nothing, so only accepted calls bind a root.
            if (
                _nex_accepted(call)
                and isinstance(call_root, str)
                and os.path.normpath(call_root) != authoring_root_norm
            ):
                failures.append(f"trace/{workflow}/root-mismatch")
                failures.append(f"trace/{workflow}/root-mismatch/{call.get('operation')}")
        response_record = capture["response_record"]
        if not isinstance(response_record.get("root"), str) or os.path.normpath(response_record["root"]) != authoring_root_norm:
            failures.append(f"capture/{workflow}/response-root-mismatch")
        capture_result = _nex_structured_content(capture["response_message"])
        review_requirement = _nex_requirement(capture_result, "review")
        review_input = review_requirement.get("review_input")
        generation = review_requirement.get("generation")
        mark(f"capture/{workflow}/successful", _nex_response_ok(capture["response_message"]) and isinstance(review_input, Mapping))
        mark(f"capture/{workflow}/generation-bound", isinstance(generation, (str, int)) and not isinstance(generation, bool))

        # The foreground review reader is synthetic and must succeed strictly
        # between the matched capture and report calls.
        reads = [
            call for call in calls
            if call.get("operation") == "read_review_input"
            and call.get("request_ns", 0) > capture["response_ns"]
            and call.get("response_ns", 0) < report["request_ns"]
        ]
        for call in reads:
            if call.get("workflow") not in {None, workflow}:
                failures.append(f"review/{workflow}/workflow-binding-invalid")
            if isinstance(call.get("root"), str) and os.path.normpath(call["root"]) != authoring_root_norm:
                failures.append(f"review/{workflow}/root-binding-invalid")
            review_reader_ids.add(call["id"])
        valid_reads = [
            call for call in reads
            if capture["response_ns"] < call["request_ns"] < call["response_ns"] < report["request_ns"]
            and call["request"].get("synthetic") is False
            and call["response_record"].get("synthetic") is True
            and _nex_response_ok(call["response_message"])
        ]
        mark(f"review/{workflow}/reader-before-report", bool(valid_reads) and len(valid_reads) == len(reads))
        mark(f"review/{workflow}/report-success", _nex_response_ok(report["response_message"]))
        mark(f"validation/{workflow}/after-review", report["response_ns"] < validation["request_ns"])
        mark(f"validation/{workflow}/response", _nex_response_ok(validation["response_message"]))
        start_run_calls = [
            call for call in scoped
            if call.get("operation") == "advance_workflow"
            and _nex_action(call)[0] == "start_run"
        ]
        mark(
            f"publication/{workflow}/start-run-policy",
            len(start_run_calls) == (1 if workflow == "nex890-positive" else 0)
            and all(_nex_response_ok(call["response_message"]) for call in start_run_calls),
        )
        # The validation handler executes the pinned DLT transform in a scratch
        # kernel. Positive publication executes that same transform once more
        # through the unique StartRun request. Semantic queries read the
        # published local artifact and must not own source HTTP observations.
        # Each source request is attributed only to one of those exact
        # request-to-response windows; 4xx cases remain validation-only.
        interval_start = validation["request_ns"]
        interval_end = validation["response_ns"]
        case_intervals[workflow] = (interval_start, interval_end, authoring_root_norm)
        if workflow == "nex890-positive" and len(start_run_calls) == 1:
            start_run = start_run_calls[0]
            mark(
                "publication/positive/start-run-after-validation",
                validation["response_ns"] < start_run["request_ns"] < start_run["response_ns"],
            )
            if paid_query_call is not None:
                mark(
                    "query/paid-call-after-publication",
                    start_run["response_ns"] < paid_query_call["request_ns"] < paid_query_call["response_ns"],
                )

        envelope = snapshots.get(workflow)
        if not isinstance(envelope, Mapping):
            failures.append(f"snapshot/{workflow}/missing")
            continue
        envelope_id = envelope.get("jsonrpc_id", envelope.get("capture_jsonrpc_id"))
        envelope_workflow = envelope.get("workflow")
        envelope_root = envelope.get("root")
        snapshot_generation = envelope.get("generation")
        capture_id = capture.get("jsonrpc_id")
        bound = (
            _nex_id_key(envelope_id) == _nex_id_key(capture_id)
            and envelope_workflow == workflow
            and isinstance(envelope_root, str)
            and os.path.normpath(envelope_root) == authoring_root_norm
            and snapshot_generation == generation
        )
        mark(f"snapshot/{workflow}/capture-bound", bound)
        mark(f"snapshot/{workflow}/capture-hash-bound", _nex_snapshot_hash_matches(envelope))
        root, files = _nex_snapshot_files(envelope, failures, workflow)
        if root != authoring_root_norm:
            failures.append(f"snapshot/{workflow}/root-mismatch")
        validation_envelope = envelope.get("validation")
        validation_files: dict[str, tuple[bytes, int | None]] = {}
        if not isinstance(validation_envelope, Mapping):
            failures.append(f"snapshot/{workflow}/validation-missing")
        else:
            validation_binding = (
                _nex_id_key(validation_envelope.get("jsonrpc_id", validation_envelope.get("capture_jsonrpc_id")))
                == _nex_id_key(validation.get("jsonrpc_id"))
                and validation_envelope.get("workflow") == workflow
                and isinstance(validation_envelope.get("root"), str)
                and os.path.normpath(validation_envelope.get("root")) == authoring_root_norm
                and validation_envelope.get("generation") == generation
            )
            mark(f"snapshot/{workflow}/validation-bound", validation_binding)
            mark(
                f"snapshot/{workflow}/validation-hash-bound",
                _nex_snapshot_hash_matches(validation_envelope),
            )
            validation_root, validation_files = _nex_snapshot_files(
                validation_envelope, failures, f"{workflow}-validation"
            )
            if validation_root != authoring_root_norm:
                failures.append(f"snapshot/{workflow}/validation-root-mismatch")
            same_reviewed_files = all(
                files.get(path) == validation_files.get(path)
                for path in files
                if path == "infra-profile.yaml" or path.startswith("transform/")
            ) and all(
                validation_files.get(path) == files.get(path)
                for path in validation_files
                if path == "infra-profile.yaml" or path.startswith("transform/")
            )
            mark(f"snapshot/{workflow}/reviewed-files-unchanged", same_reviewed_files)
        bound_snapshots[workflow] = (root or "", files, validation_files, envelope)

    mark("cycle/exact-four-workflows", set(workflow_calls) == set(_NEX_CASES) and all(workflow_calls.values()))
    all_review_reader_ids = {
        call["id"] for call in calls if call.get("operation") == "read_review_input"
    }
    mark("review/no-reader-outside-capture", all_review_reader_ids == review_reader_ids)
    roots_are_distinct = len(workflow_roots) == 4 and len(set(workflow_roots.values())) == 4
    mark("cycle/distinct-authoring-roots", roots_are_distinct)
    ordered_intervals = sorted(
        (start, end, name) for name, (start, end, _root) in case_intervals.items()
    )
    no_overlap = len(ordered_intervals) == 4 and all(
        ordered_intervals[index][1] <= ordered_intervals[index + 1][0]
        for index in range(len(ordered_intervals) - 1)
    )
    mark("cycle/no-overlap", no_overlap)

    # Bind immutable profiles and transform bytes to the capture which
    # produced them. The workflow label selects a candidate envelope only;
    # its capture identity and exact root above are the provenance checks.
    profile_entries: dict[str, dict[str, list[tuple[str | None, bool | None]]]] = {}
    transform_maps: dict[str, dict[str, bytes]] = {}
    snapshot_leak = False
    for workflow, (_root, files, validation_files, envelope) in bound_snapshots.items():
        profile = files.get("infra-profile.yaml")
        if profile is None:
            failures.append(f"profile/{workflow}/missing")
            continue
        try:
            profile_text = profile[0].decode("utf-8")
        except UnicodeDecodeError:
            failures.append(f"profile/{workflow}/invalid-utf8")
            continue
        profile_entries[workflow] = _nex_profile_fields(profile_text)
        transform_maps[workflow] = _nex_python_files(files)
        if any(marker in data for marker in markers for data, _mode in files.values()):
            snapshot_leak = True
        if any(marker in data for marker in markers for data, _mode in validation_files.values()):
            snapshot_leak = True
        if "api-source-endpoints" in files or any(
            path.rsplit("/", 1)[-1] == "api-source-endpoints" for path in files
        ):
            failures.append(f"closure/{workflow}/endpoint-companion-present")
        manifest = files.get("companion-files")
        if manifest is not None and b"api-source-endpoints" in manifest[0]:
            failures.append(f"closure/{workflow}/endpoint-companion-declared")
    mark("redaction/no-marker-in-captured-files", not snapshot_leak)

    def single_field(fields: Mapping[str, list[tuple[str | None, bool | None]]], key: str) -> tuple[str | None, bool | None] | None:
        values = fields.get(key, [])
        return values[0] if len(values) == 1 else None

    positive = profile_entries.get("nex890-positive", {})
    positive_endpoint = single_field(positive, "endpoint_orders")
    positive_base_url = single_field(positive, "base_url")
    positive_agent = single_field(positive, "header_user_agent")
    positive_credential = single_field(positive, "credential_env")
    positive_auth = single_field(positive, "auth_type")
    expected_base_urls = {
        envelope.get("expected_base_url")
        for _root, _files, _validation_files, envelope in bound_snapshots.values()
        if isinstance(envelope, Mapping)
    }
    expected_base_url = (
        next(iter(expected_base_urls))
        if len(expected_base_urls) == 1 and isinstance(next(iter(expected_base_urls)), str)
        else None
    )
    profile_positive_ok = (
        positive_endpoint == (_NEX_ENDPOINT, True)
        and positive_base_url == (expected_base_url, True)
        and expected_base_url is not None
        and positive_agent == (_NEX_USER_AGENT, True)
        and positive_credential is not None
        and positive_credential[0] == _NEX_SECRET_ENV
        and positive_credential[1] is True
        and positive_auth is not None
        and positive_auth[0] == "bearer"
        and positive_auth[1] is True
    )
    endpoint_keys = {key for key in positive if key.startswith("endpoint_")}
    profile_positive_ok = profile_positive_ok and endpoint_keys == {"endpoint_orders"}
    mark("profile/positive-contract", profile_positive_ok)
    for workflow, changed_key in (
        ("nex890-401", "auth_type"),
        ("nex890-403", "header_user_agent"),
        ("nex890-404", "endpoint_orders"),
    ):
        fields = profile_entries.get(workflow, {})
        variant_ok = bool(fields)
        all_keys = set(fields) | set(positive)
        for key in all_keys:
            if key == changed_key:
                continue
            if fields.get(key, []) != positive.get(key, []):
                variant_ok = False
        changed = single_field(fields, changed_key)
        if workflow == "nex890-401":
            variant_ok = variant_ok and changed is None
        elif workflow == "nex890-403":
            variant_ok = variant_ok and changed is not None and changed[0] != _NEX_USER_AGENT and changed[1] is True
        else:
            variant_ok = variant_ok and changed is not None and changed[0] != _NEX_ENDPOINT and changed[1] is True
        credential = single_field(fields, "credential_env")
        variant_ok = variant_ok and credential == (_NEX_SECRET_ENV, True)
        variant_base_url = single_field(fields, "base_url")
        variant_ok = variant_ok and variant_base_url == (expected_base_url, True)
        mark(f"profile/{workflow}/single-public-variant", variant_ok)

    transform_identity = bool(transform_maps) and len(transform_maps) == 4
    positive_transform = transform_maps.get("nex890-positive", {})
    for workflow in _NEX_CASES:
        if transform_maps.get(workflow) != positive_transform:
            transform_identity = False
    mark("transform/byte-identical-across-workflows", transform_identity)
    transform_gaps = _nex_transform_contract_gaps(positive_transform)
    mark("transform/dlt-profile-credential-contract", not transform_gaps)
    failures.extend(f"transform/dlt-profile-credential-contract/{gap}" for gap in transform_gaps)

    # Static profile variants and the static AST-rejection case are bound to
    # their exact runner-frozen preflight request and root. The root's basename
    # or canonical .eval-cases path identifies the case; the array position and
    # any label do not.
    static_entries: list[tuple[str, str, Mapping[str, Any], dict[str, tuple[bytes, int | None]]]] = []
    static_workspace_root = None
    if workflow_roots:
        try:
            static_workspace_root = os.path.commonpath(list(workflow_roots.values()))
        except ValueError:
            static_workspace_root = None
    for parent_workflow, (_root, _files, _validation_files, parent_envelope) in bound_snapshots.items():
        raw_static = parent_envelope.get("static", [])
        if not isinstance(raw_static, list):
            failures.append(f"snapshot/{parent_workflow}/static-invalid")
            continue
        for static_envelope in raw_static:
            if not isinstance(static_envelope, Mapping):
                failures.append(f"snapshot/{parent_workflow}/static-entry-invalid")
                continue
            static_root, static_files = _nex_snapshot_files(
                static_envelope, failures, f"{parent_workflow}-static"
            )
            if static_root is None:
                continue
            case_name = os.path.basename(static_root)
            if case_name not in {"malformed-endpoint-profile", "omitted-endpoint-profile", "hard-coded-endpoint"}:
                paths = tuple(static_files)
                candidates = (
                    "malformed-endpoint-profile", "omitted-endpoint-profile", "hard-coded-endpoint"
                )
                case_name = next((candidate for candidate in candidates if any(
                    path.startswith(f".eval-cases/{candidate}/") for path in paths
                )), "")
                if case_name:
                    prefix = f".eval-cases/{case_name}/"
                    static_files = {
                        path[len(prefix):]: item
                        for path, item in static_files.items()
                        if path.startswith(prefix)
                    }
            if not case_name:
                failures.append("static/unrecognized-case-root")
                continue
            static_workflow = static_envelope.get("workflow")
            static_id = static_envelope.get("jsonrpc_id", static_envelope.get("capture_jsonrpc_id"))
            matching_preflights = [
                call for call in calls
                if _nex_id_key(call.get("jsonrpc_id")) == _nex_id_key(static_id)
                and call.get("workflow") == static_workflow == "__static__"
                and call.get("operation") in {"check_data_product", "prepare_workflow"}
            ]
            preflight_root_matches = False
            for preflight in matching_preflights:
                preflight_args = preflight.get("arguments", {})
                candidates = [
                    preflight_args.get(name)
                    for name in ("root", "definition", "authoring_root")
                    if isinstance(preflight_args, Mapping)
                ]
                _action_kind, preflight_params = _nex_action(preflight)
                candidates.extend(
                    preflight_params.get(name)
                    for name in ("root", "definition", "authoring_root")
                    if isinstance(preflight_params.get(name), str)
                )
                if any(isinstance(value, str) and os.path.normpath(value) == static_root for value in candidates):
                    preflight_root_matches = True
            static_root_bound = (
                bool(matching_preflights)
                and preflight_root_matches
                and static_workflow == "__static__"
                and isinstance(static_envelope.get("root"), str)
                and os.path.normpath(static_envelope.get("root")) == static_root
                and static_workspace_root is not None
                and (static_root == static_workspace_root or static_root.startswith(static_workspace_root.rstrip(os.sep) + os.sep))
            )
            if not static_root_bound:
                failures.append(f"static/{case_name}/preflight-binding-invalid")
            if not _nex_snapshot_hash_matches(static_envelope):
                failures.append(f"static/{case_name}/snapshot-hash-invalid")
            if len(matching_preflights) != 1:
                failures.append(f"static/{case_name}/preflight-request-not-unique")
            else:
                preflight = matching_preflights[0]
                first_capture_request = min(
                    (call["request_ns"] for call in capture_calls.values()),
                    default=0,
                )
                if first_capture_request and preflight["request_ns"] >= first_capture_request:
                    failures.append(f"static/{case_name}/preflight-outside-static-window")
                preflight_result = _nex_structured_content(preflight["response_message"])
                generation = preflight_result.get("generation")
                if generation is None:
                    generation = preflight.get("arguments", {}).get("generation")
                snapshot_generation = static_envelope.get("generation")
                generation_binding_ok = (
                    generation is None and snapshot_generation is None
                    or generation == snapshot_generation
                )
                # NXD's self-check has no endpoint-profile rule, so a malformed
                # or omitted endpoint profile need not fail preflight; the
                # runner's static profile contract below is the authority.
                if not generation_binding_ok:
                    failures.append(f"static/{case_name}/generation-binding-invalid")
            if case_name == "hard-coded-endpoint" and any(
                call.get("operation") in {"advance_workflow", "read_review_input"}
                and call.get("root") is not None
                and os.path.normpath(call["root"]) == static_root
                for call in calls
            ):
                failures.append("static/hard-coded-endpoint/workflow-or-review-present")
            static_entries.append((case_name, parent_workflow, static_envelope, static_files))

    static_names = [name for name, _workflow, _envelope, _files in static_entries]
    if set(static_names) != {"malformed-endpoint-profile", "omitted-endpoint-profile", "hard-coded-endpoint"}:
        failures.append("static/approved-case-set-incomplete-or-extra")
    if len(static_names) != len(set(static_names)):
        failures.append("static/duplicate-case-snapshot")
    matched_static_ids = {
        _nex_id_key(envelope.get("jsonrpc_id", envelope.get("capture_jsonrpc_id")))
        for _name, _workflow, envelope, _files in static_entries
    }
    if len(static_call_ids) != 3 or static_call_ids != matched_static_ids:
        failures.append("static/trace-request-set-incomplete-or-extra")

    malformed_profiles = [(f"static-{i}", files) for i, (name, _wf, _env, files) in enumerate(static_entries) if name == "malformed-endpoint-profile"]
    omitted_profiles = [(f"static-{i}", files) for i, (name, _wf, _env, files) in enumerate(static_entries) if name == "omitted-endpoint-profile"]
    static_expected_base_urls = {
        envelope.get("expected_base_url")
        for _name, _workflow, envelope, _files in static_entries
        if isinstance(envelope, Mapping)
    }
    static_expected_base_url = (
        next(iter(static_expected_base_urls))
        if len(static_expected_base_urls) == 1
        and isinstance(next(iter(static_expected_base_urls)), str)
        else None
    )

    def valid_static_profile(files: Mapping[str, tuple[bytes, int | None]]) -> bool:
        profile = files.get("infra-profile.yaml")
        if profile is None:
            return False
        fields = _nex_profile_fields(profile[0].decode("utf-8", errors="replace"))
        return (
            single_field(fields, "base_url") == (static_expected_base_url, True)
            and static_expected_base_url is not None
            and single_field(fields, "auth_type") == ("bearer", True)
            and single_field(fields, "header_user_agent") == (_NEX_USER_AGENT, True)
            and single_field(fields, "credential_env") == (_NEX_SECRET_ENV, True)
        )

    malformed_ok = False
    for _label, files in malformed_profiles:
        profile = files.get("infra-profile.yaml")
        if profile is None or not valid_static_profile(files):
            continue
        endpoint = single_field(
            _nex_profile_fields(profile[0].decode("utf-8", errors="replace")),
            "endpoint_orders",
        )
        if endpoint is not None and endpoint[0] is not None and endpoint[0] != _NEX_ENDPOINT:
            malformed_ok = True
    omitted_ok = any(
        not _nex_profile_fields(files["infra-profile.yaml"][0].decode("utf-8", errors="replace")).get("endpoint_orders")
        and valid_static_profile(files)
        for _label, files in omitted_profiles if "infra-profile.yaml" in files
    )
    mark("static/malformed-endpoint-profile", malformed_ok)
    mark("static/omitted-endpoint-profile", omitted_ok)

    hardcoded_cases = [(f"static-{i}", files) for i, (name, _wf, _env, files) in enumerate(static_entries) if name == "hard-coded-endpoint"]
    hardcoded_ast = False
    hardcoded_failure_record = False
    for _label, files in hardcoded_cases:
        transform_files = {
            path: data for path, (data, _mode) in files.items()
            if path.startswith("transform/")
        }
        if any(path == "failure.json" or path.endswith("/failure.json") for path in files):
            hardcoded_failure_record = True
        if _nex_hardcoded_endpoint_ast(transform_files):
            hardcoded_ast = True
    mark("static/hard-coded-endpoint-runner-ast-rejection", hardcoded_ast and not hardcoded_failure_record)
    if not hardcoded_cases:
        failures.append("static/hard-coded-endpoint/case-snapshot-missing")
    elif not hardcoded_ast:
        failures.append("static/hard-coded-endpoint/literal-endpoint-not-found")
    if hardcoded_failure_record:
        failures.append("static/hard-coded-endpoint/failure-record-present")

    # Structured diagnostics are accepted only from direct diagnostic objects
    # on a JSON-RPC-matched response. Free prose and nested arbitrary values
    # never supply codes or phases.
    diagnostic_keys: set[tuple[str, str, str, str]] = set()
    diagnostics_by_workflow: dict[str, list[Mapping[str, Any]]] = {}
    for call in calls:
        workflow = call.get("workflow")
        if workflow not in _NEX_CASES and workflow != "__static__":
            continue
        response = call["response_message"]
        if _nex_evidence_call_rpc_error(call, validated_calls):
            failures.append("diagnostic/jsonrpc-integer-error-code")
        structured = _nex_structured_content(response)
        raw_diagnostics = structured.get("diagnostics")
        if raw_diagnostics is not None and not isinstance(raw_diagnostics, (list, Mapping)):
            failures.append("diagnostic/structured-container-invalid")
        if isinstance(raw_diagnostics, list) and any(not isinstance(item, Mapping) for item in raw_diagnostics):
            failures.append("diagnostic/non-object-list-entry")
        direct = _nex_direct_diagnostics(response)
        for diagnostic in direct:
            code, phase = diagnostic.get("code"), diagnostic.get("phase")
            if not isinstance(code, str) or not code.strip() or not isinstance(phase, str) or not phase.strip():
                failures.append("diagnostic/direct-code-phase-invalid")
                continue
            key = (str(workflow), call["id"], phase, code)
            if key in diagnostic_keys:
                failures.append("diagnostic/duplicate-direct-diagnostic")
            diagnostic_keys.add(key)
            diagnostics_by_workflow.setdefault(str(workflow), []).append(diagnostic)
            terms = " ".join(
                str(diagnostic.get(name, ""))
                for name in ("code", "phase", "category", "status")
                if isinstance(diagnostic.get(name), (str, int))
            ).lower()
            if any(term in terms for term in _NEX_FORBIDDEN_DIAGNOSTIC_TERMS):
                failures.append("diagnostic/forbidden-category")
    for workflow in ("nex890-401", "nex890-403", "nex890-404"):
        validation = validated_calls.get(workflow)
        direct = diagnostics_by_workflow.get(workflow, [])
        validation_diagnostics = []
        if validation is not None:
            validation_diagnostics = [
                item for item in _nex_direct_diagnostics(validation["response_message"])
                if isinstance(item.get("code"), str) and isinstance(item.get("phase"), str)
            ]
        mark(f"diagnostic/{workflow}/matched-validation-object", bool(validation_diagnostics) and bool(direct))

    # Correlate each frozen stub row solely by its monotonic position inside an
    # exact transform-execution request interval. The optional label is a
    # consistency check after interval ownership has been established.
    observations = frozen_stub_observations if isinstance(frozen_stub_observations, list) else []
    if not isinstance(frozen_stub_observations, list):
        failures.append("observations/not-a-list")
    owned: dict[str, dict[str, list[Mapping[str, Any]]]] = {
        name: {"validation": [], "run": []} for name in _NEX_CASES
    }
    interval_rows: list[tuple[int, int, str, str]] = []
    for name, (start, end, root) in case_intervals.items():
        interval_rows.append((start, end, name, "validation"))
    for call in positive_start_run_calls:
        interval_rows.append((
            call["request_ns"],
            call["response_ns"],
            "nex890-positive",
            "run",
        ))
    for observation in observations:
        if not isinstance(observation, Mapping):
            failures.append("observations/non-object-record")
            continue
        timestamp = _nex_timestamp(observation)
        if timestamp is None:
            failures.append("observations/timestamp-invalid")
            continue
        owners = [
            (name, phase) for start, end, name, phase in interval_rows
            if start <= timestamp <= end
        ]
        if len(owners) != 1:
            failures.append("observations/outside-or-overlapping-workflow-interval")
            continue
        owner, phase = owners[0]
        label = observation.get("X-Eval-Case", observation.get("x_eval_case", observation.get("case_label")))
        if label is not None and label != owner:
            failures.append(f"observations/{owner}/untrusted-label-mismatch")
        if any(str(key).lower() == "authorization" for key in observation):
            failures.append("observations/authorization-value-field-present")
        owned[owner][phase].append(observation)

    for workflow, expected_status in _NEX_CASES.items():
        validation_rows = owned[workflow]["validation"]
        run_rows = owned[workflow]["run"]
        rows = [*validation_rows, *run_rows]
        statuses = [row.get("status") for row in rows]
        if expected_status == 200:
            status_ok = bool(rows) and all(status == 200 for status in statuses)
            status_ok = status_ok and bool(validation_rows) and bool(run_rows) and all(
                row.get("status_filter") in (None, "", "paid") for row in rows
            )
        else:
            status_ok = (
                statuses.count(expected_status) == 1
                and len(validation_rows) == 1
                and not run_rows
            )
        mark(f"wire/{workflow}/status-interval-bound", status_ok)
        for row in rows:
            agent, auth_leak = _nex_observation_header(row)
            if auth_leak:
                failures.append("observations/authorization-header-present")
            path = _nex_observation_path(row)
            status = row.get("status")
            if workflow == "nex890-positive":
                if status == 200 and (path != _NEX_ENDPOINT or agent != _NEX_USER_AGENT or row.get("authorized") is not True):
                    failures.append("wire/nex890-positive/request-contract")
            elif workflow == "nex890-401":
                if status == 401 and (path != _NEX_ENDPOINT or agent != _NEX_USER_AGENT or row.get("authorized") is not False):
                    failures.append("wire/nex890-401/request-contract")
            elif workflow == "nex890-403":
                if status == 403 and (path != _NEX_ENDPOINT or agent in {None, _NEX_USER_AGENT} or row.get("authorized") is not True):
                    failures.append("wire/nex890-403/request-contract")
            elif workflow == "nex890-404":
                if status == 404 and (path in {None, _NEX_ENDPOINT} or agent != _NEX_USER_AGENT or row.get("authorized") is not True):
                    failures.append("wire/nex890-404/request-contract")

    positive_rows = [*owned["nex890-positive"]["validation"], *owned["nex890-positive"]["run"]]
    unfiltered_ok_by_phase: dict[str, bool] = {}
    filtered_ok_by_phase: dict[str, bool] = {}
    for phase in ("validation", "run"):
        phase_rows = owned["nex890-positive"][phase]
        unfiltered = [
            row for row in phase_rows
            if row.get("status") == 200 and not row.get("status_filter")
        ]
        unfiltered_by_page = {row.get("page"): row for row in unfiltered}
        unfiltered_ok_by_phase[phase] = (
            set(unfiltered_by_page) == {1, 2, 3} and len(unfiltered) == 3 and all(
                unfiltered_by_page[page].get("rows") == rows
                and unfiltered_by_page[page].get("total") == 23
                and unfiltered_by_page[page].get("pages") == 3
                and unfiltered_by_page[page].get("per_page") == 10
                for page, rows in PAGE_ROWS.items()
            )
        )
        filtered = [
            row for row in phase_rows
            if row.get("status") == 200 and row.get("status_filter") == "paid"
        ]
        filtered_by_page = {row.get("page"): row for row in filtered}
        filtered_ok_by_phase[phase] = (
            set(filtered_by_page) == {1, 2} and len(filtered) == 2 and all(
                filtered_by_page[page].get("rows") == count
                and filtered_by_page[page].get("total") == FILTERED_PAGE_TOTAL
                and filtered_by_page[page].get("pages") == 2
                and filtered_by_page[page].get("per_page") == 10
                for page, count in FILTERED_PAGE_ROWS.items()
            )
        )
    mark("landed/unfiltered-pagination", all(unfiltered_ok_by_phase.values()))
    mark("landed/paid-filter-pagination", all(filtered_ok_by_phase.values()))

    positive_calls = current_calls.get("nex890-positive", [])
    required_positive_operations = ("inspect_run", "resume_data_product", "run_semantic_query", "export_data_product")
    positive_operation_calls: dict[str, dict[str, Any]] = {}
    for operation in required_positive_operations:
        found = [call for call in positive_calls if call.get("operation") == operation]
        mark(f"publication/{operation}-unique-success", len(found) == 1 and _nex_response_ok(found[0]["response_message"]))
        if len(found) == 1:
            positive_operation_calls[operation] = found[0]
    start_run_calls = [
        call for call in positive_calls
        if call.get("operation") == "advance_workflow"
        and _nex_action(call)[0] == "start_run"
    ]
    mark("publication/start-run-action-unique-success", len(start_run_calls) == 1 and _nex_response_ok(start_run_calls[0]["response_message"]))
    lifecycle_calls = [
        positive_operation_calls.get(name)
        for name in ("inspect_run", "resume_data_product", "run_semantic_query", "export_data_product")
    ]
    if len(start_run_calls) == 1 and all(lifecycle_calls):
        ordered = [
            start_run_calls[0]["request_ns"],
            *(call["request_ns"] for call in lifecycle_calls if call is not None),
        ]
        ordered_ok = ordered == sorted(ordered)
        ordered_ok = ordered_ok and start_run_calls[0]["response_ns"] < lifecycle_calls[0]["request_ns"]
        mark("publication/positive-lifecycle-order", ordered_ok)
    else:
        mark("publication/positive-lifecycle-order", False)
    inspect_call = positive_operation_calls.get("inspect_run")
    inspect_objects = _nex_structured_objects(inspect_call["response_message"]) if inspect_call else []
    authoritative_run = any(
        isinstance(item.get("run_id"), str) and item.get("run_id")
        and isinstance(item.get("definition_id"), str) and item.get("definition_id")
        and item.get("workflow") == "nex890-positive"
        for item in inspect_objects
    )
    mark("publication/inspect-authoritative-run", authoritative_run)
    query_calls = [call for call in positive_calls if call.get("operation") == "run_semantic_query"]
    paid_query = len(query_calls) == 1 and paid_query_call is query_calls[0]
    mark("query/paid-filter-trace-bound", paid_query)
    query_result = any(
        any(
            item.get("row_count") == 1
            and isinstance(item.get("rows"), list)
            and len(item["rows"]) == 1
            and isinstance(item["rows"][0], list)
            and len(item["rows"][0]) == 1
            and item["rows"][0][0] == FILTERED_PAGE_TOTAL
            for item in _nex_structured_objects(call["response_message"])
        )
        for call in query_calls if _nex_response_ok(call["response_message"])
    )
    mark("query/paid-result-16", query_result)

    # Post-run archive bytes must be supplied by the runner as immutable
    # evidence; the capture/validation snapshots predate the export call.
    output_envelope = snapshots.get("nex890-positive", {})
    outputs = output_envelope.get("outputs", {}) if isinstance(output_envelope, Mapping) else {}
    output_files: dict[str, bytes] = {}
    if isinstance(outputs, Mapping):
        for path, payload in outputs.items():
            if not isinstance(path, str) or not os.path.isabs(path):
                failures.append("snapshot/output-path-invalid")
                continue
            if isinstance(payload, Mapping):
                payload = payload.get("content")
            if isinstance(payload, str):
                payload = payload.encode("utf-8")
            if isinstance(payload, bytes):
                output_files[os.path.normpath(path)] = payload
            else:
                failures.append("snapshot/output-content-invalid")
    else:
        failures.append("snapshot/outputs-invalid")

    export_calls = [call for call in positive_calls if call.get("operation") == "export_data_product"]
    export_paths: set[str] = set()
    export_path_pairs_ok = len(export_calls) == 1 and _nex_response_ok(export_calls[0]["response_message"])
    workspace_root = None
    if workflow_roots:
        try:
            workspace_root = os.path.commonpath(list(workflow_roots.values()))
        except ValueError:
            workspace_root = None

    def normalize_export_path(value: Any) -> str | None:
        if not isinstance(value, str) or not value:
            return None
        if os.path.isabs(value):
            return os.path.normpath(value)
        if workspace_root is None:
            return None
        return os.path.normpath(os.path.join(workspace_root, value))

    for call in export_calls:
        destination = call.get("arguments", {}).get("destination")
        normalized_destination = normalize_export_path(destination)
        if normalized_destination is not None:
            export_paths.add(normalized_destination)
        structured = _nex_structured_content(call["response_message"])
        archive_path = structured.get("archive_path")
        normalized_archive = normalize_export_path(archive_path)
        if normalized_archive is not None:
            export_paths.add(normalized_archive)
        if normalized_destination is None or normalized_archive is None or normalized_destination != normalized_archive:
            export_path_pairs_ok = False
    export_bytes = next((output_files[path] for path in export_paths if path in output_files), None)
    export_redacted = export_path_pairs_ok and export_bytes is not None and bool(export_paths & set(output_files))
    if export_paths and (workspace_root is None or not all(
        path != workspace_root
        and os.path.commonpath([workspace_root, path]) == workspace_root
        for path in export_paths
    )):
        export_redacted = False
    if export_redacted:
        if workspace_root is None:
            export_redacted = False
        if any(marker in export_bytes for marker in markers):
            export_redacted = False
        try:
            with zipfile.ZipFile(io.BytesIO(export_bytes)) as bundle:
                if not bundle.namelist():
                    export_redacted = False
                for member in bundle.infolist():
                    if any(marker in bundle.read(member) for marker in markers):
                        export_redacted = False
        except (OSError, zipfile.BadZipFile, RuntimeError):
            export_redacted = False
    mark("export/frozen-output-redaction", export_redacted)
    mark("redaction/no-marker-in-frozen-outputs", not any(
        marker in data for marker in markers for data in output_files.values()
    ))

    failures = sorted(set(failures))
    return {"passed": not failures, "failures": failures, "checks": checks}


def _terminal_route_hard_coded_case_is_runner_rejected(root: Path) -> bool:
    case_root = find_closure(root / ".eval-cases" / "hard-coded-endpoint")
    transform_files = sorted((case_root / "transform").glob("*.py")) if (case_root / "transform").is_dir() else []
    if not transform_files:
        return False
    source_text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in transform_files
    )
    if "api-source-endpoints" in source_text:
        return False
    hard_coded_names: set[str] = set()
    trees: list[ast.AST] = []
    for path in transform_files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        trees.append(tree)
        for node in ast.walk(tree):
            targets: list[ast.expr] = []
            value: ast.expr | None = None
            if isinstance(node, ast.Assign):
                targets, value = node.targets, node.value
            elif isinstance(node, ast.AnnAssign):
                targets, value = [node.target], node.value
            if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
                continue
            if not re.search(r"(?:https?://|127\.0\.0\.1|/v1/orders|ENDPOINT_URL)", value.value):
                continue
            for target in targets:
                if isinstance(target, ast.Name) and re.search(r"endpoint|url|path", target.id, re.I):
                    hard_coded_names.add(target.id)

    for tree in trees:
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            function = node.func
            function_name = (
                function.id if isinstance(function, ast.Name)
                else function.attr if isinstance(function, ast.Attribute)
                else None
            )
            if function_name != "rest_api_resources":
                continue
            if any(
                isinstance(child, ast.Constant)
                and isinstance(child.value, str)
                and re.search(
                    r"(?:https?://|127\.0\.0\.1|/v1/orders|ENDPOINT_URL)",
                    child.value,
                )
                for child in ast.walk(node)
            ):
                return True
            if any(
                isinstance(child, ast.Name) and child.id in hard_coded_names
                for child in ast.walk(node)
            ):
                return True
    return False


def _hard_coded_case_is_runner_rejected(root: Path) -> bool:
    if os.environ.get("NXD_EVAL_TERMINAL_WORKFLOW_ROUTE") == "terminal_workflow_review_v1":
        return _terminal_route_hard_coded_case_is_runner_rejected(root)
    case_root = find_closure(root / ".eval-cases" / "hard-coded-endpoint")
    transform_files = sorted((case_root / "transform").glob("*.py")) if (case_root / "transform").is_dir() else []
    source_literals = [
        literal
        for path in transform_files
        for literal in _non_doc_string_literals(path)
    ]
    has_literal_topology = any(
        re.search(r"(?:https?://|127\.0\.0\.1|/v1/orders|ENDPOINT_URL)", literal)
        for literal in source_literals
    )
    return has_literal_topology and "api-source-endpoints" not in "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in transform_files
    )


def _positive_closure(root: Path) -> Path:
    """Find the authored closure without allowing a negative case to win."""
    if (root / "transform" / "main.py").is_file():
        return root
    candidates: list[Path] = []
    for path in root.rglob("transform/main.py"):
        candidate = path.parent.parent
        try:
            relative = candidate.relative_to(root)
        except ValueError:
            continue
        if ".eval-cases" in relative.parts:
            continue
        candidates.append(candidate)
    return min(
        candidates,
        key=lambda path: (len(path.relative_to(root).parts), str(path)),
    ) if candidates else root


def _check_negative_cases(
    root: Path,
    calls: list[dict[str, Any]],
    observations: list[dict[str, Any]],
    failures: list[str],
    expected_cases: dict[str, tuple[str, tuple[str, ...]]],
) -> None:
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

    for case, (phase, needles) in expected_cases.items():
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
    expected_cases = (
        TERMINAL_ROUTE_EXPECTED_CASES
        if os.environ.get("NXD_EVAL_TERMINAL_WORKFLOW_ROUTE") == "terminal_workflow_review_v1"
        else LEGACY_EXPECTED_CASES
    )
    _check_negative_cases(root, calls, runner_observations, failures, expected_cases)
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
