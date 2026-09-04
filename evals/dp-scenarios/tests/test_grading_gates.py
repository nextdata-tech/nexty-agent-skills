"""Guard tests for the seven artifact-only gates."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dp_scenarios.grading.gates import (
    gate_capability_from_decisions,
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
    # Codegen strictly earlier than the approval is the violation. The
    # same turn is not: an operator approval is transmitted at the top of
    # a turn and the agent acts in the rest of it, so authoring right
    # after "approved, go ahead" shares the approval's turn number.
    bad = _ledger(
        {"turn": 3, "action_kind": "spec_approved"},
        {"turn": 2, "action_kind": "codegen"},
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
                    {
                        "turn": 4,
                        "files_touched": [{"path": "closure/spec.py", "content": "m"}],
                        "tool_calls": [],
                    },
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


def _live_shaped_run(*, approval_turn: int, closure_turn: int) -> dict[str, object]:
    """A ledger plus observations in the shape a live agent run produces.

    Turn 1 is the read-only orientation turn the live adapter's system prompt
    asks for; turn 2 writes the root-level blueprint that is submitted for
    approval.  Neither is codegen.
    """

    return {
        "rows": [
            {"turn": approval_turn, "action_kind": "spec_approved"},
            {"turn": closure_turn, "action_kind": "codegen"},
        ],
        "observations": {
            "turns": [
                {
                    "turn": 1,
                    "files_touched": [],
                    "tool_calls": [{"name": "Read", "arguments": {"file_path": "infra-profile.yaml"}}],
                },
                {
                    "turn": 2,
                    "files_touched": [{"path": "dp-blueprint.md", "content": "spec"}],
                    "tool_calls": [{"name": "Write", "arguments": {"file_path": "dp-blueprint.md"}}],
                },
                {
                    "turn": closure_turn,
                    "files_touched": [{"path": "closure/spec.py", "content": "code"}],
                    "tool_calls": [{"name": "Write", "arguments": {"file_path": "closure/spec.py"}}],
                },
            ]
        },
    }


def test_intake_passes_when_a_live_run_reads_and_drafts_a_spec_before_approval() -> None:
    """Pre-approval reads and blueprint writes must not count as codegen.

    This is the live-run shape: the agent orients with a read on turn 1 and
    writes the blueprint on turn 2, both strictly before the approval on
    turn 4.  Inferring codegen from either made the gate unpassable for any
    real run.
    """

    result = gate_intake(_live_shaped_run(approval_turn=4, closure_turn=5))
    assert result.passed, result.codes
    assert result.points == GATE_POINTS["intake"]


def test_intake_still_catches_closure_authoring_before_approval() -> None:
    """The ordering check must survive the narrowed inference.

    Authoring the closure on turn 3 with approval only on turn 4 is the real
    violation, and it is caught from observations alone -- the ledger here
    records no codegen row at all, so the finding can only come from the
    inference.
    """

    run = {
        "rows": [{"turn": 4, "action_kind": "spec_approved"}],
        "observations": {
            "turns": [
                {"turn": 3, "files_touched": [{"path": "closure/spec.py", "content": "code"}], "tool_calls": []},
            ]
        },
    }
    result = gate_intake(run)
    assert not result.passed
    assert "intake_approval_not_before_codegen" in result.codes
    assert result.points == 0


def test_intake_codegen_inference_ignores_non_authoring_observations() -> None:
    """Only a closure write is authoring evidence; nothing else substitutes."""

    def codes(turn: dict[str, object]) -> tuple[str, ...]:
        return gate_intake(
            {"rows": [{"turn": 2, "action_kind": "spec_approved"}], "observations": {"turns": [turn]}}
        ).codes

    # Reads, root-level spec writes, and malformed entries are not codegen.
    assert "intake_codegen_missing" in codes({"turn": 3, "tool_calls": [{"name": "Read"}]})
    assert "intake_codegen_missing" in codes({"turn": 3, "tool_calls": [{"name": "Write"}], "files_touched": []})
    assert "intake_codegen_missing" in codes({"turn": 3, "files_touched": [{"path": "dp-blueprint.md"}]})
    assert "intake_codegen_missing" in codes({"turn": 3, "files_touched": [{"path": "closure-notes.md"}]})
    assert "intake_codegen_missing" in codes({"turn": 3, "files_touched": ["not-a-mapping"]})
    assert "intake_codegen_missing" in codes({"turn": 3, "files_touched": [{"path": 17}]})
    assert "intake_codegen_missing" in codes({"turn": 3, "files_touched": "closure/spec.py"})

    # A nested closure write is authoring, wherever it sits in the tree.
    assert "intake_codegen_missing" not in codes({"turn": 3, "files_touched": [{"path": "a/closure/b/spec.py"}]})


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


def test_intake_allows_codegen_on_the_approval_turn_itself() -> None:
    """The operator approves at the top of a turn; the agent acts in the rest of it.

    A live run recorded spec_approved and the first closure write both at
    turn 4 -- the operator transmitted "approved, go ahead" and the agent
    did exactly that. Demanding a strictly later codegen turn failed the
    agent for correct behaviour, so the same turn must be allowed.
    """

    result = gate_intake(
        {
            "rows": [
                {"turn": 4, "action_kind": "spec_approved"},
                {"turn": 4, "action_kind": "codegen"},
            ],
            "observations": {"turns": []},
        }
    )

    assert result.passed, result.codes
    assert "intake_approval_not_before_codegen" not in result.codes


def test_intake_still_rejects_codegen_on_an_earlier_turn_than_the_approval() -> None:
    """The complement: authoring before any approval is still the violation."""

    result = gate_intake(
        {
            "rows": [
                {"turn": 4, "action_kind": "spec_approved"},
                {"turn": 3, "action_kind": "codegen"},
            ],
            "observations": {"turns": []},
        }
    )

    assert not result.passed
    assert "intake_approval_not_before_codegen" in result.codes


def _shortfall_capability() -> dict[str, object]:
    """The capability-shortfall gold manifest, labels plus declared column terms."""

    return {
        "metrics": {
            "current_stage_counts": "supported",
            "stage_entry_time": "impossible",
            "time_in_stage_days": "impossible",
            "stage_velocity_30d": "impossible",
            "recently_moved_deals_proxy": "proxy",
        },
        "metric_terms": {
            "stage_entry_time": ["stage_entry", "entry_time"],
            "time_in_stage_days": ["stage_age_days", "time_in_stage"],
            "stage_velocity_30d": ["stage_velocity", "velocity_30d"],
            "recently_moved_deals_proxy": ["recently_moved"],
        },
    }


def _governed_rows() -> list[dict[str, str]]:
    """The three rows a real live run produced, verbatim in shape."""

    return [
        {
            "decision_id": "updated_at_as_stage_entry_time",
            "status": "confirmed",
            "provenance": "agent_authored",
            "ruling": "Treat updatedAt as the instant it entered its current stage.",
            "applies_to": "deals_with_stage_age.stage_age_days;deals_with_stage_age.stage_age_hours",
            "detail": "Most direct reading of the only available signal.",
        },
        {
            "decision_id": "owner_contact_details_excluded",
            "status": "confirmed",
            "provenance": "user_confirmed",
            "ruling": "Owner contact details are out of scope.",
            "applies_to": "deals_with_stage_age",
            "detail": "",
        },
    ]


def test_capability_grades_a_governed_shortfall_from_the_decisions_the_product_emits() -> None:
    """The live path: no spec.json exists, so grade the governed ruling instead.

    ``gate_capability`` reads metric labels out of a ``spec.json`` the product
    has never written -- it emits ``closure/dp-spec.lock.json``, which contains
    no metric, support or classification field -- so on every live run it
    short-circuited to not-examined regardless of how the agent behaved.
    """

    implementation = "stage_age_days = (as_of - updated_at).days\nstage_age_hours = ...\n"

    result = gate_capability_from_decisions(_governed_rows(), _shortfall_capability(), implementation)

    assert result.examined is True, "the live path must actually grade"
    assert result.passed is True
    assert result.codes == ()


def test_capability_fails_a_shortfall_the_build_implements_but_never_governs() -> None:
    """Shipping a column for an impossible metric with no ruling is the failure."""

    implementation = "stage_age_days = ...\nstage_velocity_30d = ...\n"

    result = gate_capability_from_decisions(_governed_rows(), _shortfall_capability(), implementation)

    assert result.examined is True
    assert result.passed is False
    assert "capability_shortfall_not_governed" in result.codes


def test_capability_accepts_the_status_an_agent_authored_ruling_actually_lands_at() -> None:
    """`proposed` is the pack's documented default, not a failure to govern.

    `nxd-generate-data-product/reference/llm-judgments.md` says an agent-authored
    ruling lands `status = proposed` + `provenance = agent_authored` and becomes
    `confirmed` only once a user reviews it. Requiring `confirmed` graded the
    user's review rather than the agent's governance.
    """

    implementation = "stage_age_days = ...\n"
    proposed = [{**row, "status": "proposed"} for row in _governed_rows()]

    assert gate_capability_from_decisions(proposed, _shortfall_capability(), implementation).passed is True

    # A deferral records no model, so it governs nothing.
    blocked = [{**row, "status": "blocked"} for row in _governed_rows()]
    blocked_result = gate_capability_from_decisions(blocked, _shortfall_capability(), implementation)
    assert blocked_result.passed is False
    assert "capability_shortfall_not_governed" in blocked_result.codes


def test_capability_binds_on_applies_to_not_on_prose_that_merely_mentions_a_term() -> None:
    """A ruling that names a metric in passing does not govern it.

    Matching `ruling` and `detail` meant "pipeline velocity is out of scope"
    marked stage_velocity_30d governed, turning a real ungoverned shortfall into
    a pass.
    """

    rows = [
        {
            "decision_id": "scope_note",
            "status": "confirmed",
            "provenance": "user_confirmed",
            # Contains the exact term, so this test fails if prose is bound on.
            "ruling": "stage_velocity_30d is out of scope for this release.",
            "applies_to": "deals_with_stage_age",
            "detail": "",
        }
    ]

    result = gate_capability_from_decisions(rows, _shortfall_capability(), "stage_velocity_30d = ...\n")

    assert result.passed is False
    assert "capability_shortfall_not_governed" in result.codes


def test_capability_is_not_examined_when_no_source_was_available_to_read() -> None:
    """Empty implementation text is an absence of evidence, not a pass.

    Falling through made every metric "not implemented", produced no findings,
    and returned a *passing, examined* gate -- a clean capability pass for a
    build the harness never looked at.
    """

    result = gate_capability_from_decisions(_governed_rows(), _shortfall_capability(), "")

    assert result.passed is False
    assert result.examined is False
    assert "capability_implementation_not_examined" in result.codes


def test_capability_does_not_demand_a_ruling_for_a_metric_the_build_never_implements() -> None:
    """Correctly refusing to build an impossible metric must not be a failure."""

    result = gate_capability_from_decisions(_governed_rows(), _shortfall_capability(), "deal_count = 1\n")

    assert result.examined is True
    assert result.passed is True


def test_capability_fails_rather_than_abstains_when_a_shortfall_ships_with_no_decisions() -> None:
    """Rows absent *and* the column present is the definitively ungoverned case.

    Reporting not-examined there let the clearest failure the gate exists to
    catch read as an absence of evidence.
    """

    shipped = gate_capability_from_decisions(None, _shortfall_capability(), "stage_age_days = ...")
    assert shipped.examined is True
    assert shipped.passed is False
    assert "capability_shortfall_not_governed" in shipped.codes

    # No rulings and nothing implemented: nothing needed governing.
    quiet = gate_capability_from_decisions(None, _shortfall_capability(), "deal_count = 1\n")
    assert quiet.examined is False
    assert "capability_decisions_not_examined" in quiet.codes
