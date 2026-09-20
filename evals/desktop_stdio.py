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
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            fd = -1
            handle.write(text)
    finally:
        if fd != -1:
            os.close(fd)


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
                try:
                    while True:
                        chunk = connection.recv(65536)
                        if not chunk:
                            break
                        child.stdin.write(chunk)
                        child.stdin.flush()
                except (BrokenPipeError, OSError):
                    pass
                finally:
                    with contextlib.suppress(OSError):
                        child.stdin.close()

            def forward_from_server() -> None:
                try:
                    for line in child.stdout:
                        connection.sendall(line)
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
                if not write_client(line):
                    return

        reader = threading.Thread(target=forward_responses, daemon=True)
        reader.start()
        assert bridge_writer is not None
        for line in sys.stdin.buffer:
            _trace_line(trace_path, "request", line)
            request: Any = None
            try:
                request = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                pass
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
