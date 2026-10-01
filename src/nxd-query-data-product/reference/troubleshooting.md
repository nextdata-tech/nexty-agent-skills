# Troubleshooting query-time failures

Symptom → cause → fix for failures hit while querying a port. Diagnose before
retrying: the same symptom (e.g. an empty result) has more than one cause, so
confirm which before changing the query.

| Symptom | Cause | Fix |
|---|---|---|
| `401 Unauthorized` from a port call | Leased credential or PAT expired (`tokens.json` `expiry` passed), or the wrong auth header. DP REST uses `x-nextdata-token`, NOT `Authorization: Bearer`. | Re-run `nxd login` (or **nxd-setup-cli**) and re-request `connect`; send the PAT as `x-nextdata-token`. |
| Gateway call (`gateway_tools.py` / `mcp_call.py`) returns `403`, but the same token gets `200` from the DP REST API | The gateway only accepts a **PAT** (`nxdpat_…`) on `X-Nextdata-Token` — a plain OAuth session token from `nxd login` is rejected even though REST accepts it. Not an expiry issue. | Check `$TOKEN_FILE` starts with `nxdpat_`; if not, ask the user to run `nxd create personal-access-token` or `nxd mcp config` to mint one, then re-read the token file. See SKILL.md Step 1. |
| `403` / `SignatureDoesNotMatch` fetching a file URL | The presigned URL TTL elapsed mid-session (they are short-lived). | Re-request `connect` for a fresh URL; don't reuse a cached one past its TTL. |
| `connect` returns `unsupported` | The port's driver has no query recipe wired, or the infra profile couldn't be resolved. | Resolve the infra profile from the active mesh; confirm the port's driver type via `gateway_tools.py details --dp <dp> --outputs`. |
| `connect` returns `approval_pending` | Access requires a pending approval. | Stop. Surface the `message` / `tracking_url` to the user. Do NOT poll. |
| Vector search returns nonsense / irrelevant hits | Query embedded with a different model than the DP indexed with. | Read the index model from the data product's `description` via `gateway_tools.py details --dp <dp>` (discovery goes through the gateway, not REST); embed the query with that exact model. |
| Vector search errors with a dimension mismatch | Query vector dimension ≠ the indexed column dimension. | Match the embedding model so dimensions agree (e.g. 384 vs 1536). |
| SQL query against a pgvector port returns 0 rows | Querying the metadata table by the wrong table name, or the DP hasn't run yet (no data). | Confirm the physical table name (model name, lowercased) and that the DP reached `STARTED` with a successful run. |
| RPC/MCP call fails to connect / 404 | Wrong tool wire name or trailing-slash mismatch on the multiplexer endpoint; or the DP MCP port is unhealthy. | Re-confirm the `<function>__<hash>` name from `gateway_tools.py tools --dp <dp>` and check `gateway_tools.py health`; if the port itself is failing, debug the DP with **nxd-debug-data-product**. |
| `run_semantic_query` returns "metrics span multiple grains" / "no join path connects model X to model Y" | Metrics from two models NOT connected by any documented join were combined in one call (chasm-trap guard) — correct governance, not a transient error. Join-reachable models (including cross-DP via a `to_data_product` edge) ARE combinable in one call; the compiler pre-aggregates each grain before joining (fan-out-safe). | Do NOT retry the same combined call or hand-write a join. Call `describe_model` on each model to confirm the join topology. If the models ARE join-reachable, the single call is correct — check the concept names. If they are NOT connected by any join, issue one `run_semantic_query` per model sharing a compatible dimension and present the result sets separately; a genuine cross-DP join requires the owning DP to publish a `to_data_product` join edge. See §6d "Semantic-layer MCP ports". |
| `run_semantic_query` returns `error: "dimension X is not compatible with metric Y"` | The dimension can't slice that metric (not in `compatible_dimensions`, no join reaching it). | Re-pick from `describe_model`'s `compatible_dimensions` / `joins.reaches_dimensions`; re-run the §6f gate. |
| Semantic query returns no rows, an empty grouped result, `SUM` returns `NULL`, or a grand-total `COUNT` returns 0 | A filter may use a value that differs from the stored value. | Follow “Resolving semantic query zeros” below before reporting a zero. |

When the failure is the Data Product itself (port unhealthy, no data produced,
RPC pod crashing) rather than the query, switch to the
**nxd-debug-data-product** skill.

## Resolving semantic query zeros

If a filtered query returns no rows, has an empty grouped result, `SUM` returns
`NULL`, or a grand-total `COUNT` returns 0, check whether a filter value matches
the stored form before reporting a zero. If the filtered dimension is not
PII-classified, probe its stored values by querying the same measure grouped by
that dimension without that filter, keeping the other filters. Retry with the
exact stored value that plausibly matches. If no stored value plausibly matches, report the
mismatch instead of a zero; never invent encodings. If the probe confirms the
exact value and the retry still returns zero, report that genuine zero without
hedging. Do not enumerate values for a PII-classified dimension; surface the
unresolved mismatch instead.
