"""Load synthetic orders and run a local field-mapper pass."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import dlt
import duckdb as duckdb_lib
from dlt.sources.filesystem import filesystem, read_csv

from nxd import data_product
from nxd.core.context import DuckDbOutput
from nxd.experimental.field_mapper import (
    Grant,
    MapperInput,
    MapperSpec,
    map_inputs,
)
from nxd.experimental.field_mapper.schema import compile_schema


BASE_MODELS = ("orders", "reviews")
DERIVED_MODELS = ()
PHYSICAL_MODELS = BASE_MODELS + DERIVED_MODELS
OPTIONAL_EMPTY_MODELS = ("reviews",)


def _synthetic_call(*, item: MapperInput, **_: Any) -> dict[str, Any]:
    """Return a typed synthetic mapping without a provider or network call."""
    category = str(item.fields["product_category"])
    return {
        "order_category": {
            "value": category,
            "evidence": [
                {
                    "quote": f"category {category}",
                    "source_field_name": "order_text",
                }
            ],
        }
    }


@data_product.on_transform()
def ingest(duckdb: DuckDbOutput, secrets: dict[str, Any]) -> None:
    source_root = Path(secrets["csv_source"])
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
    for model in BASE_MODELS:
        model_root = source_root / model
        if model in OPTIONAL_EMPTY_MODELS and not model_root.is_dir():
            continue
        reader = filesystem(bucket_url=str(model_root), file_glob="*.csv") | read_csv()
        resources.append(reader.with_name(duckdb.model_tables[model]))
    pipeline.run(resources, write_disposition="replace")

    actual = set(pipeline.default_schema.data_table_names())
    required = {duckdb.model_tables[model] for model in PHYSICAL_MODELS if model not in OPTIONAL_EMPTY_MODELS}
    optional = {duckdb.model_tables[model] for model in OPTIONAL_EMPTY_MODELS}
    absent_optional = optional - actual
    if actual != required | (actual & optional):
        raise RuntimeError(
            f"dlt produced tables {sorted(actual)!r}; expected required {sorted(required)!r}; "
            f"optional absent {sorted(absent_optional)!r}"
        )

    connection = duckdb_lib.connect(duckdb.path, read_only=True)
    try:
        source_rows = connection.execute(
            f"SELECT order_id, product_category, order_text "
            f"FROM {duckdb.full_table_name('orders')} ORDER BY order_id"
        ).fetchall()
    finally:
        connection.close()
    mapper_spec = MapperSpec.load(Path(__file__).resolve().parents[1] / "contracts/mapper_spec.json")
    mapper_spec = mapper_spec.with_wire_schema(compile_schema(mapper_spec))
    grant_data = json.loads(
        (Path(__file__).resolve().parents[1] / "contracts/mapper_grant.json").read_text(
            encoding="utf-8"
        )
    )
    grant_data["mapper_spec_id"] = mapper_spec.mapper_spec_id
    grant = Grant.from_dict(grant_data)
    order_inputs = [
        MapperInput(
            input_id=str(order_id),
            identity={"order_id": str(order_id)},
            fields={"order_id": str(order_id), "product_category": str(category)},
            landed_text=str(order_text),
            document_class="order",
        )
        for order_id, category, order_text in source_rows
    ]
    result = map_inputs(
        order_inputs,
        spec=mapper_spec,
        grant=grant,
        run_dir=str(run_dir / "mapper"),
        call=_synthetic_call,
        allow_unverified=False,
    )
    if not result.proposals:
        raise RuntimeError("synthetic mapper produced no proposals")
    (run_dir / ".transform-complete").touch()


if __name__ == "__main__":
    data_product.main()
