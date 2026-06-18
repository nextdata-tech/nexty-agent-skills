# Troubleshooting deployed Data Products

## Contents
- Startup timeout / OOM diagnosis
- Spec validation errors
- RPC output port crashes
- Transform writes wrong, zero, or duplicate data
- Custom expectation pod Pending
- Stuck in PROVISIONING / PENDING
- Infra-profile / service resolution failures
- Debugging workflow

Symptom → diagnosis → fix reference for Data Products that fail after
`nxd launch`. Each entry gives the error as the platform reports it, the
likely root cause (sometimes different from what the error text suggests),
how to confirm, and the fix.

**General rule: the first error you see is not always the root cause.** Work
the evidence before patching: the platform status reason
(`GET /api/v1/status?include_reason=true&include_details=true`) and `nxd logs`
read from the FIRST error are enough to root-cause most failures with only the
public CLI. Where you also have cluster access, pod-level evidence
(`kubectl describe pod`, container exit codes, previous-container logs) can
confirm a hypothesis — but it is a deepening, not a prerequisite.

**Diagnose before you patch — discriminate, don't guess.** When two causes
explain the same symptom, run the one cheap read that tells them apart before
changing any code:

| Symptom | Competing causes | Discriminating read |
|---|---|---|
| "startup timeout" | OOM during import vs genuinely slow start | status reason / `Last State: OOMKilled` exit 137 → OOM; clean exit + long init log → slow start (§1) |
| green run, no data | empty source window vs broken write path | row count at source for the queried window before blaming the transform (§4) |
| `nxd validate` exits 0, no output | actually passed vs not authenticated | `nxd whoami` — `Not logged in` ⇒ validation NOT RUN (see [common-pitfalls.md](common-pitfalls.md)) |
| pgvector write refused | wrong column type vs dimension mismatch | exact error text — `not type Vector` ⇒ declared `string()`; `expected N got M` ⇒ wrong `vector_embeddings(dim)` (§4) |
| contract pod never runs | code error vs scheduling | pod phase — `Pending` ⇒ scheduling, the container never ran (§5) |
| `Service <name> not found` at validate/launch | service-name typo vs wrong infra profile vs service absent from mesh | list the profile's real services (`nxd --config=<session_config> rest -u /api/v1/infraprofiles/<profile>/services`) and compare to the name in `.source(...)`/`storage(...)` — it is a profile/service problem, NOT a transform bug (§7) |

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
limit. Also batch large writes (see §4) — peak memory scales with the largest
in-flight batch.

---

## 2. Spec validation errors — exact messages and what they actually mean

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

## 3. RPC output port (MCP/API serving) crashes

| Symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'mcp'` in the RPC pod | RPC runtime deps not in the DP venv | Add `nxd-drivers[rpc]` to the Data Product's dependencies. |
| `NameError: name '<module-global>' is not defined` when a tool is called | The RPC runtime executes the decorated function WITHOUT its module globals | Make RPC function bodies fully self-contained: all imports and constants inside the function. Cache heavyweight state on an imported module attribute (e.g. `sentence_transformers._my_model = m`). |
| RPC pod killed (exit 137) loading a model | RPC pods get the same default memory limit as compute pods | Raise the RPC pod's memory. If the spec API version in use doesn't expose RPC resources, the kubernetes/rpc driver reads a flattened `resources` key from the port config. |

---

## 4. Transform runs but writes wrong / zero / duplicate data

| Symptom | Cause | Fix |
|---|---|---|
| `TypeError: sequence item N: expected str instance, dict found` joining API fields | Some APIs return rich-text fields as structured documents (e.g. Atlassian Document Format), not strings | Flatten the document to text before chunking. |
| Run green, 0 rows written | Source query window matches nothing (e.g. a 30-day lookback against a dormant source) | Verify the query returns data *for the actual source state* before blaming the pipeline; widen the window or target the active dataset. |
| `ON CONFLICT` / upsert errors from langchain `PGVectorStore` | Provisioned tables have no PK or unique index; langchain upserts on `langchain_id` | `CREATE UNIQUE INDEX IF NOT EXISTS ... ON <table> (langchain_id)` at transform start. |
| Row count multiplies on every run | Chunk ids generated with random UUIDs → every run inserts fresh rows | Deterministic ids: `uuid.uuid5(uuid.NAMESPACE_URL, f"<source>:{record_key}:{chunk_index}")` makes reruns idempotent upserts. |
| Backing Postgres restarts / `server closed the connection unexpectedly` mid-write | One giant write spikes DB memory (small instances can kill their backends) | Batch writes (e.g. 500 docs per `add_documents` call). |
| Write fails with `Embedding column is not type Vector` (or langchain refuses to write to the pgvector table) | The embedding attribute was declared `string()` in the semantic model. The pgvector driver provisions the table FROM the model, so a `string()` attribute becomes a `TEXT` column — langchain/pgvector then refuses to store vectors in it. The error surfaces at write time, far from the spec, so it reads as a transform bug. | Declare the embedding attribute as `vector_embeddings(<dim>)` with the dimension your embedding model emits (e.g. `vector_embeddings(384)` for `all-MiniLM-L6-v2`, `vector_embeddings(1536)` for OpenAI `text-embedding-3-small`). Re-launch so the table is re-provisioned as a `vector` column. |
| Write fails with a dimension-mismatch error (`expected N dimensions, got M`) | The declared `vector_embeddings(N)` dimension does not match what the embedding model actually returns | Align the declared dimension with the model output; if the model changed, the table must be re-provisioned (drop/relaunch) so the column width matches. |

---

## 5. Custom expectation fails: contract pod stuck in Pending

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

## 6. Stuck in `PROVISIONING` / `PENDING`

A Data Product that never reaches `STARTED` is reporting a *state*, not yet an
error. Read the state before reading code:

| State | Meaning | First check |
|---|---|---|
| `PROVISIONING` | Installing the Python environment | Dependency install is failing — a package name, an unavailable version, or a registry that can't be reached. Inspect the init logs and `requirements.txt`. |
| `PENDING` | Waiting to start | Usually transient; if it never advances, the compute can't be scheduled (see §5 for the contract-pod analogue). |
| `FAILED` | Transform or model error | Read the status reason (workflow step 2) and `nxd logs`. |
| `STARTED` | Healthy | — |

`ModuleNotFoundError: No module named 'nxd.data_product'` (or a missing-bindings
error) during `PROVISIONING` means `requirements.txt` is missing the SDK.
**Both `nxd_core` and `nxd_data_product` are always required** — see
[common-pitfalls.md](common-pitfalls.md).

---

## 7. Infra-profile / service resolution failures

A service URL in `.source(...)`, `storage(...)`, or `.compute(...)` is resolved
against the **active mesh's infra profile** when you `nxd validate` / `nxd launch`
— `nxd validate` is NOT offline-only (see [common-pitfalls.md](common-pitfalls.md)).
A name that doesn't resolve fails here, far from the transform code, so it reads
like a build bug. It isn't: **`Service <name> not found` and friends are
profile/service-wiring problems, never transform-runtime problems.**

**Verify the name before you trust the spec.** Don't guess service names — list
what the chosen profile actually offers and match exactly:

```bash
# Profiles available on the active mesh:
nxd ls infra-profiles --config=<session_config>

