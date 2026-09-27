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
PROBE_ALLOWED_MODULE_IMPORTS = {
    "json",
    "os",
    "sys",
    "urllib.error",
    "urllib.request",
}
PROBE_ALLOWED_FROM_IMPORTS = {
    "__future__": {"annotations"},
    "typing": {"Any"},
    "urllib.error": {"HTTPError", "URLError"},
    "urllib.request": {"Request", "urlopen"},
}
ALTERNATE_ENVIRONMENT_API_ROOTS = {
    "posix",
    "nt",
    "ctypes",
    "dotenv",
    "decouple",
    "dynaconf",
    "environs",
    "envparse",
}


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
                or (
                    isinstance(value, str)
                    and value.startswith("auth_")
                    and isinstance(default_node, ast.Constant)
                    and default == ""
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


def _runtime_probe_token_read(node: ast.AST | None) -> bool:
    """Recognize the probe's narrowly scoped runtime token input."""
    if (
        not isinstance(node, ast.Call)
        or _dotted_name(node.func) not in {"os.getenv", "os.environ.get"}
        or node.keywords
        or len(node.args) not in {1, 2}
        or _constant(node.args[0]) != "ORDERS_READ_TOKEN"
    ):
        return False
    return len(node.args) == 1 or (
        isinstance(node.args[1], ast.Constant)
        and node.args[1].value in {"", None}
    )


def _runtime_probe_os_access_is_safe(module: ast.Module) -> bool:
    """Allow only direct reads through one unshadowed ``import os`` binding."""
    parents = {
        child: parent
        for parent in ast.walk(module)
        for child in ast.iter_child_nodes(parent)
    }
    allowed_imports = 0
    for node in ast.walk(module):
        if isinstance(node, ast.Match):
            return False
        if isinstance(node, ast.Import):
            if node not in module.body:
                return False
            for alias in node.names:
                if (
                    alias.asname is not None
                    or alias.name not in PROBE_ALLOWED_MODULE_IMPORTS
                ):
                    return False
                if alias.name == "os":
                    allowed_imports += 1
        elif isinstance(node, ast.ImportFrom):
            allowed_names = PROBE_ALLOWED_FROM_IMPORTS.get(node.module or "")
            if (
                node not in module.body
                or node.level != 0
                or allowed_names is None
                or not node.names
                or any(
                    alias.asname is not None or alias.name not in allowed_names
                    for alias in node.names
                )
            ):
                return False
        elif isinstance(node, ast.Name) and node.id == "os":
            if not isinstance(node.ctx, ast.Load):
                return False
            parent = parents.get(node)
            if not isinstance(parent, ast.Attribute) or parent.value is not node:
                return False
            if parent.attr == "getenv":
                call = parents.get(parent)
                if not (
                    isinstance(call, ast.Call)
                    and call.func is parent
                    and _runtime_probe_token_read(call)
                ):
                    return False
            elif parent.attr == "environ":
                get_attribute = parents.get(parent)
                call = parents.get(get_attribute) if get_attribute is not None else None
                if not (
                    isinstance(get_attribute, ast.Attribute)
                    and get_attribute.value is parent
                    and get_attribute.attr == "get"
                    and isinstance(call, ast.Call)
                    and call.func is get_attribute
                    and _runtime_probe_token_read(call)
                ):
                    return False
            else:
                return False
        elif isinstance(node, ast.arg) and node.arg == "os":
            return False
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name == "os":
                return False
        elif isinstance(node, (ast.Global, ast.Nonlocal)) and "os" in node.names:
            return False
        elif isinstance(node, ast.ExceptHandler) and node.name == "os":
            return False
        elif isinstance(node, ast.MatchAs) and node.name == "os":
            return False
        elif isinstance(node, ast.MatchStar) and node.name == "os":
            return False
        elif isinstance(node, ast.MatchMapping) and node.rest == "os":
            return False

    if allowed_imports != 1:
        return False

    # The key literal is privileged: it may occur only as the first argument
    # of one of the exact direct-read forms recognized above.
    for node in ast.walk(module):
        if not isinstance(node, ast.Constant) or node.value != "ORDERS_READ_TOKEN":
            continue
        parent = parents.get(node)
        if not (
            isinstance(parent, ast.Call)
            and parent.args
            and parent.args[0] is node
            and _runtime_probe_token_read(parent)
        ):
            return False
    return True


def _uses_alternate_environment_api(module: ast.Module) -> bool:
    """Reject known environment-mutating libraries throughout the closure."""
    for node in ast.walk(module):
        if isinstance(node, ast.Import):
            if any(
                alias.name.split(".", 1)[0] in ALTERNATE_ENVIRONMENT_API_ROOTS
                for alias in node.names
            ):
                return True
        elif isinstance(node, ast.ImportFrom) and (
            (node.module or "").split(".", 1)[0]
            in ALTERNATE_ENVIRONMENT_API_ROOTS
        ):
            return True
    return False


def _os_module_is_not_aliased(module: ast.Module) -> bool:
    """Reject escaping the direct ``os`` name in modules with no env exception."""
    parents = {
        child: parent
        for parent in ast.walk(module)
        for child in ast.iter_child_nodes(parent)
    }
    for node in ast.walk(module):
        if isinstance(node, ast.Import):
            for alias in node.names:
                bound_name = alias.asname or alias.name.split(".", 1)[0]
                if alias.name == "os" or bound_name == "os":
                    if not (
                        node in module.body
                        and alias.name == "os"
                        and alias.asname is None
                    ):
                        return False
        elif isinstance(node, ast.ImportFrom):
            if any((alias.asname or alias.name) == "os" for alias in node.names):
                return False
        elif isinstance(node, ast.Name) and node.id == "os":
            if not isinstance(node.ctx, ast.Load):
                return False
            parent = parents.get(node)
            if not isinstance(parent, ast.Attribute) or parent.value is not node:
                return False
        elif isinstance(node, ast.arg) and node.arg == "os":
            return False
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name == "os":
                return False
        elif isinstance(node, (ast.Global, ast.Nonlocal)) and "os" in node.names:
            return False
        elif isinstance(node, ast.ExceptHandler) and node.name == "os":
            return False
        elif isinstance(node, ast.MatchAs) and node.name == "os":
            return False
        elif isinstance(node, ast.MatchStar) and node.name == "os":
            return False
        elif isinstance(node, ast.MatchMapping) and node.rest == "os":
            return False
    return True


def _runtime_probe_token_aliases(scope: ast.AST) -> set[str]:
    """Resolve aliases from the named environment input, never profile/literals."""
    assignments: dict[str, list[ast.AST | None]] = {}
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

    aliases: set[str] = set()
    if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
        positional = scope.args.posonlyargs + scope.args.args
        defaulted = {
            argument.arg
            for argument in positional[len(positional) - len(scope.args.defaults):]
        } if scope.args.defaults else set()
        defaulted.update(
            argument.arg
            for argument, default in zip(scope.args.kwonlyargs, scope.args.kw_defaults)
            if default is not None
        )
        aliases.update(
            argument.arg
            for argument in positional + scope.args.kwonlyargs
            if argument.arg not in defaulted
            and store_counts.get(argument.arg) == 1
            and _profile_key_for_auth_name(argument.arg) == "auth_token"
        )

    unique = {
        name: values[0]
        for name, values in assignments.items()
        if len(values) == 1 and store_counts.get(name) == 1
    }
    for _ in range(len(unique) + 1):
        changed = False
        for name, value in unique.items():
            if name not in aliases and (
                _runtime_probe_token_read(value)
                or isinstance(value, ast.Name) and value.id in aliases
            ):
                aliases.add(name)
                changed = True
        if not changed:
            break
    return aliases


def _runtime_probe_token_calls_are_safe(modules: list[ast.Module]) -> bool:
    """Require named token parameters to receive an approved runtime value."""
    for module in modules:
        top_level_functions = {
            node.name: node
            for node in module.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        signatures: dict[str, list[tuple[str, int | None]]] = {}
        for node in ast.walk(module):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            all_args = node.args.posonlyargs + node.args.args
            defaulted = {
                argument.arg
                for argument in all_args[len(all_args) - len(node.args.defaults):]
            } if node.args.defaults else set()
            defaulted.update(
                argument.arg
                for argument, default in zip(node.args.kwonlyargs, node.args.kw_defaults)
                if default is not None
            )
            auth_args = [
                argument
                for argument in all_args + node.args.kwonlyargs
                if _profile_key_for_auth_name(argument.arg) == "auth_token"
            ]
            if not auth_args:
                continue
            if (
                top_level_functions.get(node.name) is not node
                or node.name in signatures
                or node.args.vararg is not None
                or node.args.kwarg is not None
                or any(argument.arg in defaulted for argument in auth_args)
                or any(argument in node.args.posonlyargs for argument in auth_args)
            ):
                return False
            signatures[node.name] = [
                (
                    argument.arg,
                    all_args.index(argument) if argument in node.args.args else None,
                )
                for argument in auth_args
            ]

        if not signatures:
            continue
        parents = {
            child: parent
            for parent in ast.walk(module)
            for child in ast.iter_child_nodes(parent)
        }
        for node in ast.walk(module):
            if isinstance(node, ast.Name) and node.id in signatures:
                parent = parents.get(node)
                if not isinstance(parent, ast.Call) or parent.func is not node:
                    return False
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            params = signatures.get(node.func.id)
            if params is None:
                continue
            if (
                any(keyword.arg is None for keyword in node.keywords)
                or any(isinstance(argument, ast.Starred) for argument in node.args)
            ):
                return False
            caller_scope: ast.AST = module
            parent = parents.get(node)
            while parent is not None:
                if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                    caller_scope = parent
                    break
                parent = parents.get(parent)
            aliases = _runtime_probe_token_aliases(caller_scope)
            for name, position in params:
                values = [keyword.value for keyword in node.keywords if keyword.arg == name]
                if (
                    len(values) != 1
                    or position is not None and len(node.args) > position
                ):
                    return False
                value = values[0]
                if not (
                    _runtime_probe_token_read(value)
                    or isinstance(value, ast.Name) and value.id in aliases
                ):
                    return False
    return True


def _auth_source_aliases(
    scope: ast.AST, *, allow_runtime_probe_token: bool = False
) -> dict[str, str]:
    """Resolve profile secrets plus the single approved runtime probe token."""
    aliases = _profile_secret_aliases(scope)
    if allow_runtime_probe_token:
        aliases.update(
            {name: "auth_token" for name in _runtime_probe_token_aliases(scope)}
        )
    return aliases


def _reads_auth_credential(
    node: ast.AST | None,
    key: str,
    aliases: dict[str, str],
    *,
    allow_runtime_probe_token: bool = False,
) -> bool:
    return _reads_profile_secret(node, key, aliases) or (
        allow_runtime_probe_token
        and key == "auth_token"
        and _runtime_probe_token_read(node)
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
        return (
            _safe_unsupported_auth_raise(statement)
            and function_store_counts.get("ValueError", 0) == 0
            and all(
                _stored_name_counts([module]).get("ValueError", 0) == 0
                for module in modules
            )
        )

    def raises_for_unsupported(suite: list[ast.stmt]) -> bool:
        if len(suite) != 1:
            return False
        if isinstance(suite[0], ast.Raise):
            return is_safe_unsupported_raise(suite[0])
        if not isinstance(suite[0], ast.If):
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
            if len(branch.orelse) != 1:
                return False
            fallback = branch.orelse[0]
            if isinstance(fallback, ast.If):
                branch = fallback
            else:
                return is_safe_unsupported_raise(fallback)

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


def _dotted_name(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _dotted_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else None
    return None


def _literal_string_mapping(node: ast.AST | None) -> dict[str, ast.AST] | None:
    if not isinstance(node, ast.Dict):
        return None
    result: dict[str, ast.AST] = {}
    for key, value in zip(node.keys, node.values):
        name = _constant(key)
        if not isinstance(name, str) or name in result:
            return None
        result[name] = value
    return result


def _name_is(node: ast.AST | None, name: str) -> bool:
    return isinstance(node, ast.Name) and node.id == name


def _secret_read_is(node: ast.AST | None, key: str) -> bool:
    return (
        isinstance(node, ast.Subscript)
        and _name_is(node.value, "secrets")
        and _constant(node.slice) == key
    )


def _attribute_is(node: ast.AST | None, value: str, attribute: str) -> bool:
    return isinstance(node, ast.Attribute) and node.attr == attribute and _name_is(
        node.value, value
    )


def _keyword_map(call: ast.Call) -> dict[str, ast.AST] | None:
    result: dict[str, ast.AST] = {}
    for keyword in call.keywords:
        if keyword.arg is None or keyword.arg in result:
            return None
        result[keyword.arg] = keyword.value
    return result


def _is_on_transform_decorator(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and _dotted_name(node.func) == "data_product.on_transform"
        and not node.args
        and not node.keywords
    )


def _direct_import_count(
    modules: list[ast.Module], module_name: str, imported_name: str
) -> int:
    return sum(
        1
        for module in modules
        for statement in module.body
        if isinstance(statement, ast.ImportFrom)
        and statement.module == module_name
        for alias in statement.names
        if alias.name == imported_name and alias.asname is None
    )


def _plain_import_count(modules: list[ast.Module], module_name: str) -> int:
    return sum(
        1
        for module in modules
        for statement in module.body
        if isinstance(statement, ast.Import)
        for alias in statement.names
        if alias.name == module_name and alias.asname is None
    )


def _is_approved_probe_read_attribute(
    node: ast.Attribute, parents: dict[ast.AST, ast.AST]
) -> bool:
    if _dotted_name(node) == "os.getenv":
        call = parents.get(node)
        return (
            isinstance(call, ast.Call)
            and call.func is node
            and _runtime_probe_token_read(call)
        )
    if _dotted_name(node) == "os.environ":
        get_attribute = parents.get(node)
        call = parents.get(get_attribute) if get_attribute is not None else None
        return (
            isinstance(get_attribute, ast.Attribute)
            and get_attribute.value is node
            and get_attribute.attr == "get"
            and isinstance(call, ast.Call)
            and call.func is get_attribute
            and _runtime_probe_token_read(call)
        )
    return False


def _has_static_cursor(node: ast.AST | None, cursor_path: str, cursor_param: str) -> bool:
    values = _literal_string_mapping(node)
    return values is not None and set(values) == {
        "type", "cursor_path", "cursor_param",
    } and _constant(values["type"]) == "cursor" and _constant(
        values["cursor_path"]
    ) == cursor_path and _constant(values["cursor_param"]) == cursor_param


def _is_safe_type_name_attribute(node: ast.Attribute) -> bool:
    """Allow only the probe's safe ``type(value|exc).__name__`` forms."""
    call = node.value
    return (
        node.attr == "__name__"
        and isinstance(call, ast.Call)
        and _name_is(call.func, "type")
        and len(call.args) == 1
        and isinstance(call.args[0], ast.Name)
        and call.args[0].id in {"value", "exc"}
        and not call.keywords
    )


def _reflective_or_dynamic_import_access(
    modules: list[ast.Module],
    *,
    allow_runtime_environment_reads: bool = False,
    allow_os_environ_access: bool = False,
) -> bool:
    reflective_names = {
        "globals", "locals", "vars", "getattr", "setattr", "exec", "eval",
        "compile", "__import__", "__dict__", "__builtins__",
    }
    sensitive_environment_attributes = {
        "os", "posix", "nt", "environ", "environb", "getenv", "getenvb",
        "putenv", "unsetenv",
    }
    for module in modules:
        parents = {
            child: parent
            for parent in ast.walk(module)
            for child in ast.iter_child_nodes(parent)
        }
        for node in ast.walk(module):
            if isinstance(node, ast.Match):
                return True
            if isinstance(node, ast.Name) and node.id in reflective_names:
                return True
            if isinstance(node, ast.Attribute):
                dotted = _dotted_name(node)
                bare_os_base = _name_is(node.value, "os")
                if (
                    node.attr in reflective_names
                    or (
                        node.attr.startswith("__")
                        and node.attr.endswith("__")
                        and not _is_safe_type_name_attribute(node)
                    )
                    or (
                        node.attr in sensitive_environment_attributes
                        and not (
                            bare_os_base
                            and node.attr in {"environ", "getenv"}
                        )
                    )
                    or dotted in {"sys.modules", "sys.path"}
                    or dotted in {
                        "os.putenv", "os.unsetenv", "os.getenvb", "os.environb"
                    }
                    or (
                        dotted == "os.getenv"
                        and not (
                            allow_runtime_environment_reads
                            and _is_approved_probe_read_attribute(node, parents)
                        )
                    )
                    or (
                        dotted == "os.environ"
                        and not allow_os_environ_access
                        and not (
                            allow_runtime_environment_reads
                            and _is_approved_probe_read_attribute(node, parents)
                        )
                    )
                    or (
                    dotted is not None
                    and dotted.startswith("sys.")
                    and dotted != "sys.exit"
                    )
                ):
                    return True
            if isinstance(node, ast.Import):
                if any(
                    alias.name == "importlib"
                    or alias.name.startswith("importlib.")
                    or (alias.name == "sys" and alias.asname is not None)
                    or (alias.name == "os" and alias.asname is not None)
                    for alias in node.names
                ):
                    return True
            if isinstance(node, ast.ImportFrom):
                if (node.module or "").startswith("importlib") or (
                    node.module == "sys"
                    and any(alias.name in {"*", "modules", "path"} for alias in node.names)
                ) or (
                    (node.module or "").split(".", 1)[0] == "os"
                ) or (
                    node.module in {"builtins", "__builtins__"}
                    and any(alias.name == "*" or alias.name in reflective_names for alias in node.names)
                ):
                    return True
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                value = node.value
                if isinstance(value, ast.Name) and value.id == "sys":
                    return True
    return False


def _is_docstring(statement: ast.stmt) -> bool:
    return (
        isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Constant)
        and isinstance(statement.value.value, str)
    )


def _safe_unsupported_auth_raise(statement: ast.AST) -> bool:
    if not isinstance(statement, ast.Raise) or statement.cause is not None:
        return False
    exception = statement.exc
    if (
        not isinstance(exception, ast.Call)
        or not _name_is(exception.func, "ValueError")
        or len(exception.args) != 1
        or exception.keywords
    ):
        return False
    message = exception.args[0]
    if isinstance(message, ast.Constant):
        return isinstance(message.value, str)
    if not isinstance(message, ast.JoinedStr):
        return False
    return all(
        isinstance(part, ast.Constant)
        and isinstance(part.value, str)
        or (
            isinstance(part, ast.FormattedValue)
            and _name_is(part.value, "auth_type")
            and part.conversion in {-1, ord("r"), ord("s")}
            and part.format_spec is None
        )
        for part in message.values
    )


def _safe_annotation(node: ast.AST | None) -> bool:
    if node is None:
        return True
    if isinstance(node, ast.Name):
        return node.id in {
            "Any", "DuckDbOutput", "None", "bool", "dict", "float", "int",
            "list", "str", "tuple",
        }
    if isinstance(node, ast.Constant):
        return node.value is None or isinstance(node.value, str)
    if isinstance(node, ast.Subscript):
        return (
            isinstance(node.value, ast.Name)
            and node.value.id in {"dict", "list", "tuple"}
            and _safe_annotation(node.slice)
        )
    if isinstance(node, ast.Tuple):
        return all(_safe_annotation(element) for element in node.elts)
    return False


def _transform_import_surface_is_safe(module: ast.Module) -> bool:
    allowed_from = {
        "__future__": {"annotations"},
        "pathlib": {"Path"},
        "typing": {"Any"},
        "dlt.sources.rest_api": {"RESTAPIConfig", "rest_api_resources"},
        "nxd": {"data_product"},
        "nxd.core.context": {"DuckDbOutput"},
    }
    seen: set[tuple[str, str]] = set()
    for statement in module.body:
        if isinstance(statement, ast.Import):
            for alias in statement.names:
                if alias.name not in {"dlt", "os"} or alias.asname is not None:
                    return False
                binding = ("import", alias.name)
                if binding in seen:
                    return False
                seen.add(binding)
        elif isinstance(statement, ast.ImportFrom):
            if statement.level or statement.module not in allowed_from:
                return False
            for alias in statement.names:
                if alias.name not in allowed_from[statement.module] or alias.asname is not None:
                    return False
                binding = (statement.module, alias.name)
                if binding in seen:
                    return False
                seen.add(binding)
        elif isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        elif _is_docstring(statement):
            continue
        elif _name_assignment(statement, "PHYSICAL_MODELS") is not None:
            continue
        elif _name_assignment(statement, "OPTIONAL_EMPTY_MODELS") is not None:
            continue
        elif _main_guard(statement):
            continue
        else:
            return False
    return ("import", "dlt") in seen and ("import", "os") in seen


def _static_helper_shape(
    helper: ast.FunctionDef,
    *,
    resource_name: str,
    endpoint_key: str,
    items_field: str,
    cursor_path: str,
    cursor_param: str,
) -> bool:
    args = helper.args
    if (
        helper.decorator_list
        or args.posonlyargs
        or len(args.args) != 1
        or args.args[0].arg != "secrets"
        or not _safe_annotation(args.args[0].annotation)
        or not _safe_annotation(helper.returns)
        or args.vararg is not None
        or args.kwonlyargs
        or args.kwarg is not None
        or args.defaults
        or args.kw_defaults
        or any(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda,
                              ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp))
            for node in ast.walk(helper)
            if node is not helper
        )
    ):
        return False

    statements = list(helper.body)
    if statements and _is_docstring(statements[0]):
        statements.pop(0)
    if len(statements) != 5:
        return False
    client_stmt, auth_stmt, dispatch, config_stmt, return_stmt = statements
    client_value = _annotated_name_assignment(client_stmt, "client_config")

    if not (
        client_value is not None
        and isinstance(auth_stmt, ast.Assign)
        and len(auth_stmt.targets) == 1
        and _name_is(auth_stmt.targets[0], "auth_type")
        and _direct_profile_secret_key(auth_stmt.value) == "auth_type"
        and isinstance(config_stmt, ast.AnnAssign)
        and config_stmt.simple == 1
        and _name_is(config_stmt.target, "config")
        and _name_is(config_stmt.annotation, "RESTAPIConfig")
        and isinstance(return_stmt, ast.Return)
        and isinstance(return_stmt.value, ast.Call)
        and _dotted_name(return_stmt.value.func) == "rest_api_resources"
        and len(return_stmt.value.args) == 1
        and not return_stmt.value.keywords
        and _name_is(return_stmt.value.args[0], "config")
    ):
        return False

    client_values = _literal_string_mapping(client_value)
    if client_values is None or _constant(client_values.get("base_url")) is not None:
        # The profile value must be the direct runtime secret, never a literal.
        return False
    if not _secret_read_is(client_values.get("base_url"), "base_url"):
        return False

    if not isinstance(dispatch, ast.If):
        return False
    bearer_test = dispatch.test
    if not (
        isinstance(bearer_test, ast.Compare)
        and _name_is(bearer_test.left, "auth_type")
        and len(bearer_test.ops) == 1
        and isinstance(bearer_test.ops[0], ast.Eq)
        and len(bearer_test.comparators) == 1
        and _constant(bearer_test.comparators[0]) == "bearer"
        and len(dispatch.body) == 1
        and len(dispatch.orelse) == 1
    ):
        return False
    auth_write = dispatch.body[0]
    auth_values = _literal_string_mapping(auth_write.value) if isinstance(
        auth_write, ast.Assign
    ) else None
    unsupported = dispatch.orelse[0]
    # This scenario requires bearer auth, so the fallback must raise even when
    # auth_type is absent (for example, when it was read with secrets.get()).
    unsupported_branch_ok = _safe_unsupported_auth_raise(unsupported)
    if not (
        isinstance(auth_write, ast.Assign)
        and len(auth_write.targets) == 1
        and isinstance(auth_write.targets[0], ast.Subscript)
        and _name_is(auth_write.targets[0].value, "client_config")
        and _constant(auth_write.targets[0].slice) == "auth"
        and auth_values is not None
        and set(auth_values) == {"type", "token"}
        and _constant(auth_values["type"]) == "bearer"
        and _secret_read_is(auth_values["token"], "auth_token")
        and unsupported_branch_ok
    ):
        return False

    config_values = _literal_string_mapping(config_stmt.value)
    if (
        config_values is None
        or set(config_values) != {"client", "resources"}
        or not _name_is(config_values["client"], "client_config")
        or not isinstance(config_values["resources"], ast.List)
        or len(config_values["resources"].elts) != 1
    ):
        return False
    resource = _literal_string_mapping(config_values["resources"].elts[0])
    if resource is None or set(resource) != {"name", "endpoint"} or _constant(
        resource["name"]
    ) != resource_name:
        return False
    endpoint = _literal_string_mapping(resource["endpoint"])
    if endpoint is None or set(endpoint) not in (
        {"path", "method", "data_selector", "paginator"},
        {"path", "method", "data_selector"},
    ):
        return False
    if not (
        _secret_read_is(endpoint["path"], endpoint_key)
        and _constant(endpoint["method"]) == "GET"
        and _constant(endpoint["data_selector"]) == items_field
    ):
        return False

    client_paginator = client_values.get("paginator")
    endpoint_paginator = endpoint.get("paginator")
    if (client_paginator is None) == (endpoint_paginator is None):
        return False
    if not _has_static_cursor(
        client_paginator or endpoint_paginator, cursor_path, cursor_param
    ):
        return False
    return set(client_values) in ({"base_url", "paginator"}, {"base_url"})


def _name_assignment(statement: ast.stmt, name: str) -> ast.AST | None:
    if (
        isinstance(statement, ast.Assign)
        and len(statement.targets) == 1
        and _name_is(statement.targets[0], name)
    ):
        return statement.value
    return None


def _annotated_name_assignment(statement: ast.stmt, name: str) -> ast.AST | None:
    if isinstance(statement, ast.AnnAssign) and statement.simple == 1:
        return (
            statement.value
            if _name_is(statement.target, name) and _safe_annotation(statement.annotation)
            else None
        )
    return _name_assignment(statement, name)


def _actual_tables_expression(node: ast.AST | None) -> bool:
    return (
        isinstance(node, ast.Call)
        and _name_is(node.func, "set")
        and len(node.args) == 1
        and not node.keywords
        and isinstance(node.args[0], ast.Call)
        and _dotted_name(node.args[0].func) == "pipeline.default_schema.data_table_names"
        and not node.args[0].args
        and not node.args[0].keywords
    )


def _model_table_set(
    node: ast.AST | None,
    *,
    collection_name: str,
    literal_model: str | None = None,
) -> bool:
    if isinstance(node, ast.SetComp) and len(node.generators) == 1:
        generator = node.generators[0]
        target = generator.target
        return (
            isinstance(node.elt, ast.Subscript)
            and _attribute_is(node.elt.value, "duckdb", "model_tables")
            and isinstance(node.elt.slice, ast.Name)
            and _name_is(target, node.elt.slice.id)
            and _name_is(generator.iter, collection_name)
            and not generator.ifs
            and not generator.is_async
        )
    return (
        literal_model is not None
        and isinstance(node, ast.Set)
        and len(node.elts) == 1
        and isinstance(node.elts[0], ast.Subscript)
        and _attribute_is(node.elts[0].value, "duckdb", "model_tables")
        and _constant(node.elts[0].slice) == literal_model
    )


def _readback_condition(statement: ast.If, *, optional_models: bool) -> bool:
    test = statement.test
    if not (
        isinstance(test, ast.Compare)
        and _name_is(test.left, "actual")
        and len(test.ops) == 1
        and isinstance(test.ops[0], ast.NotEq)
        and len(test.comparators) == 1
    ):
        return False
    expected = test.comparators[0]
    if optional_models:
        return (
            isinstance(expected, ast.BinOp)
            and isinstance(expected.op, ast.Sub)
            and _name_is(expected.left, "expected")
            and _name_is(expected.right, "absent_optional")
        )
    return _name_is(expected, "expected")


def _readback_tail_is_safe(statements: list[ast.stmt]) -> bool:
    """Accept the required-table shorthand or the canonical optional-table check."""
    if len(statements) == 4:
        actual_stmt, expected_stmt, check_stmt, marker_stmt = statements
        expected_value = _name_assignment(expected_stmt, "expected")
        optional_value = None
        expected_ok = _model_table_set(
            expected_value,
            collection_name="PHYSICAL_MODELS",
            literal_model="orders",
        )
        optional_models = False
    elif len(statements) == 7:
        actual_stmt, expected_stmt, optional_stmt, missing_stmt, absent_stmt, check_stmt, marker_stmt = statements
        expected_value = _name_assignment(expected_stmt, "expected")
        optional_value = _name_assignment(optional_stmt, "optional")
        missing_value = _name_assignment(missing_stmt, "missing")
        absent_value = _name_assignment(absent_stmt, "absent_optional")
        expected_ok = _model_table_set(
            expected_value, collection_name="PHYSICAL_MODELS"
        )
        optional_models = (
            _model_table_set(optional_value, collection_name="OPTIONAL_EMPTY_MODELS")
            and isinstance(missing_value, ast.BinOp)
            and isinstance(missing_value.op, ast.Sub)
            and _name_is(missing_value.left, "expected")
            and _name_is(missing_value.right, "actual")
            and isinstance(absent_value, ast.BinOp)
            and isinstance(absent_value.op, ast.BitAnd)
            and _name_is(absent_value.left, "missing")
            and _name_is(absent_value.right, "optional")
        )
        if not optional_models:
            return False
    else:
        return False

    actual_value = _name_assignment(actual_stmt, "actual")
    if not (
        _actual_tables_expression(actual_value)
        and expected_ok
        and isinstance(check_stmt, ast.If)
        and _readback_condition(check_stmt, optional_models=optional_models)
        and len(check_stmt.body) == 1
        and not check_stmt.orelse
        and isinstance(check_stmt.body[0], ast.Raise)
        and check_stmt.body[0].cause is None
        and isinstance(check_stmt.body[0].exc, ast.Call)
        and _name_is(check_stmt.body[0].exc.func, "RuntimeError")
        and len(check_stmt.body[0].exc.args) == 1
        and not check_stmt.body[0].exc.keywords
    ):
        return False

    marker_call = marker_stmt.value if isinstance(marker_stmt, ast.Expr) else None
    if not (
        isinstance(marker_call, ast.Call)
        and isinstance(marker_call.func, ast.Attribute)
        and marker_call.func.attr == "touch"
        and isinstance(marker_call.func.value, ast.BinOp)
        and isinstance(marker_call.func.value.op, ast.Div)
        and _name_is(marker_call.func.value.left, "run_dir")
        and _constant(marker_call.func.value.right) == ".transform-complete"
        and not marker_call.args
        and not marker_call.keywords
    ):
        return False

    allowed_names = {
        "PHYSICAL_MODELS", "OPTIONAL_EMPTY_MODELS", "RuntimeError", "absent_optional",
        "actual", "duckdb", "expected", "missing", "model", "optional", "pipeline",
        "run_dir", "set", "sorted",
    }
    if any(
        isinstance(node, ast.Name) and node.id not in allowed_names
        for statement in statements
        for node in ast.walk(statement)
    ):
        return False

    verified_expressions = [actual_value, expected_value]
    if optional_value is not None:
        verified_expressions.append(optional_value)
    allowed_attributes = {
        node
        for expression in verified_expressions
        for node in ast.walk(expression)
        if isinstance(node, ast.Attribute)
    }
    allowed_attributes.add(marker_call.func)
    if any(
        isinstance(node, ast.Attribute) and node not in allowed_attributes
        for statement in statements
        for node in ast.walk(statement)
    ):
        return False

    allowed_calls = {
        "set", "pipeline.default_schema.data_table_names", "RuntimeError", "sorted",
    }
    for statement in statements:
        for node in ast.walk(statement):
            if not isinstance(node, ast.Call) or node is marker_call:
                continue
            if _dotted_name(node.func) not in allowed_calls:
                return False
    return not any(
        isinstance(node, ast.Name) and node.id in {"secrets", "res"}
        for statement in statements
        for node in ast.walk(statement)
    )


def _main_guard(statement: ast.stmt) -> bool:
    return (
        isinstance(statement, ast.If)
        and isinstance(statement.test, ast.Compare)
        and _name_is(statement.test.left, "__name__")
        and len(statement.test.ops) == 1
        and isinstance(statement.test.ops[0], ast.Eq)
        and len(statement.test.comparators) == 1
        and _constant(statement.test.comparators[0]) == "__main__"
        and len(statement.body) == 1
        and isinstance(statement.body[0], ast.Expr)
        and isinstance(statement.body[0].value, ast.Call)
        and _dotted_name(statement.body[0].value.func) == "data_product.main"
        and not statement.body[0].value.args
        and not statement.body[0].value.keywords
        and not statement.orelse
    )


def _model_constant(statement: ast.stmt, name: str, expected: tuple[str, ...]) -> bool:
    value = _name_assignment(statement, name)
    return (
        isinstance(value, ast.Tuple)
        and tuple(_constant(item) for item in value.elts) == expected
    )


def _desktop_transform_shape(ingest: ast.FunctionDef) -> bool:
    args = ingest.args
    if (
        args.posonlyargs
        or [argument.arg for argument in args.args] != ["duckdb", "secrets"]
        or not _name_is(args.args[0].annotation, "DuckDbOutput")
        or not _safe_annotation(args.args[1].annotation)
        or not _safe_annotation(ingest.returns)
        or args.vararg is not None
        or args.kwonlyargs
        or args.kwarg is not None
        or args.defaults
        or args.kw_defaults
        or len(ingest.decorator_list) != 1
        or not _is_on_transform_decorator(ingest.decorator_list[0])
    ):
        return False
    statements = list(ingest.body)
    if statements and _is_docstring(statements[0]):
        statements.pop(0)
    if len(statements) < 8:
        return False
    run_dir_stmt, pipelines_stmt, mkdir_stmt, env_stmt, pipeline_stmt, res_stmt, run_stmt = statements[:7]
    tail = statements[7:]

    run_dir_value = (
        run_dir_stmt.value
        if isinstance(run_dir_stmt, ast.Assign)
        and len(run_dir_stmt.targets) == 1
        and _name_is(run_dir_stmt.targets[0], "run_dir")
        else None
    )
    path_call = run_dir_value.value if isinstance(run_dir_value, ast.Attribute) else None
    if not (
        isinstance(run_dir_value, ast.Attribute)
        and run_dir_value.attr == "parent"
        and isinstance(path_call, ast.Call)
        and _name_is(path_call.func, "Path")
        and len(path_call.args) == 1
        and not path_call.keywords
        and _attribute_is(path_call.args[0], "duckdb", "path")
    ):
        return False

    if not (
        isinstance(pipelines_stmt, ast.Assign)
        and len(pipelines_stmt.targets) == 1
        and _name_is(pipelines_stmt.targets[0], "pipelines_dir")
        and isinstance(pipelines_stmt.value, ast.BinOp)
        and isinstance(pipelines_stmt.value.op, ast.Div)
        and _name_is(pipelines_stmt.value.left, "run_dir")
        and _constant(pipelines_stmt.value.right) == "dlt-pipelines"
    ):
        return False
    mkdir_call = mkdir_stmt.value if isinstance(mkdir_stmt, ast.Expr) else None
    mkdir_keywords = _keyword_map(mkdir_call) if isinstance(mkdir_call, ast.Call) else None
    if not (
        isinstance(mkdir_call, ast.Call)
        and _attribute_is(mkdir_call.func, "pipelines_dir", "mkdir")
        and not mkdir_call.args
        and mkdir_keywords is not None
        and set(mkdir_keywords) == {"parents", "exist_ok"}
        and all(isinstance(value, ast.Constant) and value.value is True for value in mkdir_keywords.values())
    ):
        return False

    env_value = env_stmt.value if isinstance(env_stmt, ast.Assign) else None
    env_target = env_stmt.targets[0] if isinstance(env_stmt, ast.Assign) and len(env_stmt.targets) == 1 else None
    env_data = (
        env_value.args[0]
        if isinstance(env_value, ast.Call) and len(env_value.args) == 1
        else None
    )
    env_path = env_data
    if not (
        isinstance(env_target, ast.Subscript)
        and _attribute_is(env_target.value, "os", "environ")
        and _constant(env_target.slice) == "DLT_DATA_DIR"
        and isinstance(env_value, ast.Call)
        and _name_is(env_value.func, "str")
        and not env_value.keywords
        and isinstance(env_path, ast.BinOp)
        and isinstance(env_path.op, ast.Div)
        and _name_is(env_path.left, "run_dir")
        and _constant(env_path.right) == "dlt-data"
    ):
        return False

    pipeline_call = pipeline_stmt.value if isinstance(pipeline_stmt, ast.Assign) else None
    pipeline_keywords = _keyword_map(pipeline_call) if isinstance(pipeline_call, ast.Call) else None
    if not (
        isinstance(pipeline_stmt, ast.Assign)
        and len(pipeline_stmt.targets) == 1
        and _name_is(pipeline_stmt.targets[0], "pipeline")
        and isinstance(pipeline_call, ast.Call)
        and _dotted_name(pipeline_call.func) == "dlt.pipeline"
        and not pipeline_call.args
        and pipeline_keywords is not None
        and set(pipeline_keywords) == {"pipelines_dir", "destination", "dataset_name"}
    ):
        return False
    pipelines_arg = pipeline_keywords["pipelines_dir"]
    destination = pipeline_keywords["destination"]
    destination_keywords = _keyword_map(destination) if isinstance(destination, ast.Call) else None
    if not (
        isinstance(pipelines_arg, ast.Call)
        and _name_is(pipelines_arg.func, "str")
        and len(pipelines_arg.args) == 1
        and _name_is(pipelines_arg.args[0], "pipelines_dir")
        and not pipelines_arg.keywords
        and isinstance(destination, ast.Call)
        and _dotted_name(destination.func) == "dlt.destinations.duckdb"
        and not destination.args
        and destination_keywords is not None
        and set(destination_keywords) == {"credentials"}
        and _attribute_is(destination_keywords["credentials"], "duckdb", "path")
        and _attribute_is(pipeline_keywords["dataset_name"], "duckdb", "schema")
    ):
        return False

    res_call = res_stmt.value if isinstance(res_stmt, ast.Assign) else None
    if not (
        isinstance(res_stmt, ast.Assign)
        and len(res_stmt.targets) == 1
        and _name_is(res_stmt.targets[0], "res")
        and isinstance(res_call, ast.Call)
        and _name_is(res_call.func, "_orders_resources")
        and len(res_call.args) == 1
        and _name_is(res_call.args[0], "secrets")
        and not res_call.keywords
    ):
        return False

    run_call = run_stmt.value if isinstance(run_stmt, ast.Expr) else None
    run_keywords = _keyword_map(run_call) if isinstance(run_call, ast.Call) else None
    if not (
        isinstance(run_call, ast.Call)
        and _attribute_is(run_call.func, "pipeline", "run")
        and len(run_call.args) == 1
        and _name_is(run_call.args[0], "res")
        and run_keywords is not None
        and set(run_keywords) == {"write_disposition"}
        and _constant(run_keywords["write_disposition"]) == "replace"
    ):
        return False

    if not _readback_tail_is_safe(tail):
        return False

    names = [node for node in ast.walk(ingest) if isinstance(node, ast.Name)]
    res_nodes = [node for node in names if node.id == "res"]
    pipeline_nodes = [node for node in names if node.id == "pipeline"]
    secrets_loads = [
        node for node in names
        if node.id == "secrets" and isinstance(node.ctx, ast.Load)
    ]
    return (
        len(res_nodes) == 2
        and any(node is res_stmt.targets[0] and isinstance(node.ctx, ast.Store) for node in res_nodes)
        and any(node is run_call.args[0] and isinstance(node.ctx, ast.Load) for node in res_nodes)
        and len(pipeline_nodes) == 3
        and any(node is pipeline_stmt.targets[0] and isinstance(node.ctx, ast.Store) for node in pipeline_nodes)
        and any(node is run_call.func.value and isinstance(node.ctx, ast.Load) for node in pipeline_nodes)
        and len(secrets_loads) == 1
        and secrets_loads[0] is res_call.args[0]
    )


def active_desktop_source_flow(
    transform_modules: list[ast.Module],
    closure_modules: list[ast.Module],
    active_config: dict[str, bool],
    *,
    resource_name: str,
    endpoint_key: str,
    items_field: str,
    cursor_path: str,
    cursor_param: str,
    connectivity_probe_modules: list[ast.Module] | None = None,
) -> bool:
    """Fail closed on the one-resource helper and local Desktop dlt dataflow."""
    connectivity_probe_modules = connectivity_probe_modules or []
    probe_ids = {id(module) for module in connectivity_probe_modules}
    transform_fingerprints = {
        ast.dump(module, include_attributes=False) for module in transform_modules
    }
    if (
        len(probe_ids) != len(connectivity_probe_modules)
        or any(
            not any(module is closure_module for closure_module in closure_modules)
            for module in connectivity_probe_modules
        )
        or any(
            any(module is transform_module for transform_module in transform_modules)
            for module in connectivity_probe_modules
        )
        or any(
            not _runtime_probe_os_access_is_safe(module)
            for module in connectivity_probe_modules
        )
        or any(_uses_alternate_environment_api(module) for module in closure_modules)
        or any(
            not _os_module_is_not_aliased(module)
            for module in closure_modules
            if id(module) not in probe_ids
        )
        or any(
            _reflective_or_dynamic_import_access(
                [module],
                allow_runtime_environment_reads=id(module) in probe_ids,
                allow_os_environ_access=ast.dump(module, include_attributes=False)
                in transform_fingerprints,
            )
            for module in closure_modules
        )
        or len(transform_modules) != 1
        or _reflective_or_dynamic_import_access(
            transform_modules, allow_os_environ_access=True
        )
        or not _transform_import_surface_is_safe(transform_modules[0])
    ):
        return False
    module = transform_modules[0]
    top_level_functions = [
        node for node in module.body
        if isinstance(node, ast.FunctionDef)
    ]
    helpers = [node for node in top_level_functions if node.name == "_orders_resources"]
    ingests = [node for node in top_level_functions if node.name == "ingest"]
    if len(helpers) != 1 or len(ingests) != 1:
        return False
    helper, ingest = helpers[0], ingests[0]
    transforms = [
        node
        for candidate in transform_modules
        for node in ast.walk(candidate)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and any(_is_on_transform_decorator(decorator) for decorator in node.decorator_list)
    ]
    if transforms != [ingest]:
        return False

    # Preserve the Desktop template surfaces while keeping this fixture to one
    # required physical model and no optional/derived models.
    model_constants = [
        statement
        for statement in module.body
        if _name_assignment(statement, "PHYSICAL_MODELS") is not None
        or _name_assignment(statement, "OPTIONAL_EMPTY_MODELS") is not None
    ]
    if (
        len(model_constants) != 2
        or sum(_model_constant(node, "PHYSICAL_MODELS", (resource_name,)) for node in model_constants) != 1
        or sum(_model_constant(node, "OPTIONAL_EMPTY_MODELS", ()) for node in model_constants) != 1
    ):
        return False

    # The transform module is intentionally a tiny, self-contained closure:
    # direct imports, the required model constants, helper/entrypoint, and main guard.
    main_guards = 0
    for statement in module.body:
        if statement in {helper, ingest} or isinstance(statement, (ast.Import, ast.ImportFrom)):
            continue
        if _is_docstring(statement):
            continue
        if statement in model_constants:
            continue
        if _main_guard(statement):
            main_guards += 1
            continue
        return False
    if main_guards != 1:
        return False

    rest_aliases = [
        alias
        for candidate in closure_modules
        for statement in candidate.body
        if isinstance(statement, ast.ImportFrom)
        and statement.module == "dlt.sources.rest_api"
        for alias in statement.names
        if alias.name in {"rest_api_resources", "RESTAPIConfig"}
        or alias.asname in {"rest_api_resources", "RESTAPIConfig"}
    ]
    if (
        len(rest_aliases) != 2
        or {alias.name for alias in rest_aliases} != {"rest_api_resources", "RESTAPIConfig"}
        or any(alias.asname is not None for alias in rest_aliases)
        or _direct_import_count(closure_modules, "dlt.sources.rest_api", "rest_api_resources") != 1
        or _direct_import_count(closure_modules, "dlt.sources.rest_api", "RESTAPIConfig") != 1
        or _plain_import_count([module], "dlt") != 1
        or _plain_import_count([module], "os") != 1
        or _direct_import_count([module], "pathlib", "Path") != 1
        or _direct_import_count([module], "nxd", "data_product") != 1
        or _direct_import_count([module], "nxd.core.context", "DuckDbOutput") != 1
    ):
        return False

    protected_names = {
        "_orders_resources", "RESTAPIConfig", "rest_api_resources", "dlt",
        "os", "Path", "data_product", "DuckDbOutput",
    }
    for candidate in closure_modules:
        for node in ast.walk(candidate):
            if isinstance(node, ast.Name) and node.id in protected_names and isinstance(node.ctx, ast.Store):
                return False
            if isinstance(node, ast.arg) and node.arg in protected_names:
                return False
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                and node.name in protected_names
            ):
                if not (
                    node.name == "_orders_resources"
                    and node.lineno == helper.lineno
                    and ast.dump(node, include_attributes=False)
                    == ast.dump(helper, include_attributes=False)
                ):
                    return False
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                aliases = node.names
                if any(
                    alias.name == "_orders_resources" or alias.asname == "_orders_resources"
                    for alias in aliases
                ):
                    return False

    if not _static_helper_shape(
        helper,
        resource_name=resource_name,
        endpoint_key=endpoint_key,
        items_field=items_field,
        cursor_path=cursor_path,
        cursor_param=cursor_param,
    ) or not _desktop_transform_shape(ingest):
        return False

    helper_calls = [
        node
        for candidate in transform_modules
        for node in ast.walk(candidate)
        if isinstance(node, ast.Call) and _name_is(node.func, "_orders_resources")
    ]
    rest_calls = [
        node
        for candidate in transform_modules
        for node in ast.walk(candidate)
        if isinstance(node, ast.Call) and _name_is(node.func, "rest_api_resources")
    ]
    if len(helper_calls) != 1 or len(rest_calls) != 1:
        return False
    pipeline_calls = [
        node
        for candidate in closure_modules
        for node in ast.walk(candidate)
        if isinstance(node, ast.Call) and _dotted_name(node.func) == "dlt.pipeline"
    ]
    if len(pipeline_calls) != 1:
        return False
    if not all(active_config.values()):
        return False

    # The transform may touch process environment only to isolate dlt state;
    # the sibling authoring-time connectivity probe may read its runtime token.
    allowed_env = next(
        (
            node.targets[0].value
            for node in ast.walk(ingest)
            if isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Subscript)
            and _attribute_is(node.targets[0].value, "os", "environ")
            and _constant(node.targets[0].slice) == "DLT_DATA_DIR"
        ),
        None,
    )
    env_attributes = [
        node
        for candidate in transform_modules
        for node in ast.walk(candidate)
        if isinstance(node, ast.Attribute) and _dotted_name(node) == "os.environ"
    ]
    if (
        allowed_env is None
        or len(env_attributes) != 1
        or (
            env_attributes[0].lineno,
            env_attributes[0].col_offset,
            env_attributes[0].end_lineno,
            env_attributes[0].end_col_offset,
        )
        != (
            allowed_env.lineno,
            allowed_env.col_offset,
            allowed_env.end_lineno,
            allowed_env.end_col_offset,
        )
    ):
        return False
    for candidate in closure_modules:
        for node in ast.walk(candidate):
            dotted = _dotted_name(node) if isinstance(node, ast.Attribute) else None
            if dotted is not None and (
                dotted == "dlt.config"
                or dotted.startswith("dlt.config.")
                or dotted == "dlt.secrets"
                or dotted.startswith("dlt.secrets.")
            ):
                return False
    return True


