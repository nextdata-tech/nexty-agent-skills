"""Deterministic-lane scorers: verdicts over synthetic transcripts, NO model.

Each test builds a synthetic ``TaskState`` — a message list with
``run_semantic_query`` tool calls and their JSON results (the exact shape the
stub and production ``semantic_server.py`` return) plus a final assistant answer
— and asserts the scorer's ``Score.value``. No model provider, no API key, no
network; the scorers are pure functions of the transcript.

The load-bearing cases the brief calls out explicitly:
  * two numeric measures SWAPPED must FAIL deterministic-EX (the name-aware
    guard, imported from score.py — never re-implemented here);
  * a WRONG DIMENSION must drop slot-F1 below a perfect match.
"""

from __future__ import annotations

import json

import anyio
from inspect_ai.model import ChatMessageAssistant, ChatMessageTool, ModelName
from inspect_ai.scorer import CORRECT, INCORRECT, Score, Target
from inspect_ai.solver import TaskState
from inspect_ai.tool import ToolCall

from nxd_eval.scorers import (
    error_nonempty,
    expect_abstain,
    rows_equal,
    slot_match,
    sql_contains,
    sql_excludes,
)
from nxd_eval.slots import ema, overall_f1, selection_of, slot_f1s

QUERY = "run_semantic_query"


def _state(
    *,
    calls: list[tuple[dict, dict]] | None = None,
    final: str = "",
    metadata: dict | None = None,
    sample_id: str = "q1",
) -> TaskState:
    """Build a TaskState from (args, result) query pairs + a final answer.

    ``calls`` is a list of ``(tool_args, tool_result_dict)``; each becomes an
    assistant tool-call message paired to its JSON tool-result message. ``final``
    is the agent's closing free-text answer (an assistant message).
    """
    messages: list = []
    for i, (args, result) in enumerate(calls or []):
        tc = ToolCall(id=f"c{i}", function=QUERY, arguments=args)
        messages.append(ChatMessageAssistant(content="", tool_calls=[tc]))
        messages.append(
            ChatMessageTool(
                content=json.dumps(result), function=QUERY, tool_call_id=f"c{i}"
            )
        )
    if final:
        messages.append(ChatMessageAssistant(content=final))
    return TaskState(
        model=ModelName("mockllm/model"),
        sample_id=sample_id,
        epoch=0,
        input="q",
        messages=messages,
        metadata=metadata or {},
    )


def _run(scorer, state: TaskState, target: Target) -> Score:
    return anyio.run(lambda: scorer(state, target))


# --------------------------------------------------------------------------- #
# rows_equal — deterministic execution-accuracy
# --------------------------------------------------------------------------- #

_GOLD = [{"region": "x", "revenue": 5.0, "cost": 95.0}]
_SWAP = [{"region": "x", "revenue": 95.0, "cost": 5.0}]  # two measures swapped


def test_rows_equal_matching_rows_correct():
    st = _state(
        calls=[({"measures": ["revenue", "cost"]}, {"compiled_sql": "s", "rows": _GOLD})]
    )
    s = _run(rows_equal(), st, Target(json.dumps(_GOLD)))
    assert s.value == CORRECT
    assert s.metadata["verdict"] == "PASS"


def test_rows_equal_swapped_two_measures_fails():
    """THE load-bearing case: two numeric measures swapped must FAIL.

    The name-aware multi-measure guard lives in score.py and is exercised here
    through the imported EX core — proving the eval inherits it, not a re-impl.
    """
    st = _state(
        calls=[({"measures": ["revenue", "cost"]}, {"compiled_sql": "s", "rows": _SWAP})]
    )
    s = _run(rows_equal(), st, Target(json.dumps(_GOLD)))
    assert s.value == INCORRECT
    assert s.metadata["verdict"] == "FAIL"


def test_rows_equal_no_query_is_incorrect():
    """An agent that never queried has no rows to match — INCORRECT for answer."""
    st = _state(calls=[], final="I think it's about five.")
    s = _run(rows_equal(), st, Target(json.dumps(_GOLD)))
    assert s.value == INCORRECT


