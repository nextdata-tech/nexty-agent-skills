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

# Digests of the CSV export this harness ships. They pin the supplied-data
# invariant for the fixture closure: the author must not edit a header or a row
# to manufacture a key. A closure generated over a DIFFERENT export (a derived-
# model closure over transactions/invoices, say) legitimately has none of these
# files; for those, `csv-source-unmodified` degrades to a presence check on the
# base models' own directories, and the no-editing rule is enforced by the
# generating harness that supplied the export.
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


def chain_calls(node: ast.expr) -> list[ast.Call]:
    """Every Call in a fluent chain, outermost first.

    semantic_model("x").description("...").schema({...}) is as valid as the
    bare semantic_model("x").schema({...}), so the builder call and the schema
    call must be located anywhere in the chain rather than assumed adjacent.
    """
    out: list[ast.Call] = []
    while isinstance(node, ast.Call):
        out.append(node)
        node = node.func.value if isinstance(node.func, ast.Attribute) else None
    return out


def chain_schema(chain: list[ast.Call]) -> ast.Dict | None:
    for call in chain:
        if call_name(call.func) in ("schema", "fields") and len(call.args) == 1:
            if isinstance(call.args[0], ast.Dict):
                return call.args[0]
    return None


def base_model_schemas(tree: ast.AST) -> dict[str, ast.Dict]:
    results: dict[str, ast.Dict] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        chain = chain_calls(node.value)
        if not chain:
            continue
        model_call = chain[-1]
        if call_name(model_call.func) != "semantic_model" or not model_call.args:
            continue
        if not isinstance(model_call.args[0], ast.Constant) or not isinstance(model_call.args[0].value, str):
            continue
        schema = chain_schema(chain)
        if schema is None:
            continue
        results[model_call.args[0].value] = schema
    return results


def base_model_descriptions(tree: ast.AST) -> dict[str, str]:
    """Model name -> its description, from either authoring form.

    The chained semantic_model(...).description(...) is the form verified
    against the runtime, but the description= constructor kwarg is pinned in
    the documented signature and is what the vendored nextdata-public-examples
    corpus uses throughout. Rejecting it would fail closures written the way
    the shipped reference corpus writes them, so both are accepted; the prose
    recommends the chained form rather than the checker enforcing it.
    """
    results: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        chain = chain_calls(node.value)
        if not chain:
            continue
        model_call = chain[-1]
        if call_name(model_call.func) != "semantic_model" or not model_call.args:
            continue
        name = model_call.args[0]
        if not isinstance(name, ast.Constant) or not isinstance(name.value, str):
            continue
        text = (string_keyword(model_call, "description")
                or next((joined_string(k.value) or "" for k in model_call.keywords
                         if k.arg == "description"), "") or "")
        for call in chain:
            if call_name(call.func) == "description" and call.args:
                joined = joined_string(call.args[0])
                if joined:
                    text = joined
        if text.strip():
            results[name.value] = text.strip()
    return results


