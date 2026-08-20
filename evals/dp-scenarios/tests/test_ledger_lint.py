"""Tests for the fail-closed evidence-ledger hard gate."""

import json
from pathlib import Path

import pytest

from dp_scenarios.ledger import (
    CLAIM_WITHOUT_EVIDENCE,
    INCOMPLETE_SUPERVISOR_FACTS,
    INVALID_EVENT_ID,
    INVALID_MATCHED_RULE_ID,
    INVALID_MANIFEST,
    INVALID_QUALIFICATION,
    INVALID_SUPERSESSION,
    LEDGER_EMPTY,
    PHASE_NOT_APPLICABLE_WITHOUT_REASON,
    PHASE_UNACCOUNTED,
    ROW_MANIFEST_MISMATCH,
    SENTINEL_NOT_PERMITTED_FOR_TIER,
    SUPERVISOR_FACT_ABSENT,
    SUPERVISOR_FACT_MISMATCH,
    SUPERVISOR_FACT_NOT_STRING,
    TURN_DECREASED,
)
from dp_scenarios.ledger.lint import (
    IncompleteSupervisorFactsError,
    SupervisorFacts,
    UnhandledSituationError,
    PHASE_ACTION_KINDS,
    lint,
    supersession_diff,
)
from dp_scenarios.ledger.manifest import Manifest
from dp_scenarios.ledger.schema import LedgerRow
from dp_scenarios.ledger.store import LedgerStore, LedgerTamperError, read_ledger


def make_manifest(**overrides: object) -> Manifest:
    values: dict[str, object] = {
        "agent_model_id": "agent-v1",
        "agent_sampling_params": {"temperature": 0},
        "judge_model_id": "not-applicable",
        "judge_prompt_hash": "not-applicable",
        "skill_pack_version": "skills-1",
        "supervisor_version": "sup-1",
        "nxd_data_product_wheel_version": "wheel-1",
        "fixture_dir_hash": "fixtures-1",
        "mock_api_version": "mock-1",
        "operator_script_hash": "operator-1",
        "turn_budget": 20,
        "grant_fixture_hash": "not-applicable",
        "scenario_id": "grain-trap",
        "tier": "smoke",
        "trial_index": 1,
        "canary_claims_hash": "canary-1",
        "persona_paraphrase_prompt_hash": "not-applicable",
        "judge_calibration_set_hash": "not-applicable",
        "fixture_seed": 7,
        "fixture_base_instant": "2024-01-01T00:00:00+00:00",
        "run_id": "run-1",
    }
    values.update(overrides)
    return Manifest(**values)


def make_row(**overrides: object) -> LedgerRow:
    values: dict[str, object] = {
        "run_id": "run-1",
        "scenario_id": "grain-trap",
        "turn": 1,
        "phase": 1,
        "phase_status": "executed",
        "phase_status_reason": None,
        "action_kind": "intake",
        "action": "intake",
        "artifact_ref": None,
        "claim": None,
        "evidence_ref": None,
        "qualification": None,
        "supersedes": None,
        "term": None,
        "fact_key": None,
    }
    values.update(overrides)
    return LedgerRow(**values)


FACTS = SupervisorFacts(
    run_id="run-1",
    artifact_id="artifact-7",
    publish_sequence="3",
    per_model_row_counts={"model-a": "1000"},
    lifecycle_state="served",
)


def complete_rows() -> list[LedgerRow]:
    rows = [
        make_row(turn=1, phase=1, action_kind="intake"),
        make_row(turn=2, phase=2, action_kind="capability_probe"),
        make_row(turn=3, phase=3, action_kind="narrowing"),
        make_row(turn=4, phase=4, action_kind="codegen"),
        make_row(turn=5, phase=5, action_kind="build"),
        make_row(turn=6, phase=5, action_kind="supervisor_fact", fact_key="run_id", claim="run-1", evidence_ref="inspect#run", qualification="strong"),
        make_row(turn=7, phase=5, action_kind="supervisor_fact", fact_key="artifact_id", claim="artifact-7", evidence_ref="inspect#artifact", qualification="strong"),
        make_row(turn=8, phase=5, action_kind="supervisor_fact", fact_key="publish_sequence", claim="3", evidence_ref="inspect#publish", qualification="strong"),
        make_row(turn=9, phase=5, action_kind="supervisor_fact", fact_key="per_model_row_counts.model-a", claim="1000", evidence_ref="inspect#rows", qualification="strong"),
        make_row(turn=10, phase=5, action_kind="supervisor_fact", fact_key="lifecycle_state", claim="served", evidence_ref="inspect#state", qualification="strong"),
        make_row(turn=11, phase=6, action_kind="serve"),
        make_row(turn=12, phase=7, action_kind="follow_up"),
    ]
    return rows


