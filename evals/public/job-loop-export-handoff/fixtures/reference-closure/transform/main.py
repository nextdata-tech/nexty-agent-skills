"""Load the reference CSV export through the local DuckDB output port."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

repo_root = Path(os.environ["NXD_DESKTOP_REPO_ROOT"])
for source in reversed((repo_root / "components/nxd_py/data_product", repo_root / "components/nxd_py/core", repo_root / "components/nxd_py/drivers")):
    sys.path.insert(0, str(source))

import dlt
from dlt.sources.filesystem import filesystem, read_csv
from nxd import data_product
from nxd.core.context import DuckDbOutput


@data_product.on_transform()
def ingest(output: DuckDbOutput, secrets: dict[str, Any]) -> None:
    source_root = Path(secrets["csv_source"])
    run_dir = Path(output.path).parent
    os.environ["DLT_DATA_DIR"] = str(run_dir / "dlt-data")
    pipeline = dlt.pipeline(
        pipelines_dir=str(run_dir / "dlt-pipelines"),
        destination=dlt.destinations.duckdb(credentials=output.path),
        dataset_name=output.schema,
    )
    readers = []
    for model, table_name in output.model_tables.items():
        readers.append((filesystem(bucket_url=str(source_root / model), file_glob="*.csv") | read_csv()).with_name(table_name))
    pipeline.run(readers, write_disposition="replace")
    if set(pipeline.default_schema.data_table_names()) != set(output.model_tables.values()):
        raise RuntimeError("dlt table names diverged from the output port")
    (run_dir / ".transform-complete").touch()


if __name__ == "__main__":
    data_product.main()