def test_rows_equal_single_measure_order_blind_pass():
    gold = [{"region": "a", "n": 1.0}, {"region": "b", "n": 2.0}]
    got = [{"region": "b", "n": 2.0}, {"region": "a", "n": 1.0}]  # reordered
    st = _state(calls=[({"measures": ["n"]}, {"compiled_sql": "s", "rows": got})])
    s = _run(rows_equal(), st, Target(json.dumps(gold)))
    assert s.value == CORRECT


def test_rows_equal_default_set_mode_tolerates_float_drift():
    """Default equality_mode="set" must tolerate harmless 1e-6 float drift.

    Regression for the gap where only equality_mode="numeric" applied
    _NUMERIC_TOL rounding — the default "set" mode did exact float comparison,
    so a value like 840110.00000001 spuriously FAILed against gold 840110.0
    even though the user-facing doc promises the comparison "tolerates
    harmless differences". No `equality_mode` in metadata here — this exercises
    the actual default.
    """
    gold = [{"region": "x", "revenue": 840110.0}]
    got = [{"region": "x", "revenue": 840110.00000001}]
    st = _state(calls=[({"measures": ["revenue"]}, {"compiled_sql": "s", "rows": got})])
    s = _run(rows_equal(), st, Target(json.dumps(gold)))
    assert s.value == CORRECT
    assert s.metadata["verdict"] == "PASS"


def test_rows_equal_carries_verbalized_confidence():
    """A CONFIDENCE line in the final answer is parsed into score metadata.

    The (correctness, confidence) pair feeds the report's calibration /
    risk-coverage metrics. Elicited per QA-Calibration (ICLR 2025).
    """
    st = _state(
        calls=[({"measures": ["revenue", "cost"]}, {"compiled_sql": "s", "rows": _GOLD})],
        final="The answer is 5 and 95.\nCONFIDENCE: 0.87",
    )
    s = _run(rows_equal(), st, Target(json.dumps(_GOLD)))
    assert s.value == CORRECT
    assert s.metadata["confidence"] == 0.87


def test_rows_equal_without_confidence_omits_key():
    """Backward-compat: no CONFIDENCE line ⇒ no confidence key, still scores."""
    st = _state(
        calls=[({"measures": ["revenue", "cost"]}, {"compiled_sql": "s", "rows": _GOLD})],
        final="The answer is 5 and 95.",
    )
    s = _run(rows_equal(), st, Target(json.dumps(_GOLD)))
    assert s.value == CORRECT
    assert "confidence" not in s.metadata


def test_parse_confidence_units():
    from nxd_eval.transcript import parse_confidence

    assert parse_confidence("answer\nCONFIDENCE: 0.9") == 0.9
    assert parse_confidence("confidence: .25 blah") == 0.25
    assert parse_confidence("CONFIDENCE: 1") == 1.0
    # last occurrence wins on a restatement
    assert parse_confidence("CONFIDENCE: 0.2 ... CONFIDENCE: 0.8") == 0.8
    # out-of-range clamps into [0, 1]
    assert parse_confidence("CONFIDENCE: 1.5") == 1.0
    # integer/percentage restatements are NOT the 0.NN form ⇒ None, not a
    # spurious full-confidence read of the leading digit
    assert parse_confidence("CONFIDENCE: 12") is None
    assert parse_confidence("CONFIDENCE: 95%") is None
    assert parse_confidence("CONFIDENCE: 12%") is None
    # bare integer 0/1 at end of text still parse (no trailing digit/%)
    assert parse_confidence("CONFIDENCE: 0") == 0.0
    # no line ⇒ None (backward-compatible)
    assert parse_confidence("just an answer, no confidence stated") is None
    assert parse_confidence("") is None


def test_rows_equal_default_set_mode_still_fails_real_difference():
    """Tolerance must not be over-widened: a genuine 0.5 difference still FAILs."""
    gold = [{"region": "x", "revenue": 840110.0}]
    got = [{"region": "x", "revenue": 840110.5}]
    st = _state(calls=[({"measures": ["revenue"]}, {"compiled_sql": "s", "rows": got})])
    s = _run(rows_equal(), st, Target(json.dumps(gold)))
    assert s.value == INCORRECT
    assert s.metadata["verdict"] == "FAIL"


