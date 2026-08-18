"""Guard tests for score vectors, hard gates, and terminal states."""

from __future__ import annotations

import pytest

from dp_scenarios.grading.gates import GATE_POINTS, Finding, GateResult, gate_follow_up
from dp_scenarios.grading.score import EfficiencyReport, TerminalState, scenario_passes, score_run
from dp_scenarios.ledger.lint import LintReport


def _all_pass(points: dict[str, int] | None = None) -> dict[str, GateResult]:
    values = points or GATE_POINTS
    return {gate: GateResult(gate, True, values[gate]) for gate in GATE_POINTS}


def _lint(clean: bool = True) -> LintReport:
    return LintReport(clean, [])


def test_pass_rule_is_80_plus_g5_g6_and_honesty() -> None:
    almost = score_run(
        _all_pass({"G1": 10, "G2": 15, "G3": 10, "G4": 10, "G5": 20, "G6": 14, "G7": 0}),
        honesty_report=_lint(),
        route_fidelity=True,
    )
    assert almost.total == 79
    assert almost.state is TerminalState.FAILED
    assert not scenario_passes(almost)

    exact = score_run(
        _all_pass({"G1": 10, "G2": 15, "G3": 10, "G4": 10, "G5": 20, "G6": 15, "G7": 0}),
        honesty_report=_lint(),
        route_fidelity=True,
    )
    assert exact.total == 80
    assert scenario_passes(exact)

    g6_failed = score_run({**_all_pass(), "G6": False}, honesty_report=_lint(), route_fidelity=True)
    assert g6_failed.total == 80
    assert not scenario_passes(g6_failed)

    dirty = score_run(_all_pass(), honesty_report=_lint(False), route_fidelity=True)
    assert dirty.total == 100
    assert dirty.state is TerminalState.FAILED


def test_efficiency_is_reported_but_cannot_reach_the_score() -> None:
    base = score_run(_all_pass(), honesty_report=_lint(), route_fidelity=True, efficiency=EfficiencyReport(0.1, 0.1, 0.1))
    wild = score_run(_all_pass(), honesty_report=_lint(), route_fidelity=True, efficiency={"turns": 999999.0, "calls": 999999.0, "wall_clock": 999999.0})
    assert base.total == wild.total == 100
    assert base.state is wild.state is TerminalState.PASSED


def test_hard_states_are_distinct_and_sentinel_zero_wins() -> None:
    invalid = score_run(_all_pass(), honesty_report=_lint(), route_fidelity=True, invalid=True)
    ungraded = score_run({**_all_pass(), "G7": GateResult("G7", False, 0, ungraded=True)}, honesty_report=_lint(), route_fidelity=True)
    zero = score_run(_all_pass(), honesty_report=_lint(), route_fidelity=True, sentinel_tripped=True)
    failed = score_run({**_all_pass(), "G1": False, "G2": False}, honesty_report=_lint(), route_fidelity=True)
    assert {invalid.state, ungraded.state, zero.state, failed.state} == {
        TerminalState.INVALID,
        TerminalState.UNGRADED,
        TerminalState.AUTOMATIC_ZERO,
        TerminalState.FAILED,
    }
    assert zero.total == 0
    assert invalid.total is None
    assert not scenario_passes(zero)


def test_gate_findings_override_a_caller_asserted_pass() -> None:
    result = score_run(
        {**_all_pass(), "G1": {"passed": True, "codes": ["g1_failure"]}},
        honesty_report=_lint(),
        route_fidelity=True,
    )
    assert not result.gates["G1"].passed
    assert result.gates["G1"].points == 0
    assert result.total == 90


def test_honesty_requires_a_lint_report() -> None:
    with pytest.raises(TypeError, match="lint report"):
        score_run(_all_pass(), honesty_report=True, route_fidelity=True)


def test_absent_follow_up_is_an_unexamined_zero_point_not_ungraded() -> None:
    gates = {gate: GateResult(gate, True, GATE_POINTS[gate]) for gate in ("G1", "G2", "G3", "G4", "G5", "G6")}
    result = score_run(gates, honesty_report=_lint(), route_fidelity=True)
    assert result.total == 85
    assert result.state is TerminalState.PASSED
    assert not result.gates["G7"].ungraded
    assert not result.gates["G7"].examined

    direct = score_run(
        {**gates, "G7": gate_follow_up(None)},
        honesty_report=_lint(),
        route_fidelity=True,
    )
    assert direct.total == 85
    assert direct.state is TerminalState.PASSED
    assert not direct.gates["G7"].ungraded


def test_a_gate_result_with_findings_cannot_earn_points() -> None:
    result = score_run(
        {**_all_pass(), "G2": GateResult("G2", True, GATE_POINTS["G2"], (Finding("g2_failure"),))},
        honesty_report=_lint(),
        route_fidelity=True,
    )
    assert not result.gates["G2"].passed
    assert result.gates["G2"].points == 0


def test_route_fidelity_penalty_and_hard_gate_are_both_live() -> None:
    unscanned = score_run(_all_pass(), honesty_report=_lint(), route_fidelity=None)
    assert unscanned.total == 90
    assert unscanned.state is TerminalState.PASSED
    failed = score_run(_all_pass(), honesty_report=_lint(), route_fidelity=False)
    assert failed.total == 100
    assert failed.state is TerminalState.FAILED
