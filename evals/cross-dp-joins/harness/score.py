"""CLI / report layer for the cross-DP join-strategy eval.

The pure scoring surface (`score_one`, `fanout_of`, `matches_compiler`,
`distinct_results`, `_remap_gold_record`, `COMPILER_STRATEGY`) is OWNED by
nxd_eval and imported below (`from nxd_eval._ex_core.score import …`). This
module adds only the experiment-specific layer: loading GOLD_CROSS_DP from the
external text-to-SQL PoC, collapsing trial records into a matrix, and emitting
CSV / markdown. That layer needs the PoC checkout (and, upstream, live
Snowflake), so it stays here rather than in the shipping wheel.

Consumes a results JSON (one record per question x strategy x trial) and, per
(question, strategy), computes five axes:

  acc              accuracy vs the frozen gold record (PASS/FAIL/ABSTAIN/ERROR/N/A).
  fanout           fan-out safety of the emitted SQL (FANOUT_SAFE/FANOUT_RISK/N/A).
  matches_compiler whether this strategy's executed rows set-equal the COMPILER
                   strategy's executed rows for the same question (the
                   compiler-as-oracle axis). Strategy A is the oracle and always
                   matches itself; a strategy that emits no rows where the
                   compiler emits some does NOT match.
  distinct_results across the N trials for this (question, strategy), the count of
                   distinct normalized row-sets (1 == deterministic output).
  abstained        whether any trial abstained.

`main(results_json)` reads a results file and writes the matrix to report/ as
both CSV and markdown.

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
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------- #
# Deterministic-EX scoring core
# --------------------------------------------------------------------------- #
# The pure scoring surface is OWNED by nxd_eval (`nxd_eval._ex_core.score`) and
# imported here, so the eval and this experiment can never drift on what "PASS"
# or "FANOUT_SAFE" means. This module keeps only the CLI/report layer
# (gold-loading from the PoC, matrix assembly, CSV/markdown emit, `main`), which
# depends on the external text-to-SQL PoC checkout and live Snowflake and so
# does not belong in the shipping wheel. Requires nxd_eval importable — install
# it (`uv pip install nxd-eval`) or run with `evals/nxd_eval/src` on PYTHONPATH.
from nxd_eval._ex_core.score import COMPILER_STRATEGY
from nxd_eval._ex_core.score import _remap_gold_record
from nxd_eval._ex_core.score import distinct_results
from nxd_eval._ex_core.score import fanout_of
from nxd_eval._ex_core.score import matches_compiler
from nxd_eval._ex_core.score import score_one

# The external text-to-SQL PoC checkout — the source of GOLD_CROSS_DP and the
# freeze helpers this CLI layer loads. Resolved from an env override or the known
# worktree path; only the cross-DP experiment needs it (the shipping wheel does
# not). run_eval.py reads this to put the PoC's gold modules on sys.path.
_POC_ROOT_ENV = os.environ.get("T2SQL_POC_ROOT")
_POC_ROOT_DEFAULT = (
    "/Volumes/PRO-G40/projects/nxd/.claude/worktrees/t2sql-exp/examples/t2sql-poc"
)
POC_ROOT = Path(_POC_ROOT_ENV or _POC_ROOT_DEFAULT)


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
