"""Runner-side structural checks for the generic OpenAPI source eval."""

from __future__ import annotations

import argparse
import ast
from pathlib import Path
import re
import sys
from typing import Any
from urllib.parse import urlsplit

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools"))
from api_connector_gate import (  # noqa: E402
    find_closure,
    no_hardcoded_url_or_path,
    profile_attributes,
    profile_has_structured_auth,
    string_literals,
    transform_sources,
    is_dlt_rest_call,
    uses_rest_api_resources,
)

_AMBIGUOUS_STATIC_VALUE = object()
AUTH_TOKEN_PLACEHOLDER = "${ORDERS_READ_TOKEN}"


def fail(message: str) -> None:
    print(f"FAIL {message}")
    raise SystemExit(1)


def check(label: str, condition: bool, detail: str = "") -> None:
    if not condition:
        fail(f"{label}: {detail}" if detail else label)
    print(f"PASS {label}")


def _resolve_local_ref(document: dict[str, Any], schema: Any) -> dict[str, Any]:
    if not isinstance(schema, dict):
        raise ValueError("response schema must be an object")
    reference = schema.get("$ref")
    if reference is None:
        return schema
    if not isinstance(reference, str) or not reference.startswith("#/"):
        raise ValueError("response schema must use a local OpenAPI reference")
    resolved: Any = document
    for part in reference[2:].split("/"):
        if not isinstance(resolved, dict) or part not in resolved:
            raise ValueError("response schema contains an unresolved local reference")
        resolved = resolved[part]
    if not isinstance(resolved, dict):
        raise ValueError("response schema reference must resolve to an object")
    return resolved


def contract_expectations(document: dict[str, Any]) -> dict[str, Any]:
    """Read route, auth, envelope and cursor requirements from the OpenAPI file."""
    if not str(document.get("openapi", "")).startswith("3."):
        raise ValueError("source contract must be OpenAPI 3.x")
    servers = document.get("servers")
    if not isinstance(servers, list) or not servers or not isinstance(servers[0], dict):
        raise ValueError("source contract must declare a server URL")
    base_url = servers[0].get("url")
    if not isinstance(base_url, str) or not urlsplit(base_url).hostname:
        raise ValueError("source contract server URL is invalid")

    operations: list[tuple[str, str, dict[str, Any]]] = []
    for route_path, path_item in (document.get("paths") or {}).items():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if method.lower() in {"get", "post", "put", "patch", "delete", "head", "options"}:
                if isinstance(operation, dict):
                    operations.append((route_path, method.upper(), operation))
    if len(operations) != 1:
        raise ValueError("source contract must declare exactly one operation")
    route_path, method, operation = operations[0]

    pagination = operation.get("x-nexty-pagination")
    if not isinstance(pagination, dict):
        raise ValueError("source contract must declare x-nexty-pagination")
    for key in ("cursor_param", "cursor_path", "items_field", "page_size"):
        if key not in pagination:
            raise ValueError(f"pagination contract is missing {key}")

    parameters = operation.get("parameters", [])
    query_names = {
        parameter.get("name")
        for parameter in parameters
        if isinstance(parameter, dict) and parameter.get("in") == "query"
    }
    if pagination["cursor_param"] not in query_names:
        raise ValueError("cursor parameter is not declared as an OpenAPI query parameter")

    response = (operation.get("responses") or {}).get("200")
    media = (response or {}).get("content", {}).get("application/json", {})
    schema = _resolve_local_ref(document, media.get("schema"))
    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        raise ValueError("response envelope must declare schema properties")
    if pagination["items_field"] not in properties or pagination["cursor_path"] not in properties:
        raise ValueError("pagination envelope fields are absent from the response schema")
    items_schema = _resolve_local_ref(document, properties[pagination["items_field"]])
    if items_schema.get("type") != "array":
        raise ValueError("pagination items field must be an array")

    security = operation.get("security", document.get("security", []))
    if (
        not isinstance(security, list)
        or len(security) != 1
        or not isinstance(security[0], dict)
        or len(security[0]) != 1
    ):
        raise ValueError("source contract must declare one bearer security requirement")
    security_name, security_scopes = next(iter(security[0].items()))
    scheme = (document.get("components", {}).get("securitySchemes", {}) or {}).get(
        security_name, {}
    )
    if (scheme.get("type"), str(scheme.get("scheme", "")).lower()) != ("http", "bearer"):
        raise ValueError("source contract security scheme must be HTTP bearer")
    if security_scopes != []:
        raise ValueError("OpenAPI 3.0 bearer security requirements must have an empty scope list")
    scopes = operation.get("x-nexty-required-scopes")
    if not isinstance(scopes, list) or not scopes or any(
        not isinstance(scope, str) or not scope.strip() for scope in scopes
    ):
        raise ValueError("source contract must declare x-nexty-required-scopes")

    resource_name = operation.get("x-nexty-resource-name") or route_path.strip("/").split("/")[-1]
    return {
        "base_url": base_url.rstrip("/"),
        "route_path": route_path,
        "method": method,
        "resource_name": resource_name,
        "scopes": [str(scope) for scope in scopes],
        "pagination": pagination,
        "response_schema": schema,
    }


def _constant(node: ast.AST | None) -> Any:
    if node is None:
        return None
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError):
        return None


def _scope_nodes(scope: ast.AST) -> list[ast.AST]:
    """Return nodes belonging to one lexical scope, excluding nested scopes."""
    nodes: list[ast.AST] = []
    pending = [scope]
    while pending:
        node = pending.pop()
        nodes.append(node)
        pending.extend(
            child for child in ast.iter_child_nodes(node)
            if child is scope or not isinstance(
                child,
                (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda),
            )
        )
    return nodes


