"""The Inspect ``@metric`` wrappers surface the stats numbers without a model call.

``wilson_accuracy`` reports the Wilson lower bound (a run cannot claim a rate its
sample size does not support); ``reliability_score`` applies the TrustSQL
asymmetric penalty over the abstain scorer's feasible/abstained metadata.
"""

from __future__ import annotations

import math

from inspect_ai.scorer import CORRECT, INCORRECT, SampleScore, Score

from nxd_eval import stats as S
from nxd_eval.metrics import reliability_score, wilson_accuracy


def _sample(value: str, **meta) -> SampleScore:
    return SampleScore(
        score=Score(value=value, metadata=meta or None),
        sample_id="s",
    )


# --------------------------------------------------------------------------- #
# wilson_accuracy
# --------------------------------------------------------------------------- #


def test_wilson_accuracy_reports_lower_bound():
    m = wilson_accuracy()
    scores = [_sample(CORRECT)] * 126 + [_sample(INCORRECT)] * 14  # 126/140
    got = m(scores)
    expected = S.wilson_ci(126, 140).low
    assert math.isclose(got, expected, abs_tol=1e-9)
    # The lower bound is strictly below the naive point estimate.
    assert got < 126 / 140


def test_wilson_accuracy_empty_is_zero():
    assert wilson_accuracy()([]) == 0.0


# --------------------------------------------------------------------------- #
# reliability_score (TrustSQL asymmetric penalty)
# --------------------------------------------------------------------------- #


def test_reliability_rewards_correct_feasible_answer():
    m = reliability_score(c=1.0)
    scores = [_sample(CORRECT, feasible=True, abstained=False)]
    assert m(scores) == 1.0


def test_reliability_rewards_correct_infeasible_abstention():
    m = reliability_score(c=1.0)
    scores = [_sample(CORRECT, feasible=False, abstained=True)]
    assert m(scores) == 1.0


def test_reliability_over_caution_is_zero_not_penalized():
    m = reliability_score(c=2.0)
    # Abstained on a feasible question: no reward, but no penalty.
    scores = [_sample(INCORRECT, feasible=True, abstained=True)]
    assert m(scores) == 0.0


def test_reliability_penalizes_fabrication_asymmetrically():
    # A wrong answer on a feasible question is punished by -c.
    scores = [_sample(INCORRECT, feasible=True, abstained=False)]
    assert reliability_score(c=1.0)(scores) == -1.0
    assert reliability_score(c=3.0)(scores) == -3.0


def test_reliability_larger_c_prefers_abstention_over_error():
    # One correct + one confident error vs one correct + one safe abstention.
    error_run = [
        _sample(CORRECT, feasible=True, abstained=False),
        _sample(INCORRECT, feasible=True, abstained=False),
    ]
    abstain_run = [
        _sample(CORRECT, feasible=True, abstained=False),
        _sample(INCORRECT, feasible=True, abstained=True),
    ]
    c = 2.0
    assert reliability_score(c)(abstain_run) > reliability_score(c)(error_run)


def test_reliability_empty_is_zero():
    assert reliability_score()([]) == 0.0
