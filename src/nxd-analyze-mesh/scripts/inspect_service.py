#!/usr/bin/env python3
"""Inspect data-bearing services from a nextdata infra profile (read-only).

Connects to each named service through its driver plugin, inventories its
data assets with schema-fingerprint grouping, de-duplicates shared stores,
and writes a combined inventory JSON. Credentials are read from the profile
in-process and never printed.

Driver plugins live in `drivers/` — one file per service type. Built-in:
s3, snowflake. To support another service type, add `drivers/<name>.py`.

Usage:
    inspect_service.py <profile.yaml> <service> [<service> ...] [--out FILE] [--api-url URL]
"""
import json, argparse

from meshlib.schema import jdefault
from meshlib.inventory import inspect_services
from drivers import default_registry


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("profile")
    ap.add_argument("services", nargs="+")
    ap.add_argument("--out", default="mesh-assets-inventory.json")
    ap.add_argument("--api-url", default="",
                    help="mesh API base URL; makes service URLs absolute")
    args = ap.parse_args()

    result = inspect_services(args.profile, args.services,
                              default_registry(), args.api_url)

    with open(args.out, "w") as f:
        json.dump(result, f, indent=2, default=jdefault)

    for name, inv in result.items():
        if "error" in inv:
            print(f"  {name}: ERROR {inv['error']}")
        elif "duplicate_of" in inv:
            print(f"  {name}: duplicate of '{inv['duplicate_of']}' "
                  f"(same store {inv['store']})")
        else:
            print(f"  {name}: {inv['store']} -> {len(inv['assets'])} logical assets")
    print(f"\ninventory written to {args.out}")


if __name__ == "__main__":
    main()
