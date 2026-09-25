"""Collect deterministic, runner-owned supervisor history for one adapter.

Evidence contract
=================

All turns in these artifacts are operator turns intended to equal the turn
numbers in operator-observations.json. The live session supplies the
authoritative turn number; callers without one use the adapter's increasing
counter. A repeated supplied turn first discards history from that turn onward
so native resume replaces observations from an aborted attempt. Supervisor
tables and MCP calls have no common wall clock, so turn attribution comes only
from those request observations.

The seven JSON artifacts contain only the fields below and only the named
supervisor facts or structured MCP facts:

* publication-history.json: releases are keyed by workflow, publish sequence,
  and run. turn is the first operator turn on which the release belongs to this
  session; workflow_id, workflow_key, run_id, publish_sequence, artifact_id,
  definition_id, verification_outcome, row_counts, and published_at_unix_ms
  come from the supervisor release record. release_basename is its filename;
  admission_id comes from the matching admission-link file or is null.
  attributed_by says built_run or session_request. changed_after_first_seen
  marks later changes to the source release or admission-link projection.
* run-records.json: run_id and workflow_id identify a read-only runs or
  wf_admissions row. request_id, admission_id, admission_status,
  definition_id, artifact_id, publish_sequence, capture_id, and
  capture_sha256 come from the admission and its dossier (definition and
  artifact may fall back to runs); status and verification/publication times
  come from runs. terminal is derived only from the supervisor status enum.
  start_turn is the matching advance request turn or first state-read turn;
  start_turn_source names request or state. terminal_turn is the first turn a
  terminal status was read. status_history appends each turn/status change.
  attributed_by uses built_run or session_request.
* run-failures.json: turn is the operator turn of the source diagnostic or
  request. source is run_diagnostic, operation_diagnostic, or tool_result.
  tool, workflow_id, run_id, operation_id, request_id, requirement_id, phase,
  code, recovery, outcome, timeout_phase, last_phase, failed_contracts, and
  exception_class are bounded projections of the same named supervisor
  fields. failed_contracts keeps only contract, model, and failed_count.
  Unavailable scalar identities are null. Free-form detail, error, summary,
  stdout, and stderr are never copied.
* tool-calls.json: last_turn is the greatest recorded operator turn. calls
  contains one record per nxd-desktop observation:
  turn, zero-based index, tool, is_error, answered, workflow_id, request_id,
  action_type, requirement_id, run_id, and endpoint. Identifier fields come
  only from the named scalar argument/result fields. endpoints maps a semantic
  endpoint learned from a structured result to its workflow_id.
* query-history.json: dropped counts queries evicted beyond the 64-query cap.
  Each query stores turn, tool-call index, workflow_id, endpoint, the known
  endpoint run_id, result columns, and mapped rows from a successful
  structured run_semantic_query result.
* supervisor-captures.json: captures contains capture_sha256, capture_id,
  workflow_ids, run_ids, first_turn, sources, files, skipped, and truncated.
  capture_sha256 is the supervisor digest; capture_id may be null. The sorted
  workflow_ids, run_ids, and sources describe associated history runs and
  successful capture results, which may be the only observed association.
  first_turn is their earliest attributed turn. files lists relative path,
  byte size, and sha256 for copied capture bytes; skipped lists relative paths
  and fixed refusal reasons; truncated says a size cap stopped copying.
  Snapshot bytes live below supervisor-captures/<digest>/.
* definition-export.json: definitions contains definition_id, run_ids,
  workflow_ids, present, inventory_valid, output_promises, model_promises,
  and input_expectations. present reports whether the digest directory exists;
  inventory_valid reports a matching definition.json schema and id with valid
  file entries. Promise records copy manifest names, descriptions where
  applicable, models, source, verifier_kind, source_in_inventory, and driver;
  output promises also copy source_sha256 from the inventory. port and
  source_name identify structural attachment. model_promises stores port and
  model names. Source code is never copied.

The only retained capture files are the explicit allowlist below. Every source
path is resolved inside the supervisor state directory, SQLite is opened in
read-only URI mode, and parse/read errors leave earlier history intact.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

PUBLICATION_SCHEMA = "dp-scenario-publication-history-v1"
RUN_RECORDS_SCHEMA = "dp-scenario-run-records-v1"
RUN_FAILURES_SCHEMA = "dp-scenario-run-failures-v1"
TOOL_CALLS_SCHEMA = "dp-scenario-tool-calls-v1"
QUERY_HISTORY_SCHEMA = "dp-scenario-query-history-v1"
CAPTURES_SCHEMA = "dp-scenario-supervisor-captures-v1"
DEFINITION_EXPORT_SCHEMA = "dp-scenario-definition-export-v1"

QUERY_HISTORY_LIMIT = 64
CAPTURE_TOTAL_LIMIT = 2 * 1024 * 1024
CAPTURE_FILE_LIMIT = 512 * 1024
_DEFINITION_ID_RE = re.compile(r"^sha256-v1:([0-9a-f]{64})$")
_CAPTURE_SHA_RE = re.compile(r"^sha256:([0-9a-f]{64})$")
_SAFE_FAILURE_VALUE_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,256}$")
_FAILED_CONTRACT_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_EXCEPTION_CLASS_RE = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$"
)
_TERMINAL_RUN_STATUSES = {
    "Published",
    "RolledBack",
    "Failed",
    "Cancelled",
    "Superseded",
}
_REQUEST_TOOLS = {"prepare_workflow", "advance_workflow", "reset_workflow"}
_CAPTURE_ALLOW_ROOT_FILES = {
    "spec.py",
    "models.py",
    "dp-blueprint.lock.json",
    "dp-blueprint.approved.md",
    "dp-blueprint.proposal.approved.json",
    "build-record.json",
    "requirements.txt",
}
_CAPTURE_EXCLUDED_NAMES = {
    "infra-profile.yaml",
    "SENSITIVE",
    "csv-source-path",
    "self_check.py",
    "connectivity_check.py",
    ".gitignore",
}
_URL_USERINFO_PASSWORD_RE = re.compile(
    rb"(?i)\b[a-z][a-z0-9+.-]*://[^/@\s:]+:([^/@\s]+)@"
)
_BEARER_TOKEN_RE = re.compile(rb"(?i)\bbearer\s+([A-Za-z0-9._~+/=-]{20,})")
_PEM_PRIVATE_KEY_RE = re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----")
_COMPACT_JWT_RE = re.compile(
    rb"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"
)
_VENDOR_TOKEN_RE = re.compile(
    rb"\b(?:sk-|ghp_|github_pat_|xox[bp]-)[A-Za-z0-9_-]{16,}"
)
_PLACEHOLDER_PASSWORDS = {"***", "password", "pass", "xxx"}


def _credential_literal(content: bytes) -> bool:
    """Recognize credential-shaped literals without inspecting file paths."""

    for match in _URL_USERINFO_PASSWORD_RE.finditer(content):
        password_bytes = match.group(1)
        if password_bytes.startswith((b"{", b"$", b"%", b"<")):
            continue
        try:
            password = password_bytes.decode("ascii").casefold()
        except UnicodeError:
            return True
        if password in _PLACEHOLDER_PASSWORDS:
            continue
        return True
    return any(
        pattern.search(content) is not None
        for pattern in (
            _BEARER_TOKEN_RE,
            _PEM_PRIVATE_KEY_RE,
            _COMPACT_JWT_RE,
            _VENDOR_TOKEN_RE,
        )
    )


def _is_obvious_secret(value: str) -> bool:
    """Reuse the checkpoint's shared secret-word filter on demand."""

    from dp_scenarios.runner.checkpoint import _is_obvious_secret_value

    return _is_obvious_secret_value(value)


def _is_secret_path_component(value: str) -> bool:
    """Reuse the checkpoint's shared secret-key filter on demand."""

    from dp_scenarios.runner.checkpoint import _is_secret_key

    return _is_secret_key(value)


def _read_json(path: Path) -> object | None:
    """Read one JSON source without turning an unreadable source into loss."""

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None


def _write_json(path: Path, value: object) -> None:
    """Use the adapter's canonical atomic JSON writer for every history file."""

    # This import is intentionally local: claude_adapter imports this module.
    from dp_scenarios.runner.claude_adapter import _write_json as adapter_writer

    adapter_writer(path, value)


def _safe_string(value: object, *, limit: int = 512) -> str | None:
    """Retain a bounded non-secret scalar string, never coercing other types."""

    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        return None
    if any(ord(character) < 32 and character not in "\t\n\r" for character in value):
        return None
    if _is_obvious_secret(value):
        return None
    # A structured endpoint is allowed, but a host filesystem path is not a
    # safe identifier in any history artifact.
    if re.search(r"/(?:private|Users|Volumes)(?:/|$)", value):
        return None
    if any(
        marker in value.casefold()
        for marker in ("token=", "password=", "secret=", "api_key=", "api-key=", "bearer ")
    ):
        return None
    return value


def _failure_string(value: object) -> str | None:
    """Retain only a small identifier-like diagnostic scalar."""

    if not isinstance(value, str) or _SAFE_FAILURE_VALUE_RE.fullmatch(value) is None:
        return None
    if _is_obvious_secret(value):
        return None
    return value


def _safe_time(value: object) -> int | str | None:
    """Preserve an integer or decimal-string supervisor unix-ms timestamp."""

    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    if isinstance(value, str) and value.isdecimal():
        return value
    return None


def _safe_count(value: object) -> str | None:
    """Normalize release row counts without accepting arbitrary text."""

    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return str(value)
    if isinstance(value, str) and value.isdecimal():
        return value
    return None


def _safe_row_counts(value: object) -> dict[str, str]:
    """Return sorted, bounded model/table row counts from a release record."""

    if not isinstance(value, Mapping):
        return {}
    result: dict[str, str] = {}
    for key, count in value.items():
        name = _safe_string(key, limit=256)
        safe_count = _safe_count(count)
        if name is not None and safe_count is not None:
            result[name] = safe_count
    return dict(sorted(result.items()))


def _parse_failed_contracts(value: object) -> list[dict[str, object]]:
    """Keep only the pinned supervisor's bounded contract/model/count tuple."""

    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    contracts: set[tuple[str, str, int]] = set()
    for item in value:
        if not isinstance(item, Mapping):
            continue
        contract = item.get("contract")
        model = item.get("model")
        failed_count = item.get("failed_count")
        if (
            not isinstance(contract, str)
            or _FAILED_CONTRACT_ID_RE.fullmatch(contract) is None
            or not isinstance(model, str)
            or _FAILED_CONTRACT_ID_RE.fullmatch(model) is None
            or not isinstance(failed_count, int)
            or isinstance(failed_count, bool)
            or failed_count < 0
        ):
            continue
        contracts.add((contract, model, failed_count))
    return [
        {"contract": contract, "model": model, "failed_count": failed_count}
        for contract, model, failed_count in sorted(contracts)
    ]


