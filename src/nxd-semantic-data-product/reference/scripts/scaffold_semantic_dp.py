#!/usr/bin/env python3
"""Scaffold a semantic-layer data product (flat layout).

Writes placeholder registry.py, tools.py, provision.py, transform.py, models.py
FLAT at the DP root (NOT under a transform/ subdir), and prints the
requirements.txt lines and the spec.py wiring block the DP needs.

The compiler, dialect, and MCP tool factory are provided by the installed
nxd.data_product wheel (module nxd.experimental.semantic) — imported, not
vendored. The DP authors the registry + tools + transform and wires spec.py.

Every stub follows the deploy recipe in SKILL.md Steps 3 + 4 — the stubs MUST
agree with it.

Usage:
    uv run python scaffold_semantic_dp.py <target_dir>

<target_dir> should be the root of the data product directory (the directory
that will contain spec.py). All modules are created as flat siblings.

FOUR WIRING CONSTRAINTS
------------------------------------------------------------------------------
1. code() cannot extract closures. build_semantic_tools(REGISTRY) returns
   closures — author MODULE-LEVEL functions in tools.py and pass code(<fn>);
   reuse build_semantic_tools(...) only for the request/response schemas.
2. The registry/tools/provision siblings are bundled ONLY when there is a
   .transform(...). The rpc-output code() path ships only the extracted tool
   scripts; the **/*.py glob on the transform path bundles the siblings. The
   transform is MANDATORY.
3. Keep all modules FLAT at the DP root — never a transform/ subdir package — so
   the extracted tool scripts resolve `from registry import REGISTRY` against the
   script dir (the only path on sys.path in the rpc subprocess).
4. DDL IN @on_provision, DATA IN THE TRANSFORM. provision.py (an @on_provision
   hook, wired via .provision(script("provision.py").compute(...)) IMMEDIATELY
   BEFORE .transform()) creates the base table STRUCTURE(s) (CREATE TABLE IF NOT
   EXISTS) + the single-table <MODEL>_SEMANTIC view (CREATE OR REPLACE VIEW) —
   DDL only, no data. transform.py seeds the ROWS (TRUNCATE TABLE IF EXISTS +
   write_pandas) — NO DDL. Kernel order is provision -> transform -> promise
   verification, so the rows are present when the promise is checked; the DP
   deploys green in one launch. A transform that RE-PROVISIONS (CREATE OR REPLACE
   TABLE each run) is what made DPs flap Started↔Failed. Promise the REAL model;
   target snowflake.full_table_name("<model>") in BOTH so produce-verification
   matches.

Reference (PROVEN, deployed-and-running):
    evals/query-loop/mesh/<dp>/{spec,provision,transform,models,tools}.py
"""

from __future__ import annotations

import sys
from pathlib import Path


REQUIREMENTS_LINES = [
    "nxd.data_product[spec]",
    "nxd.drivers[rpc]",
    "snowflake-connector-python[pandas]",
    "pandas",
]

_REGISTRY_STUB = """\
# TODO: author your SemanticRegistry here.
# See reference/registry-authoring.md for the full API.
#
# from nxd.experimental.semantic import Agg, Cardinality, SemanticRegistry
#
# REGISTRY = (
#     SemanticRegistry()
#     .model(...)
#     .dimension(...)
#     .metric(...)
#     .join(...)
#     .build()
# )
"""

