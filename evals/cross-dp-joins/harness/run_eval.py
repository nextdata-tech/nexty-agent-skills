#!/usr/bin/env python3
"""Orchestrator for the cross-DP join-strategy eval (DEFECT 2 — the missing seam).

Wires the agent/compiler drivers to the scorer. Before this module there was NO
glue between ``agent_driver`` / ``strategy_compiler`` and ``score.py``, and their
record shapes were incompatible: ``CaseResult`` (case_id, answer_rows, abstained,
error, sql) vs the scorer's trial record (question_id, rows, abstained, errored,
sql). A crash used to be indistinguishable from a valid-but-wrong answer, so a
crash scored FAIL instead of ERROR.

Per (question x strategy x trial) this module:

  1. invokes the driver for the strategy:
       - "A" / "compiler" -> strategy_compiler.run_compiler_strategy (deterministic).
       - any agent strategy ("B"/"strict"/"compiler"-as-agent) -> agent_driver.run_case.
  2. builds an EXPLICIT trial record:
       {question_id, strategy, trial, rows, sql, abstained, errored}
     with
       errored   = bool(<driver error>)        # a crash scores ERROR, not FAIL
       abstained = (the driver abstained)       # distinct from a parse-miss
       rows      = None on abstain OR error     # never a stale/partial set
  3. loads + freezes the cross-DP gold (gold_cross_dp.GOLD_CROSS_DP via
     freeze_gold.freeze on a RAW Snowflake conn) and remaps each gold record the
     SAME way run.py:238-246 does (id->question_id, expect_abstain list ->
     expects_abstain dict, frozen rows injected).
  4. calls score.build_matrix and writes CSV + markdown under report/.

A ``--dry-run`` mode builds the trial records from a canned results JSON (no live
agents, no Snowflake) so the agent->scorer seam can be exercised offline.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
EVAL_DIR = _HERE.parent                       # evals/cross-dp-joins
REPORT_DIR = EVAL_DIR / "report"

if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import score  # noqa: E402  (harness/score.py — the scorer + gold remap helpers)


# --------------------------------------------------------------------------- #
# Gold freeze + remap
# --------------------------------------------------------------------------- #
# The canonical remap lives in run.py:238-246. Quoted verbatim:
#
#     # Normalize the per-question gold record into the shape score_accuracy()
#     # expects: question_id + frozen rows + an {approach: bool} abstain map.
#     expect_abstain = {a: True for a in q.get("expect_abstain", [])}
#     frozen = gold_frozen.get(q["id"], {})
#     gold_record = {
#         "question_id": q["id"],
#         "equality_mode": q.get("equality_mode", "set"),
#         "rows": frozen.get("rows"),
#         "expects_abstain": expect_abstain,
#     }
#
# score._remap_gold_record already reproduces exactly this remap (id->question_id,
# expect_abstain list -> expects_abstain dict, frozen rows injected), so we REUSE
# it via score.load_gold rather than re-implementing it here — keeping the seam
# single-sourced. We only own the freeze (run freeze_gold.freeze on a raw conn
# and persist its {id: {"rows":...}} JSON), then hand that frozen file to the
# scorer's loader, which performs the run.py:238-246 remap per record.


def freeze_gold_to_file(out_path: Path) -> Path:
    """Freeze GOLD_CROSS_DP against a RAW Snowflake conn; write {id:{rows..}} JSON.

    Mirrors run.py: ``freeze(con)`` is run on the ungoverned base connection while
    it is still on the base schema (no governed masking active), here scoped to
    the cross-DP gold set. Imports the PoC modules from POC_ROOT (the same path
    score.py resolves), so the eval and the PoC never drift on what gold means.
    """
    poc_root = score.POC_ROOT
    if str(poc_root) not in sys.path:
        sys.path.insert(0, str(poc_root))
    from gold.freeze_gold import freeze  # noqa: E402
    from gold.gold_cross_dp import GOLD_CROSS_DP  # noqa: E402
    from harness.snowflake_conn import connect  # noqa: E402

    con = connect()
    try:
        frozen = freeze(con, GOLD_CROSS_DP)
    finally:
        try:
            con.close()
        except Exception:  # noqa: BLE001 — best-effort close
            pass

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(frozen), encoding="utf-8")
    return out_path


# --------------------------------------------------------------------------- #
# CaseResult / compiler-result -> explicit trial record
# --------------------------------------------------------------------------- #


def trial_record_from_case(res: Any, *, question_id: str, strategy: str, trial: int) -> dict:
    """Build the scorer's trial record from an agent_driver.CaseResult.

    Key correctness points (DEFECT 2):
      - errored   = bool(res.error): a crash/timeout/empty-transcript scores ERROR,
                    not the valid-but-wrong FAIL the unwired path mis-scored as.
      - abstained = res.abstained: the agent driver sets this True ONLY for an
                    explicit ``{"abstain": true}`` block (via the ABSTAIN sentinel),
                    so a deliberate abstain is never conflated with a parse-miss.
      - rows      = None on abstain OR error; otherwise res.answer_rows.
    """
    errored = bool(getattr(res, "error", "") or "")
    abstained = bool(getattr(res, "abstained", False))
    rows = None if (errored or abstained) else getattr(res, "answer_rows", None)
    return {
        "question_id": question_id,
        "strategy": strategy,
        "trial": trial,
        "rows": rows,
        "sql": getattr(res, "sql", None),
        "abstained": abstained,
        "errored": errored,
    }


def trial_record_from_compiler(
    result: dict | None, error: str | None, *, question_id: str, strategy: str, trial: int
) -> dict:
    """Build the scorer's trial record from a strategy_compiler result dict.

    ``run_compiler_strategy`` returns {sql, rows, deterministic_hash, fanout_safe}
    on success or raises; the caller passes the raised message as ``error``. The
    compiler never "abstains" — it either compiles+executes or fails loud.
    """
    errored = bool(error)
    rows = None if errored else (result or {}).get("rows")
    sql = None if errored else (result or {}).get("sql")
    return {
        "question_id": question_id,
        "strategy": strategy,
        "trial": trial,
        "rows": rows,
        "sql": sql,
        "abstained": False,
        "errored": errored,
    }


# --------------------------------------------------------------------------- #
# Live trial collection
# --------------------------------------------------------------------------- #


def _run_agent_trial(case: dict, strategy: str, trial: int, run_ts: str, token_file: str | None) -> dict:
    from agent_driver import run_case  # noqa: E402  (lazy: avoids the run_query_loop import on dry-run)

    res = run_case(
        case_id=case["id"],
        strategy=strategy,
        question=case["question"],
        run_ts=run_ts,
        token_file=token_file,
    )
    return trial_record_from_case(
        res, question_id=case["id"], strategy=strategy, trial=trial
    )


def _run_compiler_trial(case: dict, strategy: str, trial: int, token_file: str) -> dict:
    import strategy_compiler  # noqa: E402

    sel = case.get("compiler_selection")
    if not sel:
        # No selection wired for this question -> the compiler can't run it; record
        # an explicit ERROR (rows None) rather than silently skipping the cell.
        return trial_record_from_compiler(
            None,
            "no compiler_selection for question (cannot drive strategy A)",
            question_id=case["id"],
            strategy=strategy,
            trial=trial,
        )
    error: str | None = None
    result: dict | None = None
    try:
        result = strategy_compiler.run_compiler_strategy(
            measures=sel["measures"],
            dimensions=sel["dimensions"],
            dps=sel["dps"],
            token_file=token_file,
        )
    except Exception as exc:  # noqa: BLE001 — a compile/exec failure scores ERROR
        error = str(exc)
    return trial_record_from_compiler(
        result, error, question_id=case["id"], strategy=strategy, trial=trial
    )


def collect_trials_live(
    cases: list[dict],
    strategies: list[str],
    trials: int,
    *,
    compiler_strategy: str,
    token_file: str | None,
) -> list[dict]:
    """Drive every (question x strategy x trial) live; return trial records."""
    run_ts = time.strftime("%Y%m%dT%H%M%S")
    records: list[dict] = []
    for case in cases:
        for strat in strategies:
            for t in range(trials):
                if strat == compiler_strategy:
                    rec = _run_compiler_trial(case, strat, t, token_file or "")
                else:
                    rec = _run_agent_trial(case, strat, t, run_ts, token_file)
                records.append(rec)
    return records


# --------------------------------------------------------------------------- #
# Dry-run: build trial records from a canned results JSON (no live agents)
# --------------------------------------------------------------------------- #


def collect_trials_dry_run(canned_path: Path) -> list[dict]:
    """Build trial records from a canned results JSON so the seam is offline-testable.

    The canned file is a list of raw driver outcomes — each entry may be either an
    agent-shaped dict ({case_id|question_id, strategy, answer_rows, abstained, sql,
    error}) or an already-built trial record ({question_id, strategy, trial, rows,
    sql, abstained, errored}). Agent-shaped entries are passed through
    ``trial_record_from_case`` (via a tiny shim) so the SAME normalization the live
    path uses (errored/abstained/rows None-on-error) is exercised offline.
    """
    raw = json.loads(canned_path.read_text())
    records: list[dict] = []
    for i, entry in enumerate(raw):
        # Trial-record shape carries "rows"; agent-shape carries "answer_rows".
        # Disambiguate on "rows" (NOT "errored" — a hand-written trial record may
        # legitimately omit "errored" and rely on the defensive default below).
        if "rows" in entry and "answer_rows" not in entry:
            # already a trial record — take as-is (fill defaults defensively)
            records.append(
                {
                    "question_id": entry.get("question_id") or entry.get("case_id"),
                    "strategy": entry["strategy"],
                    "trial": entry.get("trial", i),
                    "rows": entry.get("rows"),
                    "sql": entry.get("sql"),
                    "abstained": bool(entry.get("abstained")),
                    "errored": bool(entry.get("errored")),
                }
            )
            continue
        # agent-shaped: normalize through the live seam helper via a shim object.
        shim = _CaseShim(
            answer_rows=entry.get("answer_rows"),
            abstained=bool(entry.get("abstained")),
            sql=entry.get("sql"),
            error=entry.get("error", "") or "",
        )
        qid = entry.get("question_id") or entry.get("case_id")
        records.append(
            trial_record_from_case(
                shim, question_id=qid, strategy=entry["strategy"], trial=entry.get("trial", i)
            )
        )
    return records


class _CaseShim:
    """Minimal stand-in for agent_driver.CaseResult (dry-run only)."""

    def __init__(self, *, answer_rows, abstained, sql, error):
        self.answer_rows = answer_rows
        self.abstained = abstained
        self.sql = sql
        self.error = error


# --------------------------------------------------------------------------- #
# Entrypoint
# --------------------------------------------------------------------------- #


def _load_cases(cases_path: Path | None) -> list[dict]:
    """Load the question set. Defaults to GOLD_CROSS_DP (id+question only)."""
    if cases_path is not None:
        return json.loads(cases_path.read_text())
    poc_root = score.POC_ROOT
    if str(poc_root) not in sys.path:
        sys.path.insert(0, str(poc_root))
    from gold.gold_cross_dp import GOLD_CROSS_DP  # noqa: E402

    return [{"id": r["id"], "question": r["question"]} for r in GOLD_CROSS_DP]


def run_eval(
    *,
    strategies: list[str],
    trials: int,
    compiler_strategy: str,
    cases_path: Path | None,
    dry_run_results: Path | None,
    frozen_path: Path | None,
    report_dir: Path,
    token_file: str | None,
) -> list[dict]:
    """Collect trial records, score them against frozen gold, write the report."""
    report_dir.mkdir(parents=True, exist_ok=True)

    if dry_run_results is not None:
        records = collect_trials_dry_run(dry_run_results)
    else:
        cases = _load_cases(cases_path)
        records = collect_trials_live(
            cases,
            strategies,
            trials,
            compiler_strategy=compiler_strategy,
            token_file=token_file,
        )

    # Persist the trial records next to the report for reproducibility/debugging.
    (report_dir / "trials.json").write_text(json.dumps(records, indent=2, default=str))

    # Freeze gold unless a frozen file was supplied. On dry-run, freezing is
    # skipped when no frozen file exists (no live Snowflake) — the scorer then
    # leaves gold rows absent, so accuracy reads FAIL for answered questions
    # (surfacing the missing oracle), which is the documented score.py behavior.
    if frozen_path is None and dry_run_results is None:
        frozen_path = report_dir / "frozen_gold.json"
        freeze_gold_to_file(frozen_path)

    gold = score.load_gold(frozen_path)
    matrix = score.build_matrix(records, gold)

    (report_dir / "matrix.csv").write_text(score.to_csv(matrix))
    (report_dir / "matrix.md").write_text(score.to_markdown(matrix))
    return matrix


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="run_eval", description=__doc__)
    ap.add_argument(
        "--strategies",
        default="A,B",
        help="comma-separated strategy ids (compiler id + agent ids), default A,B",
    )
    ap.add_argument("--trials", type=int, default=1, help="trials per (question, strategy)")
    ap.add_argument(
        "--compiler-strategy",
        default=score.COMPILER_STRATEGY,
        help="which strategy id is the deterministic compiler (default A)",
    )
    ap.add_argument("--cases", type=Path, default=None, help="questions JSON (default: GOLD_CROSS_DP)")
    ap.add_argument("--token-file", default=None, help="session token file (default: driver discovers)")
    ap.add_argument("--frozen-gold", type=Path, default=None, help="reuse an existing freeze JSON")
    ap.add_argument("--report-dir", type=Path, default=REPORT_DIR)
    ap.add_argument(
        "--dry-run",
        type=Path,
        default=None,
        metavar="CANNED_RESULTS_JSON",
        help="build trial records from a canned results JSON (no live agents/Snowflake)",
    )
    args = ap.parse_args(argv)

    matrix = run_eval(
        strategies=[s for s in args.strategies.split(",") if s],
        trials=args.trials,
        compiler_strategy=args.compiler_strategy,
        cases_path=args.cases,
        dry_run_results=args.dry_run,
        frozen_path=args.frozen_gold,
        report_dir=args.report_dir,
        token_file=args.token_file,
    )
    print(json.dumps(matrix, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