def write_ledger(path: Path, rows: list[LedgerRow], *, manifest: Manifest | None = None) -> None:
    with LedgerStore.open(path, manifest or make_manifest()) as store:
        for row in rows:
            store.append(row)


def codes(report: object) -> set[str]:
    return {finding.code for finding in report.findings}  # type: ignore[attr-defined]


def test_good_ledger_lints_clean(tmp_path: Path) -> None:
    path = tmp_path / "good.jsonl"
    write_ledger(path, complete_rows())
    report = lint(path, supervisor_facts=FACTS)
    assert report.clean
    assert not report.findings


def test_empty_ledger_is_not_clean(tmp_path: Path) -> None:
    path = tmp_path / "empty.jsonl"
    with LedgerStore.open(path, make_manifest()):
        pass
    report = lint(path, supervisor_facts=FACTS)
    assert LEDGER_EMPTY in codes(report)


def test_claim_without_evidence_code_fires(tmp_path: Path) -> None:
    path = tmp_path / "claim.jsonl"
    rows = complete_rows()
    rows[0] = make_row(turn=1, claim="published", qualification="strong")
    write_ledger(path, rows)
    assert CLAIM_WITHOUT_EVIDENCE in codes(lint(path, supervisor_facts=FACTS))


def test_empty_claim_without_evidence_is_not_a_claim(tmp_path: Path) -> None:
    path = tmp_path / "empty-claim.jsonl"
    rows = complete_rows()
    rows[0] = make_row(turn=1, claim="")
    write_ledger(path, rows)

    report = lint(path, supervisor_facts=FACTS)

    assert CLAIM_WITHOUT_EVIDENCE not in codes(report)


def test_invalid_qualification_code_fires(tmp_path: Path) -> None:
    path = tmp_path / "qualification.jsonl"
    rows = complete_rows()
    rows[0] = make_row(turn=1, claim="published", evidence_ref="inspect#published", qualification="maybe")
    write_ledger(path, rows)
    assert INVALID_QUALIFICATION in codes(lint(path, supervisor_facts=FACTS))


def test_rule_and_event_ids_use_stable_identifier_grammars(tmp_path: Path) -> None:
    valid_path = tmp_path / "valid-identifiers.jsonl"
    rows = complete_rows()
    rows[0] = make_row(
        turn=1,
        matched_rule_id="source.answer.orders",
        event_ids=("deadline", "credential-fumble.1"),
    )
    write_ledger(valid_path, rows)
    assert lint(valid_path, supervisor_facts=FACTS).clean

    invalid_path = tmp_path / "invalid-identifiers.jsonl"
    rows[0] = make_row(
        turn=1,
        matched_rule_id="free prose rule",
        event_ids=("deadline", "event with spaces", "event🚫"),
    )
    write_ledger(invalid_path, rows)
    report = lint(invalid_path, supervisor_facts=FACTS)

    assert INVALID_MATCHED_RULE_ID in codes(report)
    invalid_events = [finding for finding in report.findings if finding.code == INVALID_EVENT_ID]
    assert [finding.value for finding in invalid_events] == ["event with spaces", "event🚫"]
    assert all(finding.field == "event_ids" for finding in invalid_events)


def test_matched_rule_id_with_a_junk_prefix_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "junk-prefixed-rule.jsonl"
    rows = complete_rows()
    rows[0] = make_row(turn=1, matched_rule_id="junk.source.answer.orders")
    write_ledger(path, rows)

    report = lint(path, supervisor_facts=FACTS)

    assert INVALID_MATCHED_RULE_ID in codes(report)


