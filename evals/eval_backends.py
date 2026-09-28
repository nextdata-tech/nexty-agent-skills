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

import contextlib
import dataclasses
import json
import os
import queue
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Callable, Protocol

try:
    from desktop_stdio import DesktopStdioError, DesktopStdioSession, redact_text
except ImportError:  # pragma: no cover - package-style imports in downstream runners
    from .desktop_stdio import DesktopStdioError, DesktopStdioSession, redact_text


# Cap each tool-result block fed to the judge so a huge file read doesn't blow
# up the judge prompt; the head is enough to see what the agent inspected.
TOOL_RESULT_HEAD_CHARS = 1500
_CREDENTIAL_ENV_KEY = re.compile(
    r"(?i)(?:anthropic|openai|claude|api|access|secret|bearer|token|password|private).*"
    r"(?:key|token|secret|credential|password)|(?:key|token|secret|credential|password).*"
    r"(?:anthropic|openai|claude|api|access|secret|bearer|private)"
)
_RESERVED_CREDENTIAL_ENV_KEYS = frozenset(
    {
        "NXD_EVAL_SOURCE_TOKEN",
        "NXD_DESKTOP_TRUSTED_CREDENTIAL_ENVS",
    }
)


def source_access_audit(
    raw_stdout: str, markers: list[tuple[str, str]] | None, *, incomplete: bool = False
) -> dict:
    """Return private, normalized evidence of attempted withheld-source access.

    Audit the unrendered stream before trace truncation. The runner supplies
    normalized IDs; raw needles and matched text never enter metrics or judges.
    """
    if not markers:
        return {"status": "incomplete" if incomplete else "not_required", "matched_marker_ids": []}
    matched = [marker_id for marker_id, needle in markers if needle in raw_stdout]
    return {
        "status": "incomplete" if incomplete else "access_observed" if matched else "clean",
        "matched_marker_ids": matched,
    }


def timeout_stdout(exc: subprocess.TimeoutExpired) -> str:
    """Return any partial stdout without assuming the subprocess text mode.

    Python may attach bytes even with ``text=True``; a timeout never provides a
    complete stream, so callers must pair this with ``incomplete=True``.
    """
    raw = getattr(exc, "stdout", None)
    if raw is None:
        raw = getattr(exc, "output", None)
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace")
    return raw if isinstance(raw, str) else ""


# argv rejects an embedded NUL outright — execv treats it as the end of the
# string — so a single stray binary byte that finds its way into a trace, and
# thence into the judge prompt built from that trace, makes the whole CLI
# invocation raise ValueError("embedded null byte") before the process even
# starts. That escapes the `except subprocess.TimeoutExpired` guards below and
# collapses an otherwise-gradeable cell into an unattributable one-liner. Every
# free-text string that reaches a claude argv slot is passed through this first.
# Tab, newline and carriage return are the whitespace controls real transcripts
# legitimately carry, so they stay; NUL, the rest of the C0 controls, and DEL
# are dropped. Stripping rather than rejecting keeps the run gradeable: a stray
# byte in a tool result should not fail the judge, only be scrubbed from the
# text it reasons over. Codex takes its prompt on stdin, which has no such
# restriction, so this is wired only into the argv paths that need it.
_ARGV_CONTROL_CHARS = (
    "".join(chr(c) for c in range(0x20) if c not in (0x09, 0x0A, 0x0D)) + "\x7f"
)
_ARGV_CONTROL_RE = re.compile(f"[{re.escape(_ARGV_CONTROL_CHARS)}]")


def strip_argv_control_chars(text: str) -> str:
    """Remove NUL and other non-printable control bytes from argv-bound text."""
    return _ARGV_CONTROL_RE.sub("", text)


# Multi-turn scenarios instruct the agent to emit this marker when it is
# stopping to wait on a user answer. No structural signal in the CLI's result
# event distinguishes "asked and waiting" from "task complete" — both report the
# same stop reason — so the boundary is DECLARED by the agent, not inferred.
#
# The marker gates only turns that opt into ``when: "awaiting_input"``. Turns
# default to ``when: "always"`` precisely so a missed marker cannot cascade: an
# agent that asks its question in prose still receives the follow-up and the
# rest of the rubric still gets graded. Whether it *stopped* correctly is graded
# separately — by the judge, and mechanically by trace-ordering checkers that
# compare write positions against the turn separator below.
TURN_BOUNDARY_SENTINEL = "[[AWAITING_USER_INPUT]]"

# Written into the accumulated trace between turns so both the judge and
# trace-reading deterministic checkers can locate the boundary. A checker that
# grades "did the agent write anything before the user replied" matches this
# line and compares positions — keep the format stable.
TURN_SEPARATOR_PREFIX = "[user_turn "

# Cap on the stderr retained from a multi-turn CLI process. The stream must be
# drained continuously — an undrained PIPE deadlocks the child once the OS pipe
# buffer fills, which would surface as a bogus turn timeout — but only the tail
# is ever reported, so an unbounded buffer is pure memory growth on a chatty run.
STDERR_TAIL_CHARS = 8000
# Cap on the partial transcript carried in metrics when a multi-turn run aborts.
# Diagnosis only — it never reaches the judge, so it just has to stay small
# enough to keep a report readable.
PARTIAL_TRACE_CHARS = 20_000
# How long to let a multi-turn CLI drain and exit after stdin closes. Fixed
# rather than "whatever is left of the run budget": the transcript is complete
# by then and a CLI that will not exit fails the run regardless, so a longer
# wait buys nothing and stalls the suite.
CLOSE_GRACE_S = 30


def _tool_input_json(inp: object) -> str:
    """Serialize a tool_use input, `command` first.

    The rendered line is truncated at 600 chars, and trace-reading gates parse
    `command` out of it to decide whether a run materialized anything. With
    dict order left to the CLI, a long `description` serialized ahead of
    `command` could push the command past the cut — the extractor would then
    find nothing, the gate would see no write, and `card-before-materialization`
    would PASS on a run that did write. Ordering the key that gates a verdict
    first makes that unreachable rather than merely unlikely.
    """
    if not isinstance(inp, dict):
        return json.dumps(inp, ensure_ascii=False)
    ordered = {k: inp[k] for k in ("command",) if k in inp}
    ordered.update({k: v for k, v in inp.items() if k not in ordered})
    return json.dumps(ordered, ensure_ascii=False)


def turn_separator(turn_index: int, text: str, *, after_await: bool = False) -> str:
    """Render the trace separator announcing a scripted user turn.

    ``after_await`` records whether the PRECEDING turn ended with the boundary
    sentinel. Because turns default to ``when: "always"``, the separator's mere
    presence says only that the harness spoke — not that the agent had stopped
    to be spoken to. A trace-reading checker grading "did the agent stop and
    ask" needs those two cases separated in the artifact it reads, so the state
    is written into the separator line itself rather than left implicit.
    """
    state = AWAITED_MARK if after_await else NOT_AWAITED_MARK
    return f"{TURN_SEPARATOR_PREFIX}{turn_index}{state}] {text}"


# Appended inside the separator's bracket, which MOVES the closing bracket: the
# rendered line is ``[user_turn 2 unprompted]``, so the literal ``[user_turn 2]``
# no longer appears anywhere in a trace. A checker that only cares about position
# must therefore match the unterminated prefix ``[user_turn 2`` (as
# check_executable_policy.TURN_2_SEPARATOR does); one grading the stop matches
# the fuller form. Keep any prose quoting this format in sync — a checker left
# pinning the old bracketed literal silently stops finding the boundary and
# collapses every ordering verdict to the same answer.
AWAITED_MARK = " after-await"
NOT_AWAITED_MARK = " unprompted"


@dataclasses.dataclass(frozen=True)
class FollowupTurn:
    """One scripted user message sent after the agent's previous turn ends.

    Turns are static text from the scenario's ``checks.json``. Nothing here is
    model-generated: a simulated user would add a second stochastic process to
    the measurement instrument.
    """

    #: The scripted user message, sent verbatim.
    text: str
    #: ``"always"`` sends unconditionally (the default and the recommended
    #: shape); ``"awaiting_input"`` sends only when the previous turn's final
    #: answer ended with :data:`TURN_BOUNDARY_SENTINEL`.
    when: str = "always"
    #: Per-turn wall-clock budget, measured from the moment the turn is sent
    #: and further bounded by whatever remains of the run-level ``timeout_s`` —
    #: which stays a whole-RUN budget regardless of how many turns a scenario
    #: scripts. A chatty turn does not extend it: the cap is a fixed instant,
    #: not a gap between streamed lines.
    timeout_s: int | None = None


WHEN_ALWAYS = "always"
WHEN_AWAITING_INPUT = "awaiting_input"
TURN_WHEN_VALUES = (WHEN_ALWAYS, WHEN_AWAITING_INPUT)


def parse_followup_turns(raw: object) -> list[FollowupTurn]:
    """Build :class:`FollowupTurn` objects from a scenario's ``turns`` array.

    Raises ``ValueError`` on a malformed declaration rather than dropping the
    turn: a silently ignored turn would grade a multi-turn scenario against a
    single-turn transcript and report the resulting failures as agent quality.
    """
    if raw in (None, []):
        return []
    if not isinstance(raw, list):
        raise ValueError("checks.json 'turns' must be a list")
    turns: list[FollowupTurn] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"checks.json turns[{i}] must be an object")
        text = item.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"checks.json turns[{i}] needs a non-empty 'text'")
        when = item.get("when", WHEN_ALWAYS)
        if when not in TURN_WHEN_VALUES:
            raise ValueError(
                f"checks.json turns[{i}] 'when' must be one of "
                f"{', '.join(TURN_WHEN_VALUES)}; got {when!r}"
            )
        timeout_s = item.get("timeout_s")
        # `bool` is a subclass of `int`, so a bare isinstance check accepts
        # `true` and silently yields a ~1-second cap — a turn budget nobody
        # wrote, failing the turn as an agent timeout. Reject it explicitly.
        if timeout_s is not None and (
            isinstance(timeout_s, bool)
            or not isinstance(timeout_s, int)
            or timeout_s <= 0
        ):
            raise ValueError(
                f"checks.json turns[{i}] 'timeout_s' must be a positive int"
            )
        turns.append(FollowupTurn(text=text, when=when, timeout_s=timeout_s))
    return turns


