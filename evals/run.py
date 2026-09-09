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
import dataclasses
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
import traceback
from dataclasses import dataclass, field
from pathlib import Path

from eval_backends import (
    AGENT_BACKENDS,
    JUDGE_BACKENDS,
    BackendDependencyError,
    TURN_BOUNDARY_SENTINEL as AWAITING_INPUT_MARKER,
    FollowupTurn,
    get_agent_backend,
    get_judge_backend,
    parse_followup_turns,
)
from desktop_stdio import DesktopStdioError, DesktopStdioSession, redact_text


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
# desktop's proven smoke invocation is deliberately narrower than the generic
# eval harness: no web/docs escape hatch and no helper tools beyond the local
# file + shell surface. Skill remains essential: without it the installed
# plugin bodies never activate, so this would not measure the local desktop skills.
# It stays here because it is a *scenario* constraint, not a provider default;
# it is applied only on the Claude backend (see run_one), the only provider that
# has a per-tool allowlist to narrow.
# Naming rule for the two prefixes this file mixes, so a future sweep has one to
# follow: JOB_ names the *loop* — the scenario shape this harness drives, matching
# the nxd-run-job-loop skill and the job-loop-* scenarios. DESKTOP_/desktop names
# the *runtime* being driven — the supervisor, its binaries, its env vars and its
# opt-in marker, none of which this repo owns. NXD_JOB_CHECK_TMPDIR pointing at
# .desktop-check-tmp is therefore correct, not a straggler: the loop's checker
# writes into the runtime's scratch dir.
JOB_AGENT_ALLOWED_TOOLS = "Bash,Read,Write,Edit,Glob,Grep,Skill"

# Semantic-MCP scenarios. A scenario opts in by shipping fixtures/mcp.json:
#   {"tools": ["list_models","describe_model","run_semantic_query"],
#    "dp": "semantic-demo", "rpc_port": "mcp-api"}
# When present, run.py starts evals/mcp/semantic_server.py as a Streamable-HTTP
# MCP server (via uv / EVAL_MCP_PYTHON, so its heavy deps — the real
# nxd.experimental.semantic compiler + Snowflake connector — stay out of the
# stdlib-only runner) and puts a fake `nxd` on the agent's PATH so the
# nxd-query-data-product skill's shipped HTTP toolchain (`nxd mcp health` +
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
JOB_RUNNER_SIDE_FIXTURES = {
    # These fixtures are trusted runner inputs. The agent gets data/ and the
    # checker, but never the known-good preflight closure or opt-in marker.
    "desktop.json",
    "desktop_stdio.json",
    "prepare_stdio_profile.py",
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
STATIC_ARTIFACT_RUNNER_SIDE_FIXTURES = {
    # The checker states the exact render order, required glosses and forbidden
    # payload fields. Handing it to the agent turns "follow the skill contract"
    # into "satisfy this file", which is the opposite of what the scenario
    # measures. Scoped to this scenario rather than to every scenario declaring
    # a deterministic_check, so other scenarios' workspaces are unchanged.
    # (The bridge-read-*.json fixtures stay in the workspace — prompt.md points
    # the agent at them as reference transport shapes.)
    "check_static_artifact.py",
}
EXECUTABLE_POLICY_RUNNER_SIDE_FIXTURES = {
    # The checker hardcodes EDITED_ADVANCE_THRESHOLD = "4.25" — the value the
    # SCRIPTED TURN 2 introduces. Staging it hands the agent the user's
    # correction before the user makes it, so an agent that reads its own
    # workspace could pre-empt the edit and the round-trip half of the rubric
    # would measure nothing. It also names the card gates, which would turn
    # "propose an executable policy" into "satisfy this file".
    "check_executable_policy.py",
}

# A desktop custom-contract checker is unstaged evaluator input, not a prompt
# input: staging it lets the agent optimize to the checker instead of authoring
# the closure. Being unstaged is not inherently unreadable from the source
# checkout; the protected scenario's configured source-isolation wrapper must
# independently block that path. This is intentionally scenario-local; another
# scenario may use the same filename as an ordinary fixture and must keep it.
SCENARIO_WORKSPACE_FIXTURE_EXCLUSIONS = {
    "terminal-timeout-lifecycle": frozenset({
        "stub_slow_paginated_api.py",
        "check_terminal_timeout_lifecycle.py",
    }),
    "desktop-custom-contracts": frozenset({"check_custom_contracts.py"}),
    # The terminal mapper checker is withheld from the agent; it is runner-side
    # oracle material and is passed directly to the deterministic subprocess.
    "terminal-field-mapper-adapter-contract": frozenset({"check_terminal_mapper_adapter.py"}),
    # The self-check provenance checker is runner-side oracle material and must
    # not be staged into the agent workspace.
    "terminal-self-check-provenance": frozenset({"check_terminal_self_check.py"}),
    "multi-source-labeled-roots": frozenset({"check_labeled_multi_source.py"}),
    "multi-source-labeled-roots-supervisor": frozenset({"check_supervisor_pin.py"}),
    # Names the banned host/path literals and the exact connector architecture
    # it grades — staged into the workspace it would turn "build this the
    # documented way" into "satisfy this file".
    "worldbank-live": frozenset({"check_worldbank_connector.py"}),
    # Harness only, unlike job-loop's check_job_loop.py which the agent runs as
    # a forcing function: this verifier computes the exact per-team check counts
    # a correct product must reproduce, which is the answer key to the brief's
    # question 1, and it imports runner-side modules the workspace does not have.
    "authenticated-api-source-supervisor": frozenset({"check_api_source_e2e.py"}),
    # The optional-output desktop verifier is runner-side ground truth: it
    # re-serves the landed closure and checks the catalog/query contract.
    "optional-empty-output-aggregate-desktop": frozenset({
        "check_optional_empty_aggregate.py",
    }),
    # The incremental scenario's delta and deterministic checker are runner-side
    # oracle material. The agent receives only the initial export; the runner
    # adds the delta immediately before the third transform invocation.
    "incremental-transform-state": frozenset({
        "check_incremental_state.py",
        "delta",
    }),
}

INCREMENTAL_FOLLOWUP_WORKSPACE_SETUP_ID = (
    "incremental-transform-state:stage-delta-before-followup"
)


def _stage_incremental_delta_before_followup(
    scenario_dir: Path, workspace: Path, turn_index: int
) -> None:
    """Add the withheld source delta immediately before incremental turn 2.

    The delta is runner-owned oracle input: it must be absent from the initial
    workspace, but the agent must see it after the scripted user says the
    source has gained rows. ``run_one`` removes this staged copy after the
    agent finishes, before the deterministic checker replays its own timeline.
    """
    if scenario_dir.name != "incremental-transform-state" or turn_index != 2:
        return
    source = scenario_dir / "fixtures" / "delta" / "part-0003.csv"
    target = workspace / "data_product" / "data" / "events" / source.name
    if not source.is_file():
        raise FileNotFoundError(f"incremental delta fixture missing: {source}")
    if target.exists():
        raise FileExistsError(
            f"incremental delta target already exists before follow-up: {target}"
        )
    if not target.parent.is_dir():
        raise FileNotFoundError(
            f"incremental delta target directory missing before follow-up: "
            f"{target.parent}"
        )
    shutil.copy2(source, target)


def _remove_incremental_delta_after_agent(
    scenario_dir: Path, workspace: Path
) -> None:
    """Restore the base export before the checker replays its three runs."""
    if scenario_dir.name != "incremental-transform-state":
        return
    target = workspace / "data_product" / "data" / "events" / "part-0003.csv"
    target.unlink(missing_ok=True)

_SOURCE_ISOLATION_FINGERPRINT = re.compile(r"[0-9a-fA-F]{64}\Z")
_SOURCE_ISOLATION_MARKER_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,63}\Z")


@dataclass(frozen=True)
class SourceIsolationProbe:
    """One wrapper-enforced protected-source probe, without a resolved path."""

    probe_id: str
    target: str
    fixture: str | None
    root: str | None
    command: tuple[str, ...]


@dataclass(frozen=True)
class SourceIsolation:
    """Operator-attested source-isolation evidence for one protected cell."""

    capability_id: str
    profile_fingerprint: str
    wrapper_path: str
    wrapper_sha256: str
    markers: tuple[tuple[str, str], ...]
    probes: tuple[SourceIsolationProbe, ...]
    roots: tuple[tuple[str, str], ...]

    def identity(self) -> dict[str, object]:
        return {
            "capability_id": self.capability_id,
            "profile_fingerprint": self.profile_fingerprint,
            "wrapper_path": self.wrapper_path,
            "wrapper_sha256": self.wrapper_sha256,
            "markers": [
                {"id": marker_id, "needle_sha256": hashlib.sha256(needle.encode()).hexdigest()}
                for marker_id, needle in self.markers
            ],
            "probes": [
                {
                    "id": probe.probe_id,
                    "target": probe.target,
                    "fixture": probe.fixture,
                    "root": probe.root,
                    "command_sha256": hashlib.sha256("\\0".join(probe.command).encode()).hexdigest(),
                }
                for probe in self.probes
            ],
            "root_sha256": {
                name: hashlib.sha256(value.encode()).hexdigest()
                for name, value in self.roots
            },
        }

# Scenario-specific: the stub module's filename is excluded per-scenario (added
# to this set below, keyed by scenario) because its payload/auth/pagination
# logic is the answer key the agent must instead discover by calling the live
# endpoint — exactly why MCP_SERVER_SIDE_FIXTURES hides catalog.json/semantic.json.
# How the VERIFIER subprocess learns where the stub's request log is. The stub
# itself is handed the path on its module instance (see http_stub_server) —
# cells share a process, so an env var cannot address one cell's stub. This is
# set only on the verifier's own environment, never on the agent's. Mirrors
# stub_beacon_api.OBSERVATIONS_ENV; the two are pinned together by
# test_api_source_supervisor_e2e.py so a rename cannot silently disable the log.
STUB_OBSERVATIONS_ENV = "NXD_STUB_OBSERVATIONS"

