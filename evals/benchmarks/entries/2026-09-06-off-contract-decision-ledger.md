---
id: 2026-09-06-off-contract-decision-ledger
date: 2026-09-06
label: "name an off-contract decision ledger instead of calling it ungoverned"
plugin_version: 0.45.0
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — name an off-contract decision ledger instead of calling it ungoverned

## Notes

Harness grading only; no skill under `src/` changes and nothing agent-visible
moves, so no runnable public arm can distinguish it.

**Correcting the previous entry.** `2026-09-06-abstention-and-waiver-categories`
closes by recording that `_metric_is_governed` binds on `applies_to` and accepts
only `confirmed`/`proposed` while the live closures wrote
`decision_id,description,status,provenance` with `approved`/`settled`, and calls
that "the next false negative in this family". **It is not a false negative.**
That entry is frozen evidence and stays as written; this one supersedes its
final paragraph.

The pack fixes the ledger vocabulary and enforces it: `derivation-plan.md`
declares `nxd_decisions` as `decision_id, status, provenance, ruling,
applies_to, detail` with `status` exactly one of `confirmed`/`proposed`/
`blocked`, and `self_check.py` phase D hard-fails a closure whose ledger is
missing either column or carries a value outside that vocabulary
(`policy.decisions_column_missing`, `policy.decisions_value_out_of_vocab`).
`approved` is the *blueprint* status vocabulary (`dp_diagnostics.py`
`STATUS_VALUES`) bleeding into the ruling ledger — two vocabularies the pack
keeps deliberately disjoint. So the live rows are not rulings the harness failed
to read; they are a closure the pack's own tripwire rejects, and widening the
gate's allowlist to admit them would make the eval pass a build the skill fails.

The verdict was already right. Only the label was wrong:
`capability_shortfall_not_governed` reads as "the agent wrote no ruling", which
points a reader at this gate's allowlist rather than at the skill.

**What changed.** `_ledger_contract_breaches` classifies a non-empty ledger
against the same two vocabularies phase D uses (copied, not imported, with a
comment naming that file as the source of truth) plus the presence of
`applies_to`, the field that binds a ruling to columns. A breach yields one
`capability_decisions_off_contract` finding for the closure — failing, examined
— and the per-metric loop is skipped so one defect is not charged once per
metric. `_metric_is_governed` is unchanged: a row with no `applies_to` never
reaches it, so there is no pull toward matching `description` and reopening the
prose false positive ("pipeline velocity is out of scope" governing
`stage_velocity_30d`).

Two scoping decisions, both narrowing:

- An absent or header-only ledger is **not** off-contract. It has no row to be
  off-contract with, and treating it so would relabel the clearest ungoverned
  case — a shortfall column shipped with no ruling at all — as a schema
  complaint.
- The check only fires for a closure that actually shipped a shortfall column.
  This gate's claim is about those and nothing else; failing a correct
  abstention over ledger hygiene would grade the self-check's question here and
  resurrect "any unrelated decision row decides the outcome" in mirror image.

Vocabulary is unioned across rows, as phase D does: one `superseded` row among
clean ones still makes the ledger unreadable as a class, and dropping it would
let the survivors govern in its place.

## Evidence

- `evals/dp-scenarios/tests/test_grading_gates.py` — the crm-pipeline live
  ledger shape (`decision_id,description,status,provenance` with
  `approved`/`settled`) now reports `capability_decisions_off_contract` alone
  and names both the missing binding column and the out-of-vocabulary status;
  a single `superseded` row among conforming ones is enough; an absent or
  header-only ledger still reports `capability_shortfall_not_governed`; and an
  off-contract ledger does not fail a run that shipped no shortfall column.
  The first and second of those fail against the previous implementation.
- `src/nxd-run-job-loop/scripts/self_check.py` phase D — the source of truth
  the copied vocabularies must stay in step with.
