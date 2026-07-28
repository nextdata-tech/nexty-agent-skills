# Contracts: expectations and promises on a local data product

## Contents

- [What runs, and what does not](#what-runs-and-what-does-not)
- [What a model contract checks](#what-a-model-contract-checks)
- [The three origins of a contract](#the-three-origins-of-a-contract)
- [Authoring](#authoring)
- [Custom checks: not on the local runtime](#custom-checks-not-on-the-local-runtime)
- [Contracts and transform asserts are complementary](#contracts-and-transform-asserts-are-complementary)
- [Invariants](#invariants)

How a constraint the user stated — or one profiling discovered and the user
confirmed — becomes a **declared, enforced** contract on the generated closure.

This is the durable, exportable statement of what the product guarantees. It is
not a replacement for the in-transform asserts of Step 3b; the two check
different things at different moments and both are required.

---

## What runs, and what does not

The local runtime does not execute every contract shape the platform does.
Declaring one it cannot run is worse than declaring nothing, because it reads to
a consumer as a guarantee. Only the first row below is available today:

| Shape | Local runtime | Use it? |
|---|---|---|
| **Model contract** — a `semantic_model` passed to `.promise(...)` | The storage driver checks the landed table: every declared column present, declared non-nullable columns hold no nulls, declared numeric ranges hold. It reports a real verdict rather than the empty result it used to return. **The publish is not yet gated on that verdict** — see below. | **Yes** — this is the sanctioned shape. |
| **Custom verify** — `custom("name").verify(code(fn))` | **Never author one.** Both shapes fail at boot: without compute routing the spec resolves to a contract executor the local profile does not declare, and routed to local compute the run dies with `Driver nxd:local/python/compute:0.1.0 not found` — confirmed on a live run, not inferred. | **No** — see "Custom checks" below. |
| **Input expectation** — `.expectation(...)` on an input | Base models land in the same database as outputs, so a base model's contract is checked when it is promised on the output port. There is no separate source-side check. | Express it as a **promise** on the landed model. |

Everything here therefore attaches to the **output port**, even for a constraint
the user phrased about the input ("the orders file always has an order id").
That constraint is about a column that lands, so promising the landed model
enforces it.

---

## What a model contract checks

A promised `semantic_model` is checked field by field against its landed table:

- **column presence** — every field declared in the model exists;
- **nullability** — a field declared non-nullable holds no nulls;
- **numeric range** — a field's declared `min`/`max` bounds hold.

A failure names the column and the count of offending rows. Non-numeric bounds
are not checked: comparing them correctly needs collation rules, and a check
that guesses is worse than one that abstains.

Declare a field non-nullable because the data must never omit it — not because
it *looks* required. The declaration is the product's stated guarantee, and it
is what a consumer reads.

**What it does NOT yet do: block the publish.** The driver computes and reports
the verdict, but the local runtime tears the kernel down as soon as the
transform's output lands — before the phase that would act on it — so a run
whose data violates a declared contract still publishes today. This is a known
runtime gap, established by a live run rather than assumed.

So: declare contracts, because they are the durable statement of what the
product guarantees and they become enforcing the moment that gap closes. But do
not tell a user a violating run will be stopped — say the contract is declared
and checked, and keep the **Step-3b transform asserts** as the check that
actually fails a build today.

---

## The three origins of a contract

| Origin | Where it comes from | Confirmation |
|---|---|---|
| **Stated** | The user's own words in the intent — "order ids are never null", "amounts are never negative". | None needed. It is already their words. |
| **Discovered** | Profiling observed it and it is load-bearing for a question. | **Required** — see below. |
| **Derived** | Implied by a ruling you encoded — a classification whose output column must always be populated, a reference mapping that must cover every source key. | None needed beyond the policy read-back that already covered the ruling. |

### Stated constraints

Encode faithfully, and encode **only** what was stated. A user who says "order
ids are never null" has constrained one column; do not generalise it into a
uniqueness claim, and do not quietly extend it to sibling columns.

If a stated constraint cannot be expressed as a model contract — it spans rows,
compares tables, or depends on an aggregate — it belongs in a **Step-3b
transform assert** instead. Say so rather than silently dropping it.

### Discovered invariants

Profiling already reports what a contract needs: `null_pct`, `cardinality`,
`distinct_count`, and `sample_values` per column. An invariant is a **candidate**
only, never adopted on the strength of the profile alone.

**Held-on-this-export is not proof it holds on the next export.** This is the
same discipline already applied to primary keys, for the same reason.

**Filter by rule before proposing.** A candidate reaches the user only when both
hold:

1. **It is load-bearing** — a question depends on the column, or a derived model
   or gate reads it. An invariant on a column nothing consumes is an observation,
   not a contract.
2. **It clears the evidence floor** — the profile covers enough rows to mean
   something, and the observation is not degenerate.

Reject by rule, without spending a turn:

- a column that is **100% null** in the sample — that is an absent column, not a
  non-null-complement, and promising anything about it is noise;
- a domain of **one distinct value** — a sample that happens to contain one
  status is not evidence the status set has one member;
- a range read off a **small sample** — min/max over a handful of rows is the
  sample's shape, not the domain's.

**Propose in ONE batched turn**, capped at about seven. State each candidate,
the evidence, and what declaring it would mean:

> Profiling suggests three constraints. Declaring one means a future run
> violating it will not publish.
>
> - `order_id` — never null across 12,480 rows. Declare non-null?
> - `amount` — always ≥ 0 across 12,480 rows. Declare a lower bound of 0?
> - `status` — only `paid`, `refunded`, `pending` across 12,480 rows. This one
>   is a domain rather than a range, so it cannot be declared as a contract;
>   recorded as an observation instead.
>
> Anything you decline is recorded in the context record rather than enforced.

Everything filtered out or declined is recorded as an observation in
`CONTEXT.md` — never silently discarded, never silently enforced.

**This turn must never share a turn with the policy read-back.** They are two
gates of equal strength with different subjects. Presenting both together lets a
single reply be read as approving both, which retroactively weakens the policy
gate. Run the policy read-back first, to its own reply; propose invariants
after.

**As a generation subagent you never open either turn.** Return the candidates
in your structured result and let the orchestrator decide; declaring an
unconfirmed discovered invariant is the same failure as encoding an unapproved
policy.

---

## Authoring

A contract is a field-level declaration in `models.py` — there is no separate
contract file for the sanctioned shape.

Constraints are attached with **`.constraints(...)` chained onto the field**, not
passed as `field()` keyword arguments. `field()` accepts only the data type,
roles, `description`, `label` and `name`; a constraint passed there raises.
Bounds are **strings**, including for numeric columns:

```python
# models.py
orders = (
    semantic_model("orders")
    .description("One row per customer order.")
    .schema({
        "order_id": field(string(), primary_key()).constraints(nullable=False),
        "amount": field(
            number(),
            dimension(name="amount", description="Order value in the source currency."),
        ).constraints(nullable=False, min="0"),
        "note": field(
            string(),
            dimension(name="note", description="Free-text note; frequently absent."),
        ),
    })
)
```

A field with no `.constraints(...)` call is nullable and unbounded — which is
the right default for a column the data may legitimately omit. Only constrain
what must hold.

`spec.py` needs no change beyond promising the model, which it already does:

```python
.promise(orders)
```

Promising the model is what puts its contract in force. A model registered with
`.model(...)` only — a semantic view — has no table and is never checked.

**Verify the pins before authoring.** The exact keyword spelling for
nullability and bounds is in `reference/nxd-spec-api.md`; trust that over this
example, and over re-reading library source.

---

## Custom checks: not on the local runtime

Do **not** author `custom(...).verify(code(...))` in a local closure.

Both shapes fail at boot. Without explicit compute routing the spec resolves to
a platform contract executor the local profile does not declare. Routing it to
local compute fails too — confirmed on a live run, which died 913ms in with:

```
Error: Driver nxd:local/python/compute:0.1.0 not found
```

The local compute driver registers no contract capability, so the kernel cannot
resolve an executor for the contract even though the same service runs the
transform perfectly well. There is no third shape to try.

A constraint that genuinely needs procedural logic — spanning rows, comparing
against an independently-read source, reconciling a total — belongs in a
**Step-3b transform assert**, which does run, does fail the build, and can see
the closure's own code.

---

## Contracts and transform asserts are complementary

Neither replaces the other, and it is a mistake to treat one as covering for the
other:

| | Transform assert (Step 3b) | Declared contract |
|---|---|---|
| **When** | During the transform, before rows are yielded | After the transform, before the release publishes |
| **Sees** | The closure's own Python — keys, derivations, independently-read source totals | The landed table and the declared schema |
| **On failure** | Fails the build | Stops the publish; the previous version stays served |
| **Visible to a consumer?** | No | Yes — it is what the product declares |

The assert is how you prove a derivation is correct. The contract is how a
consumer who never reads the transform knows what the product guarantees.

A key-uniqueness claim stays with the **assert**: the contract surface carries no
primary-key concept, so uniqueness cannot be expressed there.

---

## Invariants

- **Only model contracts.** Never author a custom verify in a local closure —
  its execution path is unresolved and the unrouted shape fails at boot.
- **A declared contract is enforced, not documentation.** Declaring a field
  non-nullable means a run whose data omits it will not publish. Declare it
  because that is the desired behaviour.
- **A discovered invariant is confirmed before it is declared** — one batched,
  capped, rule-filtered turn, never sharing a turn with the policy read-back, and
  never opened by a subagent.
- **A stated constraint is encoded as stated** — not generalised, not extended to
  sibling columns, and not silently dropped when it does not fit the contract
  surface (say so, and put it in an assert).
- **What is not declared is recorded.** Every filtered or declined candidate
  lands as an observation in `CONTEXT.md`.
- **Never weaken a contract to make a run publish.** A failing promise means the
  data or the promise is wrong; fix whichever is, rather than removing the check.
