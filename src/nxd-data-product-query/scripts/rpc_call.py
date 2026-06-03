"""Invoke a function on an RPC output port via HTTP.

Falls back to surfacing the function schemas (request_model / response_model)
when no --function is given, so the LLM can pick the right call.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from nxd_api import auth_headers, dp_base_url, find_dp, list_rpc_outputs, read_token

import requests


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--api-url", required=True)
    p.add_argument("--dp", required=True)
    p.add_argument("--port", required=True)
    p.add_argument("--function", help="Function name; omit to list functions on the port")
    p.add_argument("--args", default="{}", help="JSON payload conforming to the function's request_model")
    p.add_argument("--token-file")
    p.add_argument("--out")
    args = p.parse_args()

    token = read_token(args.token_file)
    dp = find_dp(args.api_url, token, args.dp)
    if not dp:
        sys.exit(f"data product not found: {args.dp}")

    rpc = list_rpc_outputs(dp, token)
    port = next((pt for pt in rpc.get("ports", []) if pt["name"] == args.port), None)
    if not port:
        sys.exit(f"rpc port {args.port!r} not found")

    if not args.function:
        print(json.dumps(port, indent=2))
        return

    fn = next((f for f in port.get("functions", []) if f["name"] == args.function), None)
    if not fn:
        sys.exit(f"function {args.function!r} not found on rpc port {args.port}")

    url = f"{dp_base_url(dp)}/v1/rpc/{args.port}/{args.function}"
    payload = json.loads(args.args)
    r = requests.post(
        url,
        headers={**auth_headers(token), "Content-Type": "application/json"},
        data=json.dumps(payload),
        timeout=60,
    )
    out = {"status": r.status_code, "body": r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text}
    text = json.dumps(out, default=str, indent=2)
    if args.out:
        Path(args.out).write_text(text)
    else:
        print(text)


if __name__ == "__main__":
    main()
