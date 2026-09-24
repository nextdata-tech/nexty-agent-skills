#!/usr/bin/env python3
"""Runner-owned stdio MCP plumbing for terminal Desktop evals.

The scenario runner must not inherit Claude Desktop's global MCP registry. A
DesktopStdioSession writes a private, strict MCP config and points it at this
module's small proxy. The runner starts exactly one server child behind a
credential-free local bridge; the proxy forwards newline-delimited JSON-RPC and
records a redacted trace. It is intentionally stdlib-only so setup is usable
before the Desktop Python environment is ready.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import datetime as _dt
import io
import json
import math
import os
import re
import secrets
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Mapping, Sequence


REDACTED = "<redacted>"
_SECRET_KEY = re.compile(
    r"(?:password|passwd|secret|token|api[_-]?key|access[_-]?key|"
    r"authorization|cookie|credential|bearer|private[_-]?key|grant)",
    re.IGNORECASE,
)
_BEARER = re.compile(r"(?i)(\bbearer\s+)[A-Za-z0-9._~+/=-]+")
_URL_AUTH = re.compile(
    r"([a-z][a-z0-9+.-]*://)([^/@\s:]+):([^/@\s]+)@", re.IGNORECASE
)
_QUERY_SECRET = re.compile(
    r"(?i)([?&](?:token|api[_-]?key|secret|password|authorization)=)[^&#\s]+"
)
_ASSIGN_SECRET = re.compile(
    r"(?i)((?<![A-Za-z0-9_])(?:token|api[_-]?key|secret|password|"
    r"authorization|cookie|credential|bearer|private[_-]?key|grant|"
    r"passwd|access[_-]?key|aws[_-]?secret[_-]?access[_-]?key|"
    r"pg\w*password)\s*(?:[:=]|\bis\b)\s*)[^\s,;]+"
)
# The allowlist carries only environment-variable *names*, not credential
# values.  It is needed by the supervisor to validate the explicit source
# credential above, so it must survive the proxy's credential-key filter.
_TRUSTED_CREDENTIAL_MAPPING_ENV = "NXD_DESKTOP_TRUSTED_CREDENTIAL_ENVS"
_TRUSTED_EXPLICIT_SECRET_KEYS = frozenset(
    {
        "NXD_EVAL_SOURCE_TOKEN",
        _TRUSTED_CREDENTIAL_MAPPING_ENV,
    }
)
_TRUSTED_CREDENTIAL_MAPPING_ENTRY = re.compile(
    r"(?P<service>[A-Za-z0-9._-]+)=(?P<variable>[A-Za-z_][A-Za-z0-9_]*)\Z"
)
_SOURCE_SERVICE_NAME = "api-source"
_SOURCE_CREDENTIAL_ENV = "NXD_EVAL_SOURCE_TOKEN"
_MAX_TRUSTED_CREDENTIAL_MAPPING_ENTRIES = 16
_MAX_TRUSTED_CREDENTIAL_MAPPING_LENGTH = 4096
_REVIEW_PENDING_BLOCKED_OPERATIONS = frozenset(
    {
        "reset_workflow",
        "list_data_products",
        "inspect_workflow",
        "check_data_product",
        "prepare_workflow",
        "get_workflow_capabilities",
    }
)
_REVIEW_READER_TOOL = "read_review_input"
_REVIEW_READER_MAX_BYTES = 128 * 1024
_REVIEW_READER_MAX_LINES = 500
_REVIEW_READER_MAX_SOURCE_BYTES = 1024 * 1024
_REVIEW_READER_TRUNCATION_MARKER = "\n[runner output truncated]\n"
_REVIEW_READER_DENIED_NAMES = frozenset(
    {
        ".env",
        "credentials",
        "credential",
        "secrets",
        "secret",
        "sensitive",
        "id_rsa",
    }
)


def _safe_trusted_credential_mappings(
    value: str, available_keys: set[str]
) -> list[str]:
    """Return only bounded service-to-environment-name mappings."""

    if len(value) > _MAX_TRUSTED_CREDENTIAL_MAPPING_LENGTH:
        return []
    entries = [entry.strip() for entry in value.split(",") if entry.strip()]
    if len(entries) > _MAX_TRUSTED_CREDENTIAL_MAPPING_ENTRIES:
        return []
    valid: list[str] = []
    services: set[str] = set()
    for entry in entries:
        match = _TRUSTED_CREDENTIAL_MAPPING_ENTRY.fullmatch(entry)
        if match is None:
            return []
        service = match["service"]
        if service in services:
            return []
        services.add(service)
        variable = match["variable"]
        if (
            variable == _SOURCE_CREDENTIAL_ENV
            and service != _SOURCE_SERVICE_NAME
        ) or (
            service == _SOURCE_SERVICE_NAME
            and variable != _SOURCE_CREDENTIAL_ENV
        ):
            return []
        if variable not in available_keys:
            continue
        valid.append(f"{service}={variable}")

    return valid


def _safe_server_environment(server_env: Mapping[str, str]) -> dict[str, str]:
    """Build the supervisor environment without retaining untrusted secrets."""

    env = {
        key: os.environ[key]
        for key in ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL")
        if os.environ.get(key)
    }
    env.update({str(key): str(value) for key, value in server_env.items()})
    mapping_key = _TRUSTED_CREDENTIAL_MAPPING_ENV
    raw_mapping = env.get(mapping_key)
    entries = (
        _safe_trusted_credential_mappings(raw_mapping, set(env))
        if raw_mapping is not None
        else []
    )
    trusted_mapping_variables = {
        entry.split("=", 1)[1] for entry in entries
    }
    for key in tuple(env):
        if (
            _SECRET_KEY.search(key)
            and key not in _TRUSTED_EXPLICIT_SECRET_KEYS
            and key not in trusted_mapping_variables
        ):
            env.pop(key, None)
    if entries:
        env[mapping_key] = ",".join(entries)
    else:
        env.pop(mapping_key, None)
    # The source token is meaningful only with the runner-generated mapping.
    # This also closes the direct-session path when a caller supplies the
    # reserved variable without its matching service declaration.
    if _SOURCE_CREDENTIAL_ENV not in trusted_mapping_variables:
        env.pop(_SOURCE_CREDENTIAL_ENV, None)
    return env


PROXY_MODULE = Path(__file__).resolve()
_TRACE_LOCK = threading.Lock()


def _write_private_text(path: Path, text: str) -> None:
    """Atomically create/truncate a runner-owned file with mode 0600."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            fd = -1
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        if fd != -1:
            os.close(fd)
        with contextlib.suppress(FileNotFoundError):
            temporary_path.unlink()


def redact_json_rpc(value: Any, *, key: str = "") -> Any:
    """Recursively redact credentials before a JSON-RPC value is persisted."""
    if _SECRET_KEY.search(key):
        return REDACTED
    if isinstance(value, Mapping):
        return {str(k): redact_json_rpc(v, key=str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_json_rpc(v, key=key) for v in value]
    if isinstance(value, tuple):
        return [redact_json_rpc(v, key=key) for v in value]
    if isinstance(value, str):
        value = _URL_AUTH.sub(r"\1" + REDACTED + "@", value)
        value = _BEARER.sub(r"\1" + REDACTED, value)
        value = _QUERY_SECRET.sub(r"\1" + REDACTED, value)
        value = _ASSIGN_SECRET.sub(r"\1" + REDACTED, value)
        return value
    return value


def redact_text(value: str) -> str:
    """Redact free-form diagnostics without retaining raw server output."""
    return str(redact_json_rpc(value))


def _review_allowlist_payload(state: Mapping[str, Any] | None) -> dict[str, str]:
    """Extract only the two supervisor-bound paths used by a review child."""

    review_input = state.get("review_input") if isinstance(state, Mapping) else None
    if not isinstance(review_input, Mapping):
        return {}
    paths: dict[str, str] = {}
    for key in ("retained_capture_root", "retained_blueprint_path"):
        value = review_input.get(key)
        if isinstance(value, str) and value.strip():
            paths[key] = value
    return paths


def _review_reader_tool_definition() -> dict[str, Any]:
    """Describe the runner-owned bounded reader exposed to a Codex child."""

    return {
        "name": _REVIEW_READER_TOOL,
        "description": (
            "Runner-owned, read-only access to the exact current supervisor "
            "review_input paths. Use only for the CODEX_REVIEW_CHILD review; "
            "writes, execution, network access, and other paths are rejected."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "operation": {"type": "string", "enum": ["read", "list"]},
                "max_lines": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": _REVIEW_READER_MAX_LINES,
                },
                "max_bytes": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": _REVIEW_READER_MAX_BYTES,
                },
            },
            "required": ["path", "operation"],
            "additionalProperties": False,
        },
    }


