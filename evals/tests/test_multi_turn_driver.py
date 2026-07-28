"""The multi-turn driver must not weaken the single-turn path or the gates.

Multi-turn adds a second way for a transcript to be produced, and the risks are
all failures that still look green:

1. A scenario declaring turns runs on a provider that cannot drive them, turn 1
   is graded against a multi-turn rubric, and the resulting failures are read as
   agent quality rather than an unsupported provider.
2. Per-turn metrics overwrite instead of accumulate, so an N-turn run reports
   one turn's tool calls — an efficiency regression rendered as an improvement.
3. The single-turn path quietly acquires multi-turn machinery and starts
   failing (or behaving differently) for scenarios that script no turns at all.

So these tests assert the refusal is loud, the folding is arithmetic, and the
single-turn call is byte-for-byte the command it always was.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

EVALS_DIR = Path(__file__).resolve().parents[1]
if str(EVALS_DIR) not in sys.path:
    sys.path.insert(0, str(EVALS_DIR))

import eval_backends as eb  # noqa: E402


def _load_run_module():
    spec = importlib.util.spec_from_file_location("evals_run", EVALS_DIR / "run.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------- #
# Turn declaration parsing
# --------------------------------------------------------------------------- #
def test_absent_turns_is_single_turn():
    assert eb.parse_followup_turns(None) == []
    assert eb.parse_followup_turns([]) == []


def test_turn_defaults_to_always():
    """`always` is the default on purpose: a conditional default would let one
    missed sentinel withhold the follow-up and leave the whole remaining rubric
    ungraded, converting one boundary miss into a wall of false negatives."""
    (turn,) = eb.parse_followup_turns([{"text": "go ahead"}])
    assert turn.when == eb.WHEN_ALWAYS
    assert turn.timeout_s is None


@pytest.mark.parametrize(
    "raw",
    [
        "not-a-list",
        [{"when": "always"}],           # missing text
        [{"text": "   "}],              # blank text
        [{"text": "x", "when": "maybe"}],
        [{"text": "x", "timeout_s": 0}],
        [{"text": "x", "timeout_s": "60"}],
        # `bool` subclasses `int`, so a bare isinstance check accepts this and
        # silently installs a ~1-second turn cap nobody wrote.
        [{"text": "x", "timeout_s": True}],
        [{"text": "x", "timeout_s": False}],
        ["just a string"],
    ],
)
def test_malformed_turns_raise(raw):
    """Malformed turns must raise, never be dropped: a silently ignored turn
    grades a multi-turn scenario against a single-turn transcript."""
    with pytest.raises(ValueError):
        eb.parse_followup_turns(raw)


# --------------------------------------------------------------------------- #
# Boundary sentinel
# --------------------------------------------------------------------------- #
def test_sentinel_matches_only_on_the_trailing_line():
    assert eb.awaiting_input(f"Here is my proposal.\n{eb.TURN_BOUNDARY_SENTINEL}")
    assert eb.awaiting_input(f"proposal\n{eb.TURN_BOUNDARY_SENTINEL}\n\n  ")
    # Merely discussing the marker is not a hit.
    assert not eb.awaiting_input(
        f"I will emit {eb.TURN_BOUNDARY_SENTINEL} when I stop.\nBuilding now."
    )
    assert not eb.awaiting_input("")
    assert not eb.awaiting_input("done")


# --------------------------------------------------------------------------- #
# Metrics folding
# --------------------------------------------------------------------------- #
def test_turn_metrics_are_summed_not_overwritten():
    """The stream parser rebuilds its counters per call, so the run-level
    numbers have to be folded. Taking the last turn's dict would report a
    3-turn run as if it cost one turn."""
    merged = eb._merge_turn_metrics([
        {"tool_calls": 3, "num_turns": 2, "duration_ms": 100,
         "input_tokens": 10, "output_tokens": 1, "total_cost_usd": 0.5,
         "final_answer": "first", "is_error": False},
        {"tool_calls": 5, "num_turns": 4, "duration_ms": 250,
         "input_tokens": 20, "output_tokens": 2, "total_cost_usd": 0.25,
         "final_answer": "second", "is_error": False},
    ])
    assert merged["tool_calls"] == 8
    assert merged["num_turns"] == 6
    assert merged["duration_ms"] == 350
    assert merged["input_tokens"] == 30
    assert merged["output_tokens"] == 3
    assert merged["total_cost_usd"] == 0.75
    # The conversation's answer is the LAST turn's, not a concatenation.
    assert merged["final_answer"] == "second"


def test_any_turn_error_taints_the_run():
    merged = eb._merge_turn_metrics([
        {"final_answer": "a", "is_error": True},
        {"final_answer": "b", "is_error": False},
    ])
    assert merged["is_error"] is True


# --------------------------------------------------------------------------- #
# Provider capability
# --------------------------------------------------------------------------- #
def test_codex_refuses_multi_turn_loudly():
    """Never degrade to single-turn: a turn-1-only transcript graded against a
    multi-turn rubric reads as an agent regression, not a provider gap."""
    with pytest.raises(ValueError, match="cannot drive multi-turn"):
        eb.CodexBackend().run_agent(
            Path("/tmp"), "prompt", "model", 60,
            followup_turns=[eb.FollowupTurn(text="go ahead")],
        )


def test_codex_still_runs_single_turn(monkeypatch):
    """The refusal must be scoped to scripted turns — passing None or [] leaves
    the existing Codex path completely alone."""
    calls = []

    class _Completed:
        returncode = 0
        stdout = json.dumps({
            "type": "item.completed",
            "item": {"type": "agent_message", "text": "done"},
        })
        stderr = ""

    def _fake_run(cmd, **kwargs):
        calls.append(cmd)
        return _Completed()

    monkeypatch.setattr(eb.subprocess, "run", _fake_run)
    ok, trace, metrics = eb.CodexBackend().run_agent(
        Path("/tmp"), "prompt", "model", 60, followup_turns=[]
    )
    assert ok and calls and metrics["final_answer"] == "done"


def test_backends_declare_the_capability():
    assert eb.ClaudeBackend.supports_multi_turn is True
    assert eb.CodexBackend.supports_multi_turn is False


# --------------------------------------------------------------------------- #
# Single-turn path is untouched
# --------------------------------------------------------------------------- #
def test_single_turn_claude_command_is_unchanged(monkeypatch):
    """The pre-existing invocation shape is load-bearing: `-p <prompt>` with a
    one-shot subprocess.run, no stream-json input, no session id."""
    seen = {}

    class _Completed:
        returncode = 0
        stdout = json.dumps({
            "type": "result", "result": "answer", "is_error": False,
            "num_turns": 1, "usage": {},
        })
        stderr = ""

    def _fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["kwargs"] = kwargs
        return _Completed()

    monkeypatch.setattr(eb.subprocess, "run", _fake_run)
    ok, _trace, metrics = eb.ClaudeBackend().run_agent(
        Path("/tmp"), "the prompt", "the-model", 42,
    )
    cmd = seen["cmd"]
    assert ok and metrics["final_answer"] == "answer"
    assert cmd[:3] == ["claude", "-p", "the prompt"]
    assert "--input-format" not in cmd
    assert "--session-id" not in cmd
    assert seen["kwargs"]["timeout"] == 42


def test_single_turn_never_opens_a_persistent_process(monkeypatch):
    """A single-turn run must not touch Popen at all — the two paths are
    deliberately disjoint so multi-turn work cannot regress single-turn."""
    class _Completed:
        returncode = 0
        stdout = json.dumps({"type": "result", "result": "a", "is_error": False})
        stderr = ""

    monkeypatch.setattr(eb.subprocess, "run", lambda *a, **k: _Completed())

    def _boom(*_a, **_k):
        raise AssertionError("single-turn must not start a persistent process")

    monkeypatch.setattr(eb.subprocess, "Popen", _boom)
    ok, _t, _m = eb.ClaudeBackend().run_agent(Path("/tmp"), "p", "m", 10)
    assert ok


def test_shared_flags_match_between_paths():
    """Capability flags live in one builder, so the multi-turn process can never
    silently run with a different tool surface or skill pack than single-turn."""
    backend = eb.ClaudeBackend()
    shared = backend._agent_command(
        Path("/ws"), "m", extra_dirs=[Path("/x")], effort="high",
        skill_pack_dir=Path("/pack"), allowed_tools="Read,Bash",
    )
    for flag in ("--allowedTools", "--plugin-dir", "--add-dir", "--effort",
                 "--setting-sources", "--output-format"):
        assert flag in shared
    assert shared[shared.index("--allowedTools") + 1] == "Read,Bash"


# --------------------------------------------------------------------------- #
# The turn loop, driven against a fake CLI
#
# These exercise the real Popen/reader-thread/deadline machinery — including the
# wedge-and-kill escalation, which is otherwise only reached by a hung agent in
# production and would ship untested.
# --------------------------------------------------------------------------- #
FAKE_CLI = r'''#!/usr/bin/env python3
"""Stands in for `claude -p --input-format stream-json`.

