"""Every trace-reading checker must match the format the backends emit.

`_trace_from_stream` writes `[tool_use:Write] {json}` — never `Write(...)`. A
checker whose markers use the second form cannot match any real trace, so
`first_write_index` always returns None. That is not merely a dead ordering
gate: `check_coauthored_closure.main()` treats a None as "the agent stopped for
approval without writing" and short-circuits to ALL CHECKS PASSED before any
artifact check runs, so the whole deterministic gate silently cannot fail.

`coauthor-supplied-rubric` is NOT `ci_skip`, so that checker runs on the PR gate
whenever `nxd-generate-dp` or `nxd-pocket-loop` change. These tests pin the
marker contract for both checkers so the two can never drift apart again.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

EVALS_DIR = Path(__file__).resolve().parents[1]
CHECKERS = {
    "coauthor-supplied-rubric": "check_coauthored_closure.py",
    "coauthor-executable-policy-readback": "check_executable_policy.py",
}


def _load(scenario: str, filename: str):
    path = EVALS_DIR / "public" / scenario / "fixtures" / filename
    spec = importlib.util.spec_from_file_location(f"_chk_{scenario}", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(params=sorted(CHECKERS.items()), ids=lambda kv: kv[0])
def checker(request):
    return _load(*request.param)


# The exact shapes `ClaudeBackend._trace_from_stream` emits.
WRITE_LINE = '[tool_use:Write] {"file_path": "/ws/spec.py", "content": "x"}'
EDIT_LINE = '[tool_use:Edit] {"file_path": "/ws/models.py"}'


def _bash(command: str, description: str = "x") -> str:
    return (
        '[tool_use:Bash] {"command": "%s", "description": "%s"}'
        % (command, description)
    )


def test_the_emitted_write_marker_is_detected(checker):
    """The regression: `Write(` markers matched nothing a backend emits."""
    trace = ["[assistant] Here is the read-back.", WRITE_LINE]
    assert checker.first_write_index(trace) == 1


def test_the_emitted_edit_marker_is_detected(checker):
    assert checker.first_write_index([EDIT_LINE]) == 0


def test_a_mutating_shell_command_is_detected(checker):
    assert checker.first_write_index([_bash("mkdir -p transform")]) == 0


def test_a_redirect_to_a_path_is_detected(checker):
    assert checker.first_write_index([_bash("echo hi > out.txt")]) == 0


def test_a_pure_read_is_not_a_write(checker):
    assert checker.first_write_index([_bash("head -5 data/x.csv")]) is None


def test_a_numeric_comparison_is_not_a_redirect(checker):
    """`awk '{if ($5 > 3)}'` over the supplied CSV is inspection, not a write.

    A bare `>\\s` marker read the comparison as a redirect and failed the agent
    that inspected the data most carefully — inverting what the gate rewards.
    """
    cmd = "awk -F, '{if ($5 > 3) print}' data/applicants/applicants.csv"
    assert checker.first_write_index([_bash(cmd)]) is None


def test_description_prose_cannot_trip_the_gate(checker):
    """The description is prose ABOUT intent; only the command is graded."""
    line = _bash("head -5 data/x.csv", "Add up the criteria columns")
    assert checker.first_write_index([line]) is None


def test_package_install_is_not_materialization(checker):
    """`pip install` provisions the interpreter; it writes no closure file."""
    assert checker.first_write_index([_bash("pip install -q duckdb")]) is None
