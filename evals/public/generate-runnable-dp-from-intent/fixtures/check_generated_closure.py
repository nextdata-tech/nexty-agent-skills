#!/usr/bin/env python3
"""Validate a Python-only desktop closure and execute its transform."""

from __future__ import annotations

import ast
import csv
import hashlib
import json
import os
import re
import sys
import tempfile
import types
from dataclasses import dataclass
from pathlib import Path


REQUIRED = (
    "spec.py",
    "models.py",
    "infra-profile.yaml",
    "transform/main.py",
    "requirements.txt",
    "csv-source-path",
)
FORBIDDEN = ("deployment-spec.yaml", "manifest.yaml", "models.yaml")
CSV_SHA256 = {
    "customers/customers.csv": "e839803bf3f5d44488dbed69d5605114f9436249cdd421bd0b38a8cd40d6914b",
    "orders/orders.csv": "24f7a01bbb4a5fa9b12489a0c0475de885a86a01a37a404ec62a196cb2a4e69d",
}


def fail(message: str) -> None:
    print(f"FAIL {message}")
    raise SystemExit(1)


def check(label: str, condition: bool, detail: str = "") -> None:
    if not condition:
        fail(f"{label}: {detail}" if detail else label)
    print(f"PASS {label}")


@dataclass
class DuckDbOutput:
    path: str
    schema: str
    model_tables: dict[str, str]


class Runtime:
    def on_transform(self, *args, **kwargs):
        if args and callable(args[0]) and not kwargs:
            return args[0]
        return lambda fn: fn

    def main(self):
        return None


def install_transform_stubs() -> None:
    nxd = types.ModuleType("nxd")
    core = types.ModuleType("nxd.core")
    context = types.ModuleType("nxd.core.context")
    context.DuckDbOutput = DuckDbOutput
    core.context = context
    nxd.core = core
    nxd.data_product = Runtime()
    sys.modules.update({"nxd": nxd, "nxd.core": core, "nxd.core.context": context})


def csv_count(path: Path) -> int:
    with path.open(newline="", encoding="utf-8") as handle:
        return sum(1 for row in csv.reader(handle) if row) - 1


def call_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def promised_models(tree: ast.AST) -> set[str]:
    promised: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "promise" or len(node.args) != 1:
            continue
        argument = node.args[0]
        if isinstance(argument, ast.Name):
            promised.add(argument.id)
    return promised


def base_model_schemas(tree: ast.AST) -> dict[str, ast.Dict]:
    results: dict[str, ast.Dict] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        value = node.value
        if not isinstance(value, ast.Call) or not isinstance(value.func, ast.Attribute):
            continue
        if value.func.attr != "schema" or not isinstance(value.func.value, ast.Call):
            continue
        model_call = value.func.value
        if call_name(model_call.func) != "semantic_model" or len(model_call.args) != 1:
            continue
        if not isinstance(model_call.args[0], ast.Constant) or not isinstance(model_call.args[0].value, str):
            continue
        if len(value.args) != 1 or not isinstance(value.args[0], ast.Dict):
            continue
        results[model_call.args[0].value] = value.args[0]
    return results


def base_model_primary_keys(tree: ast.AST) -> dict[str, set[str]]:
    results: dict[str, set[str]] = {}
    for model, schema in base_model_schemas(tree).items():
        results[model] = {
            column.value
            for column, field_spec in zip(schema.keys, schema.values, strict=True)
            if isinstance(column, ast.Constant)
            and isinstance(column.value, str)
            and any(call_name(role.func) == "primary_key" for role in field_roles(field_spec))
        }
    return results


def field_roles(field_spec: ast.expr) -> list[ast.Call]:
    """Return only roles passed directly to the public field() constructor."""
    if not isinstance(field_spec, ast.Call) or call_name(field_spec.func) != "field":
        return []
    return [role for role in field_spec.args[1:] if isinstance(role, ast.Call)]


def string_keyword(call: ast.Call, name: str) -> str | None:
    for keyword in call.keywords:
        if keyword.arg == name and isinstance(keyword.value, ast.Constant):
            return keyword.value.value if isinstance(keyword.value.value, str) else None
    return None


def bool_keyword(call: ast.Call, name: str) -> bool:
    return any(
        keyword.arg == name
        and isinstance(keyword.value, ast.Constant)
        and keyword.value.value is True
        for keyword in call.keywords
    )


