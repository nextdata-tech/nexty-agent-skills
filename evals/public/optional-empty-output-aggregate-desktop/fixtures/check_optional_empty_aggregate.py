#!/usr/bin/env python3
"""Runner-owned verifier for the optional-output desktop scenario."""

from __future__ import annotations

import argparse
import csv
import contextlib
import hashlib
import json
import os
import secrets
import signal
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
WORKFLOW = "mapper-aggregate-e2e"


class CheckFailure(RuntimeError):
    pass


def _supervisor() -> str:
    value = os.environ.get("EVAL_DESKTOP_SUPERVISOR", "")
    if value:
        return value
    for candidate in ("nxd-desktop-supervisor",):
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    raise CheckFailure("nxd-desktop-supervisor is not on PATH")


def _source_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*.csv"))
    }


def _expected_counts() -> dict[str, int]:
    source = HERE / "data/orders/orders.csv"
    with source.open(newline="", encoding="utf-8") as handle:
        return {
            category: count
            for category, count in _count_rows(csv.DictReader(handle)).items()
        }


def _count_rows(rows: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        category = str(row["product_category"])
        counts[category] = counts.get(category, 0) + 1
    return counts


def _run(args: list[str], *, timeout: int = 90, env: dict[str, str] | None = None) -> str:
    proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout, env=env)
    if proc.returncode != 0:
        raise CheckFailure(f"command failed: {args[0]} ({proc.returncode})")
    return proc.stdout.strip()


def _contains(value: Any, needle: str) -> bool:
    if isinstance(value, str):
        return value == needle or needle in value
    if isinstance(value, dict):
        return any(_contains(key, needle) or _contains(item, needle) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains(item, needle) for item in value)
    return False


