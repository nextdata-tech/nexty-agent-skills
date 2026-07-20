#!/usr/bin/env python3
"""Map changed files to the eval scenarios that exercise them.

CI runs the eval suite on pull requests, but running all 15 scenarios on every
PR is slow and expensive. Each scenario's ``checks.json`` declares the skills it
exercises under ``skills``; this script inverts that mapping so a PR touching
``src/<skill>/**`` runs only the scenarios that actually cover that skill.

Two changed-path classes select the *whole* suite rather than a subset, because
they can change any scenario's outcome:

- the harness itself (``evals/run.py``, ``evals/eval_backends.py``, ...)
- shared fixtures or skill-set composition (``evals/skill-sets.yaml``)

A skill with no scenario coverage selects nothing. That is a real gap in the
suite, not an error, so it is reported on stderr and the skill is listed in the
JSON output under ``uncovered_skills`` — a PR touching only such a skill gets a
green no-op rather than a misleading pass.

A scenario may set ``ci_skip`` in its ``checks.json`` to a string explaining why
it cannot run unattended (e.g. it needs a live local supervisor). Such scenarios
are never selected automatically — they would fail on the environment rather
than on the skill — but remain runnable via ``workflow_dispatch`` and locally.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Changes to these select every scenario: they alter how runs are executed or
# graded, so no per-skill narrowing is sound.
SUITE_WIDE_PREFIXES = (
    "evals/run.py",
    "evals/eval_backends.py",
    "evals/skill-sets.yaml",
    ".github/workflows/evals.yml",
)


def load_scenarios(suite: str) -> tuple[dict[str, list[str]], dict[str, str]]:
    """Return ``({scenario: [skill, ...]}, {scenario: ci_skip_reason})``."""
    suite_dir = REPO_ROOT / "evals" / suite
    if not suite_dir.is_dir():
        raise SystemExit(f"no such suite directory: {suite_dir}")

    scenarios: dict[str, list[str]] = {}
    skipped: dict[str, str] = {}
    for checks_file in sorted(suite_dir.glob("*/checks.json")):
        name = checks_file.parent.name
        try:
            data = json.loads(checks_file.read_text())
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{checks_file}: invalid JSON: {exc}") from exc
        skills = data.get("skills")
        if not isinstance(skills, list) or not all(isinstance(s, str) for s in skills):
            raise SystemExit(
                f"{checks_file}: missing or malformed `skills` list. Every scenario "
                f"must declare the skills it exercises so CI can select it."
            )
        scenarios[name] = skills
        reason = data.get("ci_skip")
        if isinstance(reason, str) and reason.strip():
            skipped[name] = reason.strip()
    return scenarios, skipped


def select(
    changed: list[str],
    scenarios: dict[str, list[str]],
    skipped: dict[str, str] | None = None,
) -> dict[str, object]:
    """Choose the scenarios a set of changed paths should run."""
    skipped = skipped or {}

    suite_wide = sorted(
        p for p in changed if any(p.startswith(prefix) for prefix in SUITE_WIDE_PREFIXES)
    )
    if suite_wide:
        # Still honour ci_skip here: a harness change does not make a scenario
        # that needs a live supervisor runnable unattended.
        runnable = sorted(s for s in scenarios if s not in skipped)
        return {
            "scenarios": runnable,
            "reason": f"harness change ({suite_wide[0]}) — running the full suite",
            "uncovered_skills": [],
            "skipped": sorted(skipped),
        }

    # A scenario is selected either because one of its skills changed, or
    # because its own scenario directory changed.
    touched_skills = {
        Path(p).parts[1]
        for p in changed
        if p.startswith("src/") and len(Path(p).parts) > 1
    }
    selected: set[str] = set()
    for name, skills in scenarios.items():
        if touched_skills.intersection(skills):
            selected.add(name)
    for p in changed:
        parts = Path(p).parts
        if len(parts) > 2 and parts[0] == "evals" and parts[2] in scenarios:
            selected.add(parts[2])

    # Coverage is measured before ci_skip is applied: a skill covered only by a
    # skipped scenario is genuinely covered by the suite, just not by CI.
    # Reporting it as "uncovered" would misattribute an environment limit to a
    # gap in the scenarios.
    covered = {s for skills in scenarios.values() for s in skills}
    uncovered = sorted(touched_skills - covered)

    skipped_hits = sorted(selected.intersection(skipped))
    selected -= set(skipped)

    if selected:
        reason = f"{len(selected)} scenario(s) cover the changed skills"
    elif skipped_hits:
        reason = (
            f"only CI-skipped scenario(s) cover the changed skills: "
            f"{', '.join(skipped_hits)}"
        )
    elif uncovered:
        reason = f"changed skills have no scenario coverage: {', '.join(uncovered)}"
    else:
        reason = "no changed path maps to a scenario"

    return {
        "scenarios": sorted(selected),
        "reason": reason,
        "uncovered_skills": uncovered,
        "skipped": skipped_hits,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", default="public", help="Suite directory under evals/.")
    parser.add_argument(
        "--changed-file",
        type=Path,
        help="File with one changed path per line (default: read stdin).",
    )
    parser.add_argument(
        "--format",
        choices=("json", "args"),
        default="json",
        help="`json` for the full decision, `args` for repeated --scenario flags.",
    )
    args = parser.parse_args()

    raw = (
        args.changed_file.read_text()
        if args.changed_file
        else sys.stdin.read()
    )
    changed = [line.strip() for line in raw.splitlines() if line.strip()]

    scenarios, skipped = load_scenarios(args.suite)
    result = select(changed, scenarios, skipped)

    if result["uncovered_skills"]:
        print(
            f"warning: no scenario covers {', '.join(result['uncovered_skills'])}",
            file=sys.stderr,
        )
    for name in result.get("skipped", []):
        print(f"note: skipping {name} in CI — {skipped[name]}", file=sys.stderr)

    if args.format == "args":
        print(" ".join(f"--scenario {s}" for s in result["scenarios"]))
    else:
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
