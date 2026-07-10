"""Post-process an Inspect eval log into a KPI report + a certification gate.

This is the read side of the framework. An eval run writes a ``.eval`` log; this
module reads it back (``read_eval_log``), flattens every scored sample into a
tidy row, and rolls those rows up into a :class:`Report`. A report carries, per
answer bucket (``answer`` / ``clarify`` / ``abstain``):

* a Wilson confidence interval on the accuracy, computed on the *effective*
  sample size ``N_eff`` — repeats of the same case (epochs, or several cases
  sharing a ``cluster`` key) are correlated, so the raw ``n`` overstates the
  information and the interval is widened by the design effect ``deff`` estimated
  from the clustering;
* the Reliability Score at penalties ``c ∈ {0, 1, 2}`` (TrustSQL posture);
* governance precision / recall — how well the agent refuses the infeasible
  cases without wrongly refusing feasible ones;
* ``pass^k`` — the fraction of clusters that pass on *every* epoch;
* calibration / selective-prediction quality over the answered samples that
  carry a verbalized confidence: Brier score, Expected Calibration Error (ECE),
  and the Area Under the Risk–Coverage curve (AURC). The confidence is the
  agent's calibrated self-report (QA-Calibration, ICLR 2025); pairing it with
  the 0/1 correctness outcome turns the binary abstain rate into a
  risk-coverage view (Geifman & El-Yaniv, "Selective Classification for Deep
  Neural Networks", NeurIPS 2017). Absent confidences ⇒ the block is omitted,
  never a crash.

``Report.to_markdown`` / ``Report.to_json`` emit the cards. Against a
``--baseline`` report, :meth:`Report.regression_against` reports the per-bucket
accuracy delta and a BH-FDR-corrected McNemar p-value per bucket, so a noisy
single-bucket wobble does not read as a real regression.

The numbers all come from :mod:`nxd_eval.stats`; nothing statistical is
re-derived here.
"""

from __future__ import annotations

import json
import math
import statistics
from collections import defaultdict
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path

from .stats import ConfidenceInterval
from .stats import aurc
from .stats import bh_fdr
from .stats import brier
from .stats import cohen_kappa
from .stats import design_effect
from .stats import ece
from .stats import gwet_ac1
from .stats import mcnemar_paired
from .stats import wilson_ci

# The three answer buckets, in report order. A sample's bucket rides in Sample
# metadata under "bucket" (set by the task layer from Case.expect).
BUCKETS = ("answer", "clarify", "abstain")

# The deterministic verdict scorer whose CORRECT/INCORRECT drives the headline
# accuracy. Kept in lockstep with scorers.DETERMINISTIC_EX; imported lazily-free
# as a literal so report.py has no import cycle with scorers.py.
_EX_SCORER = "deterministic_ex"
_ABSTAIN_SCORER = "abstain_infeasible"
_JUDGE_SCORER = "judge"

# Inspect encodes Score.value as single-letter grades for the categorical
# scorers we use: CORRECT="C", INCORRECT="I", NOANSWER="N", PARTIAL="P".
_CORRECT = "C"


# --------------------------------------------------------------------------- #
# Row model — one scored sample-epoch, flattened out of the eval log
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class SampleRow:
    """One scored ``(sample_id, epoch)`` pair, flattened from the eval log.

    ``passed`` is the primary correctness verdict for this sample. For an
    ``answer`` case it is the deterministic-EX scorer's CORRECT; for a
    ``clarify`` / ``abstain`` case it is the abstain/infeasible discriminator's
    CORRECT. ``feasible`` / ``abstained`` come from the abstain scorer's
    metadata and drive the reliability + governance numbers.
    """

    sample_id: str
    epoch: int
    bucket: str
    cluster: str
    feasible: bool
    passed: bool
    abstained: bool
    confidence: float | None = None

    @property
    def key(self) -> str:
        """Cluster key used to group correlated repeats for the design effect."""
        return self.cluster


