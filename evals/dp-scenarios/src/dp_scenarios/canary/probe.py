"""Invoke the supervisor preflight and one publish build.

The invariant is that a missing or non-executable supervisor is an explicit
probe failure, never an inferred skip.  Report interpretation remains code-
based: this module only preserves the supervisor's machine-readable document
and validates its status vocabulary.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any, Mapping, Sequence


ALLOWED_STATUSES = frozenset({"pass", "warn", "fail", "skip"})
SUPERVISOR_ENV = "NXD_DESKTOP_SUPERVISOR"
PYTHON_ENV = "NXD_DESKTOP_PYTHON"
SESSION_ENVIRONMENT_ALLOWLIST = frozenset(
    {
        "COLORTERM",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "NO_COLOR",
        "PATH",
        "PYTHONIOENCODING",
        "PYTHONUNBUFFERED",
        "SHELL",
        "TERM",
        "TEMP",
        "TMP",
        "TMPDIR",
        "TZ",
        "USER",
        "VIRTUAL_ENV",
    }
)


class ProbeError(RuntimeError):
    """Raised when the supervisor protocol cannot be observed safely."""


class SupervisorNotFoundError(ProbeError):
    """Raised when no executable supervisor exists at any discovery location."""


@dataclass(frozen=True)
class ProbeResult:
    """The preflight process result and its parsed report."""

    supervisor: str
    closure: str
    command: tuple[str, ...]
    returncode: int
    report: dict[str, Any]
    stdout: str
    stderr: str
    supervisor_digest: str | None = None

    @property
    def outcome(self) -> str:
        return str(self.report.get("outcome", ""))

    def to_dict(self) -> dict[str, Any]:
        return {
            "supervisor": self.supervisor,
            "supervisor_digest": self.supervisor_digest,
            "closure": self.closure,
            "command": list(self.command),
            "returncode": self.returncode,
            "report": self.report,
            "stderr": self.stderr,
        }


@dataclass(frozen=True)
class BuildResult:
    """The one non-serving create invocation performed after preflight."""

    supervisor: str
    closure: str
    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    diagnostic: dict[str, Any] | None = None
    supervisor_digest: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "supervisor": self.supervisor,
            "supervisor_digest": self.supervisor_digest,
            "closure": self.closure,
            "command": list(self.command),
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "diagnostic": self.diagnostic,
        }


def _candidate_locations(explicit: Path | str | None) -> list[str]:
    if explicit is not None:
        return [str(Path(explicit).expanduser())]
    candidates: list[str] = []
    environment_value = os.environ.get(SUPERVISOR_ENV)
    if environment_value:
        candidates.append(str(Path(environment_value).expanduser()))
    path_value = shutil.which("nxd-desktop-supervisor")
    if path_value:
        candidates.append(path_value)
    candidates.append(str(Path.home() / ".nxd" / "bin" / "nxd-desktop-supervisor"))
    return candidates


def resolve_supervisor(explicit: Path | str | None = None) -> Path:
    """Resolve an executable supervisor, rejecting broken symlinks."""

    tried = _candidate_locations(explicit)
    checked: list[str] = []
    for candidate in tried:
        resolved = shutil.which(candidate) if not Path(candidate).is_absolute() else candidate
        display = str(resolved or candidate)
        if not resolved:
            checked.append(f"{display} (not found on PATH)")
            continue
        path = Path(resolved).expanduser()
        if path.is_symlink() and not path.exists():
            checked.append(f"{path} (broken symlink)")
            continue
        try:
            resolved_path = path.resolve(strict=True)
        except OSError as exc:
            checked.append(f"{path} (unresolvable: {exc})")
            continue
        if resolved_path.is_file() and os.access(resolved_path, os.X_OK):
            return resolved_path
        checked.append(f"{path} (not an executable file)")
    if explicit is not None:
        detail = f"explicit supervisor {explicit!s}"
    else:
        detail = f"{SUPERVISOR_ENV}, PATH, and ~/.nxd/bin/nxd-desktop-supervisor"
    tried_text = ", ".join(checked) if checked else "<no locations>"
    raise SupervisorNotFoundError(
        f"no executable nxd-desktop-supervisor found while checking {detail}; tried: {tried_text}"
    )


def _run(command: Sequence[str], *, closure: Path) -> subprocess.CompletedProcess[str]:
    environment = {
        key: value for key, value in os.environ.items() if key in SESSION_ENVIRONMENT_ALLOWLIST
    }
    if not environment.get(PYTHON_ENV):
        provisioned_python = Path.home() / ".nxd" / "desktop-venv" / "bin" / "python"
        if provisioned_python.is_file() and os.access(provisioned_python, os.X_OK):
            # Direct CLI probes do not pass through Desktop's MCP registration,
            # which normally pins this interpreter for the supervisor's kernel
            # and compute children.
            environment[PYTHON_ENV] = str(provisioned_python)
    try:
        return subprocess.run(
            list(command),
            cwd=closure,
            check=False,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        raise ProbeError(f"could not execute supervisor for closure {closure}: {exc}") from exc


def _parse_json(stdout: str, *, closure: Path) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    for index, character in enumerate(stdout):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(stdout[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and "stages" in value:
            return value
    raise ProbeError(
        f"supervisor check for closure {closure} did not emit a machine-readable JSON report; "
        f"stdout={stdout[-1000:]!r}"
    )


def _supervisor_digest(path: Path) -> str:
    """Hash the resolved executable so reports identify what actually ran."""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_report_shape(report: Mapping[str, Any], *, closure: Path) -> None:
    outcome = report.get("outcome")
    if outcome not in ALLOWED_STATUSES:
        raise ProbeError(f"supervisor report for closure {closure} has unknown outcome {outcome!r}")
    stages = report.get("stages")
    if not isinstance(stages, list) or not stages:
        raise ProbeError(f"supervisor report for closure {closure} has no stages")
    for stage in stages:
        if not isinstance(stage, Mapping):
            raise ProbeError(f"supervisor report for closure {closure} contains a non-object stage")
        status = stage.get("status")
        if status not in ALLOWED_STATUSES:
            raise ProbeError(
                f"supervisor report for closure {closure} has unknown status {status!r} "
                f"in stage {stage.get('stage', '<unnamed>')!r}"
            )
        checks = stage.get("checks")
        if not isinstance(checks, list):
            raise ProbeError(
                f"supervisor report for closure {closure} has no checks array in stage {stage.get('stage')!r}"
            )
        for check in checks:
            if not isinstance(check, Mapping):
                raise ProbeError(f"supervisor report for closure {closure} contains a non-object check")
            check_status = check.get("status")
            if check_status not in ALLOWED_STATUSES:
                raise ProbeError(
                    f"supervisor report for closure {closure} has unknown check status {check_status!r} "
                    f"for code {check.get('code', '<unnamed>')!r}"
                )
            if not check.get("code"):
                raise ProbeError(f"supervisor report for closure {closure} has a check without a code")


def run_preflight(
    closure: Path | str,
    *,
    supervisor: Path | str | None = None,
    data_dir: Path | str | None = None,
    workflow: str = "drift-canary",
) -> ProbeResult:
    """Run ``check --definition ... --json`` and preserve its report."""

    closure_path = Path(closure).expanduser().resolve()
    if not closure_path.is_dir():
        raise ProbeError(f"canary closure directory does not exist: {closure_path}")
    supervisor_path = resolve_supervisor(supervisor)
    command = [str(supervisor_path), "check", "--definition", str(closure_path), "--workflow", workflow]
    if data_dir is not None:
        command.extend(("--data-dir", str(Path(data_dir).expanduser())))
    command.append("--json")
    completed = _run(command, closure=closure_path)
    report = _parse_json(completed.stdout, closure=closure_path)
    _validate_report_shape(report, closure=closure_path)
    return ProbeResult(
        supervisor=str(supervisor_path),
        closure=str(closure_path),
        command=tuple(command),
        returncode=completed.returncode,
        report=report,
        stdout=completed.stdout,
        stderr=completed.stderr,
        supervisor_digest=_supervisor_digest(supervisor_path),
    )


def run_build(
    closure: Path | str,
    *,
    supervisor: Path | str | None = None,
    data_dir: Path | str | None = None,
    workflow: str = "drift-canary",
) -> BuildResult:
    """Perform one real non-serving ``create`` build after preflight."""

    closure_path = Path(closure).expanduser().resolve()
    if not closure_path.is_dir():
        raise ProbeError(f"canary closure directory does not exist: {closure_path}")
    supervisor_path = resolve_supervisor(supervisor)
    effective_data_dir = _effective_data_dir(closure_path, data_dir)
    previous_diagnostics = _diagnostic_paths(effective_data_dir)
    command = [
        str(supervisor_path),
        "create",
        "--definition",
        str(closure_path),
        "--workflow",
        workflow,
        "--hold-secs",
        "0",
    ]
    command.extend(("--data-dir", str(effective_data_dir)))
    completed = _run(command, closure=closure_path)
    diagnostic = (
        _read_failed_build_diagnostic(effective_data_dir, previous_diagnostics)
        if completed.returncode != 0
        else None
    )
    return BuildResult(
        supervisor=str(supervisor_path),
        closure=str(closure_path),
        command=tuple(command),
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        diagnostic=diagnostic,
        supervisor_digest=_supervisor_digest(supervisor_path),
    )


def run_probe_and_build(
    closure: Path | str,
    *,
    supervisor: Path | str | None = None,
    data_dir: Path | str | None = None,
    workflow: str = "drift-canary",
    build: bool = True,
) -> tuple[ProbeResult, BuildResult | None]:
    """Run preflight, then attempt exactly one real build when requested."""

    closure_path = Path(closure).expanduser().resolve()
    temporary: tempfile.TemporaryDirectory[str] | None = None
    if data_dir is None:
        temporary = tempfile.TemporaryDirectory(
            prefix=f".{closure_path.name}-canary-data-",
            dir=closure_path.parent,
        )
        effective_data_dir = Path(temporary.name)
    else:
        effective_data_dir = _effective_data_dir(closure_path, data_dir)
    try:
        preflight = run_preflight(
            closure_path,
            supervisor=supervisor,
            data_dir=effective_data_dir,
            workflow=workflow,
        )
        built = (
            run_build(
                closure_path,
                supervisor=preflight.supervisor,
                data_dir=effective_data_dir,
                workflow=workflow,
            )
            if build
            else None
        )
        return preflight, built
    finally:
        if temporary is not None:
            temporary.cleanup()


def _effective_data_dir(closure: Path, data_dir: Path | str | None) -> Path:
    """Return an existing per-run data directory for every create invocation."""

    if data_dir is None:
        return Path(tempfile.mkdtemp(prefix=f".{closure.name}-canary-data-", dir=closure.parent))
    path = Path(data_dir).expanduser()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _diagnostic_paths(data_dir: Path) -> set[Path]:
    """Return the failed-run diagnostic files already present for this run."""

    diagnostics = data_dir / "diagnostics"
    if not diagnostics.is_dir():
        return set()
    return set(diagnostics.glob("*/diagnostic.json"))


def _read_failed_build_diagnostic(data_dir: Path, previous: set[Path]) -> dict[str, Any] | None:
    """Read the newest diagnostic written by a failed create invocation."""

    candidates = [path for path in _diagnostic_paths(data_dir) if path not in previous]
    if not candidates:
        candidates = list(_diagnostic_paths(data_dir))
    for path in sorted(candidates, key=lambda value: value.stat().st_mtime_ns, reverse=True):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(value, dict):
            return value
    return None
