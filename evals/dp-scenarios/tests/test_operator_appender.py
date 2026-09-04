"""Supervisor provenance and row-shape tests for the operator appender."""

import pytest

from dp_scenarios.ledger import LedgerStore, Manifest, SupervisorFacts, lint
from dp_scenarios.operator.appender import (
    AppenderError,
    StaticSupervisorRecordReader,
    TurnEvidence,
    append_supervisor_facts,
    append_turn_row,
    row_payload,
)


def facts() -> SupervisorFacts:
    return SupervisorFacts(
        run_id="run-1",
        artifact_id="artifact-1",
        publish_sequence="7",
        per_model_row_counts={"model-a": "42"},
        lifecycle_state="served",
    )


def turn(**overrides: object) -> TurnEvidence:
    values: dict[str, object] = {
        "run_id": "run-1",
        "scenario_id": "scenario-1",
        "turn": 1,
        "phase": 1,
        "action_kind": "intake",
        "detail": "operator reply selected",
        "matched_rule_id": "fallback.no-leading",
        "evidence_ref": "operator#turn-1",
    }
    values.update(overrides)
    return TurnEvidence(**values)  # type: ignore[arg-type]


def test_appender_carries_reply_rule_id_in_structured_payload() -> None:
    payload = row_payload(turn())

    assert payload["matched_rule_id"] == "fallback.no-leading"
    assert payload["action"] == "operator reply selected"


def test_appender_serializes_absent_rule_and_event_ids_as_null() -> None:
    payload = row_payload(turn(matched_rule_id=None, event_ids=()))

    assert payload["matched_rule_id"] is None
    assert payload["event_ids"] is None


def test_appender_accepts_a_boolean_repeat_suppression_claim() -> None:
    payload = row_payload(turn(claim={"operator_repeat_suppressed": True}))

    assert payload["claim"] == {"operator_repeat_suppressed": True}


def test_appender_rejects_a_non_boolean_repeat_suppression_claim() -> None:
    with pytest.raises(AppenderError, match="operator_repeat_suppressed must be a boolean"):
        row_payload(turn(claim={"operator_repeat_suppressed": "yes"}))


def test_write_path_keeps_rule_and_event_ids_out_of_free_prose() -> None:
    rows: list[object] = []
    payload = append_turn_row(
        rows,  # type: ignore[arg-type]
        turn(event_ids=("deadline",), detail="operator response selected"),
    )

    assert payload["matched_rule_id"] == "fallback.no-leading"
    assert payload["event_ids"] == ["deadline"]
    assert "fallback.no-leading" not in payload["action"]
    assert "deadline" not in payload["action"]


def test_lint_rejects_a_rule_id_outside_the_matcher_grammar(tmp_path) -> None:
    manifest = Manifest(
        agent_model_id="agent-v1",
        agent_sampling_params={"temperature": 0},
        judge_model_id="not-applicable",
        judge_prompt_hash="not-applicable",
        skill_pack_version="skills-1",
        supervisor_version="sup-1",
        nxd_data_product_wheel_version="wheel-1",
        fixture_dir_hash="fixtures-1",
        mock_api_version="mock-1",
        operator_script_hash="operator-1",
        turn_budget=20,
        grant_fixture_hash="not-applicable",
        scenario_id="scenario-1",
        tier="smoke",
        trial_index=1,
        canary_claims_hash="canary-1",
        persona_paraphrase_prompt_hash="not-applicable",
        judge_calibration_set_hash="not-applicable",
        fixture_seed=7,
        fixture_base_instant="2024-01-01T00:00:00+00:00",
        run_id="run-1",
    )
    path = tmp_path / "lint.jsonl"
    with LedgerStore.open(path, manifest) as store:
        rows = (
            turn(phase=1, matched_rule_id="free prose rule"),
            turn(turn=2, phase=2, action_kind="capability_probe", matched_rule_id="source.answer.orders"),
            turn(turn=3, phase=3, action_kind="narrowing", matched_rule_id=None),
            turn(turn=4, phase=4, action_kind="codegen", matched_rule_id=None),
            turn(turn=5, phase=5, action_kind="self_check", matched_rule_id=None, phase_status="not-applicable", phase_status_reason="scenario stopped before build"),
            turn(turn=6, phase=6, action_kind="serve", matched_rule_id=None),
            turn(turn=7, phase=7, action_kind="follow_up", matched_rule_id=None),
        )
        for row in rows:
            store.append(row_payload(row))

    report = lint(path, supervisor_facts=facts())

    assert any(finding.code == "invalid_matched_rule_id" for finding in report.findings)


