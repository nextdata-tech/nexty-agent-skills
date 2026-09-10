"""Small helpers for the local Claude Code scenario runner."""

from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import tempfile
from collections.abc import Mapping
from typing import Any

from dp_scenarios.ledger import SupervisorFacts


class LocalRunnerError(ValueError):
    """Raised when local runner setup is incomplete."""


_JOB_HELPER_FILES = (
    "SKILL.md",
    "scripts/dp_diagnostics.py",
    "scripts/dp_spec_authoring.py",
    "scripts/dp_spec_v2.py",
    "scripts/requirements.txt",
    "scripts/self_check.py",
    "scripts/validate_dp_spec.py",
)


def staged_job_helper_dir(plugin_dir: str | Path, expected_version: str) -> Path:
    """Return the helper tree belonging to one staged plugin.

    The normal skill bootstrap searches every installed copy visible from the
    host home. That is useful for an interactive session, but it can select an
    older cached plugin when the scenario runner stages a newer pack. The
    runner therefore resolves the helper directory from the exact staged
    plugin and rejects an incomplete or version-mismatched tree before any
    Claude process starts.
    """

    if not isinstance(expected_version, str) or not expected_version.strip():
        raise LocalRunnerError("staged skill pack version must be non-empty")
    staged_root = Path(plugin_dir).expanduser().resolve()
    helper = (staged_root / "src" / "nxd-run-job-loop").resolve()
    try:
        helper.relative_to(staged_root)
    except ValueError as exc:
        raise LocalRunnerError("staged job helper directory escaped the plugin root") from exc
    if not helper.is_dir():
        raise LocalRunnerError(f"staged nxd-run-job-loop helper directory is missing: {helper}")

    manifest_path = staged_root / ".claude-plugin" / "plugin.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LocalRunnerError(f"staged plugin manifest is unreadable: {manifest_path}") from exc
    if not isinstance(manifest, Mapping) or manifest.get("version") != expected_version:
        raise LocalRunnerError("staged plugin manifest version does not match the pinned skill pack")

    missing = [relative for relative in _JOB_HELPER_FILES if not (helper / relative).is_file()]
    if missing:
        raise LocalRunnerError(
            "staged nxd-run-job-loop helper is incomplete: " + ", ".join(missing)
        )
    skill_text = (helper / "SKILL.md").read_text(encoding="utf-8")
    metadata_match = re.search(r"(?ms)^metadata:\s*$.*?^\s+version:\s*([^\s#]+)\s*$", skill_text)
    if metadata_match is None or metadata_match.group(1).strip("\"'") != expected_version:
        raise LocalRunnerError("staged nxd-run-job-loop skill version does not match the pinned skill pack")
    return helper


class FileSupervisorRecordReader:
    """Read a runner-owned supervisor fact document at grading time."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def read_facts(self) -> SupervisorFacts:
        """Load and validate the five canonical facts, fail closed on absence."""

        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw, Mapping):
            raise LocalRunnerError(f"supervisor fact artifact is not an object: {self.path}")
        return SupervisorFacts.from_mapping(raw)


def stage_plugin(source_root: str | Path, destination_parent: str | Path) -> Path:
    """Stage ``src/`` as a private Claude Code plugin directory.

    The staged plugin is outside the agent workspace. The agent therefore
    receives the skill pack but cannot edit the source checkout or the runner's
    evidence directory through its normal file-tool scope.
    """

    source = Path(source_root).expanduser().resolve()
    destination = Path(destination_parent).expanduser().resolve() / "nexty-agent-skills"
    src = source / "src"
    manifest = source / ".claude-plugin" / "plugin.json"
    if not src.is_dir() or not manifest.is_file():
        raise LocalRunnerError(f"skill pack source is incomplete: {source}")
    destination.mkdir(parents=True, exist_ok=False)
    shutil.copytree(
        src,
        destination / "src",
        ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", ".ruff_cache", "*.pyc", "*.pyo"),
    )
    plugin_manifest: dict[str, Any] = json.loads(manifest.read_text(encoding="utf-8"))
    plugin_manifest["skills"] = "./src/"
    plugin_dir = destination / ".claude-plugin"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.json").write_text(
        json.dumps(plugin_manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return destination


def temporary_plugin(source_root: str | Path) -> tuple[tempfile.TemporaryDirectory[str], Path]:
    """Create a private staged plugin and return its cleanup owner plus path."""

    owner = tempfile.TemporaryDirectory(prefix="dp-scenarios-plugin-")
    try:
        return owner, stage_plugin(source_root, owner.name)
    except Exception:
        owner.cleanup()
        raise


__all__ = [
    "FileSupervisorRecordReader",
    "LocalRunnerError",
    "stage_plugin",
    "staged_job_helper_dir",
    "temporary_plugin",
]
