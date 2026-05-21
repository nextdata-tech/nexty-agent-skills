#!/usr/bin/env python3
"""Parse a nextdata infra profile and classify its services.

Prints the services grouped by category. Storage and API services are
data-bearing and inspectable; Compute, RPC, and Governance are not.
Only non-secret locator attributes are shown — credentials are never printed.

Usage:
    classify_profile.py <profile.yaml> [--json]
"""
import json, argparse

from meshlib.profile import parse_services, CATEGORY_ORDER


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("profile")
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = ap.parse_args()

    profile_name, services = parse_services(args.profile)
    # drop the full attrs (secrets) — expose only non-secret locator fields
    public = [{"name": s["name"], "driver": s["driver"],
               "driver_name": s["driver_name"], "category": s["category"],
               "locator": s["locator"]} for s in services]

    if args.json:
        print(json.dumps({"profile": profile_name, "services": public}, indent=2))
        return

    print(f"profile: {profile_name}\n")
    for cat in CATEGORY_ORDER:
        rows = [s for s in public if s["category"] == cat]
        if not rows:
            continue
        tag = " (inspectable)" if cat in ("STORAGE", "API") else " (skip - not a data source)"
        print(f"== {cat}{tag} ==")
        for s in rows:
            loc = ", ".join(f"{k}={v}" for k, v in s["locator"].items())
            print(f"  {s['name']}  [{s['driver_name']}]  {loc}")
        print()


if __name__ == "__main__":
    main()
