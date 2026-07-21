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

    # A run whose sandbox refused every shell call yields a transcript with no
    # evidence in it, which the judge correctly fails — but the agent never got
    # to attempt the task, so that FAIL says nothing about the skill. Grading it
    # would report an environment fault as a content regression and block
    # unrelated PRs.
    metrics = result.get("metrics") or {}
    if metrics.get("sandbox_blocked"):
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
    parser.add_argument(
        "--write-regressed",
        type=Path,
        default=None,
        help=(
            "Write the regressed scenario names (one per line) to this file. "
            "CI uses it to re-run only the failing cells before failing the build."
        ),
    )
    parser.add_argument(
        "--confirm-with",
        type=Path,
        default=None,
        help=(
            "A second report of a re-run. A cell regresses only if it also failed "
            "there; a cell that passed on retry is reported as flaky-run and does "
            "not fail the build."
        ),
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
            grade = verdict_of(result)
            if grade == "ERROR":
                # A cell that never ran carries no signal about the skill.
                # Recording it would leave an entry implying coverage that does
                # not exist, and it can never be regressed against anyway.
                print(f"  skipping {cell_key(result)}: ERROR (not recorded)")
                continue
            key = cell_key(result)
            prior = cells.get(key) or {}
            if prior.get("flaky"):
                # Never let a routine --update quietly re-arm a cell that was
                # marked unstable on evidence. Overwriting the entry would drop
                # both the marker and the note recording why, so the next run
                # would gate on a verdict already known to be a coin toss.
                print(f"  keeping {key}: marked flaky (verdict not re-recorded)")
                continue
            cells[key] = {"verdict": grade}
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
    flaky_hits: list[tuple[str, str]] = []
    unchanged = 0

    for result in results:
        key = cell_key(result)
        now = verdict_of(result)
        entry = baseline.get(key) or {}
        # A cell marked flaky has been observed returning different verdicts for
        # identical input. It is still run and reported, but it cannot gate: a
        # cell that flips on its own would red PRs at random, which trains
        # everyone to ignore the check.
        #
        # This covers PASS as well as FAIL. A flaky cell that happens to pass is
        # not an improvement to lock in — recording that PASS is precisely what
        # turns a coin toss into a gating cell, so it must not be reported as
        # progress either.
        if entry.get("flaky"):
            flaky_hits.append((key, now))
            continue
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

    # A single agent run is noisy enough that one FAIL is not proof of a
    # regression: false-pass-validation was observed PASS, FAIL, then PASS again
    # across identical inputs. When a retry report is supplied, a cell has to
    # fail twice to count — a cell that passes on retry is reported and dropped.
    retry_rescued: list[str] = []
    if args.confirm_with and regressions:
        retry_verdicts = {
            cell_key(r): verdict_of(r) for r in load_report(args.confirm_with)
        }
        confirmed: list[tuple[str, str]] = []
        for key, now in regressions:
            again = retry_verdicts.get(key)
            if again == "PASS":
                retry_rescued.append(key)
            else:
                confirmed.append((key, again or now))
        regressions = confirmed

    print(f"baseline: {baseline_path}")
    print(
        f"{len(results)} cell(s): {unchanged} unchanged, {len(improvements)} improved, "
        f"{len(new_cells)} new, {len(flaky_hits)} flaky, {len(regressions)} regressed"
    )
    for key in retry_rescued:
        print(f"  FLAKY-RUN  {key}: failed once, passed on retry — not gated")
    for key, now in new_cells:
        print(f"  NEW        {key}: {now} (not in baseline — not gated)")
    for key, now in flaky_hits:
        print(f"  FLAKY      {key}: {now} (known-unstable cell — reported, not gated)")
    for key in improvements:
        print(f"  IMPROVED   {key}: FAIL -> PASS (update the baseline to lock this in)")
    for key, now in regressions:
        print(f"  REGRESSION {key}: PASS -> {now}")

    if args.write_regressed:
        # Scenario name only — the runner takes --scenario, not skill_set/scenario.
        args.write_regressed.write_text(
            "".join(f"{key.split('/', 1)[1]}\n" for key, _ in regressions)
        )

    if regressions:
        confirmed_note = " (confirmed by retry)" if args.confirm_with else ""
        print(
            f"\nA cell that passed on the baseline now fails{confirmed_note}. If this "
            "is an accepted change, re-run and update evals/baselines/ in this PR.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
