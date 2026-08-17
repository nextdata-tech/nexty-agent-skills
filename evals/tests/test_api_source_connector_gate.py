"""`ingestion:rest-api-resources-used` must reject a HYBRID closure.

The measured NEX-873 benchmark
(`evals/benchmarks/entries/2026-08-11-api-source-custom-client-headers.md`)
found both arms hand-rolling `requests` while the check that exists to require
dlt's REST connector passed or failed on nothing but the presence of an import.
A closure could import `rest_api_resources`, never send a request through it,
and fetch every row with `requests.get` beside it.

These tests pin the tightened gate: the connector must be used AND nothing may
fetch HTTP next to it. They are the CI-side complement to the scenario run,
which needs a live agent and cannot gate a PR.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

CHECKER = (Path(__file__).parents[1] / "public" / "authenticated-api-source-build" /
           "fixtures" / "check_authenticated_api_source.py")
spec = importlib.util.spec_from_file_location("api_source_checker_gate", CHECKER)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


CLEAN = '''
from dlt.sources.rest_api import RESTAPIConfig, rest_api_resources

def ingest(duckdb, secrets):
    config = {"client": {"base_url": secrets["base_url"]}, "resources": []}
    resources = {r.name: r for r in rest_api_resources(config)}
    return resources
'''

HYBRID = '''
import requests
from dlt.sources.rest_api import RESTAPIConfig, rest_api_resources

def ingest(duckdb, secrets):
    config = {"client": {"base_url": secrets["base_url"]}, "resources": []}
    _ = rest_api_resources(config)          # imported, configured, never used
    rows = []
    page = 1
    while True:
        r = requests.get(f"{secrets['base_url']}/v1/checks", params={"page": page})
        rows += r.json()["data"]
        if page >= r.json()["pages"]:
            break
        page += 1
    return rows
'''

PURE_HAND_ROLL = '''
import urllib.request

def ingest(duckdb, secrets):
    with urllib.request.urlopen(secrets["base_url"] + "/v1/checks") as fh:
        return fh.read()
'''

# The guidance in api-source.md names `requests` and `urllib` in prose. A
# closure that QUOTES that guidance while correctly avoiding both must pass.
MENTIONS_IN_PROSE = '''
from dlt.sources.rest_api import RESTAPIConfig, rest_api_resources

def ingest(duckdb, secrets):
    """Ingest via dlt's REST connector.

    Deliberately NOT a hand-rolled requests/urllib loop -- see api-source.md.
    """
    # Do not use requests.get here; the connector owns the transport.
    config = {"client": {"base_url": secrets["base_url"]}, "resources": []}
    return {r.name: r for r in rest_api_resources(config)}
'''


def _closure(tmp_path: Path, **modules: str) -> Path:
    (tmp_path / "transform").mkdir(parents=True, exist_ok=True)
    for name, src in modules.items():
        (tmp_path / "transform" / f"{name}.py").write_text(src, encoding="utf-8")
    return tmp_path


def test_clean_connector_closure_passes(tmp_path: Path):
    ok, detail = checker.uses_rest_api_resources(_closure(tmp_path, main=CLEAN))
    assert ok, detail


def test_hybrid_is_rejected(tmp_path: Path):
    ok, detail = checker.uses_rest_api_resources(_closure(tmp_path, main=HYBRID))
    assert not ok, "a closure that imports the connector AND hand-rolls must fail"
    assert "HYBRID" in detail
    assert "requests.get" in detail, f"the offending call should be named: {detail}"


def test_pure_hand_roll_is_rejected_with_its_own_message(tmp_path: Path):
    # Distinct from the hybrid message: the fix differs (adopt the connector vs
    # remove the loop beside it), so the two must not collapse into one string.
    ok, detail = checker.uses_rest_api_resources(_closure(tmp_path, main=PURE_HAND_ROLL))
    assert not ok
    assert "HYBRID" not in detail
    assert "urllib.request.urlopen" in detail


DOTTED_IMPORT = '''
import dlt.sources.rest_api as rest

def ingest(duckdb, secrets):
    config = {"client": {"base_url": secrets["base_url"]}, "resources": []}
    return {r.name: r for r in rest.rest_api_resources(config)}
'''


def test_the_dotted_import_form_is_the_same_architecture(tmp_path: Path):
    """`import dlt.sources.rest_api as rest` is the connector, spelled sideways.

    Recognizing only the `from`-form failed a correct closure with "no
    dlt.sources.rest_api import found" — a false accusation, and one the gate
    can least afford now that three scenarios share it.
    """
    ok, detail = checker.uses_rest_api_resources(_closure(tmp_path, main=DOTTED_IMPORT))
    assert ok, detail


def test_prose_mentioning_requests_still_passes(tmp_path: Path):
    # Substring scanning would fail this closure for describing what it avoided.
    ok, detail = checker.uses_rest_api_resources(_closure(tmp_path, main=MENTIONS_IN_PROSE))
    assert ok, detail


def test_hand_roll_in_a_sibling_module_is_caught(tmp_path: Path):
    # Checking only main.py lets the loop move one file over, unchanged.
    ok, detail = checker.uses_rest_api_resources(
        _closure(tmp_path, main=CLEAN, fetch=PURE_HAND_ROLL)
    )
    assert not ok, "a fetch loop in transform/fetch.py must not escape the gate"
    assert "fetch.py" in detail


def test_dlt_own_requests_wrapper_is_still_hand_rolled(tmp_path: Path):
    # dlt-flavored, but a hand-written loop feeding a plain generator all the
    # same -- it is not the REST connector.
    src = '''
from dlt.sources.helpers import requests
from dlt.sources.rest_api import rest_api_resources

def ingest(duckdb, secrets):
    _ = rest_api_resources({"client": {}, "resources": []})
    return requests.get(secrets["base_url"]).json()
'''
    ok, detail = checker.uses_rest_api_resources(_closure(tmp_path, main=src))
    assert not ok
    assert "HYBRID" in detail


@pytest.mark.parametrize("alias_src,expected", [
    ("import requests as rq\ndef f(s):\n    return rq.get(s)\n", "rq.get"),
    ("from urllib.request import urlopen\ndef f(s):\n    return urlopen(s)\n", "urlopen"),
    ("import httpx\ndef f(s):\n    return httpx.Client().get(s)\n", "httpx.Client"),
])
def test_aliased_and_bare_imports_resolve(tmp_path: Path, alias_src: str, expected: str):
    ok, detail = checker.uses_rest_api_resources(_closure(tmp_path, main=alias_src))
    assert not ok
    assert expected in detail


def test_urllib_parse_is_not_a_network_call(tmp_path: Path):
    """`import urllib` + `urllib.parse.quote` must PASS.

    Keying on the bound root name flags this, because `import urllib` binds
    `urllib` and `urllib.request` lives under it. `reference/self-check.md`
    documents the same trap and refuses to make it: `urllib.parse` "is pure
    string manipulation with no network and is used by shipped example
    transforms". Resolution has to be on the full dotted path.
    """
    src = '''
import urllib
from dlt.sources.rest_api import rest_api_resources

def ingest(duckdb, secrets):
    path = urllib.parse.quote(secrets["endpoint_checks"])
    return {r.name: r for r in rest_api_resources({"client": {}, "resources": []})}
'''
    ok, detail = checker.uses_rest_api_resources(_closure(tmp_path, main=src))
    assert ok, f"urllib.parse is string manipulation, not a network call: {detail}"


def test_urllib_request_under_a_bare_root_import_is_still_caught(tmp_path: Path):
    # The other side of the same fix: full-path resolution must not let the
    # network submodule escape just because the root was imported bare.
    src = '''
import urllib
def ingest(duckdb, secrets):
    return urllib.request.urlopen(secrets["base_url"]).read()
'''
    ok, detail = checker.uses_rest_api_resources(_closure(tmp_path, main=src))
    assert not ok
    assert "urllib.request.urlopen" in detail


def test_missing_transform_dir_reports_clearly(tmp_path: Path):
    ok, detail = checker.uses_rest_api_resources(tmp_path)
    assert not ok
    assert "transform" in detail


def test_unparseable_transform_is_not_a_silent_pass(tmp_path: Path):
    ok, detail = checker.uses_rest_api_resources(
        _closure(tmp_path, main="def ingest(:\n")
    )
    assert not ok
    assert "does not parse" in detail


# ---------------------------------------------------------------------------
# header:built-from-secrets — same two properties, same reasoning
# ---------------------------------------------------------------------------

_GOOD_HEADERS = '''
from dlt.sources.rest_api import rest_api_resources

def _headers_from(secrets):
    out = {}
    for key, value in secrets.items():
        if key.startswith("header_"):
            out["-".join(p.title() for p in key[7:].split("_"))] = str(value)
    return out

def ingest(duckdb, secrets):
    client = {"base_url": secrets["base_url"], "headers": _headers_from(secrets)}
    return rest_api_resources({"client": client, "resources": []})
'''


def test_documenting_the_required_header_is_not_hardcoding_it(tmp_path: Path):
    """A comment naming the required User-Agent must not read as a hardcode.

    The substring form of this check failed a fully correct closure for
    explaining, in a comment, the requirement it correctly satisfied.
    """
    src = _GOOD_HEADERS.replace(
        "def ingest(duckdb, secrets):",
        "# Beacon rejects any client not sending User-Agent: nexty-test-client/1.0;\n"
        "# supplied via the header_user_agent profile attribute.\n"
        "def ingest(duckdb, secrets):",
    )
    ok, detail = checker.headers_built_from_secrets(_closure(tmp_path, main=src))
    assert ok, f"a comment explaining the requirement is not a hardcode: {detail}"


def test_docstring_naming_the_header_is_not_hardcoding_it(tmp_path: Path):
    src = _GOOD_HEADERS.replace(
        'def ingest(duckdb, secrets):\n    client',
        'def ingest(duckdb, secrets):\n'
        '    """Ingest. Beacon requires User-Agent: nexty-test-client/1.0."""\n'
        '    client',
    )
    ok, detail = checker.headers_built_from_secrets(_closure(tmp_path, main=src))
    assert ok, f"a docstring is documentation, not configuration: {detail}"


def test_a_real_hardcode_is_still_caught(tmp_path: Path):
    src = '''
from dlt.sources.rest_api import rest_api_resources

def ingest(duckdb, secrets):
    client = {"headers": {"User-Agent": "nexty-test-client/1.0"}}
    return rest_api_resources({"client": client, "resources": []})
'''
    ok, detail = checker.headers_built_from_secrets(_closure(tmp_path, main=src))
    assert not ok
    assert "hardcodes" in detail


def test_headers_helper_in_a_sibling_module_passes(tmp_path: Path):
    """Factoring _headers_from into transform/http.py is correct, not a defect."""
    main = '''
from dlt.sources.rest_api import rest_api_resources
from .http import build_headers

def ingest(duckdb, secrets):
    client = {"base_url": secrets["base_url"], "headers": build_headers(secrets)}
    return rest_api_resources({"client": client, "resources": []})
'''
    http = '''
def build_headers(secrets):
    out = {}
    for key, value in secrets.items():
        if key.startswith("header_"):
            out["-".join(p.title() for p in key[7:].split("_"))] = str(value)
    return out
'''
    ok, detail = checker.headers_built_from_secrets(_closure(tmp_path, main=main, http=http))
    assert ok, f"a header helper in a sibling module still reaches the wire: {detail}"


def test_no_headers_at_all_is_still_caught(tmp_path: Path):
    src = '''
from dlt.sources.rest_api import rest_api_resources

def ingest(duckdb, secrets):
    return rest_api_resources({"client": {"base_url": secrets["base_url"]}, "resources": []})
'''
    ok, detail = checker.headers_built_from_secrets(_closure(tmp_path, main=src))
    assert not ok
    assert "never reads a header_*" in detail


# ---------------------------------------------------------------------------
# ingestion:no-hardcoded-url-or-path — the same two properties again
# ---------------------------------------------------------------------------


def test_documenting_the_endpoints_is_not_hardcoding_them(tmp_path: Path):
    """This check reads AST literals now, not the raw file text.

    A closure that names /v1/monitors in a docstring while reading the path
    from `secrets["endpoint_monitors"]` is describing its topology, and the
    text form reported that description as the defect it describes avoiding —
    the same false accusation `headers_built_from_secrets` was fixed for.
    """
    src = '''
from dlt.sources.rest_api import rest_api_resources

def ingest(duckdb, secrets):
    """Ingest /v1/monitors and /v1/checks from the Beacon API at 127.0.0.1.

    Both paths come from secrets; neither is written here.
    """
    # secrets["endpoint_monitors"] is /v1/monitors on localhost in the fixture.
    resources = [{"name": "monitors",
                  "endpoint": {"path": secrets["endpoint_monitors"]}}]
    return rest_api_resources(
        {"client": {"base_url": secrets["base_url"]}, "resources": resources})
'''
    ok, detail = checker.no_hardcoded_url_or_path(
        _closure(tmp_path, main=src), checker.STUB_HOSTS, checker.STUB_PATHS)
    assert ok, f"a docstring is documentation, not configuration: {detail}"


def test_a_frozen_endpoint_in_a_sibling_module_is_caught(tmp_path: Path):
    """main.py-only scanning is defeated by moving the literal one file over."""
    main = '''
from dlt.sources.rest_api import rest_api_resources
from .endpoints import RESOURCES

def ingest(duckdb, secrets):
    return rest_api_resources(
        {"client": {"base_url": secrets["base_url"]}, "resources": RESOURCES})
'''
    endpoints = '''
RESOURCES = [{"name": "monitors", "endpoint": {"path": "/v1/monitors"}}]
'''
    ok, detail = checker.no_hardcoded_url_or_path(
        _closure(tmp_path, main=main, endpoints=endpoints),
        checker.STUB_HOSTS, checker.STUB_PATHS)
    assert not ok
    assert "/v1/monitors" in detail
