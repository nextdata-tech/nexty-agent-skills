"""storefront-events: land the append-only event export into DuckDB."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import dlt
from dlt.sources.filesystem import filesystem, read_csv

from nxd import data_product
from nxd.core.context import DuckDbOutput

# Landed tables promised by spec.py; never semantic views.
BASE_MODELS = ("events",)
DERIVED_MODELS = ()
PHYSICAL_MODELS = BASE_MODELS + DERIVED_MODELS


@data_product.on_transform()
def ingest(duckdb: DuckDbOutput, secrets: dict[str, Any]) -> None:
    """Land each promised model into the DuckDB output port."""
    source_root = Path(secrets["csv_source"])
    # Keep ALL dlt state run-local (next to the staging file) — never ~/.dlt.
    run_dir = Path(duckdb.path).parent
    pipelines_dir = run_dir / "dlt-pipelines"
    pipelines_dir.mkdir(parents=True, exist_ok=True)
    os.environ["DLT_DATA_DIR"] = str(run_dir / "dlt-data")

    pipeline = dlt.pipeline(
        pipelines_dir=str(pipelines_dir),
        destination=dlt.destinations.duckdb(credentials=duckdb.path),
        dataset_name=duckdb.schema,
    )

    resources = []
    # Base models: one dlt CSV reader per data/<model>/ directory.
    for model in BASE_MODELS:
        reader = (
            filesystem(bucket_url=str(source_root / model), file_glob="*.csv")
            | read_csv()
        )
        resources.append(reader.with_name(duckdb.model_tables[model]))

    # Full replace: the whole export is re-read and the table rewritten every
    # run, so a re-run cannot duplicate rows.
    pipeline.run(resources, write_disposition="replace")

    # dlt must write exactly the promised tables, never semantic views.
    actual = set(pipeline.default_schema.data_table_names())
    expected = {duckdb.model_tables[model] for model in PHYSICAL_MODELS}
    if actual != expected:
        raise RuntimeError(
            f"dlt produced tables {sorted(actual)!r}, expected {sorted(expected)!r}"
        )

    # Produce-verification marker: the supervisor's readiness gate waits for it.
    (run_dir / ".transform-complete").touch()


if __name__ == "__main__":
    data_product.main()
