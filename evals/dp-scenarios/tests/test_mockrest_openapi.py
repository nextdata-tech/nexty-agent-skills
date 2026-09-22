"""Atomic OpenAPI-to-mock source coverage for desktop API-generation tests."""

from __future__ import annotations

import asyncio
import copy
from pathlib import Path
from typing import Any

from aiohttp import ClientSession
import pytest

from dp_scenarios.mockrest import MockRestServer, OpenAPIError, openapi_to_scenario
from dp_scenarios.mockrest.config import ConfigError, load_config


OPENAPI = {
    "openapi": "3.0.3",
    "components": {
        "schemas": {
            "Order": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "example": "order-1"},
                    "amount": {"type": "number", "example": 12.5},
                },
            }
        },
        "securitySchemes": {
            "bearerAuth": {"type": "http", "scheme": "bearer"},
        },
    },
    "paths": {
        "/orders": {
            "get": {
                "security": [{"bearerAuth": ["orders:read"]}],
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "data": {
                                            "type": "array",
                                            "items": {"$ref": "#/components/schemas/Order"},
                                        }
                                    },
                                }
                            }
                        }
                    }
                },
            }
        },
        "/health": {
            "get": {
                "security": [],
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {"example": {"ok": True}}
                        }
                    }
                },
            }
        },
    },
}


def run(coro: Any) -> Any:
    return asyncio.run(coro)


def test_openapi_compiler_materializes_schema_examples_and_security() -> None:
    scenario = openapi_to_scenario(
        OPENAPI,
        auth={"token": "synthetic-token", "initial_requests": 10, "scopes": ["orders:read"]},
    )

    orders = next(route for route in scenario["routes"] if route["path"] == "/orders")
    health = next(route for route in scenario["routes"] if route["path"] == "/health")
    assert orders["auth_required"] is True
    assert orders["required_scopes"] == ["orders:read"]
    assert orders["response"] == {"json": {"data": [{"id": "order-1", "amount": 12.5}]}}
    assert health["auth_required"] is False
    assert scenario["capability"]["endpoints"]["/orders"]["GET"] == [200]


def test_openapi_yaml_accepts_unquoted_numeric_response_keys(tmp_path: Path) -> None:
    path = tmp_path / "openapi.yaml"
    path.write_text(
        """
openapi: 3.0.3
paths:
  /health:
    get:
      responses:
        200:
          content:
            application/json:
              example:
                ok: true
""",
        encoding="utf-8",
    )

    scenario = openapi_to_scenario(path)

    assert scenario["routes"] == [
        {
            "path": "/health",
            "method": "GET",
            "response": {"json": {"ok": True}},
            "status": 200,
            "auth_required": False,
        }
    ]


def test_openapi_preserves_success_status_codes() -> None:
    document = {
        "openapi": "3.0.3",
        "paths": {
            "/created": {
                "get": {
                    "responses": {
                        201: {
                            "content": {
                                "application/json": {"example": {"created": True}}
                            }
                        }
                    }
                }
            }
        },
    }

    async def check() -> None:
        server = MockRestServer(load_config(openapi_to_scenario(document)))
        await server.start()
        try:
            async with ClientSession() as client:
                response = await client.get(server.data_url + "/created")
                assert response.status == 201
                assert await response.json() == {"created": True}
        finally:
            await server.stop()

    run(check())


def test_openapi_security_distinguishes_401_from_403_and_success() -> None:
    async def check() -> None:
        scenario = openapi_to_scenario(
            OPENAPI,
            auth={"token": "synthetic-token", "initial_requests": 10, "scopes": []},
        )
        server = MockRestServer(load_config(scenario))
        await server.start()
        try:
            async with ClientSession() as client:
                missing = await client.get(server.data_url + "/orders")
                assert missing.status == 401

                insufficient = await client.get(
                    server.data_url + "/orders",
                    headers={"Authorization": "Bearer synthetic-token"},
                )
                assert insufficient.status == 403

                health = await client.get(server.data_url + "/health")
                assert health.status == 200
                assert await health.json() == {"ok": True}

            authorized_scenario = openapi_to_scenario(
                OPENAPI,
                auth={
                    "token": "synthetic-token",
                    "initial_requests": 10,
                    "scopes": ["orders:read"],
                },
            )
            authorized_server = MockRestServer(load_config(authorized_scenario))
            await authorized_server.start()
            try:
                async with ClientSession() as authorized_client:
                    response = await authorized_client.get(
                        authorized_server.data_url + "/orders",
                        headers={"Authorization": "Bearer synthetic-token"},
                    )
                    assert response.status == 200
                    assert await response.json() == {
                        "data": [{"id": "order-1", "amount": 12.5}]
                    }
            finally:
                await authorized_server.stop()
        finally:
            await server.stop()

    run(check())


def test_openapi_rejects_ambiguous_security_alternatives() -> None:
    document = {
        **OPENAPI,
        "paths": {
            "/orders": {
                "get": {
                    "security": [{"bearerAuth": []}, {}],
                    "responses": {
                        "200": {
                            "content": {"application/json": {"example": []}}
                        }
                    },
                }
            }
        },
    }
    with pytest.raises(OpenAPIError, match="one testable alternative"):
        openapi_to_scenario(document, auth={"token": "t", "initial_requests": 1})


def test_openapi_rejects_credential_modes_not_modeled_by_the_atomic_mock() -> None:
    document = copy.deepcopy(OPENAPI)
    document["components"]["securitySchemes"]["bearerAuth"] = {
        "type": "http",
        "scheme": "basic",
    }
    with pytest.raises(OpenAPIError, match="only supports http/bearer"):
        openapi_to_scenario(document)


def test_required_scopes_cannot_be_configured_without_authentication() -> None:
    with pytest.raises(ConfigError, match="required_scopes requires auth_required"):
        load_config(
            {
                "routes": [
                    {
                        "path": "/orders",
                        "response": {"json": []},
                        "required_scopes": ["orders:read"],
                    }
                ]
            }
        )
