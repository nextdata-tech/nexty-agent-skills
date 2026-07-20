#!/usr/bin/env python3
"""Pluggable agent + judge backends for the skill-eval runner.

``run.py`` drives a headless agent over each scenario and grades the transcript
with an LLM judge. Both of those are a *provider* choice — historically the
Claude Code CLI (``claude -p``), but the same loop measures any agentic CLI. This
module abstracts the two provider-specific call sites behind small interfaces so
``run.py`` stays provider-agnostic:

  * ``AgentBackend.run_agent(...)`` — drive the agent-under-test in an isolated
    workspace and return ``(ok, trace, metrics)``. The trace is the tool-call
    transcript the judge grades; ``metrics["final_answer"]`` is the answer.
  * ``JudgeBackend.run_judge(...)`` — grade a trace against a prompt and return
    the parsed verdict dict.

Two providers ship:

  * ``claude`` (:class:`ClaudeBackend`) — shells ``claude -p`` with stream-json.
    This is the original behaviour, extracted verbatim; the default.
  * ``codex`` (:class:`CodexBackend`) — shells ``codex exec --json`` (the OpenAI
    Codex CLI). Same subprocess shape, different event vocabulary.

Skill activation differs by provider. Claude loads a skill-set as a plugin via
``--plugin-dir`` (skills become invokable ``<plugin>:<skill>``). Codex has no
equivalent, so :meth:`CodexBackend.run_agent` receives the skill-pack directory
and the caller injects a prompt line pointing the agent at those files — the
skills are *available as context*, not activated through a Skill tool. That is a
real fidelity difference between providers, not a bug; report both numbers as
"provider X with skill-set Y", never as directly comparable to the other
provider.

Stdlib only, to match ``run.py`` (no third-party deps in the runner).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Protocol


# Cap each tool-result block fed to the judge so a huge file read doesn't blow
# up the judge prompt; the head is enough to see what the agent inspected.
TOOL_RESULT_HEAD_CHARS = 1500


# --------------------------------------------------------------------------- #
# Interfaces
# --------------------------------------------------------------------------- #
class AgentBackend(Protocol):
    """Drives the agent-under-test over one scenario workspace."""

    #: Stable identifier used on the CLI (``--agent-backend <name>``) and in
    #: the cache key so switching providers invalidates cached transcripts.
    name: str

    def run_agent(
        self,
        ws: Path,
        prompt: str,
        model: str,
        timeout_s: int,
        *,
        extra_dirs: list[Path] | None = None,
        effort: str = "",
        env_overrides: dict | None = None,
        path_prepend: Path | None = None,
        skill_pack_dir: Path | None = None,
        allowed_tools: str | None = None,
    ) -> tuple[bool, str, dict]:
        """Return ``(ok, trace, metrics)``.

        ``trace`` is the readable tool-call transcript the judge grades;
        ``metrics`` carries run stats plus ``metrics["final_answer"]``.
        ``skill_pack_dir`` is the directory holding the skill-set's skills
        (``None`` for the ``no_skills`` baseline). Providers load it however
        their CLI supports (Claude: ``--plugin-dir``; Codex: files-in-workspace
        + prompt).

        ``allowed_tools`` narrows the agent's tool surface for scenarios that
        measure behaviour under a restricted toolset. Providers that gate tools
        per-call honour it; sandbox-based providers (Codex) ignore it.
        """
        ...


class JudgeBackend(Protocol):
    """Grades an agent transcript against a scenario's checks."""

    name: str

    def run_judge(
        self,
        prompt: str,
        system: str,
        model: str,
        timeout_s: int,
        effort: str = "",
    ) -> dict:
        """Return the parsed verdict dict (``overall_pass`` etc.), or an
        ``{"error": ..., "overall_pass": False}`` shape on failure."""
        ...


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


