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
import contextlib
import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
EVALS_DIR = REPO_ROOT / "evals"
SKILL_SETS_FILE = EVALS_DIR / "skill-sets.yaml"

# Models. The agent under test runs on sonnet (the cheaper model we measure);
# the judge runs on opus because grading is the call we want to trust most.
# Override either on the CLI.
DEFAULT_AGENT_MODEL = "sonnet"
DEFAULT_JUDGE_MODEL = "opus"

# Reasoning effort. The agent under test mirrors a real session (medium). The
# judge runs at xhigh because grading is the call we most want to trust — a
# stronger judge separates real check failures from transcript-skim misreads,
# and the judge cost is small relative to the agent runs. Override on the CLI.
# Set to "" to leave it to the CLI default.
DEFAULT_AGENT_EFFORT = "medium"
DEFAULT_JUDGE_EFFORT = "xhigh"

# How many (skill-set x scenario) cells run concurrently. Each cell is an
# independent subprocess; the cap bounds local load and API rate.
DEFAULT_CONCURRENCY = 4

# A scenario run is wall-clock bounded so a stuck agent never hangs CI.
DEFAULT_AGENT_TIMEOUT_S = 1200
DEFAULT_JUDGE_TIMEOUT_S = 300

# Tools the agent under test may use. Read/write/inspect the workspace, run the
# (mocked) shell, and fetch the public platform docs. WebFetch is what lets the
# no_skills baseline reach the same public docs a real user has, so the only
# variable between skill-sets is the curated skills themselves.
#
# NOTE: `Skill` MUST be here or installed skills never activate — the agent only
# stumbles onto skill *files* by globbing the workspace and reading some ad hoc,
# so a skill's SKILL.md body (its actual guidance) is never loaded through
# activation. That silently under-measures every skill-set: the lift attributable
# to a skill collapses to "whatever files the agent happened to read." With Skill
# present the agent invokes the matching skill and its body loads as designed.
AGENT_ALLOWED_TOOLS = "Bash,Read,Write,Edit,Glob,Grep,TodoWrite,WebFetch,Skill"

# Semantic-MCP scenarios. A scenario opts in by shipping fixtures/mcp.json:
#   {"tools": ["list_models","describe_model","run_semantic_query"],
#    "dp": "semantic-demo", "rpc_port": "mcp-api"}
# When present, run.py starts evals/mcp/semantic_server.py as a Streamable-HTTP
# MCP server (via uv / EVAL_MCP_PYTHON, so its heavy deps — the real
# nxd.experimental.semantic compiler + Snowflake connector — stay out of the
# stdlib-only runner) and puts a fake `nxd` on the agent's PATH so the
# nxd-data-product-query skill's shipped HTTP toolchain (`nxd mcp health` +
# Streamable-HTTP) discovers + drives the genuine tools, exactly as in
# production. Without this, the agent can only Read the catalog fixture and
# *narrate* tool output (fabricating SQL + rows) — which the xhigh judge
# correctly fails.
MCP_DIR = EVALS_DIR / "mcp"
MCP_SERVER_NAME = "nxd-semantic"
# Fixture filenames that belong to the MCP SERVER, not the agent. Excluded from
# the agent workspace so the agent must obtain the catalog by calling the tools
# (not by reading the file) and never sees the physical mapping / seed secrets.
MCP_SERVER_SIDE_FIXTURES = {
    "catalog.json",       # agent must get this via list_models/describe_model
    "semantic.json",      # physical-mapping secret (columns, grains)
    "seed.sql",           # base-table fixtures
    "mcp.json",           # runner opt-in marker
    "golden_pairs.json",  # expected verdicts — that's the rubric, never show it
}
# MCP tool calls reach Snowflake (lower-env). Each call is slower than a local
# file read, so MCP scenarios get a longer agent timeout.
MCP_AGENT_TIMEOUT_S = 1800

# Public platform docs base. The docs site is a docsify SPA: the human viewer
# lives at https://docs.demo.nextopia.dev/#/<path>, but the *fetchable* markdown
# is served without the hash fragment at <docs-base><path>.md (e.g.
# https://docs.demo.nextopia.dev/tutorials/cli/setup.md). WebFetch must use the
# .md form — a "#/..." fragment is client-side only and returns the empty SPA
# shell. Every run (baseline included) is told this base so the comparison is
# "skills vs. equally-informed agent", not "skills vs. ignorance". Override with
# --docs-base (e.g. a local mesh like http://nxd.nxd.local/docs/ for testing).
DEFAULT_DOCS_BASE = "https://docs.demo.nextopia.dev/"

