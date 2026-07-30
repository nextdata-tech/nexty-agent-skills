#!/usr/bin/env python3
"""Record a benchmark run in evals/benchmarks/ (ledger + compact record).

Whenever a skill change is benchmarked (see "Benchmarking a skill change" in
evals/README.md), this script turns the run.py --report JSON(s) into:

  1. an appended, human-readable entry in evals/benchmarks/ledger.md — the
     committed before/after history of skill quality and efficiency, and
  2. a compact machine-readable record under evals/benchmarks/records/
     (the report minus transcripts/final answers, so it stays diffable and
     small enough to commit).

Usage:

    python3 evals/benchmark_record.py \
        --label "nxd-setup: headless device-flow branch" \
        --report before-v0.7.0=/tmp/eval-before.json \
        --report after-v0.8.0=/tmp/eval-after.json \
        --notes "Adds sandboxed-shell auth branch; scenario nxd-setup-headless-auth is new."

Each --report may be a bare path or ``tag=path``; the tag labels the rows that
came from that report (conventionally ``before-vX.Y.Z`` / ``after-vX.Y.Z``).
Commit the ledger + record changes in the same PR as the skill change they
measure. Stdlib only, same as run.py.
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BENCH_DIR = REPO_ROOT / "evals" / "benchmarks"
LEDGER = BENCH_DIR / "ledger.md"
RECORDS_DIR = BENCH_DIR / "records"
PLUGIN_MANIFEST = REPO_ROOT / ".claude-plugin" / "plugin.json"

LEDGER_HEADER = """\
# Skill benchmark ledger

Append-only history of measured skill changes: for every skill improvement,
the before/after eval verdicts and efficiency metrics (turns, tool calls,
tokens, cost) that justified shipping it. Entries are appended by
`evals/benchmark_record.py` from `run.py --report` JSONs; the matching compact
reports live in `records/`. Newest entries at the bottom.

Reading a row: the judge verdict (checks passed) is the regression gate;
turns/tool_calls/tokens are the efficiency trend. Single-run metric deltas
under ~20% are noise — see "Benchmarking a skill change" in `evals/README.md`.
"""

MISSING = "—"


def parse_report_arg(spec: str) -> tuple[str, Path]:
    """Split ``tag=path`` (or bare ``path``) into (tag, path)."""
    tag, sep, path = spec.partition("=")
    if not sep:
        return "", Path(spec)
    return tag.strip(), Path(path.strip())


def cell_rows(tag: str, report: dict) -> list[dict]:
    rows = []
    for res in report.get("results", []):
        verdict = res.get("verdict", {}) or {}
        metrics = res.get("metrics", {}) or {}
        checks = verdict.get("checks", []) or []
        n_pass = sum(1 for c in checks if c.get("pass"))
        if not res.get("ok"):
            status = "ERROR"
        else:
            status = "PASS" if verdict.get("overall_pass") else "FAIL"
        cost = metrics.get("total_cost_usd")
        rows.append({
            "tag": tag or MISSING,
            "skill_set": res.get("skill_set", MISSING),
            "scenario": res.get("scenario", MISSING),
            "status": status,
            "checks": f"{n_pass}/{len(checks)}" if checks else MISSING,
            "num_turns": metrics.get("num_turns", MISSING),
            "tool_calls": metrics.get("tool_calls", MISSING),
            "output_tokens": metrics.get("output_tokens", MISSING),
            "cost_usd": f"{cost:.2f}" if isinstance(cost, (int, float)) else MISSING,
            # Per-run first: run.py pins a pocket-path scenario to
            # POCKET_AGENT_MODEL regardless of the report-level default, so the
            # report field mislabels those rows. Fall back only when absent.
            "agent_model": metrics.get(
                "agent_model", report.get("agent_model", MISSING)
            ),
        })
    return rows


def compact_report(report: dict) -> dict:
    """Strip transcripts / final answers so the record stays small + committable."""
    slim = {k: v for k, v in report.items() if k != "results"}
    slim["results"] = []
    for res in report.get("results", []):
        r = {k: v for k, v in res.items() if k != "transcript"}
        metrics = dict(r.get("metrics", {}) or {})
        metrics.pop("final_answer", None)
        r["metrics"] = metrics
        slim["results"].append(r)
    return slim


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:60] or "benchmark"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True,
                        help="What changed, e.g. 'nxd-setup: headless device-flow branch'.")
    parser.add_argument("--report", action="append", required=True,
                        dest="reports", metavar="[TAG=]PATH",
                        help="run.py --report JSON; repeatable. Tag rows with "
                             "e.g. before-v0.7.0= / after-v0.8.0=.")
    parser.add_argument("--notes", default="",
                        help="One or two sentences of context for the ledger entry.")
    args = parser.parse_args()

    try:
        plugin_version = json.loads(
            PLUGIN_MANIFEST.read_text(encoding="utf-8")).get("version", MISSING)
    except (OSError, json.JSONDecodeError):
        plugin_version = MISSING

    today = datetime.date.today().isoformat()
    rows: list[dict] = []
    record = {"date": today, "label": args.label, "notes": args.notes,
              "plugin_version": plugin_version, "reports": {}}
    for spec in args.reports:
        tag, path = parse_report_arg(spec)
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"cannot read report {path}: {exc}", file=sys.stderr)
            return 2
        rows.extend(cell_rows(tag, report))
        record["reports"][tag or path.name] = compact_report(report)

    if not rows:
        print("reports contained no result cells", file=sys.stderr)
        return 2

    RECORDS_DIR.mkdir(parents=True, exist_ok=True)
    record_name = f"{today}-{slugify(args.label)}.json"
    record_path = RECORDS_DIR / record_name
    record_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")

    header = ("| run | skill-set | scenario | verdict | checks | turns "
              "| tool_calls | out_tokens | cost_usd | agent |\n"
              "|---|---|---|---|---|---|---|---|---|---|")
    table = "\n".join(
        f"| {r['tag']} | {r['skill_set']} | {r['scenario']} | {r['status']} "
        f"| {r['checks']} | {r['num_turns']} | {r['tool_calls']} "
        f"| {r['output_tokens']} | {r['cost_usd']} | {r['agent_model']} |"
        for r in rows
    )
    entry = [f"\n## {today} — {args.label} (plugin v{plugin_version})\n",
             header, table]
    if args.notes:
        entry.append(f"\nNotes: {args.notes}")
    entry.append(f"\nRecord: [`records/{record_name}`](records/{record_name})\n")

    if not LEDGER.exists():
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        LEDGER.write_text(LEDGER_HEADER, encoding="utf-8")
    with LEDGER.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(entry))

    print(f"appended entry to {LEDGER.relative_to(REPO_ROOT)}")
    print(f"wrote record to {record_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
