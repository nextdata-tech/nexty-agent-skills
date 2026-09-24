"""The OpenAPI source checker must accept both supported dlt cursor forms."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
CHECKER = (
    ROOT / "evals" / "public" / "openapi-api-source-codegen" / "fixtures"
    / "check_openapi_api_source.py"
)
spec = importlib.util.spec_from_file_location("openapi_api_source_checker", CHECKER)
checker = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = checker
assert spec.loader is not None
spec.loader.exec_module(checker)


def test_active_cursor_config_accepts_dict_and_class_forms() -> None:
    cursor_dict = {
        "type": "cursor",
        "cursor_path": "next_cursor",
        "cursor_param": "after",
    }
    cursor_class = checker.ast.parse(
        "JSONResponseCursorPaginator(cursor_path='next_cursor', cursor_param='after')"
    ).body[0].value
    assert checker._cursor_config_value_matches(cursor_dict, "next_cursor", "after")
    assert checker._cursor_config_value_matches(cursor_class, "next_cursor", "after")


def test_active_cursor_config_rejects_a_mismatched_contract() -> None:
    config = {"type": "cursor", "cursor_path": "id", "cursor_param": "after"}
    assert not checker._cursor_config_value_matches(config, "next_cursor", "after")


def test_cursor_paginator_gate_rejects_unsupported_generic_class_name() -> None:
    value = checker.ast.parse(
        "CursorPaginator(cursor_path='next_cursor', cursor_param='after')"
    ).body[0].value
    assert not checker._cursor_config_value_matches(value, "next_cursor", "after")


def test_contract_uses_bearer_auth_and_separate_authorization_extension() -> None:
    document = checker.yaml.safe_load(
        (ROOT / "evals" / "public" / "openapi-api-source-codegen" / "fixtures" / "openapi.yaml")
        .read_text(encoding="utf-8")
    )
    expected = checker.contract_expectations(document)
    assert expected["scopes"] == ["orders:read"]


def test_contract_rejects_nonempty_openapi_30_bearer_scope_list() -> None:
    document = checker.yaml.safe_load(
        (ROOT / "evals" / "public" / "openapi-api-source-codegen" / "fixtures" / "openapi.yaml")
        .read_text(encoding="utf-8")
    )
    document["paths"]["/orders"]["get"]["security"][0]["bearerAuth"] = ["orders:read"]
    with pytest.raises(ValueError, match="empty scope list"):
        checker.contract_expectations(document)


def test_read_only_gate_rejects_write_method_literals_case_insensitively() -> None:
    assert checker.read_only_operation([checker.ast.parse('method = "GET"')], "GET")
    assert not checker.read_only_operation([checker.ast.parse('method = "post"')], "GET")


def test_active_rest_resource_rejects_dynamic_method() -> None:
    source = '''
from dlt.sources.rest_api import rest_api_resources

def ingest(secrets):
    auth_type = secrets.get("auth_type")
    if auth_type == "bearer":
        config = {
            "client": {"auth": {"type": "bearer", "token": secrets["auth_token"]}},
            "resources": [{
                "name": "orders",
                "endpoint": {
                    "path": secrets["endpoint_orders"],
                    "method": secrets["method"],
                    "data_selector": "results",
                },
            }],
        }
        return rest_api_resources(config)
    raise ValueError("unsupported auth type")
'''
    evidence = checker.active_rest_api_contract(
        [checker.ast.parse(source)],
        resource_name="orders",
        endpoint_key="endpoint_orders",
        items_field="results",
        cursor_path="next_cursor",
        cursor_param="after",
    )
    assert evidence["endpoint"]
    assert not evidence["read_only_method"]


def test_active_rest_resource_rejects_ambiguous_method_mutations() -> None:
    source = '''
from dlt.sources.rest_api import rest_api_resources

def ingest(secrets):
    auth_type = secrets.get("auth_type")
    if auth_type == "bearer":
        endpoint = {
            "path": secrets["endpoint_orders"],
            "data_selector": "results",
        }
        endpoint["method"] = "GET"
        endpoint["method"] = secrets["method"]
        config = {
            "client": {"auth": {"type": "bearer", "token": secrets["auth_token"]}},
            "resources": [{"name": "orders", "endpoint": endpoint}],
        }
        return rest_api_resources(config)
    raise ValueError("unsupported auth type")
'''
    evidence = checker.active_rest_api_contract(
        [checker.ast.parse(source)],
        resource_name="orders",
        endpoint_key="endpoint_orders",
        items_field="results",
        cursor_path="next_cursor",
        cursor_param="after",
    )
    assert evidence["endpoint"]
    assert not evidence["read_only_method"]


def test_openapi_contract_rejects_rest_api_source_instead_of_resources() -> None:
    source = '''
from dlt.sources.rest_api import rest_api_source as rest_api_resources

def ingest(secrets):
    auth_type = secrets.get("auth_type")
    if auth_type == "bearer":
        config = {
            "client": {"auth": {"type": "bearer", "token": secrets["auth_token"]}},
            "resources": [{
                "name": "orders",
                "endpoint": {
                    "path": secrets["endpoint_orders"],
                    "data_selector": "results",
                },
            }],
        }
        return rest_api_resources(config)
    raise ValueError("unsupported auth type")
'''
    evidence = checker.active_rest_api_contract(
        [checker.ast.parse(source)],
        resource_name="orders",
        endpoint_key="endpoint_orders",
        items_field="results",
        cursor_path="next_cursor",
        cursor_param="after",
    )
    assert not evidence["connector"]
    assert not evidence["auth"]


def test_active_rest_config_binds_auth_endpoint_pagination_and_selector() -> None:
    source = '''
from dlt.sources.rest_api import rest_api_resources

def ingest(secrets):
    client_config = {
        "base_url": secrets["base_url"],
        "paginator": {
            "type": "cursor",
            "cursor_path": "next_cursor",
            "cursor_param": "after",
        },
    }
    auth_type = secrets.get("auth_type")
    if auth_type == "bearer":
        client_config["auth"] = {"type": "bearer", "token": secrets["auth_token"]}
        config = {
            "client": client_config,
            "resources": [{
                "name": "orders",
                "endpoint": {
                    "path": secrets["endpoint_orders"],
                    "data_selector": "results",
                },
            }],
        }
        return rest_api_resources(config)
    raise ValueError("unsupported auth type")
'''
    evidence = checker.active_rest_api_contract(
        [checker.ast.parse(source)],
        resource_name="orders",
        endpoint_key="endpoint_orders",
        items_field="results",
        cursor_path="next_cursor",
        cursor_param="after",
    )
    assert evidence == {
        "auth": True,
        "connector": True,
        "endpoint": True,
        "data_selector": True,
        "pagination": True,
        "read_only_method": True,
    }


def test_active_rest_config_rejects_unconnected_auth_and_resource_decoys() -> None:
    source = '''
from dlt.sources.rest_api import rest_api_resources

def ingest(secrets):
    auth_type = secrets.get("auth_type")
    if auth_type == "bearer":
        unused_client = {
            "auth": {"type": "bearer", "token": secrets["auth_token"]},
            "paginator": {
                "type": "cursor",
                "cursor_path": "next_cursor",
                "cursor_param": "after",
            },
        }
        unused_resource = {
            "name": "orders",
            "endpoint": {"path": secrets["endpoint_orders"], "data_selector": "results"},
        }
    active_config = {
        "client": {"base_url": secrets["base_url"]},
        "resources": [{
            "name": "orders",
            "endpoint": {"path": secrets["endpoint_orders"], "data_selector": "items"},
        }],
    }
    return rest_api_resources(active_config)
'''
    module = checker.ast.parse(source)
    evidence = checker.active_rest_api_contract(
        [module],
        resource_name="orders",
        endpoint_key="endpoint_orders",
        items_field="results",
        cursor_path="next_cursor",
        cursor_param="after",
    )
    assert evidence == {
        "auth": False,
        "connector": True,
        "endpoint": False,
        "data_selector": False,
        "pagination": False,
        "read_only_method": False,
    }


def test_active_rest_config_does_not_credit_auth_mutation_after_call() -> None:
    source = '''
from dlt.sources.rest_api import rest_api_resources

def ingest(secrets):
    client_config = {
        "base_url": secrets["base_url"],
        "paginator": {
            "type": "cursor",
            "cursor_path": "next_cursor",
            "cursor_param": "after",
        },
    }
    config = {
        "client": client_config,
        "resources": [{
            "name": "orders",
            "endpoint": {
                "path": secrets["endpoint_orders"],
                "data_selector": "results",
            },
        }],
    }
    auth_type = secrets.get("auth_type")
    if auth_type == "bearer":
        resources = rest_api_resources(config)
        client_config["auth"] = {"type": "bearer", "token": secrets["auth_token"]}
        return resources
'''
    evidence = checker.active_rest_api_contract(
        [checker.ast.parse(source)],
        resource_name="orders",
        endpoint_key="endpoint_orders",
        items_field="results",
        cursor_path="next_cursor",
        cursor_param="after",
    )
    assert not evidence["auth"]
    assert evidence["endpoint"] and evidence["data_selector"] and evidence["pagination"]


def test_active_rest_config_rejects_nested_conditional_auth_setup() -> None:
    source = '''
from dlt.sources.rest_api import rest_api_resources

def ingest(secrets):
    auth_type = secrets.get("auth_type")
    client_config = {"base_url": secrets["base_url"]}
    if auth_type == "bearer":
        if secrets.get("use_alternate_auth"):
            client_config["auth"] = {"type": "bearer", "token": secrets["auth_token"]}
        config = {
            "client": client_config,
            "resources": [{
                "name": "orders",
                "endpoint": {
                    "path": secrets["endpoint_orders"],
                    "data_selector": "results",
                },
            }],
        }
        return rest_api_resources(config)
'''
    evidence = checker.active_rest_api_contract(
        [checker.ast.parse(source)],
        resource_name="orders",
        endpoint_key="endpoint_orders",
        items_field="results",
        cursor_path="next_cursor",
        cursor_param="after",
    )
    assert evidence["connector"]
    assert not any(value for key, value in evidence.items() if key != "connector")


def test_unrelated_function_cannot_supply_active_auth_type_dispatch() -> None:
    source = '''
from dlt.sources.rest_api import rest_api_resources

def decoy(secrets):
    auth_type = secrets.get("auth_type")
    if auth_type == "bearer":
        unused_client = {"auth": {"type": "bearer", "token": secrets["auth_token"]}}

def ingest(secrets):
    client_config = {"base_url": secrets["base_url"], "auth": {
        "type": "bearer", "token": secrets["auth_token"]
    }}
    config = {
        "client": client_config,
        "resources": [{
            "name": "orders",
            "endpoint": {"path": secrets["endpoint_orders"], "data_selector": "results"},
        }],
    }
    return rest_api_resources(config)
'''
    evidence = checker.active_rest_api_contract(
        [checker.ast.parse(source)],
        resource_name="orders",
        endpoint_key="endpoint_orders",
        items_field="results",
        cursor_path="next_cursor",
        cursor_param="after",
    )
    assert evidence["connector"]
    assert not evidence["auth"]


@pytest.mark.parametrize("guard", [
    'if auth_type == "bearer" or auth_type == "none":',
    'auth_type = "bearer"\n    if auth_type == "bearer":',
])
def test_active_auth_branch_must_use_the_unmodified_profile_value(guard: str) -> None:
    source = f'''
from dlt.sources.rest_api import rest_api_resources

def ingest(secrets):
    auth_type = secrets.get("auth_type")
    {guard}
        config = {{
            "client": {{"auth": {{"type": "bearer", "token": secrets["auth_token"]}}}},
            "resources": [{{
                "name": "orders",
                "endpoint": {{"path": secrets["endpoint_orders"], "data_selector": "results"}},
            }}],
        }}
        return rest_api_resources(config)
'''
    evidence = checker.active_rest_api_contract(
        [checker.ast.parse(source)],
        resource_name="orders",
        endpoint_key="endpoint_orders",
        items_field="results",
        cursor_path="next_cursor",
        cursor_param="after",
    )
    assert not evidence["auth"]


def test_active_rest_config_rejects_literal_bearer_token() -> None:
    source = '''
from dlt.sources.rest_api import rest_api_resources

def ingest(secrets):
    auth_type = secrets.get("auth_type")
    if auth_type == "bearer":
        client_config = {"auth": {"type": "bearer", "token": "invented-token"}}
        config = {
            "client": client_config,
            "resources": [{
                "name": "orders",
                "endpoint": {
                    "path": secrets["endpoint_orders"],
                    "data_selector": "results",
                    "paginator": {"type": "cursor", "cursor_path": "next_cursor", "cursor_param": "after"},
                },
            }],
        }
        return rest_api_resources(config)
'''
    module = checker.ast.parse(source)
    evidence = checker.active_rest_api_contract(
        [module],
        resource_name="orders",
        endpoint_key="endpoint_orders",
        items_field="results",
        cursor_path="next_cursor",
        cursor_param="after",
    )
    assert not evidence["auth"]
    assert not checker.has_no_hardcoded_auth_literals([module])


def test_hardcoded_auth_scanner_rejects_token_alias_and_bearer_header() -> None:
    alias = checker.ast.parse('ORDERS_ACCESS_TOKEN = "invented-token"')
    header = checker.ast.parse(
        'headers = {"Authorization": "Bearer " + "invented-token"}'
    )
    assigned_header = checker.ast.parse(
        'headers["Authorization"] = "Bearer " + "invented-token"'
    )
    tuple_header = checker.ast.parse(
        'headers = [("Proxy-Authorization", "Bearer " + "invented-token")]'
    )
    token_parts = checker.ast.parse('auth = {"token": "invented-" + "token"}')
    assert not checker.has_no_hardcoded_auth_literals([alias])
    assert not checker.has_no_hardcoded_auth_literals([header])
    assert not checker.has_no_hardcoded_auth_literals([assigned_header])
    assert not checker.has_no_hardcoded_auth_literals([tuple_header])
    assert not checker.has_no_hardcoded_auth_literals([token_parts])


def test_profile_scope_gate_requires_exact_scope_tokens() -> None:
    assert checker.profile_scopes_match("orders:read", ["orders:read"])
    assert not checker.profile_scopes_match("orders:readwrite", ["orders:read"])
    assert not checker.profile_scopes_match(
        "orders:read orders:write", ["orders:read"]
    )