def joined_string(node: ast.expr) -> str | None:
    """A str constant, or the literal parts of an f-string.

    Adjacent string literals are folded into a single ast.Constant by the
    parser, so the multi-line parenthesised form needs no special handling.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts = [p.value for p in node.values
                 if isinstance(p, ast.Constant) and isinstance(p.value, str)]
        # An f-string of pure interpolations has no literal parts but is still
        # an authored description; fall back to the source so this accepts the
        # same set self_check.py's desc_str() does.
        return "".join(parts) or ast.unparse(node)
    return None


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
        chain = chain_calls(node.value)
        if not chain:
            continue
        view_call = chain[-1]
        if call_name(view_call.func) != "semantic_view" or len(view_call.args) != 2:
            continue
        name, base = view_call.args
        schema = chain_schema(chain)
        if not (
            isinstance(name, ast.Constant)
            and isinstance(name.value, str)
            and isinstance(base, ast.Name)
            and schema is not None
        ):
            continue
        views[node.targets[0].id] = (base.id, schema)
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


def has_description(call: ast.Call) -> bool:
    """A non-empty description= on this call."""
    for keyword in call.keywords:
        if keyword.arg != "description":
            continue
        text = joined_string(keyword.value)
        if text is None and isinstance(keyword.value, ast.BinOp):
            text = ast.unparse(keyword.value)
        if text and text.strip():
            return True
    return False


def annotation_errors(
    tree: ast.AST, inferred: dict[str, object], promised: set[str], registered_views: set[str]
) -> list[str]:
    """Descriptions the inferred model supplied must survive into models.py.

    describe_model is the only surface the querying agent reads, so a concept
    placed with its name but not its description arrives as a bare label. The
    inferred_model.json handoff carries a description on every dimension and
    metric and on each model; this asserts they were carried through, and that
    they were put where the compiler actually reads them.
    """
    errors: list[str] = []
    schemas = base_model_schemas(tree)
    views = semantic_view_schemas(tree)
    descriptions = base_model_descriptions(tree)

    # A description on the field()/metric_field() WRAPPER becomes an attribute
    # description: it reaches the structural data_model block and never
    # describe_model. The author believes the concept is documented and it is
    # not, so this is an error rather than a warning.
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if call_name(node.func) in ("field", "metric_field") and any(
            keyword.arg == "description" for keyword in node.keywords
        ):
            errors.append(
                f"description= on {call_name(node.func)}() never reaches "
                f"describe_model — move it inside dimension(...) / metric(...)"
            )

    for model in sorted(promised):
        spec = inferred.get(model) or {}
        if (spec.get("description") or "").strip() and not descriptions.get(model):  # type: ignore[union-attr]
            errors.append(
                f"{model}: the inferred model supplied a description and the "
                f"model declares none — list_models and describe_model show it"
            )
        schema = schemas.get(model)
        if schema is None:
            continue
        field_specs = {
            column.value: field_spec
            for column, field_spec in zip(schema.keys, schema.values, strict=True)
            if isinstance(column, ast.Constant) and isinstance(column.value, str)
        }
        for column, column_spec in ((spec.get("columns") or {})).items():  # type: ignore[union-attr]
            if column not in field_specs:
                continue
            for role in column_spec.get("roles", []):
                wanted = (role.get("description") or "").strip()
                if not wanted:
                    continue
                kind = role.get("kind")
                if kind == "dimension":
                    matched = [
                        call for call in field_roles(field_specs[column])
                        if call_name(call.func) == "dimension"
                        and string_keyword(call, "name") == role.get("name")
                    ]
                    if matched and not any(has_description(call) for call in matched):
                        errors.append(
                            f"{model}.{column}: dimension {role.get('name')!r} "
                            f"placed without the supplied description"
                        )
                if kind == "metric":
                    for view_name, (base, view_schema) in views.items():
                        if base != model or view_name not in registered_views:
                            continue
                        for field_spec in view_schema.values:
                            if not metric_matches(field_spec, model, column, role):
                                continue
                            metric_call = next(
                                argument for argument in field_spec.args[1:]
                                if isinstance(argument, ast.Call)
                                and call_name(argument.func) == "metric"
                            )
                            if not has_description(metric_call):
                                errors.append(
                                    f"{model}.{column}: metric "
                                    f"{role.get('name')!r} placed without the "
                                    f"supplied description"
                                )
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


def string_tuple_constant(tree: ast.AST, name: str) -> tuple[str, ...] | None:
    """Read a module-level ``NAME = ("a", "b")`` string tuple/list literal."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name) or target.id != name:
            continue
        if not isinstance(node.value, (ast.Tuple, ast.List)):
            continue
        if all(isinstance(element, ast.Constant) and isinstance(element.value, str) for element in node.value.elts):
            return tuple(element.value for element in node.value.elts)  # type: ignore[union-attr]
    return None


