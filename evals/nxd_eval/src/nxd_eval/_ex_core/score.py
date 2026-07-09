"""Scorer for the cross-DP join-strategy eval.

Consumes a results JSON (one record per question x strategy x trial), and for
each (question, strategy) computes five axes:

  acc              accuracy vs the frozen gold record (PASS/FAIL/ABSTAIN/ERROR/N/A),
                   reusing the PoC's scoring.score_accuracy.
  fanout           fan-out safety of the emitted SQL (FANOUT_SAFE/FANOUT_RISK/N/A),
                   reusing the PoC's structure_check.fanout_safe.
  matches_compiler whether this strategy's executed rows set-equal the COMPILER
                   strategy's executed rows for the same question (the
                   compiler-as-oracle axis). Strategy A is the oracle and always
                   matches itself; a strategy that emits no rows where the
                   compiler emits some does NOT match.
  distinct_results across the N trials for this (question, strategy), the count of
                   distinct normalized row-sets (1 == deterministic output).
  abstained        whether any trial abstained.

Everything here is a pure function over plain dicts plus the PoC scoring/
structure_check modules. No network, no Snowflake. `main(results_json)` reads a
results file and writes the matrix to report/ as both CSV and markdown.

RESULTS JSON shape (list of trial records):

    {
        "question_id": str,          # gold record id (the PoC field is `id`;
                                     #   the caller must remap id -> question_id)
        "strategy":    str,          # e.g. "A" (compiler) | "B" (strict-mode)
        "trial":       int,          # 0-based trial index
        "rows":        list[dict] | None,   # executed result rows (None on error)
        "sql":         str | None,   # emitted SQL, if the strategy produced one
        "abstained":   bool,         # strategy declined this question
        "errored":     bool,         # SQL failed / solve raised
    }

GOLD records come from the PoC's gold.gold_cross_dp.GOLD_CROSS_DP, remapped to
the scoring shape (id -> question_id, expect_abstain list -> expects_abstain
dict, rows injected from the frozen oracle). `load_gold` does that remap.

The COMPILER strategy id defaults to "A" (configurable via COMPILER_STRATEGY).
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from collections import defaultdict
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------- #
# Scoring primitives
# --------------------------------------------------------------------------- #
# The scorer reuses the frozen scoring + structure_check primitives verbatim (a
# byte-for-byte copy of the text-to-SQL PoC harness they originated in) so the
# eval never drifts on what "PASS" or "FANOUT_SAFE" means. They are vendored
# into this package (`_ex_core._primitives`) so the built wheel is
# self-contained — nothing resolved by filesystem path at runtime.
from ._primitives import scoring  # noqa: E402
from ._primitives import structure_check  # noqa: E402

# Strategy id treated as the compiler oracle for the matches_compiler axis.
COMPILER_STRATEGY = "A"


# --------------------------------------------------------------------------- #
# Gold loading + remap (PoC `id` -> scoring `question_id`)
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


def load_gold(frozen_path: str | Path | None = None) -> dict[str, dict]:
    """Load GOLD_CROSS_DP from the PoC and return {question_id: remapped_record}.

    If `frozen_path` points at a freeze_gold JSON ({id: {"rows":..., ...}}),
    each record's gold rows are injected; otherwise rows are left absent.
    """
    from gold.gold_cross_dp import GOLD_CROSS_DP  # noqa: E402

    frozen_rows: dict | None = None
    if frozen_path is not None:
        frozen_rows = json.loads(Path(frozen_path).read_text())

    out: dict[str, dict] = {}
    for rec in GOLD_CROSS_DP:
        remapped = _remap_gold_record(rec, frozen_rows)
        out[remapped["question_id"]] = remapped
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


def score_one(
    trial: dict, gold_record: dict, *, strategy_for_abstain: str | None = None
) -> str:
    """Accuracy for a single trial via the PoC scorer.

    `strategy_for_abstain` is the `approach` key scoring uses to read
    expects_abstain; defaults to the trial's own strategy.
    """
    approach = strategy_for_abstain or trial.get("strategy")
    verdict = scoring.score_accuracy(
        trial.get("rows"),
        gold_record,
        abstained=bool(trial.get("abstained")),
        approach=approach,
        errored=bool(trial.get("errored")),
    )
    # CP1 hardening (harness layer): the PoC's PASS is column-name blind, so two
    # numeric measures SWAPPED still score PASS. When gold has >=2 numeric measure
    # columns, re-validate name-aware and downgrade a name-mismatch PASS to FAIL.
    # Only touches the answered-PASS path — ABSTAIN/ERROR/N/A/FAIL are unchanged.
    if verdict == "PASS" and not bool(trial.get("abstained")) and not bool(
        trial.get("errored")
    ):
        gold_rows = gold_record.get("rows")
        mode = (gold_record.get("equality_mode") or "set") if gold_record else "set"
        if not rows_equal_name_aware(trial.get("rows"), gold_rows, mode):
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


def matches_compiler(
    rows: list[dict] | None, compiler_rows: list[dict] | None
) -> bool:
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


# --------------------------------------------------------------------------- #
# Matrix assembly
# --------------------------------------------------------------------------- #

_FIELDS = [
    "question",
    "strategy",
    "acc",
    "fanout",
    "matches_compiler",
    "distinct_results",
    "abstained",
]


def build_matrix(
    results: list[dict], gold: dict[str, dict]
) -> list[dict]:
    """Collapse trial records into one matrix row per (question, strategy).

    For each (question, strategy):
      acc               from the FIRST non-errored trial if any, else the first
                        trial (so a strategy that errored every trial scores
                        ERROR, not its abstain default).
      fanout            from the first trial that emitted SQL, else N/A.
      matches_compiler  the strategy's representative rows vs the compiler
                        strategy's representative rows for the same question.
      distinct_results  across all trials.
      abstained         True if ANY trial abstained.

    Representative rows for a (q, strategy) = the rows of its first non-errored,
    non-abstained trial (the answer the strategy stands behind); None if it never
    produced one.
    """
    # group trials
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in results:
        grouped[(r.get("question_id"), r.get("strategy"))].append(r)

    # representative rows per (q, strategy) for the compiler-oracle axis
    rep_rows: dict[tuple[str, str], list[dict] | None] = {}
    for key, trials in grouped.items():
        rep_rows[key] = _representative_rows(trials)

    rows_out: list[dict] = []
    for (qid, strat), trials in sorted(grouped.items()):
        gold_record = gold.get(qid, {"question_id": qid})

        rep = _representative_trial(trials)
        acc = score_one(rep, gold_record, strategy_for_abstain=strat)

        sql = _first_sql(trials)
        fanout = fanout_of(sql)

        compiler_rows = rep_rows.get((qid, COMPILER_STRATEGY))
        own_rows = rep_rows.get((qid, strat))
        if own_rows is None:
            # CP2 cosmetic: this strategy produced no representative rows (errored
            # / abstained every trial). It didn't "match" the compiler on a row it
            # never emitted — report None (rendered "self"/"—") instead of a
            # misleading True, even for the compiler strategy itself.
            mc = None
        elif strat == COMPILER_STRATEGY:
            mc = True  # the oracle trivially matches itself
        else:
            mc = matches_compiler(own_rows, compiler_rows)

        rows_out.append(
            {
                "question": qid,
                "strategy": strat,
                "acc": acc,
                "fanout": fanout,
                "matches_compiler": mc,
                "distinct_results": distinct_results(trials),
                "abstained": any(bool(t.get("abstained")) for t in trials),
            }
        )
    return rows_out


def _representative_trial(trials: list[dict]) -> dict:
    """First non-errored trial, else first trial (never empty list)."""
    for t in trials:
        if not t.get("errored"):
            return t
    return trials[0]


def _representative_rows(trials: list[dict]) -> list[dict] | None:
    """Rows of the first non-errored, non-abstained trial; else None."""
    for t in trials:
        if not t.get("errored") and not t.get("abstained"):
            return t.get("rows")
    return None


def _first_sql(trials: list[dict]) -> str | None:
    for t in trials:
        sql = t.get("sql")
        if sql:
            return sql
    return None


# --------------------------------------------------------------------------- #
# Emit
# --------------------------------------------------------------------------- #


def to_csv(matrix: list[dict]) -> str:
    import io

    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=_FIELDS)
    w.writeheader()
    for row in matrix:
        w.writerow({k: _csv_cell(row.get(k)) for k in _FIELDS})
    return buf.getvalue()


def _csv_cell(v: Any) -> Any:
    if isinstance(v, bool):
        return "true" if v else "false"
    return v


def to_markdown(matrix: list[dict]) -> str:
    header = "| " + " | ".join(_FIELDS) + " |"
    sep = "| " + " | ".join("---" for _ in _FIELDS) + " |"
    lines = [header, sep]
    for row in matrix:
        cells = [_md_cell(row.get(k)) for k in _FIELDS]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def _md_cell(v: Any) -> str:
    if v is None:
        return "—"  # CP2: no representative rows; matches_compiler is "self"/N/A
    if isinstance(v, bool):
        return "✓" if v else "✗"
    return str(v)


# --------------------------------------------------------------------------- #
# Entrypoint
# --------------------------------------------------------------------------- #

_REPORT_DIR = Path(__file__).resolve().parent.parent / "report"


def main(
    results_json: str | Path,
    *,
    frozen_path: str | Path | None = None,
    report_dir: str | Path | None = None,
) -> list[dict]:
    """Score a results JSON file; write CSV + markdown to report/; return matrix.

    `results_json` : path to the trial-records list (see module docstring).
    `frozen_path`  : optional freeze_gold JSON to inject gold rows for accuracy.
                     Defaults to <results_dir>/frozen_gold.json if present.
    `report_dir`   : override the output dir (default evals/.../report/).
    """
    results_path = Path(results_json)
    results = json.loads(results_path.read_text())

    if frozen_path is None:
        cand = results_path.parent / "frozen_gold.json"
        frozen_path = cand if cand.exists() else None

    gold = load_gold(frozen_path)
    matrix = build_matrix(results, gold)

    out_dir = Path(report_dir) if report_dir else _REPORT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "matrix.csv").write_text(to_csv(matrix))
    (out_dir / "matrix.md").write_text(to_markdown(matrix))
    return matrix


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(
            "usage: python harness/score.py <results.json> [frozen_gold.json]",
            file=sys.stderr,
        )
        raise SystemExit(2)
    frozen = sys.argv[2] if len(sys.argv) > 2 else None
    m = main(sys.argv[1], frozen_path=frozen)
    print(json.dumps(m, indent=2, default=str))
