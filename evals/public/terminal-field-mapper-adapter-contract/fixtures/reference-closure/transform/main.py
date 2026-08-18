"""Synthetic terminal field-mapper adapter closure."""
from __future__ import annotations
import json
import os
from pathlib import Path
from dataclasses import replace
from typing import Any
import dlt
from dlt.sources.filesystem import filesystem, read_csv
import duckdb
from nxd import data_product
from nxd.core.context import DuckDbOutput
@data_product.on_transform()
def ingest(output: DuckDbOutput, secrets: dict[str, Any]) -> None:
    import nxd.experimental as nxd_experimental
    repo_root = os.environ.get("NXD_DESKTOP_REPO_ROOT")
    if repo_root:
        nxd_experimental.__path__.insert(0, str(Path(repo_root) / "components/nxd_py/data_product/nxd/experimental"))
    from nxd.experimental.field_mapper import EvaluationProfile, Grant, MapperInput, MapperSpec, __version__, make_call, map_inputs
    from nxd.experimental.field_mapper.schema import compile_schema
    source_root = Path(secrets["csv_source"])
    run_dir = Path(output.path).parent
    os.environ["DLT_DATA_DIR"] = str(run_dir / "dlt-data")
    pipeline = dlt.pipeline(pipelines_dir=str(run_dir / "dlt-pipelines"), destination=dlt.destinations.duckdb(credentials=output.path), dataset_name=output.schema)
    source = filesystem(bucket_url=str(source_root / "orders"), file_glob="*.csv") | read_csv()
    pipeline.run(source.with_name(output.model_tables["orders"]), write_disposition="replace")
    con = duckdb.connect(output.path)
    rows = con.execute(f"SELECT order_id, product_category, order_text FROM {output.full_table_name('orders')} ORDER BY order_id").fetchall()
    con.close()
    root = Path(__file__).resolve().parents[1]
    spec = MapperSpec.load(root / "contracts" / "mapper_spec.json")
    spec = spec.with_wire_schema(compile_schema(spec))
    if not spec.harness_version:
        spec = replace(spec, harness_version=__version__)
    grant_data = json.loads((root / "contracts" / "mapper_grant.json").read_text())
    grant_data["mapper_spec_id"] = spec.mapper_spec_id
    grant = Grant.from_dict(grant_data)
    profile_path = os.environ.get("NXD_SYNTHETIC_EVALUATION_PROFILE")
    if not profile_path:
        raise RuntimeError("synthetic evaluation profile was not injected by the runner")
    profile = EvaluationProfile.load(profile_path, workspace_root=root)
    call = make_call(spec=spec, grant=grant, evaluation_profile=profile)
    inputs = [MapperInput(input_id=row[0], identity={"order_id": row[0]}, fields={"order_id": row[0], "product_category": row[1]}, landed_text=row[2], document_class="order") for row in rows]
    result = map_inputs(inputs, spec=spec, grant=grant, run_dir=str(run_dir / "run" / "mapper"), call=call)
    if not result.proposals:
        raise RuntimeError("mapper produced no proposals")
    (run_dir / ".transform-complete").touch()

if __name__ == "__main__":
    data_product.main()
