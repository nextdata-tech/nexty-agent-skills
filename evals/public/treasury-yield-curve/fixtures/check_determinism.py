"""Rerun check: building the same closure twice must land the same rows.

NOTE FOR MAINTAINERS — this file is copied into the agent's workspace. The
harness requires a scenario's checker under `fixtures/`, and the copy loop
excludes only dotfiles, `__pycache__`, and the runner-side name lists. So do
NOT enumerate here the specific defects a rubric grades: an agent that reads
this file would be handed the answer to the checks that grade them, the same
way the trap catalogue in PROVENANCE.md is kept at scenario level for being
agent-visible under `fixtures/`. Describe the MECHANISM, not the failures.

SCOPE. This compares two back-to-back builds of one closure, so it assumes a
stable source. A closure reading a live upstream that legitimately changed
between the two builds is not defective, and this checker cannot tell that
case apart from a genuine one — scenarios whose source moves should not attach
it until the harness can pin a source snapshot across both builds.

WHY THIS COMPARES ROWS AND NOT FILES. The obvious implementation — hash the
artifact directory after each build and compare — fails on every honest
closure. dlt stamps two non-deterministic columns onto every user table:

  * `_dlt_load_id` — the load's wall-clock timestamp, e.g. `1785149914.043455`
  * `_dlt_id`      — a random per-row surrogate key

and it ACCUMULATES load history rather than replacing it, so a second build
adds a whole load package whose directory name is itself a wall-clock
timestamp. The path set, not merely file contents, differs between two correct
builds. A file-digest gate would therefore fail 100% of the time while telling
you nothing about the transform.

So the comparison is logical: user tables only, user columns only, ordered
deterministically, hashed. That isolates exactly what the closure controls.

The table/column SET is asserted separately from the row hash. An empty table
hashes stably, so a table or column that silently vanished on the second build
would slip past a row-content comparison on its own.

Run against two data dirs produced by building the SAME closure twice:

    python check_determinism.py --fixtures <fixtures> --root <closure-root>

`--root` is the closure the harness landed. The two builds are performed by
this checker, not by the agent — an agent-run determinism check could pass by
simply not rebuilding.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import duckdb

# dlt's bookkeeping surface. Both the column prefix and these whole tables are
# load-scoped: they legitimately differ between two correct builds.
DLT_COLUMN_PREFIX = "_dlt"
DLT_TABLES = {"_dlt_loads", "_dlt_pipeline_state", "_dlt_version"}

# A build boots a kernel child, runs the transform, and publishes. The
# supervisor's own staging wait is 170s, so this must exceed it or a slow
# machine reports a determinism failure that is really a timeout.
#
# The ceiling is the harness's, not ours: run.py caps the WHOLE checker
# invocation at DETERMINISTIC_CHECK_TIMEOUT_S = 600s, and that budget covers
# two builds plus uv's dependency resolution. A per-build budget of 600s is
# therefore unreachable — two honest 320s builds would trip the outer cap and
# be recorded as an infrastructure_error, failing the cell without producing a
# verdict rather than reporting a determinism result.
#
# Budget, worst reachable case: build 1 finishing near its cap, build 2 timing
# out AT the cap, then one `supervisor stop` per data dir, and uv's dependency
# resolution on top of all of it. 2*200 + 2*30 = 460s leaves ~140s for uv and
# process teardown inside the harness's 600s, while still clearing the
# supervisor's own 170s staging wait with room to spare.
BUILD_TIMEOUT_S = 200

# Per-data-dir stop in the finally block. Charged against the same outer cap,
# so it cannot be generous.
STOP_TIMEOUT_S = 30

PASSES: list[str] = []
FAILURES: list[tuple[str, str]] = []


def ok(name: str) -> None:
    PASSES.append(name)


def bad(name: str, detail: str) -> None:
    FAILURES.append((name, detail))


def pocket_python() -> Path | None:
    """The provisioned venv interpreter that has nxd importable.

    EVAL_POCKET_PYTHON is what the harness sets; the desktop setup script
    provisions the same interpreter at ~/.nxd/desktop-venv. Either is fine —
    what matters is that it is NOT a bare python3.
    """
    env_python = os.environ.get("EVAL_POCKET_PYTHON", "").strip()
    if env_python and Path(env_python).is_file():
        return Path(env_python)
    fallback = Path.home() / ".nxd" / "desktop-venv" / "bin" / "python"
    return fallback if fallback.is_file() else None


def supervisor_binary() -> Path | None:
    """Locate the desktop supervisor the same way the harness does."""
    env_dir = os.environ.get("EVAL_POCKET_SUPERVISOR_DIR", "").strip()
    if env_dir:
        candidate = Path(env_dir).expanduser() / "nxd-desktop-supervisor"
        if candidate.is_file():
            return candidate
    found = shutil.which("nxd-desktop-supervisor")
    return Path(found) if found else None


def build_env() -> dict[str, str]:
    """Environment for every supervisor call this checker makes.

    The kernel runs the transform with NXD_DESKTOP_PYTHON, falling back to a
    bare python3 that has no nxd installed — the transform then dies with
    ModuleNotFoundError after the full staging timeout. Pin it to the
    provisioned venv the harness already located, so this checker does not
    depend on the variable happening to be exported into its own environment.
    """
    env = dict(os.environ)
    if not env.get("NXD_DESKTOP_PYTHON"):
        venv_python = pocket_python()
        if venv_python is not None:
            env["NXD_DESKTOP_PYTHON"] = str(venv_python)
    return env


def build_once(supervisor: Path, closure: Path, data_dir: Path, workflow: str) -> str | None:
    """Build the closure into a fresh data dir. Return an error string, or None.

    `--definition` MUST be absolute. A relative path publishes fine and then
    dies ~170s later inside the kernel with `can't open file 'main.py'`,
    because the transform path is resolved against a different root.
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(supervisor), "create",
        "--data-dir", str(data_dir.resolve()),
        "--definition", str(closure.resolve()),
        "--workflow", workflow,
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=BUILD_TIMEOUT_S,
            env=build_env(),
        )
    except subprocess.TimeoutExpired:
        return f"build timed out after {BUILD_TIMEOUT_S}s"
    except OSError as exc:
        return f"build failed to start: {exc}"
    if proc.returncode != 0:
        detail = (proc.stderr.strip() or proc.stdout.strip() or "(no output)")
        return f"build exited {proc.returncode}: {detail[-1500:]}"
    if "published=yes" not in proc.stdout:
        return f"build did not publish: {proc.stdout.strip()[-1500:]}"
    return None


