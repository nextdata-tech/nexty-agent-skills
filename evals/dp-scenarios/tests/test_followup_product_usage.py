"""B8 release, decision, and query evidence must agree (offline unit tests).

This package cannot run live yet (see scenarios/product-usage/README.md and
scenario.live_blocked_reason: nxd U1/U2 are still outstanding), so these
tests exercise ``followups.product_usage.check`` the same way
``test_followup_mrr_waterfall.py`` exercises B7: against synthetic
runner-owned evidence, never a live session.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from dp_scenarios.followups import FollowUpContext
from dp_scenarios.followups.product_usage import check
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


GOLD_DIR = Path(__file__).parents[1] / "scenarios/product-usage/gold"
ANSWER = json.loads((GOLD_DIR / "product_usage_answer.json").read_text(encoding="utf-8"))
ADOPTION = json.loads((GOLD_DIR / "product_usage_feature_adoption.json").read_text(encoding="utf-8"))
LOOKBACK_ANSWER = (
    "Reread at least the prior three calendar days, deduplicate by event_id "
    "against already landed keys, and retain older landed history rather "
    "than replacing it."
)
MODELS_PY = b"class WeeklyActiveAccounts:\n    week_start: str\n    active_accounts: int\n"


def _sha(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _approved_capture() -> dict[str, bytes]:
    proposal = {
        "proposal": {
            "decisions": [
                {
                    "id": "usage_events_lookback",
                    "target": "usage_events",
                    "ruling": LOOKBACK_ANSWER,
                    "status": "locked",
                },
            ]
        }
    }
    approved = b"# Approved B8 usage bridge\n"
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
        "models.py": MODELS_PY,
    }


class Case:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.files = {1: _approved_capture(), 2: _approved_capture()}
        self.docs: dict[str, dict[str, object]] = {
            "publication-history": {"schema": PUBLICATION_SCHEMA, "releases": []},
            "run-records": {"schema": RUN_RECORDS_SCHEMA, "runs": []},
            "run-failures": {"schema": RUN_FAILURES_SCHEMA, "failures": []},
            "tool-calls": {"schema": TOOL_CALLS_SCHEMA, "calls": []},
            "query-history": {
                "schema": QUERY_HISTORY_SCHEMA,
                "queries": [
                    {"turn": 25, "index": 0, "run_id": "run-2", "workflow_id": "product-usage", "rows": ANSWER},
                    {"turn": 25, "index": 1, "run_id": "run-2", "workflow_id": "product-usage", "rows": ADOPTION},
                ],
            },
            "supervisor-captures": {"schema": CAPTURES_SCHEMA, "captures": []},
            "definition-export": {"schema": DEFINITION_EXPORT_SCHEMA, "definitions": []},
        }
        row_counts = (
            {"main.usage_events": "8400"},
            {
                "main.usage_events": "9030",
                "main.weekly_active_accounts": "3",
                "main.weekly_feature_adoption": "9",
                "main.usage_export_status": "1",
            },
        )
        for index, published_turn in ((1, 17), (2, 24)):
            run_id = f"run-{index}"
            definition_id = f"sha256-v1:{index:064x}"
            capture_sha = f"sha256:{index:064x}"
            release = {
                "run_id": run_id,
                "workflow_id": "product-usage",
                "definition_id": definition_id,
                "artifact_id": f"artifact-{index}",
                "publish_sequence": str(index),
                "verification_outcome": "passed",
                "row_counts": dict(row_counts[index - 1]),
                "turn": published_turn - 3,
            }
            self.docs["publication-history"]["releases"].append(release)
            self.docs["run-records"]["runs"].append(
                {
                    "run_id": run_id,
                    "workflow_id": "product-usage",
                    "definition_id": definition_id,
                    "artifact_id": f"artifact-{index}",
                    "publish_sequence": str(index),
                    "capture_sha256": capture_sha,
                    "status": "Published",
                    "status_history": [
                        {"turn": published_turn - 3, "status": "Running"},
                        {"turn": published_turn, "status": "Published"},
                    ],
                }
            )
            self.docs["definition-export"]["definitions"].append(
                {
                    "definition_id": definition_id,
                    "run_ids": [run_id],
                    "workflow_ids": ["product-usage"],
                    "present": True,
                    "inventory_valid": True,
                    "output_promises": [],
                }
            )
            self.docs["supervisor-captures"]["captures"].append(
                {"capture_sha256": capture_sha, "run_ids": [run_id], "workflow_ids": ["product-usage"], "files": []}
            )
        self.observations: dict[str, object] = {
            "turns": [
                {
                    "turn": 18,
                    "fired_event_ids": ["B8-late-arrival-refresh"],
                    "operator_message": "I'm back the next morning; did it finish, and can you update the numbers?",
                },
                {
                    "turn": 19,
                    "fired_event_ids": [],
                    "operator_message": "Please continue.",
                    "operator_matched_rule_id": "decision.answer.usage_events_lookback",
                    "operator_matched_decision_id": "usage_events_lookback",
                    "operator_matched_reply": LOOKBACK_ANSWER,
                    "operator_matched": True,
                },
                {"turn": 20, "fired_event_ids": [], "operator_message": LOOKBACK_ANSWER},
            ]
        }
        self.scenario = SimpleNamespace(
            answer_sheet=SimpleNamespace(
                decision_answers={"usage_events_lookback": SimpleNamespace(answer=LOOKBACK_ANSWER)}
            ),
            raw_gold=lambda key: {"answer": ANSWER, "feature_adoption": ADOPTION}[key],
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
        return dict(
            check(
                self.scenario,
                {},
                {},
                FollowUpContext(
                    operator_observations=self.observations,
                    supervisor_history=load_supervisor_history_view(self.root),
                ),
            )
        )


@pytest.fixture
def case(tmp_path: Path) -> Case:
    return Case(tmp_path / "artifacts")


def test_clean_refresh_never_passes_because_H1_filtered_refresh_proof_is_out_of_scope(case: Case) -> None:
    """The one finding a live H1 unblock would clear; every mutation test below adds more on top."""

    result = case.check()
    assert result["status"] == "examined"
    assert result["findings"] == ["b8_filtered_refresh_unproven"]
    assert result["passed"] is False


def test_runner_history_absent_is_ungraded(tmp_path: Path) -> None:
    case = Case(tmp_path / "absent")
    view = load_supervisor_history_view(case.root)
    result = check(case.scenario, {}, {}, FollowUpContext(operator_observations=case.observations, supervisor_history=view))
    assert result["status"] == "ungraded"


def test_an_unasked_decision_is_not_evidence(case: Case) -> None:
    """The decision must actually be delivered on the operator's own turns, not merely locked in the blueprint."""

    case.observations["turns"][2]["operator_message"] = "Please continue."
    assert "b8_lookback_decision_unobserved" in case.check()["findings"]


