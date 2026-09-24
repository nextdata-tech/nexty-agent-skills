"""Local auth and pagination contract tests for the OpenAPI codegen eval."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from aiohttp import ClientSession
import pytest
import yaml

from dp_scenarios.mockrest import MockRestServer, openapi_to_scenario
from dp_scenarios.mockrest.config import load_config


ROOT = Path(__file__).resolve().parents[3]
OPENAPI_PATH = ROOT / "evals" / "public" / "openapi-api-source-codegen" / "fixtures" / "openapi.yaml"
ACCESS_PATH = Path(__file__).parent / "fixtures" / "openapi-api-source-codegen" / "source-access.yaml"
ORDERS = [
    {"id": f"order-{index:03d}", "amount": index * 10.5, "status": "paid"}
    for index in range(1, 6)
]


def _read_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _resolve_schema(document: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    reference = schema.get("$ref")
    if reference is None:
        return schema
    assert isinstance(reference, str) and reference.startswith("#/")
    resolved: Any = document
    for part in reference[2:].split("/"):
        resolved = resolved[part]
    assert isinstance(resolved, dict)
    return resolved


def _assert_matches_schema(value: Any, schema: dict[str, Any], document: dict[str, Any]) -> None:
    schema = _resolve_schema(document, schema)
    expected_type = schema.get("type")
    if value is None and schema.get("nullable") is True:
        return
    if expected_type == "object":
        assert isinstance(value, dict)
        assert set(schema.get("required", ())) <= set(value)
        for key, child_schema in schema.get("properties", {}).items():
            if key in value:
                _assert_matches_schema(value[key], child_schema, document)
    elif expected_type == "array":
        assert isinstance(value, list)
        for item in value:
            _assert_matches_schema(item, schema["items"], document)
    elif expected_type == "string":
        assert isinstance(value, str)
    elif expected_type == "number":
        assert isinstance(value, (int, float)) and not isinstance(value, bool)
    if "enum" in schema:
        assert value in schema["enum"]


def _source_access() -> dict[str, Any]:
    access = _read_yaml(ACCESS_PATH)
    contract = _read_yaml(OPENAPI_PATH)
    operation = contract["paths"]["/orders"]["get"]
    required = operation["x-nexty-required-scopes"]
    assert operation["security"][0]["bearerAuth"] == []
    assert access["required_scopes"] == required
    return access


def _mock_scenario(identity: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    document = _read_yaml(OPENAPI_PATH)
    operation = document["paths"]["/orders"]["get"]
    pagination = operation["x-nexty-pagination"]
    scenario = openapi_to_scenario(
        OPENAPI_PATH,
        auth={
            "token": identity["token"],
            "initial_requests": _source_access()["initial_requests"],
            "scopes": identity["scopes"],
        },
    )
    route = next(route for route in scenario["routes"] if route["path"] == "/orders")
    route["required_scopes"] = operation["x-nexty-required-scopes"]

    # First prove that OpenAPI compilation retains a response conforming to the
    # declared envelope. The mock's paginator consumes rows, then wraps each
    # page with the same fields from the x-nexty-pagination overlay.
    media = operation["responses"]["200"]["content"]["application/json"]
    _assert_matches_schema(route["response"]["json"], media["schema"], document)
    route["response"] = {"json": ORDERS}
    route["pagination"] = {
        "page_size": pagination["page_size"],
        "cursor_param": pagination["cursor_param"],
        "items_field": pagination["items_field"],
        "cursor_field": pagination["cursor_path"],
    }
    # Keep server readiness independent of the caller's grants, without adding
    # a non-source endpoint to the OpenAPI document used by the codegen eval.
    scenario["routes"].append(
        {
            "path": "/__ready",
            "method": "GET",
            "response": {"json": {"ok": True}},
            "status": 200,
            "auth_required": False,
        }
    )
    return scenario, document


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


@pytest.mark.parametrize("request_identity", ["missing", "invalid_request_token"])
def test_openapi_mock_returns_401_for_missing_or_invalid_token(request_identity: str) -> None:
    access = _source_access()
    expected_identity = access["identities"]["api_expected_token"]
    scenario, _ = _mock_scenario(expected_identity)

    async def check() -> None:
        server = MockRestServer(load_config(scenario))
        await server.start()
        try:
            headers: dict[str, str] = {}
            if request_identity != "missing":
                token = access["identities"][request_identity]
                headers["Authorization"] = f"Bearer {token}"
            async with ClientSession() as client:
                response = await client.get(server.data_url + "/orders", headers=headers)
                assert response.status == 401
        finally:
            await server.stop()

    _run(check())


def test_openapi_mock_returns_403_for_authenticated_identity_without_scope() -> None:
    identity = _source_access()["identities"]["authenticated_without_scope"]
    scenario, _ = _mock_scenario(identity)

    async def check() -> None:
        server = MockRestServer(load_config(scenario))
        await server.start()
        try:
            async with ClientSession() as client:
                response = await client.get(
                    server.data_url + "/orders",
                    headers={"Authorization": f"Bearer {identity['token']}"},
                )
                assert response.status == 403
        finally:
            await server.stop()

    _run(check())


def test_openapi_mock_returns_schema_valid_cursor_pages_for_authorized_identity() -> None:
    access = _source_access()
    identity = access["identities"]["authorized"]
    scenario, document = _mock_scenario(identity)
    operation = document["paths"]["/orders"]["get"]
    pagination = operation["x-nexty-pagination"]
    envelope_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]

    async def check() -> None:
        server = MockRestServer(load_config(scenario))
        await server.start()
        try:
            cursor: str | None = None
            sent_cursors: list[str | None] = []
            observed_orders: list[dict[str, Any]] = []
            async with ClientSession() as client:
                for _ in range(4):
                    sent_cursors.append(cursor)
                    params = {pagination["cursor_param"]: cursor} if cursor else None
                    response = await client.get(
                        server.data_url + "/orders",
                        params=params,
                        headers={"Authorization": f"Bearer {identity['token']}"},
                    )
                    assert response.status == 200
                    payload = await response.json()
                    _assert_matches_schema(payload, envelope_schema, document)
                    page = payload[pagination["items_field"]]
                    assert 0 < len(page) <= pagination["page_size"]
                    observed_orders.extend(page)
                    next_cursor = payload[pagination["cursor_path"]]
                    if next_cursor is None:
                        break
                    assert next_cursor != cursor
                    cursor = next_cursor
                else:
                    pytest.fail("cursor pagination did not terminate")

            assert len(sent_cursors) == 3
            assert sent_cursors[0] is None
            assert all(cursor for cursor in sent_cursors[1:])
            assert [row["id"] for row in observed_orders] == [row["id"] for row in ORDERS]
        finally:
            await server.stop()

    _run(check())