def _review_reader_error(message: str) -> dict[str, Any]:
    payload = {"error": message}
    return {
        "isError": True,
        "structuredContent": payload,
        "content": [{"type": "text", "text": json.dumps(payload, sort_keys=True)}],
    }


def _review_utf8_prefix(value: str, max_bytes: int) -> str:
    """Return a UTF-8 prefix no larger than max_bytes, ending on a code point."""

    return value.encode("utf-8")[:max_bytes].decode("utf-8", errors="ignore")


def _review_entry_is_sensitive(name: str) -> bool:
    """Return whether a review-reader path component is credential-shaped."""

    lowered = name.casefold()
    return (
        lowered in _REVIEW_READER_DENIED_NAMES
        or lowered.startswith(".env.")
        or lowered.endswith((".pem", ".key", ".p12", ".pfx"))
    )


def _review_reader_roots(
    allowlist_path: Path,
) -> tuple[list[tuple[Path, Path, bool]], str | None]:
    """Load and validate the current review roots without exposing values."""

    try:
        raw = json.loads(allowlist_path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return [], "review input allowlist is unavailable"
    if not isinstance(raw, Mapping):
        return [], "review input allowlist is malformed"
    roots: list[tuple[Path, Path, bool]] = []
    for key, is_directory in (
        ("retained_capture_root", True),
        ("retained_blueprint_path", False),
    ):
        value = raw.get(key)
        if not isinstance(value, str) or not value.strip():
            continue
        if "\x00" in value:
            return [], "review input allowlist contains an invalid path"
        root = Path(value)
        if ".." in root.parts:
            return [], "review input allowlist contains parent traversal"
        if not root.is_absolute():
            return [], "review input allowlist contains a non-absolute path"
        try:
            resolved_root = root.resolve(strict=True)
        except (OSError, RuntimeError, ValueError):
            return [], "review input root is unavailable"
        if is_directory and not resolved_root.is_dir():
            return [], "retained capture root is not a directory"
        if not is_directory and not resolved_root.is_file():
            return [], "retained blueprint path is not a regular file"
        roots.append((root, resolved_root, is_directory))
    if not roots:
        return [], "review input allowlist is empty"
    return roots, None


@dataclasses.dataclass(frozen=True)
class _ReviewReaderPath:
    """Resolved access path plus the allowlist-spelled path shown to the child."""

    resolved: Path
    display: Path


def _review_request_path_error(path_value: object) -> str | None:
    """Validate the caller-supplied path before loading the allowlist."""

    if not isinstance(path_value, str) or not path_value.strip():
        return "path must be a non-empty absolute path"
    if "\x00" in path_value:
        return "path contains an invalid character"
    requested = Path(path_value)
    if not requested.is_absolute():
        return "path must be absolute"
    if ".." in requested.parts:
        return "path must not contain parent traversal"
    if any(_review_entry_is_sensitive(part) for part in requested.parts):
        return "requested review path is sensitive"
    if redact_text(path_value) != path_value:
        return "requested review path cannot be shown verbatim"
    return None


def _review_reader_path(
    path_value: object,
    allowlist_path: Path,
    *,
    roots: list[tuple[Path, Path, bool]] | None = None,
) -> tuple[_ReviewReaderPath | None, str | None]:
    """Resolve a requested review path against the current private allowlist."""

    request_error = _review_request_path_error(path_value)
    if request_error is not None:
        return None, request_error
    assert isinstance(path_value, str)
    requested = Path(path_value)
    if roots is None:
        roots, error = _review_reader_roots(allowlist_path)
        if error is not None:
            return None, error
    try:
        resolved = requested.resolve(strict=True)
    except (OSError, RuntimeError):
        return None, "requested review path is unavailable"
    if any(
        _review_entry_is_sensitive(part)
        for part in resolved.parts
    ):
        return None, "requested review path is sensitive"
    for written_root, resolved_root, is_directory in roots:
        if resolved == resolved_root or (
            is_directory and resolved_root in resolved.parents
        ):
            relative = resolved.relative_to(resolved_root)
            display = written_root / relative
            if redact_text(str(display)) != str(display):
                return None, "requested review path cannot be shown verbatim"
            return _ReviewReaderPath(resolved, display), None
    return None, "requested review path is outside the current review_input"


def _review_list_trailer(
    *, total: int, withheld: int, max_lines: int, max_bytes: int
) -> str:
    return (
        f"\n[{total} entries omitted: withheld={withheld} "
        f"max_lines={max_lines} max_bytes={max_bytes}]"
    )


def _review_reader_list(
    reader_path: _ReviewReaderPath,
    *,
    roots: list[tuple[Path, Path, bool]],
    allowlist_path: Path,
    max_lines: int,
    max_bytes: int,
) -> tuple[dict[str, Any] | None, str | None]:
    """Build a deterministic, bounded directory result with omission reasons."""

    resolved_directory = reader_path.resolved
    if not resolved_directory.is_dir():
        return None, "list requires a directory"

    withheld = 0
    candidates: list[dict[str, str]] = []
    for entry in sorted(resolved_directory.iterdir(), key=lambda item: item.name):
        if _review_entry_is_sensitive(entry.name):
            withheld += 1
            continue
        child_path, child_error = _review_reader_path(
            str(reader_path.display / entry.name), allowlist_path, roots=roots
        )
        if child_error is not None or child_path is None:
            withheld += 1
            continue
        resolved_child = child_path.resolved
        if not resolved_child.is_dir() and not resolved_child.is_file():
            withheld += 1
            continue
        candidates.append(
            {
                "name": entry.name,
                "path": str(child_path.display),
                "kind": "directory" if resolved_child.is_dir() else "file",
            }
        )

    def encoded_entries(entries: list[dict[str, str]]) -> str:
        return json.dumps(entries, sort_keys=True)

    visible: list[dict[str, str]] = []
    cut_reason: str | None = None
    for candidate in candidates:
        if len(visible) >= max_lines:
            cut_reason = "max_lines"
            break
        next_visible = [*visible, candidate]
        if len(encoded_entries(next_visible).encode("utf-8")) > max_bytes:
            cut_reason = "max_bytes"
            break
        visible = next_visible
    omitted_candidates = len(candidates) - len(visible)
    if withheld == 0 and omitted_candidates == 0:
        text = encoded_entries(visible)
        if len(text.encode("utf-8")) > max_bytes:
            return None, "max_bytes too small to list review directory"
        return {"path": str(reader_path.display), "entries": visible, "text": text}, None

    total_entries = withheld + len(candidates)
    reserve = len(
        _review_list_trailer(
            total=total_entries,
            withheld=total_entries,
            max_lines=total_entries,
            max_bytes=total_entries,
        ).encode("utf-8")
    )
    if max_bytes < len("[]".encode("utf-8")) + reserve:
        return None, "max_bytes too small to list review directory"

    visible = []
    cut_reason = None
    for candidate in candidates:
        if len(visible) >= max_lines:
            cut_reason = "max_lines"
            break
        next_visible = [*visible, candidate]
        if len(encoded_entries(next_visible).encode("utf-8")) + reserve > max_bytes:
            cut_reason = "max_bytes"
            break
        visible = next_visible
    omitted_candidates = len(candidates) - len(visible)
    omitted_lines = omitted_candidates if cut_reason == "max_lines" else 0
    omitted_bytes = omitted_candidates if cut_reason == "max_bytes" else 0
    total_omitted = withheld + omitted_lines + omitted_bytes
    trailer = _review_list_trailer(
        total=total_omitted,
        withheld=withheld,
        max_lines=omitted_lines,
        max_bytes=omitted_bytes,
    )
    text = encoded_entries(visible) + trailer
    structured = {
        "path": str(reader_path.display),
        "entries": visible,
        "omitted": {
            "total": total_omitted,
            "withheld": withheld,
            "max_lines": omitted_lines,
            "max_bytes": omitted_bytes,
        },
    }
    return {**structured, "text": text}, None


def _review_reader_result(
    request: Mapping[str, Any], allowlist_path: Path
) -> dict[str, Any]:
    """Serve one bounded, read-only review-input request."""

    params = request.get("params")
    arguments = params.get("arguments") if isinstance(params, Mapping) else None
    if not isinstance(arguments, Mapping):
        return _review_reader_error("arguments must be an object")
    path_value = arguments.get("path")
    request_error = _review_request_path_error(path_value)
    if request_error is not None:
        return _review_reader_error(request_error)
    roots, error = _review_reader_roots(allowlist_path)
    if error is not None:
        return _review_reader_error(error)
    reader_path, error = _review_reader_path(
        path_value, allowlist_path, roots=roots
    )
    if error is not None:
        return _review_reader_error(error)
    assert reader_path is not None

    operation = arguments.get("operation")
    if not isinstance(operation, str) or operation not in {"read", "list"}:
        return _review_reader_error("operation must be read or list")
    max_lines = arguments.get("max_lines", _REVIEW_READER_MAX_LINES)
    max_bytes = arguments.get("max_bytes", _REVIEW_READER_MAX_BYTES)
    if (
        isinstance(max_lines, bool)
        or not isinstance(max_lines, int)
        or not 1 <= max_lines <= _REVIEW_READER_MAX_LINES
        or isinstance(max_bytes, bool)
        or not isinstance(max_bytes, int)
        or not 1 <= max_bytes <= _REVIEW_READER_MAX_BYTES
    ):
        return _review_reader_error("read bounds are outside the permitted limits")

    path = str(reader_path.display)
    try:
        if operation == "list":
            result, error = _review_reader_list(
                reader_path,
                roots=roots,
                allowlist_path=allowlist_path,
                max_lines=max_lines,
                max_bytes=max_bytes,
            )
            if error is not None:
                return _review_reader_error(error)
            assert result is not None
            text = result.pop("text")
            structured = result
        else:
            resolved_file = reader_path.resolved
            if not resolved_file.is_file():
                return _review_reader_error("read requires a regular file")
            with resolved_file.open("rb") as source_file:
                raw_bytes = source_file.read(_REVIEW_READER_MAX_SOURCE_BYTES + 1)
            source_truncated = len(raw_bytes) > _REVIEW_READER_MAX_SOURCE_BYTES
            if source_truncated:
                raw_bytes = raw_bytes[:_REVIEW_READER_MAX_SOURCE_BYTES]
            selected_lines: list[bytes] = []
            offset = 0
            while len(selected_lines) < max_lines:
                newline = raw_bytes.find(b"\n", offset)
                if newline < 0:
                    if offset < len(raw_bytes) and not source_truncated:
                        selected_lines.append(raw_bytes[offset:])
                        offset = len(raw_bytes)
                    break
                selected_lines.append(raw_bytes[offset : newline + 1])
                offset = newline + 1
            line_truncated = source_truncated or offset < len(raw_bytes)
            body = redact_text(
                b"".join(selected_lines).decode("utf-8", errors="replace")
            )
            prefix = f"Path: {path}\n"
            prefix_bytes = len(prefix.encode("utf-8"))
            body_bytes = len(body.encode("utf-8"))
            truncated = line_truncated or prefix_bytes + body_bytes > max_bytes
            if truncated:
                marker = _REVIEW_READER_TRUNCATION_MARKER
                remaining = max_bytes - prefix_bytes - len(marker.encode("utf-8"))
                if remaining <= 0:
                    return _review_reader_error("max_bytes too small for review path")
                body = _review_utf8_prefix(body, remaining) + marker
            text = prefix + body
            structured = {"path": path, "text": body, "truncated": truncated}
    except (OSError, UnicodeError) as exc:
        return _review_reader_error(f"review input read failed: {redact_text(str(exc))}")
    return {
        "isError": False,
        "structuredContent": structured,
        "content": [{"type": "text", "text": text}],
    }


def _review_reader_trace_metadata(
    request: Mapping[str, Any],
    result: Mapping[str, Any],
    allowlist_path: Path,
    *,
    elapsed_ms: float,
) -> dict[str, Any]:
    """Summarize a review-reader call without retaining paths or file text."""

    params = request.get("params")
    arguments = params.get("arguments") if isinstance(params, Mapping) else None
    arguments = arguments if isinstance(arguments, Mapping) else {}
    operation_value = arguments.get("operation")
    operation = (
        operation_value
        if isinstance(operation_value, str) and operation_value in {"read", "list"}
        else "invalid"
    )
    # Derive the trace class through the same validator as the user-visible
    # result; otherwise the trace could classify malformed input differently.
    path, path_error = _review_reader_path(arguments.get("path"), allowlist_path)
    path_class = "invalid_allowlist"
    path_depth: int | None = None
    if path_error is None and path is not None:
        roots, roots_error = _review_reader_roots(allowlist_path)
        if roots_error is None:
            for _, resolved_root, is_directory in roots:
                if path.resolved == resolved_root or (
                    is_directory and resolved_root in path.resolved.parents
                ):
                    path_class = "capture_root" if is_directory else "blueprint"
                    path_depth = (
                        len(path.resolved.relative_to(resolved_root).parts)
                        if is_directory
                        else 0
                    )
                    break
        else:
            path_class = "invalid_allowlist"
    elif path_error == "path must be absolute":
        path_class = "relative"
    elif path_error == "requested review path is outside the current review_input":
        path_class = "outside_allowlist"
    elif path_error == "requested review path is sensitive":
        path_class = "sensitive"
    elif path_error in {
        "requested review path is unavailable",
        "review input root is unavailable",
    }:
        path_class = "unavailable"
    elif path_error is not None and path_error not in {
        "review input allowlist is unavailable",
        "review input allowlist is malformed",
        "review input allowlist contains an invalid path",
        "review input allowlist contains parent traversal",
        "review input allowlist contains a non-absolute path",
        "retained capture root is not a directory",
        "retained blueprint path is not a regular file",
        "review input allowlist is empty",
    }:
        path_class = "invalid"

    max_lines = arguments.get("max_lines", _REVIEW_READER_MAX_LINES)
    max_bytes = arguments.get("max_bytes", _REVIEW_READER_MAX_BYTES)
    limits_valid = (
        isinstance(max_lines, int)
        and not isinstance(max_lines, bool)
        and 1 <= max_lines <= _REVIEW_READER_MAX_LINES
        and isinstance(max_bytes, int)
        and not isinstance(max_bytes, bool)
        and 1 <= max_bytes <= _REVIEW_READER_MAX_BYTES
    )
    structured = result.get("structuredContent")
    structured = structured if isinstance(structured, Mapping) else {}
    error_message = structured.get("error")
    error_codes = {
        "arguments must be an object": "invalid_arguments",
        "path must be a non-empty absolute path": "invalid_path",
        "path contains an invalid character": "path_invalid_character",
        "path must be absolute": "relative_path",
        "path must not contain parent traversal": "path_parent_traversal",
        "requested review path is sensitive": "sensitive_path",
        "requested review path cannot be shown verbatim": "path_not_verbatim",
        "review input allowlist is unavailable": "allowlist_unavailable",
        "review input allowlist is malformed": "allowlist_malformed",
        "review input allowlist contains an invalid path": "allowlist_path_invalid_character",
        "review input allowlist contains parent traversal": "allowlist_parent_traversal",
        "review input allowlist contains a non-absolute path": "allowlist_path_invalid",
        "review input root is unavailable": "allowlist_root_unavailable",
        "retained capture root is not a directory": "capture_root_invalid",
        "retained blueprint path is not a regular file": "blueprint_invalid",
        "review input allowlist is empty": "allowlist_empty",
        "requested review path is unavailable": "path_unavailable",
        "requested review path is outside the current review_input": "path_outside_allowlist",
        "operation must be read or list": "invalid_operation",
        "read bounds are outside the permitted limits": "invalid_bounds",
        "max_bytes too small for review path": "max_bytes_below_prefix",
        "max_bytes too small to list review directory": "max_bytes_below_trailer",
        "list requires a directory": "not_directory",
        "read requires a regular file": "not_file",
    }
    if result.get("isError") is True:
        if isinstance(error_message, str) and error_message.startswith("review input read failed:"):
            error_code = "read_failed"
        else:
            error_code = (
                error_codes.get(error_message, "reader_error")
                if isinstance(error_message, str)
                else "reader_error"
            )
    else:
        error_code = "ok"

    content = result.get("content")
    text_value = (
        content[0].get("text")
        if isinstance(content, list)
        and content
        and isinstance(content[0], Mapping)
        and isinstance(content[0].get("text"), str)
        else ""
    )
    summary: dict[str, Any] = {
        "operation": operation,
        "path_class": path_class,
        "limits_valid": limits_valid,
        "error_code": error_code,
        "output_bytes": len(text_value.encode("utf-8")),
        "truncated": bool(structured.get("truncated", False)),
        "elapsed_ms": round(max(0.0, elapsed_ms), 3),
    }
    if path_depth is not None:
        summary["path_depth"] = path_depth
    if operation == "list" and error_code == "ok":
        entries = structured.get("entries")
        if isinstance(entries, list):
            summary["returned_entries"] = len(entries)
        omitted = structured.get("omitted")
        if isinstance(omitted, Mapping):
            counts = {
                "total": "omitted_total",
                "withheld": "omitted_withheld",
                "max_lines": "omitted_max_lines",
                "max_bytes": "omitted_max_bytes",
            }
            valid_counts = all(
                isinstance(omitted.get(key), int)
                and not isinstance(omitted.get(key), bool)
                and omitted[key] >= 0
                for key in counts
            )
            if valid_counts:
                summary.update({output: omitted[key] for key, output in counts.items()})
                summary["truncated"] = omitted["total"] > 0
    return summary


def _trace_review_reader_summary(path: Path, summary: Mapping[str, Any]) -> None:
    """Write only safe metadata for a review-reader call to the MCP trace."""

    record = {
        "source": "runner",
        "protocol": "mcp",
        "timestamp": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "direction": "summary",
        "message": {
            "method": "tools/call",
            "params": {"name": _REVIEW_READER_TOOL},
        },
        "review_reader_summary": dict(summary),
        "forwarded": False,
        "synthetic": True,
    }
    with _TRACE_LOCK:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")


def _augment_tools_list(
    message: Mapping[str, Any], *, allowlist_path: Path
) -> dict[str, Any]:
    """Keep the reader in the catalog while the allowlist gates every call.

    Codex app-server caches the MCP tool catalog for the parent thread, and
    clients that do consult that catalog need the name before capture. Waiting
    to advertise this synthetic tool until after capture therefore makes it
    invisible to those clients: the allowlist is valid by the time the child
    runs, but the client received the earlier catalog. Advertising the name
    from startup fixes that discovery path; some app-server versions still do
    not propagate MCP tools into collaboration children, so the Codex adapter
    has a strictly read-only fallback for that boundary. The
    ``_review_reader_result`` still fails closed until the runner publishes the
    exact current review paths, so catalog visibility does not grant access to
    any path.
    """

    augmented = dict(message)
    result = message.get("result")
    if not isinstance(result, Mapping) or not isinstance(result.get("tools"), list):
        return augmented
    result_copy = dict(result)
    tools = list(result["tools"])
    if not any(
        isinstance(tool, Mapping) and tool.get("name") == _REVIEW_READER_TOOL
        for tool in tools
    ):
        tools.append(_review_reader_tool_definition())
    result_copy["tools"] = tools
    augmented["result"] = result_copy
    return augmented


@dataclasses.dataclass(frozen=True)
class StdioOutcome:
    """One independently attributable part of a Desktop eval run."""

    status: str
    error: str | None = None
    exit_code: int | None = None
    trace_path: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


class DesktopStdioError(RuntimeError):
    """Invalid runner setup or a proxy lifecycle failure."""


@dataclasses.dataclass
class _PendingRequest:
    """One runner-injected deadline that is still waiting for the child."""

    request_key: str
    request_id: Any
    method: str
    timeout_ms: int
    started_at: float
    timer: threading.Timer | None = None
    timed_out: bool = False


@dataclasses.dataclass
class _TimeoutFault:
    after_ms: int
    remaining: int | None = None
    workflow: str | None = None


def _rpc_id_key(value: Any) -> str | None:
    """Return a collision-safe key for JSON-RPC scalar request IDs."""
    if value is None or isinstance(value, bool):
        return None
    if not isinstance(value, (str, int, float)):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return f"{type(value).__name__}:{json.dumps(value, separators=(',', ':'), sort_keys=True)}"


def _timeout_faults(raw: Any) -> dict[str, _TimeoutFault]:
    """Validate the opt-in operation -> deadline configuration from server-spec."""
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise ValueError("request_timeout_faults must be an object")
    faults: dict[str, _TimeoutFault] = {}
    for method, value in raw.items():
        if not isinstance(method, str) or not method:
            raise ValueError("request_timeout_faults method names must be non-empty strings")
        once = False
        workflow: str | None = None
        if isinstance(value, Mapping):
            once = value.get("once", False)
            workflow_value = value.get("workflow")
            if workflow_value is not None:
                if not isinstance(workflow_value, str) or not workflow_value:
                    raise ValueError(
                        f"request_timeout_faults[{method!r}] workflow must be a non-empty string"
                    )
                workflow = workflow_value
            value = value.get("after_ms")
        if not isinstance(once, bool):
            raise ValueError(f"request_timeout_faults[{method!r}] once must be boolean")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"request_timeout_faults[{method!r}] must contain after_ms")
        if not math.isfinite(float(value)) or value <= 0 or value > 600_000:
            raise ValueError(f"request_timeout_faults[{method!r}] after_ms is out of bounds")
        faults[method] = _TimeoutFault(
            int(value), remaining=1 if once else None, workflow=workflow
        )
    return faults


