# nxd-data-product-query — semantic querying design notes

Background for the skill's semantic-layer path (Step 6f + `reference/semantic-intent-validation.md`).
**Not loaded by the query flow** — `SKILL.md` and the `reference/` docs are what the
agent reads at query time. This README is for a human (or a future contributor)
who wants to understand *why* the semantic path is shaped the way it is, *how* the
MCP tools it talks to are generated, and *what* is intentionally left for later.

If you only want to run a query, read `SKILL.md`. If you only want the intent-gate
mechanics, read `reference/semantic-intent-validation.md`.

---

## 1. What the semantic path is

A data product built with the **`nxd-semantic-data-product`** skill exposes a
governed text-to-SQL surface: three MCP tools that turn *concept names* into
correct, governed, aggregated SQL. The querying agent never authors SQL — it
discovers concepts, builds a `{measures, dimensions, filters}` selection, and the
DP compiles + runs it.

| Tool | Purpose |
|------|---------|
| `list_models` | Enumerate the semantic models (entities) with grain, metric/dimension counts, and joins. |
| `describe_model(name)` | Full detail for one model: its `metrics` (each with the `compatible_dimensions` it can be sliced by), its own `dimensions` (with PII flags), and its `joins` (each naming the reached model and the dimensions it unlocks via `reaches_dimensions`). |
| `run_semantic_query` | Compile a concept selection to SQL, run it, return `compiled_sql` + rows. |

This is the **server side** of the contract; the querying skill is one **client**.
The same three tools back any consumer.

---

## 2. The intent-validation design (why Step 6f exists)

The value of the semantic layer is a **two-layer trust split**:

- **selection → SQL** is *solved and deterministic*. The compiler enforces one
  grain per query (chasm-trap guard) and renders read-only aggregated SQL — same
  selection always yields the same SQL. Once the selection is right, the number is
  right, forever and reproducibly.
- **intent → selection** is *the open layer*. A *valid* selection can still be the
  *wrong* one — `call_count` when the user meant `sales_calls`, a missing filter,
  the wrong fiscal boundary. It compiles clean and returns a confident number for
  the wrong question.

Because the lower layer is deterministic, **all residual trust risk collapses onto
the upper layer**, and — crucially — the selection is a first-class, inspectable
object on the wire (`{measures, dimensions, filters}`), not buried inside generated
SQL. So we can validate it as its own artifact: echo it back, critique it, clarify
it. Free-form text-to-SQL can't do this because there is no selection to inspect.

Step 6f is that validation, run **client-side** before `run_semantic_query`:

1. **Critic** — LLM verdict (`ok` / `ambiguous` / `likely-wrong`) over
   `{question, selection, describe_model metadata}`.
2. **Echo** — deterministic plain-language restatement of the selection from the
   catalog descriptions, shown to the user.
3. **Clarify** — on an unclear verdict or an unreachable dimension, ask with the
   real candidate concepts instead of guessing.

All three read only what `list_models` + `describe_model` already return — zero
server change. Echo is deterministic; critic and clarify are non-deterministic /
interactive, so they stay client-side, which keeps the `run_semantic_query` path
deterministic (the determinism dividend). Full design:
[`reference/semantic-intent-validation.md`](reference/semantic-intent-validation.md).

---

## 3. How the MCP tools are generated (server-side mechanics)

The querying skill never builds these tools — but understanding how they come into
existence explains why the response shapes the intent gate reads are stable, and
where a missing field (e.g. a richer `describe_model`) would have to be added.

### The kit

The compiler, dialect, and the **MCP tool factory** `build_semantic_tools` ship in
the `nxd.data_product` wheel as the importable package `nxd.experimental.semantic`.
A DP imports it at runtime; it is **not** vendored or copied.

```python
from nxd.experimental.semantic import (
    SemanticRegistry, build_semantic_tools, compile_selection,
    SnowflakeDialect, CompileError,
)
```

The `experimental` namespace is a stopgap — once the first-class `nxd.spec`
measure/dimension DSL lands, the public
names migrate into it. The names are already
pre-aligned, so the migration is a mechanical import-path change.

### Registry → tools

A DP author writes a `SemanticRegistry` (models + grains, dimensions with PII
flags, metrics with aggregations, joins with cardinality). Then:

```python
tools = build_semantic_tools(REGISTRY, dialect=SnowflakeDialect(), fqn="DB.SCHEMA.")
# -> list[SemanticTool], one each for list_models / describe_model / run_semantic_query
```

Each `SemanticTool` carries `.fn` (a closure callable), `.request_model`,
`.response_model`, and `.description`. The **response shapes** the intent gate
depends on (`describe_model` → `metrics[].compatible_dimensions`,
`dimensions[].pii`, `joins[].reaches_dimensions`) are derived directly from the
registry by this factory — they are not hand-authored per DP, which is why the
client can rely on them.

### Wiring into a running DP (producer side)

NXD exposes MCP tools **only** through `spec.py` via `data_product_rpc_output()`.
There is no module-level `tools` list discovery — a bare
`tools = build_semantic_tools(...)` in some file exposes **zero** tools at runtime.
The correct wiring passes `code(<module-level tools.py function>)` (NOT `code(t.fn)`
— `t.fn` is a closure `code()` cannot extract) and reuses `build_semantic_tools(...)`
only for the schemas, and **requires** a `.transform(...)` so the sibling
`registry.py` / `tools.py` modules are bundled into the image:

