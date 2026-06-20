#!/usr/bin/env python3
"""Scaffold a semantic-layer data product (flat layout).

Writes placeholder registry.py, tools.py, transform.py, models.py FLAT at the
DP root (NOT under a transform/ subdir), and prints the requirements.txt lines
and the spec.py rpc-output wiring block the DP needs.

The compiler, dialect, and MCP tool factory are provided by the installed
nxd.data_product wheel (module nxd.experimental.semantic) — imported, not
vendored. The DP authors the registry + tools + transform and wires spec.py.

Usage:
    uv run python scaffold_semantic_dp.py <target_dir>

<target_dir> should be the root of the data product directory (the directory
that will contain spec.py). All modules are created as flat siblings.

FOUR WIRING CONSTRAINTS (see reference/scripts/templates/transform_provision.py.tmpl)
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
4. Base tables must exist BEFORE promise verification (it runs before the
   transform). Prefer a facade over pre-existing tables provisioned at provision
   time.

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
"""

from typing import Any

from nxd.drivers.rpc import Request, Response, function, mcp
from registry import REGISTRY  # flat sibling import
from nxd.experimental.semantic.compiler import (
    CompileError,
    compile_selection,
    semantic_view_query,
)
from nxd.experimental.semantic.dialect import SnowflakeDialect

_DIALECT = SnowflakeDialect(view_name="")


@function(name="list_models")
@mcp.tool(name="list_models", description="TODO: list the semantic models.")
def list_models(request: Request) -> Response:
    raise NotImplementedError("Copy the body from the template tools.py section.")


@function(name="describe_model")
@mcp.tool(name="describe_model", description="TODO: describe one model in full.")
def describe_model(request: Request) -> Response:
    raise NotImplementedError("Copy the body from the template tools.py section.")


@function(name="run_semantic_query")
@mcp.tool(name="run_semantic_query", description="TODO: the safe, default query path.")
def run_semantic_query(snowflake: Any, request: Request) -> Response:
    raise NotImplementedError("Copy the body from the template tools.py section.")
'''

_TRANSFORM_STUB = '''\
"""MANDATORY transform — provisions the semantic view AND bundles the siblings.

The rpc-output code() path ships only the extracted tool scripts; the **/*.py
glob on this transform path is what bundles registry.py / tools.py into the
image so the extracted tool scripts can `from registry import REGISTRY`. Without
a transform the pod dies with ModuleNotFoundError.

Copy the full body from reference/scripts/templates/transform_provision.py.tmpl
(transform.py section). Note: promise verification runs BEFORE this transform,
so for production prefer a facade over pre-existing tables (provisioned at
provision time) rather than seeding base tables here.
"""

from nxd.data_product.context import Snowflake


def transform(snowflake: Snowflake) -> None:
    from registry import REGISTRY  # noqa: F401
    from nxd.experimental.semantic.compiler import (  # noqa: F401
        native_semantic_view_ddl,
        plain_view_ddl,
    )
    from nxd.experimental.semantic.dialect import SnowflakeDialect  # noqa: F401

    raise NotImplementedError("Copy the body from the template transform.py section.")
'''

_MODELS_STUB = '''\
"""One promised marker model — satisfies the storage output port."""

from nxd.spec import semantic_model
from nxd.spec.data_types import int64, string

provision_marker = (
    semantic_model("semantic_marker")
    .description("Marker table written by the provisioning transform.")
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
    data_product(name="<your-dp-name>", domain="<domain>", version="0.1.0",
                 infra_profile="<infra-profile>")
    # MANDATORY transform — provisions the view AND bundles registry.py/tools.py.
    .transform(code(transform).compute("<infra-profile-path>#/services/<compute>"))
    .output(
        data_product_output()
        .promise(provision_marker)
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
    _write_stub(target_dir / "transform.py", _TRANSFORM_STUB, "MANDATORY transform stub — fill in body")
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
        "spec.py + tools.py + transform.py example."
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