def _get_score(scores: dict, name: str):
    """Look up a scorer's Score by its short name, prefix-tolerantly.

    Inspect keys ``sample.scores`` by the scorer's registry name. That name is
    bare (``deterministic_ex``) when the scorers are imported as loose modules,
    but package-qualified (``nxd_eval/deterministic_ex``) once nxd_eval is
    installed as a wheel. Match the exact key first, then any key whose segment
    after the last ``/`` equals ``name`` — so the report reads the same whether
    it runs against a src checkout or the published package.
    """
    sc = scores.get(name)
    if sc is not None:
        return sc
    for key, val in scores.items():
        if key.rsplit("/", 1)[-1] == name:
            return val
    return None


def _verdict_correct(scores: dict, name: str) -> bool | None:
    """Was scorer ``name``'s value CORRECT? None if the scorer is absent."""
    sc = _get_score(scores, name)
    if sc is None:
        return None
    return _score_value(sc) == _CORRECT


def _score_value(sc) -> str:
    """The categorical value of a Score-like object from the eval log."""
    val = getattr(sc, "value", None)
    if val is None and isinstance(sc, dict):
        val = sc.get("value")
    return val


def _score_meta(sc) -> dict:
    """The metadata dict of a Score-like object from the eval log."""
    meta = getattr(sc, "metadata", None)
    if meta is None and isinstance(sc, dict):
        meta = sc.get("metadata")
    return meta or {}


def _confidence_of(meta: dict) -> float | None:
    """A finite verbalized confidence in ``[0, 1]`` from scorer metadata, else None."""
    val = meta.get("confidence")
    if val is None:
        return None
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    return max(0.0, min(1.0, f))


def _primary_passed(bucket: str, scores: dict) -> bool:
    """The correctness verdict for a sample given its bucket.

    ``answer`` cases are judged by deterministic-EX; ``clarify`` / ``abstain``
    cases by the abstain/infeasible discriminator. Falls back across the two so a
    suite that only attached one scorer still yields a verdict.
    """
    if bucket == "answer":
        primary, secondary = _EX_SCORER, _ABSTAIN_SCORER
    else:
        primary, secondary = _ABSTAIN_SCORER, _EX_SCORER
    v = _verdict_correct(scores, primary)
    if v is not None:
        return v
    v = _verdict_correct(scores, secondary)
    return bool(v)


def _rows_from_log(log) -> list[SampleRow]:
    """Flatten an ``EvalLog`` into one :class:`SampleRow` per scored sample-epoch."""
    rows: list[SampleRow] = []
    for s in log.samples or []:
        meta = s.metadata or {}
        bucket = meta.get("bucket", "answer")
        cluster = meta.get("cluster") or str(s.id)
        scores = s.scores or {}

        # feasible / abstained come from the abstain scorer's metadata when
        # present, else from the sample-level routing metadata.
        abstain_meta = _score_meta(_get_score(scores, _ABSTAIN_SCORER))
        feasible = bool(
            abstain_meta.get("feasible", meta.get("feasible", bucket != "abstain"))
        )
        abstained = bool(abstain_meta.get("abstained", False))

        # Verbalized confidence rides in the deterministic-EX scorer's metadata
        # for answered cases (scorers.py stamps it when the agent emitted a
        # CONFIDENCE line). Absent ⇒ None, and the sample contributes no
        # confidence pair to the calibration metrics.
        confidence = _confidence_of(_score_meta(_get_score(scores, _EX_SCORER)))

        rows.append(
            SampleRow(
                sample_id=str(s.id),
                epoch=int(getattr(s, "epoch", 1) or 1),
                bucket=bucket,
                cluster=str(cluster),
                feasible=feasible,
                passed=_primary_passed(bucket, scores),
                abstained=abstained,
                confidence=confidence,
            )
        )
    return rows