def test_supervisor_fact_cannot_be_written_without_reader() -> None:
    rows: list[object] = []

    with pytest.raises(AppenderError, match="record reader"):
        append_turn_row(
            rows,  # type: ignore[arg-type]
            turn(action_kind="supervisor_fact", fact_key="per_model_row_counts.model-a"),
        )


def test_non_fact_supervisor_claim_requires_reader_provenance() -> None:
    with pytest.raises(AppenderError, match="record reader"):
        row_payload(turn(action_kind="build", phase=5, claim={"run_id": "run-1"}))


def test_supervisor_fact_requires_a_fact_key_even_with_reader() -> None:
    rows: list[object] = []

    with pytest.raises(AppenderError, match="explicit fact_key"):
        append_turn_row(
            rows,  # type: ignore[arg-type]
            turn(action_kind="supervisor_fact"),
            supervisor_reader=StaticSupervisorRecordReader(facts()),
        )


def test_unknown_action_kind_is_rejected_by_the_appender() -> None:
    with pytest.raises(AppenderError, match="unknown ledger action kind"):
        row_payload(turn(action_kind="not-a-real-action"))


def test_reader_returning_the_wrong_type_is_rejected() -> None:
    class WrongReader:
        def read_facts(self) -> object:
            return {"run_id": "run-1"}

    with pytest.raises(AppenderError, match="no SupervisorFacts"):
        append_turn_row(
            [],  # type: ignore[arg-type]
            turn(action_kind="supervisor_fact", fact_key="run_id"),
            supervisor_reader=WrongReader(),  # type: ignore[arg-type]
        )


def test_empty_per_model_row_counts_are_rejected_by_fact_appender() -> None:
    malformed = object.__new__(SupervisorFacts)
    object.__setattr__(malformed, "run_id", "run-1")
    object.__setattr__(malformed, "artifact_id", "artifact-1")
    object.__setattr__(malformed, "publish_sequence", "7")
    object.__setattr__(malformed, "per_model_row_counts", {})
    object.__setattr__(malformed, "lifecycle_state", "served")

    with pytest.raises(AppenderError, match="no per-model row counts"):
        append_supervisor_facts(
            [],  # type: ignore[arg-type]
            StaticSupervisorRecordReader(malformed),  # type: ignore[arg-type]
            run_id="run-1",
            scenario_id="scenario-1",
            turn=6,
            phase=5,
        )


def test_agent_authored_supervisor_count_is_rejected_even_with_reader() -> None:
    rows: list[object] = []
    reader = StaticSupervisorRecordReader(facts())

    with pytest.raises(AppenderError, match="must come from"):
        append_turn_row(
            rows,  # type: ignore[arg-type]
            turn(
                action_kind="supervisor_fact",
                fact_key="per_model_row_counts.model-a",
                claim="999999",
            ),
            supervisor_reader=reader,
        )


def test_supervisor_fact_cannot_launder_through_a_build_row() -> None:
    rows: list[object] = []

    with pytest.raises(AppenderError, match="record reader"):
        append_turn_row(
            rows,  # type: ignore[arg-type]
            turn(
                action_kind="build",
                phase=5,
                claim={"per_model_row_counts": {"model-a": "999999"}},
            ),
        )


def test_structured_supervisor_claim_is_byte_equal_before_append() -> None:
    rows: list[object] = []
    reader = StaticSupervisorRecordReader(facts())

    payload = append_turn_row(
        rows,  # type: ignore[arg-type]
        turn(
            action_kind="build",
            phase=5,
            claim={"per_model_row_counts": {"model-a": "42"}},
        ),
        supervisor_reader=reader,
    )

    assert payload["claim"] == {"per_model_row_counts": {"model-a": "42"}}


