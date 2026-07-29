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


def test_bash_description_prose_cannot_trip_the_write_gate(tmp_path):
    """The mutation markers grade the COMMAND, never the sibling description.

    `"dd "` matched inside `"Add "`, so a pure `head -5 …` whose description
    read "Add up the criteria columns" was classified as materialization —
    failing the ordering gate for an agent that inspected carefully and then
    stopped, which is the exact behaviour the scenario rewards.
    """
    read_only = (
        '[tool_use:Bash] {"command": "head -5 data/applicants/applicants.csv", '
        '"description": "Add up the criteria columns"}'
    )
    proc = _run(tmp_path, f"{read_only}\n{GOOD_CARD}{TURN_2}\n{WRITE_LINE}\n")
    assert "PASS card-before-materialization" in proc.stdout, proc.stdout


def test_package_install_is_not_materialization(tmp_path):
    """`pip install` provisions the interpreter; it writes nothing into the closure.

    `install -` matched it, so an agent installing duckdb to READ the CSV was
    recorded as having written files before its card.
    """
    trace = (
        '[tool_use:Bash] {"command": "pip install -q duckdb pandas", '
        '"description": "deps to inspect the CSV"}\n'
        f"{GOOD_CARD}{TURN_2}\n{WRITE_LINE}\n"
    )
    proc = _run(tmp_path, trace)
    assert "PASS card-before-materialization" in proc.stdout, proc.stdout


def test_coreutils_install_is_still_materialization(tmp_path):
    """Excluding `pip install` must not open a hole for the real `install`."""
    trace = (
        '[tool_use:Bash] {"command": "install -m 644 a.csv ws/data/a.csv", '
        '"description": "place the source"}\n'
        f"{GOOD_CARD}{TURN_2}\n"
    )
    proc = _run(tmp_path, trace)
    assert "FAIL card-before-materialization" in proc.stdout, proc.stdout


def test_in_memory_duckdb_connect_is_a_read(tmp_path):
    """`duckdb.connect()` with no path materializes nothing."""
    trace = (
        '[tool_use:Bash] {"command": "python3 -c \\"import duckdb; '
        'print(duckdb.connect().execute(1))\\"", "description": "inspect"}\n'
        f"{GOOD_CARD}{TURN_2}\n{WRITE_LINE}\n"
    )
    proc = _run(tmp_path, trace)
    assert "PASS card-before-materialization" in proc.stdout, proc.stdout


def test_card_restating_the_supplied_rubric_is_not_a_threshold(tmp_path):
    """Prompt echo must not satisfy the executability gate.

    `C5 = 5` is a criterion score the USER supplied and `C1 = 35` a weight; both
    appear in near-verbatim restatements of the prompt, so a card whose only
    forward-looking statement was "I'll pick the cut-offs later" passed.
    """
    trace = (
        "[assistant] Here is the policy as I understand it.\n"
        "- No captured portfolio URL caps at NEEDS_MORE_INFO unless C5 = 5 "
        "(exceptional override).\n"
        "- Verdicts: ADVANCE, HOLD, REJECT, NEEDS_MORE_INFO. Weights: C1 = 35, "
        "C2 = 20, C3 = 20.\n"
        "I'll pick the ADVANCE/HOLD/REJECT cut-offs once I've scored the rows.\n"
        f"{TURN_2}\n{WRITE_LINE}\n"
    )
    proc = _run(tmp_path, trace)
    assert "FAIL card-quotes-a-decisive-threshold" in proc.stdout, proc.stdout


def test_vague_card_naming_verdicts_still_fails_the_threshold_check(tmp_path):
    """The false green: a card that PROMISES to pick cut-offs must not pass.

    `threshold` / `cut-off` / `band` used to sit in the operator alternation, so
    a card promising to choose one supplied its own operator and then needed
    only a nearby digit — and this scenario always has one ("5 criteria").
    `checks.json` calls this card a failure outright; the mechanical gate has to
    agree. The older `test_card_without_numerals_fails` misses it because its
    fixture names no verdict, so it fails on the verdict term first.
    """
    trace = (
        "[assistant] Verdicts: ADVANCE, HOLD, REJECT, NEEDS_MORE_INFO. "
        "I'll choose thresholds that suit the 10 rows, and pick a sensible "
        "ADVANCE cut-off once we've discussed the 5 criteria.\n"
        f"{TURN_2}\n{WRITE_LINE}\n"
    )
    proc = _run(tmp_path, trace)
    assert "FAIL card-quotes-a-decisive-threshold" in proc.stdout, proc.stdout