def physical_model_names(tree: ast.AST) -> tuple[tuple[str, ...], tuple[str, ...], list[str]]:
    """Resolve (BASE_MODELS, DERIVED_MODELS) from the transform's own constants.

    The closure declares its landed tables; the harness must not re-derive them
    from the `data/` listing, which by design cannot represent a derived model.
    `PHYSICAL_MODELS = BASE_MODELS + DERIVED_MODELS` is the contract, so a
    closure with no derived models may omit DERIVED_MODELS entirely.
    """
    errors: list[str] = []
    base = string_tuple_constant(tree, "BASE_MODELS")
    derived = string_tuple_constant(tree, "DERIVED_MODELS")
    if base is None:
        errors.append("transform must declare BASE_MODELS as a literal string tuple")
        base = ()
    if derived is None:
        derived = ()
    overlap = sorted(set(base) & set(derived))
    if overlap:
        errors.append(f"models in both BASE_MODELS and DERIVED_MODELS: {overlap}")
    return base, derived, errors


def derived_resource_flatness_errors(tree: ast.AST, derived: tuple[str, ...]) -> list[str]:
    """Reject nested literals yielded by a derived resource.

    dlt routes a nested dict/list to a `parent__field` child table, which breaks
    the read-back assert; and the pinned desktop venv has no pyarrow, so a
    DataFrame cannot be routed at all. Both failures are statically visible when
    the resource yields dict literals, which is the shape the contract requires.
    """
    if not derived:
        return []
    errors: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if not any(
            isinstance(decorator, ast.Call)
            and call_name(decorator.func) == "resource"
            for decorator in node.decorator_list
        ):
            continue
        for inner in ast.walk(node):
            if isinstance(inner, ast.Call) and call_name(inner.func) in {"DataFrame", "from_records", "from_dict"}:
                errors.append(f"{node.name}: yields a DataFrame; the pinned venv has no pyarrow")
        for inner in ast.walk(node):
            if not isinstance(inner, ast.Dict):
                continue
            for value in inner.values:
                if isinstance(value, (ast.Dict, ast.List, ast.Set)):
                    errors.append(
                        f"{node.name}: nested value in yielded dict spawns a dlt child table"
                    )
    return errors


def derived_rows_are_flat(rows: object, model: str) -> list[str]:
    """Runtime flatness assert over the rows a derived model actually landed."""
    errors: list[str] = []
    if not isinstance(rows, list):
        return errors
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"{model}: row {index} is {type(row).__name__}, expected dict")
            continue
        for column, value in row.items():
            if isinstance(value, (dict, list, set, tuple)):
                errors.append(f"{model}.{column}: nested {type(value).__name__} at row {index}")
    return errors


def validate_primary_key_tuples(data: Path, keys_by_model: dict[str, set[str]]) -> list[str]:
    """Prove each BASE model's declared key over its supplied CSV export.

    Derived models are excluded by the caller: they have no `data/<name>/`
    directory by design, and their key is proven post-run against the landed
    table plus the transform's own in-memory assert.
    """
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


def executable_source(source: str) -> str:
    """Return the source with comments and docstrings removed.

    The DDL ban below is a raw substring scan, and it must judge what the
    transform DOES, not what its prose says. A docstring stating "no raw
    duckdb.connect, no DDL" is the closure honouring the ban, yet a scan over
    the whole file reads it as a violation. Stripping non-executable text keeps
    the ban exactly as strict over real code while removing that false positive:
    a string used as an actual DDL argument is an expression, not a docstring,
    and survives this pass.
    """
    tree = ast.parse(source)
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        body = getattr(node, "body", [])
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            docstrings.add(id(body[0].value))

    class StripDocstrings(ast.NodeTransformer):
        def visit_Expr(self, node: ast.Expr):  # noqa: N802
            if isinstance(node.value, ast.Constant) and id(node.value) in docstrings:
                return None
            return node

    stripped = StripDocstrings().visit(tree)
    ast.fix_missing_locations(stripped)
    return ast.unparse(stripped)


DDL_TOKENS = ("duckdb.connect", "CREATE TABLE", "CREATE VIEW")
DDL_STATEMENTS = ("create table", "create view", "create or replace")


