# Scenario: Generate a runnable desktop data product from intent

This scenario measures the code-generation half of the local desktop flow. The
semantic model was already inferred and the connector export is already in the
workspace. Assemble a Python-only definition closure that the desktop supervisor
can compile, build, and query.

## Task

Read `inferred_model.json` and the CSV headers before writing anything. Then
create these authored files at the workspace root:

- `spec.py`
- `models.py`
- `infra-profile.yaml`
- `transform/main.py`
- `requirements.txt`
- `csv-source-path`, containing the relative path `data`

Do not author `deployment-spec.yaml`, `manifest.yaml`, or `models.yaml`: those
are supervisor-compiled outputs, not source files.

Preserve every supplied CSV byte-for-byte. Each physical base model has one
lowercase name shared by `semantic_model(name)`, `.promise(name)`,
`data/<name>/`, and the DuckDB table `main.<name>`. A metric is query-time only:
declare it with the public DSL on `semantic_view(...)` through
`metric_field(metric(...))`, then register the view with `.model(view)`. Never
import `nxd.spec._*` or write `__nxd_semantic__` metadata directly.

Every promised physical base model must mark one or more existing source
columns with `primary_key()`. The single key or composite tuple must be
non-null and unique across the complete supplied export for that model. Never
synthesize one or change source data; if the inferred model cannot support a
key, stop and ask for the source entity/event key. Semantic views are exempt.

Use a local DuckDB output port named `duckdb`, the local Python compute service,
and the dlt-through-port transform. The transform must obtain its source only
from `secrets["csv_source"]`, declare the promised base models explicitly, and
assert the actual dlt tables match only those physical models. Do not iterate
all `duckdb.model_tables`: it can include semantic views that have no CSV
directory or physical table. Write `.transform-complete` only after that check.

Run the shipped check before finishing:

```bash
uv run --python 3.12 --with "dlt[duckdb]==1.28.2" --with "duckdb==1.5.4" \
  --with "pandas==2.3.3" python check_generated_closure.py
```

It must print `ALL CHECKS PASSED`. The evaluator does not contain a supervisor,
so do not claim a build or semantic query ran there.

In the final response, give the source-file inventory, the base-model-to-table
mapping, the semantic-view-to-metric mapping, and the check result.
