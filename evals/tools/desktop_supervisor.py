"""Talking to the local desktop supervisor from a runner-side verifier.

The publish → resume → describe → query surface, factored out of what
`job-loop-serve-query-refine`'s `check_job_loop.py` does inline. That file and
its `job-loop-export-handoff` twin already carry two near-identical copies of
this plumbing; this module exists so the third scenario to need it does not
create a third. Those two predate it and can migrate — deliberately not done
here, since rewriting two working verifiers is a larger change than the one
that needed this.

Nothing here trusts a transcript. Every fact comes from the supervisor's own
state database or from an authenticated call against an endpoint this module
started itself.
"""

from __future__ import annotations

import contextlib
import json
import os
import secrets
import shutil
import signal
import sqlite3
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SERVE_TIMEOUT_S = 240
SEMANTIC_READY_TIMEOUT_S = 60


class CheckFailure(RuntimeError):
    """A verifiable claim about the supervisor did not hold."""


def command(args: list[str], *, cwd: Path | None = None, timeout: int = 90,
            env: dict[str, str] | None = None) -> str:
    proc = subprocess.run(args, cwd=cwd, text=True, capture_output=True,
                          timeout=timeout, env=env)
    if proc.returncode:
        raise CheckFailure(
            f"command failed ({proc.returncode}): {' '.join(args)}\n{proc.stderr[-1000:]}")
    return proc.stdout.strip()


def supervisor() -> str:
    exe = shutil.which("nxd-desktop-supervisor")
    if not exe:
        raise CheckFailure("nxd-desktop-supervisor is not on PATH")
    return exe


