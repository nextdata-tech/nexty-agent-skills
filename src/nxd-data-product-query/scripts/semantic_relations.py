"""Strict mode — collect semantic_model MCP responses across DPs.

Reads the gateway catalogue produced by ``mcp_gateway.py`` and, for every
endpoint that advertises a ``semantic_model``-shaped tool, opens an MCP
session and calls it. The responses are merged into a single relations
bundle so the plan validator can verify joins, projections, and filters
against an authoritative source.

Output schema (written to ``--out``):

    {
      "source_gateway": "<path>",
      "models": [
        {"dp": "<fullName>", "model": "<name>", "attributes": [...], "source_tool": "semantic_model"}
      ],
      "relationships": [
        {"from_dp": "...", "from_model": "...", "to_dp": "...", "to_model": "...",
         "kind": "fk|derived|joins_on|...",
         "on": [{"from": "col", "to": "col"}],
         "evidence": {"semantic_model_dp": "...", "tool": "semantic_model", "path": "relationships[0]"}}
      ],
      "errors": [...]
    }

The script is permissive about the exact shape returned by each DP's
semantic_model tool — different DPs may use slightly different field names
(``relationships``, ``relations``, ``links``). Anything unrecognised is
captured under ``raw`` so the validator can still cite provenance.

CLI:

    python3 semantic_relations.py --gateway /tmp/nxd-mcp-gateway.json \
        --token-file /tmp/nxd.tok --out /tmp/nxd-relations.json \
        [--dps <dp-1>,<dp-2>] \
        [--tool-pattern semantic_model] \
        [--call-args '{}']
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from mcp_http import McpClient, McpError, with_retry
from nxd_api import read_token, resolve_mesh


def _matches(tool_name: str, pattern: str) -> bool:
    return re.search(pattern, tool_name or "", re.IGNORECASE) is not None


def _unwrap_tool_result(result: dict[str, Any]) -> Any:
    """MCP ``tools/call`` returns ``{content: [...], structuredContent: {...}}``.

    Prefer ``structuredContent`` when present; otherwise stitch any text
    blocks from ``content`` together and try to parse as JSON. Fallback is
    the raw result so the validator can still inspect it."""
    if not isinstance(result, dict):
        return result
    if "structuredContent" in result and result["structuredContent"] is not None:
        return result["structuredContent"]
    content = result.get("content")
    if isinstance(content, list):
        texts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
        joined = "\n".join(texts)
        if joined.strip():
            try:
                return json.loads(joined)
            except json.JSONDecodeError:
                return {"text": joined}
    return result


def _harvest_models(payload: Any, dp: str, tool: str) -> tuple[list[dict], list[dict], str | None]:
    """Pull model entries + relationship entries from a semantic_model response.

    Recognised field names — case insensitive:
      models | semantic_models                         → list of {name|model, attributes|fields|columns}
      relationships | relations | links | joins        → list of {from|source, to|target, kind|type, on|join_on}

    Also accepts a top-level ``result`` envelope (a common MCP server
    pattern) and surfaces any ``error`` field as the third return value.
    """
    models: list[dict] = []
    rels: list[dict] = []
    if not isinstance(payload, dict):
        return models, rels, None
    # Unwrap the serialized-registry envelope {"payload": "<json string>"} that
    # the standard `semantic_model` tool returns (the cross-DP registry payload).
    if "payload" in payload and isinstance(payload["payload"], str) and "models" not in payload:
        try:
            payload = json.loads(payload["payload"])
        except json.JSONDecodeError:
            pass
    # Unwrap a top-level "result" envelope if present.
    if "result" in payload and isinstance(payload["result"], dict) and not (
        payload.get("models") or payload.get("relationships")
    ):
        payload = payload["result"]
    tool_error = payload.get("error") if isinstance(payload.get("error"), str) else None

    # Models
    raw_models_any: Any = (
        payload.get("models")
        or payload.get("semantic_models")
        or payload.get("schemas")
        or []
    )
    if isinstance(raw_models_any, dict):
        raw_models = [
            {"name": k, **(v if isinstance(v, dict) else {"value": v})}
            for k, v in raw_models_any.items()
        ]
    else:
        raw_models = list(raw_models_any or [])
    for m in raw_models:
        if not isinstance(m, dict):
            continue
        name = m.get("name") or m.get("model") or m.get("id")
        attrs = (
            m.get("attributes")
            or m.get("fields")
            or m.get("columns")
            or m.get("properties")
            or []
        )
        models.append({"dp": dp, "model": name, "attributes": attrs, "source_tool": tool})

        # Per-model link arrays. Each entry typically has
        # {field, predicate, data_product, model, attribute}.
        for idx, link in enumerate(m.get("links") or m.get("relationships") or []):
            if not isinstance(link, dict):
                continue
            other_dp = link.get("data_product") or link.get("to_dp") or link.get("target_dp")
            other_model = link.get("model") or link.get("to_model") or link.get("target")
            other_attr = link.get("attribute") or link.get("to_attribute") or link.get("target_attribute")
            field = link.get("field") or link.get("from_attribute")
            kind = link.get("predicate") or link.get("kind") or link.get("type") or "joins_on"
            rels.append(
                {
                    "from_dp": dp,
                    "from_model": name,
                    "from_attribute": field,
                    "to_dp": other_dp or dp,
                    "to_model": other_model,
                    "to_attribute": other_attr,
                    "kind": kind,
                    "evidence": {
                        "semantic_model_dp": dp,
                        "tool": tool,
                        "path": f"models[{name}].links[{idx}]",
                    },
                    "raw": link,
                }
            )

    # Relationships. NOTE: `joins` is intentionally NOT here — the registry-style
    # `joins` array ({left, right, on, cardinality}) is parsed by the dedicated
    # block below; including it here would double-count it as None→None.
    raw_rels = (
        payload.get("relationships")
        or payload.get("relations")
        or payload.get("links")
        or []
    )
    for idx, r in enumerate(raw_rels or []):
        if not isinstance(r, dict):
            continue
        rels.append(
            {
                "from_dp": r.get("from_dp") or r.get("source_dp") or dp,
                "from_model": r.get("from_model") or r.get("from") or r.get("source") or r.get("source_model"),
                "to_dp": r.get("to_dp") or r.get("target_dp") or dp,
                "to_model": r.get("to_model") or r.get("to") or r.get("target") or r.get("target_model"),
                "kind": r.get("kind") or r.get("type") or "joins_on",
                "on": r.get("on") or r.get("join_on") or r.get("keys") or [],
                "evidence": {
                    "semantic_model_dp": dp,
                    "tool": tool,
                    "path": f"relationships[{idx}]",
                },
                "raw": r,
            }
        )

    # Registry-style joins: {left, right, on: [[from_col, to_col], ...], cardinality}
    # — the shape the nxd.experimental.semantic registry / `semantic_model` tool
    # emits. ``left`` is the many side, ``right`` the one side.
    for idx, j in enumerate(payload.get("joins") or []):
        if not isinstance(j, dict):
            continue
        on_pairs = [
            {"from": pair[0], "to": pair[1]}
            for pair in (j.get("on") or [])
            if isinstance(pair, (list, tuple)) and len(pair) == 2
        ]
        rels.append(
            {
                "from_dp": dp,
                "from_model": j.get("left") or j.get("from_model"),
                "to_dp": dp,
                "to_model": j.get("right") or j.get("to_model"),
                "kind": j.get("cardinality") or j.get("kind") or "joins_on",
                "on": on_pairs,
                "evidence": {
                    "semantic_model_dp": dp,
                    "tool": tool,
                    "path": f"joins[{idx}]",
                },
                "raw": j,
            }
        )

    return models, rels, tool_error


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--gateway", required=True, help="Path to gateway catalogue JSON from mcp_gateway.py")
    p.add_argument("--token-file", help="Path to a file holding the bearer token (preferred)")
    p.add_argument("--mesh", help="Mesh name when multiple are configured")
    p.add_argument("--out", required=True, help="Where to write the relations bundle")
    p.add_argument(
        "--dps",
        default="",
        help="Optional comma-separated DP fullName allow-list (default: all DPs that expose a semantic_model tool)",
    )
    p.add_argument(
        "--tool-pattern",
        default=r"^semantic[_-]?models?(__[a-z0-9]+)?$",
        help="Regex to match the semantic-model tool name (case-insensitive). "
        "Default matches the contracted standard `semantic_model` with an optional "
        "multiplexer `__<hash>` suffix (the gateway namespaces per-DP tools). "
        "Override if a DP author uses a non-standard name (e.g. `get_semantic_models`): "
        "`--tool-pattern '^(get_)?semantic_models?(__[a-z0-9]+)?$'`.",
    )
    p.add_argument(
        "--call-args",
        default="{}",
        help="JSON object passed as arguments to the semantic-model tool (default {})",
    )
    p.add_argument("--timeout", type=float, default=30.0)
    args = p.parse_args()

    try:
        gateway = json.loads(Path(args.gateway).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        sys.exit(f"cannot read gateway file {args.gateway}: {exc}")

    try:
        call_args = json.loads(args.call_args)
    except json.JSONDecodeError as exc:
        sys.exit(f"--call-args is not valid JSON: {exc}")

    if args.token_file:
        token = read_token(args.token_file)
    else:
        m = resolve_mesh(args.mesh)
        if not m.token:
            sys.exit("no bearer token for the active mesh — run nxd-setup or nxd login")
        token = m.token

    dp_filter: set[str] = {x.strip() for x in args.dps.split(",") if x.strip()}

    models: list[dict] = []
    relationships: list[dict] = []
    errors: list[dict] = []
    visited: list[dict] = []

    for ep in gateway.get("endpoints") or []:
        dp = ep.get("dp_full_name") or ""
        endpoint = ep.get("endpoint") or ""
        if not dp or not endpoint or ep.get("error"):
            continue
        if dp_filter and dp not in dp_filter:
            continue
        tools = ep.get("tools") or []
        sem_tools = [t for t in tools if _matches(t.get("name") or "", args.tool_pattern)]
        if not sem_tools:
            continue
        for t in sem_tools:
            tool_name = t.get("name")
            visited.append({"dp": dp, "tool": tool_name})
            try:
                with McpClient(endpoint=endpoint, token=token, timeout=args.timeout) as c:
                    # Retry transient 5xx on the semantic-model call — cold DP
                    # proxies sometimes 503 the first request after a redeploy.
                    raw = with_retry(lambda: c.tools_call(tool_name, call_args))
            except McpError as exc:
                errors.append({"dp": dp, "tool": tool_name, "reason": f"{exc.code}: {exc.message}"})
                continue
            except Exception as exc:  # noqa: BLE001
                errors.append({"dp": dp, "tool": tool_name, "reason": f"{type(exc).__name__}: {exc}"})
                continue
            payload = _unwrap_tool_result(raw)
            m, r, tool_err = _harvest_models(payload, dp, tool_name)
            models.extend(m)
            relationships.extend(r)
            if tool_err:
                errors.append({"dp": dp, "tool": tool_name, "reason": f"tool reported error: {tool_err}"})

    bundle = {
        "source_gateway": str(Path(args.gateway).resolve()),
        "visited": visited,
        "models": models,
        "relationships": relationships,
        "errors": errors,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(bundle, indent=2))

    print(
        json.dumps(
            {
                "out": str(out_path),
                "models": len(models),
                "relationships": len(relationships),
                "visited_dps": len({v["dp"] for v in visited}),
                "errors": len(errors),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
