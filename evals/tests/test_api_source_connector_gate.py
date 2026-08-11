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
