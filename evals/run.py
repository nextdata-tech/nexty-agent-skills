#!/usr/bin/env python3
"""Run Nexty skill evals: drive a headless agent over scenarios and grade it.

For each (skill-set x scenario) pair this runner:

  1. Builds an isolated workspace and installs only the skill-set's skills into
     ``<workspace>/.claude/skills`` (the ``no_skills`` baseline installs none).
  2. Copies the scenario's ``fixtures/`` (mock nxd output, source DP dirs) into
     the workspace so the agent has the same artifacts a real session would.
  3. Runs ``claude -p`` from the workspace with the scenario ``prompt.md`` and
     captures the transcript + run metrics (turns, tokens, cost, duration).
  4. Asks a separate ``claude -p`` judge to grade the transcript against the
     scenario's ``checks.json`` (the structured form of the prose success
     checks). The judge never sees the prompt-under-test's hints; the agent
     never sees ``checks.json``.

The same command runs locally and in CI. Authentication is whatever ``claude``
already resolves (OAuth token / API key) — this script sets none.

Stdlib only; no third-party deps. ``skill-sets.yaml`` is parsed with a tiny
purpose-built reader (the file shape is fixed); per-scenario checks are JSON.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
EVALS_DIR = REPO_ROOT / "evals"
SKILL_SETS_FILE = EVALS_DIR / "skill-sets.yaml"

# Models. The agent under test mirrors what ships to users; the judge is a
# separate, cheaper-but-capable grader. Override on the CLI.
DEFAULT_AGENT_MODEL = "opus"
DEFAULT_JUDGE_MODEL = "opus"

# A scenario run is wall-clock bounded so a stuck agent never hangs CI.
DEFAULT_AGENT_TIMEOUT_S = 1200
DEFAULT_JUDGE_TIMEOUT_S = 300

# Tools the agent under test may use. Read/write/inspect the workspace and run
# the (mocked) shell; no network beyond what the skills themselves drive.
AGENT_ALLOWED_TOOLS = "Bash,Read,Write,Edit,Glob,Grep,TodoWrite"


@dataclass
class SkillSet:
    name: str
    description: str
    skills: list[str]


@dataclass
class RunResult:
    skill_set: str
    scenario: str
    ok: bool                      # the run produced a gradeable transcript
    error: str = ""
    transcript: str = ""
    metrics: dict[str, object] = field(default_factory=dict)
    verdict: dict[str, object] = field(default_factory=dict)


def parse_skill_sets(path: Path) -> dict[str, SkillSet]:
    """Parse evals/skill-sets.yaml.

    Only the exact shape this repo uses is supported:

        skill_sets:
          <name>:
            description: "..."
            skills:
              - "src/..."
            # or: skills: []
    """
    text = path.read_text(encoding="utf-8")
    sets: dict[str, SkillSet] = {}
    name: str | None = None
    desc = ""
    skills: list[str] = []
    in_skills = False

    def flush() -> None:
        nonlocal name, desc, skills
        if name is not None:
            sets[name] = SkillSet(name=name, description=desc, skills=skills)
        name, desc, skills = None, "", []

    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if raw.strip() == "skill_sets:":
            continue
        # Two-space indented key => a skill-set name.
        m = re.match(r"^  ([A-Za-z0-9_]+):\s*$", raw)
        if m:
            flush()
            name = m.group(1)
            in_skills = False
            continue
        m = re.match(r"^    description:\s*(.*)$", raw)
        if m:
            desc = _strip_quotes(m.group(1))
            in_skills = False
            continue
        m = re.match(r"^    skills:\s*(\[\s*\])?\s*$", raw)
        if m:
            in_skills = True
            continue
        m = re.match(r"^      -\s*(.*\S)\s*$", raw)
        if m and in_skills:
            skills.append(_strip_quotes(m.group(1)))
            continue
    flush()
    return sets


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def discover_scenarios(suite: str) -> list[Path]:
    base = EVALS_DIR / suite
    if not base.is_dir():
        return []
    return sorted(p.parent for p in base.glob("*/prompt.md"))


def build_workspace(tmp: Path, skill_set: SkillSet, scenario_dir: Path) -> Path:
    """Create an isolated agent workspace: installed skills + scenario fixtures."""
    ws = tmp / "workspace"
    ws.mkdir(parents=True, exist_ok=True)

    skills_dst = ws / ".claude" / "skills"
    skills_dst.mkdir(parents=True, exist_ok=True)
    for rel in skill_set.skills:
        src = REPO_ROOT / rel
        if not src.is_dir():
            raise FileNotFoundError(f"skill path missing: {rel}")
        shutil.copytree(src, skills_dst / src.name)

    fixtures = scenario_dir / "fixtures"
    if fixtures.is_dir():
        for item in fixtures.iterdir():
            dst = ws / item.name
            if item.is_dir():
                shutil.copytree(item, dst)
            else:
                shutil.copy2(item, dst)
    return ws


def run_agent(ws: Path, prompt: str, model: str, timeout_s: int) -> tuple[bool, str, dict]:
    """Run the headless agent in the workspace. Returns (ok, transcript, metrics)."""
    cmd = [
        "claude", "-p", prompt,
        "--output-format", "json",
        "--model", model,
        # Isolate to the workspace project so user/global skills don't leak in
        # and confound the no_skills baseline.
        "--setting-sources", "project",
        "--allowedTools", AGENT_ALLOWED_TOOLS,
        "--add-dir", str(ws),
    ]
    try:
        proc = subprocess.run(
            cmd, cwd=ws, capture_output=True, text=True, timeout=timeout_s
        )
    except subprocess.TimeoutExpired:
        return False, "", {"error": f"agent timed out after {timeout_s}s"}
    if proc.returncode != 0:
        return False, "", {"error": f"claude exited {proc.returncode}: {proc.stderr[-2000:]}"}
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return False, "", {"error": f"non-JSON agent output: {proc.stdout[-2000:]}"}

    transcript = data.get("result", "")
    usage = data.get("usage", {}) or {}
    metrics = {
        "num_turns": data.get("num_turns"),
        "duration_ms": data.get("duration_ms"),
        "total_cost_usd": data.get("total_cost_usd"),
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "is_error": data.get("is_error"),
    }
    return not data.get("is_error", False), transcript, metrics


JUDGE_SYSTEM = (
    "You are an exacting eval grader for an AI agent. You are given a scenario, "
    "a list of success checks, and the agent's final answer transcript. Grade "
    "each check independently against ONLY what the transcript shows. Do not "
    "give credit for things the agent did not actually say or do. Be skeptical: "
    "a plausible-sounding answer that misses the check fails it."
)


def build_judge_prompt(scenario_dir: Path, checks: dict, transcript: str) -> str:
    prompt_md = (scenario_dir / "prompt.md").read_text(encoding="utf-8")
    check_lines = "\n".join(
        f'  {i + 1}. [id={c["id"]}] {c["check"]}' for i, c in enumerate(checks["checks"])
    )
    return f"""Scenario name: {checks.get("name", scenario_dir.name)}

