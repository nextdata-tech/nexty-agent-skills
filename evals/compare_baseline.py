#!/usr/bin/env python3
"""Gate an eval report against a committed baseline of known verdicts.

Agent runs are nondeterministic and some cells fail at baseline for reasons a
given PR did not introduce, so gating on absolute PASS would be both flaky and
unfair. This gates on *regression* instead: a cell fails CI only when it passed
in the baseline and fails now.

Baseline shape (``evals/baselines/<suite>.json``)::

    {
      "_comment": "...",
      "cells": {
        "<skill_set>/<scenario>": {"verdict": "PASS", "note": "..."}
      }
    }

Exit codes: 0 = no regression, 1 = at least one regression, 2 = usage error.

A cell absent from the baseline is reported as ``new`` and never fails the
build — the first run of a new scenario records its result rather than
punishing the PR that adds it. Use ``--update`` to rewrite the baseline from a
report once a result is accepted.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def cell_key(result: dict) -> str:
    return f"{result.get('skill_set')}/{result.get('scenario')}"


def verdict_of(result: dict) -> str:
    """Normalise a report result to PASS / FAIL / ERROR.

    ``ok`` is the *infrastructure* status (did the cell run and get graded at
    all), which is distinct from the grade itself — the judge verdict lives in
    ``verdict.overall_pass``. A cell that never ran is ERROR, not FAIL: it
    carries no signal about the skill, so gating on it would turn an
    infrastructure blip into a content regression.
    """
    if not result.get("ok", False) or result.get("error"):
        return "ERROR"
    verdict = result.get("verdict")
    if not isinstance(verdict, dict) or "overall_pass" not in verdict:
        return "ERROR"
    return "PASS" if verdict["overall_pass"] else "FAIL"


def load_report(path: Path) -> list[dict]:
    data = json.loads(path.read_text())
    results = data.get("results")
    if not isinstance(results, list):
        raise SystemExit(f"{path}: report has no `results` list")
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True, help="Eval report JSON.")
    parser.add_argument("--suite", default="public")
    parser.add_argument(
        "--baseline",
        type=Path,
        default=None,
        help="Baseline file (default: evals/baselines/<suite>.json).",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Rewrite the baseline from this report instead of gating on it.",
    )
    args = parser.parse_args()

    baseline_path = args.baseline or REPO_ROOT / "evals" / "baselines" / f"{args.suite}.json"
    results = load_report(args.report)

    if args.update:
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        existing = (
            json.loads(baseline_path.read_text()) if baseline_path.exists() else {}
        )
        cells = existing.get("cells", {})
        for result in results:
            cells[cell_key(result)] = {"verdict": verdict_of(result)}
        payload = {
            "_comment": (
                "Known-good verdict per <skill_set>/<scenario>. CI fails a PR only "
                "when a cell recorded PASS here now fails. Regenerate with: "
                "python3 evals/compare_baseline.py --report <report>.json --update"
            ),
            "cells": dict(sorted(cells.items())),
        }
        baseline_path.write_text(json.dumps(payload, indent=2) + "\n")
        print(f"baseline updated: {baseline_path} ({len(cells)} cells)")
        return 0

    if not baseline_path.exists():
        print(f"no baseline at {baseline_path}; nothing to compare against")
        return 0

    baseline = json.loads(baseline_path.read_text()).get("cells", {})

    regressions: list[tuple[str, str]] = []
    improvements: list[str] = []
    new_cells: list[tuple[str, str]] = []
    unchanged = 0

    for result in results:
        key = cell_key(result)
        now = verdict_of(result)
        if key not in baseline:
            new_cells.append((key, now))
            continue
        was = baseline[key].get("verdict", "ERROR")
        if was == "PASS" and now != "PASS":
            regressions.append((key, now))
        elif was != "PASS" and now == "PASS":
            improvements.append(key)
        else:
            unchanged += 1

    print(f"baseline: {baseline_path}")
    print(
        f"{len(results)} cell(s): {unchanged} unchanged, {len(improvements)} improved, "
        f"{len(new_cells)} new, {len(regressions)} regressed"
    )
    for key, now in new_cells:
        print(f"  NEW        {key}: {now} (not in baseline — not gated)")
    for key in improvements:
        print(f"  IMPROVED   {key}: FAIL -> PASS (update the baseline to lock this in)")
    for key, now in regressions:
        print(f"  REGRESSION {key}: PASS -> {now}")

    if regressions:
        print(
            "\nA cell that passed on the baseline now fails. If this is an accepted "
            "change, re-run and update evals/baselines/ in this PR.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
