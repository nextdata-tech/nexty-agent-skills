# Troubleshooting deployed Data Products

Field-tested symptom → diagnosis → fix catalog, compiled from debugging the
`jira-issues` DP on the demo environment (2026-06, NEX-639). Each entry gives
the error exactly as the platform reports it, the real root cause (often
different from what the error says), how to confirm, and the fix.

**General rule: the first error you see is frequently NOT the root cause.**
Work through the pod-level evidence (`kubectl describe pod`, container exit
codes, previous-container logs) before trusting the kernel's summary error.

---

## 1. "Execution timeout: Failed to start within the configured startup timeout"

**Symptom (kernel log / status reason):**

```
Execution timeout: Failed to start within the configured startup timeout
WARN Timeout waiting for execution to start - init container may have failed
```

The init log tail attached to the error looks *healthy* ("Virtual environment
extraction completed", "Execution context downloaded") — that is the tell. The
init container succeeded; the MAIN container died before signalling Started.

**Most common real cause: the main container was OOM-killed.** The k8s compute
pod's default memory limit is **512Mi**. Importing heavy libraries (torch,
sentence-transformers, spark clients) blows past it during import, before the
runner can signal startup. The driver cannot distinguish this from a slow
start, so it reports a timeout.

**Diagnose:**

```bash
kubectl get pods -n dps                        # find the compute pod (name contains the dp/run id)
kubectl describe pod -n dps <pod>              # look at Last State
# Last State: Terminated, Reason: OOMKilled, Exit Code: 137  → confirmed OOM
```

If the pod is already gone, check node events: `kubectl get events -n dps
--sort-by=.lastTimestamp | grep -i oom`.

A genuinely slow start (large venv, model download on first run) also hits the
default **180s** startup timeout without any OOM.

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

Rule of thumb: any DP importing torch/transformers needs at least a 2–4Gi
limit. Also batch large writes (see §7) — peak memory scales with the largest
in-flight batch.

---

## 2. "Failed to abort transaction: ... statement timeout" hides the real error

**Symptom (status / user-facing error):**

```
Internal error happened at compute
Caused by: Failed to abort transaction: error returned from database:
           canceling statement due to statement timeout
```

**Real cause:** a *different* error failed the run; the kernel then tried to
abort the open storage transaction, the abort ALSO failed (e.g. the platform
database was slow), and the abort error **replaced** the original error.

Fixed in kernel PR [nextdata-tech/nxd#6802] (abort failures are now logged,
the original error always surfaces). On clusters running an older kernel:
scroll **up** in the DP pod logs (`nxd logs <dp>` / `kubectl logs -n dps
<kernel-pod>`) — the genuine failure is logged before the abort attempt.

---

## 3. Promise / verify fails on any table with a vector column

**Symptom:**

```
Unknown type USER-DEFINED for column embedding
```

(or a CheckedPromise that fails on every run for a pgvector-backed model).

