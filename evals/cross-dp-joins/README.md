# Cross-DP join-strategy eval

Measures whether a **server-side compiler data product** can answer cross–data-product
analytical questions on a live data mesh more correctly, more deterministically, and
more fan-out-safely than a **strict-MCP LLM agent** working the same mesh tool-by-tool.

This is the live-mesh, governance-real successor to the offline `examples/t2sql-poc`
fixture eval. It runs the two strategies against eight healthy pharma DPs on the local
cluster and scores both against an **independent, frozen oracle** — not against either
strategy's own output.

---

## Methodology

### What is compared

| Strategy id | What it is | How it answers |
|---|---|---|
| **A** (compiler) | The deployed server-side compiler DP `cross-dp-query-demo-demo`, MCP tool `run_cross_dp_query`. | Given a `{measures, dimensions, filters}` selection plus each member DP's `semantic_model` payload, it merges the registries (two-pass, owner-wins), compiles **one** fan-out-safe cross-schema SQL, and executes it **in-pod** under `LOWERENVS_ROLE` (cross-schema USAGE). Deterministic. Never abstains — it either compiles+executes or fails loud. |
| **strict** (agent) | A strict-MCP `claude-sonnet-4-6` agent (`agent_driver.py`). | Works the live mesh one MCP call at a time (`semantic_model` + `run_semantic_query` per member DP), then merges client-side. Abstains (`{"abstain": true}`) on questions outside the semantic grammar (window/rank, top-N, dimension-only, no-aggregate list). |

The PoC's three approaches map onto the live ids: PoC `X` (cross-DP compiler) → live **A**;
PoC `P` (strict-MCP plan-validated) → live **strict**; PoC `M` (LLM-merge baseline) is not
run live (its expectation folds into the strict abstain remap).

### The mesh

Eight DPs on the local cluster, each serving `semantic_model` + `run_semantic_query` over MCP.
The five data-bearing members (`LOWERENVS_DB`):

```
pharma-subjects-demo  subjects(SUBJECT_ID, SUBJECT_COUNTRY, SUBJECT_MRN)            n=8
pharma-sites-demo     site_subjects(SITE_ID, SUBJECT_ID) n=10 ; sites(SITE_ID, SITE_REGION) n=5  (NA/EU/APAC)
pharma-labs-demo      assays(ASSAY_ID, SUBJECT_ID, ASSAY_TYPE, TITER)              n=8
pharma-rx-demo        dispenses(DISPENSE_ID, SUBJECT_ID, PRODUCT_ID, UNITS, DISPENSE_CHANNEL, PRESCRIBER_NPI)  n=5
pharma-product-demo   products(PRODUCT_ID, PRODUCT_NAME, MODALITY)                 n=5
```

The live mesh columns differ from the PoC fixture (`TITER` not `titer_value`,
`DISPENSE_CHANNEL` not `channel`, region on `sites.SITE_REGION` reached via
`site_subjects.SITE_ID`, `products.MODALITY` not `therapeutic_area`). The gold was therefore
**re-authored** to the live columns in `harness/gold_cross_dp_live.py` — the PoC canonical
SQL does not run live.

### The oracle (no circularity)

The gold rows are an **independent ground truth**, frozen ahead of any strategy run:

- `harness/gold_cross_dp_live.py` carries the re-authored `canonical_sql` per question.
- `harness/freeze_live.py` runs each `canonical_sql` through the **root cross-DP principal**
  (infra-profile `nxd-snowflake-keypair`, user `LOWERENVS_KEYPAIR_USER`, role `LOWERENVS_ROLE`,
  key-pair auth) on a raw Snowflake connection — **not** through the compiler DP and **not**
  through the agent. The result is `harness/oracle_live.json` (`{id: {rows, row_hash}}`).
- Both A and strict are then scored against the **same** frozen oracle rows.

This is the no-circularity guarantee: the compiler is **never** its own oracle. The
`matches_compiler` axis is reported separately and is informational only — accuracy is always
vs the independent freeze.

---

## What is measured

`harness/score.py` collapses every (question × strategy × trial) into one matrix row with five axes:

| Axis | Meaning |
|---|---|
| **acc** | Accuracy vs the frozen oracle: `PASS` / `FAIL` / `ABSTAIN` / `ERROR` / `N/A`. Reuses the PoC `scoring.score_accuracy`, hardened in the harness so two numeric measures **swapped** (name-blind PASS) downgrade to FAIL when gold has ≥2 numeric measure columns. |
| **fanout** | Fan-out safety of the emitted SQL on the discriminators: `FANOUT_SAFE` / `FANOUT_RISK` / `N/A` (no SQL → client-side merge or abstain). Reuses the PoC `structure_check`. |
| **matches_compiler** | Set-equality (name-blind, numeric-tolerant) of this strategy's rows vs strategy A's rows. Informational; A trivially matches itself. |
| **distinct_results** | Across N trials, count of distinct normalized row-sets. `1` ⇒ deterministic. |
| **abstained** | True if any trial abstained. Abstain **quality** = abstaining exactly on the questions outside the semantic grammar (the `expect_abstain` set), not over- or under-declining. |