_TOOLS_STUB = '''\
"""Module-level MCP tool functions — code() can extract these (closures it can't).

Author list_models / describe_model / run_semantic_query as TOP-LEVEL functions
that import REGISTRY flat and delegate to the library compiler. Copy the full
bodies from the deployed reference (pharma-subjects-demo/tools.py), which mirrors
the validated deployable-dp example.

Two rpc-extraction deploy-breakers this stub already avoids (SKILL.md Step 3):
  1. run_semantic_query's storage param is typed with the SPECIFIC driver handle
     (`snowflake: Snowflake`) via a MODULE-LEVEL import — NOT `Any`. An untyped /
     Any param gets a raw Context with no driver methods and fails live. The param
     NAME must match the storage output port name (`snowflake`).
  2. No module-level constant is referenced from inside a tool. code() drops
     module-level `=` assignments, so a module-level `_DIALECT = ...` (or a
     description constant) raises NameError at rpc load → 0 tools registered.
     Inline the @mcp.tool description literals and build the dialect INSIDE the
     function body.
"""

from nxd.drivers.rpc import Request, Response, function, mcp
# MODULE-LEVEL import of the typed Snowflake handle — REQUIRED (see gotcha 1).
from nxd.data_product.context import Snowflake
from registry import REGISTRY  # flat sibling import
from nxd.experimental.semantic.compiler import (
    CompileError,
    compile_selection,
    semantic_view_query,
)
from nxd.experimental.semantic.dialect import SnowflakeDialect


@function(name="list_models")
@mcp.tool(
    name="list_models",
    description="List the semantic models, their grain, and metric/dimension counts.",
)
def list_models(request: Request) -> Response:
    raise NotImplementedError("Copy the body from the deployed tools.py reference.")


@function(name="describe_model")
@mcp.tool(
    name="describe_model",
    description="Describe one model's metrics, dimensions, joins, and PII flags.",
)
def describe_model(request: Request) -> Response:
    raise NotImplementedError("Copy the body from the deployed tools.py reference.")


@function(name="run_semantic_query")
@mcp.tool(
    name="run_semantic_query",
    description="Compile a concept selection to governed SQL and return rows.",
)
def run_semantic_query(snowflake: Snowflake, request: Request) -> Response:
    # Build the dialect INSIDE the body — never reference a module-level constant.
    # default_view_name(REGISTRY) resolves the SAME <MODEL>_SEMANTIC view the
    # provision hook creates, so the native-view probe matches (regression python.md #62).
    dialect = SnowflakeDialect(view_name=SnowflakeDialect.default_view_name(REGISTRY))  # noqa: F841
    raise NotImplementedError("Copy the body from the deployed tools.py reference.")
'''

_PROVISION_STUB = '''\
"""@on_provision hook — DDL ONLY: table STRUCTURE(s) + single-table semantic view.

Runs in Phase A, BEFORE the transform (kernel order: provision -> transform ->
promise verification). Creates this DP's OWN table(s) (CREATE TABLE IF NOT EXISTS,
structure only — no rows) and the single-table <MODEL>_SEMANTIC view (CREATE OR
REPLACE VIEW). The transform seeds the rows afterwards.

The param name (`snowflake`) MUST match the storage output port name; the
ProvisionOutputPortArgumentProvider injects it as a typed Snowflake handle. Create
the PROMISED model's managed table via `snowflake.full_table_name("<model>")` so
the storage driver verifies the promise against the exact table.

The trailing `if __name__ == "__main__":` guard is REQUIRED — a
registered-but-never-invoked lifecycle hook is a hard ValidationError at build time.
"""

from nxd import data_product
from nxd.data_product.context import Snowflake

# = SnowflakeDialect.default_view_name(REGISTRY) for the promised model. Replace
# "<MODEL_UPPER>" with your model name uppercased (e.g. model `subjects` ->
# "SUBJECTS_SEMANTIC").
_VIEW_NAME = "<MODEL_UPPER>_SEMANTIC"


@data_product.on_provision()
def provision(snowflake: Snowflake) -> None:
    from snowflake import connector

    if snowflake is None or not snowflake.schema:
        print("provision skipped — no Snowflake schema in context")
        return

    fqn = (
        f"{snowflake.database}.{snowflake.schema}."
        if snowflake.database
        else f"{snowflake.schema}."
    )

    conn = connector.connect(
        user=snowflake.user,
        account=snowflake.account,
        warehouse=snowflake.warehouse,
        role=snowflake.role,
        database=snowflake.database,
        schema=snowflake.schema,
        ocsp_fail_open=True,
        **snowflake.connector_params(),
    )
    try:
        cur = conn.cursor()
        try:
            # 1) Create the PROMISED model's managed table — STRUCTURE ONLY (no
            # rows). full_table_name("<model>") is the exact table the storage
            # driver verifies the promise against.
            managed = snowflake.full_table_name("<model>")
            cur.execute(
                f"CREATE TABLE IF NOT EXISTS {managed} "
                "(<COL_A> NUMBER, <COL_B> VARCHAR)"
            )
            print(f"provisioned TABLE {managed}")

            # 2) SINGLE-TABLE semantic view over the promised table. References ONLY
            # this DP's own table — never a cross-DP JOIN (cross-DP joins resolve at
            # QUERY time via the live mesh, never at view-creation time).
            cur.execute(
                f"CREATE OR REPLACE VIEW {fqn}{_VIEW_NAME} AS "
                "SELECT <COL_A> AS <COL_A>, <COL_B> AS <COL_B> "
                f"FROM {managed}"
            )
            print(f"provisioned single-table VIEW {fqn}{_VIEW_NAME}")
        finally:
            cur.close()
    finally:
        conn.close()


if __name__ == "__main__":
    data_product.provision()
'''

