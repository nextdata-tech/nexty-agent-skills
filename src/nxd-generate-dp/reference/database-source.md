# Database source: materialize to CSV before generation

## Contents

- Scope
- Materializing to CSV
- Credential hygiene
- Naming (it's just CSV from here)
- Self-check

This is **not** a closure-level connector type. A live database is never
wired into the served closure or its transform. Instead, pull the needed
tables into local CSV files **once**, at gather time, then hand the result to
nxd-generate-dp exactly like any other CSV export (see `SKILL.md`'s inlined
CSV template). This sidesteps the one real gap in `nxd:generic-secrets:1.0.0`:
this repo has no confirmed mechanism for delivering a *live* credential to a
running closure at supervisor boot — so no live credential is ever asked to
survive that boot in the first place.

## Scope

Postgres and MySQL for this first cut — the two vendors with mature, readily
available Python drivers (`psycopg2`, `pymysql`) for a one-off extraction
script. Other SQL databases are architecturally plausible but unverified
here; do not claim support for a vendor that hasn't been proven.

## Materializing to CSV

Connect with the credentials the user supplied, run one query per promised
physical model, and write the result as CSV — one file per model, matching
the model's attribute names as the header row:

```python
import csv
from pathlib import Path

import psycopg2  # or pymysql for MySQL

conn = psycopg2.connect(host=..., port=..., dbname=..., user=..., password=...)
with conn.cursor() as cur:
    for model, source_table in table_map.items():  # e.g. {"orders": "public.orders"}
        cur.execute(f"SELECT * FROM {source_table}")
        columns = [d.name for d in cur.description]
        out_dir = Path("data") / model  # data-<label>/ if labeled — see multi-source.md
        out_dir.mkdir(parents=True, exist_ok=True)
        with open(out_dir / f"{model}.csv", "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(columns)
            writer.writerows(cur.fetchall())
conn.close()
```

`pandas.read_sql(query, conn).to_csv(path, index=False)` is a fine substitute
for the manual `csv.writer` loop. Either way, dlt and duckdb never see the
database directly — they only ever read the CSV this step produces. Preserve
column names and values faithfully; do not rename, coerce, deduplicate, or
drop rows during this pull — this is production data leaving its source, not
a rewrite.

## Credential hygiene

The credential is used **only** in this extraction step, in the current
shell session. It never reaches the closure directory, `spec.py`,
`infra-profile.yaml`, `transform/main.py`, or any generated file, and it
never needs to survive past this step:

- Never write a raw password into any file inside the closure directory.
- Never persist a credential in narration or a committed file.
- Never fabricate one if the user hasn't supplied it — ask instead.
- Once the CSVs are written, the credential has done its job; do not carry
  it forward into generation, serving, or querying.

## Naming (it's just CSV from here)

Once materialized, this is a plain CSV source: `csv-source` / `csv_source` /
`csv-source-path` + `data/<model>/*.csv` — see `SKILL.md`'s inlined CSV
template for the full shape. There is no `db-source` service, no
`db_source` secrets key, and no `db-source-tables` companion file — those
belonged to a retired live-connector approach. With two or more database
sources (or a database mixed with another source), label each during
materialization — see `reference/multi-source.md`'s `csv-source-<label>` row
— and give each its own `data-<label>/` root so exports never collide on
disk.

## Self-check

Before generation, confirm each written CSV is non-empty and its header row
matches the model's expected attribute names — the same structural check as
any CSV source (see `SKILL.md` Step 7). There is no separate "connectivity"
self-check for the transform, because the transform never connects to the
database — the connection already happened, once, during materialization.
