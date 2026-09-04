"""Capability manifest and strict YAML validation checks."""

from __future__ import annotations

import asyncio
import copy
from pathlib import Path

import pytest
from aiohttp import ClientSession

from dp_scenarios.mockrest.capability import CapabilityError, CapabilityManifest
from dp_scenarios.mockrest.config import ConfigError, load_config
from dp_scenarios.mockrest.server import MockRestServer


def test_capability_manifest_round_trip_and_control_port_only(tmp_path: Path) -> None:
    manifest = CapabilityManifest.from_mapping(
        {
            "metrics": {"revenue": "supported", "margin": "proxy", "secret": "impossible"},
            "endpoints": {"/rows": {"GET": [200], "POST": [403]}, "/gone": [404]},
        }
    )
    target = manifest.write(tmp_path / "capability.json")
    loaded = CapabilityManifest.load(target)
    assert loaded.as_dict() == manifest.as_dict()
    assert loaded.status_codes("/rows", "POST") == (403,)
    assert loaded.status_codes("/gone") == (404,)

    async def check() -> None:
        config = load_config(
            {
                "capability": manifest.as_dict(),
                "routes": [{"path": "/rows", "method": "GET", "response": {"json": []}}],
            }
        )
        server = MockRestServer(config)
        await server.start()
        try:
            async with ClientSession() as client:
                assert (await client.get(server.data_url + "/capability")).status == 404
                assert (
                    await client.get(server.control_url + "/capability")
                ).status == 401
                response = await client.get(
                    server.control_url + "/capability", headers=server.control_headers
                )
                assert await response.json() == manifest.as_dict()
        finally:
            await server.stop()

    asyncio.run(check())


@pytest.mark.parametrize(
    "scope",
    [
        "scenario",
        "response",
        "pagination",
        "required_header",
        "fanout",
        "rate_limit",
        "auth",
        "control",
        "docs",
        "capability",
    ],
)
def test_unknown_config_key_is_rejected_at_every_scope(scope: str) -> None:
    config: dict[str, object] = {
        "routes": [{"path": "/rows", "method": "GET", "response": {"json": []}}]
    }
    route = config["routes"][0]  # type: ignore[index]
    assert isinstance(route, dict)
    if scope == "scenario":
        config["not_a_behavior"] = True
    elif scope == "response":
        route["response"]["not_a_behavior"] = True  # type: ignore[index]
    elif scope == "pagination":
        route["pagination"] = {"page_size": 1, "not_a_behavior": True}
    elif scope == "required_header":
        route["required_header"] = {"name": "X-Key", "value": "yes", "not_a_behavior": True}
    elif scope == "fanout":
        config["routes"] = [
            {
                "path": "/parents/{parent_id}/rows",
                "method": "GET",
                "response": {"json": []},
                "fanout": {"child_parent_field": "parent_id", "not_a_behavior": True},
            }
        ]
    elif scope == "rate_limit":
        route["rate_limit"] = {"every": 2, "not_a_behavior": True}
    elif scope == "auth":
        route["auth_required"] = True
        config["auth"] = {"token": "token", "initial_requests": 1, "not_a_behavior": True}
    elif scope == "control":
        config["control"] = {"health_path": "/health", "not_a_behavior": True}
    elif scope == "docs":
        config["docs"] = {"/docs": {"body": "docs", "not_a_behavior": True}}
    elif scope == "capability":
        config["capability"] = {"metrics": {}, "not_a_behavior": True}
    with pytest.raises(ConfigError, match="unknown key"):
        load_config(copy.deepcopy(config))


def test_capability_labels_and_statuses_are_closed() -> None:
    with pytest.raises(CapabilityError):
        CapabilityManifest.from_mapping({"metrics": {"x": "maybe"}})
    with pytest.raises(CapabilityError):
        CapabilityManifest.from_mapping({"endpoints": {"gone": [404]}})
    with pytest.raises(CapabilityError, match="method"):
        CapabilityManifest.from_mapping({"endpoints": {"/rows": {"GEET": [200]}}})


