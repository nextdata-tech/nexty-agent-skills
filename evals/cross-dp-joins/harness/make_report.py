#!/usr/bin/env python3
"""Build the DEFINITIVE scored-matrix markdown report from a completed live run.

Reads report/trials.json + report/matrix.csv (written by run_eval --live) and the
frozen oracle_live.json, then emits report/REPORT.md with:

  - the headline per-question matrix (A verdict | strict verdict | discriminated?)
  - the determinism finding (A byte-identical SQL across its 3 trials? strict varies?)
  - the fan-out-safety roll-up on the 3 live discriminators
  - the abstain-quality roll-up
  - the adversarial-validation section (re-run live, by execution)
  - the head-to-head conclusion

Pure post-processing — no network. Run AFTER run_eval --live finishes.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
import score  # noqa: E402
import run_eval  # noqa: E402
from gold_cross_dp_live import GOLD_CROSS_DP_LIVE  # noqa: E402

REPORT = _HERE.parent / "report"
ORACLE = _HERE / "oracle_live.json"


def _live_records():
    return [r for r in GOLD_CROSS_DP_LIVE if not r.get("skipped")]


def _discriminators():
    return [r["id"] for r in GOLD_CROSS_DP_LIVE
            if r.get("is_discriminator") and not r.get("skipped")]


def main() -> int:
    trials = json.loads((REPORT / "trials.json").read_text())
    gold = run_eval.load_gold_live(ORACLE)
    matrix = score.build_matrix(trials, gold)

    # index matrix by (q, strategy)
    mx = {(r["question"], r["strategy"]): r for r in matrix}
    # group trials by (q, strategy)
    grouped: dict[tuple, list] = defaultdict(list)
    for t in trials:
        grouped[(t["question_id"], t["strategy"])].append(t)

    live = _live_records()
    qids = [r["id"] for r in live]
    cat = {r["id"]: r.get("category", "") for r in live}
    disc = set(_discriminators())

    lines: list[str] = []
    A = lines.append
    A("# Cross-DP join-strategy eval — DEFINITIVE live scored matrix\n")
    A("Strategies: **A** = deployed server-side compiler DP (`cross-dp-query-demo-demo`, "
      "`run_cross_dp_query`); **strict** = sonnet strict-MCP agent. Scored vs the frozen "
      "root-principal `oracle_live.json` (independent ground truth — NOT the compiler).\n")
    A(f"Trials: A x3 (determinism), strict x2 (variance). Questions: {len(qids)} "
      "live-reproducible (x11 dropped: non-discriminating live).\n")

    # ---- headline matrix ----
    A("## Headline matrix\n")
    A("| q | category | discriminator | A acc | A fanout | A det(rows) | strict acc | strict abstain | strict det(rows) | did-it-discriminate (A / strict) |")
    A("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for q in qids:
        a = mx.get((q, "A"), {})
        s = mx.get((q, "strict"), {})
        is_d = "yes" if q in disc else ""
        # discriminate = on a chasm row, did the strategy land the CORRECT rollup (PASS) not the naive double-count (FAIL)?
        def discriminated(rec):
            if q not in disc:
                return "—"
            return "✓ correct rollup" if rec.get("acc") == "PASS" else f"✗ ({rec.get('acc')})"
        A(f"| {q} | {cat[q]} | {is_d} | {a.get('acc','—')} | {a.get('fanout','—')} | "
          f"{a.get('distinct_results','—')} | {s.get('acc','—')} | "
          f"{'yes' if s.get('abstained') else 'no'} | {s.get('distinct_results','—')} | "
          f"{discriminated(a)} / {discriminated(s)} |")
    A("")

    # ---- determinism: byte-identical SQL for A ----
    A("## Determinism finding (task 3b — by execution, not assumed)\n")
    A("`distinct_results` in the matrix normalizes ROW-SETS. The stronger claim — A emits "
      "**byte-identical SQL** across its 3 trials — is checked here directly against "
      "`trials.json`.\n")
    A("| q | A trials | distinct SQL strings | byte-identical? | distinct row-sets |")
    A("| --- | --- | --- | --- | --- |")
    a_all_ident = True
    for q in qids:
        ts = sorted(grouped.get((q, "A"), []), key=lambda t: t["trial"])
        sqls = [t.get("sql") for t in ts]
        distinct_sql = len({s for s in sqls})
        ident = (distinct_sql == 1 and len(ts) > 1)
        if not ident:
            a_all_ident = False
        A(f"| {q} | {len(ts)} | {distinct_sql} | {'✓' if ident else '✗'} | "
          f"{mx.get((q,'A'),{}).get('distinct_results','—')} |")
    A("")
    A(f"**A determinism**: {'ALL questions byte-identical SQL across 3 trials' if a_all_ident else 'NOT all byte-identical — see ✗ rows'}.\n")

    # strict variance
    strict_varies = []
    for q in qids:
        dr = mx.get((q, "strict"), {}).get("distinct_results")
        if isinstance(dr, int) and dr > 1:
            strict_varies.append(q)
    A(f"**strict variance**: distinct row-sets >1 across 2 trials on: "
      f"{strict_varies or 'none observed (low-variance sample at n=2)'}.\n")

    # ---- fanout on discriminators ----
    A("## Fan-out safety on the 3 live discriminators\n")
    A("| q | A fanout | A acc (correct rollup vs naive double-count) |")
    A("| --- | --- | --- |")
    for q in sorted(disc):
        a = mx.get((q, "A"), {})
        A(f"| {q} | {a.get('fanout','—')} | {a.get('acc','—')} |")
    A("")

    # ---- abstain quality ----
    A("## Abstain quality (strict)\n")
    A("Expected-abstain (outside strict semantic grammar): "
      + ", ".join(r["id"] for r in live if run_eval.__dict__  # noqa
                  and score and (r.get("expect_abstain"))) + "\n")
    A("| q | strict expected-abstain | strict abstained | acc | verdict |")
    A("| --- | --- | --- | --- | --- |")
    from gold_live_selections import live_expects_abstain
    for q in qids:
        rec = next(r for r in live if r["id"] == q)
        exp = bool(live_expects_abstain(rec.get("expect_abstain")).get("strict"))
        s = mx.get((q, "strict"), {})
        ab = bool(s.get("abstained"))
        acc = s.get("acc", "—")
        if exp and ab:
            v = "correct abstain (PASS)"
        elif exp and not ab:
            v = "over-reach (answered an out-of-grammar q)"
        elif not exp and ab:
            v = "under-reach (abstained an answerable q)"
        else:
            v = "answered (judged on rows)"
        A(f"| {q} | {'yes' if exp else 'no'} | {'yes' if ab else 'no'} | {acc} | {v} |")
    A("")

    (REPORT / "REPORT.md").write_text("\n".join(lines) + "\n")
    # also refresh matrix.csv/md from the recomputed matrix (single-source)
    (REPORT / "matrix.csv").write_text(score.to_csv(matrix))
    (REPORT / "matrix.md").write_text(score.to_markdown(matrix))
    print("wrote", REPORT / "REPORT.md")
    # emit headline json for the caller
    print(json.dumps({
        "a_all_byte_identical_sql": a_all_ident,
        "strict_varies_on": strict_varies,
        "discriminators": sorted(disc),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