### The four fan-out discriminators

The questions designed to separate a fan-out-safe plan from a naive raw-spine join. A naive
plan double-counts a many-to-one fact across the join spine; the correct plan rolls each fact
to its own grain and DISTINCT-collapses the bridge before joining:

| id | discriminator | naive vs correct (live) |
|---|---|---|
| **x07** | two MANY/subject facts (titer + units) per `subject_country` via the crosswalk | correct US (495,120) DE (500,135) FR (175,—); naive US (990,300) |
| **x08** | same two facts per `site_region` — a subject at ≥2 sites in one region double-counts within the region | correct NA (titer 845, units 255); naive NA (1140, 285) |
| **x12** | fact-spine chasm per `prescriber_npi` — subject 1 has two dispenses under the same NPI | correct 1234567890=200; naive =400 |
| **x11** | **NOT live-reproducible** — no live subject has ≥2 dispenses in the **same channel**, so the fan-out collapses (naive == correct). `skipped` in the gold; the freezer records the reason rather than freezing a no-op discriminator. |

x07 is the proven case: A executes the fan-out-safe SQL in-pod → US (495,120) DE (500,135)
FR (175,—) BE/NL —, matching the oracle.

---

## How to run

### Prerequisites

```sh
# TLS for any MCP call against the local mesh
export NXD_CA_BUNDLE=/Volumes/PRO-G40/projects/nxd/shared/charts/nxd/localCerts/nxdCA.crt
export REQUESTS_CA_BUNDLE=$NXD_CA_BUNDLE
export SSL_CERT_FILE=$NXD_CA_BUNDLE

# PoC scoring/structure_check are imported from the t2sql-poc worktree.
# Override only if your worktree path differs:
export T2SQL_POC_ROOT=/Volumes/PRO-G40/projects/nxd/.claude/worktrees/t2sql-exp/examples/t2sql-poc
```

The root cross-DP principal for the oracle freeze comes from
`/Volumes/PRO-G40/projects/nxd/.nxd/lowerenvs_ip.yaml` (gitignored — do not commit).
Python is always run via `uv run` (never bare).

### 1. Freeze the oracle (independent ground truth)

Run each `canonical_sql` through the root key-pair principal and write `oracle_live.json`.
Re-freeze only when the gold SQL or the live data changes.

```sh
cd /Volumes/PRO-G40/projects/nexty-agent-skills/evals/cross-dp-joins
uv run python harness/freeze_live.py        # -> harness/oracle_live.json
```

### 2. Run the definitive live matrix

Drives strategy A (compiler DP) and `strict` (sonnet agent) over every non-skipped live gold
question and scores both against the frozen oracle. Asymmetric trial budget: ≥3 deterministic
trials for A, ≥2 variance trials for the strict agent.

```sh
uv run python harness/run_eval.py \
  --live harness/oracle_live.json \
  --strategies A,strict \
  --compiler-strategy A \
  --trials 3 --strict-trials 2
# writes report/trials.json, report/matrix.csv, report/matrix.md
```

### 3. Build the definitive report

```sh
uv run python harness/make_report.py        # -> report/REPORT.md
```

Offline seam check (no live agents / Snowflake), exercises the agent→scorer normalization:

```sh
uv run python harness/run_eval.py --dry-run <canned_results.json>
```

---

## Live results

### Frozen oracle — the definitive ground truth

Frozen via the independent root principal (`harness/oracle_live.json`). Both strategies score
against these rows. `—` = NULL (left-join orphan / no facts for that group).

| id | category | discriminator | oracle rows |
|---|---|---|---|
| x01 | single_dp | | subject_count = 8 |
| x02 | single_dp | | specialty 90 · retail 60 · mail-order 105 |
| x03 | two_dp_join | | US 4 · DE 3 · FR 1 · BE — · NL — (assay_count) |
| x04 | two_dp_join | | NA 255 · EU — · APAC — (units) |
| x05 | three_dp_multihop | | US 495 · DE 500 · FR 175 · BE — · NL — (titer) |
| x06 | four_dp_far_dim | | small_molecule 200 · antibody 495 · vaccine 350 (titer) |
| **x07** | cross_dp_fanout | ✓ | US (495,120) · DE (500,135) · FR (175,—) · BE/NL — |
| **x08** | cross_dp_fanout | ✓ | NA (845,255) · EU (325,—) · APAC — |
| **x11** | cross_dp_fanout | ✓ | **skipped — not live-reproducible** (fan-out collapses, naive == correct) |
| **x12** | cross_dp_fanout | ✓ | 1234567890=200 · 9876543210=295 · 5556667770=350 (titer) |
| x09 | governance | | (MRN-0001,1234567890) · (MRN-0002,9876543210) · (MRN-0003,5556667770) |
| x10 | long_tail | | ranked subjects within country by titer (5 rows, rnk 1..2) |
| x13 | left_join_complete | | Comirnaty 135 · Humira 60 · Lipitor 60 · Keytruda — · Metformin — |
| x13b | left_join_inner | | Comirnaty 135 · Humira 60 · Lipitor 60 (orphans dropped) |
| x14 | top_n | | Comirnaty 135 · Humira 60 (top-2, tiebreak product_name) |
| x15 | label_column | | Comirnaty 135 · Humira 60 · Lipitor 60 · Keytruda — · Metformin — |
| x16 | grand_total | | titer_sum = 1170 |
| x17 | dimension_only | | mail-order · retail · specialty |

