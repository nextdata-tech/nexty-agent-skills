"""Put the nxd monorepo source ahead of the installed wheel, when it is newer.

WHY THIS EXISTS. The installed wheel is `nxd.core` v0.41.26. The monorepo source
is v0.41.14x, and the difference matters here: `local/duckdb/storage` — and with
it the `DuckDbOutput` context type the transform binds — does not exist in the
wheel. `storage_context_type_for_driver` has no duckdb case there, so a DuckDB
output port is not constructible at all and the transform can only be proven
with NO ports and its own env-var plumbing.

With the source on `sys.path` first, the Python layer overlays the wheel while
still using its compiled Rust extension, so no build step is required.

Deliberately NOT silent. Which nxd answered is load-bearing for what a green run
proves, so `describe()` reports the version and where it came from, and the
scripts print it. A run that quietly fell back to the wheel would prove less than
its output claims.
"""

from __future__ import annotations

import sys
from pathlib import Path

#: Walk up looking for the monorepo. The experiment lives in a worktree of the
#: SKILLS repo, not of the monorepo, so this cannot be a fixed relative path.
_CANDIDATE_ROOTS = (
    Path("/Volumes/PRO-G40/projects/nxd"),
    Path.home() / "projects" / "nxd",
)

_SOURCE_SUBDIRS = ("components/nxd_py/core", "components/nxd_py/data_product")


def _monorepo_source_paths() -> list[Path]:
    for root in _CANDIDATE_ROOTS:
        paths = [root / sub for sub in _SOURCE_SUBDIRS]
        if all(p.is_dir() for p in paths):
            return paths
    return []


def use_monorepo_nxd() -> bool:
    """Prepend the monorepo nxd source to `sys.path`. True if it was found.

    Must run BEFORE the first `import nxd`: once the wheel's `nxd` package is
    imported, prepending a path does nothing.
    """
    if "nxd" in sys.modules:
        raise RuntimeError(
            "nxd was already imported; call use_monorepo_nxd() before any "
            "`import nxd`, or the path change has no effect and the run "
            "silently uses the older wheel."
        )
    paths = _monorepo_source_paths()
    for path in reversed(paths):
        sys.path.insert(0, str(path))
    return bool(paths)


def describe() -> str:
    """One line naming which nxd is live and whether it supports duckdb ports."""
    import nxd.core  # noqa: PLC0415  - after path setup, on purpose

    # `nxd.core` exposes no __version__; the number lives in the sibling
    # `nxd/version.py` of whichever tree answered. Resolved from nxd's own
    # __path__ so it reports the tree actually in use, not one guessed at.
    version = "unknown"
    for entry in getattr(sys.modules["nxd"], "__path__", []):
        candidate = Path(entry) / "version.py"
        if candidate.is_file():
            for line in candidate.read_text(encoding="utf-8").splitlines():
                if line.startswith("__version__"):
                    version = line.split("=", 1)[1].split("#")[0].strip().strip('"\'')
                    break
        if version != "unknown":
            break
    try:
        from nxd.core.context import DuckDbOutput  # noqa: F401,PLC0415

        duck = "DuckDbOutput available"
    except ImportError:
        duck = "NO DuckDbOutput (wheel too old; ports cannot be bound)"
    source = "monorepo source" if _monorepo_source_paths() else "installed wheel"
    return f"nxd.core {version} ({source}) — {duck}"
