#!/usr/bin/env python3
"""Scaffold a semantic-layer data product.

Copies the vendored semantic/ kit into <target_dir>/transform/semantic/,
writes a placeholder registry.py, and prints the spec.py rpc-output wiring
block and the requirements.txt lines the DP needs.

Usage:
    uv run python scaffold_semantic_dp.py <target_dir>

<target_dir> should be the root of the data product directory (the directory
that will contain spec.py). The script creates transform/ if it does not exist.

NXD WIRING NOTE
---------------
NXD exposes MCP tools ONLY through spec.py via data_product_rpc_output().
There is NO module-level `tools` list discovery — a bare
`tools = build_semantic_tools(REGISTRY)` exposes ZERO MCP tools at runtime.

The scaffold prints the correct spec.py block:

    _rpc = data_product_rpc_output()
    for _t in build_semantic_tools(REGISTRY):
        _rpc = _rpc.function(
            rpc_function(code(_t.fn), _t.request_model, _t.response_model)
            .description(_t.description)
        )
    _rpc = _rpc.port(
        "mcp-api",
        rpc_server("<infra-profile mcp service ref>")
        .enable_endpoints()
        .mcp_path("/mcp"),
    )
    # then: .output(_rpc) on the data_product(...) spec

Reference: reference/scripts/templates/spec_rpc_output.py.tmpl
PoC example: examples_private/argenx/hcp-poc/spec.py
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path


SKILL_ROOT = Path(__file__).parent
SEMANTIC_SRC = SKILL_ROOT / "semantic"

REQUIREMENTS_LINES = [
    "nxd.data_product[spec]",
    "nxd.drivers[rpc]",
    "snowflake-connector-python[pandas]",
    "pandas",
]

# The correct spec.py wiring block to print for the user.
SPEC_RPC_OUTPUT_SNIPPET = """\
# ── Add these imports to spec.py ─────────────────────────────────────────────
from nxd.spec import (
    data_product_rpc_output,
    rpc_function,
    rpc_server,
    code,
)
from semantic import build_semantic_tools
from registry import REGISTRY

# ── RPC output wiring (the ONLY supported MCP delivery mechanism) ─────────────
_rpc = data_product_rpc_output()
for _t in build_semantic_tools(REGISTRY):
    _rpc = _rpc.function(
        rpc_function(code(_t.fn), _t.request_model, _t.response_model)
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
    data_product(name="<your-dp-name>", ...)
    .output(_rpc)
    # Add inputs, transforms, additional outputs as needed.
)
"""


def scaffold(target_dir: Path) -> None:
    transform_dir = target_dir / "transform"
    transform_dir.mkdir(parents=True, exist_ok=True)

    semantic_dest = transform_dir / "semantic"
    if semantic_dest.exists():
        print(f"  [skip] {semantic_dest} already exists — not overwriting.")
    else:
        shutil.copytree(SEMANTIC_SRC, semantic_dest)
        print(f"  [copy] semantic/ kit -> {semantic_dest}")

    registry_py = transform_dir / "registry.py"
    if not registry_py.exists():
        placeholder = (
            "# TODO: author your SemanticRegistry here.\n"
            "# See reference/registry-authoring.md for the full API.\n"
            "#\n"
            "# from semantic.registry import Agg, Cardinality, SemanticRegistry\n"
            "#\n"
            "# REGISTRY = (\n"
            "#     SemanticRegistry()\n"
            "#     .model(...)\n"
            "#     .dimension(...)\n"
            "#     .metric(...)\n"
            "#     .join(...)\n"
            "#     .build()\n"
            "# )\n"
        )
        registry_py.write_text(placeholder, encoding="utf-8")
        print(f"  [write] {registry_py} (placeholder — fill in your registry)")

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
        "See reference/scripts/templates/transform_provision.py.tmpl for a complete spec.py example."
    )


def main() -> int:
    if len(sys.argv) != 2:
        print(f"Usage: uv run python {sys.argv[0]} <target_dp_dir>", file=sys.stderr)
        return 1
    target = Path(sys.argv[1]).resolve()
    if not target.exists():
        print(f"Error: target directory does not exist: {target}", file=sys.stderr)
        return 1
    print(f"Scaffolding semantic-layer DP in: {target}")
    scaffold(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