def awaiting_input(final_answer: str) -> bool:
    """True when a turn's final answer ends with the boundary sentinel.

    Trailing-line match only, so an agent that merely *discusses* the marker
    (quoting it back, explaining the protocol) is not counted as waiting.
    """
    non_empty = [ln.strip() for ln in (final_answer or "").splitlines() if ln.strip()]
    return bool(non_empty) and non_empty[-1].endswith(TURN_BOUNDARY_SENTINEL)


# Metrics the stream parser reports per turn that describe a QUANTITY of work,
# so the run-level number is their sum. Anything not listed here is not summable
# and is handled explicitly by _merge_turn_metrics.
# UNVERIFIED against a live CLI: this assumes each turn's `result` event reports
# that TURN's quantity, not a session-running total. If the CLI reports any of
# these cumulatively in `--input-format stream-json` mode, summing them
# triangular-over-counts — a 3-turn run would report roughly 2x the true figure,
# and `num_turns` / `output_tokens` are what the ledger records as the efficiency
# signal, so the inflated number would be written down as evidence.
#
# The fake CLI emits per-turn values by construction, so the tests pass under
# either semantics and CANNOT settle this. Settle it with one real multi-turn run
# with the per-turn `result` events dumped; if any is cumulative, move it out of
# this tuple and take the last value instead. `tool_calls` is counted locally per
# segment, so it stays summed regardless.
_SUMMED_TURN_METRICS = (
    "num_turns",
    "duration_ms",
    "total_cost_usd",
    "input_tokens",
    "output_tokens",
    "tool_calls",
)


def _merge_turn_metrics(per_turn: list[dict]) -> dict:
    """Fold per-turn metrics dicts into one run-level dict.

    Each turn is parsed on its own, so each yields its own metrics — the parser
    rebuilds its counters per call and overwrites ``metrics`` wholesale on the
    turn's ``result`` event. Reporting the last turn's numbers as the run's
    would silently undercount every earlier turn (a 3-turn run showing one
    turn's tool calls looks like an efficient run, not a broken metric), so the
    quantities are summed here and the non-quantities resolved deliberately.
    """
    merged: dict = {"is_error": False}
    for metrics in per_turn:
        for key in _SUMMED_TURN_METRICS:
            value = metrics.get(key)
            if value is not None:
                merged[key] = (merged.get(key) or 0) + value
        # Any turn erroring taints the whole conversation.
        if metrics.get("is_error"):
            merged["is_error"] = True
    # The conversation's answer is the last turn's answer, not a concatenation.
    merged["final_answer"] = per_turn[-1].get("final_answer", "") if per_turn else ""
    return merged


# --------------------------------------------------------------------------- #
# Interfaces
# --------------------------------------------------------------------------- #
class BackendDependencyError(RuntimeError):
    """Raised when a selected backend cannot run in this environment."""


def _require_executable(name: str, executable: str, install_hint: str) -> None:
    """Fail clearly when a backend's required CLI is not on PATH."""
    if shutil.which(executable) is not None:
        return
    raise BackendDependencyError(
        f"backend {name!r} requires the {executable!r} CLI, but it was not "
        f"found on PATH. {install_hint}"
    )


class AgentBackend(Protocol):
    """Drives the agent-under-test over one scenario workspace."""

    #: Stable identifier used on the CLI (``--agent-backend <name>``) and in
    #: the cache key so switching providers invalidates cached transcripts.
    name: str

    #: Executable the backend shells by default.
    executable: str

    #: Whether this provider can drive scripted follow-up turns. A provider that
    #: cannot MUST reject ``followup_turns`` loudly rather than running turn 1
    #: and returning: that would grade a multi-turn scenario against a
    #: single-turn transcript and report a bogus pass rate.
    supports_multi_turn: bool

    def check_dependencies(self, *, executable: str | None = None) -> None:
        """Raise ``BackendDependencyError`` if this backend cannot be launched."""
        ...

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
        followup_turns: list[FollowupTurn] | None = None,
        before_followup_turn: Callable[[Path, int], None] | None = None,
        source_audit_markers: list[tuple[str, str]] | None = None,
        executable: str | None = None,
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

        ``followup_turns`` scripts user messages sent after the agent's first
        turn ends. ``None``/empty is single-turn and MUST take exactly the
        pre-existing code path. ``timeout_s`` remains a whole-RUN budget across
        every turn, not a per-turn one.

        ``before_followup_turn`` may stage runner-owned workspace inputs after
        the preceding turn and before a scripted follow-up is delivered. It is
        called only for a follow-up that will actually be sent.
        """
        ...


class JudgeBackend(Protocol):
    """Grades an agent transcript against a scenario's checks."""

    name: str
    executable: str

    def check_dependencies(self, *, executable: str | None = None) -> None:
        """Raise ``BackendDependencyError`` if this backend cannot be launched."""
        ...

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
DESKTOP_MCP_TOOL_PREFIX = "mcp__nxd-desktop__"


def isolated_mcp_allowed_tools(
    allowed_tools: str | None = None,
    *,
    server_name: str = "nxd-desktop",
) -> str:
    """Return the caller's tools plus only the named private MCP server.

    The strict config prevents inherited MCP servers; this allowlist prevents
    an agent from reaching an unrelated configured MCP namespace even if a
    scenario broadens its normal shell/file tools.
    """
    source = allowed_tools or CLAUDE_AGENT_ALLOWED_TOOLS
    values = [item.strip() for item in source.split(",") if item.strip()]
    prefix = f"mcp__{server_name}__"
    values = [item for item in values if not item.startswith("mcp__")]
    values.append(prefix + "*")
    return ",".join(dict.fromkeys(values))


