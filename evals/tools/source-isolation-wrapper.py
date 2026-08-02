#!/usr/bin/env python3
"""Default-deny source-isolation wrapper for the nxd eval harness.

Two modes, both required by ``evals/run.py``:

1. ``--eval-source-isolation-probe -- <command...>``
   Run the command under the deny policy and report whether it was BLOCKED.
   Emits one JSON object as the last stdout line: ``{"passed": true,
   "status": "blocked"}``. If the command SUCCEEDS, the source was reachable
   and the probe reports ``passed: false`` — the harness then aborts the run
   as infrastructure-invalid, which is the whole point.

2. anything else (the real agent invocation)
   Exec the command under the same deny policy, passing stdin/stdout through
   untouched so the harness can audit the raw stream.

Enforcement is macOS ``sandbox-exec`` (Seatbelt), not an env var or a PATH
trick: the harness's guarantee is that the agent COULD NOT read the protected
roots, and only kernel-level denial supports that claim. The policy denies
read access to each configured root and allows everything else, so the agent
still runs normally inside its workspace.

Note what is NOT protected: this wrapper's own file and the root mapping in
``EVAL_SOURCE_ISOLATION_ROOTS`` stay readable, so an agent could in principle
enumerate the protected paths. That is deliberate — knowing a path exists is
not the same as reading what is under it, and the harness pins the wrapper by
sha256 so tampering shows up in the attestation. Protect the wrapper itself
only if a scenario's threat model needs it.

Protected roots come from EVAL_SOURCE_ISOLATION_ROOTS (JSON object of
name -> absolute path), the same variable run.py reads, so the wrapper and the
harness cannot disagree about what is protected.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys


def _roots() -> list[str]:
    raw = os.environ.get("EVAL_SOURCE_ISOLATION_ROOTS", "")
    if not raw:
        return []
    try:
        mapping = json.loads(raw)
    except json.JSONDecodeError:
        return []
    out = []
    for value in mapping.values():
        p = os.path.realpath(str(value))
        if p and p != "/":
            out.append(p)
    return sorted(set(out))


def _profile(roots: list[str]) -> str:
    """Seatbelt policy: allow by default, deny reads under each protected root.

    `subpath` covers the root itself and everything beneath it. Denials are
    listed AFTER the blanket allow because Seatbelt takes the last matching
    rule.
    """
    lines = ["(version 1)", "(allow default)"]
    for r in roots:
        escaped = r.replace('"', '\\"')
        lines.append(f'(deny file-read* (subpath "{escaped}"))')
    return "\n".join(lines) + "\n"


TOOL = "codex"


def _sandboxed(command: list[str], roots: list[str]) -> list[str]:
    """Wrap a command in the deny policy.

    The harness substitutes this wrapper for argv[0] and passes only the
    REMAINING arguments, so an agent invocation arrives as
    ``["exec", "--json", …]`` with no binary in it at all. Anything whose
    first element is not an absolute path is therefore a codex subcommand and
    needs the real binary prepended; a probe passes a full path already.
    """
    sandbox = shutil.which("sandbox-exec") or "/usr/bin/sandbox-exec"
    argv = list(command)
    if argv and not argv[0].startswith("/"):
        argv = [_real_binary(TOOL), *argv]
    elif argv:
        argv[0] = _real_binary(argv[0])
    return [sandbox, "-p", _profile(roots), *argv]


def _real_binary(name: str) -> str:
    """Resolve to an executable that runs WITHOUT a version-manager shim.

    An asdf shim is `exec asdf exec "<tool>" "$@"`, which needs `asdf` itself
    on PATH at exec time. Inside the sandbox that lookup fails and bash reports
    `execvp() of 'exec' failed`, which reads like a wrapper bug but is really
    the shim failing to re-dispatch. Ask asdf for the real path up front.
    """
    found = shutil.which(name) or name
    try:
        with open(found, "rb") as fh:
            head = fh.read(256)
    except OSError:
        return found
    if b"asdf" not in head:
        return found
    try:
        out = subprocess.run(["asdf", "which", name],
                             capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return found
    real = out.stdout.strip()
    return real if out.returncode == 0 and real else found


def _probe(command: list[str], roots: list[str]) -> int:
    """A probe PASSES when the command is denied."""
    if not command:
        print(json.dumps({"passed": False, "status": "no-command"}))
        return 1
    try:
        proc = subprocess.run(
            _sandboxed(command, roots),
            capture_output=True, text=True, timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        # Could not even launch the sandbox: report unblocked rather than
        # claiming a denial we did not observe.
        print(json.dumps({"passed": False, "status": "probe-error"}))
        return 1
    blocked = proc.returncode != 0
    print(json.dumps({
        "passed": bool(blocked),
        "status": "blocked" if blocked else "reachable",
    }))
    return 0 if blocked else 1


def main(argv: list[str]) -> int:
    roots = _roots()
    if not roots:
        print(json.dumps({"passed": False, "status": "no-roots-configured"}))
        return 1
    if argv and argv[0] == "--eval-source-isolation-probe":
        rest = argv[1:]
        if rest and rest[0] == "--":
            rest = rest[1:]
        return _probe(rest, roots)
    if not argv:
        return 1
    # Real agent run: stream through, no capture, so the harness audits raw output.
    return subprocess.run(_sandboxed(argv, roots)).returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
