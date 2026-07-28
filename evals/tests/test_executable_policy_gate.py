"""The executable-policy checker's ordering and card gates must actually bite.

The ancestor suite (``test_trace_ordering_gate.py``) pins a DIFFERENT checker —
``coauthor-supplied-rubric``'s — so none of it exercises the ordering, anchor or
round-trip logic added for the read-back scenario. These tests drive
``check_executable_policy.py`` directly.

Two things make a gate worth testing here rather than trusting:

1. It must match the trace format the backends really emit —
   ``[tool_use:Write] {...}`` and ``[user_turn 2 ...]`` (see
   ``eval_backends._trace_from_stream`` / ``turn_separator``). A marker set that
   never matches makes the gate unconditionally green.
2. It must be able to FAIL. A card check satisfied by the very thresholds it is
   supposed to be independent of measures nothing.

Only the trace-driven checks run here: the checker's later half imports the
agent's ``transform/main.py`` and needs duckdb + a landed closure, which is the
scenario's job, not a unit test's. These cases stop at the first artifact check
and assert on the ordering/card lines the checker prints before that point.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

EVALS_DIR = Path(__file__).resolve().parents[1]
SCENARIO = EVALS_DIR / "public" / "coauthor-executable-policy-readback"
CHECKER = SCENARIO / "fixtures" / "check_executable_policy.py"

# The real separator the driver writes. `turn_separator` appends a stop-state
# mark inside the bracket, so the literal "[user_turn 2]" no longer appears —
# these tests pin the emitted form to catch a checker that only matches the old
# one.
TURN_2 = "[user_turn 2 unprompted] Right, I'm back. ADVANCE starts at 4.25."
TURN_2_AWAITED = "[user_turn 2 after-await] Right, I'm back. ADVANCE at 4.25."

# A card that quotes cut-offs AND defines intermediate levels — the good case.
GOOD_CARD = """\
[assistant] Before I create anything, here is the policy I propose.
Intermediate anchors for C4 experience: 4 = 7-9 years, 3 = 4-6 years,
2 = 2-3 years. Same shape on C1-C3.
Verdict bands: ADVANCE at >= 4.0, HOLD >= 2.5, REJECT below.
Does that look right before I build?
"""

# Quotes the thresholds, defines NO anchor. The regression: the anchor check
# used to match the decimal digits of these very thresholds.
THRESHOLD_ONLY_CARD = """\
[assistant] Here is my proposed rule card.
Verdict mapping: ADVANCE at >= 4.0, HOLD >= 2.5, otherwise REJECT.
I will pick sensible meanings for the middle levels as I go.
"""

WRITE_LINE = '[tool_use:Write] {"file_path": "spec.py", "content": "..."}'


def _run(root: Path, trace: str) -> subprocess.CompletedProcess:
    tf = root / "_trace.txt"
    tf.write_text(trace, encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(root), "--trace", str(tf)],
        capture_output=True, text=True,
    )


def test_write_before_turn_2_fails_ordering(tmp_path):
    """Materializing before the user replied is the defect under test."""
    proc = _run(tmp_path, f"{WRITE_LINE}\n{GOOD_CARD}{TURN_2}\n")
    assert "FAIL card-before-materialization" in proc.stdout, proc.stdout


def test_write_after_turn_2_passes_ordering(tmp_path):
    """Card, stop, then build on the go-ahead is the ideal run."""
    proc = _run(tmp_path, f"{GOOD_CARD}{TURN_2}\n{WRITE_LINE}\n")
    assert "PASS card-before-materialization" in proc.stdout, proc.stdout


def test_missing_turn_2_is_flagged_as_harness_failure(tmp_path):
    """No separator means the scripted turn never landed — not an agent fault."""
    proc = _run(tmp_path, f"{GOOD_CARD}{WRITE_LINE}\n")
    assert "FAIL turn-2-was-sent" in proc.stdout, proc.stdout


def test_no_materialization_anywhere_fails(tmp_path):
    """Turn 2 said build; a run that never wrote ignored the go-ahead."""
    proc = _run(tmp_path, f"{GOOD_CARD}{TURN_2}\n[assistant] Done thinking.\n")
    assert "FAIL materialized-after-go-ahead" in proc.stdout, proc.stdout


def test_card_without_numerals_fails(tmp_path):
    """'I'll choose sensible thresholds' is not a correctable proposal."""
    trace = (
        "[assistant] I'll define anchors and choose sensible verdict cut-offs "
        "once I see the spread.\n"
        f"{TURN_2}\n{WRITE_LINE}\n"
    )
    proc = _run(tmp_path, trace)
    assert "FAIL card-quotes-a-decisive-threshold" in proc.stdout, proc.stdout


