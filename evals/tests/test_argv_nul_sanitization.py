"""A stray binary byte in a trace must not crash the claude backend (NEX-871).

`subprocess` builds argv with `execv`, which treats a NUL byte as the end of the
string and refuses the call outright: `ValueError: embedded null byte`. The
judge prompt is assembled from the agent trace, so a single non-printable byte
in a tool result rode straight into a `-p <prompt>` argv slot and raised before
the process even started. That ValueError escaped the backends' `except
subprocess.TimeoutExpired` guards and surfaced at run.py's catch-all as an
unattributable one-liner with the traceback and every gathered metric discarded.

These tests pin the fix at the layer that matters — the argv slots — and prove
the exact failure mode they defend against is real.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

EVALS_DIR = Path(__file__).resolve().parents[1]
if str(EVALS_DIR) not in sys.path:
    sys.path.insert(0, str(EVALS_DIR))

import eval_backends as eb  # noqa: E402


# --------------------------------------------------------------------------- #
# The failure mode is real: a NUL byte in argv aborts the call.
# --------------------------------------------------------------------------- #
def test_real_subprocess_rejects_a_nul_in_argv():
    """Document why the sanitizer exists: this is what used to reach the CLI."""
    with pytest.raises(ValueError):
        subprocess.run([sys.executable, "-c", "pass", "arg\x00with-nul"])


# --------------------------------------------------------------------------- #
# strip_argv_control_chars
# --------------------------------------------------------------------------- #
def test_strip_removes_nul_and_other_controls():
    assert eb.strip_argv_control_chars("a\x00b") == "ab"
    # A spread of C0 controls plus DEL, all dropped.
    assert eb.strip_argv_control_chars("x\x01\x07\x1b\x7fy") == "xy"


def test_strip_keeps_ordinary_whitespace_and_text():
    text = "line one\tcol\nline two\r\nunicode ✓ é 漢字"
    assert eb.strip_argv_control_chars(text) == text


def test_strip_is_a_noop_on_clean_text():
    assert eb.strip_argv_control_chars("the prompt") == "the prompt"


# --------------------------------------------------------------------------- #
# A fake subprocess.run that rejects a NUL exactly the way CPython does, so a
# scrubbed arg passes and an unscrubbed one would still blow up.
# --------------------------------------------------------------------------- #
class _Completed:
    returncode = 0
    stderr = ""

    def __init__(self, stdout: str):
        self.stdout = stdout


def _nul_strict_run_factory(seen: dict, stdout: str):
    def _fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        for part in cmd:
            if isinstance(part, str) and "\x00" in part:
                # Mirror CPython's own message so the test fails the same way a
                # regression would in production.
                raise ValueError("embedded null byte")
        return _Completed(stdout)

    return _fake_run


def test_single_turn_agent_scrubs_nul_before_argv(monkeypatch):
    import json

    seen: dict = {}
    result = json.dumps({
        "type": "result", "result": "ok", "is_error": False,
        "num_turns": 1, "usage": {},
    })
    monkeypatch.setattr(eb.subprocess, "run", _nul_strict_run_factory(seen, result))

    # A prompt carrying a stray binary byte must not raise.
    ok, _trace, metrics = eb.ClaudeBackend().run_agent(
        Path("/tmp"), "hello\x00world", "the-model", 42,
    )
    assert ok and metrics["final_answer"] == "ok"
    assert seen["cmd"][:2] == ["claude", "-p"]
    assert seen["cmd"][2] == "helloworld"
    assert not any("\x00" in p for p in seen["cmd"])


def test_judge_scrubs_nul_from_prompt_and_system(monkeypatch):
    import json

    seen: dict = {}
    wrapper = json.dumps({"result": json.dumps({"overall_pass": True})})
    monkeypatch.setattr(eb.subprocess, "run", _nul_strict_run_factory(seen, wrapper))

    # Both the trace-derived prompt and the system prompt carry a NUL.
    verdict = eb.ClaudeBackend().run_judge(
        "transcript with a \x00 byte", "system \x00 prompt", "judge-model", 30,
    )
    assert verdict.get("overall_pass") is True
    assert not any(isinstance(p, str) and "\x00" in p for p in seen["cmd"])
    # The scrubbed text is still present, just without the control byte.
    assert "transcript with a  byte" in seen["cmd"]
