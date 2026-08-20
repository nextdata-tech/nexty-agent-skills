"""Delegate synthetic profile creation to the upstream PR #189 fixture."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any

from .grants import grant_scope

PROFILE_SCHEMA = "nxd-synthetic-evaluation-profile-v1"


class ProfileBuildError(RuntimeError):
    """The upstream profile builder could not produce a usable profile."""


def default_profile_builder() -> Path:
    """Locate the checked-in PR #189 profile builder in this repository."""

    return Path(__file__).resolve().parents[4] / "public/terminal-field-mapper-adapter-contract/fixtures/prepare_stdio_profile.py"


def _import_builder(path: Path) -> ModuleType | None:
    module_name = "_dp_scenarios_prepare_stdio_profile"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except ImportError:
        return None
    return module


def _run_imported(module: ModuleType, *, workspace: Path, output: Path) -> None:
    main = getattr(module, "main", None)
    if not callable(main):
        raise ProfileBuildError("prepare_stdio_profile.py is importable but has no callable main()")
    previous = sys.argv
    sys.argv = [
        str(getattr(module, "__file__", "prepare_stdio_profile.py")),
        "--workspace",
        str(workspace),
        "--output",
        str(output),
    ]
    try:
        result = main()
    finally:
        sys.argv = previous
    if result not in (None, 0):
        raise ProfileBuildError(f"upstream profile builder returned {result!r}")


def _run_subprocess(path: Path, *, workspace: Path, output: Path) -> None:
    environment = os.environ.copy()
    completed = subprocess.run(
        [sys.executable, str(path), "--workspace", str(workspace), "--output", str(output)],
        cwd=path.parent,
        env=environment,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip() or "no diagnostic"
        raise ProfileBuildError(f"upstream profile builder failed ({completed.returncode}): {detail}")


def write_synthetic_evaluation_profile(
    workspace: str | Path,
    output: str | Path,
    *,
    builder: str | Path | None = None,
    closure: str | Path | None = None,
    scenario_closure: str | Path | None = None,
    grant_fixture: Any | None = None,
    workflow: str = "terminal-mapper-adapter",
) -> Path:
    """Run the upstream builder for an isolated scenario closure.

    ``workspace`` is an evaluated caller-owned directory, not the builder's
    scratch area.  The selected closure is copied to a temporary staging
    directory before delegation.  When a :class:`GrantFixture` is supplied,
    its initial grant replaces the staged closure's grant so the approval
    subject and the ledger's grant are the same object.
    """

    workspace_path = Path(workspace).resolve()
    output_path = Path(output).resolve()
    if not workspace_path.is_dir():
        raise ProfileBuildError(f"evaluation workspace does not exist: {workspace_path}")
    if output_path == workspace_path or workspace_path in output_path.parents:
        raise ProfileBuildError("synthetic evaluation profile must be outside the evaluated workspace")
    builder_path = Path(builder).resolve() if builder is not None else default_profile_builder()
    if not builder_path.is_file():
        raise ProfileBuildError(f"upstream profile builder does not exist: {builder_path}")
    if not workflow.strip():
        raise ProfileBuildError("profile workflow must be non-empty")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if closure is not None and scenario_closure is not None:
        raise ProfileBuildError("pass only one of closure or scenario_closure")
    closure_path = Path(scenario_closure or closure or workspace).resolve()
    if not closure_path.is_dir():
        raise ProfileBuildError(f"scenario closure does not exist: {closure_path}")
    if output_path == closure_path or closure_path in output_path.parents:
        raise ProfileBuildError("synthetic evaluation profile must be outside the scenario closure")

    upstream_closure = builder_path.parent / "reference-closure"
    if not upstream_closure.is_dir():
        if grant_fixture is not None or workflow != "terminal-mapper-adapter":
            raise ProfileBuildError(
                "the selected profile builder has no configurable reference-closure; "
                "it cannot bind a scenario GrantFixture or workflow"
            )
        with tempfile.TemporaryDirectory(prefix="dp-scenarios-profile-") as temporary:
            staged_workspace = Path(temporary) / "workspace"
            shutil.copytree(closure_path, staged_workspace)
            imported = _import_builder(builder_path)
            if imported is not None:
                _run_imported(imported, workspace=staged_workspace, output=output_path)
            else:
                _run_subprocess(builder_path, workspace=staged_workspace, output=output_path)
    else:
        # The checked-in upstream script currently hardcodes both its source
        # closure and WORKFLOW.  An isolated copy lets us delegate unchanged
        # profile construction while supplying scenario-owned inputs without
        # mutating either the caller workspace or the checked-in fixture.
        with tempfile.TemporaryDirectory(prefix="dp-scenarios-profile-") as temporary:
            temporary_root = Path(temporary)
            staged_builder = temporary_root / "prepare_stdio_profile.py"
            staged_reference = temporary_root / "reference-closure"
            staged_workspace = temporary_root / "workspace"
            shutil.copy2(builder_path, staged_builder)
            shutil.copytree(closure_path, staged_reference)
            staged_workspace.mkdir()
            builder_text = staged_builder.read_text(encoding="utf-8")
            marker = 'WORKFLOW = "terminal-mapper-adapter"'
            if marker not in builder_text:
                raise ProfileBuildError(
                    "upstream profile builder does not expose its workflow constant; "
                    "scenario workflow cannot be bound"
                )
            staged_builder.write_text(
                builder_text.replace(marker, f"WORKFLOW = {workflow!r}", 1),
                encoding="utf-8",
            )
            if grant_fixture is not None:
                grant = getattr(grant_fixture, "initial", None)
                if grant is None:
                    raise ProfileBuildError("grant_fixture has no initial grant")
                grant_path = staged_reference / "contracts/mapper_grant.json"
                grant_path.parent.mkdir(parents=True, exist_ok=True)
                grant_path.write_text(
                    json.dumps(grant_scope(grant), ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
            imported = _import_builder(staged_builder)
            if imported is not None:
                _run_imported(imported, workspace=staged_workspace, output=output_path)
            else:
                _run_subprocess(staged_builder, workspace=staged_workspace, output=output_path)

    try:
        output_metadata = output_path.lstat()
    except OSError as exc:
        raise ProfileBuildError(f"upstream profile builder produced no output: {output_path}") from exc
    if stat.S_ISLNK(output_metadata.st_mode) or not stat.S_ISREG(output_metadata.st_mode):
        raise ProfileBuildError("synthetic evaluation profile must be a regular, non-symlink file")
    if not output_path.is_file():
        raise ProfileBuildError(f"upstream profile builder produced no output: {output_path}")
    try:
        raw = json.loads(output_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProfileBuildError(f"upstream profile is not valid JSON: {output_path}") from exc
    if not isinstance(raw, dict) or raw.get("schema") != PROFILE_SCHEMA:
        raise ProfileBuildError(f"upstream profile has unexpected schema: {output_path}")
    output_path.chmod(0o444)
    return output_path


prepare_profile = write_synthetic_evaluation_profile


__all__ = [
    "PROFILE_SCHEMA",
    "ProfileBuildError",
    "default_profile_builder",
    "prepare_profile",
    "write_synthetic_evaluation_profile",
]
