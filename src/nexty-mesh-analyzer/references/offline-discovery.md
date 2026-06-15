# Offline Discovery (read-only collection pass)

This is an **optional** offline collection pass. When live service inspection is
not possible — no network access to the services, credentials withheld, or the
user prefers to share evidence by hand — collect the same kinds of evidence
manually and feed them into the same candidate-matching the analyzer performs on
live services. The output of this pass augments (or substitutes for) the live
inventory that normally drives the `mesh-assets-<profile>.md` report.

Everything here is **read-only**: inspect, sample, and describe — never create,
write, or mutate data on any service.

## Opening Prompts

Ask the user for the available discovery surface:

- **Source systems:** databases, warehouses, lake storage, APIs, message
  streams, file shares.
- **Code:** Git repos, dbt projects, notebooks, SQL folders, Spark jobs,
  orchestrator pipelines (Airflow/Dagster/Prefect).
- **Documents:** PDFs, slide decks, diagrams, data dictionaries, BI/report
  catalogs, operating docs.
- **Domains & ownership:** domains, teams, owners, stewards, critical consumers.
- **Priorities:** first business area, critical reports, known broken pipelines,
  high-value data.

## Warehouse / Database (read-only)

Stay read-only. For a warehouse platform such as Snowflake, collect:

- Accounts, databases, schemas, tables, views, stages, tasks, streams, and
  warehouses in scope.
- `DESCRIBE TABLE`, `SHOW COLUMNS`, comments/descriptions,
  clustering/partitioning hints, row counts, and sample rows when permitted.
- Query/task history exports or SQL snippets that show transformations and
  dependencies.
- Consumers such as BI reports, downstream jobs, shares, or applications.

Useful read-only commands (Snowflake form shown — adapt to the platform):

```sql
SHOW DATABASES;
SHOW SCHEMAS IN DATABASE <database>;
SHOW TABLES IN SCHEMA <database>.<schema>;
DESCRIBE TABLE <database>.<schema>.<table>;
SELECT COUNT(*) FROM <database>.<schema>.<table>;
SELECT * FROM <database>.<schema>.<table> LIMIT 20;
```

Do not run DDL, DML, grants, copy, load, or any mutation commands.

## Git Repositories

Inspect read-only:

- SQL models, dbt `manifest.json`, `schema.yml`, tests, macros, and exposures.
- Orchestrator definitions (Airflow DAGs, Dagster assets, Prefect flows), Spark
  jobs, notebooks, Dockerfiles, and CI files.
- Config files that reveal schedules, sources, dependencies, environments, and
  owners.
- README/docs that explain business purpose.

Record code paths as evidence. Distinguish observed dependencies from inferred
dependencies.

## Local Data Samples

Profile CSV, JSON, JSONL, and Parquet files with the local profiler that ships
with this skill:

```bash
python3 scripts/profile_tabular.py <path>
```

Use the output to infer semantic models, data types, nullability, sample values,
and partition/freshness hints. This is the offline equivalent of the schema
fingerprint the live `inspect_service.py` derives.

## Documents, Diagrams, and Images

Extract text and visual clues from PDFs, slide decks, diagrams, and screenshots.
Capture:

- Systems, tables, domains, teams, reports, metrics, policies, and process steps.
- Arrows or connections as **candidate** dependencies, not facts.
- Labels and report titles as evidence with lower confidence unless corroborated.

Record the artifact path, page/slide/image number when known, and the confidence
level.

## Domain & Ownership Context

Collect:

- Domain names and boundaries.
- Producers, owners, stewards, and consumers.
- Approval/compliance constraints.
- Operational SLAs and freshness expectations.
- First-wave priorities and deferrals.

When ownership is ambiguous, mark the candidate as needing owner confirmation
instead of inventing one.

## Feeding the candidate match

The evidence collected here describes the same assets the live inventory would —
locators, schemas, formats, partitioning, and observed/inferred dependencies.
Carry it as context into the matching step (Step 5 of the main flow): connected
input/output pairs, source-aligned vs. transformed classification, and domain
grouping are derived the same way, and the candidates land in the same
`mesh-assets-<profile>.md` report.