HTTP_STUB_RUNNER_SIDE_FIXTURES = {
    "http_stub.json",  # runner opt-in marker, parallel to mcp.json/desktop.json
    "stub_beacon_api.py",  # authenticated-api-source-build's stub module/answer key
    "check_authenticated_api_source.py",  # its deterministic checker: states
    # the exact expected row counts (12 monitors, 37 checks) and every trap by
    # name, which would turn "discover the payload's shape" into "satisfy this
    # file" — same reasoning as DERIVATION_RUNNER_SIDE_FIXTURES excluding
    # check_derived_closure.py.
}
# MCP tool calls reach Snowflake (lower-env). Each call is slower than a local
# file read, so MCP scenarios get a longer agent timeout.
MCP_AGENT_TIMEOUT_S = 1800
# A genuine generate -> serve -> refine run starts a local kernel twice and is
# intentionally much slower than mocked eval cells.
JOB_AGENT_TIMEOUT_S = 2400
# The verified local smoke used Opus 4.8.  Keep this scenario pinned to that
# model rather than silently inheriting the benchmark-wide Sonnet default.
JOB_AGENT_MODEL = "claude-opus-4-8"


def effective_agent_model(is_desktop: bool, backend_name: str, default_model: str) -> str:
    """Resolve the model a scenario actually runs on.

    desktop is pinned to a verified Claude model, but that id is meaningless to
    any other provider, so the pin applies only on the Claude backend. The
    dispatch path and the report must agree on this or a report attributes a
    Codex desktop run to a Claude model and poisons benchmark evidence.
    """
    if is_desktop and backend_name == "claude":
        return JOB_AGENT_MODEL
    return default_model
# The verifier may legitimately re-serve the final snapshot plus several
# earlier published snapshots.  Give that work most of the agent budget, then
# report a timeout as runner infrastructure rather than an agent failure.
JOB_HARNESS_TIMEOUT_S = 1800
_JOB_PREFLIGHT_LOCK = threading.Lock()
_JOB_PREFLIGHT_DONE = False
_JOB_PREFLIGHT_ERROR: str | None = None
_JOB_PREFLIGHT_ENDPOINT: str | None = None

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
    / "src" / "nxd-build-data-product" / "reference" / "nextdata-public-examples"
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


def _copy_skill_tree(src: Path, dst: Path) -> None:
    """Stage skill content without carrying repository/submodule metadata."""
    # A submodule's `.git` is often a *file* pointing at the shared checkout's
    # object store, rather than a directory.  Ignore by basename recursively so
    # neither shape reaches the plugin nor Codex's workspace-visible skill copy.
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(".git"))


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
            _copy_skill_tree(src, skills_dst / src.name)
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
                _copy_skill_tree(src, ws_skills / src.name)

    fixtures = scenario_dir / "fixtures"
    if fixtures.is_dir():
        scenario_exclusions = SCENARIO_WORKSPACE_FIXTURE_EXCLUSIONS.get(
            scenario_dir.name, frozenset()
        )
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
            # Scenario-local exclusions are merely unstaged. They do not make
            # a source checkout unreadable; protected cells prove that with
            # their separately configured source-isolation wrapper.
            if (item.name.startswith(".") or item.name == "__pycache__"
                    or item.name in MCP_SERVER_SIDE_FIXTURES | JOB_RUNNER_SIDE_FIXTURES
                    | STATIC_ARTIFACT_RUNNER_SIDE_FIXTURES
                    | DERIVATION_RUNNER_SIDE_FIXTURES
                    | EXECUTABLE_POLICY_RUNNER_SIDE_FIXTURES
                    | HTTP_STUB_RUNNER_SIDE_FIXTURES
                    or item.name in scenario_exclusions):
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
    source_isolation: bool = False,
) -> str:
    """Prepend the shared context every skill-set gets (docs + examples).

    ``skills_in_workspace`` is set for providers that cannot activate skills as a
    plugin (Codex): the skill dirs are staged under ``<workspace>/.skills/`` and
    this adds a line telling the agent to read them, so the skill guidance is
    available as context. Providers that activate skills natively (Claude) leave
    this False — the skills load through the Skill tool, not by file-reading."""
    if source_isolation:
        lines = [
            "You are working on a Nextdata OS (nxd) data-product task.",
            "",
            "Available context (protected evaluation):",
            "- Every permitted task input and example is already materialized as "
            "ordinary files inside your workspace. Inspect those workspace files first.",
            "- You may use system and desktop executables available on PATH when the "
            "task requires them.",
            "- Do not discover, list, read, or execute task inputs, examples, repo "
            "source, histories, or rubrics outside the workspace. Do not use git, "
            "submodules, or another checkout to find them.",
        ]
    else:
        # Keep this branch byte-for-byte stable for ordinary scenarios: their
        # public-docs and mounted-examples contract remains unchanged.
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
    if has_examples and not source_isolation:
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


def scenario_needs_desktop(scenario_dir: Path) -> dict | None:
    """Return the local desktop runtime marker when a scenario opts into the local
    desktop supervisor. Kept parallel to MCP opt-in so ordinary cells never
    inherit a host binary, Python venv, or persistent-process cleanup."""
    marker = scenario_dir / "fixtures" / "desktop.json"
    if not marker.exists():
        return None
    return json.loads(marker.read_text(encoding="utf-8"))


def scenario_needs_desktop_stdio(scenario_dir: Path) -> dict | None:
    """Return the runner-owned stdio MCP marker for a terminal scenario."""
    marker = scenario_dir / "fixtures" / "desktop_stdio.json"
    if not marker.exists():
        return None
    return json.loads(marker.read_text(encoding="utf-8"))


def _prepare_stdio_profile(
    scenario_dir: Path,
    desktop_spec: dict,
    workspace: Path,
    output: Path,
    python: str,
) -> None:
    """Build a sealed synthetic profile outside the agent workspace."""
    builder = scenario_dir / "fixtures" / str(desktop_spec["profile_builder"])
    if not builder.is_file():
        raise RuntimeError(f"stdio profile builder not found: {builder}")
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    proc = subprocess.run(
        [python, str(builder), "--workspace", str(workspace), "--output", str(output)],
        cwd=workspace, capture_output=True, text=True, timeout=30,
        env={
            "PATH": os.environ.get("PATH", ""),
            "PYTHONPATH": os.environ.get("PYTHONPATH", ""),
            "EVAL_NXD_REPO_ROOT": os.environ.get("EVAL_NXD_REPO_ROOT", ""),
        },
    )
    if proc.returncode != 0:
        detail = redact_text(proc.stderr.strip() or proc.stdout.strip() or "profile builder failed")
        raise RuntimeError(f"stdio evaluation profile setup failed: {detail[-1000:]}")
    if not output.is_file():
        raise RuntimeError("stdio profile builder did not create its output")
    output.chmod(0o444)


def _desktop_stdio_session(
    scenario_dir: Path,
    desktop_spec: dict,
    workspace: Path,
    tmp: Path,
) -> tuple[Path, dict[str, str], str, DesktopStdioSession]:
    """Build one runner-owned stdio session and its isolated runtime inputs."""
    bin_dir, env_over, desktop_python = _desktop_runtime(scenario_dir, tmp)
    profile_path = tmp / "stdio-profile.json"
    _prepare_stdio_profile(
        scenario_dir, desktop_spec, workspace, profile_path, desktop_python
    )
    state_dir = tmp / "stdio-state"
    server_args = [
        "--data-dir", str(state_dir),
        "mcp", "serve",
        "--evaluation-profile", str(profile_path),
    ]
    session = DesktopStdioSession(
        [bin_dir / "nxd-desktop-supervisor", *server_args],
        server_env={**env_over, "NXD_DESKTOP_PYTHON": desktop_python},
        root=tmp / "stdio-session",
        server_name=str(desktop_spec.get("server_name", "nxd-desktop")),
        allowed_tools=desktop_spec.get("allowed_tools"),
        request_timeout_faults=desktop_spec.get("request_timeout_faults"),
        startup_timeout_s=30.0,
    )
    return bin_dir, env_over, desktop_python, session


def scenario_needs_http_stub(scenario_dir: Path) -> dict | None:
    """Return the HTTP-stub marker when a scenario opts into a runner-started
    local REST fixture. Kept parallel to the MCP/desktop opt-ins for the same
    reason: ordinary cells must not inherit a background process, and only a
    scenario that names ``fixtures/http_stub.json`` gets one.

    Marker shape: ``{"module": "<py filename under fixtures/>",
    "start": "<callable name>", "stop": "<callable name>",
    "endpoint_file": "<workspace-relative path the base URL is written to>"}``.
    ``start`` must return ``(server, port, thread)``; ``stop`` takes those same
    three (minus port). This is intentionally generic — the module supplies its
    own routes/auth/payload, the runner only supplies the process lifecycle and
    the port handoff, exactly as ``semantic_http_server`` supplies lifecycle for
    the (heavier, license-gated) semantic MCP server.

    Two optional keys, both load-bearing where they appear (implemented in
    ``http_stub_server``, which carries the full reasoning):

    ``"fixtures_from": "<sibling scenario name>"``
        Resolve ``module`` from THAT scenario's ``fixtures/`` instead of this
        one's, so two scenarios ingesting the same fixture share one file
        rather than a copy that drifts.
    ``"observations": true``
        Back the stub with a request log outside the workspace, yielded
        alongside the base URL and reachable by a separate verifier process.
        Requires the module to define ``set_observations_path(path | None)``
        — the runner hands the path to that one module instance rather than
        through ``os.environ``, because cells share a process and a global
        would cross-wire concurrent runs. The runner sets the env var for the
        verifier subprocess only, never for the agent.

    Lifecycle contract: a combined stdio+HTTP run performs its deterministic
    check while this runner-owned stub is still alive. An HTTP-only run performs
    its deterministic check after this context exits, so that checker must
    create its own fixture if it needs a live HTTP service.
    """
    marker = scenario_dir / "fixtures" / "http_stub.json"
    if not marker.exists():
        return None
    return json.loads(marker.read_text(encoding="utf-8"))


def _desktop_runtime(scenario_dir: Path, tmp: Path) -> tuple[Path, dict[str, str], str]:
    """Return a narrow command directory and the matched Python interpreter."""
    supervisor_dir = Path(os.environ.get("EVAL_DESKTOP_SUPERVISOR_DIR", "")).expanduser()
    python = os.environ.get("EVAL_DESKTOP_PYTHON", "").strip()
    if not supervisor_dir.is_dir() or not python:
        raise RuntimeError(
            "set EVAL_DESKTOP_SUPERVISOR_DIR (both desktop binaries) and "
            "EVAL_DESKTOP_PYTHON (supervisor venv Python)"
        )
    binaries = ("nxd-desktop-supervisor", "nxd-desktop-kernel-host")
    missing = [name for name in binaries if not (supervisor_dir / name).is_file()]
    if missing or not Path(python).is_file():
        raise RuntimeError(
            f"desktop runtime missing binaries={missing} or Python={python!r}"
        )
    # The supervisor finds its kernel-host sibling from its *real* executable
    # path, so tiny exec wrappers preserve that contract while exposing only the
    # two intended desktop commands to the evaluated agent.  Do not symlink: the
    # detached implementation historically re-execed through current_exe().
    bin_dir = tmp / "desktop-bin"
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


