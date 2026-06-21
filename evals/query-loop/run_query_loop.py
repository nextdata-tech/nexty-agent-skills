#!/usr/bin/env python3
"""Reproducible query-skill improvement loop runner.

One command drives the whole loop against the deployed pharma mesh:

    deploy mesh (optional) -> drive isolated test agents over a query test suite
    -> record each agent's full transcript + outcome -> emit a structured
    issue-candidate report -> (human/loop applies skill+suite fixes) -> re-run.

The test agents are **isolated sonnet** sessions: they get ONLY the
nxd-data-product-query skill (loaded as a plugin via --plugin-dir, the mechanism
that actually activates skills — see PR #39) and the local cluster env (the
cluster CA + a session token). They do NOT get the rest of the repo or the
internet beyond the platform docs. Each test case is one NL question the agent
must answer by driving the strict-mode MCP toolchain against the real mesh.

Design mirrors evals/run.py (the skill-pack eval harness) but:
  - target is the REAL deployed mesh on nxd.nxd.local, not a stub;
  - the agent uses the genuine nxd mcp health -> Streamable-HTTP path;
  - every transcript is archived for issue mining;
  - the judge/reviewer extracts friction into the audit log, it doesn't just PASS/FAIL.

Auth + TLS (from the Phase-0 findings, now fixed in the skill):
  - Session token: `python3 src/nxd-data-product-query/scripts/find_mesh.py` -> token_file.
    (NOT a minted PAT — wrong audience, 401s.)
  - TLS: export NXD_CA_BUNDLE / REQUESTS_CA_BUNDLE at the cluster CA
    (shared/charts/nxd/localCerts/nxdCA.crt).
  - mesh discovery: `nxd mcp health` WITHOUT --mesh on a default-mesh config.

Status: SKELETON. Phase 2 fills in agent invocation + issue mining once the
Phase-1 mesh is deployed and Healthy.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
QUERY_SKILL = REPO_ROOT / "src" / "nxd-data-product-query"
LOOP_DIR = Path(__file__).resolve().parent
SUITE_FILE = LOOP_DIR / "test_suite.json"
ARCHIVE_DIR = LOOP_DIR / "runs"

# The query skill, loaded as a plugin so it actually activates (PR #39 lesson).
AGENT_ALLOWED_TOOLS = "Bash,Read,Glob,Grep,Skill,WebFetch"


@dataclass
class TestCase:
    id: str
    question: str
    # Optional expectations the issue-miner uses (not shown to the agent):
    expect: str = ""           # "answer" | "clarify" | "abstain"
    why: str = ""              # rationale (chasm trap / confusable / PII refusal)
    gold_note: str = ""        # what a correct answer looks like


@dataclass
class CaseResult:
    id: str
    ok: bool
    transcript: str = ""
    final_answer: str = ""
    metrics: dict = field(default_factory=dict)
    error: str = ""


def load_suite(path: Path) -> list[TestCase]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [TestCase(**c) for c in raw["cases"]]


def build_plugin_dir(tmp: Path) -> Path:
    """Per-run plugin dir holding ONLY the query skill (isolated agent context)."""
    import shutil

    pdir = tmp / "plugin"
    (pdir / ".claude-plugin").mkdir(parents=True, exist_ok=True)
    shutil.copytree(QUERY_SKILL, pdir / "skills" / QUERY_SKILL.name)
    (pdir / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({
            "name": "nxd-query-loop",
            "version": "0.0.1",
            "description": "query skill under test",
            "skills": "./skills/",
        }),
        encoding="utf-8",
    )
    return pdir


def cluster_env() -> dict:
    """Env the isolated agent gets: cluster CA + session token path.

    The CA bundle path comes from NXD_CA_BUNDLE/REQUESTS_CA_BUNDLE (the operator
    exports it). The session token is refreshed + resolved via the skill's own
    find_mesh.py so the agent uses the sanctioned path.
    """
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
        capture_output=True, text=True, timeout=40,
    )
    if p.returncode != 0:
        return None
    try:
        return json.loads(p.stdout).get("token_file")
    except json.JSONDecodeError:
        return None


# --- agent invocation + issue mining: Phase 2 fills these in -----------------

def run_case(case: TestCase, plugin_dir: Path, env_extra: dict, args) -> CaseResult:
    """Drive one isolated sonnet agent over one NL question against the live mesh.

    TODO (Phase 2): assemble the agent prompt (strict-mode query + the question),
    invoke `claude -p` with --plugin-dir + AGENT_ALLOWED_TOOLS + the cluster env,
    capture the stream-json transcript, archive it under runs/<ts>/<case.id>.json.
    """
    raise NotImplementedError("Phase 2: wire claude -p agent invocation")


def mine_issues(results: list[CaseResult], suite: list[TestCase]) -> list[dict]:
    """Extract friction/issues from transcripts (Phase 2: an xhigh reviewer agent).

    Produces issue candidates -> appended to the audit log: each is
    {case_id, symptom, suspected_cause, skill_or_suite, severity}.
    """
    raise NotImplementedError("Phase 2: wire the xhigh issue-miner")


def main() -> int:
    p = argparse.ArgumentParser(prog="run_query_loop")
    p.add_argument("--suite", default=str(SUITE_FILE))
    p.add_argument("--agent-model", default="sonnet")
    p.add_argument("--agent-effort", default="medium")
    p.add_argument("--concurrency", type=int, default=2)
    p.add_argument("--deploy", action="store_true", help="deploy/refresh the mesh first")
    p.add_argument("--list", action="store_true")
    args = p.parse_args()

    suite = load_suite(Path(args.suite))
    if args.list:
        for c in suite:
            print(f"{c.id}: [{c.expect}] {c.question}")
        return 0

    print("SKELETON — Phase 2 wires agent invocation + issue mining.", file=sys.stderr)
    print(f"Loaded {len(suite)} test cases. Query skill: {QUERY_SKILL}", file=sys.stderr)
    tf = refresh_session_token()
    print(f"session token_file: {tf}", file=sys.stderr)
    print(f"cluster env: {sorted(cluster_env())}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
