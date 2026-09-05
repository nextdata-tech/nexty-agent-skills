"""Layout-robust roots for tests that reach outside this project.

A fixed ``Path(__file__).parents[3]`` hop to the repository root is correct for
the checked-out tree and wrong for every relocated copy of it.  The mutation
run (``scripts/mutation_test.sh``) executes the suite from
``evals/dp-scenarios/mutants/``, one level deeper, where the same hop silently
resolves to ``evals/`` and every repo-root path it builds points at a file that
does not exist.  Walking up for a marker that only the real root carries gives
the same answer from both layouts and raises rather than returning a plausible
wrong directory.
"""

from __future__ import annotations

from pathlib import Path


def _walk_up_for(*markers: str) -> Path:
    for parent in Path(__file__).resolve().parents:
        if any((parent / marker).exists() for marker in markers):
            return parent
    raise RuntimeError(f"no ancestor of {__file__} carries any of {markers!r}")


# The plugin manifest is the repo's identity file (AGENTS.md: "The plugin
# version in .claude-plugin/plugin.json is authoritative"), so it marks the
# repository root and nothing below it.
REPO_ROOT = _walk_up_for(".claude-plugin/plugin.json")

# The shared desktop substrate lives at the evals root and nowhere else.
EVALS_ROOT = _walk_up_for("desktop_stdio.py")