def _request_operation(request: Mapping[str, Any]) -> str | None:
    """Return the operation name used by timeout-fault configuration.

    Direct JSON-RPC test servers use the request method as their operation
    name. MCP tool calls carry the operation in ``params.name`` instead.
    Keeping this normalization in the runner makes a fault target the public
    tool regardless of which JSON-RPC envelope the child receives.
    """
    method = request.get("method")
    if method == "tools/call":
        params = request.get("params")
        if isinstance(params, Mapping):
            name = params.get("name")
            if isinstance(name, str) and name:
                return name
    return method if isinstance(method, str) else None


def _request_workflow(request: Mapping[str, Any]) -> str | None:
    """Return an MCP tool call's workflow argument, when present."""
    params = request.get("params")
    if not isinstance(params, Mapping):
        return None
    arguments = params.get("arguments")
    if not isinstance(arguments, Mapping):
        return None
    workflow = arguments.get("workflow")
    return workflow if isinstance(workflow, str) else None


def _request_action(request: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """Return an ``advance_workflow`` action from an MCP request."""

    params = request.get("params")
    if not isinstance(params, Mapping):
        return None
    arguments = params.get("arguments")
    if not isinstance(arguments, Mapping):
        return None
    action = arguments.get("action")
    return action if isinstance(action, Mapping) else None


def _walk_json_values(value: Any) -> list[Any]:
    """Flatten structured MCP values, decoding embedded JSON text once."""

    values = [value]
    if isinstance(value, Mapping):
        for child in value.values():
            values.extend(_walk_json_values(child))
    elif isinstance(value, list):
        for child in value:
            values.extend(_walk_json_values(child))
    elif isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith(("{", "[")):
            with contextlib.suppress(json.JSONDecodeError):
                decoded = json.loads(stripped)
                if decoded != value:
                    values.extend(_walk_json_values(decoded))
    return values


def _response_is_error(response: Mapping[str, Any]) -> bool:
    """Return whether an MCP/JSON-RPC response reports a failed operation."""

    if "error" in response:
        return True
    for value in _walk_json_values(response.get("result")):
        if isinstance(value, Mapping) and value.get("isError") is True:
            return True
    return False


def _response_requires_review(response: Mapping[str, Any]) -> bool:
    """Return whether a successful capture requires a review report."""

    for value in _walk_json_values(response):
        if not isinstance(value, Mapping):
            continue
        if value.get("code") == "workflow/review_pending":
            return True
        if (
            value.get("type", value.get("action")) == "report_requirement"
            and value.get("requirement_id") == "review"
        ):
            return True
        requirements = value.get("requirements")
        if isinstance(requirements, Mapping):
            review = requirements.get("review")
            if isinstance(review, Mapping) and review.get("status") == "pending":
                return True
        elif isinstance(requirements, list):
            if any(
                isinstance(review, Mapping)
                and review.get("id") == "review"
                and review.get("status") == "pending"
                for review in requirements
            ):
                return True
    return False


def _response_satisfies_review(response: Mapping[str, Any]) -> bool:
    """Return whether the supervisor completed the review-report relay.

    ``workflow/review_findings`` is a completed report relay even though the
    review requirement remains unsatisfied.  The owning conversation must be
    able to adjudicate those findings and reset the mutable capture for a
    fresh generation; keeping the proxy guard in its pre-report state would
    reject that required reset before the supervisor can validate it.
    """

    for value in _walk_json_values(response):
        if not isinstance(value, Mapping):
            continue
        if value.get("code") == "workflow/review_findings":
            return True
        if (
            value.get("code") == "workflow/requirement_satisfied"
            and value.get("requirement_id") == "review"
        ):
            return True
        requirements = value.get("requirements")
        if isinstance(requirements, Mapping):
            review = requirements.get("review")
            if isinstance(review, Mapping) and review.get("status") in {
                "satisfied",
                "complete",
                "completed",
            }:
                return True
        elif isinstance(requirements, list):
            if any(
                isinstance(review, Mapping)
                and review.get("id") == "review"
                and review.get("status") in {"satisfied", "complete", "completed"}
                for review in requirements
            ):
                return True
    return False


def _review_guard_snapshot(response: Mapping[str, Any]) -> dict[str, Any]:
    """Retain only the bounded workflow facts needed for a corrective error."""

    snapshot: dict[str, Any] = {}
    for value in _walk_json_values(response):
        if not isinstance(value, Mapping):
            continue
        for key in (
            "workflow",
            "revision",
            "invalidation_epoch",
            "generation",
            "subject_sha256",
            "dependency_evidence_sha256",
            "review_input",
        ):
            if key not in value or key in snapshot:
                continue
            candidate = value[key]
            # Workflow-v2 returns one RequirementView per requirement. Views
            # unrelated to the review carry ``review_input: null``; keep
            # looking until the matching review view supplies the bound paths.
            if key == "review_input" and not isinstance(candidate, Mapping):
                continue
            snapshot[key] = candidate
    return snapshot


class DesktopStdioSession:
    """Own one isolated Desktop MCP config, proxy, trace, and cleanup scope.

    The server is started by the runner after the private proxy connects over a
    local socket. This keeps the credential-bearing child outside the evaluated
    agent's process lineage while allowing the runner to retain a JSON-RPC trace.
    """

    SERVER_NAME = "nxd-desktop"
    PROXY_MODULE = Path(__file__).resolve()

    def __init__(
        self,
        server_command: str | os.PathLike[str] | Sequence[str],
        server_args: Sequence[str] = (),
        *,
        server_env: Mapping[str, str] | None = None,
        root: Path | None = None,
        server_name: str = SERVER_NAME,
        allowed_tools: Sequence[str] | None = None,
        workflow_action_guard: bool = False,
        request_timeout_faults: Mapping[str, Any] | None = None,
        startup_timeout_s: float = 15.0,
        shutdown_timeout_s: float = 5.0,
    ) -> None:
        if isinstance(server_command, (str, os.PathLike)):
            command = [str(server_command), *(str(a) for a in server_args)]
        else:
            command = [str(a) for a in server_command]
            if server_args:
                command.extend(str(a) for a in server_args)
        if not command or not command[0]:
            raise ValueError("server_command must not be empty")
        self.server_command = tuple(command)
        self.server_env = _safe_server_environment(server_env or {})
        self.server_name = server_name
        self.allowed_tools = (
            tuple(allowed_tools)
            if allowed_tools is not None
            else (f"mcp__{server_name}__*",)
        )
        self.workflow_action_guard = bool(workflow_action_guard)
        self.request_timeout_faults = dict(request_timeout_faults or {})
        self.startup_timeout_s = startup_timeout_s
        self.shutdown_timeout_s = shutdown_timeout_s
        self._provided_root = Path(root) if root is not None else None
        self._temp: tempfile.TemporaryDirectory[str] | None = None
        self._root: Path | None = None
        self._attached: list[subprocess.Popen[Any]] = []
        self._bridge_listener: socket.socket | None = None
        self._bridge_connection: socket.socket | None = None
        self._bridge_thread: threading.Thread | None = None
        self._bridge_connections: set[socket.socket] = set()
        self._bridge_workers: set[threading.Thread] = set()
        self._bridge_state_lock = threading.Lock()
        self._review_guard_state: dict[str, Any] | None = None
        self._bridge_stop = threading.Event()
        self._bridge_path: Path | None = None
        self._server_process: subprocess.Popen[bytes] | None = None
        self._server_processes: set[subprocess.Popen[bytes]] = set()
        self._started = False
        self._closed = False
        self.setup_result = StdioOutcome("not_started")
        self.agent_result = StdioOutcome("not_started")
        self.server_result = StdioOutcome("not_started")

    @property
    def root(self) -> Path:
        if self._root is None:
            raise DesktopStdioError("DesktopStdioSession has not started")
        return self._root

    @property
    def config_path(self) -> Path:
        return self.root / "mcp-config.json"

    @property
    def trace_path(self) -> Path:
        return self.root / "mcp-trace.jsonl"

    @property
    def review_allowlist_path(self) -> Path:
        return self.root / "review-allowlist.json"

    @property
    def server_result_path(self) -> Path:
        return self.root / "server-result.json"

    @property
    def bridge_path(self) -> Path:
        return self._bridge_path or (self.root / "mcp-bridge.sock")

    @property
    def server_process_result_path(self) -> Path:
        return self.root / "server-process-result.json"

    @property
    def strict_mcp_config(self) -> bool:
        return True

    @property
    def allowed_tools_csv(self) -> str:
        return ",".join(self.allowed_tools)

    def _write_review_allowlist(self, state: Mapping[str, Any] | None) -> None:
        """Publish only the current supervisor-bound review paths to the proxy."""

        _write_private_text(
            self.review_allowlist_path,
            json.dumps(_review_allowlist_payload(state), sort_keys=True),
        )

    def start(self) -> "DesktopStdioSession":
        if self._started:
            return self
        if self._closed:
            raise DesktopStdioError("DesktopStdioSession cannot be restarted after close")
        try:
            if self._provided_root is None:
                self._temp = tempfile.TemporaryDirectory(prefix="eval-desktop-stdio-")
                self._root = Path(self._temp.name)
            else:
                self._root = self._provided_root
                self._root.mkdir(parents=True, exist_ok=True, mode=0o700)
            with contextlib.suppress(OSError):
                self.root.chmod(0o700)
            listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            for _attempt in range(8):
                candidate = Path("/tmp") / (
                    f"nxd-eval-mcp-{secrets.token_hex(8)}.sock"
                )
                try:
                    listener.bind(str(candidate))
                except OSError:
                    if _attempt == 7:
                        listener.close()
                        raise
                else:
                    self._bridge_path = candidate
                    break
            with contextlib.suppress(OSError):
                self.bridge_path.chmod(0o600)
            listener.listen(1)
            listener.settimeout(0.2)
            self._bridge_listener = listener
            spec = {
                "bridge_path": str(self.bridge_path),
                "server_process_result_path": str(self.server_process_result_path),
                "trace_path": str(self.trace_path),
                "result_path": str(self.server_result_path),
                "review_allowlist_path": str(self.review_allowlist_path),
                "shutdown_timeout_s": self.shutdown_timeout_s,
                "request_timeout_faults": self.request_timeout_faults,
            }
            spec_path = self.root / "server-spec.json"
            _write_private_text(spec_path, json.dumps(spec, sort_keys=True))
            config = {
                "mcpServers": {
                    self.server_name: {
                        "command": sys.executable,
                        "args": [
                            str(self.PROXY_MODULE),
                            "--proxy",
                            "--spec",
                            str(spec_path),
                        ],
                        "env": {"PYTHONUNBUFFERED": "1"},
                    }
                }
            }
            _write_private_text(
                self.config_path, json.dumps(config, indent=2, sort_keys=True)
            )
            _write_private_text(self.trace_path, "")
            _write_private_text(self.server_result_path, "{}")
            _write_private_text(self.server_process_result_path, "{}")
            self._write_review_allowlist(None)
            self._bridge_thread = threading.Thread(
                target=self._serve_bridge,
                name="dp-scenarios-desktop-bridge",
                daemon=True,
            )
            self._bridge_thread.start()
            self.setup_result = StdioOutcome("passed")
            self._started = True
            return self
        except (OSError, TypeError, ValueError) as exc:
            self.setup_result = StdioOutcome("failed", redact_text(str(exc)))
            self.cleanup()
            raise DesktopStdioError(f"stdio MCP setup failed: {exc}") from exc

    def ensure_started(self) -> "DesktopStdioSession":
        return self.start()

    def attach_process(self, proc: subprocess.Popen[Any]) -> None:
        """Register the Claude process for process-group cleanup."""
        self._attached.append(proc)

    def record_agent(self, *, status: str, error: str | None = None) -> None:
        self.agent_result = StdioOutcome(
            status, redact_text(error) if error else None
        )

    def _serve_bridge(self) -> None:
        """Accept and serve trusted supervisors for proxy connections.

        Codex app-server may restart its stdio MCP client while refreshing the
        tool catalog. The proxy command is then launched again with the same
        private spec. A single accepted socket could serve the first client
        forever while leaving the replacement client connected to the listen
        backlog with no supervisor behind it. Start a fresh trusted child for
        each accepted connection; the supervisor data directory remains the
        durable boundary shared by the sessions, while credentials stay in
        this runner-owned environment.
        """

        listener = self._bridge_listener
        if listener is None:
            return
        while not self._bridge_stop.is_set():
            try:
                connection, _ = listener.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            if self._bridge_stop.is_set():
                self._close_socket(connection)
                return
            worker = threading.Thread(
                target=self._serve_connection,
                args=(connection,),
                name="dp-scenarios-desktop-proxy",
                daemon=True,
            )
            with self._bridge_state_lock:
                self._bridge_connections.add(connection)
                self._bridge_workers.add(worker)
            worker.start()

    def _serve_connection(self, connection: socket.socket) -> None:
        """Run one supervisor child for one Codex stdio client connection."""

        child: subprocess.Popen[bytes] | None = None
        send_lock = threading.Lock()
        request_context: dict[str, Mapping[str, Any]] = {}

        def send_to_proxy(line: bytes) -> None:
            with send_lock:
                connection.sendall(line)

        def blocked_review_response(request: Mapping[str, Any], operation: str) -> bytes:
            with self._bridge_state_lock:
                state = dict(self._review_guard_state or {})
            payload = {
                "code": "runner/review_pending",
                "operation": operation,
                "required_action": {
                    "type": "report_requirement",
                    "requirement_id": "review",
                },
                "message": (
                    "workflow review is pending; dispatch one provider-native "
                    "read-only reviewer with the captured review_input, then "
                    "submit advance_workflow/report_requirement"
                ),
            }
            for key in (
                "workflow",
                "revision",
                "invalidation_epoch",
                "generation",
                "subject_sha256",
                "dependency_evidence_sha256",
                "review_input",
            ):
                if key in state:
                    payload[key] = state[key]
            return (
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": request.get("id"),
                        "result": {
                            "isError": True,
                            "structuredContent": payload,
                            "content": [
                                {
                                    "type": "text",
                                    "text": json.dumps(payload, sort_keys=True),
                                }
                            ],
                        },
                    },
                    separators=(",", ":"),
                ).encode()
                + b"\n"
            )

        def should_block(request: Mapping[str, Any]) -> bool:
            if not self.workflow_action_guard:
                return False
            operation = _request_operation(request)
            if operation not in _REVIEW_PENDING_BLOCKED_OPERATIONS:
                return False
            with self._bridge_state_lock:
                return self._review_guard_state is not None

        def update_review_guard(
            request: Mapping[str, Any] | None, response: Mapping[str, Any]
        ) -> None:
            if not self.workflow_action_guard or request is None:
                return
            if _response_is_error(response):
                return
            operation = _request_operation(request)
            action = _request_action(request)
            if operation == "advance_workflow" and isinstance(action, Mapping):
                action_type = action.get("type")
                if action_type == "capture" and _response_requires_review(response):
                    state = _review_guard_snapshot(response)
                    workflow = _request_workflow(request)
                    if workflow is not None:
                        state["workflow"] = workflow
                    with self._bridge_state_lock:
                        self._review_guard_state = state
                    self._write_review_allowlist(state)
                elif (
                    action_type == "report_requirement"
                    and _response_satisfies_review(response)
                ):
                    with self._bridge_state_lock:
                        self._review_guard_state = None
                    self._write_review_allowlist(None)

        try:
            self._bridge_connection = connection
            child = subprocess.Popen(
                list(self.server_command),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=self.server_env,
                start_new_session=True,
            )
            self._server_process = child
            with self._bridge_state_lock:
                self._server_processes.add(child)
            assert child.stdin is not None
            assert child.stdout is not None
            assert child.stderr is not None

            def forward_to_server() -> None:
                buffer = b""
                try:
                    while True:
                        chunk = connection.recv(65536)
                        if not chunk:
                            break
                        buffer += chunk
                        while b"\n" in buffer:
                            line, buffer = buffer.split(b"\n", 1)
                            line += b"\n"
                            request: Any = None
                            with contextlib.suppress(UnicodeDecodeError, json.JSONDecodeError):
                                request = json.loads(line.decode("utf-8"))
                            if isinstance(request, Mapping):
                                request_id = _rpc_id_key(request.get("id"))
                                if request_id is not None:
                                    request_context[request_id] = request
                                operation = _request_operation(request)
                                if should_block(request) and operation is not None:
                                    send_to_proxy(blocked_review_response(request, operation))
                                    continue
                            child.stdin.write(line)
                            child.stdin.flush()
                    if buffer:
                        child.stdin.write(buffer)
                        child.stdin.flush()
                except (BrokenPipeError, OSError):
                    pass
                finally:
                    with contextlib.suppress(OSError):
                        child.stdin.close()

            def forward_from_server() -> None:
                try:
                    for line in child.stdout:
                        response: Any = None
                        with contextlib.suppress(UnicodeDecodeError, json.JSONDecodeError):
                            response = json.loads(line.decode("utf-8"))
                        request = None
                        if isinstance(response, Mapping) and "id" in response:
                            request_id = _rpc_id_key(response.get("id"))
                            if request_id is not None:
                                request = request_context.pop(request_id, None)
                        if isinstance(response, Mapping):
                            update_review_guard(request, response)
                        send_to_proxy(line)
                except (BrokenPipeError, OSError):
                    pass

            def drain_stderr() -> None:
                for _line in child.stderr:
                    pass

            to_server = threading.Thread(target=forward_to_server, daemon=True)
            from_server = threading.Thread(target=forward_from_server, daemon=True)
            stderr_reader = threading.Thread(target=drain_stderr, daemon=True)
            to_server.start()
            from_server.start()
            stderr_reader.start()
            to_server.join()
            from_server.join(timeout=self.shutdown_timeout_s)
            if child.poll() is None:
                try:
                    child.wait(timeout=self.shutdown_timeout_s)
                except subprocess.TimeoutExpired:
                    self._kill_process(child)
            else:
                child.wait()
            code = child.returncode
            _write_private_text(
                self.server_process_result_path,
                json.dumps(
                    {
                        "status": "passed" if code == 0 else "failed",
                        "exit_code": code,
                        "pid": child.pid,
                    },
                    sort_keys=True,
                ),
            )
            # Publish the server outcome before releasing the bridge reader;
            # the proxy uses that file to report a complete result.
            with contextlib.suppress(OSError):
                connection.shutdown(socket.SHUT_WR)
        except (OSError, ValueError) as exc:
            _write_private_text(
                self.server_process_result_path,
                json.dumps({"status": "failed", "error": redact_text(str(exc))}, sort_keys=True),
            )
            if child is not None:
                self._kill_process(child)
        finally:
            with contextlib.suppress(OSError):
                connection.close()
            with self._bridge_state_lock:
                self._bridge_connections.discard(connection)
                if child is not None:
                    self._server_processes.discard(child)
                self._bridge_workers.discard(threading.current_thread())
            if self._bridge_connection is connection:
                self._bridge_connection = None
            if child is not None and self._server_process is child:
                self._server_process = None

    @staticmethod
    def _close_socket(value: socket.socket | None) -> None:
        if value is None:
            return
        with contextlib.suppress(OSError):
            value.shutdown(socket.SHUT_RDWR)
        with contextlib.suppress(OSError):
            value.close()

    def _read_server_result(self) -> StdioOutcome:
        if not self._started or self._root is None:
            return StdioOutcome("not_started")
        try:
            data = json.loads(self.server_result_path.read_text(encoding="utf-8"))
            return StdioOutcome(
                str(data.get("status", "unknown")),
                redact_text(data["error"]) if data.get("error") else None,
                data.get("exit_code"),
                str(self.trace_path),
            )
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return StdioOutcome(
                "not_started" if not self.trace_path.exists() else "unknown",
                "stdio proxy did not write a server result",
                trace_path=str(self.trace_path),
            )

    def result_metrics(self) -> dict[str, Any]:
        self.server_result = self._read_server_result()
        return {
            "setup_result": self.setup_result.as_dict(),
            "agent_result": self.agent_result.as_dict(),
            "server_result": self.server_result.as_dict(),
            "mcp_config": str(self.config_path) if self._started else None,
            "mcp_trace": str(self.trace_path) if self._started else None,
        }

    @staticmethod
    def _kill_process(proc: subprocess.Popen[Any]) -> None:
        if proc.poll() is not None:
            return
        with contextlib.suppress(OSError):
            os.killpg(proc.pid, signal.SIGTERM)
        with contextlib.suppress(OSError):
            proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(OSError):
                os.killpg(proc.pid, signal.SIGKILL)
            with contextlib.suppress(OSError):
                proc.kill()
            with contextlib.suppress(subprocess.TimeoutExpired):
                proc.wait(timeout=5)

    def cleanup(self) -> None:
        if self._closed:
            return
        for proc in self._attached:
            self._kill_process(proc)
        self._attached.clear()
        self._bridge_stop.set()
        self._close_socket(self._bridge_listener)
        if self._bridge_thread is not None:
            self._bridge_thread.join(timeout=5)
            self._bridge_thread = None
        with self._bridge_state_lock:
            connections = list(self._bridge_connections)
            processes = list(self._server_processes)
            workers = list(self._bridge_workers)
        for connection in connections:
            self._close_socket(connection)
        self._bridge_connection = None
        self._bridge_listener = None
        for proc in processes:
            self._kill_process(proc)
        for worker in workers:
            worker.join(timeout=5)
        with self._bridge_state_lock:
            self._bridge_connections.clear()
            self._bridge_workers.clear()
            self._server_processes.clear()
        self._server_process = None
        if self._root is not None:
            try:
                result = json.loads(
                    self.server_result_path.read_text(encoding="utf-8")
                )
                pid = int(result.get("proxy_pid", 0))
                group_killed = False
                if pid > 0 and pid != os.getpid():
                    try:
                        os.killpg(pid, signal.SIGTERM)
                        group_killed = True
                    except OSError:
                        pass
                child_pid = int(result.get("child_pid", 0))
                if (
                    result.get("status") == "started"
                    and not group_killed
                    and child_pid > 0
                    and child_pid != os.getpid()
                ):
                    # The runner normally tears down the bridge and its
                    # supervisor child directly. Keep the recorded PID as a
                    # fallback for a proxy that was killed before it could
                    # publish the final result.
                    with contextlib.suppress(OSError):
                        os.kill(child_pid, signal.SIGTERM)
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                pass
        bridge_path = self._bridge_path
        if self._temp is not None:
            self._temp.cleanup()
            self._temp = None
        elif self._provided_root is not None:
            for name in (
                "mcp-config.json",
                "server-spec.json",
                "server-process-result.json",
                "mcp-trace.jsonl",
                "server-result.json",
                "review-allowlist.json",
            ):
                with contextlib.suppress(OSError):
                    (self.root / name).unlink()
        if bridge_path is not None:
            with contextlib.suppress(OSError):
                bridge_path.unlink()
        self._bridge_path = None
        self._closed = True

    def __enter__(self) -> "DesktopStdioSession":
        return self.start()

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.cleanup()


