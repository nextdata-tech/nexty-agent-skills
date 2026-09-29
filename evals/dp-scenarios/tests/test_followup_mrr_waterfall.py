"""B7 release, capture, verifier, and query evidence must agree."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from dp_scenarios.followups import FollowUpContext
from dp_scenarios.followups.mrr_waterfall import check
from dp_scenarios.grading.gates import gate_query
from dp_scenarios.runner.evidence_context import load_supervisor_history_view
from dp_scenarios.runner.supervisor_history import (
    CAPTURES_SCHEMA,
    DEFINITION_EXPORT_SCHEMA,
    PUBLICATION_SCHEMA,
    QUERY_HISTORY_SCHEMA,
    RUN_FAILURES_SCHEMA,
    RUN_RECORDS_SCHEMA,
    TOOL_CALLS_SCHEMA,
)


GOLD_DIR = Path(__file__).parents[1] / "scenarios/mrr-waterfall/gold"
ANSWER = json.loads((GOLD_DIR / "mrr_waterfall_answer.json").read_text(encoding="utf-8"))
GROSS = json.loads((GOLD_DIR / "mrr_waterfall_gross.json").read_text(encoding="utf-8"))
CONTROLS = json.loads((GOLD_DIR / "mrr_waterfall_controls.json").read_text(encoding="utf-8"))
SCRIPT = b'''import duckdb
from nxd import data_product
from nxd.core.context import DuckDbOutput, VerifyResult, VerifyResultEnum

@data_product.on_verify()
def verify(output: DuckDbOutput):
    waterfall = output.full_table_name("mrr_waterfall")
    witness = output.full_table_name("customer_month_mrr")
    connection = duckdb.connect(str(output.path), read_only=True)
    rows = connection.execute(f"""
        WITH movement AS (
          SELECT month,
            SUM(CASE WHEN movement = 'new' THEN amount_cents ELSE 0 END)
            + SUM(CASE WHEN movement = 'expansion' THEN amount_cents ELSE 0 END)
            - SUM(CASE WHEN movement = 'contraction' THEN amount_cents ELSE 0 END)
            - SUM(CASE WHEN movement = 'churn' THEN amount_cents ELSE 0 END)
            + SUM(CASE WHEN movement = 'reactivation' THEN amount_cents ELSE 0 END) AS delta
          FROM {waterfall} GROUP BY month
        ), balances AS (
          SELECT month, SUM(opening_mrr_cents) AS opening,
            SUM(closing_mrr_cents) AS closing
          FROM {witness} GROUP BY month
        )
        SELECT movement.month FROM movement JOIN balances USING (month)
        WHERE movement.delta <> balances.closing - balances.opening
    """).fetchall()
    if rows:
        return VerifyResult(VerifyResultEnum.FAILED, {"rows": rows})
    return VerifyResult(VerifyResultEnum.PASS, {"rows": 0})

if __name__ == "__main__":
    data_product.verify()
'''
VACUOUS = b'''from nxd import data_product
from nxd.core.context import VerifyResult, VerifyResultEnum

@data_product.on_verify()
def verify(output):
    return VerifyResult(VerifyResultEnum.PASS, {})

if __name__ == "__main__":
    data_product.verify()
'''


def _sha(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _approved_capture(*, gross: bool) -> dict[str, bytes]:
    policy = (
        "Show same-month down and up movements separately on a gross basis."
        if gross else
        "Use prior-month close and current-month close; net interim movements out."
    )
    proposal = {
        "proposal": {
            "decisions": [
                {"id": "same_month_classification", "target": "mrr_movement_amount_cents", "ruling": policy, "status": "locked"},
                {"id": "event_deduplication", "target": "billing_events_dedup", "ruling": "Use event_id, retain one exact copy, and stop on conflicting duplicates.", "status": "locked"},
            ]
        }
    }
    approved = b"# Approved B7 bridge\n"
    proposal_bytes = json.dumps(proposal, sort_keys=True).encode()
    lock = {
        "spec_status_at_copy": "approved",
        "snapshot_sha256": _sha(approved),
        "proposal_snapshot_sha256": _sha(proposal_bytes),
    }
    return {
        "dp-blueprint.approved.md": approved,
        "dp-blueprint.proposal.approved.json": proposal_bytes,
        "dp-blueprint.lock.json": json.dumps(lock).encode(),
        "contracts/mrr_bridge_identity.py": SCRIPT,
    }


def _change_ruling(case: Case, index: int, decision_id: str, ruling: str) -> None:
    proposal = json.loads(case.files[index]["dp-blueprint.proposal.approved.json"])
    decision = next(item for item in proposal["proposal"]["decisions"] if item["id"] == decision_id)
    decision["ruling"] = ruling
    content = json.dumps(proposal, sort_keys=True).encode()
    case.files[index]["dp-blueprint.proposal.approved.json"] = content
    lock = json.loads(case.files[index]["dp-blueprint.lock.json"])
    lock["proposal_snapshot_sha256"] = _sha(content)
    case.files[index]["dp-blueprint.lock.json"] = json.dumps(lock).encode()


class Case:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.files = {1: _approved_capture(gross=True), 2: _approved_capture(gross=False)}
        self.docs: dict[str, dict[str, object]] = {
            "publication-history": {"schema": PUBLICATION_SCHEMA, "releases": []},
            "run-records": {"schema": RUN_RECORDS_SCHEMA, "runs": []},
            "run-failures": {"schema": RUN_FAILURES_SCHEMA, "failures": []},
            "tool-calls": {"schema": TOOL_CALLS_SCHEMA, "calls": [{"turn": 27, "tool": "inspect_workflow", "workflow_id": "mrr-waterfall", "answered": True, "is_error": False}]},
            "query-history": {"schema": QUERY_HISTORY_SCHEMA, "queries": [
                {"turn": 12, "index": 0, "run_id": "run-1", "workflow_id": "mrr-waterfall", "rows": GROSS},
                {"turn": 24, "index": 0, "run_id": "run-2", "workflow_id": "mrr-waterfall", "rows": ANSWER},
                {"turn": 25, "index": 0, "run_id": "run-2", "workflow_id": "mrr-waterfall", "rows": [
                    {"month": row["month"], "opening_mrr_cents": row["opening_mrr_cents"], "closing_mrr_cents": row["closing_mrr_cents"]}
                    for row in CONTROLS
                ]},
            ]},
            "supervisor-captures": {"schema": CAPTURES_SCHEMA, "captures": []},
            "definition-export": {"schema": DEFINITION_EXPORT_SCHEMA, "definitions": []},
        }
        for index, published_turn in ((1, 10), (2, 23)):
            run_id = f"run-{index}"
            definition_id = f"sha256-v1:{index:064x}"
            capture_sha = f"sha256:{index:064x}"
            release = {
                "run_id": run_id, "workflow_id": "mrr-waterfall", "definition_id": definition_id,
                "artifact_id": f"artifact-{index}", "publish_sequence": str(index),
                "verification_outcome": "passed",
                "row_counts": {"main.billing_events_dedup": "21", "main.customer_month_mrr": "24", "main.mrr_waterfall": "14"},
                # This is the run-start turn, deliberately earlier than publish.
                "turn": published_turn - 4,
            }
            self.docs["publication-history"]["releases"].append(release)
            self.docs["run-records"]["runs"].append({
                "run_id": run_id, "workflow_id": "mrr-waterfall", "definition_id": definition_id,
                "artifact_id": f"artifact-{index}", "publish_sequence": str(index),
                "capture_sha256": capture_sha, "status": "Published",
                "status_history": [{"turn": published_turn - 4, "status": "Running"}, {"turn": published_turn, "status": "Published"}],
            })
            self.docs["definition-export"]["definitions"].append({
                "definition_id": definition_id, "run_ids": [run_id], "workflow_ids": ["mrr-waterfall"],
                "present": True, "inventory_valid": True,
                "output_promises": [{
                    "port": "duckdb", "name": "mrr-bridge-identity", "models": ["mrr_waterfall"],
                    "source": "contracts/mrr_bridge_identity.py", "verifier_kind": "script",
                    "source_in_inventory": True, "source_hash_verified": True,
                    "source_sha256": _sha(SCRIPT),
                }],
            })
            self.docs["supervisor-captures"]["captures"].append({
                "capture_sha256": capture_sha, "run_ids": [run_id], "workflow_ids": ["mrr-waterfall"],
                "files": [],
            })
        self.observations: dict[str, object] = {"turns": [
            {"turn": 4, "fired_event_ids": ["B7-same-month"], "operator_message": "Please ask me how a same-month drop and rise should appear."},
            {"turn": 5, "fired_event_ids": [], "operator_message": "Please continue.", "operator_matched_rule_id": "decision.answer.same_month_classification", "operator_matched_decision_id": "same_month_classification", "operator_matched_reply": "Show both directions separately, gross.", "operator_matched": True},
            {"turn": 6, "fired_event_ids": [], "operator_message": "Show both directions separately, gross."},
            {"turn": 7, "fired_event_ids": [], "operator_message": "Please continue.", "operator_matched_rule_id": "decision.answer.event_deduplication", "operator_matched_decision_id": "event_deduplication", "operator_matched_reply": "Keep one exact event_id copy and stop on conflict.", "operator_matched": True},
            {"turn": 8, "fired_event_ids": [], "operator_message": "Keep one exact event_id copy and stop on conflict."},
            {"turn": 17, "fired_event_ids": ["B7-E8"], "operator_message": "I am changing the same-month decision."},
            {"turn": 18, "fired_event_ids": [], "operator_message": "Please continue.", "operator_matched_rule_id": "decision.answer.same_month_classification_revised", "operator_matched_decision_id": "same_month_classification_revised", "operator_matched_reply": "Use prior-month close and current-month close, netting interim moves.", "operator_matched": True},
            {"turn": 19, "fired_event_ids": [], "operator_message": "Use prior-month close and current-month close, netting interim moves."},
            {"turn": 27, "fired_event_ids": ["B7-E3"], "operator_message": "Where were we?"},
        ]}
        self.scenario = SimpleNamespace(
            answer_sheet=SimpleNamespace(decision_answers={
                "same_month_classification": SimpleNamespace(answer="Show both directions separately, gross."),
                "same_month_classification_revised": SimpleNamespace(answer="Use prior-month close and current-month close, netting interim moves."),
                "event_deduplication": SimpleNamespace(answer="Keep one exact event_id copy and stop on conflict."),
            }),
            raw_gold=lambda key: {"answer": ANSWER, "controls": CONTROLS}[key],
        )

    def write(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        for index, files in self.files.items():
            capture = self.docs["supervisor-captures"]["captures"][index - 1]
            capture["files"] = []
            folder = self.root / "supervisor-captures" / f"{index:064x}"
            folder.mkdir(parents=True, exist_ok=True)
            for name, content in files.items():
                path = folder / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
                capture["files"].append({"path": name, "size": len(content), "sha256": _sha(content)})
        for name, doc in self.docs.items():
            (self.root / f"{name}.json").write_text(json.dumps(doc), encoding="utf-8")

    def check(self) -> dict[str, object]:
        self.write()
        return dict(check(self.scenario, {}, {}, FollowUpContext(
            operator_observations=self.observations,
            supervisor_history=load_supervisor_history_view(self.root),
        )))


@pytest.fixture
def case(tmp_path: Path) -> Case:
    return Case(tmp_path / "artifacts")


def test_clean_revised_release_passes_from_runner_owned_evidence(case: Case) -> None:
    assert case.check() == {"status": "examined", "passed": True, "findings": []}


def test_runner_history_absent_is_ungraded(tmp_path: Path) -> None:
    case = Case(tmp_path / "absent")
    view = load_supervisor_history_view(case.root)
    result = check(case.scenario, {}, {}, FollowUpContext(operator_observations=case.observations, supervisor_history=view))
    assert result["status"] == "ungraded"


def test_selected_but_undelivered_decision_is_not_evidence(case: Case) -> None:
    case.observations["turns"][2]["operator_message"] = "Please continue."
    assert "b7_decision_exchange_missing" in case.check()["findings"]


@pytest.mark.parametrize("turn_index", [4, 7])
def test_dedup_or_revised_answer_must_be_delivered(case: Case, turn_index: int) -> None:
    case.observations["turns"][turn_index]["operator_message"] = "Please continue."
    assert "b7_decision_exchange_missing" in case.check()["findings"]


def test_initial_and_final_approved_captures_must_record_stable_locked_decision(case: Case) -> None:
    for index in (1, 2):
        mutant = Case(case.root / str(index))
        mutant.files[index].pop("dp-blueprint.proposal.approved.json")
        assert "b7_decision_record_missing" in mutant.check()["findings"]


def test_blueprint_only_dedup_text_does_not_count(case: Case) -> None:
    proposal = json.loads(case.files[2]["dp-blueprint.proposal.approved.json"])
    proposal["proposal"]["decisions"] = proposal["proposal"]["decisions"][:1]
    content = json.dumps(proposal, sort_keys=True).encode()
    case.files[2]["dp-blueprint.proposal.approved.json"] = content
    lock = json.loads(case.files[2]["dp-blueprint.lock.json"])
    lock["proposal_snapshot_sha256"] = _sha(content)
    case.files[2]["dp-blueprint.lock.json"] = json.dumps(lock).encode()
    case.files[2]["dp-blueprint.approved.md"] = b"# event_deduplication uses event_id, exact copy, stop on conflict\n"
    lock["snapshot_sha256"] = _sha(case.files[2]["dp-blueprint.approved.md"])
    case.files[2]["dp-blueprint.lock.json"] = json.dumps(lock).encode()
    assert "b7_dedup_rule_missing" in case.check()["findings"]


def test_negated_policy_text_cannot_pass_the_approved_decision_checks(case: Case) -> None:
    _change_ruling(case, 1, "same_month_classification", "Do not show down and up separately on a gross basis; use net.")
    assert "b7_decision_record_missing" in case.check()["findings"]
    _change_ruling(case, 1, "same_month_classification", "Show same-month down and up movements separately on a gross basis.")
    _change_ruling(case, 2, "same_month_classification", "Do not use prior-month close and current-month close to net movements.")
    assert "b7_decision_record_missing" in case.check()["findings"]
    _change_ruling(case, 2, "same_month_classification", "Use prior-month close and current-month close; net interim movements out.")
    _change_ruling(case, 2, "event_deduplication", "Use event_id; do not retain one exact copy or stop on conflicts.")
    assert "b7_dedup_rule_missing" in case.check()["findings"]
    _change_ruling(case, 1, "same_month_classification", "Gross basis is not permitted; show down and up movements separately.")
    assert "b7_decision_record_missing" in case.check()["findings"]
    _change_ruling(case, 1, "same_month_classification", "Show same-month down and up movements separately on a gross basis.")
    _change_ruling(case, 2, "same_month_classification", "Prior-month and current-month close should be used; net treatment is prohibited.")
    assert "b7_decision_record_missing" in case.check()["findings"]
    _change_ruling(case, 2, "same_month_classification", "Use prior-month close and current-month close; net interim movements out.")
    _change_ruling(case, 2, "event_deduplication", "Use event_id for exact copies; stopping on conflict is not required.")
    assert "b7_dedup_rule_missing" in case.check()["findings"]


def test_revised_publication_must_follow_e8_with_a_new_definition(case: Case) -> None:
    case.docs["run-records"]["runs"][1]["status_history"][-1]["turn"] = 16
    assert "b7_revised_release_missing" in case.check()["findings"]


def test_stale_same_shaped_gross_query_cannot_be_borrowed_from_first_run(case: Case) -> None:
    queries = case.docs["query-history"]["queries"]
    queries.pop(1)
    assert "b7_final_query_run_mismatch" in case.check()["findings"]
    assert not gate_query({"rows": GROSS, "queries": [ANSWER, GROSS]}, ANSWER).passed


def test_query_must_follow_revised_publication(case: Case) -> None:
    case.docs["query-history"]["queries"][1]["turn"] = 22
    assert "b7_final_query_run_mismatch" in case.check()["findings"]


def test_identity_uses_independent_control_rows_from_final_run(case: Case) -> None:
    rows = case.docs["query-history"]["queries"][2]["rows"]
    rows[1]["closing_mrr_cents"] += 1
    assert "b7_identity_rows_differ" in case.check()["findings"]


def test_compiled_promise_must_be_executed_and_nonvacuous(case: Case) -> None:
    case.docs["publication-history"]["releases"][1]["verification_outcome"] = "failed"
    assert "b7_identity_promise_missing" in case.check()["findings"]
    case.docs["publication-history"]["releases"][1]["verification_outcome"] = "passed"
    case.files[2]["contracts/mrr_bridge_identity.py"] = VACUOUS
    case.docs["definition-export"]["definitions"][1]["output_promises"][0]["source_sha256"] = _sha(VACUOUS)
    assert "b7_identity_promise_missing" in case.check()["findings"]
    case.docs["definition-export"]["definitions"][1]["output_promises"][0]["source_hash_verified"] = False
    assert "b7_identity_promise_missing" in case.check()["findings"]
    constant_branch = SCRIPT.replace(b"if rows:", b"if False:")
    case.files[2]["contracts/mrr_bridge_identity.py"] = constant_branch
    promise = case.docs["definition-export"]["definitions"][1]["output_promises"][0]
    promise["source_hash_verified"] = True
    promise["source_sha256"] = _sha(constant_branch)
    assert "b7_identity_promise_missing" in case.check()["findings"]
    unused_helper = SCRIPT.replace(
        b"    if rows:\n        return VerifyResult(VerifyResultEnum.FAILED, {\"rows\": rows})\n",
        b"    def unused(value):\n        if value:\n            return VerifyResult(VerifyResultEnum.FAILED, {})\n",
    )
    case.files[2]["contracts/mrr_bridge_identity.py"] = unused_helper
    promise["source_sha256"] = _sha(unused_helper)
    assert "b7_identity_promise_missing" in case.check()["findings"]
    unrelated_branch = SCRIPT.replace(b"if rows:", b"if unrelated_flag:")
    case.files[2]["contracts/mrr_bridge_identity.py"] = unrelated_branch
    promise["source_sha256"] = _sha(unrelated_branch)
    assert "b7_identity_promise_missing" in case.check()["findings"]
    for decoy in (b"if waterfall == witness:", b"if len(waterfall) + len(witness) < 0:"):
        decoy_source = SCRIPT.replace(b"if rows:", decoy)
        case.files[2]["contracts/mrr_bridge_identity.py"] = decoy_source
        promise["source_sha256"] = _sha(decoy_source)
        assert "b7_identity_promise_missing" in case.check()["findings"]
    always_empty_helper = SCRIPT.replace(
        b"    rows = connection.execute(f\"\"\"",
        b"    rows = compare_monthly_totals(waterfall, witness)\n"
        b"    unused = connection.execute(f\"\"\"",
    )
    always_empty_helper = always_empty_helper.replace(
        b"@data_product.on_verify()",
        b"def compare_monthly_totals(_waterfall, _witness):\n    return []\n\n@data_product.on_verify()",
    )
    case.files[2]["contracts/mrr_bridge_identity.py"] = always_empty_helper
    promise["source_sha256"] = _sha(always_empty_helper)
    assert "b7_identity_promise_missing" in case.check()["findings"]


def test_revised_model_counts_are_exact(case: Case) -> None:
    case.docs["publication-history"]["releases"][1]["row_counts"]["main.customer_month_mrr"] = "23"
    assert "b7_model_row_count_mismatch" in case.check()["findings"]


def test_e3_requires_supervisor_read_and_forbids_new_workflow_action(case: Case) -> None:
    calls = case.docs["tool-calls"]["calls"]
    calls.append({"turn": 27, "tool": "advance_workflow", "action_type": "publish", "answered": True, "is_error": False})
    assert "b7_e3_resume_missing" in case.check()["findings"]
    calls.pop()
    calls.clear()
    assert "b7_e3_resume_missing" in case.check()["findings"]
    calls.append({"turn": 27, "tool": "inspect_workflow", "workflow_id": "unrelated", "answered": True, "is_error": False})
    assert "b7_e3_resume_missing" in case.check()["findings"]


def test_wrong_run_capture_or_definition_is_ungraded(case: Case) -> None:
    case.docs["run-records"]["runs"][1]["capture_sha256"] = f"sha256:{1:064x}"
    assert case.check()["status"] == "ungraded"
    case.docs["run-records"]["runs"][1]["capture_sha256"] = f"sha256:{2:064x}"
    case.docs["publication-history"]["releases"][1]["definition_id"] = f"sha256-v1:{1:064x}"
    assert case.check()["status"] == "ungraded"


def test_agent_artifact_claims_cannot_replace_publication_evidence(case: Case) -> None:
    case.docs["publication-history"]["releases"].pop()
    case.write()
    context = FollowUpContext(
        operator_observations=case.observations,
        supervisor_history=load_supervisor_history_view(case.root),
    )
    target = {"publication_ref": "run-2", "governed_query_refs": ["24:0"], "decision_refs": ["approved"]}
    result = check(case.scenario, target, {}, context)
    assert "b7_revised_release_missing" in result["findings"]


# --- successor-workflow revision (live run r416) -----------------------------
#
# The shipped skill forbids revising a published workflow in place: it asks
# the operator, then prepares a separate versioned product under a NEW
# workflow id. The grader must accept that as the revised release, but only
# when the operator authorized it after the agent asked.

_SUCCESSOR = "mrr-waterfall-v2"
_ASK = (
    "I haven't revised anything. Restating the decision would mean a new "
    "versioned product under a new workflow id, and I'd ask you first."
)


def _to_successor(case: Case, *, ask_turn: int | None = 17, prepare_turn: int = 19) -> None:
    """Move the revised release (index 2) onto a successor workflow id."""

    case.docs["publication-history"]["releases"][1]["workflow_id"] = _SUCCESSOR
    case.docs["run-records"]["runs"][1]["workflow_id"] = _SUCCESSOR
    case.docs["definition-export"]["definitions"][1]["workflow_ids"] = [_SUCCESSOR]
    case.docs["supervisor-captures"]["captures"][1]["workflow_ids"] = [_SUCCESSOR]
    for query in case.docs["query-history"]["queries"][1:]:
        query["workflow_id"] = _SUCCESSOR
    calls = case.docs["tool-calls"]["calls"]
    for call in calls:
        call["workflow_id"] = _SUCCESSOR
    calls.append({"turn": prepare_turn, "tool": "prepare_workflow", "workflow_id": _SUCCESSOR, "answered": True, "is_error": False})
    if ask_turn is not None:
        next(row for row in case.observations["turns"] if row["turn"] == ask_turn)["agent_message"] = _ASK
    for row in case.observations["turns"]:
        row.setdefault("agent_message", "Noted.")


def test_authorized_successor_workflow_is_the_revised_release(case: Case) -> None:
    _to_successor(case)
    assert case.check() == {"status": "examined", "passed": True, "findings": []}


def test_successor_without_the_agent_asking_is_rejected(case: Case) -> None:
    _to_successor(case, ask_turn=None)
    findings = case.check()["findings"]
    assert "b7_revised_release_missing" in findings
    assert "b7_final_query_run_mismatch" in findings


def test_successor_prepared_before_any_operator_reply_is_rejected(case: Case) -> None:
    # The agent asked on turn 17 but prepared the new workflow on that same
    # turn, so no operator message could have authorized it.
    _to_successor(case, prepare_turn=17)
    assert "b7_revised_release_missing" in case.check()["findings"]


def test_successor_without_supervisor_prepare_evidence_is_rejected(case: Case) -> None:
    _to_successor(case)
    case.docs["tool-calls"]["calls"] = [
        call for call in case.docs["tool-calls"]["calls"] if call.get("tool") != "prepare_workflow"
    ]
    assert "b7_revised_release_missing" in case.check()["findings"]


def test_successor_must_carry_the_revised_ruling(case: Case) -> None:
    _to_successor(case)
    _change_ruling(case, 2, "same_month_classification", "Show same-month down and up movements separately on a gross basis.")
    assert "b7_revised_release_missing" in case.check()["findings"]


def test_successor_authorization_cannot_predate_the_reversal(case: Case) -> None:
    # An ask before E8 (turn 17) is not an ask about the reversal.
    _to_successor(case, ask_turn=None)
    next(row for row in case.observations["turns"] if row["turn"] == 8)["agent_message"] = _ASK
    assert "b7_revised_release_missing" in case.check()["findings"]


def _e8_card_scenario(case: Case, *, linked: bool) -> None:
    turns = case.observations["turns"]
    # Drop the separately solicited revised-answer exchange entirely.
    for row in turns:
        if row.get("operator_matched_decision_id") == "same_month_classification_revised":
            row.pop("operator_matched_decision_id")
            row.pop("operator_matched_rule_id")
    next(row for row in turns if row["turn"] == 19)["operator_message"] = "Please continue."
    e8 = next(row for row in turns if row["turn"] == 17)
    e8["operator_delivered_decision_id"] = "same_month_classification_revised"
    card = SimpleNamespace(
        card_id="B7-E8", content="I am changing the same-month decision.",
        delivers_decision="same_month_classification_revised" if linked else None,
    )
    case.scenario.events = SimpleNamespace(cards=(card,))


def test_e8_card_that_states_the_ruling_delivers_the_revised_decision(case: Case) -> None:
    _e8_card_scenario(case, linked=True)
    assert case.check() == {"status": "examined", "passed": True, "findings": []}


def test_e8_card_without_the_link_does_not_deliver_the_decision(case: Case) -> None:
    _e8_card_scenario(case, linked=False)
    assert "b7_decision_exchange_missing" in case.check()["findings"]


def test_e8_link_needs_the_engine_to_have_recorded_the_delivery(case: Case) -> None:
    _e8_card_scenario(case, linked=True)
    next(row for row in case.observations["turns"] if row["turn"] == 17).pop("operator_delivered_decision_id")
    assert "b7_decision_exchange_missing" in case.check()["findings"]
