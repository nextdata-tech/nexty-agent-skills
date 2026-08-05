"""The build record is what makes "healed with concessions" checkable.

Three things are pinned here, because all three are claims the design makes that
would otherwise rest on prose:

* the golden record validates, and every field the schema requires is present;
* INVARIANT-D2 — a heal that moved the spec hash edited the IR to make the build
  pass, and the record writer rejects it;
* the §5.1 state machine as a truth table, including the two states that are
  easy to get wrong: the false accusation (a correctly blocked-and-written-back
  run must NOT read as a spec edit) and `environment_suspect` (reachable only on
  supervisor-authored evidence).
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "src" / "nxd-run-job-loop" / "scripts"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import dp_diagnostics as dpd  # noqa: E402

GOLDEN = FIXTURES / "golden-build-record.json"
GOLDEN_LOCK = FIXTURES / "golden-dp-spec.lock.json"


@pytest.fixture
def record() -> dict:
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


@pytest.fixture
def lock() -> dict:
    return json.loads(GOLDEN_LOCK.read_text(encoding="utf-8"))


def _fail_stage(record: dict, stage: str, code: str, **diag_kwargs) -> dict:
    diag = dpd.diagnostic(code, message="something went wrong", stage=stage, **diag_kwargs)
    record["stages"][stage]["diagnostics"].append(diag.to_dict())
    record["stages"][stage]["status"] = "failed"
    return record


# --- the golden record ------------------------------------------------------

def test_golden_record_validates(record):
    assert dpd.validate_build_record(record) == []


def test_golden_record_matches_the_published_schema(record):
    jsonschema = pytest.importorskip(
        "jsonschema", reason="stdlib-only repo; validate_build_record is the enforcement"
    )
    schema = copy.deepcopy(dpd.BUILD_RECORD_SCHEMA)
    resolver = jsonschema.RefResolver.from_schema(
        schema, store={dpd.DIAGNOSTIC_SCHEMA_ID: dpd.DIAGNOSTIC_SCHEMA}
    )
    jsonschema.validate(record, schema, resolver=resolver)


def test_every_stage_key_is_always_present(record):
    assert list(record["stages"]) == list(dpd.STAGES)


def test_phase_b_and_published_row_counts_stay_separate(record):
    """One is a dry run against a temporary database; the other is what shipped."""
    evidence = record["evidence"]
    assert "phase_b_row_counts" in evidence and "published_row_counts" in evidence
    assert evidence["phase_b_row_counts"]["origin"] == "agent_observed"
    assert evidence["published_row_counts"]["origin"] == "supervisor_reported"
    assert evidence["published_row_counts"]["source"].startswith("verified.json:")


def test_narrative_declares_itself_llm_authored(record):
    assert record["narrative"]["origin"] == "llm_authored"
    record["narrative"]["origin"] = "tool_computed"
    assert dpd.validate_build_record(record)


def test_readback_is_data_not_prose(record):
    uniform = [d for d in record["readback"]["distribution"] if d["uniform"]]
    assert uniform, "the read-back must record the uniform column, not just print it"
    assert uniform[0]["column"] == "gate_g1"


def test_skipped_is_only_legal_for_publish_and_answer(record):
    assert dpd.SKIPPABLE_STAGES == ("s7_publish", "s8_answer")
    record["stages"]["s6_run"]["status"] = "skipped"
    assert any("skipped" in p for p in dpd.validate_build_record(record))


def test_a_concession_is_never_forbidden(record):
    record["concessions"][0]["class"] = "forbidden"
    problems = dpd.validate_build_record(record)
    assert any("discouraged" in p for p in problems), problems


# --- bounded adversarial review --------------------------------------------

def _review_round(**overrides) -> dict:
    base = {
        "status": "complete",
        "started_at_unix_ms": 1769904020000,
        "ended_at_unix_ms": 1769904025000,
        "budget_ms": 120000,
        "findings": [
            {
                "id": "R1",
                "claim": "The grain does not answer the requested cohort question.",
                "evidence": ["closure:models.py:42", "request:question 2"],
                "classification": "behavior_affecting",
                "proposed_effect": "Change the cohort grain before materialization.",
                "applied_files": [],
                "state": "not_applied",
            }
        ],
        "adjudications": [
            {
                "finding_id": "R1",
                "disposition": "rejected",
                "citation": "closure:models.py:42",
            }
        ],
        "user_decision": None,
    }
    base.update(overrides)
    return base


def test_review_round_adjudicates_every_finding(record):
    record["review_rounds"] = [_review_round(adjudications=[])]
    problems = dpd.validate_build_record(record)
    assert any("without an adjudication" in p for p in problems), problems


def test_rejected_review_finding_requires_a_citation(record):
    review = _review_round()
    review["adjudications"][0]["citation"] = None
    record["review_rounds"] = [review]
    problems = dpd.validate_build_record(record)
    assert any("rejected findings require a citation" in p for p in problems), problems


def test_review_needing_user_blocks_materialization(record, lock):
    review = _review_round(status="needs_user")
    review["findings"][0]["state"] = "needs_user"
    review["adjudications"][0]["disposition"] = "accepted"
    review["adjudications"][0]["citation"] = None
    record["review_rounds"] = [review]
    state = dpd.materialization_state(record, lock)
    assert state["materialized"] is False
    assert state["state"] == "needs_user"
    assert any("review round" in reason for reason in state["why"]), state


def test_user_decision_cannot_be_fabricated_while_review_needs_user(record):
    review = _review_round(
        status="needs_user",
        user_decision={
            "approved_at_unix_ms": 1769904026000,
            "citation": "user:approval message",
            "approved_finding_ids": ["R1"],
        },
    )
    review["findings"][0]["state"] = "needs_user"
    review["adjudications"][0]["disposition"] = "accepted"
    review["adjudications"][0]["citation"] = None
    record["review_rounds"] = [review]
    problems = dpd.validate_build_record(record)
    assert any("only allowed for a complete review" in p for p in problems)


def test_behavior_affecting_review_change_requires_named_user_approval(record):
    review = _review_round()
    review["findings"][0].update(
        state="applied",
        applied_files=["transform/main.py"],
    )
    record["review_rounds"] = [review]
    problems = dpd.validate_build_record(record)
    assert any("require explicit user approval" in p for p in problems), problems


def test_named_user_approval_allows_the_corresponding_behavior_change(record):
    review = _review_round(
        user_decision={
            "approved_at_unix_ms": 1769904026000,
            "citation": "user:approve R1",
            "approved_finding_ids": ["R1"],
        }
    )
    review["findings"][0].update(
        state="applied",
        applied_files=["transform/main.py"],
    )
    record["review_rounds"] = [review]
    assert dpd.validate_build_record(record) == []


def test_structural_note_can_record_an_evidenced_mechanical_fix(record):
    review = _review_round()
    review["findings"][0].update(
        classification="structural_note",
        proposed_effect="Correct a typo without changing behavior.",
        state="applied",
        applied_files=["transform/main.py"],
    )
    record["review_rounds"] = [review]
    assert dpd.validate_build_record(record) == []


def test_timed_out_review_can_preserve_partial_results_at_the_deadline(record):
    review = _review_round(
        status="timed_out",
        ended_at_unix_ms=1769904140000,
    )
    record["review_rounds"] = [review]
    assert dpd.validate_build_record(record) == []


def test_timed_out_review_may_include_cancellation_overhead(record):
    review = _review_round(
        status="timed_out",
        ended_at_unix_ms=1769904140001,
    )
    record["review_rounds"] = [review]
    assert dpd.validate_build_record(record) == []


def test_timed_out_review_cannot_end_before_its_budget(record):
    review = _review_round(
        status="timed_out",
        ended_at_unix_ms=1769904139999,
    )
    record["review_rounds"] = [review]
    problems = dpd.validate_build_record(record)
    assert any("timed_out review ended before budget_ms" in problem for problem in problems)


@pytest.mark.parametrize("status", ("complete", "needs_user"))
def test_non_timed_out_review_cannot_exceed_its_budget(record, status):
    review = _review_round(
        status=status,
        ended_at_unix_ms=1769904140001,
    )
    record["review_rounds"] = [review]
    problems = dpd.validate_build_record(record)
    assert any(f"{status} review exceeded budget_ms" in problem for problem in problems)


def test_timed_out_review_without_auditable_user_choice_blocks_materialization(record, lock):
    # A timed-out round is not a clean review. This shape was previously valid
    # and materialized because only status=needs_user was checked.
    review = _review_round(
        status="timed_out",
        ended_at_unix_ms=1769904140000,
    )
    record["review_rounds"] = [review]
    assert dpd.validate_build_record(record) == []
    state = dpd.materialization_state(record, lock)
    assert state["materialized"] is False
    assert state["state"] == "needs_user"
    assert any("timed_out review" in reason for reason in state["why"]), state


def test_auditable_user_choice_unblocks_a_timed_out_review(record, lock):
    # The review remains truthfully timed_out; an explicit empty approval list
    # records the user's decision to continue without a completed review.
    review = _review_round(
        status="timed_out",
        ended_at_unix_ms=1769904140000,
        user_decision={
            "approved_at_unix_ms": 1769904140000,
            "citation": "user:continue without completed review",
            "approved_finding_ids": [],
        },
    )
    record["review_rounds"] = [review]
    assert dpd.validate_build_record(record) == []
    assert dpd.materialization_state(record, lock)["materialized"] is True


def test_accepted_behavior_finding_without_user_decision_blocks_materialization(record, lock):
    # An accepted logical finding left not_applied is still a pending choice;
    # it must not read as materialized simply because review status is complete.
    review = _review_round()
    review["adjudications"][0].update(disposition="accepted", citation="closure:models.py:42")
    record["review_rounds"] = [review]
    assert dpd.validate_build_record(record) == []
    state = dpd.materialization_state(record, lock)
    assert state["materialized"] is False
    assert state["state"] == "needs_user"
    assert any("accepted behavior-affecting" in reason for reason in state["why"]), state


def test_auditable_user_decision_unblocks_accepted_behavior_finding(record, lock):
    review = _review_round(
        user_decision={
            "approved_at_unix_ms": 1769904026000,
            "citation": "user:decline R1 and continue",
            "approved_finding_ids": [],
        }
    )
    review["adjudications"][0].update(disposition="accepted", citation="closure:models.py:42")
    record["review_rounds"] = [review]
    assert dpd.validate_build_record(record) == []
    assert dpd.materialization_state(record, lock)["materialized"] is True


# --- INVARIANT-D2 -----------------------------------------------------------

def _attempt(**overrides) -> dict:
    base = {
        "kind": "heal",
        "stage": "s2_transform",
        "started_at_unix_ms": 1769904030000,
        "origin": "agent_observed",
        "diagnosis": {
            "code": "runtime.assert_failed",
            "path": "closure:transform/main.py:214",
            "summary": "uniqueness assert fired",
        },
        "changed": [{"file": "transform/main.py", "what": "deduplicate before the join"}],
        "spec_hash_before": "sha256:" + "a" * 64,
        "spec_hash_after": "sha256:" + "a" * 64,
        "exit": "healed",
    }
    base.update(overrides)
    return base


@pytest.mark.parametrize("kind", ["heal", "retry", "remap"])
def test_a_hash_moving_attempt_is_rejected(record, kind):
    problems = dpd.append_attempt(
        record, _attempt(kind=kind, spec_hash_after="sha256:" + "b" * 64)
    )
    assert any("INVARIANT-D2" in p for p in problems), problems
    appended = record["attempts"][-1]
    assert appended["exit"] == "blocked", "a rejected attempt is recorded, not dropped"
    assert record["blockers"][-1]["code"] == "blocker.spec_edit_required"
    assert record["blockers"][-1]["disposition"] == "blocked"
    assert not dpd.materialized(record)


def test_regenerate_is_the_one_kind_allowed_to_move_the_hash(record):
    problems = dpd.append_attempt(
        record,
        _attempt(kind="regenerate", spec_hash_after="sha256:" + "b" * 64, exit="healed"),
    )
    assert problems == []
    assert record["attempts"][-1]["exit"] == "healed"


# --- the §2.5 ORDERING RULE, both directions --------------------------------

def test_a_blocked_and_written_back_run_is_not_accused_of_editing_the_ir(record):
    """The false-accusation case.

    The attempt that discovered the blocker is appended FIRST with equal hashes
    — truthfully, because the attempt itself never edited the IR — and only then
    is the live spec edited. That divergence is `plan_moved`, never
    `blocker.spec_edit_required`.
    """
    problems = dpd.append_attempt(record, _attempt(exit="blocked"))
    assert problems == []
    assert dpd.append_blocker(
        record,
        {
            "code": "blocker.open_question",
            "open_question_id": "fx_rates",
            "question": "Which EUR to USD rate, over what date range?",
            "blocks": ["total_opex"],
            "disposition": "blocked",
            "stage": "s6_run",
            "path": "v2:open_questions[fx_rates]",
            "written_back": True,
        },
    ) == []
    assert dpd.validate_build_record(record) == []
    assert not any(
        b["code"] == "blocker.spec_edit_required" for b in record["blockers"]
    )
    # And the resulting live-hash divergence surfaces only as the blocker.
    state = dpd.materialization_state(record, None, "sha256:" + "c" * 64)
    assert state["state"] == "needs_user"
    assert any("moved away" in w for w in state["why"]), state["why"]


def test_the_same_attempt_with_differing_hashes_is_rejected(record):
    problems = dpd.append_attempt(record, _attempt(exit="blocked", spec_hash_after="sha256:" + "d" * 64))
    assert any("INVARIANT-D2" in p for p in problems), problems


# --- the §5.1 state machine -------------------------------------------------

def test_the_golden_record_is_materialized(record, lock):
    state = dpd.materialization_state(record, lock)
    assert state == {"materialized": True, "state": "materialized", "why": []}


def test_needs_user_outranks_plan_moved(record, lock):
    """Reporting `plan_moved` first would tell the agent to regenerate against a
    spec that still carries the unanswered question that stopped the build."""
    dpd.append_blocker(
        record,
        {
            "code": "blocker.open_question",
            "question": "Which rate?",
            "disposition": "blocked",
            "stage": "s6_run",
        },
    )
    state = dpd.materialization_state(record, lock, "sha256:" + "e" * 64)
    assert state["state"] == "needs_user"
    assert len([w for w in state["why"] if "moved away" in w]) == 1


def test_plan_moved(record, lock):
    state = dpd.materialization_state(record, lock, "sha256:" + "e" * 64)
    assert state == {
        "materialized": False,
        "state": "plan_moved",
        "why": ["the live spec's canonical hash has moved away from the lock"],
    }


def test_code_wrong_when_an_offline_stage_failed(record, lock):
    _fail_stage(record, "s2_transform", "runtime.assert_failed")
    state = dpd.materialization_state(record, lock)
    assert state["state"] == "code_wrong"
    assert any("never environmental" in w for w in state["why"])


def test_unsettled_when_a_late_failure_has_no_supervisor_evidence(record, lock):
    """Fail closed. Misclassifying a real bug as 'the environment' is what ships
    a broken data product flagged green."""
    _fail_stage(record, "s4_pin", "pin.build_failed", origin="agent_observed")
    assert dpd.materialization_state(record, lock)["state"] == "unsettled"


def test_unsettled_when_the_environment_claim_is_unbacked(record, lock):
    _fail_stage(record, "s6_run", "env.connection_refused", origin="agent_observed")
    assert dpd.materialization_state(record, lock)["state"] == "unsettled"


def test_environment_suspect_is_reachable_today(record, lock):
    """A connection-refused body returned verbatim by the supervisor satisfies
    the relay criterion, so the environment path is live with no supervisor
    change."""
    _fail_stage(
        record,
        "s6_run",
        "env.connection_refused",
        origin="supervisor_reported",
        path="tool:build_data_product.error",
        evidence={"supervisor_detail": "ConnectionRefusedError: [Errno 111]"},
    )
    assert dpd.materialization_state(record, lock)["state"] == "environment_suspect"


def test_a_silent_failing_stage_cannot_ride_on_another_stages_evidence(record, lock):
    """REGRESSION. A real supervisor failing at pin attaches NO per-stage
    diagnostics. Flattening diagnostics across stages before the relay check let
    that empty stage pass vacuously on a LATER stage's supervisor payload, so a
    pure code bug reported as `environment_suspect` and the agent was told to
    retry an unbroken environment forever. Silence is not evidence: every
    failing stage must contribute its own.
    """
    record["stages"]["s4_pin"]["status"] = "failed"
    record["stages"]["s4_pin"]["diagnostics"] = []
    _fail_stage(
        record,
        "s6_run",
        "env.connection_refused",
        origin="supervisor_reported",
        path="tool:build_data_product.error",
        evidence={"supervisor_detail": "ConnectionRefusedError: [Errno 111]"},
    )
    state = dpd.materialization_state(record, lock)
    assert state["state"] == "unsettled"
    assert "s4_pin" in " ".join(state["why"])


def test_every_failing_stage_backed_still_reaches_environment_suspect(record, lock):
    """The fix must not close the environment path when the evidence IS there:
    two failing stages, each carrying its own supervisor-authored diagnostic."""
    for stage in ("s5_serve", "s6_run"):
        _fail_stage(
            record,
            stage,
            "env.connection_refused",
            origin="supervisor_reported",
            path="tool:build_data_product.error",
            evidence={"supervisor_detail": "ConnectionRefusedError: [Errno 111]"},
        )
    assert dpd.materialization_state(record, lock)["state"] == "environment_suspect"


def test_undisclosed_concession_is_not_materialized(record, lock):
    """The worst state in the design, because it reads as materialized."""
    record["concessions"][0]["disclosed"] = False
    state = dpd.materialization_state(record, lock)
    assert state["state"] == "undisclosed_concession"
    assert not dpd.materialized(record, lock)


def test_awaiting_answer(record, lock):
    _fail_stage(record, "s8_answer", "semantic.query_error")
    state = dpd.materialization_state(record, lock)
    assert state["state"] == "awaiting_answer"


def test_in_progress(record, lock):
    record["stages"]["s6_run"]["status"] = "not_reached"
    state = dpd.materialization_state(record, lock)
    assert state["state"] == "in_progress"
    assert any("not reached" in w for w in state["why"])


def test_source_staleness_never_participates(record, lock):
    """A correctly built product must not read as broken because its input is a
    day old."""
    record["evidence"]["source_state"]["watermark"] = "1999-01-01T00:00:00Z"
    assert dpd.materialized(record, lock)


def test_compiled_from_mismatch_is_code_wrong(record, lock):
    record["compiled_from"] = "sha256:" + "f" * 64
    state = dpd.materialization_state(record, lock)
    assert state["state"] == "code_wrong"
    assert not dpd.materialized(record, lock)


# --- caps -------------------------------------------------------------------

def test_caps_are_counted_from_attempts_not_estimated(record):
    for _ in range(3):
        dpd.append_attempt(record, _attempt(kind="regenerate", spec_hash_after="sha256:" + "a" * 64))
    for _ in range(2):
        dpd.append_attempt(record, _attempt(kind="remap", question="q1", exit="healed"))
    dpd.append_attempt(record, _attempt(kind="retry", exit="retry_environmental"))
    caps = record["caps"]
    assert caps["regenerates_used"] == 3
    assert caps["remaps_used"] == {"q1": 2}
    assert caps["retries_used"] == 1
    assert "regenerate_total" in caps["exhausted"]
    assert "remap_per_question" in caps["exhausted"]
    assert "retry_environmental" not in caps["exhausted"]


def test_environmental_retries_have_a_bound_of_their_own(record):
    """An environmental retry consumes neither a remap nor a regenerate, so
    without a bound of its own it could retry forever and never reach the user."""
    assert record["caps"]["retry_environmental_total"] == 3
    for _ in range(3):
        dpd.append_attempt(record, _attempt(kind="retry", exit="retry_environmental"))
    assert "retry_environmental" in record["caps"]["exhausted"]


# --- queries ----------------------------------------------------------------

def test_query_routes_by_owner_not_severity(record):
    dpd.append_blocker(
        record,
        {"code": "blocker.open_question", "question": "Which rate?", "disposition": "blocked"},
    )
    result = dpd.query_record(record, unresolved=True)
    assert result["blockers"], "an unresolved query must surface the user's queue"
    assert result["ok"] is False
