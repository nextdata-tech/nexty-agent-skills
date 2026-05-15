# Discovery Guide

Use this guide to collect enough evidence to build a first mesh map and draft data products.

## Opening Prompts

Ask for the available discovery surface:

- Source systems: databases, warehouses, lake storage, APIs, message streams, file shares.
- Code: Git repos, dbt projects, notebooks, SQL folders, Spark jobs, Airflow/Dagster/Prefect pipelines.
- Documents: PDFs, PowerPoints, diagrams, screenshots, data dictionaries, BI/report catalogs, operating docs.
- People: domains, teams, owners, stewards, critical consumers, compliance reviewers.
- Priorities: first business area, critical reports, migration deadlines, known broken pipelines, high-value data.

## Snowflake

Stay read-only. Collect:

- Accounts, databases, schemas, tables, views, stages, tasks, streams, and warehouses in scope.
- `DESCRIBE TABLE`, `SHOW COLUMNS`, comments/descriptions, clustering/partitioning hints, row counts, and sample rows when permitted.
- Query/task history exports or SQL snippets that show transformations and dependencies.
- Consumers such as BI reports, downstream jobs, shares, or applications.

Useful user-facing commands:

```sql
SHOW DATABASES;
SHOW SCHEMAS IN DATABASE <database>;
SHOW TABLES IN SCHEMA <database>.<schema>;
DESCRIBE TABLE <database>.<schema>.<table>;
SELECT COUNT(*) FROM <database>.<schema>.<table>;
SELECT * FROM <database>.<schema>.<table> LIMIT 20;
```

Do not run DDL, DML, grants, copy, load, or mutation commands.

## Git Repositories

Inspect read-only:

- SQL models, dbt `manifest.json`, `schema.yml`, tests, macros, and exposures.
- Airflow DAGs, Dagster assets, Prefect flows, Spark jobs, notebooks, Dockerfiles, and CI files.
- Config files that reveal schedules, sources, dependencies, environments, and owners.
- README/docs that explain business purpose.

Record code paths as evidence. Distinguish observed dependencies from inferred dependencies.

## Local Data Samples

Profile CSV, JSON, JSONL, and Parquet files with:

```bash
python3 src/nexty-mesh-bootstrap/scripts/profile_tabular.py <path>
```

Use the output to infer semantic models, data types, nullability, sample values, and partition/freshness hints.

## Documents, Diagrams, and Images

Extract text and visual clues from PDFs, PowerPoints, diagrams, and screenshots. Capture:

- Systems, tables, domains, teams, reports, metrics, policies, and process steps.
- Arrows or connections as candidate dependencies, not facts.
- Labels and report titles as evidence with lower confidence unless corroborated.

Record the artifact path, page/slide/image number when known, and the confidence level.

## Team and Domain Context

Collect:

- Domain names and boundaries.
- Producers, owners, stewards, and consumers.
- Approval/compliance constraints.
- Operational SLAs and freshness expectations.
- First-wave priorities and deferrals.

When ownership is ambiguous, mark the product as needing owner confirmation instead of inventing one.
