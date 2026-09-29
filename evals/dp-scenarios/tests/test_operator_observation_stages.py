"""Staged operator decisions are graded at delivery, not selection."""

from __future__ import annotations

import json
from pathlib import Path

from dp_scenarios.operator.answer_sheet import answer_sheet_from_mapping
from dp_scenarios.operator.engine import OperatorEngine, OperatorScript
from dp_scenarios.operator.persona import load_persona
from dp_scenarios.operator.transport import InMemoryTransport, TurnResult
from dp_scenarios.runner.tier import _write_operator_observations


ROOT = Path(__file__).parents[1]


def test_three_stage_decision_observations_distinguish_selection_and_delivery(
    tmp_path: Path,
) -> None:
    opening = "Refresh the report."
    sheet = answer_sheet_from_mapping(
        {
            "version": 1,
            "scenario_id": "staged-observation-test",
            "opening_message": opening,
            "turns": [opening, "Please continue.", "Please continue.", "Please continue."],
            "source_answers": {},
            "decision_answers": {
                "stage_treatment": {
                    "terms": ["stage", "treatment"],
                    "stages": [
                        "I need to check with Finance.",
                        "Finance has not confirmed the treatment.",
                        "Publish provisional rows with a warning.",
                    ],
                }
            },
            "status_answers": {},
            "opening_forbidden_terms": ["warning"],
            "open_decision_markers": ["[DECISION NEEDED]"],
            "obstacle_terms": [],
        }
    )
    script = OperatorScript.from_components(
        load_persona(ROOT / "scenarios/_personas/smoke.yaml"),
        sheet,
        turns=sheet.turns,
        turn_budget=4,
        phase_by_turn={1: 1, 2: 2, 3: 3, 4: 4},
    )
    question = "What stage treatment should I use?"
    result = OperatorEngine(
        script,
        InMemoryTransport(
            [
                TurnResult(agent_message=question),
                TurnResult(agent_message=question),
                TurnResult(agent_message=question),
                TurnResult(agent_message="Understood."),
            ]
        ),
    ).run()

    _write_operator_observations(tmp_path, result)
    turns = json.loads((tmp_path / "operator-observations.json").read_text())["turns"]

    assert [turn["operator_selected_decision_stage"] for turn in turns] == [1, 2, 3, None]
    assert [turn["operator_delivered_decision_stage"] for turn in turns] == [None, 1, 2, 3]
    assert [turn["operator_selected_decision_final"] for turn in turns] == [False, False, True, None]
    assert [turn["operator_delivered_decision_final"] for turn in turns] == [None, False, False, True]
    assert turns[2]["operator_delivered_decision_final"] is False
    assert turns[3]["operator_delivered_decision_id"] == "stage_treatment"
    assert "Publish provisional rows" in turns[3]["operator_message"]

