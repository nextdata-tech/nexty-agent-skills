---
id: 2026-09-21-ratio-metric-reduction-guidance
date: 2026-09-21
label: "nxd-generate-data-product: reject reduced row-level ratios"
plugin_version: 0.51.6
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — reject reduced row-level ratios

## Notes

The authenticated B3 run on the pre-fix pack reached retained review and
returned the blocking finding `campaign-cpa-metric-avg-of-ratios`: the closure
exposed per-campaign CPA through `Agg.AVG`, which produces the wrong aggregate
CPA. The fix makes the shipped guidance explicit: aggregate queries must use
additive numerator and denominator metrics, while a row-level ratio must stay
at its declared grain and must not be reduced.

No controlled after-arm is recorded. The post-fix live attempt was invalid
before the scenario started because the Claude provider session limit was
reached. Manufacturing a score from that incomplete run would make the
benchmark less trustworthy.

## Evidence

- `evals/tests/test_source_contract.py` — explicit regression coverage for the
  row-level-ratio reduction ban and additive-ratio guidance.
- `src/nxd-generate-data-product/reference/pre-capture-audit.md` — deterministic
  pre-capture rule for ratio grain and aggregate metrics.
