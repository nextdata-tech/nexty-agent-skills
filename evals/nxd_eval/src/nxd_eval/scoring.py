"""Thin adapter over the cross-DP ``harness/score.py`` deterministic-EX core.

The deterministic lane MUST NOT re-implement "what PASS means". The single
source of truth is ``evals/cross-dp-joins/harness/score.py`` — it wraps the
text-to-SQL PoC's scoring primitives and adds the name-aware multi-measure
guard. This module loads that file the SAME way it loads the PoC (by file path,
via ``importlib``), because there is no importable package around it, and
re-exports its public surface so the eval and the PoC never drift.

``score.py`` resolves the PoC scoring primitives (``scoring`` /
``structure_check``) from ``T2SQL_POC_ROOT`` (env override) or a hardcoded
worktree path that does not exist on every machine. To keep this eval project
self-contained, the exact PoC ``scoring.py`` + ``structure_check.py`` are
vendored under ``vendor/poc_scoring/harness/`` and we point ``T2SQL_POC_ROOT``
at them before loading ``score.py`` — UNLESS the caller already set the env, in
which case their real PoC checkout wins. Either way the EX verdict flows through
``score.py``'s wrappers, never a local re-implementation.

Public surface re-exported (see ``score.py`` for signatures):

    score_one(trial, gold_record, *, strategy_for_abstain=None) -> str
    rows_equal_name_aware(actual, gold_rows, mode) -> bool
    _norm_rowset(rows) -> frozenset[tuple]
    matches_compiler(rows, compiler_rows) -> bool
    fanout_of(sql) -> str
    distinct_results(trials) -> int
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType

# --------------------------------------------------------------------------- #
# Locate the cross-DP score.py wrapper + the vendored PoC scoring primitives.
# --------------------------------------------------------------------------- #

# evals/nxd_eval/src/nxd_eval/scoring.py -> repo root is four parents up.
_REPO_ROOT = Path(__file__).resolve().parents[4]
_SCORE_PY = _REPO_ROOT / "evals" / "cross-dp-joins" / "harness" / "score.py"

# The vendored PoC scoring root has the shape score.py expects: it loads
# ``<POC_ROOT>/harness/scoring.py`` and ``<POC_ROOT>/harness/structure_check.py``.
_VENDORED_POC_ROOT = Path(__file__).resolve().parent.parent.parent / "vendor" / "poc_scoring"


def _load_score_module() -> ModuleType:
    """Load ``cross-dp-joins/harness/score.py`` by file path.

    Points ``T2SQL_POC_ROOT`` at the vendored PoC primitives so ``score.py``
    resolves ``scoring`` / ``structure_check`` from this repo, unless the caller
    already set the env to their own PoC checkout (that wins). Loading by path
    mirrors how ``score.py`` itself loads the PoC, so there is no packaging
    assumption.
    """
    if not os.environ.get("T2SQL_POC_ROOT"):
        if not (_VENDORED_POC_ROOT / "harness" / "scoring.py").exists():
            raise FileNotFoundError(
                "deterministic-EX core unavailable: neither T2SQL_POC_ROOT is "
                f"set nor is the vendored PoC present at {_VENDORED_POC_ROOT}. "
                "score.py cannot resolve the PoC scoring primitives."
            )
        os.environ["T2SQL_POC_ROOT"] = str(_VENDORED_POC_ROOT)

    if not _SCORE_PY.exists():  # pragma: no cover - repo-layout guard
        raise FileNotFoundError(f"cross-DP score.py not found at {_SCORE_PY}")

    spec = importlib.util.spec_from_file_location("nxd_eval_cdp_score", _SCORE_PY)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise ImportError(f"cannot load score.py from {_SCORE_PY}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


_score = _load_score_module()

# --------------------------------------------------------------------------- #
# Re-export the public deterministic-EX surface (no re-implementation).
# --------------------------------------------------------------------------- #

score_one = _score.score_one
rows_equal_name_aware = _score.rows_equal_name_aware
_norm_rowset = _score._norm_rowset
matches_compiler = _score.matches_compiler
fanout_of = _score.fanout_of
distinct_results = _score.distinct_results

__all__ = [
    "score_one",
    "rows_equal_name_aware",
    "_norm_rowset",
    "matches_compiler",
    "fanout_of",
    "distinct_results",
]
