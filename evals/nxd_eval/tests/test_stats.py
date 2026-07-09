"""The statistics contract, pinned to exact verified numbers.

These tests guard the foundation against silent drift: they must FAIL if someone
swaps the Wilson interval for Wald, changes the sample-size planner, or breaks the
design-effect / McNemar / BH-FDR wiring. Every number asserted here was produced
by statsmodels/scipy/sklearn and is fixed in the build brief's statistics section.
"""

from __future__ import annotations

import math

from statsmodels.stats.contingency_tables import mcnemar as sm_mcnemar
from statsmodels.stats.multitest import multipletests

from nxd_eval import stats as S


# --------------------------------------------------------------------------- #
# Wilson score interval
# --------------------------------------------------------------------------- #


def test_wilson_halfwidth_at_p090_n140_is_005():
    # p_hat = 0.90, n = 140 -> symmetric-ish, halfwidth ~= +/-0.050.
    ci = S.wilson_ci(count=126, nobs=140)
    assert ci.p_hat == 126 / 140
    assert math.isclose(ci.halfwidth, 0.050, abs_tol=1e-3)


def test_wilson_at_p098_n140_is_asymmetric_bounds():
    # p_hat = 0.98 (137/140) -> [0.939, 0.993], asymmetric about 0.98.
    ci = S.wilson_ci(count=137, nobs=140)
    assert math.isclose(ci.low, 0.939, abs_tol=1e-3)
    assert math.isclose(ci.high, 0.993, abs_tol=1e-3)
    # Asymmetric about the point estimate: the lower reach exceeds the upper.
    lower_reach = ci.p_hat - ci.low
    upper_reach = ci.high - ci.p_hat
    assert lower_reach > upper_reach
    assert not math.isclose(lower_reach, upper_reach, abs_tol=1e-3)


def test_wilson_is_not_wald():
    # A Wald interval at 137/140 would be symmetric about p_hat and would
    # overshoot toward 1.0; Wilson does not. This is the anti-drift guard.
    ci = S.wilson_ci(count=137, nobs=140)
    p = 137 / 140
    z = 1.959963984540054
    wald_hw = z * math.sqrt(p * (1 - p) / 140)
    wald_high = p + wald_hw
    # Wald would push the upper bound past the Wilson upper bound.
    assert wald_high > ci.high


# --------------------------------------------------------------------------- #
# Required-N planning table (p = 0.90)
# --------------------------------------------------------------------------- #


def test_required_n_table_at_p090():
    assert S.sample_size_for(0.90, 0.05) == 138
    assert S.sample_size_for(0.90, 0.03) == 384
    assert S.sample_size_for(0.90, 0.02) == 864


# --------------------------------------------------------------------------- #
# Design effect
# --------------------------------------------------------------------------- #


def test_design_effect_values():
    assert math.isclose(S.design_effect(5, 0.2), 1.80, abs_tol=1e-3)
    assert math.isclose(S.design_effect(10, 0.3), 3.70, abs_tol=1e-3)


def test_n_eff_deflates_by_design_effect():
    # n=100, m=5, icc=0.2 -> deff 1.8 -> n_eff ~= 55.56
    assert math.isclose(S.n_eff(100, 5, 0.2), 100 / 1.8, abs_tol=1e-6)


# --------------------------------------------------------------------------- #
# Paired significance (McNemar) — matches statsmodels exactly
# --------------------------------------------------------------------------- #


def test_mcnemar_matches_statsmodels():
    a, b, c, d = 10, 5, 2, 8
    ours = S.mcnemar_paired(a, b, c, d, exact=False, correction=True)
    ref = sm_mcnemar([[a, b], [c, d]], exact=False, correction=True)
    assert math.isclose(ours.statistic, float(ref.statistic), abs_tol=1e-9)
    assert math.isclose(ours.pvalue, float(ref.pvalue), abs_tol=1e-9)
    # Only the discordant cells matter and are surfaced.
    assert ours.b == b
    assert ours.c == c


def test_mcnemar_ignores_concordant_d():
    # Changing d must not move the statistic/pvalue in the discordant-only test.
    r1 = S.mcnemar_paired(10, 5, 2, 8, exact=False, correction=True)
    r2 = S.mcnemar_paired(999, 5, 2, 0, exact=False, correction=True)
    assert math.isclose(r1.statistic, r2.statistic, abs_tol=1e-9)
    assert math.isclose(r1.pvalue, r2.pvalue, abs_tol=1e-9)


# --------------------------------------------------------------------------- #
# Multiple comparisons (Benjamini–Hochberg) — matches statsmodels exactly
# --------------------------------------------------------------------------- #


def test_bh_fdr_matches_statsmodels():
    pvals = [0.01, 0.04, 0.03, 0.20, 0.005]
    ours = S.bh_fdr(pvals)
    _, ref, _, _ = multipletests(pvals, method="fdr_bh")
    assert len(ours) == len(pvals)
    for got, exp in zip(ours, list(ref)):
        assert math.isclose(got, float(exp), abs_tol=1e-9)


