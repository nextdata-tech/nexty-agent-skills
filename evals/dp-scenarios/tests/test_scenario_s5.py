"""Guard tests for exact optional-versus-required zero-row semantics."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from dp_scenarios.scenario import load_scenario
from dp_scenarios.operator.matcher import Category, MatcherBank


ROOT = Path(__file__).parents[1]
SCENARIO = load_scenario(ROOT / "scenarios/s5-smoke-zero-row")


def _hand_built_closure(generated: object, root: Path) -> Path:
    data_dir = root / "data"
    data_dir.mkdir(parents=True)
    generated_data = generated.data_dir  # type: ignore[attr-defined]
    for resource in ("optional_events", "primary"):
        shutil.copy2(generated_data / f"{resource}.csv", data_dir / f"{resource}.csv")
    (root / "requiredness.json").write_text(
        json.dumps({"requiredness": {"optional_events": False, "primary": True}}),
        encoding="utf-8",
    )
    return root


def test_file_backed_variant_preserves_empty_optional_and_exact_required_count(tmp_path: Path) -> None:
    generated = SCENARIO.generate_fixture(tmp_path / "zero")
    closure = _hand_built_closure(generated, tmp_path / "closure")
    result = SCENARIO.follow_up_check(closure)
    assert SCENARIO.fixture_variant == "file-backed"
    assert not (closure / "gold").exists()
    assert result["passed"]
    assert result["actual_counts"] == {"optional_events": 0, "primary": 5}
    assert result["expected_counts"] == {"optional_events": 0, "primary": 5}
    assert result["required"] == {"optional_events": False, "primary": True}


def test_manufactured_placeholder_row_fails_the_optional_check(tmp_path: Path) -> None:
    generated = SCENARIO.generate_fixture(tmp_path / "zero")
    closure = _hand_built_closure(generated, tmp_path / "closure")
    optional = closure / "data" / "optional_events.csv"
    optional.write_text(
        optional.read_text(encoding="utf-8") + "PLACEHOLDER,REC-29-001,2024-01-01T00:00:00+00:00\n",
        encoding="utf-8",
    )
    result = SCENARIO.follow_up_check(closure)
    assert not result["passed"]
    assert "resource_count_mismatch" in result["findings"]
    assert "optional_placeholder_row" in result["findings"]


def test_absent_optional_resource_is_distinct_and_fails_file_backed_materialization(tmp_path: Path) -> None:
    generated = SCENARIO.generate_fixture(tmp_path / "zero")
    closure = _hand_built_closure(generated, tmp_path / "closure")
    (closure / "data" / "optional_events.csv").unlink()

    result = SCENARIO.follow_up_check(closure)

    assert result["status"] == "examined"
    assert not result["passed"]
    assert "optional_resource_absent" in result["findings"]
    assert "optional_placeholder_row" not in result["findings"]


def test_required_output_is_still_strictly_checked(tmp_path: Path) -> None:
    generated = SCENARIO.generate_fixture(tmp_path / "zero")
    closure = _hand_built_closure(generated, tmp_path / "closure")
    primary = closure / "data" / "primary.csv"
    lines = primary.read_text(encoding="utf-8").splitlines(keepends=True)
    primary.write_text("".join(lines[:-1]), encoding="utf-8")
    result = SCENARIO.follow_up_check(closure)
    assert not result["passed"]
    assert "resource_count_mismatch" in result["findings"]
    assert "optional_placeholder_row" not in result["findings"]


def test_absent_required_resource_is_a_graded_failure(tmp_path: Path) -> None:
    generated = SCENARIO.generate_fixture(tmp_path / "zero")
    closure = _hand_built_closure(generated, tmp_path / "closure")
    (closure / "data" / "primary.csv").unlink()

    result = SCENARIO.follow_up_check(closure)

    assert result["status"] == "examined"
    assert not result["passed"]
    assert "required_resource_absent" in result["findings"]


@pytest.mark.parametrize("payload", [b"", b"\xff\xfe\x00\x80"])
def test_declared_but_malformed_resource_is_a_graded_failure(payload: bytes, tmp_path: Path) -> None:
    generated = SCENARIO.generate_fixture(tmp_path / "zero")
    closure = _hand_built_closure(generated, tmp_path / "closure")
    (closure / "data" / "optional_events.csv").write_bytes(payload)

    result = SCENARIO.follow_up_check(closure)

    assert result["status"] == "examined"
    assert not result["passed"]
    assert "resource_malformed:optional_events" in result["findings"]


def test_row_count_oracle_is_primary_over_closure_source_csvs(tmp_path: Path) -> None:
    generated = SCENARIO.generate_fixture(tmp_path / "zero")
    closure = _hand_built_closure(generated, tmp_path / "closure")
    optional = closure / "data" / "optional_events.csv"
    optional.write_text(
        optional.read_text(encoding="utf-8") + "PLACEHOLDER,REC-29-001,2024-01-01T00:00:00+00:00\n",
        encoding="utf-8",
    )

    result = SCENARIO.follow_up_check(
        {
            "closure": closure,
            "row_count_oracle": {"per_model_row_counts": generated.manifest["table_row_counts"]},
        }
    )

    assert result["passed"]
    assert result["count_source"] == "row_count_oracle"
    assert result["actual_counts"] == {"optional_events": 0, "primary": 5}


def test_generated_fixture_manifest_is_the_named_oracle_fallback(tmp_path: Path) -> None:
    generated = SCENARIO.generate_fixture(tmp_path / "zero")
    closure = _hand_built_closure(generated, tmp_path / "closure")
    (closure / "data" / "primary.csv").write_text("not,the,source\n", encoding="utf-8")

    result = SCENARIO.follow_up_check(closure, generated.out_dir)

    assert result["passed"]
    assert result["count_source"] == "fixture_manifest"


def test_requiredness_is_read_from_the_named_agent_document(tmp_path: Path) -> None:
    generated = SCENARIO.generate_fixture(tmp_path / "zero")
    closure = _hand_built_closure(generated, tmp_path / "closure")
    (closure / "requiredness.json").write_text(
        json.dumps({"requiredness": {"optional_events": True, "primary": True}}),
        encoding="utf-8",
    )

    result = SCENARIO.follow_up_check(closure)

    assert not result["passed"]
    assert result["status"] == "examined"
    assert "requiredness_artifact_mismatch" in result["findings"]


def test_unrecognized_or_unparseable_targets_are_not_examined(tmp_path: Path) -> None:
    missing = SCENARIO.follow_up_check(tmp_path / "does-not-exist")
    empty_mapping = SCENARIO.follow_up_check({})
    malformed_mapping = SCENARIO.follow_up_check({"counts": {"primary": "5"}})

    assert missing["status"] == "not-examined"
    assert empty_mapping["status"] == "not-examined"
    assert malformed_mapping["status"] == "not-examined"
    assert not SCENARIO.follow_up_gate(tmp_path / "does-not-exist").examined
    assert SCENARIO.follow_up_gate(tmp_path / "does-not-exist").ungraded


def test_resource_roles_are_machine_readable_and_g7_is_wired() -> None:
    binding = SCENARIO.gates["G7"]
    assert binding.kind == "optional_required_outputs"
    resources = binding.settings["resources"]
    assert resources["optional_events"]["required"] is False
    assert resources["primary"]["required"] is True


def test_turn_one_is_one_analyst_sentence_without_source_driver_or_mechanism_nouns() -> None:
    ask = SCENARIO.answer_sheet.turn_one
    forbidden = {
        "source", "driver", "mechanism", "data", "dataset", "table", "file",
        "resource", "row", "record", "required", "optional", "output", "count",
    }
    lowered = ask.casefold()

    assert sum(character in ".!?" for character in ask) == 1
    assert not any(term in lowered for term in forbidden)
    assert set(SCENARIO.answer_sheet.opening_forbidden_terms) >= forbidden


def test_optional_resource_is_reachable_from_plausible_follow_up_questions() -> None:
    bank = MatcherBank(SCENARIO.persona, SCENARIO.answer_sheet)

    primary = bank.reply_for("Which source did you use to work out how January went?")
    assert primary.category is Category.SOURCE_QUESTION
    assert primary.answer_key == "source"
    questions = (
        "Were there any problems during January?",
        "Which issues surfaced during January?",
        "Did any exceptions appear in January?",
        "Was there an anomaly in January?",
        "What should I worry about for January?",
        "Were you worried about anything in January?",
    )
    operator_turns = set(SCENARIO.answer_sheet.turns)
    assert not operator_turns.intersection(questions)
    for question in questions:
        optional = bank.reply_for(question)
        assert optional.category is Category.DECISION_REQUEST
        assert optional.decision_id is not None
        assert optional.decision_id.startswith("optional_output")
        assert "placeholder" in optional.reply.casefold()

    unrelated = bank.reply_for("What was the January outcome?")
    assert unrelated.decision_id is None
    assert "placeholder" not in unrelated.reply.casefold()


def test_s5_certifies_only_the_examinable_build_gate() -> None:
    assert SCENARIO.repeatability.gates == ("G5",)
    assert "counts" in SCENARIO.gold_paths


def test_phase_five_and_six_turns_drive_build_and_query() -> None:
    assert "build" in SCENARIO.answer_sheet.turns[4].casefold()
    assert "query" in SCENARIO.answer_sheet.turns[5].casefold()


def test_required_plant_is_event_backed_and_must_be_observed_before_g7() -> None:
    assert SCENARIO.required_plants == {"optional_zero_row"}
    assert SCENARIO.events.planted_card_ids() == SCENARIO.required_plants
    assert SCENARIO.events.cards[0].event_type.value == "raw_rows_request"

    fired = SCENARIO.check_fired_plants(
        {"fixture_manifest": {"table_row_counts": {"optional_events": 0, "primary": 5}}}
    )
    missing = SCENARIO.check_fired_plants(
        {"fixture_manifest": {"table_row_counts": {"optional_events": 1, "primary": 5}}}
    )

    assert fired.passed
    assert not missing.passed
    assert missing.ungraded
    assert missing.codes == ("required_plant_not_fired",)


def test_fired_plant_evidence_cannot_be_replaced_by_an_event_id() -> None:
    result = SCENARIO.check_fired_plants({"fired_plant_ids": ["optional_zero_row"]})
    assert not result.passed
    assert result.ungraded
    assert result.codes == ("plants_not_examined",)


def test_follow_up_gate_without_fired_plant_evidence_is_not_examined(tmp_path: Path) -> None:
    generated = SCENARIO.generate_fixture(tmp_path / "zero")
    closure = _hand_built_closure(generated, tmp_path / "closure")
    result = SCENARIO.follow_up_gate(closure)
    assert not result.passed
    assert result.ungraded
    assert result.codes == ("plants_not_examined",)
