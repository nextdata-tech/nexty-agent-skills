# Cross-DP query DP — server-side cross-DP compiler (reference template)

A **generic, deployable facade data product** that serves one MCP tool,
`run_cross_dp_query`: it takes the caller's already-harvested per-DP semantic
registries plus a concept selection, merges them into ONE registry, compiles ONE
fan-out-safe cross-schema SQL with the shipped `nxd.experimental.semantic`
compiler, and executes it **in-pod** under a cross-DP-scoped Snowflake role.

This is the **server-side home of the cross-DP compiler** that the client-side
`scripts/cross_dp_compile.py` stands in for. It moves the compile + execute step
to where it can actually run.

## Contents

- [Why server-side (the two findings the live eval proved)](#why-server-side-the-two-findings-the-live-eval-proved)
- [Why the caller passes the registries (dynamic — no redeploy)](#why-the-caller-passes-the-registries-dynamic--no-redeploy)
- [Shape — a true facade (no transform, no promise, no data)](#shape--a-true-facade-no-transform-no-promise-no-data)
- [Deploy onto any mesh — the two preconditions](#deploy-onto-any-mesh--the-two-preconditions)
- [Using the tool](#using-the-tool)
- [Relationship to the client-side script](#relationship-to-the-client-side-script)

## Why server-side (the two findings the live eval proved)

A client cannot run a cross-DP join itself:

1. **Execution locus.** The warehouse network policy admits the platform's
   egress IP, not an arbitrary client's — a laptop connecting directly to
   Snowflake is blocked (`250001 Could not connect`). This DP's pod egress IS
   allowlisted, so the same compiled SQL runs here.
2. **Authorization scope.** A per-DP leased credential is scoped to ONE schema;
   a single cross-schema `SELECT` needs `USAGE` on EVERY spanned schema. A per-DP
   lease returns `002003 … schema not authorized` the moment a query crosses a DP
   boundary. This DP runs under a role granted cross-schema read — the cross-DP
   principal.

Determinism + fan-out-safety are the compiler's wins; reachability + a cross-DP
principal are why it can only be deployed server-side.

## Why the caller passes the registries (dynamic — no redeploy)

The agent already calls each DP's `semantic_model` tool to plan a query, so it
holds the serialized payloads. `run_cross_dp_query` takes them as an argument:

- **No mesh discovery, no sibling auth, no in-pod harvest** — the agent did the
  harvest over MCP with its own credentials.
- **No redeploy when the mesh changes** — the member set is data, never baked.
  A new DP joins → the agent harvests it → includes its payload in the next call.

## Shape — a true facade (no transform, no promise, no data)

```
cross-dp-query-dp/
  spec.py            facade DP: rpc output (run_cross_dp_query) + storage port
  cross_dp_query.py  self-contained tool — merge + compile + in-pod execute
  models.py          marker model (build-time only; see below)
  requirements.txt   nxd.* >=0.41.101
```

- **No `.transform()`.** This DP owns no data. The rpc output bundles
  `cross_dp_query.py` on its own (each `code(fn)` ships its own module), so the
  transform-gated `**/*.py` glob is not needed. The tool module is
  self-contained — it imports only from the installed `nxd.experimental.semantic`
  library, so there is no flat sibling to bundle.
- **No `.promise()`.** The storage port attaches the marker model via
  `.model(...)` (which DECLARES a model — satisfying the validator's
  every-port-needs-a-model rule) NOT `.promise(...)` (which would require the
  kernel to verify a produced table after a transform). Nothing is produced or
  verified.
- **The `snowflake` storage port** exists only to inject the Snowflake handle
  into the tool (param name == port name). Its role is the cross-DP principal.

## Deploy onto any mesh — the two preconditions

Edit `spec.py`:

1. `INFRA_PROFILE` — the infra-profile that owns this mesh's services.
2. `SNOWFLAKE_SERVICE` — a `storage` service whose Snowflake **role has `USAGE`
   on every member-DP schema** the queries will span. This is the deliberate
   cross-DP grant ("the mesh-governed service identity"). A role scoped to one
   DP's schema will fail with `002003` the moment a query crosses a boundary.

Then:

```bash
nxd validate          # from this directory
nxd launch
```

## Using the tool

1. The agent calls `semantic_model` on each DP its question spans and collects
   the payloads.
2. The agent calls `run_cross_dp_query` with:
   - `registry_payloads`: the list of those `semantic_model` payloads (dicts or
     their JSON strings).
   - `measures`: metric names (from any included DP).
   - `dimensions` (optional): group-by dimension names.
   - `filters` (optional): `[{"dimension","op","value"}]`.
3. The DP merges (two-pass, owner-wins), compiles ONE fan-out-safe cross-schema
   SQL, executes it in-pod, and returns `{compiled_sql, row_count, columns, rows,
   error}` — the same shape as the per-DP `run_semantic_query`.

The compiler pre-aggregates each measure at its model's grain before any join,
so a measure spanning a 1:N cross-DP relationship is **not** double-counted (the
chasm trap); an unreachable / mixed-grain selection returns an error rather than
a wrong number.

## Relationship to the client-side script

`scripts/cross_dp_compile.py` runs the identical merge + compile from a client
(handy for offline / pre-deploy iteration), but its EXECUTION is blocked by the
two findings above. This DP is the same compiler with the execution moved to a
locus that is reachable and authorized. The merge + compile logic is shared by
construction (both call the shipped `nxd.experimental.semantic` compiler).
