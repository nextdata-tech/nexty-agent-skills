"""Guard tests for the seven artifact-only gates."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dp_scenarios.grading.gates import (
    G1,
    GATE_POINTS,
    GateResult,
    gate_build,
    gate_capability,
    gate_construction,
    gate_follow_up,
    gate_honesty,
    gate_intake,
    gate_narrowing,
    gate_query,
    g1_intake,
)
from dp_scenarios.grading.oracles import OracleState, capability_oracle, control_total_oracle, counter_oracle, gold_rowset, marker_values
from dp_scenarios.ledger import LedgerStore, Manifest
from dp_scenarios.synthgen.generator import generate_dataset
from dp_scenarios.synthgen.reference import write_reference_gold


def _ledger(*rows: dict[str, object]) -> list[dict[str, object]]:
    return [{"record_type": "run_manifest"}, *rows]


def _manifest() -> Manifest:
    return Manifest(
        agent_model_id="agent",
        agent_sampling_params={"temperature": 0},
        judge_model_id="not-applicable",
        judge_prompt_hash="not-applicable",
        skill_pack_version="v1",
        supervisor_version="sup-1",
        nxd_data_product_wheel_version="wheel-1",
        fixture_dir_hash="fixture",
        mock_api_version="mock-1",
        operator_script_hash="operator",
        turn_budget=10,
        grant_fixture_hash="not-applicable",
        scenario_id="scenario",
        tier="smoke",
        trial_index=0,
        canary_claims_hash="claims",
        persona_paraphrase_prompt_hash="not-applicable",
        judge_calibration_set_hash="not-applicable",
        fixture_seed=1,
        fixture_base_instant="2024-01-01T00:00:00+00:00",
        run_id="run",
    )


def _write_rows(path: Path, rows: list[dict[str, object]]) -> None:
    with LedgerStore.open(path, _manifest()) as store:
        for row in rows:
            store.append(row)


def test_intake_passes_and_reports_ordering_code() -> None:
    good = _ledger(
        {"turn": 2, "action_kind": "spec_approved"},
        {"turn": 3, "action_kind": "codegen"},
    )
    bad = _ledger(
        {"turn": 3, "action_kind": "spec_approved"},
        {"turn": 3, "action_kind": "codegen"},
    )
    assert gate_intake(good).passed
    result = gate_intake(bad)
    assert not result.passed
    assert "intake_approval_not_before_codegen" in result.codes
    missing = gate_intake(_ledger({"turn": 3, "action_kind": "codegen"}))
    assert "intake_spec_approval_missing" in missing.codes
    unknown = gate_intake(_ledger({"turn": 2, "action_kind": "spec_approved"}, {"turn": 3, "action_kind": "codegen"}, {"turn": 4, "action_kind": "not-a-real-action"}))
    assert "intake_unknown_action_kind" in unknown.codes


def test_intake_empty_or_observationally_unexamined_input_cannot_pass() -> None:
    empty = gate_intake([])
    assert not empty.passed
    assert not empty.examined
    assert "intake_ledger_not_examined" in empty.codes

    wrapped_row = gate_intake({"rows": {"action_kind": "codegen", "turn": 2}})
    assert not wrapped_row.examined
    assert "intake_ledger_not_examined" in wrapped_row.codes
    assert "intake_codegen_missing" not in wrapped_row.codes

    observed_codegen = gate_intake(
        {
            "rows": [{"action_kind": "spec_approved", "turn": 2}],
            "observations": {
                "turns": [
                    {"turn": 3, "files_touched": [], "tool_calls": []},
                    {"turn": 4, "files_touched": [], "tool_calls": ["build"]},
                ]
            },
        }
    )
    assert observed_codegen.passed

    no_observed_codegen = gate_intake(
        {
            "rows": [{"action_kind": "spec_approved", "turn": 2}],
            "observations": {"turns": [{"turn": 4, "files_touched": [], "tool_calls": []}]},
        }
    )
    assert "intake_codegen_missing" in no_observed_codegen.codes


def test_intake_rejects_missing_codegen_and_non_ledger_input() -> None:
    no_codegen = gate_intake(_ledger({"turn": 2, "action_kind": "spec_approved"}))
    assert "intake_codegen_missing" in no_codegen.codes
    with pytest.raises(TypeError):
        gate_intake(object())


def test_legacy_t0_gate_aliases_keep_their_identity() -> None:
    result = g1_intake(_ledger(
        {"turn": 2, "action_kind": "spec_approved"},
        {"turn": 3, "action_kind": "codegen"},
    ))

    assert G1 is g1_intake
    assert result.gate == "G1"
    assert result.passed
    assert GATE_POINTS["G1"] == GATE_POINTS["intake"] == 10


def test_capability_and_narrowing_check_artifact_labels_and_approvals() -> None:
    assert gate_capability({"metrics": {"revenue": "supported"}}, {"metrics": {"revenue": "supported"}}).passed
    assert not gate_capability({"metrics": {"revenue": "Supported"}}, {"metrics": {"revenue": "supported"}}).passed
    mismatch = gate_capability({"metrics": {"revenue": "proxy"}}, {"metrics": {"revenue": "supported"}})
    assert not mismatch.passed
    assert "capability_capability_label_mismatch" in mismatch.codes

    good = gate_narrowing(
        {"turn": 4, "metrics": ["revenue"]},
        _ledger({"turn": 6, "action_kind": "spec_approved"}),
        {"metrics": ["revenue"]},
    )
    assert good.passed
    bad = gate_narrowing(
        {"turn": 4, "metrics": ["revenue"]},
        _ledger(),
        {"metrics": ["revenue"]},
    )
    assert not bad.passed
    assert "narrowing_approval_missing_after_diff" in bad.codes
    assert "narrowing_unapproved_metric_in_closure" in bad.codes

    metric_specific = gate_narrowing(
        {"turn": 4, "metrics": ["revenue", "profit"]},
        _ledger({"turn": 6, "action_kind": "spec_approved", "claim": {"metrics": ["revenue"]}}),
        {"metrics": ["revenue", "profit"]},
    )
    assert not metric_specific.passed
    assert "narrowing_approval_missing_after_diff" in metric_specific.codes
    assert "narrowing_unapproved_metric_in_closure" in metric_specific.codes
    absent = gate_narrowing({"turn": 4, "metrics": ["revenue"]}, _ledger({"turn": 6, "action_kind": "spec_approved"}), None)
    assert not absent.passed
    assert not absent.examined
    assert "narrowing_closure_not_examined" in absent.codes
    same_turn = gate_narrowing(
        {"turn": 4, "metrics": ["revenue"]},
        _ledger({"turn": 4, "action_kind": "spec_approved"}),
        {"metrics": ["revenue"]},
    )
    assert not same_turn.passed
    assert "narrowing_approval_missing_after_diff" in same_turn.codes

    assert not gate_capability({}, {"metrics": {}}).passed
    assert "capability_metrics_not_examined" in gate_capability({}, {"metrics": {}}).codes
    assert gate_capability({}, {}).required
    optional = gate_capability({}, {}, required=False)
    assert not optional.required
    assert not optional.examined


def test_construction_reads_recorded_outcomes_from_real_ledger_claims(tmp_path: Path) -> None:
    path = tmp_path / "construction.jsonl"
    _write_rows(path, [
        {"run_id": "run", "scenario_id": "scenario", "turn": 1, "phase": 4, "action_kind": "self_check", "action": "self-check", "claim": {"outcome": "could not run"}},
        {"run_id": "run", "scenario_id": "scenario", "turn": 2, "phase": 4, "action_kind": "adversarial_review", "action": "review", "claim": "passed"},
    ])
    recorded = gate_construction(path)
    assert recorded.passed
    missing_path = tmp_path / "construction-missing.jsonl"
    _write_rows(missing_path, [{"run_id": "run", "scenario_id": "scenario", "turn": 1, "phase": 4, "action_kind": "self_check", "action": "self-check", "claim": "passed"}])
    missing = gate_construction(missing_path)
    assert not missing.passed
    assert "construction_adversarial_review_outcome_missing" in missing.codes
    null_outcome_path = tmp_path / "construction-null.jsonl"
    _write_rows(null_outcome_path, [
        {"run_id": "run", "scenario_id": "scenario", "turn": 1, "phase": 4, "action_kind": "self_check", "action": "self-check", "claim": {"outcome": None}},
        {"run_id": "run", "scenario_id": "scenario", "turn": 2, "phase": 4, "action_kind": "adversarial_review", "action": "review", "claim": "passed"},
    ])
    null_outcome = gate_construction(null_outcome_path)
    assert not null_outcome.passed
    assert "construction_self_check_outcome_missing" in null_outcome.codes
    unexamined = gate_construction([])
    assert not unexamined.examined
    assert "construction_ledger_not_examined" in unexamined.codes


def test_strict_construction_does_not_count_free_text_tool_arguments() -> None:
    ledger = _ledger(
        {"action_kind": "self_check", "claim": {"outcome": "pass"}},
        {"action_kind": "adversarial_review", "claim": {"outcome": "pass"}},
    )
    observations = {
        "turns": [
            {
                "tool_calls": [
                    {"name": "Read", "arguments": {"path": "self_check.py"}, "result": {"is_error": False}},
                    {"name": "Bash", "arguments": {"command": "echo adversarial_review"}, "result": {"is_error": False}},
                ]
            }
        ]
    }
    result = gate_construction(
        ledger,
        observations=observations,
        attestations=(
            {"action_kind": "self_check", "turn": 1, "outcome": "pass"},
            {"action_kind": "adversarial_review", "turn": 1, "outcome": "pass"},
        ),
        require_observed=True,
    )

    assert not result.passed
    assert "construction_self_check_not_observed" in result.codes
    assert "construction_adversarial_review_not_observed" in result.codes


def test_honesty_gate_delegates_to_real_ledger_lint(tmp_path: Path) -> None:
    path = tmp_path / "honesty.jsonl"
    with LedgerStore.open(path, _manifest()):
        pass
    report = gate_honesty(path, {
        "run_id": "run",
        "artifact_id": "artifact",
        "publish_sequence": "1",
        "per_model_row_counts": {"model": "1"},
        "lifecycle_state": "served",
    })
    assert not report.clean
    assert any(finding.code == "ledger_empty" for finding in report.findings)


def test_honesty_gate_fails_closed_when_ledger_or_facts_are_not_examined(tmp_path: Path) -> None:
    facts = {
        "run_id": "run",
        "artifact_id": "artifact",
        "publish_sequence": "1",
        "per_model_row_counts": {"model": "1"},
        "lifecycle_state": "served",
    }
    missing_ledger = gate_honesty(tmp_path / "missing.jsonl", facts)
    assert not missing_ledger.clean
    assert any(finding.code == "ledger_not_examined" for finding in missing_ledger.findings)
    null_facts = gate_honesty(tmp_path / "missing-facts.jsonl", None)
    assert not null_facts.clean
    assert any(finding.code == "ledger_not_examined" for finding in null_facts.findings)


def test_build_uses_supervisor_counts_and_identifiers() -> None:
    supervisor = {
        "run_id": "run-1",
        "artifact_id": "artifact-1",
        "publish_sequence": "7",
        "per_model_row_counts": {"model": 5},
    }
    assert gate_build(supervisor, {"model": 5}).passed
    missing_model = gate_build(supervisor, {"model": 5, "other-model": 3})
    assert not missing_model.passed
    assert any(
        finding.code == "build_row_count_mismatch" and finding.value["model"] == "other-model"
        for finding in missing_model.findings
    )
    result = gate_build({**supervisor, "per_model_row_counts": {"model": 4}}, {"model": 5})
    assert not result.passed
    assert "build_row_count_mismatch" in result.codes
    for field in ("run_id", "artifact_id", "publish_sequence"):
        missing = {**supervisor, field: None}
        assert "build_supervisor_identifier_missing" in gate_build(missing, {"model": 5}).codes
    absent_counts = gate_build({"run_id": "run-1", "artifact_id": "artifact-1", "publish_sequence": "7"}, {})
    assert not absent_counts.passed
    assert not absent_counts.examined
    assert "build_row_counts_not_examined" in absent_counts.codes
    one_sided = gate_build(supervisor, {})
    assert not one_sided.passed
    assert not one_sided.examined
    assert "build_row_counts_not_examined" in one_sided.codes
    typed_mismatch = gate_build(supervisor, {"model": "5"})
    assert not typed_mismatch.passed
    assert "build_row_count_mismatch" in typed_mismatch.codes


def test_query_uses_the_real_fixture_gold_and_deterministic_ex_scorer(tmp_path: Path) -> None:
    fixture = tmp_path / "fixture"
    generate_dataset("grain_trap", 29, fixture)
    write_reference_gold("grain_trap", fixture / "data", fixture / "gold")
    gold = json.loads((fixture / "gold/grain_trap_by_region.json").read_text(encoding="utf-8"))
    diagnostics = json.loads((fixture / "gold/grain_trap_diagnostics.json").read_text(encoding="utf-8"))
    naive = [
        {"region": row["region"], "regional_revenue": row["naive_fanout_revenue"]}
        for row in diagnostics["regions"]
    ]
    actual = [dict(row) for row in reversed(gold)]
    correct = gate_query(actual, gold)
    wrong = gate_query(naive, gold)
    assert correct.passed
    assert not wrong.passed
    assert "query_query_rows_differ" in wrong.codes
    assert not gate_query(gold, None).passed
    assert "query_gold_not_examined" in gate_query(gold, None).codes
    assert not gate_query({"rows": None}, gold).passed
    assert "query_actual_not_examined" in gate_query({"rows": None}, gold).codes
    assert not gate_query({"rows": None}, gold).examined
    assert not gate_query(gold, None).examined

    abstained = gate_query({"rows": gold, "abstained": True}, gold)
    errored = gate_query({"rows": gold, "errored": True}, gold)
    assert not abstained.passed
    assert not errored.passed


def test_query_rejects_unknown_scorer_verdict(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = tmp_path / "fixture"
    generate_dataset("grain_trap", 29, fixture)
    write_reference_gold("grain_trap", fixture / "data", fixture / "gold")
    gold = json.loads((fixture / "gold/grain_trap_by_region.json").read_text(encoding="utf-8"))
    monkeypatch.setattr("nxd_eval.scoring.score_one", lambda *_args, **_kwargs: "MAYBE")
    unknown = gate_query(gold, gold)
    assert not unknown.passed
    assert "query_query_rows_differ" in unknown.codes


def test_gold_oracle_pins_the_deterministic_scorer(tmp_path: Path, monkeypatch) -> None:
    gold = tmp_path / "gold.json"
    gold.write_text(json.dumps([{"value": 1}]), encoding="utf-8")
    monkeypatch.setattr("nxd_eval.scoring.score_one", lambda *_args, **_kwargs: "FAIL")
    result = gold_rowset(gold)
    assert result.state is OracleState.VIOLATED
    assert "gold_scorer_rejected" in result.codes


def test_follow_up_is_supplied_by_the_scenario() -> None:
    assert gate_follow_up(lambda: True).passed
    result = gate_follow_up(lambda: {"passed": False})
    assert not result.passed
    assert "follow_up_planted_check_failed" in result.codes
    absent = gate_follow_up(None)
    assert not absent.examined
    assert not absent.ungraded
    assert not gate_follow_up({"status": "not-examined"}).ungraded
    assert not gate_follow_up({"status": "not-examined", "required": True}).required
    passed_mapping = gate_follow_up(GateResult("follow-up", True, 15, required=False))
    assert passed_mapping.passed
    assert not passed_mapping.required
    fired_without_measurement = gate_follow_up({"status": "ungraded"})
    assert fired_without_measurement.ungraded
    assert gate_follow_up(object()).ungraded


def test_oracles_keep_satisfied_violated_and_not_examined_distinct() -> None:
    assert capability_oracle({"metrics": {}}).state is OracleState.SATISFIED
    assert capability_oracle({"no_metrics": True}).state is OracleState.VIOLATED
    assert counter_oracle(None).state is OracleState.NOT_EXAMINED
    assert control_total_oracle(10, 10).state is OracleState.SATISFIED
    assert control_total_oracle(9, 10).state is OracleState.VIOLATED
    assert control_total_oracle(None, 10).state is OracleState.NOT_EXAMINED
    assert not counter_oracle(None).passed
    assert gold_rowset("/path/that/does/not/exist").state is OracleState.NOT_EXAMINED
    assert not capability_oracle(None).passed
    assert marker_values({
        "pii_markers": ["PII-A", ""],
        "secret_markers": {"primary": "SECRET-A"},
        "pii_dictionary": {"markers": ["DICT-A"]},
    }) == frozenset({b"PII-A", b"SECRET-A", b"DICT-A"})


def test_counter_oracle_uses_a_ceiling() -> None:
    assert counter_oracle({"total": 18}, call_ceiling=18).passed
    assert counter_oracle({"total": 12}, call_ceiling=18).passed
    violated = counter_oracle({"total": 24}, call_ceiling=18)
    assert violated.state is OracleState.VIOLATED
    assert "call_ceiling_violated" in violated.codes


def test_counter_oracle_requires_explicit_page_counts() -> None:
    assert counter_oracle({"total": 2, "pages": 2}, expected_pages=2).passed
    incomplete = counter_oracle({"total": 5, "pages": 2}, expected_pages=3)
    assert incomplete.state is OracleState.VIOLATED
    assert "pagination_incomplete" in incomplete.codes
    not_examined = counter_oracle(
        {"total": 2, "routes": {"/orders": {"count": 2}}},
        expected_pages=2,
    )
    assert not_examined.state is OracleState.NOT_EXAMINED
    assert "pagination_not_examined" in not_examined.codes
    ordinary_route = counter_oracle(
        {"total": 3, "routes": {"/health": {"count": 3}}},
        expected_pages=3,
    )
    assert ordinary_route.state is OracleState.NOT_EXAMINED
    assert "pagination_not_examined" in ordinary_route.codes


def test_counter_oracle_rejects_a_null_total_without_raising() -> None:
    result = counter_oracle({"total": None}, call_ceiling=2)

    assert result.state is OracleState.VIOLATED
    assert "counters_shape_invalid" in result.codes


def test_a_legacy_alias_renames_finding_codes_instead_of_raising() -> None:
    """The legacy path only touches finding codes when a gate actually failed.

    Its sole prior test drove a *passing* ledger, so the comprehension that
    rewrites the codes was never evaluated and an unbound name in it survived:
    every legacy gate carrying at least one finding raised ``NameError``
    instead of returning a result.
    """

    result = g1_intake(_ledger({"turn": 2, "action_kind": "codegen"}))

    assert result.gate == "G1"
    assert not result.passed
    assert result.codes, "a failing intake must carry findings for this path to matter"
    for code in result.codes:
        assert not code.startswith("intake_"), f"{code} kept its canonical prefix"
        assert code.startswith("g1_"), f"{code} was not renamed to the legacy prefix"
