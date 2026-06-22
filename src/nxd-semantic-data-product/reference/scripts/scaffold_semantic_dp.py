#!/usr/bin/env python3
"""Scaffold a semantic-layer data product (flat layout).

Writes placeholder registry.py, tools.py, transform.py, provision.py, models.py
FLAT at the DP root (NOT under a transform/ subdir), and prints the
requirements.txt lines and the spec.py wiring block the DP needs.

The compiler, dialect, and MCP tool factory are provided by the installed
nxd.data_product wheel (module nxd.experimental.semantic) — imported, not
vendored. The DP authors the registry + tools + transform + provision and wires
spec.py.

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
2. The registry/tools siblings are bundled ONLY when there is a .transform(...).
   The rpc-output code() path ships only the extracted tool scripts; the
   **/*.py glob on the transform path bundles the siblings. The transform is
   MANDATORY.
3. Keep all modules FLAT at the DP root — never a transform/ subdir package — so
   the extracted tool scripts resolve `from registry import REGISTRY` against the
   script dir (the only path on sys.path in the rpc subprocess).
4. Promise verification runs BEFORE the transform, so seed the promised base
   table(s) + create the single-table <MODEL>_SEMANTIC view at PROVISION time via
   an @on_provision function wired with .provision(script("provision.py")). The
   transform is for RUNTIME data production (a no-op for a static-seed DP) and
   must NEVER (re)provision — transform-time seeding fails verification
   ("Field ... not found in the model") and makes the DP flap Started↔Failed.

Reference: reference/scripts/templates/spec_rpc_output.py.tmpl
           reference/scripts/templates/transform_provision.py.tmpl
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
bodies from reference/scripts/templates/transform_provision.py.tmpl (tools.py
section), which mirrors the validated deployable-dp example.

Two rpc-extraction deploy-breakers this stub already avoids (SKILL.md Step 3):
  1. run_semantic_query's storage param is typed with the SPECIFIC driver handle
     (`snowflake: Snowflake`) via a MODULE-LEVEL import — NOT `Any`. An untyped /
     Any param gets a raw Context with no driver methods and fails live.
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
    raise NotImplementedError("Copy the body from the template tools.py section.")


@function(name="describe_model")
@mcp.tool(
    name="describe_model",
    description="Describe one model's metrics, dimensions, joins, and PII flags.",
)
def describe_model(request: Request) -> Response:
    raise NotImplementedError("Copy the body from the template tools.py section.")


@function(name="run_semantic_query")
@mcp.tool(
    name="run_semantic_query",
    description="Compile a concept selection to governed SQL and return rows.",
)
def run_semantic_query(snowflake: Snowflake, request: Request) -> Response:
    # Build the dialect INSIDE the body — never reference a module-level constant.
    dialect = SnowflakeDialect(view_name="")  # noqa: F841
    raise NotImplementedError("Copy the body from the template tools.py section.")
'''

_TRANSFORM_STUB = '''\
"""Transform — RUNTIME data production + sibling bundling. NEVER provisions.

