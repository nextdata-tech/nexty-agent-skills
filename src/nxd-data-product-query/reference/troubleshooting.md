# Troubleshooting query-time failures

Symptom → cause → fix for failures hit while querying a port. Diagnose before
retrying: the same symptom (e.g. an empty result) has more than one cause, so
confirm which before changing the query.

| Symptom | Cause | Fix |
|---|---|---|
| `401 Unauthorized` from a port call | Leased credential or PAT expired (`tokens.json` `expiry` passed), or the wrong auth header. DP REST uses `x-nextdata-token`, NOT `Authorization: Bearer`. | Re-run `nxd login` (or **nxd-setup**) and re-request `connect`; send the PAT as `x-nextdata-token`. |
| `403` / `SignatureDoesNotMatch` fetching a file URL | The presigned URL TTL elapsed mid-session (they are short-lived). | Re-request `connect` for a fresh URL; don't reuse a cached one past its TTL. |
| `connect` returns `unsupported` | The port's driver has no query recipe wired, or the infra profile couldn't be resolved. | Resolve the infra profile from the active mesh; confirm the port's driver type via `gateway_tools.py details --dp <dp> --outputs`. |
| `connect` returns `approval_pending` | Access requires a pending approval. | Stop. Surface the `message` / `tracking_url` to the user. Do NOT poll. |
| Vector search returns nonsense / irrelevant hits | Query embedded with a different model than the DP indexed with. | Read the index model from the DP `description` / `/v1/info`; embed the query with that exact model. |
| Vector search errors with a dimension mismatch | Query vector dimension ≠ the indexed column dimension. | Match the embedding model so dimensions agree (e.g. 384 vs 1536). |
| SQL query against a pgvector port returns 0 rows | Querying the metadata table by the wrong table name, or the DP hasn't run yet (no data). | Confirm the physical table name (model name, lowercased) and that the DP reached `STARTED` with a successful run. |
| RPC/MCP call fails to connect / 404 | Wrong tool wire name or trailing-slash mismatch on the multiplexer endpoint; or the DP MCP port is unhealthy. | Re-confirm the `<function>__<hash>` name from `gateway_tools.py tools --dp <dp>` and check `gateway_tools.py health`; if the port itself is failing, debug the DP with **nxd-debugging-data-products**. |
| `run_semantic_query` returns "metrics span multiple grains" | Metrics from two different-grain models were combined in one call (chasm-trap guard) — correct governance, not a transient error. | Do NOT retry the same combined call. Call `describe_model` on each model to confirm grain membership, then issue one `run_semantic_query` per model sharing a compatible dimension; present the result sets separately. See §6d "Semantic-layer MCP ports". |
| `run_semantic_query` returns `error: "dimension X is not compatible with metric Y"` | The dimension can't slice that metric (not in `compatible_dimensions`, no join reaching it). | Re-pick from `describe_model`'s `compatible_dimensions` / `joins.reaches_dimensions`; re-run the §6f gate. |
| Filtered semantic query returns 0 rows, but the unfiltered query returns rows | Likely a **value mismatch** — the NL literal (`"California"`) doesn't match the stored encoding (`"CA"`); structural validation can't catch it (the dimension exists, only the value diverges). | Surface to the user; ask for the stored form or drop the filter. Do **NOT** retry with invented encodings. Durable fix is server-side value-linking (§6f "Not yet built"). |

When the failure is the Data Product itself (port unhealthy, no data produced,
RPC pod crashing) rather than the query, switch to the
**nxd-debugging-data-products** skill.
