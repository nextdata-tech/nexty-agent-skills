# nxd_eval methodology

Every headline number in an nxd_eval report traces to a published method. The
code names techniques by their eponym ("Wilson interval", "TrustSQL-style
reliability", "pass^k"); this page is the one place those eponyms resolve to a
citation. It also records one honest limitation of our execution-accuracy scorer
(the *equivalence bound*, below).

All references are to public papers (arXiv / ACL Anthology / DOI). Nothing here
depends on internal trackers.

## Metric → source

| Metric (code symbol) | Where | Source |
|---|---|---|
| Wilson score interval on a pass rate — `wilson_ci`, `wilson_accuracy` | `stats.py`, `metrics.py` | Wilson, E. B. (1927). "Probable Inference, the Law of Succession, and Statistical Inference." *JASA* 22(158): 209–212. DOI:10.1080/01621459.1927.10502953 |
| Reliability score with asymmetric wrong-answer penalty `-c` — `reliability_score`, `_reliability` | `metrics.py`, `report.py` | Lee et al. (2024), "TrustSQL: Benchmarking Text-to-SQL Reliability with Penalty-Based Scoring." arXiv:2403.15879 |
| Design effect `deff = 1 + (m-1)·ICC` and effective sample size `n_eff` — `design_effect`, `n_eff` | `stats.py` | Kish, L. (1965). *Survey Sampling*. Wiley. (The `deff` / effective-N deflation for correlated observations.) |
| ICC(1), one-way random-effects intra-cluster correlation — `_icc_oneway` | `report.py` | Shrout, P. E. & Fleiss, J. L. (1979). "Intraclass correlations: uses in assessing rater reliability." *Psychological Bulletin* 86(2): 420–428. DOI:10.1037/0033-2909.86.2.420 |
| McNemar paired-binary test for baseline vs. current — `mcnemar_paired` | `stats.py` | McNemar, Q. (1947). "Note on the sampling error of the difference between correlated proportions or percentages." *Psychometrika* 12(2): 153–157. DOI:10.1007/BF02295996 |
| Benjamini–Hochberg FDR control across per-bucket p-values — `bh_fdr`, `regression_against` | `stats.py`, `report.py` | Benjamini, Y. & Hochberg, Y. (1995). "Controlling the False Discovery Rate." *JRSS-B* 57(1): 289–300. DOI:10.1111/j.2517-6161.1995.tb02031.x |
| Brier score for confidence calibration — `brier` | `stats.py` | Brier, G. W. (1950). "Verification of forecasts expressed in terms of probability." *Monthly Weather Review* 78(1): 1–3. DOI:10.1175/1520-0493(1950)078<0001:VOFEIT>2.0.CO;2 |
| Expected Calibration Error (ECE), binned reliability gap — `ece` | `stats.py` | Naeini, Pakdaman M., Cooper, G. & Hauskrecht, M. (2015). "Obtaining Well Calibrated Probabilities Using Bayesian Binning." *AAAI 2015*. (Binned-ECE definition; see also Guo et al. 2017, arXiv:1706.04599, for the neural-net-era formulation we mirror.) |
| Area Under the Risk–Coverage curve (AURC) / selective prediction — `aurc` | `stats.py` | Geifman, Y. & El-Yaniv, R. (2017). "Selective Classification for Deep Neural Networks." *NeurIPS 2017*. arXiv:1705.08500. (Risk–coverage curve; El-Yaniv & Wiener 2010, *JMLR* 11, is the original selective-prediction framing.) |
| pass^k — fraction of clusters that pass on *every* epoch — `_pass_at_k` | `report.py` | Kulal et al. (2019), "SPoC: Search-based Pseudocode to Code" (arXiv:1906.04908) introduces pass@k; Chen et al. (2021), "Evaluating Large Language Models Trained on Code" (arXiv:2107.03374) popularizes it. Our `pass^k` is the strict all-epochs-pass variant. |
| Gwet AC1 for judge/annotator reliability | judge-reliability reporting (methodology-level; no code symbol yet) | Gwet, K. L. (2008). "Computing inter-rater reliability and its variance in the presence of high agreement." *British Journal of Mathematical and Statistical Psychology* 61(1): 29–48. DOI:10.1348/000711006X126600 |

Notes on non-obvious choices:

- **Wilson over Wald.** The pass-rate gate always uses the Wilson score interval,
  never the normal-approximation (Wald) interval, which under-covers and can
  escape `[0, 1]` at small `n` or extreme `p`. The unit tests assert the Wilson
  asymmetry precisely to catch a silent swap to Wald.
- **Effective N.** Epochs (repeats of a case) and cases sharing a `cluster` key
  are correlated, so raw `n` overstates the information. We deflate by the Kish
  design effect using an ICC(1) estimated from the 0/1 pass outcomes, then widen
  the Wilson interval on `n_eff = n / deff`.
- **Reliability score.** Correctly answering a feasible question or correctly
  abstaining on an infeasible one earns `+1`; a silent miss earns `0`; a wrong
  answer (fabrication or wrong result) is penalized `-c`. Sweeping `c ∈ {0,1,2}`
  is the TrustSQL posture: higher `c` prefers a cautious abstention over a
  confident mistake.

## Execution-accuracy lineage

Our deterministic execution-accuracy (EX) scorer compares an agent's result
rows to a frozen gold result set. This is the test-based / result-comparison
family of text-to-SQL evaluation, whose known failure mode and mitigations are:

- **SpotIt** — Klopfenstein et al. (2025), "SpotIt: Evaluating Text-to-SQL Evaluation
  with Formal Verification." arXiv:2510.26840. Uses SMT-backed *bounded
  equivalence* to catch queries that agree on the benchmark database but differ
  in general; reports an **11–14% EX overestimate on BIRD** relative to formal
  equivalence.
- **Distilled test suites** — Zhong, R., Yu, T. & Klein, D. (2020), "Semantic
  Evaluation for Text-to-SQL with Distilled Test Suites." *EMNLP 2020*
  (arXiv:2010.02840). Bounds the *false-negative* side of single-database
  comparison: a distilled multi-database test suite leaves a residual
  **2.5% average / 8.1% worst-case** gap on Spider.

Together these two set the empirical envelope for how far a single-result EX
check can drift from true semantic equivalence.

## The EX equivalence bound (and why we are less exposed)

**Test-based EX on a single frozen result is optimistic.** Two SQL queries can
return identical rows on one frozen database yet be non-equivalent in general
(differ on some other data instance). Comparing agent rows to a single frozen
gold therefore *over-credits*: it counts a coincidental match on the frozen
instance as a correct query. SpotIt quantifies this on BIRD at 11–14% EX
overestimate; Zhong et al. bound the reverse (false-negative) error of
single-database comparison at 2.5% average / 8.1% worst-case on Spider. We
inherit this bound and do **not** run a bounded-equivalence verifier — this is a
documented limitation, not a solved problem.

**Why our architecture is less exposed than raw text-to-SQL.** In nxd_eval the
agent does not emit free-form SQL that we then execute and compare. The
selection → SQL layer is **deterministic**: a fixed compiler turns the agent's
structured selection into SQL, so there is no space for two arbitrary,
semantically different SQL strings to be judged equal. The residual exposure is
confined to the final frozen-gold **row comparison** — the compiler removes the
query-diversity degree of freedom that drives most of the SpotIt/Zhong gap. The
`matches_compiler` axis further checks the agent's rows against the compiler's
own executed rows, so a coincidental frozen-gold match that the compiler would
not have produced is still visible. The bound above is thus an upper limit on
our exposure, and in practice narrower.

See `_ex_core/score.py` for the row-comparison implementation and the same note
in situ.