**Cause:** PostgreSQL's `information_schema` reports extension types
(`vector`, `halfvec`, `sparsevec`) as `USER-DEFINED`; older pgvector drivers
could not map that, so verification failed for ANY table containing an
embedding column. Fixed in [nextdata-tech/nxd#6802] (driver reads `udt_name`).

**Workaround on clusters without the fix:** keep the model on the port with
`.model(my_model)` but comment out `.promise(my_model)`, with a TODO to
re-enable after the platform upgrade. Do NOT delete the embedding column from
the model or split the model in two — that desyncs the catalog from the
physical table.

---

## 4. `type "vector" does not exist` (SQLSTATE 42704) at provision time

**Symptom:** pgvector storage provisioning fails creating a table with a
`vector(N)` column.

**Cause:** the pgvector EXTENSION lives in one schema per database (normally
`public`). The driver used to set `search_path` to the configured schema
*only*, so under any non-public schema the `vector` type was invisible. Fixed
in [nextdata-tech/nxd#6807] (search_path keeps `public`; extension pinned to
`public`).

**Workaround on clusters without the fix:** pin the port schema to public —
`pg_vector_config("public")`.

---

## 5. Spec validation errors — exact messages and what they actually mean

| Error | Real meaning | Fix |
|---|---|---|
| `At least one model should be defined on Output` | Output ports register models, but the OUTPUT level has none. Validation requires ≥1 model at the output (global) level. | Add `.model(m)` on `data_product_output()` itself, in addition to port-level. |
| `Attributes ['embedding'] defined with metadata do not exist in model X` (where X genuinely has no such attribute) | nxd_py bug: when a port has 2+ models, the attribute-metadata dict is shared between them, so vector-dimension metadata leaks across models. | Keep ONE model per pgvector port; don't re-declare the input model at the output level. |
| `Model expectation on model X is not supported for an nxd:api source` | Schema expectations need stored data to verify against; an unmanaged API source has none. | Remove `.expectation(model)` from the input; use a `custom(...)` verifier instead. |
| Promise silently absent from port models / verify never runs | `.promise()` was attached at the OUTPUT level. Since the promise-scoping change, port-level and output-level are distinct: the driver only sees PORT-level promises. | Move `.promise(model)` onto the `.port(...)` spec. |
| `409 ... model(s) no longer available: [...]` at launch | The image registry's schema-evolution check rejects removing/retyping models between **released** versions. | During iteration keep a `-dev` version (dev images overwrite in place, no check). Bump to a new release version only when the schema is settled. |

Also note: the pgvector driver provisions a table named `to_sql_name(model
name)` for every public port model — `target_table()` affects
verify/location reporting, NOT which table gets created. Keep model name ==
intended physical table name.

---

## 6. Compute pod's RPC sibling (MCP/API port) crashes

| Symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'mcp'` in the RPC pod | RPC runtime deps not in the DP venv | Add `nxd-drivers[rpc]` to the DP's dependencies. |
| `NameError: name '<module-global>' is not defined` when a tool is called | The RPC runtime executes the decorated function WITHOUT its module globals | Make RPC function bodies fully self-contained: all imports and constants inside the function. Cache heavyweight state on an imported module attribute (e.g. `sentence_transformers._my_model = m`). |
| RPC pod OOMKilled (exit 137) loading a model | RPC pods get the same 512Mi default limit; the spec API does not expose RPC pod resources yet | Patch the port's `_build_config` to inject a flattened `resources` key (the kubernetes/rpc driver reads it from port config). See the jira-issues `spec.py` `_rpc_with_resources` helper. |

---

## 7. Transform runs but writes wrong/zero/duplicate data

| Symptom | Cause | Fix |
|---|---|---|
| `TypeError: sequence item N: expected str instance, dict found` joining Jira fields | Jira REST v3 returns rich-text fields (description, comments) as **ADF** (Atlassian Document Format) dicts, not strings | Flatten ADF to text before chunking (walk `content` nodes, collect `text`). |
| Run green, 0 rows written | Source query window matches nothing (e.g. `updated >= -PT30D` on a dormant project) | Verify the query returns data *for the actual source state* before blaming the pipeline; widen the window or target the active project. |
| `ON CONFLICT` / upsert errors from langchain `PGVectorStore` | NXD-provisioned tables have no PK or unique index; langchain upserts on `langchain_id` | `CREATE UNIQUE INDEX IF NOT EXISTS ... ON <table> (langchain_id)` at transform start. |
| Row count multiplies on every run | Chunk ids generated with random UUIDs → every run inserts fresh rows | Deterministic ids: `uuid.uuid5(uuid.NAMESPACE_URL, f"<source>:{record_key}:{chunk_index}")` makes reruns idempotent upserts. |
| Backing Postgres restarts / `server closed the connection unexpectedly` mid-write | One giant write spikes DB memory (small dev/demo instances OOM their backends) | Batch writes (e.g. 500 docs per `add_documents` call). |

---

## 8. Custom expectation fails: contract pod stuck in Pending

**Symptom:**

```
Error happened while verifying: Contract verification pod failed:
Pod startup timeout: pod 'contract-...' stuck in Pending state;
Initialized: False, reason=ContainersNotInitialized ...
```

**Meaning:** `Pending` is a *scheduling/init* problem, not a code problem —
the contract container never ran. The message does not yet surface the
scheduling reason.

**Diagnose (needs cluster access):**

```bash
kubectl describe pod -n dps contract-<id>      # Events section has the real reason
kubectl get events -n dps --sort-by=.lastTimestamp | grep contract-<id>
```

Usual culprits: cluster out of allocatable CPU/memory (`FailedScheduling`),
image pull failure on the contract image (`ErrImagePull`), or a missing
volume/secret. If the cluster is at capacity, lower the DP's compute resource
*requests* or free node capacity; the contract pod itself takes the defaults.

---

## Debugging workflow (do this in order)

1. `nxd ls data-products` — state.
2. Status with reasons:
   `GET https://dp.<domain>/<dp>/api/v1/status?include_reason=true&include_details=true`
   (header `x-nextdata-token: <PAT>` locally, `Authorization: Bearer` on
   multi-domain envs).
3. `nxd logs <dp>` — read from the FIRST error, not the last (see §2).
4. `kubectl get pods -n dps` + `kubectl describe pod` on anything not
   Running — exit code 137 = OOM (§1), Pending = scheduling (§8).
5. Re-launch with `--debug-mode` before concluding anything from a single
   WARN line — default log level hides most INFO.
6. After a fix, confirm data: row counts + a sample query against the output
   port, not just a green state.
