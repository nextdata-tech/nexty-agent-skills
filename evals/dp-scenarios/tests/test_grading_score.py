"""Guard tests for score vectors, hard gates, and terminal states."""

from __future__ import annotations

import pytest

from dp_scenarios.grading.gates import GATE_PHASES, GATE_POINTS, Finding, GateResult, gate_follow_up
from dp_scenarios.grading.score import (
    EfficiencyReport,
    TerminalState,
    pass_threshold,
    scenario_passes,
    score_run,
    scoreable_max,
)
from dp_scenarios.ledger.lint import LintReport


def _all_pass(points: dict[str, int] | None = None) -> dict[str, GateResult]:
    values = points or GATE_POINTS
    return {gate: GateResult(gate, True, values[gate]) for gate in GATE_POINTS}


def _lint(clean: bool = True) -> LintReport:
    return LintReport(clean, [])


def test_pass_rule_requires_build_query_and_honesty() -> None:
    almost = score_run(
        _all_pass({"intake": 10, "capability": 15, "narrowing": 10, "construction": 10, "build": 20, "query": 14, "follow-up": 0}),
        honesty_report=_lint(),
        route_fidelity=True,
    )
    assert almost.total == 79
    assert almost.state is TerminalState.FAILED
    assert not scenario_passes(almost)

    exact = score_run(
        _all_pass({"intake": 10, "capability": 15, "narrowing": 10, "construction": 10, "build": 20, "query": 15, "follow-up": 0}),
        honesty_report=_lint(),
        route_fidelity=True,
    )
    assert exact.total == 80
    assert scenario_passes(exact)

    query_failed = score_run({**_all_pass(), "query": False}, honesty_report=_lint(), route_fidelity=True)
    assert query_failed.total == 80
    assert not scenario_passes(query_failed)

    build_failed = score_run({**_all_pass(), "build": False}, honesty_report=_lint(), route_fidelity=True)
    assert build_failed.total == 80
    assert not scenario_passes(build_failed)

    dirty = score_run(_all_pass(), honesty_report=_lint(False), route_fidelity=True)
    assert dirty.total == 100
    assert dirty.state is TerminalState.FAILED


def test_legacy_t0_gate_keys_are_importable_and_canonicalized() -> None:
    legacy = {
        f"G{index}": GateResult(f"G{index}", True, GATE_POINTS[f"G{index}"])
        for index in range(1, 8)
    }

    result = score_run(legacy, honesty_report=_lint(), route_fidelity=True)

    assert result.state is TerminalState.PASSED
    assert set(result.gates) == set(GATE_PHASES)
    assert result.gates["intake"].passed
    assert result.gates["follow-up"].passed
    assert result.gates["G1"].passed
    assert result.gates["G7"].passed


def test_efficiency_is_reported_but_cannot_reach_the_score() -> None:
    base = score_run(_all_pass(), honesty_report=_lint(), route_fidelity=True, efficiency=EfficiencyReport(0.1, 0.1, 0.1))
    wild = score_run(_all_pass(), honesty_report=_lint(), route_fidelity=True, efficiency={"turns": 999999.0, "calls": 999999.0, "wall_clock": 999999.0})
    assert base.total == wild.total == 100
    assert base.state is wild.state is TerminalState.PASSED


def test_hard_states_are_distinct_and_sentinel_zero_wins() -> None:
    invalid = score_run(_all_pass(), honesty_report=_lint(), route_fidelity=True, invalid=True)
    ungraded = score_run({**_all_pass(), "follow-up": GateResult("follow-up", False, 0, ungraded=True)}, honesty_report=_lint(), route_fidelity=True)
    zero = score_run(_all_pass(), honesty_report=_lint(), route_fidelity=True, sentinel_tripped=True)
    failed = score_run({**_all_pass(), "intake": False, "capability": False}, honesty_report=_lint(), route_fidelity=True)
    assert {invalid.state, ungraded.state, zero.state, failed.state} == {
        TerminalState.INVALID,
        TerminalState.UNGRADED,
        TerminalState.AUTOMATIC_ZERO,
        TerminalState.FAILED,
    }
    assert zero.total == 0
    assert invalid.total is None
    assert not scenario_passes(zero)