--- SCENARIO DEFINITION (for your context only) ---
{prompt_md}

--- SUCCESS CHECKS (grade each one) ---
{check_lines}

--- AGENT FINAL ANSWER (transcript to grade) ---
{transcript}

--- INSTRUCTIONS ---
Grade every check as pass or fail with a one-sentence justification grounded in
the transcript. Then give an overall pass only if ALL checks pass.

Respond with ONE JSON object and nothing else, in this exact shape:
{{"checks": [{{"id": "<id>", "pass": true|false, "why": "<one sentence>"}}],
  "overall_pass": true|false, "summary": "<one sentence>"}}"""


def run_judge(scenario_dir: Path, checks: dict, transcript: str, model: str,
              timeout_s: int) -> dict:
    prompt = build_judge_prompt(scenario_dir, checks, transcript)
    cmd = [
        "claude", "-p", prompt,
        "--output-format", "json",
        "--model", model,
        "--setting-sources", "project",
        "--append-system-prompt", JUDGE_SYSTEM,
        "--allowedTools", "",   # judge reasons over given text; no tools
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        return {"error": f"judge timed out after {timeout_s}s", "overall_pass": False}
    if proc.returncode != 0:
        return {"error": f"judge exited {proc.returncode}: {proc.stderr[-1000:]}",
                "overall_pass": False}
    try:
        outer = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"error": "judge wrapper not JSON", "overall_pass": False}
    verdict_text = outer.get("result", "")
    parsed = _extract_json(verdict_text)
    if parsed is None:
        return {"error": f"judge verdict not JSON: {verdict_text[:500]}",
                "overall_pass": False}
    return parsed


def _extract_json(text: str) -> dict | None:
    """Pull the first {...} JSON object out of a model response."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        candidate = fence.group(1)
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        candidate = text[start:end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None


def run_one(skill_set: SkillSet, scenario_dir: Path, args) -> RunResult:
    name = scenario_dir.name
    res = RunResult(skill_set=skill_set.name, scenario=name, ok=False)

    checks_file = scenario_dir / "checks.json"
    if not checks_file.exists():
        res.error = "missing checks.json"
        return res
    checks = json.loads(checks_file.read_text(encoding="utf-8"))
    prompt = (scenario_dir / "prompt.md").read_text(encoding="utf-8")

    with tempfile.TemporaryDirectory(prefix=f"eval-{skill_set.name}-{name}-") as tmp:
        try:
            ws = build_workspace(Path(tmp), skill_set, scenario_dir)
        except FileNotFoundError as exc:
            res.error = str(exc)
            return res

        ok, transcript, metrics = run_agent(
            ws, prompt, args.agent_model, args.agent_timeout
        )
        res.transcript = transcript
        res.metrics = metrics
        if not ok:
            res.error = str(metrics.get("error", "agent run failed"))
            return res

        res.verdict = run_judge(
            scenario_dir, checks, transcript, args.judge_model, args.judge_timeout
        )
        res.ok = True
    return res


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", default="public",
                        help="Scenario suite under evals/ (default: public)")
    parser.add_argument("--skill-set", action="append", dest="skill_sets",
                        help="Skill set(s) to run; repeatable. Default: all.")
    parser.add_argument("--scenario", action="append", dest="scenarios",
                        help="Scenario name(s) to run; repeatable. Default: all.")
    parser.add_argument("--agent-model", default=DEFAULT_AGENT_MODEL)
    parser.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL)
    parser.add_argument("--agent-timeout", type=int, default=DEFAULT_AGENT_TIMEOUT_S)
    parser.add_argument("--judge-timeout", type=int, default=DEFAULT_JUDGE_TIMEOUT_S)
    parser.add_argument("--report", type=Path,
                        help="Write a JSON report to this path.")
    parser.add_argument("--list", action="store_true",
                        help="List skill sets and scenarios, then exit.")
    args = parser.parse_args()

    sets = parse_skill_sets(SKILL_SETS_FILE)
    scenarios = discover_scenarios(args.suite)

    if args.list:
        print("Skill sets:")
        for s in sets.values():
            print(f"  {s.name}: {len(s.skills)} skill(s)")
        print(f"Scenarios ({args.suite}):")
        for sc in scenarios:
            print(f"  {sc.name}")
        return 0

    selected_sets = (
        [sets[n] for n in args.skill_sets] if args.skill_sets else list(sets.values())
    )
    if args.scenarios:
        want = set(args.scenarios)
        scenarios = [sc for sc in scenarios if sc.name in want]

    if not scenarios:
        print("No scenarios selected.", file=sys.stderr)
        return 2

    results: list[RunResult] = []
    started = time.time()
    for skill_set in selected_sets:
        for scenario_dir in scenarios:
            label = f"{skill_set.name} :: {scenario_dir.name}"
            print(f"▶ {label}", file=sys.stderr)
            res = run_one(skill_set, scenario_dir, args)
            results.append(res)
            if not res.ok:
                print(f"  ✗ run failed: {res.error}", file=sys.stderr)
            else:
                passed = res.verdict.get("overall_pass")
                mark = "✓ PASS" if passed else "✗ FAIL"
                print(f"  {mark} — {res.verdict.get('summary', '')}", file=sys.stderr)

    print_summary(results)

    if args.report:
        report = {
            "elapsed_s": round(time.time() - started, 1),
            "agent_model": args.agent_model,
            "judge_model": args.judge_model,
            "results": [
                {
                    "skill_set": r.skill_set,
                    "scenario": r.scenario,
                    "ok": r.ok,
                    "error": r.error,
                    "metrics": r.metrics,
                    "verdict": r.verdict,
                    "transcript": r.transcript,
                }
                for r in results
            ],
        }
        args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Report written to {args.report}", file=sys.stderr)

    # Exit non-zero only on infrastructure failures (a run that could not be
    # graded). A graded FAIL is a signal, not a CI break — eval pass rates are
    # tracked, not gated.
    infra_failures = [r for r in results if not r.ok]
    return 1 if infra_failures else 0


def print_summary(results: list[RunResult]) -> None:
    print("\n=== Eval summary ===", file=sys.stderr)
    width = max((len(f"{r.skill_set}/{r.scenario}") for r in results), default=10)
    for r in results:
        label = f"{r.skill_set}/{r.scenario}".ljust(width)
        if not r.ok:
            print(f"  {label}  ERROR  {r.error}", file=sys.stderr)
            continue
        status = "PASS" if r.verdict.get("overall_pass") else "FAIL"
        n_pass = sum(1 for c in r.verdict.get("checks", []) if c.get("pass"))
        n_total = len(r.verdict.get("checks", []))
        print(f"  {label}  {status}  ({n_pass}/{n_total} checks)", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
