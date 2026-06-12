# Troubleshooting deployed Data Products

Symptom → diagnosis → fix reference for Data Products that fail after
`nxd launch`. Each entry gives the error as the platform reports it, the
likely root cause (sometimes different from what the error text suggests),
how to confirm, and the fix.

**General rule: the first error you see is not always the root cause.**
Where you have cluster access, work through the pod-level evidence
(`kubectl describe pod`, container exit codes, previous-container logs)
before concluding from the summary error alone.

---

## 1. "Execution timeout: Failed to start within the configured startup timeout"

**Symptom (status reason / logs):**

```
Execution timeout: Failed to start within the configured startup timeout
WARN Timeout waiting for execution to start - init container may have failed
```

The init log tail attached to the error looks *healthy* ("Virtual environment
extraction completed", "Execution context downloaded") — that is the tell. The
init container succeeded; the MAIN container died before signalling it
started.

**Most common real cause: the main container ran out of memory.** The compute
pod's default memory limit is modest. Importing heavy libraries (torch,
sentence-transformers, spark clients) can exceed it during import, before the
transform signals startup, and the resulting kill is reported as a timeout.

**Diagnose (with cluster access):**

```bash
kubectl get pods -n dps                        # find the compute pod
kubectl describe pod -n dps <pod>              # check Last State
# Last State: Terminated, Reason: OOMKilled, Exit Code: 137  → confirmed OOM
```

Without cluster access, treat heavy ML/data dependencies in the venv as a
strong prior for OOM. A genuinely slow start (large venv, model download on
first run) can also exceed the default startup timeout without any OOM.

**Fix — set resources and startup timeout on the transform in `spec.py`:**

```python
.transform(
    code(transform)
    .compute(f"https://.../services/k8s-compute")
    .config({
        "startup_timeout_secs": 600,
        "resources": {
            "requests": {"cpu": "1", "memory": "1Gi", "ephemeral-storage": "8Gi"},
            "limits": {"memory": "4Gi"},
        },
    })
    .when(...)
)
```

Rule of thumb: anything importing torch/transformers needs at least a 2–4Gi
limit. Also batch large writes (see §6) — peak memory scales with the largest
in-flight batch.

---

## 2. Error reads "Failed to abort transaction: ..."

**Symptom:**

```
Internal error happened at compute
Caused by: Failed to abort transaction: ...
```

**Meaning:** a *different* error failed the run first; the platform then tried
to roll back the open storage transaction and that rollback also failed.
Recent platform versions always surface the original error; if you see the
abort error as the top-level reason, you are on an older version — scroll
**up** in the Data Product logs (`nxd logs <dp>`): the genuine failure is
logged before the abort attempt.

---

## 3. Vector-column verification or provisioning errors (pgvector)

Two related symptoms on pgvector-backed output ports:

- Promise/verify fails with `Unknown type USER-DEFINED for column <name>` —
  older platform versions could not verify any table containing a `vector`
  column.
- Provisioning fails with `type "vector" does not exist` (SQLSTATE 42704) when
  the port is configured with a non-`public` schema — the pgvector extension
  lives in one schema per database (normally `public`), and older versions did
  not keep `public` on the search path.

Both are fixed in current platform versions. If the target environment still
shows them:

- For the verify failure: keep the model registered on the port with
  `.model(my_model)` but temporarily comment out `.promise(my_model)`, with a
  TODO to re-enable after the platform upgrade. Do NOT delete the embedding
  column from the model or split the model in two — that desyncs the catalog
  from the physical table.
- For the 42704: pin the port schema to public — `pg_vector_config("public")`.

---

## 4. Spec validation errors — exact messages and what they actually mean

| Error | Real meaning | Fix |
|---|---|---|
| `At least one model should be defined on Output` | Output ports register models, but the OUTPUT level has none. Validation requires ≥1 model at the output (global) level. | Add `.model(m)` on `data_product_output()` itself, in addition to port-level. |
| `Attributes ['<attr>'] defined with metadata do not exist in model X` (where X genuinely has no such attribute) | Known SDK limitation: when a port has 2+ models, attribute metadata can leak between them. | Keep ONE model per pgvector port; don't re-declare the input model at the output level. |
| `Model expectation on model X is not supported for an nxd:api source` | Schema expectations need stored data to verify against; an unmanaged API source has none. | Remove `.expectation(model)` from the input; use a `custom(...)` verifier instead. |
| Promise silently absent from port models / verify never runs | `.promise()` was attached at the OUTPUT level. Port-level and output-level are distinct: the storage driver only sees PORT-level promises. | Move `.promise(model)` onto the `.port(...)` spec. |
| `409 ... model(s) no longer available: [...]` at launch | The image registry rejects removing/retyping models between released versions (schema evolution check). | During iteration keep a `-dev` version (dev images overwrite in place, no check). Bump to a new release version only when the schema is settled. |