def _kv(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def _log_tail(path: Path, limit: int = 1000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[-limit:]
    except OSError:
        return ""


def _serve(supervisor: str, definition: Path, data_dir: Path) -> tuple[subprocess.Popen[str], str, str]:
    token = "desktop-check-" + secrets.token_urlsafe(18)
    env = {**os.environ, "NXD_DESKTOP_BEARER": token}
    with tempfile.TemporaryDirectory(prefix="optional-empty-supervisor-") as log_dir:
        stdout_path = Path(log_dir) / "stdout.log"
        stderr_path = Path(log_dir) / "stderr.log"
        proc: subprocess.Popen[str] | None = None
        try:
            with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open(
                "w", encoding="utf-8"
            ) as stderr:
                proc = subprocess.Popen(
                    [supervisor, "serve", "--definition", str(definition), "--workflow", WORKFLOW,
                     "--data-dir", str(data_dir)],
                    stdout=stdout,
                    stderr=stderr,
                    text=True,
                    env=env,
                    start_new_session=True,
                )
            deadline = time.monotonic() + 300
            readiness_error = ""
            while time.monotonic() < deadline:
                values = _kv(stdout_path.read_text(encoding="utf-8", errors="replace"))
                if values.get("published") == "yes":
                    endpoint = values.get("semantic_endpoint", "")
                    if not endpoint:
                        raise CheckFailure(f"supervisor published without an endpoint: {values}")
                    try:
                        describe = json.loads(_run([
                            supervisor, "describe", "--endpoint", endpoint, "--token", token
                        ], timeout=90))
                        if not isinstance(describe.get("models"), list) or not describe["models"]:
                            raise CheckFailure("describe_models returned no models")
                        return proc, endpoint, token
                    except (CheckFailure, json.JSONDecodeError) as exc:
                        readiness_error = str(exc)
                if proc.poll() is not None:
                    raise CheckFailure(
                        "supervisor exited before semantic readiness: "
                        + _log_tail(stderr_path)
                        + _log_tail(stdout_path)
                    )
                time.sleep(0.2)
            raise CheckFailure(
                "supervisor did not become ready within the verifier budget: "
                + readiness_error
                + " stderr="
                + _log_tail(stderr_path)
                + " stdout="
                + _log_tail(stdout_path)
            )
        except BaseException:
            if proc is not None:
                with contextlib.suppress(CheckFailure, OSError, subprocess.TimeoutExpired):
                    _stop(supervisor, data_dir, proc)
                if proc.poll() is None:
                    _reap(proc)
            raise


def _reap(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except (OSError, ProcessLookupError):
        return
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(OSError, ProcessLookupError):
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        with contextlib.suppress(subprocess.TimeoutExpired):
            proc.wait(timeout=10)


def _stop(supervisor: str, data_dir: Path, proc: subprocess.Popen[str]) -> str:
    try:
        stopped = subprocess.run(
            [supervisor, "stop", "--data-dir", str(data_dir)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        detail = (stopped.stderr or stopped.stdout).strip()
        if (
            stopped.returncode != 0
            and proc.poll() is None
            and "without a detached control marker" not in detail
        ):
            raise CheckFailure(f"supervisor stop failed ({stopped.returncode}): {detail}")
    finally:
        _reap(proc)
    if proc.poll() is None:
        raise CheckFailure("supervisor process group did not exit during teardown")
    return "process_group_reaped"


def _verify(definition: Path) -> dict[str, Any]:
    if _source_hashes(definition / "data") != _source_hashes(HERE / "data"):
        raise CheckFailure("source CSVs were changed")
    if (definition / "data/reviews").exists():
        raise CheckFailure("optional review source was materialized")

    transform = (definition / "transform/main.py").read_text(encoding="utf-8")
    models = (definition / "models.py").read_text(encoding="utf-8")
    spec = (definition / "spec.py").read_text(encoding="utf-8")
    if 'OPTIONAL_EMPTY_MODELS = ("reviews",)' not in transform:
        raise CheckFailure("optional review metadata is missing")
    if "map_inputs(" not in transform or "nxd.experimental.field_mapper" not in transform:
        raise CheckFailure("public mapper seam is missing")
    if "field_mapper.transport" in transform or "field_mapper.ledger" in transform:
        raise CheckFailure("private mapper seam was imported")
    if ".model(reviews)" not in spec or ".promise(reviews)" in spec:
        raise CheckFailure("optional review output is wired with the wrong contract")
    if ".model(order_metrics)" not in spec or "semantic_view(\"order_metrics\", orders)" not in models:
        raise CheckFailure("aggregate semantic view is missing")
    if "Agg.COUNT" not in models or 'orders.field("*")' not in models:
        raise CheckFailure("aggregate view is not a COUNT(*) metric")

    supervisor = _supervisor()
    runtime_tmp = os.environ.get("NXD_JOB_CHECK_TMPDIR", "")
    if runtime_tmp:
        Path(runtime_tmp).mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="optional-empty-e2e-", dir=runtime_tmp or None) as tmp:
        data_dir = Path(tmp) / "state"
        proc, endpoint, token = _serve(supervisor, definition, data_dir)
        result: dict[str, Any]
        try:
            describe = json.loads(_run([
                supervisor, "describe", "--endpoint", endpoint, "--token", token
            ], timeout=90))
            models_payload = describe.get("models")
            if not isinstance(models_payload, list):
                raise CheckFailure("describe_models did not return a model catalog")
            if not any(_contains(model, "reviews") for model in models_payload):
                raise CheckFailure("optional reviews model is absent from the catalog")
            metric_names = [
                str(measure["name"])
                for model in models_payload
                if isinstance(model, dict) and model.get("name") == "order_metrics"
                for measure in model.get("metrics", [])
                if (
                    isinstance(measure, dict)
                    and isinstance(measure.get("name"), str)
                    and str(measure.get("aggregation", "")).upper() == "COUNT"
                )
            ]
            if len(metric_names) != 1:
                raise CheckFailure("aggregate catalog does not expose exactly one COUNT metric")
            count_metric = metric_names[0]

            selection = Path(tmp) / "selection.json"
            selection.write_text(json.dumps({
                "measures": [count_metric],
                "dimensions": ["product_category"],
            }), encoding="utf-8")
            query = json.loads(_run([
                supervisor, "query", "--endpoint", endpoint, "--token", token,
                "--selection", str(selection),
            ], timeout=90))
            columns = query.get("columns")
            rows = query.get("rows")
            if not isinstance(columns, list) or not isinstance(rows, list):
                raise CheckFailure("governed query returned no tabular result")
            if set(columns) != {"product_category", count_metric}:
                raise CheckFailure("governed query exposed record-level columns")
            actual = {
                str(row[columns.index("product_category")]): int(
                    row[columns.index(count_metric)]
                )
                for row in rows
            }
            expected = _expected_counts()
            if actual != expected:
                raise CheckFailure("governed aggregate counts do not match pristine source")
            result = {
                "passed": True,
                "published": "yes",
                "catalog_models": len(models_payload),
                "optional_model_visible": True,
                "count_metric": count_metric,
                "query_columns": columns,
                "aggregate_rows": actual,
                "compiler_execution": "deferred follow-up",
            }
        finally:
            teardown = _stop(supervisor, data_dir, proc)
        result["teardown"] = teardown
        return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--workflow", required=True)
    args = parser.parse_args()
    try:
        if args.mode != "harness":
            raise CheckFailure("verifier only runs in harness mode")
        if args.workflow != WORKFLOW:
            raise CheckFailure("unexpected workflow")
        facts = _verify(Path(args.workspace))
    except (CheckFailure, OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        facts = {"passed": False, "error": str(exc)}
    print(json.dumps(facts, sort_keys=True))
    return 0 if facts.get("passed") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
