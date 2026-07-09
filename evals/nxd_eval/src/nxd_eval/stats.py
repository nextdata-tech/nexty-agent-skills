"""Statistics contract for the nxd_eval framework.

Every number the report and the certify gate lean on is computed here, on top of
``statsmodels`` / ``scipy`` / ``scikit-learn`` (all BSD). Three quantities have no
one-call library form and are hand-rolled with the standard textbook definition:
the design effect (one line), the Expected Calibration Error (a short loop over
``calibration_curve`` bins), and the Area Under the Risk–Coverage curve (sort by
confidence, sweep coverage, integrate risk).

Deliberately NOT a dependency: ``pingouin`` — it is GPL-licensed and would
contaminate the pack's license posture. Nothing here needs it.

The interval used to *gate* a pass rate is always the Wilson score interval
(``proportion_confint(..., method="wilson")``); swapping in the Wald interval is
exactly the silent drift the unit tests are built to catch.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.stats import norm
from sklearn.calibration import calibration_curve
from sklearn.metrics import brier_score_loss
from statsmodels.stats.contingency_tables import mcnemar
from statsmodels.stats.multitest import multipletests
from statsmodels.stats.proportion import proportion_confint

__all__ = [
    "ConfidenceInterval",
    "McNemarResult",
    "wilson_ci",
    "sample_size_for",
    "design_effect",
    "n_eff",
    "mcnemar_paired",
    "bh_fdr",
    "brier",
    "ece",
    "aurc",
    "gwet_ac1",
    "cohen_kappa",
]


# --------------------------------------------------------------------------- #
# Proportion estimation
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ConfidenceInterval:
    """A point estimate with a two-sided confidence interval."""

    p_hat: float
    low: float
    high: float
    n: int

    @property
    def halfwidth(self) -> float:
        """Half the interval width — the plus/minus margin of error."""
        return (self.high - self.low) / 2.0


def wilson_ci(count: int, nobs: int, *, alpha: float = 0.05) -> ConfidenceInterval:
    """Wilson score interval for a binomial proportion.

    Thin wrapper over ``statsmodels.stats.proportion.proportion_confint`` with
    ``method="wilson"``. The Wilson interval is asymmetric near 0/1 and never
    escapes ``[0, 1]`` — that asymmetry is a feature the tests assert, and it is
    the whole reason we do not use the Wald interval here.

    Args:
        count: Number of successes (e.g. PASS samples).
        nobs: Number of trials.
        alpha: Two-sided significance level; ``0.05`` → 95% interval.
    """
    if nobs <= 0:
        raise ValueError("nobs must be positive")
    low, high = proportion_confint(count, nobs, alpha=alpha, method="wilson")
    return ConfidenceInterval(
        p_hat=count / nobs,
        low=float(low),
        high=float(high),
        n=int(nobs),
    )


def sample_size_for(p: float, moe: float, *, alpha: float = 0.05) -> int:
    """Planning sample size for a target margin of error at proportion ``p``.

    Uses the standard normal-approximation planning formula

        n = z**2 * p * (1 - p) / moe**2

    floored to an integer. This is the sample-size *planner* — the actual gate
    on an observed rate still uses :func:`wilson_ci`. The rounded-count Wilson
    halfwidth is non-monotone in ``n`` near the boundary (rounding ``p*n`` to an
    integer count wobbles the width up and down), so the closed-form planner is
    what gives a stable, reproducible N-table.

    Args:
        p: Assumed underlying proportion (worst case is ``0.5``).
        moe: Target margin of error (half-width), e.g. ``0.05`` for +/-5%.
        alpha: Two-sided significance level backing the ``z`` multiplier.
    """
    if not 0.0 <= p <= 1.0:
        raise ValueError("p must be in [0, 1]")
    if moe <= 0.0:
        raise ValueError("moe must be positive")
    z = float(norm.ppf(1.0 - alpha / 2.0))
    raw = z * z * p * (1.0 - p) / (moe * moe)
    return int(math.floor(raw))


# --------------------------------------------------------------------------- #
# Clustering / design effect
# --------------------------------------------------------------------------- #


def design_effect(m: float, icc: float) -> float:
    """Design effect for ``m`` correlated observations per cluster.

        deff = 1 + (m - 1) * icc

    With epochs (``k`` repeats of the same case) the repeats are correlated, so
    the effective sample size shrinks by this factor. ``icc`` is the
    intra-cluster correlation.
    """
    return 1.0 + (m - 1.0) * icc


def n_eff(n: int, m: float, icc: float) -> float:
    """Effective sample size after deflating ``n`` by the design effect."""
    deff = design_effect(m, icc)
    if deff <= 0.0:
        raise ValueError("design effect must be positive")
    return n / deff


# --------------------------------------------------------------------------- #
# Paired significance / multiple comparisons
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class McNemarResult:
    """Outcome of a McNemar test on a 2x2 discordant table."""

    statistic: float
    pvalue: float
    b: int
    c: int


def mcnemar_paired(
    a: int,
    b: int,
    c: int,
    d: int | None = None,
    *,
    exact: bool | None = None,
    correction: bool = True,
) -> McNemarResult:
    """McNemar test for paired binary outcomes (e.g. ``current_pack`` vs
    ``no_skills`` on the same cases).

    The 2x2 table is ``[[a, b], [c, d]]`` where ``b`` and ``c`` are the
    *discordant* cells (one variant right, the other wrong). Only the discordant
    counts drive the test; ``d`` defaults to 0 and never affects the result.

    Delegates to ``statsmodels.stats.contingency_tables.mcnemar``. By default we
    let statsmodels pick exact vs asymptotic (exact when the discordant total is
    small); pass ``exact=True/False`` to force it. ``correction`` applies the
    continuity correction in the asymptotic branch.
    """
    if d is None:
        d = 0
    table = [[a, b], [c, d]]
    # statsmodels treats exact=None as "auto"; forward it unchanged so callers
    # get the library's own small-sample switch.
    kwargs: dict = {"correction": correction}
    if exact is not None:
        kwargs["exact"] = exact
    result = mcnemar(table, **kwargs)
    stat = result.statistic
    return McNemarResult(
        statistic=float("nan") if stat is None else float(stat),
        pvalue=float(result.pvalue),
        b=int(b),
        c=int(c),
    )


def bh_fdr(pvals: list[float], *, alpha: float = 0.05) -> list[float]:
    """Benjamini–Hochberg FDR-adjusted p-values.

    Thin wrapper over ``statsmodels.stats.multitest.multipletests`` with
    ``method="fdr_bh"``. Returns the adjusted p-values in the input order.
    """
    if not pvals:
        return []
    _, padj, _, _ = multipletests(pvals, alpha=alpha, method="fdr_bh")
    return [float(p) for p in padj]


# --------------------------------------------------------------------------- #
# Calibration / confidence quality
# --------------------------------------------------------------------------- #


def brier(y_true: list[int], y_prob: list[float]) -> float:
    """Brier score — mean squared error between confidence and outcome.

    Wrapper over ``sklearn.metrics.brier_score_loss``. Lower is better; 0 is a
    perfectly calibrated, perfectly confident predictor.
    """
    return float(brier_score_loss(y_true, y_prob))


def ece(y_true: list[int], y_prob: list[float], *, n_bins: int = 10) -> float:
    """Expected Calibration Error over equal-width confidence bins.

        ECE = sum over bins of  (bin_weight * |acc_bin - conf_bin|)

    ``calibration_curve`` gives per-bin accuracy and mean confidence; we weight
    each bin by its share of the (non-empty) samples and sum the absolute gaps.
    Hand-rolled because sklearn exposes the curve but not the scalar summary.
    """
    y_true_arr = np.asarray(y_true, dtype=float)
    y_prob_arr = np.asarray(y_prob, dtype=float)
    n = y_prob_arr.shape[0]
    if n == 0:
        return 0.0

    # Per-bin accuracy (frac_pos) and mean confidence (mean_pred) for the bins
    # that actually contain samples; sklearn drops empty bins.
    frac_pos, mean_pred = calibration_curve(
        y_true_arr, y_prob_arr, n_bins=n_bins, strategy="uniform"
    )

    # Recover each returned bin's sample count so we can weight by bin mass. Use
    # the same uniform edges sklearn used, then match populated bins in order.
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    # np.digitize with right=True puts p==edge into the lower bin; clamp to
    # [1, n_bins] then shift to 0-based bin ids.
    bin_ids = np.clip(np.digitize(y_prob_arr, edges[1:-1], right=False), 0, n_bins - 1)
    counts = np.bincount(bin_ids, minlength=n_bins)
    populated = counts[counts > 0]

    if populated.shape[0] != frac_pos.shape[0]:
        # Defensive: if edge cases desync the two, fall back to equal weights.
        weights = np.full(frac_pos.shape[0], 1.0 / frac_pos.shape[0])
    else:
        weights = populated / float(n)

    return float(np.sum(weights * np.abs(frac_pos - mean_pred)))


def aurc(y_true: list[int], y_prob: list[float]) -> float:
    """Area Under the Risk–Coverage curve (selective-prediction quality).

    Sort predictions by confidence descending, sweep coverage from the most- to
    least-confident sample, and integrate the running risk (error rate over the
    covered head) against coverage with the trapezoidal rule. Lower is better: a
    model that is confident exactly when it is right keeps risk low at high
    coverage, shrinking the area.
    """
    y_true_arr = np.asarray(y_true, dtype=float)
    y_prob_arr = np.asarray(y_prob, dtype=float)
    n = y_prob_arr.shape[0]
    if n == 0:
        return 0.0

    order = np.argsort(-y_prob_arr, kind="stable")
    errors = 1.0 - y_true_arr[order]  # 1 where the covered prediction is wrong

    cum_errors = np.cumsum(errors)
    k = np.arange(1, n + 1, dtype=float)
    risk = cum_errors / k  # running error rate over the covered head
    coverage = k / float(n)

    return float(np.trapezoid(risk, coverage))


# --------------------------------------------------------------------------- #
# Chance-corrected inter-rater / test-retest agreement
# --------------------------------------------------------------------------- #


def _confusion_from_pairs(
    rater_a: list[str], rater_b: list[str]
) -> tuple[list[str], np.ndarray]:
    """Ordered category list + confusion matrix for two aligned label vectors."""
    if len(rater_a) != len(rater_b):
        raise ValueError("rater label vectors must be the same length")
    if not rater_a:
        raise ValueError("need at least one paired label")
    cats = sorted(set(rater_a) | set(rater_b))
    index = {c: i for i, c in enumerate(cats)}
    q = len(cats)
    m = np.zeros((q, q), dtype=float)
    for a, b in zip(rater_a, rater_b):
        m[index[a], index[b]] += 1.0
    return cats, m


def cohen_kappa(rater_a: list[str], rater_b: list[str]) -> float:
    """Cohen's kappa — chance-corrected agreement between two raters.

        kappa = (p_o - p_e) / (1 - p_e)

    where ``p_o`` is observed agreement and ``p_e`` the chance agreement from the
    product of the two raters' marginals. Provided alongside :func:`gwet_ac1` so
    the report can show the *kappa paradox*: under concentrated marginals (one
    label dominates) ``p_e`` inflates toward ``p_o`` and kappa collapses even when
    observed agreement is high. Returns ``1.0`` when both raters agree everywhere
    on a single category (degenerate ``1 - p_e == 0``).
    """
    _cats, m = _confusion_from_pairs(rater_a, rater_b)
    n = m.sum()
    p_o = float(np.trace(m) / n)
    row = m.sum(axis=1) / n
    col = m.sum(axis=0) / n
    p_e = float(np.dot(row, col))
    if math.isclose(p_e, 1.0):
        return 1.0
    return (p_o - p_e) / (1.0 - p_e)


def gwet_ac1(rater_a: list[str], rater_b: list[str]) -> float:
    """Gwet's AC1 — chance-corrected agreement robust to concentrated marginals.

        AC1 = (p_o - p_e) / (1 - p_e)

    with the *same* observed-agreement ``p_o`` as Cohen's kappa but a different
    chance term. Gwet models chance agreement as a random-rating event whose
    probability is estimated from the pooled category prevalence ``pi_k``:

        p_e = (1 / (q - 1)) * sum_k  pi_k * (1 - pi_k)

    where ``q`` is the number of categories and ``pi_k`` is the mean marginal
    prevalence of category ``k`` across the two raters. Because ``p_e`` here does
    not blow up when one category dominates, AC1 stays stable in the
    range-restriction / kappa-paradox regime where kappa under-reports (see
    :func:`cohen_kappa`). This is the documented fix for reliability estimated on
    a judge whose labels cluster in a narrow band.

    Nominal AC1 (for unordered labels such as the judge's C/P/I grades). Uses only
    numpy — no GPL dependency (``pingouin`` is deliberately avoided; see module
    docstring).

    Reference:
        Gwet, K. L. (2008). "Computing inter-rater reliability and its variance
        in the presence of high agreement." British Journal of Mathematical and
        Statistical Psychology, 61(1), 29–48.
    """
    cats, m = _confusion_from_pairs(rater_a, rater_b)
    q = len(cats)
    n = m.sum()
    p_o = float(np.trace(m) / n)
    if q == 1:
        # Only one category ever observed: raters agree by construction and the
        # (q-1) chance normaliser is undefined. Perfect agreement.
        return 1.0
    # Mean marginal prevalence per category across the two raters.
    prevalence = (m.sum(axis=1) + m.sum(axis=0)) / (2.0 * n)
    p_e = float(np.sum(prevalence * (1.0 - prevalence)) / (q - 1))
    if math.isclose(p_e, 1.0):
        return 1.0
    return (p_o - p_e) / (1.0 - p_e)
