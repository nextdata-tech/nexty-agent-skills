#!/usr/bin/env python3
"""Independent verifier for the local job loop export/handoff eval.

``--mode agent`` is the forcing function an agent runs while its endpoint is
live: it re-answers the questions from pristine ground truth AND opens the
exported bundle to confirm it is a complete, self-contained handoff.
``--mode harness`` is run from the pristine scenario copy after the agent
exits: it re-serves the last immutable snapshot, then independently re-opens the
exported bundle, extracts it, serves the *bundle's own* closure into a fresh
workflow, and confirms it reproduces every answer.  Neither mode trusts a
transcript, an answer pasted by the agent, or the mutable workspace for its
ground truth.

The bundle is what ``export_data_product`` (surfaced on the CLI as
``nxd-desktop-supervisor export``) produces: the whole closure with credentials
stripped fail-closed, plus a generated ``IMPORT.md`` and ``export.json``.  This
scenario's source is a credential-free CSV export, so redaction is a clean
no-op — the property under test here is that the bundle is a *complete,
rebuildable* handoff.  A credential-bearing (database/REST) variant that also
proves fail-closed redaction on real secret bytes is a documented follow-up (it
needs the runner to stand up the source's backend during preflight).
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import secrets
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse


HERE = Path(__file__).resolve().parent
PRISTINE_DATA = HERE / "data"
MAX_ATTEMPTS = 80

# The exported bundle must carry at least these closure members for a recipient
# to rebuild.  Matched by basename/suffix against the (optionally top-level-
# prefixed) zip entries.  requirements.txt and the generated record files
# (dp-blueprint.approved.md, dp-blueprint.lock.json, build-record.json, README.md) are
# expected too but treated as soft signals: the round-trip re-serve is the real
# completeness gate.
CORE_MEMBERS = ("spec.py", "models.py", "transform/main.py", "infra-profile.yaml")


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


def published_definitions(data_dir: Path, workflow: str) -> list[str]:
    db = state_database(data_dir)
    con = sqlite3.connect(db)
    try:
        columns = [str(row[1]) for row in con.execute("PRAGMA table_info(runs)")]
        required = {"run_id", "workflow_id", "definition_id", "status"}
        if not required <= set(columns):
            raise CheckFailure(f"runs table missing required columns: {sorted(required - set(columns))}")
        rows = con.execute(
            "SELECT definition_id FROM runs WHERE workflow_id = ? AND status = 'Published' ORDER BY rowid",
            (workflow,),
        ).fetchall()
    finally:
        con.close()
    definitions = [str(row[0]) for row in rows if row[0]]
    if not definitions:
        raise CheckFailure("no Published run found for workflow")
    return definitions


def definition_path(data_dir: Path, definition_id: str) -> Path:
    """Resolve a persisted definition id to its content-addressed directory."""
    root = data_dir / "definitions"
    if ":" in definition_id:
        namespace, digest = definition_id.split(":", 1)
        addressed = root / namespace / digest
        if addressed.is_dir():
            return addressed
    return root / definition_id


@dataclass
class SnapshotServe:
    holder: tempfile.TemporaryDirectory[str]
    data_dir: Path
    endpoint: str
    bearer: str
    process: subprocess.Popen
    stdout: object
    stderr: object


def serve_definition(definition: Path, label: str) -> SnapshotServe:
    """Serve one Python-source closure with the foreground supervisor command.

    Works for both a pinned snapshot and a freshly extracted bundle closure:
    the supervisor compiles spec.py at serve time in either case.
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
            [supervisor(), "serve", "--definition", str(definition),
             "--workflow", label, "--data-dir", str(data_dir)],
            stdout=stdout, stderr=stderr, text=True, env=env, start_new_session=True,
        )
        deadline = time.time() + 240
        while time.time() < deadline:
            stdout.seek(0)
            values = kv(stdout.read().strip())
            if values.get("published") == "yes":
                endpoint = values.get("semantic_endpoint", "")
                if not endpoint:
                    raise CheckFailure(f"serve omitted endpoint: {values}")
                readiness_deadline = min(deadline, time.time() + 60)
                while time.time() < readiness_deadline:
                    try:
                        describe(endpoint, bearer)
                        return SnapshotServe(holder, data_dir, endpoint, bearer, process, stdout, stderr)
                    except CheckFailure:
                        if process.poll() is not None:
                            raise CheckFailure(f"serve exited before semantic readiness ({process.returncode})")
                        time.sleep(0.25)
                raise CheckFailure(f"semantic endpoint was not ready: {endpoint}")
            if process.poll() is not None:
                stderr.seek(0)
                raise CheckFailure(f"serve exited before publication ({process.returncode}): {stderr.read()[-1000:]}")
            time.sleep(0.1)
        stdout.seek(0)
        stderr.seek(0)
        raise CheckFailure(
            f"serve did not publish within 240s: stdout={stdout.read()[-500:]} stderr={stderr.read()[-500:]}"
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
    return {
        file.relative_to(root).as_posix(): hashlib.sha256(file.read_bytes()).hexdigest()
        for file in sorted(root.rglob("*.csv"))
    }


def endpoint_alive(data_dir: Path) -> bool:
    pid_file = data_dir / "semantic.pid"
    if not pid_file.exists():
        return False
    try:
        os.kill(int(pid_file.read_text().strip()), 0)
    except (OSError, ValueError):
        return False
    return True


# --- Bundle inspection -----------------------------------------------------

def _strip_top_level(names: list[str]) -> list[str]:
    """Drop a single shared top-level directory prefix if the zip has one."""
    tops = {n.split("/", 1)[0] for n in names if "/" in n}
    non_top = {n for n in names if "/" not in n}
    if len(tops) == 1 and not non_top:
        prefix = next(iter(tops)) + "/"
        return [n[len(prefix):] for n in names if n != prefix and n.startswith(prefix)]
    return names


def inspect_bundle(bundle: Path) -> dict[str, Any]:
    """Structural facts about an exported bundle, without trusting the agent."""
    facts: dict[str, Any] = {
        "bundle_found": bundle.is_file(),
        "bundle_path": str(bundle),
        "bundle_is_zip": False,
        "core_members_present": False,
        "missing_core_members": [],
        "has_import_md": False,
        "import_md_nonempty": False,
        "has_export_json": False,
        "export_json_parses": False,
        "has_data_csv": False,
    }
    if not bundle.is_file() or not zipfile.is_zipfile(bundle):
        return facts
    facts["bundle_is_zip"] = True
    with zipfile.ZipFile(bundle) as zf:
        raw_names = [i.filename for i in zf.infolist() if not i.is_dir()]
        names = _strip_top_level(raw_names)
        nameset = set(names)

        def present(member: str) -> bool:
            return member in nameset or any(n.endswith("/" + member) or n == member for n in names)

        missing = [m for m in CORE_MEMBERS if not present(m)]
        facts["missing_core_members"] = missing
        facts["core_members_present"] = not missing
        facts["has_data_csv"] = any(n.startswith("data/") and n.endswith(".csv") for n in names)
        facts["has_import_md"] = present("IMPORT.md")
        facts["has_export_json"] = present("export.json")

        def read_member(member: str) -> bytes | None:
            for info in zf.infolist():
                stripped = _strip_top_level([info.filename])[0] if info.filename else info.filename
                if stripped == member or info.filename.endswith("/" + member) or info.filename == member:
                    return zf.read(info.filename)
            return None

        import_md = read_member("IMPORT.md")
        facts["import_md_nonempty"] = bool(import_md and import_md.strip())
        export_json = read_member("export.json")
        if export_json is not None:
            try:
                json.loads(export_json)
                facts["export_json_parses"] = True
            except json.JSONDecodeError:
                facts["export_json_parses"] = False
    return facts


def bundle_closure_root(extract_root: Path) -> Path:
    """Find the directory inside an extracted bundle that holds spec.py."""
    for spec in sorted(extract_root.rglob("spec.py")):
        return spec.parent
    raise CheckFailure("extracted bundle has no spec.py")


def find_bundle(workspace: Path) -> Path | None:
    preferred = workspace / "export" / "invoice-pulse-bundle.zip"
    if preferred.is_file():
        return preferred
    candidates = [
        p for p in sorted(workspace.rglob("*.zip"))
        if ".desktop-check-tmp" not in p.relative_to(workspace).parts
        and "state" not in p.relative_to(workspace).parts
    ]
    return candidates[0] if candidates else None


# --- Modes -----------------------------------------------------------------

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
        for question in QUESTIONS:
            found = answer_question(question, args.endpoint, args.bearer, catalog_json, scratch)
            if found is None:
                raise CheckFailure(f"{question.ident}: no catalog selection answered the pristine-data ground truth")
            print(f"PASS {question.ident}: {json.dumps(found['selection'], sort_keys=True)}")

    if not args.bundle:
        raise CheckFailure("agent mode requires --bundle for the export scenario")
    bundle = Path(args.bundle).resolve()
    facts = inspect_bundle(bundle)
    if not facts["bundle_found"]:
        raise CheckFailure(f"exported bundle not found at {bundle}")
    if not facts["bundle_is_zip"]:
        raise CheckFailure(f"exported bundle is not a zip: {bundle}")
    if not facts["core_members_present"]:
        raise CheckFailure(f"bundle missing core closure members: {facts['missing_core_members']}")
    if not facts["has_import_md"] or not facts["import_md_nonempty"]:
        raise CheckFailure("bundle has no non-empty IMPORT.md")
    if not facts["has_export_json"] or not facts["export_json_parses"]:
        raise CheckFailure("bundle has no parseable export.json")
    print(f"PASS bundle_structure: {json.dumps({k: facts[k] for k in ('core_members_present', 'has_import_md', 'has_export_json')}, sort_keys=True)}")
    print(f"ALL CHECKS PASSED ({len(QUESTIONS) + 1}/{len(QUESTIONS) + 1})")
    return 0


def harness_mode(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
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
        "runs_published": 0,
        "agent_left_endpoint_running": False,
        "bundle": {},
        "bundle_roundtrip_answers": {q.ident: "UNANSWERABLE" for q in QUESTIONS},
        "bundle_ok": False,
    }
    if len(state_dbs) != 1:
        facts["error"] = f"expected exactly one supervisor state directory, found {len(state_dbs)}"
        print(json.dumps(facts, sort_keys=True))
        return 1
    data_dir = state_dbs[0]
    facts["agent_left_endpoint_running"] = endpoint_alive(data_dir)
    try:
        definitions = published_definitions(data_dir, args.workflow)
        facts["runs_published"] = len(definitions)

        # 1. Re-serve the agent's last immutable snapshot and re-answer from
        #    pristine truth — proves the served product is correct.
        last = serve_definition(definition_path(data_dir, definitions[-1]), "desktop-final-snapshot")
        try:
            final_catalog = describe(last.endpoint, last.bearer)
            with tempfile.TemporaryDirectory(prefix="desktop-harness-check-") as tmp:
                for question in QUESTIONS:
                    facts["questions"][question.ident] = (
                        "CORRECT" if answer_question(question, last.endpoint, last.bearer, final_catalog, Path(tmp)) else "INCORRECT"
                    )
        finally:
            stop_snapshot(last)

        # 2. Independently inspect the exported bundle, then rebuild FROM IT.
        bundle = find_bundle(workspace)
        if bundle is None:
            facts["bundle"] = {"bundle_found": False}
        else:
            bundle_facts = inspect_bundle(bundle)
            facts["bundle"] = bundle_facts
            structural_ok = (
                bundle_facts["bundle_is_zip"]
                and bundle_facts["core_members_present"]
                and bundle_facts["has_import_md"]
                and bundle_facts["import_md_nonempty"]
                and bundle_facts["has_export_json"]
                and bundle_facts["export_json_parses"]
            )
            if structural_ok:
                with tempfile.TemporaryDirectory(prefix="desktop-bundle-extract-") as ex:
                    with zipfile.ZipFile(bundle) as zf:
                        zf.extractall(ex)
                    closure = bundle_closure_root(Path(ex))
                    served = serve_definition(closure, "desktop-bundle-roundtrip")
                    try:
                        rt_catalog = describe(served.endpoint, served.bearer)
                        with tempfile.TemporaryDirectory(prefix="desktop-bundle-check-") as tmp:
                            for question in QUESTIONS:
                                facts["bundle_roundtrip_answers"][question.ident] = (
                                    "CORRECT" if answer_question(question, served.endpoint, served.bearer, rt_catalog, Path(tmp)) else "INCORRECT"
                                )
                    finally:
                        stop_snapshot(served)
            facts["bundle_ok"] = structural_ok and all(
                value == "CORRECT" for value in facts["bundle_roundtrip_answers"].values()
            )
    except (CheckFailure, OSError, sqlite3.Error) as exc:
        facts["error"] = str(exc)

    facts["passed"] = (
        all(value == "CORRECT" for value in facts["questions"].values())
        and facts["bundle_ok"]
        and facts["runs_published"] >= 1
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
    parser.add_argument("--bundle", help="agent mode: path to the exported bundle zip")
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