def semantic_view_schemas(tree: ast.AST) -> dict[str, tuple[str, ast.Dict]]:
    views: dict[str, tuple[str, ast.Dict]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        value = node.value
        if not isinstance(value, ast.Call) or not isinstance(value.func, ast.Attribute):
            continue
        if value.func.attr != "schema" or not isinstance(value.func.value, ast.Call):
            continue
        view_call = value.func.value
        if call_name(view_call.func) != "semantic_view" or len(view_call.args) != 2:
            continue
        name, base = view_call.args
        if not (
            isinstance(name, ast.Constant)
            and isinstance(name.value, str)
            and isinstance(base, ast.Name)
            and len(value.args) == 1
            and isinstance(value.args[0], ast.Dict)
        ):
            continue
        views[node.targets[0].id] = (base.id, value.args[0])
    return views


def registered_model_views(tree: ast.AST) -> set[str]:
    return {
        call.args[0].id
        for call in method_calls(tree, "model")
        if len(call.args) == 1 and isinstance(call.args[0], ast.Name)
    }


def metric_matches(
    field_spec: ast.expr, model: str, column: str, role: dict[str, object]
) -> bool:
    if not isinstance(field_spec, ast.Call) or call_name(field_spec.func) != "metric_field":
        return False
    metric_call = next(
        (argument for argument in field_spec.args[1:] if isinstance(argument, ast.Call) and call_name(argument.func) == "metric"),
        None,
    )
    if metric_call is None:
        return False
    aggregation = metric_call.args[0] if metric_call.args else None
    source = named_argument(metric_call, "of")
    return (
        string_keyword(metric_call, "name") == role.get("name")
        and isinstance(aggregation, ast.Attribute)
        and aggregation.attr.lower() == role.get("agg")
        and (not role.get("boolean") or bool_keyword(metric_call, "boolean"))
        and isinstance(source, ast.Call)
        and isinstance(source.func, ast.Attribute)
        and source.func.attr == "field"
        and is_name(source.func.value, model)
        and is_string(source.args[0] if source.args else None, column)
    )


def semantic_errors(
    tree: ast.AST, inferred: dict[str, object], promised: set[str], registered_views: set[str]
) -> list[str]:
    errors: list[str] = []
    schemas = base_model_schemas(tree)
    views = semantic_view_schemas(tree)
    for model in sorted(promised):
        columns = ((inferred.get(model) or {}).get("columns") or {})  # type: ignore[union-attr]
        schema = schemas.get(model)
        if schema is None:
            errors.append(f"{model}: missing semantic_model schema")
            continue
        field_specs = {
            column.value: field_spec
            for column, field_spec in zip(schema.keys, schema.values, strict=True)
            if isinstance(column, ast.Constant) and isinstance(column.value, str)
        }
        for column, column_spec in columns.items():
            if column not in field_specs:
                errors.append(f"{model}.{column}: missing source column")
                continue
            for role in column_spec.get("roles", []):
                kind = role.get("kind")
                calls = field_roles(field_specs[column])
                if kind == "primary_key" and not any(call_name(call.func) == kind for call in calls):
                    errors.append(f"{model}.{column}: missing primary_key()")
                if kind == "dimension" and not any(
                    call_name(call.func) == kind and string_keyword(call, "name") == role.get("name")
                    and (not role.get("pii") or bool_keyword(call, "pii"))
                    for call in calls
                ):
                    errors.append(f"{model}.{column}: missing dimension {role.get('name')!r}")
                if kind == "join" and not any(
                    call_name(call.func) == kind
                    and string_keyword(call, "to") == role.get("to_model")
                    and string_keyword(call, "to_column") == role.get("to_column")
                    for call in calls
                ):
                    errors.append(f"{model}.{column}: missing join to {role.get('to_model')!r}")
                if kind == "metric" and not any(
                    base == model
                    and view_name in registered_views
                    and any(metric_matches(field_spec, model, column, role) for field_spec in view_schema.values)
                    for view_name, (base, view_schema) in views.items()
                ):
                    errors.append(f"{model}.{column}: missing metric {role.get('name')!r}")
    return errors


def assigned_strings(tree: ast.AST) -> dict[str, str]:
    strings: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Constant):
            continue
        if not isinstance(node.value.value, str):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                strings[target.id] = node.value.value
    return strings


def method_calls(tree: ast.AST, method: str) -> list[ast.Call]:
    return [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == method
    ]


def named_argument(call: ast.Call, name: str) -> ast.expr | None:
    return next((keyword.value for keyword in call.keywords if keyword.arg == name), None)


def is_name(node: ast.expr | None, name: str) -> bool:
    return isinstance(node, ast.Name) and node.id == name


def is_string(node: ast.expr | None, value: str) -> bool:
    return isinstance(node, ast.Constant) and node.value == value


