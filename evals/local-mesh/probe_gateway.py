#!/usr/bin/env python3
"""Wait for this eval's semantic tools to appear on the local mesh gateway."""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EVALS = ROOT / "evals"
SCENARIO = EVALS / "public" / "semantic-filter-coverage"
if str(EVALS) not in sys.path:
    sys.path.insert(0, str(EVALS))

import run  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()
    token = os.environ.get("EVAL_MESH_TOKEN", "").strip()
    if not token:
        print("EVAL_MESH_TOKEN is required for authenticated gateway discovery.", file=sys.stderr)
        return 2
    spec = run.scenario_needs_mesh(SCENARIO)
    if spec is None:
        print("semantic-filter-coverage is missing fixtures/mesh.json", file=sys.stderr)
        return 2

    deadline = time.monotonic() + max(args.timeout, 0)
    last_error = "gateway did not return the required tools"
    while True:
        try:
            tools = run.list_local_mesh_tools(spec, token)
            run._check_local_mesh_tools(spec, tools)
            print(f"Ready: all four semantic tools for {spec['dp']} are listed on the local mesh gateway.")
            return 0
        except run.LocalMeshSetupError as exc:
            last_error = str(exc)
        if time.monotonic() >= deadline:
            print(f"Timed out waiting for semantic tools: {last_error}", file=sys.stderr)
            return 1
        time.sleep(min(5, max(deadline - time.monotonic(), 0)))


if __name__ == "__main__":
    raise SystemExit(main())