def _desktop_kv(output: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in output.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


@dataclass
class DesktopServe:
    """Foreground supervisor process plus its startup transcript files."""

    process: subprocess.Popen
    stdout: object
    stderr: object
    values: dict[str, str]
    bearer: str


def _desktop_start_serve(supervisor: Path, definition: Path, workflow: str,
                        data_dir: Path, env: dict[str, str],
                        timeout_s: int = 300) -> DesktopServe:
    """Start documented foreground ``serve`` and wait for real publication.

    ``create --detach`` can report ``published=yes`` while its child has already
    lost its inherited lifecycle context.  Runner-owned setup deliberately uses
    the same foreground command agents are asked to use, with a direct Popen
    handle held until ``stop`` reaps it.
    """
    bearer = f"eval-desktop-{secrets.token_urlsafe(24)}"
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
        values = _desktop_kv(output)
        if values.get("published") == "yes":
            return DesktopServe(proc, stdout, stderr, values, bearer)
        if proc.poll() is not None:
            stderr.seek(0)
            detail = stderr.read()
            stdout.close()
            stderr.close()
            raise RuntimeError(f"foreground serve exited before publication: {detail[-1200:]}")
        time.sleep(0.1)
    _sweep_desktop_pid(proc.pid)
    stdout.seek(0)
    stderr.seek(0)
    detail = f"stdout={stdout.read()[-600:]} stderr={stderr.read()[-600:]}"
    stdout.close()
    stderr.close()
    raise RuntimeError(f"foreground serve did not publish within {timeout_s}s: {detail}")


def _desktop_stop_serve(supervisor: Path, data_dir: Path, served: DesktopServe,
                       env: dict[str, str]) -> None:
    """Stop a foreground desktop serve and close runner-owned log handles."""
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
        _sweep_desktop_pid(pid)
    if served.process.poll() is None:
        _sweep_desktop_pid(served.process.pid)
    with contextlib.suppress(subprocess.TimeoutExpired):
        served.process.wait(timeout=10)
    served.stdout.close()
    served.stderr.close()


def _sweep_stale_preflights(supervisor: Path, env: dict[str, str]) -> None:
    """Recover a preflight abandoned by SIGKILL or an interrupted runner."""
    for root in Path(tempfile.gettempdir()).glob("eval-desktop-preflight-*"):
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
                    _sweep_desktop_pid(int((data_dir / name).read_text(encoding="utf-8").strip()))
        shutil.rmtree(root, ignore_errors=True)


def desktop_preflight(scenario_dir: Path, bin_dir: Path, env_overrides: dict[str, str]) -> str | None:
    """Serve/describe/query/stop the committed closure once per runner.

    A broken local build is infrastructure failure, not evidence an agent could
    not use the skills. The memoized result is shared across parallel cells.
    """
    global _JOB_PREFLIGHT_DONE, _JOB_PREFLIGHT_ERROR, _JOB_PREFLIGHT_ENDPOINT
    with _JOB_PREFLIGHT_LOCK:
        if _JOB_PREFLIGHT_DONE:
            return _JOB_PREFLIGHT_ERROR
        _JOB_PREFLIGHT_DONE = True
        reference = scenario_dir / "fixtures" / "reference-closure"
        supervisor = bin_dir / "nxd-desktop-supervisor"
        if not reference.is_dir():
            _JOB_PREFLIGHT_ERROR = "reference closure is missing"
            return _JOB_PREFLIGHT_ERROR
        env = dict(os.environ)
        env.update(env_overrides)
        env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
        _sweep_stale_preflights(supervisor, env)
        tmp = Path(tempfile.mkdtemp(prefix="eval-desktop-preflight-"))
        (tmp / ".owner-pid").write_text(str(os.getpid()), encoding="utf-8")
        data_dir = tmp / "state"
        served: DesktopServe | None = None
        try:
            try:
                served = _desktop_start_serve(
                    supervisor, reference, "desktop-preflight", data_dir, env
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
                _JOB_PREFLIGHT_ENDPOINT = endpoint
                print(f"Desktop preflight OK: semantic_endpoint={endpoint}",
                      file=sys.stderr, flush=True)
            except (OSError, subprocess.TimeoutExpired, RuntimeError, json.JSONDecodeError) as exc:
                _JOB_PREFLIGHT_ERROR = str(exc)
        finally:
            if served is not None:
                _desktop_stop_serve(supervisor, data_dir, served, env)
            else:
                with contextlib.suppress(OSError, subprocess.TimeoutExpired):
                    subprocess.run([str(supervisor), "stop", "--data-dir", str(data_dir)],
                                   capture_output=True, text=True, timeout=60, env=env)
            shutil.rmtree(tmp, ignore_errors=True)
        return _JOB_PREFLIGHT_ERROR


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _sweep_desktop_pid(pid: int) -> None:
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
def desktop_process_guard(ws: Path, supervisor: Path, env_overrides: dict[str, str]):
    """Always stop persistent supervisors created by a desktop agent cell."""
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
                    _sweep_desktop_pid(int(pid_file.read_text(encoding="utf-8").strip()))
                except (OSError, ValueError):
                    pass


def desktop_harness_fact(scenario_dir: Path, ws: Path, python: str, workflow: str,
                        bin_dir: Path, env_overrides: dict[str, str],
                        verifier: str = "check_job_loop.py") -> str:
    """Run the pristine verifier before the temporary workspace disappears.

    ``verifier`` comes from ``desktop.json``. It defaults to the job-loop
    checker every desktop scenario shipped when this was a fixed filename — a
    scenario verifying a different closure shape (an api-source E2E, say) names
    its own instead of overloading that one.
    """
    checker = scenario_dir / "fixtures" / verifier
    if not checker.is_file():
        return "JOB VERIFY (authoritative runner facts): " + json.dumps(
            {"passed": False,
             "infrastructure_error": f"desktop verifier not found: {checker}"},
            sort_keys=True,
        )
    env = dict(os.environ)
    # A runner-owned observation path is meaningful only when this verifier was
    # explicitly given one. Never let a parent process point the checker at a
    # different cell's log (or at a stale log from an earlier run).
    env.pop(STUB_OBSERVATIONS_ENV, None)
    env.update(env_overrides)
    env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
    # Snapshot re-serves must be visible to desktop_process_guard even if this
    # verifier times out after its child supervisor was spawned.
    checker_tmp = ws / ".desktop-check-tmp"
    checker_tmp.mkdir(parents=True, exist_ok=True)
    env["NXD_JOB_CHECK_TMPDIR"] = str(checker_tmp)
    try:
        proc = subprocess.run(
            [python, str(checker), "--mode", "harness", "--workspace", str(ws),
             "--workflow", workflow],
            capture_output=True, text=True, timeout=JOB_HARNESS_TIMEOUT_S, env=env,
        )
        lines = [line for line in proc.stdout.splitlines() if line.strip()]
        if not lines:
            facts = {
                "passed": False,
                "infrastructure_error": "desktop harness verifier emitted no facts",
            }
        else:
            facts = json.loads(lines[-1])
        facts["harness_exit_code"] = proc.returncode
    except subprocess.TimeoutExpired as exc:
        facts = {
            "passed": False,
            "infrastructure_error": (
                f"desktop harness verifier timed out after {JOB_HARNESS_TIMEOUT_S}s: {exc}"
            ),
        }
    except (OSError, json.JSONDecodeError) as exc:
        facts = {
            "passed": False,
            "infrastructure_error": f"desktop harness verifier failed: {exc}",
        }
    return "JOB VERIFY (authoritative runner facts): " + json.dumps(facts, sort_keys=True)


def desktop_facts_passed(facts: list[str]) -> bool:
    """Return whether an authoritative desktop verifier fact explicitly passed.

    A desktop cell is fail-closed: missing, malformed, timed-out, or negative
    verifier output must not be rescued by a lenient LLM judge.
    """
    prefix = "JOB VERIFY (authoritative runner facts): "
    for fact in facts:
        if fact.startswith(prefix):
            try:
                return json.loads(fact[len(prefix):]).get("passed") is True
            except json.JSONDecodeError:
                return False
    return False


def desktop_facts_infrastructure_error(facts: list[str]) -> str | None:
    """Return a verifier infrastructure failure, if one was recorded."""
    prefix = "JOB VERIFY (authoritative runner facts): "
    for fact in facts:
        if fact.startswith(prefix):
            try:
                error = json.loads(fact[len(prefix):]).get("infrastructure_error")
            except json.JSONDecodeError:
                return "desktop verifier facts were malformed"
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


def _private_text_file(
    directory_prefix: str, filename: str, text: str
) -> tuple[tempfile.TemporaryDirectory, Path]:
    """Create a runner-owned 0600 text file and its private temp directory."""
    holder = tempfile.TemporaryDirectory(prefix=directory_prefix)
    path = Path(holder.name) / filename

    def opener(file_path: str, flags: int) -> int:
        return os.open(file_path, flags | os.O_CREAT | os.O_EXCL, 0o600)

    try:
        with open(path, "w", encoding="utf-8", opener=opener) as handle:
            handle.write(text)
    except BaseException:
        holder.cleanup()
        raise
    return holder, path


def deterministic_check_fact(
    scenario_dir: Path,
    ws: Path,
    cfg: dict,
    trace: str = "",
    *,
    env_overrides: dict[str, str] | None = None,
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

    For combined stdio+HTTP scenarios this is called while the runner-owned
    HTTP stub is alive. HTTP-only scenarios call it after the stub context has
    exited; such a checker must start its own fixture if it needs live HTTP.
    """
    fixtures = scenario_dir / "fixtures"
    script = fixtures / str(cfg.get("script", ""))
    if not script.is_file():
        return DETERMINISTIC_CHECK_PREFIX + json.dumps(
            {"passed": False,
             "infrastructure_error": f"checker not found: {script}"},
            sort_keys=True,
        )
    # ``trace`` is normally the agent transcript. A Desktop stdio scenario
    # supplies the proxy's runner-authored JSON-RPC trace instead; unlike the
    # transcript it cannot be spoofed by printing tool names.
    trace_source = cfg.get("trace_source")
    if trace_source not in (None, "transcript", "runner_mcp"):
        return DETERMINISTIC_CHECK_PREFIX + json.dumps(
            {"passed": False, "infrastructure_error": f"unknown trace source: {trace_source!r}"},
            sort_keys=True,
        )
    if trace_source == "runner_mcp" and not trace.strip():
        return DETERMINISTIC_CHECK_PREFIX + json.dumps(
            {"passed": False, "infrastructure_error": "runner-authored MCP trace is empty"},
            sort_keys=True,
        )
    # An OMITTED `deps` takes the duckdb default (most checkers read a landed
    # DuckDB). An explicitly EMPTY list means none: a static checker that never
    # opens a database should not pay for the install, and `"deps": []` has to
    # mean what it says or checks.json is describing a run that isn't happening.
    deps = cfg.get("deps")
    if deps is None:
        deps = ["duckdb"]
    cmd = ["uv", "run", "--no-project"]
    for dep in deps:
        cmd += ["--with", str(dep)]
    cmd += ["python", str(script), "--fixtures", str(fixtures), "--root", str(ws)]
    private_files: list[tempfile.TemporaryDirectory] = []
    try:
        # A checker may need to prove redaction of a runner-supplied synthetic
        # secret. Pass it through a runner-owned 0600 file, never argv: argv is
        # visible to other processes and may be echoed into CI diagnostics.
        raw_markers = cfg.get("redaction_markers", [])
        if not isinstance(raw_markers, list):
            return DETERMINISTIC_CHECK_PREFIX + json.dumps(
                {"passed": False, "infrastructure_error": "redaction_markers must be a list"},
                sort_keys=True,
            )
        markers = [str(marker) for marker in raw_markers if str(marker)]
        if markers:
            marker_holder, marker_file = _private_text_file(
                "nxd-eval-markers-", "markers.txt", "\n".join(markers) + "\n"
            )
            private_files.append(marker_holder)
            cmd += ["--secret-marker-file", str(marker_file)]
        if cfg.get("wants_trace"):
            trace_holder, trace_file = _private_text_file(
                "nxd-eval-trace-", "trace.txt", trace
            )
            private_files.append(trace_holder)
            cmd += ["--trace", str(trace_file)]
        checker_env = dict(os.environ)
        # The observation path is a per-run capability. Inheriting it from the
        # parent would let a no-log checker read or truncate an unrelated log.
        checker_env.pop(STUB_OBSERVATIONS_ENV, None)
        if env_overrides:
            checker_env.update(env_overrides)
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=DETERMINISTIC_CHECK_TIMEOUT_S, env=checker_env,
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
    except OSError as exc:
        return DETERMINISTIC_CHECK_PREFIX + json.dumps(
            {"passed": False, "infrastructure_error": f"checker input staging failed: {exc}"},
            sort_keys=True,
        )
    finally:
        for holder in private_files:
            holder.cleanup()
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

    This mirrors production: the nxd-query-data-product skill discovers DP MCP
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


class HttpStubSetupError(RuntimeError):
    """A fault in bringing the stub up — not a fault in the agent run.

    The two must stay distinguishable: `run_agent` executes INSIDE the stub's
    `with` block, so a bare `except RuntimeError` there records a skill or
    backend failure as "http stub setup failed" and points the operator at the
    fixture instead of the thing that broke.
    """


class HttpStubTeardownError(RuntimeError):
    """A fault while stopping or cleaning up the HTTP stub."""


def _redacted_exception_detail(exc: BaseException) -> str:
    """Format an exception and its notes without exposing fixture secrets."""
    detail = redact_text(str(exc))
    if not isinstance(exc, (HttpStubSetupError, HttpStubTeardownError)):
        detail = f"{type(exc).__name__}: {detail}"
    notes = getattr(exc, "__notes__", ())
    if notes:
        detail += " (" + "; ".join(redact_text(str(note)) for note in notes) + ")"
    return detail


@contextlib.contextmanager
def http_stub_server(scenario_dir: Path, ws: Path, spec: dict, agent_backend_name: str = ""):
    """Start a scenario-supplied in-process HTTP stub for the run's duration.

    Runs the fixture module's own ``start``/``stop`` callables IN this process
    (unlike ``semantic_http_server``, which shells to a separate interpreter for
    a heavy licensed dependency) — the stub is stdlib-only `http.server`, so no
    subprocess or extra interpreter is needed. Writes the base URL to
    ``spec["endpoint_file"]`` inside the workspace before yielding, so the agent
    reads it exactly like any other fixture file; the port itself is chosen
    fresh per run via ``socket.bind(("127.0.0.1", 0))`` inside the module.
    """
    # `fixtures_from` borrows another scenario's stub instead of copying it. Two
    # scenarios ingesting from the same fixture must serve the SAME payload,
    # auth and header gate, or the pair stops being comparable — and a copy
    # drifts silently, which is worse than either scenario having no stub.
    borrowed = str(spec.get("fixtures_from", "")).strip()
    fixtures_dir = scenario_dir / "fixtures"
    if borrowed:
        fixtures_dir = scenario_dir.parent / borrowed / "fixtures"
        if not fixtures_dir.is_dir():
            raise HttpStubSetupError(
                f"http_stub fixtures_from names no such scenario: {borrowed}")
    module_name = str(spec.get("module", "")).removesuffix(".py")
    module_path = fixtures_dir / f"{module_name}.py"
    if not module_path.is_file():
        raise HttpStubSetupError(f"http_stub module not found: {module_path}")

    # A file-backed request log, for scenarios whose verifier is a SEPARATE
    # process and must answer "did the closure the supervisor materialized
    # actually reach this fixture, carrying the required header?". The module's
    # in-memory OBSERVED cannot cross that boundary.
    #
    # Deliberately outside the workspace, and handed to the stub through the
    # module instance loaded just above — never through os.environ. Cells run in
    # a thread pool inside ONE process (see the ThreadPoolExecutor in main), so a
    # process-global would let two concurrent cells write into one another's
    # logs, and the first to exit would unset it under the other. The env var is
    # for the verifier subprocess only, and is set on that call, not here: in the
    # agent's environment it would hand back the headers its own failing requests
    # carried, turning "diagnose an unexplained 403" — the task — into a lookup.
    observations: Path | None = None
    log_holder: tempfile.TemporaryDirectory | None = None
    module = None
    setup_complete = False
    setup_error: BaseException | None = None
    setup_cleanup_errors: list[BaseException] = []
    try:
        import importlib.util

        mod_spec = importlib.util.spec_from_file_location(
            f"_eval_http_stub_{module_name}", module_path
        )
        if mod_spec is None or mod_spec.loader is None:
            raise HttpStubSetupError(f"could not load http_stub module: {module_path}")
        module = importlib.util.module_from_spec(mod_spec)
        mod_spec.loader.exec_module(module)

        if spec.get("observations"):
            if not hasattr(module, "set_observations_path"):
                raise HttpStubSetupError(
                    f"{module_path.name} declares observations but defines no "
                    f"set_observations_path(); the runner has no other way to reach "
                    f"one stub instance without affecting the others")
            log_holder = tempfile.TemporaryDirectory(prefix="eval-stub-observations-")

        if log_holder is not None:
            observations = Path(log_holder.name) / "observations.jsonl"
            observations.write_text("", encoding="utf-8")
            module.set_observations_path(observations)

        start_fn = getattr(module, str(spec.get("start", "start_server")))
        stop_fn = getattr(module, str(spec.get("stop", "stop_server")))
        server, port, thread = start_fn()
        setup_complete = True
    except BaseException as exc:
        setup_error = exc
    finally:
        # Anything from here on leaves no server to stop, but the temp dir is
        # already on disk. Without this it survives for the life of the process.
        # Cleanup is also required when KeyboardInterrupt/SystemExit leaves the
        # setup block without entering an Exception handler.
        if not setup_complete and log_holder is not None:
            if module is not None:
                try:
                    module.set_observations_path(None)
                except BaseException as exc:
                    setup_cleanup_errors.append(exc)
            try:
                log_holder.cleanup()
            except BaseException as exc:
                setup_cleanup_errors.append(exc)

    if setup_error is not None:
        control_flow = next(
            (error for error in [setup_error, *setup_cleanup_errors]
             if not isinstance(error, Exception)),
            None,
        )
        if control_flow is not None:
            if control_flow is not setup_error:
                control_flow.add_note(
                    "HTTP stub setup also failed: "
                    f"{_redacted_exception_detail(setup_error)}"
                )
            for cleanup_error in setup_cleanup_errors:
                if cleanup_error is not control_flow:
                    control_flow.add_note(
                        "HTTP stub setup cleanup failed: "
                        f"{_redacted_exception_detail(cleanup_error)}"
                    )
            raise control_flow
        wrapped = HttpStubSetupError(_redacted_exception_detail(setup_error))
        for cleanup_error in setup_cleanup_errors:
            wrapped.add_note(
                "HTTP stub setup cleanup failed: "
                f"{_redacted_exception_detail(cleanup_error)}"
            )
        raise wrapped from None
    if setup_cleanup_errors:
        control_flow = next(
            (error for error in setup_cleanup_errors if not isinstance(error, Exception)),
            None,
        )
        if control_flow is not None:
            raise control_flow
        wrapped = HttpStubSetupError(
            "setup cleanup failed: "
            + "; ".join(_redacted_exception_detail(error)
                         for error in setup_cleanup_errors)
        )
        raise wrapped from None

    pending: BaseException | None = None
    try:
        try:
            base_url = f"http://127.0.0.1:{port}"
            endpoint_file = ws / str(spec.get("endpoint_file", "ENDPOINT_URL"))
            endpoint_file.parent.mkdir(parents=True, exist_ok=True)
            endpoint_file.write_text(base_url + "\n", encoding="utf-8")

            # The stub is useless unless the AGENT can reach it, and the agent's
            # sandbox is not this process's. Codex's default `workspace-write`
            # implements isolation with a network namespace, so the agent's curl gets
            # `Failed to connect to 127.0.0.1` while this process talks to the same
            # port happily — verified, not theorised.
            #
            # Left unchecked, that produces the worst possible outcome: the run
            # completes, every data-dependent check fails for want of data, and the
            # report reads as a skill regression. The scenario is unrunnable under
            # that sandbox, so say so here rather than grading a run that never had
            # a source. CI already exports EVAL_CODEX_AGENT_SANDBOX=danger-full-access
            # (`.github/workflows/evals.yml`); a local run needs the same.
            if agent_backend_name == "codex" and os.environ.get(
                    "EVAL_CODEX_AGENT_SANDBOX", "").strip() in ("", "workspace-write"):
                raise HttpStubSetupError(
                    f"scenario needs a runner-started HTTP stub at {base_url}, but the "
                    "codex agent sandbox is 'workspace-write', which blocks loopback "
                    "network from the agent's shell. The agent would see connection "
                    "refused and every data-dependent check would fail as though the "
                    "skills regressed. Re-run with "
                    "EVAL_CODEX_AGENT_SANDBOX=danger-full-access (what CI uses), or "
                    "with --agent-backend claude."
                )
        except HttpStubSetupError as exc:
            raise HttpStubSetupError(redact_text(str(exc))) from None
        except Exception as exc:
            raise HttpStubSetupError(_redacted_exception_detail(exc)) from None

        yield base_url, observations
    except BaseException as exc:
        # Capture the exception actually propagating from the whole post-start
        # region, including endpoint-file setup. `sys.exc_info()` in a finally
        # block can refer to an unrelated exception handled by an outer frame,
        # causing a teardown failure to disappear.
        pending = exc
        raise
    finally:
        # Cleanup runs even if stop_fn raises: a stub that failed to shut down
        # cleanly must not also strand its log directory for the whole run.
        teardown_errors: list[BaseException] = []
        try:
            stop_fn(server, thread)
        except BaseException as exc:
            teardown_errors.append(exc)
        finally:
            if log_holder is not None:
                try:
                    module.set_observations_path(None)
                except BaseException as exc:
                    teardown_errors.append(exc)
                finally:
                    try:
                        log_holder.cleanup()
                    except BaseException as exc:
                        teardown_errors.append(exc)
        if teardown_errors:
            control_flow = next(
                (error for error in teardown_errors if not isinstance(error, Exception)),
                None,
            )
            if control_flow is not None and isinstance(pending, Exception):
                control_flow.add_note(
                    "HTTP stub body failed: "
                    f"{_redacted_exception_detail(pending)}"
                )
                raise control_flow
            details = "; ".join(
                _redacted_exception_detail(error) for error in teardown_errors
            )
            if pending is not None:
                pending.add_note(f"HTTP stub teardown failed: {details}")
            elif control_flow is not None:
                raise control_flow
            else:
                raise HttpStubTeardownError(details) from None


@contextlib.contextmanager
def desktop_stdio_runtime(
    scenario_dir: Path,
    workspace: Path,
    tmp: Path,
    desktop_spec: dict,
    http_spec: dict | None = None,
    agent_backend_name: str = "",
):
    """Own one isolated stdio Desktop session, optionally with an HTTP fixture.

    The HTTP fixture is the outer context so its endpoint file exists while a
    scenario's stdio profile builder runs. It also remains bound until the
    caller has finished any deterministic verification that needs the request
    log. The yielded observation path is runner-only and is never put in the
    agent environment. This is the combined stdio+HTTP lifecycle; HTTP-only
    deterministic checks run after their stub context exits.
    """
    stub_ctx: contextlib.AbstractContextManager = (
        http_stub_server(scenario_dir, workspace, http_spec, agent_backend_name)
        if http_spec is not None
        else contextlib.nullcontext((None, None))
    )
    with stub_ctx as (_stub_url, stub_observations):
        bin_dir, env_over, desktop_python, session = _desktop_stdio_session(
            scenario_dir, desktop_spec, workspace, tmp
        )
        with session:
            yield bin_dir, env_over, desktop_python, session, stub_observations


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


def build_scripted_turns_block(checks: dict, metrics: dict | None = None) -> str:
    """Describe the scripted user turns to the judge, or "" for single-turn.

    Without this the judge reads a transcript in which the agent suddenly
    adopts a correction it was handed, cannot attribute it to the user, and may
    credit the agent for the user's idea. The turns are quoted verbatim, and the
    turns that did NOT fire are named so their checks are not graded against a
    conversation that never happened.
    """
    turns = checks.get("turns") or []
    if not turns:
        return ""
    skipped = set((metrics or {}).get("skipped_turns") or [])
    # Turns default to `when: "always"`, so a turn arriving proves nothing about
    # whether the agent stopped for it. `awaited_input_turns` records which turns
    # ENDED with the boundary sentinel, which is the only signal separating "the
    # user answered a question the agent asked" from "the harness talked over an
    # agent that had already barrelled on". Without it in the prompt the judge
    # reads an unconditional delivery as evidence of a checkpoint that may never
    # have happened — and a scenario grading "did it stop and ask" would pass
    # while measuring nothing.
    awaited = set((metrics or {}).get("awaited_input_turns") or [])
    lines = [
        "\n--- SCRIPTED USER TURNS (supplied by the HARNESS, not authored by "
        "the agent — the agent's first message answers the task above; these "
        "arrived afterwards as the user speaking) ---"
    ]
    for i, turn in enumerate(turns):
        index = i + 2  # turn 1 is the scenario prompt
        status = " [NOT SENT]" if index in skipped else ""
        lines.append(f'  [user_turn {index}]{status} {turn.get("text", "")}')
    # Report the stop/no-stop verdict for the turn each scripted message
    # FOLLOWED, since that is the turn whose ending is under grading.
    for i, _turn in enumerate(turns):
        index = i + 2
        if index in skipped:
            continue
        # Walk back to the last turn that actually RAN. Indices are positional,
        # so they do not renumber around a skip — `index - 1` can name a turn
        # that was never sent, and the fact would then be stated about a turn
        # with no ending to grade.
        preceding = index - 1
        while preceding in skipped:
            preceding -= 1
        if preceding in awaited:
            lines.append(
                f"  HARNESS FACT: before [user_turn {index}], the agent ended "
                f"turn {preceding} with the {AWAITING_INPUT_MARKER} marker — it "
                f"stopped and waited for the user."
            )
        else:
            lines.append(
                f"  HARNESS FACT: the agent did NOT end turn {preceding} with "
                f"the {AWAITING_INPUT_MARKER} marker. [user_turn {index}] was "
                f"delivered unconditionally by the harness, NOT because the "
                f"agent asked for input. Any check about the agent stopping, "
                f"pausing, or waiting for approval at that point MUST be failed "
                f"— the conversation continuing is the harness's doing, not "
                f"evidence the agent yielded."
            )
    if skipped:
        lines.append(
            "  A turn marked [NOT SENT] never reached the agent, because the "
            "agent did not signal it was waiting for input. Any check tagged "
            "with that turn number MUST be failed with the reason \"turn not "
            "sent\" — do not grade it against this transcript, and do not "
            "credit the agent for behaviour the turn would have prompted."
        )
    return "\n".join(lines) + "\n"


def build_judge_prompt(scenario_dir: Path, checks: dict, trace: str,
                       final_answer: str, facts: list[str] | None = None,
                       metrics: dict | None = None) -> str:
    prompt_md = (scenario_dir / "prompt.md").read_text(encoding="utf-8")
    check_lines = "\n".join(
        f'  {i + 1}. [id={c["id"]}]'
        + (f' (about user_turn {c["turn"]})' if c.get("turn") else "")
        + f' {c["check"]}'
        for i, c in enumerate(checks["checks"])
    )
    scripted_turns = build_scripted_turns_block(checks, metrics)
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
{scripted_turns}
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

For desktop scenarios, direct writes to the agent-owned supervisor state under
`.desktop/state/` (`state.sqlite*` or `definitions/**`) outside an
`nxd-desktop-supervisor` command are an automatic FAIL for the
supervisor-state-integrity check and therefore for the whole cell. The
runner-owned `.desktop-check-tmp/` is explicitly excluded from this rule because
it holds verifier snapshot re-serves. In particular, do not excuse SQLite
inserts, copied/edited pinned snapshots, or shell redirection in `.desktop/state`
merely because the final re-served output is plausible. Use the harness-provided
published-run timestamps and definition SHA-256s to cross-check the trace
chronology.

Respond with ONE JSON object and nothing else, in this exact shape:
{{"checks": [{{"id": "<id>", "pass": true|false, "why": "<one sentence>"}}],
  "overall_pass": true|false, "summary": "<one sentence>"}}"""


def run_judge(judge_backend, scenario_dir: Path, checks: dict, trace: str,
              final_answer: str, model: str, timeout_s: int,
              effort: str = "", facts: list[str] | None = None,
              metrics: dict | None = None) -> dict:
    """Grade one transcript. Builds the provider-independent judge prompt (which
    folds in the harness-verified ``facts`` and, for multi-turn scenarios, the
    scripted user turns), then delegates the actual model call to the selected
    judge backend."""
    prompt = build_judge_prompt(
        scenario_dir, checks, trace, final_answer, facts, metrics
    )
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
_STAGED_INPUT_DIRS = frozenset({".skills", ".claude", "fixtures", ".desktop"})


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
                     backend: str, model: str, effort: str,
                     followup_turns: list[FollowupTurn] | None = None,
                     source_isolation_identity: dict[str, object] | None = None,
                     workspace_setup_id: str | None = None) -> str:
    """Cache key for an agent run. Independent of the judge and of checks.json's
    GRADING fields, so iterating on the rubric reuses the expensive agent
    transcript. Includes the agent backend so switching provider (claude ↔
    codex) never reuses the other provider's transcript.

    Scripted follow-up turns are hashed in even though they live in checks.json:
    they are not grading, they are agent INPUT that shapes the transcript.
    ``_fixtures_fingerprint`` covers only ``fixtures/``, so without this an
    edited turn script would silently replay a transcript recorded against the
    old wording. A scenario with no turns contributes NOTHING to the hash, so
    every single-turn key predates this change unchanged and no existing cached
    transcript is discarded by multi-turn support merely existing."""
    h = hashlib.sha256()
    desktop_runtime_key = ""
    if (scenario_needs_desktop(scenario_dir) is not None or scenario_needs_desktop_stdio(scenario_dir) is not None):
        desktop_runtime_key = "|".join((
            os.environ.get("EVAL_DESKTOP_SUPERVISOR_DIR", ""),
            os.environ.get("EVAL_DESKTOP_PYTHON", ""),
        ))
    parts = [
        skill_set.name,
        ",".join(sorted(skill_set.skills)),
        scenario_dir.name,
        prompt,
        backend,
        model,
        effort,
        _fixtures_fingerprint(scenario_dir),
        desktop_runtime_key,
    ]
    # APPENDED ONLY when the scenario actually scripts turns. A single-turn
    # scenario must contribute no field at all — even an empty string still
    # feeds its \x00 delimiter into the digest and would invalidate every
    # cached transcript in the repo.
    if followup_turns:
        parts.append(json.dumps(
            [dataclasses.asdict(t) for t in followup_turns], sort_keys=True
        ))
    if source_isolation_identity is not None:
        parts.append(json.dumps(source_isolation_identity, sort_keys=True))
    if workspace_setup_id is not None:
        parts.append(workspace_setup_id)
    for part in parts:
        h.update(part.encode())
        h.update(b"\x00")
    return h.hexdigest()


def _source_isolation_value(args, attr: str, env: str) -> str:
    value = getattr(args, attr, None)
    return str(value if value not in (None, "") else os.environ.get(env, "")).strip()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_isolation_roots(args) -> tuple[dict[str, str] | None, str | None]:
    """Resolve operator-local root aliases without writing their paths to reports."""
    roots: dict[str, str] = {}
    raw_env = os.environ.get("EVAL_SOURCE_ISOLATION_ROOTS", "").strip()
    if raw_env:
        try:
            parsed = json.loads(raw_env)
        except json.JSONDecodeError:
            return None, "EVAL_SOURCE_ISOLATION_ROOTS must be a JSON object"
        if (not isinstance(parsed, dict)
                or not all(isinstance(k, str) and isinstance(v, str) and v for k, v in parsed.items())):
            return None, "EVAL_SOURCE_ISOLATION_ROOTS must map symbolic names to non-empty strings"
        roots.update(parsed)
    for raw in getattr(args, "source_isolation_roots", None) or []:
        if not isinstance(raw, str) or "=" not in raw:
            return None, "--source-isolation-root must be NAME=PATH"
        name, value = raw.split("=", 1)
        if not name or not value:
            return None, "--source-isolation-root must be NAME=PATH"
        roots[name] = value
    canonical: dict[str, str] = {}
    for name, value in roots.items():
        path = Path(value)
        if not path.is_absolute():
            return None, f"source-isolation root {name!r} must be absolute"
        try:
            resolved = path.resolve(strict=True)
        except OSError:
            return None, f"source-isolation root {name!r} does not exist"
        # Require the exact canonical spelling. A symlink (including one in an
        # ancestor) lets the raw-stream marker and wrapper probe describe the
        # same protected root differently.
        if path != resolved:
            return None, f"source-isolation root {name!r} must not traverse a symlink"
        if not resolved.is_file() and not resolved.is_dir():
            return None, f"source-isolation root {name!r} must be a file or directory"
        canonical[name] = str(resolved)
    return canonical, None


def _resolve_source_isolation(
    checks: dict, args, backend_name: str, scenario_dir: Path
) -> tuple[SourceIsolation | None, str | None]:
    """Validate protected-scenario config and its explicit operator attestation.

    The attestation says an operator selected an isolation profile; it is not
    treated as proof. The wrapper probe and raw-stream audit are independent
    evidence and run before an agent transcript can be judged or cached.
    """
    raw = checks.get("agent_source_isolation")
    if not raw:
        return None, None
    if not isinstance(raw, dict):
        return None, "agent_source_isolation must be an object"
    if backend_name != "codex":
        return None, "agent-source isolation requires the configured codex wrapper backend"
    declared_capability = raw.get("capability_id")
    if not isinstance(declared_capability, str) or not declared_capability.strip():
        return None, "agent_source_isolation requires an explicit capability_id"
    capability_id = _source_isolation_value(
        args, "source_isolation_capability_id", "EVAL_SOURCE_ISOLATION_CAPABILITY_ID"
    )
    if not capability_id:
        return None, "missing source-isolation capability ID"
    if capability_id != declared_capability:
        return None, "source-isolation capability ID does not match the scenario requirement"
    profile_fingerprint = _source_isolation_value(
        args, "source_isolation_profile_fingerprint", "EVAL_SOURCE_ISOLATION_PROFILE_FINGERPRINT"
    )
    if not _SOURCE_ISOLATION_FINGERPRINT.fullmatch(profile_fingerprint):
        return None, "source-isolation profile fingerprint must be exactly 64 hexadecimal characters"
    wrapper_value = _source_isolation_value(args, "codex_wrapper", "EVAL_CODEX_WRAPPER")
    if not wrapper_value:
        return None, "missing configured codex wrapper"
    wrapper_candidate = Path(wrapper_value).expanduser()
    wrapper = wrapper_candidate if wrapper_candidate.is_absolute() or "/" in wrapper_value else shutil.which(wrapper_value)
    if not wrapper:
        return None, "configured codex wrapper could not be resolved"
    wrapper_path = Path(wrapper).resolve()
    if not wrapper_path.is_file() or not os.access(wrapper_path, os.X_OK):
        return None, "configured codex wrapper is not an executable file"
    roots, roots_error = _source_isolation_roots(args)
    if roots_error:
        return None, roots_error
    markers_raw = raw.get("raw_stream_markers")
    if not isinstance(markers_raw, list) or not markers_raw:
        return None, "agent_source_isolation requires non-empty raw_stream_markers"
    markers: list[tuple[str, str]] = []
    for marker in markers_raw:
        if not isinstance(marker, dict):
            return None, "source-isolation marker must be an object"
        marker_id = marker.get("id")
        if not isinstance(marker_id, str) or not _SOURCE_ISOLATION_MARKER_ID.fullmatch(marker_id):
            return None, "source-isolation markers need normalized IDs"
        fields = [key for key in ("needle", "target", "root") if key in marker]
        if len(fields) != 1:
            return None, "source-isolation markers need exactly one needle, target, or root"
        if "needle" in marker:
            needle = marker["needle"]
            if not isinstance(needle, str) or not needle:
                return None, "source-isolation marker needles must be non-empty strings"
        elif marker.get("target") == "scenario_checks":
            # The declaration stays machine-independent, but the audit matches
            # the actual runner-side checks path rather than any generated
            # workspace file coincidentally named checks.json.
            needle = str(scenario_dir / "checks.json")
        elif "root" in marker and isinstance(marker["root"], str) and marker["root"] in roots:
            needle = roots[marker["root"]]
        else:
            return None, "source-isolation marker target/root is not configured"
        markers.append((marker_id, needle))
    probes_raw = raw.get("probes")
    if not isinstance(probes_raw, list) or not probes_raw:
        return None, "agent_source_isolation requires non-empty structured probes"
    probes: list[SourceIsolationProbe] = []
    probe_ids: set[str] = set()
    for probe in probes_raw:
        if not isinstance(probe, dict):
            return None, "source-isolation probe must be an object"
        probe_id, target = probe.get("id"), probe.get("target")
        command = probe.get("command")
        if (not isinstance(probe_id, str) or not _SOURCE_ISOLATION_MARKER_ID.fullmatch(probe_id)
                or probe_id in probe_ids or not isinstance(target, str)
                or not isinstance(command, list) or not command
                or not all(isinstance(part, str) and part for part in command)):
            return None, "source-isolation probes need unique normalized IDs, targets, and commands"
        fixture = probe.get("fixture")
        root = probe.get("root")
        if target == "withheld_fixture":
            fixture_path = Path(fixture) if isinstance(fixture, str) else None
            if (fixture_path is None or not fixture or fixture_path.is_absolute()
                    or ".." in fixture_path.parts):
                return None, "withheld-fixture probes need a relative fixture path"
        elif target == "scenario_checks":
            if fixture is not None or root is not None:
                return None, "scenario-checks probes cannot declare fixture/root"
        elif target == "operator_root":
            if not isinstance(root, str) or root not in roots or fixture is not None:
                return None, "operator-root probes need a configured symbolic root"
        else:
            return None, "source-isolation probe has an unknown target"
        if "{target}" not in command:
            return None, "source-isolation probe command must contain {target}"
        probe_ids.add(probe_id)
        probes.append(SourceIsolationProbe(probe_id, target, fixture, root, tuple(command)))
    return SourceIsolation(
        capability_id=capability_id,
        profile_fingerprint=profile_fingerprint.lower(),
        wrapper_path=str(wrapper_path),
        wrapper_sha256=_sha256_file(wrapper_path),
        markers=tuple(markers),
        probes=tuple(probes),
        roots=tuple(sorted(roots.items())),
    ), None


def _source_isolation_probes(isolation: SourceIsolation, scenario_dir: Path) -> tuple[list[dict[str, str]], str | None]:
    """Ask the wrapper to prove every symbolic protected source is blocked.

    The wrapper contract is deliberately small: ``--eval-source-isolation-probe
    -- <command...>`` must emit one JSON object with ``passed: true`` and
    ``status: "blocked"``. No probe target or raw wrapper output enters report
    metrics; only normalized probe IDs and statuses do.
    """
    roots = dict(isolation.roots)
    env = dict(os.environ)
    env.update({
        "EVAL_SOURCE_ISOLATION_CAPABILITY_ID": isolation.capability_id,
        "EVAL_SOURCE_ISOLATION_PROFILE_FINGERPRINT": isolation.profile_fingerprint,
        # The resolved map, so a root supplied via --source-isolation-root is
        # the same set the wrapper denies. Probing a root the sandbox does not
        # know about would report "blocked" for the wrong reason.
        "EVAL_SOURCE_ISOLATION_ROOTS": json.dumps(roots),
    })
    evidence: list[dict[str, str]] = []
    for probe in isolation.probes:
        if probe.target == "withheld_fixture":
            target = scenario_dir / "fixtures" / str(probe.fixture)
            if not target.is_file():
                return evidence, f"source-isolation probe {probe.probe_id} fixture is missing"
        elif probe.target == "scenario_checks":
            target = scenario_dir / "checks.json"
        else:
            target = Path(roots[str(probe.root)])
        command = tuple(str(target) if part == "{target}" else part for part in probe.command)
        try:
            proc = subprocess.run(
                [isolation.wrapper_path, "--eval-source-isolation-probe", "--", *command],
                capture_output=True, text=True, timeout=30, env=env,
            )
        except (OSError, subprocess.TimeoutExpired):
            evidence.append({"id": probe.probe_id, "status": "failed"})
            return evidence, f"source-isolation probe {probe.probe_id} failed to start"
        try:
            payload = json.loads(proc.stdout.strip().splitlines()[-1])
        except (IndexError, json.JSONDecodeError):
            evidence.append({"id": probe.probe_id, "status": "failed"})
            return evidence, f"source-isolation probe {probe.probe_id} returned no structured result"
        if proc.returncode != 0 or not isinstance(payload, dict) or payload.get("passed") is not True or payload.get("status") != "blocked":
            evidence.append({"id": probe.probe_id, "status": "failed"})
            return evidence, f"source-isolation probe {probe.probe_id} did not report blocked access"
        evidence.append({"id": probe.probe_id, "status": "passed"})
    return evidence, None


def _source_access_audit_error(metrics: dict, required: bool) -> str | None:
    if not required:
        return None
    audit = metrics.get("source_access_audit")
    if not isinstance(audit, dict):
        return "source-access audit is unavailable"
    status = audit.get("status")
    if status == "clean":
        return None
    if status == "access_observed":
        ids = audit.get("matched_marker_ids") or []
        return "source-access audit observed attempted access: " + ", ".join(map(str, ids))
    if status == "incomplete":
        return "source-access audit is incomplete"
    return "source-access audit is unavailable"


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

    # Scripted follow-up turns. Absent/empty ⇒ single-turn, which takes exactly
    # the pre-existing path all the way down to the backend.
    try:
        followup_turns = parse_followup_turns(checks.get("turns"))
    except ValueError as exc:
        res.error = f"invalid turns declaration: {exc}"
        return res
    if followup_turns and not getattr(agent_backend, "supports_multi_turn", False):
        # Checked BEFORE a workspace is built or an agent run is burned, and
        # reported as a hard error rather than degrading to single-turn: a
        # turn-1-only transcript graded against a multi-turn rubric reads as an
        # agent regression instead of an unsupported provider.
        res.error = (
            f"scenario scripts {len(followup_turns)} follow-up turn(s); agent "
            f"backend {agent_backend.name!r} cannot drive multi-turn"
        )
        return res

    # Codex has no --plugin-dir skill activation: the skills are staged into the
    # workspace and the agent is told where to read them. Claude activates them
    # as a plugin, so its prompt gets no skill-file hint. `has_skills` is only
    # relevant for the file-hint (baseline no_skills skips it either way).
    skills_in_workspace = (
        agent_backend.name != "claude" and bool(skill_set.skills)
    )

    desktop_spec = scenario_needs_desktop(scenario_dir)
    desktop_stdio_spec = scenario_needs_desktop_stdio(scenario_dir)
    http_stub_spec = scenario_needs_http_stub(scenario_dir)
    # desktop cells run the agent with extra_dirs=[] (see the agent call below),
    # so the prompt must not advertise an examples directory the agent can never
    # --add-dir, or it wastes turns hunting for it.
    extra_dirs = [] if (desktop_spec is not None or desktop_stdio_spec is not None) else (
        [EXAMPLES_DIR] if EXAMPLES_DIR.is_dir() else []
    )
    prompt = build_agent_prompt(
        agent_task, args.docs_base, bool(extra_dirs),
        skills_in_workspace=skills_in_workspace,
        source_isolation=bool(checks.get("agent_source_isolation")),
    )
    agent_model = effective_agent_model(
        (desktop_spec is not None or desktop_stdio_spec is not None), agent_backend.name, args.agent_model
    )
    preflight_metrics: dict[str, object] = {}
    isolation, isolation_error = _resolve_source_isolation(
        checks, args, agent_backend.name, scenario_dir
    )
    if isolation_error:
        res.error = f"source-isolation infrastructure invalid: {isolation_error}"
        return res
    isolation_identity = isolation.identity() if isolation is not None else None
    if isolation is not None:
        probe_metrics, probe_error = _source_isolation_probes(isolation, scenario_dir)
        preflight_metrics["source_isolation_attestation"] = {
            "capability_id": isolation.capability_id,
            "profile_fingerprint": isolation.profile_fingerprint,
            "wrapper_path": isolation.wrapper_path,
            "wrapper_sha256": isolation.wrapper_sha256,
        }
        preflight_metrics["source_isolation_probes"] = probe_metrics
        if probe_error:
            res.metrics = preflight_metrics
            res.error = f"source-isolation infrastructure invalid: {probe_error}"
            return res

    def source_audit_failure(metrics: dict) -> RunResult | None:
        """Stop before any verifier, workspace fact, cache, or judge sees it."""
        audit_error = _source_access_audit_error(metrics, isolation is not None)
        if audit_error is None:
            return None
        res.metrics = {
            **preflight_metrics,
            **metrics,
            "agent_model": agent_model,
        }
        res.error = f"source-isolation infrastructure invalid: {audit_error}"
        return res

    if desktop_spec is not None:
        # Run the infrastructure gate even when an agent transcript is cached:
        # a rebuild can drift from the closure/skill contract between runs.
        with tempfile.TemporaryDirectory(prefix="eval-desktop-runtime-") as runtime_tmp:
            try:
                preflight_bin, preflight_env, _ = _desktop_runtime(
                    scenario_dir, Path(runtime_tmp)
                )
                preflight_error = desktop_preflight(
                    scenario_dir, preflight_bin, preflight_env
                )
            except RuntimeError as exc:
                preflight_error = str(exc)
        if preflight_error:
            # Deliberately stable: callers distinguish this infrastructure
            # error from an agent FAIL without parsing build-specific details.
            res.error = "desktop preflight failed"
            res.metrics["desktop_preflight_error"] = preflight_error
            return res
        preflight_metrics["desktop_preflight"] = "passed"
        if _JOB_PREFLIGHT_ENDPOINT:
            preflight_metrics["desktop_preflight_endpoint"] = _JOB_PREFLIGHT_ENDPOINT

    # Agent step (cacheable). The agent run is the slow/expensive part; cache it
    # keyed on everything that affects the transcript so judge-only iteration is
    # cheap. The judge is never cached (it's cheap and the rubric changes often).
    cache_dir = Path(args.cache_dir) if args.cache_dir else None
    cache_file = None
    if cache_dir:
        workspace_setup_id = (
            INCREMENTAL_FOLLOWUP_WORKSPACE_SETUP_ID
            if followup_turns and name == "incremental-transform-state"
            else None
        )
        key = _agent_cache_key(
            skill_set, scenario_dir, prompt, agent_backend.name,
            agent_model, args.agent_effort, followup_turns,
            source_isolation_identity=isolation_identity,
            workspace_setup_id=workspace_setup_id,
        )
        cache_file = cache_dir / f"agent-{key}.json"

    cached = None
    facts: list[str] = []
    ws_fact: str | None = None
    det_fact: str | None = None
    http_stub_teardown_error: str | None = None
    if cache_file and cache_file.exists():
        try:
            loaded = json.loads(cache_file.read_text(encoding="utf-8"))
            if "trace" in loaded and "metrics" in loaded:
                cached = loaded
        except json.JSONDecodeError:
            cached = None

    if cached and isolation is not None:
        identity_matches = cached.get("source_isolation_identity") == isolation_identity
        audit_error = _source_access_audit_error(cached.get("metrics", {}), True)
        if not identity_matches or audit_error is not None:
            with contextlib.suppress(OSError):
                cache_file.unlink()  # type: ignore[union-attr]
            res.metrics = preflight_metrics
            reason = "identity does not match" if not identity_matches else audit_error
            res.error = f"source-isolation cache entry evicted: {reason}"
            return res

    if cached:
        trace = cached["trace"]
        metrics = {**cached["metrics"], **preflight_metrics, "cached": True}
        facts = list(cached.get("facts", []))
        ok = True
    else:
        # MCP scenarios run a live Streamable-HTTP semantic server + a fake `nxd`
        # on PATH so the query skill's shipped HTTP toolchain drives the real
        # tools. Tool calls reach Snowflake, so allow a longer timeout.
        mcp_spec = scenario_needs_mcp(scenario_dir)
        # Omitted entirely for single-turn scenarios so their call is byte-for-
        # byte what it was, and a backend that never sees the kwarg cannot be
        # perturbed by multi-turn support existing.
        turn_kwargs = {"followup_turns": followup_turns} if followup_turns else {}
        if followup_turns and name == "incremental-transform-state":
            turn_kwargs["before_followup_turn"] = (
                lambda workspace, turn_index: _stage_incremental_delta_before_followup(
                    scenario_dir, workspace, turn_index
                )
            )
        source_audit_kwargs = (
            {
                "source_audit_markers": list(isolation.markers),
                "executable": isolation.wrapper_path,
            }
            if isolation is not None else {}
        )
        source_isolation_env = (
            {
                "EVAL_SOURCE_ISOLATION_CAPABILITY_ID": isolation.capability_id,
                "EVAL_SOURCE_ISOLATION_PROFILE_FINGERPRINT": isolation.profile_fingerprint,
                # Export the RESOLVED root map, not just whatever the operator
                # happened to put in the environment. Roots may arrive via
                # --source-isolation-root, and the wrapper reads them only from
                # this variable — so without this the flag declares a root the
                # harness probes but the sandbox never denies.
                "EVAL_SOURCE_ISOLATION_ROOTS": json.dumps(dict(isolation.roots)),
            }
            if isolation is not None else {}
        )
        agent_timeout = (
            max(args.agent_timeout, MCP_AGENT_TIMEOUT_S)
            if mcp_spec is not None
            else max(args.agent_timeout, JOB_AGENT_TIMEOUT_S)
            if (desktop_spec is not None or desktop_stdio_spec is not None)
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

            runner_mcp_trace: str | None = None
            if mcp_spec is not None:
                bin_dir = Path(tmp) / "bin"
                bin_dir.mkdir(parents=True, exist_ok=True)
                _write_fake_nxd(bin_dir)
                try:
                    with semantic_http_server(scenario_dir, mcp_spec) as (_ep, env_over):
                        ok, trace, metrics = agent_backend.run_agent(
                            ws, prompt, agent_model, agent_timeout,
                            extra_dirs=extra_dirs, effort=args.agent_effort,
                            env_overrides={**env_over, **source_isolation_env}, path_prepend=bin_dir,
                            skill_pack_dir=plugin_dir, **source_audit_kwargs,
                            **turn_kwargs,
                        )
                        failure = source_audit_failure(metrics)
                        if failure is not None:
                            return failure
                except (RuntimeError, TimeoutError) as exc:
                    res.error = f"MCP server setup failed: {exc}"
                    return res
            elif desktop_stdio_spec is not None:
                try:
                    with desktop_stdio_runtime(
                        scenario_dir,
                        ws,
                        Path(tmp),
                        desktop_stdio_spec,
                        http_stub_spec,
                        agent_backend.name,
                    ) as (bin_dir, env_over, desktop_python, session,
                          stub_observations):
                        ok, trace, metrics = agent_backend.run_agent(
                            ws, prompt, agent_model, agent_timeout,
                            extra_dirs=[], effort=args.agent_effort,
                            env_overrides={**env_over, **source_isolation_env},
                            path_prepend=bin_dir, skill_pack_dir=plugin_dir,
                            allowed_tools=str(desktop_stdio_spec.get(
                                "agent_allowed_tools", "mcp__nxd-desktop__*"
                            )),
                            stdio_session=session, **source_audit_kwargs, **turn_kwargs,
                        )
                        runner_mcp_trace = session.trace_path.read_text(encoding="utf-8")
                        metrics["stdio_mcp_trace_source"] = "runner"
                        metrics["stdio_mcp_trace_events"] = len(
                            [line for line in runner_mcp_trace.splitlines() if line.strip()]
                        )
                        if ok and checks.get("deterministic_check"):
                            checker_env = (
                                {STUB_OBSERVATIONS_ENV: str(stub_observations)}
                                if stub_observations is not None else None
                            )
                            det_fact = deterministic_check_fact(
                                scenario_dir, ws, checks["deterministic_check"],
                                runner_mcp_trace,
                                env_overrides=checker_env,
                            )
                except HttpStubSetupError as exc:
                    res.error = f"http stub setup failed: {_redacted_exception_detail(exc)}"
                    return res
                except HttpStubTeardownError as exc:
                    http_stub_teardown_error = (
                        f"http stub teardown failed: {_redacted_exception_detail(exc)}"
                    )
                except (RuntimeError, DesktopStdioError, OSError) as exc:
                    res.error = f"desktop stdio setup failed: {redact_text(str(exc))}"
                    return res
            elif desktop_spec is not None:
                try:
                    bin_dir, env_over, desktop_python = _desktop_runtime(
                        scenario_dir, Path(tmp)
                    )
                except RuntimeError as exc:
                    res.error = f"desktop runtime setup failed: {exc}"
                    return res
                # Both the agent forcing-function checker and the pristine
                # harness verifier place snapshot state under the workspace so
                # desktop_process_guard can clean it after normal exit, timeout,
                # or a killed verifier subprocess.
                env_over = {
                    **env_over,
                    **source_isolation_env,
                    "NXD_JOB_CHECK_TMPDIR": str(ws / ".desktop-check-tmp"),
                }
                # A desktop scenario may ALSO need the runner's local REST
                # fixture: an api-source closure ingests from it, and the
                # supervisor re-materializes on every serve — including the
                # verifier's re-serve of the published snapshot. So the stub
                # must outlive the agent run, on the SAME port. The base_url
                # the agent pinned into infra-profile.yaml is the port the
                # runner bound; restart the stub between the two and the
                # published definition points at a closed socket, which reads
                # as "the closure is broken" rather than "the fixture moved".
                stub_ctx: contextlib.AbstractContextManager = (
                    http_stub_server(scenario_dir, ws, http_stub_spec,
                                     agent_backend.name)
                    if http_stub_spec is not None
                    else contextlib.nullcontext((None, None))
                )
                # Keep the workspace until the pristine verifier has re-served
                # its snapshots. The guard then runs on all outcomes, including
                # a timed-out Claude process.
                try:
                    with stub_ctx as (_stub_url, stub_observations), \
                            desktop_process_guard(
                                ws, bin_dir / "nxd-desktop-supervisor", env_over):
                        # desktop narrows the tool allowlist (no web/docs escape
                        # hatch). Backends that gate per-tool (Claude) honour it;
                        # sandbox-based ones (Codex) ignore it, so a desktop run is
                        # not comparable across providers.
                        desktop_kwargs = {"allowed_tools": JOB_AGENT_ALLOWED_TOOLS}
                        # The guard wraps the WHOLE turn loop: run_agent returns
                        # only once every turn is done, so the cleanup below fires
                        # once at the end and never sweeps a supervisor out from
                        # under a turn still to come.
                        ok, trace, metrics = agent_backend.run_agent(
                            ws, prompt, agent_model, agent_timeout,
                            extra_dirs=[], effort=args.agent_effort,
                            env_overrides=env_over, path_prepend=bin_dir,
                            skill_pack_dir=plugin_dir, **desktop_kwargs,
                            **source_audit_kwargs, **turn_kwargs,
                        )
                        failure = source_audit_failure(metrics)
                        if failure is not None:
                            return failure
                        # Inside the stub context on purpose: the verifier
                        # re-serves the published definition, which
                        # re-materializes the transform and therefore re-fetches
                        # from the fixture.
                        if checks.get("desktop_verify"):
                            verify_env = dict(env_over)
                            if stub_observations is not None:
                                verify_env[STUB_OBSERVATIONS_ENV] = str(stub_observations)
                            facts.append(desktop_harness_fact(
                                scenario_dir, ws, desktop_python,
                                str(desktop_spec.get("workflow", "invoice-pulse")),
                                bin_dir, verify_env,
                                verifier=str(desktop_spec.get(
                                    "verifier", "check_job_loop.py")),
                            ))
                except HttpStubSetupError as exc:
                    res.error = f"http stub setup failed: {_redacted_exception_detail(exc)}"
                    return res
                except HttpStubTeardownError as exc:
                    http_stub_teardown_error = (
                        f"http stub teardown failed: {_redacted_exception_detail(exc)}"
                    )
            elif http_stub_spec is not None:
                # A runner-started local REST fixture the agent reaches over a
                # real socket for the duration of this run — see
                # http_stub_server(). No extra interpreter/subprocess: the stub
                # is stdlib-only and runs in this process.
                try:
                    with http_stub_server(scenario_dir, ws, http_stub_spec,
                                          agent_backend.name):
                        ok, trace, metrics = agent_backend.run_agent(
                            ws, prompt, agent_model, agent_timeout,
                            extra_dirs=extra_dirs, effort=args.agent_effort,
                            skill_pack_dir=plugin_dir, **turn_kwargs,
                        )
                except HttpStubSetupError as exc:
                    res.error = f"http stub setup failed: {_redacted_exception_detail(exc)}"
                    return res
                except HttpStubTeardownError as exc:
                    http_stub_teardown_error = (
                        f"http stub teardown failed: {_redacted_exception_detail(exc)}"
                    )
            else:
                ok, trace, metrics = agent_backend.run_agent(
                    ws, prompt, agent_model, agent_timeout,
                    extra_dirs=extra_dirs, effort=args.agent_effort,
                    env_overrides=source_isolation_env or None,
                    skill_pack_dir=plugin_dir, **source_audit_kwargs,
                    **turn_kwargs,
                )
                failure = source_audit_failure(metrics)
                if failure is not None:
                    return failure

            if ok and name == "incremental-transform-state":
                _remove_incremental_delta_after_agent(scenario_dir, ws)

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
                if runner_mcp_trace is None:
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
        if (
            ok
            and cache_file
            and http_stub_teardown_error is None
            and desktop_facts_infrastructure_error(facts) is None
        ):
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(
                json.dumps({
                    "trace": trace,
                    "metrics": metrics,
                    "facts": facts,
                    "source_isolation_identity": isolation_identity,
                }),
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
    if http_stub_teardown_error is not None:
        # Keep the completed run's evidence available to the caller, but mark
        # the cell as infrastructure-failed and make sure it cannot be cached.
        res.metrics["http_stub_teardown_error"] = http_stub_teardown_error
    if det_status:
        res.metrics["deterministic_check"] = det_status
        if det_status == "failed":
            res.metrics["deterministic_check_detail"] = deterministic_check_detail(facts)
    res.facts = facts
    if not ok:
        res.error = http_stub_teardown_error or str(
            metrics.get("error", "agent run failed")
        )
        return res

    verifier_infrastructure_error = desktop_facts_infrastructure_error(facts)
    if verifier_infrastructure_error:
        res.error = f"desktop harness infrastructure failure: {verifier_infrastructure_error}"
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
        facts=facts, metrics=metrics,
    )
    if checks.get("desktop_verify") and not desktop_facts_passed(facts):
        # The verifier re-serves the actual published closure and is the hard
        # acceptance gate; facts are not merely advisory evidence for the judge.
        res.verdict["overall_pass"] = False
        prior = str(res.verdict.get("summary", ""))
        res.verdict["summary"] = (
            f"{prior} Desktop verifier did not pass; the cell is mechanically failed."
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
    if http_stub_teardown_error is not None:
        res.ok = False
        res.error = http_stub_teardown_error
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
    parser.add_argument("--source-isolation-capability-id", default=None,
                        help="Operator capability ID for protected-source evals "
                             "(or EVAL_SOURCE_ISOLATION_CAPABILITY_ID).")
    parser.add_argument("--source-isolation-profile-fingerprint", default=None,
                        help="Exact 64-hex source-isolation profile fingerprint "
                             "(or EVAL_SOURCE_ISOLATION_PROFILE_FINGERPRINT).")
    parser.add_argument("--codex-wrapper", default=None,
                        help="Configured Codex isolation wrapper executable "
                             "(or EVAL_CODEX_WRAPPER).")
    parser.add_argument("--source-isolation-root", action="append", dest="source_isolation_roots",
                        help="Operator-only symbolic protected root as NAME=PATH; repeatable. "
                             "Alternatively set EVAL_SOURCE_ISOLATION_ROOTS to a JSON object.")
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

    try:
        get_agent_backend(args.agent_backend).check_dependencies()
        get_judge_backend(args.judge_backend).check_dependencies()
    except BackendDependencyError as exc:
        print(f"eval dependency check failed: {exc}", file=sys.stderr)
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
                # `fut.result()` re-raises with the original traceback, so this
                # is the real failure site — a NUL byte reaching argv used to
                # arrive here as a bare "unexpected: embedded null byte" with the
                # traceback and every gathered metric discarded, unattributable
                # to any line of code. Log the full traceback so the cause is
                # recoverable, and carry both the exception type and the
                # traceback tail in the emitted result's metrics so the JSON
                # report preserves them instead of collapsing to a one-liner.
                tb = traceback.format_exc()
                print(
                    f"[unexpected] {ss.name} :: {sc.name}\n{tb}",
                    file=sys.stderr, flush=True,
                )
                res = RunResult(
                    skill_set=ss.name, scenario=sc.name, ok=False,
                    error=f"unexpected {type(exc).__name__}: {exc}",
                    metrics={
                        "unexpected_exception": f"{type(exc).__name__}: {exc}",
                        "traceback": tb[-4000:],
                    },
                )
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
                    scenario_needs_desktop(scenario) is not None,
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
