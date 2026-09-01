"""Stdlib-only semantic-child shim used for deterministic broker faults.

The NXD supervisor supplies ``--port`` to its configured semantic entrypoint.
The shim either holds that port across ``exec`` or remains alive past the
declared bind timeout, then delegates to the real child.  It is deliberately a
process seam: no supervisor module is imported or monkeypatched here.
"""

from __future__ import annotations

import os
import socket
import sys
import time


def _value(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _port(argv: list[str]) -> int:
    try:
        return int(argv[argv.index("--port") + 1])
    except (ValueError, IndexError) as exc:
        raise SystemExit(2) from exc


def _quiet_stderr() -> None:
    """Make the occupied-port shape intentionally diagnostic-free."""

    with open(os.devnull, "wb", closefd=True) as sink:
        os.dup2(sink.fileno(), 2)


def main() -> None:
    real_entrypoint = _value("NXD_EVAL_BROKER_REAL_ENTRYPOINT")
    if not real_entrypoint:
        raise SystemExit(2)
    fault = _value("NXD_EVAL_BROKER_FAULT", "none")
    argv = sys.argv[1:]
    if fault == "sleep_past_bind_timeout":
        seconds = int(_value("NXD_EVAL_BROKER_BIND_TIMEOUT_S", "30")) + int(
            _value("NXD_EVAL_BROKER_MARGIN_S", "1")
        )
        time.sleep(seconds)
    elif fault == "occupied_port":
        _quiet_stderr()
        holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        holder.set_inheritable(True)
        try:
            holder.bind(("127.0.0.1", _port(argv)))
            holder.listen(1)
        except OSError:
            holder.close()
            raise SystemExit(2)
    elif fault != "none":
        raise SystemExit(2)
    os.execv(sys.executable, [sys.executable, real_entrypoint, *argv])


if __name__ == "__main__":
    main()