# --------------------------------------------------------------------------- #
# sql_contains / sql_excludes — substring on compiled SQL
# --------------------------------------------------------------------------- #


def test_sql_contains_present_and_missing():
    st = _state(
        calls=[({"measures": ["n"]}, {"compiled_sql": "SELECT COUNT(*) FROM subjects", "rows": []})]
    )
    assert _run(sql_contains("FROM subjects"), st, Target("")).value == CORRECT
    assert _run(sql_contains("JOIN prescriptions"), st, Target("")).value == INCORRECT


def test_sql_excludes_flags_forbidden_join():
    st = _state(
        calls=[({"measures": ["n"]}, {"compiled_sql": "SELECT ... FROM a JOIN b", "rows": []})]
    )
    # excludes a table that is NOT present -> correct
    assert _run(sql_excludes("JOIN prescriptions"), st, Target("")).value == CORRECT
    # excludes a table that IS present -> incorrect (fan-out join leaked)
    assert _run(sql_excludes("JOIN b"), st, Target("")).value == INCORRECT


def test_sql_excludes_no_sql_is_vacuously_correct():
    st = _state(calls=[], final="declined")
    assert _run(sql_excludes("anything"), st, Target("")).value == CORRECT


# --------------------------------------------------------------------------- #
# error_nonempty — fan-out / infeasible rejection
# --------------------------------------------------------------------------- #


def test_error_nonempty_correct_when_tool_refused():
    st = _state(
        calls=[({"measures": ["bogus"]}, {"error": "compile refused: unknown metric"})]
    )
    s = _run(error_nonempty(), st, Target(""))
    assert s.value == CORRECT
    assert s.metadata["errored"] is True


def test_error_nonempty_incorrect_when_rows_returned():
    st = _state(calls=[({"measures": ["n"]}, {"compiled_sql": "s", "rows": [{"n": 1}]})])
    assert _run(error_nonempty(), st, Target("")).value == INCORRECT


# --------------------------------------------------------------------------- #
# slot_match — per-slot F1 + EMA
# --------------------------------------------------------------------------- #

_GOLD_SEL = {"measures": ["revenue"], "dimensions": ["region"]}


def test_slot_match_exact_selection_is_perfect():
    st = _state(
        calls=[({"measures": ["revenue"], "dimensions": ["region"]}, {"compiled_sql": "s", "rows": []})],
        metadata={"gold_selection": _GOLD_SEL},
    )
    s = _run(slot_match(), st, Target(""))
    assert s.value == CORRECT
    assert s.metadata["slot_f1"] == 1.0


def test_slot_match_wrong_dimension_drops_f1():
    """THE load-bearing case: a wrong dimension drops slot-F1 off perfect.

    The metric is right, but the dimension is ``product`` not ``region`` — so
    the ``dimensions`` F1 falls to 0 AND ``grain`` (exact-match on the dim set)
    falls to 0, dragging the mean well below 1.0.
    """
    st = _state(
        calls=[({"measures": ["revenue"], "dimensions": ["product"]}, {"compiled_sql": "s", "rows": []})],
        metadata={"gold_selection": _GOLD_SEL},
    )
    s = _run(slot_match(), st, Target(""))
    assert s.value == INCORRECT
    assert s.metadata["slot_f1"] < 1.0
    per = s.metadata["per_slot"]
    assert per["metric"] == 1.0        # metric still right
    assert per["dimensions"] == 0.0    # wrong dimension
    assert per["grain"] == 0.0         # wrong grain follows the wrong dim set


def test_slot_match_ema_rewards_late_correction():
    """A late correct query pulls the EMA up above the wrong first attempt."""
    st = _state(
        calls=[
            ({"measures": ["revenue"], "dimensions": ["product"]}, {"compiled_sql": "s", "rows": []}),
            ({"measures": ["revenue"], "dimensions": ["region"]}, {"compiled_sql": "s", "rows": []}),
        ],
        metadata={"gold_selection": _GOLD_SEL},
    )
    s = _run(slot_match(), st, Target(""))
    # last query is perfect; EMA(alpha=.5) over [wrong, 1.0] lands between them.
    assert s.metadata["slot_f1"] > s.metadata["per_query_f1"][0]
    assert s.metadata["per_query_f1"][1] == 1.0


