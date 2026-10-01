"""Regression tests for ``transcript.extract`` against the real gateway contract.

The production mesh MCP gateway multiplexes every data product behind one
server, so the tool the agent actually calls is
``run_semantic_query__<10-char-suffix>`` — never the bare ``run_semantic_query``
a stub server exposes — and its result payload carries positional
JSON-encoded ``rows`` (paired with ``columns``) plus an ``"error": ""`` on
success rather than an absent/``null`` error. These tests pin the extractor
against that shape directly (bypassing the deterministic-scorer test helper,
which only builds bare-named calls) so a regression here is caught before it
masquerades as "every answer case scores INCORRECT" downstream.
"""

from __future__ import annotations

import json
import time
from decimal import Decimal
from types import SimpleNamespace

import pytest

from nxd_eval.transcript import QueryCall, Transcript, extract


def _msg(**kw):
    return SimpleNamespace(
        role=kw.pop("role", "tool"),
        text=kw.pop("text", None),
        content=kw.pop("content", None),
        function=kw.pop("function", None),
        tool_call_id=kw.pop("tool_call_id", None),
        tool_calls=kw.pop("tool_calls", []),
        **kw,
    )


def _call(id_, function, arguments):
    return SimpleNamespace(id=id_, function=function, arguments=arguments)


def _transcript(function: str, result: dict) -> object:
    return SimpleNamespace(
        messages=[
            _msg(
                role="assistant",
                tool_calls=[_call("c1", function, {"measures": ["PUMS"]})],
            ),
            _msg(
                role="tool",
                function=function,
                tool_call_id="c1",
                text=json.dumps(result),
            ),
        ]
    )


def _query_call(rows: list[dict], *, errored: bool = False) -> QueryCall:
    return QueryCall(arguments={}, result={"rows": rows}, errored=errored)


_SUCCESS = {"columns": ["PUMS"], "rows": ["[22583.0]"], "error": ""}


# --------------------------------------------------------------------------- #
# Defect 1 — suffixed tool name
# --------------------------------------------------------------------------- #


def test_bare_tool_name_extracted_unchanged():
    state = _transcript("run_semantic_query", _SUCCESS)
    tx = extract(state)
    assert tx.made_query
    assert len(tx.calls) == 1


def test_gateway_suffixed_tool_name_extracted():
    state = _transcript("run_semantic_query__grtmoib26y", _SUCCESS)
    tx = extract(state)
    assert tx.made_query
    assert len(tx.calls) == 1


def test_lookalike_tool_names_not_extracted():
    for bad in ("run_semantic_query_v2", "not_run_semantic_query"):
        state = _transcript(bad, _SUCCESS)
        tx = extract(state)
        assert not tx.made_query, bad


def test_two_distinct_suffixes_both_extracted_in_order():
    messages = [
        _msg(
            role="assistant",
            tool_calls=[
                _call("c1", "run_semantic_query__aaaaaaaaaa", {"measures": ["A"]}),
                _call("c2", "run_semantic_query__bbbbbbbbbb", {"measures": ["B"]}),
            ],
        ),
        _msg(
            role="tool",
            function="run_semantic_query__aaaaaaaaaa",
            tool_call_id="c1",
            text=json.dumps({"columns": ["A"], "rows": ["[1.0]"], "error": ""}),
        ),
        _msg(
            role="tool",
            function="run_semantic_query__bbbbbbbbbb",
            tool_call_id="c2",
            text=json.dumps({"columns": ["B"], "rows": ["[2.0]"], "error": ""}),
        ),
    ]
    tx = extract(SimpleNamespace(messages=messages))
    assert len(tx.calls) == 2
    assert tx.calls[0].measures == ["A"]
    assert tx.calls[1].measures == ["B"]


def test_non_query_tool_in_suffixed_transcript_ignored():
    messages = [
        _msg(
            role="assistant",
            tool_calls=[
                _call("c1", "list_models__grtmoib26y", {}),
                _call("c2", "run_semantic_query__grtmoib26y", {"measures": ["PUMS"]}),
            ],
        ),
        _msg(
            role="tool",
            function="list_models__grtmoib26y",
            tool_call_id="c1",
            text=json.dumps({"models": []}),
        ),
        _msg(
            role="tool",
            function="run_semantic_query__grtmoib26y",
            tool_call_id="c2",
            text=json.dumps(_SUCCESS),
        ),
    ]
    tx = extract(SimpleNamespace(messages=messages))
    assert len(tx.calls) == 1
    assert tx.calls[0].measures == ["PUMS"]