def test_a_new_workflow_refresh_is_not_the_same_workflow_being_rebuilt(case: Case) -> None:
    case.docs["publication-history"]["releases"][1]["workflow_id"] = "product-usage-v2"
    case.docs["run-records"]["runs"][1]["workflow_id"] = "product-usage-v2"
    case.docs["supervisor-captures"]["captures"][1]["workflow_ids"] = ["product-usage-v2"]
    case.docs["definition-export"]["definitions"][1]["workflow_ids"] = ["product-usage-v2"]
    case.docs["query-history"]["queries"][0]["workflow_id"] = "product-usage-v2"
    case.docs["query-history"]["queries"][1]["workflow_id"] = "product-usage-v2"
    assert "b8_release_identity_ambiguous" in case.check()["findings"]


def test_high_watermark_loss_undercounts_landed_events(case: Case) -> None:
    """A naive high-watermark reread lands 9,000, not the correct union of 9,030."""

    case.docs["publication-history"]["releases"][1]["row_counts"]["main.usage_events"] = "9000"
    assert "b8_late_rows_missing_or_duplicated" in case.check()["findings"]


def test_full_replace_of_the_landed_set_drops_the_first_served_day(case: Case) -> None:
    """Replacing from v2 instead of unioning with v1 lands 8,430, not 9,030."""

    case.docs["publication-history"]["releases"][1]["row_counts"]["main.usage_events"] = "8430"
    assert "b8_late_rows_missing_or_duplicated" in case.check()["findings"]


def test_overlap_duplicates_from_an_undeduplicated_reread_overcount(case: Case) -> None:
    """Rereading the lookback window without key dedup double-counts overlap rows."""

    case.docs["publication-history"]["releases"][1]["row_counts"]["main.usage_events"] = "9420"
    assert "b8_late_rows_missing_or_duplicated" in case.check()["findings"]


def test_actor_column_landing_fails_even_with_correct_counts(case: Case) -> None:
    case.files[2]["models.py"] = b"class WeeklyActiveAccounts:\n    actor_email: str\n"
    assert "b8_person_field_landed" in case.check()["findings"]


def test_display_name_field_landing_also_fails(case: Case) -> None:
    case.files[1]["models.py"] = b"class UsageEvents:\n    display_name: str\n"
    assert "b8_person_field_landed" in case.check()["findings"]


def test_quietly_published_short_day_is_visible_as_a_freshness_mismatch(case: Case) -> None:
    """A short day silently folded into the export-status model row count must not pass unnoticed."""

    case.docs["publication-history"]["releases"][1]["row_counts"]["main.usage_export_status"] = "0"
    assert "b8_freshness_clock_invalid" in case.check()["findings"]


def test_final_queries_must_come_from_the_refreshed_run_after_publication(case: Case) -> None:
    case.docs["query-history"]["queries"][0]["turn"] = 21
    assert any(
        finding in case.check()["findings"]
        for finding in ("b8_late_rows_missing_or_duplicated", "b8_release_identity_ambiguous", "b8_feature_adoption_rows_differ")
    )


def test_feature_adoption_rows_must_match_gold_exactly(case: Case) -> None:
    mutated = [dict(row) for row in ADOPTION]
    mutated[0]["active_accounts"] += 1
    case.docs["query-history"]["queries"][1]["rows"] = mutated
    assert "b8_feature_adoption_rows_differ" in case.check()["findings"]


def test_weekly_answer_rows_must_match_gold_exactly(case: Case) -> None:
    mutated = [dict(row) for row in ANSWER]
    mutated[0]["active_accounts"] += 1
    case.docs["query-history"]["queries"][0]["rows"] = mutated
    assert "b8_late_rows_missing_or_duplicated" in case.check()["findings"]


def test_lookback_ruling_must_be_retain_not_replace(case: Case) -> None:
    proposal = json.loads(case.files[2]["dp-blueprint.proposal.approved.json"])
    proposal["proposal"]["decisions"][0]["ruling"] = (
        "Reread three calendar days and replace the whole landed usage_events table."
    )
    content = json.dumps(proposal, sort_keys=True).encode()
    case.files[2]["dp-blueprint.proposal.approved.json"] = content
    lock = json.loads(case.files[2]["dp-blueprint.lock.json"])
    lock["proposal_snapshot_sha256"] = _sha(content)
    case.files[2]["dp-blueprint.lock.json"] = json.dumps(lock).encode()
    assert "b8_lookback_decision_unobserved" in case.check()["findings"]
