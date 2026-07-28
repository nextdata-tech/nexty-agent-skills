# NEX-827 — constraints as expectations and promises

Design record. Two halves ship together: the local storage driver gains real
model verification, and the generation skills learn to author contracts.

## The problem

A constraint the user states about their data — on the way in or on the way out
— survives today only as prose in the closure's context record. Two mechanisms
exist and neither is the contract surface:

- **Prose** (context record, policy read-back) — not machine-checked, rots.
- **In-transform asserts** — real, but only on derived models, only over the
  source-vs-derived relationship, and invisible to anyone querying the product.

`.expectation(...)` and `.promise(...)` are exactly the surface for this, and
they are currently unused on the local path.

## Runtime facts

Verified against the code before designing; each changes what is shippable.

| Fact | Evidence |
|---|---|
| spec compilation preserves expectations and promises into the manifest | `nxd_py/.../spec/_writer.py:66-76`; `_spec.py:1663-1678` (`build_source_expectations`), `_spec.py:3365-3382` (`build_promises`) |
| kernel dispatch is identical to the platform path (same binary) | `kernel/data_product/src/outputs/verification.rs:233-274`; `registry/domain/handlers/storage_streaming.rs:13,54` |
| the local storage driver returns an **empty verification stream** and reports **zero expectations** | `driver_impls/drivers/nxd-local-drivers/src/lib.rs:93-114` |
| an empty stream is **indistinguishable from all-pass** — it folds to `Pass` | `nxd_core/src/verification.rs:263` — `worst_result.unwrap_or(VerificationOutcome::Pass)` |
| a custom verify with no explicit compute routing defaults to the platform contract executor and **fails at boot** — not because that driver is unregistered (it is registered, `k8s_compute/mod.rs:496,829`) but because `generate_contract` resolves a `kubernetes-contract` **infra-profile service** the local profile does not declare | `_spec.py:857-887` (line 866); `kernel_commons/src/config_loading/drivers.rs:1461-1494` |
| **UNRESOLVED — routing a custom verify to local python compute is NOT established to work.** Two independent static traces say it cannot: `LocalPythonCompute` registers only `ComputeDriverPlugin`, never a `ContractDriverItem` (`local_python_compute.rs:366`), so `generate_contract` → `get_driver` misses and boot fails the same way; and `STATIC_RUN_KIND = Streaming` (`local_python_compute.rs:62`) puts desktop DPs on the streaming RunDone path, which verifies with `skip_contracts=true` (`compute/mod.rs:2653-2659`) — kernel-side contract verify never runs for a streaming DP. The relay at `local_python_compute.rs:160-165` proves only that **in-script registered validations** report their results back, which is a different mechanism. **Blocked on a live E2E.** | see § Open question |

Three consequences:

1. The obvious authoring shape — a custom verify with no routing — **bricks the
   build at boot**. Guidance that teaches contracts without teaching routing
   ships a reliable failure. But the corrected shape is **not yet known** (see
   the unresolved row above): no custom-verify guidance is written until a live
   E2E establishes what actually executes.
2. A model contract on the local driver **looks enforced and is not**. Silent
   green is worse than a crash. This is why the driver work is in scope rather
   than deferred.
3. **Driver verification alone is cosmetic.** The supervisor's publish gate never
   consults promise results, and the local driver has no transaction to roll
   back — so a Failed promise today still publishes and still serves the
   violating rows. The supervisor gate below is load-bearing, not a follow-up.

## The publish gate — why this is the load-bearing half

The desktop publish path is: `POST /api/v1/compute/run {"wait":true}` returns
HTTP 200 (success determined by status line alone, `kernel.rs:1005-1044`) →
`publish::artifact_present(&staging)` → dlt checkpoint capture and verify →
`VERIFIED` → `PROMOTING` → `materialize_generation` → `publish_protocol` →
`flip_pointer` (`supervisor.rs:392-448`).