# --------------------------------------------------------------------------- #
# Judge test-retest reliability (Gwet AC1)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class JudgeReliability:
    """Test-retest reliability of the model judge over its C/P/I labels.

    Computed only when the run was executed with the opt-in judge-retest pass
    (``NXD_EVAL_JUDGE_RETEST``), which grades each sample twice with independent
    criteria orderings. ``ac1`` is Gwet's AC1 between the two label sets — stable
    under the concentrated marginals that make the judge axis cluster in a narrow
    band, where Cohen's kappa under-reports (the kappa paradox). ``kappa`` is
    carried alongside purely to expose that gap. ``None`` fields mean the retest
    pass was not run (no paired labels in the log). ``judge_present`` is True when
    at least one sample carried a judge Score — it separates "judge ran but the
    retest pass was off" (worth prompting for) from "no judge in this suite at all"
    (a pure deterministic run, where the retest hint would be misleading noise).
    """

    n_pairs: int
    ac1: float | None
    kappa: float | None
    percent_agreement: float | None
    judge_present: bool = False

    def to_dict(self) -> dict:
        return {
            "n_pairs": self.n_pairs,
            "ac1": self.ac1,
            "kappa": self.kappa,
            "percent_agreement": self.percent_agreement,
            "judge_present": self.judge_present,
        }


def _judge_retest_pairs(log) -> tuple[list[str], list[str]]:
    """Extract paired (grade_1, grade_2) judge labels from an eval log.

    Present only when the judge ran with the opt-in retest pass, which stamps both
    grades into the judge Score's metadata. Samples without both labels are
    skipped. Returns two aligned label vectors.
    """
    first: list[str] = []
    second: list[str] = []
    for s in log.samples or []:
        sc = _get_score(s.scores or {}, _JUDGE_SCORER)
        if sc is None:
            continue
        meta = _score_meta(sc)
        g1 = meta.get("grade_1")
        g2 = meta.get("grade_2")
        if g1 is None or g2 is None:
            continue
        first.append(str(g1))
        second.append(str(g2))
    return first, second


def _judge_present(log) -> bool:
    """True when at least one sample carries a judge Score.

    Distinguishes a suite that ran the model judge (retest merely off) from a pure
    deterministic run with no judge at all, so the report can suppress the
    retest-hint noise in the latter case.
    """
    for s in log.samples or []:
        if _get_score(s.scores or {}, _JUDGE_SCORER) is not None:
            return True
    return False


def _judge_reliability(log) -> JudgeReliability:
    """Gwet AC1 (and kappa, for contrast) of the judge's test-retest labels."""
    first, second = _judge_retest_pairs(log)
    n = len(first)
    present = _judge_present(log)
    if n == 0:
        return JudgeReliability(
            n_pairs=0,
            ac1=None,
            kappa=None,
            percent_agreement=None,
            judge_present=present,
        )
    agree = sum(1 for a, b in zip(first, second) if a == b) / n
    return JudgeReliability(
        n_pairs=n,
        ac1=gwet_ac1(first, second),
        kappa=cohen_kappa(first, second),
        percent_agreement=agree,
        judge_present=present,
    )


# --------------------------------------------------------------------------- #
# Effective-N estimation (design effect from cluster structure)
# --------------------------------------------------------------------------- #


def _icc_oneway(groups: list[list[float]]) -> float:
    """One-way ANOVA intra-cluster correlation over 0/1 pass outcomes.

    ICC(1) = (MSB - MSW) / (MSB + (m0 - 1) * MSW), the standard one-way random-
    effects estimator, clamped to ``[0, 1]``. With singleton clusters or no
    within-cluster variance it degenerates to 0 (uncorrelated), which makes the
    design effect 1 and leaves ``N_eff`` equal to ``n`` — the honest "no evidence
    of clustering" answer.
    """
    groups = [g for g in groups if g]
    k = len(groups)
    n_total = sum(len(g) for g in groups)
    if k <= 1 or n_total <= k:
        return 0.0

    grand = sum(sum(g) for g in groups) / n_total
    ssb = sum(len(g) * (statistics.fmean(g) - grand) ** 2 for g in groups)
    ssw = sum(sum((x - statistics.fmean(g)) ** 2 for x in g) for g in groups)

    df_b = k - 1
    df_w = n_total - k
    msb = ssb / df_b
    msw = ssw / df_w if df_w > 0 else 0.0

    # Average cluster size adjusted for unequal sizes (the classic m0 term).
    sizes = [len(g) for g in groups]
    m0 = (n_total - sum(s * s for s in sizes) / n_total) / (k - 1)
    if m0 <= 0:
        return 0.0

    denom = msb + (m0 - 1.0) * msw
    if denom <= 0:
        return 0.0
    icc = (msb - msw) / denom
    return max(0.0, min(1.0, icc))


