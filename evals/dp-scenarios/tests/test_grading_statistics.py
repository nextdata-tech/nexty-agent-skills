"""Guard tests for Wilson rates, declared repeats, pairing, and clustering."""

from __future__ import annotations

import pytest
from types import SimpleNamespace

from dp_scenarios.grading.gates import GATE_POINTS, GateResult
from dp_scenarios.grading.score import score_run
from dp_scenarios.ledger.manifest import default_runtime_knobs
from dp_scenarios.grading.statistics import (
    DemonstratedOnce,
    RepeatabilityTier,
    discount_twins,
    gate_pass_rates,
    paired_mcnemar,
    render_rate,
    repeatability_plan,
    repeatability_certificate,
)
from dp_scenarios.ledger.lint import LintReport
from dp_scenarios.ledger.manifest import ManifestError
from nxd_eval.stats import wilson_ci


def _run(state: str = "passed", *, scenario_id: str = "s", g5: bool = True, g6: bool = True, tier: str | None = None) -> dict[str, object]:
    result: dict[str, object] = {"state": state, "scenario_id": scenario_id, "gates": {"build": g5, "query": g6}}
    if tier is not None:
        result["repeatability_tier"] = tier
    return result


def _manifest() -> dict[str, object]:
    return {
        "agent_model_id": "agent",
        "agent_sampling_params": {"temperature": 0},
        "judge_model_id": "not-applicable",
        "judge_prompt_hash": "not-applicable",
        "skill_pack_version": "v1",
        "supervisor_version": "sup-1",
        "nxd_data_product_wheel_version": "wheel-1",
        "fixture_dir_hash": "fixture",
        "mock_api_version": "mock-1",
        "operator_script_hash": "operator",
        "turn_budget": 10,
        "grant_fixture_hash": "not-applicable",
        "scenario_id": "scenario",
        "tier": "smoke",
        "trial_index": 0,
        "canary_claims_hash": "claims",
        "persona_paraphrase_prompt_hash": "not-applicable",
        "judge_calibration_set_hash": "not-applicable",
        "fixture_seed": 1,
        "fixture_base_instant": "2024-01-01T00:00:00+00:00",
        "run_id": "run",
        "runtime_knobs": default_runtime_knobs(),
    }


def test_rates_use_nxd_eval_wilson_and_exclude_invalid() -> None:
    runs = [_run(), _run("failed", g6=False), _run("invalid"), _run()]
    report = gate_pass_rates(runs)
    assert report.excluded_invalid == 1
    expected = wilson_ci(3, 3)
    assert report.rates["build"].lower_bound == expected.low
    assert report.rates["query"].passed == 2
    assert report.rates["build"].examined == 3


def test_declared_repeatability_and_one_shot_have_distinct_surfaces() -> None:
    deterministic = repeatability_certificate([_run() for _ in range(5)], RepeatabilityTier.DETERMINISTIC)
    assert deterministic.required_epochs == 5
    assert not deterministic.certified  # five observations cannot clear a 0.90 Wilson lower bound
    one_shot = repeatability_certificate([_run()], RepeatabilityTier.DEMONSTRATED_ONCE)
    assert isinstance(one_shot.demonstrated_once, DemonstratedOnce)
    assert one_shot.rates is None
    with pytest.raises(TypeError, match="demonstrated-once"):
        render_rate(one_shot.demonstrated_once)  # type: ignore[arg-type]
    # One observation is not a caller error, it is a batch that cannot be
    # rated: an empty report, not an exception.
    assert gate_pass_rates([_run()]).rates == {}
    with pytest.raises(ValueError, match="demonstrated-once"):
        gate_pass_rates([_run(tier="demonstrated-once") for _ in range(3)])


def test_wilson_lower_bound_and_exact_epoch_count_are_both_required() -> None:
    declared = SimpleNamespace(
        tier=RepeatabilityTier.DETERMINISTIC,
        epochs=30,
        certification_rule="wilson_lower_bound",
        gates=("build",),
        lower_bound=0.85,
        confidence=0.95,
    )
    bound_between_thresholds = repeatability_certificate(
        [_run(g5=index < 29) for index in range(30)],
        declared,
    )
    assert bound_between_thresholds.rates is not None
    lower_bound = bound_between_thresholds.rates.rates["build"].lower_bound
    assert lower_bound < declared.lower_bound
    assert 0.80 < lower_bound < 0.90
    assert not bound_between_thresholds.certified

    short_declared = SimpleNamespace(
        tier=RepeatabilityTier.DETERMINISTIC,
        epochs=30,
        certification_rule="wilson_lower_bound",
        gates=("build",),
        lower_bound=0.80,
        confidence=0.95,
    )
    short_batch = repeatability_certificate([_run() for _ in range(29)], short_declared)
    assert not short_batch.certified