class ClaudeBackend:
    """Agent + judge via the Claude Code CLI (``claude -p``)."""

    name = "claude"
    executable = "claude"
    supports_multi_turn = True

    def check_dependencies(self, *, executable: str | None = None) -> None:
        _require_executable(
            self.name,
            executable or self.executable,
            "Install Claude Code and make sure `claude` is available in the "
            "environment running evals/run.py.",
        )

    # -- agent ----------------------------------------------------------------
    def _agent_command(
        self,
        ws: Path,
        model: str,
        *,
        extra_dirs: list[Path] | None,
        effort: str,
        skill_pack_dir: Path | None,
        allowed_tools: str | None,
        mcp_config: Path | None = None,
        strict_mcp_config: bool = False,
        nex_mode: bool = False,
        nex_settings_path: Path | None = None,
    ) -> list[str]:
        """Flags shared by the single-turn and multi-turn invocations.

        Only the prompt-delivery flags differ between them, so everything that
        shapes the agent's capabilities lives here and cannot drift apart.
        """
        cmd = [
            # stream-json + verbose emits per-step events so we can reconstruct
            # the tool-call trace, not just the final answer.
            "--output-format", "stream-json", "--verbose",
            "--model", model,
            # Isolate to the workspace project so user/global skills don't leak
            # in and confound the no_skills baseline.
            "--setting-sources", "project",
            # Scenarios that measure behaviour under a restricted tool surface
            # (e.g. job-loop, which withholds WebFetch) pass their own list.
            "--allowedTools", allowed_tools or CLAUDE_AGENT_ALLOWED_TOOLS,
            "--add-dir", str(ws),
        ]
        if mcp_config is not None:
            cmd += ["--mcp-config", str(mcp_config)]
            if strict_mcp_config:
                cmd += ["--strict-mcp-config"]
        elif strict_mcp_config:
            raise ValueError("strict_mcp_config requires mcp_config")
        if nex_mode:
            if nex_settings_path is None or not nex_settings_path.is_file():
                raise ValueError("NEX-890 requires runner-owned Claude settings")
            cmd += [
                "--settings", str(nex_settings_path),
                "--forward-subagent-text",
                "--disallowedTools",
                "Bash,BashOutput,KillShell,Monitor,PowerShell",
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
        return cmd

    @staticmethod
    def _agent_env(
        env_overrides: dict | None,
        path_prepend: Path | None,
        *,
        credential_isolation: bool = False,
    ) -> dict[str, str]:
        env = dict(os.environ)
        if env_overrides:
            env.update(env_overrides)
        if path_prepend is not None:
            env["PATH"] = f"{path_prepend}{os.pathsep}{env.get('PATH', '')}"
        if credential_isolation:
            for key in tuple(env):
                if (
                    key in _RESERVED_CREDENTIAL_ENV_KEYS
                    or _CREDENTIAL_ENV_KEY.search(key)
                ):
                    env.pop(key, None)
        return env

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
        followup_turns: list[FollowupTurn] | None = None,
        before_followup_turn: Callable[[Path, int], None] | None = None,
        source_audit_markers: list[tuple[str, str]] | None = None,
        executable: str | None = None,
        mcp_config: Path | None = None,
        strict_mcp_config: bool = False,
        stdio_session: DesktopStdioSession | None = None,
    ) -> tuple[bool, str, dict]:
        if followup_turns and stdio_session is not None and getattr(
            stdio_session, "nex_mode", False
        ):
            return False, "", {
                "status": "UNSUPPORTED",
                "error": "NEX-890 Claude stream guards currently support one turn only",
            }
        if stdio_session is not None:
            try:
                stdio_session.ensure_started()
            except DesktopStdioError as exc:
                return False, "", {
                    "error": redact_text(str(exc)),
                    **stdio_session.result_metrics(),
                }
            mcp_config = stdio_session.config_path
            strict_mcp_config = True
            allowed_tools = isolated_mcp_allowed_tools(
                allowed_tools,
                server_name=stdio_session.server_name,
            )
        elif strict_mcp_config:
            raise ValueError("strict_mcp_config requires mcp_config")
        # Multi-turn takes a separate, persistent-process implementation. The
        # single-turn path below is left byte-for-byte as it was so a scenario
        # that scripts no turns cannot regress from multi-turn work.
        if followup_turns:
            return self._run_agent_multi_turn(
                ws, prompt, model, timeout_s,
                extra_dirs=extra_dirs, effort=effort,
                env_overrides=env_overrides, path_prepend=path_prepend,
                skill_pack_dir=skill_pack_dir, allowed_tools=allowed_tools,
                followup_turns=followup_turns,
                before_followup_turn=before_followup_turn,
                source_audit_markers=source_audit_markers,
                mcp_config=mcp_config,
                strict_mcp_config=strict_mcp_config,
                stdio_session=stdio_session,
            )
        if mcp_config is not None:
            return self._run_agent_stdio(
                ws, prompt, model, timeout_s,
                executable=executable or self.executable,
                extra_dirs=extra_dirs, effort=effort,
                env_overrides=env_overrides, path_prepend=path_prepend,
                skill_pack_dir=skill_pack_dir, allowed_tools=allowed_tools,
                mcp_config=mcp_config,
                strict_mcp_config=strict_mcp_config,
                stdio_session=stdio_session,
                source_audit_markers=source_audit_markers,
            )
        cmd = [
            executable or self.executable, "-p", strip_argv_control_chars(prompt),
        ] + self._agent_command(
            ws, model, extra_dirs=extra_dirs, effort=effort,
            skill_pack_dir=skill_pack_dir, allowed_tools=allowed_tools,
            mcp_config=mcp_config, strict_mcp_config=strict_mcp_config,
            nex_mode=bool(stdio_session is not None and stdio_session.nex_mode),
            nex_settings_path=(
                stdio_session.nex_settings_path
                if stdio_session is not None and stdio_session.nex_mode
                else None
            ),
        )

        env = self._agent_env(env_overrides, path_prepend)
        try:
            proc = subprocess.run(
                cmd, cwd=ws, capture_output=True, text=True, timeout=timeout_s,
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            return False, "", {"error": f"agent timed out after {timeout_s}s",
                               "source_access_audit": source_access_audit(
                                   timeout_stdout(exc), source_audit_markers, incomplete=True
                               )}
        if proc.returncode != 0:
            # The CLI reports some fatal errors on stdout, not stderr — an
            # expired OAuth session is the common one. Reporting stderr alone
            # renders those as a bare "claude exited 1:" with no detail, which
            # is indistinguishable from a crash and sends the reader hunting in
            # the wrong place. Fall back to stdout when stderr is empty.
            detail = proc.stderr.strip() or proc.stdout.strip() or "(no output)"
            return False, "", {"error": f"claude exited {proc.returncode}: {detail[-2000:]}",
                                "source_access_audit": source_access_audit(proc.stdout, source_audit_markers)}

        # Audit the complete raw backend stream before deriving a readable
        # trace, whose tool outputs are intentionally truncated for judging.
        audit = source_access_audit(proc.stdout, source_audit_markers)
        trace, metrics = self._trace_from_stream(proc.stdout)
        if not trace and not metrics.get("final_answer"):
            return False, "", {"error": f"empty stream output: {proc.stdout[-2000:]}",
                                "source_access_audit": source_access_audit(proc.stdout, source_audit_markers)}
        metrics["source_access_audit"] = audit
        return not metrics.get("is_error", False), trace, metrics

    def _run_agent_stdio(
        self,
        ws: Path,
        prompt: str,
        model: str,
        timeout_s: int,
        *,
        executable: str,
        extra_dirs: list[Path] | None,
        effort: str,
        env_overrides: dict | None,
        path_prepend: Path | None,
        skill_pack_dir: Path | None,
        allowed_tools: str | None,
        mcp_config: Path,
        strict_mcp_config: bool,
        stdio_session: DesktopStdioSession | None,
        source_audit_markers: list[tuple[str, str]] | None,
    ) -> tuple[bool, str, dict]:
        """Run one Claude turn with a runner-owned strict MCP config.

        This path intentionally uses Popen rather than subprocess.run so a
        timeout can terminate the whole process group (Claude plus its MCP
        proxy/server descendants). The legacy single-turn path remains
        unchanged when no MCP config is supplied.
        """
        if not mcp_config.is_file():
            error = f"MCP config does not exist: {mcp_config}"
            if stdio_session is not None:
                stdio_session.record_agent(status="setup_failed", error=error)
                return False, "", {
                    "error": error,
                    **stdio_session.result_metrics(),
                }
            return False, "", {"error": error}
        cmd = [
            executable,
            "-p",
            strip_argv_control_chars(prompt),
        ] + self._agent_command(
            ws,
            model,
            extra_dirs=extra_dirs,
            effort=effort,
            skill_pack_dir=skill_pack_dir,
            allowed_tools=allowed_tools,
            mcp_config=mcp_config,
            strict_mcp_config=strict_mcp_config,
            nex_mode=bool(stdio_session is not None and stdio_session.nex_mode),
            nex_settings_path=(
                stdio_session.nex_settings_path
                if stdio_session is not None and stdio_session.nex_mode
                else None
            ),
        )
        env = self._agent_env(
            env_overrides,
            path_prepend,
            credential_isolation=stdio_session is not None,
        )
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=ws,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                start_new_session=True,
            )
            if stdio_session is not None:
                stdio_session.attach_process(proc)
            try:
                if stdio_session is not None and stdio_session.nex_mode:
                    stdout_parts: list[str] = []
                    stderr_parts: list[str] = []
                    stream_errors: list[str] = []

                    def read_stdout() -> None:
                        assert proc.stdout is not None
                        try:
                            for line in proc.stdout:
                                stdout_parts.append(line)
                                try:
                                    event = json.loads(line)
                                except json.JSONDecodeError:
                                    stdio_session.invalidate_nex(
                                        "Claude stream-json contained a malformed event"
                                    )
                                    continue
                                if not isinstance(event, Mapping):
                                    stdio_session.invalidate_nex(
                                        "Claude stream-json event was not an object"
                                    )
                                    continue
                                stdio_session.observe_claude_stream_event(event)
                        except (OSError, UnicodeError) as exc:
                            stream_errors.append(f"stdout reader failed: {exc}")
                            stdio_session.invalidate_nex("Claude stdout stream could not be fully read")

                    def read_stderr() -> None:
                        assert proc.stderr is not None
                        try:
                            for line in proc.stderr:
                                stderr_parts.append(line)
                        except (OSError, UnicodeError) as exc:
                            stream_errors.append(f"stderr reader failed: {exc}")

                    stdout_thread = threading.Thread(
                        target=read_stdout, name="nex890-claude-stream", daemon=True
                    )
                    stderr_thread = threading.Thread(
                        target=read_stderr, name="nex890-claude-stderr", daemon=True
                    )
                    stdout_thread.start()
                    stderr_thread.start()
                    started_at = time.monotonic()
                    overall_deadline = started_at + timeout_s
                    idle_limit = max(
                        1.0,
                        min(float(getattr(stdio_session, "idle_timeout_seconds", timeout_s)), float(timeout_s)),
                    )
                    stop_reason: str | None = None
                    while proc.poll() is None:
                        now = time.monotonic()
                        if now >= overall_deadline:
                            stop_reason = "overall"
                            break
                        if now - stdio_session.last_nex_activity() >= idle_limit:
                            stop_reason = "idle"
                            break
                        try:
                            proc.wait(timeout=min(0.25, overall_deadline - now))
                        except subprocess.TimeoutExpired:
                            continue
                    if stop_reason is not None:
                        if stdio_session is not None:
                            stdio_session.record_agent(
                                status="incomplete",
                                error=(
                                    f"Claude produced no stream or authenticated MCP activity for {idle_limit:g}s"
                                    if stop_reason == "idle"
                                    else f"agent timed out after {timeout_s}s"
                                ),
                            )
                        DesktopStdioSession._kill_process_group(proc)
                        stdout_thread.join(timeout=5)
                        stderr_thread.join(timeout=5)
                        stdout = "".join(stdout_parts)
                        stderr = "".join(stderr_parts)
                        if stdio_session is not None and stdio_session.nex_mode:
                            safe_stdout, stdout_secret_leak = stdio_session.redact_nex_text(stdout)
                            safe_stderr, stderr_secret_leak = stdio_session.redact_nex_text(stderr)
                        else:
                            safe_stdout = redact_text(stdout)
                            safe_stderr = redact_text(stderr)
                            stdout_secret_leak = stderr_secret_leak = False
                        result = {
                            "status": "INCOMPLETE",
                            "error": (
                                f"Claude produced no stream or authenticated MCP activity for {idle_limit:g}s"
                                if stop_reason == "idle"
                                else f"agent timed out after {timeout_s}s"
                            ),
                            "partial_stream_jsonl": safe_stdout,
                            "partial_stderr": safe_stderr[-4000:],
                            "nex_agent_stream_secret_leak": (
                                stdout_secret_leak or stderr_secret_leak
                            ),
                            "source_access_audit": source_access_audit(
                                stdout, source_audit_markers, incomplete=True
                            ),
                            "nex_stream_errors": stream_errors,
                        }
                        result.update(stdio_session.result_metrics())
                        return False, "", result
                    stdout_thread.join(timeout=10)
                    stderr_thread.join(timeout=10)
                    if stdout_thread.is_alive() or stderr_thread.is_alive():
                        stdio_session.invalidate_nex("Claude output reader did not drain after CLI exit")
                        DesktopStdioSession._kill_process_group(proc)
                    stdout = "".join(stdout_parts)
                    stderr = "".join(stderr_parts)
                else:
                    stdout, stderr = proc.communicate(timeout=timeout_s)
            except subprocess.TimeoutExpired as exc:
                if stdio_session is not None:
                    stdio_session.record_agent(
                        status="timeout",
                        error=f"agent timed out after {timeout_s}s",
                    )
                DesktopStdioSession._kill_process(proc)
                partial = timeout_stdout(exc)
                result = {
                    "error": f"agent timed out after {timeout_s}s",
                    "source_access_audit": source_access_audit(
                        partial, source_audit_markers, incomplete=True
                    ),
                }
                if stdio_session is not None:
                    result.update(stdio_session.result_metrics())
                return False, "", result
        except OSError as exc:
            error = f"could not start claude: {redact_text(str(exc))}"
            if stdio_session is not None:
                stdio_session.record_agent(status="failed", error=error)
                return False, "", {
                    "error": error,
                    **stdio_session.result_metrics(),
                }
            return False, "", {"error": error}
        finally:
            if stdio_session is not None:
                # The process is already reaped on normal and timeout paths;
                # cleanup remains idempotent for the caller's context manager.
                if not stdio_session.nex_mode:
                    stdio_session._attached = [
                        item for item in stdio_session._attached if item.poll() is None
                    ]

        nex_agent_stream_secret_leak = False
        if stdio_session is not None and stdio_session.nex_mode:
            _safe_stdout, stdout_secret_leak = stdio_session.redact_nex_text(stdout)
            _safe_stderr, stderr_secret_leak = stdio_session.redact_nex_text(stderr)
            nex_agent_stream_secret_leak = stdout_secret_leak or stderr_secret_leak

        if proc.returncode != 0:
            detail = stderr.strip() or stdout.strip() or "(no output)"
            safe_detail = (
                stdio_session.redact_nex_text(detail)[0]
                if stdio_session is not None and stdio_session.nex_mode
                else redact_text(detail)
            )
            error = f"claude exited {proc.returncode}: {safe_detail[-2000:]}"
            if stdio_session is not None:
                stdio_session.record_agent(status="failed", error=error)
            result = {
                "error": error,
                "nex_agent_stream_secret_leak": nex_agent_stream_secret_leak,
                "source_access_audit": source_access_audit(
                    stdout, source_audit_markers
                ),
            }
            if stdio_session is not None:
                result.update(stdio_session.result_metrics())
            return False, "", result
        audit = source_access_audit(stdout, source_audit_markers)
        trace, metrics = self._trace_from_stream(stdout)
        if not trace and not metrics.get("final_answer"):
            safe_stdout_tail = (
                stdio_session.redact_nex_text(stdout[-2000:])[0]
                if stdio_session is not None and stdio_session.nex_mode
                else redact_text(stdout[-2000:])
            )
            error = f"empty stream output: {safe_stdout_tail}"
            if stdio_session is not None:
                stdio_session.record_agent(status="failed", error=error)
            result = {
                "error": error,
                "nex_agent_stream_secret_leak": nex_agent_stream_secret_leak,
                "source_access_audit": audit,
            }
            if stdio_session is not None:
                result.update(stdio_session.result_metrics())
            return False, "", result
        if stdio_session is not None:
            stdio_session.record_agent(
                status="passed" if not metrics.get("is_error", False) else "failed",
                error="Claude returned an error result"
                if metrics.get("is_error", False)
                else None,
            )
            metrics.update(stdio_session.result_metrics())
            if stdio_session.nex_mode:
                metrics["nex_stream_errors"] = stream_errors
                metrics["nex_agent_stream_secret_leak"] = nex_agent_stream_secret_leak
        metrics["source_access_audit"] = audit
        return not metrics.get("is_error", False), trace, metrics

    # -- agent (multi-turn) ---------------------------------------------------
    def _run_agent_multi_turn(
        self,
        ws: Path,
        prompt: str,
        model: str,
        timeout_s: int,
        *,
        extra_dirs: list[Path] | None,
        effort: str,
        env_overrides: dict | None,
        path_prepend: Path | None,
        skill_pack_dir: Path | None,
        allowed_tools: str | None,
        followup_turns: list[FollowupTurn],
        before_followup_turn: Callable[[Path, int], None] | None,
        source_audit_markers: list[tuple[str, str]] | None,
        mcp_config: Path | None,
        strict_mcp_config: bool,
        stdio_session: DesktopStdioSession | None,
    ) -> tuple[bool, str, dict]:
        """Drive one conversation over a single long-lived CLI process.

        One ``Popen`` per scenario, fed one JSON user message per turn on stdin.
        A live process is used rather than re-invoking the CLI per turn because
        the process-level flags (``--add-dir``, ``--plugin-dir``) are set once on
        a process that never restarts, and because a desktop cell's supervisor
        children stay under a single process lineage for the caller's cleanup
        guard to sweep — which it does once, after this method returns.

        ``timeout_s`` is a whole-RUN budget: a monotonic deadline is taken at
        entry and every turn is bounded by what remains, so an N-turn scenario
        cannot run N times the single-turn budget.
        """
        # `-p` with no prompt argument: turn 1's text goes over stdin like every
        # other turn, so the turn loop has exactly one code path.
        session_id = str(uuid.uuid4())
        cmd = [
            self.executable, "-p",
            "--input-format", "stream-json",
            "--session-id", session_id,
        ] + self._agent_command(
            ws, model, extra_dirs=extra_dirs, effort=effort,
            skill_pack_dir=skill_pack_dir, allowed_tools=allowed_tools,
            mcp_config=mcp_config, strict_mcp_config=strict_mcp_config,
            nex_mode=bool(stdio_session is not None and stdio_session.nex_mode),
            nex_settings_path=(
                stdio_session.nex_settings_path
                if stdio_session is not None and stdio_session.nex_mode
                else None
            ),
        )
        env = self._agent_env(
            env_overrides,
            path_prepend,
            credential_isolation=stdio_session is not None,
        )

        deadline = time.monotonic() + timeout_s
        try:
            proc = subprocess.Popen(
                cmd, cwd=ws, env=env, text=True, bufsize=1,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
            if stdio_session is not None:
                stdio_session.attach_process(proc)
        except OSError as exc:
            error = f"could not start claude: {redact_text(str(exc))}"
            if stdio_session is not None:
                stdio_session.record_agent(status="failed", error=error)
                return False, "", {
                    "error": error,
                    **stdio_session.result_metrics(),
                }
            return False, "", {"error": error}

        stdout_q: queue.Queue[str | None] = queue.Queue()
        stderr_chunks: list[str] = []
        # Mirrors stderr_chunks. The CLI reports some fatal errors on stdout —
        # an expired OAuth session is the common one — so an error path that
        # reads stderr alone renders those as a bare exit code with no detail.
        # The consuming loop takes lines off the queue, which empties it, so
        # the text has to be kept here to stay reachable from the error paths.
        stdout_chunks: list[str] = []
        # This is intentionally unbounded for the duration of a single eval
        # conversation.  Source-isolation evidence must inspect the complete
        # raw stream, not the rendered or diagnostic-tail transcript.
        raw_stdout_chunks: list[str] = []

        def _drain_stdout() -> None:
            for line in proc.stdout:  # type: ignore[union-attr]
                raw_stdout_chunks.append(line)
                stdout_chunks.append(line)
                if len(stdout_chunks) > 2000:
                    del stdout_chunks[:1000]
                stdout_q.put(line)
            stdout_q.put(None)

        def _drain_stderr() -> None:
            # stderr MUST be drained continuously even though it is only ever
            # reported as a tail: leaving the pipe unread deadlocks the child
            # once the OS buffer fills mid-turn, which would surface as a turn
            # timeout — an infrastructure failure wearing an agent failure's
            # clothes.
            for line in proc.stderr:  # type: ignore[union-attr]
                stderr_chunks.append(line)
                if len(stderr_chunks) > 2000:
                    del stderr_chunks[:1000]

        readers = [
            threading.Thread(target=_drain_stdout, daemon=True),
            threading.Thread(target=_drain_stderr, daemon=True),
        ]
        for reader in readers:
            reader.start()

        def _stderr_tail() -> str:
            return "".join(stderr_chunks).strip()[-STDERR_TAIL_CHARS:]

        def _stdout_tail() -> str:
            return "".join(stdout_chunks).strip()[-STDERR_TAIL_CHARS:]

        def _failure_detail() -> str:
            # Same precedence the single-turn path uses: stderr when there is
            # any, else stdout, so a stdout-only fatal error still names itself
            # instead of arriving as an undiagnosable bare exit.
            return _stderr_tail() or _stdout_tail()

        def _abort(error: str) -> tuple[bool, str, dict]:
            # Kill BEFORE returning. The caller's process guard sweeps pid files
            # in its `finally`; a CLI still alive at that moment can re-write one
            # after the sweep ran and leak a supervisor for the rest of the run.
            with contextlib.suppress(OSError, ValueError):
                os.killpg(proc.pid, signal.SIGTERM)
            with contextlib.suppress(OSError, ValueError):
                proc.kill()
            # TimeoutExpired subclasses SubprocessError, NOT OSError, so it
            # would escape a suppress(OSError) and crash the whole eval run
            # instead of erroring this one scenario.
            with contextlib.suppress(OSError, ValueError, subprocess.TimeoutExpired):
                proc.wait(timeout=30)
            # The child is dead, so both reader threads are about to hit EOF.
            # Joining briefly lets them append whatever the CLI wrote on its way
            # out — which for a stdout-only fatal error is the whole diagnosis.
            for reader in readers:
                reader.join(timeout=5)
            detail = _failure_detail()
            nex_secret_leak = False
            if stdio_session is not None and stdio_session.nex_mode:
                _safe_raw_stream, nex_secret_leak = stdio_session.redact_nex_text(
                    "".join(raw_stdout_chunks)
                )
                detail = stdio_session.redact_nex_text(detail)[0]
            # The trace stays "" — a partial transcript must never be graded, and
            # returning one here would let a run that died mid-conversation be
            # scored against the full rubric as an agent failure. But the turns
            # that DID complete are the diagnosis for a late-turn timeout, so
            # they travel in metrics where the judge never sees them.
            partial = "\n".join(t for t, _ in segments).strip()
            meta: dict = {
                "error": f"{error}: {detail[-2000:]}" if detail else error,
                "nex_agent_stream_secret_leak": nex_secret_leak,
            }
            meta["source_access_audit"] = source_access_audit(
                "".join(raw_stdout_chunks), source_audit_markers
            )
            if partial:
                meta["partial_trace"] = partial[-PARTIAL_TRACE_CHARS:]
                meta["partial_segments"] = len(segments)
            if stdio_session is not None:
                stdio_session.record_agent(status="failed", error=error)
                meta.update(stdio_session.result_metrics())
            return False, "", meta

        segments: list[tuple[str, dict]] = []
        turns_sent = 1
        skipped_turns: list[int] = []
        awaited_input_turns: list[int] = []
        pending: list[FollowupTurn | None] = [None] + list(followup_turns)

        for offset, turn in enumerate(pending):
            turn_index = offset + 1
            text = prompt if turn is None else turn.text
            if turn is not None:
                after_await = awaiting_input(
                    segments[-1][1].get("final_answer", "") if segments else ""
                )
                if turn.when == WHEN_AWAITING_INPUT and not after_await:
                    # The agent did not declare that it was waiting, so sending
                    # this turn would talk over a finished run. Recorded, not an
                    # error — the scenario grades the stop separately.
                    skipped_turns.append(turn_index)
                    continue
                if before_followup_turn is not None:
                    try:
                        before_followup_turn(ws, turn_index)
                    except Exception as exc:  # noqa: BLE001 - setup is scenario-owned
                        return _abort(
                            f"follow-up workspace setup failed before turn "
                            f"{turn_index}: {type(exc).__name__}: {exc}"
                        )
                segments.append(
                    (turn_separator(turn_index, text, after_await=after_await), {})
                )
                turns_sent += 1

            message = {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [{"type": "text", "text": text}],
                },
            }
            try:
                proc.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")  # type: ignore[union-attr]
                proc.stdin.flush()  # type: ignore[union-attr]
            except (BrokenPipeError, OSError):
                return _abort(
                    f"claude closed its input before turn {turn_index}"
                )

            lines: list[str] = []
            saw_result = False
            # Both budgets are fixed points in time, taken ONCE before the read
            # loop. Deriving the turn cap inside the loop instead would restart
            # it on every streamed line, turning a wall-clock cap into a
            # gap-between-lines cap: a turn emitting steady heartbeats or tool
            # chatter would never trip it and would run to the run deadline.
            turn_deadline = deadline
            if turn is not None and turn.timeout_s is not None:
                turn_deadline = min(deadline, time.monotonic() + turn.timeout_s)

            def _timeout_error(_turn_deadline: float = turn_deadline) -> str:
                # Name the budget that actually expired. Reporting the run
                # budget for a per-turn timeout sends the reader off raising
                # --agent-timeout, which cannot fix a turn-level cap.
                if _turn_deadline < deadline:
                    return (
                        f"agent exceeded its {turn.timeout_s}s turn budget "  # type: ignore[union-attr]
                        f"during turn {turn_index}"
                    )
                return f"agent timed out after {timeout_s}s during turn {turn_index}"

            while True:
                remaining = turn_deadline - time.monotonic()
                if remaining <= 0:
                    return _abort(_timeout_error())
                try:
                    line = stdout_q.get(timeout=remaining)
                except queue.Empty:
                    return _abort(_timeout_error())
                if line is None:
                    return _abort(
                        f"claude exited during turn {turn_index} without a "
                        "result event"
                    )
                lines.append(line)
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    obj = json.loads(stripped)
                except json.JSONDecodeError:
                    continue
                # `json.loads` succeeds on any valid JSON scalar, so a bare
                # `null`, `5` or `"..."` parses and then `.get` raises
                # AttributeError. That escapes run_agent entirely — it takes the
                # scenario down instead of erroring it, and skips _abort, so the
                # CLI is left alive with its reader threads attached and can
                # re-write a pid file after the caller's guard has swept.
                if isinstance(obj, dict) and obj.get("type") == "result":
                    saw_result = True
                if saw_result:
                    break

            seg_trace, seg_metrics = self._trace_from_stream("".join(lines))
            segments.append((seg_trace, seg_metrics))
            if awaiting_input(seg_metrics.get("final_answer", "")):
                awaited_input_turns.append(turn_index)

        # Closing stdin ends the session; the CLI drains and exits.
        with contextlib.suppress(OSError, ValueError):
            proc.stdin.close()  # type: ignore[union-attr]
        killed_on_close = False
        try:
            # A FIXED grace, not the rest of the run budget. The transcript is
            # already complete here and the outcome decided — a CLI that will
            # not exit gets killed_on_close, a nonzero returncode and a failed
            # run either way — so handing it the unspent --agent-timeout only
            # stalls the suite. A 2-minute conversation inside a 30-minute
            # budget blocked for the other 28 before killing.
            returncode = proc.wait(timeout=CLOSE_GRACE_S)
        except subprocess.TimeoutExpired:
            # Hung on stdin close. Kill and reap, but remember that we did: the
            # transcript is complete, yet the process did not shut down cleanly.
            killed_on_close = True
            with contextlib.suppress(OSError, ValueError):
                proc.kill()
            try:
                returncode = proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                # Killed but unreapable (a child wedged in uninterruptible I/O).
                # Raising here would abort the entire eval run.
                returncode = None
        for reader in readers:
            reader.join(timeout=5)

        trace = "\n".join(part for part, _ in segments if part)
        metrics = _merge_turn_metrics([m for _, m in segments if m])
        metrics.update({
            "session_id": session_id,
            "turns_sent": turns_sent,
            "skipped_turns": skipped_turns,
            "awaited_input_turns": awaited_input_turns,
            "exit_code": returncode,
            "killed_on_close": killed_on_close,
            "source_access_audit": source_access_audit(
                "".join(raw_stdout_chunks), source_audit_markers
            ),
        })
        if stdio_session is not None:
            if stdio_session.nex_mode:
                _safe_raw_stream, nex_secret_leak = stdio_session.redact_nex_text(
                    "".join(raw_stdout_chunks)
                )
                metrics["nex_agent_stream_secret_leak"] = nex_secret_leak
            stdio_session.record_agent(
                status="passed" if not metrics.get("is_error", False) else "failed",
                error="Claude returned an error result"
                if metrics.get("is_error", False)
                else None,
            )
            metrics.update(stdio_session.result_metrics())
        if not trace and not metrics.get("final_answer"):
            detail = _failure_detail()
            if stdio_session is not None and stdio_session.nex_mode:
                detail = stdio_session.redact_nex_text(detail)[0]
            metrics["error"] = (
                f"empty stream output (exit {returncode}): "
                f"{redact_text(detail[-2000:])}"
            )
            return False, "", metrics
        # A nonzero exit fails the run exactly as it does on the single-turn
        # path. A CLI that emits its result events and then dies with a fatal
        # error would otherwise be graded ok on a transcript it disowned.
        if returncode != 0:
            detail = _failure_detail()
            if stdio_session is not None and stdio_session.nex_mode:
                detail = stdio_session.redact_nex_text(detail)[0]
            reason = (
                "did not exit after its input was closed"
                if killed_on_close else f"exited {returncode}"
            )
            metrics["error"] = f"claude {reason}: {redact_text(detail[-2000:])}"
            return False, trace, metrics
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
            # A valid JSON scalar (`null`, `5`, `"..."`) parses fine, so `.get`
            # on it raises AttributeError — not a JSONDecodeError, so it escapes
            # every handler above and kills the run rather than erroring it.
            if not isinstance(d, dict):
                continue
            typ = d.get("type")
            if typ == "assistant":
                for block in d.get("message", {}).get("content", []):
                    if block.get("type") == "text" and block.get("text", "").strip():
                        parts.append(f"[assistant] {block['text'].strip()}")
                    elif block.get("type") == "tool_use":
                        tool_calls += 1
                        parts.append(
                            f"[tool_use:{block.get('name')}] "
                            f"{_tool_input_json(block.get('input', {}))[:600]}"
                        )
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
        # The judge prompt is built from the agent trace, so a stray binary byte
        # in a tool result rides straight into this argv slot; scrub both the
        # trace-derived prompt and the system prompt before they get there.
        cmd = [
            self.executable, "-p", strip_argv_control_chars(prompt),
            "--output-format", "json",
            "--model", model,
            "--setting-sources", "project",
            "--append-system-prompt", strip_argv_control_chars(system),
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
            # Same stdout-vs-stderr split as the agent path above.
            detail = proc.stderr.strip() or proc.stdout.strip() or "(no output)"
            return {"error": f"judge exited {proc.returncode}: {detail[-1000:]}",
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
#
# Codex implements `workspace-write` with bubblewrap, which needs privileges a
# GitHub-hosted runner does not grant: every shell call dies with
# `bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted` before the
# command runs. The agent then cannot read its own fixtures, and the judge —
# correctly — fails a transcript that produced no evidence, which is
# indistinguishable from a skill regression.
#
# EVAL_CODEX_AGENT_SANDBOX lets such an environment select
# `danger-full-access`. That is only safe where the whole machine is already
# disposable and isolated (an ephemeral CI runner); it is deliberately NOT the
# default, so a local run keeps the sandbox.
CODEX_AGENT_SANDBOX = os.environ.get("EVAL_CODEX_AGENT_SANDBOX", "").strip() or "workspace-write"
# The judge only reasons over given text and must not touch the filesystem.
CODEX_JUDGE_SANDBOX = "read-only"


# Signatures of the sandbox itself refusing to run a command, as opposed to a
# command running and failing. `bwrap` is bubblewrap, which Codex uses to
# implement workspace-write and which cannot create a network namespace on a
# GitHub-hosted runner.
_SANDBOX_FAILURE_MARKERS = (
    "bwrap:",
    "Failed RTM_NEWADDR",
    "seccomp",
    "landlock",
    "sandbox denied",
    "Operation not permitted (os error 1)",
)


def _is_sandbox_failure(output: str) -> bool:
    """True when a shell result shows the sandbox blocked execution."""
    return any(marker in output for marker in _SANDBOX_FAILURE_MARKERS)


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
      * **No multi-turn.** ``codex exec`` is single-shot: the prompt arrives on
        stdin and the process ends with the answer. There is no persistent-stdin
        protocol and no resume flag, so scripted follow-up turns cannot be
        driven. See :attr:`supports_multi_turn`.
    """

    name = "codex"
    executable = "codex"
    TERMINAL_WORKFLOW_ROUTE = "terminal_workflow_review_v1"
    TERMINAL_ROUTE_WALL_CAP_S = 1800
    # Concatenating a scenario's turns into one prompt would run without error
    # while measuring a different thing entirely: an agent told the correction
    # up front never has to stop and ask, which is usually the behaviour under
    # test. So multi-turn is refused, not approximated.
    supports_multi_turn = False

    def check_dependencies(self, *, executable: str | None = None) -> None:
        _require_executable(
            self.name,
            executable or self.executable,
            "Install the OpenAI Codex CLI and make sure `codex` is available in "
            "the environment running evals/run.py.",
        )

    @staticmethod
    def _stdio_mcp_config_args(stdio_session: DesktopStdioSession) -> list[str]:
        """Return isolated Codex config overrides for one runner-owned MCP server."""
        # `-c` uses dotted config keys, not TOML table syntax. Quoting the
        # name here makes the quotes part of the server identifier, so Codex
        # rejects it as an invalid MCP name before the model can see tools.
        # MCP server names permit the hyphen used by the desktop namespace.
        prefix = f"mcp_servers.{stdio_session.server_name}"
        proxy_args = [
            str(DesktopStdioSession.PROXY_MODULE),
            "--proxy",
            "--spec",
            str(stdio_session.root / "server-spec.json"),
        ]
        return [
            "-c", f"{prefix}.command={json.dumps(sys.executable)}",
            "-c", f"{prefix}.args={json.dumps(proxy_args)}",
            "-c", f"{prefix}.env.PYTHONUNBUFFERED={json.dumps('1')}",
            "-c", f"{prefix}.enabled=true",
            "-c", f"{prefix}.required=true",
        ]

    @staticmethod
    def _review_reader_trace_paths(trace_path: Path) -> set[str]:
        """Return only exact paths with a matching synthetic reader response."""
        try:
            rows = [
                json.loads(line)
                for line in trace_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        except (OSError, json.JSONDecodeError):
            return set()
        requests: dict[tuple[str, str], str] = {}
        completed: set[tuple[str, str]] = set()
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("message"), dict):
                continue
            message = row["message"]
            request_id = message.get("id")
            if request_id is None or isinstance(request_id, (dict, list)):
                continue
            key = (type(request_id).__name__, json.dumps(request_id, sort_keys=True))
            if row.get("direction") == "request":
                params = message.get("params")
                if (
                    message.get("method") == "tools/call"
                    and isinstance(params, dict)
                    and params.get("name") == "read_review_input"
                    and isinstance(params.get("arguments"), dict)
                ):
                    args = params["arguments"]
                    path = args.get("path")
                    if (
                        isinstance(path, str)
                        and args.get("operation") in {"read", "list"}
                        and set(args).issubset({"path", "operation", "max_lines", "max_bytes"})
                    ):
                        requests[key] = path
            elif (
                row.get("direction") == "response"
                and row.get("synthetic") is True
                and row.get("review_reader") is True
                and "error" not in message
                and isinstance(message.get("result"), dict)
                and message["result"].get("isError") is not True
            ):
                completed.add(key)
        return {path for key, path in requests.items() if key in completed}

    @staticmethod
    def _read_route_audit(path: Path) -> dict:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            value = {}
        audit = value if isinstance(value, dict) else {}
        event_log = path.with_name("codex-app-server-events.jsonl")
        try:
            event_lines = event_log.read_text(encoding="utf-8").splitlines()
        except OSError:
            event_lines = []
        events = []
        for line in event_lines:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                events.append(row)
        if events:
            audit = {**audit, "events": events, "event_count": len(events)}
        return audit

    @staticmethod
    def _timeout_stream_output(
        timeout_error: subprocess.TimeoutExpired,
        previous_stdout: str = "",
        previous_stderr: str = "",
    ) -> tuple[str, str]:
        def as_text(value: object, fallback: str) -> str:
            if isinstance(value, bytes):
                return value.decode("utf-8", errors="replace")
            return value if isinstance(value, str) and value else fallback

        return (
            as_text(timeout_error.output, previous_stdout),
            as_text(timeout_error.stderr, previous_stderr),
        )

    @staticmethod
    def _terminal_route_audit_evidence(
        audit: Mapping[str, object], codex_version: str,
        trace_reader_paths: set[str],
    ) -> tuple[bool, bool]:
        """Validate reviewer identity and its exact matching proxy read."""
        child_paths = audit.get("child_reader_paths", [])
        matching_reader = bool(
            isinstance(child_paths, list)
            and any(isinstance(path, str) and path in trace_reader_paths for path in child_paths)
        )
        spawned = audit.get("spawned_receiver_ids", [])
        review_receivers = audit.get("review_receiver_ids", [])
        def string_ids(key: str) -> set[str]:
            values = audit.get(key)
            if not isinstance(values, list) or not all(
                isinstance(value, str) and value for value in values
            ):
                return set()
            return set(values)

        spawned_ids = string_ids("spawned_receiver_ids")
        review_ids = string_ids("review_receiver_ids")
        child_readers = string_ids("child_reader_receivers")
        child_successes = string_ids("child_success_receivers")
        child_messages = string_ids("child_message_receivers")
        violations = audit.get("violations", [])
        report_count = audit.get("review_report_count")
        turn_count = audit.get("turn_count")
        pending_count = audit.get("pending_child_event_count", 0)
        required_tools = {
            "get_workflow_capabilities", "check_data_product", "prepare_workflow",
            "advance_workflow", "inspect_workflow", "inspect_run",
            "list_data_products", "resume_data_product", "describe_models",
            "run_semantic_query", "export_data_product",
        }
        completion_tools = {
            "advance_workflow", "inspect_workflow", "inspect_run",
            "list_data_products", "resume_data_product", "describe_models",
            "run_semantic_query", "export_data_product",
        }
        successful_root_tools = audit.get("successful_root_tools", [])
        completed_stage_tools = audit.get("completion_tools", [])
        audit_ok = bool(
            audit.get("review_verified") is True
            and audit.get("codex_version") == codex_version
            and isinstance(spawned, list) and spawned_ids
            and isinstance(review_receivers, list) and len(review_receivers) == 1
            and review_ids
            and review_ids.issubset(spawned_ids)
            and isinstance(report_count, int) and not isinstance(report_count, bool)
            and report_count == 1
            and isinstance(child_paths, list) and child_paths
            and child_readers
            and child_readers.issubset(child_successes)
            and child_readers.issubset(child_messages)
            and child_readers.issubset(review_ids)
            and matching_reader
            and isinstance(violations, list) and not violations
            and audit.get("unattributed_events") == 0
            and isinstance(pending_count, int) and not isinstance(pending_count, bool)
            and pending_count == 0
            and isinstance(turn_count, int) and not isinstance(turn_count, bool)
            and 3 <= turn_count <= 7
            and isinstance(successful_root_tools, list)
            and all(isinstance(item, str) for item in successful_root_tools)
            and required_tools.issubset(set(successful_root_tools))
            and isinstance(completed_stage_tools, list)
            and all(isinstance(item, str) for item in completed_stage_tools)
            and completion_tools.issubset(set(completed_stage_tools))
            and audit.get("completion_verified") is True
        )
        return audit_ok, matching_reader

    def _run_codex_app_server_route(
        self,
        ws: Path,
        prompt: str,
        model: str,
        timeout_s: int,
        *,
        effort: str,
        env_overrides: dict | None,
        path_prepend: Path | None,
        executable: str | None,
        source_audit_markers: list[tuple[str, str]] | None,
        stdio_session: DesktopStdioSession,
    ) -> tuple[bool, str, dict]:
        """Run the narrowly opted-in staged workflow over Codex app-server."""
        if source_audit_markers:
            return False, "", {
                "error": "Codex app-server route cannot grade source-isolation markers without raw marker audit",
                **stdio_session.result_metrics(),
            }
        if getattr(stdio_session, "codex_app_server_route", None) != self.TERMINAL_WORKFLOW_ROUTE:
            return False, "", {
                "error": "unsupported Codex app-server route opt-in",
                **stdio_session.result_metrics(),
            }
        if not getattr(stdio_session, "workflow_action_guard", False):
            return False, "", {
                "error": "Codex app-server route requires the workflow action guard",
                **stdio_session.result_metrics(),
            }
        route_timeout = min(max(1, int(timeout_s)), self.TERMINAL_ROUTE_WALL_CAP_S)
        try:
            stdio_session.ensure_started()
        except DesktopStdioError as exc:
            return False, "", {"error": redact_text(str(exc)), **stdio_session.result_metrics()}

        codex = executable or self.executable
        resolved = shutil.which(codex) if not os.path.isabs(codex) else codex
        if not resolved:
            return False, "", {"error": f"Codex executable is unavailable: {codex}"}

        env = dict(os.environ)
        if env_overrides:
            env.update(env_overrides)
        for key in tuple(env):
            if key in _RESERVED_CREDENTIAL_ENV_KEYS or _CREDENTIAL_ENV_KEY.search(key):
                env.pop(key, None)
        if path_prepend is not None:
            env["PATH"] = f"{path_prepend}{os.pathsep}{env.get('PATH', '')}"
        package_root = Path(__file__).resolve().parent / "dp-scenarios" / "src"
        existing_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = os.pathsep.join(
            item for item in (str(package_root), existing_pythonpath) if item
        )
        try:
            version_proc = subprocess.run(
                [str(resolved), "--version"],
                cwd=ws,
                capture_output=True,
                text=True,
                timeout=min(15, route_timeout),
                env=env,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return False, "", {
                "error": f"Codex version probe failed: {redact_text(str(exc))}",
                **stdio_session.result_metrics(),
            }
        codex_version = redact_text((version_proc.stdout or version_proc.stderr).strip())
        if version_proc.returncode != 0 or not codex_version:
            return False, "", {
                "error": "Codex version probe did not return a version",
                **stdio_session.result_metrics(),
            }

        supervisor = getattr(stdio_session, "desktop_supervisor", None)
        desktop_python = getattr(stdio_session, "desktop_python", None)
        supervisor_data = getattr(stdio_session, "supervisor_data_dir", None)
        if not all(isinstance(value, (str, Path)) for value in (supervisor, desktop_python, supervisor_data)):
            return False, "", {
                "error": "Codex app-server route is missing runner-owned desktop runtime paths",
                "codex_version": codex_version,
                **stdio_session.result_metrics(),
            }

        artifact_dir = stdio_session.root.parent / "codex-app-server-artifacts"
        artifact_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        audit_path = artifact_dir / "codex-app-server-audit.json"
        repo_root = Path(__file__).resolve().parent.parent
        adapter_command = [
            str(desktop_python), "-m", "dp_scenarios.runner.codex_adapter",
            "--codex", str(resolved),
            "--model", model,
            "--effort", effort or "medium",
            "--skill-pack-root", str(ws),
            "--repo-root", str(repo_root),
            "--fixture-dir", "",  # populated below with an empty directory outside ws
            "--artifact-dir", str(artifact_dir),
            "--desktop-supervisor", str(supervisor),
            "--desktop-python", str(desktop_python),
            "--timeout", str(route_timeout),
            "--idle-timeout", str(getattr(stdio_session, "idle_timeout_seconds", 180.0)),
            "--codex-version", codex_version,
            "--mcp-config", str(stdio_session.config_path),
            "--strict-mcp-config",
            "--supervisor-data-dir", str(supervisor_data),
            "--terminal-route",
            "--no-fixture-handoff",
            "--multi-agent-v2",
        ]
        with tempfile.TemporaryDirectory(prefix="nex890-empty-source-") as empty_source:
            adapter_command[adapter_command.index("")] = empty_source
            input_line = json.dumps({"message": {"text": prompt, "attachments": []}}) + "\n"
            try:
                proc = subprocess.Popen(
                    adapter_command,
                    cwd=ws,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    env=env,
                    start_new_session=True,
                )
                stdio_session.attach_process(proc)
                try:
                    stdout, stderr = proc.communicate(
                        input=input_line,
                        timeout=route_timeout + 9,
                    )
                except subprocess.TimeoutExpired as initial_timeout:
                    stdout, stderr = self._timeout_stream_output(initial_timeout)
                    with contextlib.suppress(ProcessLookupError, PermissionError):
                        os.kill(proc.pid, signal.SIGTERM)
                    try:
                        grace_stdout, grace_stderr = proc.communicate(timeout=8)
                        stdout = grace_stdout or stdout
                        stderr = grace_stderr or stderr
                    except subprocess.TimeoutExpired as grace_timeout:
                        stdout, stderr = self._timeout_stream_output(
                            grace_timeout, stdout, stderr
                        )
                        with contextlib.suppress(ProcessLookupError, PermissionError):
                            os.kill(proc.pid, signal.SIGKILL)
                        # If SIGTERM could not run the adapter's finally/close,
                        # remove any app-server descendants before reaping pipes.
                        with contextlib.suppress(ProcessLookupError, PermissionError):
                            os.killpg(proc.pid, signal.SIGKILL)
                        try:
                            kill_stdout, kill_stderr = proc.communicate(timeout=3)
                            stdout = kill_stdout or stdout
                            stderr = kill_stderr or stderr
                        except subprocess.TimeoutExpired as kill_timeout:
                            stdout, stderr = self._timeout_stream_output(
                                kill_timeout, stdout, stderr
                            )
                            for pipe in (proc.stdout, proc.stderr):
                                if pipe is not None:
                                    with contextlib.suppress(OSError):
                                        pipe.close()
                    partial_payload: dict = {}
                    for line in (stdout or "").splitlines():
                        try:
                            candidate = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if isinstance(candidate, dict) and isinstance(candidate.get("result"), dict):
                            partial_payload = candidate
                    partial_result = partial_payload.get("result", {})
                    partial_audit = (
                        partial_payload.get("route_audit")
                        if isinstance(partial_payload.get("route_audit"), dict)
                        else self._read_route_audit(audit_path)
                    )
                    partial_final_answer = partial_result.get("agent_message", "")
                    partial_transcript = partial_result.get("transcript_delta", "")
                    if not isinstance(partial_final_answer, str):
                        partial_final_answer = ""
                    if not isinstance(partial_transcript, str):
                        partial_transcript = ""
                    audit = self._read_route_audit(audit_path)
                    stdio_session.record_agent(
                        status="timeout", error="Codex app-server route exceeded its outer wall-clock deadline"
                    )
                    return False, redact_text(partial_transcript), {
                        "error": "Codex app-server route exceeded its outer wall-clock deadline",
                        "timed_out": True,
                        "codex_version": codex_version,
                        "route_audit": partial_audit or audit,
                        "final_answer": redact_text(partial_final_answer),
                        "input_tokens": partial_result.get("input_tokens", audit.get("input_tokens")),
                        "output_tokens": partial_result.get("output_tokens", audit.get("output_tokens")),
                        "provider_model_calls": partial_result.get("provider_model_calls"),
                        "num_turns": partial_result.get("terminal_result_count", audit.get("turn_count")),
                        "mcp_trace": str(stdio_session.trace_path),
                        "route_audit_path": str(audit_path),
                        **stdio_session.result_metrics(),
                    }
            except (OSError, subprocess.SubprocessError) as exc:
                return False, "", {
                    "error": f"Codex app-server adapter failed: {redact_text(str(exc))}",
                    "codex_version": codex_version,
                    "route_audit": self._read_route_audit(audit_path),
                    "route_audit_path": str(audit_path),
                    **stdio_session.result_metrics(),
                }

        payload: dict = {}
        for line in stdout.splitlines():
            try:
                candidate = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, dict) and isinstance(candidate.get("result"), dict):
                payload = candidate
        result = payload.get("result", {}) if payload else {}
        audit = payload.get("route_audit") if isinstance(payload.get("route_audit"), dict) else {}
        if not audit:
            audit = self._read_route_audit(audit_path)
        transcript = result.get("transcript_delta", "")
        final_answer = result.get("agent_message", "")
        transcript = transcript if isinstance(transcript, str) else ""
        final_answer = final_answer if isinstance(final_answer, str) else ""
        trace_reader_paths = self._review_reader_trace_paths(stdio_session.trace_path)
        audit_ok, matching_reader = self._terminal_route_audit_evidence(
            audit, codex_version, trace_reader_paths
        )
        terminal_ok = bool(
            result.get("terminal_result_subtype") == "success"
            and result.get("terminal_result_is_error") is False
            and result.get("environment_wedged") is False
            and result.get("turn_timed_out") is False
        )
        ok = bool(
            proc.returncode == 0
            and terminal_ok
            and audit_ok
            and final_answer
        )
        error = None
        if not ok:
            error = redact_text(
                result.get("environment_detail")
                or stderr[-1500:]
                or "Codex app-server route ended incomplete or failed its evidence gate"
            )
        stdio_session.record_agent(
            status="passed" if ok else "failed",
            error=error,
        )
        metrics = {
            "is_error": not ok,
            "error": error,
            "final_answer": final_answer,
            "provider_model_calls": result.get("provider_model_calls"),
            "input_tokens": result.get("input_tokens", audit.get("input_tokens")),
            "output_tokens": result.get("output_tokens", audit.get("output_tokens")),
            "num_turns": audit.get("turn_count"),
            "tool_calls": len(result.get("tool_calls", [])) if isinstance(result.get("tool_calls"), list) else 0,
            "codex_version": codex_version,
            "route_audit": audit,
            "route_audit_path": str(audit_path),
            "review_reader_trace_paths": sorted(trace_reader_paths),
            "review_reader_trace_matched": matching_reader,
            "mcp_trace": str(stdio_session.trace_path),
            "terminal_result_subtype": result.get("terminal_result_subtype"),
            "terminal_result_is_error": result.get("terminal_result_is_error"),
        }
        metrics.update(stdio_session.result_metrics())
        return ok, trace if (trace := redact_text(transcript)) else "", metrics
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
        followup_turns: list[FollowupTurn] | None = None,
        before_followup_turn: Callable[[Path, int], None] | None = None,
        source_audit_markers: list[tuple[str, str]] | None = None,
        executable: str | None = None,
        stdio_session: DesktopStdioSession | None = None,
    ) -> tuple[bool, str, dict]:
        route = getattr(stdio_session, "codex_app_server_route", None)
        if route is not None:
            if route != self.TERMINAL_WORKFLOW_ROUTE or stdio_session is None:
                return False, "", {"error": "unsupported Codex app-server route opt-in"}
            return self._run_codex_app_server_route(
                ws,
                prompt,
                model,
                timeout_s,
                effort=effort,
                env_overrides=env_overrides,
                path_prepend=path_prepend,
                executable=executable,
                source_audit_markers=source_audit_markers,
                stdio_session=stdio_session,
            )
        if followup_turns:
            # Loud, not silent. Running turn 1 and returning would produce a
            # single-turn transcript graded against a multi-turn rubric and
            # report the resulting failures as agent quality.
            raise ValueError(
                f"agent backend {self.name!r} cannot drive multi-turn scenarios: "
                f"this scenario scripts {len(followup_turns)} follow-up turn(s), "
                "and codex exec has no persistent-stdin or resume protocol. Run "
                "it with --agent-backend claude."
            )
        if stdio_session is not None:
            try:
                stdio_session.ensure_started()
            except DesktopStdioError as exc:
                return False, "", {
                    "error": redact_text(str(exc)),
                    **stdio_session.result_metrics(),
                }
        # allowed_tools is intentionally unused here: Codex gates capability with
        # a sandbox policy, not a per-tool allowlist, so a scenario's narrowed
        # tool surface cannot be reproduced exactly. Runs of a tool-restricted
        # scenario are therefore not comparable to the same scenario on Claude.
        # skill_pack_dir is intentionally unused here: run.py stages the skills
        # into the workspace (or a mounted dir) and points the agent at them via
        # the prompt, because Codex cannot load a plugin dir. Accepting the arg
        # keeps the AgentBackend interface uniform across providers.
        cmd = [
            executable or self.executable, "exec",
            "--json",
            "--model", model,
            "--sandbox", CODEX_AGENT_SANDBOX,
            "--skip-git-repo-check",
            # Workspace is the primary writable root; extra_dirs (examples repo)
            # are added read/writable alongside so the agent can reference them.
            "-C", str(ws),
        ]
        if stdio_session is not None:
            # Ignore the user's global MCP registry and expose only the
            # runner-owned proxy for this isolated eval cell.
            cmd.append("--ignore-user-config")
            cmd += self._stdio_mcp_config_args(stdio_session)
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
        if stdio_session is not None:
            for key in tuple(env):
                if key == "NXD_EVAL_SOURCE_TOKEN" or _CREDENTIAL_ENV_KEY.search(key):
                    env.pop(key, None)
        try:
            if stdio_session is not None:
                proc = subprocess.Popen(
                    cmd,
                    cwd=ws,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    env=env,
                    start_new_session=True,
                )
                stdio_session.attach_process(proc)
                stdout, stderr = proc.communicate(input=prompt, timeout=timeout_s)
            else:
                completed = subprocess.run(
                    cmd, cwd=ws, input=prompt, capture_output=True, text=True,
                    timeout=timeout_s, env=env,
                )
                proc = completed
                stdout, stderr = completed.stdout, completed.stderr
        except subprocess.TimeoutExpired as exc:
            if stdio_session is not None:
                DesktopStdioSession._kill_process(proc)
                stdio_session.record_agent(
                    status="timeout", error=f"agent timed out after {timeout_s}s"
                )
            result = {
                "error": f"agent timed out after {timeout_s}s",
                "source_access_audit": source_access_audit(
                    timeout_stdout(exc), source_audit_markers, incomplete=True
                ),
            }
            if stdio_session is not None:
                result.update(stdio_session.result_metrics())
            return False, "", result
        except OSError as exc:
            error = f"could not start codex: {redact_text(str(exc))}"
            if stdio_session is not None:
                stdio_session.record_agent(status="failed", error=error)
                return False, "", {
                    "error": error,
                    **stdio_session.result_metrics(),
                }
            raise
        if proc.returncode != 0:
            # Same stdout-vs-stderr fallback as the Claude paths. No Codex
            # stdout-only failure is known today, but a CLI that dies with an
            # empty stderr reports as a bare "codex exited 1:" either way, and
            # the fallback costs nothing when stderr is populated.
            detail = stderr.strip() or stdout.strip() or "(no output)"
            error = f"codex exited {proc.returncode}: {detail[-2000:]}"
            if stdio_session is not None:
                stdio_session.record_agent(status="failed", error=error)
            result = {
                "error": error,
                "source_access_audit": source_access_audit(stdout, source_audit_markers),
            }
            if stdio_session is not None:
                result.update(stdio_session.result_metrics())
            return False, "", result

        # Do not let the trace parser's truncation decide isolation evidence.
        audit = source_access_audit(stdout, source_audit_markers)
        trace, metrics = self._trace_from_stream(stdout)
        if not trace and not metrics.get("final_answer"):
            error = f"empty stream output: {stdout[-2000:]}"
            if stdio_session is not None:
                stdio_session.record_agent(status="failed", error=error)
            result = {
                "error": error,
                "source_access_audit": source_access_audit(stdout, source_audit_markers),
            }
            if stdio_session is not None:
                result.update(stdio_session.result_metrics())
            return False, "", result
        metrics["source_access_audit"] = audit
        ok = not metrics.get("is_error", False)
        if stdio_session is not None:
            stdio_session.record_agent(
                status="passed" if ok else "failed",
                error=None if ok else "codex agent reported an error",
            )
            metrics.update(stdio_session.result_metrics())
        return ok, trace, metrics

    @staticmethod
    def _trace_from_stream(stdout: str) -> tuple[str, dict]:
        """Parse Codex JSONL events into the same trace + metrics shape Claude
        produces, so the judge prompt and reports are provider-independent.

        Codex event vocabulary (``codex exec --json``):
          * ``item.completed`` with ``item.type == "agent_message"`` → assistant
            text; the LAST one is the final answer.
          * ``item.completed`` with ``item.type == "command_execution"`` → a
            shell tool call (``command`` + truncated ``aggregated_output``).
          * ``item.completed`` with ``item.type == "mcp_tool_call"`` → an MCP
            tool call plus its result, rendered with Claude's stable tool-name
            shape so the judge can grade provider-independent evidence.
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
        shell_calls = 0
        shell_successes = 0
        sandbox_failures = 0
        metrics: dict = {"is_error": False}
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            # A valid JSON scalar (`null`, `5`, `"..."`) parses fine, so `.get`
            # on it raises AttributeError — not a JSONDecodeError, so it escapes
            # every handler above and kills the run rather than erroring it.
            if not isinstance(d, dict):
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
                    shell_calls += 1
                    if exit_code == 0:
                        shell_successes += 1
                    elif _is_sandbox_failure(out):
                        sandbox_failures += 1
                elif itype == "mcp_tool_call":
                    tool_calls += 1
                    server = str(item.get("server", ""))
                    tool = str(item.get("tool", ""))
                    tool_name = f"mcp__{server}__{tool}"
                    arguments = _tool_input_json(item.get("arguments", {}))
                    parts.append(
                        f"[tool_use:{tool_name}] {arguments[:600]}"
                    )
                    result = item.get("result")
                    error = item.get("error")
                    if error:
                        rendered = json.dumps(error, ensure_ascii=False)
                    elif isinstance(result, dict):
                        content = result.get("content")
                        if isinstance(content, list):
                            rendered = " ".join(
                                str(block.get("text", ""))
                                for block in content
                                if isinstance(block, dict) and "text" in block
                            )
                        else:
                            rendered = json.dumps(result, ensure_ascii=False)
                    else:
                        rendered = str(result or "")
                    parts.append(f"[tool_result] {rendered[:TOOL_RESULT_HEAD_CHARS]}")
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
                # `codex exec` emits one turn.completed per invocation, whose
                # usage covers the whole run — but that is CLI behaviour we do
                # not control, and overwriting would silently undercount if it
                # ever emitted per-turn usage across a multi-turn run. Summing
                # is correct either way: with a single event it is the identity.
                usage = d.get("usage", {}) or {}
                for key in (
                    "input_tokens",
                    "output_tokens",
                    "reasoning_output_tokens",
                    "cached_input_tokens",
                ):
                    value = usage.get(key)
                    if value is not None:
                        metrics[key] = (metrics.get(key) or 0) + value
                metrics["is_error"] = False
        metrics["is_error"] = errored or metrics.get("is_error", False)
        metrics["tool_calls"] = tool_calls
        metrics["shell_calls"] = shell_calls
        metrics["sandbox_failures"] = sandbox_failures
        trace = "\n".join(parts)
        # When the sandbox refuses to launch commands, the agent never gets to
        # attempt the task: it cannot read its fixtures or run anything. The
        # judge still grades the transcript and correctly finds no evidence,
        # which is indistinguishable from a skill regression. Flag it so the
        # caller can classify the cell as an infrastructure failure instead.
        #
        # The signature has to be looked for across the whole trace, not just
        # in shell results. Observed shapes on a GitHub-hosted runner: every
        # shell call fails with the bwrap error in its output; a shell call
        # fails with EMPTY output and the agent names the error only in prose;
        # and the agent retries, gives up, and reports the error having logged
        # no shell call at all. Requiring zero successful shell calls keeps this
        # narrow — a run that got real work done is never reclassified, and a
        # command that failed on its own merits does not count as success.
        metrics["shell_successes"] = shell_successes
        metrics["sandbox_blocked"] = _is_sandbox_failure(trace) and shell_successes == 0
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
                self.executable, "exec",
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
                detail = proc.stderr.strip() or proc.stdout.strip() or "(no output)"
                return {
                    "error": f"judge exited {proc.returncode}: {detail[-1000:]}",
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
        if not isinstance(d, dict):
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
