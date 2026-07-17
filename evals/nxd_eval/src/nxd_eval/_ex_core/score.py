"""Deterministic-EX scoring core.

The pure scoring surface shared by the nxd_eval eval harness and the cross-DP
join-strategy experiment, so the two can never drift on what "PASS" or
"FANOUT_SAFE" means. nxd_eval OWNS this module; the cross-DP harness imports it
(`from nxd_eval._ex_core import score`) — the ownership is deliberately this way
round so the shipping package is self-contained and the experiment consumes it.

Everything here is a pure function over plain dicts plus the vendored PoC
scoring / structure_check primitives (`_ex_core._primitives`). No network, no
Snowflake, no filesystem or report I/O — that CLI/report layer lives in the
cross-DP harness (`evals/cross-dp-joins/harness/score.py`), which imports the
functions below.

Public surface (re-exported by `nxd_eval.scoring`):

    score_one(trial, gold_record, *, strategy_for_abstain=None) -> str
    rows_equal_name_aware(actual, gold_rows, mode) -> bool
    _norm_rowset(rows) -> frozenset[tuple]
    matches_compiler(rows, compiler_rows) -> bool
    fanout_of(sql) -> str
    distinct_results(trials) -> int

Also used by the cross-DP harness: `COMPILER_STRATEGY`, `_remap_gold_record`.

EX equivalence bound (optimistic single-frozen-gold comparison)
---------------------------------------------------------------
`score_one` / `rows_equal_name_aware` compare agent rows against ONE frozen gold
result set. Test-based execution accuracy on a single frozen result is
OPTIMISTIC: two queries can coincide on the frozen database yet differ in
general, so a coincidental row match is credited as a correct query. This is the
known EX-overestimate of the result-comparison family — SpotIt (Klopfenstein et
al. 2025, arXiv:2510.26840) measures 11–14% EX drop under SMT bounded equivalence on
BIRD, and Zhong et al. (2020, EMNLP, arXiv:2010.02840) bound the false-negative
side of single-database comparison at 2.5% avg / 8.1% worst on Spider.

Our architecture is LESS exposed than raw text-to-SQL: the selection→SQL layer
is deterministic via the compiler, so there is no free-form-SQL diversity to be
falsely equated — the exposure is confined to this frozen-gold row comparison,
and `matches_compiler` (below) cross-checks against the compiler's own executed
rows. We do not run a bounded-equivalence verifier; this is a documented bound,
not a solved gap. Full write-up: `evals/nxd_eval/METHODOLOGY.md`.
"""

from __future__ import annotations

from collections import Counter

# --------------------------------------------------------------------------- #
# Scoring primitives
# --------------------------------------------------------------------------- #
# The scorer reuses the frozen scoring + structure_check primitives verbatim (a
# byte-for-byte copy of the text-to-SQL PoC harness they originated in) so the
# eval never drifts on what "PASS" or "FANOUT_SAFE" means. They are vendored
# into this package (`_ex_core._primitives`) so the built wheel is
# self-contained — nothing resolved by filesystem path at runtime.
from ._primitives import scoring
from ._primitives import structure_check

# Strategy id treated as the compiler oracle for the matches_compiler axis.
COMPILER_STRATEGY = "A"


# --------------------------------------------------------------------------- #
# Gold remap (PoC `id` -> scoring `question_id`)
# --------------------------------------------------------------------------- #


def _remap_gold_record(rec: dict, frozen_rows: dict | None) -> dict:
    """Remap a raw GOLD_CROSS_DP record into the scoring.score_accuracy shape.

    PoC gold keys differ from what scoring reads:
      id              -> question_id
      expect_abstain  (list[str])  -> expects_abstain ({strategy: True})
      rows            injected from the frozen oracle ({id: {"rows": [...]}})

    `frozen_rows` is the freeze_gold.freeze() output keyed by gold id; pass None
    to leave rows absent (rows-equality then always fails, surfacing missing
    oracle wiring rather than silently passing).
    """
    out = dict(rec)
    qid = rec.get("id")
    out["question_id"] = qid
    expect_list = rec.get("expect_abstain") or []
    out["expects_abstain"] = {a: True for a in expect_list}
    if frozen_rows is not None:
        out["rows"] = (frozen_rows.get(qid) or {}).get("rows")
    return out