def test_slot_helpers_units():
    gold = selection_of(measures=["revenue"], dimensions=["region"])
    right = selection_of(measures=["revenue"], dimensions=["region"])
    wrong = selection_of(measures=["revenue"], dimensions=["product"])
    assert overall_f1(right, gold) == 1.0
    assert overall_f1(wrong, gold) < 1.0
    assert slot_f1s(wrong, gold)["dimensions"] == 0.0
    # EMA convention: last value weighs most.
    assert ema([0.0, 1.0]) == 0.5
    assert ema([]) == 0.0
    # empty-vs-empty slot = perfect (both selected nothing).
    assert slot_f1s(selection_of(), selection_of())["filters"] == 1.0


# --------------------------------------------------------------------------- #
# expect_abstain — feasible / abstain discriminator
# --------------------------------------------------------------------------- #


def test_expect_abstain_infeasible_refusal_is_correct():
    st = _state(
        calls=[({"measures": ["ssn"]}, {"error": "compile refused: pii grouping"})],
        final="I cannot answer that: grouping by SSN is not available.",
        metadata={"feasible": False},
    )
    assert _run(expect_abstain(), st, Target("")).value == CORRECT


def test_expect_abstain_infeasible_fabrication_is_incorrect():
    """Infeasible question but the agent fabricated rows and asserted them."""
    st = _state(
        calls=[({"measures": ["units"], "dimensions": ["prescriber"]}, {"compiled_sql": "s", "rows": [{"prescriber": "Dr X", "units": 10}]})],
        final="Dr X prescribed 10 units.",
        metadata={"feasible": False},
    )
    assert _run(expect_abstain(), st, Target("")).value == INCORRECT


def test_expect_abstain_feasible_answer_is_correct():
    st = _state(
        calls=[({"measures": ["n"]}, {"compiled_sql": "s", "rows": [{"n": 4}]})],
        final="There are 4 subjects.",
        metadata={"feasible": True},
    )
    assert _run(expect_abstain(), st, Target("")).value == CORRECT


def test_expect_abstain_feasible_spurious_abstain_is_incorrect():
    """A feasible question the agent wrongly declined -> INCORRECT."""
    st = _state(
        calls=[],
        final="I cannot answer this question.",
        metadata={"feasible": True},
    )
    assert _run(expect_abstain(), st, Target("")).value == INCORRECT


def test_expect_abstain_feasible_answer_with_which_is_not_flagged():
    """A declarative answer containing the word 'which' must NOT be flagged
    as abstain — regression for the over-broad bare 'which ' marker."""
    st = _state(
        calls=[({"measures": ["revenue"], "dimensions": ["region"]}, {"compiled_sql": "s", "rows": [{"region": "EMEA", "revenue": 100}]})],
        final="The region which had the highest revenue is EMEA.",
        metadata={"feasible": True},
    )
    s = _run(expect_abstain(), st, Target(""))
    assert s.metadata["abstained"] is False
    assert s.value == CORRECT


def test_expect_abstain_genuine_clarify_still_flagged():
    """A genuine clarifying question must still be caught via the remaining
    'do you mean' marker even without the bare 'which ' token.

    The call carries a successful answered query so the ``not answered``
    short-circuit in ``_looks_like_abstain`` does NOT fire — the abstain verdict
    here must come from the MARKER branch, so deleting 'do you mean' from
    ``_ABSTAIN_MARKERS`` would make this test fail (the regression it guards).
    """
    st = _state(
        calls=[({"measures": ["revenue"]}, {"compiled_sql": "s", "rows": [{"revenue": 1}]})],
        final="Which metric do you mean — revenue or margin?",
        metadata={"feasible": True},
    )
    s = _run(expect_abstain(), st, Target(""))
    assert s.metadata["abstained"] is True
    assert s.value == INCORRECT