def _stored_name_counts(roots: list[ast.AST]) -> dict[str, int]:
    """Count bindings in the supplied lexical scope, including destructuring."""
    counts: dict[str, int] = {}

    def count(name: str | None) -> None:
        if name:
            counts[name] = counts.get(name, 0) + 1

    for root in roots:
        pending = [root]
        while pending:
            node = pending.pop()
            if node is not root and isinstance(
                node,
                (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda),
            ):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    count(node.name)
                continue
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                count(node.id)
            elif isinstance(node, ast.arg):
                count(node.arg)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    count(alias.asname or alias.name.split(".", maxsplit=1)[0])
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node is not root:
                count(node.name)
            elif isinstance(node, ast.ExceptHandler):
                count(node.name)
            elif isinstance(node, (ast.MatchAs, ast.MatchStar)):
                count(node.name)
            elif isinstance(node, ast.MatchMapping):
                count(node.rest)
            pending.extend(ast.iter_child_nodes(node))
    return counts


def _direct_profile_secret_key(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Subscript):
        if isinstance(node.value, ast.Name) and node.value.id == "secrets":
            value = _constant(node.slice)
            return value if isinstance(value, str) else None
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        if (
            isinstance(node.func.value, ast.Name)
            and node.func.value.id == "secrets"
            and node.func.attr == "get"
            and len(node.args) in {1, 2}
            and not node.keywords
        ):
            value = _constant(node.args[0])
            default_node = node.args[1] if len(node.args) == 2 else None
            default = _constant(default_node)
            default_is_safe = (
                len(node.args) == 1
                or (
                    isinstance(default_node, ast.Constant)
                    and default_node.value is None
                )
                or (
                    value == "auth_key_location"
                    and isinstance(default_node, ast.Constant)
                    and default == "header"
                )
            )
            return value if isinstance(value, str) and default_is_safe else None
    return None


def _profile_secret_aliases(scope: ast.AST) -> dict[str, str]:
    """Resolve simple, unambiguous local aliases of runtime profile secrets."""
    assignments: dict[str, list[ast.AST]] = {}
    store_counts = _stored_name_counts([scope])

    for node in _scope_nodes(scope):
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        for target in targets:
            if isinstance(target, ast.Name):
                assignments.setdefault(target.id, []).append(node.value)

    unique = {
        name: values[0]
        for name, values in assignments.items()
        if len(values) == 1 and store_counts.get(name) == 1
    }
    aliases: dict[str, str] = {}
    for _ in range(len(unique) + 1):
        changed = False
        for name, value in unique.items():
            key = _direct_profile_secret_key(value)
            if key is None and isinstance(value, ast.Name):
                key = aliases.get(value.id)
            if key is not None and aliases.get(name) != key:
                aliases[name] = key
                changed = True
        if not changed:
            break
    return aliases


def _reads_profile_secret(
    node: ast.AST | None,
    key: str,
    aliases: dict[str, str] | None = None,
) -> bool:
    if _direct_profile_secret_key(node) == key:
        return True
    return (
        isinstance(node, ast.Name)
        and aliases is not None
        and aliases.get(node.id) == key
    )


def _normalized_profile_secret_read(
    node: ast.AST | None,
    key: str,
    aliases: dict[str, str],
) -> bool:
    """Accept only direct profile reads with simple string case normalization."""
    if _reads_profile_secret(node, key, aliases):
        return True
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"lower", "casefold"}
        and not node.args
        and not node.keywords
        and _reads_profile_secret(node.func.value, key, aliases)
    )


def _static_constant(value: Any) -> Any:
    return _constant(value) if isinstance(value, ast.AST) else value