def landed_database(data_dir: Path) -> Path | None:
    """The published generation's duckdb file, if exactly one was produced."""
    candidates = sorted((data_dir / "generations").glob("*/data.duckdb"))
    if len(candidates) != 1:
        return None
    return candidates[0]


def user_tables(con: duckdb.DuckDBPyConnection) -> list[str]:
    rows = con.execute(
        "select table_name from information_schema.tables "
        "where table_schema not in ('information_schema', 'pg_catalog') "
        "order by table_name"
    ).fetchall()
    return [
        r[0] for r in rows
        if r[0] not in DLT_TABLES and not r[0].startswith(DLT_COLUMN_PREFIX)
    ]


def user_columns(con: duckdb.DuckDBPyConnection, table: str) -> list[str]:
    rows = con.execute(f'pragma table_info("{table}")').fetchall()
    return [r[1] for r in rows if not r[1].startswith(DLT_COLUMN_PREFIX)]


def table_fingerprint(con: duckdb.DuckDBPyConnection, table: str, cols: list[str]) -> str:
    """Hash a table's user data, ordered so insert order cannot affect it."""
    if not cols:
        return "sha256:no-user-columns"
    projection = ", ".join(f'"{c}"' for c in cols)
    rows = con.execute(f'select {projection} from "{table}" order by all').fetchall()
    digest = hashlib.sha256()
    for row in rows:
        # repr of a tuple is stable for the scalar types duckdb returns here
        # and keeps None distinguishable from the empty string.
        digest.update(repr(row).encode("utf-8"))
        digest.update(b"\x1e")
    return f"sha256:{digest.hexdigest()}"


