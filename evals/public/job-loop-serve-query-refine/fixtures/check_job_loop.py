#!/usr/bin/env python3
"""Independent verifier for the local job loop end-to-end eval.

``--mode agent`` is the forcing function an agent runs while its endpoint is
live.  ``--mode harness`` is deliberately run from the pristine scenario copy
after the agent exits: it re-serves immutable snapshots and emits facts for the
judge.  Neither mode trusts a transcript, an answer pasted by the agent, or
the mutable workspace CSVs for its ground truth.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import hashlib
import json
import os
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse


HERE = Path(__file__).resolve().parent
PRISTINE_DATA = HERE / "data"
MAX_ATTEMPTS = 80


@dataclass(frozen=True)
class Question:
    ident: str
    reference_sql: str
    dimension_hint: str | None = None
    filter_hints: tuple[str, ...] = ()
    filters: tuple[tuple[str, str, str], ...] = ()
    ordered: bool = False
    limit: int | None = None


QUESTIONS = (
    Question(
        "spain_q2_total",
        """SELECT round(sum(o.amount_eur), 2) FROM orders o JOIN customers c USING(customer_id)
           WHERE c.billing_country = 'Spain' AND o.order_date >= DATE '2025-04-01'
             AND o.order_date < DATE '2025-07-01'""",
        filter_hints=("country", "date"),
        filters=(("country", "=", "Spain"), ("date", ">=", "2025-04-01"), ("date", "<", "2025-07-01")),
    ),
    Question(
        "q2_amount_by_segment",
        """SELECT c.segment, round(sum(o.amount_eur), 2) FROM orders o JOIN customers c USING(customer_id)
           WHERE o.order_date >= DATE '2025-04-01' AND o.order_date < DATE '2025-07-01'
           GROUP BY c.segment""",
        dimension_hint="segment",
        filter_hints=("date",),
        filters=(("date", ">=", "2025-04-01"), ("date", "<", "2025-07-01")),
    ),
    Question(
        "overdue_by_category",
        """SELECT product_category, sum(CASE WHEN is_overdue THEN 1 ELSE 0 END)::DOUBLE
           FROM orders GROUP BY product_category""",
        dimension_hint="category",
    ),
    Question(
        "top_customers_by_amount",
        """SELECT c.customer_name, round(sum(o.amount_eur), 2) FROM orders o JOIN customers c USING(customer_id)
           GROUP BY c.customer_name ORDER BY 2 DESC LIMIT 3""",
        dimension_hint="customer|name",
        ordered=True,
        limit=3,
    ),
    Question(
        "average_by_segment_q2",
        """SELECT c.segment, round(avg(o.amount_eur), 2) FROM orders o JOIN customers c USING(customer_id)
           WHERE o.order_date >= DATE '2025-04-01' AND o.order_date < DATE '2025-07-01'
           GROUP BY c.segment""",
        dimension_hint="segment",
        filter_hints=("date",),
        filters=(("date", ">=", "2025-04-01"), ("date", "<", "2025-07-01")),
    ),
)


class CheckFailure(RuntimeError):
    pass


def command(args: list[str], *, cwd: Path | None = None, timeout: int = 90,
            env: dict[str, str] | None = None) -> str:
    proc = subprocess.run(args, cwd=cwd, text=True, capture_output=True, timeout=timeout, env=env)
    if proc.returncode:
        raise CheckFailure(f"command failed ({proc.returncode}): {' '.join(args)}\n{proc.stderr[-1000:]}")
    return proc.stdout.strip()


def supervisor() -> str:
    exe = shutil.which("nxd-desktop-supervisor")
    if not exe:
        raise CheckFailure("nxd-desktop-supervisor is not on PATH")
    return exe


def kv(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            out[key.strip()] = value.strip()
    return out


def status(data_dir: Path, workflow: str) -> dict[str, str]:
    values = kv(command([supervisor(), "status", "--data-dir", str(data_dir), "--workflow", workflow]))
    if not values.get("current_artifact") or values["current_artifact"] == "none":
        raise CheckFailure(f"status has no current artifact: {values}")
    if not values.get("pointer") or values["pointer"] == "none":
        raise CheckFailure(f"status has no current pointer: {values}")
    return values


def describe(endpoint: str, bearer: str) -> dict[str, Any]:
    raw = command([supervisor(), "describe", "--endpoint", endpoint, "--token", bearer])
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CheckFailure(f"describe was not one JSON object: {raw[:300]!r}") from exc
    if not isinstance(parsed.get("models"), list):
        raise CheckFailure(f"describe lacks models: {parsed}")
    return parsed


def query(endpoint: str, bearer: str, selection: dict[str, Any], scratch: Path) -> dict[str, Any]:
    selection_file = scratch / "selection.json"
    selection_file.write_text(json.dumps(selection), encoding="utf-8")
    raw = command([supervisor(), "query", "--endpoint", endpoint, "--token", bearer, "--selection", str(selection_file)])
    lines = [line for line in raw.splitlines() if line.strip()]
    if len(lines) != 1:
        raise CheckFailure(f"query must emit exactly one JSON line, got {len(lines)}: {raw[:300]!r}")
    try:
        result = json.loads(lines[0])
    except json.JSONDecodeError as exc:
        raise CheckFailure(f"query result is not JSON: {lines[0][:300]!r}") from exc
    if result.get("error") != "":
        raise CheckFailure(f"query error: {result.get('error')!r}")
    rows = result.get("rows")
    columns = result.get("columns")
    if not isinstance(rows, list) or not isinstance(columns, list):
        raise CheckFailure(f"query has invalid rows/columns: {result}")
    if result.get("row_count") != len(rows):
        raise CheckFailure(f"row_count mismatch: {result.get('row_count')} != {len(rows)}")
    if result.get("truncated") is not False:
        raise CheckFailure("required answer was truncated")
    if len(columns) != (len(rows[0]) if rows else len(columns)):
        raise CheckFailure("column count does not match returned rows")
    return result


def catalog(catalog_json: dict[str, Any]) -> tuple[list[str], list[dict[str, str]]]:
    measures: list[str] = []
    dimensions: list[dict[str, str]] = []
    for model in catalog_json["models"]:
        for metric in model.get("metrics", []):
            if isinstance(metric, dict) and isinstance(metric.get("name"), str):
                measures.append(metric["name"])
        for dimension in model.get("dimensions", []):
            if isinstance(dimension, dict) and isinstance(dimension.get("name"), str):
                dimensions.append({
                    "name": dimension["name"],
                    "text": " ".join(str(dimension.get(key, "")) for key in ("name", "description", "type")).lower(),
                })
    return sorted(set(measures)), dimensions


def matches_hint(dimension: dict[str, str], hint: str) -> bool:
    return any(part in dimension["text"] for part in hint.lower().split("|"))


def reference_rows(question: Question) -> list[tuple[Any, ...]]:
    try:
        import duckdb
    except ImportError as exc:
        raise CheckFailure("duckdb is required for desktop ground truth") from exc
    with tempfile.TemporaryDirectory(prefix="desktop-truth-") as tmp:
        con = duckdb.connect(str(Path(tmp) / "truth.duckdb"))
        try:
            for table in ("customers", "orders"):
                source = PRISTINE_DATA / table / f"{table}.csv"
                con.execute(f"CREATE TABLE {table} AS SELECT * FROM read_csv_auto(?)", [str(source)])
            return [tuple(row) for row in con.execute(question.reference_sql).fetchall()]
        finally:
            con.close()


def numeric_equal(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return abs(float(left) - float(right)) <= 0.01
    return str(left) == str(right)


def canonical_row(row: Iterable[Any]) -> tuple[Any, ...]:
    # Result column order is a catalog implementation detail, not a semantic
    # requirement.  Dimensions are strings and measures numeric in this eval.
    return tuple(sorted(row, key=lambda value: (isinstance(value, (int, float)) and not isinstance(value, bool), str(value))))


def rows_equal(actual: list[list[Any]], expected: list[tuple[Any, ...]], ordered: bool) -> bool:
    left = [canonical_row(row) for row in actual]
    right = [canonical_row(row) for row in expected]
    if not ordered:
        left, right = sorted(left, key=repr), sorted(right, key=repr)
    return len(left) == len(right) and all(
        len(a) == len(b) and all(numeric_equal(x, y) for x, y in zip(a, b))
        for a, b in zip(left, right)
    )


def selections(question: Question, catalog_json: dict[str, Any]) -> Iterable[dict[str, Any]]:
    measures, dimensions = catalog(catalog_json)
    dimension_choices = dimensions
    if question.dimension_hint:
        dimension_choices = [d for d in dimensions if matches_hint(d, question.dimension_hint)]
    if question.filter_hints:
        filter_dimensions = {
            hint: [d for d in dimensions if matches_hint(d, hint)] for hint in question.filter_hints
        }
        if any(not values for values in filter_dimensions.values()):
            return
    for measure in measures:
        dims = [None] if question.dimension_hint is None else dimension_choices
        for dim in dims:
            candidates: list[dict[str, str]] = [{}]
            for hint, op, value in question.filters:
                next_candidates: list[dict[str, str]] = []
                for assigned in candidates:
                    for candidate in filter_dimensions[hint]:
                        # Both Q2 bounds must be on the same date dimension.
                        if hint in assigned and assigned[hint] != candidate["name"]:
                            continue
                        next_candidates.append({**assigned, hint: candidate["name"]})
                candidates = next_candidates
            for assigned in candidates:
                selection: dict[str, Any] = {"measures": [measure]}
                if dim is not None:
                    selection["dimensions"] = [dim["name"]]
                if question.filters:
                    selection["filters"] = [
                        {"dimension": assigned[hint], "op": op, "value": value}
                        for hint, op, value in question.filters
                    ]
                if question.ordered:
                    selection["order_by"] = [{"name": measure, "dir": "desc"}]
                if question.limit is not None:
                    selection["limit"] = question.limit
                yield selection


def answer_question(question: Question, endpoint: str, bearer: str, catalog_json: dict[str, Any], scratch: Path) -> dict[str, Any] | None:
    expected = reference_rows(question)
    for attempt, selection in enumerate(selections(question, catalog_json), start=1):
        if attempt > MAX_ATTEMPTS:
            # A rich but valid catalog must fail this question only; do not
            # abort the full harness facts pass and misreport every later
            # question as unanswerable.
            return None
        try:
            result = query(endpoint, bearer, selection, scratch)
        except CheckFailure:
            continue
        if rows_equal(result["rows"], expected, question.ordered):
            return {"selection": selection, "result": result}
    return None


def state_database(data_dir: Path) -> Path:
    dbs = [data_dir / "state.sqlite3", data_dir / "state.sqlite"]
    db = next((p for p in dbs if p.exists()), None)
    if not db:
        raise CheckFailure(f"missing supervisor state database under {data_dir}")
    return db


def published_runs(data_dir: Path, workflow: str) -> list[dict[str, Any]]:
    """Read the supervisor's publication chronology with any stored timestamps.

    The agent can mutate this database, so these facts are evidence for the
    trace-aware judge rather than a standalone immutability guarantee.  Include
    every native timestamp column the pinned runtime exposes instead of baking
    a version-specific schema into the eval.
    """
    db = state_database(data_dir)
    con = sqlite3.connect(db)
    try:
        columns = [str(row[1]) for row in con.execute("PRAGMA table_info(runs)")]
        required = {"run_id", "workflow_id", "artifact_id", "definition_id", "status"}
        if not required <= set(columns):
            raise CheckFailure(f"runs table missing required columns: {sorted(required - set(columns))}")
        timestamp_columns = [
            column for column in columns
            if column.lower().endswith(("_at", "_time", "_timestamp"))
            or column.lower() in {"created", "updated", "published"}
        ]
        selected = ["rowid", "run_id", "workflow_id", "artifact_id", "definition_id", "status", *timestamp_columns]
        quoted = ", ".join('"' + column.replace('"', '""') + '"' for column in selected)
        rows = con.execute(
            f"SELECT {quoted} FROM runs WHERE workflow_id = ? AND status = 'Published' ORDER BY rowid",
            (workflow,),
        ).fetchall()
    finally:
        con.close()
    publications = [dict(zip(selected, row)) for row in rows if row[4]]
    if len(publications) < 2:
        raise CheckFailure(f"need at least two Published runs, found {len(publications)}")
    return publications


def published_definitions(data_dir: Path, workflow: str) -> list[str]:
    return [str(run["definition_id"]) for run in published_runs(data_dir, workflow)]


def definition_path(data_dir: Path, definition_id: str) -> Path:
    """Resolve a persisted definition id to its content-addressed directory."""
    root = data_dir / "definitions"
    if ":" in definition_id:
        namespace, digest = definition_id.split(":", 1)
        addressed = root / namespace / digest
        if addressed.is_dir():
            return addressed
    return root / definition_id


def definition_hashes(data_dir: Path, definitions: Iterable[str]) -> dict[str, dict[str, str]]:
    """Hash every file in each pinned definition for trace cross-checking."""
    hashes: dict[str, dict[str, str]] = {}
    for definition in definitions:
        snapshot = definition_path(data_dir, definition)
        if not snapshot.is_dir():
            raise CheckFailure(f"published definition is missing: {snapshot}")
        files = [file for file in sorted(snapshot.rglob("*")) if file.is_file()]
        if not files:
            raise CheckFailure(f"published definition is empty: {snapshot}")
        hashes[definition] = {
            file.relative_to(snapshot).as_posix(): hashlib.sha256(file.read_bytes()).hexdigest()
            for file in files
        }
    return hashes


@dataclass
class SnapshotServe:
    holder: tempfile.TemporaryDirectory[str]
    data_dir: Path
    endpoint: str
    bearer: str
    process: subprocess.Popen
    stdout: object
    stderr: object


def serve_snapshot(snapshot: Path, label: str) -> SnapshotServe:
    """Re-serve one immutable snapshot with the foreground supervisor command.

    The detached create path is not a suitable readiness primitive: it may print
    publication metadata after its child has lost the long-lived serve context.
    Hold a direct foreground ``serve`` process instead, exactly as the agent's
    documented loop does, and let ``stop_snapshot`` reap it.
    """
    temp_root = os.environ.get("NXD_JOB_CHECK_TMPDIR", "").strip()
    if temp_root:
        Path(temp_root).mkdir(parents=True, exist_ok=True)
        holder = tempfile.TemporaryDirectory(prefix=f"desktop-{label}-", dir=temp_root)
    else:
        holder = tempfile.TemporaryDirectory(prefix=f"desktop-{label}-")
    data_dir = Path(holder.name) / "state"
    bearer = f"desktop-check-{secrets.token_urlsafe(24)}"
    env = {**os.environ, "NXD_DESKTOP_BEARER": bearer}
    stdout = tempfile.TemporaryFile(mode="w+", encoding="utf-8")
    stderr = tempfile.TemporaryFile(mode="w+", encoding="utf-8")
    process: subprocess.Popen | None = None
    try:
        process = subprocess.Popen(
            [supervisor(), "serve", "--definition", str(snapshot),
             "--workflow", label, "--data-dir", str(data_dir)],
            stdout=stdout, stderr=stderr, text=True, env=env, start_new_session=True,
        )
        deadline = time.time() + 240
        while time.time() < deadline:
            stdout.seek(0)
            output = stdout.read().strip()
            values = kv(output)
            if values.get("published") == "yes":
                endpoint = values.get("semantic_endpoint", "")
                if not endpoint:
                    raise CheckFailure(f"snapshot serve omitted endpoint: {values}")
                # Publication is emitted before the semantic child has always
                # bound its socket.  A verifier must wait for the actual
                # authenticated catalog instead of turning that brief startup
                # race into an incorrect answer or infrastructure failure.
                readiness_deadline = min(deadline, time.time() + 60)
                while time.time() < readiness_deadline:
                    try:
                        describe(endpoint, bearer)
                        return SnapshotServe(holder, data_dir, endpoint, bearer, process, stdout, stderr)
                    except CheckFailure:
                        if process.poll() is not None:
                            raise CheckFailure(
                                f"snapshot serve exited before semantic readiness ({process.returncode})"
                            )
                        time.sleep(0.25)
                raise CheckFailure(f"snapshot semantic endpoint was not ready: {endpoint}")
            if process.poll() is not None:
                stderr.seek(0)
                raise CheckFailure(
                    f"snapshot serve exited before publication ({process.returncode}): {stderr.read()[-1000:]}"
                )
            time.sleep(0.1)
        stdout.seek(0)
        stderr.seek(0)
        raise CheckFailure(
            f"snapshot serve did not publish within 240s: stdout={stdout.read()[-500:]} stderr={stderr.read()[-500:]}"
        )
    except BaseException:
        stop_data_dir(data_dir)
        if process is not None and process.poll() is None:
            reap_process_group(process.pid)
        if process is not None:
            with contextlib.suppress(subprocess.TimeoutExpired):
                process.wait(timeout=10)
        stdout.close()
        stderr.close()
        holder.cleanup()
        raise


def stop_data_dir(data_dir: Path) -> None:
    try:
        command([supervisor(), "stop", "--data-dir", str(data_dir)], timeout=45)
    except (CheckFailure, FileNotFoundError):
        pass


def reap_process_group(pid: int) -> None:
    """Best-effort TERM/KILL reap for a supervisor or semantic-child group."""
    try:
        os.killpg(pid, signal.SIGTERM)
    except OSError:
        return
    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            os.kill(pid, 0)
        except OSError:
            return
        time.sleep(0.1)
    with contextlib.suppress(OSError):
        os.killpg(pid, signal.SIGKILL)


def stop_snapshot(served: SnapshotServe) -> None:
    recorded_pids: list[int] = []
    for name in ("semantic.pid", "supervisor.pid"):
        try:
            recorded_pids.append(int((served.data_dir / name).read_text(encoding="utf-8").strip()))
        except (OSError, ValueError):
            pass
    stop_data_dir(served.data_dir)
    for pid in recorded_pids:
        reap_process_group(pid)
    if served.process.poll() is None:
        reap_process_group(served.process.pid)
    with contextlib.suppress(subprocess.TimeoutExpired):
        served.process.wait(timeout=10)
    served.stdout.close()
    served.stderr.close()
    served.holder.cleanup()


def source_hashes(root: Path) -> dict[str, str]:
    hashes = {}
    for file in sorted(root.rglob("*.csv")):
        hashes[file.relative_to(root).as_posix()] = hashlib.sha256(file.read_bytes()).hexdigest()
    return hashes


def endpoint_alive(data_dir: Path) -> bool:
    pid_file = data_dir / "semantic.pid"
    if not pid_file.exists():
        return False
    try:
        os.kill(int(pid_file.read_text().strip()), 0)
    except (OSError, ValueError):
        return False
    return True


def qualifying_phase_a_definition(data_dir: Path, workflow: str) -> str | None:
    """Find a pre-final publication that genuinely was the phase-A catalog.

    A dummy first publication followed by one full catalog would otherwise pass
    the old ``first snapshot lacks average`` check.  An honest agent may have
    unsuccessful early publications, so accept *any* earlier snapshot that
    answers Q1--Q4 and cannot answer the staged average question.
    """
    definitions = published_definitions(data_dir, workflow)
    for definition in definitions[:-1]:
        served = serve_snapshot(definition_path(data_dir, definition), "desktop-phase-a-snapshot")
        try:
            catalog_json = describe(served.endpoint, served.bearer)
            with tempfile.TemporaryDirectory(prefix="desktop-phase-a-check-") as tmp:
                scratch = Path(tmp)
                phase_a_answers = [
                    answer_question(question, served.endpoint, served.bearer, catalog_json, scratch)
                    for question in QUESTIONS[:-1]
                ]
                refine_answer = answer_question(
                    QUESTIONS[-1], served.endpoint, served.bearer, catalog_json, scratch
                )
            if all(answer is not None for answer in phase_a_answers) and refine_answer is None:
                return definition
        finally:
            stop_snapshot(served)
    return None


def require_live(data_dir: Path, workflow: str, endpoint: str, bearer: str) -> dict[str, Any]:
    status(data_dir, workflow)
    parsed = urlparse(endpoint)
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or not parsed.port:
        raise CheckFailure(f"endpoint is not loopback HTTP: {endpoint!r}")
    if not endpoint_alive(data_dir):
        raise CheckFailure("semantic.pid is absent or not alive")
    return describe(endpoint, bearer)


def agent_mode(args: argparse.Namespace) -> int:
    data_dir = Path(args.data_dir).resolve()
    catalog_json = require_live(data_dir, args.workflow, args.endpoint, args.bearer)
    with tempfile.TemporaryDirectory(prefix="desktop-agent-check-") as tmp:
        scratch = Path(tmp)
        passed: list[str] = []
        for question in QUESTIONS:
            found = answer_question(question, args.endpoint, args.bearer, catalog_json, scratch)
            if found is None:
                raise CheckFailure(f"{question.ident}: no catalog selection answered the pristine-data ground truth")
            passed.append(question.ident)
            print(f"PASS {question.ident}: {json.dumps(found['selection'], sort_keys=True)}")

    phase_a_definition = qualifying_phase_a_definition(data_dir, args.workflow)
    if phase_a_definition is None:
        raise CheckFailure(
            "no published definition before the final run answered every phase-A question "
            "while lacking the staged average metric"
        )
    print(f"PASS phase_a_snapshot: {phase_a_definition}")
    print(f"ALL CHECKS PASSED ({len(passed) + 2}/{len(QUESTIONS) + 2})")
    return 0


def harness_mode(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    # A killed verifier can leave a temporary snapshot serve under this
    # harness-owned root. It is neither agent state nor a reason to reject the
    # real .desktop/state directory on a rerun.
    state_dbs = sorted({
        p.parent for p in workspace.rglob("state.sqlite*")
        if p.name in {"state.sqlite", "state.sqlite3"}
        and ".desktop-check-tmp" not in p.relative_to(workspace).parts
    })
    facts: dict[str, Any] = {
        "check_script_pristine": (workspace / "check_job_loop.py").exists()
        and (workspace / "check_job_loop.py").read_bytes() == Path(__file__).read_bytes(),
        "source_csvs_pristine": (workspace / "data").exists() and source_hashes(workspace / "data") == source_hashes(PRISTINE_DATA),
        "state_dirs": [str(p.relative_to(workspace)) for p in state_dbs],
        "questions": {q.ident: "UNANSWERABLE" for q in QUESTIONS},
        "phase_a_definition_id": None,
        "phase_a_snapshot_refine_unanswerable": False,
        "runs_published": 0,
        "published_runs": [],
        "definition_sha256": {},
        "agent_left_endpoint_running": False,
    }
    if len(state_dbs) != 1:
        facts["error"] = f"expected exactly one supervisor state directory, found {len(state_dbs)}"
        print(json.dumps(facts, sort_keys=True))
        return 1
    data_dir = state_dbs[0]
    facts["agent_left_endpoint_running"] = endpoint_alive(data_dir)
    try:
        runs = published_runs(data_dir, args.workflow)
        definitions = [str(run["definition_id"]) for run in runs]
        facts["runs_published"] = len(runs)
        # Keep the full publication order and immutable-content fingerprints in
        # the fact payload. The judge uses them with the trace to reject a
        # fabricated second run or a post-publication snapshot rewrite.
        facts["published_runs"] = runs
        facts["definition_sha256"] = definition_hashes(data_dir, definitions)
        # Re-serve the LAST immutable snapshot, not the mutable closure or a
        # stale endpoint. This reruns its transform from the pinned CSVs.
        last = serve_snapshot(definition_path(data_dir, definitions[-1]), "desktop-final-snapshot")
        try:
            final_catalog = describe(last.endpoint, last.bearer)
            with tempfile.TemporaryDirectory(prefix="desktop-harness-check-") as tmp:
                for question in QUESTIONS:
                    facts["questions"][question.ident] = "CORRECT" if answer_question(question, last.endpoint, last.bearer, final_catalog, Path(tmp)) else "INCORRECT"
        finally:
            stop_snapshot(last)

        phase_a_definition = qualifying_phase_a_definition(data_dir, args.workflow)
        facts["phase_a_definition_id"] = phase_a_definition
        facts["phase_a_snapshot_refine_unanswerable"] = phase_a_definition is not None
    except (CheckFailure, OSError, sqlite3.Error) as exc:
        facts["error"] = str(exc)

    facts["passed"] = (
        all(value == "CORRECT" for value in facts["questions"].values())
        and facts["phase_a_snapshot_refine_unanswerable"]
        and facts["runs_published"] >= 2
        and facts["source_csvs_pristine"]
        and facts["check_script_pristine"]
    )
    print(json.dumps(facts, sort_keys=True))
    return 0 if facts["passed"] else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("agent", "harness"), default="agent")
    parser.add_argument("--data-dir", help="agent mode: supervisor data directory")
    parser.add_argument("--workflow", default="invoice-pulse")
    parser.add_argument("--endpoint", help="agent mode: current semantic endpoint")
    parser.add_argument("--bearer", help="agent mode: current bearer token")
    parser.add_argument("--workspace", help="harness mode: preserved agent workspace")
    args = parser.parse_args()
    if args.mode == "agent" and not all((args.data_dir, args.endpoint, args.bearer)):
        parser.error("agent mode requires --data-dir, --endpoint, and --bearer")
    if args.mode == "harness" and not args.workspace:
        parser.error("harness mode requires --workspace")
    return args


def main() -> int:
    args = parse_args()
    try:
        return agent_mode(args) if args.mode == "agent" else harness_mode(args)
    except CheckFailure as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