def test_supervisor_facts_reject_unknown_mapping_fields() -> None:
    raw = {
        "run_id": "run-1",
        "artifact_id": "artifact-7",
        "publish_sequence": "3",
        "per_model_row_counts": {"model-a": "1000"},
        "lifecycle_state": "served",
        "unexpected": "not-a-fact",
    }

    with pytest.raises(TypeError, match="unknown supervisor fact field"):
        SupervisorFacts.from_mapping(raw)


def test_claimed_approval_requires_strong_qualification(tmp_path: Path) -> None:
    path = tmp_path / "approval-qualification.jsonl"
    rows = complete_rows()
    rows[2] = make_row(
        turn=3,
        phase=3,
        action_kind="spec_approved",
        artifact_ref="artifact://spec-v1",
        claim={"open_decision_marker": False},
        evidence_ref="operator#turn-3",
        qualification="demonstrated-once",
    )
    write_ledger(path, rows)
    assert INVALID_QUALIFICATION in codes(lint(path, supervisor_facts=FACTS))


def test_spec_presentation_and_approval_are_lintable_before_codegen(tmp_path: Path) -> None:
    path = tmp_path / "approval-phase.jsonl"
    assert {phase for phase, kinds in PHASE_ACTION_KINDS.items() if "spec_presented" in kinds} == {3, 4, 5, 6, 7}
    assert {phase for phase, kinds in PHASE_ACTION_KINDS.items() if "spec_approved" in kinds} == {3, 4, 5, 6, 7}
    rows = complete_rows()
    rows.append(make_row(turn=13, phase=3, action_kind="spec_presented"))
    rows[2] = make_row(
        turn=3,
        phase=3,
        action_kind="spec_approved",
        artifact_ref="artifact://spec-v1",
        claim={"open_decision_marker": False},
        evidence_ref="operator#turn-3",
        qualification="strong",
    )
    write_ledger(path, rows)
    assert lint(path, supervisor_facts=FACTS).clean


def test_supervisor_fact_comparison_is_exact_and_does_not_alias(tmp_path: Path) -> None:
    path = tmp_path / "facts.jsonl"
    rows = complete_rows()
    rows[8] = make_row(turn=9, phase=5, action_kind="supervisor_fact", fact_key="per_model_row_counts.model-a", claim="1,000", evidence_ref="inspect#rows", qualification="strong")
    write_ledger(path, rows)
    mismatch = lint(path, supervisor_facts=FACTS)
    assert SUPERVISOR_FACT_MISMATCH in codes(mismatch)

    rows = complete_rows()
    rows[8] = make_row(turn=9, phase=5, action_kind="supervisor_fact", fact_key="per_model_row_counts.model-a", claim="1000", evidence_ref="inspect#rows", qualification="strong")
    exact_path = tmp_path / "facts-exact.jsonl"
    write_ledger(exact_path, rows)
    assert lint(exact_path, supervisor_facts=FACTS).clean


def test_supervisor_fact_aliases_are_unhandled(tmp_path: Path) -> None:
    path = tmp_path / "fact-alias.jsonl"
    rows = complete_rows()
    rows[7] = make_row(turn=8, phase=5, action_kind="supervisor_fact", fact_key="publish_seq", claim="3", evidence_ref="inspect#publish", qualification="strong")
    write_ledger(path, rows)
    with pytest.raises(UnhandledSituationError, match="fact_key"):
        lint(path, supervisor_facts=FACTS)


def test_non_string_ledger_fact_has_distinct_code(tmp_path: Path) -> None:
    path = tmp_path / "number-fact.jsonl"
    rows = complete_rows()
    rows[8] = make_row(turn=9, phase=5, action_kind="supervisor_fact", fact_key="per_model_row_counts.model-a", claim=1000, evidence_ref="inspect#rows", qualification="strong")
    write_ledger(path, rows)
    assert SUPERVISOR_FACT_NOT_STRING in codes(lint(path, supervisor_facts=FACTS))


def test_boolean_json_tokens_are_not_python_repr(tmp_path: Path) -> None:
    path = tmp_path / "boolean.jsonl"
    rows = complete_rows()
    rows[9] = make_row(turn=10, phase=5, action_kind="supervisor_fact", fact_key="lifecycle_state", claim=True, evidence_ref="inspect#state", qualification="strong")
    facts = SupervisorFacts(
        run_id="run-1", artifact_id="artifact-7", publish_sequence="3",
        per_model_row_counts={"model-a": "1000"}, lifecycle_state=True,
    )
    write_ledger(path, rows)
    assert lint(path, supervisor_facts=facts).clean
    assert SUPERVISOR_FACT_MISMATCH not in codes(lint(path, supervisor_facts=facts))