def _write_proxy_result(path: Path, **payload: Any) -> None:
    payload.setdefault(
        "finished_at", _dt.datetime.now(_dt.timezone.utc).isoformat()
    )
    with contextlib.suppress(OSError):
        _write_private_text(path, json.dumps(redact_json_rpc(payload), sort_keys=True))


def _trace_line(path: Path, direction: str, line: bytes, **metadata: Any) -> None:
    """Persist only parsed, recursively-redacted JSON-RPC messages."""
    try:
        value = json.loads(line.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        value = {"parse_error": True}
    record = {
        "source": "runner",
        "protocol": "mcp",
        "timestamp": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "direction": direction,
        "message": redact_json_rpc(value),
    }
    if metadata:
        record.update(redact_json_rpc(metadata))
    with _TRACE_LOCK:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n"
            )


def run_stdio_proxy(spec_path: Path) -> int:
    """Run the forwarding proxy used by Claude's private MCP config."""
    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        bridge_path = Path(spec["bridge_path"])
        server_process_result_path = Path(spec["server_process_result_path"])
        trace_path = Path(spec["trace_path"])
        result_path = Path(spec["result_path"])
        review_allowlist_path = Path(spec["review_allowlist_path"])
        timeout_faults = _timeout_faults(spec.get("request_timeout_faults"))
        # The proxy is part of the evaluated agent's process lineage. It gets
        # only a private socket endpoint; the parent runner owns the other end
        # and starts the supervisor child with its in-memory environment.
        os.environ.pop(_SOURCE_CREDENTIAL_ENV, None)
        os.environ.pop(_TRUSTED_CREDENTIAL_MAPPING_ENV, None)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return 2
    bridge: socket.socket | None = None
    bridge_reader: Any | None = None
    bridge_writer: Any | None = None
    child_error: list[str] = []
    try:
        bridge = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        bridge.connect(str(bridge_path))
        bridge_reader = bridge.makefile("rb", buffering=0)
        bridge_writer = bridge.makefile("wb", buffering=0)
        with contextlib.suppress(OSError):
            os.setsid()

        state_lock = threading.Lock()
        pending: dict[str, _PendingRequest] = {}
        request_methods: dict[str, str] = {}
        fault_lock = threading.Lock()
        timers_lock = threading.Lock()
        active_timers: set[threading.Timer] = set()
        output_lock = threading.Lock()
        closing = threading.Event()
        shutting_down = False

        def next_timeout_ms(operation: str, request: Mapping[str, Any]) -> int | None:
            with fault_lock:
                fault = timeout_faults.get(operation)
                if fault is None:
                    return None
                if fault.workflow is not None and _request_workflow(request) != fault.workflow:
                    return None
                if fault.remaining == 0:
                    return None
                if fault.remaining is not None:
                    fault.remaining -= 1
                return fault.after_ms

        def write_client(line: bytes) -> bool:
            try:
                with output_lock:
                    sys.stdout.buffer.write(line)
                    sys.stdout.buffer.flush()
                return True
            except (BrokenPipeError, OSError):
                return False

        def write_review_reader_response(request: Mapping[str, Any]) -> None:
            started_at = time.monotonic()
            result = _review_reader_result(request, review_allowlist_path)
            response = {
                "jsonrpc": "2.0",
                "id": request.get("id"),
                "result": result,
            }
            line = json.dumps(response, separators=(",", ":")).encode() + b"\n"
            _trace_review_reader_summary(
                trace_path,
                _review_reader_trace_metadata(
                    request,
                    result,
                    review_allowlist_path,
                    elapsed_ms=(time.monotonic() - started_at) * 1000.0,
                ),
            )
            write_client(line)

        def cancel_timers() -> None:
            with timers_lock:
                timers = list(active_timers)
            for timer in timers:
                timer.cancel()
            current = threading.current_thread()
            for timer in timers:
                if timer is not current:
                    timer.join(timeout=1)

        def timeout_response(state: _PendingRequest) -> None:
            try:
                with state_lock:
                    if (
                        closing.is_set()
                        or pending.get(state.request_key) is not state
                        or state.timed_out
                    ):
                        return
                    state.timed_out = True
                line = (
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": state.request_id,
                            "error": {
                                "code": -32098,
                                "message": "client deadline exceeded",
                                "data": {
                                    "method": state.method,
                                    "timeout_ms": state.timeout_ms,
                                    "elapsed_ms": max(
                                        0, round((time.monotonic() - state.started_at) * 1000)
                                    ),
                                },
                            },
                        },
                        separators=(",", ":"),
                    ).encode()
                    + b"\n"
                )
                _trace_line(
                    trace_path,
                    "response",
                    line,
                    forwarded=True,
                    synthetic=True,
                    timeout_fault=True,
                )
                write_client(line)
            finally:
                with timers_lock:
                    active_timers.discard(threading.current_thread())

        def schedule_timeout(state: _PendingRequest) -> None:
            timer = threading.Timer(
                state.timeout_ms / 1000,
                timeout_response,
                args=(state,),
            )
            timer.daemon = True
            state.timer = timer
            with timers_lock:
                active_timers.add(timer)
            timer.start()

        def reject_duplicate(request: Mapping[str, Any]) -> None:
            line = (
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": request.get("id"),
                        "error": {
                            "code": -32600,
                            "message": "duplicate request id while request is pending",
                        },
                    },
                    separators=(",", ":"),
                ).encode()
                + b"\n"
            )
            _trace_line(
                trace_path,
                "response",
                line,
                forwarded=True,
                synthetic=True,
                duplicate_id=True,
            )
            write_client(line)

        def terminate_child(signum: int, _frame: Any) -> None:
            nonlocal shutting_down
            if shutting_down:
                return
            shutting_down = True
            closing.set()
            cancel_timers()
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            signal.signal(signal.SIGINT, signal.SIG_IGN)
            # Closing the bridge tells the parent runner to stop the trusted
            # supervisor child. The proxy never owns or receives that child.
            if bridge is not None:
                with contextlib.suppress(OSError):
                    bridge.shutdown(socket.SHUT_RDWR)
                with contextlib.suppress(OSError):
                    bridge.close()
            raise SystemExit(128 + signum)

        signal.signal(signal.SIGTERM, terminate_child)
        signal.signal(signal.SIGINT, terminate_child)
        _write_proxy_result(
            result_path, status="started", proxy_pid=os.getpid(), child_pid=None
        )

        def forward_responses() -> None:
            assert bridge_reader is not None
            for line in bridge_reader:
                state: _PendingRequest | None = None
                response_operation: str | None = None
                message: Any = None
                try:
                    message = json.loads(line.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    pass
                if isinstance(message, Mapping) and "id" in message:
                    request_key = _rpc_id_key(message.get("id"))
                    if request_key is not None:
                        with state_lock:
                            state = pending.pop(request_key, None)
                            response_operation = request_methods.pop(request_key, None)
                        if state is not None and state.timer is not None:
                            state.timer.cancel()
                            with timers_lock:
                                active_timers.discard(state.timer)
                with contextlib.suppress(OSError):
                    _trace_line(
                        trace_path,
                        "response",
                        line,
                        forwarded=not (state is not None and state.timed_out),
                        late=bool(state is not None and state.timed_out),
                    )
                if state is not None and state.timed_out:
                    continue
                output_line = line
                if (
                    isinstance(message, Mapping)
                    and not (state is not None and state.timed_out)
                    and response_operation == "tools/list"
                ):
                    output_message = _augment_tools_list(
                        message, allowlist_path=review_allowlist_path
                    )
                    if output_message != message:
                        output_line = (
                            json.dumps(output_message, separators=(",", ":")).encode()
                            + b"\n"
                        )
                        _trace_line(
                            trace_path,
                            "response",
                            output_line,
                            forwarded=True,
                            injected_review_reader=True,
                        )
                if not write_client(output_line):
                    return

        reader = threading.Thread(target=forward_responses, daemon=True)
        reader.start()
        assert bridge_writer is not None
        for line in sys.stdin.buffer:
            request: Any = None
            try:
                request = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                pass
            is_review_reader_call = (
                isinstance(request, Mapping)
                and request.get("method") == "tools/call"
                and isinstance(request.get("params"), Mapping)
                and request["params"].get("name") == _REVIEW_READER_TOOL
            )
            if isinstance(request, Mapping):
                if is_review_reader_call:
                    write_review_reader_response(request)
                    continue
            _trace_line(trace_path, "request", line)
            if isinstance(request, Mapping):
                operation = _request_operation(request)
                request_key = (
                    _rpc_id_key(request.get("id"))
                    if "id" in request and operation is not None
                    else None
                )
                # Only a request that can actually carry a deadline may consume
                # the fault budget, and a duplicate is settled before that
                # budget is touched. Consuming it earlier lets a notification
                # or a re-used id silently burn a ``once`` deadline that then
                # never fires, and the scenario reports a missing timeout
                # instead of the reason there was none. Screening duplicates
                # first also keeps them rejected once the budget is spent,
                # rather than forwarding one whose reply is then swallowed as
                # the pending request's suppressed late response.
                if request_key is not None:
                    with state_lock:
                        duplicate = request_key in pending
                    if duplicate:
                        reject_duplicate(request)
                        continue
                    with state_lock:
                        request_methods[request_key] = operation
                    timeout_ms = next_timeout_ms(operation, request)
                    if timeout_ms is not None:
                        state = _PendingRequest(
                            request_key=request_key,
                            request_id=request.get("id"),
                            method=operation,
                            timeout_ms=timeout_ms,
                            started_at=time.monotonic(),
                        )
                        # Only this thread inserts into ``pending``; the reader
                        # thread only pops, so the check above cannot go stale
                        # in the direction that would admit a duplicate.
                        with state_lock:
                            pending[request_key] = state
                        schedule_timeout(state)
            try:
                bridge_writer.write(line)
                bridge_writer.flush()
            except (BrokenPipeError, OSError):
                child_error.append("server bridge closed")
                break
        # EOF is the client's shutdown boundary: stop emitting synthetic
        # deadlines while the child drains or exits, but still let the reader
        # trace any response that was already produced.
        closing.set()
        cancel_timers()
        with contextlib.suppress(OSError):
            bridge_writer.close()
        with contextlib.suppress(OSError):
            bridge.shutdown(socket.SHUT_WR)
        reader.join(timeout=5)
        # The child may close its bridge without answering every forwarded
        # request. Drop correlation state before returning so a long-lived
        # proxy cannot retain request metadata past the child lifecycle.
        with state_lock:
            pending.clear()
            request_methods.clear()
        try:
            server_result = json.loads(
                server_process_result_path.read_text(encoding="utf-8")
            )
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            server_result = {}
        code = server_result.get("exit_code") if isinstance(server_result, Mapping) else None
        if child_error:
            status, error = "failed", child_error[0]
        elif code == 0:
            status, error = "passed", None
        elif code is None:
            status, error = "failed", "server bridge ended without a server result"
        else:
            status, error = "failed", f"server exited {code}"
        _write_proxy_result(
            result_path,
            status=status,
            error=error,
            exit_code=code,
            proxy_pid=os.getpid(),
            child_pid=(
                server_result.get("pid")
                if isinstance(server_result, Mapping)
                else None
            ),
        )
        return 0 if status == "passed" else 1
    except (OSError, ValueError) as exc:
        _write_proxy_result(
            result_path,
            status="failed",
            error=str(exc),
            proxy_pid=os.getpid(),
            child_pid=None,
        )
        return 1
    finally:
        for stream in (bridge_reader, bridge_writer):
            if stream is not None:
                with contextlib.suppress(OSError):
                    stream.close()
        if bridge is not None:
            with contextlib.suppress(OSError):
                bridge.close()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--proxy", action="store_true")
    parser.add_argument("--spec", type=Path)
    args = parser.parse_args(argv)
    if args.proxy and args.spec:
        return run_stdio_proxy(args.spec)
    parser.error("the proxy requires --proxy --spec <path>")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