**No step reads `CheckedPromise`, `AllPromisesChecked`, or the DP status.** A
streaming promise failure pushes `DataProductStatus::Failed` as an event
(`compute/mod.rs:1881-1891`) into a state DB the publish path never opens. And
because the local driver declares no transaction, the transform has already
written the violating rows into the tables that get promoted and served.

So "a violating row fails the run" is currently unfalsifiable: kernel-error,
DP-status, and supervisor-publish disagree about what failure means. Note the
platform path agrees — `OutputDomain::run` returns `Ok(())` on
`VerificationFailed` (`outputs/mod.rs:491-493,546`); there, "fails" means the
transaction aborts and the status flips, not that the call errors.

**Scope:** between child reap and `VERIFIED`, the supervisor reads the run's
promise outcomes and refuses to promote on any `Failed` — leaving the run
terminal-failed rather than disarming the failure. Two things to establish
empirically first: whether the `{"wait":true}` response even resolves after
promise checks drain (they are drained asynchronously in the event loop, so the
wait may be on transform completion only), and what the observable is that the
supervisor can read without racing the kernel's shutdown.

**Acceptance names its observable:** the supervisor does not flip the pointer,
and the previously published artifact — if any — remains the served one.

## Half one — local storage driver verification

### What the driver can actually see

The kernel already supplies the full model definitions before `new()` is called
(`kernel_commons/src/config_loading/config.rs:1069-1099`), as
`DriverConfig.public_output_models` / `input_models` / `private_models`. Each is
a `Model { name, description, fields, sampling }` whose `Field` carries:

```rust
pub struct Field { pub name: String, pub data_type: DataType,
                   pub description: Option<String>,
                   pub metadata: Option<BTreeMap<String, String>>,
                   pub constraints: Option<Constraints> }
pub struct Constraints { pub min: Option<String>, pub max: Option<String>,
                         pub nullable: bool }
```

**`LocalDuckDbStorage::new()` discards this entirely** — the parameter is
`_config`, unused (`lib.rs:58-67`). Capturing it is the prerequisite for
everything else, and is what every reference driver already does (Postgres
`storage.rs:42-43,124-125`; Snowflake, BigQuery, Databricks the same).

**There is no primary-key concept in the wire model.** `Field`/`Constraints`
carry name, type, nullability and min/max, and nothing else; `primary_key`
appears nowhere in `nxd_driver_wire_types` or `yaml_schemas`. So driver-side
key-uniqueness verification is **not expressible from the declared schema** and
is out of scope for the driver half — it stays with the transform asserts, which
read the key from the closure's own Python. This corrects the initial scoping.

### What the driver will verify

Per promised model, one suite, following the shape all four reference drivers
use — look the model up by name in the stored `Vec<Model>`, resolve its physical
table from `model_tables`, issue one query, diff, return via `stream::once`:

- **column presence** — every declared field exists on the landed table.
- **type conformance** — the landed column's type is compatible with the
  declared `data_type`, reusing the existing coercion logic rather than a new
  comparison vocabulary.
- **nullability** — a field declared non-nullable has no nulls.
- **range** — `Constraints::min`/`max`, when present, hold over the column.

Failure returns `VerificationOutcome::Failed` with an `extra_info_json["error"]`
naming the column and the actual-vs-declared values, matching Snowflake
(`verify.rs:210-257`) and BigQuery (`verification.rs:79-165`).

`expectations()` returns one `Expectation` per model/table pair instead of an
empty vec, mirroring Postgres (`storage.rs:280-294`).

### How the query runs — through the venv interpreter, not a native crate

**Decided: the driver queries DuckDB through the desktop venv's Python
interpreter. No new native dependency.**

The rejected alternative was adding the `duckdb` crate to `nxd-local-drivers`.
That crate is a direct dependency of the kernel
(`kernel/data_product/Cargo.toml:139`) and is force-linked through
`use_drivers_workaround_rust_issues_133491` (`lib.rs:95`), so a bundled
`duckdb` would compile libduckdb's C++ into the platform kernel image, every CI
kernel build, and the arm64 wheel pipeline — to serve a desktop-only code path.
Feature-gating it per-binary is not supported by the current crate layout, and
gating it at all would undermine the same-binary property that makes desktop
verification behave like the platform.

