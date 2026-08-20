"""Adapter between the scenario turn protocol and the shared desktop substrate.

``DesktopStdioSession`` owns the isolated MCP environment and its process
lineage.  This module only binds that environment to the command-driven
``LiveSession``; it deliberately does not implement another proxy, redactor,
or cleanup routine.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
from collections.abc import Callable, Mapping, Sequence
from typing import Any
from urllib.parse import urlsplit, urlunsplit


class DesktopTransportError(RuntimeError):
    """Raised when a live desktop transport cannot be materialized."""


# The substrate is a repo-level eval module rather than an installed package.
# Keep the import seam here, next to its sole consumer, so replay imports do
# not need to load it and no copy of the substrate can drift into this package.
_EVALS_ROOT = Path(__file__).resolve().parents[4]
if str(_EVALS_ROOT) not in sys.path:
    sys.path.append(str(_EVALS_ROOT))

try:
    from desktop_stdio import (  # noqa: E402
        DesktopStdioSession,
        StdioOutcome,
    )
except ImportError as exc:  # pragma: no cover - exercised in installed-layout smoke tests
    expected = _EVALS_ROOT / "desktop_stdio.py"
    raise DesktopTransportError(
        "could not import the shared desktop stdio substrate; "
        f"resolved evals root is {_EVALS_ROOT}, expected {expected}: {exc}"
    ) from exc


CommandBuilder = Callable[[Path, bool, str], Sequence[str]]


def _resolved_supervisor_identity(command: Sequence[str]) -> str:
    """Identify the supervisor script/binary and pin its content when possible."""

    for index, argument in enumerate(command[:-1]):
        if argument == "-m":
            module_name = str(command[index + 1])
            try:
                module_spec = importlib.util.find_spec(module_name)
            except (ImportError, ModuleNotFoundError, ValueError):
                module_spec = None
            origin = module_spec.origin if module_spec is not None else None
            if origin and origin not in {"built-in", "frozen"}:
                target = Path(origin).resolve()
                identity = f"module:{module_name}:{target}"
                if target.is_file():
                    identity += f"#sha256:{hashlib.sha256(target.read_bytes()).hexdigest()}"
                return identity
            return f"module:{module_name}"

    target: Path | None = None
    candidates = command if command else ()
    config_suffixes = {".json", ".ini", ".toml", ".yaml", ".yml", ".conf", ".cfg"}

    def candidate_path(argument: str) -> Path | None:
        if argument.startswith("-"):
            return None
        candidate = Path(argument).expanduser()
        return candidate if candidate.is_file() else None

    # Prefer a real supervisor-looking script/binary.  In particular, do not
    # mistake a value following ``--config`` for the executable merely because
    # that configuration file happens to exist.
    for argument in candidates:
        candidate = candidate_path(str(argument))
        if candidate is None or candidate.suffix.lower() in config_suffixes:
            continue
        stem = candidate.stem.lower()
        if "supervisor" in stem or "server" in stem or candidate.suffix.lower() in {".py", ".exe"}:
            target = candidate
            break

    if target is None:
        for argument in candidates:
            candidate = candidate_path(str(argument))
            if candidate is not None and candidate.suffix.lower() not in config_suffixes:
                target = candidate
                break
    if target is None:
        executable = shutil.which(command[0])
        target = Path(executable or command[0]).expanduser()
    resolved = target.resolve()
    identity = str(resolved)
    if resolved.is_file():
        digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
        identity += f"#sha256:{digest}"
    return identity


def _session_config_digest(session: DesktopStdioSession) -> str:
    """Hash semantic session inputs while excluding run-local artifact paths."""

    run_parent = session.root.parent.resolve()
    ephemeral_url_environment_keys = frozenset({"NXD_EVAL_SOURCE_URL"})

    def canonical_environment_value(key: str, value: str) -> str:
        path = Path(value).expanduser()
        if path.is_absolute():
            try:
                relative = path.resolve().relative_to(run_parent)
            except ValueError:
                pass
            else:
                return f"<run-parent>/{relative.as_posix()}"

        # The mock source binds an ephemeral data port for every live run.  Its
        # URL is still a semantic input: scheme, host, path, query, and
        # fragment identify the source shape, while the selected port does not.
        if key in ephemeral_url_environment_keys:
            try:
                parsed = urlsplit(value)
                port = parsed.port
            except ValueError:
                return value
            if parsed.scheme and parsed.netloc and port is not None and parsed.hostname:
                host = parsed.hostname
                if ":" in host:
                    host = f"[{host}]"
                userinfo = ""
                if parsed.username is not None:
                    userinfo = parsed.username
                    if parsed.password is not None:
                        userinfo += f":{parsed.password}"
                    userinfo += "@"
                return urlunsplit(
                    (
                        parsed.scheme,
                        f"{userinfo}{host}:<ephemeral-port>",
                        parsed.path,
                        parsed.query,
                        parsed.fragment,
                    )
                )
        return value

    semantic_config = {
        "server_command": list(session.server_command),
        "server_environment": {
            key: canonical_environment_value(key, value)
            for key, value in sorted(session.server_env.items())
        },
        "shutdown_timeout_s": session.shutdown_timeout_s,
        "startup_timeout_s": session.startup_timeout_s,
        "allowed_tools": list(session.allowed_tools),
        "strict_mcp_config": session.strict_mcp_config,
        "server_name": session.server_name,
    }
    encoded = json.dumps(
        semantic_config,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


class DesktopStdioTransport:
    """Bind a turn-process command to one shared ``DesktopStdioSession``.

    The ``command``/``environment``/``cwd`` properties are the exact inputs
    consumed by :class:`~dp_scenarios.runner.session.LiveSession`.  The
    ``session`` remains the owner of the isolated root, MCP config, trace,
    server result, and child-process cleanup.
    """

    def __init__(
        self,
        session: DesktopStdioSession,
        *,
        command_builder: CommandBuilder,
        environment: Mapping[str, str],
        cwd: str | Path,
    ) -> None:
        if not isinstance(session, DesktopStdioSession):
            raise TypeError("desktop transport requires a DesktopStdioSession")
        if not callable(command_builder):
            raise TypeError("desktop transport requires a command builder")
        self.session = session
        self.command_builder = command_builder
        self.command: tuple[str, ...] | None = None
        self.environment = {str(key): str(value) for key, value in environment.items()}
        self.cwd = Path(cwd)

    @classmethod
    def create(
        cls,
        command_builder: CommandBuilder,
        *,
        environment: Mapping[str, str],
        cwd: str | Path,
        server_command: str | os.PathLike[str] | Sequence[str],
        server_args: Sequence[str] = (),
        server_environment: Mapping[str, str] | None = None,
        root: str | Path,
        server_name: str = DesktopStdioSession.SERVER_NAME,
        allowed_tools: Sequence[str] | None = None,
        startup_timeout_s: float = 15.0,
        shutdown_timeout_s: float = 5.0,
    ) -> "DesktopStdioTransport":
        """Create an adapter without reimplementing session setup."""

        session = DesktopStdioSession(
            server_command,
            server_args,
            server_env=server_environment,
            root=Path(root),
            server_name=server_name,
            allowed_tools=allowed_tools,
            startup_timeout_s=startup_timeout_s,
            shutdown_timeout_s=shutdown_timeout_s,
        )
        return cls(session, command_builder=command_builder, environment=environment, cwd=cwd)

    @property
    def root(self) -> Path:
        return self.session.root

    @property
    def config_path(self) -> Path:
        return self.session.config_path

    @property
    def trace_path(self) -> Path:
        return self.session.trace_path

    @property
    def server_result_path(self) -> Path:
        return self.session.server_result_path

    @property
    def setup_result(self) -> StdioOutcome:
        return self.session.setup_result

    @property
    def agent_result(self) -> StdioOutcome:
        return self.session.agent_result

    @property
    def server_result(self) -> StdioOutcome:
        return self.session.server_result

    @property
    def supervisor_binary_path(self) -> str:
        return _resolved_supervisor_identity(self.session.server_command)

    @property
    def session_config_sha256(self) -> str:
        self.start()
        return _session_config_digest(self.session)

    @property
    def artifact_paths(self) -> Mapping[str, str]:
        """Return paths only; trace bytes never become manifest evidence."""

        self.start()
        return {
            "config": str(self.config_path),
            "trace": str(self.trace_path),
            "server_result": str(self.server_result_path),
        }

    def manifest_fields(self) -> dict[str, str]:
        """Return the desktop identity fields added to a live manifest."""

        self.start()
        return {
            "supervisor_binary_path": self.supervisor_binary_path,
            "session_root": str(self.root),
            "session_config_path": str(self.config_path),
            "session_config_sha256": self.session_config_sha256,
            "session_trace_path": str(self.trace_path),
            "session_server_result_path": str(self.server_result_path),
        }

    def start(self) -> "DesktopStdioTransport":
        self.session.ensure_started()
        if self.command is None:
            try:
                command = tuple(
                    str(argument)
                    for argument in self.command_builder(
                        self.session.config_path,
                        self.session.strict_mcp_config,
                        self.session.allowed_tools_csv,
                    )
                )
            except Exception as exc:
                self.session.cleanup()
                raise DesktopTransportError(f"desktop command builder failed: {exc}") from exc
            if not command or not command[0]:
                self.session.cleanup()
                raise DesktopTransportError("desktop command builder returned an empty argv")
            self.command = command
        return self

    ensure_started = start

    def live_session(self, *, timeout: float = 300.0) -> Any:
        """Return a turn-protocol session owned by this desktop transport."""

        from .session import LiveSession

        self.start()
        assert self.command is not None
        return LiveSession(
            self.command,
            environment=self.environment,
            cwd=self.cwd,
            timeout=timeout,
            desktop_session=self.session,
        )

    build_live_session = live_session

    def attach_process(self, process: Any) -> None:
        self.session.attach_process(process)

    def record_agent(self, *, status: str, error: str | None = None) -> None:
        self.session.record_agent(status=status, error=error)

    def result_metrics(self) -> dict[str, Any]:
        """Expose supervisor-owned outcomes without inspecting agent prose."""

        return self.session.result_metrics()

    def cleanup(self) -> None:
        self.session.cleanup()

    close = cleanup

    def __enter__(self) -> "DesktopStdioTransport":
        return self.start()

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.cleanup()


__all__ = [
    "DesktopStdioTransport",
    "DesktopTransportError",
    "CommandBuilder",
    "StdioOutcome",
]
