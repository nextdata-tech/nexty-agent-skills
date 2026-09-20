"""Counter-oracle and readiness checks over real sockets."""

from __future__ import annotations

import asyncio
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from aiohttp import ClientSession
import pytest

from dp_scenarios.mockrest.config import load_config
from dp_scenarios.mockrest import cli
from dp_scenarios.mockrest.counters import RequestCounters, caller_identity
from dp_scenarios.mockrest.server import MockRestServer, wait_until_ready


def run(coro: Any) -> Any:
    return asyncio.run(coro)


def test_counters_record_routes_methods_and_identities_and_reset_on_control_port() -> None:
    async def check() -> None:
        config = load_config(
            {
                "routes": [
                    {"path": "/one", "method": "GET", "response": {"json": [{"ok": True}]}},
                    {"path": "/write", "method": "POST", "write_forbidden": True},
                ]
            }
        )
        server = MockRestServer(config)
        await server.start()
        try:
            async with ClientSession() as client:
                assert (
                    await client.get(
                        server.data_url + "/one", headers={"X-Caller-Id": "worker-a"}
                    )
                ).status == 200
                assert (await client.post(server.data_url + "/write")).status == 403
                assert (await client.get(server.data_url + "/unknown")).status == 404
                snapshot_response = await client.get(
                    server.control_url + "/counters", headers=server.control_headers
                )
                snapshot = await snapshot_response.json()
                assert snapshot["total"] == 3
                assert snapshot["routes"]["/one"]["methods"] == {"GET": 1}
                assert snapshot["routes"]["/one"]["identities"] == {"worker-a": 1}
                assert snapshot["routes"]["/write"]["methods"] == {"POST": 1}
                assert snapshot["routes"]["__unmatched__"]["count"] == 1
                assert (await client.get(server.data_url + "/counters")).status == 404
                assert (await client.post(server.data_url + "/counters/reset")).status == 404
                assert (
                    await client.post(
                        server.control_url + "/counters/reset", headers=server.control_headers
                    )
                ).status == 200
                assert (
                    await (
                        await client.get(
                            server.control_url + "/counters", headers=server.control_headers
                        )
                    ).json()
                )["total"] == 0
        finally:
            await server.stop()

    run(check())


def test_readiness_helper_probes_both_ports_before_returning() -> None:
    async def check() -> None:
        config = load_config(
            {
                "routes": [
                    {
                        "path": "/rows/{id}",
                        "method": "GET",
                        "response": {"json": [{"id": "row-1"}]},
                    },
                    {"path": "/ready", "method": "GET", "response": {"json": []}},
                ]
            }
        )
        server = MockRestServer(config)
        assert server._readiness_probe()[0] == "/ready"
        release_control = asyncio.Event()
        original_control_handler = server._control_handler

        async def delayed_control(request: Any) -> Any:
            if request.path == server.config.control.health_path:
                await release_control.wait()
            return await original_control_handler(request)

        server._control_handler = delayed_control  # type: ignore[method-assign]
        await server.start(wait_for_ready=False)
        try:
            readiness = asyncio.create_task(
                wait_until_ready(
                    server.data_url,
                    server.control_url,
                    data_probe_path="/ready",
                    control_headers=server.control_headers,
                )
            )
            await asyncio.sleep(0.02)
            assert not readiness.done()
            release_control.set()
            await readiness
            assert server.counters.snapshot()["routes"]["/ready"]["count"] == 1
            with pytest.raises(RuntimeError) as error:
                await wait_until_ready(
                    server.data_url,
                    server.control_url,
                    data_probe_path="/ready",
                    control_headers={"X-Source-Control": "wrong"},
                    deadline=0.05,
                    probe_timeout=0.01,
                    max_backoff=0.01,
                )
            assert "data probe path=/ready" in str(error.value)
            assert "last probe error=control health returned HTTP 401" in str(error.value)
            async with ClientSession() as client:
                assert (await client.get(server.data_url + "/_mockrest/health")).status == 404
                assert (
                    await client.get(
                        server.control_url + "/health", headers=server.control_headers
                    )
                ).status == 200
        finally:
            await server.stop()

    run(check())