Reads one JSON user message per line and answers each with an assistant block
plus a result event, mimicking the real stream well enough to drive the loop.
Env knobs select the failure being tested.
"""
import json, os, sys, time

mode = os.environ.get("FAKE_MODE", "normal")
noise = int(os.environ.get("FAKE_STDERR_LINES", "0"))
turn = 0
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    turn += 1
    msg = json.loads(line)
    text = msg["message"]["content"][0]["text"]
    if mode == "wedge" and turn == 2:
        time.sleep(600)          # never answers: forces the deadline path
    if mode == "chatty" and turn == 2:
        # Streams forever without ever emitting a result event. A per-turn cap
        # recomputed per line would be reset by each of these and never fire.
        while True:
            print(json.dumps({"type": "assistant", "message": {"content": [
                {"type": "text", "text": "heartbeat"}]}}), flush=True)
            time.sleep(0.2)
    if mode == "die" and turn == 2:
        sys.exit(3)              # dies mid-conversation
    if mode == "dirty_exit" and turn == 2:
        # Answers in full, THEN dies. The transcript looks complete, so an
        # ignored exit code grades a disowned run as success.
        print(json.dumps({"type": "assistant", "message": {"content": [
            {"type": "text", "text": f"saw: {text}"}]}}), flush=True)
        print(json.dumps({"type": "result", "result": "answer 2",
                          "is_error": False, "num_turns": 1}), flush=True)
        sys.stderr.write("fatal: session store corrupted\n")
        sys.stderr.flush()
        sys.exit(1)
    if mode == "hang_on_close" and turn == 2:
        print(json.dumps({"type": "assistant", "message": {"content": [
            {"type": "text", "text": f"saw: {text}"}]}}), flush=True)
        print(json.dumps({"type": "result", "result": "answer 2",
                          "is_error": False, "num_turns": 1}), flush=True)
        time.sleep(600)          # never exits after stdin closes
    for _ in range(noise):       # fill the stderr pipe to prove it is drained
        sys.stderr.write("x" * 512 + "\n")
    sys.stderr.flush()
    print(json.dumps({"type": "assistant", "message": {"content": [
        {"type": "text", "text": f"saw: {text}"},
        {"type": "tool_use", "name": "Read", "input": {"n": turn}},
    ]}}), flush=True)
    answer = os.environ.get(f"FAKE_ANSWER_{turn}", f"answer {turn}")
    print(json.dumps({
        "type": "result", "result": answer, "is_error": False,
        "num_turns": 1, "duration_ms": 10, "usage": {
            "input_tokens": 5, "output_tokens": 1},
    }), flush=True)
'''


@pytest.fixture
def fake_cli(tmp_path, monkeypatch):
    """Put a fake `claude` on PATH and return its bin dir."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    exe = bin_dir / "claude"
    exe.write_text(FAKE_CLI, encoding="utf-8")
    exe.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    return bin_dir


