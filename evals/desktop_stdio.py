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
import copy
import ctypes
import dataclasses
import datetime as _dt
import hashlib
import io
import json
import math
import os
import re
import secrets
import signal
import shlex
import socket
import stat
import struct
import subprocess
import sys
import sysconfig
import shutil
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


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
_REVIEW_READER_TOOL = "read_review_input"
# While review is pending every tool call is held except these: the
# captured-input reader, and `inspect_workflow`, a bounded read-only supervisor
# inspection. The review report itself is decided by `_review_guard_decision`.
_REVIEW_PENDING_ALLOWED_OPERATIONS = frozenset({_REVIEW_READER_TOOL, "inspect_workflow"})
_NEX_WORKFLOWS = (
    "nex890-positive", "nex890-401", "nex890-403", "nex890-404",
)
# Bridge diagnostics expose forwarded-request methods only through this
# allowlist; every other method is reported as "other".
_NEX_DIAG_METHOD_LABELS = frozenset({"initialize", "tools/list", "tools/call"})
_NEX_MAX_SNAPSHOT_FILES = 256
_NEX_MAX_SNAPSHOT_FILE_BYTES = 1024 * 1024
# Upper bound on an export archive frozen at the moment its response crosses
# the bridge (the runner grades these bytes, not the post-run workspace).
_NEX_MAX_EXPORT_ARCHIVE_BYTES = 50 * 1024 * 1024
_NEX_STREAM_PAIR_WAIT_S = 3.0
# Preflight keeps at most this many characters of redacted tool_result text.
_NEX_PREFLIGHT_RESULT_TEXT_CHARS = 2000
_NEX_WORKFLOW_OPERATIONS = {
    "check_data_product", "prepare_workflow", "advance_workflow",
    "inspect_workflow", "inspect_run", "list_data_products",
    "resume_data_product", "describe_models", "run_semantic_query",
    "export_data_product", _REVIEW_READER_TOOL,
}
_DARWIN_SOL_LOCAL = 0
_DARWIN_LOCAL_PEERCRED = 1
_DARWIN_LOCAL_PEERPID = 2
_DARWIN_CTL_KERN = 1
_DARWIN_KERN_ARGMAX = 8
_DARWIN_KERN_PROCARGS2 = 49
_DARWIN_PROC_PIDTBSDINFO = 3
_PROCESS_ARGS_MIN_BYTES = 4096
_PROCESS_ARGS_MAX_BYTES = 16 * 1024 * 1024


class _DarwinProcBsdInfo(ctypes.Structure):
    """Darwin ``struct proc_bsdinfo`` from sys/proc_info.h."""

    _fields_ = [
        ("pbi_flags", ctypes.c_uint32),
        ("pbi_status", ctypes.c_uint32),
        ("pbi_xstatus", ctypes.c_uint32),
        ("pbi_pid", ctypes.c_uint32),
        ("pbi_ppid", ctypes.c_uint32),
        ("pbi_uid", ctypes.c_uint32),
        ("pbi_gid", ctypes.c_uint32),
        ("pbi_ruid", ctypes.c_uint32),
        ("pbi_rgid", ctypes.c_uint32),
        ("pbi_svuid", ctypes.c_uint32),
        ("pbi_svgid", ctypes.c_uint32),
        ("rfu_1", ctypes.c_uint32),
        ("pbi_comm", ctypes.c_char * 16),
        ("pbi_name", ctypes.c_char * 32),
        ("pbi_nfiles", ctypes.c_uint32),
        ("pbi_pgid", ctypes.c_uint32),
        ("pbi_pjobc", ctypes.c_uint32),
        ("e_tdev", ctypes.c_uint32),
        ("e_tpgid", ctypes.c_uint32),
        ("pbi_nice", ctypes.c_int32),
        ("pbi_start_tvsec", ctypes.c_uint64),
        ("pbi_start_tvusec", ctypes.c_uint64),
    ]


@dataclasses.dataclass(frozen=True)
class _ProxyPeerIdentity:
    parent_pid: int
    executable: str
    argv: tuple[str, ...]


def _canonical_process_path(value: str | os.PathLike[str]) -> str:
    """Canonicalize a process argument across symlinks and /private aliases."""
    return os.path.normcase(os.path.realpath(os.path.abspath(os.fspath(value))))


def _same_executable(left: str, right: str) -> bool:
    """Compare executable identity by inode, then canonical path as fallback."""
    try:
        left_stat = os.stat(left)
        right_stat = os.stat(right)
        if (left_stat.st_dev, left_stat.st_ino) == (right_stat.st_dev, right_stat.st_ino):
            return True
    except OSError:
        pass
    return _canonical_process_path(left) == _canonical_process_path(right)


def _proxy_interpreter_paths() -> tuple[str, ...]:
    """Return only runner-configured Python interpreter paths for the proxy."""
    configured = [sys.executable]
    if sys.platform == "darwin":
        framework = sysconfig.get_config_var("PYTHONFRAMEWORK")
        install_dir = sysconfig.get_config_var("PYTHONFRAMEWORKINSTALLDIR")
        version = sysconfig.get_config_var("VERSION")
        if all(
            isinstance(value, str) and value
            for value in (framework, install_dir, version)
        ):
            version_root = Path(install_dir) / "Versions" / version
            configured.extend(
                (
                    str(
                        version_root
                        / "Resources"
                        / f"{framework}.app"
                        / "Contents"
                        / "MacOS"
                        / framework
                    ),
                    str(version_root / framework),
                )
            )
    paths: list[str] = []
    for value in configured:
        absolute = os.path.abspath(value)
        for candidate in (absolute, os.path.realpath(absolute)):
            if candidate not in paths:
                paths.append(candidate)
    return tuple(paths)


def _parse_darwin_procargs2(
    buffer: bytearray,
    used_length: int,
    *,
    allowed_argv0: Sequence[bytes],
    expected_argv_tail: Sequence[str],
) -> tuple[str, ...] | None:
    """Parse argv only; the KERN_PROCARGS2 environment tail stays opaque."""
    if (
        not isinstance(used_length, int)
        or isinstance(used_length, bool)
        or used_length < struct.calcsize("=i")
        or used_length > len(buffer)
        or len(expected_argv_tail) != 4
    ):
        return None
    argc = struct.unpack_from("=i", buffer, 0)[0]
    if argc != 5:
        return None
    executable_end = buffer.find(b"\0", struct.calcsize("=i"), used_length)
    if executable_end < 0:
        return None
    offset = executable_end + 1
    while offset < used_length and buffer[offset] == 0:
        offset += 1
    if offset >= used_length:
        return None
    argv0_end = buffer.find(b"\0", offset, used_length)
    if argv0_end <= offset:
        return None

    # Check argv[0] against runner-owned executable paths before copying or
    # decoding bytes. An empty argv[0] is indistinguishable from padding here;
    # the next non-empty item must therefore be the configured interpreter.
    candidate = memoryview(buffer)[offset:argv0_end]
    if not any(candidate == expected for expected in allowed_argv0):
        return None
    offset = argv0_end + 1
    for expected in expected_argv_tail:
        end = buffer.find(b"\0", offset, used_length)
        if end < 0:
            return None
        if memoryview(buffer)[offset:end] != os.fsencode(expected):
            return None
        offset = end + 1
    # Only argv[0] is copied after it matches a runner-configured interpreter.
    # Compare the remaining four arguments in place so a malformed empty argv[0]
    # can never cause an environment string to be copied into Python memory.
    return (os.fsdecode(bytes(candidate)), *expected_argv_tail)


def _parse_linux_process_stat(pid: int, raw: bytes) -> tuple[int, int] | None:
    """Parse (parent pid, start ticks), splitting comm at its final right paren."""
    if not raw or len(raw) > 8192:
        return None
    pid_field, separator, remainder = raw.partition(b" (")
    if not separator:
        return None
    try:
        if int(pid_field) != pid:
            return None
    except ValueError:
        return None
    # The comm field is parenthesized but may itself contain spaces and right
    # parentheses. Split at its final close paren, never the first.
    _comm, close_paren, fields_blob = remainder.rpartition(b")")
    if not close_paren:
        return None
    fields = fields_blob.split()
    if len(fields) < 20 or len(fields[0]) != 1:
        return None
    try:
        parent_pid = int(fields[1])
        start_ticks = int(fields[19])
    except ValueError:
        return None
    if parent_pid < 0 or start_ticks <= 0:
        return None
    return parent_pid, start_ticks


def _linux_process_snapshot(pid: int) -> tuple[int, int] | None:
    """Return (parent pid, start ticks) from one bounded Linux proc stat read."""
    try:
        with (Path("/proc") / str(pid) / "stat").open("rb") as handle:
            raw = handle.read(8193)
    except OSError:
        return None
    return _parse_linux_process_stat(pid, raw)


def _darwin_process_snapshot(pid: int) -> tuple[int, int, int] | None:
    """Return (parent pid, start seconds, start microseconds) for one PID."""
    try:
        libproc = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
        proc_pidinfo = libproc.proc_pidinfo
        proc_pidinfo.argtypes = [
            ctypes.c_int, ctypes.c_int, ctypes.c_uint64,
            ctypes.c_void_p, ctypes.c_int,
        ]
        proc_pidinfo.restype = ctypes.c_int
        info = _DarwinProcBsdInfo()
        expected_size = ctypes.sizeof(info)
        result_size = proc_pidinfo(
            pid, _DARWIN_PROC_PIDTBSDINFO, 0,
            ctypes.byref(info), expected_size,
        )
        if result_size != expected_size or info.pbi_pid != pid:
            return None
        if info.pbi_ppid < 0:
            return None
        return info.pbi_ppid, info.pbi_start_tvsec, info.pbi_start_tvusec
    except (OSError, AttributeError, TypeError, ValueError):
        return None


def _process_parent(pid: int) -> int | None:
    """Read only a process parent PID; ancestor command lines are irrelevant."""
    if pid <= 1:
        return None
    if sys.platform.startswith("linux"):
        snapshot = _linux_process_snapshot(pid)
        return snapshot[0] if snapshot is not None else None
    if sys.platform == "darwin":
        snapshot = _darwin_process_snapshot(pid)
        return snapshot[0] if snapshot is not None else None
    return None


def _darwin_process_executable(pid: int) -> str | None:
    """Read a process executable path using libproc only, without argv fallback."""
    try:
        libproc = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
        proc_pidpath = libproc.proc_pidpath
        proc_pidpath.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
        proc_pidpath.restype = ctypes.c_int
        buffer = ctypes.create_string_buffer(4096)
        result_size = proc_pidpath(pid, buffer, len(buffer))
        if result_size <= 0 or result_size >= len(buffer):
            return None
        path = os.fsdecode(buffer.value)
        return path or None
    except (OSError, AttributeError, TypeError, ValueError):
        return None


def _linux_process_executable(pid: int) -> str | None:
    try:
        executable = os.readlink(Path("/proc") / str(pid) / "exe")
        if not executable or executable.endswith(" (deleted)"):
            return None
        return executable
    except OSError:
        return None


def _parse_linux_process_cmdline(raw: bytes) -> tuple[str, ...] | None:
    if not raw or len(raw) > _PROCESS_ARGS_MAX_BYTES or not raw.endswith(b"\0"):
        return None
    return tuple(os.fsdecode(item) for item in raw[:-1].split(b"\0"))


def _linux_process_argv(pid: int) -> tuple[str, ...] | None:
    try:
        with (Path("/proc") / str(pid) / "cmdline").open("rb") as handle:
            raw = handle.read(_PROCESS_ARGS_MAX_BYTES + 1)
    except OSError:
        return None
    return _parse_linux_process_cmdline(raw)


def _darwin_process_argv(
    pid: int,
    *,
    allowed_argv0: Sequence[bytes],
    expected_argv_tail: Sequence[str],
) -> tuple[str, ...] | None:
    """Read argv with KERN_PROCARGS2; do not copy or expose its envp tail."""
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        sysctl = libc.sysctl
        sysctl.argtypes = [
            ctypes.POINTER(ctypes.c_int), ctypes.c_uint,
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_size_t),
            ctypes.c_void_p, ctypes.c_size_t,
        ]
        sysctl.restype = ctypes.c_int
        argmax_mib = (ctypes.c_int * 2)(_DARWIN_CTL_KERN, _DARWIN_KERN_ARGMAX)
        argmax = ctypes.c_int()
        argmax_length = ctypes.c_size_t(ctypes.sizeof(argmax))
        if (
            sysctl(
                argmax_mib, 2, ctypes.byref(argmax), ctypes.byref(argmax_length),
                None, 0,
            ) != 0
            or argmax_length.value != ctypes.sizeof(argmax)
            or not _PROCESS_ARGS_MIN_BYTES <= argmax.value <= _PROCESS_ARGS_MAX_BYTES
        ):
            return None

        buffer = bytearray(argmax.value)
        c_buffer = (ctypes.c_char * len(buffer)).from_buffer(buffer)
        try:
            process_mib = (
                ctypes.c_int * 3
            )(_DARWIN_CTL_KERN, _DARWIN_KERN_PROCARGS2, pid)
            used_length = ctypes.c_size_t(len(buffer))
            if sysctl(
                process_mib, 3, ctypes.cast(c_buffer, ctypes.c_void_p),
                ctypes.byref(used_length), None, 0,
            ) != 0:
                return None
            return _parse_darwin_procargs2(
                buffer,
                used_length.value,
                allowed_argv0=allowed_argv0,
                expected_argv_tail=expected_argv_tail,
            )
        finally:
            ctypes.memset(ctypes.addressof(c_buffer), 0, len(buffer))
    except (OSError, AttributeError, TypeError, ValueError):
        return None


