#!/usr/bin/env python3
"""Run Nexty skill evals: drive a headless agent over scenarios and grade it.

For each (skill-set x scenario) pair this runner:

  1. Builds an isolated workspace and installs only the skill-set's skills into
     ``<workspace>/.claude/skills`` (the ``no_skills`` baseline installs none).
  2. Copies the scenario's ``fixtures/`` (mock nxd output, source DP dirs) into
     the workspace so the agent has the same artifacts a real session would.
  3. Runs ``claude -p`` from the workspace with the scenario ``prompt.md`` and
     captures the transcript + run metrics (turns, tokens, cost, duration).
  4. Runs any runner-side deterministic checker the scenario declares against
     the landed workspace (opt-in via ``deterministic_check`` in checks.json).
     Its verdict is stated to the judge as an authoritative fact AND enforced
     mechanically, so a closure with wrong numbers cannot pass on a generous
     judge read.
  5. Asks a separate ``claude -p`` judge to grade the transcript against the
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
import shlex
import shutil
import signal
import secrets
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from eval_backends import (
    AGENT_BACKENDS,
    JUDGE_BACKENDS,
    get_agent_backend,
    get_judge_backend,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
EVALS_DIR = REPO_ROOT / "evals"
SKILL_SETS_FILE = EVALS_DIR / "skill-sets.yaml"

# Providers driving the agent-under-test and the judge. `claude` shells the
# Claude Code CLI; `codex` shells the OpenAI Codex CLI. Both implement the same
# AgentBackend/JudgeBackend interface (see eval_backends.py). Pick per-side on
# the CLI (--agent-backend / --judge-backend). Default: claude for both.
DEFAULT_AGENT_BACKEND = "claude"
DEFAULT_JUDGE_BACKEND = "claude"

# Default models per provider. The agent under test runs on the cheaper model we
# measure; the judge runs on the stronger model because its grading is the call
# we most want to trust. Codex model ids differ from Claude's, so the default
# resolves from the chosen backend when --agent-model / --judge-model is unset.
DEFAULT_MODELS = {
    "claude": {"agent": "sonnet", "judge": "opus"},
    "codex": {"agent": "gpt-5.6-luna", "judge": "gpt-5.6-terra"},
}

# Codex reasoning effort is a separate axis from Claude's, and its useful range
# differs (no "xhigh"). These apply only when the corresponding side runs on the
# codex backend AND the user did not pass an explicit --agent-effort /
# --judge-effort. Claude's effort defaults below are unchanged.
#
# Both sides run lower than the Claude defaults to keep the per-pull-request
# gate cheap, since it runs on every touched skill. This is a cost/signal trade,
# not a free win: a weaker agent fails more cells for real reasons, and a weaker
# judge is more prone to the transcript-skim misreads that a stronger one
# catches. Verdicts recorded at one effort are not comparable to another, so
# changing these invalidates evals/baselines/ — re-measure with
# `mode: stability` before trusting a baseline recorded at a different effort.
#   agent: low was measured and reverted. On low the agent writes the fluent
#   API (metric()/join()/dimension(pii=True)/primary_key()) instead of the
#   required per-field __nxd_semantic__ blobs, sometimes leaving the blobs in
#   comments or module-level maps. generate-semantic-layer-dp-from-schema fell
#   from [P P P P P] to [F P F F F] on an unchanged commit. That is a real skill
#   failure the judge described correctly, not a grading artifact, so the cheaper
#   agent buys nothing: it fails cells for reasons the skill did not cause.
#
#   judge: xhigh -> medium was measured and reverted, but NOT for the reason
#   first recorded here. The evidence used was false-pass-validation going
#   [F F F] at medium, read at the time as medium grading a check literally
#   where xhigh credited substance. Later observations at xhigh show F, P, F —
#   one pass in six across both efforts, always the same check. The cell simply
#   flakes on whether the agent names the next command, independent of judge
#   effort, so it was never evidence about the judge at all.
#
#   What the judge drop actually has going for it: it held [P P P P P] on
#   generate-semantic-layer-dp-from-schema. What is still unknown is whether it
#   errs toward false PASS, which no passing cell can reveal. Reverted on that
#   uncertainty rather than on the misread — the whole baseline was recorded
#   under xhigh, and re-grading ten cells to save judge tokens is a poor trade.
CODEX_DEFAULT_AGENT_EFFORT = "medium"
CODEX_DEFAULT_JUDGE_EFFORT = "xhigh"

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

# The generic agent tool allowlist now lives with the Claude backend
# (``CLAUDE_AGENT_ALLOWED_TOOLS`` in eval_backends.py), because it is a
# provider-specific concept: Codex gates the agent through a sandbox policy
# instead of a per-tool allowlist.
#
# Pocket's proven smoke invocation is deliberately narrower than the generic
# eval harness: no web/docs escape hatch and no helper tools beyond the local
# file + shell surface. Skill remains essential: without it the installed
# plugin bodies never activate, so this would not measure the Pocket skills.
# It stays here because it is a *scenario* constraint, not a provider default;
# it is applied only on the Claude backend (see run_one), the only provider that
# has a per-tool allowlist to narrow.
POCKET_AGENT_ALLOWED_TOOLS = "Bash,Read,Write,Edit,Glob,Grep,Skill"

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
POCKET_RUNNER_SIDE_FIXTURES = {
    # These fixtures are trusted runner inputs. The agent gets data/ and the
    # checker, but never the known-good preflight closure or opt-in marker.
    "pocket.json",
    "reference-closure",
    "build_data.py",     # contains fixture discriminator fingerprints
}
DERIVATION_RUNNER_SIDE_FIXTURES = {
    # Ground-truth totals for the derivation scenario. Handing these to the
    # agent hands it the answer key: the scenario measures whether the closure
    # materializes the rulings a question needs, and truth.json states the exact
    # numbers a correct closure produces (and the exact ones a closure that
    # forgets to net refunds produces). Runner-side only.
    "truth.json",
    # The checker leaks the answer key too: its docstring names the seeded
    # merchant->category mapping and the netted-vs-charges-only discrimination
    # strategy. The agent cannot run it anyway (no truth.json), so it has no
    # reason to be in the workspace.
    "check_derived_closure.py",
}
# MCP tool calls reach Snowflake (lower-env). Each call is slower than a local
# file read, so MCP scenarios get a longer agent timeout.
MCP_AGENT_TIMEOUT_S = 1800
# A genuine generate -> serve -> refine run starts a local kernel twice and is
# intentionally much slower than mocked eval cells.
POCKET_AGENT_TIMEOUT_S = 2400
# The verified local smoke used Opus 4.8.  Keep this scenario pinned to that
# model rather than silently inheriting the benchmark-wide Sonnet default.
POCKET_AGENT_MODEL = "claude-opus-4-8"


def effective_agent_model(is_pocket: bool, backend_name: str, default_model: str) -> str:
    """Resolve the model a scenario actually runs on.

    Pocket is pinned to a verified Claude model, but that id is meaningless to
    any other provider, so the pin applies only on the Claude backend. The
    dispatch path and the report must agree on this or a report attributes a
    Codex pocket run to a Claude model and poisons the benchmark ledger.
    """
    if is_pocket and backend_name == "claude":
        return POCKET_AGENT_MODEL
    return default_model
# The verifier may legitimately re-serve the final snapshot plus several
# earlier published snapshots.  Give that work most of the agent budget, then
# report a timeout as runner infrastructure rather than an agent failure.
POCKET_HARNESS_TIMEOUT_S = 1800
_POCKET_PREFLIGHT_LOCK = threading.Lock()
_POCKET_PREFLIGHT_DONE = False
_POCKET_PREFLIGHT_ERROR: str | None = None
_POCKET_PREFLIGHT_ENDPOINT: str | None = None

# Public platform docs base. The docs site is a docsify SPA: the human viewer
# lives at https://docs.demo.nextopia.dev/#/<path>, but the *fetchable* markdown
# is served without the hash fragment at <docs-base><path>.md (e.g.
# https://docs.demo.nextopia.dev/tutorials/cli/setup.md). WebFetch must use the
# .md form — a "#/..." fragment is client-side only and returns the empty SPA
# shell. Every run (baseline included) is told this base so the comparison is
# "skills vs. equally-informed agent", not "skills vs. ignorance". Override with
# --docs-base (e.g. a local cluster's docs host, for testing).
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
    facts: list[str] = field(default_factory=list)


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


def build_workspace(
    tmp: Path,
    skill_set: SkillSet,
    scenario_dir: Path,
    stage_skills_in_workspace: bool = False,
) -> tuple[Path, Path | None]:
    """Create an isolated agent workspace + a per-skill-set plugin dir.

    Returns ``(workspace, plugin_dir)``. ``plugin_dir`` is None for the
    ``no_skills`` baseline (no skills) and otherwise a directory holding a
    minimal `.claude-plugin/plugin.json` + the set's skills, loaded by the agent
    via ``--plugin-dir``.

    Skills MUST be loaded as a plugin for the Claude backend: copying skill dirs
    into the workspace's ``.claude/skills/`` does NOT register them — ``claude -p
    --setting-sources project`` ignores project-directory skills, so they never
    activate and the agent only benefits from files it happens to read.
    ``--plugin-dir`` with a `plugin.json` is the mechanism that actually surfaces
    them as invokable skills (`<plugin>:<skill>`).

    ``stage_skills_in_workspace`` is for providers without plugin-dir skill
    activation (Codex): the skill dirs are additionally copied under
    ``<workspace>/.skills/<name>`` so the agent can read their SKILL.md files as
    context. The agent prompt points at that directory (see ``build_agent_prompt``
    with ``skills_in_workspace=True``). The plugin_dir is still built and returned
    (harmless; Codex just ignores it)."""
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
        if stage_skills_in_workspace:
            ws_skills = ws / SKILLS_WORKSPACE_DIR
            ws_skills.mkdir(parents=True, exist_ok=True)
            for rel in skill_set.skills:
                src = REPO_ROOT / rel
                shutil.copytree(src, ws_skills / src.name)

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
            # Never copy generated bytecode or hidden runner detritus.  In
            # particular, a sibling __pycache__/build_data.pyc would reveal
            # runner-only discriminator assertions to the agent.
            if (item.name.startswith(".") or item.name == "__pycache__"
                    or item.name in MCP_SERVER_SIDE_FIXTURES | POCKET_RUNNER_SIDE_FIXTURES
                    | DERIVATION_RUNNER_SIDE_FIXTURES):
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

    Both the task line and the section headers may be written as plain lines
    ("Task for the agent:") or markdown headings ("## Task for the agent") —
    match either, or a heading-styled prompt leaks the whole spec (intro,
    artifacts, stopgap notes) to the agent and the no-skills baseline.
    """
    lines = prompt_md.splitlines()
    section_re = re.compile(
        r"^\s*(?:#{1,6}\s*)?"
        r"(Required artifacts|Success checks|Constraints|Expected final|"
        r"Note on the annotation)",
        re.IGNORECASE,
    )
    task_start = None
    for i, line in enumerate(lines):
        if re.match(r"^\s*(?:#{1,6}\s*)?Task for the agent:?\s*$", line,
                    re.IGNORECASE):
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
        if re.match(r"^\s*(?:#{1,6}\s*)?Success checks:?\s*$", line, re.IGNORECASE):
            cut = i
            break
    return "\n".join(lines[:cut]).strip()


