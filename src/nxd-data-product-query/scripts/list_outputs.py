"""List data + RPC output ports of a Data Product."""

from __future__ import annotations

import argparse
import json
import sys

from nxd_api import find_dp, list_outputs, list_rpc_outputs, read_token


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--api-url", required=True)
    p.add_argument("--dp", required=True, help="Data Product fullName")
    p.add_argument("--token-file")
    args = p.parse_args()

    token = read_token(args.token_file)
    dp = find_dp(args.api_url, token, args.dp)
    if not dp:
        sys.exit(f"data product not found: {args.dp}")

    outputs = list_outputs(dp, token)
    try:
        rpc = list_rpc_outputs(dp, token)
    except Exception:
        rpc = {"functions": [], "ports": []}

    result = {
        "dp": {
            "fullName": dp["fullName"],
            "baseUrl": dp["baseUrl"],
            "domain": dp.get("domain"),
        },
        "model_names": outputs.get("model_names", []),
        "data_ports": [
            {
                "kind": "data",
                "name": port["name"],
                "infra_profile_name": port.get("infra_profile_name"),
                "infra_service_name": port.get("infra_service_name"),
                "model_names": port.get("model_names", []),
                "promises": port.get("promises"),
            }
            for port in outputs.get("ports", [])
        ],
        "rpc_ports": [
            {
                "kind": "rpc",
                "name": port["name"],
                "service_name": port.get("service_name"),
                "functions": [
                    {
                        "name": fn["name"],
                        "description": fn.get("description"),
                        "request_model": fn.get("request_model"),
                        "response_model": fn.get("response_model"),
                    }
                    for fn in port.get("functions", [])
                ],
            }
            for port in rpc.get("ports", [])
        ],
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