# --------------------------------------------------------------------------- #
# Pure scoring helpers
# --------------------------------------------------------------------------- #


def _norm_rowset(rows: list[dict] | None) -> frozenset[tuple]:
    """Order-independent, name-blind signature of a row-set for set-equality.

    Lowercases column names, normalizes values via scoring._norm_value, and
    reduces each row to scoring._row_signature (value multiset, column-name
    blind, numeric-tolerant). Returns a frozenset of row signatures — DISTINCT
    rows only, which is the contract for the compiler-as-oracle and determinism
    axes (both ask "is this the same set of answers", not "same multiplicity").
    """
    if rows is None:
        return frozenset()
    sigs = set()
    for raw in rows:
        nrow = {scoring._norm_key(k): scoring._norm_value(v) for k, v in raw.items()}
        sigs.add(scoring._row_signature(nrow, scoring._ALL_COLS))
    return frozenset(sigs)


def _bucket_numeric_cells(rows: list[dict] | None) -> list[dict] | None:
    """Snap every numeric cell to the vendored scorer's tolerance bucket.

    The vendored `rows_equal` only applies `_NUMERIC_TOL` (1e-6) rounding under
    `equality_mode="numeric"` — the default "set" mode (and "multiset") compare
    raw float values, so harmless float drift like 840110.00000001 spuriously
    fails against gold's 840110.0 even though the doc promises tolerance.
    Rather than editing the drift-pinned vendored file, we pre-round numeric
    cells of both sides here, in the owned layer, to the SAME bucket the
    vendored `_row_signature` computes under "numeric" mode
    (`round(v / scoring._NUMERIC_TOL)`) before delegating. Doing so BEFORE
    `rows_equal` runs makes its exact-equality comparison treat bucket-identical
    floats as equal in every mode, while real differences (e.g. 0.5 apart) still
    land in different buckets and still fail. `None` passes through unchanged;
    non-float cells (str/bool/None/int) are untouched.
    """
    if rows is None:
        return None
    out = []
    for raw in rows:
        nrow = {}
        for k, v in raw.items():
            nv = scoring._norm_value(v)
            if isinstance(nv, float):
                nv = round(nv / scoring._NUMERIC_TOL) * scoring._NUMERIC_TOL
            nrow[k] = nv
        out.append(nrow)
    return out


def score_one(
    trial: dict, gold_record: dict, *, strategy_for_abstain: str | None = None
) -> str:
    """Accuracy for a single trial via the PoC scorer.

    `strategy_for_abstain` is the `approach` key scoring uses to read
    expects_abstain; defaults to the trial's own strategy.
    """
    approach = strategy_for_abstain or trial.get("strategy")
    mode = (gold_record.get("equality_mode") or "set") if gold_record else "set"
    trial_rows = trial.get("rows")
    gold_for_scoring = gold_record
    if mode != "numeric" and gold_record is not None:
        # "numeric" mode already tolerates float drift via the vendored
        # rows_equal; bucket the other modes here so tolerance is real under
        # the default "set" mode too (see _bucket_numeric_cells).
        trial_rows = _bucket_numeric_cells(trial_rows)
        gold_for_scoring = dict(gold_record)
        gold_for_scoring["rows"] = _bucket_numeric_cells(gold_record.get("rows"))
    verdict = scoring.score_accuracy(
        trial_rows,
        gold_for_scoring,
        abstained=bool(trial.get("abstained")),
        approach=approach,
        errored=bool(trial.get("errored")),
    )
    # CP1 hardening (harness layer): the PoC's PASS is column-name blind, so two
    # numeric measures SWAPPED still score PASS. When gold has >=2 numeric measure
    # columns, re-validate name-aware and downgrade a name-mismatch PASS to FAIL.
    # Only touches the answered-PASS path — ABSTAIN/ERROR/N/A/FAIL are unchanged.
    if (
        verdict == "PASS"
        and not bool(trial.get("abstained"))
        and not bool(trial.get("errored"))
    ):
        # Re-check against the SAME bucketed rows score_accuracy just judged —
        # using the raw (unbucketed) rows here would spuriously downgrade a
        # float-drift PASS back to FAIL under "set"/"multiset" mode.
        if not rows_equal_name_aware(
            trial_rows, gold_for_scoring.get("rows") if gold_for_scoring else None, mode
        ):
            return "FAIL"
    return verdict