@pytest.mark.parametrize(
    "claim",
    [
        "the row count is 999999",
        {"row_counts": {"model-a": "999999"}},
    ],
)
def test_non_fact_claims_cannot_launder_supervisor_facts(claim: object) -> None:
    rows: list[object] = []

    with pytest.raises(AppenderError, match="structured claim shape|unknown key"):
        append_turn_row(rows, turn(action_kind="build", phase=5, claim=claim))


def test_non_fact_outcome_claim_is_string_typed() -> None:
    with pytest.raises(AppenderError, match="outcome must be a string"):
        row_payload(turn(action_kind="self_check", phase=4, claim={"outcome": 1}))


def test_operator_unmatched_claim_is_boolean_typed() -> None:
    with pytest.raises(AppenderError, match="operator_unmatched must be a boolean"):
        row_payload(turn(action_kind="intake", phase=1, claim={"operator_unmatched": "yes"}))

    payload = row_payload(turn(action_kind="intake", phase=1, claim={"operator_unmatched": True}))
    assert payload["claim"] == {"operator_unmatched": True}


def test_operator_answered_from_ground_truth_claim_is_boolean_typed() -> None:
    with pytest.raises(AppenderError, match="operator_answered_from_ground_truth must be a boolean"):
        row_payload(
            turn(action_kind="intake", phase=1, claim={"operator_answered_from_ground_truth": "yes"})
        )

    payload = row_payload(
        turn(action_kind="intake", phase=1, claim={"operator_answered_from_ground_truth": True})
    )
    assert payload["claim"] == {"operator_answered_from_ground_truth": True}


def test_driver_claims_have_a_closed_structured_shape() -> None:
    payload = row_payload(
        turn(
            claim={
                "operator_mode": "driver",
                "operator_beat_id": "scope-creep",
                "driver_leading_rejected": True,
                "driver_beat_substituted": True,
            }
        )
    )
    assert payload["claim"]["operator_mode"] == "driver"
    assert payload["claim"]["driver_beat_substituted"] is True


@pytest.mark.parametrize(
    "key",
    ["driver_leading_rejected", "driver_obstacle_rejected", "driver_repeat_rejected", "driver_beat_substituted"],
)
def test_driver_boolean_claims_reject_non_boolean_values(key: str) -> None:
    with pytest.raises(AppenderError, match=f"{key} must be a boolean"):
        row_payload(turn(claim={key: "yes"}))


def test_supervisor_rows_are_copied_from_reader_and_not_agent_text() -> None:
    rows: list[object] = []
    reader = StaticSupervisorRecordReader(facts())

    appended = append_supervisor_facts(
        rows,  # type: ignore[arg-type]
        reader,
        run_id="run-1",
        scenario_id="scenario-1",
        turn=6,
        phase=5,
    )

    assert len(appended) == 5
    row_by_key = {row["fact_key"]: row["claim"] for row in appended}
    assert row_by_key["run_id"] == "run-1"
    assert row_by_key["artifact_id"] == "artifact-1"
    assert row_by_key["publish_sequence"] == "7"
    assert row_by_key["per_model_row_counts.model-a"] == "42"
    assert row_by_key["lifecycle_state"] == "served"


def test_supervisor_model_rows_are_appended_in_sorted_order() -> None:
    rows: list[object] = []
    reader = StaticSupervisorRecordReader(
        SupervisorFacts(
            run_id="run-1",
            artifact_id="artifact-1",
            publish_sequence="7",
            per_model_row_counts={"model-z": "9", "model-a": "42"},
            lifecycle_state="served",
        )
    )

    appended = append_supervisor_facts(
        rows,
        reader,
        run_id="run-1",
        scenario_id="scenario-1",
        turn=6,
        phase=5,
    )

    assert [row["fact_key"] for row in appended if str(row["fact_key"]).startswith("per_model")] == [
        "per_model_row_counts.model-a",
        "per_model_row_counts.model-z",
    ]
