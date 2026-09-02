"""Run the closure surfaces through one local DuckDB transform."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import dlt
from dlt.sources.filesystem import filesystem, read_csv

from nxd import data_product  # noqa: E402
from nxd.core.context import DuckDbOutput  # noqa: E402


REQUIRED_MODELS = ("orders", "file_rows", "db_rows", "api_events")
OPTIONAL_EMPTY_MODELS = ("optional_zero",)


def _read_companion(name: str) -> list[str]:
    root_text = os.environ.get("NXD_TRANSFORM_ROOT")
    if not root_text:
        raise RuntimeError("NXD_TRANSFORM_ROOT is unset while reading a declared companion file")
    path = Path(root_text) / name
    if not path.is_file():
        raise RuntimeError(f"declared companion file {path} is missing")
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


@dlt.resource(name="file_rows")
def _file_rows(path: Path):
    """Read the canary's local JSONL fixture without contacting a file source."""

    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            yield json.loads(line)


@dlt.resource(name="db_rows")
def _db_rows():
    """Provide deterministic rows after validating the database config shape."""

    yield {"row_id": 1, "name": "fixture-db"}


@dlt.resource(name="api_events")
def _api_events():
    """Provide deterministic rows after validating the API config shape."""

    yield {"event_id": 1, "active": True}


@data_product.on_transform()
def ingest(duckdb: DuckDbOutput, secrets: dict[str, Any]) -> None:
    """Exercise flat connector attributes and a deterministic local build.

    The canary validates the connector configuration contract without making a
    network request. Database and API rows are local fixtures; their profile
    attributes are still read through the same flat ``secrets`` mapping that a
    real transform uses.
    """

    _read_companion("db-source-tables")

    # Generic-secrets values are merged flat by attribute key. The service name
    # is not an additional mapping level.
    base_url = secrets["base_url"]
    endpoint = secrets["endpoint_api_events"]
    host = secrets["host"]
    database = secrets["database"]
    file_source = Path(secrets["file_source"])
    if (base_url, endpoint, host, database) != (
        "https://api.example.invalid/v1",
        "/v1/events",
        "catalog.example.invalid",
        "canary",
    ):
        raise RuntimeError("flat connector attributes do not match the canary profile")
    if not (file_source / "rows.jsonl").is_file():
        raise RuntimeError(f"file-source root is not materialized: {file_source}")

    source_root = Path(secrets["csv_source"])
    run_dir = Path(duckdb.path).parent
    pipeline = dlt.pipeline(
        pipelines_dir=str(run_dir / "dlt-pipelines"),
        destination=dlt.destinations.duckdb(credentials=duckdb.path),
        dataset_name=duckdb.schema,
    )
    readers = []
    orders = filesystem(bucket_url=str(source_root / "orders"), file_glob="*.csv") | read_csv()
    readers.append(orders.with_name(duckdb.model_tables["orders"]))
    optional_zero = filesystem(bucket_url=str(source_root / "optional_zero"), file_glob="*.csv") | read_csv()
    readers.append(optional_zero.with_name(duckdb.model_tables["optional_zero"]))
    readers.append(_file_rows(file_source / "rows.jsonl").with_name(duckdb.model_tables["file_rows"]))
    readers.append(_db_rows().with_name(duckdb.model_tables["db_rows"]))
    readers.append(_api_events().with_name(duckdb.model_tables["api_events"]))
    pipeline.run(readers, write_disposition="replace")
    actual = set(pipeline.default_schema.data_table_names())
    expected = {duckdb.model_tables[model] for model in REQUIRED_MODELS}
    optional = {duckdb.model_tables[model] for model in OPTIONAL_EMPTY_MODELS}
    if not expected <= actual or not actual <= expected | optional:
        raise RuntimeError(
            f"transform produced {sorted(actual)!r}, expected required {sorted(expected)!r}; "
            f"optional may be absent {sorted(optional)!r}"
        )
    (run_dir / ".transform-complete").touch()


if __name__ == "__main__":
    data_product.main()
