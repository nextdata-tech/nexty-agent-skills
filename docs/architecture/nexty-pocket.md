# Nexty Pocket — architecture

## Contents

- What Nexty Pocket is
- End-to-end flow
- The skills (subskills) and what each owns
- Context capture: `CONTEXT.md` and `nxd_decisions`
- Deterministic runtime checks (the self-check phases)
- Evals that exercise this loop
- Automated tests that guard the gates themselves
- Known coverage gaps
- Where things live

## What Nexty Pocket is

Nexty Pocket is the **local, no-Kubernetes** path for turning a natural-language
question plus a local data source (CSVs, another local file, a live database, or
a REST API) into a running, queryable data product on a **local desktop
supervisor** — then answering questions against it and refining wrong answers
back into a rebuild. There is no remote warehouse and no cluster: the closure a
skill authors is compiled, run, and served entirely by
`nxd-desktop-supervisor` + `nxd-desktop-kernel-host` on the user's machine (or
reached through the `nxd-desktop` MCP server in Claude Desktop/Cowork).

It is one of two AI-assisted data-product paths in this repo (see the
top-level `README.md`): the **platform/k8s path** (`nxd-data-product-builder`,
`nxd-semantic-data-product`'s platform flow, `nxd-data-product-query`) targets a
deployed Nextdata OS mesh; Nexty Pocket targets a single local machine and
never talks to a mesh.

## End-to-end flow

```
intent + source + questions           (nxd-pocket-loop, Step 1)
      │  gather intent/source/questions/procedure;
      │  policy read-back gate fires here if a supplied rubric has a gap
      ▼
infer the semantic model                (nxd-semantic-data-product, inference mode)
      │  profile source → schema.json → grains/dimensions/metrics/joins/PII
      ▼
generate the runnable closure           (nxd-generate-dp)
      │  spec.py + models.py + infra-profile.yaml + transform/main.py +
      │  requirements.txt + CONTEXT.md + connector artifact
      │  → Step 7 self-check (Phases A–D, see below) before handoff
      ▼
build + serve on the supervisor         (nxd-desktop MCP, or direct CLI on host-local Darwin)
      │  build_data_product → semantic_endpoint + bearer_token
      ▼
translate NL question → query           (nxd-pocket-loop, agent-side)
      │  describe_models → map question to measures/dimensions/filters →
      │  run_semantic_query (never raw SQL)
      ▼
answer, quantify any review bucket, state the ruling behind the number
      │
      └─ wrong/missing answer → Step 6: query-level remap (cheap) or
         model/DP-level regenerate (back to inference/generation, same workflow id)
```

`nxd-pocket-loop` is the **orchestrator** — it owns the conversation, the
routing decision (deployed DP vs. existing local product vs.
resume-an-existing-workflow vs. new build vs. trivial arithmetic), and the one
hard gate (the policy read-back). It is also the entry point for a direct "build
me a data product" request — arriving straight at `nxd-generate-dp` skips that
gathering and its own gate fires as a backstop. Two concerns it used to inline
now live in `src/nxd-pocket-loop/reference/`: **task scheduling** (routing, step
order, caps, subagent fan-out) in `scheduling.md`, and **context** (resume-first
reattach, rebuild fallback, the session ledger) in `context-and-resume.md`.

## The skills (subskills) and what each owns

| Skill | Role in the Pocket loop | Not responsible for |
|---|---|---|
| **`nxd-pocket-loop`** | Entry point and orchestrator. Gathers intent/source/questions/procedure, runs the policy read-back, sequences Steps 2–6, does the NL→selection translation and answer presentation, bounds query-remap/regenerate cycles. | Inference logic and closure authoring — it invokes the two skills below rather than re-teaching either. |
| **`nxd-semantic-data-product`** (inference mode) | Profiles a materialized local source (`nxd-mesh-analyzer`'s profiler → `schema.json`) and derives the semantic vocabulary — grains/primary keys, dimensions, metrics, joins, PII flags — from the profile **and** the user's questions. Owns the public semantic role grammar (`primary_key()`, `dimension()`, `metric()`, `join()`). | Placing those roles into the desktop closure shape, or generating `spec.py`/`transform/main.py` — that's `nxd-generate-dp`. This skill also has a separate **platform flow** (Snowflake/k8s `.semantic_tools()`) that Pocket does not use. |
| **`nxd-generate-dp`** | Construction specialist. Takes the settled plan (intent + inferred model + connector config) and emits the complete Python-only closure: `spec.py`, `models.py`, `infra-profile.yaml`, `transform/main.py`, `requirements.txt`, `CONTEXT.md`, plus the connector-specific artifact (CSV/file/database/API). Owns the naming invariant, derived-model rules, the in-transform asserts (Step 3b), and the Step 7 self-check. Opens with its own policy read-back gate as a backstop if invoked directly. | Inferring semantic roles (placed, not designed) and driving the supervisor — that's `nxd-pocket-loop` Step 4. |
| **`nxd-desktop` MCP** (not a skill in `src/`, a capability of the Claude Desktop/Cowork host) | `build_data_product`, `describe_models`, `run_semantic_query` — compiles `spec.py` into the kernel definition YAML, runs the transform, verifies staging, stands up the semantic MCP endpoint, and answers governed queries. | Everything upstream of a settled closure. |
| **`nxd-mesh-analyzer`** | Supplies the profiler script (`scripts/profile_tabular.py`) `nxd-semantic-data-product` calls to build `schema.json` from a local DuckDB sample. | Anything past the profile — it does not infer roles itself. |
| **`nxd-data-product-query`** | Not part of the Pocket loop's build path, but Step 5's NL→concept mapping approach is reused from its semantic-layer section. It targets a **deployed** platform DP; Pocket routes there instead of building locally when the user names a remote DP. | Local desktop closures. |

A single-source build needs only `nxd-pocket-loop` → `nxd-semantic-data-product`
→ `nxd-generate-dp` → the desktop MCP tools. Multi-source builds thread a
short label per source through all three steps (`reference/multi-source.md` in
`nxd-generate-dp`).

## Context capture: `CONTEXT.md` and `nxd_decisions`

A closure has to survive being handed off cold — a later session, possibly
without this skill loaded, has to be able to continue or reopen the work with
nothing but the closure directory. Two distinct, complementary mechanisms
capture that context, and neither substitutes for the other:

**`CONTEXT.md`** (`src/nxd-generate-dp/reference/context-doc.md`) is the
**prose** design/process record, emitted at the closure root by every build
(Step 6a), mandatory (enforced by self-check Phase C below). It has 8 required
sections: intent; the population/sample-selection rule (and, if sampled, an
explicit statement of what's excluded and whether a downstream step depends on
it); per-field inference/determinism caveats (distinguishing what the agent
inferred from what the user actually supplied — otherwise indistinguishable in
the data); required-capture fields (a source field a downstream model depends
on — missing it silently no-ops the downstream step rather than erroring);
the full contract for any derived model not yet built; the reopen recipe
(workflow id + closure path — the only durable key, since the bearer token
never persists); credentials (key *names* only, never values); and known
runtime blockers, kept separate from artifact correctness. A worked template
for both `CONTEXT.md` and the companion `contracts/<name>.md` ships in the
same reference file.

**`nxd_decisions`** (`src/nxd-generate-dp/reference/derivation-plan.md`) is the
**machine-queryable** ledger for the same rulings — a reserved-name base model
landed as `data/nxd_decisions/nxd_decisions.csv`, one row per ruling, with a
`status` column restricted to `confirmed` / `proposed` / `blocked`. It's what
makes a ruling *editable* and *reviewable* rather than merely documented, and
it's mechanically enforced by self-check Phase D below (must be a base model,
not a derived one generated from a Python literal; no policy value may also
appear as a hardcoded literal in the transform).

The two are meant to describe the **same** rulings from two angles — `CONTEXT.md`
says "here's the ruling and why," `nxd_decisions` makes it a queryable, editable
row — and this is stated in both files (`CONTEXT.md`'s per-field-inference
section says it "mirrors the dimension `description=` in `models.py`"; the
model itself is what a later consumer edits). What's *not* stated explicitly in
either file is the failure mode of the two drifting apart — e.g. `CONTEXT.md`
describing a ruling that was later changed in `nxd_decisions` without the prose
being updated to match. No check catches that divergence today; Phase D only
catches a ruling duplicated as a code literal, not a ruling whose prose and
data have quietly diverged from each other.

## Deterministic runtime checks (the self-check phases)

Unlike the platform flow (which relies on the kernel's own build-time
validation plus the acceptance test in `nxd-semantic-data-product`),
Nexty Pocket closures get a **static, pre-handoff self-check** because the
`nxd` wheel is not installable in the authoring environment — nothing can be
imported and exercised for real before the supervisor pins it. That script
(shipped as source in `src/nxd-generate-dp/reference/self-check.md`, run from
the closure root at Step 7) is the mandatory deterministic gate before any
handoff. It has four phases plus two non-blocking read-backs:

| Phase | What it checks | How | Blocking? |
|---|---|---|---|
| **A — structural** | `models.py` / `spec.py` parsed with `ast` against the pinned `nxd.spec` DSL surface (`reference/nxd-spec-api.md`, pinned to a specific `nxd` version): known role kwargs, known data types, known `Agg` members, the naming invariant (`semantic_model` name == `.promise` == `PHYSICAL_MODELS` == `data/<name>/`), `.semantic_tools()` forbidden, output port must be `"duckdb"`, `infra_profile="desktop-local"`, every base model has a `primary_key()`. | Pure `ast.parse` — nothing imported or executed. Dynamic constructs (variables, comprehensions, `**` spreads) are reported `unverified:` rather than silently passed. | Yes |
| **B — transform dry-run** | Actually **executes** `transform/main.py` against a scratch DuckDB with a stub `DuckDbOutput`, then queries every `PHYSICAL_MODELS` table and asserts `.transform-complete` exists. | Real execution — the only phase that runs code. | Yes |
| **C — context-completeness** | `CONTEXT.md` exists at the closure root; no closure file references a contract/design doc by a `../`-rooted path that escapes the closure; if `infra-profile.yaml` carries a populated `attributes:` list (a live credential), `.gitignore` (naming the file, never `*`) and `SENSITIVE` both exist. | Text/regex scan of author-facing files; never reads or echoes a secret value, only reports missing guard files. | Yes |
| **D — policy boundary** | A promised `nxd_decisions` model must be a **base** model (backed by `data/`, not derived from a Python literal) with a `status` column restricted to `{confirmed, proposed, blocked}`; no distinctive value in a landed policy CSV also appears as a literal in `transform/main.py`. | AST-derived `PHYSICAL_MODELS`/`BASE_MODELS` from the values Phase B actually imported (not the static parse, which can't resolve `BASE_MODELS + DERIVED_MODELS` as a literal) + CSV/text scan. | Yes |
| **Distribution read-back** | Prints value counts for every classification-shaped column of every derived model; flags `UNIFORM` (a value the code supplied, not one the data produced). | Query over the Phase-B DuckDB connection. | No — always relayed to the user before build, never fails the run. |
| **ABSENT read-back** | Flags a declared vocabulary value (verdict/bucket/tier/category-named CSV columns) that never appears in any derived output column — a branch that never fired. | Set-difference over declared vs. produced values. | No — informational only. |

Two invariants this design leans on hard, both covered by the `evals/tests/`
suite (below): **Phase A checks a pin, not the live wheel** — a closure can
pass Phase A in full and still fail when the real supervisor compiles it, so
the self-check doc explicitly documents this gap ("What this script does NOT
cover"). And **an expected value in any check must come from landed data or a
user's contract, never from the transform's own constants** — restating the
transform's arithmetic as its own proof is called out by name as the usual way
this gets violated.

Underneath Step 3b (inside the transform itself, not the self-check script),
every derived model carries **mandatory in-transform asserts**. They are the
gate over the closure's own logic: a declared contract on a promised model does
now stop the publish, but it runs after the transform and sees only the landed
table, so a derivation's correctness can be proven only here (platform-side
custom contract verification still does not run locally): Tier 1
(declared-key uniqueness + grain-derived row count vs. independently-read
source) always, Tier 2 (signed measure total reconciled per-currency in
`Decimal`, every intentional divergence itemized) whenever a measure column is
present.

At the **pack level** (not specific to Pocket, but Pocket's skills are subject
to it), `scripts/validate_skills.py` enforces the mechanical conventions in
`AGENTS.md` — frontmatter shape, `metadata.version` lockstep with the plugin
version, reference-file `## Contents` headers, no angle-bracket placeholders —
and `build-skills.sh` enforces the 200-entry Claude Desktop zip cap. Both run
in CI and before any PR per `AGENTS.md`.

## Evals that exercise this loop

Evals live under `evals/public/` and are graded by `run.py`: a headless agent
drives the scenario's `prompt.md` with the target skill-set installed, and an
LLM judge (default `opus`) grades the transcript against `checks.json`. Some
scenarios additionally run a **deterministic checker script** from
`fixtures/` and fold its `PASS`/`FAIL` output into the judge's facts
(`deterministic_check_fact` in `run.py`) — these are the ones that verify
ground truth mechanically instead of trusting the transcript or the agent's
own claims.

| Scenario | Skills exercised | What it checks |
|---|---|---|
| **`pocket-loop-serve-query-refine`** | `nxd-pocket-loop`, `nxd-semantic-data-product`, `nxd-generate-dp` | The full end-to-end loop against a **live local desktop supervisor** (`ci_skip`'d — needs `EVAL_POCKET_SUPERVISOR_DIR`/`EVAL_POCKET_PYTHON`, run locally or via `workflow_dispatch`): serve, `describe`, four phase-A questions answered correctly (country+date filters, a cross-model join, a boolean-sum aggregation, top-N ordering+limit), a staged phase-B request (add an average metric) that must trigger a real regenerate + re-serve of the **same** workflow id rather than being pre-empted, no direct writes to the supervisor's own state DB, and an **independent re-serve of the final immutable snapshot** recomputing every answer from pristine CSVs. `fixtures/check_pocket_loop.py` is the forcing-function/ground-truth script — it never trusts a transcript, a pasted answer, or the mutable workspace CSVs; it re-derives every reference answer from its own pristine `reference_sql` and independently re-serves the pinned snapshot in `--mode harness`. |
| **`generate-runnable-dp-from-intent`** | `nxd-generate-dp` | Given an already-inferred model, checks the Python-only closure shape (no hand-written `deployment-spec.yaml`/`manifest.yaml`/`models.yaml`), base-vs-derived primary-key rules, derived rows landed through the `duckdb` port as flat dicts in one `pipeline.run(...)`, the naming invariant (`PHYSICAL_MODELS` vs. `data/` directories), public-DSL-only usage, and runs `fixtures/check_generated_closure.py` for `ALL CHECKS PASSED`. |
| **`generate-semantic-layer-dp-from-schema`** | `nxd-semantic-data-product` | The **platform** flow from a supplied schema doc: grains, metric aggregations (`sum`/`count_distinct`), boolean-flag metrics, join blobs, PII flags, and the `.semantic_tools()` wiring — all graded directly against the quoted `models.py`/`spec.py` text. |
| **`generate-semantic-layer-from-live-source-and-questions`** | `nxd-semantic-data-product` | The **inference** flow (the half Pocket shares): profile a live DuckDB sample of two tables *before* authoring, save the combined profile to `schema.json` and cite it, declare bare unquoted table names matching profiled columns byte-exactly, infer grains from exact full-table cardinality, surface a genuinely ambiguous metric (revenue with `refunded`/`cancelled` rows present) rather than silently resolving it, and support a column carrying two roles (`sum` + `avg`) via a multi-role wrapper. |
| **`pharma-cross-dp-mesh-query`** | `nxd-data-product-query` (platform path, not Pocket) | Included here only because Pocket's Step 5 reuses its NL→concept mapping approach; the scenario itself targets deployed cross-DP semantic queries, not a local closure. |
| **`semantic-intent-validation`** | `nxd-data-product-query` | Exercises the "intent gate" (critic/echo/clarify) ahead of `run_semantic_query` — the same discipline Pocket's Step 5 leans on when mapping a question to a selection, though the scenario itself runs against a deployed DP. |
| **`coauthor-supplied-rubric`** (not Pocket-specific but shares the gate `nxd-generate-dp`/`nxd-pocket-loop` both implement) | `nxd-generate-dp` | The policy read-back gate: a supplied rubric with an incomplete scale must be read back and approved **before** any closure file is written. `fixtures/check_coauthored_closure.py` fails a transcript where scaffolding starts before the read-back, fails post-hoc disclosure (reading back only after building), and separately fails a **routing** regression where a build request reaches `nxd-generate-dp` directly instead of `nxd-pocket-loop` gathering first. |
| **`derive-models-from-questions`** | `nxd-generate-dp` | Step 1a/3a/3b end-to-end on a messy transactions export: refund netting (the derived spend *measure* must be correct even though the row count is a red herring), transfer exclusion, a monthly regrain (the semantic layer can't `DATE_TRUNC` at query time), an undisclosed-FX-rate trap across three currencies (silently inventing a rate fails; silently refusing to convert without disclosing why also fails), and a merchant→category ruling landed in `nxd_decisions` (never a dict literal or `if/elif` chain) with an explicit `needs_review` bucket for uncovered merchants. Has its own `deterministic_check` (`fixtures/check_derived_closure.py`) folded into the judge's facts. |

Efficiency (turns, tool calls, tokens, cost) is graded alongside correctness
for every scenario — a skill edit that keeps a `PASS` verdict but doubles the
tool-call count is treated as a regression too (`evals/README.md`,
"Benchmarking a skill change"). Before/after comparisons for a behavior change
to any of these skills are recorded in `evals/benchmarks/ledger.md` via
`evals/benchmark_record.py`; see e.g. the `nxd-generate-dp` phase-D and
multi-connector-type entries already in `evals/benchmarks/records/`.

## Automated tests that guard the gates themselves

`evals/tests/` is plain pytest — it does not run an agent. It exists because a
gate that is only prose, or only exercised inside a nondeterministic agent
eval, can silently stop firing. Each test extracts the **actual shipped
script** (from `self-check.md` or a scenario's `fixtures/`) and runs it
directly against synthetic inputs designed to hit the exact failure the gate
was written for:

- **`test_deterministic_check.py`** / **`test_deterministic_check_wiring.py`** —
  `run.py`'s `deterministic_check_fact` mechanism itself: that a scenario's
  checker script actually runs, that its `PASS`/`FAIL`/`ALL CHECKS PASSED`
  output reaches the judge as a fact, and that trace-forwarding only happens
  when a scenario opts in with `wants_trace` (and that the trace file never
  leaks into the agent's own workspace for a later turn to read).
- **`test_policy_boundary_phase_d.py`** — pins Phase D of the self-check
  against the **real regression** that motivated it: a `nxd_decisions` model
  built from a Python literal (`DERIVED_MODELS`) that *describes* a threshold
  rather than being editable data. It specifically pins that Phase D keys off
  the values Phase B actually **imports** at runtime (`BASE_MODELS`,
  `PHYSICAL_MODELS`), not the statically-parsed literal — the first version of
  Phase D keyed on the static parse, which can't resolve
  `PHYSICAL_MODELS = BASE_MODELS + DERIVED_MODELS` as a literal, and so
  silently never fired on the very closure it was written to catch.
- **`test_trace_ordering_gate.py`** — the pre-build policy read-back gate
  (`coauthor-supplied-rubric`'s checker): fails a transcript where a `Write`
  precedes the read-back, fails the post-hoc-disclosure loophole (read-back
  present, but only after building), passes read-only source inspection
  before the read-back, and separately asserts the **routing** check — that
  reaching `nxd-generate-dp` before `nxd-pocket-loop` is graded as a failure
  distinct from what happens inside either skill.

Run them with plain `pytest evals/tests/` — no live supervisor, no agent, no
API key required.

## Known coverage gaps

Three gaps in what's actually verified, none hypothetical — each is either an
open tracked issue or a documented note in the eval ledger:

- **`reference/context-and-resume.md` (reattach) and `reference/query-grammar.md`
  (the Omission Test) have thin scenario coverage.** Both are carefully worked
  reference docs — the reattach playbook's resume-first ordering,
  credential-recovery branches and honesty-clause narration rules, the Omission
  Test's ruling-vs-filter classification. A plain-pytest gate in `evals/tests/`
  now pins the resume-first tool ordering (`list_data_products` before
  `resume_data_product` before `build_data_product`), but the full playbook and
  the Omission Test are still ungraded by any live scenario. Tracked in
  **[#103](https://github.com/nextdata-tech/nexty-agent-skills/issues/103)**,
  E5 ("pocket-loop invariants with no scenario at all") — the reattach path is
  "the one a real user hits every second session, since the bearer is
  per-session and never persisted"; E4 separately flags the Omission Test as
  mechanically decidable (run the ruling-bearing measure with no filters,
  compare against the ruled total) but currently ungraded even by the judge.
- **Database and REST-API connector types have no scenario coverage.**
  `reference/database-source.md`, `reference/api-source.md`, the labeled
  multi-source naming scheme, and the structured `auth_type` dispatch all
  shipped, but every public eval that touches `nxd-generate-dp` only exercises
  the single-CSV-source path — noted at the time in
  `evals/benchmarks/records/2026-07-21-...multi-connector-type-sources.json`
  as "real follow-up work" but never filed until now:
  **[#107](https://github.com/nextdata-tech/nexty-agent-skills/issues/107)**.
- **The flagship end-to-end scenario can't run in CI or in a plain sandbox.**
  `pocket-loop-serve-query-refine` needs a live `nxd-desktop-supervisor`
  binary (`ci_skip`'d for exactly this reason), and the same 2026-07-21 ledger
  entry separately notes it "remains blocked in this sandbox (missing
  nxd-desktop-supervisor binary)" — so it has apparently not actually run
  against the connector-type and reopen-recipe changes layered on top of it
  since. Tracked as part of **[#90](https://github.com/nextdata-tech/nexty-agent-skills/issues/90)**
  ("Covered only by `ci_skip` scenarios") and **#103** E3 (whether
  `pocket_verify` should generalize beyond this one scenario).

There is also **no check for `CONTEXT.md`/`nxd_decisions` drifting apart** from
each other over time (see "Context capture" above) — not yet filed as an issue,
since it's a narrower, newly-noticed gap rather than an already-tracked one.

## Where things live

- `src/nxd-pocket-loop/SKILL.md`, `reference/scheduling.md` (task scheduling),
  `reference/context-and-resume.md` (reattach/context), `reference/dlt.md` —
  the orchestrator.
- `src/nxd-semantic-data-product/SKILL.md` + `reference/` — inference (shared)
  and the platform `.semantic_tools()` flow (not used by Pocket).
- `src/nxd-generate-dp/SKILL.md` + `reference/` — the desktop closure
  generator, including `reference/self-check.md` (the script above).
- `examples/pocket-demo/RUNBOOK.md` — a manual live-QA script for driving the
  loop inside Claude Desktop/Cowork against a real supervisor, focused on
  environment-specific quirks the automated eval can't reach (skill
  activation, PATH persistence across Bash calls, the `bearer_token`-on-stderr
  behavior, sandbox egress).
- `evals/public/pocket-loop-serve-query-refine/` — the end-to-end eval above.
- `evals/tests/` — the pytest suite pinning the gates themselves.
- `README.md` (`current_pack` in `evals/skill-sets.yaml`, and the "Available
  Skills" table) — where Pocket's skills are wired into the shipped pack.
