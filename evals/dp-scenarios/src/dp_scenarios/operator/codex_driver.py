"""Codex CLI provider for the free-authoring operator driver.

Each authored turn runs as a short, isolated ``codex exec`` invocation. The
process starts in a newly-created empty directory, receives only the prompt on
stdin, and runs with read-only sandboxing and user configuration/rules disabled.
Codex authentication remains owned by the user's Codex CLI installation; this
module never reads or copies its credential files.

Codex CLI has no universal no-tools switch. The provider disables the known
tool-bearing features exposed by the installed CLI and retains read-only
sandboxing as an additional boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
from typing import TYPE_CHECKING

from .openai_driver import (
    DriverConfigError,
    DriverProviderError,
    build_messages,
    driver_prompt_hash,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .driver import DriverView


_ALLOWED_EFFORTS = frozenset({"minimal", "low", "medium", "high", "xhigh", "max"})
_DISABLED_FEATURES = (
    "hooks",
    "plugins",
    "apps",
    "browser_use",
    "in_app_browser",
    "computer_use",
    "image_generation",
    "view_image",
    "skill_search",
    "remote_plugin",
    "shell_tool",
    "unified_exec",
    "shell_snapshot",
    "code_mode_host",
    "web_search_request",
    "multi_agent",
)
_ERROR_LIMIT = 500
_TERMINATE_GRACE_SECONDS = 0.5


def _prompt(view: "DriverView") -> str:
    """Encode the shared prompt messages as one Codex CLI instruction."""

    messages = json.dumps(build_messages(view), ensure_ascii=False, sort_keys=True)
    return (
        "Use the following two-message conversation as your complete instructions. "
        "Do not use tools or inspect files. Follow its system message, answer its "
        "user message, and return only the operator's message with no explanation.\n\n"
        f"{messages}"
    )


def _minimal_environment() -> dict[str, str]:
    """Return only the environment needed to locate Codex and its auth home."""

    environment: dict[str, str] = {"PATH": os.environ.get("PATH", os.defpath)}
    for key in ("HOME", "CODEX_HOME", "LANG", "LC_ALL"):
        value = os.environ.get(key)
        if isinstance(value, str) and value:
            environment[key] = value
    return environment


def _signal_process_group(process: subprocess.Popen[str], sig: signal.Signals) -> None:
    """Signal the dedicated group created for one Codex invocation."""

    try:
        os.killpg(process.pid, sig)
    except ProcessLookupError:
        pass
    except OSError:
        # The caller still attempts to reap the direct child below.
        pass


def _terminate_process_group(process: subprocess.Popen[str]) -> None:
    """Stop the Codex process and any descendants it started."""

    _signal_process_group(process, signal.SIGTERM)
    try:
        process.wait(timeout=_TERMINATE_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        pass

    # Send SIGKILL even if the direct child exited promptly: a descendant may
    # have closed the inherited pipes and otherwise outlived its parent.
    _signal_process_group(process, signal.SIGKILL)
    try:
        process.communicate(timeout=2.0)
    except subprocess.TimeoutExpired:
        # A failed group signal must not leave the direct child behind.
        process.kill()
        process.communicate()


def _bounded_error(text: str) -> str:
    """Normalise and bound a diagnostic before it can reach a caller."""

    # Provider stderr is intentionally not incorporated into surfaced errors:
    # the CLI may include request context or credential diagnostics that cannot
    # be reliably scrubbed. Only locally-created, bounded diagnostics reach a
    # caller.
    return " ".join(text.split())[:_ERROR_LIMIT]


@dataclass(frozen=True, slots=True, repr=False)
class CodexDriverProvider:
    """Author one operator turn by invoking the installed Codex CLI.

    The executable is resolved at construction time, so a missing CLI is
    reported before a scenario starts and before any provider call can spend
    tokens. The provider is synchronous to match ``DriverProvider``.
    """

    model: str
    effort: str = "medium"
    timeout_seconds: float = 300.0
    executable: str | None = None
    _resolved_executable: str = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.model, str) or not self.model.strip():
            raise DriverConfigError("driver model must be a non-empty string")
        if not isinstance(self.effort, str) or self.effort not in _ALLOWED_EFFORTS:
            raise DriverConfigError("driver effort must be minimal, low, medium, high, xhigh, or max")
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, (int, float))
            or not math.isfinite(self.timeout_seconds)
            or self.timeout_seconds <= 0
        ):
            raise DriverConfigError("driver timeout_seconds must be positive")
        candidate = self.executable if self.executable is not None else "codex"
        if not isinstance(candidate, str) or not candidate.strip():
            raise DriverConfigError("Codex CLI executable must be a non-empty string")
        resolved = shutil.which(candidate)
        if resolved is None:
            raise DriverConfigError("Codex CLI executable was not found")
        # The child runs from a fresh directory, so preserve the executable's
        # location even when a caller supplied a relative path.
        object.__setattr__(self, "_resolved_executable", str(Path(resolved).resolve()))

    def __repr__(self) -> str:
        return (
            f"CodexDriverProvider(model={self.model!r}, effort={self.effort!r}, "
            f"timeout_seconds={self.timeout_seconds!r}, executable=<resolved>)"
        )

    __str__ = __repr__

    def __call__(self, view: "DriverView") -> str:
        """Ask Codex to author a message and return only its final response."""

        with tempfile.TemporaryDirectory(prefix="dp-scenario-codex-driver-") as temp_dir:
            working_directory = Path(temp_dir)
            response_path = working_directory / "last-message.txt"
            command = [
                self._resolved_executable,
                "exec",
                "--ignore-user-config",
                "--ignore-rules",
                "--ephemeral",
                "--skip-git-repo-check",
                *(argument for feature in _DISABLED_FEATURES for argument in ("--disable", feature)),
                "--sandbox",
                "read-only",
                "--model",
                self.model,
                "--config",
                f'model_reasoning_effort="{self.effort}"',
                "--cd",
                str(working_directory),
                "--output-last-message",
                str(response_path),
                "-",
            ]
            try:
                process = subprocess.Popen(
                    command,
                    cwd=working_directory,
                    env=_minimal_environment(),
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    start_new_session=True,
                )
            except Exception as exc:
                raise DriverProviderError(
                    _bounded_error(f"Codex CLI could not be started ({type(exc).__name__})")
                ) from None

            try:
                process.communicate(input=_prompt(view), timeout=self.timeout_seconds)
            except subprocess.TimeoutExpired:
                _terminate_process_group(process)
                raise DriverProviderError(
                    _bounded_error(f"Codex CLI timed out after {self.timeout_seconds:g} seconds")
                ) from None
            except Exception as exc:
                _terminate_process_group(process)
                raise DriverProviderError(
                    _bounded_error(f"Codex CLI invocation failed ({type(exc).__name__})")
                ) from None

            if process.returncode != 0:
                raise DriverProviderError(
                    _bounded_error(f"Codex CLI exited with status {process.returncode}")
                ) from None
            try:
                response = response_path.read_text(encoding="utf-8").strip()
            except (OSError, UnicodeError):
                response = ""
            if not response:
                raise DriverProviderError("Codex CLI returned no message") from None
            return response


__all__ = [
    "CodexDriverProvider",
    "DriverConfigError",
    "DriverProviderError",
    "build_messages",
    "driver_prompt_hash",
]
