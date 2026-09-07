"""Guard tests for the seven artifact-only gates."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from dp_scenarios.grading.gates import (
    _ledger_contract_breaches,
    _mapping_artifact,
    _review_round_outcome,
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
    g3_narrowing,
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
    assert optional.gate == "capability"
    assert optional.passed is False
    assert optional.points == 0
    assert not optional.required
    assert not optional.examined
    assert not optional.ungraded
    assert optional.codes == ("capability_shortfall_not_staged",)

    optional_narrowing = gate_narrowing({}, [], None, required=False)
    assert optional_narrowing.required is False
    assert optional_narrowing.examined is False
    assert optional_narrowing.codes == ("narrowing_change_not_staged",)


def test_optional_capability_gate_preserves_its_non_scoreable_result() -> None:
    result = gate_capability_from_decisions(
        None,
        _shortfall_capability(),
        "stage_age_days = ...\n",
        required=False,
    )

    assert result.gate == "capability"
    assert result.passed is False
    assert result.points == 0
    assert result.codes == ("capability_shortfall_not_staged",)
    assert result.examined is False
    assert result.ungraded is False
    assert result.required is False


def test_legacy_narrowing_wrapper_forwards_declaration_requiredness() -> None:
    result = g3_narrowing({}, [], None, required=False)

    assert result.gate == "G3"
    assert result.passed is False
    assert result.points == 0
    assert result.codes == ("g3_change_not_staged",)
    assert result.examined is False
    assert result.required is False


def test_staged_gate_missing_evidence_stays_required_and_fails() -> None:
    capability = gate_capability_from_decisions(
        None,
        _shortfall_capability(),
        "",
        required=True,
    )
    assert capability.required is True
    assert capability.examined is False
    assert "capability_implementation_not_examined" in capability.codes

    narrowing = gate_narrowing(None, [], None, required=True)
    assert narrowing.required is True
    assert narrowing.examined is False
    assert "narrowing_ledger_not_examined" in narrowing.codes


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


def test_construction_does_not_ask_the_agent_to_retell_a_check_it_watched() -> None:
    """A self-check the harness observed needs no agent testimony about it.

    A live crm-pipeline run called ``check_data_product`` successfully before
    every build and still failed on ``self_check_outcome_missing`` and
    ``self_check_attestation_missing`` -- the harness failing an agent for not
    re-telling it what it had just seen. Same pattern as the build gate, where
    examinability depended on which artifacts the agent volunteered.
    """

    observations = {
        "turns": [
            {
                "tool_calls": [
                    {
                        "name": "mcp__nxd-desktop__check_data_product",
                        "arguments": {"name": "crm-deals"},
                        "result": {"is_error": False},
                    },
                    {
                        "name": "Task",
                        "arguments": {"subagent_type": "nxd-review-closure"},
                        "result": {"is_error": False},
                    },
                ]
            }
        ]
    }
    # No ledger row and no attestation for self_check; the reviewer half still
    # supplies both, because no tool call reveals what a review concluded.
    ledger = _ledger({"action_kind": "adversarial_review", "claim": {"outcome": "two claims, both rejected"}})

    result = gate_construction(
        ledger,
        observations=observations,
        attestations=({"action_kind": "adversarial_review", "turn": 1, "outcome": "two claims, both rejected"},),
        require_observed=True,
    )

    assert result.passed is True, "an observed check must not need an attestation as well"
    assert result.codes == ()


def _dispatch_observations(*, tool: str = "Agent", subagent_type: str = "general-purpose") -> dict:
    return {
        "turns": [
            {
                "tool_calls": [
                    {
                        "name": "mcp__nxd-desktop__check_data_product",
                        "arguments": {"name": "crm-deals"},
                        "result": {"is_error": False},
                    },
                    {
                        "name": tool,
                        "arguments": {"subagent_type": subagent_type, "prompt": "review the closure"},
                        "result": {"is_error": False},
                    },
                ]
            }
        ]
    }


def test_construction_observes_the_review_the_mandated_flow_actually_produces() -> None:
    """``subagent_type="nxd-review-closure"`` is a token no agent can emit.

    `reference/adversarial-review.md` mandates "one built-in read-only
    subagent -- never a custom/plugin agent definition", this plugin registers
    no agents at all, and the CLI rejects an unknown subagent type. Keying the
    gate on that name made `construction` unpassable by an agent doing exactly
    what the skill says.

    What the flow does produce is a ``review_rounds[]`` entry in
    build-record.json. Paired with an observed delegation call it is the
    behaviour itself, and it carries the outcome.

    The attestation is still required for this kind, unlike ``self_check``: a
    delegation call only shows that *a* subagent ran, and the round entry is
    agent-written, so neither is the harness witnessing a review the way a
    ``check_data_product`` call is the harness witnessing a self-check.
    """

    result = gate_construction(
        _ledger({"action_kind": "self_check", "claim": {"outcome": "pass"}}),
        observations=_dispatch_observations(),
        attestations=({"action_kind": "adversarial_review", "turn": 1, "outcome": "one claim, rejected"},),
        review_rounds=[{"status": "complete", "findings": [{"claim": "grain is wrong", "adjudication": "rejected"}]}],
        require_observed=True,
    )

    assert result.passed is True
    assert result.codes == ()


def test_construction_does_not_exempt_the_reviewer_from_its_attestation() -> None:
    """A research subagent plus a hand-written round is not a review.

    The observed-call exemption is scoped to ``self_check``, where the harness
    watched the exact event. Extending it to ``adversarial_review`` made a
    documentation-hunting subagent plus ``{"status": "complete"}`` pass with no
    attestation at all -- a weaker gate than the one before this branch.
    """

    result = gate_construction(
        _ledger({"action_kind": "self_check", "claim": {"outcome": "pass"}}),
        observations=_dispatch_observations(),
        attestations=(),
        review_rounds=[{"status": "complete"}],
        require_observed=True,
    )

    assert result.passed is False
    assert "construction_adversarial_review_attestation_missing" in result.codes


def test_construction_needs_both_the_dispatch_and_the_recorded_round() -> None:
    """Either half alone is not the behaviour, so neither alone counts.

    A research subagent records no round; a fabricated round dispatched
    nothing. Run 3 made four ``Agent`` calls -- doc hunting and a file
    deletion -- and must not be credited with a review.
    """

    ledger = _ledger({"action_kind": "self_check", "claim": {"outcome": "pass"}})

    dispatch_only = gate_construction(
        ledger, observations=_dispatch_observations(), attestations=(), review_rounds=[], require_observed=True
    )
    assert dispatch_only.passed is False
    assert "construction_adversarial_review_not_observed" in dispatch_only.codes

    no_dispatch = {"turns": [{"tool_calls": [
        {"name": "mcp__nxd-desktop__check_data_product", "arguments": {}, "result": {"is_error": False}},
    ]}]}
    round_only = gate_construction(
        ledger,
        observations=no_dispatch,
        attestations=(),
        review_rounds=[{"status": "complete"}],
        require_observed=True,
    )
    assert round_only.passed is False
    assert "construction_adversarial_review_not_observed" in round_only.codes

    # ``skipped`` is deliberately not a review status: a non-eligible review
    # produces no entry, so an entry claiming it is not a round.
    skipped = gate_construction(
        ledger,
        observations=_dispatch_observations(),
        attestations=(),
        review_rounds=[{"status": "skipped"}],
        require_observed=True,
    )
    assert skipped.passed is False
    assert "construction_adversarial_review_not_observed" in skipped.codes


def test_construction_observes_the_reviewer_under_either_delegation_tool_name() -> None:
    """The delegation tool is ``Agent`` in some builds and ``Task`` in others.

    A live crm-pipeline run made four ``Agent`` calls and zero ``Task`` calls.
    Matching only ``task`` made the step 6b reviewer dispatch unobservable by
    name, so the gate would have failed an agent that did exactly what the
    skill mandates.
    """

    for tool_name in ("Task", "Agent"):
        observations = {
            "turns": [
                {
                    "tool_calls": [
                        {
                            "name": "mcp__nxd-desktop__check_data_product",
                            "arguments": {"name": "crm-deals"},
                            "result": {"is_error": False},
                        },
                        {
                            "name": tool_name,
                            "arguments": {"subagent_type": "nexty-agent-skills:nxd-review-closure"},
                            "result": {"is_error": False},
                        },
                    ]
                }
            ]
        }
        result = gate_construction(
            _ledger({"action_kind": "adversarial_review", "claim": {"outcome": "one claim, rejected"}}),
            observations=observations,
            attestations=({"action_kind": "adversarial_review", "turn": 1, "outcome": "one claim, rejected"},),
            require_observed=True,
        )
        assert result.passed is True, f"{tool_name} dispatch must be observed"
        assert "construction_adversarial_review_not_observed" not in result.codes


def test_construction_still_fails_when_the_check_was_never_called() -> None:
    """Owning the self-check evidence must not make the gate unfailable."""

    ledger = _ledger({"action_kind": "adversarial_review", "claim": {"outcome": "clean"}})
    quiet = gate_construction(
        ledger,
        observations={"turns": [{"tool_calls": []}]},
        attestations=({"action_kind": "adversarial_review", "turn": 1, "outcome": "clean"},),
        require_observed=True,
    )

    assert quiet.passed is False
    assert "construction_self_check_not_observed" in quiet.codes
    assert "construction_self_check_outcome_missing" in quiet.codes
    assert "construction_self_check_attestation_missing" in quiet.codes


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


def test_build_grades_the_release_identity_and_ignores_the_row_count_oracle() -> None:
    """The two sides of the old comparison were never the same thing.

    The oracle is ``synthgen``'s ``table_row_counts``, keyed by *source table*
    with int values; the supervisor reports *built model* names, schema-
    qualified and stringified. A live crm-pipeline run compared
    ``{"main.active_deals": "5", ...}`` against ``{"deals": 1}`` and failed on
    every key. Nothing an agent could build would have passed it.
    """

    supervisor = {
        "run_id": "run-1",
        "artifact_id": "artifact-1",
        "publish_sequence": "7",
        "per_model_row_counts": {"main.deals_raw": "6", "main.pages_log": "3"},
    }

    # The real live shape, against the real oracle for that scenario.
    live = gate_build(supervisor, {"per_model_row_counts": {"deals": 1}})
    assert live.examined is True
    assert live.passed is True, "a published release must not fail on a comparison with no meaning"
    assert live.codes == ()

    # The oracle is accepted and ignored, whatever it says.
    for oracle in (None, {}, {"deals": 1}, {"main.deals_raw": 99}):
        assert gate_build(supervisor, oracle).passed is True
        assert "build_row_count_mismatch" not in gate_build(supervisor, oracle).codes


def test_build_still_fails_when_no_release_carries_the_supervisor_identity() -> None:
    """The gate stays required, so building nothing cannot dodge it.

    Dropping the count comparison must not leave a gate that cannot fail:
    ``_pass_rule`` requires ``build`` unconditionally, and no release means no
    supervisor identifiers.
    """

    supervisor = {"run_id": "run-1", "artifact_id": "artifact-1", "publish_sequence": "7"}
    for field in ("run_id", "artifact_id", "publish_sequence"):
        missing = gate_build({**supervisor, field: None}, None)
        assert missing.passed is False
        assert "build_supervisor_identifier_missing" in missing.codes

    # Absent means absent or blank, not merely falsy: ``claude_adapter``
    # accepts an integer ``publish_sequence``, and a whitespace-only string
    # clears the ledger's non-empty check while identifying nothing.
    assert gate_build({**supervisor, "publish_sequence": 0}, None).passed is True
    blank = gate_build({**supervisor, "run_id": "   "}, None)
    assert blank.passed is False
    assert blank.codes == ("build_supervisor_identifier_missing",)

    nothing_built = gate_build(None, {"per_model_row_counts": {"deals": 1}})
    assert nothing_built.passed is False
    assert nothing_built.examined is False, "no facts to read is an absence of evidence"
    assert nothing_built.codes == (
        "build_supervisor_identifier_missing",
        "build_supervisor_identifier_missing",
        "build_supervisor_identifier_missing",
    )


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


def test_query_accepts_an_earlier_retained_answer_when_a_later_query_differs() -> None:
    gold = [{"category": "契約", "row_count": 7}]
    actual = {
        "rows": [{"category": "Renovación", "row_count": 7}],
        "queries": [
            gold,
            [{"category": "Renovación", "row_count": 7}],
            gold,
        ],
    }

    result = gate_query(actual, gold)

    assert result.passed
    assert result.examined
    assert result.diagnostics[0].code == "query_matched_earlier_answer"
    assert result.diagnostics[0].value == {
        "candidate_index": 1,
        "candidate_count": 2,
        "latest_query_matched": False,
    }


def test_query_keeps_latest_rows_as_a_fallback_when_history_diverges() -> None:
    gold = [{"metric": "reconciliation", "difference": 38}]
    result = gate_query(
        {
            "rows": gold,
            "queries": [[{"metric": "reconciliation", "difference": 0}]],
        },
        gold,
    )

    assert result.passed
    assert result.diagnostics == ()


def test_query_rejects_malformed_retained_rows_without_raising() -> None:
    result = gate_query(
        {
            "rows": [{"category": "Renovación", "row_count": 7}],
            "queries": [["not a row"]],
        },
        [{"category": "契約", "row_count": 7}],
    )

    assert not result.passed
    assert result.examined
    assert result.codes == ("query_query_rows_differ",)


def test_query_rejects_malformed_latest_rows_without_raising() -> None:
    result = gate_query({"rows": ["not a row"]}, [{"metric": "reconciliation"}])

    assert not result.passed
    assert not result.examined
    assert result.codes == ("query_actual_not_examined",)


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


def test_ledger_contract_breaches_checks_each_declared_vocabulary() -> None:
    rows = [
        {
            "status": "confirmed",
            "provenance": "not-a-provenance",
            "applies_to": "deals.stage_age_days",
        },
        {
            "status": "not-a-status",
            "applies_to": "deals.stage_age_days",
        },
    ]

    assert _ledger_contract_breaches([]) == ()
    assert _ledger_contract_breaches(rows) == (
        "status has ['not-a-status']",
        "provenance has ['', 'not-a-provenance']",
    )


def test_ledger_contract_breaches_does_not_skip_provenance_when_status_is_absent() -> None:
    rows = [{"provenance": "not-a-provenance", "applies_to": "deals.stage_age_days"}]

    assert _ledger_contract_breaches(rows) == (
        "no 'status' column",
        "provenance has ['not-a-provenance']",
    )


def test_mapping_artifact_preserves_supported_object_and_nested_shapes() -> None:
    object_artifact = SimpleNamespace(
        run_id="run-1",
        artifact_id="artifact-1",
        publish_sequence=0,
        per_model_row_counts={"model": "1"},
        lifecycle_state="published",
    )
    assert _mapping_artifact(object_artifact) == {
        "run_id": "run-1",
        "artifact_id": "artifact-1",
        "publish_sequence": 0,
        "per_model_row_counts": {"model": "1"},
        "lifecycle_state": "published",
    }

    nested = _mapping_artifact(
        {
            "records": [
                {"run_id": "old"},
                {
                    "run_id": "record-run",
                    "identifiers": {
                        "run_id": "identifier-run",
                        "artifact_id": "identifier-artifact",
                    },
                },
            ]
        }
    )
    assert nested["run_id"] == "record-run"
    assert nested["artifact_id"] == "identifier-artifact"


def test_review_round_outcome_accepts_only_valid_terminal_statuses() -> None:
    assert _review_round_outcome(None) is None
    assert _review_round_outcome("complete") is None
    assert _review_round_outcome([{"status": "skipped"}, {"status": "unknown"}]) is None
    assert _review_round_outcome(
        {
            "review_rounds": [
                {"status": " COMPLETE "},
                {"status": "timed_out"},
                {"status": "needs_user"},
                {"status": "skipped"},
                {"outcome": "complete"},
                "not-a-round",
            ]
        }
    ) == "3 review round(s): complete, needs_user, timed_out"


def test_construction_can_read_a_review_outcome_from_the_recorded_round() -> None:
    result = gate_construction(
        _ledger({"action_kind": "self_check", "claim": {"outcome": "pass"}}),
        review_rounds={"review_rounds": [{"status": "needs_user"}]},
    )

    assert result.passed is True
    assert result.codes == ()


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

    # Correct abstention: the impossible metric was refused, so no column
    # shipped and there was nothing to govern. That is the gate's claim
    # satisfied, not an absence of evidence -- and once a scenario declares a
    # manifest the gate is required, so not-examined here failed the run for
    # doing the right thing.
    quiet = gate_capability_from_decisions(None, _shortfall_capability(), "deal_count = 1\n")
    assert quiet.examined is True
    assert quiet.passed is True
    assert quiet.codes == ()

    # The guard that keeps this from being a gate that cannot fail: nothing to
    # read is still not-examined, so an absent or empty closure cannot pass.
    empty = gate_capability_from_decisions(None, _shortfall_capability(), "")
    assert empty.examined is False
    assert "capability_implementation_not_examined" in empty.codes

    # And an unrelated ruling no longer decides the outcome. Before, any row
    # about anything flipped the quiet case to examined; now the verdict comes
    # from what shipped.
    unrelated = gate_capability_from_decisions(
        [
            {
                "decision_id": "stage_enum",
                "status": "proposed",
                "provenance": "agent_authored",
                "ruling": "Normalise the stage enum.",
                "applies_to": "deals.stage",
                "detail": "",
            }
        ],
        _shortfall_capability(),
        "deal_count = 1\n",
    )
    assert (unrelated.examined, unrelated.passed) == (quiet.examined, quiet.passed)


def _off_contract_rows() -> list[dict[str, str]]:
    """The ledger the crm-pipeline live run actually wrote, verbatim in shape.

    Columns ``decision_id,description,status,provenance`` with blueprint
    statuses -- no ``applies_to``, so nothing binds a ruling to a column.
    """

    return [
        {
            "decision_id": "updated_at_as_stage_entry_time",
            "description": "Treat updatedAt as the stage entry instant.",
            "status": "approved",
            "provenance": "agent_authored",
        },
        {
            "decision_id": "owner_contact_details_excluded",
            "description": "Owner contact details are out of scope.",
            "status": "settled",
            "provenance": "user_confirmed",
        },
    ]


def test_capability_names_an_off_contract_ledger_instead_of_calling_it_ungoverned() -> None:
    """The live shape: rulings exist, in a vocabulary the pack rejects.

    ``capability_shortfall_not_governed`` reads as "the agent wrote no ruling",
    which sends a reader at this gate's allowlist. The agent *did* write one --
    with the blueprint's ``approved``/``settled`` statuses and no ``applies_to``
    -- and ``self_check.py`` phase D hard-fails that closure for the same
    reason. The verdict is unchanged; the diagnosis now names the defect.
    """

    result = gate_capability_from_decisions(
        _off_contract_rows(), _shortfall_capability(), "stage_age_days = ...\n"
    )

    assert result.examined is True
    assert result.passed is False
    assert result.codes == ("capability_decisions_off_contract",)
    # Not both: one defect must not be charged once per metric as well.
    assert "capability_shortfall_not_governed" not in result.codes
    breaches = result.findings[0].value["breaches"]
    assert "applies_to" in " ".join(breaches), "the missing binding column must be named"
    assert "approved" in " ".join(breaches), "the out-of-vocabulary status must be named"
    assert result.findings[0].value["columns"] == [
        "decision_id",
        "description",
        "provenance",
        "status",
    ]


def test_capability_off_contract_survives_a_row_with_more_fields_than_headers() -> None:
    """One unquoted comma in a prose column must not crash grading.

    ``csv.DictReader`` files surplus fields under ``restkey``, which defaults to
    ``None``, and sorting ``None`` beside ``str`` raises. Nothing between the
    gate and ``_grade`` catches that, so the ledger too broken to grade would
    take the harness down instead of being reported as unreadable -- on exactly
    the hand-written shape this branch exists to report.
    """

    raw = (
        "decision_id,description,status,provenance\n"
        "updated_at_as_stage_entry,Treat updatedAt as the entry instant, per the owner,"
        "approved,agent_authored\n"
    )
    rows = [dict(row) for row in csv.DictReader(io.StringIO(raw))]
    assert None in rows[0], "the fixture must actually produce a restkey"

    result = gate_capability_from_decisions(rows, _shortfall_capability(), "stage_age_days = ...\n")

    assert result.codes == ("capability_decisions_off_contract",)
    assert "None" in result.findings[0].value["columns"]


def test_capability_off_contract_check_ignores_a_ledger_with_no_rows() -> None:
    """An empty or absent ledger is not off-contract, it is simply unruled.

    Reading a header-only or missing ``nxd_decisions`` as a contract breach
    would relabel the clearest ungoverned case -- a shortfall column shipped
    with no ruling at all -- as a schema complaint.
    """

    for rows in (None, ()):
        result = gate_capability_from_decisions(
            rows, _shortfall_capability(), "stage_age_days = ...\n"
        )
        assert "capability_shortfall_not_governed" in result.codes
        assert "capability_decisions_off_contract" not in result.codes


def test_capability_off_contract_ledger_does_not_fail_a_correct_abstention() -> None:
    """This gate's claim is about shipped shortfall columns, nothing else.

    An agent that refused the impossible metric has satisfied it. Failing that
    run over ledger hygiene would grade the self-check's question here, and
    would resurrect "any unrelated decision row decides the outcome" in mirror
    image.
    """

    result = gate_capability_from_decisions(
        _off_contract_rows(), _shortfall_capability(), "deal_count = 1\n"
    )

    assert result.examined is True
    assert result.passed is True
    assert result.codes == ()


def test_capability_off_contract_covers_one_bad_row_among_clean_ones() -> None:
    """A single out-of-vocabulary row makes the whole ledger unreadable.

    Dropping it and grading the survivors would let a clean ``proposed`` row
    govern a column while a ``superseded`` row with the same id says otherwise
    -- which is exactly what phase D refuses to do.
    """

    rows = [*_governed_rows(), {**_governed_rows()[0], "status": "superseded"}]

    result = gate_capability_from_decisions(
        rows, _shortfall_capability(), "stage_age_days = ...\n"
    )

    assert result.passed is False
    assert result.codes == ("capability_decisions_off_contract",)
    assert "superseded" in " ".join(result.findings[0].value["breaches"])