# --------------------------------------------------------------------------- #
# Claude Code CLI backend (the original behaviour)
# --------------------------------------------------------------------------- #
# Tools the agent under test may use. Read/write/inspect the workspace, run the
# (mocked) shell, and fetch the public platform docs. `Skill` MUST be here or
# installed skills never activate.
CLAUDE_AGENT_ALLOWED_TOOLS = "Bash,Read,Write,Edit,Glob,Grep,TodoWrite,WebFetch,Skill"


class ClaudeBackend:
    """Agent + judge via the Claude Code CLI (``claude -p``)."""

    name = "claude"

    # -- agent ----------------------------------------------------------------
    def run_agent(
        self,
        ws: Path,
        prompt: str,
        model: str,
        timeout_s: int,
        *,
        extra_dirs: list[Path] | None = None,
        effort: str = "",
        env_overrides: dict | None = None,
        path_prepend: Path | None = None,
        skill_pack_dir: Path | None = None,
        allowed_tools: str | None = None,
    ) -> tuple[bool, str, dict]:
        cmd = [
            "claude", "-p", prompt,
            # stream-json + verbose emits per-step events so we can reconstruct
            # the tool-call trace, not just the final answer.
            "--output-format", "stream-json", "--verbose",
            "--model", model,
            # Isolate to the workspace project so user/global skills don't leak
            # in and confound the no_skills baseline.
            "--setting-sources", "project",
            # Scenarios that measure behaviour under a restricted tool surface
            # (e.g. pocket-loop, which withholds WebFetch) pass their own list.
            "--allowedTools", allowed_tools or CLAUDE_AGENT_ALLOWED_TOOLS,
            "--add-dir", str(ws),
        ]
        # Load the skill-set as a plugin so its skills actually activate
        # (invokable as nxd-eval-pack:<skill>). Copying into .claude/skills/
        # does NOT register them. no_skills baseline passes skill_pack_dir=None
        # → genuinely zero curated skills.
        if skill_pack_dir is not None:
            cmd += ["--plugin-dir", str(skill_pack_dir)]
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
            return False, "", {
                "error": f"claude exited {proc.returncode}: {proc.stderr[-2000:]}"
            }

        trace, metrics = self._trace_from_stream(proc.stdout)
        if not trace and not metrics.get("final_answer"):
            return False, "", {"error": f"empty stream output: {proc.stdout[-2000:]}"}
        return not metrics.get("is_error", False), trace, metrics

    @staticmethod
    def _trace_from_stream(stdout: str) -> tuple[str, dict]:
        """Parse Claude stream-json lines into a readable trace + final metrics.

        The trace interleaves the agent's reasoning text, each tool call (name +
        input), and a truncated tool result — so the judge can see *what the
        agent inspected*, not just its final answer.
        """
        parts: list[str] = []
        final_answer = ""
        tool_calls = 0
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
                        tool_calls += 1
                        inp = json.dumps(block.get("input", {}), ensure_ascii=False)
                        parts.append(f"[tool_use:{block.get('name')}] {inp[:600]}")
            elif typ == "user":
                for block in d.get("message", {}).get("content", []):
                    if block.get("type") == "tool_result":
                        content = block.get("content", "")
                        if isinstance(content, list):
                            content = " ".join(
                                c.get("text", "")
                                for c in content
                                if isinstance(c, dict)
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
        # tool_calls is the "how many steps did this take" efficiency signal.
        metrics["tool_calls"] = tool_calls
        trace = "\n".join(parts)
        return trace, {"final_answer": final_answer, **metrics}

    # -- judge ----------------------------------------------------------------
    def run_judge(
        self,
        prompt: str,
        system: str,
        model: str,
        timeout_s: int,
        effort: str = "",
    ) -> dict:
        cmd = [
            "claude", "-p", prompt,
            "--output-format", "json",
            "--model", model,
            "--setting-sources", "project",
            "--append-system-prompt", system,
            "--allowedTools", "",   # judge reasons over given text; no tools
        ]
        if effort:
            cmd += ["--effort", effort]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout_s
            )
        except subprocess.TimeoutExpired:
            return {"error": f"judge timed out after {timeout_s}s",
                    "overall_pass": False}
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


