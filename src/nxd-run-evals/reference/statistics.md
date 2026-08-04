# The statistics contract

## Contents

- [The one idea: gate the lower bound, not the mean](#the-one-idea-gate-the-lower-bound-not-the-mean)
- [Wilson score interval](#wilson-score-interval)
- [Required-N table](#required-n-table)
- [Design effect and effective N](#design-effect-and-effective-n)
- [Reliability score](#reliability-score)
- [Calibration: Brier, ECE, AURC](#calibration-brier-ece-aurc)
- [Paired comparison: McNemar + BH-FDR](#paired-comparison-mcnemar--bh-fdr)
- [Reading `certify` verdicts](#reading-certify-verdicts)

The math lives in `evals/nxd_eval/src/nxd_eval/stats.py` and is covered by
`tests/test_stats.py`, which asserts the exact numbers quoted below. Everything is
BSD-licensed (`statsmodels` / `scipy` / `scikit-learn`) plus three small
hand-rolls (deff, ECE, AURC) — no GPL dependency.

## The one idea: gate the lower bound, not the mean

A raw pass rate lies about small samples: 9/10 = 90% looks like it clears a 90%
bar, but you could not defend "at least 90%" — the true rate could easily be 70%.
`certify` gates on the **lower bound of a Wilson confidence interval**. A change
passes only when even the pessimistic end of the interval clears the target. This
is the whole posture of the harness: you may claim only the number the sample
size actually supports.

## Wilson score interval

`statsmodels.stats.proportion.proportion_confint(count, nobs, alpha=0.05,
method='wilson')`. The Wilson interval is asymmetric near 0 and 1 (unlike the
naive Wald `p ± z·√(p(1-p)/n)`), which is exactly why it's used — the Wald bound
overstates the lower reach near a high pass rate.

Worked numbers the tests assert:

- p̂ = 0.90, n = 140 → half-width **±0.050**.
- p̂ = 0.98, n = 140 → **[0.939, 0.993]** — note it is *asymmetric* about 0.98
  (the interval is pulled toward the interior).

## Required-N table

The smallest n whose Wilson half-width ≤ target, at p = 0.90:

| Target half-width | Required n |
|---|---|
| ±5% | **138** |
| ±3% | **384** |
| ±2% | **864** |

This is why "~140 questions for ±5%" is the rule of thumb. Tighter claims cost
super-linearly more evidence. These are counts of **independent** questions — see
effective N below for what happens when they aren't independent.

## Design effect and effective N

Repeated epochs of one question, and near-duplicate templated questions, are
**correlated** — they don't each contribute a full independent data point. The
design effect quantifies the loss:

```
deff = 1 + (m - 1) · ICC
```

where `m` is the average cluster size (e.g. epochs per question) and `ICC` is the
intra-cluster correlation. Worked numbers the tests assert:

- m = 5,  ICC = 0.2 → deff = **1.80**
- m = 10, ICC = 0.3 → deff = **3.70**

The **effective sample size** is `N_eff = N / deff`, and the Wilson interval is
computed on `N_eff`, not the raw row count. So 140 rows that are really 28
templates × 5 epochs at ICC = 0.2 give `deff = 1.8`, `N_eff ≈ 78` — well short of
the 138 needed for ±5%, and `certify` will **REFUSE**. The KPI card prints
`N_eff`, `deff`, `icc`, and `m` so the discount is visible.

## Reliability score

A TrustSQL-style reliability score (`nxd_eval.metrics.reliability_score`, mirrored
in the report). Per sample: a correct answer scores `+1`, a correct abstention on
an infeasible question also scores `+1` (refusing was right), and a **confident
wrong answer** scores `-c`. The mean over samples is the reliability score.

The wrong-answer penalty `c` is a dial:

- `c = 0` — reliability equals plain accuracy (no fabrication penalty).
- `c = 1` — a fabrication costs as much as a correct answer earns; a safe
  abstention scores strictly above a confident error.
- `c = 2` — fabrication is penalized double.

A high accuracy with a low `c=1` reliability is a red flag: the agent is
fabricating on the questions it should have refused. The card prints all three.

## Calibration: Brier, ECE, AURC

When the agent emits a confidence, these measure whether the confidence is honest:

- **Brier** — `sklearn.metrics.brier_score_loss(y_true, y_prob)`; mean squared
  error of the confidence against correctness. Lower is better.
- **Reliability curve** — `sklearn.calibration.calibration_curve`.
- **ECE** (expected calibration error) — a hand-roll over the calibration bins:
  `Σ (bin_weight · |acc_bin − conf_bin|)`. The gap between claimed and actual
  accuracy, weighted by how many samples land in each confidence bin.
- **AURC** (area under the risk–coverage curve) — a hand-roll: sort samples by
  confidence descending, sweep coverage from high-confidence to low, integrate the
  error rate. Low AURC means the agent's confidence usefully ranks its correct
  answers ahead of its wrong ones (good selective prediction).

## Paired comparison: McNemar + BH-FDR

To compare two variants (`current_pack` vs `no_skills`) **on the same cases**, a
paired test is correct — an unpaired proportion test throws away the pairing.

- **McNemar** — `statsmodels.stats.contingency_tables.mcnemar` on the 2×2
  discordant table (cases one variant got right and the other wrong). It tests
  whether the *net* swing (regressions vs recoveries) is significant, ignoring the
  cases both variants agree on.
- **BH-FDR** — `statsmodels.stats.multitest.multipletests(pvals,
  method='fdr_bh')`. When you test many buckets / suites at once, Benjamini–
  Hochberg controls the false-discovery rate so you don't cry "regression" on
  noise from running many comparisons.

`certify --baseline <old>.eval` prints, per bucket, the accuracy delta, the raw
McNemar p, and the BH-FDR-adjusted p, and flags a bucket as a regression only when
the adjusted p < 0.05 **and** the delta is negative.

## Reading `certify` verdicts

| Verdict | Meaning | What to do |
|---|---|---|
| **PASS** | Wilson lower bound ≥ target. | Claim the number. |
| **FAIL** | Wilson lower bound below target — the point estimate either misses the target outright, or clears it while the lower bound does not. | The change didn't earn the claim at this confidence; improve the agent or accept a lower target. |
| **REFUSE** | Observed half-width on `N_eff` exceeds `--halfwidth` — insufficient N. | Grow the suite with *distinct* questions (not more epochs) and re-run. |

Gate grammar: `--gate 'accuracy>=0.90'` gates overall accuracy;
`--gate 'abstain>=0.95'` (or `answer` / `clarify`) gates one bucket. `--confidence
0.95` sets the interval (alpha = 1 − confidence). `--halfwidth 0.05` sets the
REFUSE threshold. `--json` emits the full report before the verdict.
