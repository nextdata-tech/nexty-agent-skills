# Connection Matching Heuristics

How to decide that two data assets are **connected** — one is the input, the other the output of the same candidate data product — and whether the product is **source-aligned** or **transformed**.

## Signals

Score each candidate pair across these signals:

1. **Naming lineage** — service or asset names carry a stage suffix/prefix: `input`↔`output`, `raw`/`landing`↔`staging`/`curated`, `bronze`↔`silver`↔`gold`, `src`↔`dim`/`fact`. A pair spanning two adjacent stages is a strong link. Example: `s3-input` bucket `lowerenvs-input-data-product` ↔ `s3-output` bucket `lowerenvs-output-data-product`.

2. **Asset name match** — the same base table/file/directory name appears on both sides (`orders/` → `orders/`, `customers` → `customers`). A *generic* name — `documents`, `data`, `output`, `items`, `records`, `export`, `file`, `events`, `log`, ... — is too weak to pair on by itself: it counts as a match only alongside another signal (schema overlap, naming lineage). Two unrelated assets both called `documents` are not connected.

3. **Schema similarity** — compute the Jaccard overlap of column/field names:
   - ≥ 0.9 with compatible types → near-identical model → **source-aligned** signal.
   - 0.4–0.9, or renamed columns, or output is a strict subset/superset → **transformed**.
   - < 0.4 → likely unrelated; do not pair on schema alone.

   Guard against false positives: **skip schema pairing for assets with fewer than 3 columns** — a 2-column `(id, name)` table matches half the world at Jaccard 0.5. Weight by column *rarity*: generic names (`id`, `name`, `date`, `created_at`) carry little signal; a match is only meaningful when the shared columns include **distinctive** names. Never promote a pair to a candidate on schema overlap alone — require a second signal (naming lineage or asset-name match).

4. **Partitioning carried through** — same partition keys on both sides → source-aligned. Partitioning dropped or added → transformed.

5. **Temporal order** — the output's `last_modified` is at or after the input's. An asset modified strictly before a candidate input cannot be that input's output.

6. **Cardinality** — output `row_count` ≈ input `row_count` → pass-through. Output much smaller → aggregation. Output much larger → join / explode / enrichment.

7. **Format or store change only** — same schema, different format (csv→parquet) or different store (S3→Snowflake) → classic source-aligned product.

## Exclusion rules

Some assets and pairs are never real data product inputs or outputs — drop them before scoring. Rules are split into **per-source-type** asset rules and **generic** rules; add new per-driver rules as needed.

- **Snowflake clone tables** (per-source-type) — a table named `<table>_CLONE_<digits>` is a platform clone, not an output. Exclude the asset.
- **hello-world test data** (generic) — any asset whose name contains `hello world` — as one word or hyphen/underscore delimited — is example/test data. Exclude the asset.
- **personal scratch / test sandbox** (generic) — any asset whose path contains a segment matching a known scratch marker (`billg`, `sina-test`, `bill-test`, `test-data`, `tmp`, `sandbox`, `myenv`, `my-dp`, `placeholder`, `debug`, …; see `TEST_SANDBOX_SEGMENTS` in `meshlib/matching.py`), or any token *starting with* `hello` followed by one or more chars (`hellopython`, `hello6`, `helloincremental`, `playlistshello`), is a private workspace / scaffold variant, not a real data product. Exclude the asset.
- **Bucket/account root** (generic) — an asset whose locator is a bare bucket or account root (`s3://bucket/`, `adls://account/`) with no dataset path is not a named dataset. Exclude the asset.
- **Plural twins** (generic) — two datasets in the same database/store whose names differ only by a trailing plural (`amazon_review` vs `amazon_reviews`) are the same dataset, not an input/output pair. Exclude the pair.
- **Production-score Pareto dominance** (generic, ambiguous candidates) — when several pairs share the same input basename + output basename (an "ambiguous candidate"), each pair is ranked by `production_score` on input and output sides. `prod` / `production` / `live` / `main` / `master` / `release` segments score positive; `staging` / `stg` / `dev` / `demo` / `uat` / `qa` segments score negative; trailing numeric variants like `_2`, `_3`, `-v2` on the final segment score lower. A pair that is Pareto-dominated (≥ on both sides, > on at least one) by another pair in the same ambiguous candidate is dropped. Many ambiguous candidates collapse to a singleton this way without needing a user prompt.

