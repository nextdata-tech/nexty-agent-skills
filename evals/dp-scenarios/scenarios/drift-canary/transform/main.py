"""Run the closure surfaces through one local DuckDB transform."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import dlt
from dlt.sources.filesystem import filesystem, read_csv


from nxd import data_product  # noqa: E402
from nxd.core.context import DuckDbOutput  # noqa: E402


PHYSICAL_MODELS = ("orders", "file_rows", "db_rows", "api_events", "optional_zero")


def _read_companion(name: str) -> list[str]:
    root_text = os.environ.get("NXD_TRANSFORM_ROOT")
    if not root_text:
        raise RuntimeError("NXD_TRANSFORM_ROOT is unset while reading a declared companion file")
    path = Path(root_text) / name
    if not path.is_file():
        raise RuntimeError(f"declared companion file {path} is missing")
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


@data_product.on_transform()
def ingest(duckdb: DuckDbOutput, secrets: dict[str, Any]) -> None:
    """Exercise companion files and the documented nested connector shape."""

    endpoints = _read_companion("api-source-endpoints")
    if endpoints != ["api_events=/v1/events"]:
        raise RuntimeError(f"api-source-endpoints has unexpected content: {endpoints!r}")
    _read_companion("db-source-tables")

    # The installed API/database references show a nested access shape.  The
    # current supervisor is expected to expose a flat merged secrets map; the
    # resulting KeyError is the forward-drift signal this closure records.
    api_secrets = secrets["api_source"]
    db_secrets = secrets["db_source"]
    file_source = secrets["file_source"]
    if not isinstance(api_secrets, dict) or not isinstance(db_secrets, dict):
        raise RuntimeError("documented connector secrets must be nested dictionaries")

    source_root = Path(secrets["csv_source"])
    run_dir = Path(duckdb.path).parent
    pipeline = dlt.pipeline(
        pipelines_dir=str(run_dir / "dlt-pipelines"),
        destination=dlt.destinations.duckdb(credentials=duckdb.path),
        dataset_name=duckdb.schema,
    )
    readers = []
    for model in PHYSICAL_MODELS:
        model_root = source_root / model
        reader = filesystem(bucket_url=str(model_root), file_glob="*.csv") | read_csv()
        readers.append(reader.with_name(duckdb.model_tables[model]))
    pipeline.run(readers, write_disposition="replace")
    actual = set(pipeline.default_schema.data_table_names())
    expected = {duckdb.model_tables[model] for model in PHYSICAL_MODELS}
    if actual != expected:
        raise RuntimeError(f"transform produced {sorted(actual)!r}, expected {sorted(expected)!r}")
    (run_dir / ".transform-complete").touch()


if __name__ == "__main__":
    data_product.main()
