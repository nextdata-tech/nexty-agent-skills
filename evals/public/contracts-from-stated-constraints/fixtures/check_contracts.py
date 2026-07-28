#!/usr/bin/env python3
"""Validate that stated constraints landed as ENFORCED contracts.

Declaring a contract is not the deliverable — enforcing one is. So this
harness does two things a structural check cannot:

1. It parses `models.py` and requires each stated constraint to appear as a
   real `.constraints(...)` call on the right field.
2. It then re-runs the author's own constraint declarations against a
   **violating** copy of the source and requires them to REJECT it.

Step 2 is the forcing function. A closure that declares constraints which
happen to pass everything — a nullable-everything schema, a bound wide
enough to admit any value — fails here, because passing this check has to
mean the constraints would actually stop bad data.
"""

from __future__ import annotations

import ast
import csv
import sys
from dataclasses import dataclass, field
from pathlib import Path


# The constraints the scenario prompt states in the user's words. Each is
# (model, column, kind, value) where kind is "not_null" or "min".
STATED = [
    ("orders", "order_id", "not_null", None),
    ("orders", "amount_usd", "min", "0"),
]


def fail(message: str) -> None:
    print(f"FAIL {message}")
    raise SystemExit(1)


def check(label: str, condition: bool, detail: str = "") -> None:
    if not condition:
        fail(f"{label}: {detail}" if detail else label)
    print(f"PASS {label}")


@dataclass
class FieldConstraints:
    """What a `.constraints(...)` call declared for one column."""

    nullable: bool | None = None
    minimum: str | None = None
    maximum: str | None = None


@dataclass
class ModelDecl:
    name: str
    constraints: dict[str, FieldConstraints] = field(default_factory=dict)


def literal(node: ast.AST) -> object:
    try:
        return ast.literal_eval(node)
    except (ValueError, SyntaxError):
        return None


def parse_models(source: str) -> dict[str, ModelDecl]:
    """Extract per-model, per-column constraint declarations from models.py.

    Reads the AST rather than importing: the nxd wheel is not installable in
    the eval sandbox, and importing would execute author code.
    """
    tree = ast.parse(source)
    models: dict[str, ModelDecl] = {}

    for call in ast.walk(tree):
        if not isinstance(call, ast.Call):
            continue
        func = call.func
        if not (isinstance(func, ast.Name) and func.id == "semantic_model"):
            continue
        if not call.args:
            continue
        name = literal(call.args[0])
        if not isinstance(name, str):
            continue
        models.setdefault(name, ModelDecl(name=name))

    # `.schema({...})` maps a column name to a field expression; a
    # `.constraints(...)` anywhere inside that expression belongs to it.
    for call in ast.walk(tree):
        if not isinstance(call, ast.Call):
            continue
        func = call.func
        if not (isinstance(func, ast.Attribute) and func.attr == "schema"):
            continue
        owner = model_name_of(func.value)
        if owner is None or not call.args:
            continue
        mapping = call.args[0]
        if not isinstance(mapping, ast.Dict):
            continue
        decl = models.setdefault(owner, ModelDecl(name=owner))
        for key_node, value_node in zip(mapping.keys, mapping.values):
            column = literal(key_node) if key_node is not None else None
            if not isinstance(column, str):
                continue
            found = constraints_in(value_node)
            if found is not None:
                decl.constraints[column] = found

    return models


def model_name_of(node: ast.AST) -> str | None:
    """Walk a chained expression back to its `semantic_model("name")` root."""
    while isinstance(node, ast.Call) or isinstance(node, ast.Attribute):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "semantic_model" and node.args:
                name = literal(node.args[0])
                return name if isinstance(name, str) else None
            node = func
        else:
            node = node.value
    return None


def constraints_in(node: ast.AST) -> FieldConstraints | None:
    """Find a `.constraints(...)` call inside a field expression."""
    for inner in ast.walk(node):
        if not isinstance(inner, ast.Call):
            continue
        func = inner.func
        if not (isinstance(func, ast.Attribute) and func.attr == "constraints"):
            continue
        found = FieldConstraints()
        for kw in inner.keywords:
            value = literal(kw.value)
            if kw.arg == "nullable":
                found.nullable = value if isinstance(value, bool) else None
            elif kw.arg == "min":
                found.minimum = str(value) if value is not None else None
            elif kw.arg == "max":
                found.maximum = str(value) if value is not None else None
        return found
    return None


