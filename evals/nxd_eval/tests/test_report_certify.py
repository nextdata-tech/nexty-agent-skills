"""Report roll-up + certification gate — the read side of the framework.

These tests build synthetic Inspect eval logs (no model, no MCP, no key) with
known pass patterns and assert:

* per-bucket Wilson CIs land on the effective sample size (a clustered log gets a
  wider interval than the same rate spread across independent cases);
* the certify gate keys on the Wilson LOWER bound, not the point estimate — a run
  whose mean clears the target but whose lower bound does not must FAIL, while a
  run with a genuinely high lower bound PASSES;
* an underpowered run REFUSES with an insufficient-N verdict and a non-zero exit
  code, rather than emitting a pass/fail its sample cannot support.

The synthetic log is the real ``EvalLog`` type written to and read back from disk
via ``write_eval_log`` / ``read_eval_log``, so the on-disk path certify() uses in
production is exercised, not mocked.
"""

from __future__ import annotations

import math

import pytest
from inspect_ai.log import (
    EvalLog,
    EvalSample,
    EvalSpec,
    read_eval_log,
    write_eval_log,
)
from inspect_ai.scorer import Score

from nxd_eval.certify import CertifyResult, certify, parse_gate
from nxd_eval.report import Report

_EX = "deterministic_ex"
_ABS = "abstain_infeasible"


# --------------------------------------------------------------------------- #
# Synthetic-log builders
# --------------------------------------------------------------------------- #


def _spec() -> EvalSpec:
    return EvalSpec(
        created="2026-07-07",
        task="synthetic-suite",
        dataset={},
        model="mockllm/model",
        config={},
    )


def _sample(
    sample_id: str,
    *,
    epoch: int = 1,
    bucket: str = "answer",
    cluster: str | None = None,
    feasible: bool = True,
    passed: bool = True,
    abstained: bool = False,
) -> EvalSample:
    """One scored EvalSample with our routing metadata + the primary scorer."""
    scorer_name = _EX if bucket == "answer" else _ABS
    scores = {
        scorer_name: Score(
            value="C" if passed else "I",
            metadata={"feasible": feasible, "abstained": abstained},
        )
    }
    return EvalSample(
        id=sample_id,
        epoch=epoch,
        input="q",
        target="",
        metadata={
            "bucket": bucket,
            "cluster": cluster or sample_id,
            "feasible": feasible,
        },
        scores=scores,
    )


def _log(samples: list[EvalSample]) -> EvalLog:
    return EvalLog(eval=_spec(), samples=samples, status="success")


def _write(tmp_path, samples: list[EvalSample], name="run.eval") -> str:
    p = tmp_path / name
    write_eval_log(_log(samples), str(p))
    return str(p)


def _answer_samples(n: int, n_correct: int, *, bucket: str = "answer") -> list[EvalSample]:
    """``n`` independent (distinct-cluster) answer samples, ``n_correct`` passing."""
    out = []
    for i in range(n):
        out.append(_sample(f"{bucket}-{i}", bucket=bucket, passed=(i < n_correct)))
    return out


# --------------------------------------------------------------------------- #
# Report roll-up
# --------------------------------------------------------------------------- #


def test_report_per_bucket_counts_and_pointwise_accuracy():
    samples = (
        _answer_samples(10, 9, bucket="answer")
        + [
            _sample("cl-0", bucket="clarify", passed=True),
            _sample("cl-1", bucket="clarify", passed=False),
        ]
        + [
            _sample("ab-0", bucket="abstain", feasible=False, passed=True, abstained=True),
            _sample("ab-1", bucket="abstain", feasible=False, passed=False, abstained=False),
        ]
    )
    rep = Report.from_log(_log(samples))

    assert rep.cards["answer"].n == 10
    assert rep.cards["answer"].passed == 9
    assert math.isclose(rep.cards["answer"].p_hat, 0.9)
    assert rep.cards["clarify"].n == 2
    assert rep.cards["abstain"].passed == 1
    assert rep.overall.n == 14
    assert rep.overall.passed == 11


def test_report_independent_bucket_ci_matches_wilson_on_n():
    # 10 independent answer cases, all distinct clusters -> icc 0 -> deff 1 ->
    # N_eff == n, so the bucket CI equals the plain Wilson CI on n.
    rep = Report.from_log(_log(_answer_samples(10, 9)))
    from nxd_eval.stats import wilson_ci

    ref = wilson_ci(9, 10)
    card = rep.cards["answer"]
    assert math.isclose(card.eff.n_eff, 10.0, abs_tol=1e-9)
    assert math.isclose(card.eff.deff, 1.0, abs_tol=1e-9)
    assert math.isclose(card.ci.low, ref.low, abs_tol=1e-9)
    assert math.isclose(card.ci.high, ref.high, abs_tol=1e-9)