def test_threshold_only_card_fails_the_anchor_check(tmp_path):
    """The regression: thresholds must not satisfy the ANCHOR requirement.

    'ADVANCE at >= 4.0' / 'HOLD >= 2.5' previously yielded levels {4, 2} out of
    their own decimal digits, so this card — which defines no intermediate level
    at all — cleared the bar and the check could never fail once the threshold
    check passed.
    """
    proc = _run(tmp_path, f"{THRESHOLD_ONLY_CARD}{TURN_2}\n{WRITE_LINE}\n")
    assert "PASS card-quotes-a-decisive-threshold" in proc.stdout, proc.stdout
    assert "FAIL card-quotes-intermediate-anchors" in proc.stdout, proc.stdout


def test_criterion_labels_are_not_anchors(tmp_path):
    """'C2:' and 'C4 —' name criteria; a letter-prefixed digit is not a level."""
    trace = (
        "[assistant] Scoring criteria: C2: portfolio quality. C4 — experience.\n"
        "Verdict bands: ADVANCE at >= 4.0, HOLD >= 2.5.\n"
        f"{TURN_2}\n{WRITE_LINE}\n"
    )
    proc = _run(tmp_path, trace)
    assert "FAIL card-quotes-intermediate-anchors" in proc.stdout, proc.stdout


def test_read_only_interpreter_inspection_is_not_a_write(tmp_path):
    """A diligent agent inspecting the CSV must not fail the ordering gate.

    The prompt allows reading the source. Treating `uv run`/`python -c` as a
    mutation outright failed the agent that looked before it proposed.
    """
    trace = (
        '[tool_use:Bash] {"command": "uv run python -c \\"import csv; '
        'print(len(list(csv.DictReader(open(\'a.csv\')))))\\""}\n'
        f"{GOOD_CARD}{TURN_2}\n{WRITE_LINE}\n"
    )
    proc = _run(tmp_path, trace)
    assert "PASS card-before-materialization" in proc.stdout, proc.stdout


def test_interpreter_that_actually_writes_is_a_write(tmp_path):
    """Dropping interpreter names must not open a hole: a writing body counts."""
    trace = (
        '[tool_use:Bash] {"command": "uv run python -c \\"import shutil; '
        'shutil.copy(\'a.csv\', \'ws/data/a.csv\')\\""}\n'
        f"{GOOD_CARD}{TURN_2}\n"
    )
    proc = _run(tmp_path, trace)
    assert "FAIL card-before-materialization" in proc.stdout, proc.stdout


def test_turn_separator_position_decides_ordering(tmp_path):
    """The gate is positional: the same two lines, order swapped, flips it.

    Guards the separator format itself. If `turn_separator` changed and the
    checker's `TURN_2_SEPARATOR` did not, `turn_2_index` would return None and
    every ordering verdict would collapse to the same answer.
    """
    before = _run(tmp_path, f"{GOOD_CARD}{TURN_2}\n{WRITE_LINE}\n")
    after = _run(tmp_path, f"{GOOD_CARD}{WRITE_LINE}\n{TURN_2}\n")
    assert "PASS card-before-materialization" in before.stdout, before.stdout
    assert "FAIL card-before-materialization" in after.stdout, after.stdout


def test_awaited_separator_form_is_recognised(tmp_path):
    """Both stop-state marks must parse as the same turn-2 boundary."""
    proc = _run(tmp_path, f"{GOOD_CARD}{TURN_2_AWAITED}\n{WRITE_LINE}\n")
    assert "PASS turn-2-was-sent" in proc.stdout, proc.stdout
    assert "PASS card-before-materialization" in proc.stdout, proc.stdout


def test_checker_matches_the_separator_the_driver_actually_renders(tmp_path):
    """Pin the checker against `turn_separator`'s REAL output, not a literal.

    Every other case here hand-writes the separator, so the checker and these
    tests could drift away from the driver together and still agree with each
    other. This one calls `turn_separator` and feeds the result through, which
    is the only assertion that fails if the rendered format changes.

    It is not hypothetical: the stop-state mark is appended INSIDE the bracket,
    so the older literal `[user_turn 2]` stopped appearing in traces entirely.
    A checker still pinning that string would find no boundary, and `t2 is
    None` makes `card-before-materialization` fail for every run — an agent
    that did everything right included.
    """
    sys.path.insert(0, str(EVALS_DIR))
    import eval_backends as eb

    for after_await in (False, True):
        sep = eb.turn_separator(2, "ADVANCE starts at 4.25.", after_await=after_await)
        proc = _run(tmp_path, f"{GOOD_CARD}{sep}\n{WRITE_LINE}\n")
        assert "PASS turn-2-was-sent" in proc.stdout, (sep, proc.stdout)
        assert "PASS card-before-materialization" in proc.stdout, (sep, proc.stdout)