@dataclass(frozen=True)
class EffectiveN:
    """Raw vs effective sample size for one group of correlated rows."""

    n: int
    n_eff: float
    m: float
    icc: float
    deff: float


def _effective_n(rows: list[SampleRow]) -> EffectiveN:
    """Effective sample size for ``rows`` after deflating by the design effect.

    Clusters are the ``cluster`` keys (a case + its epochs, or several cases the
    author grouped). ``m`` is the mean cluster size; ``icc`` is estimated from
    the 0/1 pass outcomes; ``deff = 1 + (m-1)*icc``; ``n_eff = n / deff``.
    """
    n = len(rows)
    if n == 0:
        return EffectiveN(n=0, n_eff=0.0, m=0.0, icc=0.0, deff=1.0)

    by_cluster: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        by_cluster[r.cluster].append(1.0 if r.passed else 0.0)

    sizes = [len(g) for g in by_cluster.values()]
    m = statistics.fmean(sizes) if sizes else 1.0
    icc = _icc_oneway(list(by_cluster.values()))
    deff = design_effect(m, icc)
    deff = deff if deff > 0 else 1.0
    return EffectiveN(n=n, n_eff=n / deff, m=m, icc=icc, deff=deff)


# --------------------------------------------------------------------------- #
# Calibration / selective-prediction quality
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Calibration:
    """Confidence-quality summary over answered samples carrying a confidence.

    ``n`` is the number of (correctness, confidence) pairs the metrics were
    computed over — always a subset of the bucket's rows, since a sample without
    a verbalized confidence contributes nothing here. Lower is better for all
    three: ``brier`` (mean squared error of confidence vs outcome), ``ece``
    (Expected Calibration Error), ``aurc`` (Area Under the Risk–Coverage curve).
    """

    n: int
    brier: float
    ece: float
    aurc: float

    def to_dict(self) -> dict:
        return {
            "n": self.n,
            "brier": self.brier,
            "ece": self.ece,
            "aurc": self.aurc,
        }


def _calibration(rows: list[SampleRow]) -> Calibration | None:
    """Brier / ECE / AURC over the rows that carry a confidence, else None.

    Builds the ``(correctness, confidence)`` pairs from every row whose
    ``confidence`` is present, then defers to the ``stats`` primitives. Returns
    ``None`` when no row carries a confidence — the report then omits the block
    cleanly rather than emitting a degenerate zero. Uses the agent's calibrated
    self-report (QA-Calibration, ICLR 2025) to build the risk-coverage view
    (Geifman & El-Yaniv, NeurIPS 2017).
    """
    y_true: list[int] = []
    y_prob: list[float] = []
    for r in rows:
        if r.confidence is None:
            continue
        y_true.append(1 if r.passed else 0)
        y_prob.append(float(r.confidence))
    if not y_prob:
        return None
    return Calibration(
        n=len(y_prob),
        brier=brier(y_true, y_prob),
        ece=ece(y_true, y_prob),
        aurc=aurc(y_true, y_prob),
    )