def test_multi_turn_drives_every_turn(fake_cli, tmp_path):
    ok, trace, metrics = eb.ClaudeBackend().run_agent(
        tmp_path, "first prompt", "m", 60,
        followup_turns=[
            eb.FollowupTurn(text="second message"),
            eb.FollowupTurn(text="third message"),
        ],
    )
    assert ok, metrics
    assert metrics["turns_sent"] == 3
    assert metrics["skipped_turns"] == []
    # Every turn actually reached the CLI, in order.
    assert "saw: first prompt" in trace
    assert "saw: second message" in trace
    assert "saw: third message" in trace
    # Separators are present and ordered, so a trace-reading checker can locate
    # the boundary and compare write positions against it.
    i2 = trace.index("[user_turn 2]")
    i3 = trace.index("[user_turn 3]")
    assert trace.index("saw: first prompt") < i2 < trace.index("saw: second message")
    assert i2 < i3 < trace.index("saw: third message")
    # Folded, not overwritten: one tool call per turn.
    assert metrics["tool_calls"] == 3
    assert metrics["num_turns"] == 3
    assert metrics["final_answer"] == "answer 3"
    assert metrics["session_id"]


def test_conditional_turn_is_skipped_without_the_sentinel(fake_cli, tmp_path):
    ok, trace, metrics = eb.ClaudeBackend().run_agent(
        tmp_path, "first", "m", 60,
        followup_turns=[eb.FollowupTurn(text="second", when="awaiting_input")],
    )
    assert ok
    assert metrics["turns_sent"] == 1
    assert metrics["skipped_turns"] == [2]
    assert metrics["awaited_input_turns"] == []
    assert "second" not in trace