def out_of_port_write_errors(tree: ast.AST) -> list[str]:
    """Catch writes outside the dlt port that the literal token scan misses.

    The substring ban reads `duckdb.connect(...)` but not `from duckdb import
    connect as c; c(...)`, and reads a `CREATE TABLE` literal but not one
    assembled or cased differently. Writing outside the port escapes the
    pin-substituted staging path that the publish step promotes crash-safely,
    so the alias route is closed here rather than left to the substring scan.
    """
    errors: list[str] = []
    aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "duckdb" and alias.asname:
                    aliases.add(alias.asname)
        elif isinstance(node, ast.ImportFrom) and node.module == "duckdb":
            for alias in node.names:
                if alias.name == "connect":
                    errors.append("imports duckdb.connect directly; write through the dlt port")
                    aliases.add(alias.asname or alias.name)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "connect" and isinstance(func.value, ast.Name) and func.value.id in aliases:
            errors.append(f"{func.value.id}.connect(...) opens a write outside the dlt port")
        if isinstance(func, ast.Name) and func.id in aliases and func.id != "duckdb":
            errors.append(f"{func.id}(...) opens a duckdb connection outside the dlt port")
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            lowered = " ".join(node.value.lower().split())
            for statement in DDL_STATEMENTS:
                if statement in lowered:
                    errors.append(f"DDL statement in a string literal: {statement!r}")
                    break
    return sorted(set(errors))


def landed_key_errors(connection, model: str, columns: set[str]) -> list[str]:
    """Prove a derived model's declared key over the table it actually landed."""
    ordered = sorted(columns)
    projection = ", ".join(ordered)
    predicate = " OR ".join(f"{column} IS NULL" for column in ordered)
    errors: list[str] = []
    nulls = connection.execute(
        f"SELECT COUNT(*) FROM main.{model} WHERE {predicate}"
    ).fetchone()[0]
    if nulls:
        errors.append(f"{model}: {nulls} rows with a null key column {ordered}")
    total, distinct = connection.execute(
        f"SELECT COUNT(*), COUNT(DISTINCT ({projection})) FROM main.{model}"
    ).fetchone()
    if total != distinct:
        errors.append(f"{model}: key {ordered} not unique ({total} rows, {distinct} distinct)")
    return errors