def _safe_failure_facts(value: Mapping[str, object]) -> tuple[
    list[dict[str, object]], str | None
]:
    """Project validated failure identities and exception class only."""

    failed = _parse_failed_contracts(value.get("failed_contracts"))
    exception_class = value.get("exception_class")
    if (
        not isinstance(exception_class, str)
        or len(exception_class) > 128
        or _EXCEPTION_CLASS_RE.fullmatch(exception_class) is None
    ):
        exception_class = None
    return failed, exception_class


def _failure_entry(
    *,
    turn: int,
    source: str,
    tool: str | None = None,
    workflow_id: str | None = None,
    run_id: str | None = None,
    operation_id: str | None = None,
    request_id: str | None = None,
    requirement_id: str | None = None,
    diagnostic: Mapping[str, object] | None = None,
    run_facts: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Build the closed run-failures record from named scalar fields only."""

    diagnostic = diagnostic or {}
    run_facts = run_facts or {}
    failed_contracts, exception_class = _safe_failure_facts(
        run_facts if "failed_contracts" in run_facts or "exception_class" in run_facts else diagnostic
    )
    return {
        "turn": turn,
        "source": source,
        "tool": _safe_string(tool),
        "workflow_id": _safe_string(workflow_id),
        "run_id": _safe_string(run_id),
        "operation_id": _safe_string(operation_id),
        "request_id": _safe_string(request_id),
        "requirement_id": _safe_string(requirement_id),
        "phase": _failure_string(diagnostic.get("phase", run_facts.get("phase"))),
        "code": _failure_string(diagnostic.get("code", run_facts.get("code"))),
        "recovery": _failure_string(diagnostic.get("recovery")),
        "outcome": _failure_string(run_facts.get("outcome", diagnostic.get("outcome"))),
        "timeout_phase": _failure_string(
            run_facts.get("timeout_phase", diagnostic.get("timeout_phase"))
        ),
        "last_phase": _failure_string(
            run_facts.get("last_phase", diagnostic.get("last_phase"))
        ),
        "failed_contracts": failed_contracts,
        "exception_class": exception_class,
    }


def _failure_key(entry: Mapping[str, object]) -> tuple[object, ...]:
    """Return the per-source stable identity used for failure deduplication."""

    contracts = entry.get("failed_contracts")
    contract_key = tuple(
        (item.get("contract"), item.get("model"), item.get("failed_count"))
        for item in contracts
        if isinstance(contracts, list) and isinstance(item, Mapping)
    ) if isinstance(contracts, list) else ()
    return (
        entry.get("source"),
        entry.get("tool"),
        entry.get("workflow_id"),
        entry.get("run_id"),
        entry.get("operation_id"),
        entry.get("request_id"),
        entry.get("requirement_id"),
        entry.get("phase"),
        entry.get("code"),
        entry.get("recovery"),
        entry.get("outcome"),
        entry.get("timeout_phase"),
        entry.get("last_phase"),
        contract_key,
        entry.get("exception_class"),
    )


def _schema_rows(value: object, schema: str, member: str) -> list[dict[str, object]]:
    """Load a schema-valid array of object entries, or treat it as absent."""

    if not isinstance(value, Mapping) or value.get("schema") != schema:
        return []
    rows = value.get(member)
    if not isinstance(rows, list):
        return []
    return [dict(row) for row in rows if isinstance(row, Mapping)]


def _relative_path(value: object) -> PurePosixPath | None:
    """Parse a safe relative POSIX path used by supervisor manifests."""

    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        return None
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        return None
    return path


def _within(root: Path, candidate: Path, *, strict: bool = True) -> Path | None:
    """Resolve a source path while refusing symlinks and state-root escapes."""

    try:
        root_path = root.resolve(strict=True)
        cursor = candidate
        while cursor != root_path:
            if cursor.is_symlink():
                return None
            if cursor.parent == cursor:
                return None
            cursor = cursor.parent
        resolved = candidate.resolve(strict=strict)
        resolved.relative_to(root_path)
    except (OSError, RuntimeError, ValueError):
        return None
    return resolved


def _terminal(status: object) -> bool:
    """Return whether a supervisor run status is one of the terminal enum values."""

    return isinstance(status, str) and status in _TERMINAL_RUN_STATUSES


def _tool_call_shape(value: object) -> dict[str, object] | None:
    """Validate and copy one persisted allowlisted tool-call record."""

    if not isinstance(value, Mapping):
        return None
    turn = value.get("turn")
    index = value.get("index")
    if (
        not isinstance(turn, int)
        or isinstance(turn, bool)
        or turn <= 0
        or not isinstance(index, int)
        or isinstance(index, bool)
        or index < 0
    ):
        return None
    tool = _safe_string(value.get("tool"), limit=128)
    if tool is None:
        return None
    return {
        "turn": turn,
        "index": index,
        "tool": tool,
        "is_error": value.get("is_error") is True,
        "answered": value.get("answered") is True,
        "workflow_id": _safe_string(value.get("workflow_id")),
        "request_id": _safe_string(value.get("request_id")),
        "action_type": _safe_string(value.get("action_type"), limit=128),
        "requirement_id": _safe_string(value.get("requirement_id"), limit=128),
        "run_id": _safe_string(value.get("run_id")),
        "endpoint": _safe_string(value.get("endpoint")),
    }


class SupervisorHistory:
    """Accumulate and write turn-attributed supervisor history.

    The class loads schema-valid artifacts on its first observation or write,
    keeps keys append-only during ordinary turns, and writes canonical JSON
    only after the adapter completes its existing fact writers. Native resume
    may explicitly discard a timed-out turn and later records before retrying
    that turn. state_dir is read without creating or modifying any file under
    it.
    """

    def __init__(
        self,
        artifact_dir: Path,
        *,
        secret_values: Iterable[str] = (),
    ) -> None:
        self.artifact_dir = Path(artifact_dir)
        self._secret_values = tuple(
            encoded
            for value in secret_values
            if isinstance(value, str) and len(value) >= 8
            for encoded in (value.encode("utf-8", errors="ignore"),)
            if encoded
        )
        self._loaded = False
        self._last_turn = 0
        self._tool_calls: dict[tuple[int, int], dict[str, object]] = {}
        self._endpoints: dict[str, str] = {}
        self._endpoint_runs: dict[str, str] = {}
        self._queries: list[dict[str, object]] = []
        self._queries_dropped = 0
        self._failures: dict[tuple[object, ...], dict[str, object]] = {}
        self._session_requests: dict[tuple[str, str], int] = {}
        self._advance_requests: dict[tuple[str, str], int] = {}
        self._built_run_ids: set[str] = set()
        self._run_records: dict[str, dict[str, object]] = {}
        self._publications: dict[tuple[str, str, str], dict[str, object]] = {}
        self._definitions: dict[str, dict[str, object]] = {}
        self._captures: dict[str, dict[str, object]] = {}
        self._capture_results: dict[str, list[dict[str, object]]] = {}
        self._capture_copy_bytes = 0
        self._capture_copy_stopped = False
        self._state_artifacts_enabled = False

    def _safe_argument(self, value: object, *, limit: int = 512) -> str | None:
        """Accept one whitelisted raw argument if it contains no known credential."""

        safe = _safe_string(value, limit=limit)
        if safe is None:
            return None
        content = safe.encode("utf-8")
        if any(secret in content for secret in self._secret_values):
            return None
        if _credential_literal(content):
            return None
        return safe

    @property
    def last_turn(self) -> int:
        """Return the greatest turn loaded from or observed by this history."""

        self._load_existing()
        return self._last_turn

    def _load_existing(self) -> None:
        """Resume only from existing artifacts with the expected schema."""

        if self._loaded:
            return
        self._loaded = True

        tool_path = self.artifact_dir / "tool-calls.json"
        tool_value = _read_json(tool_path)
        if isinstance(tool_value, Mapping) and tool_value.get("schema") == TOOL_CALLS_SCHEMA:
            last_turn = tool_value.get("last_turn")
            if isinstance(last_turn, int) and not isinstance(last_turn, bool) and last_turn >= 0:
                self._last_turn = last_turn
            endpoints = tool_value.get("endpoints")
            if isinstance(endpoints, Mapping):
                for endpoint, workflow in endpoints.items():
                    safe_endpoint = _safe_string(endpoint)
                    safe_workflow = _safe_string(workflow)
                    if safe_endpoint is not None and safe_workflow is not None:
                        self._endpoints[safe_endpoint] = safe_workflow
            for raw in tool_value.get("calls", []) if isinstance(tool_value.get("calls"), list) else []:
                call = _tool_call_shape(raw)
                if call is None:
                    continue
                key = (call["turn"], call["index"])
                self._tool_calls.setdefault(key, call)
                workflow = call.get("workflow_id")
                request_id = call.get("request_id")
                tool = call.get("tool")
                if (
                    isinstance(workflow, str)
                    and isinstance(request_id, str)
                    and tool in _REQUEST_TOOLS
                ):
                    request_key = (workflow, request_id)
                    self._session_requests[request_key] = min(
                        self._session_requests.get(request_key, call["turn"]),
                        call["turn"],
                    )
                    if tool == "advance_workflow":
                        self._advance_requests[request_key] = min(
                            self._advance_requests.get(request_key, call["turn"]),
                            call["turn"],
                        )
                if (
                    tool == "advance_workflow"
                    and call.get("action_type") == "start_run"
                    and isinstance(call.get("run_id"), str)
                ):
                    self._built_run_ids.add(call["run_id"])
                if (
                    tool == "resume_data_product"
                    and isinstance(call.get("endpoint"), str)
                    and isinstance(call.get("run_id"), str)
                ):
                    self._endpoint_runs[call["endpoint"]] = call["run_id"]

        queries_value = _read_json(self.artifact_dir / "query-history.json")
        if isinstance(queries_value, Mapping) and queries_value.get("schema") == QUERY_HISTORY_SCHEMA:
            dropped = queries_value.get("dropped")
            if isinstance(dropped, int) and not isinstance(dropped, bool) and dropped >= 0:
                self._queries_dropped = dropped
            queries = queries_value.get("queries")
            if isinstance(queries, list):
                self._queries = [
                    dict(query) for query in queries if isinstance(query, Mapping)
                ][-QUERY_HISTORY_LIMIT:]

        for item in _schema_rows(
            _read_json(self.artifact_dir / "run-failures.json"),
            RUN_FAILURES_SCHEMA,
            "failures",
        ):
            self._failures.setdefault(_failure_key(item), item)

        for item in _schema_rows(
            _read_json(self.artifact_dir / "run-records.json"),
            RUN_RECORDS_SCHEMA,
            "runs",
        ):
            run_id = _safe_string(item.get("run_id"))
            if run_id is not None:
                self._run_records.setdefault(run_id, item)

        for item in _schema_rows(
            _read_json(self.artifact_dir / "publication-history.json"),
            PUBLICATION_SCHEMA,
            "releases",
        ):
            workflow_id = _safe_string(item.get("workflow_id"))
            sequence = _safe_string(item.get("publish_sequence"))
            run_id = _safe_string(item.get("run_id"))
            if workflow_id is not None and sequence is not None and run_id is not None:
                self._publications.setdefault((workflow_id, sequence, run_id), item)

        for item in _schema_rows(
            _read_json(self.artifact_dir / "definition-export.json"),
            DEFINITION_EXPORT_SCHEMA,
            "definitions",
        ):
            definition_id = _safe_string(item.get("definition_id"))
            if definition_id is not None and _DEFINITION_ID_RE.fullmatch(definition_id):
                self._definitions.setdefault(definition_id, item)

        for item in _schema_rows(
            _read_json(self.artifact_dir / "supervisor-captures.json"),
            CAPTURES_SCHEMA,
            "captures",
        ):
            digest = item.get("capture_sha256")
            match = _CAPTURE_SHA_RE.fullmatch(digest) if isinstance(digest, str) else None
            if match is None:
                continue
            self._captures.setdefault(match.group(1), item)
            files = item.get("files")
            if isinstance(files, list):
                self._capture_copy_bytes += sum(
                    size
                    for file in files
                    if isinstance(file, Mapping)
                    and isinstance((size := file.get("size")), int)
                    and not isinstance(size, bool)
                    and size >= 0
                )
            if item.get("truncated") is True:
                self._capture_copy_stopped = True

    def discard_turns_from(self, turn: int) -> None:
        """Remove a timed-out operator turn and later records before its retry."""

        if not isinstance(turn, int) or isinstance(turn, bool) or turn <= 0:
            return
        self._load_existing()
        if turn > self._last_turn:
            return

        self._tool_calls = {
            key: call for key, call in self._tool_calls.items() if key[0] < turn
        }
        self._endpoints = {}
        self._endpoint_runs = {}
        self._session_requests = {}
        self._advance_requests = {}
        self._built_run_ids = set()
        for key in sorted(self._tool_calls):
            call = self._tool_calls[key]
            call_turn = call["turn"]
            workflow = call.get("workflow_id")
            request_id = call.get("request_id")
            tool = call.get("tool")
            endpoint = call.get("endpoint")
            run_id = call.get("run_id")
            if isinstance(endpoint, str) and isinstance(workflow, str):
                self._endpoints[endpoint] = workflow
            if (
                isinstance(workflow, str)
                and isinstance(request_id, str)
                and tool in _REQUEST_TOOLS
            ):
                request_key = (workflow, request_id)
                self._session_requests.setdefault(request_key, call_turn)
                if tool == "advance_workflow":
                    self._advance_requests.setdefault(request_key, call_turn)
            if (
                tool == "advance_workflow"
                and call.get("action_type") == "start_run"
                and isinstance(run_id, str)
            ):
                self._built_run_ids.add(run_id)
            if (
                tool == "resume_data_product"
                and isinstance(endpoint, str)
                and isinstance(run_id, str)
            ):
                self._endpoint_runs[endpoint] = run_id

        self._queries = [
            query
            for query in self._queries
            if isinstance(query.get("turn"), int)
            and not isinstance(query.get("turn"), bool)
            and query["turn"] < turn
        ]
        self._failures = {
            key: item
            for key, item in self._failures.items()
            if not isinstance(item.get("turn"), int)
            or isinstance(item.get("turn"), bool)
            or item["turn"] < turn
        }

        retained_runs: set[str] = set()
        records: dict[str, dict[str, object]] = {}
        for run_id, original in self._run_records.items():
            start_turn = original.get("start_turn")
            if (
                isinstance(start_turn, int)
                and not isinstance(start_turn, bool)
                and start_turn >= turn
            ):
                continue
            record = dict(original)
            statuses = record.get("status_history")
            if isinstance(statuses, list):
                record["status_history"] = [
                    dict(status)
                    for status in statuses
                    if isinstance(status, Mapping)
                    and isinstance(status.get("turn"), int)
                    and not isinstance(status.get("turn"), bool)
                    and status["turn"] < turn
                ]
                if record["status_history"]:
                    latest = record["status_history"][-1].get("status")
                    if isinstance(latest, str):
                        record["status"] = latest
                        record["terminal"] = _terminal(latest)
            terminal_turn = record.get("terminal_turn")
            if (
                isinstance(terminal_turn, int)
                and not isinstance(terminal_turn, bool)
                and terminal_turn >= turn
            ):
                record["terminal_turn"] = None
            records[run_id] = record
            retained_runs.add(run_id)
        self._run_records = records

        self._publications = {
            key: item
            for key, item in self._publications.items()
            if not (
                isinstance(item.get("turn"), int)
                and not isinstance(item.get("turn"), bool)
                and item["turn"] >= turn
            )
        }
        definitions: dict[str, dict[str, object]] = {}
        for definition_id, original in self._definitions.items():
            definition = dict(original)
            raw_run_ids = definition.get("run_ids")
            if isinstance(raw_run_ids, list):
                run_ids = [
                    run_id
                    for run_id in raw_run_ids
                    if isinstance(run_id, str) and run_id in retained_runs
                ]
                if raw_run_ids and not run_ids:
                    continue
                definition["run_ids"] = run_ids
            definitions[definition_id] = definition
        self._definitions = definitions

        captures: dict[str, dict[str, object]] = {}
        for digest, original in self._captures.items():
            first_turn = original.get("first_turn")
            if (
                isinstance(first_turn, int)
                and not isinstance(first_turn, bool)
                and first_turn >= turn
            ):
                continue
            capture = dict(original)
            raw_run_ids = capture.get("run_ids")
            if isinstance(raw_run_ids, list):
                capture["run_ids"] = [
                    run_id
                    for run_id in raw_run_ids
                    if isinstance(run_id, str) and run_id in retained_runs
                ]
            captures[digest] = capture
        self._captures = captures
        self._capture_results = {
            digest: [
                candidate
                for candidate in candidates
                if isinstance(candidate.get("turn"), int)
                and not isinstance(candidate.get("turn"), bool)
                and candidate["turn"] < turn
            ]
            for digest, candidates in self._capture_results.items()
        }
        self._capture_results = {
            digest: candidates
            for digest, candidates in self._capture_results.items()
            if candidates
        }
        self._capture_copy_bytes = sum(
            size
            for capture in self._captures.values()
            for file in (
                capture.get("files")
                if isinstance(capture.get("files"), list)
                else []
            )
            if isinstance(file, Mapping)
            and isinstance((size := file.get("size")), int)
            and not isinstance(size, bool)
            and size >= 0
        )
        self._capture_copy_stopped = any(
            capture.get("truncated") is True for capture in self._captures.values()
        )
        self._last_turn = turn - 1
        self._state_artifacts_enabled = self._state_artifacts_enabled or any(
            (self.artifact_dir / name).is_file()
            for name in (
                "publication-history.json",
                "run-records.json",
                "definition-export.json",
                "supervisor-captures.json",
            )
        )
        had_failure_artifact = (self.artifact_dir / "run-failures.json").is_file()
        self.write()
        if had_failure_artifact and not self._state_artifacts_enabled and not any(
            item.get("source") == "tool_result" for item in self._failures.values()
        ):
            _write_json(
                self.artifact_dir / "run-failures.json",
                {"schema": RUN_FAILURES_SCHEMA, "failures": []},
            )

    def observe_turn(
        self,
        *,
        turn: int,
        observations: Sequence[Mapping[str, object]],
        built_runs: set[str],
        state_dir: Path | None,
    ) -> None:
        """Record one operator turn from structured MCP calls and supervisor state.

        observations have the parser's {tool, arguments, result, is_error,
        answered} shape. Only named scalar arguments and result fields enter
        tool-calls.json. built_runs is read but never modified here.
        """

        self._load_existing()
        if not isinstance(turn, int) or isinstance(turn, bool) or turn <= 0:
            return
        self._last_turn = max(self._last_turn, turn)
        self._state_artifacts_enabled = state_dir is not None
        for safe_run_id in built_runs:
            run_id = _safe_string(safe_run_id)
            if run_id is not None:
                self._built_run_ids.add(run_id)

        # The adapter already parsed and redacted structured JSON-RPC results.
        # These imports keep the exact accepted row and admission predicates
        # shared with the pre-existing artifact path without a module cycle.
        from dp_scenarios.runner.claude_adapter import (
            _advance_action_type,
            _advance_requirement_id,
            _rows_as_mappings,
            _workflow_admission,
        )

        call_index = 0
        for observation in observations:
            raw_tool = observation.get("tool")
            if not isinstance(raw_tool, str):
                continue
            tool = raw_tool.removeprefix("mcp__nxd-desktop__")
            arguments = observation.get("arguments")
            if not isinstance(arguments, Mapping):
                arguments = {}
            payload = observation.get("result")
            if not isinstance(payload, Mapping):
                payload = {}
            is_error = observation.get("is_error") is True
            answered = observation.get("answered") is True
            workflow_id = self._safe_argument(arguments.get("workflow"))
            request_id = self._safe_argument(arguments.get("request_id"))
            endpoint_argument = self._safe_argument(arguments.get("endpoint"))
            action_type = self._safe_argument(
                _advance_action_type(arguments), limit=128
            )
            requirement_id = self._safe_argument(
                _advance_requirement_id(arguments), limit=128
            )

            if (
                tool in _REQUEST_TOOLS
                and workflow_id is not None
                and request_id is not None
            ):
                key = (workflow_id, request_id)
                self._session_requests[key] = min(
                    self._session_requests.get(key, turn), turn
                )
                if tool == "advance_workflow":
                    self._advance_requests[key] = min(
                        self._advance_requests.get(key, turn), turn
                    )

            # Learn endpoint identity only from structured endpoint/workflow
            # pairs. resume_data_product is the common path; the two explicit
            # aliases also cover forward-compatible structured responses.
            result_workflow = _safe_string(payload.get("workflow"))
            if result_workflow is None:
                result_workflow = _safe_string(payload.get("workflow_id"))
            paired_endpoint = _safe_string(payload.get("semantic_endpoint"))
            if paired_endpoint is None:
                paired_endpoint = _safe_string(payload.get("endpoint"))
            if paired_endpoint is not None and result_workflow is not None:
                self._endpoints[paired_endpoint] = result_workflow

            endpoint = endpoint_argument
            if tool == "resume_data_product":
                endpoint = _safe_string(payload.get("semantic_endpoint"))
                result_run_id = _safe_string(payload.get("run_id"))
                result_workflow = result_workflow or workflow_id
                if endpoint is not None and result_workflow is not None:
                    self._endpoints[endpoint] = result_workflow
                if endpoint is not None and result_run_id is not None:
                    self._endpoint_runs[endpoint] = result_run_id

            resolved_workflow = workflow_id
            if (
                resolved_workflow is None
                and endpoint_argument is not None
                and tool in {"run_semantic_query", "describe_models"}
            ):
                resolved_workflow = self._endpoints.get(endpoint_argument)
            if (
                resolved_workflow is None
                and endpoint is not None
                and tool in {"run_semantic_query", "describe_models"}
            ):
                resolved_workflow = self._endpoints.get(endpoint)

            run_id = self._safe_argument(arguments.get("run_id"))
            if tool == "advance_workflow" and action_type == "start_run":
                admission = _workflow_admission(payload, arguments)
                if run_id is None and admission is not None:
                    run_id = _safe_string(admission.get("run_id"))
                if admission is not None:
                    admitted_run_id = _safe_string(admission.get("run_id"))
                    if admitted_run_id is not None:
                        self._built_run_ids.add(admitted_run_id)
            elif tool == "inspect_run":
                run = payload.get("run")
                if run_id is None and isinstance(run, Mapping):
                    run_id = _safe_string(run.get("run_id")) or run_id
            elif tool == "resume_data_product":
                if run_id is None:
                    run_id = _safe_string(payload.get("run_id"))
            call = {
                "turn": turn,
                "index": call_index,
                "tool": tool,
                "is_error": is_error,
                "answered": answered,
                "workflow_id": resolved_workflow,
                "request_id": request_id,
                "action_type": action_type,
                "requirement_id": requirement_id,
                "run_id": run_id,
                "endpoint": endpoint,
            }
            normalized_call = _tool_call_shape(call)
            if normalized_call is not None:
                self._tool_calls.setdefault((turn, call_index), normalized_call)
                call_index += 1

            if (
                tool == "run_semantic_query"
                and not is_error
                and isinstance(payload, Mapping)
            ):
                rows = _rows_as_mappings(payload)
                if rows is not None:
                    columns = payload.get("columns")
                    if (
                        isinstance(columns, list)
                        and all(isinstance(column, str) for column in columns)
                        and len(set(columns)) == len(columns)
                    ):
                        query_columns = list(columns)
                    elif rows:
                        query_columns = list(rows[0].keys())
                    else:
                        query_columns = []
                    query = {
                        "turn": turn,
                        "index": max(0, call_index - 1),
                        "workflow_id": resolved_workflow,
                        "endpoint": endpoint,
                        "run_id": (
                            self._endpoint_runs.get(endpoint)
                            if endpoint is not None
                            else None
                        ),
                        "columns": query_columns,
                        "rows": rows,
                    }
                    self._append_query(query)

            self._observe_tool_failure(
                turn=turn,
                tool=tool,
                arguments=arguments,
                payload=payload,
                is_error=is_error,
                answered=answered,
                workflow_id=resolved_workflow or workflow_id,
                request_id=request_id,
                requirement_id=requirement_id,
                run_id=run_id,
                action_type=action_type,
                workflow_admission=_workflow_admission,
            )

            if (
                tool == "advance_workflow"
                and action_type == "capture"
                and answered
                and not is_error
            ):
                self._remember_capture_result(
                    turn=turn,
                    workflow_id=workflow_id,
                    payload=payload,
                )

        if state_dir is None:
            return

        state_root = self._state_root(state_dir)
        if state_root is None:
            return
        state = self._read_state_tables(state_root)
        if state is not None:
            attributed = self._history_run_attribution(
                turn=turn,
                built_runs=built_runs,
                runs=state["runs"],
                admissions=state["wf_admissions"],
            )
            self._update_run_records(
                turn=turn,
                attributed=attributed,
                runs=state["runs"],
                admissions=state["wf_admissions"],
            )
            self._update_run_diagnostics(
                turn=turn,
                attributed=attributed,
                rows=state["run_diagnostics"],
            )
            self._update_operation_diagnostics(
                turn=turn,
                operations=state["wf_operations"],
                requests=state["wf_requests"],
                diagnostics=state["wf_operation_diagnostics"],
            )
        else:
            attributed = {}

        self._update_publications(
            turn=turn,
            state_dir=state_root,
            attributed=attributed,
        )
        self._update_definition_export(state_root)
        self._update_capture_snapshots(
            turn=turn,
            state_dir=state_root,
            attributed=attributed,
        )

    def _append_query(self, query: dict[str, object]) -> None:
        """Append a query keyed by turn/index and count any bounded eviction."""

        key = (query.get("turn"), query.get("index"))
        if any((old.get("turn"), old.get("index")) == key for old in self._queries):
            return
        self._queries.append(query)
        self._queries.sort(key=lambda item: (int(item.get("turn", 0)), int(item.get("index", 0))))
        if len(self._queries) > QUERY_HISTORY_LIMIT:
            removed = len(self._queries) - QUERY_HISTORY_LIMIT
            del self._queries[:removed]
            self._queries_dropped += removed

    def _observe_tool_failure(
        self,
        *,
        turn: int,
        tool: str,
        arguments: Mapping[str, object],
        payload: Mapping[str, object],
        is_error: bool,
        answered: bool,
        workflow_id: str | None,
        request_id: str | None,
        requirement_id: str | None,
        run_id: str | None,
        action_type: str | None,
        workflow_admission: Any,
    ) -> None:
        """Extract only the pinned inspect_run and advance_workflow failure paths."""

        if not answered:
            return
        if tool == "inspect_run":
            run = payload.get("run")
            if not isinstance(run, Mapping):
                return
            failed, exception = _safe_failure_facts(run)
            outcome = run.get("outcome")
            if not failed and exception is None and outcome != "failed":
                return
            entry = _failure_entry(
                turn=turn,
                source="tool_result",
                tool=tool,
                workflow_id=_safe_string(run.get("workflow")) or workflow_id,
                run_id=_safe_string(run.get("run_id")) or run_id,
                request_id=request_id,
                run_facts=run,
            )
            self._append_failure(entry)
            return
        if tool != "advance_workflow":
            return

        admission = workflow_admission(payload, arguments)
        admitted_run_id = (
            _safe_string(admission.get("run_id"))
            if admission is not None
            else None
        )
        if admitted_run_id is None:
            admitted_run_id = None if action_type != "start_run" else run_id

        candidates: list[tuple[Mapping[str, object], Mapping[str, object]]] = []
        direct_diagnostic = payload.get("diagnostic")
        if isinstance(direct_diagnostic, Mapping):
            candidates.append(({}, direct_diagnostic))
        operation = payload.get("operation")
        if isinstance(operation, Mapping):
            diagnostic = operation.get("diagnostic")
            if isinstance(diagnostic, Mapping):
                candidates.append((operation, diagnostic))
            if "failed_contracts" in operation or "exception_class" in operation:
                candidates.append((operation, operation))
        operations = payload.get("operations")
        if isinstance(operations, Sequence) and not isinstance(
            operations, (str, bytes, bytearray)
        ):
            for item in operations:
                if not isinstance(item, Mapping):
                    continue
                diagnostic = item.get("diagnostic")
                if isinstance(diagnostic, Mapping):
                    candidates.append((item, diagnostic))
                if "failed_contracts" in item or "exception_class" in item:
                    candidates.append((item, item))
        if (
            "failed_contracts" in payload
            or "exception_class" in payload
        ):
            candidates.append(({}, payload))

        seen_operations: set[str] = set()
        for operation_record, diagnostic in candidates:
            failed, exception = _safe_failure_facts(
                operation_record
                if "failed_contracts" in operation_record
                or "exception_class" in operation_record
                else diagnostic
            )
            has_diagnostic = any(
                _failure_string(diagnostic.get(key)) is not None
                for key in ("phase", "code", "recovery")
            )
            if not failed and exception is None and not has_diagnostic:
                continue
            operation_id = _safe_string(operation_record.get("operation_id"))
            if operation_id is not None and operation_id in seen_operations:
                continue
            if operation_id is not None:
                seen_operations.add(operation_id)
            entry = _failure_entry(
                turn=turn,
                source="tool_result",
                tool=tool,
                workflow_id=_safe_string(operation_record.get("workflow"))
                or workflow_id,
                run_id=admitted_run_id,
                operation_id=operation_id,
                request_id=_safe_string(operation_record.get("request_id"))
                or request_id,
                requirement_id=_safe_string(
                    (operation_record.get("binding") or {}).get("requirement_id")
                )
                if isinstance(operation_record.get("binding"), Mapping)
                else requirement_id,
                diagnostic=diagnostic,
                run_facts=(
                    operation_record
                    if "failed_contracts" in operation_record
                    or "exception_class" in operation_record
                    else {}
                ),
            )
            self._append_failure(entry)

    def _append_failure(self, entry: dict[str, object]) -> None:
        """Keep the first value for a stable source-specific failure key."""

        self._failures.setdefault(_failure_key(entry), entry)

    def _remember_capture_result(
        self,
        *,
        turn: int,
        workflow_id: str | None,
        payload: Mapping[str, object],
    ) -> None:
        """Remember a successful pending-review capture digest in memory only."""

        requirements = payload.get("requirements")
        if not isinstance(requirements, Sequence) or isinstance(
            requirements, (str, bytes, bytearray)
        ):
            return
        for requirement in requirements:
            if (
                not isinstance(requirement, Mapping)
                or requirement.get("id") != "review"
                or str(requirement.get("status", "")).casefold() != "pending"
            ):
                continue
            review_input = requirement.get("review_input")
            if not isinstance(review_input, Mapping):
                continue
            raw_root = review_input.get("retained_capture_root")
            if not isinstance(raw_root, str) or not raw_root:
                continue
            components = PurePosixPath(raw_root).parts
            if len(components) < 3 or components[-3:-1] != ("captures", "sha256"):
                continue
            digest = components[-1]
            if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
                continue
            candidates = self._capture_results.setdefault(digest, [])
            safe_workflow_id = _safe_string(workflow_id)
            if not any(
                item.get("turn") == turn
                and item.get("workflow_id") == safe_workflow_id
                for item in candidates
            ):
                candidates.append(
                    {
                        "turn": turn,
                        "workflow_id": safe_workflow_id,
                    }
                )

    def _state_root(self, state_dir: Path) -> Path | None:
        """Resolve an existing supervisor data directory without creating it."""

        try:
            root = Path(state_dir).resolve(strict=True)
            return root if root.is_dir() else None
        except (OSError, RuntimeError):
            return None

    def _read_state_tables(self, state_dir: Path) -> dict[str, list[dict[str, object]]] | None:
        """Read supported supervisor tables through a read-only SQLite URI."""

        database = state_dir / "state.sqlite3"
        safe_database = _within(state_dir, database)
        if safe_database is None or not safe_database.is_file():
            return None
        uri = safe_database.as_uri() + "?mode=ro"
        table_names = (
            "runs",
            "wf_admissions",
            "wf_operations",
            "wf_requests",
            "wf_operation_diagnostics",
            "run_diagnostics",
        )
        try:
            connection = sqlite3.connect(
                uri,
                uri=True,
                timeout=0.25,
            )
            connection.row_factory = sqlite3.Row
            result: dict[str, list[dict[str, object]]] = {}
            try:
                for table in table_names:
                    try:
                        rows = connection.execute(f"SELECT * FROM {table}").fetchall()
                    except sqlite3.OperationalError as exc:
                        if "no such table" in str(exc).casefold():
                            result[table] = []
                            continue
                        raise
                    result[table] = [dict(row) for row in rows]
            finally:
                connection.close()
        except (OSError, sqlite3.Error):
            return None
        return result

    def _history_run_attribution(
        self,
        *,
        turn: int,
        built_runs: set[str],
        runs: list[dict[str, object]],
        admissions: list[dict[str, object]],
    ) -> dict[str, dict[str, object]]:
        """Select only this session's runs and record their attribution source."""

        runs_by_id = {
            run_id: row
            for row in runs
            if (run_id := _safe_string(row.get("run_id"))) is not None
        }
        admission_by_run: dict[str, dict[str, object]] = {}
        for admission in admissions:
            run_id = _safe_string(admission.get("run_id"))
            if run_id is not None:
                admission_by_run.setdefault(run_id, admission)

        requested_built = {
            run_id
            for run_id in (
                [_safe_string(item) for item in built_runs]
                + list(self._built_run_ids)
            )
            if run_id is not None
        }
        candidates = set(runs_by_id) | set(admission_by_run) | requested_built
        attributed: dict[str, dict[str, object]] = {}
        for run_id in candidates:
            admission = admission_by_run.get(run_id, {})
            workflow = _safe_string(
                admission.get("workflow")
                or runs_by_id.get(run_id, {}).get("workflow_id")
            )
            request_id = _safe_string(admission.get("request_id"))
            if run_id in requested_built:
                attributed_by = "built_run"
            elif (
                workflow is not None
                and request_id is not None
                and (workflow, request_id) in self._session_requests
            ):
                attributed_by = "session_request"
            else:
                continue

            request_turn = (
                self._advance_requests.get((workflow, request_id))
                if workflow is not None and request_id is not None
                else None
            )
            if request_turn is None:
                request_turn = self._run_start_turn(run_id, workflow, request_id)
            existing = self._run_records.get(run_id)
            state_turn = (
                existing.get("start_turn")
                if isinstance(existing, Mapping)
                and isinstance(existing.get("start_turn"), int)
                and not isinstance(existing.get("start_turn"), bool)
                else turn
            )
            attributed[run_id] = {
                "attributed_by": attributed_by,
                "workflow_id": workflow,
                "request_id": request_id,
                "start_turn": request_turn or state_turn,
                "start_turn_source": "request" if request_turn is not None else "state",
            }
        return attributed

    def _run_start_turn(
        self,
        run_id: str,
        workflow_id: str | None,
        request_id: str | None,
    ) -> int | None:
        """Find a previously logged start-run request without using sticky admission."""

        for call in sorted(
            self._tool_calls.values(),
            key=lambda value: (int(value["turn"]), int(value["index"])),
        ):
            if (
                call.get("tool") == "advance_workflow"
                and call.get("action_type") == "start_run"
                and call.get("workflow_id") == workflow_id
                and call.get("run_id") == run_id
                and (
                    request_id is None
                    or call.get("request_id") == request_id
                )
            ):
                return int(call["turn"])
        return None

    def _update_run_records(
        self,
        *,
        turn: int,
        attributed: Mapping[str, Mapping[str, object]],
        runs: list[dict[str, object]],
        admissions: list[dict[str, object]],
    ) -> None:
        """Append run identities and update only observed lifecycle changes."""

        runs_by_id = {
            run_id: row
            for row in runs
            if (run_id := _safe_string(row.get("run_id"))) is not None
        }
        admissions_by_run: dict[str, dict[str, object]] = {}
        for row in admissions:
            run_id = _safe_string(row.get("run_id"))
            if run_id is not None:
                admissions_by_run.setdefault(run_id, row)

        for run_id, attribution in attributed.items():
            run = runs_by_id.get(run_id, {})
            admission = admissions_by_run.get(run_id, {})
            prior = self._run_records.get(run_id)
            workflow_id = _safe_string(
                admission.get("workflow")
                or run.get("workflow_id")
                or attribution.get("workflow_id")
            )
            dossier = admission.get("dossier_json")
            dossier_value: object = None
            if isinstance(dossier, (str, bytes, bytearray)):
                try:
                    dossier_value = json.loads(dossier)
                except (UnicodeError, json.JSONDecodeError, TypeError):
                    dossier_value = None
            if not isinstance(dossier_value, Mapping):
                dossier_value = {}
            capture_id = _safe_string(dossier_value.get("capture_id"))
            capture_sha256 = dossier_value.get("capture_sha256")
            if not isinstance(capture_sha256, str) or _CAPTURE_SHA_RE.fullmatch(capture_sha256) is None:
                capture_sha256 = None

            status = _safe_string(run.get("status"), limit=64)
            if status is None and isinstance(prior, Mapping):
                status = _safe_string(prior.get("status"), limit=64)
            start_turn = attribution.get("start_turn")
            if not isinstance(start_turn, int) or isinstance(start_turn, bool) or start_turn <= 0:
                start_turn = turn
            status_history: list[dict[str, object]] = []
            if isinstance(prior, Mapping) and isinstance(prior.get("status_history"), list):
                status_history = [
                    dict(item)
                    for item in prior["status_history"]
                    if isinstance(item, Mapping)
                ]
            previous_status = status_history[-1].get("status") if status_history else None
            if status is not None and status != previous_status:
                status_history.append({"turn": turn, "status": status})

            prior_terminal_turn = (
                prior.get("terminal_turn")
                if isinstance(prior, Mapping)
                else None
            )
            terminal_turn = prior_terminal_turn
            if terminal_turn is None and _terminal(status):
                terminal_turn = turn

            record = {
                "run_id": run_id,
                "workflow_id": workflow_id,
                "request_id": _safe_string(admission.get("request_id"))
                or _safe_string(attribution.get("request_id")),
                "admission_id": _safe_string(admission.get("admission_id")),
                "admission_status": _safe_string(admission.get("status"), limit=64),
                "definition_id": _safe_string(
                    run.get("definition_id") or admission.get("definition_id")
                ),
                "artifact_id": _safe_string(
                    run.get("artifact_id") or admission.get("artifact_id")
                ),
                "publish_sequence": _safe_string(
                    run.get("publish_seq") or admission.get("publish_seq")
                ),
                "capture_id": capture_id,
                "capture_sha256": capture_sha256,
                "status": status,
                "terminal": _terminal(status),
                "verified_at_unix_ms": _safe_time(
                    run.get("verified_at_unix_ms")
                    if run.get("verified_at_unix_ms") is not None
                    else prior.get("verified_at_unix_ms")
                    if isinstance(prior, Mapping)
                    else None
                ),
                "published_at_unix_ms": _safe_time(
                    run.get("published_at_unix_ms")
                    if run.get("published_at_unix_ms") is not None
                    else prior.get("published_at_unix_ms")
                    if isinstance(prior, Mapping)
                    else None
                ),
                "start_turn": (
                    prior.get("start_turn")
                    if isinstance(prior, Mapping)
                    and isinstance(prior.get("start_turn"), int)
                    and not isinstance(prior.get("start_turn"), bool)
                    else start_turn
                ),
                "start_turn_source": (
                    prior.get("start_turn_source")
                    if isinstance(prior, Mapping)
                    and prior.get("start_turn_source") in {"request", "state"}
                    else attribution.get("start_turn_source", "state")
                ),
                "terminal_turn": terminal_turn,
                "status_history": status_history,
                "attributed_by": attribution.get("attributed_by"),
            }
            self._run_records.setdefault(run_id, record)
            current = self._run_records[run_id]
            # Lifecycle fields are the only mutable run fields. Identity is
            # first-seen data, while status history captures every transition.
            current["status"] = status
            current["terminal"] = _terminal(status)
            if run.get("verified_at_unix_ms") is not None:
                current["verified_at_unix_ms"] = _safe_time(
                    run.get("verified_at_unix_ms")
                )
            if run.get("published_at_unix_ms") is not None:
                current["published_at_unix_ms"] = _safe_time(
                    run.get("published_at_unix_ms")
                )
            current["status_history"] = status_history
            if (
                attribution.get("start_turn_source") == "request"
                and current.get("start_turn_source") != "request"
            ):
                current["start_turn"] = start_turn
                current["start_turn_source"] = "request"
            if current.get("terminal_turn") is None and _terminal(status):
                current["terminal_turn"] = turn

    def _update_run_diagnostics(
        self,
        *,
        turn: int,
        attributed: Mapping[str, Mapping[str, object]],
        rows: list[dict[str, object]],
    ) -> None:
        """Project nxd-run-diagnostic-v5 facts for session-attributed runs."""

        for row in rows:
            run_id = _safe_string(row.get("run_id"))
            if run_id is None or run_id not in attributed:
                continue
            diagnostic = row.get("diagnostic_json")
            try:
                document = json.loads(diagnostic) if isinstance(diagnostic, (str, bytes, bytearray)) else None
            except (UnicodeError, json.JSONDecodeError, TypeError):
                continue
            if (
                not isinstance(document, Mapping)
                or document.get("schema") != "nxd-run-diagnostic-v5"
            ):
                continue
            run_record = self._run_records.get(run_id, {})
            entry = _failure_entry(
                turn=(
                    run_record.get("start_turn")
                    if isinstance(run_record.get("start_turn"), int)
                    else turn
                ),
                source="run_diagnostic",
                workflow_id=_safe_string(row.get("workflow_id"))
                or _safe_string(document.get("workflow_id")),
                run_id=run_id,
                run_facts=document,
            )
            if any(
                entry.get(name) is not None
                for name in (
                    "code",
                    "outcome",
                    "timeout_phase",
                    "last_phase",
                    "exception_class",
                )
            ) or entry["failed_contracts"]:
                self._append_failure(entry)

    def _update_operation_diagnostics(
        self,
        *,
        turn: int,
        operations: list[dict[str, object]],
        requests: list[dict[str, object]],
        diagnostics: list[dict[str, object]],
    ) -> None:
        """Join operation diagnostics to the first sent session request turn."""

        operations_by_id = {
            operation_id: row
            for row in operations
            if (operation_id := _safe_string(row.get("operation_id"))) is not None
        }
        request_by_operation = {
            operation_id: request_id
            for row in requests
            if (operation_id := _safe_string(row.get("operation_id"))) is not None
            and (request_id := _safe_string(row.get("request_id"))) is not None
        }
        for row in diagnostics:
            operation_id = _safe_string(row.get("operation_id"))
            operation = operations_by_id.get(operation_id or "", {})
            request_id = _safe_string(operation.get("request_id"))
            if request_id is None and operation_id is not None:
                request_id = request_by_operation.get(operation_id)
            workflow_id = _safe_string(
                row.get("workflow") or operation.get("workflow")
            )
            if request_id is None or workflow_id is None:
                continue
            request_key = (workflow_id, request_id)
            request_turn = self._session_requests.get(request_key)
            if request_turn is None:
                continue
            raw_diagnostic = row.get("diagnostic_json")
            try:
                diagnostic = (
                    json.loads(raw_diagnostic)
                    if isinstance(raw_diagnostic, (str, bytes, bytearray))
                    else None
                )
            except (UnicodeError, json.JSONDecodeError, TypeError):
                continue
            if not isinstance(diagnostic, Mapping):
                continue
            entry = _failure_entry(
                turn=request_turn,
                source="operation_diagnostic",
                workflow_id=workflow_id,
                operation_id=operation_id,
                request_id=request_id,
                requirement_id=_safe_string(
                    row.get("requirement_id")
                    or operation.get("requirement_id")
                ),
                diagnostic=diagnostic,
            )
            if any(
                entry.get(name) is not None
                for name in ("phase", "code", "recovery")
            ):
                self._append_failure(entry)

    def _release_records(
        self,
        state_dir: Path,
    ) -> list[tuple[Mapping[str, object], str]]:
        """Reuse the adapter release reader and pair its records with basenames."""

        from dp_scenarios.runner.claude_adapter import _published_releases

        records = _published_releases(state_dir)
        remaining = list(records)
        paired: list[tuple[Mapping[str, object], str]] = []
        for path in sorted(state_dir.glob("workflows/*/releases/release-*.json")):
            if _within(state_dir, path) is None:
                continue
            document = _read_json(path)
            if not isinstance(document, Mapping):
                continue
            for index, record in enumerate(remaining):
                if dict(record) == dict(document):
                    paired.append((document, path.name))
                    del remaining[index]
                    break
        return paired

    def _admission_link_id(
        self,
        *,
        state_dir: Path,
        workflow_key: str | None,
        release_basename: str,
    ) -> str | None:
        """Read only the admission_id from the matching supervisor link file."""

        if workflow_key is None or "/" in workflow_key or "\\" in workflow_key:
            return None
        link = (
            state_dir
            / "workflows"
            / workflow_key
            / "admission-links"
            / f"{release_basename}.json"
        )
        safe_link = _within(state_dir, link)
        if safe_link is None or not safe_link.is_file():
            return None
        document = _read_json(safe_link)
        return (
            _safe_string(document.get("admission_id"))
            if isinstance(document, Mapping)
            else None
        )

    def _update_publications(
        self,
        *,
        turn: int,
        state_dir: Path,
        attributed: Mapping[str, Mapping[str, object]],
    ) -> None:
        """Append qualifying release records, preserving the first projection."""

        for record, basename in self._release_records(state_dir):
            run_id = _safe_string(record.get("run_id"))
            workflow_id = _safe_string(record.get("workflow_id"))
            workflow_key = _safe_string(record.get("workflow_key"))
            publish_value = record.get("publish_seq")
            if (
                run_id is None
                or workflow_id is None
                or run_id not in attributed
                or isinstance(publish_value, bool)
                or not isinstance(publish_value, (str, int))
            ):
                continue
            try:
                publish_sequence = str(int(publish_value))
            except ValueError:
                continue
            if int(publish_sequence) < 0:
                continue
            verification = record.get("verification")
            if not isinstance(verification, Mapping):
                verification = {}
            new_entry: dict[str, object] = {
                "turn": int(attributed[run_id].get("start_turn", turn)),
                "workflow_id": workflow_id,
                "workflow_key": workflow_key,
                "run_id": run_id,
                "publish_sequence": publish_sequence,
                "artifact_id": _safe_string(record.get("artifact_id")),
                "definition_id": _safe_string(record.get("definition_id")),
                "verification_outcome": _safe_string(
                    verification.get("outcome"), limit=64
                ),
                "row_counts": _safe_row_counts(verification.get("row_counts")),
                "published_at_unix_ms": _safe_time(
                    record.get("published_at_unix_ms")
                ),
                "release_basename": basename,
                "admission_id": self._admission_link_id(
                    state_dir=state_dir,
                    workflow_key=workflow_key,
                    release_basename=basename,
                ),
                "attributed_by": attributed[run_id].get("attributed_by"),
                "changed_after_first_seen": False,
            }
            key = (workflow_id, publish_sequence, run_id)
            previous = self._publications.get(key)
            if previous is None:
                self._publications[key] = new_entry
                continue
            projection_keys = (
                "workflow_id",
                "workflow_key",
                "run_id",
                "publish_sequence",
                "artifact_id",
                "definition_id",
                "verification_outcome",
                "row_counts",
                "published_at_unix_ms",
                "release_basename",
                "admission_id",
                "attributed_by",
            )
            if any(previous.get(field) != new_entry.get(field) for field in projection_keys):
                previous["changed_after_first_seen"] = True

    def _definition_sources(
        self,
        manifest: Mapping[str, object],
        *,
        definition_dir: Path,
        state_dir: Path,
        inventory_paths: set[str],
        inventory_hashes: Mapping[str, str],
    ) -> tuple[
        list[dict[str, object]],
        list[dict[str, object]],
        list[dict[str, object]],
    ]:
        """Project validation promises, model promises, and input expectations."""

        def source_facts(
            source_value: object,
        ) -> tuple[str | None, str, bool, str | None]:
            source = source_value if isinstance(source_value, str) else None
            parsed = _relative_path(source)
            if parsed is None:
                return (
                    None,
                    "none" if source_value is None else "unknown",
                    False,
                    None,
                )
            relative = parsed.as_posix()
            source_in_inventory = relative in inventory_paths
            within_contracts = parsed.parts[0] == "contracts" and len(parsed.parts) >= 2
            source_file = _within(state_dir, definition_dir.joinpath(*parsed.parts))
            source_exists = (
                source_file is not None
                and source_file.is_file()
            )
            verifier = (
                "script"
                if within_contracts and (source_in_inventory or source_exists)
                else "unknown"
            )
            return (
                relative,
                verifier,
                source_in_inventory,
                inventory_hashes.get(relative),
            )

        def strings(value: object, *, max_items: int = 256) -> list[str]:
            if not isinstance(value, Sequence) or isinstance(
                value, (str, bytes, bytearray)
            ):
                return []
            values: set[str] = set()
            for item in value[:max_items]:
                safe = _safe_string(item, limit=256)
                if safe is not None:
                    values.add(safe)
            return sorted(values)

        def promise(
            item: object,
            *,
            port: str | None,
            source_key: str = "source",
        ) -> dict[str, object] | None:
            if not isinstance(item, Mapping):
                return None
            name = _safe_string(item.get("name"), limit=256)
            if name is None:
                return None
            source, verifier, source_in_inventory, source_sha256 = source_facts(
                item.get(source_key)
            )
            service = item.get("computeService")
            driver = (
                _safe_string(service.get("driver"), limit=256)
                if isinstance(service, Mapping)
                else None
            )
            return {
                "port": port,
                "name": name,
                "description": _safe_string(item.get("description"), limit=2048),
                "models": strings(item.get("models")),
                "source": source,
                "verifier_kind": verifier,
                "source_in_inventory": source_in_inventory,
                "source_sha256": source_sha256,
                "driver": driver,
            }

        output_promises: list[dict[str, object]] = []
        model_promises: list[dict[str, object]] = []
        input_expectations: list[dict[str, object]] = []

        output = manifest.get("output")
        if isinstance(output, Mapping):
            ports = output.get("ports")
            if isinstance(ports, Mapping):
                for raw_port, port_value in ports.items():
                    port = _safe_string(raw_port, limit=128)
                    if port is None or not isinstance(port_value, Mapping):
                        continue
                    promises = port_value.get("promises")
                    if not isinstance(promises, Mapping):
                        continue
                    validations = promises.get("validation")
                    if isinstance(validations, list):
                        for item in validations:
                            projected = promise(item, port=port)
                            if projected is not None:
                                output_promises.append(projected)
                    models = strings(promises.get("model"))
                    if models:
                        model_promises.append({"port": port, "models": models})

            top_promises = output.get("promises")
            if isinstance(top_promises, Mapping):
                validations = top_promises.get("validation")
                if isinstance(validations, list):
                    for item in validations:
                        projected = promise(item, port=None)
                        if projected is not None:
                            output_promises.append(projected)

        inputs = manifest.get("inputs")
        sources = inputs.get("sources") if isinstance(inputs, Mapping) else None
        if isinstance(sources, Mapping):
            for raw_source_name, source_value in sources.items():
                source_name = _safe_string(raw_source_name, limit=256)
                if source_name is None or not isinstance(source_value, Mapping):
                    continue
                expects = source_value.get("expects")
                validations = (
                    expects.get("validation")
                    if isinstance(expects, Mapping)
                    else None
                )
                if not isinstance(validations, list):
                    continue
                for item in validations:
                    projected = promise(item, port=None)
                    if projected is None:
                        continue
                    input_expectations.append(
                        {
                            "source_name": source_name,
                            "name": projected["name"],
                            "models": projected["models"],
                            "source": projected["source"],
                            "verifier_kind": projected["verifier_kind"],
                            "source_in_inventory": projected["source_in_inventory"],
                            "driver": projected["driver"],
                        }
                    )

        output_promises.sort(
            key=lambda item: (
                "" if item["port"] is None else str(item["port"]),
                str(item["name"]),
            )
        )
        model_promises.sort(key=lambda item: str(item["port"]))
        input_expectations.sort(
            key=lambda item: (str(item["source_name"]), str(item["name"]))
        )
        return output_promises, model_promises, input_expectations

    def _update_definition_export(self, state_dir: Path) -> None:
        """Export deterministic manifest metadata for session-run definitions."""

        import yaml

        associations: dict[str, dict[str, set[str]]] = {}
        for run in self._run_records.values():
            definition_id = run.get("definition_id")
            run_id = run.get("run_id")
            workflow_id = run.get("workflow_id")
            if (
                not isinstance(definition_id, str)
                or _DEFINITION_ID_RE.fullmatch(definition_id) is None
                or not isinstance(run_id, str)
                or not isinstance(workflow_id, str)
            ):
                continue
            aggregate = associations.setdefault(
                definition_id, {"run_ids": set(), "workflow_ids": set()}
            )
            aggregate["run_ids"].add(run_id)
            aggregate["workflow_ids"].add(workflow_id)

        # A release is another supervisor-owned source for a session run's
        # definition id when the lifecycle row is absent or incomplete.
        for release in self._publications.values():
            definition_id = release.get("definition_id")
            run_id = release.get("run_id")
            workflow_id = release.get("workflow_id")
            if (
                not isinstance(definition_id, str)
                or _DEFINITION_ID_RE.fullmatch(definition_id) is None
                or not isinstance(run_id, str)
                or not isinstance(workflow_id, str)
            ):
                continue
            aggregate = associations.setdefault(
                definition_id, {"run_ids": set(), "workflow_ids": set()}
            )
            aggregate["run_ids"].add(run_id)
            aggregate["workflow_ids"].add(workflow_id)

        for definition_id, aggregate in associations.items():
            match = _DEFINITION_ID_RE.fullmatch(definition_id)
            if match is None:
                continue
            digest = match.group(1)
            definition_dir = state_dir / "definitions" / "sha256-v1" / digest
            safe_dir = _within(state_dir, definition_dir)
            present = safe_dir is not None and safe_dir.is_dir()
            inventory_paths: set[str] = set()
            inventory_hashes: dict[str, str] = {}
            inventory_valid = False
            if present and safe_dir is not None:
                inventory_path = _within(
                    state_dir, safe_dir / "definition.json"
                )
                inventory = (
                    _read_json(inventory_path)
                    if inventory_path is not None and inventory_path.is_file()
                    else None
                )
                if (
                    isinstance(inventory, Mapping)
                    and inventory.get("schema") == "nxd-definition-manifest-v1"
                    and inventory.get("definition_id") == definition_id
                    and isinstance(inventory.get("files"), list)
                ):
                    entries_valid = True
                    for file_record in inventory["files"]:
                        if not isinstance(file_record, Mapping):
                            entries_valid = False
                            break
                        relative = _relative_path(file_record.get("path"))
                        size = file_record.get("size")
                        digest_value = file_record.get("sha256")
                        valid_size = (
                            isinstance(size, int)
                            and not isinstance(size, bool)
                            and size >= 0
                        ) or (
                            isinstance(size, str)
                            and re.fullmatch(r"[0-9]+", size) is not None
                        )
                        if (
                            relative is None
                            or not valid_size
                            or not isinstance(digest_value, str)
                            or re.fullmatch(
                                r"(?:sha256:)?[0-9a-f]{64}", digest_value
                            )
                            is None
                        ):
                            entries_valid = False
                            break
                        inventory_paths.add(relative.as_posix())
                        inventory_hashes[relative.as_posix()] = digest_value
                    inventory_valid = entries_valid
                    if not inventory_valid:
                        inventory_paths.clear()
                        inventory_hashes.clear()

            manifest: Mapping[str, object] = {}
            if present and safe_dir is not None:
                manifest_path = _within(state_dir, safe_dir / "manifest.yaml")
                if manifest_path is not None and manifest_path.is_file():
                    try:
                        loaded = yaml.safe_load(
                            manifest_path.read_text(encoding="utf-8")
                        )
                    except (OSError, UnicodeError, yaml.YAMLError):
                        loaded = None
                    if isinstance(loaded, Mapping):
                        manifest = loaded

            if manifest:
                output_promises, model_promises, input_expectations = (
                    self._definition_sources(
                        manifest,
                        definition_dir=safe_dir or definition_dir,
                        state_dir=state_dir,
                        inventory_paths=inventory_paths,
                        inventory_hashes=inventory_hashes,
                    )
                )
            else:
                output_promises, model_promises, input_expectations = [], [], []

            entry = {
                "definition_id": definition_id,
                "run_ids": sorted(aggregate["run_ids"]),
                "workflow_ids": sorted(aggregate["workflow_ids"]),
                "present": present,
                "inventory_valid": inventory_valid,
                "output_promises": output_promises,
                "model_promises": model_promises,
                "input_expectations": input_expectations,
            }
            self._definitions.setdefault(definition_id, entry)
            current = self._definitions[definition_id]
            if current.get("definition_id") == definition_id:
                current["run_ids"] = sorted(
                    set(current.get("run_ids", [])) | aggregate["run_ids"]
                )
                current["workflow_ids"] = sorted(
                    set(current.get("workflow_ids", []))
                | aggregate["workflow_ids"]
                )

    def _capture_root(
        self,
        *,
        state_dir: Path,
        digest: str,
    ) -> tuple[Path | None, str | None]:
        """Resolve the digest path under state, rejecting symlinks and escapes."""

        expected = state_dir / "captures" / "sha256" / digest
        resolved = _within(state_dir, expected)
        if resolved is None:
            reason = (
                "missing_capture_root"
                if not expected.exists() and not expected.is_symlink()
                else "capture_path_refused"
            )
            return None, reason
        try:
            relative = resolved.relative_to(state_dir).as_posix()
        except ValueError:
            return None, "capture_path_refused"
        if relative != f"captures/sha256/{digest}":
            return None, "capture_path_refused"
        return resolved, None

    def _capture_marker_paths(self, capture_root: Path, state_dir: Path) -> set[str]:
        """Read only File lines from SENSITIVE markers for copy refusal."""

        paths: set[str] = set()
        marker = capture_root / "SENSITIVE"
        safe_marker = _within(state_dir, marker)
        if safe_marker is None or not safe_marker.is_file():
            return paths
        try:
            text = safe_marker.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            return paths
        for line in text.splitlines():
            if not line.startswith("File:"):
                continue
            relative = _relative_path(line.partition(":")[2].strip())
            if relative is not None:
                paths.add(relative.as_posix())
        return paths

    def _capture_allowed(self, relative: PurePosixPath) -> bool:
        """Return whether a relative path matches the small capture allowlist."""

        parts = relative.parts
        normalized = relative.as_posix()
        if len(parts) == 1 and normalized in _CAPTURE_ALLOW_ROOT_FILES:
            return True
        if (
            len(parts) >= 2
            and parts[0] in {"contracts", "transform"}
            and relative.suffix == ".py"
        ):
            return True
        return False

    def _capture_refusal(self, relative: PurePosixPath, sensitive: set[str]) -> str | None:
        """Return a fixed refusal reason before any capture file is read."""

        normalized = relative.as_posix()
        if normalized in sensitive:
            return "sensitive_marker"
        if any(part.startswith(".env") for part in relative.parts):
            return "environment_file"
        if any(_is_secret_path_component(part) for part in relative.parts):
            return "secret_path_component"
        if (
            any(part == "data" for part in relative.parts)
            or relative.name in _CAPTURE_EXCLUDED_NAMES
        ):
            return "excluded_path"
        if not self._capture_allowed(relative):
            return "not_allowlisted"
        return None

    def _capture_file_refusal(self, content: bytes) -> str | None:
        """Return a fixed reason for undecodable text or credential literals."""

        try:
            content.decode("utf-8")
        except UnicodeError:
            return "redacted_text"
        if any(secret in content for secret in self._secret_values):
            return "secret_value"
        if _credential_literal(content):
            return "credential_literal"
        return None

    def _copy_capture_files(
        self,
        *,
        capture_root: Path,
        state_dir: Path,
        digest: str,
        entry: dict[str, object],
    ) -> None:
        """Copy only safe allowlisted bytes, enforcing both deterministic caps."""

        files: list[dict[str, object]] = []
        skipped: list[dict[str, str]] = []
        truncated = False
        sensitive = self._capture_marker_paths(capture_root, state_dir)
        walk_errors: list[OSError] = []

        def onerror(error: OSError) -> None:
            walk_errors.append(error)

        candidates: list[tuple[Path, PurePosixPath, bool]] = []
        for directory, dirnames, filenames in os.walk(
            capture_root,
            topdown=True,
            followlinks=False,
            onerror=onerror,
        ):
            base = Path(directory)
            dirnames.sort()
            filenames.sort()
            for dirname in list(dirnames):
                child = base / dirname
                if child.is_symlink():
                    try:
                        relative = child.relative_to(capture_root).as_posix()
                    except ValueError:
                        relative = "."
                    skipped.append({"path": relative, "reason": "symlink"})
                    dirnames.remove(dirname)
            for filename in filenames:
                candidate = base / filename
                try:
                    relative = PurePosixPath(
                        candidate.relative_to(capture_root).as_posix()
                    )
                except ValueError:
                    continue
                candidates.append((candidate, relative, candidate.is_symlink()))

        for error in walk_errors:
            skipped.append({"path": ".", "reason": "capture_read_error"})

        candidates.sort(key=lambda item: item[1].as_posix())
        for source, relative, is_symlink in candidates:
            path_text = relative.as_posix()
            if is_symlink:
                skipped.append({"path": path_text, "reason": "symlink"})
                continue
            refusal = self._capture_refusal(relative, sensitive)
            if refusal is not None:
                skipped.append({"path": path_text, "reason": refusal})
                continue
            safe_source = _within(state_dir, source)
            if safe_source is None or not safe_source.is_file():
                skipped.append({"path": path_text, "reason": "capture_path_refused"})
                continue
            try:
                size = safe_source.stat().st_size
            except OSError:
                skipped.append({"path": path_text, "reason": "capture_read_error"})
                continue
            if self._capture_copy_stopped:
                truncated = True
                skipped.append({"path": path_text, "reason": "global_size_cap"})
                continue
            if size > CAPTURE_FILE_LIMIT:
                truncated = True
                self._capture_copy_stopped = True
                skipped.append({"path": path_text, "reason": "per_file_size_cap"})
                break
            if self._capture_copy_bytes + size > CAPTURE_TOTAL_LIMIT:
                truncated = True
                self._capture_copy_stopped = True
                skipped.append({"path": path_text, "reason": "total_size_cap"})
                break
            try:
                content = safe_source.read_bytes()
            except OSError:
                skipped.append({"path": path_text, "reason": "capture_read_error"})
                continue
            if len(content) != size:
                skipped.append({"path": path_text, "reason": "capture_read_error"})
                continue
            refusal = self._capture_file_refusal(content)
            if refusal is not None:
                skipped.append({"path": path_text, "reason": refusal})
                continue
            target = self.artifact_dir / "supervisor-captures" / digest
            target = target.joinpath(*relative.parts)
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
            except OSError:
                skipped.append({"path": path_text, "reason": "snapshot_write_error"})
                continue
            self._capture_copy_bytes += len(content)
            files.append(
                {
                    "path": path_text,
                    "size": len(content),
                    "sha256": "sha256:" + hashlib.sha256(content).hexdigest(),
                }
            )

        prior_files = entry.get("files")
        if isinstance(prior_files, list):
            files = [
                dict(item)
                for item in prior_files
                if isinstance(item, Mapping)
            ] + files
        prior_skipped = entry.get("skipped")
        if isinstance(prior_skipped, list):
            skipped = [
                dict(item)
                for item in prior_skipped
                if isinstance(item, Mapping)
            ] + skipped
        entry["files"] = sorted(
            {
                (item.get("path"), item.get("size"), item.get("sha256")): item
                for item in files
            }.values(),
            key=lambda item: str(item.get("path", "")),
        )
        entry["skipped"] = sorted(
            {
                (item.get("path"), item.get("reason")): item
                for item in skipped
            }.values(),
            key=lambda item: (str(item.get("path", "")), str(item.get("reason", ""))),
        )
        entry["truncated"] = bool(entry.get("truncated")) or truncated

    def _update_capture_snapshots(
        self,
        *,
        turn: int,
        state_dir: Path,
        attributed: Mapping[str, Mapping[str, object]],
    ) -> None:
        """Snapshot admission captures and matching successful capture results."""

        by_digest: dict[str, dict[str, object]] = {}
        for run_id, run in self._run_records.items():
            if run_id not in attributed:
                continue
            capture_sha256 = run.get("capture_sha256")
            match = (
                _CAPTURE_SHA_RE.fullmatch(capture_sha256)
                if isinstance(capture_sha256, str)
                else None
            )
            if match is None:
                continue
            digest = match.group(1)
            group = by_digest.setdefault(
                digest,
                {
                    "run_ids": set(),
                    "workflow_ids": set(),
                    "sources": {"admission"},
                    "first_turn": int(run.get("start_turn", turn)),
                    "capture_id": None,
                },
            )
            group["run_ids"].add(run_id)
            workflow_id = run.get("workflow_id")
            if isinstance(workflow_id, str):
                group["workflow_ids"].add(workflow_id)
            group["first_turn"] = min(
                int(group["first_turn"]),
                int(run.get("start_turn", turn)),
            )
            if group["capture_id"] is None and isinstance(run.get("capture_id"), str):
                group["capture_id"] = run.get("capture_id")

        # Capture results can also be the only evidence of a capture when the
        # operator is still preparing review and has not admitted a run. Only
        # the validated digest suffix is used; the observed host-path prefix
        # never enters path resolution or durable history.
        for digest, candidates in self._capture_results.items():
            capture_root, reason = self._capture_root(
                state_dir=state_dir,
                digest=digest,
            )
            if capture_root is None and reason == "missing_capture_root":
                continue
            group = by_digest.get(digest)
            if group is None:
                group = by_digest.setdefault(
                    digest,
                    {
                        "run_ids": set(),
                        "workflow_ids": set(),
                        "sources": {"capture_result"},
                        "first_turn": turn,
                        "capture_id": None,
                    },
                )
            for candidate in candidates:
                candidate_workflow = candidate.get("workflow_id")
                if (
                    isinstance(candidate_workflow, str)
                    and group["run_ids"]
                    and candidate_workflow not in group["workflow_ids"]
                ):
                    continue
                group["sources"].add("capture_result")
                if isinstance(candidate_workflow, str):
                    group["workflow_ids"].add(candidate_workflow)
                candidate_turn = candidate.get("turn")
                if isinstance(candidate_turn, int) and not isinstance(candidate_turn, bool):
                    group["first_turn"] = min(int(group["first_turn"]), candidate_turn)

        for digest, group in sorted(
            by_digest.items(),
            key=lambda item: (int(item[1]["first_turn"]), item[0]),
        ):
            prior = self._captures.get(digest)
            if prior is None:
                entry: dict[str, object] = {
                    "capture_sha256": "sha256:" + digest,
                    "capture_id": group["capture_id"],
                    "workflow_ids": sorted(group["workflow_ids"]),
                    "run_ids": sorted(group["run_ids"]),
                    "first_turn": int(group["first_turn"]),
                    "sources": sorted(group["sources"]),
                    "files": [],
                    "skipped": [],
                    "truncated": False,
                }
                self._captures[digest] = entry
            else:
                entry = prior
                entry["workflow_ids"] = sorted(
                    set(entry.get("workflow_ids", [])) | group["workflow_ids"]
                )
                entry["run_ids"] = sorted(
                    set(entry.get("run_ids", [])) | group["run_ids"]
                )
                entry["sources"] = sorted(
                    set(entry.get("sources", [])) | group["sources"]
                )
                entry["first_turn"] = min(
                    int(entry.get("first_turn", group["first_turn"])),
                    int(group["first_turn"]),
                )
            if prior is not None:
                continue

            capture_root, capture_reason = self._capture_root(
                state_dir=state_dir,
                digest=digest,
            )
            if capture_root is not None:
                self._copy_capture_files(
                    capture_root=capture_root,
                    state_dir=state_dir,
                    digest=digest,
                    entry=entry,
                )
            else:
                entry["skipped"] = [
                    {
                        "path": ".",
                        "reason": capture_reason or "missing_capture_root",
                    }
                ]

    def write(self) -> None:
        """Write the seven canonical JSON histories without changing legacy files."""

        self._load_existing()
        _write_json(
            self.artifact_dir / "tool-calls.json",
            {
                "schema": TOOL_CALLS_SCHEMA,
                "last_turn": self._last_turn,
                "calls": [
                    self._tool_calls[key]
                    for key in sorted(self._tool_calls)
                ],
                "endpoints": dict(sorted(self._endpoints.items())),
            },
        )
        _write_json(
            self.artifact_dir / "query-history.json",
            {
                "schema": QUERY_HISTORY_SCHEMA,
                "dropped": self._queries_dropped,
                "queries": list(self._queries[-QUERY_HISTORY_LIMIT:]),
            },
        )

        has_tool_failure = any(
            entry.get("source") == "tool_result"
            for entry in self._failures.values()
        )
        if self._state_artifacts_enabled or has_tool_failure:
            failures = sorted(
                self._failures.values(),
                key=lambda entry: (
                    int(entry.get("turn", 0)),
                    str(entry.get("workflow_id") or ""),
                    str(entry.get("source") or ""),
                    str(entry.get("operation_id") or ""),
                    str(entry.get("run_id") or ""),
                    str(entry.get("request_id") or ""),
                ),
            )
            _write_json(
                self.artifact_dir / "run-failures.json",
                {"schema": RUN_FAILURES_SCHEMA, "failures": failures},
            )

        if not self._state_artifacts_enabled:
            return
        publications = sorted(
            self._publications.values(),
            key=lambda entry: (
                int(entry.get("turn", 0)),
                str(entry.get("workflow_id", "")),
                int(str(entry.get("publish_sequence", "0"))),
                str(entry.get("run_id", "")),
            ),
        )
        _write_json(
            self.artifact_dir / "publication-history.json",
            {"schema": PUBLICATION_SCHEMA, "releases": publications},
        )
        runs = sorted(
            self._run_records.values(),
            key=lambda entry: (
                int(entry.get("start_turn", 0)),
                str(entry.get("workflow_id") or ""),
                str(entry.get("run_id") or ""),
            ),
        )
        _write_json(
            self.artifact_dir / "run-records.json",
            {"schema": RUN_RECORDS_SCHEMA, "runs": runs},
        )
        definitions = sorted(
            self._definitions.values(),
            key=lambda entry: str(entry.get("definition_id", "")),
        )
        _write_json(
            self.artifact_dir / "definition-export.json",
            {"schema": DEFINITION_EXPORT_SCHEMA, "definitions": definitions},
        )
        captures = sorted(
            self._captures.values(),
            key=lambda entry: (
                int(entry.get("first_turn", 0)),
                str(entry.get("capture_sha256", "")),
            ),
        )
        _write_json(
            self.artifact_dir / "supervisor-captures.json",
            {"schema": CAPTURES_SCHEMA, "captures": captures},
        )


__all__ = [
    "CAPTURES_SCHEMA",
    "CAPTURE_FILE_LIMIT",
    "CAPTURE_TOTAL_LIMIT",
    "DEFINITION_EXPORT_SCHEMA",
    "PUBLICATION_SCHEMA",
    "QUERY_HISTORY_LIMIT",
    "QUERY_HISTORY_SCHEMA",
    "RUN_FAILURES_SCHEMA",
    "RUN_RECORDS_SCHEMA",
    "SupervisorHistory",
    "TOOL_CALLS_SCHEMA",
]
