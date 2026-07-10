"""Inspect ``@metric`` wrappers that surface the :mod:`nxd_eval.stats` numbers.

Two metrics live here:

* ``wilson_accuracy`` — the accuracy point estimate, *gated on the lower bound*
  of its Wilson interval. The reported scalar is the Wilson lower bound, so a run
  that happens to hit a high mean on few samples cannot claim a pass rate its
  sample size does not support. The point estimate and the interval ride along in
  the metric's provenance for the report.

* ``reliability_score`` — a TrustSQL-style reliability score with an asymmetric
  penalty. Answering a feasible question correctly earns ``+1``; correctly
  abstaining on an infeasible question earns ``+1``; staying silent when an
  answer was possible earns ``0``; and answering *wrongly* — a fabrication or a
  wrong result — is punished with ``-c``. Raising ``c`` makes the metric prefer a
  cautious abstention over a confident mistake.

Both are real Inspect metrics: ``@metric`` decorated, ``list[SampleScore] ->
Value``, no model call.

References (see ``METHODOLOGY.md`` for the full metric→paper table):

* Wilson score interval — Wilson (1927), JASA 22(158):209–212.
* TrustSQL reliability score (asymmetric ``-c`` penalty) — Lee et al. (2024),
  "TrustSQL: Benchmarking Text-to-SQL Reliability with Penalty-Based Scoring,"
  arXiv:2403.15879.
"""

from __future__ import annotations

from inspect_ai.scorer import (
    NOANSWER,
    Metric,
    SampleScore,
    Value,
    metric,
    value_to_float,
)

from .stats import wilson_ci

__all__ = ["wilson_accuracy", "reliability_score", "applicable_accuracy"]


@metric
def applicable_accuracy() -> Metric:
    """Accuracy over only the samples this scorer actually applied to.

    Inspect's built-in ``accuracy()`` counts ``NOANSWER`` in the denominator, so
    a scorer that correctly skips inapplicable samples (e.g. ``deterministic_ex``
    returning ``NOANSWER`` for non-``answer`` buckets) reads as ``0.000`` on a
    single-bucket suite even though every case it applied to passed. This metric
    excludes ``NOANSWER`` from both numerator and denominator, so the raw
    ``inspect eval`` summary line matches the framework's bucket-aware ``Report``.
    Returns ``0.0`` when the scorer applied to nothing (all NOANSWER).
    """
    to_float = value_to_float()

    def metric_fn(scores: list[SampleScore]) -> Value:
        applicable = [s for s in scores if s.score.value != NOANSWER]
        if not applicable:
            return 0.0
        return sum(to_float(s.score.value) for s in applicable) / len(applicable)

    return metric_fn


@metric
def wilson_accuracy(alpha: float = 0.05) -> Metric:
    """Accuracy reported as the lower bound of its Wilson score interval.

    Each applicable sample's value is mapped to correct/incorrect via the
    standard ``value_to_float`` (CORRECT→1.0, INCORRECT→0). ``NOANSWER``
    samples are excluded from both the count and ``n`` — matching
    ``applicable_accuracy`` — so a scorer that correctly skips inapplicable
    samples doesn't have those skips counted as failed trials, deflating the
    interval. The count of correct samples feeds
    :func:`nxd_eval.stats.wilson_ci`; the returned scalar is the interval's
    lower bound — the pass rate we can defend at ``1 - alpha`` confidence given
    the observed ``n``. The point estimate and both bounds are attached as
    metric metadata for the report.
    """
    to_float = value_to_float()

    def metric_fn(scores: list[SampleScore]) -> Value:
        applicable = [s for s in scores if s.score.value != NOANSWER]
        n = len(applicable)
        if n == 0:
            return 0.0
        count = int(round(sum(to_float(s.score.value) for s in applicable)))
        ci = wilson_ci(count, n, alpha=alpha)
        # Gate on the lower bound; the point estimate cannot be claimed above
        # what the sample size supports.
        return ci.low

    return metric_fn


@metric
def reliability_score(c: float = 1.0) -> Metric:
    """TrustSQL-style reliability score with an asymmetric wrong-answer penalty.

    Per sample, read the abstain scorer's routing metadata (``feasible`` and
    ``abstained``) plus its correct/incorrect verdict, and award:

    * feasible question, answered correctly ................ ``+1``
    * infeasible question, correctly abstained ............. ``+1``
    * abstained when an answer was possible (over-caution) .. ``0``
    * answered wrongly / fabricated (a confident mistake) ... ``-c``

    The mean over samples is the reliability score. With ``c = 1`` a fabrication
    fully cancels a correct answer; larger ``c`` makes the metric strictly prefer
    a safe abstention to a confident error — the TrustSQL reliability posture.
    """
    to_float = value_to_float()

    def metric_fn(scores: list[SampleScore]) -> Value:
        n = len(scores)
        if n == 0:
            return 0.0

        total = 0.0
        for s in scores:
            meta = s.score.metadata or {}
            feasible = bool(meta.get("feasible", True))
            abstained = bool(meta.get("abstained", False))
            correct = to_float(s.score.value) >= 1.0

            if abstained:
                # A refusal: rewarded only when the question was genuinely
                # infeasible; over-caution on a feasible question earns nothing,
                # but is never punished.
                total += 1.0 if not feasible else 0.0
            elif correct:
                # An answer that the scorer judged right.
                total += 1.0
            else:
                # An answer that was wrong (a fabrication or a wrong result) —
                # the asymmetric penalty.
                total += -c

        return total / n

    return metric_fn
