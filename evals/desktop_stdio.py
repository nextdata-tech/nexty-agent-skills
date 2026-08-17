#!/usr/bin/env python3
"""Runner-owned stdio MCP plumbing for terminal Desktop evals.

The scenario runner must not inherit Claude Desktop's global MCP registry. A
DesktopStdioSession writes a private, strict MCP config and points it at this
module's small proxy. The proxy starts exactly one server child, forwards
newline-delimited JSON-RPC, and records a redacted trace. It is intentionally
stdlib-only so setup is usable before the Desktop Python environment is ready.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import datetime as _dt
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any, Mapping, Sequence


REDACTED = "<redacted>"
_SECRET_KEY = re.compile(
    r"(?:password|passwd|secret|token|api[_-]?key|access[_-]?key|"
    r"authorization|cookie|credential|bearer|private[_-]?key|grant)",
    re.IGNORECASE,
)
_BEARER = re.compile(r"(?i)(\bbearer\s+)[A-Za-z0-9._~+/=-]+")
_URL_AUTH = re.compile(r"(https?://)([^/@\s:]+):([^/@\s]+)@")
_QUERY_SECRET = re.compile(
    r"(?i)([?&](?:token|api[_-]?key|secret|password|authorization)=)[^&#\s]+"
)
_ASSIGN_SECRET = re.compile(
    r"(?i)(\b(?:token|api[_-]?key|secret|password|authorization)"
    r"\s*[:=]\s*)[^\s,;]+"
)
PROXY_MODULE = Path(__file__).resolve()


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


class DesktopStdioSession:
    """Own one isolated Desktop MCP config, proxy, trace, and cleanup scope.

    The server is started by the private proxy command referenced by Claude's
    config. This keeps all server descendants in the eval process lineage while
    allowing the runner to retain a JSON-RPC trace.
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
        self.server_env = {str(k): str(v) for k, v in (server_env or {}).items()}
        self.server_name = server_name
        self.allowed_tools = tuple(allowed_tools or ("mcp__nxd-desktop__*",))
        self.startup_timeout_s = startup_timeout_s
        self.shutdown_timeout_s = shutdown_timeout_s
        self._provided_root = Path(root) if root is not None else None
        self._temp: tempfile.TemporaryDirectory[str] | None = None
        self._root: Path | None = None
        self._attached: list[subprocess.Popen[Any]] = []
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
                self._root.mkdir(parents=True, exist_ok=True)
            spec = {
                "command": list(self.server_command),
                "env": self.server_env,
                "trace_path": str(self.trace_path),
                "result_path": str(self.server_result_path),
                "shutdown_timeout_s": self.shutdown_timeout_s,
            }
            spec_path = self.root / "server-spec.json"
            spec_path.write_text(json.dumps(spec, sort_keys=True), encoding="utf-8")
            with contextlib.suppress(OSError):
                spec_path.chmod(0o600)
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
            self.config_path.write_text(
                json.dumps(config, indent=2, sort_keys=True), encoding="utf-8"
            )
            with contextlib.suppress(OSError):
                self.config_path.chmod(0o600)
            self.trace_path.write_text("", encoding="utf-8")
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
        if self._root is not None:
            try:
                result = json.loads(
                    self.server_result_path.read_text(encoding="utf-8")
                )
                pid = int(result.get("proxy_pid", 0))
                if pid > 0 and pid != os.getpid():
                    with contextlib.suppress(OSError):
                        os.killpg(pid, signal.SIGTERM)
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                pass
        if self._temp is not None:
            self._temp.cleanup()
            self._temp = None
        elif self._provided_root is not None:
            for name in (
                "mcp-config.json",
                "server-spec.json",
                "mcp-trace.jsonl",
                "server-result.json",
            ):
                with contextlib.suppress(OSError):
                    (self.root / name).unlink()
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
        path.write_text(
            json.dumps(redact_json_rpc(payload), sort_keys=True),
            encoding="utf-8",
        )


def _trace_line(path: Path, direction: str, line: bytes) -> None:
    """Persist only parsed, recursively-redacted JSON-RPC messages."""
    try:
        value = json.loads(line.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        value = {"parse_error": True}
    record = {
        "timestamp": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "direction": direction,
        "message": redact_json_rpc(value),
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n"
        )


def run_stdio_proxy(spec_path: Path) -> int:
    """Run the forwarding proxy used by Claude's private MCP config."""
    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        command = [str(x) for x in spec["command"]]
        trace_path = Path(spec["trace_path"])
        result_path = Path(spec["result_path"])
        env = dict(os.environ)
        env.update({str(k): str(v) for k, v in (spec.get("env") or {}).items()})
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return 2
    child: subprocess.Popen[bytes] | None = None
    child_error: list[str] = []
    try:
        # Claude may launch this command without creating a process group for
        # its MCP children. Give the proxy its own group so the runner can
        # terminate it by the PID recorded in server-result.json.
        with contextlib.suppress(OSError):
            os.setsid()
        child = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            start_new_session=True,
        )
        _write_proxy_result(
            result_path, status="started", proxy_pid=os.getpid(), child_pid=child.pid
        )

        def forward_responses() -> None:
            assert child is not None and child.stdout is not None
            for line in child.stdout:
                _trace_line(trace_path, "response", line)
                try:
                    sys.stdout.buffer.write(line)
                    sys.stdout.buffer.flush()
                except (BrokenPipeError, OSError):
                    return

        def drain_stderr() -> None:
            assert child is not None and child.stderr is not None
            for _line in child.stderr:
                # Never leave the child's stderr pipe unread: a noisy server
                # must not wedge the JSON-RPC channel. Server diagnostics are
                # intentionally not copied into the public trace.
                pass

        reader = threading.Thread(target=forward_responses, daemon=True)
        stderr_reader = threading.Thread(target=drain_stderr, daemon=True)
        reader.start()
        stderr_reader.start()
        assert child.stdin is not None
        for line in sys.stdin.buffer:
            _trace_line(trace_path, "request", line)
            try:
                child.stdin.write(line)
                child.stdin.flush()
            except (BrokenPipeError, OSError):
                child_error.append("server closed stdin")
                break
        with contextlib.suppress(OSError):
            child.stdin.close()
        try:
            code = child.wait(timeout=float(spec.get("shutdown_timeout_s", 5)))
        except subprocess.TimeoutExpired:
            with contextlib.suppress(OSError):
                os.killpg(child.pid, signal.SIGTERM)
            with contextlib.suppress(subprocess.TimeoutExpired):
                child.wait(timeout=5)
            code = child.returncode
        reader.join(timeout=5)
        stderr_reader.join(timeout=5)
        if child_error:
            status, error = "failed", child_error[0]
        elif code == 0:
            status, error = "passed", None
        else:
            status, error = "failed", f"server exited {code}"
        _write_proxy_result(
            result_path,
            status=status,
            error=error,
            exit_code=code,
            proxy_pid=os.getpid(),
        )
        return 0 if status == "passed" else 1
    except (OSError, ValueError) as exc:
        _write_proxy_result(
            result_path, status="failed", error=str(exc), proxy_pid=os.getpid()
        )
        if child is not None:
            DesktopStdioSession._kill_process(child)
        return 1


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
