"""Answer-sheet validation and hashing for driven scenarios."""

from __future__ import annotations

import hashlib
import json

import pytest

from dp_scenarios.operator.answer_sheet import AnswerSheetError, answer_sheet_from_mapping


def _raw() -> dict[str, object]:
    return {
        "version": 1,
        "scenario_id": "driver-terms",
        "opening_message": "Improve weekly visibility.",
        "turns": ["Improve weekly visibility."],
        "source_answers": {},
        "decision_answers": {},
        "status_answers": {},
        "opening_forbidden_terms": ["driver"],
        "open_decision_markers": ["[DECISION NEEDED]"],
        "obstacle_terms": [],
    }


def _mapping_hash(sheet: object) -> str:
    assert hasattr(sheet, "to_mapping")
    payload = json.dumps(sheet.to_mapping(), sort_keys=True, separators=(",", ":")).encode()  # type: ignore[attr-defined]
    return hashlib.sha256(payload).hexdigest()


def test_driver_forbidden_terms_empty_list_fails_closed() -> None:
    raw = _raw()
    raw["driver_forbidden_terms"] = []
    with pytest.raises(AnswerSheetError):
        answer_sheet_from_mapping(raw)


def test_driver_forbidden_terms_are_optional_but_emitted_for_hashing() -> None:
    sheet_without = answer_sheet_from_mapping(_raw())
    raw_with = _raw()
    raw_with["driver_forbidden_terms"] = ["stage"]
    sheet_with = answer_sheet_from_mapping(raw_with)

    assert sheet_without.driver_forbidden_terms == ()
    assert "driver_forbidden_terms" not in sheet_without.to_mapping()
    assert sheet_with.to_mapping()["driver_forbidden_terms"] == ["stage"]
    assert _mapping_hash(sheet_without) != _mapping_hash(sheet_with)