def _proxy_peer_identity(
    pid: int,
    *,
    allowed_argv0: Sequence[bytes],
    expected_argv_tail: Sequence[str],
) -> _ProxyPeerIdentity | None:
    """Read a PID-bracketed proxy identity without parsing ancestor argv."""
    if pid <= 1:
        return None
    if sys.platform.startswith("linux"):
        before = _linux_process_snapshot(pid)
        executable = _linux_process_executable(pid)
        argv = _linux_process_argv(pid)
        after = _linux_process_snapshot(pid)
        executable_after = _linux_process_executable(pid)
        if (
            before is None or after != before or executable is None
            or executable_after is None
            or not _same_executable(executable, executable_after)
            or argv is None
        ):
            return None
        return _ProxyPeerIdentity(before[0], executable, argv)
    if sys.platform == "darwin":
        before = _darwin_process_snapshot(pid)
        executable = _darwin_process_executable(pid)
        argv = _darwin_process_argv(
            pid,
            allowed_argv0=allowed_argv0,
            expected_argv_tail=expected_argv_tail,
        )
        executable_after = _darwin_process_executable(pid)
        after = _darwin_process_snapshot(pid)
        if (
            before is None or after != before or executable is None
            or executable_after is None
            or not _same_executable(executable, executable_after)
            or argv is None
        ):
            return None
        return _ProxyPeerIdentity(before[0], executable, argv)
    return None


def _unix_peer_credentials(connection: socket.socket) -> tuple[int, int] | None:
    """Return peer pid/uid from kernel credentials, failing closed elsewhere."""
    if sys.platform == "darwin":
        try:
            # CPython does not expose these Darwin constants consistently.
            # Values are from the Darwin SOL_LOCAL socket option ABI.
            peer_pid_option = getattr(socket, "LOCAL_PEERPID", _DARWIN_LOCAL_PEERPID)
            peer_cred_option = getattr(socket, "LOCAL_PEERCRED", _DARWIN_LOCAL_PEERCRED)
            level = getattr(socket, "SOL_LOCAL", _DARWIN_SOL_LOCAL)
            pid_raw = connection.getsockopt(level, peer_pid_option, struct.calcsize("i"))
            cred_raw = connection.getsockopt(level, peer_cred_option, 80)
            pid = struct.unpack("i", pid_raw)[0]
            # xucred begins with version, effective uid, and group count.
            version = struct.unpack_from("i", cred_raw)[0]
            if version != 0:
                return None
            uid = struct.unpack_from("i", cred_raw, 4)[0]
            return pid, uid
        except (AttributeError, OSError, struct.error):
            return None
    if sys.platform.startswith("linux") and hasattr(socket, "SO_PEERCRED"):
        try:
            raw = connection.getsockopt(
                socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")
            )
            pid, uid, _gid = struct.unpack("3i", raw)
            return pid, uid
        except (OSError, struct.error):
            return None
    return None
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


def _nex_snapshot_excludes(name: str, *, is_directory: bool) -> bool:
    """The one entry filter shared by capture and validation snapshots.

    Both envelopes are compared file-by-file (``reviewed-files-unchanged``),
    so they must drop exactly the same entries: credential-shaped names and the
    supervisor's own ``failure.json`` diagnostic. Oversized and non-regular
    files are dropped by :func:`_nex_snapshot_read_file` for both as well.
    """

    if _review_entry_is_sensitive(name):
        return True
    return not is_directory and name == "failure.json"


class _NexSnapshotBoundExceeded(Exception):
    """A file grew past the snapshot bound between fstat and read."""


def _nex_snapshot_read_file(
    path: Path, *, skip_oversize: bool = True
) -> tuple[bytes, int] | None:
    """Read one bounded regular file without following a final symlink.

    Returns ``None`` for skipped entries: non-regular files, and (when
    ``skip_oversize``) files larger than the per-file bound at fstat time.
    Raises ``OSError`` when the file is unreadable and
    ``_NexSnapshotBoundExceeded`` when it is (or grew) past the bound and is
    not skipped.
    """

    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            return None
        if info.st_size > _NEX_MAX_SNAPSHOT_FILE_BYTES:
            if skip_oversize:
                return None
            raise _NexSnapshotBoundExceeded()
        data = os.read(descriptor, _NEX_MAX_SNAPSHOT_FILE_BYTES + 1)
        if len(data) > _NEX_MAX_SNAPSHOT_FILE_BYTES:
            raise _NexSnapshotBoundExceeded()
        return bytes(data), stat.S_IMODE(info.st_mode)
    finally:
        os.close(descriptor)


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
    except (OSError, RuntimeError, ValueError):
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
    from startup fixes that discovery path. If an app-server version does not
    propagate MCP tools into a reviewer child, the Codex route fails incomplete
    rather than assuming a child sandbox policy or falling back to shell reads.
    The ``_review_reader_result`` still fails closed until the runner publishes
    the current review paths, so catalog visibility does not grant access to
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


def _nex_result_payload(message: Mapping[str, Any]) -> Mapping[str, Any]:
    """Read the native supervisor JSON from exactly one JSON text block.

    The native supervisor serializes typed tool results into a single MCP text
    block and does not send structuredContent. Enforce that exact shape; never
    infer fields from prose or ambiguous multi-block content.
    """
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


def _nex_tool_result_text(content: Any) -> str:
    """Flatten a Claude tool_result body to its text parts only."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, Mapping) and isinstance(block.get("text"), str):
            parts.append(block["text"])
    return "\n".join(parts)


def _nex_snapshot_sha256(envelope: Mapping[str, Any]) -> str:
    """Bind frozen bytes to their exact RPC, generation, and logical root."""
    files = envelope.get("files")
    if not isinstance(files, Mapping):
        raise ValueError("snapshot files must be a mapping")
    manifest: list[dict[str, Any]] = []
    for path, entry in sorted(files.items(), key=lambda item: str(item[0])):
        if not isinstance(path, str) or not isinstance(entry, Mapping):
            raise ValueError("snapshot file entry is malformed")
        content = entry.get("content")
        mode = entry.get("mode", 0)
        if not isinstance(content, bytes) or not isinstance(mode, int) or isinstance(mode, bool):
            raise ValueError("snapshot file bytes or mode are malformed")
        manifest.append({
            "path": os.path.normpath(path),
            "sha256": hashlib.sha256(content).hexdigest(),
            "mode": mode,
        })
    binding = {
        "jsonrpc_id": json.dumps(
            [
                type(envelope.get("jsonrpc_id", envelope.get("capture_jsonrpc_id"))).__name__,
                envelope.get("jsonrpc_id", envelope.get("capture_jsonrpc_id")),
            ],
            sort_keys=True,
            separators=(",", ":"),
        ),
        "workflow": envelope.get("workflow"),
        "root": os.path.normpath(str(envelope.get("root", ""))),
        "generation": envelope.get("generation"),
        "expected_base_url": envelope.get("expected_base_url"),
        "files": manifest,
    }
    encoded = json.dumps(
        binding, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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


def _request_root(request: Mapping[str, Any]) -> str | None:
    """Return an explicit authoring root from a direct or typed action field."""
    params = request.get("params")
    arguments = params.get("arguments") if isinstance(params, Mapping) else None
    if not isinstance(arguments, Mapping):
        return None
    for key in ("authoring_root", "root", "definition"):
        value = arguments.get(key)
        if isinstance(value, str):
            return value
    action = arguments.get("action")
    action_params = action.get("parameters") if isinstance(action, Mapping) else None
    if isinstance(action_params, Mapping):
        for key in ("authoring_root", "root", "definition"):
            value = action_params.get(key)
            if isinstance(value, str):
                return value
    return None


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


def _action_requirement_id(action: Mapping[str, Any]) -> Any:
    """Read a tagged action's requirement id, rejecting conflicting aliases."""
    parameters = action.get("parameters")
    if isinstance(parameters, Mapping) and "requirement_id" in parameters:
        nested = parameters.get("requirement_id")
        if "requirement_id" in action and action.get("requirement_id") != nested:
            return None
        return nested
    return action.get("requirement_id")


def _is_review_requirement_report(action: object) -> bool:
    return bool(
        isinstance(action, Mapping)
        and action.get("type") == "report_requirement"
        and _action_requirement_id(action) == "review"
    )


def _review_guard_decision(
    action: object, *, nex_mode: bool, review_child_returned: bool
) -> tuple[bool, bool]:
    """Return (blocked, invalidate) for a tool call while review is pending."""
    if _is_review_requirement_report(action):
        if nex_mode and not review_child_returned:
            return True, True
        return False, False
    return True, False


def _is_nex_validation_advance(request: Mapping[str, Any]) -> bool:
    """Identify canonical workflow-v2 validation starts plus legacy aliases."""
    if _request_operation(request) != "advance_workflow":
        return False
    action = _request_action(request)
    if not isinstance(action, Mapping):
        return False
    action_type = action.get("type")
    if action_type in {"validate", "validation"}:
        return True
    return (
        action_type == "start_requirement"
        and _action_requirement_id(action) == "validation"
    )


def _nex_alias_path(value: str | os.PathLike[str]) -> str:
    """Normalize macOS /private aliases without resolving caller path identity."""
    normalized = os.path.normpath(os.path.abspath(os.fspath(value)))
    if normalized.startswith("/private/"):
        normalized = normalized[len("/private"):]
    return normalized


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


_NEX_READER_CLIENT_ERROR_REASONS = (
    (("exceeds maximum allowed tokens", "max_mcp_output_tokens"),
     "review reader reply was served but the client rejected it: output token limit"),
    (("permission", "denied", "hook"),
     "review reader reply was served but the client rejected it: denied"),
    (("timed out", "timeout"),
     "review reader reply was served but the client rejected it: timeout"),
    (("schema", "structuredcontent", "validation"),
     "review reader reply was served but the client rejected it: result schema"),
)


