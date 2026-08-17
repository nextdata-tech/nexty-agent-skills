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
from types import SimpleNamespace

from nxd_eval.transcript import extract


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
