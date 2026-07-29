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
import json
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
    # json.dumps, not interpolation: a command containing quotes must be
    # escaped exactly as the emitter escapes it, or the payload is invalid JSON
    # and the test exercises the truncation fallback instead of the real path.
    payload = json.dumps({"command": command, "description": description})
    return f"[tool_use:Bash] {payload}"


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


def test_a_column_comparison_is_not_a_redirect(checker):
    """`$5 > $4` compares two fields; the `$` fell through the path class.

    The literal-vs-literal case was already pinned, so this variant slipped
    through and both checkers hard-failed on it.
    """
    cmd = "awk -F, '{if ($5 > $4) print}' data/applicants/applicants.csv"
    assert checker.first_write_index([_bash(cmd)]) is None


def test_description_prose_cannot_trip_the_gate(checker):
    """The description is prose ABOUT intent; only the command is graded."""
    line = _bash("head -5 data/x.csv", "Add up the criteria columns")
    assert checker.first_write_index([line]) is None


def test_package_install_is_not_materialization(checker):
    """`pip install` provisions the interpreter; it writes no closure file."""
    assert checker.first_write_index([_bash("pip install -q duckdb")]) is None


# --- interpreted-write scoping (executable-policy checker only) -------------
#
# `INTERPRETED_WRITES` is meant for a `python -c` body that materializes
# something. Matched against EVERY Bash command it penalised pure reads, which
# is the same inversion the checker already rejects for interpreter names.

@pytest.fixture
def policy_checker():
    return _load(
        "coauthor-executable-policy-readback", "check_executable_policy.py"
    )


@pytest.mark.parametrize("cmd", [
    # Searches for the literal string; writes nothing.
    'grep -rn "to_csv" .',
    # Writes to stdout, not to a file.
    """python3 -c "import sys; sys.stdout.write(open('data/a.csv').read())" """,
    # `to_csv()` with no path RETURNS the csv as a string.
    """python3 -c "import pandas as pd; print(pd.read_csv('a').to_csv())" """,
    # A bare mode literal in a column name is not an `open(..., 'w')`.
    """python3 -c "print(df['w'])" """,
])
def test_reads_are_not_interpreted_writes(policy_checker, cmd):
    assert policy_checker.first_write_index([_bash(cmd)]) is None, cmd


@pytest.mark.parametrize("cmd", [
    """python3 -c "open('f.csv','w').write(1)" """,
    """python3 -c "import pandas as pd; pd.DataFrame().to_csv('out.csv')" """,
    """python3 -c "import shutil; shutil.copy('a','b')" """,
    """uv run python -c "from pathlib import Path; Path('x').write_text('y')" """,
])
def test_real_interpreted_writes_are_still_caught(policy_checker, cmd):
    """Scoping must not open a hole: a body that really writes still counts."""
    assert policy_checker.first_write_index([_bash(cmd)]) is not None, cmd