def violates(row: dict[str, str], column: str, declared: FieldConstraints) -> str | None:
    """Would the declared constraints reject this row's value?"""
    value = row.get(column)

    if declared.nullable is False and (value is None or value == ""):
        return f"{column} is empty but declared non-nullable"

    if value in (None, ""):
        return None

    for bound, comparison in ((declared.minimum, "min"), (declared.maximum, "max")):
        if bound is None:
            continue
        try:
            actual = float(value)
            limit = float(bound)
        except (TypeError, ValueError):
            continue
        if comparison == "min" and actual < limit:
            return f"{column}={value} is below the declared minimum {bound}"
        if comparison == "max" and actual > limit:
            return f"{column}={value} is above the declared maximum {bound}"

    return None


def main() -> None:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    fixtures = Path(__file__).resolve().parent

    models_py = root / "models.py"
    check("models-py-present", models_py.exists(), f"{models_py} missing")

    source = models_py.read_text(encoding="utf-8")
    models = parse_models(source)
    check("models-parsed", bool(models), "no semantic_model(...) declarations found")

    # 1. No custom verify: it fails at boot on the local runtime.
    for banned in ("custom(", ".verify("):
        check(
            f"no-custom-verify{banned.replace('(', '').replace('.', '-')}",
            banned not in source and banned not in (root / "spec.py").read_text(encoding="utf-8"),
            f"{banned} is not runnable on the local runtime; use an in-transform assert",
        )

    # 2. Each stated constraint is declared on the right field.
    for model_name, column, kind, value in STATED:
        decl = models.get(model_name)
        check(f"model-{model_name}-declared", decl is not None, "model absent from models.py")
        assert decl is not None

        declared = decl.constraints.get(column)
        check(
            f"constraint-declared-{model_name}-{column}",
            declared is not None,
            f"no .constraints(...) on {model_name}.{column}",
        )
        assert declared is not None

        if kind == "not_null":
            check(
                f"constraint-not-null-{column}",
                declared.nullable is False,
                f"{column} must declare nullable=False; got nullable={declared.nullable}",
            )
        elif kind == "min":
            check(
                f"constraint-min-{column}",
                declared.minimum is not None and float(declared.minimum) == float(value or 0),
                f"{column} must declare min={value!r}; got min={declared.minimum!r}",
            )

    # 3. THE FORCING FUNCTION. Replay the author's own declarations against a
    #    source that violates them. Constraints that admit this data are not
    #    constraints, however well-formed they look.
    violating = fixtures / "violating" / "orders" / "orders.csv"
    check("violating-fixture-present", violating.exists(), f"{violating} missing")

    with violating.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    check("violating-fixture-readable", bool(rows), "violating fixture has no rows")

    orders = models.get("orders")
    assert orders is not None

    rejections: list[str] = []
    for index, row in enumerate(rows, start=2):
        for column, declared in orders.constraints.items():
            reason = violates(row, column, declared)
            if reason is not None:
                rejections.append(f"row {index}: {reason}")

    check(
        "declared-constraints-reject-bad-data",
        bool(rejections),
        "the declared constraints accept a source containing a negative amount — "
        "a constraint that admits the data it exists to exclude is not enforcing anything",
    )
    print(f"     rejected: {rejections[0]}")

    # 4. The clean fixture must still pass. A constraint so tight it rejects
    #    valid data would break every legitimate run.
    clean = fixtures / "data" / "orders" / "orders.csv"
    with clean.open(encoding="utf-8", newline="") as handle:
        clean_rows = list(csv.DictReader(handle))

    false_positives = [
        f"row {index}: {reason}"
        for index, row in enumerate(clean_rows, start=2)
        for column, declared in orders.constraints.items()
        if (reason := violates(row, column, declared)) is not None
    ]
    check(
        "declared-constraints-accept-good-data",
        not false_positives,
        f"the declared constraints reject valid supplied rows: {false_positives[:2]}",
    )

    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
