# Candidate invariants

## Contents

- [What to emit](#what-to-emit)
- [Reject by rule, without proposing](#reject-by-rule-without-proposing)
- [The shape](#the-shape)
- [Why proposed and not adopted](#why-proposed-and-not-adopted)

Applies to the **local-desktop** inference path. The same profile signals that
classify a column into a role also evidence what is always TRUE of it. Those
observations become **candidates** the generator confirms with the user and then
declares as enforced contracts — a violation stops a later run from publishing.

You emit candidates. You never adopt one, and you never declare one.

## What to emit

Two candidate kinds map onto the contract surface. Nothing else does:

| Profile signal | Candidate | Meaning if declared |
|---|---|---|
| `null_pct` == 0 over the full table | the column is never null | a later run with a null here does not publish |
| numeric column, observed min / max | a lower and/or upper bound | a later run outside the bound does not publish |

**A low-cardinality string domain is an observation, not a candidate.** The
contract surface has no enum shape, so `status ∈ {paid, refunded, pending}`
cannot be declared. Report it so it can be recorded, but do not propose it as a
constraint.

Propose only what is **load-bearing**: a question, a derived model, or a gate
reads the column. An invariant on a column nothing consumes is an observation.

## Reject by rule, without proposing

These are rejected on the evidence, not by asking the user — spending a
confirmation turn on a candidate you should have rejected is itself the failure:

- **a column 100% null in the sample** — that is an absent or unextracted column,
  not a claim about the ones that are present;
- **a "domain" of one distinct value** — a sample containing one status is not
  evidence the domain has one member;
- **a range read off a handful of rows** — min/max over a small sample is the
  sample's shape, not the column's.

## The shape

Each candidate carries its evidence, because the user is asked to confirm it and
cannot confirm a bare assertion. State the observation and the rows it rests on:

```json
"candidate_invariants": [
  {
    "model": "orders",
    "column": "order_id",
    "kind": "not_null",
    "evidence": "no nulls across 12,480 rows (full table)",
    "consumed_by": "every question groups or filters by order"
  },
  {
    "model": "orders",
    "column": "amount",
    "kind": "min",
    "value": "0",
    "evidence": "minimum 0.00 across 12,480 rows (full table)",
    "consumed_by": "revenue metric"
  }
]
```

`value` is a **string**, matching the constraint surface — including for numeric
bounds.

## Why proposed and not adopted

**Held-on-this-export is not proof it holds on the next export.** This is the
reasoning already applied to primary-key selection: an observation over the
supplied data describes that data, not the domain it was drawn from.

The cost of getting this wrong is asymmetric. A declared constraint that the
domain does not actually guarantee will one day stop a legitimate run from
publishing, on data the user considers fine — and the user never agreed to it.
So the user confirms before anything is declared, and the confirming turn
belongs to whichever thread faces the user — the generator when it is invoked
directly, the orchestrator when profiling and generation run as subagents. As a
subagent you never open it: return the candidates and let the caller decide.
See `nxd-generate-dp`'s `reference/contracts.md`.
