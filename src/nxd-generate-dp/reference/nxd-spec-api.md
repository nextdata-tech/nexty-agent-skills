# The `nxd.spec` Python DSL — verified API surface

## Contents

- Why this file exists
- Data types (`nxd.spec.data_types`)
- Semantic role builders (`nxd.spec`)
- `Agg` — the closed aggregation vocabulary
- `SemanticModelSpec` / `semantic_model()` / `semantic_view()`
- `spec.py` builders: `data_product`, `script`, `data_product_output`, `storage`
- Version pin and drift

## Why this file exists

Every signature below was read directly from the installed `nxd.spec` package
source (not inferred, not from a worked example) and is pinned to the package
version in "Version pin and drift" below. **Trust this file. Do not
re-verify these signatures against the nxd source tree unless a concrete
runtime error contradicts what's written here** — a `TypeError`, an
`AttributeError`, or a validation error whose message doesn't match this
doc. Pre-emptively re-reading `nxd/spec/*.py` "just to be sure" before every
`models.py`/`spec.py` you write is the exact cost this file exists to remove.
If the installed package version differs from the pin below, treat this file
as unverified for that version and re-derive the changed piece only — not
the whole surface.

This file is also the **normative input to the Phase A structural check** in
[reference/self-check.md](self-check.md): the closed sets that check enforces
(data-type constructors, role-builder keyword names, `Agg` members,
`semantic_model`/`semantic_view` and `spec.py` builder shapes) are transcribed
from the tables below. The check therefore inherits this file's version pin and
its drift caveat — it validates against **v0.41.139 as written here, not against
the installed wheel**. When a signature below changes, update both files in the
same edit, or the check will reject valid code.

## Data types (`nxd.spec.data_types`)

All zero-argument unless noted; import what you need, e.g.
`from nxd.spec.data_types import string, number, boolean, date32`.

| Constructor | Notes |
|---|---|
| `string()`, `boolean()` | |
| `date()`, `date32()`, `date64()` | `date32()` is the proven pin used by the worked CSV example |
| `double()`, `float()`, `float16()`, `float32()`, `float64()` | |
| `int8()`, `int16()`, `int32()`, `int64()` | |
| `uint()`, `uint8()`, `uint16()`, `uint32()`, `uint64()` | `uint()` is an alias for `uint16()` |
| `number()` | A generic numeric type distinct from the sized int/float variants — this is what the skill's inferred-type mapping table uses for "int/number" and "number/double/float" |
| `vector()` | |
| `binary(length=None)`, `vector_embeddings(dimensions)`, `timestamp(unit, timezone=None)`, `decimal(precision, scale)`, `duration(unit)`, `time32(unit)`, `time64(unit)` | Parameterized; `unit` is a `DurationUnit` from `nxd.core.yaml_schemas` |
| `list(value_type)`, `list_view(value_type)`, `large_list(value_type)`, `large_list_view(value_type)`, `map(key_type, value_type)`, `dictionary(key_type, value_type)`, `struct(fields)` | Complex/nested types — `value_type`/`fields` are `Field` instances from `nxd.core.yaml_schemas` |
| `variant()` | Free-form semi-structured data (arbitrary JSON keys); wire-equivalent to `struct([])` |

The desktop closure pattern only ever needs `string()`, `number()`,
`boolean()`, `date32()` — the rest exist for the k8s/cloud topology's richer
source types.

## Semantic role builders (`nxd.spec`)

All return a `RoleSpec` (a `(kind, blob)` pair) except `field()`/`metric_field()`,
which return an `AttributeSpec` (a full column) already carrying the role blob.

- **`primary_key()`** — no arguments. The entity-key role.
- **`dimension(name=None, pii=False, label=None, description="")`** — a
  groupable/filterable column. `label` attaches a companion display column
  (`label_column` in the compiled blob).
- **`join(to, to_column=None, cardinality=None, to_data_product=None)`** —
  `to` is the target model name (positional or keyword). `cardinality`
  defaults to `Cardinality.MANY_TO_ONE` — nearly always leave it unset.
  `to_data_product` is for a cross-DP join edge (mesh only); leave `None` on
  desktop.
- **`metric(agg, of=None, name=None, description="", boolean=False, extra_dimensions=(), column=None)`**
  — `agg` is an `Agg` value. `of` is a `FieldRef` (from `<model>.field("<col>")`)
  pointing at the base column being aggregated; mutually exclusive with the
  explicit `column=` override — pass one or neither, never both.
- **`field(dtype, *role_args, roles=None, description=None, label=None, name="")`**
  — builds a base-model column. `role_args` takes `primary_key()` /
  `dimension()` / `join()` positionally; a `metric()` role here **raises** —
  metrics are consume-time-only, declared on a `semantic_view` instead.