def test_clustered_repeats_widen_the_interval():
    # Same 20 observations, same 90% pass rate, two layouts:
    #  (a) 20 independent cases  -> N_eff == 20
    #  (b) 4 clusters x 5 epochs, correlated within cluster -> N_eff < 20
    # The clustered layout must yield a strictly wider Wilson interval, because
    # correlated repeats carry less information than independent draws.
    independent = _answer_samples(20, 18)

    clustered: list[EvalSample] = []
    # 4 clusters of 5 epochs; within a cluster all epochs agree (max correlation),
    # 18/20 pass overall: clusters pass/pass/pass/fail-ish. Build 3 all-pass
    # clusters (15) and one cluster 3/5 (to reach 18 correct) -> some within-var.
    layout = [5, 5, 5, 3]  # correct-per-cluster over 5 epochs each
    for ci, correct in enumerate(layout):
        for e in range(5):
            clustered.append(
                _sample(
                    f"cluster-{ci}",
                    epoch=e + 1,
                    cluster=f"cluster-{ci}",
                    passed=(e < correct),
                )
            )

    rep_ind = Report.from_log(_log(independent))
    rep_clu = Report.from_log(_log(clustered))

    assert math.isclose(rep_ind.cards["answer"].p_hat, rep_clu.cards["answer"].p_hat)
    # Clustering deflates N_eff and widens the interval.
    assert rep_clu.cards["answer"].eff.n_eff < rep_ind.cards["answer"].eff.n_eff
    assert rep_clu.cards["answer"].eff.deff > 1.0
    assert rep_clu.cards["answer"].ci.halfwidth > rep_ind.cards["answer"].ci.halfwidth


def test_reliability_and_governance_on_abstain_bucket():
    # 3 infeasible cases: two correctly abstained, one fabricated (answered wrong).
    samples = [
        _sample("ab-0", bucket="abstain", feasible=False, passed=True, abstained=True),
        _sample("ab-1", bucket="abstain", feasible=False, passed=True, abstained=True),
        _sample("ab-2", bucket="abstain", feasible=False, passed=False, abstained=False),
    ]
    rep = Report.from_log(_log(samples))
    card = rep.cards["abstain"]

    # Reliability at c: +1 per correct abstain, -c for the fabrication.
    assert math.isclose(card.reliability[0.0], (1 + 1 + 0) / 3)
    assert math.isclose(card.reliability[1.0], (1 + 1 - 1) / 3)
    assert math.isclose(card.reliability[2.0], (1 + 1 - 2) / 3)

    # Governance: 2 abstentions, both on infeasible cases -> precision 1.0;
    # 3 infeasible, 2 refused -> recall 2/3.
    assert math.isclose(card.governance_precision, 1.0)
    assert math.isclose(card.governance_recall, 2 / 3)


def test_pass_at_k_requires_every_epoch():
    # One cluster passes on both epochs, one flakes on one epoch.
    samples = [
        _sample("c0", epoch=1, cluster="c0", passed=True),
        _sample("c0", epoch=2, cluster="c0", passed=True),
        _sample("c1", epoch=1, cluster="c1", passed=True),
        _sample("c1", epoch=2, cluster="c1", passed=False),
    ]
    rep = Report.from_log(_log(samples))
    # 1 of 2 clusters passed on EVERY epoch.
    assert math.isclose(rep.cards["answer"].pass_at_k, 0.5)


# --------------------------------------------------------------------------- #
# Report emit
# --------------------------------------------------------------------------- #


def test_report_to_json_and_markdown_shapes():
    rep = Report.from_log(_log(_answer_samples(10, 9)))
    import json as _json

    doc = _json.loads(rep.to_json())
    assert doc["buckets"]["answer"]["n"] == 10
    assert "ci_low" in doc["buckets"]["answer"]
    assert doc["overall"]["passed"] == 9

    md = rep.to_markdown()
    assert "# nxd_eval report" in md
    assert "accuracy" in md
    assert "Wilson" in md


