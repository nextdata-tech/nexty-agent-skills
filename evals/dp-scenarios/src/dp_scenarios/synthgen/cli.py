"""Command-line entry point for deterministic scenario fixture generation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .datasets import DATASET_DEFINITIONS
from .generator import VerificationError, generate_dataset, verify_dataset


def build_parser() -> argparse.ArgumentParser:
    """Build the stable CLI parser used by the harness and shell callers."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", nargs="?")
    parser.add_argument("--dataset", dest="dataset_flag", choices=sorted(DATASET_DEFINITIONS))
    parser.add_argument("--seed", type=int)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--mode", choices=("generate", "verify", "mutate"), default=None)
    parser.add_argument("--verify", action="store_true", help="verify an existing fixture")
    parser.add_argument(
        "--allow-mutation",
        action="store_true",
        help="allow verification of a fixture deliberately generated in mutation mode",
    )
    parser.add_argument("--mutate", action="store_true", help="generate a deliberate PII leak")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Generate a fixture and print a compact machine-readable summary."""

    args = build_parser().parse_args(argv)
    positional_mode = args.dataset if args.dataset in {"generate", "verify", "mutate"} else None
    dataset = None if positional_mode else (args.dataset or args.dataset_flag)
    mode = args.mode or positional_mode or ("verify" if args.verify else "mutate" if args.mutate else "generate")
    if sum(bool(flag) for flag in (args.mode, args.verify, args.mutate, positional_mode)) > 1:
        raise SystemExit("choose one CLI mode")
    if args.dataset and not positional_mode and args.dataset_flag and args.dataset != args.dataset_flag:
        raise SystemExit("positional dataset and --dataset must match")
    if mode == "verify":
        try:
            verify_dataset(
                args.out_dir,
                dataset=dataset,
                seed=args.seed,
                allow_mutation=args.allow_mutation,
            )
        except VerificationError as exc:
            print(json.dumps({"verified": False, "error": str(exc)}, sort_keys=True))
            return 1
        print(json.dumps({"verified": True, "out_dir": str(args.out_dir)}, sort_keys=True))
        return 0
    if dataset is None:
        raise SystemExit("a dataset name is required")
    if args.seed is None:
        raise SystemExit("--seed is required for generation")
    if dataset not in DATASET_DEFINITIONS:
        raise SystemExit(f"unknown dataset {dataset!r}")
    result = generate_dataset(dataset, args.seed, args.out_dir, mutation=mode == "mutate")
    print(
        json.dumps(
            {
                "dataset": result.dataset,
                "seed": result.seed,
                "out_dir": str(result.out_dir),
                "manifest": str(result.manifest_path),
                "mode": mode,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised by the CLI command
    raise SystemExit(main())