def test_bh_fdr_preserves_input_order():
    # Adjusted p-values come back aligned to the input positions, not sorted.
    pvals = [0.20, 0.01, 0.03]
    ours = S.bh_fdr(pvals)
    _, ref, _, _ = multipletests(pvals, method="fdr_bh")
    assert ours == [float(x) for x in ref]


def test_bh_fdr_empty():
    assert S.bh_fdr([]) == []


# --------------------------------------------------------------------------- #
# Calibration / confidence quality
# --------------------------------------------------------------------------- #


def test_brier_matches_manual():
    y_true = [1, 0, 1, 0]
    y_prob = [0.9, 0.1, 0.8, 0.2]
    manual = sum((p - t) ** 2 for p, t in zip(y_prob, y_true)) / len(y_true)
    assert math.isclose(S.brier(y_true, y_prob), manual, abs_tol=1e-9)


def test_ece_perfectly_calibrated_is_zero():
    # Confidence exactly equals per-bin accuracy -> ECE 0.
    y_true = [1, 1, 0, 0]
    y_prob = [1.0, 1.0, 0.0, 0.0]
    assert math.isclose(S.ece(y_true, y_prob, n_bins=10), 0.0, abs_tol=1e-9)


def test_ece_in_unit_range():
    y_true = [1, 1, 1, 0, 0]
    y_prob = [0.9, 0.8, 0.7, 0.2, 0.1]
    e = S.ece(y_true, y_prob, n_bins=5)
    assert 0.0 <= e <= 1.0


def test_ece_golden_value():
    # Pin the exact ECE so the hand-rolled bin-weighting can't silently drift.
    # Five samples, n_bins=5 (edges every 0.2). Bins are assigned exactly as
    # sklearn's calibration_curve does — ``searchsorted(edges[1:-1], p)`` — so
    # 0.8 lands on its interior edge in the [0.6,0.8) bin, giving populated bins
    # {0.1,0.2}, {0.7,0.8}, {0.9} with mean confidences 0.15 / 0.75 / 0.90 and
    # accuracies 0 / 1 / 1. Weighted |acc - conf| sums to 0.18. Recomputed
    # independently from calibration_curve + bin counts.
    y_true = [1, 1, 1, 0, 0]
    y_prob = [0.9, 0.8, 0.7, 0.2, 0.1]
    assert math.isclose(S.ece(y_true, y_prob, n_bins=5), 0.18, rel_tol=1e-6)


def test_ece_interior_edge_boundary_values():
    # Confidences sitting exactly on interior bin edges must be weighted in the
    # SAME bin the calibration curve assigns them (sklearn uses searchsorted
    # side='left'). All confidences at 0.5 collapse to a single bin: accuracy
    # 0.5, mean confidence 0.5 ⇒ ECE exactly 0.
    y_true = [1, 0, 1, 0]
    y_prob = [0.5, 0.5, 0.5, 0.5]
    assert math.isclose(S.ece(y_true, y_prob, n_bins=10), 0.0, abs_tol=1e-9)

    # A mix straddling the 0.2 edge stays finite and in range with no
    # bin-count/curve desync (which would trip the equal-weight fallback).
    y_true2 = [1, 1, 0, 0]
    y_prob2 = [0.2, 0.4, 0.2, 0.6]
    e = S.ece(y_true2, y_prob2, n_bins=5)
    assert 0.0 <= e <= 1.0
    assert math.isfinite(e)


def test_aurc_ranks_confidence_quality():
    # A ranker that is confident exactly when right has lower AURC than one that
    # is confident exactly when wrong.
    good = S.aurc([1, 1, 0, 0], [0.9, 0.8, 0.2, 0.1])
    bad = S.aurc([0, 0, 1, 1], [0.9, 0.8, 0.2, 0.1])
    assert good < bad


def test_aurc_golden_value():
    # Pin the exact AURC (trapezoid over the sorted risk-coverage curve) so a
    # sign flip in `errors = 1 - y_true`, a cumsum-vs-mean slip, or a trapezoid
    # error can't survive while merely preserving the good<bad ordering.
    # Sorted by confidence desc: [1,1,0,0] -> running risk [0, 0, 1/3, 1/2] at
    # coverage [.25,.5,.75,1.0]; trapezoid = 0.145833... Recomputed independently.
    assert math.isclose(
        S.aurc([1, 1, 0, 0], [0.9, 0.8, 0.2, 0.1]), 0.1458333333, rel_tol=1e-6
    )
    # The mirror-image bad ranker integrates to a much larger area.
    assert math.isclose(
        S.aurc([0, 0, 1, 1], [0.9, 0.8, 0.2, 0.1]), 0.6041666667, rel_tol=1e-6
    )


def test_aurc_empty_is_zero():
    assert S.aurc([], []) == 0.0