```python
from nxd.spec import (
    data_product, data_product_output, data_product_rpc_output,
    rpc_function, rpc_server, storage, code,
)
from nxd.experimental.semantic import build_semantic_tools
from registry import REGISTRY
from tools import list_models, describe_model, run_semantic_query
from transform import transform
from models import provision_marker

_tool_map = {t.name: t for t in build_semantic_tools(REGISTRY)}  # schemas only
_rpc = data_product_rpc_output()
for _fn, _name in [
    (list_models, "list_models"),
    (describe_model, "describe_model"),
    (run_semantic_query, "run_semantic_query"),
]:
    _t = _tool_map[_name]
    _rpc = _rpc.function(
        rpc_function(code(_fn), _t.request_model, _t.response_model)
        .description(_t.description)
    )
_rpc = _rpc.port(
    "mcp-api",
    rpc_server("<infra-profile-path>#/services/<mcp-service-name>")
    .enable_endpoints()
    .mcp_path("/mcp"),
)
spec = (
    data_product(name="...", ...)
    .transform(code(transform).compute("<infra-profile-path>#/services/<compute>"))  # MANDATORY
    .output(data_product_output().promise(provision_marker)
            .port("snowflake", storage("<infra-profile-path>#/services/<snowflake>")))
    .output(_rpc)
)
```

At query time, the querying skill detects this path by the three tool names on
`tools/list` (Step 6d) and then runs the intent gate (Step 6f). The producer-side
wiring constraints (flat layout, module-level tools, mandatory transform,
verify-before-transform ordering) live authoritatively in the generator skill.

Authoritative detail lives in the generator skill:
`src/nxd-semantic-data-product/reference/{overview,compiler-and-routing,runtime-and-dependencies}.md`.

---

## 4. Deferred work and product-side gaps

Documented here (not in the query flow) so the agent isn't cluttered with work it
can't do. These are candidates for convergence with a future first-class `nxd.spec` measure/dimension DSL.

### Deferred — could be built client-side later

- **Self-consistency vote.** Sample N independent interpretations of the question
  into N selections; if they disagree on metric / grain / filter, treat as
  ambiguous and clarify. Self-consistency at the *selection* layer (voting on the
  deterministic SQL would be pointless). Deferred only for LLM cost — it is the
  same shape as the critic, N-sampled.

### Product-side — cannot run client-side

| Gap | Why it needs product-side work | Leverage |
|---|---|---|
| **Value-linking / `resolve_value`** | Grounding a filter *value* against the real stored form (`"California"` → `"CA"`, `"last quarter"` → a date range) needs a warehouse `SELECT DISTINCT` against the real column. The three tools don't expose cell values, so no client-side cleverness substitutes. This is where plausible-but-wrong **filter** answers leak in. Durable home: a governed `resolve_value(dimension, nl_literal)` tool (or a dialect `DISTINCT` method) that returns the canonical stored form *before* the filter is built. | **High** |
| **`describe_model` dimension enrichment** | `compatible_dimensions` / `reaches_dimensions` may carry dimension *names*; the critic leans on the model's `dimensions` block for what each *means*. Returning full dimension objects `{name, description, type, pii}` everywhere a dimension is referenced removes the cross-ref. | Medium (ergonomics) |
| **Server-side echo** | Each client re-derives the restatement from the catalog. A `selection_restatement` field on the `run_semantic_query` response — computed purely from selection + registry, so still deterministic — gives every client the echo for free. | Low/med (optional) |

Until value-linking exists, the only client-side handling for a value mismatch is
**after** execution: a filtered query returning 0 rows while the unfiltered query
returns rows is the symptom — surface it to the user, never retry with invented
encodings. (See the value-mismatch row in `SKILL.md`'s troubleshooting table.)

---

## `scripts/cross_dp_compile.py` — experimental, NOT part of the skill

`scripts/cross_dp_compile.py` is an **experimental** client-side cross-DP
compiler: it harvests each DP's `semantic_model` payload, merges them into one
schema-qualified registry, and compiles a single fan-out-safe cross-schema SQL.
It is intentionally **not referenced by `SKILL.md`, the scripts table, or any
`reference/` doc** — the skill never invokes it.

Why it is parked here and not wired in: a cross-DP eval (commit #47,
`evals/cross-dp-joins/`) compared it head-to-head with strict mode on the live
mesh. Verdict — the compiler is the better cross-DP *engine* but is only safely
deployable **server-side**, because client-side it fails on two boundaries the
skill must respect:

1. **Authorization.** A credential leased from one DP's output port is scoped to
   that DP's schema. The compiler's single cross-schema SQL needs USAGE on every
   schema it spans → `002003 … not authorized`. A per-DP lease cannot authorize a
   cross-DP query by construction.
2. **Execution locus.** Snowflake's network policy admits the platform egress IP,
   not an arbitrary client → `250001 Could not connect`.

**The skill's canonical cross-DP path is strict mode**: discover + validate the
join via `semantic_model` (the join edge must be published in a DP's
`registry.py`), then execute as N single-DP `run_semantic_query` MCP calls
(each within its own DP's grant) and merge the already-authorized partials
client-side. Strict mode never crosses a DP boundary — that is exactly why it is
client-runnable. See `reference/strict-mode.md`.

`cross_dp_compile.py` stays in-tree only as the reference implementation for the
eventual **server-side** cross-DP endpoint. Do not add it to the skill flow.
