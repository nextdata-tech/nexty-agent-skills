#!/usr/bin/env python3
"""Measure per-cell verdict stability across repeated runs of identical input.

The PR gate assumes a cell's verdict says something about the skill. That only
holds if the cell returns the same verdict for the same input. Agent runs and
LLM grading are both nondeterministic, so some cells flip on their own — and a
cell that flips is not evidence about anything, it is a coin toss that reds
pull requests at random.

This reads N reports produced from the *same* commit and inputs, and reports
how often each cell disagreed with itself. Nothing here gates: the output is
evidence for deciding which checks to rewrite and which cells to mark flaky.

Usage::

    python3 evals/flakiness.py --report run-1.json run-2.json ... [--json out.json]

A cell is ``stable`` when every run agreed, ``flaky`` when graded verdicts
disagreed (PASS in one run, FAIL in another). ERROR runs are counted and shown
but do not make a cell flaky: an ERROR is an infrastructure fault, and treating
it as verdict instability would blame the skill for a broken runner.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

# Reuse the report-to-verdict normalisation the gate uses. If the two ever
# disagreed, measured flip rates would describe a grading rule that is not the
# one actually gating pull requests, which is worse than no measurement.
from compare_baseline import cell_key, verdict_of


def analyse(reports: list[Path]) -> dict:
    verdicts: dict[str, list[str]] = defaultdict(list)
    for path in reports:
        data = json.loads(path.read_text())
        results = data.get("results")
        if not isinstance(results, list):
            raise SystemExit(f"{path}: report has no `results` list")
        for result in results:
            verdicts[cell_key(result)].append(verdict_of(result))

    cells = {}
    for key, runs in sorted(verdicts.items()):
        graded = [v for v in runs if v != "ERROR"]
        errors = len(runs) - len(graded)
        passes = graded.count("PASS")
        distinct = set(graded)

        if len(distinct) > 1:
            status = "flaky"
        elif not graded:
            # Every run failed to execute: no verdict was ever produced, so
            # stability is unknown rather than good. Saying "stable" here would
            # advertise confidence built on zero graded observations.
            status = "unknown"
        else:
            status = "stable"

        cells[key] = {
            "status": status,
            "runs": len(runs),
            "graded": len(graded),
            "errors": errors,
            "passes": passes,
            # Share of *graded* runs that passed. 0.0 and 1.0 are consistent;
            # anything between is the flip rate, and the closer to 0.5 the more
            # often this cell will disagree with its own baseline.
            "pass_rate": round(passes / len(graded), 3) if graded else None,
            "verdicts": runs,
        }

    return {
        "reports": [str(p) for p in reports],
        "run_count": len(reports),
        "cells": cells,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report",
        type=Path,
        nargs="+",
        required=True,
        help="Two or more reports from repeated runs of the same input.",
    )
    parser.add_argument(
        "--json",
        type=Path,
        default=None,
        help="Also write the analysis as JSON to this path.",
    )
    args = parser.parse_args()

    if len(args.report) < 2:
        # One run cannot disagree with itself. Accepting a single report would
        # emit a table of "stable" cells that measured nothing at all.
        print("need at least two reports to measure stability", file=sys.stderr)
        return 2

    analysis = analyse(args.report)
    cells = analysis["cells"]
    n = analysis["run_count"]

    flaky = [k for k, c in cells.items() if c["status"] == "flaky"]
    unknown = [k for k, c in cells.items() if c["status"] == "unknown"]

    width = max((len(k) for k in cells), default=10)
    print(f"\n=== Verdict stability over {n} run(s) ===")
    for key, cell in cells.items():
        label = key.ljust(width)
        seq = " ".join(v[0] for v in cell["verdicts"])  # P / F / E
        rate = "" if cell["pass_rate"] is None else f"  pass_rate={cell['pass_rate']}"
        # Agreement is much weaker evidence than disagreement: a cell that
        # flips 1-in-5 looks stable in 2 graded runs about two thirds of the
        # time. Show the graded count so "stable" is read with the confidence
        # it actually earned rather than as a clean bill of health.
        obs = f"  ({cell['graded']} graded)" if cell["status"] == "stable" else ""
        print(f"  {label}  {cell['status'].upper():<7} [{seq}]{rate}{obs}")

    print(
        f"\n{len(cells)} cell(s): {len(cells) - len(flaky) - len(unknown)} stable, "
        f"{len(flaky)} flaky, {len(unknown)} unknown"
    )
    print(
        "\nA disagreement proves instability; agreement only fails to disprove it. "
        f"With {n} run(s), a cell that flips occasionally can still read stable here."
    )
    if flaky:
        print(
            "\nFlaky cells disagreed with themselves on identical input. Prefer "
            "rewriting their checks to assert on outcomes rather than on wording; "
            "mark them flaky in the baseline only as a stopgap."
        )
    if unknown:
        print(
            "\nUnknown cells never produced a graded verdict — that is an "
            "infrastructure fault to fix, not a stability result."
        )

    if args.json:
        args.json.write_text(json.dumps(analysis, indent=2) + "\n")
        print(f"\nAnalysis written to {args.json}")

    # Always 0: this measures, it does not judge. A non-zero exit would make it
    # a gate, and gating on a flakiness probe would block pull requests for the
    # very nondeterminism it exists to quantify.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
