#!/usr/bin/env python3
"""Render one epoch evidence bundle as a readable conversation.

    python scripts/render_conversation.py evidence/<scenario>/epoch-1
    python scripts/render_conversation.py evidence/<scenario>/epoch-1 \
        --report report.json --verbose --out conversation.txt

The report is the *tier-level* ``report.json`` (a sibling of ``evidence/``, not
a per-epoch file); the renderer looks up the matching scenario/epoch entry
inside it.  It is optional: without one the conversation still renders, with the
verdict and gate sections marked unavailable.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:  # allow running the script without installing
    sys.path.insert(0, str(_SRC))

from dp_scenarios.runner.transcript import render_epoch_conversation  # noqa: E402


def _default_report(bundle: Path) -> Path | None:
    """Guess the tier report: ``<run>/report.json`` next to ``evidence/``.

    A guess, never a requirement — if it is not there the rendering says so.
    """

    candidate = bundle.parent.parent.parent / "report.json"
    return candidate if candidate.is_file() else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("bundle", type=Path, help="evidence/<scenario>/epoch-<n> directory")
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="tier-level report.json (default: auto-detected next to evidence/, if present)",
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="do not look for a report at all",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="include tool-call arguments and results (elided by default)",
    )
    parser.add_argument("--out", type=Path, default=None, help="write to this file instead of stdout")
    args = parser.parse_args(argv)

    if not args.bundle.is_dir():
        parser.error(f"{args.bundle} is not a directory")

    report: Path | None = None
    if not args.no_report:
        report = args.report if args.report is not None else _default_report(args.bundle)

    rendered = render_epoch_conversation(args.bundle, report=report, verbose=args.verbose)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