The venv route costs nothing at build time and reuses machinery that already
exists: the desktop venv necessarily has `duckdb` (dlt writes through it), and
`LocalPythonCompute` already owns interpreter resolution — manifest interpreter,
then config, then `NXD_DESKTOP_PYTHON`, then error.

Constraints this route carries:

- **Interpreter resolution must be shared, not re-derived.** The storage driver
  reuses the compute driver's resolution order rather than reading the env var
  directly, or the two disagree about which interpreter is authoritative.
- **Subprocess discipline** — bounded timeout and a reaped child, per regression
  `rust-general` #15. A verification query that hangs must fail the check, not
  the run's shutdown.
- **The failure modes are wider than a library call.** Interpreter missing,
  `duckdb` import failing, subprocess killed — each must be distinguishable from
  "the data violated the contract". An infrastructure failure that reports as a
  contract failure is the mirror image of the vacuous pass this work removes;
  reporting it as a pass is worse still.
- **Type conformance is new code, not reuse.** There is no DuckDB type
  vocabulary in the workspace to lean on — the earlier draft mislabeled this.

### Other constraints on the implementation

- **The stream must terminate.** A non-terminating verify stream hangs the
  kernel's drain — regression `rust-driver-impls` #43, which is the same rule the
  current `stream::empty()` violates from the other direction.
- **No transaction/staging concept exists on this driver** — it overrides none of
  `start_transaction` / `commit_transaction` / `output_for_transaction` /
  `verify_output_model_for_transaction`, so `txn_state` is always `None` and
  verification targets the one static `model_tables` map. Nothing to preserve
  here, unlike the transactional drivers — and nothing to roll back either, which
  is why the publish gate carries the enforcement.
- **Emit an outcome metric** for the new query path — regression
  `always-applied` #36.
- **Bounded per-model cost.** Verification re-scans the full table each run; the
  suite needs a bound before tables grow, the local analog of regression
  `rust-driver-impls` #93.

### Input-side expectations stay vacuous — and the guidance must say so

Implementing `verify_output_model` alone leaves the taxonomy's **input** side
exactly where the output side is today. On a desktop closure the source is CSVs
that dlt reads inside the transform; no driver fronts the CSV service, and
`verify_source_aligned_model` stays an empty stream. A stated input constraint
compiled to an expectation would look enforced and not be — this work's own
consequence #2, reproduced on the half it did not fix.

Two options, and the choice belongs with the implementation rather than this
document: implement `verify_source_aligned_model` against the landed base tables
(meaningful here, since base models land in DuckDB too), or direct every stated
constraint to the **promise** side and state plainly why the input side is not
available. What is not acceptable is declaring input expectations that silently
pass.

### Acceptance

Behavioural, not structural: a violating row **fails the run**, proven by a test
that fails without the driver change. An assertion that verification was
*declared* is exactly the vacuous-pass this work removes.

## Half two — generation skills

### The contract taxonomy

Three origins, two sides:

| Origin | Input side (expectation) | Output side (promise) |
|---|---|---|
| **Stated** — the user's own words | "order_id is never null" | "every row categorised" |
| **Discovered** — profiling found it, user confirmed | key held across the export; `status` domain; `amount >= 0` | — |
| **Derived** — implied by a ruling the generator encoded | reference data covers every source key | the reconciliation, promoted to a declared promise |

### Discovered invariants are confirmed, never adopted silently

Profiling emits **candidates with evidence** — null counts, ranges, distinct
cardinality, enum domain where cardinality is low, cross-model key coverage —
each carrying what was observed and over how many rows. A candidate is presented
and adopted **only on the user's reply**.

The reasoning is the one already applied to primary keys: held-on-this-export is
not proof it holds on the next export. Auto-adopting is lower friction but lets a
future build fail on an invariant the user never saw and never agreed to. A
constraint the user **stated** needs no confirmation — it is already their words.

The adversarial case the eval must cover: an invariant that is true of the sample
and wrong of the domain — a `notes` column 100% null across 50 rows must not
become a declared non-null-complement or an enum domain of one.

