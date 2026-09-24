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


def _reads_profile_secret(node: ast.AST | None, key: str) -> bool:
    if isinstance(node, ast.Subscript):
        return (
            isinstance(node.value, ast.Name)
            and node.value.id == "secrets"
            and _constant(node.slice) == key
        )
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        return (
            isinstance(node.func.value, ast.Name)
            and node.func.value.id == "secrets"
            and node.func.attr == "get"
            and bool(node.args)
            and _constant(node.args[0]) == key
        )
    return False


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
    for node in nodes:
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        for target in targets:
            if isinstance(target, ast.Name):
                if target.id in assignments:
                    ambiguous_names.add(target.id)
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
        values: dict[str, Any] = {}
        for key, value in zip(node.keys, node.values):
            resolved_key = _constant(key)
            if isinstance(resolved_key, str):
                values[resolved_key] = _static_value(value, assignments, mutations, seen)
        return values
    if isinstance(node, (ast.List, ast.Tuple)):
        return [
            _static_value(value, assignments, mutations, seen)
            for value in node.elts
        ]
    return node


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
) -> tuple[ast.If, list[ast.AST]] | None:
    parent = parents.get(call)
    child = call
    while parent is not None and parent is not function:
        if isinstance(parent, (ast.If, ast.For, ast.While, ast.Try, ast.With, ast.Match)):
            if not isinstance(parent, ast.If) or child not in parent.body:
                return None
            test = parent.test
            if not (
                isinstance(test, ast.Compare)
                and isinstance(test.left, ast.Name)
                and test.left.id == "auth_type"
                and len(test.ops) == 1
                and isinstance(test.ops[0], ast.Eq)
                and len(test.comparators) == 1
                and _constant(test.comparators[0]) == "bearer"
            ):
                return None

            before_branch = [
                statement for statement in function.body
                if getattr(statement, "lineno", parent.lineno) < parent.lineno
            ]
            # Reject control-flow before the guard: its assignments may or may
            # not be active when the guarded REST call runs.
            allowed_before = (ast.Assign, ast.AnnAssign, ast.Import, ast.ImportFrom)
            has_function_docstring = bool(
                function.body
                and isinstance(function.body[0], ast.Expr)
                and isinstance(function.body[0].value, ast.Constant)
                and isinstance(function.body[0].value.value, str)
            )
            if any(
                not isinstance(statement, allowed_before)
                and not (has_function_docstring and statement is function.body[0])
                for statement in before_branch
            ):
                return None
            auth_type_assignments = [
                statement for statement in before_branch
                if isinstance(statement, (ast.Assign, ast.AnnAssign))
                and any(
                    isinstance(target, ast.Name) and target.id == "auth_type"
                    for target in (
                        statement.targets
                        if isinstance(statement, ast.Assign)
                        else [statement.target]
                    )
                )
            ]
            if (
                len(auth_type_assignments) != 1
                or not _reads_profile_secret(auth_type_assignments[0].value, "auth_type")
            ):
                return None

            before_call = [
                statement for statement in parent.body
                if getattr(statement, "lineno", parent.lineno) < call.lineno
            ]
            allowed_in_branch = (ast.Assign, ast.AnnAssign, ast.Import, ast.ImportFrom)
            if any(not isinstance(statement, allowed_in_branch) for statement in before_call):
                return None
            if any(
                isinstance(statement, (ast.Assign, ast.AnnAssign))
                and any(
                    isinstance(target, ast.Name) and target.id == "auth_type"
                    for target in (
                        statement.targets
                        if isinstance(statement, ast.Assign)
                        else [statement.target]
                    )
                )
                for statement in before_call
            ):
                return None
            statements = [*before_branch, *before_call]
            return parent, statements
        child = parent
        parent = parents.get(parent)
    return None


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
    bindings and ``client_config["auth"]`` mutations inside one function. The
    call must be within the positive bearer branch, and only assignments before
    it in that function are considered. The public scenario has one operation,
    so a generated comprehension or dynamic config factory would make the
    oracle less interpretable than this deterministic contract check.
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
    active_branch = _active_bearer_branch(call, function, parents)
    if active_branch is None:
        return evidence
    _, scope_nodes = active_branch
    assignments, mutations = _static_bindings(scope_nodes)
    config = _static_value(call.args[0], assignments, mutations)
    if not isinstance(config, dict):
        return evidence
    client = config.get("client")
    if not isinstance(client, dict):
        return evidence
    auth = client.get("auth")
    evidence["auth"] = (
        isinstance(auth, dict)
        and _static_constant(auth.get("type")) == "bearer"
        and _reads_profile_secret(auth.get("token"), "auth_token")
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
    if "token" in normalized:
        return "auth_token"
    if "api_key" in normalized:
        return "auth_api_key"
    if "client_secret" in normalized or normalized in {"secret", "auth_secret"}:
        return "auth_client_secret"
    if "password" in normalized:
        return "auth_password"
    return None


def has_no_hardcoded_auth_literals(modules: list[ast.Module]) -> bool:
    """Reject literal credentials in auth fields, token-like variables or headers."""
    auth_headers = {"authorization", "proxy-authorization"}
    for module in modules:
        for node in ast.walk(module):
            if isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values):
                    name = _static_string(key)
                    if name is not None and name.casefold() in auth_headers:
                        return False
                    profile_key = (
                        _profile_key_for_auth_name(name) if isinstance(name, str) else None
                    )
                    if profile_key and not _reads_profile_secret(value, profile_key):
                        return False
            if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                value = node.value
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    if (
                        isinstance(target, ast.Subscript)
                        and (_static_string(target.slice) or "").casefold() in auth_headers
                    ):
                        return False
                    profile_key = (
                        _profile_key_for_auth_name(target.id)
                        if isinstance(target, ast.Name)
                        else None
                    )
                    if profile_key and not _reads_profile_secret(value, profile_key):
                        return False
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if re.fullmatch(r"(?i)Bearer\s+\S+", node.value):
                    return False
        if any(literal.casefold() in auth_headers for literal in string_literals(module)):
            return False
    return True


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
        root, expected_token="${ORDERS_READ_TOKEN}"
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
    leaked: list[str] = []
    if profile_token_reference:
        for path in root.rglob("*"):
            if not path.is_file() or path == root / "infra-profile.yaml":
                continue
            if profile_token_reference in path.read_text(encoding="utf-8", errors="replace"):
                leaked.append(str(path.relative_to(root)))
    check("secret:not-copied-into-generated-files", not leaked, ", ".join(leaked))
    check(
        "sensitivity:artifacts",
        "infra-profile.yaml" in (root / ".gitignore").read_text(encoding="utf-8", errors="replace")
        and "auth_token" in (root / "SENSITIVE").read_text(encoding="utf-8", errors="replace"),
    )
    readme = (root / "README.md").read_text(encoding="utf-8", errors="replace")
    check("honesty:no-live-claim", "not executed" in readme.lower() or "not run" in readme.lower())
    print("\nALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
