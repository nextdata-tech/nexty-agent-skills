#!/usr/bin/env python3
"""Spawn one isolated sonnet agent to answer one cross-DP question via the query skill.

Each call to ``run_case`` launches a single ``claude -p`` process that gets ONLY
the nxd-data-product-query skill (loaded as a plugin via ``--plugin-dir``) plus
the cluster env (CA bundle + session token path). The agent receives one NL
question and the strategy it must use:

  - "strict":   strict MCP-only mode (NEX-621, generator<->validator split).
                Prompt instructs ``--strict`` and cites reference/strict-mode.md.
  - "compiler": the deterministic cross-schema compiler. Prompt instructs the
                scripts/cross_dp_compile.py path.

The full stream-json transcript is archived under
``runs/<ts>/<case_id>-<strategy>.json``. From the transcript the driver extracts
the agent's final answer rows and the list of skill scripts it invoked, and
returns a CaseResult.

The session-bootstrap helpers (build_plugin_dir, cluster_env,
refresh_session_token) are imported VERBATIM from the surveyed
evals/query-loop/run_query_loop.py — not forked here.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parents[1]          # evals/cross-dp-joins
REPO_ROOT = EVAL_DIR.parents[1]                          # repo root
RUNS_DIR = EVAL_DIR / "runs"

# Import the session/plugin bootstrap helpers verbatim from the query-loop runner.
_QUERY_LOOP = REPO_ROOT / "evals" / "query-loop"
sys.path.insert(0, str(_QUERY_LOOP))
from run_query_loop import (  # noqa: E402
    build_plugin_dir,
    cluster_env,
    refresh_session_token,
    AGENT_ALLOWED_TOOLS,
    QUERY_SKILL,
)

# Skill script base path the agent is told to run.
_SCRIPTS = QUERY_SKILL / "scripts"
# Script filenames worth tracking in scripts_called (both strategies' toolchains).
_TRACKED_SCRIPTS = (
    "cross_dp_compile.py",
    "mcp_gateway.py",
    "mcp_call.py",
    "semantic_relations.py",
    "plan_validator.py",
    "connect_port.py",
    "query_sql.py",
    "find_mesh.py",
)

# claude -p default flags. Effort maps to --max-thinking-tokens-ish via
# environment; here we pass model + effort through the documented CLI args.
_DEFAULT_MODEL = "sonnet"
_DEFAULT_EFFORT = "medium"
_DEFAULT_TIMEOUT = 900  # seconds per agent


# Distinct sentinel for an explicit ``{"abstain": true}`` block, so the scorer
# can tell a deliberate abstain apart from a parse-miss (both used to be None).
ABSTAIN = "ABSTAIN"


@dataclass
class CaseResult:
    case_id: str
    strategy: str
    answer_rows: list[dict] | None = None
    abstained: bool = False
    sql: str | None = None
    scripts_called: list[str] = field(default_factory=list)
    transcript_path: str = ""
    error: str = ""


# --- prompt construction -----------------------------------------------------

def _strict_prompt(question: str, token_file: str | None) -> str:
    ref = QUERY_SKILL / "reference" / "strict-mode.md"
    tok = f"\nSession token file: {token_file}\n" if token_file else ""
    return (
        "You are answering ONE cross-data-product question against a live "
        "Nextdata OS mesh, using the nxd-data-product-query skill in STRICT "
        "MCP-only mode.\n\n"
        f"Read {ref} first — it documents the strict-mode contract "
        "(harvest semantic_model -> draft a human-readable PLAN -> "
        "plan_validator.py runs the 5 structural checks, retry cap 3 -> on pass "
        "execute each step via run_semantic_query per DP through mcp_call.py -> "
        "merge client-side).\n\n"
        "Run the strict-mode toolchain with the '--strict' flag. The relevant "
        f"scripts live under {_SCRIPTS} (mcp_gateway.py, semantic_relations.py, "
        "plan_validator.py, mcp_call.py). Do NOT touch any data store directly; "
        "every relation must come from the live semantic_model.\n"
        f"{tok}"
        f"\nQUESTION: {question}\n\n"
        "When done, emit your final answer as a single fenced ```json code block "
        "containing a JSON array of result rows (each row an object of "
        "column -> value). If you must abstain, emit "
        '```json\n{\"abstain\": true, \"reason\": \"...\"}\n``` instead.'
    )


def _compiler_prompt(question: str, token_file: str | None) -> str:
    compiler = _SCRIPTS / "cross_dp_compile.py"
    tok = f"\nSession token file: {token_file}\n" if token_file else ""
    return (
        "You are answering ONE cross-data-product question against a live "
        "Nextdata OS mesh, using the deterministic cross-schema COMPILER.\n\n"
        f"Use {compiler}: harvest each DP's semantic_model, merge into one "
        "SemanticRegistry, compile ONE fan-out-safe cross-schema SQL "
        "(pre-aggregate CTE per fact at its grain + DISTINCT bridge + LEFT JOINs "
        "from the spine), then execute it once against a leased port credential.\n\n"
        "The compiler client needs the worktree nxd_py interpreter (0.41.99-dev5); "
        "the harvest step (mcp_call.py, needs requests) uses plain python3. You may "
        "decouple via cross_dp_compile.py --registry-json: harvest once, compile "
        "from the saved payloads.\n"
        f"{tok}"
        f"\nQUESTION: {question}\n\n"
        "When done, emit your final answer as a single fenced ```json code block "
        "containing a JSON array of result rows (each row an object of "
        "column -> value)."
    )


def _build_prompt(strategy: str, question: str, token_file: str | None) -> str:
    if strategy == "strict":
        return _strict_prompt(question, token_file)
    if strategy == "compiler":
        return _compiler_prompt(question, token_file)
    raise ValueError(f"unknown strategy: {strategy!r} (expected 'strict' | 'compiler')")


# --- transcript parsing ------------------------------------------------------

def _iter_events(raw: str):
    """Yield parsed JSON objects from a stream-json transcript (one per line)."""
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def _final_text(events: list[dict]) -> str:
    """Concatenate the assistant text from the final result/assistant events."""
    # Prefer the terminal `result` event's `result` field (claude -p stream-json).
    for ev in reversed(events):
        if ev.get("type") == "result" and isinstance(ev.get("result"), str):
            return ev["result"]
    # Fallback: last assistant message text blocks.
    for ev in reversed(events):
        if ev.get("type") == "assistant":
            msg = ev.get("message", {})
            parts = [
                b.get("text", "")
                for b in msg.get("content", [])
                if isinstance(b, dict) and b.get("type") == "text"
            ]
            if parts:
                return "\n".join(parts)
    return ""


def _scripts_called(events: list[dict]) -> list[str]:
    """Scan Bash tool_use inputs for tracked skill script filenames."""
    seen: list[str] = []
    for ev in events:
        if ev.get("type") != "assistant":
            continue
        for block in ev.get("message", {}).get("content", []):
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            cmd = json.dumps(block.get("input", {}))
            for script in _TRACKED_SCRIPTS:
                if script in cmd and script not in seen:
                    seen.append(script)
    return seen


def _extract_rows(final_text: str):
    """Pull the last ```json fenced block; return rows list, ABSTAIN, or None.

    Accepts a top-level array of row objects, or {"abstain": true, ...}.
    Returns the distinct ``ABSTAIN`` sentinel for an explicit abstain block, so a
    deliberate abstain is NOT conflated with a parse-miss (which returns None).
    """
    blocks = re.findall(r"```json\s*(.*?)```", final_text, re.DOTALL)
    for chunk in reversed(blocks):
        try:
            obj = json.loads(chunk.strip())
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and obj.get("abstain"):
            return ABSTAIN
        if isinstance(obj, list):
            return obj
        if isinstance(obj, dict) and isinstance(obj.get("rows"), list):
            return obj["rows"]
    return None


# --- agent invocation --------------------------------------------------------

def run_case(
    case_id: str,
    strategy: str,
    question: str,
    *,
    model: str = _DEFAULT_MODEL,
    effort: str = _DEFAULT_EFFORT,
    timeout: int = _DEFAULT_TIMEOUT,
    run_ts: str | None = None,
    token_file: str | None = None,
) -> CaseResult:
    """Spawn one isolated agent for (case_id, strategy, question) and score-free parse."""
    run_ts = run_ts or time.strftime("%Y%m%dT%H%M%S")
    out_dir = RUNS_DIR / run_ts
    out_dir.mkdir(parents=True, exist_ok=True)
    transcript_path = out_dir / f"{case_id}-{strategy}.json"

    if token_file is None:
        token_file = refresh_session_token()

    try:
        prompt = _build_prompt(strategy, question, token_file)
    except ValueError as exc:
        return CaseResult(case_id, strategy, error=str(exc),
                          transcript_path=str(transcript_path))

    env = {**os.environ, **cluster_env()}

    with tempfile.TemporaryDirectory(prefix=f"cdj-{case_id}-{strategy}-") as tmp:
        plugin_dir = build_plugin_dir(Path(tmp))
        cmd = [
            "claude", "-p", prompt,
            "--model", model,
            "--plugin-dir", str(plugin_dir),
            # Load NO user/project/local settings: the agent must be isolated from
            # whatever repo cwd it spawns in (CLAUDE.md + .claude/ would otherwise
            # bleed in). The skill arrives solely via --plugin-dir. `claude --help`:
            #   --setting-sources <sources>  Comma-separated list of setting sources
            #                                to load (user, project, local).
            # Empty string => load none.
            "--setting-sources", "",
            "--allowed-tools", AGENT_ALLOWED_TOOLS,
            "--output-format", "stream-json",
            "--verbose",
        ]
        if effort:
            env["MAX_THINKING_TOKENS"] = {
                "low": "4000", "medium": "10000", "high": "24000",
            }.get(effort, "10000")

        try:
            proc = subprocess.run(
                # cwd=tmp: spawn in the isolated temp dir, NOT the inherited repo
                # cwd, so no sibling CLAUDE.md / .claude settings are picked up.
                cmd, capture_output=True, text=True, timeout=timeout, env=env,
                cwd=tmp,
            )
        except subprocess.TimeoutExpired as exc:
            transcript_path.write_text(
                (exc.stdout or "") if isinstance(exc.stdout, str) else "",
                encoding="utf-8",
            )
            return CaseResult(case_id, strategy, error="timeout",
                              transcript_path=str(transcript_path))

        raw = proc.stdout or ""
        transcript_path.write_text(raw, encoding="utf-8")

        if proc.returncode != 0 and not raw.strip():
            return CaseResult(
                case_id, strategy,
                error=f"claude exit {proc.returncode}: {(proc.stderr or '')[:500]}",
                transcript_path=str(transcript_path),
            )

    events = list(_iter_events(raw))
    final = _final_text(events)
    extracted = _extract_rows(final)
    abstained = extracted is ABSTAIN
    answer_rows = None if abstained else extracted
    return CaseResult(
        case_id=case_id,
        strategy=strategy,
        answer_rows=answer_rows,
        abstained=abstained,
        scripts_called=_scripts_called(events),
        transcript_path=str(transcript_path),
        error="" if events else "empty transcript",
    )


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="agent_driver")
    ap.add_argument("--case-id", required=True)
    ap.add_argument("--strategy", required=True, choices=["strict", "compiler"])
    ap.add_argument("--question", required=True)
    ap.add_argument("--model", default=_DEFAULT_MODEL)
    ap.add_argument("--effort", default=_DEFAULT_EFFORT)
    ap.add_argument("--timeout", type=int, default=_DEFAULT_TIMEOUT)
    args = ap.parse_args()

    res = run_case(
        args.case_id, args.strategy, args.question,
        model=args.model, effort=args.effort, timeout=args.timeout,
    )
    print(json.dumps({
        "case_id": res.case_id,
        "strategy": res.strategy,
        "answer_rows": res.answer_rows,
        "abstained": res.abstained,
        "sql": res.sql,
        "scripts_called": res.scripts_called,
        "transcript_path": res.transcript_path,
        "error": res.error,
    }, indent=2, default=str))
    return 1 if res.error else 0


if __name__ == "__main__":
    raise SystemExit(main())