# --------------------------------------------------------------------------- #
# Defect 2 — positional row payload
# --------------------------------------------------------------------------- #


def test_positional_rows_zipped_into_dicts():
    state = _transcript("run_semantic_query__grtmoib26y", _SUCCESS)
    tx = extract(state)
    assert tx.calls[0].rows == [{"PUMS": 22583.0}]


def test_multi_column_multi_row_with_string_dim_and_null_measure():
    result = {
        "columns": ["INDICATION", "PUMS"],
        "rows": ['["MG", 16318.0]', '["All", null]'],
        "error": "",
    }
    state = _transcript("run_semantic_query__grtmoib26y", result)
    tx = extract(state)
    assert tx.calls[0].rows == [
        {"INDICATION": "MG", "PUMS": 16318.0},
        {"INDICATION": "All", "PUMS": None},
    ]


def test_rows_already_dicts_pass_through_unchanged():
    result = {"columns": ["PUMS"], "rows": [{"PUMS": 22583.0}], "error": ""}
    state = _transcript("run_semantic_query__grtmoib26y", result)
    tx = extract(state)
    assert tx.calls[0].rows == [{"PUMS": 22583.0}]


def test_arity_mismatch_returns_raw_payload_no_raise():
    result = {"columns": ["A", "B"], "rows": ["[1, 2, 3]"], "error": ""}
    state = _transcript("run_semantic_query__grtmoib26y", result)
    tx = extract(state)
    assert tx.calls[0].rows == ["[1, 2, 3]"]


def test_unparsable_row_string_returns_raw_payload_no_raise():
    result = {"columns": ["A"], "rows": ["not json"], "error": ""}
    state = _transcript("run_semantic_query__grtmoib26y", result)
    tx = extract(state)
    assert tx.calls[0].rows == ["not json"]


def test_empty_rows_with_columns_yields_empty_list():
    result = {"columns": ["PUMS"], "rows": [], "error": ""}
    state = _transcript("run_semantic_query__grtmoib26y", result)
    tx = extract(state)
    assert tx.calls[0].rows == []


def test_missing_columns_returns_raw_payload():
    result = {"rows": ["[22583.0]"], "error": ""}
    state = _transcript("run_semantic_query__grtmoib26y", result)
    tx = extract(state)
    assert tx.calls[0].rows == ["[22583.0]"]


# --------------------------------------------------------------------------- #
# Defect 3 — empty-string error on success
# --------------------------------------------------------------------------- #


def test_empty_string_error_is_not_errored_and_last_answered_call_returns_it():
    state = _transcript("run_semantic_query__grtmoib26y", _SUCCESS)
    tx = extract(state)
    assert tx.calls[0].errored is False
    assert tx.last_answered_call() is tx.calls[0]


def test_whitespace_only_error_is_not_errored():
    result = {**_SUCCESS, "error": "   "}
    state = _transcript("run_semantic_query__grtmoib26y", result)
    tx = extract(state)
    assert tx.calls[0].errored is False


def test_real_error_text_is_errored():
    result = {"columns": [], "rows": [], "error": "Query failed: 002003 ..."}
    state = _transcript("run_semantic_query__grtmoib26y", result)
    tx = extract(state)
    assert tx.calls[0].errored is True


def test_missing_error_key_is_not_errored():
    result = {"columns": ["PUMS"], "rows": ["[22583.0]"]}
    state = _transcript("run_semantic_query__grtmoib26y", result)
    tx = extract(state)
    assert tx.calls[0].errored is False


def test_null_error_is_not_errored():
    result = {**_SUCCESS, "error": None}
    state = _transcript("run_semantic_query__grtmoib26y", result)
    tx = extract(state)
    assert tx.calls[0].errored is False


def test_any_error_false_for_all_successful_calls_with_empty_error_string():
    messages = [
        _msg(
            role="assistant",
            tool_calls=[_call("c1", "run_semantic_query__grtmoib26y", {})],
        ),
        _msg(
            role="tool",
            function="run_semantic_query__grtmoib26y",
            tool_call_id="c1",
            text=json.dumps(_SUCCESS),
        ),
    ]
    tx = extract(SimpleNamespace(messages=messages))
    assert tx.any_error() is False