def build_agent_prompt(
    scenario_prompt: str,
    docs_base: str,
    has_examples: bool,
    skills_in_workspace: bool = False,
) -> str:
    """Prepend the shared context every skill-set gets (docs + examples).

    ``skills_in_workspace`` is set for providers that cannot activate skills as a
    plugin (Codex): the skill dirs are staged under ``<workspace>/.skills/`` and
    this adds a line telling the agent to read them, so the skill guidance is
    available as context. Providers that activate skills natively (Claude) leave
    this False — the skills load through the Skill tool, not by file-reading."""
    lines = [
        "You are working on a Nextdata OS (nxd) data-product task.",
        "",
        "Available context (the same for every run):",
        f"- Public platform docs: fetch markdown pages (WebFetch, or curl if "
        f"WebFetch is unavailable) at "
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
    if skills_in_workspace:
        lines.append(
            f"- A curated skill pack is staged under `{SKILLS_WORKSPACE_DIR}/` in "
            "your workspace: each subdirectory is a skill with a `SKILL.md` "
            "describing a procedure for this platform. BEFORE improvising, list "
            f"`{SKILLS_WORKSPACE_DIR}/`, read the `SKILL.md` of any skill whose "
            "description matches this task, and follow its steps and referenced "
            "files."
        )
    lines += ["", "--- TASK ---", scenario_prompt]
    return "\n".join(lines)


# Where the skill pack is staged inside the agent workspace for providers that
# lack plugin-dir skill activation (Codex). Claude ignores this (it loads the
# pack via --plugin-dir instead).
SKILLS_WORKSPACE_DIR = ".skills"


def scenario_needs_mcp(scenario_dir: Path) -> dict | None:
    """Return the parsed fixtures/mcp.json if this scenario opts into MCP, else None."""
    marker = scenario_dir / "fixtures" / "mcp.json"
    if not marker.exists():
        return None
    return json.loads(marker.read_text(encoding="utf-8"))


def scenario_needs_pocket(scenario_dir: Path) -> dict | None:
    """Return the Pocket runtime marker when a scenario opts into the local
    desktop supervisor. Kept parallel to MCP opt-in so ordinary cells never
    inherit a host binary, Python venv, or persistent-process cleanup."""
    marker = scenario_dir / "fixtures" / "pocket.json"
    if not marker.exists():
        return None
    return json.loads(marker.read_text(encoding="utf-8"))


def _pocket_runtime(scenario_dir: Path, tmp: Path) -> tuple[Path, dict[str, str], str]:
    """Return a narrow command directory and the matched Python interpreter."""
    supervisor_dir = Path(os.environ.get("EVAL_POCKET_SUPERVISOR_DIR", "")).expanduser()
    python = os.environ.get("EVAL_POCKET_PYTHON", "").strip()
    if not supervisor_dir.is_dir() or not python:
        raise RuntimeError(
            "set EVAL_POCKET_SUPERVISOR_DIR (both desktop binaries) and "
            "EVAL_POCKET_PYTHON (supervisor venv Python)"
        )
    binaries = ("nxd-desktop-supervisor", "nxd-desktop-kernel-host")
    missing = [name for name in binaries if not (supervisor_dir / name).is_file()]
    if missing or not Path(python).is_file():
        raise RuntimeError(
            f"Pocket runtime missing binaries={missing} or Python={python!r}"
        )
    # The supervisor finds its kernel-host sibling from its *real* executable
    # path, so tiny exec wrappers preserve that contract while exposing only the
    # two intended Pocket commands to the evaluated agent.  Do not symlink: the
    # detached implementation historically re-execed through current_exe().
    bin_dir = tmp / "pocket-bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    for name in binaries:
        target = supervisor_dir / name
        wrapper = bin_dir / name
        wrapper.write_text(
            "#!/bin/sh\nexec " + shlex.quote(str(target)) + " \"$@\"\n",
            encoding="utf-8",
        )
        wrapper.chmod(0o755)
    # semantic_child.py uses this interpreter for dlt and the local semantic
    # compiler; it must be the matched supervisor venv, not the runner Python.
    return bin_dir, {"NXD_DESKTOP_PYTHON": python}, python


def _pocket_kv(output: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in output.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


@dataclass
class PocketServe:
    """Foreground supervisor process plus its startup transcript files."""

    process: subprocess.Popen
    stdout: object
    stderr: object
    values: dict[str, str]
    bearer: str


def _pocket_start_serve(supervisor: Path, definition: Path, workflow: str,
                        data_dir: Path, env: dict[str, str],
                        timeout_s: int = 300) -> PocketServe:
    """Start documented foreground ``serve`` and wait for real publication.

    ``create --detach`` can report ``published=yes`` while its child has already
    lost its inherited lifecycle context.  Runner-owned setup deliberately uses
    the same foreground command agents are asked to use, with a direct Popen
    handle held until ``stop`` reaps it.
    """
    bearer = f"eval-pocket-{secrets.token_urlsafe(24)}"
    child_env = dict(env)
    child_env["NXD_DESKTOP_BEARER"] = bearer
    stdout = tempfile.TemporaryFile(mode="w+", encoding="utf-8")
    stderr = tempfile.TemporaryFile(mode="w+", encoding="utf-8")
    proc = subprocess.Popen(
        [str(supervisor), "serve", "--definition", str(definition),
         "--workflow", workflow, "--data-dir", str(data_dir)],
        stdout=stdout, stderr=stderr, text=True, env=child_env, start_new_session=True,
    )
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        stdout.seek(0)
        output = stdout.read()
        values = _pocket_kv(output)
        if values.get("published") == "yes":
            return PocketServe(proc, stdout, stderr, values, bearer)
        if proc.poll() is not None:
            stderr.seek(0)
            detail = stderr.read()
            stdout.close()
            stderr.close()
            raise RuntimeError(f"foreground serve exited before publication: {detail[-1200:]}")
        time.sleep(0.1)
    _sweep_pocket_pid(proc.pid)
    stdout.seek(0)
    stderr.seek(0)
    detail = f"stdout={stdout.read()[-600:]} stderr={stderr.read()[-600:]}"
    stdout.close()
    stderr.close()
    raise RuntimeError(f"foreground serve did not publish within {timeout_s}s: {detail}")


def _pocket_stop_serve(supervisor: Path, data_dir: Path, served: PocketServe,
                       env: dict[str, str]) -> None:
    """Stop a foreground Pocket serve and close runner-owned log handles."""
    recorded_pids: list[int] = []
    for name in ("semantic.pid", "supervisor.pid"):
        with contextlib.suppress(OSError, ValueError):
            recorded_pids.append(int((data_dir / name).read_text(encoding="utf-8").strip()))
    with contextlib.suppress(OSError, subprocess.TimeoutExpired):
        subprocess.run([str(supervisor), "stop", "--data-dir", str(data_dir)],
                       capture_output=True, text=True, timeout=60, env=env)
    # The semantic child owns a distinct process group. If `stop` raced the
    # foreground server's shutdown, the direct supervisor sweep below cannot
    # reach that child, so explicitly reap both pid-file identities as well.
    for pid in recorded_pids:
        _sweep_pocket_pid(pid)
    if served.process.poll() is None:
        _sweep_pocket_pid(served.process.pid)
    with contextlib.suppress(subprocess.TimeoutExpired):
        served.process.wait(timeout=10)
    served.stdout.close()
    served.stderr.close()


def _sweep_stale_preflights(supervisor: Path, env: dict[str, str]) -> None:
    """Recover a preflight abandoned by SIGKILL or an interrupted runner."""
    for root in Path(tempfile.gettempdir()).glob("eval-pocket-preflight-*"):
        owner = root / ".owner-pid"
        try:
            if owner.exists() and _pid_alive(int(owner.read_text(encoding="utf-8").strip())):
                continue
        except ValueError:
            pass
        data_dir = root / "state"
        if data_dir.exists():
            with contextlib.suppress(OSError, subprocess.TimeoutExpired):
                subprocess.run([str(supervisor), "stop", "--data-dir", str(data_dir)],
                               capture_output=True, text=True, timeout=60, env=env)
            for name in ("semantic.pid", "supervisor.pid"):
                with contextlib.suppress(OSError, ValueError):
                    _sweep_pocket_pid(int((data_dir / name).read_text(encoding="utf-8").strip()))
        shutil.rmtree(root, ignore_errors=True)


def pocket_preflight(scenario_dir: Path, bin_dir: Path, env_overrides: dict[str, str]) -> str | None:
    """Serve/describe/query/stop the committed closure once per runner.

    A broken local build is infrastructure failure, not evidence an agent could
    not use the skills. The memoized result is shared across parallel cells.
    """
    global _POCKET_PREFLIGHT_DONE, _POCKET_PREFLIGHT_ERROR, _POCKET_PREFLIGHT_ENDPOINT
    with _POCKET_PREFLIGHT_LOCK:
        if _POCKET_PREFLIGHT_DONE:
            return _POCKET_PREFLIGHT_ERROR
        _POCKET_PREFLIGHT_DONE = True
        reference = scenario_dir / "fixtures" / "reference-closure"
        supervisor = bin_dir / "nxd-desktop-supervisor"
        if not reference.is_dir():
            _POCKET_PREFLIGHT_ERROR = "reference closure is missing"
            return _POCKET_PREFLIGHT_ERROR
        env = dict(os.environ)
        env.update(env_overrides)
        env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
        _sweep_stale_preflights(supervisor, env)
        tmp = Path(tempfile.mkdtemp(prefix="eval-pocket-preflight-"))
        (tmp / ".owner-pid").write_text(str(os.getpid()), encoding="utf-8")
        data_dir = tmp / "state"
        served: PocketServe | None = None
        try:
            try:
                served = _pocket_start_serve(
                    supervisor, reference, "pocket-preflight", data_dir, env
                )
                endpoint = served.values.get("semantic_endpoint", "")
                if not endpoint:
                    raise RuntimeError("serve omitted semantic_endpoint")
                # `published=yes` is the supervisor's publication milestone,
                # not a socket-readiness guarantee for its semantic child.
                # Wait for an authenticated catalog response before declaring
                # the pinned runtime usable, otherwise a valid foreground
                # serve is misreported as a broken eval infrastructure.
                deadline = time.time() + 60
                while True:
                    desc = subprocess.run(
                        [str(supervisor), "describe", "--endpoint", endpoint,
                         "--token", served.bearer],
                        capture_output=True, text=True, timeout=15, env=env,
                    )
                    try:
                        ready = desc.returncode == 0 and bool(json.loads(desc.stdout).get("models"))
                    except json.JSONDecodeError:
                        ready = False
                    if ready:
                        break
                    if served.process.poll() is not None:
                        raise RuntimeError(
                            "foreground serve exited before semantic readiness: "
                            f"{desc.stderr[-800:]}"
                        )
                    if time.time() >= deadline:
                        raise RuntimeError(
                            "semantic endpoint did not become ready after publication: "
                            f"{desc.stderr[-800:]}"
                        )
                    time.sleep(0.25)
                probe = subprocess.run(
                    [str(supervisor), "query", "--endpoint", endpoint, "--token", served.bearer,
                     "--measure", "total_invoice_amount_eur"],
                    capture_output=True, text=True, timeout=90, env=env,
                )
                if probe.returncode != 0:
                    raise RuntimeError(f"query failed: {probe.stderr[-800:]}")
                answer = json.loads(probe.stdout)
                if answer.get("error") != "" or not answer.get("rows"):
                    raise RuntimeError(f"query response invalid: {probe.stdout[-800:]}")
                _POCKET_PREFLIGHT_ENDPOINT = endpoint
                print(f"Pocket preflight OK: semantic_endpoint={endpoint}",
                      file=sys.stderr, flush=True)
            except (OSError, subprocess.TimeoutExpired, RuntimeError, json.JSONDecodeError) as exc:
                _POCKET_PREFLIGHT_ERROR = str(exc)
        finally:
            if served is not None:
                _pocket_stop_serve(supervisor, data_dir, served, env)
            else:
                with contextlib.suppress(OSError, subprocess.TimeoutExpired):
                    subprocess.run([str(supervisor), "stop", "--data-dir", str(data_dir)],
                                   capture_output=True, text=True, timeout=60, env=env)
            shutil.rmtree(tmp, ignore_errors=True)
        return _POCKET_PREFLIGHT_ERROR


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _sweep_pocket_pid(pid: int) -> None:
    """Last-resort process-group cleanup for a supervisor whose stop failed."""
    if pid <= 0 or not _pid_alive(pid):
        return
    try:
        os.killpg(pid, signal.SIGTERM)
    except OSError:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            return
    deadline = time.time() + 5
    while _pid_alive(pid) and time.time() < deadline:
        time.sleep(0.1)
    if _pid_alive(pid):
        try:
            os.killpg(pid, signal.SIGKILL)
        except OSError:
            with contextlib.suppress(OSError):
                os.kill(pid, signal.SIGKILL)


@contextlib.contextmanager
def pocket_process_guard(ws: Path, supervisor: Path, env_overrides: dict[str, str]):
    """Always stop persistent supervisors created by a Pocket agent cell."""
    try:
        yield
    finally:
        for db in ws.rglob("state.sqlite*"):
            if db.name not in {"state.sqlite", "state.sqlite3"}:
                continue
            data_dir = db.parent
            env = dict(os.environ)
            env.update(env_overrides)
            with contextlib.suppress(OSError, subprocess.TimeoutExpired):
                subprocess.run([str(supervisor), "stop", "--data-dir", str(data_dir)],
                               capture_output=True, text=True, timeout=60, env=env)
            for name in ("semantic.pid", "supervisor.pid"):
                pid_file = data_dir / name
                try:
                    _sweep_pocket_pid(int(pid_file.read_text(encoding="utf-8").strip()))
                except (OSError, ValueError):
                    pass


def pocket_harness_fact(scenario_dir: Path, ws: Path, python: str, workflow: str,
                        bin_dir: Path, env_overrides: dict[str, str]) -> str:
    """Run the pristine verifier before the temporary workspace disappears."""
    checker = scenario_dir / "fixtures" / "check_pocket_loop.py"
    env = dict(os.environ)
    env.update(env_overrides)
    env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
    # Snapshot re-serves must be visible to pocket_process_guard even if this
    # verifier times out after its child supervisor was spawned.
    checker_tmp = ws / ".pocket-check-tmp"
    checker_tmp.mkdir(parents=True, exist_ok=True)
    env["NXD_POCKET_CHECK_TMPDIR"] = str(checker_tmp)
    try:
        proc = subprocess.run(
            [python, str(checker), "--mode", "harness", "--workspace", str(ws),
             "--workflow", workflow],
            capture_output=True, text=True, timeout=POCKET_HARNESS_TIMEOUT_S, env=env,
        )
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        if not lines:
            facts = {
                "passed": False,
                "infrastructure_error": "pocket harness verifier emitted no facts",
            }
        else:
            facts = json.loads(lines[-1])
        facts["harness_exit_code"] = proc.returncode
    except subprocess.TimeoutExpired as exc:
        facts = {
            "passed": False,
            "infrastructure_error": (
                f"pocket harness verifier timed out after {POCKET_HARNESS_TIMEOUT_S}s: {exc}"
            ),
        }
    except (OSError, json.JSONDecodeError) as exc:
        facts = {
            "passed": False,
            "infrastructure_error": f"pocket harness verifier failed: {exc}",
        }
    return "POCKET VERIFY (authoritative runner facts): " + json.dumps(facts, sort_keys=True)


def pocket_facts_passed(facts: list[str]) -> bool:
    """Return whether an authoritative Pocket verifier fact explicitly passed.

    A Pocket cell is fail-closed: missing, malformed, timed-out, or negative
    verifier output must not be rescued by a lenient LLM judge.
    """
    prefix = "POCKET VERIFY (authoritative runner facts): "
    for fact in facts:
        if fact.startswith(prefix):
            try:
                return json.loads(fact[len(prefix):]).get("passed") is True
            except json.JSONDecodeError:
                return False
    return False


def pocket_facts_infrastructure_error(facts: list[str]) -> str | None:
    """Return a verifier infrastructure failure, if one was recorded."""
    prefix = "POCKET VERIFY (authoritative runner facts): "
    for fact in facts:
        if fact.startswith(prefix):
            try:
                error = json.loads(fact[len(prefix):]).get("infrastructure_error")
            except json.JSONDecodeError:
                return "pocket verifier facts were malformed"
            return str(error) if error else None
    return None


# ---------------------------------------------------------------------------
# Runner-side deterministic check (opt-in per scenario).
#
# Some scenarios ship a checker that can decide correctness by ARITHMETIC
# rather than by a judge reading a transcript — but only because it reads a
# ground-truth fixture that states the right answer. Such a checker cannot be
# an agent self-check: handing the agent the checker or its truth file hands it
# the answer key. So the harness runs it AFTER the agent finishes, against the
# landed workspace, with the truth fixture supplied from the scenario directory
# (which is runner-side and deliberately excluded from the workspace copy).
#
# Contrast with a self-check like generate-runnable-dp-from-intent's, which the
# agent runs itself and the judge grades from the transcript: that checker
# embeds no withheld answer, so it can safely live in the workspace.
#
# Opt-in and guarded: only scenarios declaring ``"deterministic_check"`` in
# checks.json activate this. Config keys:
#   script  — checker filename under the scenario's ``fixtures/`` (required)
#   deps    — extra PyPI deps for ``uv run --with`` (default: ["duckdb"])
#
# The result is emitted as an authoritative fact (visible to the judge) AND
# enforced mechanically: a failed check fails the cell regardless of how
# generously the judge read the transcript.
# ---------------------------------------------------------------------------

DETERMINISTIC_CHECK_TIMEOUT_S = 600
DETERMINISTIC_CHECK_PREFIX = "DETERMINISTIC CHECK (authoritative runner facts): "
# Deliberately stable: report code and callers distinguish this cell outcome
# without parsing checker-specific detail.
DETERMINISTIC_CHECK_FAILED = "deterministic check failed"


def deterministic_check_fact(
    scenario_dir: Path, ws: Path, cfg: dict, trace: str = ""
) -> str:
    """Run a scenario's runner-side checker against the landed workspace.

    ``--fixtures`` points at the scenario's own ``fixtures/`` directory, never
    at the workspace: that is where the withheld ground truth lives and it must
    stay out of the agent's reach.

    ``--trace`` is passed only when the scenario sets ``"wants_trace": true``.
    A landed workspace records WHAT the agent produced but not the ORDER it
    acted in, so a scenario asserting that a conversational checkpoint preceded
    the first write cannot be graded from disk alone. The trace file lands in
    its own temp dir, never inside ``ws``: a file in the workspace would be
    visible to the agent and would perturb any workspace-files assertion.
    """
    fixtures = scenario_dir / "fixtures"
    script = fixtures / str(cfg.get("script", ""))
    if not script.is_file():
        return DETERMINISTIC_CHECK_PREFIX + json.dumps(
            {"passed": False,
             "infrastructure_error": f"checker not found: {script}"},
            sort_keys=True,
        )
    deps = cfg.get("deps") or ["duckdb"]
    cmd = ["uv", "run", "--no-project"]
    for dep in deps:
        cmd += ["--with", str(dep)]
    cmd += ["python", str(script), "--fixtures", str(fixtures), "--root", str(ws)]
    if cfg.get("wants_trace"):
        trace_file = Path(tempfile.mkdtemp(prefix="nxd-eval-trace-")) / "trace.txt"
        trace_file.write_text(trace, encoding="utf-8")
        cmd += ["--trace", str(trace_file)]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=DETERMINISTIC_CHECK_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired as exc:
        return DETERMINISTIC_CHECK_PREFIX + json.dumps(
            {"passed": False,
             "infrastructure_error": (
                 f"checker timed out after {DETERMINISTIC_CHECK_TIMEOUT_S}s: {exc}")},
            sort_keys=True,
        )
    except OSError as exc:
        return DETERMINISTIC_CHECK_PREFIX + json.dumps(
            {"passed": False, "infrastructure_error": f"checker failed to start: {exc}"},
            sort_keys=True,
        )
    stdout = proc.stdout
    # Fail closed on the exit code, and require the checker's own success
    # sentinel: a checker that dies mid-report can exit 0 without having run
    # the gate that matters.
    passed = proc.returncode == 0 and "ALL CHECKS PASSED" in stdout
    facts: dict[str, object] = {
        "passed": passed,
        "exit_code": proc.returncode,
        # Only the FAIL lines: the judge needs the naming detail, not the
        # dozen PASS lines that would crowd its context.
        "failures": [line for line in stdout.splitlines() if line.startswith("FAIL ")],
    }
    if not passed and not facts["failures"]:
        # Exit-code failure with no FAIL line means the checker aborted rather
        # than graded. Carry stderr so that is diagnosable instead of silent.
        facts["detail"] = (stdout[-1500:] + proc.stderr[-1500:]).strip()
    return DETERMINISTIC_CHECK_PREFIX + json.dumps(facts, sort_keys=True)


def deterministic_check_passed(facts: list[str]) -> bool:
    """Whether an authoritative deterministic-check fact explicitly passed.

    Fail-closed: a missing, malformed, or negative fact is not rescued by a
    lenient judge.
    """
    for fact in facts:
        if fact.startswith(DETERMINISTIC_CHECK_PREFIX):
            try:
                return json.loads(fact[len(DETERMINISTIC_CHECK_PREFIX):]).get("passed") is True
            except json.JSONDecodeError:
                return False
    return False


def deterministic_check_infrastructure_error(facts: list[str]) -> str | None:
    """Return a checker infrastructure failure, if one was recorded.

    A checker that never started or timed out proves nothing about the agent;
    the caller reports it as infrastructure rather than as an agent FAIL.
    """
    for fact in facts:
        if fact.startswith(DETERMINISTIC_CHECK_PREFIX):
            try:
                error = json.loads(fact[len(DETERMINISTIC_CHECK_PREFIX):]).get(
                    "infrastructure_error"
                )
            except json.JSONDecodeError:
                return "deterministic check facts were malformed"
            return str(error) if error else None
    return None


def deterministic_check_detail(facts: list[str]) -> str:
    """Human-readable failure detail from the deterministic-check fact."""
    for fact in facts:
        if fact.startswith(DETERMINISTIC_CHECK_PREFIX):
            try:
                data = json.loads(fact[len(DETERMINISTIC_CHECK_PREFIX):])
            except json.JSONDecodeError:
                return "deterministic check facts were malformed"
            if data.get("infrastructure_error"):
                return str(data["infrastructure_error"])
            failures = data.get("failures") or []
            return "; ".join(str(f) for f in failures) or str(data.get("detail", ""))
    return "deterministic check did not run"


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
    # Isolate the agent from any live mesh session on the host. The query
    # skill's scripts resolve the active mesh from NXD_HOME (default ~/.nxd);
    # if the machine running the eval has a valid `nxd login` session, mesh
    # discovery hijacks the cell to the LIVE mesh and the graded run measures
    # live data instead of the fixtures behind the stub server. An empty
    # NXD_HOME reproduces the CI condition (no local mesh config), so
    # discovery falls through to `nxd mcp health` — the fake nxd on PATH.
    nxd_home = tempfile.mkdtemp(prefix="eval-nxd-home-")
    try:
        _wait_for_http(endpoint, proc, timeout_s=60)
        env = {
            "EVAL_MCP_ENDPOINT": endpoint,
            "EVAL_MCP_DP": dp,
            "EVAL_MCP_TOOL_COUNT": str(tool_count),
            "NXD_HOME": nxd_home,
        }
        yield endpoint, env
    finally:
        shutil.rmtree(nxd_home, ignore_errors=True)
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


JUDGE_SYSTEM = (
    "You are an exacting eval grader for an AI agent. You are given a scenario, "
    "a list of success checks, and the agent's final answer transcript. Grade "
    "each check independently against ONLY what the transcript shows. Do not "
    "give credit for things the agent did not actually say or do. Be skeptical: "
    "a plausible-sounding answer that misses the check fails it."
)


def build_judge_prompt(scenario_dir: Path, checks: dict, trace: str,
                       final_answer: str, facts: list[str] | None = None) -> str:
    prompt_md = (scenario_dir / "prompt.md").read_text(encoding="utf-8")
    check_lines = "\n".join(
        f'  {i + 1}. [id={c["id"]}] {c["check"]}' for i, c in enumerate(checks["checks"])
    )
    # Opt-in mechanical facts the harness computed itself (not the agent's word)
    # — e.g. re-hashing the reproduced models.py to tie it to the reported
    # digest. Only present when the scenario declares it in checks.json.
    verified_facts = list(facts or [])
    tie = digest_tie_fact(final_answer, checks.get("digest_tie"))
    if tie:
        verified_facts.append(tie)
    mechanical = ""
    if verified_facts:
        mechanical = (
            "\n--- HARNESS-VERIFIED FACTS (computed mechanically by the runner, "
            "NOT the agent's claims — treat as ground truth and let them "
            "override anything the agent asserts) ---\n" + "\n".join(verified_facts) + "\n"
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
{mechanical}
--- INSTRUCTIONS ---
Grade every check as pass or fail with a one-sentence justification grounded in
the trace and final answer. A "did the agent inspect X" check passes only if the
trace shows the corresponding tool call/result. That rule is about the agent's
PROCESS. It does not apply to checks about the CONTENT of a file the agent
wrote: when a WORKSPACE FILES block is present it is the authoritative record of
what the agent produced, so grade those checks against the quoted file contents
and do not fail one merely because the trace never echoed the file. Give an overall pass only if ALL
checks pass. Where a HARNESS-VERIFIED FACTS block is present, it is authoritative
for exactly what it states and no more: it settles whether the final-answer
source matches the reported digest (use it, not the agent's self-report, for
that), but it does NOT establish that the digest came from a passing acceptance
run — grade that provenance from the trace.

For Pocket scenarios, direct writes to the agent-owned supervisor state under
`.pocket/state/` (`state.sqlite*` or `definitions/**`) outside an
`nxd-desktop-supervisor` command are an automatic FAIL for the
supervisor-state-integrity check and therefore for the whole cell. The
runner-owned `.pocket-check-tmp/` is explicitly excluded from this rule because
it holds verifier snapshot re-serves. In particular, do not excuse SQLite
inserts, copied/edited pinned snapshots, or shell redirection in `.pocket/state`
merely because the final re-served output is plausible. Use the harness-provided
published-run timestamps and definition SHA-256s to cross-check the trace
chronology.

Respond with ONE JSON object and nothing else, in this exact shape:
{{"checks": [{{"id": "<id>", "pass": true|false, "why": "<one sentence>"}}],
  "overall_pass": true|false, "summary": "<one sentence>"}}"""


def run_judge(judge_backend, scenario_dir: Path, checks: dict, trace: str,
              final_answer: str, model: str, timeout_s: int,
              effort: str = "", facts: list[str] | None = None) -> dict:
    """Grade one transcript. Builds the provider-independent judge prompt (which
    folds in the harness-verified ``facts``), then delegates the actual model
    call to the selected judge backend."""
    prompt = build_judge_prompt(scenario_dir, checks, trace, final_answer, facts)
    return judge_backend.run_judge(prompt, JUDGE_SYSTEM, model, timeout_s, effort)


# ---------------------------------------------------------------------------
# Mechanical digest tie (opt-in per scenario).
#
# Some scenarios ship an acceptance test that prints ``MODELS_SHA256: <hex>``
# — the sha256 of the exact file it validated — and require the agent to echo
# that line beside the file's full source in the final answer. A self-reported
# digest is not a genuine tie: the agent could paste file B's source while
# copying file A's passing digest. To make the tie MECHANICAL, the harness
# re-extracts the reproduced source from the final answer, hashes it itself,
# and states the match/mismatch as fact for the judge — the judge no longer
# takes the agent's word for it.
#
# The reproduced source is located by an UNAMBIGUOUS SENTINEL, not by fence
# heuristics: the agent must wrap its one authoritative models.py between
# ``===BEGIN FINAL models.py===`` / ``===END FINAL models.py===`` marker lines.
# Exactly one pair is required — zero pairs => UNSATISFIED, two-or-more pairs
# => fail closed (ambiguous, never guess which is authoritative). This kills
# the decoy-block bypass (a second "reference" block can't be selected over
# the marked one) and removes fence-format fragility (```py, ```python, or an
# unlabeled/absent fence inside the markers are all fine — the markers, not
# the fence, delimit the block).
#
# What it proves is exactly: the marked final-answer source hashes (or does
# not hash) to the reported MODELS_SHA256. It does NOT prove that digest came
# from a PASSING checker run — that provenance stays judge-graded from the
# trace.
#
# Opt-in and guarded: only scenarios that declare ``"digest_tie"`` in
# checks.json activate this; every other scenario is untouched.
# ---------------------------------------------------------------------------

def _marker_names(filename: str) -> tuple[str, str]:
    return (f"===BEGIN FINAL {filename}===", f"===END FINAL {filename}===")


def _strip_optional_fence(block: str) -> str:
    """If the marked content is itself wrapped in a single code fence, drop the
    fence lines — the digest is over the source, not the ``` decoration. A
    fence anywhere other than the first/last non-empty lines is left intact
    (it is part of the source, not decoration)."""
    lines = block.split("\n")
    # Trim leading/trailing wholly-blank lines for fence detection only.
    start = 0
    end = len(lines)
    while start < end and lines[start].strip() == "":
        start += 1
    while end > start and lines[end - 1].strip() == "":
        end -= 1
    if end - start >= 2 and lines[start].lstrip().startswith("```") \
            and lines[end - 1].strip() == "```":
        return "\n".join(lines[start + 1:end - 1])
    return block


def _extract_marked_source(text: str, filename: str) -> tuple[str | None, str]:
    """Return ``(source, status)`` for the sentinel-delimited authoritative
    ``filename``. ``status`` is one of "ok", "none", "ambiguous". Exactly one
    marker pair yields the content between them (optional inner fence stripped);
    zero pairs => (None, "none"); more than one begin OR end marker =>
    (None, "ambiguous") — fail closed, never pick one."""
    if not text:
        return None, "none"
    begin, end = _marker_names(filename)
    b_idx = [m.start() for m in re.finditer(re.escape(begin), text)]
    e_idx = [m.start() for m in re.finditer(re.escape(end), text)]
    if len(b_idx) == 0 and len(e_idx) == 0:
        return None, "none"
    if len(b_idx) != 1 or len(e_idx) != 1:
        return None, "ambiguous"
    b, e = b_idx[0], e_idx[0]
    if e <= b:
        return None, "ambiguous"
    inner = text[b + len(begin):e]
    # Drop the newline immediately after the BEGIN marker and before the END
    # marker (the markers live on their own lines); keep the source between.
    inner = inner[1:] if inner.startswith("\n") else inner
    inner = inner[:-1] if inner.endswith("\n") else inner
    return _strip_optional_fence(inner), "ok"


def _reported_digest(text: str, label: str = "MODELS_SHA256") -> str | None:
    """The last self-reported ``<LABEL>: <hex>`` digest in the final answer."""
    if not text:
        return None
    matches = re.findall(rf"{re.escape(label)}\s*:\s*([0-9a-fA-F]{{64}})", text)
    return matches[-1].lower() if matches else None


def digest_tie_fact(final_answer: str, cfg: dict) -> str | None:
    """Produce a mechanical statement for the judge tying the marked source to
    the self-reported digest, or None when the scenario doesn't opt in.

    ``cfg`` (checks.json ``digest_tie``) keys: ``filename`` (default
    "models.py"), ``label`` (default "MODELS_SHA256")."""
    if not cfg:
        return None
    filename = cfg.get("filename", "models.py")
    label = cfg.get("label", "MODELS_SHA256")
    begin, end = _marker_names(filename)

    reported = _reported_digest(final_answer, label)
    source, status = _extract_marked_source(final_answer, filename)

    if status == "ambiguous":
        return (f"MECHANICAL DIGEST TIE: UNSATISFIED (fail-closed) — the final "
                f"answer contains more than one `{begin}` / `{end}` marker pair "
                f"(or a malformed pair), so the one authoritative {filename} is "
                f"ambiguous. The harness refuses to guess which block is final; "
                f"treat any digest-tie check as FAILED.")
    if source is None and reported is None:
        return (f"MECHANICAL DIGEST TIE: UNSATISFIED — the final answer contains "
                f"neither a `{begin}` ... `{end}` marked {filename} nor a "
                f"{label} digest line.")
    if source is None:
        return (f"MECHANICAL DIGEST TIE: UNSATISFIED — the final answer has no "
                f"`{begin}` ... `{end}` marked {filename}, so the reported "
                f"{label} cannot be tied to any source.")
    if reported is None:
        return (f"MECHANICAL DIGEST TIE: UNSATISFIED — the marked {filename} is "
                f"present but the final answer has no {label} digest line to "
                f"tie it to.")

    # Hash the marked source exactly, plus trailing-newline and line-ending
    # variants, so a genuine reproduction that differs only in a final newline
    # or in CRLF-vs-LF line endings (e.g. a Windows paste) still ties.
    # Deliberately narrow: only whole-block trailing newline and the newline
    # STYLE flex — different source content can never coincide.
    bases = {source, source.replace("\r\n", "\n").replace("\r", "\n")}
    variants = {
        v
        for base in bases
        for v in (base, base + "\n", base.rstrip("\n"), base.rstrip("\n") + "\n")
    }
    computed = {hashlib.sha256(v.encode("utf-8")).hexdigest() for v in variants}
    if reported in computed:
        return (f"MECHANICAL DIGEST TIE: SATISFIED — the harness re-hashed the "
                f"{filename} the final answer marked with `{begin}` ... `{end}` "
                f"and it MATCHES the reported {label}: {reported}. This proves "
                f"ONLY that the final-answer {filename} source equals the source "
                f"that digest was computed over; whether that digest came from a "
                f"PASSING acceptance run remains to be graded from the trace.")
    return (f"MECHANICAL DIGEST TIE: MISMATCH — the {filename} the final answer "
            f"marked with `{begin}` ... `{end}` hashes to {sorted(computed)[0]}, "
            f"which does NOT equal the reported {label}: {reported}. The marked "
            f"final-answer source is NOT the source that digest was computed "
            f"over (e.g. a digest copied from a different file). Treat any "
            f"digest-tie check as FAILED.")


# Opt-in and guarded: only scenarios that declare ``"workspace_files"`` in
# checks.json get this. Checks about what an agent *wrote* cannot be graded from
# a transcript — tool results are truncated, and an agent that writes a correct
# file without echoing it back looks identical to one that wrote nothing. That
# ambiguity does not fail such a check honestly; it fails it for lack of
# evidence, and it flips run to run with how chatty the agent happened to be.
# Reading the files the agent actually left behind replaces that guesswork.
WORKSPACE_FILE_BUDGET = 60_000

# Directories the harness stages into the workspace as INPUT. Their contents are
# never the agent's output, so quoting them as such would misattribute authorship
# to the agent and burn the budget the agent's real files need.
_STAGED_INPUT_DIRS = frozenset({".skills", ".claude", "fixtures", ".pocket"})


def workspace_files_fact(ws: Path, cfg: list | None) -> str | None:
    """Quote the agent's produced files verbatim for the judge, or None when the
    scenario doesn't opt in.

    ``cfg`` (checks.json ``workspace_files``) is a list of workspace-relative
    glob patterns, e.g. ``["models.py", "spec.py", "requirements.txt"]``.
    """
    if not cfg:
        return None

    # Distinguish "the agent wrote nothing" from "the harness looked after the
    # workspace was deleted". Both otherwise yield zero matches and produce an
    # identical, confident-sounding "never written" verdict — which is how a
    # read-too-late bug once graded a whole scenario as an agent failure.
    if not ws.is_dir():
        raise RuntimeError(
            f"workspace {ws} does not exist when reading workspace_files; "
            "the fact must be collected before the temporary workspace is "
            "cleaned up, otherwise absence of files is unmeasurable"
        )

    matched: list[Path] = []
    seen: set[Path] = set()
    for pattern in cfg:
        # Anchor every match inside the workspace. A pattern escaping upward
        # (``../``) would quote harness files into the judge prompt, where they
        # would read as the agent's work.
        for path in sorted(ws.glob(pattern)):
            resolved = path.resolve()
            if not resolved.is_file():
                continue
            if not resolved.is_relative_to(ws.resolve()):
                continue
            # The staged skill pack ships reference data products whose files
            # carry exactly the names a scenario asks about. They are input the
            # harness placed, not output the agent wrote, and a recursive
            # pattern matches dozens of them — enough to exhaust the quoting
            # budget and starve the agent's own files, which is how a correct
            # run graded FAIL for "requirements.txt was not quoted".
            if any(part in _STAGED_INPUT_DIRS for part in resolved.parts):
                continue
            if resolved not in seen:
                seen.add(resolved)
                matched.append(path)

    # Shallowest first, so the agent's own top-level files are quoted before any
    # deeper match. Depth is the only signal available for "most likely to be
    # the answer" and the budget is finite; without this the ordering is
    # alphabetical and a nested directory can crowd out the real output.
    matched.sort(key=lambda p: (len(p.relative_to(ws).parts), p.as_posix()))

    if not matched:
        # State the absence explicitly. Silence would let the judge fall back to
        # the transcript and re-introduce exactly the evidence guesswork this
        # exists to remove.
        return ("WORKSPACE FILES: NONE — the harness looked for "
                f"{', '.join(cfg)} in the agent's workspace after the run and "
                "found no such file. Any check about the content of those files "
                "must FAIL: they were never written.")

    sections: list[str] = []
    budget = WORKSPACE_FILE_BUDGET
    omitted: list[str] = []
    for path in matched:
        rel = path.relative_to(ws).as_posix()
        try:
            body = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            sections.append(f"--- {rel} (UNREADABLE: {exc}) ---")
            continue
        if len(body) > budget:
            # Never silently truncate a file into the judge prompt: a check
            # about a missing annotation would then fail on a cut that the
            # harness made, which is the same false signal in a new place.
            omitted.append(rel)
            continue
        budget -= len(body)
        sections.append(f"--- {rel} ({len(body)} bytes) ---\n{body}")

    note = ""
    if omitted:
        note = ("\nNOTE: these files exceeded the quoting budget and are NOT "
                f"shown: {', '.join(omitted)}. Do not infer anything about "
                "their contents either way.")

    return ("WORKSPACE FILES (read by the harness from the agent's workspace "
            "after the run — this is the agent's actual output, authoritative "
            "over anything the transcript does or does not show; grade content "
            "checks about these files from here, NOT from whether the agent "
            "echoed them):\n" + "\n".join(sections) + note)


def _fixtures_fingerprint(scenario_dir: Path) -> str:
    """Hash the scenario fixtures so a fixture edit invalidates the cache."""
    h = hashlib.sha256()
    fixtures = scenario_dir / "fixtures"
    if fixtures.is_dir():
        for f in sorted(fixtures.rglob("*")):
            # __pycache__/*.pyc headers embed source mtimes, so hashing them
            # churns the cache key on every import even when no fixture content
            # changed. Skip them (mirrors the build_workspace exclusion).
            if f.is_file() and "__pycache__" not in f.parts:
                h.update(f.relative_to(scenario_dir).as_posix().encode())
                h.update(f.read_bytes())
    return h.hexdigest()[:16]


def _agent_cache_key(skill_set: SkillSet, scenario_dir: Path, prompt: str,
                     backend: str, model: str, effort: str) -> str:
    """Cache key for an agent run. Independent of the judge / checks.json, so
    iterating on grading reuses the expensive agent transcript. Includes the
    agent backend so switching provider (claude ↔ codex) never reuses the other
    provider's transcript."""
    h = hashlib.sha256()
    pocket_runtime_key = ""
    if scenario_needs_pocket(scenario_dir) is not None:
        pocket_runtime_key = "|".join((
            os.environ.get("EVAL_POCKET_SUPERVISOR_DIR", ""),
            os.environ.get("EVAL_POCKET_PYTHON", ""),
        ))
    for part in (
        skill_set.name,
        ",".join(sorted(skill_set.skills)),
        scenario_dir.name,
        prompt,
        backend,
        model,
        effort,
        _fixtures_fingerprint(scenario_dir),
        pocket_runtime_key,
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

    agent_backend = get_agent_backend(args.agent_backend)
    judge_backend = get_judge_backend(args.judge_backend)

    # Codex has no --plugin-dir skill activation: the skills are staged into the
    # workspace and the agent is told where to read them. Claude activates them
    # as a plugin, so its prompt gets no skill-file hint. `has_skills` is only
    # relevant for the file-hint (baseline no_skills skips it either way).
    skills_in_workspace = (
        agent_backend.name != "claude" and bool(skill_set.skills)
    )

    pocket_spec = scenario_needs_pocket(scenario_dir)
    # Pocket cells run the agent with extra_dirs=[] (see the agent call below),
    # so the prompt must not advertise an examples directory the agent can never
    # --add-dir, or it wastes turns hunting for it.
    extra_dirs = [] if pocket_spec is not None else (
        [EXAMPLES_DIR] if EXAMPLES_DIR.is_dir() else []
    )
    prompt = build_agent_prompt(
        agent_task, args.docs_base, bool(extra_dirs),
        skills_in_workspace=skills_in_workspace,
    )
    agent_model = effective_agent_model(
        pocket_spec is not None, agent_backend.name, args.agent_model
    )
    preflight_metrics: dict[str, object] = {}
    if pocket_spec is not None:
        # Run the infrastructure gate even when an agent transcript is cached:
        # a rebuild can drift from the closure/skill contract between runs.
        with tempfile.TemporaryDirectory(prefix="eval-pocket-runtime-") as runtime_tmp:
            try:
                preflight_bin, preflight_env, _ = _pocket_runtime(
                    scenario_dir, Path(runtime_tmp)
                )
                preflight_error = pocket_preflight(
                    scenario_dir, preflight_bin, preflight_env
                )
            except RuntimeError as exc:
                preflight_error = str(exc)
        if preflight_error:
            # Deliberately stable: callers distinguish this infrastructure
            # error from an agent FAIL without parsing build-specific details.
            res.error = "pocket preflight failed"
            res.metrics["pocket_preflight_error"] = preflight_error
            return res
        preflight_metrics["pocket_preflight"] = "passed"
        if _POCKET_PREFLIGHT_ENDPOINT:
            preflight_metrics["pocket_preflight_endpoint"] = _POCKET_PREFLIGHT_ENDPOINT

    # Agent step (cacheable). The agent run is the slow/expensive part; cache it
    # keyed on everything that affects the transcript so judge-only iteration is
    # cheap. The judge is never cached (it's cheap and the rubric changes often).
    cache_dir = Path(args.cache_dir) if args.cache_dir else None
    cache_file = None
    if cache_dir:
        key = _agent_cache_key(
            skill_set, scenario_dir, prompt, agent_backend.name,
            agent_model, args.agent_effort,
        )
        cache_file = cache_dir / f"agent-{key}.json"

    cached = None
    facts: list[str] = []
    ws_fact: str | None = None
    det_fact: str | None = None
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
        facts = list(cached.get("facts", []))
        ok = True
    else:
        # MCP scenarios run a live Streamable-HTTP semantic server + a fake `nxd`
        # on PATH so the query skill's shipped HTTP toolchain drives the real
        # tools. Tool calls reach Snowflake, so allow a longer timeout.
        mcp_spec = scenario_needs_mcp(scenario_dir)
        agent_timeout = (
            max(args.agent_timeout, MCP_AGENT_TIMEOUT_S)
            if mcp_spec is not None
            else max(args.agent_timeout, POCKET_AGENT_TIMEOUT_S)
            if pocket_spec is not None
            else args.agent_timeout
        )
        with tempfile.TemporaryDirectory(prefix=f"eval-{skill_set.name}-{name}-") as tmp:
            try:
                ws, plugin_dir = build_workspace(
                    Path(tmp), skill_set, scenario_dir,
                    stage_skills_in_workspace=skills_in_workspace,
                )
            except FileNotFoundError as exc:
                res.error = str(exc)
                return res

            if mcp_spec is not None:
                bin_dir = Path(tmp) / "bin"
                bin_dir.mkdir(parents=True, exist_ok=True)
                _write_fake_nxd(bin_dir)
                try:
                    with semantic_http_server(scenario_dir, mcp_spec) as (_ep, env_over):
                        ok, trace, metrics = agent_backend.run_agent(
                            ws, prompt, agent_model, agent_timeout,
                            extra_dirs=extra_dirs, effort=args.agent_effort,
                            env_overrides=env_over, path_prepend=bin_dir,
                            skill_pack_dir=plugin_dir,
                        )
                except (RuntimeError, TimeoutError) as exc:
                    res.error = f"MCP server setup failed: {exc}"
                    return res
            elif pocket_spec is not None:
                try:
                    bin_dir, env_over, pocket_python = _pocket_runtime(
                        scenario_dir, Path(tmp)
                    )
                except RuntimeError as exc:
                    res.error = f"pocket runtime setup failed: {exc}"
                    return res
                # Both the agent forcing-function checker and the pristine
                # harness verifier place snapshot state under the workspace so
                # pocket_process_guard can clean it after normal exit, timeout,
                # or a killed verifier subprocess.
                env_over = {
                    **env_over,
                    "NXD_POCKET_CHECK_TMPDIR": str(ws / ".pocket-check-tmp"),
                }
                # Keep the workspace until the pristine verifier has re-served
                # its snapshots. The guard then runs on all outcomes, including
                # a timed-out Claude process.
                with pocket_process_guard(
                    ws, bin_dir / "nxd-desktop-supervisor", env_over
                ):
                    # Pocket narrows the tool allowlist (no web/docs escape
                    # hatch). Backends that gate per-tool (Claude) honour it;
                    # sandbox-based ones (Codex) ignore it, so a pocket run is
                    # not comparable across providers.
                    pocket_kwargs = {"allowed_tools": POCKET_AGENT_ALLOWED_TOOLS}
                    ok, trace, metrics = agent_backend.run_agent(
                        ws, prompt, agent_model, agent_timeout,
                        extra_dirs=[], effort=args.agent_effort,
                        env_overrides=env_over, path_prepend=bin_dir,
                        skill_pack_dir=plugin_dir, **pocket_kwargs,
                    )
                    if checks.get("pocket_verify"):
                        facts.append(pocket_harness_fact(
                            scenario_dir, ws, pocket_python,
                            str(pocket_spec.get("workflow", "invoice-pulse")), bin_dir, env_over
                        ))
            else:
                ok, trace, metrics = agent_backend.run_agent(
                    ws, prompt, agent_model, agent_timeout,
                    extra_dirs=extra_dirs, effort=args.agent_effort,
                    skill_pack_dir=plugin_dir,
                )

            # Read the produced files INSIDE the `with`, while the temporary
            # workspace still exists. Outside it the directory is already
            # deleted and every pattern silently matches nothing, which the
            # fact then reports as "never written" — a confident-looking claim
            # that is purely an artefact of reading too late.
            ws_fact = (
                workspace_files_fact(ws, checks.get("workspace_files"))
                if ok else None
            )
            # Same reason as ws_fact: the checker reads the landed closure off
            # disk, so it has to run before the temporary workspace is removed.
            if ok and checks.get("deterministic_check"):
                det_fact = deterministic_check_fact(
                    scenario_dir, ws, checks["deterministic_check"], trace
                )

        # Never cache a transcript whose facts carry a verifier infrastructure
        # failure: the workspace is gone on a later cache hit, so the verifier
        # cannot re-run and run_one would re-report the transient failure
        # forever. Drop the cache entry so the next run re-verifies from scratch.
        #
        # `facts` deliberately does NOT include the workspace-files fact yet: on
        # a cache hit the workspace no longer exists, and replaying quoted file
        # contents as authoritative ground truth would describe a run that never
        # happened.
        if ok and cache_file and pocket_facts_infrastructure_error(facts) is None:
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(
                json.dumps({"trace": trace, "metrics": metrics, "facts": facts}),
                encoding="utf-8",
            )

        if ws_fact:
            facts.append(ws_fact)
        # Appended after the cache write for the same reason as ws_fact: the
        # verdict it carries belongs to THIS run's workspace, and replaying it
        # on a later cache hit would describe a closure that was never checked.
        if det_fact:
            facts.append(det_fact)

    if cached and checks.get("workspace_files"):
        # A cached transcript has no workspace behind it, so the files cannot be
        # read. Say so rather than letting the judge silently fall back to
        # transcript-guessing, which is the failure mode this replaces.
        facts.append(
            "WORKSPACE FILES: UNAVAILABLE — this run replayed a cached agent "
            "transcript, so the workspace no longer exists and the produced "
            "files could not be read. Grade file-content checks as unproven "
            "rather than inferring them from the transcript."
        )

    if cached and checks.get("deterministic_check"):
        # No workspace behind a cached transcript, so there is no landed closure
        # to check. Record the skip explicitly: silently treating an unrun
        # deterministic gate as a pass is exactly the hole this stage closes.
        det_status = "skipped: cached transcript, no workspace"
        facts.append(
            "DETERMINISTIC CHECK: UNAVAILABLE — this run replayed a cached agent "
            "transcript, so the workspace no longer exists and the closure's "
            "numbers could not be verified. Grade numeric-correctness checks as "
            "unproven rather than inferring them from the transcript."
        )
    elif checks.get("deterministic_check"):
        det_status = "passed" if deterministic_check_passed(facts) else "failed"
    else:
        det_status = ""

    res.transcript = trace
    res.metrics = {**preflight_metrics, **metrics, "agent_model": agent_model}
    if det_status:
        res.metrics["deterministic_check"] = det_status
        if det_status == "failed":
            res.metrics["deterministic_check_detail"] = deterministic_check_detail(facts)
    res.facts = facts
    if not ok:
        res.error = str(metrics.get("error", "agent run failed"))
        return res

    verifier_infrastructure_error = pocket_facts_infrastructure_error(facts)
    if verifier_infrastructure_error:
        res.error = f"pocket harness infrastructure failure: {verifier_infrastructure_error}"
        return res

    det_infrastructure_error = deterministic_check_infrastructure_error(facts)
    if det_infrastructure_error:
        # A checker that could not run says nothing about the agent. Report it
        # as infrastructure so it is not counted as an agent FAIL in the ledger.
        res.error = f"deterministic check infrastructure failure: {det_infrastructure_error}"
        return res

    final_answer = metrics.get("final_answer", "")
    res.verdict = run_judge(
        judge_backend, scenario_dir, checks, trace, final_answer,
        args.judge_model, args.judge_timeout, effort=args.judge_effort,
        facts=facts,
    )
    if checks.get("pocket_verify") and not pocket_facts_passed(facts):
        # The verifier re-serves the actual published closure and is the hard
        # acceptance gate; facts are not merely advisory evidence for the judge.
        res.verdict["overall_pass"] = False
        prior = str(res.verdict.get("summary", ""))
        res.verdict["summary"] = (
            f"{prior} Pocket verifier did not pass; the cell is mechanically failed."
        ).strip()
    if det_status == "failed":
        # The checker computes the answer from ground truth; it is the hard
        # acceptance gate, not advisory evidence. A closure whose numbers are
        # wrong fails the cell however generously the judge read the transcript.
        res.verdict["overall_pass"] = False
        prior = str(res.verdict.get("summary", ""))
        res.verdict["summary"] = (
            f"{prior} {DETERMINISTIC_CHECK_FAILED}: "
            f"{res.metrics['deterministic_check_detail']}"
        ).strip()
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
    parser.add_argument("--agent-backend", default=DEFAULT_AGENT_BACKEND,
                        choices=AGENT_BACKENDS,
                        help="Provider driving the agent-under-test "
                             f"(default: {DEFAULT_AGENT_BACKEND}).")
    parser.add_argument("--judge-backend", default=DEFAULT_JUDGE_BACKEND,
                        choices=JUDGE_BACKENDS,
                        help="Provider driving the judge "
                             f"(default: {DEFAULT_JUDGE_BACKEND}).")
    parser.add_argument("--agent-model", default=None,
                        help="Agent model. Default resolves from --agent-backend "
                             f"({DEFAULT_MODELS}).")
    parser.add_argument("--judge-model", default=None,
                        help="Judge model. Default resolves from --judge-backend.")
    parser.add_argument("--agent-effort", default=None,
                        help="Reasoning effort for the agent (low|medium|high|"
                             "xhigh|max; '' = CLI default). Default resolves "
                             f"from --agent-backend (claude: "
                             f"{DEFAULT_AGENT_EFFORT}, codex: "
                             f"{CODEX_DEFAULT_AGENT_EFFORT}).")
    parser.add_argument("--judge-effort", default=None,
                        help="Reasoning effort for the judge. Default resolves "
                             f"from --judge-backend (claude: "
                             f"{DEFAULT_JUDGE_EFFORT}, codex: "
                             f"{CODEX_DEFAULT_JUDGE_EFFORT}).")
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

    # Resolve per-backend default models when not overridden on the CLI, so
    # `--agent-backend codex` picks a codex model id (not Claude's "sonnet").
    if args.agent_model is None:
        args.agent_model = DEFAULT_MODELS[args.agent_backend]["agent"]
    if args.judge_model is None:
        args.judge_model = DEFAULT_MODELS[args.judge_backend]["judge"]

    # Same for reasoning effort: codex's scale has no "xhigh", so an unset
    # effort resolves per-backend. An explicit --agent-effort / --judge-effort
    # (including "") always wins.
    if args.agent_effort is None:
        args.agent_effort = (
            CODEX_DEFAULT_AGENT_EFFORT if args.agent_backend == "codex"
            else DEFAULT_AGENT_EFFORT
        )
    if args.judge_effort is None:
        args.judge_effort = (
            CODEX_DEFAULT_JUDGE_EFFORT if args.judge_backend == "codex"
            else DEFAULT_JUDGE_EFFORT
        )

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
            "agent_backend": args.agent_backend,
            "judge_backend": args.judge_backend,
            "agent_model": args.agent_model,
            "scenario_agent_models": {
                scenario.name: effective_agent_model(
                    scenario_needs_pocket(scenario) is not None,
                    args.agent_backend,
                    args.agent_model,
                )
                for scenario in scenarios
            },
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
                    "facts": r.facts,
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
        # Efficiency alongside correctness: a skill edit that keeps PASS but
        # doubles turns/tool-calls/tokens is a regression worth seeing here.
        eff = "  ".join(
            f"{k}={r.metrics[k]}"
            for k in ("num_turns", "tool_calls", "output_tokens")
            if r.metrics.get(k) is not None
        )
        print(f"  {label}  {status}  ({n_pass}/{n_total} checks)  {eff}",
              file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
