---
id: 2026-09-06-abstention-and-waiver-categories
date: 2026-09-06
label: "grade capability from what a live closure emits, and name the waivers"
plugin_version: 0.45.0
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — grade capability from what a live closure emits, and name the waivers

## Notes

Harness grading only. No skill under `src/` changes and no agent-visible
prompt changes, so no runnable public arm can distinguish it; the three
scenario edits are comments and a route-table declaration.

**Capability abstention.** `gate_capability_from_decisions` returned
not-examined when the closure implemented no shortfall metric and no
`nxd_decisions` rows existed. Once `crm-pipeline` declared a capability
manifest the gate became required, so that branch failed the run for the
correct behaviour: refuse the impossible metric, ship nothing, record nothing.
It also did not check what it appeared to — any unrelated decision row, about
the stage enum say, flipped the same closure to examined-and-passed, so the
effective rule was "abstention counts if the agent happened to write some
decision about something".

The gate's claim is narrow: no `impossible` or `proxy` column shipped without a
ruling. An agent that shipped no such column has satisfied it. The branch is
removed and the non-empty implementation-text guard above it becomes the only
not-examined path, so an absent or empty closure still cannot pass. Whether a
build really happened is the build gate's question, which `_pass_rule` requires
unconditionally and which is now harness-owned — making capability police it
too would rebuild the coupling this branch has been removing.

**The query waiver.** `query_answer_gold_not_declared` is decided from
`"answer" in scenario.gold`, read at load time, and already sets
`required=False`. It was rendering as `UNEXAMINED[...]`, which says the harness
could not look, when the truth is that the scenario does not stage a scoreable
answer. It joins `NOT_STAGED_CODES`, so it now reads `NOT-STAGED`, appears in
`waived_gates`, and reaches the qualification record. Presentation only:
`scoreable_max` and `pass_threshold` read `required`, which did not move.

**What was investigated and deliberately not changed.** Renaming the three
B-series gold keys from `pipeline`/`reconciliation` to `answer` — so their
query gate would score — was rejected on evidence. `_parse_gold` requires the
gold key set to equal the follow-up kind's `gold_keys`, so the rename raises at
load; the files are `{"rows": [...]}` objects while the query oracle requires a
bare row list; and `crm-pipeline`'s generated oracle does not contain the file
at all. More to the point, those rows are already graded — the follow-up kinds
read the key by name and compare them against the agent's evidence artifact, so
renaming would double-grade the same rows over a second channel. The scenario
files now say so where a reader will look.

**An off-contract ledger is not an ungoverned one.** `_metric_is_governed` binds
on `applies_to` and accepts only `confirmed`/`proposed`, while the live closures
wrote `decision_id,description,status,provenance` with `approved`/`settled`. The
first reading was that this is a false negative and the allowlist should widen.
It is not, and it should not.

The pack fixes the ledger vocabulary and enforces it: `derivation-plan.md`
declares `nxd_decisions` as `decision_id, status, provenance, ruling,
applies_to, detail` with `status` exactly one of
`confirmed`/`proposed`/`blocked`, and `self_check.py` phase D hard-fails a
closure whose ledger is missing either column or carries a value outside that
vocabulary (`policy.decisions_column_missing`,
`policy.decisions_value_out_of_vocab`). `approved` is the *blueprint* status
vocabulary (`dp_diagnostics.py` `STATUS_VALUES`) bleeding into the ruling
ledger — two vocabularies the pack keeps deliberately disjoint. Widening the
gate would make the eval pass a build the skill's own tripwire fails.

The verdict was already right; only the label was wrong.
`capability_shortfall_not_governed` reads as "the agent wrote no ruling", which
points a reader at the gate's allowlist instead of at the skill.
`_ledger_contract_breaches` now classifies a non-empty ledger against the same
two vocabularies phase D uses (copied, not imported, with a comment naming that
file as the source of truth) plus the presence of `applies_to`, the field that
binds a ruling to columns. A breach yields one
`capability_decisions_off_contract` finding for the closure and skips the
per-metric loop, so one defect is not charged once per metric.
`_metric_is_governed` is unchanged — a row without `applies_to` never reaches
it, so there is no pull toward matching `description` and reopening the prose
false positive.

Two scoping decisions, both narrowing: an absent or header-only ledger is **not**
off-contract (it would relabel the clearest ungoverned case as a schema
complaint), and the check fires only for a closure that actually shipped a
shortfall column, since that is the gate's whole claim. Statuses are unioned
across rows as phase D does, so one `superseded` row among clean ones still
spoils the ledger.

One crash fixed with it: `csv.DictReader` files surplus fields under `restkey`,
which defaults to `None`, and sorting `None` beside `str` raises. One unquoted
comma in a hand-written prose column — exactly the ledger this branch reports —
took the harness down instead of producing the finding.

## Evidence

- `evals/dp-scenarios/tests/test_grading_gates.py` — correct abstention is
  examined and passing; nothing to read is still not-examined so an empty
  closure cannot pass; and an unrelated ruling no longer changes the verdict.
- `evals/dp-scenarios/tests/test_scenario_loader.py` — only
  `parent-child-grain-trap` declares scoreable answer gold, and the expected
  required-gate table now derives `query` from that predicate instead of
  asserting it for all nine packages while the tier waived it for eight.
- `evals/dp-scenarios/tests/test_runner_report.py` — the query waiver is in
  `NOT_STAGED_CODES` and surfaces as a waived gate.
- `evals/dp-scenarios/tests/test_grading_gates.py` — the crm-pipeline live
  ledger shape reports `capability_decisions_off_contract` alone and names both
  the missing binding column and the out-of-vocabulary status; a single
  `superseded` row among conforming ones is enough; an absent or header-only
  ledger still reports `capability_shortfall_not_governed`; an off-contract
  ledger does not fail a run that shipped no shortfall column; and a row with
  more fields than headers is reported rather than raising.
  The first and the restkey case both fail against the previous implementation.