def profile_services(profile: str) -> tuple[str | None, dict[str, str]]:
    lines = [line.split("#", 1)[0].rstrip() for line in profile.splitlines()]
    metadata_name: str | None = None
    services: dict[str, str] = {}
    in_metadata = False
    current_service: str | None = None
    for line in lines:
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        stripped = line.strip()
        if stripped == "metadata:":
            in_metadata = True
            current_service = None
            continue
        if indent == 0:
            in_metadata = False
        if in_metadata and stripped.startswith("name:"):
            metadata_name = stripped.split(":", 1)[1].strip()
        service = re.fullmatch(r"-\s*name:\s*(\S+)", stripped)
        if service:
            current_service = service.group(1)
            continue
        if current_service and stripped.startswith("driver:"):
            services[current_service] = stripped.split(":", 1)[1].strip()
    return metadata_name, services


def desktop_wiring_errors(spec: str, profile: str, requirements: str) -> list[str]:
    errors: list[str] = []
    profile_name, services = profile_services(profile)
    if profile_name != "desktop-local":
        errors.append("infra-profile metadata.name must be desktop-local")
    expected_services = {
        "duckdb": "nxd:local/duckdb/storage:0.1.0",
        "python-compute": "nxd:local/python/compute:0.1.0",
        "csv-source": "nxd:generic-secrets:1.0.0",
    }
    for name, driver in expected_services.items():
        if services.get(name) != driver:
            errors.append(f"infra-profile service {name!r} must use {driver!r}")

    tree = ast.parse(spec, filename="spec.py")
    bindings = assigned_strings(tree)
    expected_refs = {
        "_duckdb": "/infra-profile/desktop-local#/services/duckdb",
        "_compute": "/infra-profile/desktop-local#/services/python-compute",
        "_csv": "/infra-profile/desktop-local#/services/csv-source",
    }
    for name, reference in expected_refs.items():
        if bindings.get(name) != reference:
            errors.append(f"spec.py {name} must bind {reference!r}")

    products = [node for node in ast.walk(tree) if isinstance(node, ast.Call) and call_name(node.func) == "data_product"]
    if not any(is_string(named_argument(call, "infra_profile"), "desktop-local") for call in products):
        errors.append("spec.py data_product() must set infra_profile=desktop-local")
    scripts = [node for node in ast.walk(tree) if isinstance(node, ast.Call) and call_name(node.func) == "script"]
    if not any(is_string(call.args[0] if call.args else None, "transform/main.py") for call in scripts):
        errors.append("spec.py must use script(transform/main.py)")
    if not any(is_name(call.args[0] if call.args else None, "_compute") for call in method_calls(tree, "compute")):
        errors.append("spec.py must bind python-compute with .compute(_compute)")
    if not any(
        len(call.args) == 1
        and isinstance(call.args[0], ast.List)
        and len(call.args[0].elts) == 1
        and is_name(call.args[0].elts[0], "_csv")
        for call in method_calls(tree, "secrets")
    ):
        errors.append("spec.py must bind csv-source with .secrets([_csv])")
    if not any(
        len(call.args) == 2
        and is_string(call.args[0], "duckdb")
        and isinstance(call.args[1], ast.Call)
        and call_name(call.args[1].func) == "storage"
        and is_name(call.args[1].args[0] if call.args[1].args else None, "_duckdb")
        for call in method_calls(tree, "port")
    ):
        errors.append("spec.py must bind duckdb with .port(duckdb, storage(_duckdb))")

    requirement_lines = {
        line.split("#", 1)[0].strip()
        for line in requirements.splitlines()
        if line.split("#", 1)[0].strip()
    }
    exact_requirements = {"dlt[duckdb]==1.28.2", "duckdb==1.5.4", "pandas==2.3.3"}
    missing = sorted(exact_requirements - requirement_lines)
    errors.extend(f"requirements.txt missing {requirement!r}" for requirement in missing)
    if not any(line.startswith("nxd.data_product[spec]") for line in requirement_lines):
        errors.append("requirements.txt missing nxd.data_product[spec]")
    return errors


