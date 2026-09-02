"""Small helpers for the local Claude Code scenario runner."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
from collections.abc import Mapping
from typing import Any

from dp_scenarios.ledger import SupervisorFacts


class LocalRunnerError(ValueError):
    """Raised when local runner setup is incomplete."""


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
    "temporary_plugin",
]
