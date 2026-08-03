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
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Protocol


# Cap each tool-result block fed to the judge so a huge file read doesn't blow
# up the judge prompt; the head is enough to see what the agent inspected.
TOOL_RESULT_HEAD_CHARS = 1500


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
class AgentBackend(Protocol):
    """Drives the agent-under-test over one scenario workspace."""

    #: Stable identifier used on the CLI (``--agent-backend <name>``) and in
    #: the cache key so switching providers invalidates cached transcripts.
    name: str

    #: Whether this provider can drive scripted follow-up turns. A provider that
    #: cannot MUST reject ``followup_turns`` loudly rather than running turn 1
    #: and returning: that would grade a multi-turn scenario against a
    #: single-turn transcript and report a bogus pass rate.
    supports_multi_turn: bool

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
    supports_multi_turn = True

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
        env_overrides: dict | None, path_prepend: Path | None
    ) -> dict[str, str]:
        env = dict(os.environ)
        if env_overrides:
            env.update(env_overrides)
        if path_prepend is not None:
            env["PATH"] = f"{path_prepend}{os.pathsep}{env.get('PATH', '')}"
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
        source_audit_markers: list[tuple[str, str]] | None = None,
        executable: str | None = None,
    ) -> tuple[bool, str, dict]:
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
                source_audit_markers=source_audit_markers,
            )
        cmd = [executable or "claude", "-p", prompt] + self._agent_command(
            ws, model, extra_dirs=extra_dirs, effort=effort,
            skill_pack_dir=skill_pack_dir, allowed_tools=allowed_tools,
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
        source_audit_markers: list[tuple[str, str]] | None,
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
            "claude", "-p",
            "--input-format", "stream-json",
            "--session-id", session_id,
        ] + self._agent_command(
            ws, model, extra_dirs=extra_dirs, effort=effort,
            skill_pack_dir=skill_pack_dir, allowed_tools=allowed_tools,
        )
        env = self._agent_env(env_overrides, path_prepend)

        deadline = time.monotonic() + timeout_s
        try:
            proc = subprocess.Popen(
                cmd, cwd=ws, env=env, text=True, bufsize=1,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except OSError as exc:
            return False, "", {"error": f"could not start claude: {exc}"}

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
            # The trace stays "" — a partial transcript must never be graded, and
            # returning one here would let a run that died mid-conversation be
            # scored against the full rubric as an agent failure. But the turns
            # that DID complete are the diagnosis for a late-turn timeout, so
            # they travel in metrics where the judge never sees them.
            partial = "\n".join(t for t, _ in segments).strip()
            meta: dict = {"error": f"{error}: {detail[-2000:]}" if detail else error}
            meta["source_access_audit"] = source_access_audit(
                "".join(raw_stdout_chunks), source_audit_markers
            )
            if partial:
                meta["partial_trace"] = partial[-PARTIAL_TRACE_CHARS:]
                meta["partial_segments"] = len(segments)
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
        if not trace and not metrics.get("final_answer"):
            detail = _failure_detail()
            return False, "", {
                "error": f"empty stream output (exit {returncode}): {detail[-2000:]}",
                "source_access_audit": source_access_audit(
                    "".join(raw_stdout_chunks), source_audit_markers
                ),
            }
        # A nonzero exit fails the run exactly as it does on the single-turn
        # path. A CLI that emits its result events and then dies with a fatal
        # error would otherwise be graded ok on a transcript it disowned.
        if returncode != 0:
            detail = _failure_detail()
            reason = (
                "did not exit after its input was closed"
                if killed_on_close else f"exited {returncode}"
            )
            metrics["error"] = f"claude {reason}: {detail[-2000:]}"
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
    # Concatenating a scenario's turns into one prompt would run without error
    # while measuring a different thing entirely: an agent told the correction
    # up front never has to stop and ask, which is usually the behaviour under
    # test. So multi-turn is refused, not approximated.
    supports_multi_turn = False

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
        source_audit_markers: list[tuple[str, str]] | None = None,
        executable: str | None = None,
    ) -> tuple[bool, str, dict]:
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
        # allowed_tools is intentionally unused here: Codex gates capability with
        # a sandbox policy, not a per-tool allowlist, so a scenario's narrowed
        # tool surface cannot be reproduced exactly. Runs of a tool-restricted
        # scenario are therefore not comparable to the same scenario on Claude.
        # skill_pack_dir is intentionally unused here: run.py stages the skills
        # into the workspace (or a mounted dir) and points the agent at them via
        # the prompt, because Codex cannot load a plugin dir. Accepting the arg
        # keeps the AgentBackend interface uniform across providers.
        cmd = [
            executable or "codex", "exec",
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
        except subprocess.TimeoutExpired as exc:
            return False, "", {"error": f"agent timed out after {timeout_s}s",
                               "source_access_audit": source_access_audit(
                                   timeout_stdout(exc), source_audit_markers, incomplete=True
                               )}
        if proc.returncode != 0:
            # Same stdout-vs-stderr fallback as the Claude paths. No Codex
            # stdout-only failure is known today, but a CLI that dies with an
            # empty stderr reports as a bare "codex exited 1:" either way, and
            # the fallback costs nothing when stderr is populated.
            detail = proc.stderr.strip() or proc.stdout.strip() or "(no output)"
            return False, "", {"error": f"codex exited {proc.returncode}: {detail[-2000:]}",
                                "source_access_audit": source_access_audit(proc.stdout, source_audit_markers)}

        # Do not let the trace parser's truncation decide isolation evidence.
        audit = source_access_audit(proc.stdout, source_audit_markers)
        trace, metrics = self._trace_from_stream(proc.stdout)
        if not trace and not metrics.get("final_answer"):
            return False, "", {"error": f"empty stream output: {proc.stdout[-2000:]}",
                                "source_access_audit": source_access_audit(proc.stdout, source_audit_markers)}
        metrics["source_access_audit"] = audit
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