_TRANSFORM_STUB = '''\
"""Transform — DATA ONLY: seeds the rows. NO DDL.

The table + view are created by the @on_provision hook (provision.py) BEFORE this
runs, so the transform only refreshes rows: TRUNCATE TABLE IF EXISTS + write_pandas.
NEVER issue CREATE TABLE / CREATE VIEW here — a transform that re-provisions made
DPs flap Started↔Failed. The output-port promise is verified AFTER the transform,
so the seeded rows are present in time.

The `.transform()` is ALSO what bundles the sibling `registry.py` / `tools.py` /
`provision.py` modules into the image (the `**/*.py` glob runs on the
transform/compute path), so the transform is MANDATORY even when seeding is the
only runtime work.

The param name (`snowflake`) MUST match the storage output port name. Target the
PROMISED model's managed table via `snowflake.full_table_name("<model>")` — the
same table the provision hook created and produce-verification checks.
"""

import pandas as pd
from nxd.data_product.context import Snowflake


def transform(snowflake: Snowflake) -> None:
    from snowflake import connector
    from snowflake.connector.pandas_tools import write_pandas

    if snowflake is None or not snowflake.schema:
        print("transform skipped — no Snowflake schema in context")
        return

    # TODO: replace with your real seed data (or real runtime data production).
    rows = pd.DataFrame(
        [
            {"<COL_A>": 1, "<COL_B>": "value-1"},
            {"<COL_A>": 2, "<COL_B>": "value-2"},
        ]
    )

    conn = connector.connect(
        user=snowflake.user,
        account=snowflake.account,
        warehouse=snowflake.warehouse,
        role=snowflake.role,
        database=snowflake.database,
        schema=snowflake.schema,
        ocsp_fail_open=True,
        **snowflake.connector_params(),
    )
    try:
        # Truncate-and-load the table the provision hook created. NO DDL here.
        managed = snowflake.full_table_name("<model>")
        cur = conn.cursor()
        try:
            cur.execute(f"TRUNCATE TABLE IF EXISTS {managed}")
        finally:
            cur.close()
        write_pandas(
            conn, rows, managed.split(".")[-1].strip('"'),
            database=snowflake.database, schema=snowflake.schema,
        )
        print(f"seeded {managed} rows={len(rows)}")
    finally:
        conn.close()
'''

_MODELS_STUB = '''\
"""The REAL promised semantic model — satisfies the storage output port.

Promise the REAL model (NOT a dummy marker) so the discover UI surfaces the
actual attributes, their glossary links, and (on downstream facts) the cross-DP
SEMANTIC RELATIONSHIP. The transform seeds the matching table.
"""

from nxd.spec import Predicate, semantic_model
from nxd.spec.data_types import int64, string

# The real model the transform seeds (managed table <model>).
your_model = (
    semantic_model("<model>")
    .description("One row per <grain>.")
    .schema(
        {
            "<COL_A>": int64(),
            # PII columns: document them as such.
            "<COL_B>": string(),
        }
    )
    # Glossary links at the model + attribute level (render in the UI).
    .link(Predicate.GlossaryTerm, "/data-product/<domain>/<glossary-dp>#/terms/<term>")
    .link("<COL_B>", Predicate.GlossaryTerm,
          "/data-product/<domain>/<glossary-dp>#/terms/<col_b_term>")
    # Cross-DP FK (downstream FACT models only, NOT a spine): a fact references a
    # dimension model in another DP so the mesh can plan a cross-DP join.
    # .referencing("/data-product/<domain>/<dim-dp>#/models/<dim-model>", on="<COL_A>")
)
'''

