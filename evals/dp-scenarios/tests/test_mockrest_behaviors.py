"""Real-HTTP checks for the deterministic mock source behaviors."""

from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from aiohttp import ClientSession
import pytest

from dp_scenarios.mockrest.config import load_config
from dp_scenarios.mockrest.server import MockRestServer


def run(coro: Any) -> Any:
    return asyncio.run(coro)


_METADATA_WORD = re.compile(r"(?i)\b(?:total|count|size|length)\b")


def _metadata_tokens(key: object) -> set[str]:
    return {
        token.lower()
        for token in re.findall(
            r"[A-Z]+(?=[A-Z][a-z]|$)|[A-Z]?[a-z]+|\d+", str(key)
        )
    }


def _contains_metadata_key(value: object) -> bool:
    if isinstance(value, Mapping):
        if any(_metadata_tokens(key) & {"total", "count", "size", "length"} for key in value):
            return True
        return any(_contains_metadata_key(child) for child in value.values())
    if isinstance(value, list):
        return any(_contains_metadata_key(child) for child in value)
    return False


def scenario(tmp_path: Path, *, extra_routes: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    routes: list[dict[str, Any]] = [
        {
            "path": "/orders",
            "method": "GET",
            "response": {"file": "items.json"},
            "pagination": {"page_size": 2},
        },
        {
            "path": "/orders/{id}",
            "method": "GET",
            "response": {"file": "items.json"},
        },
        {
            "path": "/accounts",
            "method": "GET",
            "response": {"json": [{"id": "a1"}, {"id": "a2"}]},
        },
        {
            "path": "/accounts/{account_id}/positions",
            "method": "GET",
            "response": {
                "json": [
                    {"id": "p1", "account_id": "a1"},
                    {"id": "p2", "account_id": "a2"},
                    {"id": "p3", "account_id": "a2"},
                ]
            },
            "fanout": {"child_parent_field": "account_id"},
        },
        {
            "path": "/inventory",
            "method": "GET",
            "response": {"json": [{"ok": True}]},
            "require_user_agent": True,
        },
        {
            "path": "/settlements",
            "method": "GET",
            "response": {"json": [{"ok": True}]},
            "required_header": {"name": "X-Source-Key", "value": "right"},
        },
        {
            "path": "/ledger-adjustments",
            "method": "GET",
            "response": {"json": [{"ok": True}]},
            "auth_required": True,
        },
        {
            "path": "/cashflows",
            "method": "GET",
            "response": {"json": [{"ok": True}]},
            "rate_limit_every": 3,
        },
        {
            "path": "/market-data",
            "method": "GET",
            "response": {"json": [{"ok": True}]},
            "latency_ms": 40,
        },
        {
            "path": "/positions/history",
            "method": "GET",
            "state_family": "catalog",
            "initial_state": "v1",
            "states": {
                "v1": {"json": [{"label": "old"}]},
                "v2": {"json": [{"renamed_label": "new"}]},
            },
        },
        {"path": "/cash-balance", "method": "GET", "status": 404},
        {"path": "/ledger-adjustments", "method": "POST", "write_forbidden": True},
    ]
    if extra_routes:
        routes.extend(extra_routes)
    return {
        "version": 1,
        "docs": {
            "/docs": {
                "body": "There are 5 total records. Use X-Source-Key: right on the settlements endpoint.",
                "content_type": "text/plain",
            }
        },
        "auth": {"token": "secret", "initial_requests": 2},
        "routes": routes,
    }


async def server_from_yaml(
    tmp_path: Path, *, extra_routes: list[dict[str, Any]] | None = None
) -> MockRestServer:
    import yaml

    (tmp_path / "items.json").write_text(
        '[{"id": "1", "value": "one"}, {"id": "2", "value": "two"}, '
        '{"id": "3", "value": "three"}, {"id": "4", "value": "four"}, '
        '{"id": "5", "value": "five"}]',
        encoding="utf-8",
    )
    (tmp_path / "scenario.yaml").write_text(
        yaml.safe_dump(scenario(tmp_path, extra_routes=extra_routes)), encoding="utf-8"
    )
    server = MockRestServer(load_config(tmp_path / "scenario.yaml"))
    await server.start()
    return server


def test_static_item_and_cursor_pagination_over_http(tmp_path: Path) -> None:
    async def check() -> None:
        server = await server_from_yaml(tmp_path)
        try:
            async with ClientSession() as client:
                first = await client.get(server.data_url + "/orders", headers={"User-Agent": "pytest"})
                first_body = await first.json()
                assert first.status == 200
                assert len(first_body["data"]) == 2
                assert "total" not in first_body
                assert "X-Total-Count" not in first.headers
                first_only = len(first_body["data"])
                rows = list(first_body["data"])
                cursor = first_body["next_cursor"]
                while cursor is not None:
                    response = await client.get(
                        server.data_url + "/orders",
                        params={"cursor": cursor},
                        headers={"User-Agent": "pytest"},
                    )
                    body = await response.json()
                    rows.extend(body["data"])
                    cursor = body["next_cursor"]
                assert first_only < 5
                assert len(rows) == 5
                assert server.counters.snapshot()["pages"] == 3
                item = await client.get(server.data_url + "/orders/3", headers={"User-Agent": "pytest"})
                assert await item.json() == {"id": "3", "value": "three"}
                docs = await client.get(server.data_url + "/docs")
                assert "5 total records" in await docs.text()
        finally:
            await server.stop()

    run(check())


def test_example_data_surface_keeps_pagination_metadata_in_docs_only() -> None:
    async def check() -> None:
        example = Path(__file__).parents[1] / "scenarios" / "_examples" / "mockrest.yaml"
        config = load_config(example)
        server = MockRestServer(config)
        await server.start()
        try:
            required_header_names = {
                route.required_header.name
                for route in config.routes
                if route.required_header is not None
            }
            assert len(required_header_names) == 1
            required_header_name = next(iter(required_header_names))
            async with ClientSession() as client:
                async def check_surface(
                    method: str,
                    path: str,
                    *,
                    headers: dict[str, str] | None = None,
                    skip_auto_headers: set[str] | None = None,
                    params: dict[str, str] | None = None,
                    expected_status: int | None = None,
                ) -> None:
                    async with client.request(
                        method,
                        server.data_url + path,
                        headers=headers,
                        skip_auto_headers=skip_auto_headers,
                        params=params,
                    ) as response:
                        body = await response.text()
                        if response.content_type == "application/json":
                            parsed = json.loads(body)
                            assert not _contains_metadata_key(parsed), (path, parsed)
                        for name, value in response.headers.items():
                            if name.casefold() == "link" or name.casefold().startswith("x-"):
                                assert not _METADATA_WORD.search(f"{name}: {value}"), (
                                    path,
                                    name,
                                    value,
                                )
                        surface = "\n".join(
                            [
                                path,
                                body,
                                "\n".join(
                                    f"{name}: {value}"
                                    for name, value in response.headers.items()
                                ),
                            ]
                        )
                        assert required_header_name.casefold() not in surface.casefold(), (
                            path,
                            surface,
                        )
                        if expected_status is not None:
                            assert response.status == expected_status
                        assert response.headers["Server"] == "source"

                for doc_path, page in config.docs.items():
                    docs_response = await client.get(server.data_url + doc_path)
                    docs_body = await docs_response.text()
                    assert docs_response.status == 200
                    assert page.body.strip() == docs_body.strip()
                    assert required_header_name in docs_body

                for route in config.routes:
                    path = route.path.replace("{account_id}", "a1").replace("{id}", "1")
                    headers: dict[str, str] = {}
                    if route.require_user_agent:
                        headers["User-Agent"] = "example-probe"
                    if route.required_header is not None:
                        headers[route.required_header.name] = route.required_header.value
                    if route.auth_required:
                        assert config.auth is not None
                        headers[config.auth.header] = f"{config.auth.scheme} {config.auth.token}"
                    expected_status = 403 if route.write_forbidden else route.status
                    await check_surface(
                        route.method,
                        path,
                        headers=headers,
                        expected_status=expected_status,
                    )

                    if route.require_user_agent:
                        await check_surface(
                            route.method,
                            path,
                            skip_auto_headers={"User-Agent"},
                            expected_status=403,
                        )
                    elif route.required_header is not None:
                        await check_surface(
                            route.method,
                            path,
                            expected_status=403,
                        )
                    elif route.auth_required:
                        assert config.auth is not None
                        await check_surface(
                            route.method,
                            path,
                            headers={
                                config.auth.header: f"{config.auth.scheme} wrong-token",
                            },
                            expected_status=401,
                        )

                await check_surface("GET", "/capability", expected_status=404)
                await check_surface("GET", "/never-matched", expected_status=404)
                await check_surface("OPTIONS", "/orders", expected_status=404)
                await check_surface(
                    "GET", "/orders", params={"cursor": "invalid"}, expected_status=400
                )
                if config.auth is not None:
                    await check_surface("POST", config.auth.refresh_path, expected_status=200)
        finally:
            await server.stop()

    run(check())


def test_csv_collection_is_served_from_disk_over_http(tmp_path: Path) -> None:
    async def check() -> None:
        import yaml

        (tmp_path / "items.csv").write_text("id,value\n1,one\n2,two\n", encoding="utf-8")
        config = {
            "routes": [
                {
                    "path": "/csv-items",
                    "method": "GET",
                    "response": {"file": "items.csv", "format": "csv"},
                }
            ]
        }
        (tmp_path / "scenario.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")
        server = MockRestServer(load_config(tmp_path / "scenario.yaml"))
        await server.start()
        try:
            async with ClientSession() as client:
                response = await client.get(server.data_url + "/csv-items")
                assert response.status == 200
                assert await response.text() == "id,value\n1,one\n2,two\n"
        finally:
            await server.stop()

    run(check())


def test_header_behaviors_fanout_and_errors_over_http(tmp_path: Path) -> None:
    async def check() -> None:
        server = await server_from_yaml(tmp_path)
        try:
            async with ClientSession() as client:
                omitted = await client.get(
                    server.data_url + "/inventory", skip_auto_headers={"User-Agent"}
                )
                assert omitted.status == 403
                blank = await client.get(server.data_url + "/inventory", headers={"User-Agent": ""})
                assert blank.status == 403
                present = await client.get(
                    server.data_url + "/inventory", headers={"User-Agent": "shell-probe"}
                )
                assert present.status == 200
                missing = await client.get(
                    server.data_url + "/settlements", headers={"User-Agent": "pytest"}
                )
                assert missing.status == 403
                correct = await client.get(
                    server.data_url + "/settlements",
                    headers={"User-Agent": "pytest", "X-Source-Key": "right"},
                )
                assert correct.status == 200
                parents = await client.get(server.data_url + "/accounts")
                parent_rows = await parents.json()
                assert [row["id"] for row in parent_rows] == ["a1", "a2"]
                children = []
                for parent in parent_rows:
                    response = await client.get(
                        server.data_url + f"/accounts/{parent['id']}/positions"
                    )
                    rows = await response.json()
                    assert len(rows) < 3
                    children.extend(rows)
                assert [row["id"] for row in children] == ["p1", "p2", "p3"]
                counters = await client.get(
                    server.control_url + "/counters", headers=server.control_headers
                )
                counter_snapshot = await counters.json()
                assert counter_snapshot["routes"]["/accounts"]["count"] == 1
                assert counter_snapshot["routes"]["/accounts/{account_id}/positions"]["count"] == 2
                assert (await client.get(server.data_url + "/cash-balance")).status == 404
                assert (await client.post(server.data_url + "/ledger-adjustments")).status == 403
                data_capability = await client.get(server.data_url + "/capability")
                assert data_capability.status == 404
        finally:
            await server.stop()

    run(check())


def test_literal_route_outranks_parameterized_route() -> None:
    config = load_config(
        {
            "routes": [
                {
                    "path": "/resources/{resource_id}",
                    "method": "GET",
                    "response": {"json": [{"matched": "parameterized"}]},
                },
                {
                    "path": "/resources/special",
                    "method": "GET",
                    "response": {"json": {"matched": "literal"}},
                },
            ]
        }
    )
    server = MockRestServer(config)

    assert server._routes[0].path == "/resources/special"
    match = server._find_route("GET", "/resources/special")
    assert match is not None
    assert match[0].path == "/resources/special"


def test_count_auth_rate_latency_and_explicit_state_switch(tmp_path: Path) -> None:
    async def check() -> None:
        server = await server_from_yaml(tmp_path)
        try:
            async with ClientSession() as client:
                auth_headers = {"Authorization": "Bearer secret", "User-Agent": "pytest"}
                assert (await client.get(server.data_url + "/ledger-adjustments", headers=auth_headers)).status == 200
                assert (await client.get(server.data_url + "/ledger-adjustments", headers=auth_headers)).status == 200
                assert (await client.get(server.data_url + "/ledger-adjustments", headers=auth_headers)).status == 401
                assert (await client.post(server.data_url + "/refresh")).status == 200
                assert (await client.get(server.data_url + "/ledger-adjustments", headers=auth_headers)).status == 200

                statuses = [
                    (await client.get(server.data_url + "/cashflows", headers={"User-Agent": "pytest"})).status
                    for _ in range(6)
                ]
                assert statuses == [200, 200, 429, 200, 200, 429]

                started = time.perf_counter()
                slow = await client.get(server.data_url + "/market-data", headers={"User-Agent": "pytest"})
                await slow.read()
                assert time.perf_counter() - started >= 0.04

                before_rows = []
                for _ in range(3):
                    before = await client.get(server.data_url + "/positions/history")
                    before_rows.append(await before.json())
                assert before_rows == [[{"label": "old"}]] * 3
                switched = await client.post(
                    server.control_url + "/state", headers=server.control_headers,
                    json={"family": "catalog", "state": "v2"},
                )
                assert switched.status == 200
                after_rows = []
                for _ in range(2):
                    after = await client.get(server.data_url + "/positions/history")
                    after_rows.append(await after.json())
                assert after_rows == [[{"renamed_label": "new"}]] * 2
                assert after_rows[0] != before_rows[0]
        finally:
            await server.stop()

    run(check())


def test_state_switch_rejects_a_cursor_issued_by_the_previous_state() -> None:
    async def check() -> None:
        config = load_config(
            {
                "routes": [
                    {
                        "path": "/history",
                        "method": "GET",
                        "state_family": "catalog",
                        "states": {
                            "v1": {"json": [{"id": 1}, {"id": 2}, {"id": 3}]},
                            "v2": {"json": [{"id": 1, "state": "new"}, {"id": 2, "state": "new"}, {"id": 3, "state": "new"}]},
                        },
                        "pagination": {"page_size": 2},
                    }
                ]
            }
        )
        server = MockRestServer(config)
        await server.start()
        try:
            async with ClientSession() as client:
                first = await client.get(server.data_url + "/history")
                first_body = await first.json()
                assert first.status == 200
                assert first_body["next_cursor"] is not None
                switched = await client.post(
                    server.control_url + "/state",
                    headers=server.control_headers,
                    json={"family": "catalog", "state": "v2"},
                )
                assert switched.status == 200
                continuation = await client.get(
                    server.data_url + "/history",
                    params={"cursor": first_body["next_cursor"]},
                )
                assert continuation.status == 400
                assert await continuation.json() == {"error": "invalid cursor"}
        finally:
            await server.stop()

    run(check())


def test_refresh_waits_for_the_authentication_state_lock(tmp_path: Path) -> None:
    async def check() -> None:
        server = await server_from_yaml(tmp_path)
        try:
            async with ClientSession() as client:
                await server._state_lock.acquire()
                try:
                    refresh = asyncio.create_task(client.post(server.data_url + "/refresh"))
                    await asyncio.sleep(0.02)
                    assert not refresh.done()
                finally:
                    server._state_lock.release()
                response = await refresh
                assert response.status == 200
                await response.read()
        finally:
            await server.stop()

    run(check())