def kv(text: str) -> dict[str, str]:
    """The supervisor's `key = value` line output, as a dict."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            out[key.strip()] = value.strip()
    return out


# ---------------------------------------------------------------------------
# State database — what the supervisor durably recorded
# ---------------------------------------------------------------------------


def state_database(data_dir: Path) -> Path:
    for name in ("state.sqlite3", "state.sqlite"):
        candidate = data_dir / name
        if candidate.exists():
            return candidate
    raise CheckFailure(f"missing supervisor state database under {data_dir}")


def find_data_dir(workspace: Path) -> Path:
    """The supervisor data dir the agent actually used.

    Located by SEARCH rather than assumed at `.desktop/state`: the prompt names
    that path, but a closure authored a directory deeper puts it somewhere else
    and a hardcoded path would report a published product as never published.
    Shallowest wins, so a scratch copy cannot outrank the real one.
    """
    found = sorted(
        (db.parent for db in workspace.rglob("state.sqlite*")
         if db.name in {"state.sqlite", "state.sqlite3"}),
        key=lambda p: (len(p.relative_to(workspace).parts), str(p)),
    )
    if not found:
        raise CheckFailure(
            f"no supervisor state database anywhere under {workspace} — nothing "
            f"was ever served")
    return found[0]


def published_runs(data_dir: Path, workflow: str) -> list[dict[str, Any]]:
    """Every Published run for one workflow, oldest first."""
    con = sqlite3.connect(state_database(data_dir))
    try:
        columns = [str(row[1]) for row in con.execute("PRAGMA table_info(runs)")]
        required = {"run_id", "workflow_id", "artifact_id", "definition_id", "status"}
        if not required <= set(columns):
            raise CheckFailure(
                f"runs table missing required columns: {sorted(required - set(columns))}")
        selected = ["rowid", "run_id", "workflow_id", "artifact_id",
                    "definition_id", "status"]
        quoted = ", ".join('"' + c.replace('"', '""') + '"' for c in selected)
        rows = con.execute(
            f"SELECT {quoted} FROM runs WHERE workflow_id = ? AND status = 'Published' "
            f"ORDER BY rowid",
            (workflow,),
        ).fetchall()
    finally:
        con.close()
    return [dict(zip(selected, row)) for row in rows if row[4]]


def definition_snapshot(data_dir: Path, definition_id: str) -> Path:
    snapshot = data_dir / "definitions" / definition_id
    if not snapshot.is_dir():
        raise CheckFailure(f"published definition is missing: {snapshot}")
    if not any(p.is_file() for p in snapshot.rglob("*")):
        raise CheckFailure(f"published definition is empty: {snapshot}")
    return snapshot


# ---------------------------------------------------------------------------
# Re-serving a published snapshot — the resume path
# ---------------------------------------------------------------------------


@dataclass
class Served:
    holder: tempfile.TemporaryDirectory
    data_dir: Path
    endpoint: str
    bearer: str
    process: subprocess.Popen
    stdout: Any
    stderr: Any


def serve_snapshot(snapshot: Path, workflow: str) -> Served:
    """Re-serve one immutable published snapshot in the foreground.

    This is the resume path a user takes in a fresh session: the durable key is
    the definition plus the workflow id, never a remembered endpoint. It also
    RE-MATERIALIZES — for an api-source closure that means re-fetching from the
    upstream, which is why the runner keeps the HTTP fixture alive across the
    verifier (see `http_stub_server` in run.py).
    """
    temp_root = os.environ.get("NXD_JOB_CHECK_TMPDIR", "").strip()
    if temp_root:
        Path(temp_root).mkdir(parents=True, exist_ok=True)
        holder = tempfile.TemporaryDirectory(prefix=f"desktop-{workflow}-", dir=temp_root)
    else:
        holder = tempfile.TemporaryDirectory(prefix=f"desktop-{workflow}-")
    data_dir = Path(holder.name) / "state"
    bearer = f"desktop-check-{secrets.token_urlsafe(24)}"
    env = {**os.environ, "NXD_DESKTOP_BEARER": bearer}
    stdout = tempfile.TemporaryFile(mode="w+", encoding="utf-8")
    stderr = tempfile.TemporaryFile(mode="w+", encoding="utf-8")
    process: subprocess.Popen | None = None
    try:
        process = subprocess.Popen(
            [supervisor(), "serve", "--definition", str(snapshot),
             "--workflow", workflow, "--data-dir", str(data_dir)],
            stdout=stdout, stderr=stderr, text=True, env=env, start_new_session=True,
        )
        deadline = time.time() + SERVE_TIMEOUT_S
        while time.time() < deadline:
            stdout.seek(0)
            values = kv(stdout.read().strip())
            if values.get("published") == "yes":
                endpoint = values.get("semantic_endpoint", "")
                if not endpoint:
                    raise CheckFailure(f"serve omitted the endpoint: {values}")
                # Publication is emitted before the semantic child has always
                # bound its socket. Wait for an authenticated catalog rather
                # than turning that startup race into a wrong answer.
                ready_by = min(deadline, time.time() + SEMANTIC_READY_TIMEOUT_S)
                while time.time() < ready_by:
                    try:
                        describe(endpoint, bearer)
                        return Served(holder, data_dir, endpoint, bearer,
                                      process, stdout, stderr)
                    except CheckFailure:
                        if process.poll() is not None:
                            raise CheckFailure(
                                "serve exited before semantic readiness "
                                f"({process.returncode})") from None
                        time.sleep(0.25)
                raise CheckFailure(f"semantic endpoint never became ready: {endpoint}")
            if process.poll() is not None:
                stderr.seek(0)
                raise CheckFailure(
                    f"serve exited before publication ({process.returncode}): "
                    f"{stderr.read()[-1000:]}")
            time.sleep(0.1)
        stdout.seek(0)
        stderr.seek(0)
        raise CheckFailure(
            f"serve did not publish within {SERVE_TIMEOUT_S}s: "
            f"stdout={stdout.read()[-500:]} stderr={stderr.read()[-500:]}")
    except BaseException:
        if process is not None and process.poll() is None:
            _reap(process)
        holder.cleanup()
        raise


def _reap(process: subprocess.Popen) -> None:
    """Kill the serve process GROUP: it spawns a semantic child of its own.

    A plain `process.kill()` leaves that child holding the port, and the next
    serve in the same run fails to bind — reported as a broken closure.
    """
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
    except (OSError, ProcessLookupError):
        return
    try:
        process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(OSError, ProcessLookupError):
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)


def stop_served(served: Served) -> None:
    try:
        with contextlib.suppress(CheckFailure, OSError, subprocess.TimeoutExpired):
            command([supervisor(), "stop", "--data-dir", str(served.data_dir)],
                    timeout=60)
    finally:
        if served.process.poll() is None:
            _reap(served.process)
        served.stdout.close()
        served.stderr.close()
        served.holder.cleanup()


# ---------------------------------------------------------------------------
# The governed surface
# ---------------------------------------------------------------------------


def describe(endpoint: str, bearer: str) -> dict[str, Any]:
    raw = command([supervisor(), "describe", "--endpoint", endpoint, "--token", bearer])
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CheckFailure(f"describe was not one JSON object: {raw[:300]!r}") from exc
    if not isinstance(parsed.get("models"), list):
        raise CheckFailure(f"describe lacks models: {parsed}")
    return parsed


def query(endpoint: str, bearer: str, selection: dict[str, Any],
          scratch: Path) -> dict[str, Any]:
    selection_file = scratch / "selection.json"
    selection_file.write_text(json.dumps(selection), encoding="utf-8")
    raw = command([supervisor(), "query", "--endpoint", endpoint, "--token", bearer,
                   "--selection", str(selection_file)])
    lines = [line for line in raw.splitlines() if line.strip()]
    if len(lines) != 1:
        raise CheckFailure(
            f"query must emit exactly one JSON line, got {len(lines)}: {raw[:300]!r}")
    try:
        result = json.loads(lines[0])
    except json.JSONDecodeError as exc:
        raise CheckFailure(f"query result is not JSON: {lines[0][:300]!r}") from exc
    if result.get("error"):
        raise CheckFailure(f"query error: {result.get('error')!r}")
    rows, columns = result.get("rows"), result.get("columns")
    if not isinstance(rows, list) or not isinstance(columns, list):
        raise CheckFailure(f"query has invalid rows/columns: {result}")
    if result.get("truncated") is True:
        raise CheckFailure("the answer was truncated")
    return result


def catalog_entries(described: dict[str, Any]) -> tuple[list[str], list[str]]:
    """(measure names, dimension names) across every described model."""
    measures: list[str] = []
    dimensions: list[str] = []
    for model in described.get("models", []):
        for metric in model.get("metrics", []) or []:
            if isinstance(metric, dict) and isinstance(metric.get("name"), str):
                measures.append(metric["name"])
        for dimension in model.get("dimensions", []) or []:
            if isinstance(dimension, dict) and isinstance(dimension.get("name"), str):
                dimensions.append(dimension["name"])
    return measures, dimensions
