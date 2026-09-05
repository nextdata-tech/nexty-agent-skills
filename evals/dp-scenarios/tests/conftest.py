"""Test-only import seam for the shared repo-level desktop substrate."""

from __future__ import annotations

import sys

from _repo_paths import EVALS_ROOT


if str(EVALS_ROOT) not in sys.path:
    sys.path.append(str(EVALS_ROOT))
