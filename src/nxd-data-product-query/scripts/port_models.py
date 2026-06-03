"""Print the model attributes (column schema) for a port's models.

Resolves the port's models from the `/v1/outputs` payload — preferring
`port.model_names`, falling back to `port.promises.model[].model`, falling
back to the DP's top-level `model_names`. Then fetches `/v1/models` and emits
just the matching models with their attributes.

Use right after the user picks a port, before they submit a query — gives
them the column list and types so they can frame the question.
"""

from __future__ import annotations

import argparse
import json
import sys

from nxd_api import find_dp, get_models, list_outputs, read_token


def _resolve_model_names(outputs: dict, port_name: str) -> list[str]:
    for port in outputs.get("ports", []):
        if port["name"] != port_name:
            continue
        names = list(port.get("model_names") or [])
        if names:
            return names
        promises = (port.get("promises") or {}).get("model") or []
        names = [p["model"] for p in promises if p.get("model")]
        if names:
            return names
        break
    return list(outputs.get("model_names") or [])


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--api-url", required=True)
    p.add_argument("--dp", required=True)
    p.add_argument("--port", required=True)
    p.add_argument("--token-file")
    args = p.parse_args()

    token = read_token(args.token_file)
    dp = find_dp(args.api_url, token, args.dp)
    if not dp:
        sys.exit(f"data product not found: {args.dp}")

    outputs = list_outputs(dp, token)
    model_names = _resolve_model_names(outputs, args.port)
    if not model_names:
        sys.exit(f"no models resolved for port {args.port!r}")

    all_models = {m["name"]: m for m in get_models(dp, token)}
    out = []
    for name in model_names:
        m = all_models.get(name)
        if not m:
            out.append({"name": name, "missing": True})
            continue
        out.append(
            {
                "name": m["name"],
                "description": m.get("description"),
                "attributes": [
                    {
                        "name": a["name"],
                        "data_type": a.get("data_type"),
                        "description": a.get("description"),
                    }
                    for a in m.get("attributes", [])
                ],
            }
        )

    print(json.dumps({"port": args.port, "models": out}, indent=2))


if __name__ == "__main__":
    main()