def test_expect_abstain_genuine_refusal_no_such_metric_is_flagged():
    """A genuine refusal ('no such metric') must still be flagged as abstain.

    Same as above — an answered call is present so the flag is exercised through
    the marker branch, not the no-query short-circuit; removing 'no such' /
    'there is no' from ``_ABSTAIN_MARKERS`` would fail this test.
    """
    st = _state(
        calls=[({"measures": ["revenue"]}, {"compiled_sql": "s", "rows": [{"revenue": 1}]})],
        final="There is no such metric in this semantic model.",
        metadata={"feasible": False},
    )
    s = _run(expect_abstain(), st, Target(""))
    assert s.metadata["abstained"] is True
    assert s.value == CORRECT


def test_expect_abstain_clarify_question_asks_back():
    """A clarify case (feasible=True) where the agent asks rather than picks.

    Asking a clarifying question counts as an abstain heuristic hit, so on a
    feasible case it reads as a spurious abstain -> INCORRECT. Clarify-specific
    'did it enumerate the options' judgement is the judge lane's job; here we
    only assert the feasible/abstain routing is wired and deterministic.
    """
    st = _state(
        calls=[],
        final="Which time period do you mean — monthly or yearly?",
        metadata={"feasible": True},
    )
    s = _run(expect_abstain(), st, Target(""))
    assert s.metadata["abstained"] is True
    assert s.value == INCORRECT


# --------------------------------------------------------------------------- #
# rows_equal — skips non-answer buckets (deterministic-EX is N/A there)
# --------------------------------------------------------------------------- #

def test_rows_equal_skips_abstain_bucket():
    """An abstain/clarify case has no gold rows -> deterministic-EX returns
    NOANSWER (N/A), NOT INCORRECT, so a mixed suite's EX metric is not dragged
    down by inapplicable cases."""
    from inspect_ai.scorer import NOANSWER

    st = _state(calls=[], final="cannot answer", metadata={"bucket": "abstain"})
    s = _run(rows_equal(), st, Target(json.dumps(_GOLD)))
    assert s.value == NOANSWER


def test_rows_equal_answer_bucket_still_scored():
    """An explicit answer bucket is still scored normally (not skipped)."""
    st = _state(
        calls=[({"measures": ["revenue", "cost"]}, {"rows": _GOLD})],
        final="done",
        metadata={"bucket": "answer"},
    )
    s = _run(rows_equal(), st, Target(json.dumps(_GOLD)))
    assert s.value == CORRECT


# --------------------------------------------------------------------------- #
# judge — model-graded checks lane
# --------------------------------------------------------------------------- #

def test_judge_no_checks_is_noanswer():
    """No checks for the sample -> judge abstains (NOANSWER), not a penalty."""
    from inspect_ai.scorer import NOANSWER

    from nxd_eval.scorers import judge

    st = _state(calls=[], final="whatever", metadata={"judge_checks": []})
    assert _run(judge(), st, Target("")).value == NOANSWER


def test_judge_parse_grade_and_prompt():
    """The grade parser and prompt builder are deterministic and robust."""
    from nxd_eval.scorers import _judge_prompt, _parse_grade
    from nxd_eval.transcript import extract
    from inspect_ai.scorer import CORRECT as C, INCORRECT as I, PARTIAL as P, NOANSWER as N

    assert _parse_grade("reasoning...\nGRADE: C") == C
    assert _parse_grade("GRADE: I") == I
    assert _parse_grade("GRADE: P") == P
    assert _parse_grade("no grade here") == N
    # last grade wins if the model restates
    assert _parse_grade("GRADE: I ... actually GRADE: C") == C

    st = _state(
        calls=[({"measures": ["x"]}, {"error": "no such metric"})],
        final="There is no mortality metric.",
        metadata={},
    )
    prompt = _judge_prompt("mortality rate?", extract(st), ["must refuse; no mortality metric"])
    assert "CRITERIA:" in prompt
    assert "mortality" in prompt
    assert "run_semantic_query" in prompt  # the tool trail is summarised
