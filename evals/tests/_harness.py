"""Locate the field-mapper harness, which lives in the nxd monorepo.

The harness ships inside the `nxd` package as `nxd.experimental.field_mapper`.
That copy is canonical: it is where the acceptance fixtures run, where the spec
hashes are pinned, and what a closure actually imports at execution.

This repo used to carry a second copy under `mapper/field_mapper/` purely so the
consent-gate tests had something real to run against. Two copies of executable
source with nothing enforcing sync is a defect in its own right — they drifted
within a day of the split — so the copy is gone and the tests reach the
canonical one instead.

Reaching it is a problem, because this repo's CI is air-gapped from the
monorepo: there is no submodule pointing at nxd (the dependency runs the other
way), and nxd wheels publish to a private registry rather than PyPI, so
`--with nxd` is not available either. The tests that need a live harness
therefore SKIP here and run where both trees exist — a developer checkout, and
the monorepo's own CI, which already vendors this repo at
`external/nexty-agent-skills`.

Most of the gate suite is unaffected. The gate is the subject of those tests;
the harness is a fixture, and the majority of them exercise branches that never
reach it.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

#: Environment variable naming the nxd monorepo checkout root.
NXD_REPO_ENV = "NXD_REPO"

_PACKAGE_SUFFIX = Path("components") / "nxd_py" / "data_product" / "nxd" / "experimental" / "field_mapper"

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _candidate_roots() -> list[Path]:
    """Monorepo checkout roots to try, most explicit first.

    The sibling convention covers the ordinary developer layout — both repos
    cloned side by side — so the tests run locally with nothing configured. The
    env var is what CI sets, and what a non-standard layout overrides with.
    """
    roots: list[Path] = []
    env = os.environ.get(NXD_REPO_ENV)
    if env:
        roots.append(Path(env))
    # Walk up rather than checking one fixed parent. A git worktree of this
    # repo sits at `<repo>/.claude/worktrees/<name>/`, so the sibling clone is
    # three levels further up than it is from a plain checkout — and the
    # monorepo is itself usually checked out as a worktree, which is why each
    # ancestor is tried against both layouts by `harness_path`.
    for ancestor in (_REPO_ROOT, *_REPO_ROOT.parents):
        roots.append(ancestor.parent / "nxd")
    return roots


def harness_path() -> Path | None:
    """Path to the installed-package harness, or None when unreachable.

    Returns the directory that `nxd.experimental.field_mapper` resolves to, so
    a caller can copy it into a closure and have the dotted import work exactly
    as it will from site-packages.
    """
    for root in _candidate_roots():
        candidate = root / _PACKAGE_SUFFIX
        if (candidate / "__init__.py").is_file():
            return candidate
        # The monorepo may itself be checked out as a worktree. Its harness is
        # then under `.claude/worktrees/<name>/`, not the root, and a checkout
        # that only exists in that form would otherwise read as absent.
        worktrees = root / ".claude" / "worktrees"
        if worktrees.is_dir():
            for tree in sorted(worktrees.iterdir()):
                candidate = tree / _PACKAGE_SUFFIX
                if (candidate / "__init__.py").is_file():
                    return candidate
    return None


#: Skip marker for tests that need the harness to ANSWER — to compute a real
#: spec id, apply a real consent rule, or be imported by a transform under
#: Phase B. Tests that only need the gate to notice an import do not need this.
requires_harness = pytest.mark.skipif(
    harness_path() is None,
    reason=(
        f"field-mapper harness not found. It lives in the nxd monorepo at "
        f"{_PACKAGE_SUFFIX}; set {NXD_REPO_ENV}=/path/to/nxd or clone nxd "
        f"beside this repo. These tests run in the monorepo's CI, which has "
        f"both trees."
    ),
)