def test_report_regression_bh_fdr_delta():
    baseline = _log(_answer_samples(20, 19))  # 95%
    candidate = _log(_answer_samples(20, 14))  # 70%, a real drop
    rep_base = Report.from_log(baseline)
    rep_cand = Report.from_log(candidate)

    reg = rep_cand.regression_against(rep_base)
    ans = reg["answer"]
    assert ans.delta < 0  # candidate regressed
    assert 0.0 <= ans.mcnemar_p_adj <= 1.0
    # Corrected p is never smaller than the raw p (BH only inflates).
    assert ans.mcnemar_p_adj >= ans.mcnemar_p - 1e-9

    # It shows up in the JSON regression block too.
    import json as _json

    doc = _json.loads(rep_cand.to_json(baseline=rep_base))
    assert doc["regression"]["answer"]["delta"] < 0


# --------------------------------------------------------------------------- #
# Certify gate — the lower-bound contract
# --------------------------------------------------------------------------- #


def test_certify_passes_on_high_lower_bound(tmp_path):
    # 138/138 pass: p_hat 1.0, Wilson lower bound well above 0.90.
    path = _write(tmp_path, _answer_samples(140, 140))
    res = certify(path, target=0.90, halfwidth=0.05)
    assert isinstance(res, CertifyResult)
    assert res.passed is True
    assert res.refused is False
    assert res.exit_code == 0
    assert res.ci_low >= 0.90


def test_certify_fails_when_point_estimate_passes_but_lower_bound_misses(tmp_path):
    # THE contract: p_hat clears 0.90 but the Wilson lower bound does not, on a
    # sample big enough to bound the margin (half-width <= 0.05). Must FAIL, not
    # pass — proving the gate keys on the lower bound, not the mean.
    #
    # 130/140 = 0.9286 point estimate (> 0.90), Wilson 95% lower bound ~= 0.872
    # (< 0.90), half-width ~= 0.042 (<= 0.05 -> not a refusal).
    path = _write(tmp_path, _answer_samples(140, 130))
    res = certify(path, target=0.90, halfwidth=0.05)

    assert res.p_hat > 0.90, "guard: point estimate must clear the target"
    assert res.ci_low < 0.90, "guard: lower bound must miss the target"
    assert res.refused is False, "sample is powered enough — this is a fail, not a refusal"
    assert res.passed is False
    assert res.exit_code != 0
    assert "lower bound" in res.reason


def test_certify_refuses_on_insufficient_n(tmp_path):
    # 9/10 pass: p_hat 0.90, but the Wilson half-width on n=10 is ~0.25, far
    # wider than the +/-0.05 margin. The gate cannot bound the pass rate -> it
    # REFUSES (insufficient N) with a non-zero exit code.
    path = _write(tmp_path, _answer_samples(10, 9))
    res = certify(path, target=0.90, halfwidth=0.05)

    assert res.refused is True
    assert res.passed is False
    assert res.exit_code != 0
    assert "insufficient n" in res.reason.lower()
    assert res.detail["observed_halfwidth"] > 0.05


def test_certify_refuses_on_empty_bucket(tmp_path):
    path = _write(tmp_path, _answer_samples(10, 9))  # no abstain cases
    res = certify(path, target=0.90, halfwidth=0.5, bucket="abstain")
    assert res.refused is True
    assert res.n == 0
    assert "insufficient" in res.reason.lower()


def test_certify_reads_from_disk_roundtrip(tmp_path):
    # Prove the log actually round-trips disk before certify reads it.
    path = _write(tmp_path, _answer_samples(140, 140))
    rl = read_eval_log(path)
    assert rl.status == "success"
    assert len(rl.samples) == 140
    res = certify(path, target=0.90, halfwidth=0.05)
    assert res.passed


def test_certify_rejects_non_wilson_method(tmp_path):
    path = _write(tmp_path, _answer_samples(140, 140))
    with pytest.raises(ValueError, match="Wilson"):
        certify(path, method="wald")


# --------------------------------------------------------------------------- #
# Gate expression parsing
# --------------------------------------------------------------------------- #


def test_parse_gate_overall_and_bucket():
    g = parse_gate("accuracy>=0.90")
    assert g.bucket is None
    assert math.isclose(g.target, 0.90)

    gb = parse_gate("abstain>=0.95")
    assert gb.bucket == "abstain"
    assert math.isclose(gb.target, 0.95)


def test_parse_gate_rejects_garbage():
    with pytest.raises(ValueError):
        parse_gate("accuracy~0.9")
    with pytest.raises(ValueError):
        parse_gate("nonsense>=0.5")