**Confirmation is one batched turn, tiered and capped.** A fifty-column table
yields thirty-plus candidates; one-per-turn is fatigue, and a default-on
checklist is auto-adoption wearing a consent costume. So:

- **Filter by rule before asking.** Only candidates that are load-bearing for a
  stated question, or that clear an evidence floor (a minimum row count, a
  non-degenerate domain), reach the user. The 100%-null-`notes` class is
  excluded **by rule, not by asking** — never spend a confirmation turn on a
  candidate the agent should have rejected.
- **One turn, hard-capped** at roughly seven proposals. Everything filtered out
  is recorded as an observation in the context record, not as a contract.
- **Never share a turn with the policy read-back.** These are two gates of equal
  strength with different subjects, and the existing read-back's trigger
  vocabulary ("a procedure changing a score, verdict, gate outcome, or which rows
  land") does not cover discovered invariants. Presenting both together lets one
  reply be read as both approvals, which retroactively weakens the policy gate.
  This is an invariant, not a preference.

### Wiring rules

- Expectations attach to inputs; promises attach to the output **port**. The
  existing expectations/promises guidance already states this and it carries over
  unchanged.
- Model contracts and custom verifies are different objects with different
  execution paths; the guidance names both rather than collapsing them.
- **Custom-verify guidance is BLOCKED** pending the E2E below. The earlier draft
  made "route every custom verify to local python compute" the highest-
  consequence rule in this document; two static traces say that shape fails at
  boot exactly like the unrouted one. Until a live run establishes what
  executes, the guidance half ships **model contracts only** — and the existing
  expectations/promises skill, which today shows the boot-bricking unrouted
  shape verbatim in its templates, gets a warning rather than a replacement
  recipe.

### Asserts and contracts are complementary

Not alternatives, and the guidance must not let one read as a replacement for the
other:

- the **transform assert** fails the build, runs over the complete derived set,
  and can see the closure's own Python (including keys the wire model cannot
  carry);
- the **declared contract** is the durable, exportable, queryable statement of
  what the product guarantees to a consumer who never reads the transform.

### Loop changes

Constraints become a first-class gathering input alongside intent, source and
questions. A failed promise becomes a caveat carried with every answer resting on
it — the same discipline already applied to an unquantified review bucket.
Refinement can add a contract, not only a model.

## Guidance text that becomes wrong

Every place the current text asserts the transform assert is the sole quality
gate. All must move in lockstep with the driver change, or the skills contradict
the runtime:

1. `nxd-generate-dp/SKILL.md:324` — the Step 3b header.
2. `nxd-generate-dp/SKILL.md:326-328` — "Desktop has no other execution point for
   data quality… verify is a no-op… the whole quality story".
3. `nxd-generate-dp/SKILL.md:484` — the Invariant, "the ONLY durable
   data-quality gate on desktop".
4. `evals/public/generate-runnable-dp-from-intent/checks.json` — the
   `derived-model-asserts` check repeats the same claim. It is an **eval**, so
   left unedited it actively penalizes correct new behaviour.
5. `nxd-adding-expectations-promises/SKILL.md` — no local-runtime awareness at
   all, and its custom-verify templates show the unrouted shape that fails at
   boot. This is where the warning lands.

Reframed, the two mechanisms are complementary: the assert fails the build and
can see the closure's own Python (including keys the wire model cannot carry);
the declared contract is the durable statement to a consumer who never reads the
transform.

Four structural interactions to settle while editing:

- **`contracts/` is already taken** — it means "deferred derived-model rubric
  doc" (`SKILL.md:439`). Reusing it for verify code overloads the term; not
  reusing it puts verify files outside self-check Phase C's closed escape-scan
  enumeration. Pick deliberately.
- **Self-check does not validate contracts.** Phase A's keyword vocabulary has no
  `expectation` / `promise` / `custom` / `verify`, so declarations pass
  structurally unchecked — the document's own "declaration alone must not pass"
  principle, violated by its own gate.
