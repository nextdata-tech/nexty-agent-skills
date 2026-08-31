"""Command-line lifecycle for one YAML-configured mock source.

The CLI prints a single JSON readiness record only after the server's own HTTP
probes have succeeded on both sockets.  It then stays alive until interrupted,
leaving the selected ports available to a scenario runner.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import signal
from dataclasses import replace
from pathlib import Path
from typing import Sequence

from .config import load_config
from .server import MockRestServer


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a configurable HTTP mock source")
    parser.add_argument("scenario", type=Path, help="scenario YAML file")
    parser.add_argument("--data-port", type=int, default=None)
    parser.add_argument("--control-port", type=int, default=None)
    parser.add_argument("--control-secret", default=None)
    return parser


async def _run(args: argparse.Namespace) -> None:
    config = load_config(args.scenario)
    if args.data_port is not None or args.control_port is not None:
        config = replace(
            config,
            data_port=config.data_port if args.data_port is None else args.data_port,
            control_port=config.control_port if args.control_port is None else args.control_port,
        )
    server = MockRestServer(config, control_secret=args.control_secret)
    await server.start()
    print(
        json.dumps(
            {
                "data_url": server.data_url,
                "data_port": server.data_port,
                "control_url": server.control_url,
                "control_port": server.control_port,
                "control_secret": server.control_secret,
            },
            sort_keys=True,
        ),
        flush=True,
    )
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signum, stopped.set)
        except (NotImplementedError, RuntimeError):
            pass
    try:
        await stopped.wait()
    finally:
        await server.stop()


def main(argv: Sequence[str] | None = None) -> int:
    """Run the mock source until SIGINT or SIGTERM."""

    args = _parser().parse_args(argv)
    asyncio.run(_run(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
