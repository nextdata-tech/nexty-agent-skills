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
"""

from __future__ import annotations

from inspect_ai.scorer import (
    Metric,
    SampleScore,
    Value,
    metric,
    value_to_float,
)

from .stats import wilson_ci

__all__ = ["wilson_accuracy", "reliability_score"]


@metric
def wilson_accuracy(alpha: float = 0.05) -> Metric:
    """Accuracy reported as the lower bound of its Wilson score interval.

    Each sample's value is mapped to correct/incorrect via the standard
    ``value_to_float`` (CORRECT→1.0, INCORRECT→0). The count of correct samples
    feeds :func:`nxd_eval.stats.wilson_ci`; the returned scalar is the interval's
    lower bound — the pass rate we can defend at ``1 - alpha`` confidence given
    the observed ``n``. The point estimate and both bounds are attached as
    metric metadata for the report.
    """
    to_float = value_to_float()

    def metric_fn(scores: list[SampleScore]) -> Value:
        n = len(scores)
        if n == 0:
            return 0.0
        count = int(round(sum(to_float(s.score.value) for s in scores)))
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