def closure_has_forbidden_dlt_config(root: Path, modules: list[ast.Module]) -> bool:
    for path in root.rglob("*"):
        if path.is_dir() and path.name == ".dlt":
            return True
        if path.is_file() and path.name in {"secrets.toml", "config.toml"}:
            return True
    for module in modules:
        for node in ast.walk(module):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                value = node.value.replace("\\", "/").lower()
                if (
                    re.search(r"(?:^|/)\.dlt(?:/|$)", value)
                    or re.search(r"(?:^|/)(?:secrets|config)\.toml(?:/|$)", value)
                ):
                    return True
    return False


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


def _profile_bearer_header(
    node: ast.AST,
    aliases: dict[str, str],
    *,
    allow_runtime_probe_token: bool = False,
) -> bool:
    """Accept only a Bearer header assembled from an approved runtime token."""
    if isinstance(node, ast.JoinedStr):
        literals = [value.value for value in node.values if isinstance(value, ast.Constant)]
        formatted = [value for value in node.values if isinstance(value, ast.FormattedValue)]
        return (
            literals in (["Bearer "], ["Bearer ", ""])
            and len(formatted) == 1
            and formatted[0].conversion == -1
            and formatted[0].format_spec is None
            and _reads_auth_credential(
                formatted[0].value,
                "auth_token",
                aliases,
                allow_runtime_probe_token=allow_runtime_probe_token,
            )
        )
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return (
            _static_string(node.left) == "Bearer "
            and _reads_auth_credential(
                node.right,
                "auth_token",
                aliases,
                allow_runtime_probe_token=allow_runtime_probe_token,
            )
        ) or (
            _static_string(node.right) == "Bearer "
            and _reads_auth_credential(
                node.left,
                "auth_token",
                aliases,
                allow_runtime_probe_token=allow_runtime_probe_token,
            )
        )
    return False


