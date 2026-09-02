#!/usr/bin/env python3
"""Runner-owned verifier for the optional-output desktop scenario."""

from __future__ import annotations

import argparse
import ast
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


def _catalog_metrics(models: list[Any]) -> list[str]:
    return [
        metric["name"]
        for model in models
        if isinstance(model, dict)
        for metric in model.get("metrics", []) or []
        if isinstance(metric, dict) and isinstance(metric.get("name"), str)
    ]


def _catalog_dimensions(models: list[Any]) -> list[str]:
    return [
        dimension["name"]
        for model in models
        if isinstance(model, dict)
        for dimension in model.get("dimensions", []) or []
        if isinstance(dimension, dict) and isinstance(dimension.get("name"), str)
    ]


def _semantic_view_names(source: str) -> set[str]:
    names: set[str] = set()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return names
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        value = node.value
        if not any(
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "semantic_view"
            for call in ast.walk(value)
        ):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        names.update(target.id for target in targets if isinstance(target, ast.Name))
    return names


def _output_model_names(source: str) -> set[str]:
    names: set[str] = set()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return names
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "model"
            and node.args
            and isinstance(node.args[0], ast.Name)
        ):
            continue
        names.add(node.args[0].id)
    return names


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


def _serve(
    supervisor: str, definition: Path, data_dir: Path
) -> tuple[subprocess.Popen[str], str, str, Path]:
    token = "desktop-check-" + secrets.token_urlsafe(18)
    env = {**os.environ, "NXD_DESKTOP_BEARER": token}
    log_dir = Path(tempfile.mkdtemp(prefix="optional-empty-supervisor-"))
    stdout_path = log_dir / "stdout.log"
    stderr_path = log_dir / "stderr.log"
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
                readiness_deadline = min(deadline, time.monotonic() + 60)
                while time.monotonic() < readiness_deadline:
                    try:
                        describe = json.loads(_run([
                            supervisor, "describe", "--endpoint", endpoint, "--token", token
                        ], timeout=15))
                        if not isinstance(describe.get("models"), list) or not describe["models"]:
                            raise CheckFailure("describe_models returned no models")
                        return proc, endpoint, token, log_dir
                    except (CheckFailure, json.JSONDecodeError, subprocess.SubprocessError) as exc:
                        readiness_error = str(exc)
                    if proc.poll() is not None:
                        raise CheckFailure(
                            "supervisor exited before semantic readiness: "
                            + _log_tail(stderr_path)
                            + _log_tail(stdout_path)
                        )
                    time.sleep(0.2)
                raise CheckFailure(
                    f"semantic endpoint was not ready within the verifier budget: {endpoint}; "
                    + readiness_error
                )
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
            _stop(supervisor, data_dir, proc)
            if proc.poll() is None:
                _reap(proc)
        shutil.rmtree(log_dir, ignore_errors=True)
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
    stop_status = "ok"
    try:
        stopped = subprocess.run(
            [supervisor, "stop", "--data-dir", str(data_dir)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if stopped.returncode != 0:
            stop_status = f"stop_exit_{stopped.returncode}"
    except (OSError, subprocess.SubprocessError) as exc:
        stop_status = f"stop_error_{type(exc).__name__}"
    finally:
        _reap(proc)
    if proc.poll() is None:
        return f"process_group_reap_incomplete ({stop_status})"
    return f"process_group_reaped ({stop_status})"


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
    view_names = _semantic_view_names(models)
    if not view_names or not view_names & _output_model_names(spec):
        raise CheckFailure("aggregate semantic view is missing")
    if "Agg.COUNT" not in models or 'orders.field("*")' not in models:
        raise CheckFailure("aggregate view is not a COUNT(*) metric")

    supervisor = _supervisor()
    runtime_tmp = os.environ.get("NXD_JOB_CHECK_TMPDIR", "")
    if runtime_tmp:
        Path(runtime_tmp).mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="optional-empty-e2e-", dir=runtime_tmp or None) as tmp:
        data_dir = Path(tmp) / "state"
        proc, endpoint, token, log_dir = _serve(supervisor, definition, data_dir)
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
            metric_names = _catalog_metrics(models_payload)
            if not metric_names:
                raise CheckFailure("aggregate catalog does not expose a metric")
            category_dimensions = [
                dimension
                for dimension in _catalog_dimensions(models_payload)
                if "product" in dimension.lower() and "categor" in dimension.lower()
            ]
            if not category_dimensions:
                raise CheckFailure("aggregate catalog does not expose a product-category dimension")
            expected = _expected_counts()
            matched: tuple[str, str, list[str], dict[str, int]] | None = None
            attempts: list[str] = []
            for category_dim in category_dimensions:
                for count_metric in sorted(
                    metric_names, key=lambda name: 0 if "count" in name.lower() else 1
                ):
                    selection = Path(tmp) / "selection.json"
                    selection.write_text(json.dumps({
                        "measures": [count_metric],
                        "dimensions": [category_dim],
                    }), encoding="utf-8")
                    try:
                        query = json.loads(_run([
                            supervisor, "query", "--endpoint", endpoint, "--token", token,
                            "--selection", str(selection),
                        ], timeout=90))
                    except (CheckFailure, json.JSONDecodeError, subprocess.SubprocessError) as exc:
                        attempts.append(f"{category_dim}/{count_metric}: {exc}")
                        continue
                    columns = query.get("columns")
                    rows = query.get("rows")
                    if not isinstance(columns, list) or not isinstance(rows, list):
                        attempts.append(f"{category_dim}/{count_metric}: no tabular result")
                        continue
                    lowered = [str(column).lower() for column in columns]
                    expected_columns = {category_dim.lower(), count_metric.lower()}
                    if len(columns) != 2 or set(lowered) != expected_columns:
                        attempts.append(f"{category_dim}/{count_metric}: record-level columns")
                        continue
                    category_index = lowered.index(category_dim.lower())
                    count_index = lowered.index(count_metric.lower())
                    try:
                        actual = {
                            str(row[category_index]): int(row[count_index])
                            for row in rows
                        }
                    except (IndexError, TypeError, ValueError) as exc:
                        attempts.append(f"{category_dim}/{count_metric}: invalid rows: {exc}")
                        continue
                    if actual == expected:
                        matched = (count_metric, category_dim, [str(column) for column in columns], actual)
                        break
                    attempts.append(f"{category_dim}/{count_metric}: got {actual}, expected {expected}")
                if matched is not None:
                    break
            if matched is None:
                raise CheckFailure(
                    "no governed aggregate selection matched pristine source: "
                    + "; ".join(attempts[:6])
                )
            count_metric, category_dim, columns, actual = matched
            result = {
                "passed": True,
                "published": "yes",
                "catalog_models": len(models_payload),
                "optional_model_visible": True,
                "count_metric": count_metric,
                "category_dimension": category_dim,
                "query_columns": columns,
                "aggregate_rows": actual,
                "compiler_execution": "deferred follow-up",
            }
        except Exception as exc:
            raise CheckFailure(
                f"{exc}; supervisor stdout={_log_tail(log_dir / 'stdout.log')} "
                f"stderr={_log_tail(log_dir / 'stderr.log')}"
            ) from exc
        finally:
            teardown = _stop(supervisor, data_dir, proc)
            shutil.rmtree(log_dir, ignore_errors=True)
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