Also note: the pgvector driver provisions a table named after each public port
model (lowercased, separators → `_`) — `target_table()` affects
verify/location reporting, NOT which table gets created. Keep model name ==
intended physical table name.

---

## 5. RPC output port (MCP/API serving) crashes

| Symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'mcp'` in the RPC pod | RPC runtime deps not in the DP venv | Add `nxd-drivers[rpc]` to the Data Product's dependencies. |
| `NameError: name '<module-global>' is not defined` when a tool is called | The RPC runtime executes the decorated function WITHOUT its module globals | Make RPC function bodies fully self-contained: all imports and constants inside the function. Cache heavyweight state on an imported module attribute (e.g. `sentence_transformers._my_model = m`). |
| RPC pod killed (exit 137) loading a model | RPC pods get the same default memory limit as compute pods | Raise the RPC pod's memory. If the spec API version in use doesn't expose RPC resources, the kubernetes/rpc driver reads a flattened `resources` key from the port config. |

---

## 6. Transform runs but writes wrong / zero / duplicate data

| Symptom | Cause | Fix |
|---|---|---|
| `TypeError: sequence item N: expected str instance, dict found` joining API fields | Some APIs return rich-text fields as structured documents (e.g. Atlassian Document Format), not strings | Flatten the document to text before chunking. |
| Run green, 0 rows written | Source query window matches nothing (e.g. a 30-day lookback against a dormant source) | Verify the query returns data *for the actual source state* before blaming the pipeline; widen the window or target the active dataset. |
| `ON CONFLICT` / upsert errors from langchain `PGVectorStore` | Provisioned tables have no PK or unique index; langchain upserts on `langchain_id` | `CREATE UNIQUE INDEX IF NOT EXISTS ... ON <table> (langchain_id)` at transform start. |
| Row count multiplies on every run | Chunk ids generated with random UUIDs → every run inserts fresh rows | Deterministic ids: `uuid.uuid5(uuid.NAMESPACE_URL, f"<source>:{record_key}:{chunk_index}")` makes reruns idempotent upserts. |
| Backing Postgres restarts / `server closed the connection unexpectedly` mid-write | One giant write spikes DB memory (small instances can kill their backends) | Batch writes (e.g. 500 docs per `add_documents` call). |

---

## 7. Custom expectation fails: contract pod stuck in Pending

**Symptom:**

```
Error happened while verifying: Contract verification pod failed:
Pod startup timeout: pod 'contract-...' stuck in Pending state;
Initialized: False, reason=ContainersNotInitialized ...
```

**Meaning:** `Pending` is a *scheduling/init* problem, not a code problem —
the contract container never ran.

**Diagnose (needs cluster access):**

```bash
kubectl describe pod -n dps contract-<id>      # Events section has the real reason
kubectl get events -n dps --sort-by=.lastTimestamp | grep contract-<id>
```

Usual culprits: cluster out of allocatable CPU/memory (`FailedScheduling`),
image pull failure (`ErrImagePull`), or a missing volume/secret. If the
cluster is at capacity, lower the Data Product's compute resource *requests*
or free node capacity.

---

## Debugging workflow (do this in order)

1. `nxd ls data-products` — state.
2. Status with reasons:
   `GET https://dp.<domain>/<dp>/api/v1/status?include_reason=true&include_details=true`
   (header `x-nextdata-token: <PAT>`, or `Authorization: Bearer` on
   multi-domain environments).
3. `nxd logs <dp>` — read from the FIRST error, not the last (see §2).
4. With cluster access: `kubectl get pods -n dps` + `kubectl describe pod` on
   anything not Running — exit code 137 = out of memory (§1), Pending =
   scheduling (§7).
5. Re-launch with `--debug-mode` before concluding anything from a single
   WARN line — the default log level hides most INFO.
6. After a fix, confirm data: row counts + a sample query against the output
   port, not just a green state.