def test_word_operator_does_not_match_inside_a_longer_word(tmp_path):
    """`at` without a word boundary matched inside `that`, `data`, `state`."""
    trace = (
        "[assistant] HOLD is for candidates that need 2 more signals before "
        "a decision, and the data we have is thin.\n"
        f"{TURN_2}\n{WRITE_LINE}\n"
    )
    proc = _run(tmp_path, trace)
    assert "FAIL card-quotes-a-decisive-threshold" in proc.stdout, proc.stdout


def test_anchors_in_a_markdown_table_are_recognised(tmp_path):
    """A table is the natural rendering of 15 definitions; it scored zero.

    A false negative is expensive here — `check()` exits non-zero, so one
    unrecognised format sinks the whole scenario for a correct read-back.
    """
    trace = (
        "[assistant] Here is the policy I propose.\n"
        "| Level | Meaning |\n"
        "| 4 | one production service |\n"
        "| 3 | a substantial side project |\n"
        "| 2 | coursework only |\n"
        "Verdict bands: ADVANCE at >= 4.0, HOLD >= 2.5, REJECT below.\n"
        f"{TURN_2}\n{WRITE_LINE}\n"
    )
    proc = _run(tmp_path, trace)
    assert "PASS card-quotes-intermediate-anchors" in proc.stdout, proc.stdout


def test_anchors_with_bold_emphasis_are_recognised(tmp_path):
    """`**4**` put a `*` between the digit and its separator."""
    trace = (
        "[assistant] Proposed anchors:\n"
        "- **4** - one production service\n"
        "- **3** - a substantial side project\n"
        "- **2** - coursework only\n"
        "Verdict bands: ADVANCE at >= 4.0, HOLD >= 2.5, REJECT below.\n"
        f"{TURN_2}\n{WRITE_LINE}\n"
    )
    proc = _run(tmp_path, trace)
    assert "PASS card-quotes-intermediate-anchors" in proc.stdout, proc.stdout


def test_multiline_tool_result_numerals_are_not_agent_prose(tmp_path):
    """The regression: only a tool result's FIRST line carries its prefix.

    `_trace_from_stream` writes `[tool_result] <content>` where the content may
    run to many lines. Matching the marker per line left every continuation line
    graded as agent prose, so a card promising only to 'pick sensible
    thresholds' cleared both numeral gates on digits it had merely READ — here
    the rubric bands in `reference/derived-models.md`. That is the exact
    promise-not-a-proposal this scenario exists to fail.
    """
    trace = (
        "[assistant] Let me look at the source first.\n"
        '[tool_use:Read] {"file_path": "reference/derived-models.md"}\n'
        "[tool_result] Scoring guidance for rubrics:\n"
        "  2 - weak evidence\n"
        "  3 - partial evidence\n"
        "  4 - strong evidence\n"
        "ADVANCE at >= 4.0 is a common default cut-off\n"
        "[assistant] I will pick sensible thresholds and anchors, then build "
        "it.\n"
        f"{TURN_2}\n{WRITE_LINE}\n"
    )
    proc = _run(tmp_path, trace)
    assert "FAIL card-quotes-a-decisive-threshold" in proc.stdout, proc.stdout
    # The threshold gate is decisive and the checker stops there, so the anchor
    # verdict is never printed. What this pins is that neither gate reports PASS
    # off the tool result's digits.
    assert "PASS card-quotes-a-decisive-threshold" not in proc.stdout, proc.stdout
    assert "PASS card-quotes-intermediate-anchors" not in proc.stdout, proc.stdout


def test_assistant_continuation_after_tool_result_still_counts(tmp_path):
    """The fix must not swallow real prose: a block reopens on `[assistant] `.

    Guards the over-correction — dropping every unprefixed line after a tool
    result would stop grading the multi-line cards this gate is built to read.
    """
    trace = (
        '[tool_use:Read] {"file_path": "applicants.csv"}\n'
        "[tool_result] full_name,years_experience\n"
        "  Ada,9\n"
        "[assistant] Here is the policy I propose.\n"
        "Intermediate anchors: 4 = 7-9 years, 3 = 4-6 years, 2 = 2-3 years.\n"
        "Verdict bands: ADVANCE at >= 4.0, HOLD >= 2.5, REJECT below.\n"
        f"{TURN_2}\n{WRITE_LINE}\n"
    )
    proc = _run(tmp_path, trace)
    assert "PASS card-quotes-a-decisive-threshold" in proc.stdout, proc.stdout
    assert "PASS card-quotes-intermediate-anchors" in proc.stdout, proc.stdout


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