def test_mixed_transcript_last_answered_call_returns_the_success():
    messages = [
        _msg(
            role="assistant",
            tool_calls=[
                _call("c1", "run_semantic_query__grtmoib26y", {"measures": ["A"]}),
                _call("c2", "run_semantic_query__grtmoib26y", {"measures": ["PUMS"]}),
            ],
        ),
        _msg(
            role="tool",
            function="run_semantic_query__grtmoib26y",
            tool_call_id="c1",
            text=json.dumps(
                {"columns": [], "rows": [], "error": "Query failed: bad column"}
            ),
        ),
        _msg(
            role="tool",
            function="run_semantic_query__grtmoib26y",
            tool_call_id="c2",
            text=json.dumps(_SUCCESS),
        ),
    ]
    tx = extract(SimpleNamespace(messages=messages))
    last = tx.last_answered_call()
    assert last is not None
    assert last.measures == ["PUMS"]
    assert last.rows == [{"PUMS": 22583.0}]


# --------------------------------------------------------------------------- #
# Answer-anchored result selection
# --------------------------------------------------------------------------- #


def test_answer_call_uses_answer_number_coverage_before_call_cell_coverage():
    exploratory = _query_call([{"n": 10}, {"n": 20}, {"n": 99}])
    answer = _query_call([{"n": 30}])
    tx = Transcript(
        calls=[exploratory, answer],
        final_answer="The values were 10, 20, and 30.",
    )
    assert tx.answer_call() is exploratory
    assert tx.answer_call_selection() == (exploratory, "answer-anchored")


def test_answer_call_does_not_let_one_row_total_beat_correct_wide_result():
    correct = _query_call([{"n": n} for n in [120, 90, 80, 70, 60, *range(1, 46)]])
    exploratory_total = _query_call([{"n": 350}])
    tx = Transcript(
        calls=[correct, exploratory_total],
        final_answer="The top five were 120, 90, 80, 70, and 60; total 350.",
    )
    assert tx.answer_call() is correct


def test_answer_call_does_not_match_gold_small_count_instead_of_answer_numbers():
    gold = _query_call([{"n": 3}])
    wrong = _query_call([{"n": 120}, {"n": 90}, {"n": 40}, *[{"n": n} for n in range(4, 11)]])
    tx = Transcript(calls=[gold, wrong], final_answer="The 3 largest are 120, 90, 40.")
    assert tx.answer_call() is wrong


def test_answer_call_tie_uses_latest_call():
    first = _query_call([{"n": 5}])
    latest = _query_call([{"n": 5}])
    tx = Transcript(calls=[first, latest], final_answer="There were 5.")
    assert tx.answer_call() is latest
    assert tx.answer_call_selection_details() == (latest, "answer-anchored-tie", [0, 1])


def test_answer_call_matches_formatted_negative_decimal_and_percent():
    call = _query_call([{"amount": -1234.5, "rate": 0.125}])
    tx = Transcript(
        calls=[call],
        final_answer="The amount was -1,234.50 and the rate was 12.5%.",
    )
    assert tx.answer_call() is call


def test_answer_call_percentage_points_are_supported_too():
    points = _query_call([{"rate": 12.5}])
    tx = Transcript(calls=[points], final_answer="The rate was 12.5%.")
    assert tx.answer_call_selection() == (points, "answer-anchored")


def test_answer_call_ignores_trailing_confidence_digits():
    answer = _query_call([{"n": 10}])
    confidence_value = _query_call([{"n": 0.87}])
    tx = Transcript(
        calls=[answer, confidence_value],
        final_answer="There were 10 subjects.\nCONFIDENCE: 0.87",
    )
    assert tx.answer_call() is answer


@pytest.mark.parametrize(
    "confidence",
    [
        "**CONFIDENCE:** 0.87",
        "inline CONFIDENCE: 0.87 in prose",
        "CONFIDENCE: 0.87\n[^1]: calibrated against 2024 observations",
    ],
)
def test_answer_parser_strips_confidence_anywhere_and_markdown(confidence):
    answer = _query_call([{"n": 10}])
    confidence_value = _query_call([{"n": 0.87}])
    tx = Transcript(calls=[answer, confidence_value], final_answer=f"There were 10 subjects. {confidence}")
    assert tx.answer_call() is answer