def _nex_reader_client_error_reason(content: Any, *, siblings: Any = None) -> str:
    """Name why the client failed a served reader reply, as a fixed runner string.

    Only the category, the matched fixed marker and the count of identical
    pending calls at bind time are kept; the client's text never reaches the
    reason.
    """

    text = json.dumps(content, ensure_ascii=False).casefold()
    count = siblings if isinstance(siblings, int) and not isinstance(siblings, bool) else -1
    for needles, reason in _NEX_READER_CLIENT_ERROR_REASONS:
        for needle in needles:
            if needle in text:
                return f"{reason} (marker={needle}; siblings={count})"
    return f"review reader response or stream tool_result was unsuccessful (siblings={count})"


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
        if value.get("code") == "workflow/review_satisfied":
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
        nex_mode: bool = False,
        nex_workspace: Path | None = None,
        nex_protected_paths: Sequence[Path] = (),
        nex_expected_base_url: str | None = None,
        idle_timeout_seconds: float = 180.0,
        nex_preflight_mode: bool = False,
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
        self._nex_redaction_values = tuple(
            value for key, value in self.server_env.items()
            if nex_mode and key == _SOURCE_CREDENTIAL_ENV and value
        )
        self.server_name = server_name
        self.allowed_tools = (
            tuple(allowed_tools)
            if allowed_tools is not None
            else (f"mcp__{server_name}__*",)
        )
        self.workflow_action_guard = bool(workflow_action_guard)
        self.nex_mode = bool(nex_mode)
        self.nex_workspace = Path(nex_workspace).resolve() if nex_workspace else None
        self.nex_expected_base_url = nex_expected_base_url
        self.nex_protected_paths = tuple(
            Path(path).resolve() for path in nex_protected_paths
        )
        self.idle_timeout_seconds = float(idle_timeout_seconds)
        self.nex_preflight_mode = bool(nex_preflight_mode)
        self.nex_settings_path: Path | None = None
        self._nex_policy_hook_path: Path | None = None
        self._nex_policy_hashes: dict[Path, str] = {}
        self.request_timeout_faults = dict(request_timeout_faults or {})
        self.startup_timeout_s = startup_timeout_s
        self.shutdown_timeout_s = shutdown_timeout_s
        self._provided_root = Path(root) if root is not None else None
        self._temp: tempfile.TemporaryDirectory[str] | None = None
        self._root: Path | None = None
        self._attached: list[subprocess.Popen[Any]] = []
        self._attached_event = threading.Event()
        self._bridge_listener: socket.socket | None = None
        self._bridge_connection: socket.socket | None = None
        self._bridge_thread: threading.Thread | None = None
        self._bridge_connections: set[socket.socket] = set()
        self._bridge_workers: set[threading.Thread] = set()
        self._bridge_state_lock = threading.Lock()
        self._nex_stream_condition = threading.Condition(self._bridge_state_lock)
        self._nex_last_monotonic_ns = 0
        self._nex_invalid_reason: str | None = None
        self._nex_connection_claimed = False
        self._nex_connection_count = 0
        self._nex_authenticated_peer: dict[str, Any] | None = None
        self._nex_trace: list[dict[str, Any]] = []
        self._nex_bridge_secret_leak = False
        self._nex_stream_uses: list[dict[str, Any]] = []
        self._nex_stream_results: dict[str, dict[str, Any]] = {}
        self._nex_preflight_events: list[dict[str, Any]] = []
        self._nex_pending_requests: dict[str, dict[str, Any]] = {}
        self._nex_server_request_ids: set[str] = set()
        self._nex_server_requests: dict[str, Mapping[str, Any]] = {}
        self._nex_active_workflow: str | None = None
        # Last known authoring root per workflow. A call that names no root
        # binds to its own workflow's root, never to another cycle's.
        self._nex_workflow_roots: dict[str, str] = {}
        self._nex_active_child_id: str | None = None
        self._nex_child_count = 0
        self._nex_children_by_workflow: dict[str, int] = {}
        self._nex_child_returned_by_workflow: dict[str, bool] = {}
        self._nex_review_read_success = False
        self._nex_review_read_child_id: str | None = None
        self._nex_review_child_returned = False
        self._nex_review_snapshot: dict[str, bytes] = {}
        self._nex_review_directories: set[str] = set()
        self._nex_review_aliases: dict[str, str] = {}
        self._nex_case_snapshots: dict[str, dict[str, Any]] = {}
        # Export archives frozen when their successful response crossed the
        # bridge, keyed by JSON-RPC id key; the agent can still write the
        # workspace afterwards, so these bytes are the graded evidence.
        self._nex_frozen_exports: dict[str, dict[str, Any]] = {}
        self._nex_pending_static_snapshots: list[dict[str, Any]] = []
        self._nex_static_snapshots_attached = False
        self._nex_agent_exited = False
        self._nex_intentional_shutdown = False
        # Diagnostic-only bridge state, runner memory only. Pending JSON-RPC
        # id keys never leave this map; result_metrics() exposes counts,
        # booleans, exit codes, and allowlisted method labels. None of it
        # feeds _nex_invalid_reason, the trace, or grading.
        self._nex_forwarded_pending: dict[str, tuple[str, float]] = {}
        self._nex_bridge_counts = {
            "forwarded_requests": 0,
            "matched_responses": 0,
            "unmatched_responses": 0,
            "non_json_response_lines": 0,
        }
        self._nex_supervisor_stdout_eof = False
        self._nex_supervisor_shutdown_requested_at_eof: bool | None = None
        self._nex_supervisor_exit_code: int | None = None
        self._nex_supervisor_shutdown_requested_at_exit: bool | None = None
        self._nex_agent_exit_snapshot: dict[str, Any] | None = None
        # The whole diagnostics payload, published once at the after-drain
        # boundary as immutable JSON text so no reader or surviving handler
        # can alter any counter or snapshot after it.
        self._nex_final_diagnostics: str | None = None
        self._nex_last_activity = time.monotonic()
        self._review_guard_state: dict[str, Any] | None = None
        self._review_capture_in_flight = False
        self._bridge_stop = threading.Event()
        self._bridge_path: Path | None = None
        self._server_spec_path: Path | None = None
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
            if self.nex_mode:
                self._prepare_nex_security_files()
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
                "result_path": str(self.server_result_path),
                "review_allowlist_path": str(self.review_allowlist_path),
                "shutdown_timeout_s": self.shutdown_timeout_s,
                "request_timeout_faults": self.request_timeout_faults,
                "nex_mode": self.nex_mode,
            }
            if not self.nex_mode:
                spec["trace_path"] = str(self.trace_path)
            spec_path = self.root / "server-spec.json"
            self._server_spec_path = spec_path
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
            if not self.nex_mode:
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
        """Register the Claude process and release the deferred NEX bridge accept."""
        self._attached.append(proc)
        self.touch_nex_activity()
        self._attached_event.set()

    def touch_nex_activity(self) -> None:
        if not self.nex_mode:
            return
        with self._bridge_state_lock:
            self._nex_last_activity = time.monotonic()

    def last_nex_activity(self) -> float:
        with self._bridge_state_lock:
            return self._nex_last_activity

    def invalidate_nex(self, reason: str) -> None:
        self._nex_invalidate(reason)

    def _prepare_nex_security_files(self) -> None:
        if self._root is None or self.nex_workspace is None:
            raise DesktopStdioError("NEX-890 write policy requires a workspace")
        source_hook = Path(__file__).with_name("nex890_write_policy_hook.py")
        if not source_hook.is_file():
            raise DesktopStdioError("NEX-890 write-policy hook source is missing")
        hook_path = self.root / "nex-write-policy-hook.py"
        shutil.copyfile(source_hook, hook_path)
        hook_path.chmod(0o400)
        self._nex_policy_hook_path = hook_path
        settings_path = self.root / "claude-settings.json"
        self.nex_settings_path = settings_path
        hook_command = shlex.join([
            shutil.which("python3") or sys.executable,
            "-I",
            str(hook_path),
            "--workspace",
            str(self.nex_workspace),
            "--private-root",
            str(self.root.resolve()),
            *[item for path in self.nex_protected_paths for item in ("--plugin-root", str(path))],
        ])
        settings = {
            "permissions": {
                "deny": [
                    "Bash", "BashOutput", "KillShell", "Monitor", "PowerShell",
                    "Write(.claude/**)", "Edit(.claude/**)", "MultiEdit(.claude/**)",
                    "NotebookEdit(.claude/**)", "Write(.mcp.json)", "Edit(.mcp.json)",
                    "MultiEdit(.mcp.json)", "NotebookEdit(.mcp.json)",
                ],
            },
            "hooks": {
                "PreToolUse": [{
                    "matcher": ".*",
                    "hooks": [{"type": "command", "command": hook_command}],
                }],
            },
        }
        _write_private_text(
            settings_path,
            json.dumps(settings, sort_keys=True, separators=(",", ":")),
        )
        settings_path.chmod(0o400)
        self._nex_policy_hashes = {
            hook_path: hashlib.sha256(hook_path.read_bytes()).hexdigest(),
            settings_path: hashlib.sha256(settings_path.read_bytes()).hexdigest(),
        }

    def verify_nex_security_files(self) -> bool:
        if not self.nex_mode:
            return True
        if not self._nex_policy_hashes:
            self._nex_invalidate("NEX-890 write-policy state was not initialized")
            return False
        for path, expected in self._nex_policy_hashes.items():
            try:
                if path.is_symlink() or not path.is_file():
                    raise OSError("policy file is unavailable")
                actual = hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError:
                self._nex_invalidate("NEX-890 write-policy state was replaced or removed")
                return False
            if actual != expected:
                self._nex_invalidate("NEX-890 write-policy state changed during the cell")
                return False
        return True

    def record_agent(self, *, status: str, error: str | None = None) -> None:
        self.agent_result = StdioOutcome(
            status, redact_text(error) if error else None
        )
        if self.nex_mode:
            with self._bridge_state_lock:
                self._nex_capture_agent_exit_locked()
                self._nex_agent_exited = True
                self._nex_intentional_shutdown = True

    def _nex_pending_snapshot_locked(self) -> dict[str, Any]:
        """Summarize unanswered forwarded requests without their ids."""
        methods: dict[str, int] = {}
        for label, _started in self._nex_forwarded_pending.values():
            methods[label] = methods.get(label, 0) + 1
        oldest = min(
            (started for _label, started in self._nex_forwarded_pending.values()),
            default=None,
        )
        return {
            "supervisor_stdout_eof": self._nex_supervisor_stdout_eof,
            "pending_count": len(self._nex_forwarded_pending),
            "pending_methods": dict(sorted(methods.items())),
            "oldest_pending_age_s": (
                None if oldest is None
                else round(max(0.0, time.monotonic() - oldest), 1)
            ),
        }

    def _nex_capture_agent_exit_locked(self) -> None:
        """Take the agent-exit snapshot once, before intentional shutdown."""
        if self._nex_agent_exit_snapshot is None:
            self._nex_agent_exit_snapshot = self._nex_pending_snapshot_locked()

    def _nex_note_forwarded(self, request: Any) -> str | None:
        """Track one id-bearing request about to be written to the supervisor."""
        if not isinstance(request, Mapping) or "method" not in request:
            return None
        key = _rpc_id_key(request.get("id"))
        if key is None:
            return None
        method = request.get("method")
        label = (
            method
            if isinstance(method, str) and method in _NEX_DIAG_METHOD_LABELS
            else "other"
        )
        with self._bridge_state_lock:
            self._nex_bridge_counts["forwarded_requests"] += 1
            self._nex_forwarded_pending[key] = (label, time.monotonic())
        return key

    def _nex_forget_forwarded(self, key: str | None) -> None:
        """Undo _nex_note_forwarded when the supervisor write itself failed."""
        if key is None:
            return
        with self._bridge_state_lock:
            if self._nex_forwarded_pending.pop(key, None) is not None:
                self._nex_bridge_counts["forwarded_requests"] -= 1

    def _nex_note_supervisor_line(self, response: Any, server_message: bool) -> None:
        """Count one supervisor stdout line against the forwarded requests."""
        with self._bridge_state_lock:
            if not isinstance(response, Mapping):
                self._nex_bridge_counts["non_json_response_lines"] += 1
            elif not server_message:
                key = _rpc_id_key(response.get("id"))
                if key is not None and self._nex_forwarded_pending.pop(key, None) is not None:
                    self._nex_bridge_counts["matched_responses"] += 1
                else:
                    self._nex_bridge_counts["unmatched_responses"] += 1

    def _nex_bridge_diagnostics_locked(
        self, after_drain: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return {
            **self._nex_bridge_counts,
            "supervisor_stdout_eof": self._nex_supervisor_stdout_eof,
            "supervisor_shutdown_requested_at_eof": self._nex_supervisor_shutdown_requested_at_eof,
            "supervisor_exit_code": self._nex_supervisor_exit_code,
            "supervisor_shutdown_requested_at_exit": self._nex_supervisor_shutdown_requested_at_exit,
            "agent_exit": copy.deepcopy(self._nex_agent_exit_snapshot),
            "after_drain": after_drain,
        }

    def _nex_bridge_diagnostics(self) -> dict[str, Any]:
        """Return the frozen final payload once published, else live values."""
        with self._bridge_state_lock:
            if self._nex_final_diagnostics is not None:
                return json.loads(self._nex_final_diagnostics)
            return self._nex_bridge_diagnostics_locked()

    @staticmethod
    def _nex_tool_name(value: object) -> str | None:
        if not isinstance(value, str):
            return None
        prefix = f"mcp__{DesktopStdioSession.SERVER_NAME}__"
        return value[len(prefix):] if value.startswith(prefix) else value

    @staticmethod
    def _nex_json(value: object) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    def _nex_timestamp_locked(self) -> int:
        """Allocate one strictly increasing timestamp under the bridge lock."""
        current = max(time.monotonic_ns(), self._nex_last_monotonic_ns + 1)
        self._nex_last_monotonic_ns = current
        return current

    def _nex_invalidate(self, reason: str) -> None:
        with self._bridge_state_lock:
            if self._nex_invalid_reason is None:
                self._nex_invalid_reason = reason

    def _nex_mark_review_child_returned_locked(self, child_id: str) -> None:
        child = self._nex_stream_results.get(child_id)
        if not (
            child is not None
            and child.get("kind") == "child"
            and child.get("success") is True
            and self._nex_review_read_success
            and self._nex_review_read_child_id == child_id
        ):
            return
        self._nex_review_child_returned = True
        workflow = child.get("workflow")
        if isinstance(workflow, str):
            self._nex_child_returned_by_workflow[workflow] = True

    def observe_claude_stream_event(self, event: Mapping[str, Any]) -> None:
        """Incrementally register Claude tool uses and child returns in memory."""
        if not self.nex_mode:
            return
        self.touch_nex_activity()
        kind = event.get("type")
        message = event.get("message")
        parent_id = event.get("parent_tool_use_id")
        if not isinstance(parent_id, str) and isinstance(message, Mapping):
            parent_id = message.get("parent_tool_use_id")
        if not isinstance(parent_id, str):
            parent_id = None
        if self.nex_preflight_mode and kind == "result":
            # An absent field is not an empty list: absence only disables the
            # canary's CLI denial-ID fallback, while a present value is graded.
            denials_present = "permission_denials" in event
            with self._nex_stream_condition:
                self._nex_preflight_events.append({
                    "kind": "result",
                    "is_error": event.get("is_error"),
                    "subtype": event.get("subtype"),
                    "permission_denials_present": denials_present,
                    "permission_denials": (
                        copy.deepcopy(event.get("permission_denials"))
                        if denials_present else None
                    ),
                    "timestamp_monotonic_ns": self._nex_timestamp_locked(),
                })
                self._nex_stream_condition.notify_all()
        if kind == "assistant":
            blocks = message.get("content", []) if isinstance(message, Mapping) else []
            if not isinstance(blocks, list):
                return
            with self._nex_stream_condition:
                for block in blocks:
                    if not isinstance(block, Mapping) or block.get("type") != "tool_use":
                        continue
                    name = block.get("name")
                    identifier = block.get("id")
                    arguments = block.get("input", {})
                    if self.nex_preflight_mode:
                        self._nex_preflight_events.append({
                            "kind": "tool_use", "id": identifier, "name": name,
                            "input": copy.deepcopy(arguments),
                            "parent_tool_use_id": parent_id,
                            "timestamp_monotonic_ns": self._nex_timestamp_locked(),
                        })
                    if not isinstance(name, str) or not isinstance(identifier, str):
                        self._nex_invalid_reason = self._nex_invalid_reason or "malformed Claude tool_use"
                        continue
                    if identifier in self._nex_stream_results or any(
                        use.get("id") == identifier for use in self._nex_stream_uses
                    ):
                        self._nex_invalid_reason = self._nex_invalid_reason or "duplicate Claude tool_use id"
                        continue
                    if name.casefold() in {"task", "agent"}:
                        if (
                            parent_id is not None
                            or self._nex_active_child_id is not None
                            or not isinstance(arguments, Mapping)
                            or arguments.get("run_in_background") is not False
                        ):
                            self._nex_invalid_reason = self._nex_invalid_reason or "nested or background review child"
                            continue
                        self._nex_child_count += 1
                        self._nex_active_child_id = identifier
                        state = self._review_guard_state or {}
                        workflow = state.get("workflow")
                        if isinstance(workflow, str):
                            self._nex_children_by_workflow[workflow] = (
                                self._nex_children_by_workflow.get(workflow, 0) + 1
                            )
                            if self._nex_children_by_workflow[workflow] > 1:
                                self._nex_invalid_reason = (
                                    self._nex_invalid_reason
                                    or "more than one foreground review child was used for a workflow"
                                )
                        self._nex_stream_results[identifier] = {
                            "kind": "child", "success": False,
                            "tool_result_seen": False,
                            "workflow": workflow if isinstance(workflow, str) else None,
                        }
                        continue
                    normalized = self._nex_tool_name(name)
                    if normalized is not None and name.startswith("mcp__"):
                        self._nex_stream_uses.append({
                            "id": identifier,
                            "name": normalized,
                            "arguments": arguments,
                            "parent_tool_use_id": parent_id,
                            "matched": False,
                            "response": False,
                            "tool_result": False,
                        })
                self._nex_stream_condition.notify_all()
        elif kind == "user":
            blocks = message.get("content", []) if isinstance(message, Mapping) else []
            if not isinstance(blocks, list):
                return
            with self._nex_stream_condition:
                for block in blocks:
                    if not isinstance(block, Mapping) or block.get("type") != "tool_result":
                        continue
                    identifier = block.get("tool_use_id")
                    error = block.get("is_error") is True
                    if self.nex_preflight_mode:
                        # Record malformed IDs before the skip below so the
                        # canary fails closed on them. Only redacted text is
                        # retained; truncation is measured after redaction.
                        text, _leaked = self.redact_nex_text(
                            _nex_tool_result_text(block.get("content", ""))
                        )
                        self._nex_preflight_events.append({
                            "kind": "tool_result",
                            "id": identifier if isinstance(identifier, str) else None,
                            "malformed_id": not isinstance(identifier, str),
                            "is_error": error,
                            "content": text[:_NEX_PREFLIGHT_RESULT_TEXT_CHARS],
                            "content_truncated": len(text) > _NEX_PREFLIGHT_RESULT_TEXT_CHARS,
                            "timestamp_monotonic_ns": self._nex_timestamp_locked(),
                        })
                    if not isinstance(identifier, str):
                        continue
                    child = self._nex_stream_results.get(identifier)
                    if child is not None and child.get("kind") == "child":
                        if child.get("tool_result_seen"):
                            self._nex_invalid_reason = self._nex_invalid_reason or "duplicate review child tool_result"
                            continue
                        child["tool_result_seen"] = True
                        text = json.dumps(block.get("content", ""), ensure_ascii=False).casefold()
                        success = not error and "async agent launched" not in text
                        child["success"] = success
                        if not success:
                            self._nex_invalid_reason = self._nex_invalid_reason or "review child did not return successfully in foreground"
                        else:
                            self._nex_mark_review_child_returned_locked(identifier)
                        if self._nex_active_child_id == identifier:
                            self._nex_active_child_id = None
                        continue
                    for use in self._nex_stream_uses:
                        if use.get("id") == identifier:
                            if use.get("tool_result"):
                                self._nex_invalid_reason = self._nex_invalid_reason or "duplicate MCP tool_result"
                                break
                            use["tool_result"] = True
                            use["tool_result_success"] = not error
                            if use.get("name") == _REVIEW_READER_TOOL:
                                if not use.get("response_success"):
                                    # The reader refused this call (bad path,
                                    # bounds or operation) and said so to the
                                    # reviewer; it served nothing, so pairing
                                    # stays intact. The review proof still
                                    # needs a successful read.
                                    pass
                                elif error:
                                    self._nex_invalid_reason = self._nex_invalid_reason or (
                                        _nex_reader_client_error_reason(
                                            block.get("content", ""),
                                            siblings=use.get("identical_pending_at_match"),
                                        )
                                    )
                                else:
                                    parent_tool_use_id = use.get("parent_tool_use_id")
                                    if isinstance(parent_tool_use_id, str):
                                        self._nex_review_read_success = True
                                        self._nex_review_read_child_id = parent_tool_use_id
                                        self._nex_mark_review_child_returned_locked(parent_tool_use_id)
                            # A valid MCP tool result may report an expected
                            # profile/validation failure. The deterministic
                            # checker grades that response; transport pairing
                            # remains complete and is not invalidated here.
                            break
                self._nex_stream_condition.notify_all()

    def nex_preflight_events(self) -> list[dict[str, Any]]:
        with self._bridge_state_lock:
            return copy.deepcopy(self._nex_preflight_events)

    def _nex_match_tool_call(
        self, request: Mapping[str, Any]
    ) -> tuple[dict[str, Any] | None, str | None]:
        params = request.get("params")
        if not isinstance(params, Mapping):
            return None, "MCP tools/call has malformed params"
        name = self._nex_tool_name(params.get("name"))
        arguments = params.get("arguments", {})
        deadline = time.monotonic() + _NEX_STREAM_PAIR_WAIT_S

        def argument_fingerprint(value: object) -> str:
            payload = self._nex_json(value).encode("utf-8")
            return hashlib.sha256(payload).hexdigest()[:12]

        with self._nex_stream_condition:
            if self._nex_invalid_reason is not None:
                return None, self._nex_invalid_reason
            candidates = [use for use in self._nex_stream_uses if not use.get("matched")]

            def matching_uses() -> list[dict[str, Any]]:
                return [
                    use for use in candidates
                    if name == use.get("name")
                    and self._nex_json(arguments) == self._nex_json(use.get("arguments", {}))
                    and (
                        (
                            self._nex_active_child_id is not None
                            and name == _REVIEW_READER_TOOL
                            and use.get("parent_tool_use_id") == self._nex_active_child_id
                        )
                        or (
                            self._nex_active_child_id is None
                            and name != _REVIEW_READER_TOOL
                            and use.get("parent_tool_use_id") is None
                        )
                    )
                ]

            exact_matches = matching_uses()
            while not exact_matches and self._nex_invalid_reason is None:
                if (
                    self._nex_active_child_id is not None
                    and name != _REVIEW_READER_TOOL
                ):
                    self._nex_invalid_reason = "parent MCP call arrived while review child is active"
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    request_hash = argument_fingerprint(arguments)
                    candidate_summary = ",".join(
                        f"{use.get('name')}:{argument_fingerprint(use.get('arguments', {}))}"
                        for use in candidates
                    )
                    reader_candidates = [
                        use for use in candidates
                        if use.get("name") == _REVIEW_READER_TOOL
                    ]
                    relationship_summary = (
                        f"active_child={bool(self._nex_active_child_id)},"
                        "reader_parent_present="
                        f"{any(bool(use.get('parent_tool_use_id')) for use in reader_candidates)},"
                        "reader_parent_matches_active="
                        f"{self._nex_active_child_id is not None and any(use.get('parent_tool_use_id') == self._nex_active_child_id for use in reader_candidates)}"
                    )
                    self._nex_invalid_reason = (
                        "MCP tools/call has no preceding matching Claude stream tool_use"
                        f" (tool={name!r}, arguments_sha256={request_hash},"
                        f" {relationship_summary}, candidates=[{candidate_summary}])"
                    )
                    break
                self._nex_stream_condition.wait(timeout=remaining)
                candidates = [use for use in self._nex_stream_uses if not use.get("matched")]
                exact_matches = matching_uses()
            if self._nex_invalid_reason is not None:
                return None, self._nex_invalid_reason
            child_id = self._nex_active_child_id
            if child_id is not None and name != _REVIEW_READER_TOOL:
                self._nex_invalid_reason = "parent MCP call arrived while review child is active"
                return None, self._nex_invalid_reason
            # Identical unmatched tool_use blocks (same normalized name,
            # canonical arguments, and parent linkage -- all enforced by
            # matching_uses) are interchangeable: only their stream ids differ,
            # and each id is still paired with exactly one response and one
            # tool_result. Claude dispatches tool_use blocks in stream order,
            # so bind the oldest one (FIFO). A use whose tool_result already
            # arrived was answered without reaching this bridge (e.g. denied
            # client-side) and is skipped. Candidates whose recorded state
            # differs in any other way are genuinely ambiguous.
            pending = [use for use in exact_matches if not use.get("tool_result")]
            if not pending:
                self._nex_invalid_reason = "MCP tools/call ambiguously matches Claude stream tool_use events"
                return None, self._nex_invalid_reason
            identity = {
                self._nex_json({
                    key: value for key, value in use.items() if key != "id"
                })
                for use in pending
            }
            if len(identity) != 1:
                self._nex_invalid_reason = "MCP tools/call ambiguously matches Claude stream tool_use events"
                return None, self._nex_invalid_reason
            use = pending[0]
            use["identical_pending_at_match"] = len(pending) - 1
            expected_parent = use.get("parent_tool_use_id")
            if name == _REVIEW_READER_TOOL:
                if child_id is None or expected_parent != child_id:
                    self._nex_invalid_reason = "review reader call lacks the pinned foreground child linkage"
                    return None, self._nex_invalid_reason
                state = self._review_guard_state or {}
                review_input = state.get("review_input")
                if not isinstance(review_input, Mapping):
                    self._nex_invalid_reason = "review reader call has no current capture root"
                    return None, self._nex_invalid_reason
                arguments_map = arguments if isinstance(arguments, Mapping) else {}
                requested_path = arguments_map.get("path")
                if requested_path not in {
                    review_input.get("retained_capture_root"),
                    review_input.get("retained_blueprint_path"),
                } and self._nex_path_key(requested_path) not in self._nex_review_aliases:
                    self._nex_invalid_reason = "review reader path does not match the current captured review input"
                    return None, self._nex_invalid_reason
            elif expected_parent is not None or child_id is not None:
                self._nex_invalid_reason = "parent MCP call carries an unexpected child identity"
                return None, self._nex_invalid_reason
            use["matched"] = True
            request_key = _rpc_id_key(request.get("id"))
            if request_key is None:
                self._nex_invalid_reason = "MCP tools/call has invalid JSON-RPC id"
                return None, self._nex_invalid_reason
            self._nex_pending_requests[request_key] = use
            return use, None

    @staticmethod
    def _nex_path_key(value: object) -> str | None:
        if not isinstance(value, str) or not value or not os.path.isabs(value):
            return None
        return os.path.normcase(_nex_alias_path(value)).casefold()

    def _nex_path_is_snapshot_alias(self, value: object) -> bool:
        key = self._nex_path_key(value)
        with self._bridge_state_lock:
            return key in self._nex_review_aliases if key is not None else False

    def _nex_snapshot_review_input(
        self, request: Mapping[str, Any], response: Mapping[str, Any]
    ) -> None:
        """Take a bounded immutable file snapshot immediately after capture."""
        state = _review_guard_snapshot(response)
        workflow_value = _request_workflow(request)
        if workflow_value is not None:
            state["workflow"] = workflow_value
        review_input = state.get("review_input")
        if not isinstance(review_input, Mapping):
            self._nex_invalidate("capture response did not include the required review_input")
            return
        snapshot: dict[str, bytes] = {}
        modes: dict[str, int] = {}
        directories: set[str] = set()
        aliases: dict[str, str] = {}

        def remember_alias(path: Path, canonical: str) -> None:
            raw = os.path.abspath(os.fspath(path))
            candidates = {raw, canonical}
            if raw.startswith("/private/"):
                candidates.add(raw[len("/private"):])
            else:
                candidates.add("/private" + raw)
            for candidate in candidates:
                key = self._nex_path_key(candidate)
                if key is not None:
                    aliases[key] = canonical

        roots: list[tuple[Path, bool, Path]] = []
        for key, is_directory in (
            ("retained_capture_root", True),
            ("retained_blueprint_path", False),
        ):
            raw = review_input.get(key)
            if not isinstance(raw, str) or not Path(raw).is_absolute():
                self._nex_invalidate("capture review_input contains an invalid path")
                return
            root = Path(raw)
            try:
                resolved = root.resolve(strict=True)
                st = root.lstat()
            except (OSError, RuntimeError, ValueError):
                self._nex_invalidate("capture review_input path is unavailable")
                return
            if stat.S_ISLNK(st.st_mode) or _nex_alias_path(root) != _nex_alias_path(resolved):
                self._nex_invalidate("capture review_input path is a symlink")
                return
            if is_directory and not resolved.is_dir():
                self._nex_invalidate("retained capture root is not a directory")
                return
            if not is_directory and not resolved.is_file():
                self._nex_invalidate("retained blueprint path is not a regular file")
                return
            logical_root = Path(_nex_alias_path(root))
            if is_directory:
                roots.append((resolved, is_directory, logical_root))
            else:
                roots.append((resolved, is_directory, logical_root))
            remember_alias(root, str(logical_root))

        capture_root = next((root for root, is_directory, _logical in roots if is_directory), None)
        authoring_root = None
        params = request.get("params")
        arguments = params.get("arguments") if isinstance(params, Mapping) else None
        if isinstance(arguments, Mapping):
            authoring_root = next(
                (arguments.get(key) for key in ("authoring_root", "root", "definition")
                 if isinstance(arguments.get(key), str)),
                None,
            )
        action = _request_action(request)
        action_params = action.get("parameters") if isinstance(action, Mapping) else None
        if authoring_root is None and isinstance(action_params, Mapping):
            authoring_root = next(
                (action_params.get(key) for key in ("authoring_root", "root", "definition")
                 if isinstance(action_params.get(key), str)),
                None,
            )
        fallback_root = review_input.get("retained_capture_root")
        logical_authoring_root = Path(os.path.normpath(os.path.abspath(
            authoring_root if isinstance(authoring_root, str)
            else str(fallback_root)
        )))
        for root, is_directory, logical_root in roots:
            if is_directory:
                directories.add(str(logical_authoring_root))
                remember_alias(root, str(logical_authoring_root))
                for current, child_dirs, filenames in os.walk(root, followlinks=False):
                    child_dirs[:] = [
                        name for name in child_dirs
                        if not _nex_snapshot_excludes(name, is_directory=True)
                        and not Path(current, name).is_symlink()
                    ]
                    current_path = Path(current)
                    relative_directory = current_path.relative_to(root)
                    logical_directory = logical_authoring_root / relative_directory
                    directories.add(str(logical_directory))
                    remember_alias(current_path, str(logical_directory))
                    for filename in sorted(filenames):
                        if _nex_snapshot_excludes(filename, is_directory=False):
                            continue
                        path = current_path / filename
                        try:
                            read = _nex_snapshot_read_file(path)
                        except _NexSnapshotBoundExceeded:
                            self._nex_invalidate("capture file exceeded the snapshot byte bound")
                            return
                        except OSError:
                            self._nex_invalidate("capture snapshot encountered an unreadable file")
                            return
                        if read is None:
                            continue
                        data, mode = read
                        if len(snapshot) >= _NEX_MAX_SNAPSHOT_FILES:
                            self._nex_invalidate("capture snapshot exceeded its file bound")
                            return
                        canonical = str(logical_authoring_root / path.relative_to(root))
                        snapshot[canonical] = bytes(data)
                        modes[canonical] = mode
                        remember_alias(path, canonical)
            else:
                try:
                    descriptor = os.open(root, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
                    try:
                        info = os.fstat(descriptor)
                        if not stat.S_ISREG(info.st_mode) or info.st_size > _NEX_MAX_SNAPSHOT_FILE_BYTES:
                            self._nex_invalidate("retained blueprint exceeds the snapshot bound")
                            return
                        data = os.read(descriptor, _NEX_MAX_SNAPSHOT_FILE_BYTES + 1)
                        if len(data) > _NEX_MAX_SNAPSHOT_FILE_BYTES:
                            self._nex_invalidate("retained blueprint exceeded the snapshot byte bound")
                            return
                        mode = stat.S_IMODE(info.st_mode)
                    finally:
                        os.close(descriptor)
                except OSError:
                    self._nex_invalidate("retained blueprint could not be snapshotted")
                    return
                try:
                    relative_blueprint = root.relative_to(capture_root) if capture_root is not None else Path(root.name)
                except ValueError:
                    relative_blueprint = Path(root.name)
                canonical = str(logical_authoring_root / relative_blueprint)
                snapshot[canonical] = bytes(data)
                modes[canonical] = mode
                remember_alias(root, canonical)
        workflow = _request_workflow(request) or ""
        generation = state.get("generation")
        envelope = {
            "jsonrpc_id": request.get("id"),
            "workflow": workflow,
            "root": str(logical_authoring_root),
            "generation": generation,
            "expected_base_url": self.nex_expected_base_url,
            "files": {
                path: {"content": data, "mode": modes.get(path, 0)}
                for path, data in snapshot.items()
            },
        }
        envelope["snapshot_sha256"] = _nex_snapshot_sha256(envelope)
        state["authoring_root"] = envelope["root"]
        with self._bridge_state_lock:
            self._review_guard_state = state
            self._nex_review_snapshot = snapshot
            self._nex_review_directories = directories
            self._nex_review_aliases = aliases
            self._nex_review_read_success = False
            self._nex_review_read_child_id = None
            self._nex_review_child_returned = False
            self._nex_active_workflow = workflow
            self._nex_workflow_roots[workflow] = str(logical_authoring_root)
            case = self._nex_case_snapshots.setdefault(workflow, {})
            if "capture" in case:
                self._nex_invalid_reason = self._nex_invalid_reason or "workflow has more than one capture snapshot"
            else:
                case.update({
                    "jsonrpc_id": envelope["jsonrpc_id"],
                    "workflow": workflow,
                    "root": envelope["root"],
                    "generation": generation,
                    "expected_base_url": self.nex_expected_base_url,
                    "files": envelope["files"],
                    "snapshot_sha256": envelope["snapshot_sha256"],
                    "capture": envelope,
                    "review_root": review_input.get("retained_capture_root"),
                })
            if self._nex_pending_static_snapshots and not self._nex_static_snapshots_attached:
                case.setdefault("static", []).extend(
                    copy.deepcopy(self._nex_pending_static_snapshots)
                )
                self._nex_static_snapshots_attached = True

    def _nex_snapshot_workspace_root(
        self, request: Mapping[str, Any], root_value: object,
        *, require_workspace: bool = True, capture_filter: bool = False,
    ) -> dict[str, Any] | None:
        """Snapshot a bounded workspace root without following any symlink.

        ``capture_filter`` applies exactly the capture snapshot's entry rules
        (shared filter, oversized files skipped rather than fatal) so the
        validation envelope is comparable file-for-file with the capture.
        """
        if not isinstance(root_value, str) or not root_value:
            return None
        root = Path(root_value)
        workspace = self.nex_workspace
        if workspace is None or not root.is_absolute():
            self._nex_invalidate("profile snapshot root is not an absolute workspace path")
            return None
        try:
            resolved_workspace = workspace.resolve(strict=True)
            resolved_root = root.resolve(strict=True)
            if _nex_alias_path(root) != _nex_alias_path(resolved_root) or (
                require_workspace and not resolved_root.is_relative_to(resolved_workspace)
            ):
                raise OSError("root is a symlink or outside workspace")
            if not resolved_root.is_dir():
                raise OSError("root is not a directory")
        except (OSError, RuntimeError, ValueError):
            self._nex_invalidate("profile snapshot root failed workspace containment checks")
            return None
        logical_root = Path(os.path.normpath(os.path.abspath(root)))
        files: dict[str, dict[str, Any]] = {}
        for current, child_dirs, filenames in os.walk(resolved_root, followlinks=False):
            child_dirs[:] = [
                name for name in child_dirs
                if not Path(current, name).is_symlink()
                and not (capture_filter and _nex_snapshot_excludes(name, is_directory=True))
            ]
            for filename in sorted(filenames):
                if capture_filter:
                    if _nex_snapshot_excludes(filename, is_directory=False):
                        continue
                elif filename == "failure.json":
                    continue
                path = Path(current) / filename
                try:
                    read = _nex_snapshot_read_file(path, skip_oversize=capture_filter)
                except _NexSnapshotBoundExceeded:
                    self._nex_invalidate("profile snapshot file exceeded the byte bound")
                    return None
                except OSError:
                    self._nex_invalidate("profile snapshot encountered an unreadable file")
                    return None
                if read is None:
                    continue
                data, mode = read
                relative = path.relative_to(resolved_root)
                files[str(logical_root / relative)] = {"content": data, "mode": mode}
                if len(files) > _NEX_MAX_SNAPSHOT_FILES:
                    self._nex_invalidate("profile snapshot exceeded its file-count bound")
                    return None
        params = request.get("params")
        arguments = params.get("arguments") if isinstance(params, Mapping) else None
        workflow = _request_workflow(request) or ""
        with self._bridge_state_lock:
            review_state = dict(self._review_guard_state or {})
        generation = review_state.get("generation")
        envelope = {
            "jsonrpc_id": request.get("id"),
            "workflow": workflow,
            "root": str(logical_root),
            "generation": generation,
            "expected_base_url": self.nex_expected_base_url,
            "files": files,
        }
        envelope["snapshot_sha256"] = _nex_snapshot_sha256(envelope)
        return envelope

    def _nex_snapshot_validation(self, request: Mapping[str, Any]) -> None:
        workflow = _request_workflow(request)
        if not workflow:
            self._nex_invalidate("validation request omitted its exact workflow")
            return
        with self._bridge_state_lock:
            case = copy.deepcopy(self._nex_case_snapshots.get(workflow))
        if not isinstance(case, dict) or "capture" not in case:
            self._nex_invalidate("validation has no preceding immutable capture snapshot")
            return
        root = case.get("review_root")
        if not isinstance(root, str) or not isinstance(case.get("root"), str):
            self._nex_invalidate("validation capture roots are unavailable")
            return
        envelope = self._nex_snapshot_workspace_root(
            request, root, require_workspace=False, capture_filter=True
        )
        if envelope is None:
            return
        source_root = Path(os.path.normpath(os.path.abspath(str(root))))
        target_root = Path(str(case.get("root")))
        rebased_files: dict[str, Any] = {}
        for path, entry in envelope.get("files", {}).items():
            try:
                relative = Path(path).relative_to(source_root)
            except (TypeError, ValueError):
                self._nex_invalidate("validation snapshot escaped the retained capture root")
                return
            rebased_files[str(target_root / relative)] = entry
        envelope["files"] = rebased_files
        envelope["root"] = case.get("root")
        envelope["generation"] = case.get("generation")
        envelope["snapshot_sha256"] = _nex_snapshot_sha256(envelope)
        with self._bridge_state_lock:
            current = self._nex_case_snapshots.get(workflow)
            if isinstance(current, dict):
                current["validation"] = envelope

    def _nex_snapshot_static_request(self, request: Mapping[str, Any]) -> None:
        params = request.get("params")
        arguments = params.get("arguments") if isinstance(params, Mapping) else None
        if not isinstance(arguments, Mapping):
            self._nex_invalidate("static profile request omitted its arguments")
            return
        root = next(
            (arguments.get(key) for key in ("authoring_root", "root", "definition")
             if isinstance(arguments.get(key), str)),
            None,
        )
        envelope = self._nex_snapshot_workspace_root(request, root)
        if envelope is None:
            return
        envelope["workflow"] = "__static__"
        envelope["snapshot_sha256"] = _nex_snapshot_sha256(envelope)
        with self._bridge_state_lock:
            self._nex_pending_static_snapshots.append(envelope)
            if not self._nex_static_snapshots_attached:
                first_capture = next(
                    (case for case in self._nex_case_snapshots.values() if "capture" in case),
                    None,
                )
                if first_capture is not None:
                    first_capture.setdefault("static", []).extend(
                        copy.deepcopy(self._nex_pending_static_snapshots)
                    )
                    self._nex_static_snapshots_attached = True

    def _nex_bind_static_generation(
        self, request: Mapping[str, Any], response: Mapping[str, Any]
    ) -> None:
        """Bind request-time static bytes when its response supplies a generation."""
        generation = _nex_result_payload(response).get("generation")
        if generation is None:
            params = request.get("params")
            arguments = params.get("arguments") if isinstance(params, Mapping) else None
            generation = arguments.get("generation") if isinstance(arguments, Mapping) else None
        if generation is None:
            return
        if not isinstance(generation, (str, int)) or isinstance(generation, bool):
            self._nex_invalidate("static profile response has an invalid generation")
            return
        request_id = _rpc_id_key(request.get("id"))
        if request_id is None:
            self._nex_invalidate("static profile response has an invalid JSON-RPC id")
            return
        with self._bridge_state_lock:
            matches = [
                entry for entry in self._nex_pending_static_snapshots
                if _rpc_id_key(entry.get("jsonrpc_id")) == request_id
            ]
            if len(matches) != 1:
                self._nex_invalid_reason = self._nex_invalid_reason or (
                    "static profile response has no unique request-time snapshot"
                )
                return
            matches[0]["generation"] = generation
            matches[0]["snapshot_sha256"] = _nex_snapshot_sha256(matches[0])
            for case in self._nex_case_snapshots.values():
                for entry in case.get("static", []):
                    if isinstance(entry, dict) and _rpc_id_key(entry.get("jsonrpc_id")) == request_id:
                        entry["generation"] = generation
                        entry["snapshot_sha256"] = _nex_snapshot_sha256(entry)

    def nex_file_snapshots(self) -> dict[str, dict[str, Any]]:
        with self._bridge_state_lock:
            return copy.deepcopy(self._nex_case_snapshots)

    def nex_frozen_exports(self) -> dict[str, dict[str, Any]]:
        """Return export archives frozen at response time, by JSON-RPC id key.

        Each entry has ``archive_path`` plus either ``content``/``sha256``/
        ``size`` or an ``error`` label; consumers must fail closed on errors.
        """
        with self._bridge_state_lock:
            return copy.deepcopy(self._nex_frozen_exports)

    def _nex_freeze_export(
        self, request: Mapping[str, Any], response: Mapping[str, Any]
    ) -> None:
        """Freeze a successful export's archive bytes before the agent sees it."""
        request_id = _rpc_id_key(request.get("id"))
        result = response.get("result")
        if request_id is None or not isinstance(result, Mapping) or result.get("isError") is True:
            return
        archive = _nex_result_payload(response).get("archive_path")
        if not isinstance(archive, str) or not archive:
            return
        entry: dict[str, Any] = {"archive_path": archive}
        path = Path(archive)
        if not path.is_absolute():
            if self.nex_workspace is None:
                path = None
            else:
                path = self.nex_workspace / path
        if path is None:
            entry["error"] = "relative archive path without a workspace"
        else:
            try:
                descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
                try:
                    info = os.fstat(descriptor)
                    if not stat.S_ISREG(info.st_mode):
                        entry["error"] = "archive is not a regular file"
                    elif info.st_size > _NEX_MAX_EXPORT_ARCHIVE_BYTES:
                        entry["error"] = "archive exceeds the freeze bound"
                    else:
                        chunks: list[bytes] = []
                        total = 0
                        while total <= _NEX_MAX_EXPORT_ARCHIVE_BYTES:
                            chunk = os.read(
                                descriptor,
                                min(1024 * 1024, _NEX_MAX_EXPORT_ARCHIVE_BYTES + 1 - total),
                            )
                            if not chunk:
                                break
                            chunks.append(chunk)
                            total += len(chunk)
                        if total > _NEX_MAX_EXPORT_ARCHIVE_BYTES:
                            entry["error"] = "archive exceeds the freeze bound"
                        else:
                            content = b"".join(chunks)
                            entry.update({
                                "content": content,
                                "sha256": hashlib.sha256(content).hexdigest(),
                                "size": len(content),
                            })
                finally:
                    os.close(descriptor)
            except OSError:
                entry["error"] = "archive could not be read"
        with self._bridge_state_lock:
            if request_id in self._nex_frozen_exports:
                self._nex_invalid_reason = self._nex_invalid_reason or (
                    "duplicate frozen export for one JSON-RPC id"
                )
                return
            self._nex_frozen_exports[request_id] = entry

    def _nex_reader_response(self, request: Mapping[str, Any]) -> dict[str, Any]:
        params = request.get("params")
        arguments = params.get("arguments") if isinstance(params, Mapping) else None
        if not isinstance(arguments, Mapping):
            return _review_reader_error("arguments must be an object")
        operation = arguments.get("operation")
        if operation not in {"read", "list"}:
            return _review_reader_error("operation must be read or list")
        max_lines = arguments.get("max_lines", _REVIEW_READER_MAX_LINES)
        max_bytes = arguments.get("max_bytes", _REVIEW_READER_MAX_BYTES)
        if (
            isinstance(max_lines, bool) or not isinstance(max_lines, int)
            or not 1 <= max_lines <= _REVIEW_READER_MAX_LINES
            or isinstance(max_bytes, bool) or not isinstance(max_bytes, int)
            or not 1 <= max_bytes <= _REVIEW_READER_MAX_BYTES
        ):
            return _review_reader_error("read bounds are outside the permitted limits")
        key = self._nex_path_key(arguments.get("path"))
        if key is None:
            return _review_reader_error("path must be an absolute captured review path")
        with self._bridge_state_lock:
            canonical = self._nex_review_aliases.get(key)
            snapshot = dict(self._nex_review_snapshot)
            directories = set(self._nex_review_directories)
        if canonical is None:
            return _review_reader_error("requested path is outside the immutable capture snapshot")
        marker = _REVIEW_READER_TRUNCATION_MARKER
        marker_bytes = len(marker.encode("utf-8"))
        try:
            if operation == "read":
                data = snapshot.get(canonical)
                if data is None:
                    return _review_reader_error("read requires a captured regular file")
                lines = data.decode("utf-8", errors="replace").splitlines(keepends=True)
                truncated = len(lines) > max_lines
                # Redact the whole selection before any byte decision so a
                # credential straddling the cutoff can never leave a prefix.
                text, leaked = self.redact_nex_text("".join(lines[:max_lines]))
                if leaked:
                    self._nex_bridge_secret_leak = True
                if truncated or len(text.encode("utf-8")) > max_bytes:
                    remaining = max_bytes - marker_bytes
                    if remaining < 0:
                        return _review_reader_error("max_bytes too small for the truncation marker")
                    text = _review_utf8_prefix(text, remaining) + marker
            else:
                if canonical not in directories:
                    return _review_reader_error("list requires a captured directory")
                prefix = canonical.rstrip(os.sep) + os.sep
                entries: dict[str, str] = {}
                for path in [*snapshot, *directories]:
                    if not path.startswith(prefix):
                        continue
                    remainder = path[len(prefix):]
                    if not remainder or os.sep in remainder:
                        continue
                    entries[remainder] = "directory" if path in directories else "file"
                selected = sorted(entries.items())
                truncated = len(selected) > max_lines
                # Redact each name, never the serialized blob, so the JSON
                # stays valid; each piece is one whole serialized entry.
                pieces: list[str] = []
                for name, kind in selected[:max_lines]:
                    safe_name, leaked = self.redact_nex_text(name)
                    if leaked:
                        self._nex_bridge_secret_leak = True
                    pieces.append(json.dumps({"name": safe_name, "kind": kind}, sort_keys=True))
                text = "[" + ", ".join(pieces) + "]"
                if truncated or len(text.encode("utf-8")) > max_bytes:
                    budget = max_bytes - marker_bytes
                    used = len(b"[]")
                    if used > budget:
                        return _review_reader_error("max_bytes too small for the truncation marker")
                    kept: list[str] = []
                    for piece in pieces:
                        cost = len(piece.encode("utf-8")) + (len(b", ") if kept else 0)
                        if used + cost > budget:
                            break
                        kept.append(piece)
                        used += cost
                    text = "[" + ", ".join(kept) + "]" + marker
            return {"isError": False, "content": [{"type": "text", "text": text}]}
        except (OSError, UnicodeError):
            return _review_reader_error("immutable review snapshot could not be served")

    def _nex_trace_record(
        self,
        direction: str,
        message: Mapping[str, Any],
        *,
        operation: str | None = None,
        workflow: str | None = None,
        root: str | None = None,
        synthetic: bool = False,
    ) -> None:
        message_copy = self._redact_nex_payload(
            message, redact_sensitive_fields=True
        )
        with self._bridge_state_lock:
            record = {
                "timestamp_monotonic_ns": self._nex_timestamp_locked(),
                "jsonrpc_id": message.get("id"),
                "direction": direction,
                "operation": operation,
                "workflow": workflow,
                "root": root,
                "synthetic": synthetic,
                "message": message_copy,
            }
            self._nex_trace.append(record)

    @classmethod
    def _replace_nex_secret(cls, value: Any, secret: str) -> Any:
        if isinstance(value, str):
            return value.replace(secret, REDACTED)
        if isinstance(value, Mapping):
            return {
                cls._replace_nex_secret(key, secret) if isinstance(key, str) else key:
                cls._replace_nex_secret(item, secret)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [cls._replace_nex_secret(item, secret) for item in value]
        return value

    @classmethod
    def _contains_nex_secret(cls, value: Any, secret: str) -> bool:
        if isinstance(value, str):
            return secret in value
        if isinstance(value, Mapping):
            return any(
                cls._contains_nex_secret(key, secret)
                or cls._contains_nex_secret(item, secret)
                for key, item in value.items()
            )
        if isinstance(value, list):
            return any(cls._contains_nex_secret(item, secret) for item in value)
        return False

    def _redact_nex_payload(
        self, value: Any, *, redact_sensitive_fields: bool = False
    ) -> Any:
        """Replace literal source credentials, preserving public profile fields."""
        if self.nex_mode and any(
            secret and self._contains_nex_secret(value, secret)
            for secret in self._nex_redaction_values
        ):
            # This can run while the bridge-state lock is held, so only set the
            # monotonic flag here. nex_evidence() turns it into a locked failure.
            self._nex_bridge_secret_leak = True
        redacted = redact_json_rpc(value) if redact_sensitive_fields else value
        for secret in sorted(self._nex_redaction_values, key=len, reverse=True):
            redacted = self._replace_nex_secret(redacted, secret)
        return redacted

    def redact_nex_text(self, value: str) -> tuple[str, bool]:
        """Redact runtime secrets from raw stream text and report literal hits."""
        text = redact_text(value)
        leaked = False
        for secret in sorted(self._nex_redaction_values, key=len, reverse=True):
            if secret and secret in value:
                leaked = True
                text = text.replace(secret, REDACTED)
        return text, leaked

    def _nex_record_response(
        self,
        request: Mapping[str, Any],
        response: Mapping[str, Any],
        *,
        synthetic: bool = False,
        workflow_override: str | None = None,
        root_override: str | None = None,
    ) -> None:
        operation = _request_operation(request)
        workflow = workflow_override or _request_workflow(request)
        if workflow is None and self.nex_mode and operation in _NEX_WORKFLOW_OPERATIONS:
            with self._bridge_state_lock:
                workflow = self._nex_active_workflow
        params = request.get("params")
        arguments = params.get("arguments") if isinstance(params, Mapping) else None
        root = None
        if isinstance(arguments, Mapping):
            for key in ("authoring_root", "definition", "root"):
                value = arguments.get(key)
                if isinstance(value, str):
                    root = value
                    break
        if root is None:
            action = _request_action(request)
            action_params = action.get("parameters") if isinstance(action, Mapping) else None
            if isinstance(action_params, Mapping):
                root = next(
                    (action_params.get(key) for key in ("authoring_root", "definition", "root")
                     if isinstance(action_params.get(key), str)),
                    None,
                )
        if root is None and self.nex_mode and operation in _NEX_WORKFLOW_OPERATIONS:
            with self._bridge_state_lock:
                root = self._nex_workflow_roots.get(workflow) if isinstance(workflow, str) else None
        if root_override is not None:
            root = root_override
        request_key = _rpc_id_key(request.get("id"))
        if request.get("method") == "tools/call" and request_key is not None:
            with self._bridge_state_lock:
                use = self._nex_pending_requests.pop(request_key, None)
                if use is None:
                    self._nex_invalid_reason = (
                        self._nex_invalid_reason or "tools/call response has no matched stream request"
                    )
                else:
                    use["response"] = True
                    use["response_success"] = not _response_is_error(response)
                    if operation == _REVIEW_READER_TOOL:
                        if not use["response_success"]:
                            self._nex_invalid_reason = self._nex_invalid_reason or (
                                "review reader MCP response was unsuccessful"
                            )
                        elif use.get("tool_result") and use.get("tool_result_success"):
                            parent_tool_use_id = use.get("parent_tool_use_id")
                            if isinstance(parent_tool_use_id, str):
                                self._nex_review_read_success = True
                                self._nex_review_read_child_id = parent_tool_use_id
                                self._nex_mark_review_child_returned_locked(parent_tool_use_id)
        if root is None:
            with self._bridge_state_lock:
                state = self._review_guard_state or {}
            review_input = state.get("review_input")
            if isinstance(review_input, Mapping):
                root = state.get("authoring_root") or review_input.get("retained_capture_root")
        self._nex_trace_record(
            "response", response, operation=operation, workflow=workflow,
            root=root if isinstance(root, str) else None, synthetic=synthetic,
        )

    def finish_nex_cell(self) -> tuple[list[dict[str, Any]], str | None]:
        """Drain and freeze runner-owned bridge evidence after Claude exits."""
        if not self.nex_mode:
            return [], None
        self.verify_nex_security_files()
        with self._bridge_state_lock:
            self._nex_capture_agent_exit_locked()
            self._nex_agent_exited = True
            self._nex_intentional_shutdown = True

        # Preserve the process-group IDs even when their leaders have exited.
        # The private MCP proxy is a Claude descendant and can outlive the CLI.
        attached = list(self._attached)
        for proc in attached:
            if not self._kill_process_group(proc):
                self._nex_invalidate("Claude process group did not empty during NEX-890 teardown")

        # Closing the listener prevents another connection. The accept thread
        # is joined first: once it has stopped, only already-registered
        # handlers can register more, so the handler set can settle. Existing
        # handlers get a bounded opportunity to drain their final response
        # before any socket is forcibly closed.
        self._bridge_stop.set()
        self._close_socket(self._bridge_listener)
        if self._bridge_thread is not None:
            self._bridge_thread.join(timeout=self.shutdown_timeout_s)
            if self._bridge_thread.is_alive():
                self._nex_invalidate("NEX-890 bridge accept thread did not stop during teardown")
        with self._bridge_state_lock:
            server_processes = set(self._server_processes)
        if self._join_bridge_handlers(time.monotonic() + self.shutdown_timeout_s):
            self._nex_invalidate("NEX-890 bridge handler did not drain after Claude exited")
            with self._bridge_state_lock:
                connections = list(self._bridge_connections)
            for connection in connections:
                self._close_socket(connection)
        with self._bridge_state_lock:
            server_processes.update(self._server_processes)
        for proc in server_processes:
            if not self._kill_process_group(proc):
                self._nex_invalidate("NEX-890 supervisor process group did not empty during teardown")
        # Sockets are closed and supervisors are gone; any handler still alive
        # could mutate diagnostics after the snapshot, so it fails closed and
        # the whole diagnostics payload is frozen here rather than read live.
        live_handlers = self._join_bridge_handlers(time.monotonic() + self.shutdown_timeout_s)
        accept_stopped = self._bridge_thread is None or not self._bridge_thread.is_alive()
        if live_handlers or not accept_stopped:
            self._nex_invalidate("NEX-890 bridge handler survived teardown")
        with self._bridge_state_lock:
            if self._nex_final_diagnostics is None:
                after_drain = self._nex_pending_snapshot_locked()
                after_drain["accept_thread_stopped"] = accept_stopped
                after_drain["live_handlers"] = live_handlers
                after_drain["quiesced"] = accept_stopped and live_handlers == 0
                self._nex_final_diagnostics = json.dumps(
                    self._nex_bridge_diagnostics_locked(after_drain), sort_keys=True
                )
        self._attached.clear()
        return self.nex_evidence()

    def _join_bridge_handlers(self, deadline: float) -> int:
        """Join registered bridge handlers until none are alive or time runs out.

        Handlers register their own forwarding threads, so the set is re-read
        after every pass. Returns the number still alive at the deadline.
        """
        while True:
            with self._bridge_state_lock:
                live = [handler for handler in self._bridge_workers if handler.is_alive()]
            if not live or time.monotonic() >= deadline:
                return len(live)
            for handler in live:
                handler.join(timeout=max(0.0, deadline - time.monotonic()))

    def nex_evidence(self) -> tuple[list[dict[str, Any]], str | None]:
        """Return a frozen copy of bridge evidence and its fail-closed status."""
        if not self.nex_mode:
            return [], None
        with self._bridge_state_lock:
            if self._nex_bridge_secret_leak:
                self._nex_invalid_reason = self._nex_invalid_reason or (
                    "NEX-890 bridge message contained the trusted source credential"
                )
            if self._nex_invalid_reason is None:
                if self._nex_connection_count != 1:
                    self._nex_invalid_reason = "NEX-890 did not use exactly one authenticated MCP connection"
                elif self._nex_active_child_id is not None:
                    self._nex_invalid_reason = "review child did not return before agent exit"
                elif self._nex_server_request_ids:
                    self._nex_invalid_reason = "Claude did not answer a server-initiated JSON-RPC request"
                elif any(not use.get("matched") or not use.get("response") or not use.get("tool_result") for use in self._nex_stream_uses):
                    self._nex_invalid_reason = "Claude stream tool_use is not fully paired with bridge request, response, and tool_result"
                elif (
                    not self.nex_preflight_mode
                    and any(use.get("name") == _REVIEW_READER_TOOL for use in self._nex_stream_uses)
                    and self._nex_child_count != 4
                ):
                    self._nex_invalid_reason = "review-child count does not match the four workflow captures"
                elif not self.nex_preflight_mode and any(
                    self._nex_children_by_workflow.get(workflow) != 1
                    or not self._nex_child_returned_by_workflow.get(workflow)
                    for workflow in _NEX_WORKFLOWS
                ):
                    self._nex_invalid_reason = "each workflow must have exactly one successful foreground review child"
            return json.loads(json.dumps(self._nex_trace)), self._nex_invalid_reason

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
            if self.nex_mode and not self._attached_event.wait(timeout=0.2):
                continue
            try:
                connection, _ = listener.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            if self._bridge_stop.is_set():
                self._close_socket(connection)
                return
            if self.nex_mode:
                with self._bridge_state_lock:
                    if self._nex_agent_exited:
                        self._nex_invalid_reason = (
                            self._nex_invalid_reason
                            or "proxy connection arrived after the Claude agent exited"
                        )
                        reject = True
                    elif self._nex_connection_claimed:
                        self._nex_invalid_reason = (
                            self._nex_invalid_reason
                            or "extra or reconnecting NEX-890 proxy connection"
                        )
                        reject = True
                    else:
                        self._nex_connection_claimed = True
                        reject = False
                if reject or not self._authenticate_nex_proxy(connection):
                    if not reject:
                        self._nex_invalidate(
                            "NEX-890 bridge peer failed kernel identity, executable, spec, or ancestry validation"
                        )
                    self._close_socket(connection)
                    continue
                self.touch_nex_activity()
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

    def _authenticate_nex_proxy(self, connection: socket.socket) -> bool:
        """Authenticate the proxy against kernel peer identity and Claude ancestry."""
        peer = _unix_peer_credentials(connection)
        if peer is None:
            return False
        peer_pid, peer_uid = peer
        if peer_uid != os.getuid() or peer_pid <= 0:
            return False
        with self._bridge_state_lock:
            attached = tuple(self._attached)
        if len(attached) != 1 or self._server_spec_path is None:
            return False
        claude_pid = attached[0].pid
        if peer_pid == claude_pid:
            return False
        expected_interpreters = _proxy_interpreter_paths()
        allowed_argv0 = tuple(os.fsencode(path) for path in expected_interpreters)
        expected_proxy = str(self.PROXY_MODULE)
        expected_spec = str(self._server_spec_path)
        identity = _proxy_peer_identity(
            peer_pid,
            allowed_argv0=allowed_argv0,
            expected_argv_tail=(expected_proxy, "--proxy", "--spec", expected_spec),
        )
        if identity is None:
            return False
        argv = identity.argv
        if (
            len(argv) != 5
            or not argv[0]
            or argv[0] not in expected_interpreters
            or not any(_same_executable(identity.executable, item) for item in expected_interpreters)
            or argv[1] != expected_proxy
            or argv[2:4] != ("--proxy", "--spec")
            or argv[4] != expected_spec
        ):
            return False

        current_pid = identity.parent_pid
        seen = {peer_pid}
        found_cli = False
        for _depth in range(64):
            if current_pid == claude_pid:
                found_cli = True
                break
            if current_pid <= 1 or current_pid in seen:
                return False
            seen.add(current_pid)
            parent_pid = _process_parent(current_pid)
            if parent_pid is None:
                return False
            current_pid = parent_pid
        if not found_cli:
            return False
        with self._bridge_state_lock:
            self._nex_connection_count += 1
            self._nex_authenticated_peer = {
                "pid": peer_pid,
                "uid": peer_uid,
                "claude_pid": claude_pid,
                "proxy_executable_candidates": expected_interpreters,
                "proxy_module": expected_proxy,
                "spec_path": expected_spec,
            }
        return True

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
                    "parameters": {"requirement_id": "review"},
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
            # Review is a tool-call boundary. Keep protocol methods available
            # so the reviewer can discover the runner-owned reader, but hold
            # every tool call once capture starts or review becomes pending.
            if request.get("method") != "tools/call":
                return False
            with self._bridge_state_lock:
                capture_in_flight = self._review_capture_in_flight
                pending = self._review_guard_state is not None
                ready = self._nex_review_child_returned
            if capture_in_flight:
                return True
            if not pending:
                return False
            operation = _request_operation(request)
            if operation in _REVIEW_PENDING_ALLOWED_OPERATIONS:
                return False
            if operation == "advance_workflow":
                action = _request_action(request)
                blocked, invalidate = _review_guard_decision(
                    action,
                    nex_mode=self.nex_mode,
                    review_child_returned=ready,
                )
                if invalidate:
                    self._nex_invalidate("review report arrived before successful child return")
                return blocked
            # While pending, only the captured-input reader, workflow
            # inspection and the review report cross the tool boundary.
            return True

        def update_review_guard(
            request: Mapping[str, Any] | None, response: Mapping[str, Any]
        ) -> None:
            if not self.workflow_action_guard or request is None:
                return
            operation = _request_operation(request)
            action = _request_action(request)
            action_type = action.get("type") if isinstance(action, Mapping) else None
            is_capture = operation == "advance_workflow" and action_type == "capture"
            if self.nex_mode and _is_nex_validation_advance(request):
                self.verify_nex_security_files()
            if _response_is_error(response):
                if is_capture:
                    with self._bridge_state_lock:
                        self._review_capture_in_flight = False
                return
            if operation == "advance_workflow" and isinstance(action, Mapping):
                if action_type == "capture":
                    if _response_requires_review(response):
                        state = _review_guard_snapshot(response)
                        workflow = _request_workflow(request)
                        if workflow is not None:
                            state["workflow"] = workflow
                        if self.nex_mode:
                            self._nex_snapshot_review_input(request, response)
                            with self._bridge_state_lock:
                                self._review_capture_in_flight = False
                            return
                        self._write_review_allowlist(state)
                        with self._bridge_state_lock:
                            self._review_guard_state = state
                            self._review_capture_in_flight = False
                    else:
                        with self._bridge_state_lock:
                            self._review_capture_in_flight = False
                elif (
                    action_type == "report_requirement"
                    and _response_satisfies_review(response)
                ):
                    with self._bridge_state_lock:
                        if self.nex_mode and not self._nex_review_child_returned:
                            self._nex_invalid_reason = (
                                self._nex_invalid_reason
                                or "review was reported before the child returned"
                            )
                            return
                        self._review_guard_state = None
                    if not self.nex_mode:
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
                        if self.nex_mode:
                            self.touch_nex_activity()
                        buffer += chunk
                        while b"\n" in buffer:
                            line, buffer = buffer.split(b"\n", 1)
                            line += b"\n"
                            request: Any = None
                            with contextlib.suppress(UnicodeDecodeError, json.JSONDecodeError):
                                request = json.loads(line.decode("utf-8"))
                            if isinstance(request, Mapping):
                                if self.nex_mode and "method" not in request:
                                    # A response to a server-initiated request
                                    # travels back on this stream. It is not a
                                    # new client request and has no server reply.
                                    response_key = _rpc_id_key(request.get("id"))
                                    server_request: Mapping[str, Any] | None = None
                                    with self._bridge_state_lock:
                                        if response_key not in self._nex_server_request_ids:
                                            self._nex_invalid_reason = (
                                                self._nex_invalid_reason
                                                or "Claude emitted an unmatched JSON-RPC response"
                                            )
                                        else:
                                            self._nex_server_request_ids.remove(response_key)
                                            server_request = self._nex_server_requests.pop(response_key, None)
                                    if server_request is None:
                                        self._nex_invalidate("Claude emitted an unmatched JSON-RPC response")
                                    else:
                                        self._nex_trace_record(
                                            "client_response", request,
                                            operation=_request_operation(server_request),
                                        )
                                    child.stdin.write(line)
                                    child.stdin.flush()
                                    continue
                                operation = _request_operation(request)
                                workflow = _request_workflow(request)
                                params = request.get("params")
                                arguments = params.get("arguments") if isinstance(params, Mapping) else None
                                root = _request_root(request)
                                matched_use: dict[str, Any] | None = None
                                trace_workflow = workflow
                                trace_root = root
                                if self.nex_mode and request.get("method") == "tools/call":
                                    matched_use, match_error = self._nex_match_tool_call(request)
                                    if match_error is not None:
                                        denied = {
                                            "jsonrpc": "2.0", "id": request.get("id"),
                                            "result": {
                                                "isError": True,
                                                "structuredContent": {"code": "runner/tool_use_mismatch"},
                                                "content": [{"type": "text", "text": "runner rejected unmatched MCP request"}],
                                            },
                                        }
                                        self._nex_trace_record(
                                            "request", request, operation=operation,
                                            workflow=workflow, root=root,
                                        )
                                        self._nex_trace_record(
                                            "response", denied, operation=operation,
                                            workflow=workflow, root=root, synthetic=True,
                                        )
                                        send_to_proxy(json.dumps(denied, separators=(",", ":")).encode() + b"\n")
                                        continue
                                    if trace_workflow is None and operation in _NEX_WORKFLOW_OPERATIONS:
                                        with self._bridge_state_lock:
                                            trace_workflow = self._nex_active_workflow
                                    if trace_root is None and operation in _NEX_WORKFLOW_OPERATIONS:
                                        with self._bridge_state_lock:
                                            trace_root = (
                                                self._nex_workflow_roots.get(trace_workflow)
                                                if isinstance(trace_workflow, str) else None
                                            )

                                if should_block(request) and operation is not None:
                                    response_line = blocked_review_response(request, operation)
                                    if self.nex_mode:
                                        self._nex_trace_record(
                                            "request", request, operation=operation,
                                            workflow=trace_workflow, root=trace_root,
                                        )
                                        response_message = json.loads(response_line.decode("utf-8"))
                                        self._nex_record_response(
                                            request, response_message, synthetic=True,
                                            workflow_override=trace_workflow,
                                            root_override=trace_root,
                                        )
                                    send_to_proxy(response_line)
                                    continue

                                if self.nex_mode and operation == "advance_workflow" and workflow is not None:
                                    with self._bridge_state_lock:
                                        self._nex_active_workflow = workflow
                                        if root is not None:
                                            self._nex_workflow_roots[workflow] = root
                                if self.nex_mode:
                                    if _is_nex_validation_advance(request):
                                        self._nex_snapshot_validation(request)
                                    elif operation in {"check_data_product", "prepare_workflow"}:
                                        candidate_root = _request_root(request)
                                        static_names = {
                                            "malformed-endpoint-profile",
                                            "omitted-endpoint-profile",
                                            "hard-coded-endpoint",
                                        }
                                        if isinstance(candidate_root, str) and Path(candidate_root).name in static_names:
                                            self._nex_snapshot_static_request(request)
                                            trace_workflow = "__static__"
                                            trace_root = candidate_root
                                request_id = _rpc_id_key(request.get("id"))
                                if request_id is not None:
                                    if request_id in request_context:
                                        if self.nex_mode:
                                            self._nex_invalidate("duplicate in-flight JSON-RPC id")
                                            continue
                                    request_context[request_id] = {
                                        **dict(request),
                                        "_nex_use": matched_use,
                                        "_nex_workflow_override": trace_workflow,
                                        "_nex_root_override": trace_root,
                                    }
                                if self.nex_mode:
                                    self._nex_trace_record(
                                        "request", request, operation=operation,
                                        workflow=trace_workflow, root=trace_root,
                                    )
                                action = _request_action(request)
                                if (
                                    self.workflow_action_guard
                                    and operation == "advance_workflow"
                                    and isinstance(action, Mapping)
                                    and action.get("type") == "capture"
                                ):
                                    with self._bridge_state_lock:
                                        self._review_capture_in_flight = True
                                if self.nex_mode and operation == _REVIEW_READER_TOOL:
                                    # Synthesized locally: no supervisor response
                                    # will ever pop this id's context.
                                    if request_id is not None:
                                        request_context.pop(request_id, None)
                                    result = self._nex_reader_response(request)
                                    response_message = {
                                        "jsonrpc": "2.0", "id": request.get("id"),
                                        "result": result,
                                    }
                                    self._nex_record_response(
                                        request, response_message, synthetic=True,
                                        workflow_override=trace_workflow,
                                        root_override=trace_root,
                                    )
                                    send_to_proxy(
                                        json.dumps(response_message, separators=(",", ":")).encode() + b"\n"
                                    )
                                    continue
                            forwarded_key = (
                                self._nex_note_forwarded(request) if self.nex_mode else None
                            )
                            try:
                                child.stdin.write(line)
                                child.stdin.flush()
                            except OSError:
                                self._nex_forget_forwarded(forwarded_key)
                                raise
                    if buffer:
                        if self.nex_mode:
                            self._nex_invalidate("unterminated bridge request line")
                        else:
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
                        if self.nex_mode:
                            self.touch_nex_activity()
                        response: Any = None
                        with contextlib.suppress(UnicodeDecodeError, json.JSONDecodeError):
                            response = json.loads(line.decode("utf-8"))
                        request = None
                        server_message = isinstance(response, Mapping) and "method" in response
                        if self.nex_mode:
                            self._nex_note_supervisor_line(response, server_message)
                        if self.nex_mode and isinstance(response, Mapping) and server_message:
                            server_id = _rpc_id_key(response.get("id"))
                            if response.get("id") is not None:
                                with self._bridge_state_lock:
                                    if server_id in self._nex_server_request_ids:
                                        self._nex_invalid_reason = (
                                            self._nex_invalid_reason
                                            or "duplicate server-initiated JSON-RPC id"
                                        )
                                    else:
                                        self._nex_server_request_ids.add(server_id)
                                        self._nex_server_requests[server_id] = copy.deepcopy(response)
                                self._nex_trace_record(
                                    "server_request", response,
                                    operation=_request_operation(response),
                                )
                            else:
                                self._nex_trace_record(
                                    "notification", response,
                                    operation=_request_operation(response),
                                )
                        elif isinstance(response, Mapping) and "id" in response:
                            request_id = _rpc_id_key(response.get("id"))
                            if request_id is not None:
                                request = request_context.pop(request_id, None)
                        if self.nex_mode and isinstance(response, Mapping):
                            if server_message:
                                # Server notifications and requests are valid
                                # protocol messages, not unmatched responses.
                                pass
                            elif request is None:
                                self._nex_invalidate("bridge response has no matched request")
                            else:
                                original = {key: value for key, value in request.items() if not key.startswith("_")}
                                workflow_override = request.get("_nex_workflow_override")
                                root_override = request.get("_nex_root_override")
                                operation = _request_operation(original)
                                if original.get("method") == "tools/list":
                                    augmented = _augment_tools_list(
                                        response, allowlist_path=self.review_allowlist_path
                                    )
                                    if augmented != response:
                                        response = augmented
                                        line = json.dumps(
                                            response, separators=(",", ":")
                                        ).encode() + b"\n"
                                update_review_guard(original, response)
                                if operation == "export_data_product":
                                    self._nex_freeze_export(original, response)
                                if workflow_override == "__static__":
                                    self._nex_bind_static_generation(original, response)
                                self._nex_record_response(
                                    original, response,
                                    workflow_override=(workflow_override if isinstance(workflow_override, str) else None),
                                    root_override=(root_override if isinstance(root_override, str) else None),
                                )
                        if isinstance(response, Mapping):
                            if not self.nex_mode:
                                update_review_guard(request, response)
                        elif self.nex_mode:
                            self._nex_invalidate("non-JSON response crossed the bridge")
                        if self.nex_mode:
                            if isinstance(response, Mapping):
                                safe_response = self._redact_nex_payload(response)
                                line = (
                                    json.dumps(safe_response, separators=(",", ":")).encode()
                                    + b"\n"
                                )
                            else:
                                safe_text, leaked = self.redact_nex_text(
                                    line.decode("utf-8", errors="replace")
                                )
                                if leaked:
                                    self._nex_bridge_secret_leak = True
                                line = safe_text.encode("utf-8")
                        send_to_proxy(line)
                    if self.nex_mode:
                        with self._bridge_state_lock:
                            self._nex_supervisor_stdout_eof = True
                            self._nex_supervisor_shutdown_requested_at_eof = (
                                self._nex_intentional_shutdown or self._bridge_stop.is_set()
                            )
                except (BrokenPipeError, OSError):
                    pass

            def drain_stderr() -> None:
                for _line in child.stderr:
                    pass

            def start_handler(target: Callable[[], None]) -> threading.Thread:
                # Forwarders mutate evidence and diagnostics, and from_server
                # can outlive this worker's bounded join. Register them so NEX
                # teardown joins them before freezing the after-drain snapshot.
                def run() -> None:
                    try:
                        target()
                    finally:
                        with self._bridge_state_lock:
                            self._bridge_workers.discard(threading.current_thread())

                handler = threading.Thread(target=run, daemon=True)
                with self._bridge_state_lock:
                    self._bridge_workers.add(handler)
                handler.start()
                return handler

            to_server = start_handler(forward_to_server)
            from_server = start_handler(forward_from_server)
            stderr_reader = threading.Thread(target=drain_stderr, daemon=True)
            stderr_reader.start()
            to_server.join()
            from_server.join(timeout=self.shutdown_timeout_s)
            if self.nex_mode:
                with self._bridge_state_lock:
                    intentional = self._nex_intentional_shutdown or self._bridge_stop.is_set()
                if intentional:
                    self._kill_process_group(child)
                elif child.poll() is None:
                    try:
                        child.wait(timeout=self.shutdown_timeout_s)
                    except subprocess.TimeoutExpired:
                        self._kill_process_group(child)
                else:
                    child.wait()
            elif child.poll() is None:
                try:
                    child.wait(timeout=self.shutdown_timeout_s)
                except subprocess.TimeoutExpired:
                    self._kill_process(child)
            else:
                child.wait()
            code = child.returncode
            with self._bridge_state_lock:
                intentional = self.nex_mode and (
                    self._nex_intentional_shutdown or self._bridge_stop.is_set()
                )
                if self.nex_mode:
                    self._nex_supervisor_exit_code = code if isinstance(code, int) else None
                    self._nex_supervisor_shutdown_requested_at_exit = intentional
            _write_private_text(
                self.server_process_result_path,
                json.dumps(
                    {
                        "status": "passed" if code == 0 or intentional else "failed",
                        "exit_code": code,
                        "pid": child.pid,
                        "intentional_shutdown": intentional,
                    },
                    sort_keys=True,
                ),
            )
            # Publish the server outcome before releasing the bridge reader;
            # the proxy uses that file to report a complete result.
            with contextlib.suppress(OSError):
                connection.shutdown(socket.SHUT_WR)
        except (OSError, ValueError) as exc:
            with self._bridge_state_lock:
                intentional = self.nex_mode and (
                    self._nex_intentional_shutdown or self._bridge_stop.is_set()
                )
            _write_private_text(
                self.server_process_result_path,
                json.dumps({
                    "status": "passed" if intentional else "failed",
                    "error": None if intentional else redact_text(str(exc)),
                    "intentional_shutdown": intentional,
                }, sort_keys=True),
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
        metrics = {
            "setup_result": self.setup_result.as_dict(),
            "agent_result": self.agent_result.as_dict(),
            "server_result": self.server_result.as_dict(),
            "nex_bridge_secret_leak": self._nex_bridge_secret_leak,
            "mcp_config": str(self.config_path) if self._started else None,
            "mcp_trace": str(self.trace_path) if self._started else None,
        }
        if self.nex_mode:
            metrics["nex_review_children"] = {
                workflow: {
                    "count": self._nex_children_by_workflow.get(workflow, 0),
                    "returned": self._nex_child_returned_by_workflow.get(workflow, False),
                }
                for workflow in _NEX_WORKFLOWS
            }
            metrics["nex_bridge_diagnostics"] = self._nex_bridge_diagnostics()
        return metrics

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

    @staticmethod
    def _process_group_alive(pgid: int) -> bool:
        try:
            os.killpg(pgid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True

    @classmethod
    def _kill_process_group(cls, proc: subprocess.Popen[Any]) -> bool:
        """Signal a run-owned group before reaping its leader, then bound cleanup."""
        pgid = proc.pid
        try:
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except OSError:
            with contextlib.suppress(OSError):
                proc.terminate()
        deadline = time.monotonic() + 5.0
        try:
            proc.wait(timeout=max(0.0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            pass
        while cls._process_group_alive(pgid) and time.monotonic() < deadline:
            time.sleep(0.05)
        if cls._process_group_alive(pgid):
            with contextlib.suppress(OSError):
                os.killpg(pgid, signal.SIGKILL)
            with contextlib.suppress(subprocess.TimeoutExpired):
                proc.wait(timeout=1.0)
        final_deadline = time.monotonic() + 2.0
        while cls._process_group_alive(pgid) and time.monotonic() < final_deadline:
            time.sleep(0.05)
        with contextlib.suppress(subprocess.TimeoutExpired):
            proc.wait(timeout=0.1)
        return not cls._process_group_alive(pgid)

    def cleanup(self) -> None:
        if self._closed:
            return
        if self.nex_mode:
            with self._bridge_state_lock:
                self._nex_intentional_shutdown = True
        for proc in self._attached:
            if self.nex_mode:
                self._kill_process_group(proc)
            else:
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
            if self.nex_mode:
                self._kill_process_group(proc)
            else:
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


def _trace_line(path: Path | None, direction: str, line: bytes, **metadata: Any) -> None:
    """Persist only parsed, recursively-redacted JSON-RPC messages."""
    if path is None:
        return
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
        trace_path = Path(spec["trace_path"]) if spec.get("trace_path") else None
        nex_mode = spec.get("nex_mode") is True
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
                if response_operation != _REVIEW_READER_TOOL:
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
                    not nex_mode
                    and
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
                if is_review_reader_call and not nex_mode:
                    write_review_reader_response(request)
                    continue
            if not is_review_reader_call:
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