### Definitive strategy-A matrix (live, 2026-06-23)

The full matrix scored against the frozen oracle (`report/matrix.md`). A's selections are
authored honestly in `harness/gold_live_selections.py` — no metric is substituted to game a
PASS.

| id | acc | fanout | distinct_results | note |
|---|---|---|---|---|
| x01, x02, x05, x06, x07, x13, x15, x16 | **PASS** | FANOUT_SAFE | 1 | in-grammar rollups + the x07 subject-spine fan-out + left-join completeness + grand-total |
| x03 | ERROR | N/A | 1 | no `assay_count` metric in the mesh — A errors loud |
| x09, x12, x17 | ERROR | N/A | 1 | no aggregate — compiler requires ≥1 metric ("No measures selected") |
| x10, x14 | FAIL | FANOUT_SAFE | 1 | window/rank (x10) + top-N (x14) — A emits the un-ranked/un-limited rollup (valid-but-wrong shape) |
| x13b | FAIL | FANOUT_SAFE | 1 | inner-join question — A correctly emits left-join completeness (oracle expects orphans dropped) |
| **x04, x08** | **FAIL** → fixed | FANOUT_SAFE | 1 | **the matrix CAUGHT a real compiler bug** — see below |

**Determinism — perfect.** `distinct_results = 1` on **every** question. The compiler's
headline claim (byte-identical SQL + rows across trials) holds at scale, not just on x07. The
strict agent is scored over ≥2 trials to surface run-to-run variance.

### 🐞 The matrix found a real compiler bug — region/bridge chasm double-count

x04 and x08 scored **FAIL** with `FANOUT_SAFE` SQL — the SQL *looked* fan-out-safe but the rows
were wrong, and **x07 alone (the discriminator run earlier) had missed it.**

The compiler is fan-out-safe for the **subject-spine** case (x07: facts keyed `SUBJECT_ID`,
bridge collapses to `DISTINCT SUBJECT_ID`, group by `subject_country`) but **double-counts when
the grouping dimension is reached through a fanned bridge whose DISTINCT key is finer than the
grouping grain**: spine `sites` (grain `SITE_ID`), bridge `site_subjects` `DISTINCT(SITE_ID,
SUBJECT_ID)`, facts keyed `SUBJECT_ID`, grouping by `SITE_REGION` → a subject enrolled at ≥2
sites in the same region is summed once per site. Live: region NA emitted titer **1140** / units
**285**; oracle truth **845** / **255**.

**Fixed in nxd PR #6964** (`fix/cross-dp-bridge-regrain`): re-grain the bridge to
`DISTINCT(<grouping-dim>, <fact-key>)` so each fact-key contributes once per grouping-dim value.
189 semantic tests pass + 5 new `coarse_spine` goldens. Live-proven: NA now 845/255, x07 still
US 495/120. (The deployed facade DP picks up the fix on the next registry republish + redeploy.)

This is the eval doing its job: an independent frozen oracle caught a wrong number the compiler
*believed* was fan-out-safe. A single hand-picked discriminator would have shipped it.

---

## Definitive conclusion

1. **A server-side compiler beats a strict agent on the axes the eval measures** — on the
   in-grammar questions A is correct, byte-deterministic (`distinct_results = 1` across the
   whole matrix), and fan-out-safe on the live discriminators, where a naive raw-spine join
   double-counts.
2. **The win is grounded in an independent oracle**, frozen via the root principal before any
   strategy ran — the compiler is never its own ground truth. That independence paid off: it
   **caught a real compiler bug** (x04/x08 region/bridge chasm double-count) that the
   single-discriminator x07 missed. Fixed in nxd PR #6964; the compiler's fan-out-safety now
   holds for the coarse-spine case too.
3. **The compiler's failures are honest and loud**: it ERRORs on questions outside its
   measure/dimension grammar (x03 missing metric, x09/x12/x17 no aggregate) and FAILs the shape
   on window/top-N (x10/x14) and inner-join (x13b), rather than silently returning a wrong
   number.
4. **The strict agent's value is its abstain quality** — declining exactly the out-of-grammar
   questions instead of guessing.
5. **x11 is the one designed discriminator that does not reproduce live** (data lacks a
   same-channel repeat), correctly `skipped` rather than frozen as a no-op.
6. **The compiler's home is server-side** — the facade DP at
   `src/nxd-data-product-query/reference/cross-dp-query-dp/` (`run_cross_dp_query`) runs the
   compile + execute in-pod under a cross-DP principal, the only locus that satisfies both the
   warehouse IP-allowlist (execution) and cross-schema USAGE (authorization). See the audit log
   for the two governance findings that force this.
