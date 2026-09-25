"""Deferred mock-rest responses backed by runner-private fixture tables."""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from dp_scenarios.mockrest import MockRestServer
from dp_scenarios.mockrest.config import (
    ConfigError,
    fixture_source_tables,
    load_config,
    resolve_fixture_sources,
)


def _config(response: object) -> dict[str, object]:
    return {"version": 1, "routes": [{"path": "/events", "method": "GET", "response": response}]}


@pytest.mark.parametrize(
    "response",
    [
        {},
        {"json": [], "file": "rows.json"},
        {"json": [], "fixture_source": "events"},
        {"file": "rows.json", "fixture_source": "events"},
    ],
)
def test_response_requires_exactly_one_source(response: object) -> None:
    with pytest.raises(ConfigError, match="exactly one of json, file, or fixture_source"):
        load_config(_config(response))


@pytest.mark.parametrize(
    "response, message",
    [
        ({"fixture_source": "events", "format": "csv"}, "format must be json"),
        ({"fixture_source": "events", "encoding": "utf-8"}, "encoding is not allowed"),
    ],
)
def test_fixture_source_accepts_json_without_encoding(
    response: object, message: str
) -> None:
    with pytest.raises(ConfigError, match=message):
        load_config(_config(response))


def test_response_and_state_fixture_sources_are_deferred() -> None:
    response_config = load_config(
        _config({"fixture_source": "events_v1", "item_key": "event_id", "format": "json"})
    )
    response = response_config.routes[0].response
    assert response is not None
    assert response.data is None
    assert response.serialized_json is None
    assert response.fixture_source == "events_v1"
    assert response.item_key == "event_id"
    assert response.deferred
    assert fixture_source_tables(response_config) == frozenset({"events_v1"})

    state_config = load_config(
        {
            "routes": [
                {
                    "path": "/history",
                    "state_family": "catalog",
                    "initial_state": "v1",
                    "states": {
                        "v1": {"fixture_source": "events_v1"},
                        "v2": {"fixture_source": "events_v2"},
                    },
                }
            ]
        }
    )
    assert all(spec.deferred for spec in state_config.routes[0].states.values())
    assert fixture_source_tables(state_config) == frozenset({"events_v1", "events_v2"})


def test_resolver_loads_canonical_json_and_checks_missing_shape_and_hash(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "oracle" / "source"
    source_dir.mkdir(parents=True)
    raw = '[{"id":"a","detail":{"labels":["x"]}}]\n'.encode("utf-8")
    source = source_dir / "events.json"
    source.write_bytes(raw)
    config = load_config(_config({"fixture_source": "events"}))
    resolved = resolve_fixture_sources(
        config,
        source_dir,
        expected_sha256={"events": hashlib.sha256(raw).hexdigest()},
    )
    spec = resolved.routes[0].response
    assert spec is not None
    assert not spec.deferred
    assert spec.fixture_source == "events"
    assert spec.source is None
    assert spec.data == [{"id": "a", "detail": {"labels": ["x"]}}]
    assert spec.serialized_json == b'[{"id":"a","detail":{"labels":["x"]}}]'
    plain = load_config(_config({"json": []}))
    assert resolve_fixture_sources(plain, source_dir) is plain

    with pytest.raises(ConfigError, match="unavailable"):
        resolve_fixture_sources(config, source_dir / "missing")
    source.write_text('{"not":"an array"}\n', encoding="utf-8")
    with pytest.raises(ConfigError, match="JSON array"):
        resolve_fixture_sources(config, source_dir)
    source.write_bytes(raw)
    with pytest.raises(ConfigError, match="sha256 does not match"):
        resolve_fixture_sources(config, source_dir, expected_sha256={"events": "0" * 64})


def test_resolver_handles_states_and_revalidates_pagination_data(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    for name, rows in {
        "v1": [{"id": "old"}],
        "v2": [{"id": "new"}],
    }.items():
        (source_dir / f"{name}.json").write_text(json.dumps(rows), encoding="utf-8")
    config = load_config(
        {
            "routes": [
                {
                    "path": "/history",
                    "state_family": "catalog",
                    "states": {
                        "v1": {"fixture_source": "v1"},
                        "v2": {"fixture_source": "v2"},
                    },
                }
            ]
        }
    )
    resolved = resolve_fixture_sources(config, source_dir)
    assert resolved.routes[0].states["v1"].data == [{"id": "old"}]
    assert resolved.routes[0].states["v2"].data == [{"id": "new"}]

    invalid = load_config(
        {
            "routes": [
                {
                    "path": "/events",
                    "pagination": {"page_size": 2},
                    "response": {"fixture_source": "scalar"},
                }
            ]
        }
    )
    (source_dir / "scalar.json").write_text('{"id":"x"}', encoding="utf-8")
    with pytest.raises(ConfigError, match="JSON array"):
        resolve_fixture_sources(invalid, source_dir)


def test_mock_server_refuses_an_unresolved_fixture_source() -> None:
    server = MockRestServer(load_config(_config({"fixture_source": "events"})))
    with pytest.raises(ConfigError, match="unresolved fixture_source"):
        asyncio.run(server.start())


def test_load_config_base_dir_is_explicit_and_defaults_stay_compatible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cwd = tmp_path / "cwd"
    package = tmp_path / "package"
    cwd.mkdir()
    package.mkdir()
    (cwd / "rows.json").write_text('[{"id":"cwd"}]', encoding="utf-8")
    (package / "rows.json").write_text('[{"id":"package"}]', encoding="utf-8")
    mapping = _config({"file": "rows.json"})
    monkeypatch.chdir(cwd)

    cwd_config = load_config(mapping)
    package_config = load_config(mapping, base_dir=package)
    assert cwd_config.routes[0].response.data == [{"id": "cwd"}]
    assert package_config.routes[0].response.data == [{"id": "package"}]
    assert cwd_config.base_dir == cwd
    assert package_config.base_dir == package

    source_path = package / "route.yaml"
    source_path.write_text(
        "version: 1\nroutes:\n  - path: /events\n    response:\n      file: rows.json\n",
        encoding="utf-8",
    )
    assert load_config(source_path).routes[0].response.data == [{"id": "package"}]


def test_cli_requires_source_dir_for_fixture_source_routes(tmp_path: Path) -> None:
    from dp_scenarios.mockrest.cli import _run

    source_path = tmp_path / "route.yaml"
    source_path.write_text(
        "version: 1\nroutes:\n  - path: /events\n    response:\n      fixture_source: events\n",
        encoding="utf-8",
    )
    args = SimpleNamespace(
        scenario=source_path,
        data_port=None,
        control_port=None,
        control_secret=None,
        source_dir=None,
    )
    with pytest.raises(ConfigError, match="--source-dir was not provided"):
        asyncio.run(_run(args))