# --------------------------------------------------------------------------- #
# Per-bucket KPI card
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class BucketCard:
    """The KPI card for one answer bucket."""

    bucket: str
    n: int
    passed: int
    p_hat: float
    ci: ConfidenceInterval  # Wilson CI computed on N_eff
    eff: EffectiveN
    reliability: dict[float, float]  # c -> score
    pass_at_k: float  # fraction of clusters passing on every epoch
    governance_precision: float | None
    governance_recall: float | None
    calibration: Calibration | None = None  # None when no confidences present

    def to_dict(self) -> dict:
        out = {
            "bucket": self.bucket,
            "n": self.n,
            "passed": self.passed,
            "p_hat": self.p_hat,
            "ci_low": self.ci.low,
            "ci_high": self.ci.high,
            "ci_halfwidth": self.ci.halfwidth,
            "n_eff": self.eff.n_eff,
            "deff": self.eff.deff,
            "icc": self.eff.icc,
            "m": self.eff.m,
            "reliability": {str(k): v for k, v in self.reliability.items()},
            "pass_at_k": self.pass_at_k,
            "governance_precision": self.governance_precision,
            "governance_recall": self.governance_recall,
        }
        if self.calibration is not None:
            out["calibration"] = self.calibration.to_dict()
        return out


def _reliability(rows: list[SampleRow], c: float) -> float:
    """TrustSQL reliability score over ``rows`` at wrong-answer penalty ``c``.

    Mirrors :func:`nxd_eval.metrics.reliability_score`: a correct abstention on
    an infeasible case and a correct answer on a feasible case both earn ``+1``;
    an over-cautious abstention on a feasible case earns ``0``; a wrong answer /
    fabrication earns ``-c``.
    """
    if not rows:
        return 0.0
    total = 0.0
    for r in rows:
        if r.abstained:
            total += 1.0 if not r.feasible else 0.0
        elif r.passed:
            total += 1.0
        else:
            total += -c
    return total / len(rows)


def _pass_at_k(rows: list[SampleRow]) -> float:
    """Fraction of clusters that pass on *every* epoch (strict pass^k).

    Groups rows by cluster and marks a cluster passed only if all its epochs
    passed. With a single epoch this collapses to the plain pass rate over
    clusters.
    """
    by_cluster: dict[str, list[bool]] = defaultdict(list)
    for r in rows:
        by_cluster[r.cluster].append(r.passed)
    if not by_cluster:
        return 0.0
    all_pass = sum(1 for v in by_cluster.values() if all(v))
    return all_pass / len(by_cluster)


def _governance(rows: list[SampleRow]) -> tuple[float | None, float | None]:
    """Governance precision / recall of the abstain behaviour.

    Treats "the agent abstained" as the positive prediction and "the case was
    genuinely infeasible" as the positive label:

    * precision = infeasible-and-abstained / all-abstained — of the times it
      refused, how often it *should* have.
    * recall = infeasible-and-abstained / all-infeasible — of the cases it should
      have refused, how often it did.

    Returns ``None`` for a rate whose denominator is empty (no abstentions, or no
    infeasible cases in the group).
    """
    tp = sum(1 for r in rows if r.abstained and not r.feasible)
    predicted_pos = sum(1 for r in rows if r.abstained)
    actual_pos = sum(1 for r in rows if not r.feasible)
    precision = tp / predicted_pos if predicted_pos else None
    recall = tp / actual_pos if actual_pos else None
    return precision, recall


def _card(bucket: str, rows: list[SampleRow], *, alpha: float) -> BucketCard:
    """Build the KPI card for one bucket's rows."""
    n = len(rows)
    passed = sum(1 for r in rows if r.passed)
    p_hat = passed / n if n else 0.0
    eff = _effective_n(rows)

    # Wilson CI on the EFFECTIVE sample size: keep the observed rate but scale the
    # count/nobs down to n_eff so correlated repeats do not buy unearned
    # tightness. Round to the nearest integer nobs; the rate is preserved.
    nobs_eff = max(1, int(round(eff.n_eff)))
    count_eff = int(round(p_hat * nobs_eff))
    ci = wilson_ci(count_eff, nobs_eff, alpha=alpha)

    reliability = {c: _reliability(rows, c) for c in (0.0, 1.0, 2.0)}
    gp, gr = _governance(rows)
    return BucketCard(
        bucket=bucket,
        n=n,
        passed=passed,
        p_hat=p_hat,
        ci=ci,
        eff=eff,
        reliability=reliability,
        pass_at_k=_pass_at_k(rows),
        governance_precision=gp,
        governance_recall=gr,
        calibration=_calibration(rows),
    )


