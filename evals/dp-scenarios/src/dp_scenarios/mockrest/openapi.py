"""Compile a small OpenAPI document into a deterministic mock-rest scenario.

This is deliberately a fixture compiler, not an OpenAPI implementation.  The
document owns route shape, response schemas, and declared security.  Runtime
credentials and authorization policy remain explicit test configuration so a
generated response cannot accidentally become the authorization oracle.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Mapping

import yaml

from .config import SUPPORTED_HTTP_METHODS


class OpenAPIError(ValueError):
    """Raised when an OpenAPI fixture cannot be compiled safely."""


_HTTP_METHODS = SUPPORTED_HTTP_METHODS - {"HEAD"}
_SUCCESS_CODES = tuple(str(code) for code in range(200, 300))
_SUPPORTED_SECURITY_TYPES = {("http", "bearer")}


def _mapping(value: Any, location: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise OpenAPIError(f"{location} must be a mapping")
    return dict(value)


def _nonempty_string(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OpenAPIError(f"{location} must be a non-empty string")
    return value


def _load_document(source: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(source, Mapping):
        return copy.deepcopy(dict(source))
    path = Path(source)
    try:
        text = path.read_text(encoding="utf-8")
        raw = yaml.safe_load(text) if path.suffix.lower() in {".yaml", ".yml"} else json.loads(text)
    except (OSError, UnicodeError, json.JSONDecodeError, yaml.YAMLError) as exc:
        raise OpenAPIError(f"could not read OpenAPI document {path}: {exc}") from exc
    return _mapping(raw, "OpenAPI document")


def _resolve_local_ref(value: Any, document: Mapping[str, Any], location: str) -> Any:
    if not isinstance(value, Mapping) or "$ref" not in value:
        return value
    reference = _nonempty_string(value["$ref"], f"{location}.$ref")
    if not reference.startswith("#/"):
        raise OpenAPIError(f"{location} only supports local $ref values")
    resolved: Any = document
    for part in reference[2:].split("/"):
        if not isinstance(resolved, Mapping) or part not in resolved:
            raise OpenAPIError(f"{location} has an unresolved $ref: {reference}")
        resolved = resolved[part]
    return resolved


def _example_from_schema(
    schema: Any,
    document: Mapping[str, Any],
    location: str,
    seen_refs: frozenset[str] = frozenset(),
) -> Any:
    if isinstance(schema, Mapping) and "$ref" in schema:
        reference = _nonempty_string(schema["$ref"], f"{location}.$ref")
        if reference in seen_refs:
            raise OpenAPIError(f"{location} contains a recursive $ref: {reference}")
        return _example_from_schema(
            _resolve_local_ref(schema, document, location),
            document,
            location,
            seen_refs | {reference},
        )
    raw = _mapping(schema, location)
    if "example" in raw:
        return copy.deepcopy(raw["example"])
    if "default" in raw:
        return copy.deepcopy(raw["default"])
    if isinstance(raw.get("enum"), list) and raw["enum"]:
        return copy.deepcopy(raw["enum"][0])

    schema_type = raw.get("type")
    if schema_type == "object" or "properties" in raw:
        properties = _mapping(raw.get("properties", {}), f"{location}.properties")
        return {
            name: _example_from_schema(value, document, f"{location}.properties.{name}")
            for name, value in properties.items()
        }
    if schema_type == "array":
        if "items" not in raw:
            raise OpenAPIError(f"{location}.items is required for an array schema")
        return [_example_from_schema(raw["items"], document, f"{location}.items")]
    if schema_type == "integer":
        return 1
    if schema_type == "number":
        return 1.0
    if schema_type == "boolean":
        return True
    if schema_type == "string" or schema_type is None:
        return "example"
    raise OpenAPIError(f"{location}.type is not supported: {schema_type}")


def _response_example(
    operation: Mapping[str, Any], document: Mapping[str, Any], location: str
) -> tuple[int, Any]:
    raw_responses = _mapping(operation.get("responses"), f"{location}.responses")
    responses: dict[str, Any] = {}
    for raw_code, response in raw_responses.items():
        code = str(raw_code)
        if code in responses:
            raise OpenAPIError(f"{location}.responses contains duplicate status: {code}")
        responses[code] = response
    selected_code: str | None = next((code for code in _SUCCESS_CODES if code in responses), None)
    if selected_code is None:
        selected_code = next(
            (
                code
                for code in responses
                if code == "2XX" or (code.startswith("2") and code.isdigit())
            ),
            None,
        )
    if selected_code is None:
        raise OpenAPIError(f"{location}.responses has no successful 2xx response")
    response = _resolve_local_ref(
        responses[selected_code], document, f"{location}.responses.{selected_code}"
    )
    response = _mapping(response, f"{location}.responses.{selected_code}")
    content = _mapping(response.get("content"), f"{location}.responses.{selected_code}.content")
    media_type = content.get("application/json")
    if media_type is None:
        media_type = next(iter(content.values()), None)
    if media_type is None:
        raise OpenAPIError(f"{location}.responses.{selected_code} has no response content")
    media_type = _resolve_local_ref(media_type, document, f"{location}.content")
    media_type = _mapping(media_type, f"{location}.content")
    if "example" in media_type:
        return int(selected_code), copy.deepcopy(media_type["example"])
    examples = media_type.get("examples")
    if isinstance(examples, Mapping) and examples:
        first_name = sorted(examples)[0]
        first = _resolve_local_ref(
            examples[first_name], document, f"{location}.examples.{first_name}"
        )
        first = _mapping(first, f"{location}.examples.{first_name}")
        if "value" not in first:
            raise OpenAPIError(f"{location}.examples.{first_name}.value is required")
        return int(selected_code), copy.deepcopy(first["value"])
    if "schema" not in media_type:
        raise OpenAPIError(f"{location}.response needs example, examples, or schema")
    status = 200 if selected_code == "2XX" else int(selected_code)
    return status, _example_from_schema(media_type["schema"], document, f"{location}.schema")


def _security_requirements(
    operation: Mapping[str, Any], document: Mapping[str, Any], location: str
) -> tuple[bool, tuple[str, ...]]:
    if "security" in operation:
        raw_security = operation["security"]
    else:
        raw_security = document.get("security", [])
    if raw_security == []:
        return False, ()
    if not isinstance(raw_security, list) or not raw_security:
        raise OpenAPIError(f"{location}.security must be a list")
    if len(raw_security) != 1:
        raise OpenAPIError(f"{location}.security must declare one testable alternative")
    requirement = _mapping(raw_security[0], f"{location}.security[0]")
    if len(requirement) != 1:
        raise OpenAPIError(f"{location}.security[0] must name one security scheme")
    scheme_name, scopes = next(iter(requirement.items()))
    components = _mapping(document.get("components", {}), "components")
    schemes = _mapping(components.get("securitySchemes", {}), "components.securitySchemes")
    scheme = _resolve_local_ref(
        schemes.get(scheme_name), document, f"security scheme {scheme_name}"
    )
    scheme = _mapping(scheme, f"security scheme {scheme_name}")
    scheme_type = scheme.get("type")
    scheme_variant = scheme.get("scheme") if scheme_type == "http" else scheme.get("in")
    if isinstance(scheme_type, str):
        scheme_type = scheme_type.lower()
    if isinstance(scheme_variant, str):
        scheme_variant = scheme_variant.lower()
    if (scheme_type, scheme_variant) not in _SUPPORTED_SECURITY_TYPES:
        raise OpenAPIError(
            f"security scheme {scheme_name} is not supported by the atomic mock: "
            f"{scheme_type}/{scheme_variant}; only supports http/bearer"
        )
    if not isinstance(scopes, list) or any(
        not isinstance(scope, str) or not scope.strip() for scope in scopes
    ):
        raise OpenAPIError(f"{location}.security[0].{scheme_name} must contain string scopes")
    return True, tuple(scopes)


def openapi_to_scenario(
    source: str | Path | Mapping[str, Any],
    *,
    auth: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compile OpenAPI operations into the existing mock-rest config shape.

    ``auth`` is intentionally supplied separately from the OpenAPI document.
    The document describes the required scheme; the test owns its synthetic
    token, expiry budget, and granted scopes.
    """

    document = _load_document(source)
    version = document.get("openapi")
    if not isinstance(version, str) or not version.startswith("3."):
        raise OpenAPIError("only OpenAPI 3.x documents are supported")
    paths = _mapping(document.get("paths"), "paths")
    if not paths:
        raise OpenAPIError("paths must contain at least one operation")

    routes: list[dict[str, Any]] = []
    capability: dict[str, dict[str, list[int]]] = {}
    for path, path_item in paths.items():
        path = _nonempty_string(path, "paths key")
        if not path.startswith("/"):
            raise OpenAPIError(f"paths key must be absolute: {path}")
        path_item = _mapping(path_item, f"paths.{path}")
        for method, operation in path_item.items():
            method_name = method.upper()
            if method_name not in _HTTP_METHODS:
                if method in {"parameters", "summary", "description", "servers"}:
                    continue
                raise OpenAPIError(f"paths.{path}.{method} is not a supported HTTP method")
            operation = _mapping(operation, f"paths.{path}.{method}")
            status, example = _response_example(operation, document, f"paths.{path}.{method}")
            auth_required, scopes = _security_requirements(
                operation, document, f"paths.{path}.{method}"
            )
            route: dict[str, Any] = {
                "path": path,
                "method": method_name,
                "response": {"json": example},
                "status": status,
                "auth_required": auth_required,
            }
            if scopes:
                route["required_scopes"] = list(scopes)
            routes.append(route)
            capability.setdefault(path, {})[method_name] = [status]

    scenario: dict[str, Any] = {
        "version": 1,
        "routes": routes,
        "capability": {"metrics": {}, "endpoints": capability},
    }
    if auth is not None:
        scenario["auth"] = copy.deepcopy(dict(auth))
    return scenario