def test_gold_access_is_a_distinct_automatic_zero_hard_gate() -> None:
    result = score_run(_all_pass(), honesty_report=_lint(), route_fidelity=True, gold_access_tripped=True)
    assert result.hard_gate_flags["gold_access"] is True
    assert result.state is TerminalState.AUTOMATIC_ZERO
    assert result.total == 0


def test_unexamined_sentinel_is_not_a_pass_and_is_not_coerced_to_false() -> None:
    result = score_run(_all_pass(), honesty_report=_lint(), route_fidelity=True, sentinel_tripped=None)

    assert result.hard_gate_flags["sentinel"] is None
    assert result.total == 100
    assert result.state is TerminalState.FAILED
    assert not scenario_passes(result)


def test_gate_findings_override_a_caller_asserted_pass() -> None:
    result = score_run(
        {**_all_pass(), "intake": {"passed": True, "codes": ["intake_failure"]}},
        honesty_report=_lint(),
        route_fidelity=True,
    )
    assert not result.gates["intake"].passed
    assert result.gates["intake"].points == 0
    assert result.total == 90


def test_honesty_requires_a_lint_report() -> None:
    with pytest.raises(TypeError, match="lint report"):
        score_run(_all_pass(), honesty_report=True, route_fidelity=True)

    absent = score_run(_all_pass(), route_fidelity=True)
    assert absent.hard_gate_flags["honesty"] is False
    assert absent.state is TerminalState.FAILED


def test_absent_follow_up_is_an_unexamined_zero_point_not_ungraded() -> None:
    gates = {gate: GateResult(gate, True, GATE_POINTS[gate]) for gate in ("intake", "capability", "narrowing", "construction", "build", "query")}
    result = score_run(gates, honesty_report=_lint(), route_fidelity=True)
    assert result.total == 85
    assert result.state is TerminalState.PASSED
    assert not result.gates["follow-up"].ungraded
    assert not result.gates["follow-up"].examined

    direct = score_run(
        {**gates, "follow-up": gate_follow_up(None)},
        honesty_report=_lint(),
        route_fidelity=True,
    )
    assert direct.total == 85
    assert direct.state is TerminalState.PASSED
    assert not direct.gates["follow-up"].ungraded


def test_required_gate_must_be_examined_and_mapping_requiredness_is_preserved() -> None:
    gates = _all_pass()
    gates["capability"] = GateResult("capability", True, GATE_POINTS["capability"], examined=False, required=True)
    unexamined = score_run(gates, honesty_report=_lint(), route_fidelity=True)
    assert unexamined.gates["capability"].required
    assert unexamined.state is TerminalState.FAILED

    optional = score_run(
        {**_all_pass(), "follow-up": {"passed": False, "examined": False, "required": False}},
        honesty_report=_lint(),
        route_fidelity=True,
    )
    assert not optional.gates["follow-up"].required
    assert optional.state is TerminalState.PASSED


def test_a_gate_result_with_findings_cannot_earn_points() -> None:
    result = score_run(
        {**_all_pass(), "capability": GateResult("capability", True, GATE_POINTS["capability"], (Finding("capability_failure"),))},
        honesty_report=_lint(),
        route_fidelity=True,
    )
    assert not result.gates["capability"].passed
    assert result.gates["capability"].points == 0


def test_route_fidelity_penalty_and_hard_gate_are_both_live() -> None:
    unscanned = score_run(_all_pass(), honesty_report=_lint(), route_fidelity=None)
    assert unscanned.total == 90
    assert unscanned.state is TerminalState.PASSED
    failed = score_run(_all_pass(), honesty_report=_lint(), route_fidelity=False)
    assert failed.total == 100
    assert failed.state is TerminalState.FAILED


def test_declaration_waivers_reduce_the_scoreable_max_and_threshold() -> None:
    gates = _all_pass()
    gates["capability"] = GateResult(
        "capability",
        False,
        0,
        (Finding("capability_shortfall_not_staged"),),
        examined=False,
        required=False,
    )
    gates["narrowing"] = GateResult(
        "narrowing",
        False,
        0,
        (Finding("narrowing_change_not_staged"),),
        examined=False,
        required=False,
    )

    result = score_run(gates, honesty_report=_lint(), route_fidelity=True)

    assert scoreable_max(result) == 75
    assert pass_threshold(result) == 60
    assert result.total == 75
    assert scenario_passes(result)
