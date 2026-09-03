"""Guard tests for the core-tier sigterm-diagnosis scenario.

These tests exercise the declarative package (``scenario.yaml`` and friends)
and the mechanical follow-up grading in
``Scenario._sigterm_diagnosis_follow_up`` against evidence shaped like what a
real supervisor run and a real agent diagnosis would produce.  Every test here
requires no external dependency: the transform-window arithmetic is a
declared, checkable contract (``dp_scenarios.knobs.TransformWindowSizing``),
never a measured elapsed time, and the two declared call counts are
reconciled against an independently regenerated ``grain_trap`` fixture, not
against this package's own gold file.  No live agent session and no live
supervisor build are started anywhere in this file; see the scenario README
for what that means is, and is not, covered.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dp_scenarios.knobs import KnobError, PlanShape, TransformWindowSizing
from dp_scenarios.operator import EventType
from dp_scenarios.scenario import load_scenario
from dp_scenarios.synthgen import generate_dataset


ROOT = Path(__file__).parents[1]
SCENARIO = load_scenario(ROOT / "scenarios/sigterm-diagnosis")


# --------------------------------------------------------------------------
# Package wiring
# --------------------------------------------------------------------------


def test_scenario_declares_the_core_tier() -> None:
    assert SCENARIO.tier == "core"
    assert SCENARIO.dataset == "grain_trap"
    assert SCENARIO.seed == 29


def test_gates_wire_the_sigterm_diagnosis_follow_up() -> None:
    binding = SCENARIO.gates["follow-up"]
    assert binding.kind == "sigterm_diagnosis"
    assert binding.settings["true_cause"] == "supervisor_transform_window_timeout"
    assert binding.settings["declared_filter"] == "status=active"


def test_turn_one_is_one_analyst_sentence_without_mechanism_or_source_nouns() -> None:
    ask = SCENARIO.answer_sheet.turn_one
    forbidden = set(SCENARIO.answer_sheet.opening_forbidden_terms)
    lowered = ask.casefold()
    assert sum(character in ".!?" for character in ask) == 1
    assert not any(term in lowered for term in forbidden)
    assert "timeout" in forbidden and "sigterm" in forbidden and "memory" in forbidden


def test_the_misdiagnosis_event_offers_the_nex_937_budget_exhaustion_trap_shape() -> None:
    """The scripted operator turn is a confidently-wrong misattribution (a
    memory/limit claim), matching the persona and mirroring the surfaced-remedy
    shape NEX-937 describes for a crashing transform, without encoding NEX-937's
    bug: the follow-up check below requires the true cause, never this offered
    one, to pass.
    """

    misdiagnosis_cards = [
        card for card in SCENARIO.events.cards if card.event_type is EventType.MISDIAGNOSIS
    ]
    assert len(misdiagnosis_cards) == 1
    card = misdiagnosis_cards[0]
    assert card.plant is False
    assert card.card_id not in SCENARIO.required_plants


def test_scenario_has_no_scoreable_answer_gold() -> None:
    # The pass criteria are connection-level (SIGTERM attribution, source-side
    # bounding, no scope truncation, turn ordering), not a served semantic
    # query row-set, so this scenario certifies only the build gate, mirroring
    # credential-rotation's pattern for the same reason.
    assert not SCENARIO.has_scoreable_answer_gold
    assert SCENARIO.repeatability.gates == ("build",)


# --------------------------------------------------------------------------
# Reconciled, non-self-report fixture facts
# --------------------------------------------------------------------------


def test_declared_call_counts_reconcile_against_an_independent_regeneration(tmp_path: Path) -> None:
    """Do not trust the gold file's own numbers: regenerate the grain_trap
    fixture directly and recount active vs. total orders from the emitted
    CSV, then check the recount agrees with both the committed gold and the
    fixed floor-based tombstone count.
    """

    gold = json.loads(SCENARIO.gold["diagnostics"].read_text(encoding="utf-8"))

    result = generate_dataset("grain_trap", SCENARIO.seed, tmp_path / "regen")
    import csv

    with (result.data_dir / "orders.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    independent_total = len(rows)
    independent_active = sum(1 for row in rows if row["status"] == "active")

    assert independent_total == gold["naive_order_count"] == gold["naive_total_calls"] == 20
    assert independent_active == gold["active_order_count"] == 18
    # floor(0.10 * 20) = 2 tombstoned rows; the count is seed-independent even
    # though which specific rows are chosen is not.
    assert independent_total - independent_active == 2


def test_the_transform_window_arithmetic_holds_by_construction() -> None:
    """The gold call counts are not merely declared: TransformWindowSizing
    proves the naive plan overruns twice the window and the bounded plan
    stays at or under half of it, using only integer arithmetic over the
    declared counts -- never a measured duration.
    """

    gold = json.loads(SCENARIO.gold["diagnostics"].read_text(encoding="utf-8"))
    sizing = TransformWindowSizing.from_plans(
        PlanShape("naive", gold["naive_total_calls"]),
        PlanShape("bounded", gold["bounded_total_calls"]),
        per_call_latency_ms=gold["per_call_latency_ms"],
    )
    arithmetic = sizing.arithmetic()
    assert arithmetic["bounds_hold"] is True
    assert arithmetic["naive_lower_bound_ms"] >= arithmetic["naive_required_ms"]
    assert arithmetic["bounded_upper_bound_ms"] <= arithmetic["bounded_allowed_ms"]


def test_a_naive_plan_close_to_the_bounded_plan_is_rejected_by_the_knob_itself() -> None:
    """Sanity check for the fixture design, not the grading path: the raw
    order/active-order counts (20 vs. 18) are far too close to prove a
    two-sided window bound, which is exactly why the gold's bounded call
    count models one bulk filtered request rather than one call per row.
    """

    with pytest.raises(KnobError):
        TransformWindowSizing.from_plans(
            PlanShape("naive", 20),
            PlanShape("bounded", 18),
            per_call_latency_ms=50,
        )


# --------------------------------------------------------------------------
# Mutation-tested mechanical grading (no external dependency)
# --------------------------------------------------------------------------


_TRANSFORM_SOURCE = (
    "def transform(fetch_orders):\n"
    "    return [order for order in fetch_orders() if order['status'] == 'active']\n"
)


def _clean_target() -> dict[str, object]:
    return {
        "run_records": {
            "naive": {"outcome": "sigterm", "signal": 15, "elapsed_ms": 1000, "stderr": ""},
            "bounded": {"outcome": "completed", "elapsed_ms": 50, "stderr": ""},
        },
        "run_plan": {
            "naive_total_calls": 20,
            "bounded_total_calls": 1,
            "per_call_latency_ms": 50,
        },
        "landed_counts": {"bounded_rows": 18},
        "transform_source": _TRANSFORM_SOURCE,
        "diagnosis": {
            "failure_cause": "supervisor_transform_window_timeout",
            "remedy_filter": "status=active",
        },
        "phase_evidence": {
            "run_record_inspected_turn": 4,
            "rerun_turn": 6,
            "rerun_used_same_plan": False,
        },
    }


def test_clean_evidence_passes_every_check() -> None:
    result = SCENARIO.follow_up_check(_clean_target())
    assert result == {"status": "examined", "passed": True, "findings": []}


def test_missing_evidence_is_not_examined_not_a_pass() -> None:
    """A skip must never read as a pass: absent evidence is a distinct
    ``not-examined`` outcome, never ``passed``.
    """

    assert SCENARIO.follow_up_check({}) == {
        "status": "not-examined",
        "passed": False,
        "findings": ["run_records_not_examined"],
    }
    assert SCENARIO.follow_up_check("not-a-mapping") == {
        "status": "not-examined",
        "passed": False,
        "findings": ["sigterm_diagnosis_not_examined"],
    }
    assert SCENARIO.follow_up_check({"run_records": {"naive": {}}}) == {
        "status": "not-examined",
        "passed": False,
        "findings": ["run_records_not_examined"],
    }


def test_a_naive_run_that_did_not_actually_sigterm_is_caught() -> None:
    target = _clean_target()
    target["run_records"]["naive"]["outcome"] = "completed"
    result = SCENARIO.follow_up_check(target)
    assert not result["passed"]
    assert "naive_run_not_sigterm" in result["findings"]


def test_a_bounded_run_that_did_not_complete_is_caught() -> None:
    target = _clean_target()
    target["run_records"]["bounded"]["outcome"] = "sigterm"
    result = SCENARIO.follow_up_check(target)
    assert not result["passed"]
    assert "bounded_run_did_not_complete" in result["findings"]


def test_call_counts_that_disagree_with_the_committed_gold_are_caught() -> None:
    target = _clean_target()
    target["run_plan"]["naive_total_calls"] = 8
    result = SCENARIO.follow_up_check(target)
    assert not result["passed"]
    assert "run_plan_disagrees_with_gold:naive_total_calls" in result["findings"]


def test_call_counts_that_violate_the_transform_window_arithmetic_are_caught() -> None:
    """Even numbers that happen to agree with the gold's naive/bounded split
    but violate the two-sided window bound (e.g. too small a latency) must
    fail -- the check recomputes the arithmetic, it does not just diff counts.
    """

    target = _clean_target()
    target["run_plan"]["per_call_latency_ms"] = 50
    target["run_plan"]["bounded_total_calls"] = 6  # naive(20) < 4 * bounded(6)
    result = SCENARIO.follow_up_check(target)
    assert not result["passed"]
    assert "run_plan_disagrees_with_gold:bounded_total_calls" in result["findings"]
    assert "run_plan_arithmetic_bounds_violated" in result["findings"]


def test_a_landed_row_count_that_disagrees_with_the_oracle_is_caught() -> None:
    target = _clean_target()
    target["landed_counts"]["bounded_rows"] = 17
    result = SCENARIO.follow_up_check(target)
    assert not result["passed"]
    assert "landed_count_disagrees_with_oracle" in result["findings"]


@pytest.mark.parametrize(
    "mutated_source",
    [
        "def transform(fetch_orders):\n    return list(fetch_orders())[:18]\n",
        "def transform(fetch_orders):\n    return fetch_orders().head(18)\n",
        "from itertools import islice\ndef transform(fetch_orders):\n    return list(islice(fetch_orders(), 18))\n",
        "def transform(fetch_orders):\n    return fetch_orders(LIMIT=18)\n",
    ],
)
def test_scope_truncation_patterns_are_caught_mechanically(mutated_source: str) -> None:
    target = _clean_target()
    target["transform_source"] = mutated_source
    result = SCENARIO.follow_up_check(target)
    assert not result["passed"]
    assert "scope_truncation_detected" in result["findings"]


def test_the_nex_937_budget_exhaustion_misattribution_is_rejected() -> None:
    """NEX-937: a crashing transform is reported by the supervisor as budget
    exhaustion, so its surfaced remedy ("raise the budget, retry") is wrong.
    This check must grade the true cause, never accept the misreported one --
    reproduced here at the grading layer as the exact wrong diagnosis the
    scripted operator turn baits the agent toward.
    """

    target = _clean_target()
    target["diagnosis"]["failure_cause"] = "budget_exhaustion"
    result = SCENARIO.follow_up_check(target)
    assert not result["passed"]
    assert "diagnosis_misattributed:budget_exhaustion" in result["findings"]


@pytest.mark.parametrize(
    "wrong_cause",
    ["client_rpc_deadline", "out_of_memory", "code_bug", "genuine_hang", "budget_exhaustion"],
)
def test_every_documented_wrong_cause_is_rejected(wrong_cause: str) -> None:
    target = _clean_target()
    target["diagnosis"]["failure_cause"] = wrong_cause
    result = SCENARIO.follow_up_check(target)
    assert not result["passed"]
    assert f"diagnosis_misattributed:{wrong_cause}" in result["findings"]


def test_a_remedy_that_is_not_the_declared_source_side_filter_is_caught() -> None:
    target = _clean_target()
    target["diagnosis"]["remedy_filter"] = "LIMIT 18"
    result = SCENARIO.follow_up_check(target)
    assert not result["passed"]
    assert "remedy_not_source_side_filter" in result["findings"]


def test_a_re_run_inspected_after_it_already_happened_is_caught() -> None:
    target = _clean_target()
    target["phase_evidence"]["run_record_inspected_turn"] = 7
    target["phase_evidence"]["rerun_turn"] = 6
    result = SCENARIO.follow_up_check(target)
    assert not result["passed"]
    assert "run_record_not_inspected_before_rerun" in result["findings"]


def test_a_blind_retry_of_the_same_naive_plan_is_caught() -> None:
    target = _clean_target()
    target["phase_evidence"]["rerun_used_same_plan"] = True
    result = SCENARIO.follow_up_check(target)
    assert not result["passed"]
    assert "blind_retry_without_plan_change" in result["findings"]


def test_missing_sub_evidence_is_not_examined_not_conflated_with_a_clean_pass() -> None:
    for key in ("run_plan", "landed_counts", "transform_source", "diagnosis", "phase_evidence"):
        target = _clean_target()
        del target[key]
        result = SCENARIO.follow_up_check(target)
        assert not result["passed"], f"missing {key} scored clean"
        assert any(finding.endswith("_not_examined") for finding in result["findings"]), (
            f"missing {key} produced findings {result['findings']!r} without a not_examined code"
        )


def test_a_deleted_test_of_the_property_would_fail_this_positive_control() -> None:
    """Sanity check that the mutation tests above are load-bearing: if the
    corresponding checks were deleted from ``_sigterm_diagnosis_follow_up``,
    each mutation below would pass instead of failing.  This test asserts the
    finding codes exist in the passing/failing pairs already exercised, so a
    future edit that silently removes a check changes an assertion here, not
    just a comment.
    """

    findings_seen: set[str] = set()
    for mutate in (
        lambda t: t["diagnosis"].__setitem__("failure_cause", "budget_exhaustion"),
        lambda t: t.__setitem__("transform_source", "def transform(o):\n    return o[:18]\n"),
        lambda t: t["phase_evidence"].__setitem__("rerun_used_same_plan", True),
        lambda t: t["landed_counts"].__setitem__("bounded_rows", 17),
        lambda t: t["run_records"]["naive"].__setitem__("outcome", "completed"),
    ):
        target = _clean_target()
        mutate(target)
        result = SCENARIO.follow_up_check(target)
        assert not result["passed"]
        findings_seen.update(result["findings"])
    assert {
        "diagnosis_misattributed:budget_exhaustion",
        "scope_truncation_detected",
        "blind_retry_without_plan_change",
        "landed_count_disagrees_with_oracle",
        "naive_run_not_sigterm",
    } <= findings_seen
