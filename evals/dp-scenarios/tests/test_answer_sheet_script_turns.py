"""A script turn may declare its reply-substitution switch as scenario data.

``ScriptTurn`` has always understood a mapping declaration carrying
``substitute_reply``, but the answer-sheet validator accepted only plain
strings, so the switch was unreachable from a scenario package: the
capability the engine implements could not be expressed by the data that
drives it. These tests pin the mapping form end to end, and -- the part that
actually matters -- that a mapping turn's text is still scanned for planted
obstacle terms exactly as a string turn's is. A declaration form that
smuggled text past the obstacle scan would let a scenario leak the very
difficulty it plants.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pytest

from dp_scenarios.operator.answer_sheet import (
    AnswerSheetError,
    answer_sheet_from_mapping,
    script_turn_text,
)
from dp_scenarios.operator.engine import ScriptTurn
from dp_scenarios.operator.matcher import MatcherBank, MatcherError
from dp_scenarios.operator.persona import load_persona

ROOT = Path(__file__).parents[1]

OBSTACLE = "reconnect"


def _sheet(
    turns: list[object],
    *,
    obstacle_terms: list[str] | None = None,
    reapproval: object | None = None,
) -> object:
    value: dict[str, object] = {
        "version": 1,
        "scenario_id": "script-turns",
        "opening_message": "How is our pipeline moving?",
        "turns": turns,
        "source_answers": {"data": "Each record carries an amount."},
        "decision_answers": {"choice": {"terms": ["option"], "answer": "Yes."}},
        "status_answers": {"status": "The work is still in progress."},
        "opening_forbidden_terms": ["driver", "mechanism"],
        "open_decision_markers": ["[DECISION NEEDED]"],
        "obstacle_terms": obstacle_terms or [],
    }
    if reapproval is not None:
        value["reapproval"] = reapproval
    return answer_sheet_from_mapping(value)


def test_a_mapping_turn_declares_the_substitution_switch() -> None:
    sheet = _sheet(
        [
            "How is our pipeline moving?",
            {"text": "Tell me exactly how long each deal sat.", "substitute_reply": False},
        ]
    )
    turn = sheet.turns[1]  # type: ignore[attr-defined]
    assert isinstance(turn, Mapping)
    assert turn["substitute_reply"] is False
    assert script_turn_text(turn) == "Tell me exactly how long each deal sat."


def test_a_plain_string_turn_still_defaults_to_substitutable() -> None:
    sheet = _sheet(["How is our pipeline moving?", "Please continue."])
    assert sheet.turns[1] == "Please continue."  # type: ignore[attr-defined]
    assert script_turn_text(sheet.turns[1]) == "Please continue."  # type: ignore[attr-defined]


def test_a_mapping_turns_text_is_still_scanned_for_planted_obstacle_terms() -> None:
    """The scan must read the turn's text, not its declaration.

    This is the property that broke when turns stopped being plain strings:
    the obstacle scan splatted the turn list directly, so a mapping turn
    would either crash the scan or, worse, be skipped by it.
    """

    sheet = _sheet(
        [
            "How is our pipeline moving?",
            {"text": f"You will need to {OBSTACLE} the CRM first.", "substitute_reply": False},
        ],
        obstacle_terms=[OBSTACLE],
    )
    with pytest.raises(MatcherError):
        MatcherBank(load_persona(ROOT / "scenarios/_personas/smoke.yaml"), sheet)  # type: ignore[arg-type]


def test_a_clean_mapping_turn_builds_a_bank() -> None:
    sheet = _sheet(
        [
            "How is our pipeline moving?",
            {"text": "Please continue with the build.", "substitute_reply": False},
        ],
        obstacle_terms=[OBSTACLE],
    )
    assert MatcherBank(load_persona(ROOT / "scenarios/_personas/smoke.yaml"), sheet) is not None  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "turn",
    [
        {"text": "", "substitute_reply": False},
        {"substitute_reply": False},
        {"text": "Fine.", "substitute_reply": "no"},
        {"text": "Fine.", "unexpected": True},
        {"text": "Fine.", "message": "Fine."},
        {"text": "Fine.", "approval": "yes"},
        42,
    ],
)
def test_a_malformed_turn_declaration_is_rejected_at_load(turn: object) -> None:
    with pytest.raises(AnswerSheetError):
        _sheet(["How is our pipeline moving?", turn])


def test_a_turn_may_declare_itself_the_operator_approval() -> None:
    """The declaration the engine mints the spec_approved row from.

    A validator that accepted a declaration ``ScriptTurn`` later rejected, or
    that dropped one it silently did not understand, would fail deep in a run
    rather than at load -- the opposite of fail-closed.
    """

    sheet = _sheet(
        [
            "How is our pipeline moving?",
            {"text": "Approved -- go ahead.", "substitute_reply": False, "approval": True},
        ]
    )
    turn = sheet.turns[1]  # type: ignore[attr-defined]
    assert isinstance(turn, Mapping)
    assert turn["approval"] is True
    assert ScriptTurn.from_value(turn).approval is True


def test_a_turn_that_declares_no_approval_is_not_an_approval() -> None:
    for turn in ("Please continue.", {"text": "Please continue.", "substitute_reply": False}):
        assert ScriptTurn.from_value(turn).approval is False


def test_a_reapproval_answer_is_declared_with_a_positive_use_limit() -> None:
    sheet = _sheet(
        ["How is our pipeline moving?", "Please continue."],
        reapproval={"answer": "Approved after the review.", "max_uses": 2},
    )

    assert sheet.reapproval.answer == "Approved after the review."  # type: ignore[attr-defined]
    assert sheet.reapproval.max_uses == 2  # type: ignore[attr-defined]
    assert sheet.to_mapping()["reapproval"] == {  # type: ignore[attr-defined]
        "answer": "Approved after the review.",
        "max_uses": 2,
    }


@pytest.mark.parametrize(
    "reapproval",
    [
        {},
        {"answer": "Approved."},
        {"answer": "Approved.", "max_uses": 0},
        {"answer": "Approved.", "max_uses": True},
        {"answer": "Approved.", "max_uses": 1, "unexpected": "yes"},
    ],
)
def test_malformed_reapproval_declarations_are_rejected(reapproval: object) -> None:
    with pytest.raises(AnswerSheetError):
        _sheet(
            ["How is our pipeline moving?", "Please continue."],
            reapproval=reapproval,
        )


def test_the_opening_check_reads_a_mapping_turns_text() -> None:
    with pytest.raises(AnswerSheetError):
        _sheet([{"text": "A different opening.", "substitute_reply": False}])