def test_declared_observed_epoch_contract_requires_all_declared_epochs() -> None:
    declared = SimpleNamespace(
        tier=RepeatabilityTier.DETERMINISTIC,
        epochs=6,
        certification_rule="observed_epochs",
        gates=("build",),
        lower_bound=0.73,
        confidence=0.80,
    )

    short = repeatability_certificate([_run() for _ in range(5)], declared)
    complete = repeatability_certificate([_run() for _ in range(6)], declared)

    assert short.required_epochs == 6
    assert short.observed_epochs == 5
    assert not short.certified
    assert complete.certified
    assert complete.rates is not None
    assert complete.rates.rates["build"].lower_bound == wilson_ci(6, 6, alpha=0.20).low


def test_invalid_epoch_cannot_certify_a_complete_repeatability_batch() -> None:
    declared = SimpleNamespace(
        tier=RepeatabilityTier.DETERMINISTIC,
        epochs=6,
        certification_rule="observed_epochs",
        gates=("build",),
        lower_bound=0.73,
        confidence=0.80,
    )
    report = repeatability_certificate([_run() for _ in range(5)] + [_run("invalid")], declared)

    assert report.rates is not None
    assert report.rates.excluded_invalid == 1
    assert not report.certified


def test_mock_source_epoch_plan_and_observed_count_are_pinned() -> None:
    assert repeatability_plan(RepeatabilityTier.MOCK_SOURCE) == 3
    report = repeatability_certificate([_run(), _run()], RepeatabilityTier.MOCK_SOURCE)
    assert report.required_epochs == 3
    assert report.observed_epochs == 2
    assert not report.certified


def test_rates_use_gate_examination_and_zero_automatic_zero_numerators() -> None:
    unexamined = _run()
    unexamined["gates"] = {"build": {"passed": True, "examined": False}, "query": True}
    report = gate_pass_rates([unexamined, _run()])
    assert report.rates["build"].passed == 1
    assert report.rates["build"].examined == 1

    zero = gate_pass_rates([_run("automatic zero"), _run()])
    assert zero.rates["build"].passed == 1
    assert zero.rates["build"].examined == 2

    typed_zero = score_run(
        {gate: GateResult(gate, True, GATE_POINTS[gate]) for gate in GATE_POINTS},
        honesty_report=LintReport(True, []),
        route_fidelity=True,
        sentinel_tripped=True,
    )
    typed_report = gate_pass_rates([typed_zero, _run()])
    assert typed_report.rates["build"].passed == 1
    assert typed_report.rates["build"].examined == 2


def test_rate_requests_require_two_valid_observations() -> None:
    """No observations is a caller error; too few *completed* ones is a result.

    The distinction matters because the second case is reachable from a bad
    environment -- a slow agent, a wedged provider, a turn timeout too tight --
    and `tier.py` calls this bare inside its per-scenario loop.  Raising there
    cost the operator `report.json` and `summary.txt` for a run that had
    already spent its agent and driver tokens, which is the moment the evidence
    is worth most.  Certification is unaffected either way: it already fails on
    ``excluded_invalid != 0``.
    """

    with pytest.raises(ValueError, match="at least two valid"):
        gate_pass_rates([])

    report = gate_pass_rates([_run(), _run("invalid"), _run("invalid")])
    assert report.rates == {}
    assert report.excluded_invalid == 2


def test_twins_are_discounted_before_rates() -> None:
    selected, discounted = discount_twins([_run(scenario_id="a"), _run(scenario_id="b"), _run(scenario_id="c")], {"a": "t", "b": "t", "c": "c"})
    assert len(selected) == 2
    assert discounted == 1