def main(root: Path) -> None:
    missing = [name for name in REQUIRED if not (root / name).is_file()]
    check("python-only-files", not missing)
    check("no-source-yaml", not any((root / name).exists() for name in FORBIDDEN))

    source_root = (root / "csv-source-path").read_text(encoding="utf-8").strip()
    check("relative-csv-source", bool(source_root) and not Path(source_root).is_absolute())
    data = root / source_root
    check("csv-source-exists", data.is_dir())
    # The shipped fixture export is digest-pinned. A closure built over another
    # export has none of these paths and is checked for presence instead.
    for relative, digest in CSV_SHA256.items():
        path = data / relative
        if not path.is_file():
            continue
        check(f"csv-preserved:{relative}", hashlib.sha256(path.read_bytes()).hexdigest() == digest)

    # Skipping absent pinned paths is deliberate (above), but on its own it is a
    # bypass: rewriting rows into a DIFFERENT filename under a pinned model's
    # own directory escapes the digest entirely while `loaded:` row counts still
    # pass. If the directory is present, every CSV in it must be a pinned name.
    pinned_by_dir: dict[str, set[str]] = {}
    for relative in CSV_SHA256:
        parent, _, name = relative.rpartition("/")
        pinned_by_dir.setdefault(parent, set()).add(name)
    for parent, names in pinned_by_dir.items():
        directory = data / parent if parent else data
        if not directory.is_dir():
            continue
        unpinned = sorted(p.name for p in directory.glob("*.csv") if p.name not in names)
        check(
            f"csv-no-unpinned:{parent or '.'}",
            not unpinned,
            f"unpinned CSVs alongside a pinned export: {unpinned}",
        )

    models = (root / "models.py").read_text(encoding="utf-8")
    spec = (root / "spec.py").read_text(encoding="utf-8")
    profile = (root / "infra-profile.yaml").read_text(encoding="utf-8")
    requirements = (root / "requirements.txt").read_text(encoding="utf-8")
    transform_path = root / "transform/main.py"
    transform = transform_path.read_text(encoding="utf-8")
    check("public-semantic-dsl", all(token in models for token in ("semantic_model", "semantic_view", "metric_field", "metric(")))
    check("no-private-semantic-metadata", "__nxd_semantic__" not in models and "nxd.spec._" not in models)
    model_tree = ast.parse(models, filename=str(root / "models.py"))
    spec_tree = ast.parse(spec, filename=str(root / "spec.py"))
    transform_tree = ast.parse(transform, filename=str(transform_path))
    promised = promised_models(spec_tree)

    base_models, derived_models, model_name_errors = physical_model_names(transform_tree)
    check("physical-model-declaration", not model_name_errors, "; ".join(model_name_errors))
    physical = tuple(base_models) + tuple(derived_models)

    # The naming invariant, in both directions: every landed table is promised,
    # every base model has a data/ directory, and no derived model does.
    invariant_errors: list[str] = []
    invariant_errors.extend(
        f"{model}: in PHYSICAL_MODELS but not .promise()d" for model in sorted(set(physical) - promised)
    )
    data_dirs = {directory.name for directory in data.iterdir() if directory.is_dir()}
    invariant_errors.extend(
        f"{model}: base model has no data/{model}/ directory" for model in sorted(set(base_models) - data_dirs)
    )
    invariant_errors.extend(
        f"{model}: derived model must not have a data/{model}/ directory"
        for model in sorted(set(derived_models) & data_dirs)
    )
    invariant_errors.extend(
        f"{model}: data/{model}/ directory has no base model" for model in sorted(data_dirs - set(base_models))
    )
    check("physical-models-match-data-dirs", not invariant_errors, "; ".join(invariant_errors))
    check("models-promised", bool(physical) and set(physical) <= promised)

    model_primary_keys = base_model_primary_keys(model_tree)
    missing_primary_keys = sorted(model for model in promised if not model_primary_keys.get(model))
    check("promised-primary-keys", not missing_primary_keys, ", ".join(missing_primary_keys))
    # Base keys are proven against the supplied export. Derived keys cannot be —
    # there is no export — so they are proven post-run against the landed table.
    key_errors = validate_primary_key_tuples(
        data, {model: model_primary_keys[model] for model in promised if model in base_models}
    )
    check("promised-base-primary-key-tuples", not key_errors, "; ".join(key_errors))
    flatness_errors = derived_resource_flatness_errors(transform_tree, derived_models)
    check("derived-resources-flat", not flatness_errors, "; ".join(flatness_errors))
    inferred_path = root / "inferred_model.json"
    check("inferred-model-present", inferred_path.is_file())
    inferred = json.loads(inferred_path.read_text(encoding="utf-8"))["models"]
    registered_views = registered_model_views(spec_tree)
    check("metric-view-registered", bool(registered_views), "no semantic view passed to .model(...)")
    inferred_errors = semantic_errors(model_tree, inferred, promised, registered_views)
    check("inferred-semantic-roles", not inferred_errors, "; ".join(inferred_errors))
    annotation_issues = annotation_errors(model_tree, inferred, promised, registered_views)
    check("annotations-carried-through", not annotation_issues, "; ".join(annotation_issues))
    wiring_errors = desktop_wiring_errors(spec, profile, requirements)
    check("desktop-wiring", not wiring_errors, "; ".join(wiring_errors))
    check("no-semantic-tools", ".semantic_tools(" not in spec)
    check("duckdb-port", ".port(\"duckdb\"" in spec and "DuckDbOutput" in transform and "def ingest(duckdb:" in transform)
    check("transform-contract", all(token in transform for token in ("PHYSICAL_MODELS", "secrets[\"csv_source\"]", "pipeline.default_schema.data_table_names()", "write_disposition=\"replace\"", ".transform-complete")))
    # Scans executable code only — a docstring naming the ban is not a breach.
    # The token list is unchanged: writing outside the dlt port is still fatal,
    # which is what keeps output inside the pin-substituted staging path.
    transform_code = executable_source(transform)
    check("no-direct-duckdb-ddl", all(token not in transform_code for token in DDL_TOKENS))
    out_of_port = out_of_port_write_errors(ast.parse(transform_code))
    check("no-out-of-port-write", not out_of_port, "; ".join(out_of_port))

    try:
        import dlt
        import duckdb
    except ImportError as exc:
        fail(f"missing runtime dependency: {exc}")
    install_transform_stubs()
    module = types.ModuleType("desktop_transform")
    module.__file__ = str(transform_path)
    # Register before exec: dlt's @dlt.resource decorator reflects the defining
    # function's module (inspect.getmodule) to build its spec, and a module
    # missing from sys.modules resolves to None there. Base CSV readers never
    # hit that path; a derived model's decorated resource always does.
    sys.modules["desktop_transform"] = module
    exec(compile(transform, str(transform_path), "exec"), module.__dict__)  # noqa: S102
    ingest = module.ingest

    # model_tables is the supervisor's identity map over PHYSICAL_MODELS — base
    # AND derived. Building it from the data/ listing would KeyError the moment a
    # derived model resolves its table name.
    model_tables = {model: model for model in physical}
    # The compiled supervisor mapping also contains semantic views registered
    # with .model(...). They are query-time only and must not be ingested.
    model_tables["semantic_view_probe"] = "semantic_view_probe"
    run = Path(tempfile.mkdtemp())
    output = DuckDbOutput(str(run / "data.duckdb"), "main", model_tables)
    ingest(output, {"csv_source": str(data)})
    connection = duckdb.connect(output.path, read_only=True)

    # Base models land 1:1 with their export, so row counts must match exactly.
    for model in base_models:
        expected = sum(csv_count(path) for path in (data / model).glob("*.csv"))
        actual = connection.execute(f"SELECT COUNT(*) FROM main.{model}").fetchone()[0]
        check(f"loaded:{model}", actual == expected)

    # Derived models have no export to count against. What is checkable here is
    # that the table exists, carries rows, and honours its declared key — the
    # in-transform assert (Step 3b) owns the semantic reconciliation.
    for model in derived_models:
        rows = connection.execute(f"SELECT COUNT(*) FROM main.{model}").fetchone()[0]
        check(f"derived-landed:{model}", rows > 0, "derived model landed zero rows")
        derived_key_errors = landed_key_errors(connection, model, model_primary_keys.get(model, set()))
        check(f"derived-key:{model}", not derived_key_errors, "; ".join(derived_key_errors))
        # A nested value survives as a flattened `field__key` column (or, for a
        # list, as a child table caught by no-child-tables below). Either way
        # the model no longer matches the schema its semantic roles describe.
        schema = base_model_schemas(model_tree).get(model)
        declared = {
            key.value
            for key in (schema.keys if schema is not None else [])
            if isinstance(key, ast.Constant) and isinstance(key.value, str)
        }
        landed_columns = {
            name
            for (name,) in connection.execute(
                "SELECT column_name FROM information_schema.columns "
                f"WHERE table_schema = 'main' AND table_name = '{model}'"
            ).fetchall()
            if not name.startswith("_dlt")
        }
        nested = sorted(column for column in landed_columns - declared if "__" in column)
        check(
            f"derived-flat:{model}",
            not nested,
            f"nested values flattened into {nested!r}; yield scalar-only dicts",
        )

    # A nested value would have made dlt emit a `parent__field` child table.
    # Assert the landed tables are exactly the promised physical models.
    # dlt's own _dlt_* bookkeeping tables are expected and are not data tables;
    # this mirrors pipeline.default_schema.data_table_names().
    landed = {
        name
        for (name,) in connection.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'main' AND table_name NOT LIKE '\\_dlt\\_%' ESCAPE '\\'"
        ).fetchall()
    }
    check(
        "no-child-tables",
        landed == set(physical),
        f"landed {sorted(landed)!r}, expected {sorted(physical)!r}",
    )
    check("transform-complete", (run / ".transform-complete").is_file())
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd())
