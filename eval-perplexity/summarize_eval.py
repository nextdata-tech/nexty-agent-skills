"""Print a per-case pass/fail summary from an inspect_ai .eval log.

Usage: python summarize_eval.py <path-to-log>.eval
"""

import json
import sys
import zipfile


def load(path):
    with zipfile.ZipFile(path) as z:
        header = json.loads(z.read("header.json"))
        samples = []
        for name in z.namelist():
            if name.startswith("samples/") and name.endswith(".json"):
                samples.append(json.loads(z.read(name)))
    samples.sort(key=lambda s: (s.get("id", ""), s.get("epoch", 0)))
    return header, samples


def verdict_for(sample):
    scores = sample.get("scores", {})
    det = scores.get("deterministic_ex", {})
    v = det.get("metadata", {}).get("verdict")
    if v:
        return v
    abstain = scores.get("abstain_infeasible", {})
    if abstain.get("value") == "C":
        return "PASS"
    if abstain:
        return "FAIL"
    return "UNKNOWN"


def main():
    if len(sys.argv) != 2:
        print("usage: python summarize_eval.py <log>.eval", file=sys.stderr)
        sys.exit(1)

    header, samples = load(sys.argv[1])
    eval_meta = header.get("eval", {})

    print(f"# Eval: {eval_meta.get('task_display_name', 'unknown')}")
    print(f"Status: **{header.get('status', 'unknown')}**")
    print(f"Agent model: `{eval_meta.get('model')}`")
    grader = eval_meta.get("model_roles", {}).get("grader", {}).get("model")
    if grader:
        print(f"Grader model: `{grader}`")
    print()

    passed = 0
    total = len(samples)

    for s in samples:
        sid = s.get("id", "unknown")
        verdict = verdict_for(s)
        passed += verdict == "PASS"
        icon = "PASS" if verdict == "PASS" else verdict

        scores = s.get("scores", {})
        det = scores.get("deterministic_ex", {})
        abstain = scores.get("abstain_infeasible", {})
        slot = scores.get("slot_match", {})
        judge = scores.get("judge", {})

        print(f"## {sid} - {icon}")
        print(f"**Question:** {s.get('input', '').splitlines()[0] if s.get('input') else ''}")
        print()
        print(f"- **Expected (target):** `{s.get('target')}`")
        print(f"- **Actual (from MCP query result):** `{det.get('answer', abstain.get('answer', 'N/A'))}`")
        print(f"- **Deterministic check:** {det.get('metadata', {}).get('verdict', 'N/A')}"
              f" (made_query={det.get('metadata', {}).get('made_query')},"
              f" confidence={det.get('metadata', {}).get('confidence')})")
        if det.get("metadata", {}).get("compiled_sql"):
            print(f"  - Query executed: `{det['metadata']['compiled_sql']}`")
        print(f"- **Abstain check:** feasible={abstain.get('metadata', {}).get('feasible')},"
              f" abstained={abstain.get('metadata', {}).get('abstained')}")
        print(f"- **Slot match F1:** {slot.get('metadata', {}).get('slot_f1', 'N/A')}")
        judge_reason = judge.get("metadata", {}).get("reason")
        print(f"- **Judge:** {judge.get('value', 'N/A')}"
              + (f" ({judge_reason})" if judge_reason else ""))
        print()

    print("---")
    print(f"**Totals: {passed}/{total} cases passed** (deterministic check)")


if __name__ == "__main__":
    main()