# --------------------------------------------------------------------------- #
# OpenAI Codex CLI backend
# --------------------------------------------------------------------------- #
# Codex has no per-tool allowlist like Claude's --allowedTools; it gates the
# agent's shell through a sandbox policy instead. `workspace-write` lets the
# agent read/write its workspace + run the (mocked) shell — the Codex analog of
# the Claude tool set — while still sandboxing the rest of the machine.
CODEX_AGENT_SANDBOX = "workspace-write"
# The judge only reasons over given text and must not touch the filesystem.
CODEX_JUDGE_SANDBOX = "read-only"


class CodexBackend:
    """Agent + judge via the OpenAI Codex CLI (``codex exec --json``).

    Structural parallel to :class:`ClaudeBackend`: same subprocess-per-run shape,
    a JSONL event stream we parse into the same ``(ok, trace, metrics)`` triple.
    Differences the caller must account for:

      * **No skill activation.** Codex has no ``--plugin-dir``. The skill-set is
        surfaced as files in the workspace; ``run.py`` adds a prompt line telling
        the agent to read them. Measures "skills as context", not "skill
        invocation".
      * **Metrics differ.** Codex reports token usage but not ``num_turns`` or
        ``total_cost_usd``; those keys are simply absent (the summary/report
        already skip missing keys).
      * **Runs outside a git repo.** Workspaces are tmpdirs, so ``exec`` is
        launched with ``--skip-git-repo-check``.
    """

    name = "codex"

    # -- agent ----------------------------------------------------------------
    def run_agent(
        self,
        ws: Path,
        prompt: str,
        model: str,
        timeout_s: int,
        *,
        extra_dirs: list[Path] | None = None,
        effort: str = "",
        env_overrides: dict | None = None,
        path_prepend: Path | None = None,
        skill_pack_dir: Path | None = None,
        allowed_tools: str | None = None,
    ) -> tuple[bool, str, dict]:
        # allowed_tools is intentionally unused here: Codex gates capability with
        # a sandbox policy, not a per-tool allowlist, so a scenario's narrowed
        # tool surface cannot be reproduced exactly. Runs of a tool-restricted
        # scenario are therefore not comparable to the same scenario on Claude.
        # skill_pack_dir is intentionally unused here: run.py stages the skills
        # into the workspace (or a mounted dir) and points the agent at them via
        # the prompt, because Codex cannot load a plugin dir. Accepting the arg
        # keeps the AgentBackend interface uniform across providers.
        cmd = [
            "codex", "exec",
            "--json",
            "--model", model,
            "--sandbox", CODEX_AGENT_SANDBOX,
            "--skip-git-repo-check",
            # Workspace is the primary writable root; extra_dirs (examples repo)
            # are added read/writable alongside so the agent can reference them.
            "-C", str(ws),
        ]
        for d in extra_dirs or []:
            cmd += ["--add-dir", str(d)]
        if effort:
            # Codex maps reasoning effort via a config override.
            cmd += ["-c", f"model_reasoning_effort={_toml_str(effort)}"]
        # Prompt is passed on stdin (trailing "-") so large scenario prompts
        # never hit argv length limits.
        cmd += ["-"]

        env = dict(os.environ)
        if env_overrides:
            env.update(env_overrides)
        if path_prepend is not None:
            env["PATH"] = f"{path_prepend}{os.pathsep}{env.get('PATH', '')}"
        try:
            proc = subprocess.run(
                cmd, cwd=ws, input=prompt, capture_output=True, text=True,
                timeout=timeout_s, env=env,
            )
        except subprocess.TimeoutExpired:
            return False, "", {"error": f"agent timed out after {timeout_s}s"}
        if proc.returncode != 0:
            return False, "", {
                "error": f"codex exited {proc.returncode}: {proc.stderr[-2000:]}"
            }

        trace, metrics = self._trace_from_stream(proc.stdout)
        if not trace and not metrics.get("final_answer"):
            return False, "", {"error": f"empty stream output: {proc.stdout[-2000:]}"}
        return not metrics.get("is_error", False), trace, metrics

    @staticmethod
    def _trace_from_stream(stdout: str) -> tuple[str, dict]:
        """Parse Codex JSONL events into the same trace + metrics shape Claude
        produces, so the judge prompt and reports are provider-independent.

        Codex event vocabulary (``codex exec --json``):
          * ``item.completed`` with ``item.type == "agent_message"`` → assistant
            text; the LAST one is the final answer.
          * ``item.completed`` with ``item.type == "command_execution"`` → a
            shell tool call (``command`` + truncated ``aggregated_output``).
          * ``item.completed`` with ``item.type in {"file_change","patch",...}``
            → a workspace mutation; rendered generically.
          * ``item.completed`` with ``item.type == "error"`` → a runtime notice
            (e.g. the skills-budget banner). Surfaced in the trace but does not
            by itself fail the run.
          * ``turn.completed`` with ``usage`` → token metrics.

        Non-JSON lines (Codex leaks some stderr diagnostics onto stdout) are
        skipped, matching the Claude parser's tolerance.
        """
        parts: list[str] = []
        final_answer = ""
        tool_calls = 0
        errored = False
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
            if typ == "item.completed":
                item = d.get("item", {}) or {}
                itype = item.get("type")
                if itype == "agent_message":
                    text = str(item.get("text", "")).strip()
                    if text:
                        parts.append(f"[assistant] {text}")
                        final_answer = text  # last agent_message wins
                elif itype == "command_execution":
                    tool_calls += 1
                    command = str(item.get("command", ""))
                    parts.append(f"[tool_use:Bash] {command[:600]}")
                    out = str(item.get("aggregated_output", ""))[:TOOL_RESULT_HEAD_CHARS]
                    exit_code = item.get("exit_code")
                    parts.append(f"[tool_result] (exit={exit_code}) {out}")
                elif itype in ("file_change", "patch", "apply_patch"):
                    tool_calls += 1
                    summary = json.dumps(
                        {k: v for k, v in item.items() if k != "type"},
                        ensure_ascii=False,
                    )
                    parts.append(f"[tool_use:{itype}] {summary[:600]}")
                elif itype == "error":
                    # Codex surfaces non-fatal notices (e.g. the skills-context
                    # budget banner) as error items. Record them but do not fail
                    # the run on their presence alone — a genuinely failed run
                    # exits non-zero or yields no final answer, handled above.
                    parts.append(f"[notice] {str(item.get('message', ''))[:600]}")
            elif typ == "turn.failed":
                errored = True
                err = d.get("error") or {}
                parts.append(f"[turn.failed] {json.dumps(err, ensure_ascii=False)[:600]}")
            elif typ == "turn.completed":
                usage = d.get("usage", {}) or {}
                metrics = {
                    "input_tokens": usage.get("input_tokens"),
                    "output_tokens": usage.get("output_tokens"),
                    "reasoning_output_tokens": usage.get("reasoning_output_tokens"),
                    "cached_input_tokens": usage.get("cached_input_tokens"),
                    "is_error": False,
                }
        metrics["is_error"] = errored or metrics.get("is_error", False)
        metrics["tool_calls"] = tool_calls
        trace = "\n".join(parts)
        return trace, {"final_answer": final_answer, **metrics}

    # -- judge ----------------------------------------------------------------
    def run_judge(
        self,
        prompt: str,
        system: str,
        model: str,
        timeout_s: int,
        effort: str = "",
    ) -> dict:
        """Grade via ``codex exec`` with an ``--output-schema`` that forces the
        verdict JSON shape. The final message (written to a temp file with
        ``-o``) is the verdict object directly — no fenced-block extraction
        needed, but we still fall back to :func:`_extract_json` defensively.

        The system prompt is prepended to the user prompt because ``codex exec``
        has no separate ``--append-system-prompt`` flag.
        """
        import tempfile

        full_prompt = f"{system}\n\n{prompt}" if system else prompt
        with tempfile.TemporaryDirectory(prefix="codex-judge-") as tmp:
            schema_path = Path(tmp) / "verdict_schema.json"
            schema_path.write_text(json.dumps(_VERDICT_SCHEMA), encoding="utf-8")
            last_msg_path = Path(tmp) / "last.txt"
            cmd = [
                "codex", "exec",
                "--json",
                "--model", model,
                "--sandbox", CODEX_JUDGE_SANDBOX,
                "--skip-git-repo-check",
                "--output-schema", str(schema_path),
                "-o", str(last_msg_path),
            ]
            if effort:
                cmd += ["-c", f"model_reasoning_effort={_toml_str(effort)}"]
            cmd += ["-"]
            try:
                proc = subprocess.run(
                    cmd, input=full_prompt, capture_output=True, text=True,
                    timeout=timeout_s,
                )
            except subprocess.TimeoutExpired:
                return {"error": f"judge timed out after {timeout_s}s",
                        "overall_pass": False}
            if proc.returncode != 0:
                return {
                    "error": f"judge exited {proc.returncode}: {proc.stderr[-1000:]}",
                    "overall_pass": False,
                }
            # Prefer the last-message file (the schema-constrained final answer);
            # fall back to scraping the JSONL stream if the file is empty.
            verdict_text = ""
            if last_msg_path.exists():
                verdict_text = last_msg_path.read_text(encoding="utf-8").strip()
            if not verdict_text:
                verdict_text = _last_agent_message(proc.stdout)
        parsed = _extract_json(verdict_text)
        if parsed is None:
            return {"error": f"judge verdict not JSON: {verdict_text[:500]}",
                    "overall_pass": False}
        return parsed