def test_counters_are_thread_safe_for_direct_recording() -> None:
    counters = __import__("dp_scenarios.mockrest.counters", fromlist=["RequestCounters"]).RequestCounters()
    previous_interval = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)

    def record_many(index: int) -> None:
        for _ in range(2_000):
            counters.record("/route", "GET", {"X-Caller-Id": f"caller-{index}"})

    try:
        with ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(record_many, range(8)))
        snapshot = counters.snapshot()
        assert snapshot["total"] == 16_000
        assert snapshot["routes"]["/route"]["count"] == 16_000
        sequences = [event.sequence for event in counters.events]
        assert len(set(sequences)) == 16_000
        assert sorted(sequences) == list(range(1, 16_001))
    finally:
        sys.setswitchinterval(previous_interval)


def test_counters_track_successful_pagination_responses_separately() -> None:
    counters = RequestCounters()
    counters.record("/orders", "GET")
    counters.record_page()
    counters.record("/orders", "GET")
    counters.record_page()
    counters.record("/health", "GET")

    assert counters.snapshot()["total"] == 3
    assert counters.snapshot()["pages"] == 2
    counters.reset()
    assert counters.snapshot()["pages"] == 0


def test_rejected_paginated_responses_do_not_count_as_pages() -> None:
    async def check() -> None:
        config = load_config(
            {
                "routes": [
                    {
                        "path": "/orders",
                        "method": "GET",
                        "response": {"json": [{"id": 1}, {"id": 2}]},
                        "pagination": {"page_size": 1},
                        "rate_limit_every": 2,
                    }
                ]
            }
        )
        server = MockRestServer(config)
        await server.start()
        try:
            async with ClientSession() as client:
                first = await client.get(server.data_url + "/orders")
                second = await client.get(server.data_url + "/orders")
                assert first.status == 200
                assert second.status == 429
            snapshot = server.counters.snapshot()
            assert snapshot["total"] == 2
            assert snapshot["pages"] == 1
        finally:
            await server.stop()

    run(check())


def test_response_observations_are_status_bound_and_pii_projected() -> None:
    counters = RequestCounters()
    request_number = counters.record("/deals", "GET")
    counters.record_response("/deals", request_number, 200)
    counters.record_page_observation(
        rows=[
            {
                "id": "DEAL-1",
                "stage": "prospecting",
                "amount": 10,
                "status": "active",
                "updatedAt": "2024-01-01T00:00:00+00:00",
                "owner": {"email": "must-not-escape"},
            }
        ],
        next_cursor="cursor-1",
    )

    snapshot = counters.snapshot()

    assert snapshot["response_statuses"] == [{"sequence": 1, "status": 200}]
    assert snapshot["page_observations"] == [
        {
            "status": 200,
            "rows": [
                {
                    "id": "DEAL-1",
                    "stage": "prospecting",
                    "amount": 10,
                    "status": "active",
                    "updatedAt": "2024-01-01T00:00:00+00:00",
                }
            ],
            "next_cursor": "present",
        }
    ]

    restored = RequestCounters()
    restored.restore_snapshot(snapshot)
    assert restored.snapshot() == snapshot


def test_caller_identity_ignores_whitespace_and_matches_header_names_case_insensitively() -> None:
    assert caller_identity({"X-Caller-Id": "   \t"}) is None
    assert caller_identity({"x-cAlLeR-iD": "worker-a"}) == "worker-a"


def test_counters_record_rejects_empty_route_and_method() -> None:
    counters = RequestCounters()
    with pytest.raises(ValueError, match="route and method are required"):
        counters.record("", "GET")
    with pytest.raises(ValueError, match="route and method are required"):
        counters.record("/route", "")


def test_cli_readiness_record_exposes_supplied_control_secret(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    import yaml

    scenario_path = tmp_path / "scenario.yaml"
    scenario_path.write_text(
        yaml.safe_dump(
            {"routes": [{"path": "/ready", "response": {"json": []}}]}
        ),
        encoding="utf-8",
    )

    class ImmediateEvent:
        def set(self) -> None:
            return None

        async def wait(self) -> None:
            return None

    monkeypatch.setattr(cli.asyncio, "Event", ImmediateEvent)
    run(
        cli._run(
            cli._parser().parse_args(
                [str(scenario_path), "--control-secret", "runner-secret"]
            )
        )
    )
    record = json.loads(capsys.readouterr().out)
    assert record["control_secret"] == "runner-secret"
