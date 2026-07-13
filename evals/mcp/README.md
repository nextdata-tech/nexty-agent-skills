# Semantic MCP server for the eval harness

A live, governed semantic-layer MCP server for eval scenarios whose agent must
actually **call** the semantic tools (`list_models`, `describe_model`,
`run_semantic_query`) rather than read a catalog fixture and narrate.

Without it the agent reads `fixtures/catalog.json` and *fabricates* SQL + result
rows; the xhigh judge correctly fails that. This server makes the tools real:
`run_semantic_query` compiles with the **genuine** `nxd.experimental.semantic`
compiler and executes against lower-env Snowflake through a governed executor
(masked views), so what's under test — fan-out-safe compilation + governance —
is the shipping code, not a stand-in.

## How a scenario opts in

Ship four server-side fixtures next to the scenario's `prompt.md` /
`checks.json` (run.py keeps them OUT of the agent workspace — the agent must use
the tools, never read the files):

| Fixture | Purpose |
|---|---|
| `mcp.json` | Opt-in marker: `{ "tools": [...], "dp": "...", "rpc_port": "..." }`. `dp`/`rpc_port` shape the proxy URL the skill parses (`/<dp>/rpcs/<rpc_port>/mcp`). |
| `catalog.json` | The agent-facing **logical** surface returned by `list_models` / `describe_model`. |
| `semantic.json` | The authoritative **physical** mapping (table, grain, columns, PII). Drives the genuine `SemanticRegistry` + the governed PII mask. Never shown to the agent. |
| `seed.sql` | DROP+CREATE+INSERT base-table fixtures, loaded into the base schema once per server start. |

### Cross-DP mesh scenarios

The same four fixtures also model a **cross-DP mesh** (`pharma-cross-dp-mesh-query`):
give each model in `semantic.json` a `data_product` label and declare the joins
that connect them — including a crosswalk/bridge model — and the genuine
`compile_selection` resolves the multi-hop join path with a BFS rooted at the
spine, pre-aggregates each fact at its own grain, and DISTINCT-collapses the
bridge. That is exactly what the deployed mesh gateway does after harvesting each
member DP's `semantic_model` and folding the cross-DP join edges into ONE merged
registry — so a single `run_semantic_query` reaching a metric in one DP sliced by
a dimension in another is the real compiler, fan-out-safe. `catalog.json` names
the owning `data_product` per model (and `to_data_product` per join) so the
agent's `describe_model` view shows the mesh is multi-DP; an unauthorized member
is simply absent from the catalog (an entitlement probe). The `data_product`
label is provenance only — the compile decision is driven by join topology, not
the label — and physical tables stay bare-named so they bind to the governed
masked views.

## How run.py drives it (production-faithful)

The `nxd-data-product-query` skill discovers DP MCP endpoints exactly as in
production — `nxd mcp health --format json` → Streamable-HTTP MCP → tool calls.
So the harness:

1. Starts `semantic_server.py --http` on a free port, serving the tools at the
   proxy URL shape (`/<dp>/rpcs/<port>/mcp`).
2. Puts a fake `nxd` (`fake_nxd.py`) on the agent's PATH; `nxd mcp health` returns
   a `data_products` row pointing at that running server.
3. Runs the agent — the skill's shipped `mcp_gateway.py` / `mcp_call.py` toolchain
   discovers and calls the genuine tools **unchanged**.
4. Tears the server down after the cell.

## Credentials

`run_semantic_query` executes against lower-env Snowflake. Export `SNOWFLAKE_*`
before running (account/user/warehouse/database/schema + keypair or password —
see `snowflake_conn.py`). Pull the env's profile from the
`infra-profile-lower-envs` GCP secret; creds are read from env only, never
written to disk by this server.

## The nxd dependency (matched-wheel)

`run_semantic_query` imports the real compiler from the `nxd_data_product`
wheel, which is **not on a public index** — a PyPI package named
`nxd-data-product` is an unrelated stub. Provide the real one one of two ways:

```bash
# (a) point run.py at an interpreter that already has the matched set
export EVAL_MCP_PYTHON=/path/to/python   # has nxd_core + nxd_drivers + nxd_data_product (one version) + mcp + snowflake-connector

# (b) install a matched wheel set into this project's venv, then default (uv run)
uv pip install --project evals/mcp \
  <nxd>/components/nxd_py/wheels/nxd_core-<ver>-*.whl \
  <nxd>/components/nxd_py/wheels/nxd_drivers-<ver>-*.whl \
  <nxd>/components/nxd_py/wheels/nxd_data_product-<ver>-*.whl
```

A stale `nxd_core` against a newer `nxd_data_product` fails at runtime — the set
must share one version.

## Run

```bash
export EVAL_MCP_PYTHON=...        # matched nxd interpreter (see above)
set -a; source <snowflake .env>; set +a
python3 evals/run.py --skill-set current_pack --scenario semantic-intent-validation
```

## Files

- `semantic_server.py` — FastMCP server (`--http` for the eval, stdio for dev). Lazy Snowflake init so the MCP handshake answers instantly; fd-1 guard so the nxd Rust banner can't corrupt the stream.
- `registry_from_fixture.py` — `semantic.json` → genuine `SemanticRegistry` + lowercased PII map.
- `executor.py` — `GovernedExecutor` (ported from the t2sql PoC; masked per-principal views, SELECT/WITH-only, LIMIT cap).
- `seed.py` / `snowflake_conn.py` — fixture loader + env-only connection.
- `fake_nxd.py` — minimal `nxd` CLI stub (`mcp health`, `whoami`).
