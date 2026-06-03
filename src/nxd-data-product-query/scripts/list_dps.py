"""List deployed Data Products on a mesh."""

from __future__ import annotations

import argparse
import json

from nxd_api import list_data_products, read_token


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--api-url", required=True)
    p.add_argument("--token-file")
    p.add_argument("--format", choices=("json", "table"), default="json")
    args = p.parse_args()

    token = read_token(args.token_file)
    dps = list_data_products(args.api_url, token)

    if args.format == "table":
        rows = [
            (dp["fullName"], dp.get("domain", ""), dp.get("version", ""), dp.get("baseUrl", ""))
            for dp in dps
        ]
        widths = [max(len(r[i]) for r in rows + [("NAME", "DOMAIN", "VERSION", "BASE_URL")]) for i in range(4)]
        header = ("NAME", "DOMAIN", "VERSION", "BASE_URL")
        print("  ".join(h.ljust(widths[i]) for i, h in enumerate(header)))
        for r in rows:
            print("  ".join(c.ljust(widths[i]) for i, c in enumerate(r)))
        return

    print(
        json.dumps(
            [
                {
                    "fullName": dp["fullName"],
                    "name": dp.get("name"),
                    "domain": dp.get("domain"),
                    "version": dp.get("version"),
                    "baseUrl": dp.get("baseUrl"),
                    "description": dp.get("description"),
                }
                for dp in dps
            ],
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