- **Export redaction does not cover evidence.** Redaction is scoped to
  `infra-profile.yaml` attributes; discovered-invariant evidence — observed enum
  domains, min/max drawn from real rows — would ship unredacted in a handoff
  bundle. New leakage surface the redaction model was not built to see.
- **"Queryable" is aspirational.** Neither `describe_models` nor the semantic
  tool surface exposes contract metadata. Either scope the exposure or drop the
  word.

## Evals

Declaration alone must not pass. The forcing-function lesson applies directly:
when an agent treats a green check as done, move the requirement into the check.

**The harness cannot currently observe any of this.** `check_generated_closure.py`
executes the transform against a scratch DuckDB and explicitly disclaims the
supervisor and kernel — driver verification only happens inside a real kernel.
So "a violating row fails the build" degrades to "a promise is declared and the
fixture has a bad row", which is the declaration-only vacuous pass this work
exists to remove. **A kernel-plus-driver eval harness is a prerequisite, not a
parallel task** — the same live-runtime bottleneck the parent issue already
tracks. Concrete bypass if it ships without one: declare the promise, silently
drop or coerce the violating row in the transform, harness green, nothing
verified.

- **stated constraints** — each lands as a declared contract on the correct side,
  and a deliberately violating fixture row **stops the publish** (the observable
  named in the publish-gate section, not "the run fails").
- **discovered invariants** — proposed with evidence and confirmed before
  adoption; the sample-true/domain-wrong candidate must not be declared.
  **Paired with a positive case in the same fixture**: a legitimately
  confirmable invariant that *must* land. Without the pair, an agent that
  declares nothing at all passes the adversarial half by being uniformly shy.
- **custom-verify routing** — deferred with the guidance. Shipping an AST check
  that enforces a shape which bricks the boot would be worse than no check.

## Open questions

- **What actually executes a custom verify on the local runtime?** Blocks every
  line of custom-verify guidance and its eval check. Needs a live desktop run,
  not another static trace. If the routed shape does fail at boot, the options
  are a local `ContractDriverItem` or in-script registered validations — with
  materially different guidance, and in the second case a swallowed-error path
  (`compute/mod.rs:2807` discards the relayed result via `let _ = …`) that would
  itself need fixing before the check means anything.
- **Does `{"wait":true}` resolve after promise checks drain?** Determines whether
  the supervisor gate can read outcomes without racing kernel shutdown.
- **`Warning` semantics.** Undefined here, and not inert: `status_computer`
  treats a warning as *clearing* a matching prior failure
  (`status_computer/mod.rs:1197-1203`). Range checks emitting `Warning` would
  erase failure state. Decide before any check emits one.
- **Renegotiation.** No procedure for a previously confirmed invariant that
  starts failing on rebuild — fail forever, re-confirm, or demote to a caveat.
  Compounded by the resume path reusing a published artifact without
  regeneration, so a promise-failure caveat has no durable home across sessions.
- **Failure UX.** The loop's vocabulary is binary build-succeeded /
  build-failed. "Built, but a promise failed" is a new run state with no
  specified rendering.

## Corrections to the initial scoping

- **Key uniqueness is out of the driver half.** The wire model carries no
  primary-key concept, so the driver cannot express it. It stays with the
  transform asserts.
- **Capturing `DriverConfig` is a prerequisite**, not an incidental detail — the
  driver currently discards the model definitions the kernel already hands it.
- **No new native dependency** — verification queries go through the desktop
  venv's interpreter (decided; rationale above).
- **The supervisor publish gate is in scope and load-bearing.** Without it the
  driver work is cosmetic: the artifact publishes and serves violating rows
  regardless of the verdict.
- **The boot-failure mechanism was misdiagnosed** in the first draft — the
  platform contract driver is registered; the missing thing is an infra-profile
  service.
- **The claim that routing to local python compute works is withdrawn** pending
  E2E.
- **Input-side expectations are not fixed** by the output-side driver work and
  must not be declared as if they were.
- **An eval harness with a real kernel is a prerequisite**, not a parallel task.
