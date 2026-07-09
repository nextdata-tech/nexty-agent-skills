"""Thin adapter over the deterministic-EX core.

The deterministic lane MUST NOT re-implement "what PASS means". The single
source of truth is the EX core, ``_ex_core.score`` — it wraps the text-to-SQL
PoC's scoring primitives and adds the name-aware multi-measure guard. This
module re-exports its public surface so the eval and the PoC never drift.

The core and the PoC primitives it wraps (``scoring`` / ``structure_check``)
are vendored inside this package under ``_ex_core/`` — a byte-for-byte copy of
``evals/cross-dp-joins/harness/score.py`` plus the two PoC files
(``test_vendored_poc_drift.py`` pins their hashes). Because they live in the
package, the built wheel is self-contained: the core is a normal package
import, not a module resolved by filesystem path or ``T2SQL_POC_ROOT`` at
runtime. The EX verdict flows through the core's wrappers, never a local
re-implementation.

Public surface re-exported (see ``_ex_core.score`` for signatures):

    score_one(trial, gold_record, *, strategy_for_abstain=None) -> str
    rows_equal_name_aware(actual, gold_rows, mode) -> bool
    _norm_rowset(rows) -> frozenset[tuple]
    matches_compiler(rows, compiler_rows) -> bool
    fanout_of(sql) -> str
    distinct_results(trials) -> int
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Re-export the public deterministic-EX surface (no re-implementation).
# --------------------------------------------------------------------------- #
# The EX core (``_ex_core.score``) and the PoC scoring primitives it wraps
# (``_ex_core.poc_scoring``) are vendored inside this package, so the built
# wheel is self-contained — the core is a normal package import, not a module
# resolved by filesystem path at runtime.
from ._ex_core import score as _score

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