# --------------------------------------------------------------------------- #
# Regression delta vs a baseline
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class BucketDelta:
    """Per-bucket regression delta of this report vs a baseline."""

    bucket: str
    delta: float  # this p_hat - baseline p_hat
    p_this: float
    p_base: float
    mcnemar_p: float  # raw McNemar p-value
    mcnemar_p_adj: float  # BH-FDR-corrected across buckets
    b: int  # baseline-right, this-wrong (regressions)
    c: int  # this-right, baseline-wrong (recoveries)


# --------------------------------------------------------------------------- #
# The report
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Report:
    """A KPI report rolled up from one eval log."""

    suite: str
    variant: str
    alpha: float
    rows: list[SampleRow]
    cards: dict[str, BucketCard]
    overall: BucketCard
    judge_reliability: JudgeReliability = field(
        default_factory=lambda: JudgeReliability(
            n_pairs=0, ac1=None, kappa=None, percent_agreement=None
        )
    )
    log_path: str | None = None
    metadata: dict = field(default_factory=dict)

    # ---- construction ---- #

    @classmethod
    def from_log(
        cls,
        log,
        *,
        alpha: float = 0.05,
        suite: str | None = None,
        variant: str = "current_pack",
        log_path: str | None = None,
    ) -> "Report":
        """Build a report from an in-memory ``EvalLog``."""
        rows = _rows_from_log(log)
        cards = {
            b: _card(b, [r for r in rows if r.bucket == b], alpha=alpha)
            for b in BUCKETS
        }
        overall = _card("overall", rows, alpha=alpha)
        name = suite or _log_suite_name(log) or "suite"
        return cls(
            suite=name,
            variant=variant,
            alpha=alpha,
            rows=rows,
            cards=cards,
            overall=overall,
            judge_reliability=_judge_reliability(log),
            log_path=log_path,
        )

    @classmethod
    def from_path(
        cls,
        path: str | Path,
        *,
        alpha: float = 0.05,
        suite: str | None = None,
        variant: str = "current_pack",
    ) -> "Report":
        """Read a ``.eval`` log off disk and build a report."""
        from inspect_ai.log import read_eval_log

        p = str(path)
        log = read_eval_log(p)
        return cls.from_log(log, alpha=alpha, suite=suite, variant=variant, log_path=p)

    # ---- accuracy accessor certify() gates on ---- #

    def accuracy_ci(self, bucket: str | None = None) -> ConfidenceInterval:
        """The Wilson CI (on N_eff) for a bucket, or overall when bucket is None."""
        if bucket is None or bucket == "overall":
            return self.overall.ci
        if bucket not in self.cards:
            raise KeyError(f"unknown bucket {bucket!r}; have {sorted(self.cards)}")
        return self.cards[bucket].ci

    # ---- regression vs baseline ---- #

    def regression_against(self, baseline: "Report") -> dict[str, BucketDelta]:
        """Per-bucket regression delta vs ``baseline``, BH-FDR-corrected.

        For each bucket we pair samples on ``(sample_id, epoch)`` present in both
        reports and build the McNemar 2x2 discordant table (baseline-right/
        this-wrong vs this-right/baseline-wrong). The raw McNemar p-values across
        the buckets are Benjamini–Hochberg-corrected together so one bucket's
        chance wobble does not read as significant.
        """
        base_by_key = {(r.sample_id, r.epoch): r for r in baseline.rows}

        raw: list[tuple[str, float, int, int]] = []
        deltas_partial: dict[str, dict] = {}
        for b in BUCKETS:
            this_card = self.cards[b]
            base_card = baseline.cards.get(b)
            p_base = base_card.p_hat if base_card else 0.0

            a = bb = cc = d = 0
            for r in self.rows:
                if r.bucket != b:
                    continue
                base = base_by_key.get((r.sample_id, r.epoch))
                if base is None:
                    continue
                if base.passed and r.passed:
                    a += 1
                elif base.passed and not r.passed:
                    bb += 1  # regression: baseline right, now wrong
                elif not base.passed and r.passed:
                    cc += 1  # recovery: now right, baseline wrong
                else:
                    d += 1
            mp = mcnemar_paired(a, bb, cc, d).pvalue
            raw.append((b, mp, bb, cc))
            deltas_partial[b] = {
                "delta": this_card.p_hat - p_base,
                "p_this": this_card.p_hat,
                "p_base": p_base,
                "mcnemar_p": mp,
                "b": bb,
                "c": cc,
            }

        adj = bh_fdr([mp for _, mp, _, _ in raw])
        out: dict[str, BucketDelta] = {}
        for (b, _, _, _), padj in zip(raw, adj):
            dp = deltas_partial[b]
            out[b] = BucketDelta(
                bucket=b,
                delta=dp["delta"],
                p_this=dp["p_this"],
                p_base=dp["p_base"],
                mcnemar_p=dp["mcnemar_p"],
                mcnemar_p_adj=padj,
                b=dp["b"],
                c=dp["c"],
            )
        return out

    # ---- emit ---- #

    def to_json(self, *, baseline: "Report | None" = None, indent: int = 2) -> str:
        """Serialize the report (and an optional regression block) to JSON."""
        doc: dict = {
            "suite": self.suite,
            "variant": self.variant,
            "alpha": self.alpha,
            "confidence": round(1.0 - self.alpha, 6),
            "log_path": self.log_path,
            "n_samples": len(self.rows),
            "overall": self.overall.to_dict(),
            "buckets": {b: self.cards[b].to_dict() for b in BUCKETS},
            "judge_reliability": self.judge_reliability.to_dict(),
        }
        if baseline is not None:
            reg = self.regression_against(baseline)
            doc["baseline"] = {
                "suite": baseline.suite,
                "variant": baseline.variant,
                "log_path": baseline.log_path,
            }
            doc["regression"] = {
                b: {
                    "delta": d.delta,
                    "p_this": d.p_this,
                    "p_base": d.p_base,
                    "mcnemar_p": d.mcnemar_p,
                    "mcnemar_p_adj": d.mcnemar_p_adj,
                    "regressions": d.b,
                    "recoveries": d.c,
                }
                for b, d in reg.items()
            }
        return json.dumps(doc, indent=indent, sort_keys=False)

    def to_markdown(self, *, baseline: "Report | None" = None) -> str:
        """Render the KPI cards (and optional regression table) as Markdown."""
        conf_pct = round((1.0 - self.alpha) * 100)
        lines: list[str] = []
        lines.append(f"# nxd_eval report — {self.suite} ({self.variant})")
        lines.append("")
        lines.append(
            f"{len(self.rows)} scored sample-epochs · {conf_pct}% Wilson CIs on N_eff"
        )
        lines.append("")

        # Overall card first, then per-bucket.
        for card in [self.overall] + [self.cards[b] for b in BUCKETS]:
            lines.extend(_card_markdown(card, conf_pct))
            lines.append("")

        judge_lines = _judge_markdown(self.judge_reliability)
        if judge_lines:
            lines.extend(judge_lines)
            lines.append("")

        if baseline is not None:
            lines.extend(_regression_markdown(self.regression_against(baseline)))
            lines.append("")

        return "\n".join(lines).rstrip() + "\n"