def _static_string(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _static_string(node.left)
        right = _static_string(node.right)
        return left + right if left is not None and right is not None else None
    return None


def _static_bindings(
    nodes: list[ast.AST],
) -> tuple[dict[str, ast.AST], dict[str, dict[str, Any]]]:
    assignments: dict[str, ast.AST] = {}
    mutations: dict[str, dict[str, Any]] = {}
    ambiguous_names: set[str] = set()
    ambiguous_mutations: set[tuple[str, str]] = set()
    store_counts = _stored_name_counts(nodes)
    for node in nodes:
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        for target in targets:
            if isinstance(target, ast.Name):
                assignments[target.id] = node.value
            elif (
                isinstance(target, ast.Subscript)
                and isinstance(target.value, ast.Name)
                and isinstance(_constant(target.slice), str)
            ):
                key = _constant(target.slice)
                fields = mutations.setdefault(target.value.id, {})
                if key in fields:
                    ambiguous_mutations.add((target.value.id, key))
                fields[key] = node.value
    ambiguous_names.update(name for name, count in store_counts.items() if count != 1)
    for name in ambiguous_names:
        assignments.pop(name, None)
    for name, key in ambiguous_mutations:
        mutations.setdefault(name, {})[key] = _AMBIGUOUS_STATIC_VALUE
    return assignments, mutations


def _static_value(
    node: ast.AST,
    assignments: dict[str, ast.AST],
    mutations: dict[str, dict[str, Any]],
    seen: frozenset[str] = frozenset(),
) -> Any:
    if isinstance(node, ast.Name):
        if node.id not in assignments or node.id in seen:
            return node
        value = _static_value(assignments[node.id], assignments, mutations, seen | {node.id})
        if isinstance(value, dict):
            value = dict(value)
            for key, mutation in mutations.get(node.id, {}).items():
                value[key] = (
                    _AMBIGUOUS_STATIC_VALUE
                    if mutation is _AMBIGUOUS_STATIC_VALUE
                    else _static_value(mutation, assignments, mutations, seen)
                )
        return value
    if isinstance(node, ast.Dict):
        keys = [_constant(key) for key in node.keys]
        if (
            not all(isinstance(key, str) for key in keys)
            or len(keys) != len(set(keys))
        ):
            # This includes ``**mapping`` entries (whose AST key is None) and
            # dynamic keys, either of which could override checked fields.
            return _AMBIGUOUS_STATIC_VALUE
        values: dict[str, Any] = {}
        for resolved_key, value in zip(keys, node.values):
            values[resolved_key] = _static_value(value, assignments, mutations, seen)
        return values
    if isinstance(node, (ast.List, ast.Tuple)):
        return [
            _static_value(value, assignments, mutations, seen)
            for value in node.elts
        ]
    return node


def _resolve_static_node(
    node: ast.AST,
    assignments: dict[str, ast.AST],
    seen: frozenset[str] = frozenset(),
) -> ast.AST:
    if isinstance(node, ast.Name) and node.id in assignments and node.id not in seen:
        return _resolve_static_node(
            assignments[node.id], assignments, seen | {node.id}
        )
    return node


def _static_dict_item_node(
    node: ast.AST,
    key: str,
    assignments: dict[str, ast.AST],
) -> ast.AST | None:
    resolved = _resolve_static_node(node, assignments)
    if not isinstance(resolved, ast.Dict):
        return None
    keys = [_constant(candidate) for candidate in resolved.keys]
    if (
        not all(isinstance(candidate, str) for candidate in keys)
        or len(keys) != len(set(keys))
    ):
        return None
    matches = [
        value
        for candidate, value in zip(resolved.keys, resolved.values)
        if _constant(candidate) == key
    ]
    return matches[0] if len(matches) == 1 else None


def _resolves_to_binding_name(
    node: ast.AST | None,
    expected_name: str,
    assignments: dict[str, ast.AST],
    seen: frozenset[str] = frozenset(),
) -> bool:
    if not isinstance(node, ast.Name):
        return False
    if node.id == expected_name:
        return True
    if node.id in seen or node.id not in assignments:
        return False
    return _resolves_to_binding_name(
        assignments[node.id], expected_name, assignments, seen | {node.id}
    )


def _target_writes_client_auth(target: ast.AST) -> bool:
    if isinstance(target, ast.Subscript):
        if (
            isinstance(target.value, ast.Name)
            and target.value.id == "client_config"
            and _constant(target.slice) == "auth"
        ):
            return True
        return _target_writes_client_auth(target.value)
    if isinstance(target, (ast.Tuple, ast.List)):
        return any(_target_writes_client_auth(element) for element in target.elts)
    if isinstance(target, ast.Starred):
        return _target_writes_client_auth(target.value)
    return False


def _client_auth_write_nodes(roots: list[ast.AST]) -> list[ast.AST]:
    writes: list[ast.AST] = []
    for root in roots:
        for node in _scope_nodes(root):
            if isinstance(node, ast.Assign):
                targets = node.targets
            elif isinstance(node, (ast.AnnAssign, ast.AugAssign, ast.NamedExpr)):
                targets = [node.target]
            elif isinstance(node, ast.Delete):
                targets = node.targets
            else:
                continue
            if any(_target_writes_client_auth(target) for target in targets):
                writes.append(node)
    return writes


def _headers_from_matches_reference(
    modules: list[ast.Module],
    call: ast.Call,
    caller_function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> bool:
    call_module = next(
        (
            module
            for module in modules
            if any(node is call for node in ast.walk(module))
        ),
        None,
    )
    if call_module is None:
        return False
    definitions = [
        node
        for node in call_module.body
        if isinstance(node, ast.FunctionDef) and node.name == "_headers_from"
    ]
    if (
        len(definitions) != 1
        or _stored_name_counts([call_module]).get("_headers_from") != 1
        or _stored_name_counts([caller_function]).get("_headers_from", 0) != 0
    ):
        return False
    function = definitions[0]
    if (
        function.decorator_list
        or len(function.args.args) != 1
        or function.args.args[0].arg != "secrets"
        or function.args.posonlyargs
        or function.args.kwonlyargs
        or function.args.vararg is not None
        or function.args.kwarg is not None
        or function.args.defaults
        or function.args.kw_defaults
    ):
        return False

    reference_path = (
        Path(__file__).resolve().parents[4]
        / "src/nxd-generate-data-product/scripts/api_source_refresh_session.py"
    )
    try:
        reference = ast.parse(reference_path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return False
    reference_functions = [
        node
        for node in reference.body
        if isinstance(node, ast.FunctionDef) and node.name == "_headers_from"
    ]
    if len(reference_functions) != 1:
        return False

    def body_without_docstring(node: ast.FunctionDef) -> str:
        body = list(node.body)
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            body.pop(0)
        return ast.dump(ast.Module(body=body, type_ignores=[]), include_attributes=False)

    return body_without_docstring(function) == body_without_docstring(
        reference_functions[0]
    )


def _auth_is_dispatched_in_bearer_branch(
    call: ast.Call,
    guard: ast.If,
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    scope_nodes: list[ast.AST],
    assignments: dict[str, ast.AST],
) -> bool:
    if _stored_name_counts([function]).get("client_config") != 1:
        return False
    base_node = _resolve_static_node(
        ast.Name(id="client_config", ctx=ast.Load()), assignments
    )
    if not isinstance(base_node, ast.Dict):
        return False
    base_keys = [_constant(key) for key in base_node.keys]
    if (
        not all(isinstance(key, str) for key in base_keys)
        or len(base_keys) != len(set(base_keys))
        or "auth" in base_keys
    ):
        return False
    if not call.args:
        return False
    client_node = _static_dict_item_node(call.args[0], "client", assignments)
    if not (
        isinstance(client_node, ast.Name)
        and client_node.id == "client_config"
        and _resolves_to_binding_name(client_node, "client_config", assignments)
    ):
        return False

    for root in scope_nodes:
        for parent in _scope_nodes(root):
            for child in ast.iter_child_nodes(parent):
                if not (
                    isinstance(child, ast.Name)
                    and child.id == "client_config"
                    and isinstance(child.ctx, ast.Load)
                ):
                    continue
                if child is client_node:
                    continue
                if isinstance(parent, ast.Subscript) and parent.value is child:
                    continue
                return False

    writes = _client_auth_write_nodes(scope_nodes)
    if len(writes) != 1:
        return False
    write = writes[0]
    for root in scope_nodes:
        for statement in _scope_nodes(root):
            if statement is write:
                continue
            if isinstance(statement, ast.Assign):
                values = [statement.value]
            elif isinstance(statement, ast.AnnAssign):
                values = [statement.value] if statement.value is not None else []
            elif isinstance(statement, ast.AugAssign):
                values = [statement.value]
            else:
                continue
            if any(
                isinstance(node, ast.Subscript)
                and _target_writes_client_auth(node)
                for value in values
                for node in ast.walk(value)
            ):
                return False
    return (
        write in guard.body
        and isinstance(write, ast.Assign)
        and len(write.targets) == 1
        and isinstance(write.targets[0], ast.Subscript)
        and isinstance(write.targets[0].value, ast.Name)
        and write.targets[0].value.id == "client_config"
        and _constant(write.targets[0].slice) == "auth"
        and isinstance(write.value, ast.Dict)
    )


def _parent_map(modules: list[ast.Module]) -> dict[ast.AST, ast.AST]:
    parents: dict[ast.AST, ast.AST] = {}
    for module in modules:
        for parent in ast.walk(module):
            for child in ast.iter_child_nodes(parent):
                parents[child] = parent
    return parents


def _enclosing_function(
    node: ast.AST, parents: dict[ast.AST, ast.AST]
) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    parent = parents.get(node)
    while parent is not None:
        if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return parent
        parent = parents.get(parent)
    return None


def _active_bearer_branch(
    call: ast.Call,
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    parents: dict[ast.AST, ast.AST],
    modules: list[ast.Module],
) -> tuple[ast.If, list[ast.AST]] | None:
    secret_aliases = _profile_secret_aliases(function)
    function_store_counts = _stored_name_counts([function])
    if function_store_counts.get("auth_type") != 1:
        return None
    auth_modes = {
        "bearer", "http_basic", "api_key", "oauth2_client_credentials",
    }

    def is_bearer_guard(statement: ast.AST) -> bool:
        test = statement.test if isinstance(statement, ast.If) else None
        return (
            isinstance(test, ast.Compare)
            and isinstance(test.left, ast.Name)
            and test.left.id == "auth_type"
            and len(test.ops) == 1
            and isinstance(test.ops[0], ast.Eq)
            and len(test.comparators) == 1
            and _constant(test.comparators[0]) == "bearer"
        )

    def auth_dispatch_mode(statement: ast.If) -> str | None:
        test = statement.test
        if (
            isinstance(test, ast.Compare)
            and isinstance(test.left, ast.Name)
            and test.left.id == "auth_type"
            and len(test.ops) == 1
            and isinstance(test.ops[0], ast.Eq)
            and len(test.comparators) == 1
        ):
            mode = _constant(test.comparators[0])
            return mode if isinstance(mode, str) else None
        if (
            isinstance(test, ast.Compare)
            and isinstance(test.left, ast.Name)
            and test.left.id == "auth_type"
            and len(test.ops) == 1
            and isinstance(test.ops[0], ast.IsNot)
            and len(test.comparators) == 1
            and isinstance(test.comparators[0], ast.Constant)
            and test.comparators[0].value is None
        ):
            return "<unsupported>"
        return None

    def has_auth_material(node: ast.AST) -> bool:
        sensitive_containers = {
            "auth_type", "auth", "client", "client_config",
            "config", "headers", "request", "session",
        }
        for child in ast.walk(node):
            if isinstance(child, ast.Name):
                if (
                    child.id in sensitive_containers
                    or _profile_key_for_auth_name(child.id) is not None
                    or (secret_aliases.get(child.id) or "").startswith("auth_")
                ):
                    return True
            profile_key = _direct_profile_secret_key(child)
            if profile_key and profile_key.startswith("auth_"):
                return True
        return False

    def is_safe_setup_call(call: ast.Call) -> bool:
        if has_auth_material(call) or not isinstance(call.func, ast.Attribute):
            return False
        receiver = call.func.value
        if not isinstance(receiver, ast.Name):
            return False
        if receiver.id in {"logger", "log"} and call.func.attr in {
            "debug", "info", "warning", "error",
        }:
            return bool(call.args) and not call.keywords and all(
                isinstance(argument, ast.Constant)
                and isinstance(argument.value, (str, int, float, bool, type(None)))
                for argument in call.args
            )
        if receiver.id != "duckdb" or call.func.attr != "execute":
            return False
        if len(call.args) != 1 or call.keywords:
            return False
        query = _static_string(call.args[0])
        if query is None:
            return False
        normalized_query = query.strip()
        if ";" in normalized_query.rstrip(";"):
            return False
        return bool(
            re.match(r"(?is)^select\b", normalized_query)
            or re.match(r"(?is)^create\s+(?:temp|temporary)\s+table\b", normalized_query)
        )

    def is_safe_preamble_call(call: ast.Call) -> bool:
        if _direct_profile_secret_key(call) is not None:
            return True
        if _normalized_profile_secret_read(
            call, "auth_type", secret_aliases
        ):
            return True
        if (
            isinstance(call.func, ast.Name)
            and call.func.id == "tuple"
            and len(call.args) == 1
            and not call.keywords
            and isinstance(call.args[0], (ast.GeneratorExp, ast.ListComp))
            and not has_auth_material(call)
        ):
            nested_calls = [
                node for node in ast.walk(call)
                if isinstance(node, ast.Call) and node is not call
            ]
            if not nested_calls:
                return True
        if (
            isinstance(call.func, ast.Name)
            and call.func.id == "JSONResponseCursorPaginator"
            and not call.args
            and all(
                keyword.arg in {"cursor_path", "cursor_param"}
                and isinstance(keyword.value, ast.Constant)
                and isinstance(keyword.value.value, str)
                for keyword in call.keywords
            )
            and len(call.keywords) == 2
        ):
            return True
        return is_safe_setup_call(call)

    def is_safe_setup_expression(statement: ast.AST) -> bool:
        if not isinstance(statement, ast.Expr) or not isinstance(statement.value, ast.Call):
            return False
        return is_safe_setup_call(statement.value)

    def is_straight_line_statement(statement: ast.AST) -> bool:
        if isinstance(statement, (ast.Assign, ast.AnnAssign)):
            return all(
                is_safe_preamble_call(node)
                for node in ast.walk(statement)
                if isinstance(node, ast.Call)
            )
        return isinstance(statement, (ast.Import, ast.ImportFrom, ast.Pass)) or (
            is_safe_setup_expression(statement)
        )

    def is_safe_bearer_branch_statement(statement: ast.AST) -> bool:
        if (
            isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Subscript)
            and isinstance(statement.targets[0].value, ast.Name)
            and statement.targets[0].value.id == "client_config"
            and _constant(statement.targets[0].slice) == "auth"
            and isinstance(statement.value, ast.Dict)
        ):
            return True
        if isinstance(statement, ast.Assign):
            return (
                len(statement.targets) == 1
                and isinstance(statement.targets[0], ast.Name)
                and _direct_profile_secret_key(statement.value) is not None
            )
        if isinstance(statement, ast.AnnAssign):
            return (
                isinstance(statement.target, ast.Name)
                and _direct_profile_secret_key(statement.value) is not None
            )
        return False

    def is_headers_assignment(statement: ast.AST) -> bool:
        if not isinstance(statement, ast.Assign) or len(statement.targets) != 1:
            return False
        target = statement.targets[0]
        value = statement.value
        return (
            isinstance(target, ast.Name)
            and target.id == "headers"
            and isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id == "_headers_from"
            and len(value.args) == 1
            and isinstance(value.args[0], ast.Name)
            and value.args[0].id == "secrets"
            and not value.keywords
            and _headers_from_matches_reference(modules, call, function)
        )

    def is_config_assignment(statement: ast.AST) -> bool:
        if isinstance(statement, ast.Assign):
            if len(statement.targets) != 1:
                return False
            target = statement.targets[0]
            value = statement.value
        elif isinstance(statement, ast.AnnAssign):
            target = statement.target
            value = statement.value
        else:
            return False
        return (
            isinstance(target, ast.Name)
            and target.id == "config"
            and isinstance(value, ast.Dict)
            and not any(isinstance(node, ast.Call) for node in ast.walk(value))
        )

    def is_optional_headers_block(statement: ast.AST) -> bool:
        if not isinstance(statement, ast.If) or statement.orelse or len(statement.body) != 1:
            return False
        if not isinstance(statement.test, ast.Name) or statement.test.id != "headers":
            return False
        mutation = statement.body[0]
        return (
            isinstance(mutation, ast.Assign)
            and len(mutation.targets) == 1
            and isinstance(mutation.targets[0], ast.Subscript)
            and isinstance(mutation.targets[0].value, ast.Name)
            and mutation.targets[0].value.id == "client_config"
            and _constant(mutation.targets[0].slice) == "headers"
            and isinstance(mutation.value, ast.Name)
            and mutation.value.id == "headers"
        )

    def is_post_dispatch_statement(statement: ast.AST) -> bool:
        return (
            is_config_assignment(statement)
            or is_headers_assignment(statement)
            or is_optional_headers_block(statement)
        )

    def preamble_is_straight_line(statements: list[ast.AST]) -> bool:
        has_docstring = bool(
            function.body
            and isinstance(function.body[0], ast.Expr)
            and isinstance(function.body[0].value, ast.Constant)
            and isinstance(function.body[0].value.value, str)
        )
        return all(
            is_straight_line_statement(statement)
            or (has_docstring and statement is function.body[0])
            for statement in statements
        )

    def profile_auth_type_assignment(statements: list[ast.AST]) -> bool:
        assignments: list[ast.AST] = []
        for statement in statements:
            if isinstance(statement, (ast.Assign, ast.AnnAssign)):
                targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
                if any(isinstance(target, ast.Name) and target.id == "auth_type" for target in targets):
                    assignments.append(statement)
        return (
            len(assignments) == 1
            and function_store_counts.get("auth_type") == 1
            and _normalized_profile_secret_read(
                assignments[0].value, "auth_type", secret_aliases
            )
        )

    def is_safe_unsupported_raise(statement: ast.AST) -> bool:
        if not isinstance(statement, ast.Raise) or statement.cause is not None:
            return False
        exception = statement.exc
        if (
            not isinstance(exception, ast.Call)
            or not isinstance(exception.func, ast.Name)
            or exception.func.id != "ValueError"
            or len(exception.args) != 1
            or exception.keywords
            or function_store_counts.get("ValueError", 0) != 0
            or any(
                _stored_name_counts([module]).get("ValueError", 0) != 0
                for module in modules
            )
        ):
            return False

        def safe_message(node: ast.AST) -> bool:
            if isinstance(node, ast.Constant):
                return isinstance(node.value, str)
            if not isinstance(node, ast.JoinedStr):
                return False
            return all(
                isinstance(part, ast.Constant)
                and isinstance(part.value, str)
                or (
                    isinstance(part, ast.FormattedValue)
                    and isinstance(part.value, ast.Name)
                    and part.value.id == "auth_type"
                    and part.conversion in {-1, ord("r"), ord("s")}
                    and part.format_spec is None
                )
                for part in node.values
            )

        return safe_message(exception.args[0])

    def raises_for_unsupported(suite: list[ast.stmt]) -> bool:
        if len(suite) != 1 or not isinstance(suite[0], ast.If):
            return False
        branch = suite[0]
        seen_modes: set[str] = {"bearer"}
        while True:
            mode = auth_dispatch_mode(branch)
            if mode == "<unsupported>":
                return (
                    len(branch.body) == 1
                    and is_safe_unsupported_raise(branch.body[0])
                    and not branch.orelse
                )
            if mode not in auth_modes or mode in seen_modes:
                return False
            if not branch.body or not all(
                is_straight_line_statement(statement) for statement in branch.body
            ):
                return False
            seen_modes.add(mode)
            if len(branch.orelse) != 1 or not isinstance(branch.orelse[0], ast.If):
                return False
            branch = branch.orelse[0]

    def statement_containing_call() -> ast.stmt | None:
        child: ast.AST = call
        parent = parents.get(child)
        while parent is not None and parent is not function:
            child = parent
            parent = parents.get(parent)
        return child if parent is function and isinstance(child, ast.stmt) else None

    function_statements = function.body
    # The prompt requires config construction and the REST call after explicit
    # auth dispatch. Keep this one straight-line shape; branch-local calls make
    # config provenance and post-dispatch mutation harder to prove.
    call_statement = statement_containing_call()
    if call_statement is None or call_statement not in function_statements:
        return None
    call_index = function_statements.index(call_statement)
    # This scenario returns the dlt source directly. Requiring the call to be
    # the final statement prevents later mutation of the config object from
    # invalidating the statically checked auth/resource values.
    if (
        call_index != len(function_statements) - 1
        or not isinstance(call_statement, ast.Return)
        or call_statement.value is not call
    ):
        return None
    guards = [
        (index, statement)
        for index, statement in enumerate(function_statements[:call_index])
        if isinstance(statement, ast.If) and is_bearer_guard(statement)
    ]
    if len(guards) != 1:
        return None
    guard_index, guard = guards[0]
    before_guard = function_statements[:guard_index]
    after_guard = function_statements[guard_index + 1:call_index]
    if not preamble_is_straight_line(before_guard):
        return None
    if _stored_name_counts(before_guard).get("config", 0) != 0:
        return None
    if not profile_auth_type_assignment(before_guard):
        return None
    if not raises_for_unsupported(guard.orelse):
        return None
    if not all(is_safe_bearer_branch_statement(statement) for statement in guard.body):
        return None
    if not all(is_post_dispatch_statement(statement) for statement in after_guard):
        return None
    if sum(is_config_assignment(statement) for statement in after_guard) != 1:
        return None
    return guard, [*before_guard, *guard.body, *after_guard]


def _cursor_config_value_matches(
    value: Any, cursor_path: str, cursor_param: str
) -> bool:
    if isinstance(value, dict):
        return (
            _static_constant(value.get("type")) == "cursor"
            and _static_constant(value.get("cursor_path")) == cursor_path
            and _static_constant(value.get("cursor_param")) == cursor_param
        )
    if isinstance(value, ast.Call):
        function = value.func
        class_name = function.id if isinstance(function, ast.Name) else (
            function.attr if isinstance(function, ast.Attribute) else ""
        )
        if class_name != "JSONResponseCursorPaginator":
            return False
        keywords = {keyword.arg: keyword.value for keyword in value.keywords if keyword.arg}
        return (
            _constant(keywords.get("cursor_path")) == cursor_path
            and _constant(keywords.get("cursor_param")) == cursor_param
        )
    return False


def active_rest_api_contract(
    modules: list[ast.Module],
    *,
    resource_name: str,
    endpoint_key: str,
    items_field: str,
    cursor_path: str,
    cursor_param: str,
    expected_method: str = "GET",
) -> dict[str, bool]:
    """Check auth and resource semantics on the config passed to one REST call.

    This deliberately accepts a static RESTAPIConfig literal with simple name
    bindings and a ``client_config["auth"]`` mutation inside one function. It
    accepts only a straight-line REST call after explicit bearer dispatch and
    unsupported-auth rejection. Before
    dispatch, only static setup, non-sensitive log messages, and narrowly
    constrained read-only/local temporary DuckDB statements are accepted. The
    public scenario has one operation, so a generated comprehension or dynamic
    config factory would make the oracle less interpretable than this
    deterministic contract check.
    """
    evidence = {
        "auth": False,
        "connector": False,
        "endpoint": False,
        "data_selector": False,
        "pagination": False,
        "read_only_method": False,
    }
    nodes = [node for module in modules for node in ast.walk(module)]
    calls = [
        node for node in nodes
        if isinstance(node, ast.Call)
        and (
            (isinstance(node.func, ast.Name) and node.func.id == "rest_api_resources")
            or (isinstance(node.func, ast.Attribute) and node.func.attr == "rest_api_resources")
        )
    ]
    if len(calls) != 1 or not calls[0].args:
        return evidence

    call = calls[0]
    call_module = next(
        module for module in modules
        if any(node is call for node in ast.walk(module))
    )
    if not is_dlt_rest_call(
        call_module, call, entrypoint="rest_api_resources"
    ):
        return evidence
    evidence["connector"] = True
    parents = _parent_map(modules)
    function = _enclosing_function(call, parents)
    if function is None:
        return evidence
    active_branch = _active_bearer_branch(call, function, parents, modules)
    if active_branch is None:
        return evidence
    guard, scope_nodes = active_branch
    assignments, mutations = _static_bindings(scope_nodes)
    aliases = _profile_secret_aliases(function)
    config = _static_value(call.args[0], assignments, mutations)
    if not isinstance(config, dict):
        return evidence
    client = config.get("client")
    if not isinstance(client, dict):
        return evidence
    auth = client.get("auth")
    evidence["auth"] = (
        _auth_is_dispatched_in_bearer_branch(
            call, guard, function, scope_nodes, assignments
        )
        and
        isinstance(auth, dict)
        and _static_constant(auth.get("type")) == "bearer"
        and _reads_profile_secret(auth.get("token"), "auth_token", aliases)
    )

    resources = config.get("resources")
    if not isinstance(resources, list):
        return evidence
    matching_resources = [
        resource for resource in resources
        if isinstance(resource, dict)
        and _static_constant(resource.get("name")) == resource_name
    ]
    if len(matching_resources) != 1:
        return evidence
    endpoint = matching_resources[0].get("endpoint")
    if not isinstance(endpoint, dict):
        return evidence
    endpoint_method = endpoint.get("method")
    evidence["read_only_method"] = (
        expected_method == "GET"
        and (endpoint_method is None or _static_constant(endpoint_method) == "GET")
    )
    evidence["endpoint"] = _reads_profile_secret(endpoint.get("path"), endpoint_key)
    evidence["data_selector"] = (
        _static_constant(endpoint.get("data_selector")) == items_field
    )
    paginator = endpoint.get("paginator", client.get("paginator"))
    evidence["pagination"] = _cursor_config_value_matches(
        paginator, cursor_path, cursor_param
    )
    return evidence


def _profile_key_for_auth_name(name: str) -> str | None:
    normalized = name.casefold().replace("-", "_")
    if normalized.endswith(("_url", "_uri", "_endpoint")):
        return None
    if "token" in normalized:
        return "auth_token"
    if "api_key" in normalized:
        return "auth_api_key"
    if "client_secret" in normalized or normalized in {"secret", "auth_secret"}:
        return "auth_client_secret"
    if "password" in normalized:
        return "auth_password"
    if "username" in normalized:
        return "auth_username"
    return None


def _profile_bearer_header(node: ast.AST, aliases: dict[str, str]) -> bool:
    """Accept only a Bearer header assembled from the private profile token."""
    if isinstance(node, ast.JoinedStr):
        literals = [value.value for value in node.values if isinstance(value, ast.Constant)]
        formatted = [value for value in node.values if isinstance(value, ast.FormattedValue)]
        return (
            literals in (["Bearer "], ["Bearer ", ""])
            and len(formatted) == 1
            and formatted[0].conversion == -1
            and formatted[0].format_spec is None
            and _reads_profile_secret(formatted[0].value, "auth_token", aliases)
        )
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return (
            _static_string(node.left) == "Bearer "
            and _reads_profile_secret(node.right, "auth_token", aliases)
        ) or (
            _static_string(node.right) == "Bearer "
            and _reads_profile_secret(node.left, "auth_token", aliases)
        )
    return False


def _is_boolean_or_none(value: ast.AST) -> bool:
    return isinstance(value, ast.Constant) and (
        isinstance(value.value, bool) or value.value is None
    )


def has_no_hardcoded_auth_literals(modules: list[ast.Module]) -> bool:
    """Reject literal credentials while allowing labels and profile-derived auth."""
    auth_headers = {"authorization", "proxy-authorization"}
    redaction_markers = {"<redacted>", "redacted", "[redacted]", "***", "..."}

    def is_redaction_value(value: ast.AST) -> bool:
        if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
            return False
        text = value.value.casefold()
        if text in redaction_markers:
            return True
        match = re.fullmatch(r"(?i)Bearer\s+(\S+)", value.value)
        return bool(match and match.group(1).casefold() in redaction_markers)

    for module in modules:
        scopes = [
            node for node in ast.walk(module)
            if isinstance(
                node,
                (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda),
            )
        ]
        for scope in scopes:
            aliases = _profile_secret_aliases(scope)
            for node in _scope_nodes(scope):
                if isinstance(node, ast.Dict):
                    for key, value in zip(node.keys, node.values):
                        name = _static_string(key)
                        if name is None:
                            continue
                        lowered = name.casefold()
                        if lowered in auth_headers:
                            if (
                                not _is_boolean_or_none(value)
                                and not is_redaction_value(value)
                                and not _profile_bearer_header(value, aliases)
                            ):
                                return False
                            continue
                        profile_key = _profile_key_for_auth_name(name)
                        if profile_key and not _reads_profile_secret(value, profile_key, aliases):
                            return False
                if isinstance(node, ast.Tuple) and len(node.elts) == 2:
                    header_name = _static_string(node.elts[0])
                    if header_name and header_name.casefold() in auth_headers:
                        if not is_redaction_value(node.elts[1]) and not _profile_bearer_header(
                            node.elts[1], aliases
                        ):
                            return False
                if isinstance(node, ast.Call):
                    for keyword in node.keywords:
                        if keyword.arg is None:
                            continue
                        lowered = keyword.arg.casefold()
                        if lowered in auth_headers:
                            if (
                                not _is_boolean_or_none(keyword.value)
                                and not is_redaction_value(keyword.value)
                                and not _profile_bearer_header(keyword.value, aliases)
                            ):
                                return False
                            continue
                        profile_key = _profile_key_for_auth_name(keyword.arg)
                        if profile_key and not _reads_profile_secret(
                            keyword.value, profile_key, aliases
                        ):
                            return False
                if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                    value = node.value
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    for target in targets:
                        if isinstance(target, ast.Subscript):
                            header_name = (_static_string(target.slice) or "").casefold()
                            if (
                                header_name in auth_headers
                                and not is_redaction_value(value)
                                and not _profile_bearer_header(value, aliases)
                            ):
                                return False
                            profile_key = _profile_key_for_auth_name(
                                _static_string(target.slice) or ""
                            )
                            if profile_key and not _reads_profile_secret(
                                value, profile_key, aliases
                            ):
                                return False
                        profile_key = (
                            _profile_key_for_auth_name(target.id)
                            if isinstance(target, ast.Name)
                            else None
                        )
                        if profile_key and not _reads_profile_secret(value, profile_key, aliases):
                            return False
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    if (
                        re.fullmatch(r"(?i)Bearer\s+\S+", node.value)
                        and not is_redaction_value(node)
                    ):
                        return False
    return True


def copied_profile_secret_paths(
    root: Path,
    secret_reference: str,
    *,
    intentional_placeholder: str = AUTH_TOKEN_PLACEHOLDER,
) -> list[str]:
    """Find copied credentials, excluding the one documented non-secret token."""
    if not secret_reference or secret_reference == intentional_placeholder:
        return []
    leaked: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file() or path == root / "infra-profile.yaml":
            continue
        if secret_reference in path.read_text(encoding="utf-8", errors="replace"):
            leaked.append(str(path.relative_to(root)))
    return leaked


def readme_reports_no_live_check(readme: str) -> bool:
    """Require a contextual no-live statement and reject conflicting success claims."""
    text = readme.casefold()
    success_claims = (
        r"\b(?:authenticated|authentication|connectivity|connection|live\s+api\s+request|api\s+request)"
        r"[^.!?;\n]{0,60}\b(?:successfully|succeeded|passed|verified|returned\s+20[0-9])\b",
        r"\b(?:successfully|succeeded|passed|verified|returned\s+20[0-9])\b"
        r"[^.!?;\n]{0,60}\b(?:authenticated|authentication|connectivity|connection|live\s+api\s+request|api\s+request)\b",
    )
    negative_claim = re.compile(
        r"\b(?:not(?!\s+only)|never|no|without|yet\s+to)\b|n't\b"
    )
    negative_prefix = re.compile(
        r"(?:\b(?:not(?!\s+only)|never|no|without|yet\s+to)\b|n't\b)"
        r"(?:\s+\w+){0,2}\s*$"
    )
    for clause in re.split(r"[.!?;\n]+", text):
        for pattern in success_claims:
            for match in re.finditer(rf"(?=({pattern}))", clause):
                claim = match.group(1)
                if negative_claim.search(claim):
                    continue
                prefix = clause[max(0, match.start() - 48):match.start()]
                if negative_prefix.search(prefix):
                    continue
                return False

    not_run = r"\b(?:not|never)\s+(?:been\s+)?(?:executed|run|tested|performed|attempted|made|sent)\b"
    negative_context = r"\b(?:live|connectivity|api|endpoint|request|connection|authenticated)\b"
    contextual_negation = (
        rf"{negative_context}[^.!?;\n]{{0,80}}{not_run}"
        rf"|{not_run}[^.!?;\n]{{0,80}}{negative_context}"
    )
    no_request = (
        r"\bno\s+(?:live\s+)?(?:api\s+)?(?:request|connection|call)\s+"
        r"(?:was\s+)?(?:made|performed|attempted|sent)\b"
    )
    return bool(re.search(contextual_negation, text) or re.search(no_request, text))


def read_only_operation(modules: list[ast.Module], expected_method: str) -> bool:
    write_methods = {"POST", "PUT", "PATCH", "DELETE"}
    literals = {
        literal.upper()
        for module in modules
        for literal in string_literals(module)
    }
    return expected_method == "GET" and not (literals & write_methods)


def profile_scopes_match(profile_value: str, expected_scopes: list[str]) -> bool:
    actual_scopes = {
        scope for scope in re.split(r"[\s,]+", profile_value.strip()) if scope
    }
    return actual_scopes == set(expected_scopes)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--fixtures", type=Path, required=True)
    args = parser.parse_args()

    try:
        document = yaml.safe_load((args.fixtures / "openapi.yaml").read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise ValueError("OpenAPI source contract must be an object")
        expected = contract_expectations(document)
    except (OSError, yaml.YAMLError, ValueError, TypeError, KeyError, AttributeError) as exc:
        fail(f"contract: {exc}")

    root = find_closure(args.root)
    required_files = (
        "spec.py",
        "models.py",
        "infra-profile.yaml",
        "transform/main.py",
        "connectivity_check.py",
        "requirements.txt",
        "README.md",
        ".gitignore",
        "SENSITIVE",
    )
    missing_files = [relative for relative in required_files if not (root / relative).is_file()]
    check("closure:required-files", not missing_files, ", ".join(missing_files))
    fields, public_flags = profile_attributes(root)
    auth_ok, auth_detail, fields = profile_has_structured_auth(
        root, expected_token=AUTH_TOKEN_PLACEHOLDER
    )
    check("profile:structured-bearer-auth", auth_ok, auth_detail)
    check("profile:source-kind", fields.get("source_kind") == "rest_api")
    check("profile:base-url", fields.get("base_url", "").rstrip("/") == expected["base_url"])
    check("profile:base-url-public", public_flags.get("base_url") == "true")
    endpoint_key = f"endpoint_{expected['resource_name']}"
    check("profile:endpoint", fields.get(endpoint_key) == expected["route_path"])
    check("profile:endpoint-public", public_flags.get(endpoint_key) == "true")
    check("profile:auth-type-public", public_flags.get("auth_type") == "true")
    check("profile:token-private", public_flags.get("auth_token") == "false")
    check("profile:scopes-public", public_flags.get("required_scopes") == "true")
    check(
        "profile:required-scopes",
        profile_scopes_match(fields.get("required_scopes", ""), expected["scopes"]),
    )
    check("profile:nonempty-token-reference", bool(fields.get("auth_token", "").strip()))

    transform_paths = transform_sources(root)
    modules: list[ast.Module] = []
    parse_errors: list[str] = []
    for path in transform_paths:
        source = path.read_text(encoding="utf-8", errors="replace")
        try:
            modules.append(ast.parse(source, filename=path.name))
        except SyntaxError as exc:
            parse_errors.append(path.name)
    check("transform:exists", bool(transform_paths))
    check("transform:parses", not parse_errors, ", ".join(parse_errors))

    connector_ok, connector_detail = uses_rest_api_resources(root)
    check("connector:dlt-rest", connector_ok, connector_detail)
    host = urlsplit(expected["base_url"]).hostname or ""
    server_path = urlsplit(expected["base_url"]).path.rstrip("/")
    topology_paths = tuple(path for path in (server_path, expected["route_path"]) if path)
    topology_ok, topology_detail = no_hardcoded_url_or_path(root, (host,), topology_paths)
    check("connector:profile-driven-topology", topology_ok, topology_detail)
    pagination = expected["pagination"]
    active_config = active_rest_api_contract(
        modules,
        resource_name=expected["resource_name"],
        endpoint_key=endpoint_key,
        items_field=str(pagination["items_field"]),
        cursor_path=str(pagination["cursor_path"]),
        cursor_param=str(pagination["cursor_param"]),
        expected_method=expected["method"],
    )
    check("connector:active-resource-path-from-profile", active_config["endpoint"])
    check("connector:active-call-is-dlt", active_config["connector"])
    check("auth:dispatches-from-private-profile", active_config["auth"])
    generated_python_modules: list[ast.Module] = []
    for path in root.rglob("*.py"):
        try:
            generated_python_modules.append(
                ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=path.name)
            )
        except SyntaxError:
            if path in transform_paths:
                continue  # The transform parse gate above reports this precisely.
    check(
        "auth:no-hardcoded-credential",
        has_no_hardcoded_auth_literals(generated_python_modules),
    )
    check("pagination:cursor", active_config["pagination"])
    check("payload:response-envelope", active_config["data_selector"])
    check("operations:active-resource-method-is-read-only", active_config["read_only_method"])
    check(
        "operations:read-only",
        read_only_operation(modules, expected["method"]),
    )

    profile_token_reference = fields.get("auth_token", "")
    leaked = copied_profile_secret_paths(root, profile_token_reference)
    check("secret:not-copied-into-generated-files", not leaked, ", ".join(leaked))
    check(
        "sensitivity:artifacts",
        "infra-profile.yaml" in (root / ".gitignore").read_text(encoding="utf-8", errors="replace")
        and "auth_token" in (root / "SENSITIVE").read_text(encoding="utf-8", errors="replace"),
    )
    readme = (root / "README.md").read_text(encoding="utf-8", errors="replace")
    check("honesty:no-live-claim", readme_reports_no_live_check(readme))
    print("\nALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
