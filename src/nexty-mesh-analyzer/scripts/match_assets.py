#!/usr/bin/env python3
"""Match candidate data product inputs and outputs across service inventories.

Reads inventory JSON files produced by inspect_service.py and reports pairs of
data assets that appear connected — one looks like the input to a transform
whose output is the other. Each candidate is classified source-aligned or
transformed, assigned a confidence and a business domain, and given a suggested
data product name (biased to the output dataset).

Writes two markdown files for a downstream data-product-authoring skill:
  <out>             candidate data products grouped by domain — for each, the
                    location and infra-profile service URL of its input and
                    output sources, the infra profile name, and the domain.
  <out>-models.md   the input and output model schemas of each candidate.

Usage:
    match_assets.py <inventory.json> [<inventory.json> ...] [--out FILE]
"""
import re, argparse

from meshlib.matching import match
from meshlib.report import write_report, write_models
from drivers import default_registry


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inventories", nargs="+")
    ap.add_argument("--out", default="mesh-assets-report.md",
                    help="markdown report path (default: mesh-assets-report.md)")
    ap.add_argument("--flow", action="append", default=[], metavar="SRC:DST",
                    help="restrict matching to a declared service flow "
                         "(input-service:output-service); repeatable. Derive "
                         "these from the customer's data-architecture docs.")
    args = ap.parse_args()

    flows = []
    for f in args.flow:
        if ":" not in f:
            ap.error(f"--flow must be SRC:DST, got '{f}'")
        src, dst = f.split(":", 1)
        flows.append((src.strip(), dst.strip()))

    result = match(args.inventories, default_registry(), flows)

    models_out = re.sub(r"\.md$", "", args.out) + "-models.md"
    write_report(args.out, args.inventories, result["services"],
                 result["assets"], result["candidates"], result["n_excluded"],
                 result["replica_groups"], result["flows"])
    write_models(models_out, result["candidates"])

    flow_note = (f", flows: {len(result['flows'])}" if result["flows"]
                 else ", flows: none (all pairs)")
    print(f"{len(result['assets'])} assets ({result['n_excluded']} excluded by rules), "
          f"{len(result['candidates'])} candidate data product(s), "
          f"{len(result['replica_groups'])} replicated dataset(s){flow_note}")
    print(f"report : {args.out}")
    print(f"models : {models_out}")


if __name__ == "__main__":
    main()