# Schema handed to codex --output-schema so the judge's final message is the
# verdict object. Mirrors the shape run.py's judge prompt asks for; the checks
# array is left open (items unconstrained) so per-scenario check ids pass
# through unchanged.
_VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "checks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "pass": {"type": "boolean"},
                    "why": {"type": "string"},
                },
                "required": ["id", "pass", "why"],
                "additionalProperties": False,
            },
        },
        "overall_pass": {"type": "boolean"},
        "summary": {"type": "string"},
    },
    "required": ["checks", "overall_pass", "summary"],
    "additionalProperties": False,
}


def _last_agent_message(stdout: str) -> str:
    """Return the last ``agent_message`` text from a Codex JSONL stream."""
    last = ""
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if d.get("type") == "item.completed":
            item = d.get("item", {}) or {}
            if item.get("type") == "agent_message":
                last = str(item.get("text", ""))
    return last


def _toml_str(value: str) -> str:
    """Quote a string for a ``codex -c key=value`` TOML override."""
    return '"' + value.replace('"', '\\"') + '"'


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
_AGENT_BACKENDS: dict[str, type] = {
    ClaudeBackend.name: ClaudeBackend,
    CodexBackend.name: CodexBackend,
}
_JUDGE_BACKENDS: dict[str, type] = {
    ClaudeBackend.name: ClaudeBackend,
    CodexBackend.name: CodexBackend,
}

AGENT_BACKENDS = tuple(_AGENT_BACKENDS)
JUDGE_BACKENDS = tuple(_JUDGE_BACKENDS)


def get_agent_backend(name: str) -> AgentBackend:
    try:
        return _AGENT_BACKENDS[name]()
    except KeyError:
        raise ValueError(
            f"unknown agent backend {name!r}; known: {', '.join(_AGENT_BACKENDS)}"
        ) from None


def get_judge_backend(name: str) -> JudgeBackend:
    try:
        return _JUDGE_BACKENDS[name]()
    except KeyError:
        raise ValueError(
            f"unknown judge backend {name!r}; known: {', '.join(_JUDGE_BACKENDS)}"
        ) from None
