"""Keep the live drift-canary closure aligned with connector contracts."""

from __future__ import annotations

import ast
from pathlib import Path

import yaml


CANARY = Path(__file__).parents[1] / "scenarios" / "drift-canary"


def _literal_secret_keys() -> set[str]:
    tree = ast.parse(
        (CANARY / "transform" / "main.py").read_text(encoding="utf-8"),
        filename="transform/main.py",
    )
    keys: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Subscript) or not isinstance(node.value, ast.Name):
            continue
        if node.value.id != "secrets" or not isinstance(node.slice, ast.Constant):
            continue
        if isinstance(node.slice.value, str):
            keys.add(node.slice.value)
    return keys


def test_drift_canary_uses_flat_connector_secrets_and_no_api_sidecar() -> None:
    """The positive build must reach the data assertions, not fail on shape drift."""

    profile = yaml.safe_load((CANARY / "infra-profile.yaml").read_text(encoding="utf-8"))
    services = {service["name"]: service for service in profile["spec"]["services"]}
    attributes = {
        attribute["key"]
        for service_name in ("db-source", "api-source")
        for attribute in services[service_name]["attributes"]
    }
    assert attributes == {"host", "database", "base_url", "endpoint_api_events"}

    secret_keys = _literal_secret_keys()
    assert {"base_url", "endpoint_api_events", "host", "database", "file_source", "csv_source"} <= secret_keys
    assert {"api_source", "db_source"}.isdisjoint(secret_keys)

    spec = (CANARY / "spec.py").read_text(encoding="utf-8")
    assert ".model(optional_zero)" in spec
    assert ".promise(optional_zero)" not in spec

    assert not (CANARY / "api-source-endpoints").exists()
    assert (CANARY / "companion-files").read_text(encoding="utf-8").splitlines()[-1] == "db-source-tables"