# Services declared in a chosen profile (spelling is "infraprofiles", no hyphen):
nxd --config=<session_config> rest -u /api/v1/infraprofiles/<profile>/services

# Spec + live source/service preflight in one shot:
nxd --config=<session_config> verify dp --dir <data_product_directory> --json
```

| Symptom | Real cause | Confirm | Fix |
|---|---|---|---|
| `Service <name> not found` | The name in `.source(...)`/`storage(...)`/`.compute(...)` doesn't match any service in the chosen profile — typo, wrong profile selected, or service genuinely absent from this mesh | List the profile's services (above); the name is missing or spelled differently | Use the exact name from the listing. Compute service names vary by profile (`k8s-compute`, `k8s-executor`, a Databricks compute) — read it, don't assume. |
| `infra profile <name> not found` / profile won't resolve | `infra_profile="..."` names a profile that doesn't exist on the active mesh (often a hardcoded demo name like `ecommerce`) | `nxd ls infra-profiles` — the name isn't in the list | Set `infra_profile` to a real profile from the list; never hardcode a demo name. |
| Validate/launch hits the wrong host or 401s on a service that "exists" | Service URL host points at a different mesh than the active `--config` | Compare the `<app_url>` host in the URL to the active mesh's `app_url` (`~/.nxd/meshes.json` selected entry) | Rebuild URLs from the active mesh host: `https://<app_url>/infra-profile/<profile>#/services/<service>`. |
| Service resolves but read/write is refused (auth/permission) | The service exists, but the leased credential lacks access, or the profile points at the wrong account/catalog | `nxd verify dp ... --json` reports the per-service failure; check the credential type and the service's target account in the profile YAML | Fix the profile's service config / request access; this is an environment problem, not a spec problem. |

`nxd validate` exiting `0` with a service problem still pending means auth wasn't
confirmed — run `nxd whoami` first (anti-false-PASS, see common-pitfalls.md).

---

## Debugging workflow (do this in order)

The CLI/REST steps below need only the public `nxd` CLI and a PAT — no cluster
access. The pod-level steps are an *optional* deepening for when you do have
cluster access; never block on them.

1. `nxd ls data-products` — state (see §6 for what each state means).
2. Status with reasons (the single highest-value read — structured failure
   reason without logs):
   `GET https://dp.<domain>/<dp>/api/v1/status?include_reason=true&include_details=true`
   (header `x-nextdata-token: <PAT>`, or `Authorization: Bearer` on
   multi-domain environments). Mint a PAT with
   `nxd create personal-access-token --name debug --expires "1 day"`.
3. `nxd logs <dp>` — read from the FIRST error, not the last — later errors are often cleanup fallout from the first one.
4. Re-launch with `--debug-mode` before concluding anything from a single
   WARN line — the default log level hides most INFO. A lone WARN
   (e.g. `Queuing run since initial policies are not evaluated yet`) is often a
   transient race that resolves in milliseconds, not a bug.
5. *(Optional — cluster access only.)* `kubectl get pods -n dps` +
   `kubectl describe pod` on anything not Running — exit code 137 = out of
   memory (§1), Pending = scheduling (§5). The public status reason in step 2
   already reports OOM/scheduling causes for most failures.
6. If only some models in a multi-model DP failed, retry just those rather than
   relaunching the whole product:
   `nxd run <dp> --retry --follow`. (There is no `nxd retry` / `nxd reset` —
   use `nxd run --retry`.)
7. After a fix, confirm data: row counts + a sample query against the output
   port, not just a green state.