def profile(db: Path) -> dict[str, tuple[list[str], str, int]]:
    """Map table -> (user columns, row fingerprint, row count)."""
    con = duckdb.connect(str(db), read_only=True)
    try:
        out = {}
        for table in user_tables(con):
            cols = user_columns(con, table)
            count = con.execute(f'select count(*) from "{table}"').fetchone()[0]
            out[table] = (cols, table_fingerprint(con, table, cols), count)
        return out
    finally:
        con.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixtures", required=True, type=Path)
    ap.add_argument("--root", default=Path("."), type=Path)
    args = ap.parse_args()

    closure = args.root.resolve()
    if not (closure / "transform").is_dir():
        # The agent may have landed the closure in a subdirectory.
        nested = [p.parent for p in closure.glob("*/transform") if p.is_dir()]
        if len(nested) == 1:
            closure = nested[0]

    supervisor = supervisor_binary()
    if supervisor is None:
        print("FAIL determinism-harness")
        print("  no nxd-desktop-supervisor found "
              "(set EVAL_POCKET_SUPERVISOR_DIR or put it on PATH)")
        return 1

    work = Path(tempfile.mkdtemp(prefix="nxd-determinism-"))
    try:
        profiles = []
        for index in (1, 2):
            data_dir = work / f"build{index}"
            error = build_once(supervisor, closure, data_dir, "determinism-probe")
            if error:
                bad(f"build-{index}", error)
                break
            db = landed_database(data_dir)
            if db is None:
                bad(f"build-{index}", "expected exactly one landed generation database")
                break
            ok(f"build-{index}")
            profiles.append(profile(db))

        if len(profiles) == 2:
            first, second = profiles

            if set(first) != set(second):
                only_first = sorted(set(first) - set(second))
                only_second = sorted(set(second) - set(first))
                bad("table-set-stable",
                    f"tables only in build 1: {only_first}; only in build 2: {only_second}")
            else:
                ok("table-set-stable")

                for table in sorted(first):
                    cols_a, hash_a, count_a = first[table]
                    cols_b, hash_b, count_b = second[table]
                    if cols_a != cols_b:
                        bad(f"columns-stable[{table}]",
                            f"build 1 {cols_a} vs build 2 {cols_b}")
                        continue
                    if hash_a != hash_b:
                        # Deliberately does NOT enumerate the defect classes a
                        # rubric grades — see the header rule. This file lands
                        # in the agent's workspace, and a list of causes here
                        # is an answer key for the checks that grade them.
                        bad(f"rows-identical[{table}]",
                            f"{count_a} rows vs {count_b} rows; "
                            f"{hash_a} != {hash_b}. Two builds of the same "
                            f"closure landed different data in this table. "
                            f"(If the closure reads a source that can change "
                            f"between builds, this check does not belong on "
                            f"that scenario — see the SCOPE note above.)")
                        continue
                    ok(f"rows-identical[{table}]")

                if not first:
                    bad("landed-any-user-table",
                        "no user tables landed; a determinism pass over an "
                        "empty database proves nothing")
    finally:
        # Stop each build's runtime BEFORE removing its data dir. `create` can
        # report published=yes while a kernel-host child is still attached, and
        # a child that outlives the tree would keep writing into build1/ or
        # build2/ after they are gone — surfacing later as a bogus row-hash
        # mismatch rather than as the process leak it is. run.py takes the same
        # precaution around its own preflight.
        for index in (1, 2):
            data_dir = work / f"build{index}"
            if not data_dir.exists():
                continue
            try:
                subprocess.run(
                    [str(supervisor), "stop", "--data-dir", str(data_dir.resolve())],
                    capture_output=True, text=True, timeout=STOP_TIMEOUT_S,
                    env=build_env(),
                )
            except (OSError, subprocess.TimeoutExpired):
                pass
        shutil.rmtree(work, ignore_errors=True)

    for name in PASSES:
        print(f"PASS {name}")
    for name, detail in FAILURES:
        print(f"FAIL {name}")
        print(f"  {detail}")
    print()
    print(f"{len(PASSES)} passed, {len(FAILURES)} failed")
    if not FAILURES:
        print("ALL CHECKS PASSED")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
