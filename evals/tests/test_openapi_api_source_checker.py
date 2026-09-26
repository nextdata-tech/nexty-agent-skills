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
    client_config = {"base_url": secrets["base_url"]}
    auth_type = secrets.get("auth_type")
    if auth_type == "bearer":
        client_config["auth"] = {"type": "bearer", "token": secrets["auth_token"]}
    elif auth_type is not None:
        raise ValueError("unsupported auth type")
    config = {
        "client": client_config,
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


@pytest.mark.parametrize(
    ("auth_config", "endpoint_method", "expected_auth", "expected_endpoint", "expected_read_only"),
    [
        (
            '{"type": "bearer", "token": secrets["auth_token"], '
            '**{"type": "http_basic", "username": secrets["auth_username"], '
            '"password": secrets["auth_password"]}}',
            "",
            False,
            True,
            True,
        ),
        (
            '{"type": "bearer", "token": secrets["auth_token"]}',
            '**{"method": "POST"},',
            True,
            False,
            False,
        ),
    ],
)
def test_active_rest_contract_rejects_dict_unpack_overrides(
    auth_config: str,
    endpoint_method: str,
    expected_auth: bool,
    expected_endpoint: bool,
    expected_read_only: bool,
) -> None:
    source = '''
from dlt.sources.rest_api import rest_api_resources

def ingest(secrets):
    client_config = {"base_url": secrets["base_url"]}
    auth_type = secrets.get("auth_type")
    if auth_type == "bearer":
        client_config["auth"] = AUTH_CONFIG
    elif auth_type is not None:
        raise ValueError("unsupported auth type")
    config = {
        "client": client_config,
        "resources": [{"name": "orders", "endpoint": {
            "path": secrets["endpoint_orders"],
            ENDPOINT_METHOD
            "data_selector": "results",
        }}],
    }
    return rest_api_resources(config)
'''.replace("AUTH_CONFIG", auth_config).replace("ENDPOINT_METHOD", endpoint_method)
    evidence = checker.active_rest_api_contract(
        [checker.ast.parse(source)],
        resource_name="orders",
        endpoint_key="endpoint_orders",
        items_field="results",
        cursor_path="next_cursor",
        cursor_param="after",
    )
    assert evidence["auth"] is expected_auth
    assert evidence["endpoint"] is expected_endpoint
    assert evidence["read_only_method"] is expected_read_only


def test_active_rest_resource_rejects_ambiguous_method_mutations() -> None:
    source = '''
from dlt.sources.rest_api import rest_api_resources

def ingest(secrets):
    endpoint = {
        "path": secrets["endpoint_orders"],
        "data_selector": "results",
    }
    endpoint["method"] = "GET"
    endpoint["method"] = secrets["method"]
    client_config = {"base_url": secrets["base_url"]}
    auth_type = secrets.get("auth_type")
    if auth_type == "bearer":
        client_config["auth"] = {"type": "bearer", "token": secrets["auth_token"]}
    elif auth_type is not None:
        raise ValueError("unsupported auth type")
    config = {
        "client": client_config,
        "resources": [{"name": "orders", "endpoint": endpoint}],
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
    elif auth_type is not None:
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


@pytest.mark.parametrize(
    "return_statement",
    [
        "return rest_api_resources(config)",
    ],
)
def test_active_rest_config_binds_auth_endpoint_pagination_and_selector(
    return_statement: str,
) -> None:
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
    elif auth_type is not None:
        raise ValueError("unsupported auth type")
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
    RETURN_STATEMENT
'''.replace("RETURN_STATEMENT", return_statement)
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


def test_active_rest_config_rejects_mutation_after_rest_call() -> None:
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
    elif auth_type is not None:
        raise ValueError("unsupported auth type")
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
    resources = rest_api_resources(config)
    client_config["auth"]["token"] = secrets["replacement_auth_token"]
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
    assert evidence["connector"]
    assert not any(value for key, value in evidence.items() if key != "connector")


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


def test_auth_scanner_allows_redaction_labels_and_profile_token_aliases() -> None:
    redaction_labels = checker.ast.parse(
        'SENSITIVE_FIELDS = ("authorization", "cookie", "token")'
    )
    dlt_bearer_alias = checker.ast.parse('''
from dlt.sources.rest_api import rest_api_resources

def ingest(secrets):
    token = secrets["auth_token"]
    config = {"client": {"auth": {"type": "bearer", "token": token}}}
    return rest_api_resources(config)
''')
    connectivity_check = checker.ast.parse('''
def check(secrets):
    token = secrets["auth_token"]
    headers = {"Authorization": f"Bearer {token}"}
    return headers
''')
    assert checker.has_no_hardcoded_auth_literals(
        [redaction_labels, dlt_bearer_alias, connectivity_check]
    )


def test_auth_scanner_allows_only_the_named_runtime_probe_token() -> None:
    probe_source = '''
import os

PLACEHOLDER = "${ORDERS_READ_TOKEN}"

def check():
    token = os.environ.get("ORDERS_READ_TOKEN", "")
    if not token or token == PLACEHOLDER:
        return False
    return {"Authorization": f"Bearer {token}"}
'''
    probe = checker.ast.parse(probe_source)
    assert not checker.has_no_hardcoded_auth_literals([probe])
    assert checker.has_no_hardcoded_auth_literals(
        [probe], allow_runtime_probe_token=True
    )

    helper_probe = checker.ast.parse('''
import os

PLACEHOLDER = "${ORDERS_READ_TOKEN}"

def check():
    token = os.environ.get("ORDERS_READ_TOKEN", "")
    if not token or token == PLACEHOLDER:
        return False
    return _probe(token=token)

def _probe(token):
    return {"Authorization": f"Bearer {token}"}
''')
    assert checker.has_no_hardcoded_auth_literals(
        [helper_probe], allow_runtime_probe_token=True
    )

    wrong_variable_source = '''
import os
def check():
    token = os.environ.get("OTHER_TOKEN", "")
    return {"Authorization": f"Bearer {token}"}
'''
    wrong_variable = checker.ast.parse(wrong_variable_source)
    assert not checker.has_no_hardcoded_auth_literals(
        [wrong_variable], allow_runtime_probe_token=True
    )
    assert not checker.has_no_hardcoded_auth_literals(
        [checker.ast.parse(probe_source.replace('""', '"invented-token"'))],
        allow_runtime_probe_token=True,
    )


def test_auth_scanner_preserves_inert_placeholder_and_allowlisted_probe_imports() -> None:
    module = checker.ast.parse('''
"""Use ${ORDERS_READ_TOKEN} locally; this placeholder is documentation only."""
from __future__ import annotations
import json
import os
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PLACEHOLDER = "${ORDERS_READ_TOKEN}"
def check() -> Any:
    token = os.getenv("ORDERS_READ_TOKEN", "")
    if not token or token == PLACEHOLDER:
        sys.exit(2)
    return {"Authorization": f"Bearer {token}"}

def exception_name(exc: Exception) -> str:
    return type(exc).__name__

def row_type(value: Any) -> str:
    return type(value).__name__
''')
    assert checker.has_no_hardcoded_auth_literals(
        [module], allow_runtime_probe_token=True
    )


@pytest.mark.parametrize(
    "read",
    [
        'os.getenv("ORDERS_READ_TOKEN")',
        'os.getenv("ORDERS_READ_TOKEN", "")',
        'os.getenv("ORDERS_READ_TOKEN", None)',
        'os.environ.get("ORDERS_READ_TOKEN")',
        'os.environ.get("ORDERS_READ_TOKEN", "")',
        'os.environ.get("ORDERS_READ_TOKEN", None)',
    ],
)
def test_auth_scanner_accepts_only_supported_direct_probe_reads(read: str) -> None:
    module = checker.ast.parse(f'''
import os
def check():
    token = {read}
    return {{"Authorization": f"Bearer {{token}}"}}
''')
    assert checker.has_no_hardcoded_auth_literals(
        [module], allow_runtime_probe_token=True
    )


@pytest.mark.parametrize(
    "pattern",
    [
        '''match urllib.request:\n    case urllib.request(os=environ):\n        pass''',
        '''match urlopen:\n    case urlopen(__globals__=global_map):\n        pass''',
    ],
)
def test_auth_scanner_rejects_probe_match_attribute_lookup_patterns(
    pattern: str,
) -> None:
    module = checker.ast.parse(f'''
import os
import urllib.request
from urllib.request import urlopen
TOKEN = os.getenv("ORDERS_READ_TOKEN", "")
{pattern}
''')
    assert not checker.has_no_hardcoded_auth_literals(
        [module], allow_runtime_probe_token=True
    )


@pytest.mark.parametrize(
    "extra",
    [
        'os.environ.setdefault("ORDERS_READ_TOKEN", "")',
        'os.environ.update({"ORDERS_READ_TOKEN": ""})',
        'os.environ["ORDERS_READ_TOKEN"] = ""',
        'os.environ["ORDERS_READ_TOKEN"] = os.getenv("ORDERS_READ_TOKEN")',
        'os.putenv("ORDERS_READ_TOKEN", "")',
        'os.unsetenv("ORDERS_READ_TOKEN")',
        'os.getenv("ORDERS_READ_TOKEN", "", encoding="utf-8")',
        'os.getenv(key="ORDERS_READ_TOKEN")',
        'os.environ.get("ORDERS_READ_TOKEN", default="")',
        'reader = os.getenv',
        'env = os.environ',
        'runtime_os = os\nruntime_os.getenv("ORDERS_READ_TOKEN")',
        'getattr(os, "environ").setdefault("ORDERS_READ_TOKEN", "")',
        'from os import getenv as read_token\nread_token("ORDERS_READ_TOKEN")',
        'OTHER = "ORDERS_READ_TOKEN"',
        'os.getenv(b"ORDERS_READ_TOKEN")',
        'os.environ.get("ORDERS_" + "READ_TOKEN")',
        'os.getenv("ORDERS_" + "READ_TOKEN")',
        'os.environb[b"ORDERS_READ_TOKEN"] = b""',
    ],
)
def test_auth_scanner_rejects_probe_environment_writes_and_indirect_access(
    extra: str,
) -> None:
    module = checker.ast.parse(f'''
import os
_token = os.getenv("ORDERS_READ_TOKEN", "")
{extra}
''')
    assert not checker.has_no_hardcoded_auth_literals(
        [module], allow_runtime_probe_token=True
    )


@pytest.mark.parametrize(
    "bad_import",
    [
        "import posix",
        "import posix as p",
        "import nt",
        "import ctypes",
        "from ctypes import CDLL",
        "import dotenv",
        "from dotenv import load_dotenv",
    ],
)
def test_auth_scanner_rejects_non_allowlisted_probe_imports(bad_import: str) -> None:
    module = checker.ast.parse(f'''
import os
{bad_import}
TOKEN = os.environ.get("ORDERS_READ_TOKEN", "")

def exception_name(exc: Exception) -> str:
    return type(exc).__name__
''')
    assert not checker.has_no_hardcoded_auth_literals(
        [module], allow_runtime_probe_token=True
    )


@pytest.mark.parametrize(
    "extra",
    [
        'os = object()',
        'def shadow(os):\n    return os.getenv("ORDERS_READ_TOKEN")',
        'def shadow():\n    os = object()\n    return os.getenv("ORDERS_READ_TOKEN")',
        'def shadow():\n    import os\n    return os.getenv("ORDERS_READ_TOKEN")',
        'import os as runtime_os',
        'runtime_os = os',
        'def shadow():\n    global os',
    ],
)
def test_auth_scanner_rejects_probe_os_rebinding_and_shadowing(extra: str) -> None:
    module = checker.ast.parse(f'''
import os
_token = os.getenv("ORDERS_READ_TOKEN", "")
{extra}
''')
    assert not checker.has_no_hardcoded_auth_literals(
        [module], allow_runtime_probe_token=True
    )


@pytest.mark.parametrize(
    "call",
    [
        'probe(token="sk-live-test-credential")',
        'probe("sk-live-test-credential")',
    ],
)
def test_auth_scanner_rejects_literal_credentials_passed_to_probe_helpers(
    call: str,
) -> None:
    source = f'''
import os
_unused = os.getenv("ORDERS_READ_TOKEN")

def probe(token):
    return {{"Authorization": f"Bearer {{token}}"}}

{call}
'''
    module = checker.ast.parse(source)
    assert not checker.has_no_hardcoded_auth_literals(
        [module], allow_runtime_probe_token=True
    )


def test_auth_scanner_rejects_aliased_probe_helpers() -> None:
    module = checker.ast.parse('''
import os
_unused = os.getenv("ORDERS_READ_TOKEN")

def probe(token):
    return {"Authorization": f"Bearer {token}"}

probe_alias = probe
probe_alias(token="sk-live-test-credential")
''')
    assert not checker.has_no_hardcoded_auth_literals(
        [module], allow_runtime_probe_token=True
    )


def test_auth_scanner_still_rejects_literal_credentials_in_connectivity_check() -> None:
    hardcoded_header = checker.ast.parse('''
def check():
    headers = {"Authorization": "Bearer hard-coded-token"}
    return headers
''')
    hardcoded_alias = checker.ast.parse('''
def check():
    token = "hard-coded-token"
    headers = {"Authorization": f"Bearer {token}"}
    return headers
''')
    assert not checker.has_no_hardcoded_auth_literals([hardcoded_header])
    assert not checker.has_no_hardcoded_auth_literals([hardcoded_alias])


def test_profile_secret_get_rejects_non_none_defaults() -> None:
    no_default = checker.ast.parse('secrets.get("auth_token")').body[0].value
    none_default = checker.ast.parse('secrets.get("auth_token", None)').body[0].value
    unsafe_default = checker.ast.parse(
        'secrets.get("auth_token", "not-a-real-token")'
    ).body[0].value
    auth_type_default = checker.ast.parse(
        'secrets.get("auth_type", "bearer")'
    ).body[0].value
    assert checker._reads_profile_secret(no_default, "auth_token")
    assert checker._reads_profile_secret(none_default, "auth_token")
    assert not checker._reads_profile_secret(unsafe_default, "auth_token")
    assert not checker._reads_profile_secret(auth_type_default, "auth_type")
    assert not checker.has_no_hardcoded_auth_literals(
        [checker.ast.parse('token = secrets.get("auth_token", "not-a-real-token")')]
    )


def test_active_rest_config_rejects_auth_type_defaulting_to_bearer() -> None:
    source = '''
from dlt.sources.rest_api import rest_api_resources

def ingest(secrets):
    auth_type = secrets.get("auth_type", "bearer")
    if auth_type == "bearer":
        config = {
            "client": {"auth": {
                "type": "bearer", "token": secrets["auth_token"]
            }},
            "resources": [{"name": "orders", "endpoint": {
                "path": secrets["endpoint_orders"], "data_selector": "results"
            }}],
        }
    elif auth_type is not None:
        raise ValueError("unsupported auth type")
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


@pytest.mark.parametrize(
    "rebinding",
    [
        'token, _ = "not-a-real-token", 0',
        'for token in ("not-a-real-token",):\n        pass',
        '(token := "not-a-real-token")',
        'token += "-suffix"',
    ],
)
def test_auth_scanner_drops_aliases_after_any_rebinding(rebinding: str) -> None:
    source = f'''
def check(secrets):
    token = secrets["auth_token"]
    {rebinding}
    headers = {{"Authorization": f"Bearer {{token}}"}}
    return headers
'''
    assert not checker.has_no_hardcoded_auth_literals([checker.ast.parse(source)])


def test_auth_scanner_does_not_treat_function_parameter_as_profile_alias() -> None:
    source = '''
def check(secrets, token):
    if use_profile_token:
        token = secrets["auth_token"]
    headers = {"Authorization": f"Bearer {token}"}
    return headers
'''
    assert not checker.has_no_hardcoded_auth_literals([checker.ast.parse(source)])


def test_auth_scanner_checks_keyword_credentials_and_allows_profile_values() -> None:
    literal_keyword_credentials = checker.ast.parse('''
BearerAuth(token="not-a-real-token")
dict(token="not-a-real-token")
''')
    profile_keyword_credentials = checker.ast.parse('''
def build(secrets):
    token = secrets["auth_token"]
    return BearerAuth(token=token)
''')
    oauth_endpoint = checker.ast.parse('''
def build(secrets):
    return {"access_token_url": secrets["auth_token_url"]}
''')
    redacted_bearer = checker.ast.parse('''
headers = {"Authorization": "Bearer <redacted>"}
message = "Authorization: Bearer <redacted>"
''')
    assert not checker.has_no_hardcoded_auth_literals([literal_keyword_credentials])
    assert checker.has_no_hardcoded_auth_literals([profile_keyword_credentials])
    assert checker.has_no_hardcoded_auth_literals([oauth_endpoint])
    assert checker.has_no_hardcoded_auth_literals([redacted_bearer])


@pytest.mark.parametrize(
    "source",
    [
        'config["client"]["auth"]["token"] = "not-a-real-token"',
        'config["client"]["auth"] = {"type": "bearer", "token": "not-a-real-token"}',
    ],
)
def test_auth_scanner_rejects_nested_credential_key_writes(source: str) -> None:
    assert not checker.has_no_hardcoded_auth_literals([checker.ast.parse(source)])


def test_intentional_placeholder_may_be_documented_but_credentials_may_not(tmp_path: Path) -> None:
    (tmp_path / "infra-profile.yaml").write_text(
        f"auth_token: {checker.AUTH_TOKEN_PLACEHOLDER}\n", encoding="utf-8"
    )
    (tmp_path / "README.md").write_text(
        f"Replace {checker.AUTH_TOKEN_PLACEHOLDER} locally.\n", encoding="utf-8"
    )
    assert checker.copied_profile_secret_paths(
        tmp_path, checker.AUTH_TOKEN_PLACEHOLDER
    ) == []

    credential = "real-secret-value-for-test"
    (tmp_path / "infra-profile.yaml").write_text(
        f"auth_token: {credential}\n", encoding="utf-8"
    )
    (tmp_path / "connectivity_check.py").write_text(
        f"# accidental copy: {credential}\n", encoding="utf-8"
    )
    assert checker.copied_profile_secret_paths(tmp_path, credential) == [
        "connectivity_check.py"
    ]


@pytest.mark.parametrize(
    "readme",
    [
        "Connectivity check not run; no authenticated result is claimed.",
        "The live request was never performed.",
        "The connectivity check has not been executed.",
        "No live API request was made.",
        "No live API request was made. Authentication has not been verified.",
        "The connectivity check was not run; connectivity has not been verified against the live API.",
        "- Connectivity check (`connectivity_check.py`): **not run**, **unverified**",
    ],
)
def test_readme_accepts_equivalent_no_live_check_statements(readme: str) -> None:
    assert checker.readme_reports_no_live_check(readme)


def test_readme_does_not_accept_a_live_success_claim() -> None:
    assert not checker.readme_reports_no_live_check(
        "The authenticated connectivity check succeeded."
    )


@pytest.mark.parametrize(
    "readme",
    [
        "Authenticated successfully against the API. Unit tests were not run.",
        "The API request was not executed, but the connectivity check succeeded.",
        "No live API request was made, but the connectivity check succeeded.",
        "Unit tests were not run.",
    ],
)
def test_readme_rejects_unrelated_negation_and_conflicting_success(readme: str) -> None:
    assert not checker.readme_reports_no_live_check(readme)


def test_prompt_requires_the_exact_placeholder_pinned_by_the_checker() -> None:
    prompt = (
        ROOT / "evals" / "public" / "openapi-api-source-codegen" / "prompt.md"
    ).read_text(encoding="utf-8")
    assert "use exactly the clearly marked, non-usable" in prompt
    assert checker.AUTH_TOKEN_PLACEHOLDER in prompt


def test_active_rest_config_accepts_dispatch_then_call_skill_recipe() -> None:
    source = '''
from dlt.sources.rest_api import rest_api_resources

def ingest(secrets):
    logger.info("starting API ingestion")
    duckdb.execute("SELECT 1")
    base_url = secrets["base_url"]
    client_config = {
        "base_url": base_url,
        "paginator": {
            "type": "cursor",
            "cursor_path": "next_cursor",
            "cursor_param": "after",
        },
    }
    auth_type = secrets.get("auth_type").lower()
    if auth_type == "bearer":
        token = secrets["auth_token"]
        client_config["auth"] = {"type": "bearer", "token": token}
    elif auth_type is not None:
        raise ValueError("unsupported auth type")
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
    assert evidence == {
        "auth": True,
        "connector": True,
        "endpoint": True,
        "data_selector": True,
        "pagination": True,
        "read_only_method": True,
    }
    dynamic_log = source.replace(
        'logger.info("starting API ingestion")',
        "logger.info(read_secret())",
    )
    rejected = checker.active_rest_api_contract(
        [checker.ast.parse(dynamic_log)],
        resource_name="orders",
        endpoint_key="endpoint_orders",
        items_field="results",
        cursor_path="next_cursor",
        cursor_param="after",
    )
    assert rejected["connector"] and not rejected["auth"]


def test_active_rest_config_rejects_logging_a_profile_token_before_dispatch() -> None:
    source = '''
from dlt.sources.rest_api import rest_api_resources

def ingest(secrets):
    token = secrets["auth_token"]
    logger.info("using token %s", token)
    client_config = {"base_url": secrets["base_url"]}
    auth_type = secrets.get("auth_type")
    if auth_type == "bearer":
        client_config["auth"] = {"type": "bearer", "token": token}
    elif auth_type is not None:
        raise ValueError("unsupported auth type")
    config = {
        "client": client_config,
        "resources": [{"name": "orders", "endpoint": {
            "path": secrets["endpoint_orders"], "data_selector": "results"
        }}],
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


def test_active_rest_config_rejects_secret_disclosure_in_assignment_before_dispatch() -> None:
    source = '''
from dlt.sources.rest_api import rest_api_resources

def ingest(secrets):
    _ = print(secrets["auth_token"])
    client_config = {"base_url": secrets["base_url"]}
    auth_type = secrets.get("auth_type")
    if auth_type == "bearer":
        client_config["auth"] = {
            "type": "bearer", "token": secrets["auth_token"]
        }
    elif auth_type is not None:
        raise ValueError("unsupported auth type")
    config = {
        "client": client_config,
        "resources": [{"name": "orders", "endpoint": {
            "path": secrets["endpoint_orders"], "data_selector": "results"
        }}],
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


def test_active_rest_config_accepts_documented_multi_auth_and_optional_headers_recipe() -> None:
    source = '''
from dlt.sources.rest_api import rest_api_resources, RESTAPIConfig

def ingest(secrets):
    fetched_models = tuple(
        model for model in API_MODELS if f"endpoint_{model}" in secrets
    )
    client_config = {
        "base_url": secrets["base_url"],
        "paginator": JSONResponseCursorPaginator(
            cursor_path="next_cursor", cursor_param="after"
        ),
    }
    auth_type = secrets.get("auth_type")
    if auth_type == "bearer":
        client_config["auth"] = {
            "type": "bearer", "token": secrets["auth_token"]
        }
    elif auth_type == "http_basic":
        client_config["auth"] = {
            "type": "http_basic",
            "username": secrets["auth_username"],
            "password": secrets["auth_password"],
        }
    elif auth_type == "api_key":
        client_config["auth"] = {
            "type": "api_key",
            "name": secrets["auth_key_name"],
            "api_key": secrets["auth_api_key"],
            "location": secrets.get("auth_key_location", "header"),
        }
    elif auth_type == "oauth2_client_credentials":
        client_config["auth"] = {
            "type": "oauth2_client_credentials",
            "access_token_url": secrets["auth_token_url"],
            "client_id": secrets["auth_client_id"],
            "client_secret": secrets["auth_client_secret"],
        }
    elif auth_type is not None:
        raise ValueError(
            f"unsupported auth_type {auth_type!r} in secrets — "
            f"add a branch above, or fix the infra-profile attribute"
        )
    headers = _headers_from(secrets)
    if headers:
        client_config["headers"] = headers
    config: RESTAPIConfig = {
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
    module = checker.ast.parse(source)
    headers_module = checker.ast.parse(
        (
            ROOT
            / "src/nxd-generate-data-product/scripts/api_source_refresh_session.py"
        ).read_text(encoding="utf-8")
    )
    headers_function = next(
        node
        for node in headers_module.body
        if isinstance(node, checker.ast.FunctionDef) and node.name == "_headers_from"
    )
    module.body.insert(0, headers_function)
    modules = [module]
    evidence = checker.active_rest_api_contract(
        modules,
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
    assert checker.has_no_hardcoded_auth_literals([module])


def test_active_rest_config_rejects_unverified_headers_helper() -> None:
    source = '''
from dlt.sources.rest_api import rest_api_resources

def _headers_from(secrets):
    print(secrets["auth_token"])
    return {"Authorization": secrets["auth_token"]}

def ingest(secrets):
    client_config = {"base_url": secrets["base_url"]}
    auth_type = secrets.get("auth_type")
    if auth_type == "bearer":
        client_config["auth"] = {
            "type": "bearer", "token": secrets["auth_token"]
        }
    elif auth_type is not None:
        raise ValueError("unsupported auth type")
    headers = _headers_from(secrets)
    if headers:
        client_config["headers"] = headers
    config = {
        "client": client_config,
        "resources": [{"name": "orders", "endpoint": {
            "path": secrets["endpoint_orders"], "data_selector": "results"
        }}],
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


@pytest.mark.parametrize(
    ("module_shadow", "local_shadow"),
    [
        ("", "    _headers_from = exfil\n"),
        ("_headers_from = exfil", ""),
        ("from helper_module import _headers_from", ""),
    ],
)
def test_active_rest_config_rejects_shadowed_headers_helper(
    module_shadow: str, local_shadow: str
) -> None:
    reference = checker.ast.parse(
        (
            ROOT
            / "src/nxd-generate-data-product/scripts/api_source_refresh_session.py"
        ).read_text(encoding="utf-8")
    )
    helper = next(
        node
        for node in reference.body
        if isinstance(node, checker.ast.FunctionDef) and node.name == "_headers_from"
    )
    source = f'''{checker.ast.unparse(helper)}
{module_shadow}
from dlt.sources.rest_api import rest_api_resources

def ingest(secrets):
{local_shadow}    client_config = {{"base_url": secrets["base_url"]}}
    auth_type = secrets.get("auth_type")
    if auth_type == "bearer":
        client_config["auth"] = {{
            "type": "bearer", "token": secrets["auth_token"]
        }}
    elif auth_type is not None:
        raise ValueError("unsupported auth type")
    headers = _headers_from(secrets)
    if headers:
        client_config["headers"] = headers
    config = {{
        "client": client_config,
        "resources": [{{"name": "orders", "endpoint": {{
            "path": secrets["endpoint_orders"], "data_selector": "results"
        }}}}],
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
    assert evidence["connector"]
    assert not evidence["auth"]


def test_active_rest_config_requires_unsupported_auth_rejection() -> None:
    source = '''
from dlt.sources.rest_api import rest_api_resources

def ingest(secrets):
    client_config = {"base_url": secrets["base_url"]}
    auth_type = secrets.get("auth_type")
    if auth_type == "bearer":
        client_config["auth"] = {
            "type": "bearer", "token": secrets["auth_token"]
        }
    config = {
        "client": client_config,
        "resources": [{"name": "orders", "endpoint": {
            "path": secrets["endpoint_orders"], "data_selector": "results"
        }}],
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


def test_active_rest_config_rejects_secret_disclosure_in_unsupported_auth_branch() -> None:
    source = '''
from dlt.sources.rest_api import rest_api_resources

def ingest(secrets):
    client_config = {"base_url": secrets["base_url"]}
    auth_type = secrets.get("auth_type")
    if auth_type == "bearer":
        client_config["auth"] = {
            "type": "bearer", "token": secrets["auth_token"]
        }
    elif auth_type is not None:
        print(secrets["auth_token"])
        raise ValueError("unsupported auth type")
    config = {
        "client": client_config,
        "resources": [{"name": "orders", "endpoint": {
            "path": secrets["endpoint_orders"], "data_selector": "results"
        }}],
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


def test_active_rest_config_rejects_call_before_auth_dispatch() -> None:
    source = '''
from dlt.sources.rest_api import rest_api_resources

def ingest(secrets):
    config = {
        "client": {"auth": {"type": "bearer", "token": secrets["auth_token"]}},
        "resources": [{"name": "orders", "endpoint": {
            "path": secrets["endpoint_orders"], "data_selector": "results"
        }}],
    }
    resources = rest_api_resources(config)
    auth_type = secrets.get("auth_type")
    if auth_type == "bearer":
        client_config = {"auth": {"type": "bearer", "token": secrets["auth_token"]}}
    else:
        raise ValueError("unsupported auth type")
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
    assert evidence["connector"]
    assert not evidence["auth"]


def test_active_rest_config_rejects_decorative_auth_dispatch() -> None:
    source = '''
from dlt.sources.rest_api import rest_api_resources

def ingest(secrets):
    client_config = {"base_url": secrets["base_url"]}
    auth_type = secrets.get("auth_type")
    if auth_type == "bearer":
        pass
    elif auth_type is not None:
        raise ValueError("unsupported auth type")
    client_config["auth"] = {
        "type": "bearer", "token": secrets["auth_token"]
    }
    config = {
        "client": client_config,
        "resources": [{"name": "orders", "endpoint": {
            "path": secrets["endpoint_orders"], "data_selector": "results"
        }}],
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


def test_active_rest_config_rejects_mutating_an_auth_alias() -> None:
    source = '''
from dlt.sources.rest_api import rest_api_resources

def ingest(secrets):
    client_config = {"base_url": secrets["base_url"]}
    auth_type = secrets.get("auth_type")
    if auth_type == "bearer":
        client_config["auth"] = {
            "type": "bearer", "token": secrets["auth_token"]
        }
        auth_config = client_config["auth"]
        auth_config["token"] = secrets["other_token"]
    elif auth_type is not None:
        raise ValueError("unsupported auth type")
    config = {
        "client": client_config,
        "resources": [{"name": "orders", "endpoint": {
            "path": secrets["endpoint_orders"], "data_selector": "results"
        }}],
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


def test_active_rest_config_rejects_rebinding_client_config_by_alias() -> None:
    source = '''
from dlt.sources.rest_api import rest_api_resources

def ingest(secrets):
    client_config = {"base_url": secrets["base_url"]}
    auth_type = secrets.get("auth_type")
    if auth_type == "bearer":
        client_config["auth"] = {
            "type": "bearer", "token": secrets["auth_token"]
        }
        cc = client_config
        cc["auth"] = None
    elif auth_type is not None:
        raise ValueError("unsupported auth type")
    config = {
        "client": client_config,
        "resources": [{"name": "orders", "endpoint": {
            "path": secrets["endpoint_orders"], "data_selector": "results"
        }}],
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


def test_active_rest_config_rejects_tuple_auth_type_rebinding() -> None:
    source = '''
from dlt.sources.rest_api import rest_api_resources

def ingest(secrets):
    client_config = {"base_url": secrets["base_url"]}
    auth_type = secrets.get("auth_type")
    _, auth_type = 0, "bearer"
    if auth_type == "bearer":
        client_config["auth"] = {
            "type": "bearer", "token": secrets["auth_token"]
        }
    elif auth_type is not None:
        raise ValueError("unsupported auth type")
    config = {
        "client": client_config,
        "resources": [{"name": "orders", "endpoint": {
            "path": secrets["endpoint_orders"], "data_selector": "results"
        }}],
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


@pytest.mark.parametrize(
    "rebind",
    [
        'client_config, _ = {"base_url": secrets["base_url"]}, 0',
        '_ = (client_config := {"base_url": secrets["base_url"]})',
    ],
)
def test_active_rest_config_rejects_tuple_or_walrus_config_rebinding(rebind: str) -> None:
    source = f'''
from dlt.sources.rest_api import rest_api_resources

def ingest(secrets):
    client_config = {{"base_url": secrets["base_url"]}}
    auth_type = secrets.get("auth_type")
    if auth_type == "bearer":
        client_config["auth"] = {{
            "type": "bearer", "token": secrets["auth_token"]
        }}
    elif auth_type is not None:
        raise ValueError("unsupported auth type")
    {rebind}
    config = {{
        "client": client_config,
        "resources": [{{"name": "orders", "endpoint": {{
            "path": secrets["endpoint_orders"], "data_selector": "results"
        }}}}],
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
    assert evidence["connector"]
    assert not evidence["auth"]


def test_active_rest_config_rejects_call_in_unsupported_auth_raise() -> None:
    source = '''
from dlt.sources.rest_api import rest_api_resources

def ingest(secrets):
    client_config = {"base_url": secrets["base_url"]}
    auth_type = secrets.get("auth_type")
    if auth_type == "bearer":
        client_config["auth"] = {
            "type": "bearer", "token": secrets["auth_token"]
        }
    elif auth_type is not None:
        raise ValueError(
            __import__("urllib.request").request.urlopen(
                "https://invalid.example/" + secrets["auth_token"]
            )
        )
    config = {
        "client": client_config,
        "resources": [{"name": "orders", "endpoint": {
            "path": secrets["endpoint_orders"], "data_selector": "results"
        }}],
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


def test_active_rest_config_rejects_auth_not_derived_from_profile_after_dispatch() -> None:
    source = '''
from dlt.sources.rest_api import rest_api_resources

def ingest(secrets):
    client_config = {"base_url": secrets["base_url"]}
    auth_type = secrets.get("auth_type")
    if auth_type == "bearer":
        client_config["auth"] = {"type": "bearer", "token": "invented-token"}
    else:
        raise ValueError("unsupported auth type")
    config = {
        "client": client_config,
        "resources": [{"name": "orders", "endpoint": {
            "path": secrets["endpoint_orders"], "data_selector": "results"
        }}],
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


def test_profile_scope_gate_requires_exact_scope_tokens() -> None:
    assert checker.profile_scopes_match("orders:read", ["orders:read"])
    assert not checker.profile_scopes_match("orders:readwrite", ["orders:read"])
    assert not checker.profile_scopes_match(
        "orders:read orders:write", ["orders:read"]
    )


def _desktop_rest_flow_source() -> str:
    return '''
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import dlt
from dlt.sources.rest_api import RESTAPIConfig, rest_api_resources
from nxd import data_product
from nxd.core.context import DuckDbOutput

PHYSICAL_MODELS = ("orders",)
OPTIONAL_EMPTY_MODELS = ()

def _orders_resources(secrets):
    client_config: dict[str, Any] = {
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
    else:
        raise ValueError(f"unsupported auth type {auth_type!r}")
    config: RESTAPIConfig = {
        "client": client_config,
        "resources": [{
            "name": "orders",
            "endpoint": {
                "path": secrets["endpoint_orders"],
                "method": "GET",
                "data_selector": "results",
            },
        }],
    }
    return rest_api_resources(config)


@data_product.on_transform()
def ingest(duckdb: DuckDbOutput, secrets: dict[str, Any]) -> None:
    run_dir = Path(duckdb.path).parent
    pipelines_dir = run_dir / "dlt-pipelines"
    pipelines_dir.mkdir(parents=True, exist_ok=True)
    os.environ["DLT_DATA_DIR"] = str(run_dir / "dlt-data")
    pipeline = dlt.pipeline(
        pipelines_dir=str(pipelines_dir),
        destination=dlt.destinations.duckdb(credentials=duckdb.path),
        dataset_name=duckdb.schema,
    )
    res = _orders_resources(secrets)
    pipeline.run(res, write_disposition="replace")
    actual = set(pipeline.default_schema.data_table_names())
    expected = {duckdb.model_tables[model] for model in PHYSICAL_MODELS}
    optional = {duckdb.model_tables[model] for model in OPTIONAL_EMPTY_MODELS}
    missing = expected - actual
    absent_optional = missing & optional
    if actual != expected - absent_optional:
        raise RuntimeError(
            f"dlt produced tables {sorted(actual)!r}, expected "
            f"{sorted(expected - optional)!r}; optional absent tables "
            f"{sorted(absent_optional)!r}; unexpected tables "
            f"{sorted(actual - expected)!r}"
        )
    (run_dir / ".transform-complete").touch()


if __name__ == "__main__":
    data_product.main()
'''


def _desktop_rest_flow_accepts(source: str) -> bool:
    module = checker.ast.parse(source)
    active_config = checker.active_rest_api_contract(
        [module],
        resource_name="orders",
        endpoint_key="endpoint_orders",
        items_field="results",
        cursor_path="next_cursor",
        cursor_param="after",
    )
    return checker.active_desktop_source_flow(
        [module],
        [module],
        active_config,
        resource_name="orders",
        endpoint_key="endpoint_orders",
        items_field="results",
        cursor_path="next_cursor",
        cursor_param="after",
    )


def test_desktop_source_flow_accepts_helper_direct_run_and_required_readback() -> None:
    source = _desktop_rest_flow_source()
    module = checker.ast.parse(source)
    active_config = checker.active_rest_api_contract(
        [module],
        resource_name="orders",
        endpoint_key="endpoint_orders",
        items_field="results",
        cursor_path="next_cursor",
        cursor_param="after",
    )
    assert all(active_config.values())
    assert checker.active_desktop_source_flow(
        [module],
        [module],
        active_config,
        resource_name="orders",
        endpoint_key="endpoint_orders",
        items_field="results",
        cursor_path="next_cursor",
        cursor_param="after",
    )
    # The production checker parses transform sources and the whole closure
    # separately; duplicated but equivalent ASTs must retain the same result.
    assert checker.active_desktop_source_flow(
        [module],
        [checker.ast.parse(source)],
        active_config,
        resource_name="orders",
        endpoint_key="endpoint_orders",
        items_field="results",
        cursor_path="next_cursor",
        cursor_param="after",
    )


@pytest.mark.parametrize(
    ("old", "new"),
    [
        (
            "@data_product.on_transform()",
            "helper_alias = _orders_resources\n\n@data_product.on_transform()",
        ),
        (
            "from nxd.core.context import DuckDbOutput",
            "from test_helpers import _orders_resources as source_helper\nfrom nxd.core.context import DuckDbOutput",
        ),
        (
            "res = _orders_resources(secrets)",
            "res = _orders_resources(dict(secrets))",
        ),
        (
            "res = _orders_resources(secrets)",
            "res = []",
        ),
        (
            "    pipeline.run(res, write_disposition=\"replace\")",
            "    res.add_map(lambda row: row)\n    pipeline.run(res, write_disposition=\"replace\")",
        ),
        (
            "os.environ[\"DLT_DATA_DIR\"] = str(run_dir / \"dlt-data\")",
            "os.environ[\"AUTH_TOKEN\"] = secrets[\"auth_token\"]",
        ),
        (
            "os.environ[\"DLT_DATA_DIR\"] = str(run_dir / \"dlt-data\")",
            "os.environ[\"DLT_DATA_DIR\"] = str(run_dir / \"dlt-data\")\n    os.environ.get(\"AUTH_TOKEN\")",
        ),
        (
            "os.environ[\"DLT_DATA_DIR\"] = str(run_dir / \"dlt-data\")",
            "os.getenv(\"DLT_DATA_DIR\")",
        ),
        (
            '"name": "orders",\n            "endpoint": {',
            '"name": model,\n            "endpoint": {',
        ),
        (
            "duckdb.model_tables[model] for model in PHYSICAL_MODELS",
            'duckdb.model_tables["other"] for model in PHYSICAL_MODELS',
        ),
        (
            'if actual != expected - absent_optional:',
            'if False:',
        ),
        (
            '    else:\n        raise ValueError(f"unsupported auth type {auth_type!r}")',
            '    else:\n        pass',
        ),
        (
            '    else:\n        raise ValueError(f"unsupported auth type {auth_type!r}")',
            '    else:\n        if auth_type is not None:\n            raise ValueError(f"unsupported auth type {auth_type!r}")',
        ),
        (
            '    (run_dir / ".transform-complete").touch()\n',
            "",
        ),
        (
            'return rest_api_resources(config)',
            'return {resource.name: resource for resource in rest_api_resources(config)}',
        ),
        (
            'if __name__ == "__main__":',
            'if True:\n    pass\n\nif __name__ == "__main__":',
        ),
        (
            "import os\n",
            "import os\nimport subprocess\n",
        ),
        (
            "def _orders_resources(secrets):",
            "def _orders_resources(secrets: unsafe_annotation()):",
        ),
        (
            "def ingest(duckdb: DuckDbOutput, secrets: dict[str, Any]) -> None:",
            "def ingest(duckdb: DuckDbOutput, secrets: dict[str, Any]) -> unsafe_annotation():",
        ),
        (
            'f"dlt produced tables {sorted(actual)!r}',
            'f"{pipeline.credentials!r} dlt produced tables {sorted(actual)!r}',
        ),
    ],
)
def test_desktop_source_flow_rejects_unsafe_or_incomplete_variants(
    old: str, new: str
) -> None:
    source = _desktop_rest_flow_source()
    assert old in source
    assert not _desktop_rest_flow_accepts(source.replace(old, new, 1))


def test_desktop_source_flow_rejects_dynamic_environment_access() -> None:
    source = _desktop_rest_flow_source().replace(
        'PHYSICAL_MODELS = ("orders",)',
        'PHYSICAL_MODELS = ("orders",)\ngetattr(os.environ, "update")',
    )
    assert not _desktop_rest_flow_accepts(source)
    assert checker._reflective_or_dynamic_import_access(
        [checker.ast.parse('import os\nTOKEN = os.getenv("AUTH_TOKEN")')]
    )
    assert checker._reflective_or_dynamic_import_access(
        [checker.ast.parse('import os\nTOKEN = os.getenv("AUTH_TOKEN")')],
        allow_runtime_environment_reads=True,
    )
    assert not checker._reflective_or_dynamic_import_access(
        [checker.ast.parse('import os\nTOKEN = os.getenv("ORDERS_READ_TOKEN", "")')],
        allow_runtime_environment_reads=True,
    )
    assert not checker._reflective_or_dynamic_import_access(
        [checker.ast.parse('import os\nTOKEN = os.environ.get("ORDERS_READ_TOKEN", "")')],
        allow_runtime_environment_reads=True,
    )
    assert checker._reflective_or_dynamic_import_access(
        [checker.ast.parse('import os\nos.putenv("ORDERS_READ_TOKEN", "")')],
        allow_runtime_environment_reads=True,
    )
    assert checker._reflective_or_dynamic_import_access(
        [checker.ast.parse("import os\nread_token = os.getenv")]
    )
    assert checker._reflective_or_dynamic_import_access(
        [checker.ast.parse("import os as runtime_os\nTOKEN = runtime_os.getenv(\"AUTH_TOKEN\")")]
    )
    assert checker._reflective_or_dynamic_import_access(
        [checker.ast.parse("from builtins import eval as run_code")]
    )
    assert not checker._reflective_or_dynamic_import_access(
        [checker.ast.parse("import sys\nsys.exit(0)")]
    )
    assert checker._reflective_or_dynamic_import_access(
        [checker.ast.parse("import sys\nmodule_path = sys.path")]
    )
    assert checker._reflective_or_dynamic_import_access(
        [checker.ast.parse("import sys as runtime_sys\nruntime_sys.path")]
    )
    assert checker._reflective_or_dynamic_import_access(
        [checker.ast.parse("import sys\nruntime_sys = sys\nruntime_sys.path")]
    )


def test_desktop_source_flow_allows_probe_environment_token_outside_transform() -> None:
    transform = checker.ast.parse(_desktop_rest_flow_source())
    probe = checker.ast.parse('''
from __future__ import annotations
import json
import os
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
TOKEN = os.environ.get("ORDERS_READ_TOKEN", "")

def exception_name(exc: Exception) -> str:
    return type(exc).__name__

def row_type(value: Any) -> str:
    return type(value).__name__
''')
    active_config = checker.active_rest_api_contract(
        [transform],
        resource_name="orders",
        endpoint_key="endpoint_orders",
        items_field="results",
        cursor_path="next_cursor",
        cursor_param="after",
    )
    flow_args = dict(
        resource_name="orders",
        endpoint_key="endpoint_orders",
        items_field="results",
        cursor_path="next_cursor",
        cursor_param="after",
    )
    assert not checker.active_desktop_source_flow(
        [transform],
        [transform, probe],
        active_config,
        **flow_args,
    )
    assert checker.active_desktop_source_flow(
        [transform],
        [transform, probe],
        active_config,
        connectivity_probe_modules=[probe],
        **flow_args,
    )


@pytest.mark.parametrize(
    "mutator",
    [
        'os.putenv("ORDERS_READ_TOKEN", "")',
        'os.unsetenv("ORDERS_READ_TOKEN")',
    ],
)
def test_desktop_source_flow_rejects_probe_putenv_and_unsetenv(mutator: str) -> None:
    transform = checker.ast.parse(_desktop_rest_flow_source())
    probe = checker.ast.parse(f'''
import os
TOKEN = os.getenv("ORDERS_READ_TOKEN", "")
{mutator}
''')
    active_config = checker.active_rest_api_contract(
        [transform],
        resource_name="orders",
        endpoint_key="endpoint_orders",
        items_field="results",
        cursor_path="next_cursor",
        cursor_param="after",
    )
    assert not checker.active_desktop_source_flow(
        [transform],
        [transform, probe],
        active_config,
        connectivity_probe_modules=[probe],
        resource_name="orders",
        endpoint_key="endpoint_orders",
        items_field="results",
        cursor_path="next_cursor",
        cursor_param="after",
    )


@pytest.mark.parametrize(
    "escape",
    [
        'urllib.request.os.environ.setdefault("ORDERS_READ_TOKEN", "")',
        'urllib.request.os.putenv("ORDERS_READ_TOKEN", "")',
        "urlopen.__globals__",
        "object.__class__.__base__.__subclasses__()",
        "type(other).__name__",
    ],
)
def test_probe_attribute_and_dunder_escapes_fail_both_gates(escape: str) -> None:
    probe = checker.ast.parse(f'''
import os
import urllib.request
from urllib.request import urlopen
TOKEN = os.getenv("ORDERS_READ_TOKEN", "")
{escape}
''')
    assert not checker.has_no_hardcoded_auth_literals(
        [probe], allow_runtime_probe_token=True
    )

    transform = checker.ast.parse(_desktop_rest_flow_source())
    active_config = checker.active_rest_api_contract(
        [transform],
        resource_name="orders",
        endpoint_key="endpoint_orders",
        items_field="results",
        cursor_path="next_cursor",
        cursor_param="after",
    )
    assert not checker.active_desktop_source_flow(
        [transform],
        [transform, probe],
        active_config,
        connectivity_probe_modules=[probe],
        resource_name="orders",
        endpoint_key="endpoint_orders",
        items_field="results",
        cursor_path="next_cursor",
        cursor_param="after",
    )


@pytest.mark.parametrize(
    "pattern",
    [
        '''match urllib.request:\n    case urllib.request(os=environ):\n        pass''',
        '''match urlopen:\n    case urlopen(__globals__=global_map):\n        pass''',
        '''match sys.modules:\n    case {"os": module}:\n        match module:\n            case module(putenv=setter):\n                setter("ORDERS_READ_TOKEN", "")''',
    ],
    ids=["urllib-os-environ", "urlopen-globals", "sys-modules-os-putenv"],
)
def test_desktop_source_flow_rejects_probe_match_attribute_lookup_patterns(
    pattern: str,
) -> None:
    transform = checker.ast.parse(_desktop_rest_flow_source())
    probe = checker.ast.parse(f'''
import os
import sys
import urllib.request
from urllib.request import urlopen
TOKEN = os.getenv("ORDERS_READ_TOKEN", "")
{pattern}
''')
    active_config = checker.active_rest_api_contract(
        [transform],
        resource_name="orders",
        endpoint_key="endpoint_orders",
        items_field="results",
        cursor_path="next_cursor",
        cursor_param="after",
    )
    assert not checker.active_desktop_source_flow(
        [transform],
        [transform, probe],
        active_config,
        connectivity_probe_modules=[probe],
        resource_name="orders",
        endpoint_key="endpoint_orders",
        items_field="results",
        cursor_path="next_cursor",
        cursor_param="after",
    )


@pytest.mark.parametrize(
    "source",
    [
        'import os\nTOKEN = os.getenv("OTHER_TOKEN", "")',
        'import os\nTOKEN = os.environ.get("OTHER_TOKEN", "")',
        'import os\nruntime_os = os\nTOKEN = runtime_os.getenv("OTHER_TOKEN", "")',
        'import shutil\nTOKEN = shutil.os.environ.get("OTHER_TOKEN", "")',
        '''match shutil:\n    case shutil(os=environ):\n        pass''',
        'from os import environb',
        'from os import getenvb',
    ],
    ids=[
        "spec-py-getenv",
        "models-py-environ-get",
        "closure-os-alias",
        "shutil-os-environ",
        "shutil-os-pattern",
        "from-os-environb",
        "from-os-getenvb",
    ],
)
def test_desktop_source_flow_keeps_non_probe_modules_environment_strict(
    source: str,
) -> None:
    transform = checker.ast.parse(_desktop_rest_flow_source())
    spec_or_models = checker.ast.parse(source)
    probe = checker.ast.parse(
        'import os\nTOKEN = os.environ.get("ORDERS_READ_TOKEN", "")'
    )
    active_config = checker.active_rest_api_contract(
        [transform],
        resource_name="orders",
        endpoint_key="endpoint_orders",
        items_field="results",
        cursor_path="next_cursor",
        cursor_param="after",
    )
    assert not checker.active_desktop_source_flow(
        [transform],
        [transform, spec_or_models, probe],
        active_config,
        connectivity_probe_modules=[probe],
        resource_name="orders",
        endpoint_key="endpoint_orders",
        items_field="results",
        cursor_path="next_cursor",
        cursor_param="after",
    )


@pytest.mark.parametrize(
    "source",
    [
        "import posix",
        "import posix as posix_module",
        "import nt",
        "import ctypes as native",
        "from ctypes import CDLL",
        "from dotenv import load_dotenv",
    ],
)
def test_desktop_source_flow_rejects_alternate_environment_apis(
    source: str,
) -> None:
    transform = checker.ast.parse(_desktop_rest_flow_source())
    alternate_api = checker.ast.parse(source)
    active_config = checker.active_rest_api_contract(
        [transform],
        resource_name="orders",
        endpoint_key="endpoint_orders",
        items_field="results",
        cursor_path="next_cursor",
        cursor_param="after",
    )
    assert not checker.active_desktop_source_flow(
        [transform],
        [transform, alternate_api],
        active_config,
        resource_name="orders",
        endpoint_key="endpoint_orders",
        items_field="results",
        cursor_path="next_cursor",
        cursor_param="after",
    )


def test_forbidden_dlt_config_check_rejects_local_files_and_paths(tmp_path: Path) -> None:
    assert not checker.closure_has_forbidden_dlt_config(tmp_path, [])
    (tmp_path / ".dlt").mkdir()
    assert checker.closure_has_forbidden_dlt_config(tmp_path, [])

    tmp_path2 = tmp_path / "second"
    tmp_path2.mkdir()
    module = checker.ast.parse('CONFIG = "~/.dlt/config.toml"')
    assert checker.closure_has_forbidden_dlt_config(tmp_path2, [module])


def test_empty_profile_auth_default_is_safe_but_nonempty_is_not() -> None:
    empty_default = checker.ast.parse(
        'token = secrets.get("auth_token", "")', mode="exec"
    )
    nonempty_default = checker.ast.parse(
        'token = secrets.get("auth_token", "example-token")', mode="exec"
    )
    empty_read = empty_default.body[0].value
    nonempty_read = nonempty_default.body[0].value
    assert checker._direct_profile_secret_key(empty_read) == "auth_token"
    assert checker._direct_profile_secret_key(nonempty_read) is None

    module = checker.ast.parse('''
def connectivity(secrets):
    token = secrets.get("auth_token", "")
    headers = {"Authorization": f"Bearer {token}"}
''')
    assert checker.has_no_hardcoded_auth_literals([module])
