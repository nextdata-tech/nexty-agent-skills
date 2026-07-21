# Scenario: Add a Case to an Eval Suite and State the Pass Criterion

The eval runner provides a workspace containing an existing `nxd_eval` suite for
the `logistics-demo` data product, the catalog of the `shipments` model, the
backing seed data, and the printed report from the most recent run of that suite.

Task for the agent:

I own the `logistics-demo` eval suite (`suite.py`). Two things I need from you.

First, our transit-time metrics keep getting mixed up by the agent in production:
`transit_days_avg` and `transit_days_sum` are different numbers and people ask
for "transit time" without saying which they mean. Add coverage for that to the
suite. Use `describe_model-shipments.txt` for the model's metrics and dimensions,
and `shipments_seed.sql` for the backing data. Write the new case(s) into
`suite.py` — keep the existing five cases working.

Second, my VP wants a one-line status for the quarterly review. Our target is
"at least 90% accuracy, ±5%, at 95% confidence". The most recent run is in
`last-run-report.txt`. Write me the status line, say why the raw sample count
does or does not support the claim, plus a short note on what I'd have to do to
be able to make that claim if we can't make it today. Put all of that in a file
called `STATUS.md` at the root of the workspace.

Required artifacts from eval runner:

- `suite.py` — the existing five-case logistics-demo suite.
- `describe_model-shipments.txt` — the shipments model catalog.
- `shipments_seed.sql` — backing data with a complete service_tier rollup.
- `last-run-report.txt` — the KPI card from the most recent run.

Risks (what a skill-less agent gets wrong):

- Reports the 90% target as met, because the 90.6% point estimate clears it. The
  card deliberately no longer prints a confidence interval, so refusing the claim
  requires knowing to compute one on `N_eff`, not on the raw 96.
- Treats 96 sample-epochs as the sample size, missing that `N_eff=66.2` is the
  figure sizing arguments must use.
- Prescribes more epochs to grow the sample. Re-running the same 24 questions
  adds correlated repeats, not independent evidence; the fix is ~140 distinct
  stratified questions. This contrast lives only in the skill
  (`reference/statistics.md`, REFUSE row) and is the scenario's most
  skill-dependent judgement.
- Adds another `answer` case for transit time, resolving the ambiguity in the
  question text, instead of a `clarify` case that preserves it — and attaches a
  gold record to it, which is meaningless for a judge-graded clarify case.