def test_conditional_turn_fires_on_the_sentinel(fake_cli, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_ANSWER_1", f"proposal\n{eb.TURN_BOUNDARY_SENTINEL}")
    ok, trace, metrics = eb.ClaudeBackend().run_agent(
        tmp_path, "first", "m", 60,
        followup_turns=[eb.FollowupTurn(text="second", when="awaiting_input")],
    )
    assert ok
    assert metrics["turns_sent"] == 2
    assert metrics["skipped_turns"] == []
    assert metrics["awaited_input_turns"] == [1]
    assert "saw: second" in trace


def test_unconditional_turn_fires_without_the_sentinel(fake_cli, tmp_path):
    """The default must not be gated on the marker: a missed marker would
    otherwise withhold the turn and leave the rest of the rubric ungraded."""
    ok, _trace, metrics = eb.ClaudeBackend().run_agent(
        tmp_path, "first", "m", 60,
        followup_turns=[eb.FollowupTurn(text="second")],
    )
    assert ok and metrics["turns_sent"] == 2 and metrics["skipped_turns"] == []


def test_a_wedged_turn_times_out_and_kills_the_process(fake_cli, tmp_path):
    """The kill must happen BEFORE returning: the caller's cleanup guard sweeps
    pid files in its `finally`, and a CLI still alive then can re-write one
    after the sweep and leak a supervisor for the rest of the run."""
    ok, trace, metrics = eb.ClaudeBackend().run_agent(
        tmp_path, "first", "m", 5,
        env_overrides={"FAKE_MODE": "wedge"},
        followup_turns=[eb.FollowupTurn(text="second")],
    )
    assert not ok
    assert not trace
    # Names the turn: "timed out" alone on a multi-turn run is undiagnosable.
    assert "during turn 2" in metrics["error"]
    # Nothing of ours is still running: no `claude` child survived the abort.
    assert not _surviving_fake_cli_pids(fake_cli)


def test_a_process_death_mid_conversation_is_not_graded_as_success(
    fake_cli, tmp_path
):
    """A partial transcript must never be reported ok — it would be graded
    against the full rubric and read as an agent failure."""
    ok, _trace, metrics = eb.ClaudeBackend().run_agent(
        tmp_path, "first", "m", 60,
        env_overrides={"FAKE_MODE": "die"},
        followup_turns=[eb.FollowupTurn(text="second")],
    )
    assert not ok
    assert "turn 2" in metrics["error"]


def test_a_chatty_stderr_does_not_deadlock_the_conversation(fake_cli, tmp_path):
    """stderr is a PIPE and must be drained continuously. Left unread, the child
    blocks once the OS buffer fills and the run dies as a bogus turn timeout —
    an infrastructure failure indistinguishable from an agent failure."""
    ok, _trace, metrics = eb.ClaudeBackend().run_agent(
        tmp_path, "first", "m", 60,
        # ~512KB per turn, far past the ~64KB pipe buffer.
        env_overrides={"FAKE_STDERR_LINES": "1000"},
        followup_turns=[eb.FollowupTurn(text="second")],
    )
    assert ok, metrics
    assert metrics["turns_sent"] == 2


def test_the_run_budget_is_whole_run_not_per_turn(fake_cli, tmp_path):
    """`timeout_s` must bound the conversation, not each turn, or an N-turn
    pocket scenario silently runs N times its budget."""
    started = time.monotonic()
    ok, _trace, metrics = eb.ClaudeBackend().run_agent(
        tmp_path, "first", "m", 4,
        env_overrides={"FAKE_MODE": "wedge"},
        followup_turns=[eb.FollowupTurn(text="second")],
    )
    elapsed = time.monotonic() - started
    assert not ok and "timed out after 4s" in metrics["error"]
    # Comfortably under 2x the budget, which is what a per-turn deadline would
    # have allowed for these two turns.
    assert elapsed < 8, elapsed


def test_a_per_turn_cap_is_wall_clock_not_a_gap_between_lines(fake_cli, tmp_path):
    """A turn that streams continuously must still trip its own cap.

    Recomputing the cap inside the read loop makes every streamed line reset it,
    so a turn emitting heartbeats or tool chatter runs to the RUN deadline while
    reporting a per-turn budget it never enforced — the per-turn cap silently
    becomes decoration on exactly the runaway turns it exists to bound.
    """
    started = time.monotonic()
    ok, _trace, metrics = eb.ClaudeBackend().run_agent(
        tmp_path, "first", "m", 60,
        env_overrides={"FAKE_MODE": "chatty"},
        followup_turns=[eb.FollowupTurn(text="second", timeout_s=1)],
    )
    elapsed = time.monotonic() - started
    assert not ok
    # Nowhere near the 60s run budget: the TURN cap is what stopped it.
    assert elapsed < 15, elapsed
    # And it says so — blaming the run budget sends the reader to raise
    # --agent-timeout, which cannot fix a turn-level cap.
    assert "1s turn budget" in metrics["error"]
    assert "during turn 2" in metrics["error"]
    assert not _surviving_fake_cli_pids(fake_cli)


def test_the_run_budget_is_still_named_when_it_is_the_one_that_expires(
    fake_cli, tmp_path
):
    """The turn-vs-run attribution must not flip the other way: a wedged turn
    with no per-turn cap still reports the run budget."""
    ok, _trace, metrics = eb.ClaudeBackend().run_agent(
        tmp_path, "first", "m", 4,
        env_overrides={"FAKE_MODE": "wedge"},
        followup_turns=[eb.FollowupTurn(text="second")],
    )
    assert not ok
    assert "timed out after 4s" in metrics["error"]
    assert "turn budget" not in metrics["error"]


def test_a_dirty_exit_after_a_complete_transcript_is_not_success(
    fake_cli, tmp_path
):
    """Multi-turn must fail a nonzero exit exactly as single-turn does. A CLI
    that emits its result events and then dies has disowned the run; grading the
    transcript ok reports an error path as agent success."""
    ok, _trace, metrics = eb.ClaudeBackend().run_agent(
        tmp_path, "first", "m", 60,
        env_overrides={"FAKE_MODE": "dirty_exit"},
        followup_turns=[eb.FollowupTurn(text="second")],
    )
    assert not ok, metrics
    assert metrics["exit_code"] == 1
    assert "session store corrupted" in metrics["error"]


def test_a_cli_that_hangs_on_close_is_recorded_not_silently_passed(
    fake_cli, tmp_path
):
    """A CLI SIGKILL'd because it never exited after stdin closed must not
    report a clean run — and must not leave the child behind."""
    ok, _trace, metrics = eb.ClaudeBackend().run_agent(
        tmp_path, "first", "m", 60,
        env_overrides={"FAKE_MODE": "hang_on_close"},
        followup_turns=[eb.FollowupTurn(text="second")],
    )
    assert not ok, metrics
    assert metrics["killed_on_close"] is True
    assert "did not exit after its input was closed" in metrics["error"]
    assert not _surviving_fake_cli_pids(fake_cli)


def test_a_clean_multi_turn_run_records_its_exit_code(fake_cli, tmp_path):
    """The exit-code gate must not fail healthy runs."""
    ok, _trace, metrics = eb.ClaudeBackend().run_agent(
        tmp_path, "first", "m", 60,
        followup_turns=[eb.FollowupTurn(text="second")],
    )
    assert ok, metrics
    assert metrics["exit_code"] == 0
    assert metrics["killed_on_close"] is False


def _surviving_fake_cli_pids(bin_dir: Path) -> list[int]:
    out = subprocess.run(
        ["pgrep", "-f", str(bin_dir / "claude")],
        capture_output=True, text=True,
    )
    return [int(p) for p in out.stdout.split() if p.strip().isdigit()]


# --------------------------------------------------------------------------- #
# run.py wiring
# --------------------------------------------------------------------------- #
def test_cache_key_changes_with_turn_text():
    """Turn scripts are agent INPUT, not grading. _fixtures_fingerprint only
    covers fixtures/, so without turns in the key an edited script would replay
    a transcript recorded against the old wording."""
    run = _load_run_module()
    skill_set = run.SkillSet(name="s", description="d", skills=["a"])
    scenario = EVALS_DIR / "public" / "coauthor-supplied-rubric"
    args = (skill_set, scenario, "prompt", "claude", "model", "")

    base = run._agent_cache_key(*args)
    one = run._agent_cache_key(*args, [eb.FollowupTurn(text="approved")])
    two = run._agent_cache_key(*args, [eb.FollowupTurn(text="approved, but")])

    assert base != one != two
    assert base != two
    assert run._agent_cache_key(*args, []) == base
    assert run._agent_cache_key(*args, None) == base


def test_single_turn_cache_keys_survive_this_change():
    """A single-turn scenario must hash to exactly what it hashed to before
    multi-turn existed. Appending even an empty field would silently discard
    every cached transcript in the repo and re-bill every scenario."""
    run = _load_run_module()
    skill_set = run.SkillSet(name="s", description="d", skills=["a"])
    scenario = EVALS_DIR / "public" / "coauthor-supplied-rubric"

    # The pre-change formula, reproduced literally.
    h = hashlib.sha256()
    for part in (
        skill_set.name,
        ",".join(sorted(skill_set.skills)),
        scenario.name,
        "prompt",
        "claude",
        "model",
        "",
        run._fixtures_fingerprint(scenario),
        "",  # pocket_runtime_key: this scenario is not a pocket cell
    ):
        h.update(part.encode())
        h.update(b"\x00")

    assert run._agent_cache_key(
        skill_set, scenario, "prompt", "claude", "model", ""
    ) == h.hexdigest()


def test_judge_prompt_omits_the_block_for_single_turn():
    run = _load_run_module()
    assert run.build_scripted_turns_block({"checks": []}) == ""
    assert run.build_scripted_turns_block({"turns": [], "checks": []}) == ""


def test_judge_prompt_quotes_scripted_turns_verbatim():
    """The judge must be able to attribute a correction to the user; otherwise
    it may credit the agent for the user's idea."""
    run = _load_run_module()
    block = run.build_scripted_turns_block(
        {"turns": [{"text": "cap it at 3, not 2"}]}, {}
    )
    assert "cap it at 3, not 2" in block
    assert "user_turn 2" in block
    assert "not authored by the agent" in block


def test_judge_is_told_to_fail_checks_whose_turn_never_fired():
    """A skipped turn leaves its checks ungradeable. Silence here produces a
    judge guess — most likely a false negative blamed on the agent."""
    run = _load_run_module()
    block = run.build_scripted_turns_block(
        {"turns": [{"text": "approved", "when": "awaiting_input"}]},
        {"skipped_turns": [2]},
    )
    assert "[NOT SENT]" in block
    assert "turn not sent" in block


def test_check_turn_annotation_reaches_the_judge():
    run = _load_run_module()
    scenario = EVALS_DIR / "public" / "coauthor-supplied-rubric"
    checks = {
        "name": "n",
        "turns": [{"text": "approved with corrections"}],
        "checks": [{"id": "applies-corrections", "check": "…", "turn": 2}],
    }
    prompt = run.build_judge_prompt(scenario, checks, "trace", "answer")
    assert "(about user_turn 2)" in prompt
    assert "approved with corrections" in prompt


def test_run_one_refuses_multi_turn_on_a_backend_that_cannot(tmp_path, monkeypatch):
    """Refused BEFORE a workspace is built, so no agent run is burned to learn
    the provider cannot express the scenario."""
    run = _load_run_module()
    scenario = tmp_path / "scenario"
    scenario.mkdir()
    (scenario / "prompt.md").write_text("--- TASK ---\ndo it\n", encoding="utf-8")
    (scenario / "checks.json").write_text(json.dumps({
        "name": "n",
        "turns": [{"text": "go ahead"}],
        "checks": [{"id": "c", "check": "…"}],
    }), encoding="utf-8")

    def _no_workspace(*_a, **_k):
        raise AssertionError("workspace must not be built for a refused scenario")

    monkeypatch.setattr(run, "build_workspace", _no_workspace)

    args = type("A", (), {
        "agent_backend": "codex", "judge_backend": "codex",
        "agent_model": "m", "judge_model": "m", "agent_effort": "",
        "judge_effort": "", "agent_timeout": 60, "judge_timeout": 60,
        "cache_dir": None, "docs_base": "https://example.invalid",
    })()
    res = run.run_one(run.SkillSet(name="s", description="d", skills=[]), scenario, args)
    assert not res.ok
    assert "cannot drive multi-turn" in res.error


def test_run_one_reports_a_malformed_turn_declaration(tmp_path):
    run = _load_run_module()
    scenario = tmp_path / "scenario"
    scenario.mkdir()
    (scenario / "prompt.md").write_text("--- TASK ---\ndo it\n", encoding="utf-8")
    (scenario / "checks.json").write_text(json.dumps({
        "name": "n",
        "turns": [{"when": "always"}],
        "checks": [{"id": "c", "check": "…"}],
    }), encoding="utf-8")

    args = type("A", (), {
        "agent_backend": "claude", "judge_backend": "claude",
        "agent_model": "m", "judge_model": "m", "agent_effort": "",
        "judge_effort": "", "agent_timeout": 60, "judge_timeout": 60,
        "cache_dir": None, "docs_base": "https://example.invalid",
    })()
    res = run.run_one(run.SkillSet(name="s", description="d", skills=[]), scenario, args)
    assert not res.ok
    assert "invalid turns declaration" in res.error