## Replicated datasets

A dataset copied verbatim across stores is **one replica set**, not an N×N grid of candidate products. When 3+ assets share **both** an identical distinctive schema fingerprint **and** the same normalized dataset name — environment/region suffixes (`_az`, `_azure`, `_prod`, ...) stripped — and span 2+ stores, set the whole group aside before pairwise scoring and list it in the report's "Replicated Datasets" section.

Key on the name as well as the schema: schema alone over-groups — e.g. per-retailer fact tables (`IRI_TARGET_FACT_SALES`, `IRI_ALBERTSONS_FACT_SALES`) share a schema but are distinct datasets, not replicas of each other.

The skill then asks the user which copy is the canonical source (the input) — they have the domain knowledge. The source → each replica is then a source-aligned candidate.

## Direction

The input is the upstream asset: modified earlier, in a `raw`/`input`/`bronze`-named location, with a larger-or-equal row count. The output is downstream. If naming and timestamps disagree, prefer timestamps and flag the ambiguity in the report.

## Classification

- **Source-aligned** — schema overlap ≥ 0.9, compatible types, partitioning preserved, cardinality roughly preserved. A source-aligned data product reads one service and writes another with minimal transform logic. The canonical case crosses services, file storage → database. A pair **within a single service** can still be source-aligned, but rank it **low confidence** — a real source-aligned product moves data between services.
- **Transformed** — schema reshaped, columns derived/dropped/aggregated, cardinality changed, or multiple inputs combined into one output.

## Confidence

- **High** — naming lineage **and** (asset-name match or schema ≥ 0.9) **and** consistent temporal order.
- **Medium** — schema ≥ 0.6 **or** asset-name match, with no temporal contradiction.
- **Low** — a single weak signal only (e.g. loose schema overlap, no naming or timing support).

Report high/medium pairs as candidate data products. List low-confidence pairs separately as "possible connections" for the user to confirm or reject. Surface assets with no counterpart as standalone-input candidates.

## Multiple inputs, multiple outputs

A transform may take several inputs (a join) or write several outputs. Group all assets that share lineage signals into one candidate product rather than emitting many disconnected pairs. Per the nextdata convention, each distinct source store is one input, and each file/table with a unique schema is its own input model within that input.

## Scheduling hint

When an input is time-partitioned, the partition granularity implies the transform's refresh cadence — daily partitions → a daily cron, hourly → hourly. Record this so nexty-bootstrap can seed the transform's `when` schedule. If an input is **not** partitioned by time, the cadence is unknown — flag it for the user to decide.

## Domain

Every data product belongs to a **domain** — a business grouping such as sales, finance, customer, or product. Classify each candidate's domain by keyword-matching its suggested name, namespaces, asset names, and service names against a domain vocabulary; the domain with the most hits wins. When nothing matches, file the candidate under `other`. Domains are not recorded in the infra profile, so this is a best-effort guess — surface it for the user to confirm or correct, and group the report's candidates by domain.

## Suggested data product name

Give each candidate a kebab-case data product name, **biased to the output dataset's name** — a data product is named for what it produces, so `sales_gross` → `sales_net` yields `sales-net`. Use the output asset's basename (table or dataset directory). Drop any `raw` marker token — the product is named for the dataset, not the rawness of its input. This name seeds the data product when the candidate is bootstrapped.

## Required report fields

A downstream skill authors data products from this report, so each candidate must carry: the suggested data product name, the domain, the infra profile name, and — for both the input and the output — the data source location and its infra-profile service URL. Carry every one of these through from the inventory into the report. Keep the input/output model schemas in the companion `*-models.md` file.