def test_answer_parser_ignores_iso_dates_and_years_when_other_numbers_exist():
    amount = _query_call([{"n": 42}])
    date_parts = _query_call([{"n": 2025}, {"n": 3}, {"n": 1}])
    tx = Transcript(calls=[date_parts, amount], final_answer="On 2025-03-01, the total was 42.")
    assert tx.answer_call() is amount


def test_year_can_anchor_only_when_no_other_answer_numbers_exist():
    year = _query_call([{"n": 2025}])
    assert Transcript(calls=[year], final_answer="The report is for 2025.").answer_call() is year


def test_year_is_ignored_when_other_numbers_exist_even_if_they_are_small():
    year = _query_call([{"n": 2025}])
    assert Transcript(calls=[year], final_answer="In 2025 there were 3 groups.").answer_call_selection() == (
        year,
        "last-answered-fallback",
    )


def test_low_information_small_integer_cannot_anchor_with_other_numbers():
    small = _query_call([{"n": 3}])
    assert Transcript(calls=[small], final_answer="The 3 largest values were 120.").answer_call_selection() == (
        small,
        "last-answered-fallback",
    )


def test_low_precision_zero_only_matches_exact_zero_cell():
    near_zero = _query_call([{"n": 0.2}, {"n": -0.2}])
    tx = Transcript(calls=[near_zero], final_answer="There were 0 dropouts.")
    assert tx.answer_call_selection() == (near_zero, "last-answered-fallback")
    exact_zero = _query_call([{"n": 0}])
    assert Transcript(calls=[exact_zero], final_answer="There were 0 dropouts.").answer_call() is exact_zero


@pytest.mark.parametrize(
    ("cell", "answer"),
    [
        (9223372036854775807, "0.1234567891"),
        (Decimal("1e30"), "5"),
        (Decimal(10**26), "12.5%"),
    ],
)
def test_large_decimal_selection_never_raises(cell, answer):
    call = _query_call([{"n": cell}])
    assert Transcript(calls=[call], final_answer=f"Value {answer}.").answer_call() is not None


def test_numeric_strings_unicode_minus_and_accounting_cells_are_parsed():
    call = _query_call([{"a": "5.00", "b": "-3", "c": "1e3", "id": "subject-5"}])
    tx = Transcript(calls=[call], final_answer="Values were 5.00, -3, and 1,000.")
    assert tx.answer_call() is call
    negatives = _query_call([{"unicode": "−5", "accounting": "(1,234)"}])
    tx = Transcript(calls=[negatives], final_answer="Values were -5 and -1,234.")
    assert tx.answer_call() is negatives


def test_answer_selection_large_workload_is_near_linear():
    calls = [_query_call([{"n": n} for n in range(2000)]) for _ in range(30)]
    answer = "Values " + ", ".join(str(n) for n in range(1000, 1200))
    started = time.perf_counter()
    selected = Transcript(calls=calls, final_answer=answer).answer_call()
    elapsed = time.perf_counter() - started
    assert selected is calls[-1]
    assert elapsed < 1.5


def test_answer_call_ignores_numbered_markdown_list_index():
    answer = _query_call([{"n": 10}])
    list_index = _query_call([{"n": 1}])
    tx = Transcript(calls=[answer, list_index], final_answer="1. There were 10 subjects.")
    assert tx.answer_call() is answer


def test_answer_call_without_numeric_overlap_falls_back_to_last_answered():
    first = _query_call([{"n": 1}])
    latest = _query_call([{"n": 2}])
    tx = Transcript(calls=[first, latest], final_answer="The answer is unavailable.")
    assert tx.answer_call_selection() == (latest, "last-answered-fallback")

    no_overlap = Transcript(calls=[first, latest], final_answer="There were 500.")
    assert no_overlap.answer_call_selection() == (latest, "last-answered-fallback")


def test_answer_call_skips_errored_results():
    errored = _query_call([{"n": 5}], errored=True)
    latest = _query_call([{"n": 1}])
    tx = Transcript(calls=[errored, latest], final_answer="There were 5.")
    assert tx.answer_call_selection() == (latest, "last-answered-fallback")