def fanout_of(sql: str | None) -> str:
    """Fan-out verdict for an emitted SQL string (FANOUT_SAFE/RISK/N/A).

    Delegates to structure_check.verdict, which returns "N/A" for a None/empty
    SQL (an abstain or a strategy that merges client-side without emitting SQL).
    """
    return structure_check.verdict(sql)


# --------------------------------------------------------------------------- #
# Multi-measure name-aware accuracy guard (harness layer; CP1 hardening)
# --------------------------------------------------------------------------- #
# The PoC's scoring.rows_equal compares a VALUE-multiset that is column-name
# blind: a row with two numeric measures SWAPPED (e.g. {revenue: 5, cost: 95}
# vs {revenue: 95, cost: 5}) scores PASS because the multiset {5, 95} is
# identical. That is fine for single-measure questions but unsafe once a gold
# record carries >=2 numeric measure columns. We HARDEN that case here, in the
# harness, WITHOUT editing the shared PoC scoring.py: when the gold rows have
# >=2 numeric columns, we additionally require a name-aware match on the numeric
# cells (compare (col_name, value) pairs), falling back to the PoC verdict for
# the single-/zero-measure case so existing behavior is unchanged.


def _numeric_cells_named(rows: list[dict]) -> Counter:
    """Multiset of (normalized_col_name, bucketed_numeric_value) over numeric cells.

    Mirrors the PoC normalization: column names via scoring._norm_key, values via
    scoring._norm_value, numeric values bucketed to scoring's numeric tolerance so
    3.0000001 and 3.0 collapse (same as scoring._row_signature under _ALL_COLS).
    Non-numeric / None / bool cells are ignored — this guard only constrains the
    numeric measures, leaving label/dimension matching to the PoC scorer.
    """
    out: Counter = Counter()
    for raw in rows or []:
        for k, v in raw.items():
            nv = scoring._norm_value(v)
            if isinstance(nv, bool) or not isinstance(nv, float):
                continue
            bucket = round(nv / scoring._NUMERIC_TOL)
            out[(scoring._norm_key(k), bucket)] += 1
    return out


def rows_equal_name_aware(
    actual: list[dict] | None, gold_rows: list[dict] | None, mode: str
) -> bool:
    """Harness wrapper over scoring.rows_equal that hardens the multi-measure case.

    Returns the PoC verdict for zero-/single-numeric-measure gold rows. When the
    gold record has >=2 numeric measure columns, additionally require the numeric
    cells to match name-aware (so two measures SWAPPED no longer scores PASS).
    """
    base = scoring.rows_equal(actual, gold_rows, mode)
    if not base or actual is None or gold_rows is None:
        return base
    # Only tighten when gold genuinely has >=2 distinct numeric measure columns.
    gold_numeric_cols = scoring._numeric_cols([scoring._norm_row(r) for r in gold_rows])
    if len(gold_numeric_cols) < 2:
        return base
    return _numeric_cells_named(actual) == _numeric_cells_named(gold_rows)


def matches_compiler(rows: list[dict] | None, compiler_rows: list[dict] | None) -> bool:
    """Set-equality of this strategy's rows vs the compiler's executed rows.

    Name-blind, numeric-tolerant, DISTINCT-row comparison (the same normalization
    rows_equal uses). When the compiler produced no rows for the question (None),
    there is no oracle to match against — return False so the gap is visible.
    """
    if compiler_rows is None:
        return False
    return _norm_rowset(rows) == _norm_rowset(compiler_rows)


def distinct_results(trials: list[dict]) -> int:
    """Count distinct normalized row-sets across N trials of one (q, strategy).

    Errored/abstained trials contribute an empty row-set; a strategy that
    sometimes answers and sometimes abstains therefore reads as non-deterministic
    (distinct > 1), which is the intended signal.
    """
    return len({_norm_rowset(t.get("rows")) for t in trials})