def test_json_tokens_distinguish_null_from_the_string_none(tmp_path: Path) -> None:
    class FactsWithAbsentLifecycle(SupervisorFacts):
        def value_for(self, fact_key: str) -> object:
            if fact_key == "lifecycle_state":
                return None
            return super().value_for(fact_key)

    path = tmp_path / "null-token.jsonl"
    rows = complete_rows()
    rows[9] = make_row(
        turn=10,
        phase=5,
        action_kind="supervisor_fact",
        fact_key="lifecycle_state",
        claim="None",
        evidence_ref="inspect#state",
        qualification="strong",
    )
    facts = FactsWithAbsentLifecycle(
        run_id="run-1",
        artifact_id="artifact-7",
        publish_sequence="3",
        per_model_row_counts={"model-a": "1000"},
        lifecycle_state="served",
    )
    write_ledger(path, rows)
    assert SUPERVISOR_FACT_MISMATCH in codes(lint(path, supervisor_facts=facts))


def test_turn_decrease_code_fires(tmp_path: Path) -> None:
    path = tmp_path / "turns.jsonl"
    rows = complete_rows()
    rows[0] = make_row(turn=2, phase=1, action_kind="intake")
    rows[1] = make_row(turn=1, phase=2, action_kind="capability_probe")
    write_ledger(path, rows)
    assert TURN_DECREASED in codes(lint(path, supervisor_facts=FACTS))


