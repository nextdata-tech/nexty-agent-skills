"""Regression: gold selection must thread from Suite.gold into Sample metadata.

Before the fix, ``_sample_metadata`` never wrote ``gold_selection`` /
``measures`` / ``group_by`` keys, so ``scorers._gold_selection`` always read an
empty selection and ``slot_match`` scored the INVERSE of correct behaviour — an
agent that queried nothing about a non-empty gold selection scored a perfect
1.0, and a correct query against a non-empty gold selection scored a miss.
"""

from __future__ import annotations

import json

from inspect_ai.model import ChatMessageAssistant, ChatMessageTool, ModelName
from inspect_ai.scorer import CORRECT, Target
from inspect_ai.solver import TaskState
from inspect_ai.tool import ToolCall

from nxd_eval.case import ABSTAIN, ANSWER, Case, Suite
from nxd_eval.gold import gold
from nxd_eval.scorers import _slot_match_score
from nxd_eval.task import case_to_sample

QUERY = "run_semantic_query"


def _suite(**gold_kw) -> Suite:
    case = Case(id="a02", question="q", expect=ANSWER, gold_id="a02-gold")
    records = gold({"a02-gold": gold.query("a02-gold", **gold_kw)})
    return Suite(name="s", cases=[case], target="http://x", gold=records)


def test_sample_metadata_carries_gold_selection_from_gold_record():
    suite = _suite(measures=["PUMS"], group_by=["product_name"])
    sample = case_to_sample(suite.cases[0], suite)
    assert sample.metadata["gold_selection"] == {
        "measures": ["PUMS"],
        "group_by": ["product_name"],
        "filters": [],
    }


def _state_with_query(measures, dimensions, metadata) -> TaskState:
    tc = ToolCall(
        id="c1", function=QUERY, arguments={"measures": measures, "dimensions": dimensions}
    )
    messages = [
        ChatMessageAssistant(content="", tool_calls=[tc]),
        ChatMessageTool(
            content=json.dumps({"columns": measures, "rows": [], "error": ""}),
            function=QUERY,
            tool_call_id="c1",
        ),
    ]
    return TaskState(
        model=ModelName("mockllm/model"),
        sample_id="a02",
        epoch=0,
        input="q",
        messages=messages,
        metadata=metadata,
    )


def _no_query_state(metadata) -> TaskState:
    return TaskState(
        model=ModelName("mockllm/model"),
        sample_id="a02",
        epoch=0,
        input="q",
        messages=[],
        metadata=metadata,
    )


def test_exact_slot_match_against_threaded_gold_scores_perfect():
    suite = _suite(measures=["PUMS"], group_by=["product_name"])
    sample = case_to_sample(suite.cases[0], suite)
    state = _state_with_query(["PUMS"], ["product_name"], sample.metadata)
    score = _slot_match_score(state, Target(sample.target), threshold=0.999)
    assert score.value == CORRECT
    assert score.metadata["per_slot"]["metric"] == 1.0
    assert score.metadata["per_slot"]["dimensions"] == 1.0


def test_missing_dimension_against_threaded_gold_is_penalised():
    """The intended inverse of pre-fix behaviour: a real miss must score < 1.0."""
    suite = _suite(measures=["PUMS"], group_by=["product_name"])
    sample = case_to_sample(suite.cases[0], suite)
    state = _state_with_query(["PUMS"], [], sample.metadata)
    score = _slot_match_score(state, Target(sample.target), threshold=0.999)
    assert score.metadata["per_slot"]["dimensions"] == 0.0
    assert score.metadata["per_slot"]["grain"] == 0.0


def test_no_query_against_nonempty_gold_selection_does_not_score_perfect():
    """The single most valuable test: querying nothing must NOT score 1.0."""
    suite = _suite(measures=["PUMS"], group_by=["product_name"])
    sample = case_to_sample(suite.cases[0], suite)
    state = _no_query_state(sample.metadata)
    score = _slot_match_score(state, Target(sample.target), threshold=0.999)
    assert score.metadata["slot_f1"] < 1.0


def test_abstain_case_without_gold_id_has_no_gold_selection_key():
    case = Case(id="c1", question="q", expect=ABSTAIN)
    suite = Suite(name="s", cases=[case], target="http://x")
    sample = case_to_sample(case, suite)
    assert "gold_selection" not in sample.metadata


def test_case_metadata_override_wins_over_derived_gold_selection():
    case = Case(
        id="a02",
        question="q",
        expect=ANSWER,
        gold_id="a02-gold",
        metadata={"gold_selection": {"measures": ["OVERRIDE"], "group_by": [], "filters": []}},
    )
    records = gold({"a02-gold": gold.query("a02-gold", measures=["PUMS"], group_by=["x"])})
    suite = Suite(name="s", cases=[case], target="http://x", gold=records)
    sample = case_to_sample(case, suite)
    assert sample.metadata["gold_selection"]["measures"] == ["OVERRIDE"]
