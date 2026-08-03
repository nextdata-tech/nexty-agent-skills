"""A minimal fake ``nxd`` CLI for MCP eval scenarios.

The nxd-query-data-product skill discovers DP MCP endpoints by shelling out to
``nxd mcp health --format json`` (see scripts/mcp_gateway.py). In the eval there
is no real mesh, so run.py starts the semantic HTTP MCP server itself and points
this stub at it: ``nxd mcp health`` returns a single ``data_products`` row whose
``endpoint`` is the running server's proxy URL. The skill's real toolchain then
opens a Streamable-HTTP MCP session against it and lists/calls the genuine tools
— so the skill runs exactly as shipped, against the real semantic compiler.

run.py writes a tiny ``nxd`` shim onto the agent's PATH that execs:
    python fake_nxd.py <args...>
with EVAL_MCP_ENDPOINT / EVAL_MCP_DP / EVAL_MCP_TOOL_COUNT set in the env.

Only the subcommands the skill actually calls are implemented; anything else
exits non-zero with a clear message so a skill relying on an unstubbed command
fails loudly rather than silently.
"""

from __future__ import annotations

import json
import os
import sys


def _mcp_health() -> int:
    endpoint = os.environ.get("EVAL_MCP_ENDPOINT", "")
    if not endpoint:
        print("fake_nxd: EVAL_MCP_ENDPOINT not set", file=sys.stderr)
        return 1
    tool_count = int(os.environ.get("EVAL_MCP_TOOL_COUNT", "3"))
    dp = os.environ.get("EVAL_MCP_DP", "semantic-demo")
    payload = {
        "service": "mcp-proxy-api",
        "version": "eval-stub",
        "summary": {"total": 1, "healthy": 1, "degraded": 0, "broken": 0},
        "discovery_stream": {"state": "Connected"},
        "data_products": [
            {
                "dp_full_name": dp,
                "endpoint": endpoint,
                "derived_state": "Healthy",
                "http": {"healthy": True},
                "mcp": {
                    "tool_count": tool_count,
                    "breaker": {"state": "Closed"},
                },
            }
        ],
    }
    print(json.dumps(payload))
    return 0


def main(argv: list[str]) -> int:
    # Recognise: nxd mcp health [--format json] [--mesh <m>]
    args = argv[1:]
    if len(args) >= 2 and args[0] == "mcp" and args[1] == "health":
        return _mcp_health()
    # whoami / login may be probed by the skill setup; report a logged-in stub.
    if args[:1] == ["whoami"]:
        print("eval-analyst@nextdata.com")
        return 0
    print(
        f"fake_nxd: unstubbed command {args!r}. Only `nxd mcp health` and "
        "`nxd whoami` are stubbed for MCP eval scenarios.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
