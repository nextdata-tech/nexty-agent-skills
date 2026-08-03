#!/usr/bin/env python3
"""Reproducible query-skill improvement loop, driven by the ``nxd_eval`` harness.

One command runs the query test suite (``test_suite.json``) against the pharma
mesh and emits a structured report + certification verdict:

    load_suite(test_suite.json) -> run_suite() over the semantic MCP tools
    -> Report (per-bucket accuracy, Wilson CIs, deltas) -> certify()
    -> (human/loop applies skill+suite fixes) -> re-run.

**This used to be a skeleton** whose ``run_case`` / ``mine_issues`` were
``NotImplementedError("Phase 2")``. That phase-2 machinery — drive an agent over
each NL question, record the transcript, score it, extract friction — is exactly
what ``nxd_eval`` provides (react agent + deterministic/judge scorers + Report),
so the loop now delegates to the framework instead of re-implementing it. The
12 cases in ``test_suite.json`` are already in the ``nxd_eval`` ``Case`` shape
(``{id, question, expect, why, gold_note}``); ``load_suite`` reads them as-is.

Two agent-execution models, one suite:

- **In-process (this runner, default):** ``nxd_eval``'s ``react()`` agent drives
  the real ``evals/mcp/semantic_server.py`` over stdio (the teardown-safe
  transport). No cluster deploy; needs the nxd wheel set + Snowflake creds (see
  ``evals/nxd_eval/README.md`` "Live mesh run"). This is what runs today.

- **Live-cluster ``claude -p`` (future, not wired):** the original ambition was
  isolated ``claude -p`` sonnet agents, each getting ONLY the
  ``nxd-query-data-product`` skill (loaded via ``--plugin-dir``) and a cluster
  session token, driving the strict-mode MCP toolchain against a *deployed*
  multi-DP mesh (see ``MESH_DESIGN.md``). The skill-isolation + token/CA plumbing
  for that lives below (``build_plugin_dir`` / ``cluster_env`` /
  ``refresh_session_token``) and is preserved for when the mesh is deployed; it
  is not on the default path.

GRADING HONESTY: the 8 ``answer`` cases carry only a prose ``gold_note``, not
structured gold rows, so ``deterministic_ex`` cannot grade them yet (they need a
``gold`` map with frozen rows — see ``--gold``). The 3 ``clarify`` + 1 ``abstain``
cases ARE graded deterministically on the ``abstain_infeasible`` axis today. The
runner reports this split explicitly rather than silently scoring answer cases as
failures.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
QUERY_SKILL = REPO_ROOT / "src" / "nxd-query-data-product"
LOOP_DIR = Path(__file__).resolve().parent
SUITE_FILE = LOOP_DIR / "test_suite.json"

# nxd_eval lives in its own uv project; add its src to the path so this runner
# can import the framework when invoked under that project's interpreter.
NXD_EVAL_SRC = REPO_ROOT / "evals" / "nxd_eval" / "src"
MCP_DIR = REPO_ROOT / "evals" / "mcp"
MCP_PY = MCP_DIR / ".venv/bin/python"
# Reuse the public pharma scenario's fixtures (the same synthetic mesh the
# adversarial suite runs against).
FIX = REPO_ROOT / "evals" / "public" / "pharma-mesh-query-hard" / "fixtures"


# --- live-cluster claude -p plumbing (preserved; not on the default path) -----
# The query skill, loaded as a plugin so it actually activates (a plugin dir is
# the mechanism that registers a skill for the isolated agent).
AGENT_ALLOWED_TOOLS = "Bash,Read,Glob,Grep,Skill,WebFetch"


def build_plugin_dir(tmp: Path) -> Path:
    """Per-run plugin dir holding ONLY the query skill (isolated agent context).

    For the future live-cluster ``claude -p`` execution model; unused by the
    in-process ``nxd_eval`` path.
    """
    import shutil

    pdir = tmp / "plugin"
    (pdir / ".claude-plugin").mkdir(parents=True, exist_ok=True)
    shutil.copytree(QUERY_SKILL, pdir / "skills" / QUERY_SKILL.name)
    (pdir / ".claude-plugin" / "plugin.json").write_text(
        json.dumps(
            {
                "name": "nxd-query-loop",
                "version": "0.0.1",
                "description": "query skill under test",
                "skills": "./skills/",
            }
        ),
        encoding="utf-8",
    )
    return pdir


def cluster_env() -> dict:
    """Env an isolated live-cluster agent gets: cluster CA + session token path."""
    env = {}
    ca = os.environ.get("NXD_CA_BUNDLE") or os.environ.get("REQUESTS_CA_BUNDLE")
    if ca:
        env["NXD_CA_BUNDLE"] = ca
        env["REQUESTS_CA_BUNDLE"] = ca
        env["SSL_CERT_FILE"] = ca
    return env


def refresh_session_token() -> str | None:
    """Refresh the session token (nxd whoami) and resolve its file via find_mesh.py."""
    subprocess.run(["nxd", "whoami"], capture_output=True, timeout=40)
    p = subprocess.run(
        [sys.executable, str(QUERY_SKILL / "scripts" / "find_mesh.py")],
        capture_output=True,
        text=True,
        timeout=40,
    )
    if p.returncode != 0:
        return None
    try:
        return json.loads(p.stdout).get("token_file")
    except json.JSONDecodeError:
        return None


# --- in-process nxd_eval driver (the default path) ---------------------------


def _server_factory():
    """Real semantic_server over stdio, forwarding SNOWFLAKE_* into the subprocess.

    A stdio child starts with a clean env, so PATH + every SNOWFLAKE_* var are
    forwarded explicitly (the compiler's executor needs the creds). Mirrors the
    ``scenarios.pharma_mesh`` factory.
    """
    from inspect_ai.tool import mcp_server_stdio

    env = {"PATH": os.environ.get("PATH", "")}
    env.update({k: v for k, v in os.environ.items() if k.startswith("SNOWFLAKE_")})
    return mcp_server_stdio(
        command=str(MCP_PY),
        args=["-m", "semantic_server", str(FIX)],
        cwd=str(MCP_DIR),
        env=env,
    )


def _load_gold(path: Path | None):
    """Optional {gold_id: record} map to make ``answer`` cases deterministically
    gradable. None (the default) leaves answer cases ungraded on the EX axis."""
    if path is None:
        return None
    from nxd_eval import gold as gold_fn

    return gold_fn(json.loads(path.read_text(encoding="utf-8")))


def run_loop(args) -> int:
    """Drive the suite through nxd_eval and print a report + gradability note."""
    sys.path.insert(0, str(NXD_EVAL_SRC))
    from nxd_eval import Report, certify, load_suite, run_suite

    gold = _load_gold(Path(args.gold) if args.gold else None)
    suite = load_suite(
        args.suite,
        server_factory=_server_factory,
        gold=gold or {},
    )

    # Honest gradability split: answer cases need structured gold to be scored by
    # deterministic_ex; clarify/abstain cases are graded by abstain_infeasible.
    graded_ids = {c.id for c in suite.cases if c.gold_id and c.gold_id in (gold or {})}
    answer_cases = [c for c in suite.cases if c.expect == "answer"]
    discriminator_cases = [c for c in suite.cases if c.expect != "answer"]
    ungraded_answers = [c for c in answer_cases if c.id not in graded_ids]

    print(f"suite: {suite.name} — {len(suite.cases)} cases", file=sys.stderr)
    print(
        f"  {len(discriminator_cases)} clarify/abstain (graded on abstain_infeasible)",
        file=sys.stderr,
    )
    if ungraded_answers:
        print(
            f"  {len(ungraded_answers)} answer cases WITHOUT gold rows — reported "
            f"but NOT deterministically graded (pass --gold to grade them): "
            f"{', '.join(c.id for c in ungraded_answers)}",
            file=sys.stderr,
        )

    if args.list:
        for c in suite.cases:
            print(f"{c.id}: [{c.expect}] {c.question}")
        return 0

    log = run_suite(
        suite,
        agent_model=args.agent_model,
        grader_model=args.grader_model or None,
        epochs=args.epochs,
        log_dir=str(args.log_dir),
    )
    report = Report.from_path(log)
    print(report.to_markdown())

    # Gate on the abstain axis — the deterministic discriminator these cases
    # exercise (answer cases need gold to gate on deterministic_ex; see above).
    verdict = certify(log, bucket="abstain", report=report)
    tag = (
        "REFUSED (insufficient N)"
        if verdict.refused
        else ("PASS" if verdict.passed else "FAIL")
    )
    print(f"\ncertify[abstain]: {tag} — {verdict.reason}", file=sys.stderr)
    return verdict.exit_code


def main() -> int:
    p = argparse.ArgumentParser(prog="run_query_loop")
    p.add_argument("--suite", default=str(SUITE_FILE))
    p.add_argument("--agent-model", default="openai/gpt-5.4-mini")
    p.add_argument(
        "--grader-model",
        default="openai/gpt-5.4-mini",
        help="model for the advisory judge lane (empty to skip)",
    )
    p.add_argument("--epochs", type=int, default=1)
    p.add_argument(
        "--gold", help="path to a {gold_id: record} JSON to grade answer cases"
    )
    p.add_argument("--log-dir", default=str(LOOP_DIR / "logs"))
    p.add_argument("--list", action="store_true")
    args = p.parse_args()
    return run_loop(args)


if __name__ == "__main__":
    raise SystemExit(main())
