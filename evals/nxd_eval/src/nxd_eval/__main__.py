"""``python -m nxd_eval`` → the report/certify CLI.

The project is ``package = false`` (an isolated venv, not a distributable), so a
console-script shim is not installed; the module entry point is the supported way
to reach the CLI:

    uv run --project evals/nxd_eval python -m nxd_eval certify \
        --log ./logs/<run>.eval --gate 'accuracy>=0.90'
"""

from __future__ import annotations

from .certify import main

if __name__ == "__main__":
    raise SystemExit(main())