def _log_suite_name(log) -> str | None:
    """Best-effort suite/task name out of the eval log header."""
    ev = getattr(log, "eval", None)
    if ev is None:
        return None
    return getattr(ev, "task", None) or getattr(ev, "task_display_name", None)


def _fmt_pct(x: float | None) -> str:
    return "—" if x is None else f"{x * 100:.1f}%"


def _card_markdown(card: BucketCard, conf_pct: int) -> list[str]:
    title = "overall" if card.bucket == "overall" else card.bucket
    ci = card.ci
    eff = card.eff
    rel = card.reliability
    lines = [
        f"## {title}",
        "",
        f"- **accuracy** {card.passed}/{card.n} = {_fmt_pct(card.p_hat)}  "
        f"(Wilson {conf_pct}% CI [{_fmt_pct(ci.low)}, {_fmt_pct(ci.high)}] on "
        f"N_eff={eff.n_eff:.1f})",
        f"- **N_eff** {eff.n_eff:.1f} of {eff.n}  "
        f"(deff={eff.deff:.2f}, icc={eff.icc:.3f}, m={eff.m:.2f})",
        f"- **reliability** c=0 {rel[0.0]:+.3f} · c=1 {rel[1.0]:+.3f} · "
        f"c=2 {rel[2.0]:+.3f}",
        f"- **pass^k** {_fmt_pct(card.pass_at_k)}",
        f"- **governance** P={_fmt_pct(card.governance_precision)} · "
        f"R={_fmt_pct(card.governance_recall)}",
    ]
    cal = card.calibration
    if cal is not None:
        lines.append(
            f"- **calibration** (n={cal.n}) Brier {cal.brier:.3f} · "
            f"ECE {cal.ece:.3f} · AURC {cal.aurc:.3f}"
        )
    return lines