A .transform(...) is MANDATORY regardless: the rpc-output code(fn) path ships
only the extracted __<fn>__.py tool scripts — NOT the sibling modules they
import (registry.py, tools.py). Those are bundled by the **/*.py glob that runs
on this transform/compute output path. Without a .transform(...) the pod dies
`ModuleNotFoundError: No module named 'registry'`.

If the DP produces data at runtime (derived tables, scheduled refresh), write
that real logic here. For a fully-static-seed DP (like the validated demo) there
is no runtime work, so this transform is legitimately a no-op — it exists only to
trigger sibling bundling.

It must NEVER (re)provision: promise verification + provisioning already ran
BEFORE the transform. Seeding/creating the promised table or the semantic view
here fails verification or makes the DP flap Started↔Failed. All one-time setup
lives in provision.py (@on_provision). Do NOT import the compiler's
native_semantic_view_ddl / plain_view_ddl here.
"""


def transform(context) -> None:
    # No runtime work for a static-seed DP; setup is owned by @on_provision.
    # A DP with real runtime data production would write that logic here instead.
    print("semantic DP: data is static seed; setup owned by @on_provision")
'''

_PROVISION_STUB = '''\
"""Provision hook — seeds the base table(s) + the view BEFORE promise verification.

The kernel runs output-port promise verification BEFORE the transform, so a
marker/base table seeded only in the transform does not exist yet at verify time
→ `Field MARKER_ID not found` → DP Failed. The provision function runs FIRST
(before storage-driver provisioning + before verify), so seeding here makes the
DP green in one launch. Wired via `.provision(script("provision.py"))` in spec.py.

SELF-CONTAINED — all imports are inline and it does NOT import any sibling module
(registry/tools/transform). The provision entrypoint is extracted into a
`provision/` subdir whose sys.path does not include the DP root, so a bare
`from registry import REGISTRY` would raise ModuleNotFoundError. The one value
that would come from the registry — the semantic view name — is hardcoded here as
the library default `<FIRST_MODEL_UPPER>_SEMANTIC`.

The view DDL references ONLY this DP's own tables — never the compiler's cross-DP
join DDL. Cross-DP joins resolve at QUERY time via the live mesh, never at
view-creation time. Hand-author a SINGLE-TABLE view.
"""

from nxd import data_product
from nxd.data_product.context import Snowflake

# Hardcoded — the library default is <FIRST_MODEL_UPPER>_SEMANTIC. Replace with
# your model's name; do NOT import the registry to compute it (no sibling imports).
_VIEW_NAME = "SUBJECTS_SEMANTIC"


@data_product.on_provision()
def provision(snowflake: Snowflake) -> None:
    if snowflake is None or not snowflake.schema:
        print("provision skipped — no Snowflake schema in context")
        return

    # Canonical connection (matches SKILL.md + the templates): connector.connect(...)
    # with the explicit fields + connector_params(); NOT snowflake.connect(...).
    from snowflake import connector
    fqn = (
        f"{snowflake.database}.{snowflake.schema}."
        if snowflake.database else f"{snowflake.schema}."
    )
    conn = connector.connect(
        user=snowflake.user, account=snowflake.account, warehouse=snowflake.warehouse,
        role=snowflake.role, database=snowflake.database, schema=snowflake.schema,
        ocsp_fail_open=True, **snowflake.connector_params(),
    )
    cur = conn.cursor()
    try:
        # 1. seed THIS DP's own base table(s) — single-table, no cross-DP refs.
        cur.execute(
            f"CREATE OR REPLACE TABLE {fqn}SUBJECTS "
            "(SUBJECT_ID NUMBER, SUBJECT_COUNTRY VARCHAR, SUBJECT_MRN VARCHAR)"
        )
        cur.execute(
            f"INSERT INTO {fqn}SUBJECTS VALUES "
            "(1, 'US', 'MRN-0001'), (2, 'US', 'MRN-0002'), "
            "(3, 'DE', 'MRN-0003'), (4, 'FR', 'MRN-0004')"
        )

        # 2. seed the promised marker table the storage output port verifies.
        cur.execute(
            f"CREATE OR REPLACE TABLE {fqn}SUBJECTS_MARKER "
            "(MARKER_ID NUMBER, VIEW_NAME VARCHAR)"
        )
        cur.execute(
            f"INSERT INTO {fqn}SUBJECTS_MARKER VALUES (1, '{_VIEW_NAME}')"
        )

        # 3. create the SINGLE-TABLE semantic view (NO cross-DP JOIN; name hardcoded).
        cur.execute(
            f"CREATE OR REPLACE VIEW {fqn}{_VIEW_NAME} AS "
            "SELECT SUBJECT_ID AS SUBJECT_ID, "
            "SUBJECT_COUNTRY AS SUBJECT_COUNTRY, "
            f"SUBJECT_MRN AS SUBJECT_MRN FROM {fqn}SUBJECTS"
        )
        print(f"provisioned single-table VIEW {fqn}{_VIEW_NAME}")
    finally:
        cur.close()
        conn.close()
'''

_MODELS_STUB = '''\
"""One promised marker model — satisfies the storage output port."""

from nxd.spec import semantic_model
from nxd.spec.data_types import int64, string

provision_marker = (
    semantic_model("subjects_marker")
    .description("Marker table written by the @on_provision hook.")
    .schema({"MARKER_ID": int64(), "VIEW_NAME": string()})
)
'''

# The correct spec.py wiring block to print for the user.
SPEC_RPC_OUTPUT_SNIPPET = """\
# ── Add these imports to spec.py ─────────────────────────────────────────────
from nxd.spec import (
    data_product,
    data_product_output,
    data_product_rpc_output,
    rpc_function,
    rpc_server,
    storage,
    code,
    script,
)
from nxd.experimental.semantic import build_semantic_tools
from registry import REGISTRY
from tools import list_models, describe_model, run_semantic_query
from transform import transform
from models import provision_marker

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
    rpc_server("<infra-profile-path>#/services/<mcp-service-name>")
    .enable_endpoints()
    .mcp_path("/mcp"),
)

# ── data_product spec ─────────────────────────────────────────────────────────
spec = (
    # provision_timeout_secs is a FACTORY kwarg (NOT .compute(...)) — heavy
    # snowflake+pandas provision deps exceed the 180s default and the DP fails.
    data_product(name="<your-dp-name>", domain="<domain>", version="0.1.0",
                 infra_profile="<infra-profile>", provision_timeout_secs=600)
    # PROVISION (runs BEFORE promise verification): seeds the base + marker tables
    # and creates the single-table <MODEL>_SEMANTIC view. provision.py is
    # self-contained (no sibling imports; view name hardcoded).
    .provision(script("provision.py"))
    # MANDATORY transform — RUNTIME data production + bundles registry.py/tools.py
    # via the **/*.py glob. No-op for a static-seed DP. NEVER (re)provisions.
    .transform(code(transform).compute("<infra-profile-path>#/services/<compute>"))
    .output(
        data_product_output()
        .promise(provision_marker)
        # plain storage(...) — NOT .config(...).as_view(...): the facade as_view
        # pattern is mutually exclusive with .transform(), and an rpc DP needs the
        # transform (for sibling bundling). nxd validate rejects facade + transform.
        .port("snowflake", storage("<infra-profile-path>#/services/<snowflake>"))
    )
    .output(_rpc)
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
    _write_stub(target_dir / "transform.py", _TRANSFORM_STUB, "MANDATORY runtime transform stub (no-op for static seed)")
    _write_stub(target_dir / "provision.py", _PROVISION_STUB, "self-contained @on_provision seed — adapt to your tables/view")
    _write_stub(target_dir / "models.py", _MODELS_STUB, "promised marker model")

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
        "See reference/scripts/templates/spec_rpc_output.py.tmpl for full annotation.\n"
        "See reference/scripts/templates/transform_provision.py.tmpl for the complete "
        "spec.py + tools.py + transform.py + provision.py example.\n"
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