def validate_primary_key_tuples(data: Path, keys_by_model: dict[str, set[str]]) -> list[str]:
    errors: list[str] = []
    for model, columns in sorted(keys_by_model.items()):
        if not columns:
            errors.append(f"{model}: no primary_key() field")
            continue
        model_dir = data / model
        csv_paths = sorted(model_dir.glob("*.csv")) if model_dir.is_dir() else []
        if not csv_paths:
            errors.append(f"{model}: no CSV export")
            continue
        seen: set[tuple[str, ...]] = set()
        for csv_path in csv_paths:
            with csv_path.open(newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                missing = columns - set(reader.fieldnames or ())
                if missing:
                    errors.append(f"{model}: missing key columns {sorted(missing)}")
                    continue
                for line, row in enumerate(reader, start=2):
                    key = tuple(row[column] or "" for column in sorted(columns))
                    if any(not value.strip() for value in key):
                        errors.append(f"{model}: null/empty key at {csv_path.name}:{line}")
                        continue
                    if key in seen:
                        errors.append(f"{model}: duplicate key {key!r}")
                    seen.add(key)
    return errors


def main(root: Path) -> None:
    missing = [name for name in REQUIRED if not (root / name).is_file()]
    check("python-only-files", not missing)
    check("no-source-yaml", not any((root / name).exists() for name in FORBIDDEN))

    source_root = (root / "csv-source-path").read_text(encoding="utf-8").strip()
    check("relative-csv-source", bool(source_root) and not Path(source_root).is_absolute())
    data = root / source_root
    check("csv-source-exists", data.is_dir())
    for relative, digest in CSV_SHA256.items():
        path = data / relative
        check(f"csv-preserved:{relative}", path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == digest)

    models = (root / "models.py").read_text(encoding="utf-8")
    spec = (root / "spec.py").read_text(encoding="utf-8")
    profile = (root / "infra-profile.yaml").read_text(encoding="utf-8")
    requirements = (root / "requirements.txt").read_text(encoding="utf-8")
    transform_path = root / "transform/main.py"
    transform = transform_path.read_text(encoding="utf-8")
    check("public-semantic-dsl", all(token in models for token in ("semantic_model", "semantic_view", "metric_field", "metric(")))
    check("no-private-semantic-metadata", "__nxd_semantic__" not in models and "nxd.spec._" not in models)
    check("base-models-promised", all(token in spec for token in (".promise(customers)", ".promise(orders)")))
    model_tree = ast.parse(models, filename=str(root / "models.py"))
    spec_tree = ast.parse(spec, filename=str(root / "spec.py"))
    promised = promised_models(spec_tree)
    model_primary_keys = base_model_primary_keys(model_tree)
    missing_primary_keys = sorted(model for model in promised if not model_primary_keys.get(model))
    check("promised-base-primary-keys", not missing_primary_keys, ", ".join(missing_primary_keys))
    key_errors = validate_primary_key_tuples(
        data, {model: model_primary_keys[model] for model in promised}
    )
    check("promised-base-primary-key-tuples", not key_errors, "; ".join(key_errors))
    inferred_path = root / "inferred_model.json"
    check("inferred-model-present", inferred_path.is_file())
    inferred = json.loads(inferred_path.read_text(encoding="utf-8"))["models"]
    registered_views = registered_model_views(spec_tree)
    check("metric-view-registered", bool(registered_views), "no semantic view passed to .model(...)")
    inferred_errors = semantic_errors(model_tree, inferred, promised, registered_views)
    check("inferred-semantic-roles", not inferred_errors, "; ".join(inferred_errors))
    wiring_errors = desktop_wiring_errors(spec, profile, requirements)
    check("desktop-wiring", not wiring_errors, "; ".join(wiring_errors))
    check("no-semantic-tools", ".semantic_tools(" not in spec)
    check("duckdb-port", ".port(\"duckdb\"" in spec and "DuckDbOutput" in transform and "def ingest(duckdb:" in transform)
    check("transform-contract", all(token in transform for token in ("PHYSICAL_MODELS", "secrets[\"csv_source\"]", "pipeline.default_schema.data_table_names()", "write_disposition=\"replace\"", ".transform-complete")))
    check("no-direct-duckdb-ddl", all(token not in transform for token in ("duckdb.connect", "CREATE TABLE", "CREATE VIEW")))

    try:
        import dlt
        import duckdb
    except ImportError as exc:
        fail(f"missing runtime dependency: {exc}")
    install_transform_stubs()
    module = types.ModuleType("desktop_transform")
    module.__file__ = str(transform_path)
    exec(compile(transform, str(transform_path), "exec"), module.__dict__)  # noqa: S102
    ingest = module.ingest

    physical_models = {directory.name: directory.name for directory in data.iterdir() if directory.is_dir()}
    # The compiled supervisor mapping also contains semantic views registered
    # with .model(...). They are query-time only and must not be ingested.
    model_tables = {**physical_models, "semantic_view_probe": "semantic_view_probe"}
    run = Path(tempfile.mkdtemp())
    output = DuckDbOutput(str(run / "data.duckdb"), "main", model_tables)
    ingest(output, {"csv_source": str(data)})
    connection = duckdb.connect(output.path, read_only=True)
    for model in physical_models:
        expected = sum(csv_count(path) for path in (data / model).glob("*.csv"))
        actual = connection.execute(f"SELECT COUNT(*) FROM main.{model}").fetchone()[0]
        check(f"loaded:{model}", actual == expected)
    check("transform-complete", (run / ".transform-complete").is_file())
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd())