def test_invalid_manifest_and_tier_sentinel_findings_name_the_field(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing-manifest-field.jsonl"
    record = make_manifest().to_record()
    del record["manifest"]["operator_script_hash"]  # type: ignore[index]
    missing_path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    missing = lint(missing_path, supervisor_facts=FACTS)
    assert INVALID_MANIFEST in codes(missing)
    finding = next(item for item in missing.findings if item.code == INVALID_MANIFEST)
    assert finding.field == "operator_script_hash"
    assert finding.value is None

    budget_path = tmp_path / "bad-budget.jsonl"
    record = make_manifest().to_record()
    record["manifest"]["turn_budget"] = 0  # type: ignore[index]
    budget_path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    budget = lint(budget_path, supervisor_facts=FACTS)
    finding = next(item for item in budget.findings if item.code == INVALID_MANIFEST)
    assert finding.field == "turn_budget"
    assert finding.value == 0

    sentinel_path = tmp_path / "bad-sentinel.jsonl"
    record = make_manifest().to_record()
    record["manifest"]["agent_model_id"] = "not-applicable"  # type: ignore[index]
    sentinel_path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    assert SENTINEL_NOT_PERMITTED_FOR_TIER in codes(lint(sentinel_path, supervisor_facts=FACTS))


def test_rows_must_match_manifest_identity(tmp_path: Path) -> None:
    path = tmp_path / "identity.jsonl"
    rows = complete_rows()
    rows[0] = make_row(run_id="other-run", turn=1)
    write_ledger(path, rows)
    assert ROW_MANIFEST_MISMATCH in codes(lint(path, supervisor_facts=FACTS))


def test_build_phase_requires_each_supervisor_fact_category(tmp_path: Path) -> None:
    path = tmp_path / "absent-facts.jsonl"
    rows = [row for row in complete_rows() if row.action_kind != "supervisor_fact"]
    write_ledger(path, rows)
    report = lint(path, supervisor_facts=FACTS)
    assert SUPERVISOR_FACT_ABSENT in codes(report)
    assert len([finding for finding in report.findings if finding.code == SUPERVISOR_FACT_ABSENT]) == 5


def test_empty_supervisor_facts_cannot_certify_null_fact_rows(tmp_path: Path) -> None:
    path = tmp_path / "incomplete-facts.jsonl"
    rows = complete_rows()
    rows[5:10] = [
        make_row(
            turn=row.turn,
            phase=5,
            action_kind="supervisor_fact",
            fact_key=row.fact_key,
            claim=None,
            evidence_ref=None,
            qualification=None,
        )
        for row in rows[5:10]
    ]
    write_ledger(path, rows)
    report = lint(path, supervisor_facts={"per_model_row_counts": {"model-a": None}})
    assert not report.clean
    assert INCOMPLETE_SUPERVISOR_FACTS in codes(report)


def test_all_present_null_scalar_facts_cannot_certify_null_fact_rows(tmp_path: Path) -> None:
    path = tmp_path / "null-scalar-facts.jsonl"
    rows = complete_rows()
    for index in (5, 6, 7, 9):
        row = rows[index]
        rows[index] = make_row(
            turn=row.turn,
            phase=5,
            action_kind="supervisor_fact",
            fact_key=row.fact_key,
            claim=None,
            evidence_ref=row.evidence_ref,
            qualification=row.qualification,
        )
    write_ledger(path, rows)
    report = lint(
        path,
        supervisor_facts={
            "run_id": None,
            "artifact_id": None,
            "publish_sequence": None,
            "per_model_row_counts": {"model-a": "1000"},
            "lifecycle_state": None,
        },
    )
    assert not report.clean
    assert INCOMPLETE_SUPERVISOR_FACTS in codes(report)


def test_supervisor_facts_reject_empty_row_count_map() -> None:
    with pytest.raises(IncompleteSupervisorFactsError, match="per_model_row_counts.*empty"):
        SupervisorFacts(
            run_id="run-1",
            artifact_id="artifact-7",
            publish_sequence="3",
            per_model_row_counts={},
            lifecycle_state="served",
        )


def test_empty_string_supervisor_facts_cannot_certify_empty_claim_rows(tmp_path: Path) -> None:
    path = tmp_path / "empty-string-facts.jsonl"
    rows = complete_rows()
    rows[5:10] = [
        make_row(
            turn=row.turn,
            phase=5,
            action_kind="supervisor_fact",
            fact_key=row.fact_key,
            claim="",
            evidence_ref=f"inspect#{row.fact_key}",
            qualification="not-claimed",
        )
        for row in rows[5:10]
    ]
    write_ledger(path, rows)
    report = lint(
        path,
        supervisor_facts={
            "run_id": "",
            "artifact_id": "",
            "publish_sequence": "",
            "per_model_row_counts": {"model-a": ""},
            "lifecycle_state": "",
        },
    )
    assert not report.clean
    assert INCOMPLETE_SUPERVISOR_FACTS in codes(report)


def test_supervisor_fact_requires_evidence_and_qualification_for_empty_claim(tmp_path: Path) -> None:
    path = tmp_path / "empty-fact-metadata.jsonl"
    rows = complete_rows()
    rows[5] = make_row(
        turn=6,
        phase=5,
        action_kind="supervisor_fact",
        fact_key="run_id",
        claim=None,
        evidence_ref=None,
        qualification=None,
    )
    write_ledger(path, rows)
    report = lint(path, supervisor_facts=FACTS)
    assert CLAIM_WITHOUT_EVIDENCE in codes(report)
    assert INVALID_QUALIFICATION in codes(report)
    assert SUPERVISOR_FACT_NOT_STRING in codes(report)


def test_per_model_fact_presence_is_checked_for_each_declared_model(tmp_path: Path) -> None:
    path = tmp_path / "missing-model-facts.jsonl"
    rows = complete_rows()
    facts = SupervisorFacts(
        run_id="run-1",
        artifact_id="artifact-7",
        publish_sequence="3",
        per_model_row_counts={"model-a": "1000", "model-b": "2000", "model-c": "3000"},
        lifecycle_state="served",
    )
    write_ledger(path, rows)
    report = lint(path, supervisor_facts=facts)
    missing = [finding for finding in report.findings if finding.code == SUPERVISOR_FACT_ABSENT]
    assert {finding.value for finding in missing} == {"model-b", "model-c"}


def test_not_applicable_build_phase_does_not_require_supervisor_facts(tmp_path: Path) -> None:
    path = tmp_path / "not-applicable-build.jsonl"
    rows = [row for row in complete_rows() if row.action_kind != "supervisor_fact"]
    rows[4] = make_row(
        turn=5,
        phase=5,
        action_kind="build",
        phase_status="not-applicable",
        phase_status_reason="scenario ended before build",
    )
    write_ledger(path, rows)
    assert lint(path, supervisor_facts=FACTS).clean


def test_supervisor_facts_are_not_extracted_from_prose(tmp_path: Path) -> None:
    path = tmp_path / "prose-fact.jsonl"
    rows = [row for row in complete_rows() if row.fact_key != "lifecycle_state"]
    rows.append(make_row(turn=13, phase=6, action_kind="query", action="lifecycle_state=served"))
    write_ledger(path, rows)
    report = lint(path, supervisor_facts=FACTS)
    assert SUPERVISOR_FACT_MISMATCH not in codes(report)
    assert SUPERVISOR_FACT_ABSENT in codes(report)


def test_phase_coverage_and_not_applicable_reason_are_required(tmp_path: Path) -> None:
    missing_path = tmp_path / "phase-missing.jsonl"
    rows = [row for row in complete_rows() if row.phase != 7]
    write_ledger(missing_path, rows)
    assert PHASE_UNACCOUNTED in codes(lint(missing_path, supervisor_facts=FACTS))

    reason_path = tmp_path / "phase-reason.jsonl"
    rows = complete_rows()
    rows[1] = make_row(turn=2, phase=2, action_kind="capability_probe", phase_status="not-applicable")
    write_ledger(reason_path, rows)
    assert PHASE_NOT_APPLICABLE_WITHOUT_REASON in codes(lint(reason_path, supervisor_facts=FACTS))


def test_unrecognized_action_kind_raises_instead_of_failing_open(tmp_path: Path) -> None:
    path = tmp_path / "unknown-action.jsonl"
    rows = complete_rows()
    rows[0] = make_row(turn=1, action_kind="narrated_fact")
    write_ledger(path, rows)
    with pytest.raises(UnhandledSituationError, match=r"action_kind 'narrated_fact'"):
        lint(path, supervisor_facts=FACTS)


def test_unknown_action_kind_check_is_independent_of_phase_matrix(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "unknown-action-isolated.jsonl"
    rows = complete_rows()
    rows[0] = make_row(turn=1, action_kind="narrated_fact")
    write_ledger(path, rows)
    monkeypatch.setitem(PHASE_ACTION_KINDS, 1, frozenset({"intake", "narrated_fact"}))
    with pytest.raises(UnhandledSituationError, match=r"action_kind 'narrated_fact'"):
        lint(path, supervisor_facts=FACTS)


def test_phase_action_matrix_rejects_impossible_combination(tmp_path: Path) -> None:
    path = tmp_path / "impossible-phase-action.jsonl"
    rows = complete_rows()
    rows[0] = make_row(turn=1, action_kind="build")
    write_ledger(path, rows)
    with pytest.raises(UnhandledSituationError, match=r"'build' in phase 1"):
        lint(path, supervisor_facts=FACTS)


def test_supersession_is_row_id_keyed_and_materialized_by_turn(tmp_path: Path) -> None:
    path = tmp_path / "supersession.jsonl"
    rows = complete_rows()
    rows[0] = make_row(turn=1, action_kind="intake", claim="revenue is stable", term="revenue", evidence_ref="inspect#revenue", qualification="strong")
    rows[1] = make_row(turn=1, phase=1, action_kind="intake", claim="revenue is seasonal", term="revenue", evidence_ref="inspect#revenue2", qualification="strong")
    write_ledger(path, rows)
    first_id = read_ledger(path)[1]["row_id"]
    with LedgerStore.open(path, make_manifest()) as store:
        store.append(make_row(turn=4, phase=7, action_kind="supersession", action="redefine first revenue claim", claim="revenue is seasonal", term="revenue", evidence_ref="inspect#correction", qualification="strong-for-this-attempt", supersedes=first_id))  # type: ignore[arg-type]

    resolved = read_ledger(path, resolve_supersession=True)
    assert resolved[1]["superseded_by_turn"] == 4
    assert resolved[2]["superseded_by_turn"] is None
    results = supersession_diff(path, term="revenue", change_turn=5)
    assert len(results) == 2
    assert results[0].has_superseding_row
    assert not results[1].has_superseding_row


def test_supersession_diff_uses_exact_term_and_excludes_correction(tmp_path: Path) -> None:
    path = tmp_path / "declared-term.jsonl"
    rows = complete_rows()
    rows[0] = make_row(turn=1, claim="net_revenue_gross_margin steady", term="net_revenue_gross_margin", evidence_ref="inspect#claim", qualification="strong")
    write_ledger(path, rows)
    assert supersession_diff(path, term="revenue", change_turn=2) == []
    assert len(supersession_diff(path, term="net_revenue_gross_margin", change_turn=2)) == 1


@pytest.mark.parametrize(
    "replacement",
    [
        {"supersedes": 999, "claim": "correction"},
        {"supersedes": 1, "claim": None},
    ],
)
def test_invalid_supersession_code_fires(tmp_path: Path, replacement: dict[str, object]) -> None:
    path = tmp_path / "bad-supersession.jsonl"
    rows = complete_rows()
    rows.append(make_row(turn=20, phase=7, action_kind="supersession", evidence_ref="inspect#correction", qualification="strong", **replacement))
    write_ledger(path, rows)
    assert INVALID_SUPERSESSION in codes(lint(path, supervisor_facts=FACTS))


def test_supersession_cannot_target_a_later_turn(tmp_path: Path) -> None:
    path = tmp_path / "later-target.jsonl"
    rows = complete_rows()
    rows.append(make_row(turn=20, phase=7, action_kind="supersession", claim="correction", evidence_ref="inspect#correction", qualification="strong", supersedes=14))
    rows.append(make_row(turn=21, phase=7, action_kind="follow_up"))
    write_ledger(path, rows)
    assert INVALID_SUPERSESSION in codes(lint(path, supervisor_facts=FACTS))


@pytest.mark.parametrize(
    "replacement",
    [
        {"action_kind": "supersession", "supersedes": 13},
        {"action_kind": "follow_up", "supersedes": 1},
    ],
)
def test_supersession_requires_a_prior_target_and_kind(tmp_path: Path, replacement: dict[str, object]) -> None:
    path = tmp_path / "bad-supersession-target.jsonl"
    rows = complete_rows()
    rows.append(
        make_row(
            turn=20,
            phase=7,
            action="invalid supersession target",
            claim="correction",
            evidence_ref="inspect#correction",
            qualification="strong",
            **replacement,
        )
    )
    write_ledger(path, rows)
    assert INVALID_SUPERSESSION in codes(lint(path, supervisor_facts=FACTS))


def test_supersession_cycle_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "supersession-cycle.jsonl"
    rows = complete_rows()
    rows.extend(
        [
            make_row(
                turn=20,
                phase=7,
                action_kind="supersession",
                claim="first correction",
                evidence_ref="inspect#first",
                qualification="strong",
                supersedes=14,
            ),
            make_row(
                turn=20,
                phase=7,
                action_kind="supersession",
                claim="second correction",
                evidence_ref="inspect#second",
                qualification="strong",
                supersedes=13,
            ),
        ]
    )
    write_ledger(path, rows)
    assert INVALID_SUPERSESSION in codes(lint(path, supervisor_facts=FACTS))


def test_lint_and_supersession_diff_reject_a_truncated_tail(tmp_path: Path) -> None:
    path = tmp_path / "truncated-tail.jsonl"
    write_ledger(path, complete_rows())
    lines = path.read_bytes().splitlines(keepends=True)
    path.write_bytes(b"".join(lines[:-1]))

    with pytest.raises(LedgerTamperError, match="history ends at line"):
        lint(path, supervisor_facts=FACTS)
    with pytest.raises(LedgerTamperError, match="history ends at line"):
        supersession_diff(path, term="revenue", change_turn=2)


def test_lint_and_supersession_diff_require_the_anchor_sidecar(tmp_path: Path) -> None:
    path = tmp_path / "sidecar-required.jsonl"
    write_ledger(path, complete_rows())
    path.with_name(path.name + ".anchor").unlink()

    with pytest.raises(LedgerTamperError, match="terminal anchor"):
        lint(path, supervisor_facts=FACTS)
    with pytest.raises(LedgerTamperError, match="terminal anchor"):
        supersession_diff(path, term="revenue", change_turn=2)


def test_supersession_diff_requires_a_declared_term(tmp_path: Path) -> None:
    path = tmp_path / "term-validation.jsonl"
    write_ledger(path, complete_rows())
    with pytest.raises(ValueError, match="term"):
        supersession_diff(path, term=None, change_turn=2)  # type: ignore[arg-type]