# The public examples repo (spec.py/transform.py/contracts for real data
# products), vendored as a submodule under the builder skill. Every run gets it
# read-only via --add-dir — it is the public GitHub examples a user starts from.
EXAMPLES_DIR = (
    REPO_ROOT
    / "src" / "nxd-data-product-builder" / "reference" / "nextdata-public-examples"
)


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


def build_workspace(tmp: Path, skill_set: SkillSet, scenario_dir: Path) -> tuple[Path, Path | None]:
    """Create an isolated agent workspace + a per-skill-set plugin dir.

    Returns ``(workspace, plugin_dir)``. ``plugin_dir`` is None for the
    ``no_skills`` baseline (no skills) and otherwise a directory holding a
    minimal `.claude-plugin/plugin.json` + the set's skills, loaded by the agent
    via ``--plugin-dir``.

    Skills MUST be loaded as a plugin: copying skill dirs into the workspace's
    ``.claude/skills/`` does NOT register them — ``claude -p --setting-sources
    project`` ignores project-directory skills, so they never activate and the
    agent only benefits from files it happens to read. ``--plugin-dir`` with a
    `plugin.json` is the mechanism that actually surfaces them as invokable
    skills (`<plugin>:<skill>`)."""
    ws = tmp / "workspace"
    ws.mkdir(parents=True, exist_ok=True)

    plugin_dir: Path | None = None
    if skill_set.skills:
        plugin_dir = tmp / "plugin"
        skills_dst = plugin_dir / "skills"
        skills_dst.mkdir(parents=True, exist_ok=True)
        (plugin_dir / ".claude-plugin").mkdir(parents=True, exist_ok=True)
        for rel in skill_set.skills:
            src = REPO_ROOT / rel
            if not src.is_dir():
                raise FileNotFoundError(f"skill path missing: {rel}")
            shutil.copytree(src, skills_dst / src.name)
        manifest = {
            "name": "nxd-eval-pack",
            "version": "0.0.1",
            "description": f"eval skill-set: {skill_set.name}",
            "skills": "./skills/",
        }
        (plugin_dir / ".claude-plugin" / "plugin.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )

    fixtures = scenario_dir / "fixtures"
    if fixtures.is_dir():
        for item in fixtures.iterdir():
            # Server-side MCP inputs must NOT land in the agent's workspace. The
            # catalog is the data the agent is supposed to obtain by CALLING the
            # tools — leaving catalog.json in the workspace lets the agent read it
            # directly and narrate tool output instead of invoking the tools
            # (exactly the fabrication the MCP server exists to prevent). seed.sql
            # / semantic.json are physical-mapping secrets the agent must never
            # see; mcp.json is a runner marker.
            if item.name in MCP_SERVER_SIDE_FIXTURES:
                continue
            dst = ws / item.name
            if item.is_dir():
                shutil.copytree(item, dst)
            else:
                shutil.copy2(item, dst)
    return ws, plugin_dir


def agent_task_from_prompt(prompt_md: str) -> str:
    """Extract only the agent-facing task from a scenario prompt.md.

    Scenario prompt.md files are authored as specs: an intro that may state the
    root cause, a "Task for the agent:" block, then "Required artifacts ..." and
    "Success checks:" sections that describe setup and the grading rubric. Only
    the task is safe to show the agent — the intro and success checks would hand
    it the answer and the rubric (the judge sees the full spec separately).

    Strategy: take the text under "Task for the agent:" up to the next section
    header. If there's no such header (build-brief style prompts), fall back to
    everything before "Success checks:" — which still strips the rubric.
    """
    lines = prompt_md.splitlines()
    section_re = re.compile(
        r"^\s*(Required artifacts|Success checks|Constraints|Expected final)",
        re.IGNORECASE,
    )
    task_start = None
    for i, line in enumerate(lines):
        if re.match(r"^\s*Task for the agent:\s*$", line, re.IGNORECASE):
            task_start = i + 1
            break

    if task_start is not None:
        body = []
        for line in lines[task_start:]:
            if section_re.match(line):
                break
            body.append(line)
        task = "\n".join(body).strip()
        if task:
            return task

    # Fallback: drop everything from "Success checks:" onward.
    cut = len(lines)
    for i, line in enumerate(lines):
        if re.match(r"^\s*Success checks:\s*$", line, re.IGNORECASE):
            cut = i
            break
    return "\n".join(lines[:cut]).strip()


def build_agent_prompt(scenario_prompt: str, docs_base: str, has_examples: bool) -> str:
    """Prepend the shared context every skill-set gets (docs + examples)."""
    lines = [
        "You are working on a Nextdata OS (nxd) data-product task.",
        "",
        "Available context (the same for every run):",
        f"- Public platform docs: fetch markdown pages with WebFetch at "
        f"{docs_base}<path>.md (e.g. {docs_base}dp_development/debugging.md). "
        f"Start from the index {docs_base}_sidebar.md to find the right page. "
        "Use the .md URLs directly — the docs viewer's #/ links are not fetchable.",
        "- Your workspace contains the files for this task. Inspect them first: "
        "any `nxd-*.txt` files are pre-captured output of nxd CLI commands that "
        "were already run for you (read them — do not try to run `nxd`, it is not "
        "installed), and any `data_product/` directory is the product source.",
    ]
    if has_examples:
        lines.append(
            "- A read-only copy of the public example data products is mounted "
            "alongside your workspace (a `nextdata-public-examples` directory with "
            "real spec.py / models.py / transform.py / contracts). Read it for "
            "working patterns."
        )
    lines += ["", "--- TASK ---", scenario_prompt]
    return "\n".join(lines)


# Cap each tool-result block fed to the judge so a huge file read doesn't blow
# up the judge prompt; the head is enough to see what the agent inspected.
TOOL_RESULT_HEAD_CHARS = 1500


def _trace_from_stream(stdout: str) -> tuple[str, dict]:
    """Parse stream-json lines into a readable trace + the final metrics.

    The trace interleaves the agent's reasoning text, each tool call (name +
    input), and a truncated tool result — so the judge can see *what the agent
    inspected*, not just its final answer. Process checks ("read the logs before
    concluding") are only gradeable from this.
    """
    parts: list[str] = []
    final_answer = ""
    metrics: dict = {"is_error": False}
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        typ = d.get("type")
        if typ == "assistant":
            for block in d.get("message", {}).get("content", []):
                if block.get("type") == "text" and block.get("text", "").strip():
                    parts.append(f"[assistant] {block['text'].strip()}")
                elif block.get("type") == "tool_use":
                    inp = json.dumps(block.get("input", {}), ensure_ascii=False)
                    parts.append(f"[tool_use:{block.get('name')}] {inp[:600]}")
        elif typ == "user":
            for block in d.get("message", {}).get("content", []):
                if block.get("type") == "tool_result":
                    content = block.get("content", "")
                    if isinstance(content, list):
                        content = " ".join(
                            c.get("text", "") for c in content if isinstance(c, dict)
                        )
                    content = str(content)[:TOOL_RESULT_HEAD_CHARS]
                    parts.append(f"[tool_result] {content}")
        elif typ == "result":
            final_answer = d.get("result", "")
            usage = d.get("usage", {}) or {}
            metrics = {
                "num_turns": d.get("num_turns"),
                "duration_ms": d.get("duration_ms"),
                "total_cost_usd": d.get("total_cost_usd"),
                "input_tokens": usage.get("input_tokens"),
                "output_tokens": usage.get("output_tokens"),
                "is_error": d.get("is_error", False),
            }
    trace = "\n".join(parts)
    return trace, {"final_answer": final_answer, **metrics}


def scenario_needs_mcp(scenario_dir: Path) -> dict | None:
    """Return the parsed fixtures/mcp.json if this scenario opts into MCP, else None."""
    marker = scenario_dir / "fixtures" / "mcp.json"
    if not marker.exists():
        return None
    return json.loads(marker.read_text(encoding="utf-8"))


def _free_port() -> int:
    import socket

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _mcp_python() -> tuple[str, list[str]]:
    """Interpreter that launches the HTTP server. Needs the GENUINE
    nxd.experimental.semantic compiler (not on a public index) + Snowflake.

      * EVAL_MCP_PYTHON=/path/to/python — an interpreter with the matched nxd
        wheel set + mcp + snowflake-connector already installed.
      * default: `uv run --project evals/mcp python` — requires the matched
        wheels to have been installed into evals/mcp/.venv first (see README).
    """
    override = os.environ.get("EVAL_MCP_PYTHON", "").strip()
    if override:
        return override, []
    return "uv", ["run", "--project", str(MCP_DIR), "python"]


@contextlib.contextmanager
def semantic_http_server(scenario_dir: Path, mcp_spec: dict):
    """Start the semantic DP as a Streamable-HTTP MCP server for the duration of
    a scenario, and yield the (endpoint_url, env_overrides) the agent needs.

    This mirrors production: the nxd-data-product-query skill discovers DP MCP
    endpoints by shelling out to ``nxd mcp health`` and then opens an HTTP MCP
    session. We start the real server, then point a fake ``nxd`` (on the agent's
    PATH) at it via EVAL_MCP_ENDPOINT — so the skill's shipped toolchain drives
    the genuine tools unchanged. Server + fake-nxd shim are torn down on exit.
    """
    fixtures_dir = str((scenario_dir / "fixtures").resolve())
    dp = mcp_spec.get("dp", "semantic-demo")
    rpc_port = mcp_spec.get("rpc_port", "mcp-api")
    tool_count = len(mcp_spec.get("tools", []))
    port = _free_port()
    endpoint = f"http://127.0.0.1:{port}/{dp}/rpcs/{rpc_port}/mcp/"

    command, base_args = _mcp_python()
    cmd = [command, *base_args, "-m", "semantic_server", fixtures_dir,
           "--http", "--host", "127.0.0.1", "--port", str(port),
           "--dp", dp, "--rpc-port", rpc_port]
    proc = subprocess.Popen(
        cmd, cwd=str(MCP_DIR), env=dict(os.environ),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_http(endpoint, proc, timeout_s=60)
        env = {
            "EVAL_MCP_ENDPOINT": endpoint,
            "EVAL_MCP_DP": dp,
            "EVAL_MCP_TOOL_COUNT": str(tool_count),
        }
        yield endpoint, env
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def _wait_for_http(endpoint: str, proc: subprocess.Popen, timeout_s: int) -> None:
    """Poll the MCP endpoint until it answers (or the server dies / times out)."""
    import urllib.error
    import urllib.request

    deadline = time.time() + timeout_s
    # An MCP initialize POST; we only care that the socket accepts + the app
    # responds (any HTTP status, incl. 307/400), not the body.
    body = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                   "clientInfo": {"name": "probe", "version": "1"}},
    }).encode()
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"MCP server exited early (code {proc.returncode})")
        req = urllib.request.Request(
            endpoint, data=body, method="POST",
            headers={"Content-Type": "application/json",
                     "Accept": "application/json, text/event-stream"},
        )
        try:
            urllib.request.urlopen(req, timeout=3)
            return
        except urllib.error.HTTPError:
            return  # app responded (e.g. 307/400) — it's up
        except (urllib.error.URLError, ConnectionError, OSError):
            time.sleep(0.5)
    raise TimeoutError(f"MCP server did not come up within {timeout_s}s at {endpoint}")