@pytest.mark.parametrize(
    "behavior",
    [
        ("response", {"json": []}),
        ("require_user_agent", True),
        ("required_header", {"name": "X-Key", "value": "yes"}),
        ("rate_limit_every", 2),
        ("auth_required", True),
        ("pagination", {"page_size": 1}),
        ("fanout", {"child_parent_field": "parent_id"}),
        ("states", {"v1": {"json": []}}),
    ],
    ids=lambda item: item[0] if isinstance(item, tuple) else str(item),
)
def test_inert_behaviors_are_rejected_on_error_routes(behavior: tuple[str, object]) -> None:
    key, value = behavior
    path = "/parents/{parent_id}/rows" if key == "fanout" else "/rows"
    route: dict[str, object] = {
        "path": path,
        "method": "GET",
        "response": {"json": []},
        "status": 404,
        key: value,
    }
    if key == "states":
        route.pop("response")
        route["state_family"] = "rows"
    with pytest.raises(ConfigError, match="behavior key"):
        load_config({"routes": [route]})


def test_rate_limiting_is_rejected_on_write_forbidden_routes() -> None:
    with pytest.raises(ConfigError, match="behavior key"):
        load_config(
            {
                "routes": [
                    {
                        "path": "/ledger-adjustments",
                        "method": "POST",
                        "write_forbidden": True,
                        "rate_limit_every": 2,
                    }
                ]
            }
        )


@pytest.mark.parametrize(
    "config",
    [
        {
            "docs": {"/rows": "docs"},
            "routes": [{"path": "/rows", "response": {"json": []}}],
        },
        {
            "auth": {"token": "token", "initial_requests": 1, "refresh_path": "/rows"},
            "routes": [
                {"path": "/rows", "response": {"json": []}, "auth_required": True}
            ],
        },
        {
            "auth": {"token": "token", "initial_requests": 1, "refresh_path": "/docs"},
            "docs": {"/docs": "docs"},
            "routes": [{"path": "/rows", "response": {"json": []}, "auth_required": True}],
        },
    ],
    ids=["docs-route", "refresh-route", "refresh-docs"],
)
def test_docs_refresh_and_routes_cannot_overlap(config: dict[str, object]) -> None:
    with pytest.raises(ConfigError, match="overlaps"):
        load_config(config)


def test_fanout_requires_a_path_parameter() -> None:
    with pytest.raises(ConfigError, match="path parameter"):
        load_config(
            {
                "routes": [
                    {
                        "path": "/positions",
                        "response": {"json": []},
                        "fanout": {"child_parent_field": "account_id"},
                    }
                ]
            }
        )


def test_encoding_requires_a_file_and_ports_must_be_distinct() -> None:
    with pytest.raises(ConfigError, match="requires file"):
        load_config({"routes": [{"path": "/rows", "response": {"json": [], "encoding": "utf-8"}}]})
    with pytest.raises(ConfigError, match="different"):
        load_config(
            {
                "data_port": 18081,
                "control_port": 18081,
                "routes": [{"path": "/rows", "response": {"json": []}}],
            }
        )


def test_metric_terms_survive_the_round_trip_into_the_artifact_snapshot() -> None:
    """The gate reads `capability.json` from the artifact root, not the gold file.

    `as_dict` is what `tier.py` writes there. It emitted metrics, endpoints and
    known_absent_dimensions only, so a manifest declaring `metric_terms` parsed
    fine and then lost them on the way to the one consumer that needs them: a
    live driven run graded `capability_metric_terms_not_declared` while the gold
    manifest declared four of them.
    """

    manifest = CapabilityManifest.from_mapping(
        {
            "metrics": {"time_in_stage_days": "impossible", "deal_count": "supported"},
            "endpoints": {"/deals": {"GET": [200]}},
            "metric_terms": {"time_in_stage_days": ["stage_age_days", "time_in_stage"]},
        }
    )

    assert manifest.metric_terms == {"time_in_stage_days": ("stage_age_days", "time_in_stage")}
    assert manifest.as_dict()["metric_terms"] == {
        "time_in_stage_days": ["stage_age_days", "time_in_stage"]
    }


def test_metric_terms_must_name_a_declared_metric() -> None:
    """A typo in a term key would otherwise silently grade nothing."""

    with pytest.raises(CapabilityError, match="undeclared metric"):
        CapabilityManifest.from_mapping(
            {
                "metrics": {"deal_count": "supported"},
                "endpoints": {},
                "metric_terms": {"tyme_in_stage_days": ["stage_age_days"]},
            }
        )