def _is_boolean_or_none(value: ast.AST) -> bool:
    return isinstance(value, ast.Constant) and (
        isinstance(value.value, bool) or value.value is None
    )


def has_no_hardcoded_auth_literals(
    modules: list[ast.Module], *, allow_runtime_probe_token: bool = False
) -> bool:
    """Reject literals, with a narrow runtime-env exception for the API probe."""
    auth_headers = {"authorization", "proxy-authorization"}
    redaction_markers = {"<redacted>", "redacted", "[redacted]", "***", "..."}

    if allow_runtime_probe_token and (
        not any(
            _runtime_probe_token_read(node)
            for module in modules
            for node in ast.walk(module)
        )
        or any(not _runtime_probe_os_access_is_safe(module) for module in modules)
        or not _runtime_probe_token_calls_are_safe(modules)
        or _reflective_or_dynamic_import_access(
            modules, allow_runtime_environment_reads=True
        )
    ):
        return False

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
            aliases = _auth_source_aliases(
                scope, allow_runtime_probe_token=allow_runtime_probe_token
            )
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
                                and not _profile_bearer_header(
                                    value,
                                    aliases,
                                    allow_runtime_probe_token=allow_runtime_probe_token,
                                )
                            ):
                                return False
                            continue
                        profile_key = _profile_key_for_auth_name(name)
                        if profile_key and not _reads_auth_credential(
                            value,
                            profile_key,
                            aliases,
                            allow_runtime_probe_token=allow_runtime_probe_token,
                        ):
                            return False
                if isinstance(node, ast.Tuple) and len(node.elts) == 2:
                    header_name = _static_string(node.elts[0])
                    if header_name and header_name.casefold() in auth_headers:
                        if not is_redaction_value(node.elts[1]) and not _profile_bearer_header(
                            node.elts[1],
                            aliases,
                            allow_runtime_probe_token=allow_runtime_probe_token,
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
                                and not _profile_bearer_header(
                                    keyword.value,
                                    aliases,
                                    allow_runtime_probe_token=allow_runtime_probe_token,
                                )
                            ):
                                return False
                            continue
                        profile_key = _profile_key_for_auth_name(keyword.arg)
                        if profile_key and not _reads_auth_credential(
                            keyword.value,
                            profile_key,
                            aliases,
                            allow_runtime_probe_token=allow_runtime_probe_token,
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
                                and not _profile_bearer_header(
                                    value,
                                    aliases,
                                    allow_runtime_probe_token=allow_runtime_probe_token,
                                )
                            ):
                                return False
                            profile_key = _profile_key_for_auth_name(
                                _static_string(target.slice) or ""
                            )
                            if profile_key and not _reads_auth_credential(
                                value,
                                profile_key,
                                aliases,
                                allow_runtime_probe_token=allow_runtime_probe_token,
                            ):
                                return False
                        profile_key = (
                            _profile_key_for_auth_name(target.id)
                            if isinstance(target, ast.Name)
                            else None
                        )
                        if profile_key and not _reads_auth_credential(
                            value,
                            profile_key,
                            aliases,
                            allow_runtime_probe_token=allow_runtime_probe_token,
                        ):
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
    explicit_status = re.compile(
        r"(?im)^\s*(?:[-*]\s*)?(?:connectivity check|live api request|api request)"
        r"\b[^\n]*\b(?:not run|not executed|not tested|unverified)\b"
    )
    return bool(
        re.search(contextual_negation, text)
        or re.search(no_request, text)
        or explicit_status.search(readme)
    )


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
    # The source-types index defines generic REST as plain `api-source`;
    # `source_kind` is for provider-specific API adapters, not this scenario.
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
    connectivity_probe_modules: list[ast.Module] = []
    connectivity_probe_parse_errors: list[str] = []
    for path in root.rglob("*.py"):
        try:
            module = ast.parse(
                path.read_text(encoding="utf-8", errors="replace"),
                filename=path.name,
            )
            generated_python_modules.append(module)
            if path.resolve() == (root / "connectivity_check.py").resolve():
                connectivity_probe_modules.append(module)
        except SyntaxError:
            if path in transform_paths:
                continue  # The transform parse gate above reports this precisely.
            if path.resolve() == (root / "connectivity_check.py").resolve():
                connectivity_probe_parse_errors.append(path.name)
    check(
        "connectivity-probe:parses",
        len(connectivity_probe_modules) == 1 and not connectivity_probe_parse_errors,
        ", ".join(connectivity_probe_parse_errors),
    )
    desktop_flow_ok = active_desktop_source_flow(
        modules,
        generated_python_modules,
        active_config,
        resource_name=expected["resource_name"],
        endpoint_key=endpoint_key,
        items_field=str(pagination["items_field"]),
        cursor_path=str(pagination["cursor_path"]),
        cursor_param=str(pagination["cursor_param"]),
        connectivity_probe_modules=connectivity_probe_modules,
    )
    check("transform:desktop-dlt-source-flow", desktop_flow_ok)
    check(
        "secrets:no-dlt-local-config",
        not closure_has_forbidden_dlt_config(root, generated_python_modules),
    )
    check(
        "auth:no-hardcoded-credential",
        has_no_hardcoded_auth_literals(
            [
                module for module in generated_python_modules
                if module not in connectivity_probe_modules
            ]
        )
        and has_no_hardcoded_auth_literals(
            connectivity_probe_modules, allow_runtime_probe_token=True
        ),
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