- **`metric_field(dtype, metric_role, description=None, name="")`** — the
  `semantic_view` counterpart to `field()`. `metric_role` must be a
  `metric()` result; anything else raises.

A field may also be written as a bare `dtype` (no role) or a
`(dtype, *rest)` tuple inside `.schema({...})` — see `SemanticModelSpec`
below; `field()`/`metric_field()` are for when you need to attach `label`,
`description`, or an explicit `name` inline.

## `Agg` — the closed aggregation vocabulary

`from nxd.spec import Agg` — despite appearing as `TYPE_CHECKING`-only in the
package source, this import works at runtime (a module-level `__getattr__`
lazily resolves it). It's a `str` enum; use it by member name
(`Agg.SUM`, not a bare string). The vocabulary is **closed**:

```
Agg.COUNT, Agg.COUNT_DISTINCT, Agg.SUM, Agg.AVG, Agg.MIN, Agg.MAX
```

An internal `Agg.EXPRESSION` member also exists but is not part of this
skill pack's documented surface — never use it. **`median` does not exist
and never will via this path** — if a question needs it, drop it or
approximate with an existing aggregation and say so; do not invent a metric
kind.

## `SemanticModelSpec` / `semantic_model()` / `semantic_view()`

- **`semantic_model(name, attributes=None, description=None, sampling=None)`**
  — starts a base model. `attributes` is rarely passed here; the normal
  pattern builds an empty model then calls `.schema({...})`.
- **`.schema(attributes: dict)`** (alias: **`.fields(...)`**, identical) —
  each dict value is one of: a bare `DataType` (no role), an `AttributeSpec`
  (a `field()`/`metric_field()` result), or a tuple `(dtype, *rest)` where
  trailing items are one optional `str` description plus any number of role
  specs. All three forms are equivalent; mix freely across attributes.
- **`.field(name) -> FieldRef`** — a handle to one of this model's columns,
  used as `metric(of=base.field("<col>"))` from a `semantic_view`. Does not
  require the field to already be declared.
- **`.description(text)`** — sets the model's description; chainable.
- **`semantic_view(name, base, attributes=None, description=None)`** — starts
  a view over `base` (a `semantic_model`). A view's fields are built with
  `metric_field(...)`; unlike a base model, a `metric()` role is allowed in
  its `.schema({...})` tuples too. A view with zero attributes raises at
  build time — always give it at least one `metric_field`.

## `spec.py` builders: `data_product`, `script`, `data_product_output`, `storage`

- **`data_product(name=, domain=, version=, infra_profile=, ...)`** — starts
  the spec. `infra_profile` is the string name matching
  `infra-profile.yaml`'s `metadata.name` (`"desktop-local"` on desktop).
  Several other keyword args exist (`versioned`, `defer_provisioning`, etc.)
  — none apply to the desktop closure pattern; leave them unset.
  - **`.transform(function_spec)`** — takes a `UserCodeSpec` (what `script(...)`
    returns), not a bare function.
  - **`.output(output_spec)`** — takes a `DataProductOutputSpec` (what
    `data_product_output()` returns).
  - **No `.semantic_tools(...)`** on desktop — it exists on `DataProductSpec`
    but wires a k8s RPC port; see the Invariants section elsewhere in this
    skill for why it's wrong here.
- **`script(path) -> UserCodeSpec`** — one file, the transform entrypoint.
  - **`.compute(url, alias=None)`** — binds the compute service (`url` is the
    infra-profile service reference, e.g.
    `"/infra-profile/desktop-local#/services/python-compute"`).
  - **`.secrets(urls: list[str])`** — one infra-profile service reference per
    source instance; **replaces** any prior call rather than accumulating —
    always pass the complete list in one call.
- **`data_product_output() -> DataProductOutputSpec`**
  - **`.port(name, port_spec)`** — `port_spec` comes from `storage(...)`;
    raises if `name` is already registered on this output.
  - **`.promise(promise)`** — a `SemanticModelSpec` (or a custom
    `VerificationSpec`); registers a produce-time contract that the model's
    physical table gets written. Never call this for a `semantic_view`.
  - **`.model(model, is_public=True, expressions=None)`** — registers a model
    (base or view) into the output's global model list without a
    produce-time contract; this is how a `semantic_view` reaches the
    compiled catalog. `is_public` defaults `True`.
- **`storage(url, alias=None) -> OutputPortSpec`** — `url` is the
  infra-profile service reference for the storage backend (e.g.
  `"/infra-profile/desktop-local#/services/duckdb"`).

## Version pin and drift

Verified against the installed `nxd` package at **`v0.41.139`**
(`nxd/version.py`). Treat this the same way the closure pins
`dlt[duckdb]==1.28.2` — if the installed version differs, this file may be
stale; re-derive only the specific signature that produces an unexpected
error, not the whole surface.