def _write_fake_nxd(bin_dir: Path) -> None:
    """Write a `nxd` shim onto a dir that gets prepended to the agent's PATH.

    The shim execs fake_nxd.py with the EVAL_MCP_* env the agent inherits, so
    `nxd mcp health` returns the running server's endpoint. Only the subcommands
    the query skill calls are stubbed (see fake_nxd.py)."""
    command, base_args = _mcp_python()
    interp = " ".join([command, *base_args])
    shim = bin_dir / "nxd"
    shim.write_text(
        "#!/usr/bin/env bash\n"
        f'exec {interp} "{MCP_DIR / "fake_nxd.py"}" "$@"\n',
        encoding="utf-8",
    )
    shim.chmod(0o755)


def run_agent(ws: Path, prompt: str, model: str, timeout_s: int,
              extra_dirs: list[Path] | None = None,
              effort: str = "",
              env_overrides: dict | None = None,
              path_prepend: Path | None = None,
              plugin_dir: Path | None = None) -> tuple[bool, str, dict]:
    """Run the headless agent. Returns (ok, trace, metrics).

    The trace (full tool-call transcript) is what the judge grades; the final
    answer and run metrics ride along in ``metrics`` (metrics["final_answer"]).

    For MCP scenarios the agent reaches the semantic tools through the query
    skill's shipped HTTP toolchain (``nxd mcp health`` + Streamable-HTTP), so no
    --mcp-config is needed: ``env_overrides`` carries EVAL_MCP_ENDPOINT and
    ``path_prepend`` puts the fake ``nxd`` on PATH. The agent uses Bash (already
    allowed) to run the skill's scripts.
    """
    cmd = [
        "claude", "-p", prompt,
        # stream-json + verbose emits per-step events so we can reconstruct the
        # tool-call trace, not just the final answer.
        "--output-format", "stream-json", "--verbose",
        "--model", model,
        # Isolate to the workspace project so user/global skills don't leak in
        # and confound the no_skills baseline.
        "--setting-sources", "project",
        "--allowedTools", AGENT_ALLOWED_TOOLS,
        "--add-dir", str(ws),
    ]
    # Load the skill-set as a plugin so its skills actually activate (invokable as
    # nxd-eval-pack:<skill>). Copying into .claude/skills/ does NOT register them.
    # no_skills baseline passes plugin_dir=None → genuinely zero curated skills.
    if plugin_dir is not None:
        cmd += ["--plugin-dir", str(plugin_dir)]
    if effort:
        cmd += ["--effort", effort]
    for d in extra_dirs or []:
        cmd += ["--add-dir", str(d)]

    env = dict(os.environ)
    if env_overrides:
        env.update(env_overrides)
    if path_prepend is not None:
        env["PATH"] = f"{path_prepend}{os.pathsep}{env.get('PATH', '')}"
    try:
        proc = subprocess.run(
            cmd, cwd=ws, capture_output=True, text=True, timeout=timeout_s,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return False, "", {"error": f"agent timed out after {timeout_s}s"}
    if proc.returncode != 0:
        return False, "", {"error": f"claude exited {proc.returncode}: {proc.stderr[-2000:]}"}

    trace, metrics = _trace_from_stream(proc.stdout)
    if not trace and not metrics.get("final_answer"):
        return False, "", {"error": f"empty stream output: {proc.stdout[-2000:]}"}
    return not metrics.get("is_error", False), trace, metrics


JUDGE_SYSTEM = (
    "You are an exacting eval grader for an AI agent. You are given a scenario, "
    "a list of success checks, and the agent's final answer transcript. Grade "
    "each check independently against ONLY what the transcript shows. Do not "
    "give credit for things the agent did not actually say or do. Be skeptical: "
    "a plausible-sounding answer that misses the check fails it."
)


def build_judge_prompt(scenario_dir: Path, checks: dict, trace: str,
                       final_answer: str) -> str:
    prompt_md = (scenario_dir / "prompt.md").read_text(encoding="utf-8")
    check_lines = "\n".join(
        f'  {i + 1}. [id={c["id"]}] {c["check"]}' for i, c in enumerate(checks["checks"])
    )
    return f"""Scenario name: {checks.get("name", scenario_dir.name)}

--- SCENARIO DEFINITION (for your context only) ---
{prompt_md}

--- SUCCESS CHECKS (grade each one) ---
{check_lines}

--- AGENT RUN TRACE (what the agent actually did: reasoning, tool calls, and
    truncated tool results — use this to grade process checks like "read the
    logs before concluding") ---
{trace}

--- AGENT FINAL ANSWER ---
{final_answer}

--- INSTRUCTIONS ---
Grade every check as pass or fail with a one-sentence justification grounded in
the trace and final answer. A "did the agent inspect X" check passes only if the
trace shows the corresponding tool call/result. Give an overall pass only if ALL
checks pass.

Respond with ONE JSON object and nothing else, in this exact shape:
{{"checks": [{{"id": "<id>", "pass": true|false, "why": "<one sentence>"}}],
  "overall_pass": true|false, "summary": "<one sentence>"}}"""


def run_judge(scenario_dir: Path, checks: dict, trace: str, final_answer: str,
              model: str, timeout_s: int, effort: str = "") -> dict:
    prompt = build_judge_prompt(scenario_dir, checks, trace, final_answer)
    cmd = [
        "claude", "-p", prompt,
        "--output-format", "json",
        "--model", model,
        "--setting-sources", "project",
        "--append-system-prompt", JUDGE_SYSTEM,
        "--allowedTools", "",   # judge reasons over given text; no tools
    ]
    if effort:
        cmd += ["--effort", effort]
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


def _fixtures_fingerprint(scenario_dir: Path) -> str:
    """Hash the scenario fixtures so a fixture edit invalidates the cache."""
    h = hashlib.sha256()
    fixtures = scenario_dir / "fixtures"
    if fixtures.is_dir():
        for f in sorted(fixtures.rglob("*")):
            if f.is_file():
                h.update(f.relative_to(scenario_dir).as_posix().encode())
                h.update(f.read_bytes())
    return h.hexdigest()[:16]


def _agent_cache_key(skill_set: SkillSet, scenario_dir: Path, prompt: str,
                     model: str, effort: str) -> str:
    """Cache key for an agent run. Independent of the judge / checks.json, so
    iterating on grading reuses the expensive agent transcript."""
    h = hashlib.sha256()
    for part in (
        skill_set.name,
        ",".join(sorted(skill_set.skills)),
        scenario_dir.name,
        prompt,
        model,
        effort,
        _fixtures_fingerprint(scenario_dir),
    ):
        h.update(part.encode())
        h.update(b"\x00")
    return h.hexdigest()


def run_one(skill_set: SkillSet, scenario_dir: Path, args) -> RunResult:
    name = scenario_dir.name
    res = RunResult(skill_set=skill_set.name, scenario=name, ok=False)

    checks_file = scenario_dir / "checks.json"
    if not checks_file.exists():
        res.error = "missing checks.json"
        return res
    checks = json.loads(checks_file.read_text(encoding="utf-8"))
    prompt_md = (scenario_dir / "prompt.md").read_text(encoding="utf-8")
    # Only the task section is agent-facing; the intro + success checks would
    # leak the answer and the rubric. The judge still sees the full prompt.md.
    agent_task = agent_task_from_prompt(prompt_md)

    extra_dirs = [EXAMPLES_DIR] if EXAMPLES_DIR.is_dir() else []
    prompt = build_agent_prompt(agent_task, args.docs_base, bool(extra_dirs))

    # Agent step (cacheable). The agent run is the slow/expensive part; cache it
    # keyed on everything that affects the transcript so judge-only iteration is
    # cheap. The judge is never cached (it's cheap and the rubric changes often).
    cache_dir = Path(args.cache_dir) if args.cache_dir else None
    cache_file = None
    if cache_dir:
        key = _agent_cache_key(
            skill_set, scenario_dir, prompt, args.agent_model, args.agent_effort
        )
        cache_file = cache_dir / f"agent-{key}.json"

    cached = None
    if cache_file and cache_file.exists():
        try:
            loaded = json.loads(cache_file.read_text(encoding="utf-8"))
            if "trace" in loaded and "metrics" in loaded:
                cached = loaded
        except json.JSONDecodeError:
            cached = None

    if cached:
        trace = cached["trace"]
        metrics = {**cached["metrics"], "cached": True}
        ok = True
    else:
        # MCP scenarios run a live Streamable-HTTP semantic server + a fake `nxd`
        # on PATH so the query skill's shipped HTTP toolchain drives the real
        # tools. Tool calls reach Snowflake, so allow a longer timeout.
        mcp_spec = scenario_needs_mcp(scenario_dir)
        agent_timeout = (
            max(args.agent_timeout, MCP_AGENT_TIMEOUT_S)
            if mcp_spec is not None
            else args.agent_timeout
        )
        with tempfile.TemporaryDirectory(prefix=f"eval-{skill_set.name}-{name}-") as tmp:
            try:
                ws, plugin_dir = build_workspace(Path(tmp), skill_set, scenario_dir)
            except FileNotFoundError as exc:
                res.error = str(exc)
                return res

            if mcp_spec is not None:
                bin_dir = Path(tmp) / "bin"
                bin_dir.mkdir(parents=True, exist_ok=True)
                _write_fake_nxd(bin_dir)
                try:
                    with semantic_http_server(scenario_dir, mcp_spec) as (_ep, env_over):
                        ok, trace, metrics = run_agent(
                            ws, prompt, args.agent_model, agent_timeout,
                            extra_dirs=extra_dirs, effort=args.agent_effort,
                            env_overrides=env_over, path_prepend=bin_dir,
                            plugin_dir=plugin_dir,
                        )
                except (RuntimeError, TimeoutError) as exc:
                    res.error = f"MCP server setup failed: {exc}"
                    return res
            else:
                ok, trace, metrics = run_agent(
                    ws, prompt, args.agent_model, agent_timeout,
                    extra_dirs=extra_dirs, effort=args.agent_effort,
                    plugin_dir=plugin_dir,
                )
        if ok and cache_file:
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(
                json.dumps({"trace": trace, "metrics": metrics}),
                encoding="utf-8",
            )

    res.transcript = trace
    res.metrics = metrics
    if not ok:
        res.error = str(metrics.get("error", "agent run failed"))
        return res

    final_answer = metrics.get("final_answer", "")
    res.verdict = run_judge(
        scenario_dir, checks, trace, final_answer,
        args.judge_model, args.judge_timeout, effort=args.judge_effort,
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
    parser.add_argument("--agent-effort", default=DEFAULT_AGENT_EFFORT,
                        help="Reasoning effort for the agent (low|medium|high|"
                             "xhigh|max; '' = CLI default).")
    parser.add_argument("--judge-effort", default=DEFAULT_JUDGE_EFFORT,
                        help="Reasoning effort for the judge.")
    parser.add_argument("--agent-timeout", type=int, default=DEFAULT_AGENT_TIMEOUT_S)
    parser.add_argument("--judge-timeout", type=int, default=DEFAULT_JUDGE_TIMEOUT_S)
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY,
                        help="How many scenario cells run at once (default 4).")
    parser.add_argument("--cache-dir", default=None,
                        help="Cache agent transcripts here; reuse on re-run when "
                             "skills/task/fixtures/model are unchanged.")
    parser.add_argument("--docs-base", default=DEFAULT_DOCS_BASE,
                        help="Public platform docs base URL given to every run.")
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

    if args.skill_sets:
        unknown = [n for n in args.skill_sets if n not in sets]
        if unknown:
            print(
                f"Unknown skill set(s): {', '.join(unknown)}. "
                f"Known sets: {', '.join(sets)}.",
                file=sys.stderr,
            )
            return 2
        selected_sets = [sets[n] for n in args.skill_sets]
    else:
        selected_sets = list(sets.values())
    if args.scenarios:
        want = set(args.scenarios)
        scenarios = [sc for sc in scenarios if sc.name in want]

    if not scenarios:
        print("No scenarios selected.", file=sys.stderr)
        return 2

    cells = [(ss, sc) for ss in selected_sets for sc in scenarios]
    total = len(cells)
    started = time.time()
    print_lock = threading.Lock()
    done = [0]

    def emit(res: RunResult) -> None:
        with print_lock:
            done[0] += 1
            label = f"{res.skill_set} :: {res.scenario}"
            if not res.ok:
                line = f"✗ ERROR — {res.error}"
            else:
                passed = res.verdict.get("overall_pass")
                cached = " (cached)" if res.metrics.get("cached") else ""
                mark = "✓ PASS" if passed else "✗ FAIL"
                line = f"{mark}{cached} — {res.verdict.get('summary', '')}"
            print(f"[{done[0]}/{total}] {label}\n    {line}", file=sys.stderr, flush=True)

    results: list[RunResult] = []
    workers = max(1, min(args.concurrency, total))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(run_one, ss, sc, args): (ss, sc) for ss, sc in cells
        }
        for fut in as_completed(futures):
            ss, sc = futures[fut]
            try:
                res = fut.result()
            except Exception as exc:  # never let one cell kill the run
                res = RunResult(skill_set=ss.name, scenario=sc.name, ok=False,
                                error=f"unexpected: {exc}")
            results.append(res)
            emit(res)

    # Deterministic order in the summary/report regardless of completion order.
    order = {(ss.name, sc.name): i for i, (ss, sc) in enumerate(cells)}
    results.sort(key=lambda r: order.get((r.skill_set, r.scenario), 0))

    print_summary(results)

    if args.report:
        report = {
            "elapsed_s": round(time.time() - started, 1),
            "agent_model": args.agent_model,
            "judge_model": args.judge_model,
            "agent_effort": args.agent_effort,
            "judge_effort": args.judge_effort,
            "concurrency": workers,
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