# The correct spec.py wiring block to print for the user.
SPEC_RPC_OUTPUT_SNIPPET = """\
# ── Add these imports to spec.py ─────────────────────────────────────────────
from nxd.spec import (
    code,
    data_product,
    data_product_output,
    data_product_rpc_output,
    Predicate,
    rpc_function,
    rpc_server,
    script,                 # required for .provision(script("provision.py"))
    storage,
)
from nxd.experimental.semantic import build_semantic_tools
from registry import REGISTRY
from tools import list_models, describe_model, run_semantic_query
from transform import transform   # provision.py is referenced by name in .provision(script(...))
from models import your_model

INFRA_PROFILE = "<infra-profile>"
SNOWFLAKE_SERVICE = "<snowflake-service>"

# ── RPC output wiring (the ONLY supported MCP delivery mechanism) ─────────────
# build_semantic_tools(REGISTRY) is used ONLY for the schemas/descriptions; the
# callable passed to code() is the module-level tools.py function — code() cannot
# extract the closures build_semantic_tools(...) returns.
_tool_map = {t.name: t for t in build_semantic_tools(REGISTRY)}
_rpc = data_product_rpc_output()
for _fn, _name in [
    (list_models, "list_models"),
    (describe_model, "describe_model"),
    (run_semantic_query, "run_semantic_query"),
]:
    _t = _tool_map[_name]
    _rpc = _rpc.function(
        rpc_function(code(_fn), _t.request_model, _t.response_model)
        .description(_t.description)
    )
_rpc = _rpc.port(
    "mcp-api",
    rpc_server(f"/infra-profile/{INFRA_PROFILE}#/services/mcp-api-service-k8s")
    .enable_endpoints()
    .mcp_path("/mcp"),
)

# Storage output port named "snowflake" — its name is the provision/transform
# parameter name and the run_semantic_query param name. Plain storage(...) with NO
# as_view: the facade as_view pattern is MUTUALLY EXCLUSIVE with .transform() (nxd
# validate HARD-REJECTS them together), and an rpc DP needs the transform for
# sibling bundling. The provision hook creates the table + view; promise the REAL model.
_storage = (
    data_product_output()
    .promise(your_model)
    .port(
        "snowflake",
        storage(f"/infra-profile/{INFRA_PROFILE}#/services/{SNOWFLAKE_SERVICE}"),
    )
)

# ── data_product spec ─────────────────────────────────────────────────────────
spec = (
    data_product(
        name="<your-dp-name>",
        domain="<domain>",
        version="0.1.0",
        infra_profile=INFRA_PROFILE,
    )
    # PROVISION (Phase A, before the transform): the @on_provision hook
    # (provision.py) creates the table STRUCTURE + the single-table semantic VIEW
    # (DDL only). Placed IMMEDIATELY BEFORE .transform(). NO .startup_timeout(...)
    # here — the validator rejects it on .provision().
    .provision(
        script("provision.py")
        .compute(f"/infra-profile/{INFRA_PROFILE}#/services/k8s-compute")
    )
    # TRANSFORM: seeds the ROWS (TRUNCATE + write_pandas, NO DDL) into the table the
    # provision hook created, and bundles registry.py/tools.py/provision.py (the
    # **/*.py glob runs on the transform path). The output-port promise is verified
    # AFTER the transform, so the rows are present in time. .startup_timeout(600) is
    # a METHOD on .compute(...) (NOT a factory kwarg) and covers cold-boot
    # contention + heavy snowflake/pandas deps.
    .transform(
        code(transform)
        .compute(f"/infra-profile/{INFRA_PROFILE}#/services/k8s-compute")
        .startup_timeout(600)
    )
    .output(_storage)
    .output(_rpc)
    .link(Predicate.GlossaryTerm, "/data-product/<domain>/<glossary-dp>#/terms/<term>")
)
"""


def _write_stub(path: Path, content: str, label: str) -> None:
    if path.exists():
        print(f"  [skip] {path} already exists — not overwriting.")
        return
    path.write_text(content, encoding="utf-8")
    print(f"  [write] {path} ({label})")


def scaffold(target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    print(f"  [ok] DP root ready: {target_dir}")

    _write_stub(target_dir / "registry.py", _REGISTRY_STUB, "placeholder — author your registry")
    _write_stub(target_dir / "tools.py", _TOOLS_STUB, "module-level tool stubs — fill in bodies")
    _write_stub(target_dir / "provision.py", _PROVISION_STUB, "@on_provision DDL stub (table + view) — adapt to your tables/view")
    _write_stub(target_dir / "transform.py", _TRANSFORM_STUB, "MANDATORY data-only transform stub (truncate-and-load) — adapt to your rows")
    _write_stub(target_dir / "models.py", _MODELS_STUB, "REAL promised semantic model — adapt to your schema")

    print()
    print("All modules are FLAT at the DP root (no transform/ subdir package).")
    print()
    print("Add these lines to requirements.txt:")
    for line in REQUIREMENTS_LINES:
        print(f"  {line}")
    print()
    print("spec.py wiring (data_product_rpc_output — the ONLY correct MCP delivery):")
    print()
    print(SPEC_RPC_OUTPUT_SNIPPET)
    print(
        "See reference/scripts/templates/transform_provision.py.tmpl for the "
        "complete spec.py + tools.py + provision.py + transform.py + models.py "
        "example.\n"
        "See SKILL.md Steps 3 + 4 for the authoritative recipe these stubs mirror."
    )


def main() -> int:
    if len(sys.argv) != 2:
        print(f"Usage: uv run python {sys.argv[0]} <target_dp_dir>", file=sys.stderr)
        return 1
    target = Path(sys.argv[1]).resolve()
    print(f"Scaffolding semantic-layer DP in: {target}")
    scaffold(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
