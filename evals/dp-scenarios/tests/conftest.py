"""Test-only import seam for the shared repo-level desktop substrate."""

from __future__ import annotations

from pathlib import Path
import sys


_EVALS_ROOT = Path(__file__).resolve().parents[2]
if str(_EVALS_ROOT) not in sys.path:
    sys.path.append(str(_EVALS_ROOT))
