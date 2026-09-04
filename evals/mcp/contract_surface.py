"""Extract the eval harness's MCP surface from the real server descriptors.

The surface is read off the FastMCP instance ``semantic_server.build_server``
actually builds, not restated here. A hand-written list of the eval's tools
would be a second place to edit whenever the server changes, and the whole point
of the contract check is that a stand-in must not be able to drift unobserved —
including from itself.

Building the server needs a scenario fixture directory and the genuine NXD
semantic registry, but no Snowflake: ``build_server`` defers every database
round-trip to the first ``run_semantic_query`` call. So this runs in CI with no
credentials.

Emits an ``nxd-eval-mcp-surface-v1`` document for ``contract_check.py``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any
from typing import Sequence

SURFACE_SCHEMA = "nxd-eval-mcp-surface-v1"

#: Any scenario fixture set will do — the three tools are registered
#: unconditionally, and only their payloads are fixture-derived. Naming one
#: keeps the extraction reproducible.
DEFAULT_FIXTURES = Path(__file__).resolve().parents[1] / "public/semantic-intent-validation/fixtures"


def _parameters(input_schema: dict[str, Any]) -> list[dict[str, Any]]:
    """Read parameters off a JSON Schema the same way NXD's producer does."""
    properties = input_schema.get("properties") or {}
    required = set(input_schema.get("required") or [])
    return [{"name": name, "required": name in required} for name in sorted(properties)]


def surface_from_tools(tools: Sequence[Any]) -> dict[str, Any]:
    """Build a surface document from MCP tool descriptors.

    Accepts anything with ``name``/``description``/``inputSchema``, so the same
    function serves both the locally built FastMCP server and a live server
    reached over Streamable-HTTP in the nightly canary.
    """
    entries: list[dict[str, Any]] = []
    for tool in tools:
        input_schema = getattr(tool, "inputSchema", None) or {}
        entries.append(
            {
                "name": tool.name,
                "description": tool.description or "",
                "input_schema": input_schema,
                "parameters": _parameters(input_schema),
            }
        )
    return {"schema": SURFACE_SCHEMA, "tools": sorted(entries, key=lambda entry: entry["name"])}


def surface_from_fixtures(fixture_dir: Path) -> dict[str, Any]:
    """Build the eval server in-process and read its registered tools."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from semantic_server import build_server

    server = build_server(fixture_dir)
    return surface_from_tools(asyncio.run(server.list_tools()))


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="contract_surface")
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    if not args.fixtures.is_dir():
        print(f"contract_surface: no such fixture directory: {args.fixtures}", file=sys.stderr)
        return 2
    surface = surface_from_fixtures(args.fixtures)
    args.out.write_text(json.dumps(surface, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"contract_surface: wrote {len(surface['tools'])} tool(s) to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