def test_mcnemar_refuses_multi_field_manifests_and_accepts_one_field() -> None:
    first = _manifest()
    second = {**first, "skill_pack_version": "v2"}
    result = paired_mcnemar(
        first,
        second,
        [_run(g6=True), _run(g6=True), _run(g6=False), _run(g6=True)],
        [_run(g6=False), _run(g6=False), _run(g6=True), _run(g6=True)],
        field_under_test="skill_pack_version",
    )
    assert result.b == 2
    assert result.c == 1

    with pytest.raises(ValueError, match="requested comparison"):
        paired_mcnemar(first, second, [_run()], [_run()], field_under_test="supervisor_version")
    with pytest.raises(ValueError, match="one outcome per identical trial"):
        paired_mcnemar(first, second, [_run()], [_run(), _run()])

    multi = {**first, "skill_pack_version": "v2", "supervisor_version": "sup-2"}
    with pytest.raises(ValueError, match="exactly one"):
        paired_mcnemar(first, multi, [_run()], [_run()])
    with pytest.raises(ValueError, match="fixture, operator script and driver"):
        paired_mcnemar(first, {**first, "fixture_dir_hash": "fixture-2"}, [_run()], [_run()])
    with pytest.raises(ValueError, match="fixture, operator script and driver"):
        paired_mcnemar(first, {**first, "operator_script_hash": "operator-2"}, [_run()], [_run()])


def test_mcnemar_refuses_validation_mode_as_a_pairing_axis() -> None:
    live = {
        **_manifest(),
        "validation_mode": "live",
        "supervisor_binary_path": "/opt/supervisor#sha256:abc",
        "session_root": "/tmp/session",
        "session_config_path": "/tmp/session/mcp-config.json",
        "session_config_sha256": "sha256:config",
        "session_trace_path": "/tmp/session/mcp-trace.jsonl",
        "session_server_result_path": "/tmp/session/server-result.json",
    }
    replay = {**live, "validation_mode": "replay"}

    with pytest.raises(ValueError, match="exactly one"):
        paired_mcnemar(live, replay, [_run()], [_run()])


def test_mcnemar_refuses_driver_model_as_a_pairing_axis() -> None:
    first = {**_manifest(), "driver_model_id": "gpt-a", "driver_sampling_params": {"temperature": 0}}
    second = {**first, "driver_model_id": "gpt-b"}

    with pytest.raises(ValueError, match="fixture, operator script and driver"):
        paired_mcnemar(first, second, [_run()], [_run()])


def test_mcnemar_refuses_a_manifest_whose_runtime_knobs_are_unpinned() -> None:
    pinned = _manifest()
    unpinned = {key: value for key, value in pinned.items() if key != "runtime_knobs"}

    with pytest.raises(ManifestError, match="runtime_knobs"):
        paired_mcnemar(pinned, unpinned, [_run()], [_run()])


def test_a_batch_of_truncated_epochs_still_reports() -> None:
    """The bad-environment shape must produce a report, not a traceback.

    A systemic cause truncates every epoch, not one: `_run_scenario_epochs` has
    no early break, so a slow agent or a --turn-timeout too tight for a driven
    turn runs all five to the same end.  Before this, feeding truncated runs to
    the `len(valid) < 2` guard raised out of `gate_pass_rates`, which `tier.py`
    calls bare -- and neither runner catches ValueError, so the operator lost
    report.json and summary.txt for a run that had already spent its agent and
    driver tokens.
    """

    for truncated_count in (4, 5):
        runs = [_run() for _ in range(5 - truncated_count)]
        runs += [{**_run(), "truncated": True} for _ in range(truncated_count)]

        report = gate_pass_rates(runs)

        assert report.rates == {}, "a batch with too few completed epochs cannot be rated"
        assert report.excluded_invalid == truncated_count
        assert report.excluded_truncated == truncated_count


def test_excluded_truncated_separates_a_timeout_from_an_invalid_run() -> None:
    """`excluded_invalid` counts both, so the two stay separable elsewhere.

    A truncated run scores PASSED with `terminal_state=turn_timeout`; reporting
    it only under a heading that says "invalid" makes the per-epoch line and
    the batch line contradict each other.
    """

    runs = [_run(), _run(), _run(), _run("invalid"), {**_run(), "truncated": True}]

    report = gate_pass_rates(runs)

    assert report.excluded_invalid == 2
    assert report.excluded_truncated == 1