def _judge_markdown(jr: JudgeReliability) -> list[str]:
    """Render the judge test-retest reliability line.

    Reports Gwet AC1 (robust under the concentrated C/P/I marginals that make the
    judge axis cluster, where kappa under-reports) with kappa alongside for
    contrast. When the opt-in retest pass did not run there are no paired labels,
    so we say so rather than fabricate a coefficient — but only when a judge
    actually ran; a pure deterministic suite (no judge Score on any sample) omits
    the section entirely, since the retest hint would be misleading noise there.
    """
    if not jr.judge_present and (jr.n_pairs == 0 or jr.ac1 is None):
        return []
    lines = ["## judge reliability (test-retest)", ""]
    if jr.n_pairs == 0 or jr.ac1 is None:
        lines.append(
            "- not measured — run with `NXD_EVAL_JUDGE_RETEST=1` to grade each "
            "sample twice and report Gwet AC1"
        )
        return lines
    kappa_str = "—" if jr.kappa is None else f"{jr.kappa:+.3f}"
    lines.append(
        f"- **Gwet AC1** {jr.ac1:+.3f} · κ {kappa_str} · "
        f"agreement {_fmt_pct(jr.percent_agreement)} over {jr.n_pairs} paired "
        "gradings"
    )
    lines.append(
        "  - the two gradings differ only in criteria order, so this bounds the "
        "judge's order-sensitivity (over the samples whose order actually "
        "changed), not its full run-to-run noise"
    )
    return lines


def _regression_markdown(deltas: dict[str, BucketDelta]) -> list[str]:
    lines = [
        "## regression vs baseline",
        "",
        "| bucket | Δ accuracy | this | base | regressions | recoveries | "
        "McNemar p | BH-FDR p |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for b in BUCKETS:
        d = deltas.get(b)
        if d is None:
            continue
        sign = "+" if d.delta >= 0 else ""
        lines.append(
            f"| {b} | {sign}{d.delta * 100:.1f}pp | {_fmt_pct(d.p_this)} | "
            f"{_fmt_pct(d.p_base)} | {d.b} | {d.c} | {d.mcnemar_p:.3f} | "
            f"{d.mcnemar_p_adj:.3f} |"
        )
    return lines
