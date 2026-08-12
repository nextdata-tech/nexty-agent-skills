"""worldbank-live grades its ingestion architecture, not just its prose (NEX-873).

The scenario carried a `rest-connector-not-hand-rolled` check that only a judge
ever read. `authenticated-api-source-build` carried the same requirement and
learned, from the measured benchmark
(`evals/benchmarks/entries/2026-08-11-api-source-custom-client-headers.md`),
that agents will import `rest_api_resources` and then fetch every row with
`requests` beside it — a shape a transcript-reading judge routinely passes.
NEX-873 tightened that scenario's deterministic gate; worldbank-live had no
deterministic gate at all.

These tests are the CI-side proof, and on this scenario they are the ONLY
proof: worldbank-live is `ci_skip`'d (live supervisor + outbound network), so
its checker never runs in CI. What CI can do is prove the checker decides
correctly, which is what happens here — the same synthetic closures the
authenticated-api-source-build gate is pinned against, plus the two defects
specific to this scenario's shape (a frozen api.worldbank.org URL and a nested
`secrets["api_source"]` read).

The identity assertion at the bottom is the point of the shared module: one
gate, two scenarios, no second copy to forget to tighten.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

EVALS = Path(__file__).resolve().parents[1]
PUBLIC = EVALS / "public"
WORLDBANK = PUBLIC / "worldbank-live"


def _load(path: Path, name: str):
    # The checkers insert evals/tools on sys.path themselves; loading them here
    # exercises that path resolution too, which is the thing that breaks if the
    # scenario tree is ever restructured.
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


checker = _load(WORLDBANK / "fixtures" / "check_worldbank_connector.py",
                "worldbank_connector_checker")
auth_checker = _load(
    PUBLIC / "authenticated-api-source-build" / "fixtures" /
    "check_authenticated_api_source.py", "authenticated_api_source_checker")


CLEAN = '''
from dlt.sources.rest_api import RESTAPIConfig, rest_api_resources

def ingest(duckdb, secrets):
    config = {
        "client": {"base_url": secrets["base_url"]},
        "resources": [
            {"name": "observations",
             "endpoint": {"path": secrets["endpoint_observations"]}},
            {"name": "economies",
             "endpoint": {"path": secrets["endpoint_economies"]}},
        ],
    }
    return {r.name: r for r in rest_api_resources(config)}
'''

HYBRID = '''
import requests
from dlt.sources.rest_api import RESTAPIConfig, rest_api_resources

def ingest(duckdb, secrets):
    _ = rest_api_resources({"client": {"base_url": secrets["base_url"]}, "resources": []})
    rows = []
    page = 1
    while True:
        r = requests.get(secrets["base_url"] + secrets["endpoint_observations"],
                         params={"page": page, "format": "json"})
        meta, data = r.json()
        rows += data
        if page >= meta["pages"]:
            break
        page += 1
    return rows
'''

HAND_ROLLED = '''
import urllib.request, json

def ingest(duckdb, secrets):
    with urllib.request.urlopen(secrets["base_url"] + secrets["endpoint_economies"]) as fh:
        return json.load(fh)[1]
'''

FROZEN_URL = '''
from dlt.sources.rest_api import RESTAPIConfig, rest_api_resources

def ingest(duckdb, secrets):
    config = {
        "client": {"base_url": "https://api.worldbank.org"},
        "resources": [{"name": "economies", "endpoint": {"path": "/v2/country"}}],
    }
    return {r.name: r for r in rest_api_resources(config)}
'''

NESTED_SECRETS = '''
from dlt.sources.rest_api import RESTAPIConfig, rest_api_resources

def ingest(duckdb, secrets):
    api = secrets["api_source"]
    config = {
        "client": {"base_url": api["base_url"]},
        "resources": [{"name": "economies",
                       "endpoint": {"path": api["endpoint_economies"]}}],
    }
    return {r.name: r for r in rest_api_resources(config)}
'''

# A closure that names the endpoints in prose while reading them from secrets is
# documenting its topology, not freezing it. The literal scan is AST-based for
# exactly this case.
DOCUMENTED_ENDPOINTS = '''
from dlt.sources.rest_api import RESTAPIConfig, rest_api_resources

def ingest(duckdb, secrets):
    """Ingest the two World Bank endpoints.

    secrets["endpoint_economies"] is /v2/country and
    secrets["endpoint_observations"] is /v2/country/all/indicator/NY.GDP.MKTP.CD,
    both served from https://api.worldbank.org. Neither is written here.
    """
    # The /v2/country payload is a two-element envelope; data_selector reaches [1].
    config = {
        "client": {"base_url": secrets["base_url"]},
        "resources": [{"name": "economies",
                       "endpoint": {"path": secrets["endpoint_economies"],
                                    "data_selector": "[1]"}}],
    }
    return {r.name: r for r in rest_api_resources(config)}
'''

PROFILE = """
services:
  - name: api-source
    driver: nxd:generic-secrets:1.0.0
    attributes:
      - key: base_url
        value: https://api.worldbank.org
        public: true
      - key: endpoint_economies
        value: /v2/country
        public: true
      - key: endpoint_observations
        value: /v2/country/all/indicator/NY.GDP.MKTP.CD
        public: true
"""


def _closure(tmp_path: Path, main: str = CLEAN, profile: str = PROFILE,
             **extra: str) -> Path:
    (tmp_path / "transform").mkdir(parents=True, exist_ok=True)
    (tmp_path / "transform" / "main.py").write_text(main, encoding="utf-8")
    for name, src in extra.items():
        (tmp_path / "transform" / f"{name}.py").write_text(src, encoding="utf-8")
    (tmp_path / "infra-profile.yaml").write_text(profile, encoding="utf-8")
    return tmp_path


def _run(root: Path) -> tuple[int, list[str]]:
    """Run the checker's main() over a closure, returning (exit code, FAIL ids)."""
    checker.FAILURES.clear()
    checker.PASSES.clear()
    argv = sys.argv
    sys.argv = ["check_worldbank_connector.py", "--fixtures",
                str(WORLDBANK / "fixtures"), "--root", str(root)]
    try:
        code = checker.main()
    finally:
        sys.argv = argv
    return code, [f.split(":", 2)[0] + ":" + f.split(":", 2)[1]
                  for f in checker.FAILURES]


def test_clean_connector_closure_passes(tmp_path: Path):
    code, failures = _run(_closure(tmp_path))
    assert code == 0, failures


def test_hybrid_is_rejected(tmp_path: Path):
    code, failures = _run(_closure(tmp_path, main=HYBRID))
    assert code == 1
    assert "ingestion:rest-api-resources-used" in failures
    assert any("HYBRID" in f for f in checker.FAILURES)


def test_pure_hand_roll_is_rejected(tmp_path: Path):
    code, failures = _run(_closure(tmp_path, main=HAND_ROLLED))
    assert code == 1
    assert "ingestion:rest-api-resources-used" in failures


def test_hand_roll_in_a_sibling_module_is_caught(tmp_path: Path):
    """`main.py`-only scanning is defeated by moving the loop one file over."""
    code, failures = _run(_closure(tmp_path, main=CLEAN, fetch=HAND_ROLLED))
    assert code == 1
    assert "ingestion:rest-api-resources-used" in failures


def test_frozen_host_and_path_are_rejected(tmp_path: Path):
    code, failures = _run(_closure(tmp_path, main=FROZEN_URL))
    assert code == 1
    assert "ingestion:no-hardcoded-url-or-path" in failures
    assert "ingestion:flat-secrets-read" not in failures, (
        "one defect, one fact — a frozen host is not also a nested-secrets read, "
        "and reporting it twice reads as two problems to fix"
    )


def test_documenting_the_endpoints_is_not_freezing_them(tmp_path: Path):
    """The AST scan must not accuse a closure of the defect it documents avoiding."""
    code, failures = _run(_closure(tmp_path, main=DOCUMENTED_ENDPOINTS))
    assert code == 0, failures


def test_nested_service_secrets_are_rejected(tmp_path: Path):
    """`secrets["api_source"]["base_url"]` raises KeyError at transform time."""
    code, failures = _run(_closure(tmp_path, main=NESTED_SECRETS))
    assert code == 1
    assert "ingestion:flat-secrets-read" in failures
    assert any("api_source" in f for f in checker.FAILURES)


def test_a_copied_secrets_map_is_not_a_nested_read(tmp_path: Path):
    """`cfg = dict(secrets)` then `cfg["base_url"]` is flat, just indirect."""
    main = '''
from dlt.sources.rest_api import rest_api_resources

def ingest(duckdb, secrets):
    cfg = dict(secrets)
    return rest_api_resources({
        "client": {"base_url": cfg["base_url"]},
        "resources": [{"name": "economies",
                       "endpoint": {"path": cfg["endpoint_economies"]}}],
    })
'''
    code, failures = _run(_closure(tmp_path, main=main))
    assert code == 0, failures


def test_indicator_code_in_an_assert_is_not_a_frozen_endpoint(tmp_path: Path):
    """The indicator id arrives in the payload; asserting on it is correct code."""
    main = CLEAN + '''
def verify(rows):
    assert {r["indicator_id"] for r in rows} == {"NY.GDP.MKTP.CD"}
'''
    code, failures = _run(_closure(tmp_path, main=main))
    assert code == 0, failures


def test_missing_endpoint_attributes_are_rejected(tmp_path: Path):
    profile = PROFILE.replace("      - key: endpoint_observations\n", "      - key: unused\n")
    code, failures = _run(_closure(tmp_path, profile=profile))
    assert code == 1
    assert "closure:endpoints-in-profile" in failures


def test_endpoint_without_a_public_flag_is_rejected(tmp_path: Path):
    """Export redaction is fail-closed: an omitted flag strips the path."""
    profile = PROFILE.replace(
        "        value: /v2/country\n        public: true\n",
        "        value: /v2/country\n")
    code, failures = _run(_closure(tmp_path, profile=profile))
    assert code == 1
    assert "closure:endpoints-public" in failures


def test_retired_companion_file_is_rejected(tmp_path: Path):
    root = _closure(tmp_path)
    (root / "api-source-endpoints").write_text("economies=/v2/country\n", encoding="utf-8")
    code, failures = _run(root)
    assert code == 1
    assert "closure:no-endpoints-companion" in failures


def test_closure_is_found_below_the_workspace_root(tmp_path: Path):
    """nxd-run-job-loop writes the closure to nxd-jobs/<workflow>/closure/."""
    nested = tmp_path / "nxd-jobs" / "gdp-by-region" / "closure"
    nested.mkdir(parents=True)
    _closure(nested)
    code, failures = _run(tmp_path)
    assert code == 0, failures


# ---------------------------------------------------------------------------
# One gate, two scenarios
# ---------------------------------------------------------------------------


def test_both_scenarios_share_one_gate_implementation():
    """A second copy is a second thing to tighten — and one always gets missed.

    Identity, not equivalence: two functions with the same behavior today
    satisfy any behavioral assertion and still drift on the next fix.
    """
    assert (checker.uses_rest_api_resources is
            auth_checker.uses_rest_api_resources), (
        "worldbank-live and authenticated-api-source-build must import the same "
        "connector gate from evals/tools/api_connector_gate.py"
    )
    assert checker.uses_rest_api_resources.__module__ == "api_connector_gate"


def test_checker_is_withheld_from_the_agent_workspace():
    """It names the banned literals and the required architecture verbatim."""
    sys.path.insert(0, str(EVALS))
    run = _load(EVALS / "run.py", "_eval_run_for_worldbank_gate")
    excluded = run.SCENARIO_WORKSPACE_FIXTURE_EXCLUSIONS.get("worldbank-live", frozenset())
    assert "check_worldbank_connector.py" in excluded, (
        "the checker would be copied into the agent's workspace, turning "
        "'build this the documented way' into 'satisfy this file'"
    )


def test_an_empty_deps_list_installs_nothing(tmp_path: Path, monkeypatch):
    """`"deps": []` must mean none, not "fall through to the duckdb default".

    This checker opens no database. Falling back on an empty list would install
    duckdb anyway and leave checks.json describing a run that isn't happening —
    the kind of drift that is only ever noticed when someone trusts the file.
    """
    sys.path.insert(0, str(EVALS))
    run = _load(EVALS / "run.py", "_eval_run_for_deps")
    captured: dict = {}

    class _Proc:
        returncode, stdout, stderr = 0, "ALL CHECKS PASSED\n", ""

    def _fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _Proc()

    monkeypatch.setattr(run.subprocess, "run", _fake_run)
    run.deterministic_check_fact(
        WORLDBANK, tmp_path, {"script": "check_worldbank_connector.py", "deps": []})
    assert "duckdb" not in captured["cmd"], captured["cmd"]
    assert "--with" not in captured["cmd"], captured["cmd"]

    run.deterministic_check_fact(
        WORLDBANK, tmp_path, {"script": "check_worldbank_connector.py"})
    assert "duckdb" in captured["cmd"], (
        "an OMITTED deps must still take the duckdb default — every other "
        "checker relies on it")


def test_touching_the_shared_gate_selects_both_scenarios():
    """A shared checker outside any scenario dir maps to nothing by default.

    The selection rules are "a skill changed" and "a scenario directory
    changed"; `evals/tools/` is neither, so tightening the gate would select
    zero scenarios and read as "no eval was affected" — the same quiet
    direction as a judge deferring to a fact nobody emits.
    """
    sys.path.insert(0, str(EVALS))
    affected = _load(EVALS / "affected_scenarios.py", "_affected_scenarios")
    scenarios, skipped = affected.load_scenarios("public")
    result = affected.select(["evals/tools/api_connector_gate.py"], scenarios, skipped)

    assert "authenticated-api-source-build" in result["scenarios"]
    # worldbank-live is ci_skip'd, so it is reported as skipped rather than
    # selected — but it must be RECOGNIZED as affected, not silently absent.
    assert "worldbank-live" in result["skipped"]


def test_scenario_declares_the_checker_and_the_judge_defers_to_it():
    checks = json.loads((WORLDBANK / "checks.json").read_text(encoding="utf-8"))
    cfg = checks.get("deterministic_check")
    assert cfg and cfg["script"] == "check_worldbank_connector.py"
    assert (WORLDBANK / "fixtures" / cfg["script"]).is_file()

    connector = next(c for c in checks["checks"]
                     if c["id"] == "rest-connector-not-hand-rolled")
    assert "HYBRID" in connector["check"], (
        "the judge check must state the hybrid failure mode the gate enforces"
    )
    for fact in ("ingestion:rest-api-resources-used",
                 "ingestion:no-hardcoded-url-or-path",
                 "ingestion:flat-secrets-read"):
        assert fact in connector["check"], (
            f"the judge must be told to grade from {fact} rather than from the "
            f"transcript"
        )


@pytest.mark.parametrize("scenario", ["worldbank-live", "authenticated-api-source-build"])
def test_every_declared_fact_is_emitted_by_its_checker(scenario: str):
    """A judge told to "grade FROM THAT FACT" needs the fact to exist.

    A renamed fact leaves the judge deferring to something the checker never
    prints, and a deferred-to-nothing check grades as absent rather than as
    failed — the quiet direction.
    """
    checks = json.loads((PUBLIC / scenario / "checks.json").read_text(encoding="utf-8"))
    script = (PUBLIC / scenario / "fixtures" /
              checks["deterministic_check"]["script"]).read_text(encoding="utf-8")
    referenced = {
        fact for check in checks["checks"]
        for fact in ("ingestion:rest-api-resources-used",
                     "ingestion:no-hardcoded-url-or-path",
                     "ingestion:flat-secrets-read",
                     "closure:endpoints-in-profile",
                     "closure:endpoints-public",
                     "closure:no-endpoints-companion")
        if fact in check["check"]
    }
    assert referenced, (
        f"{scenario} names no connector fact in any check — either the judge "
        f"stopped deferring to the gate, or this test is asserting nothing"
    )
    missing = sorted(f for f in referenced if f'"{f}"' not in script)
    assert not missing, f"{scenario}: judge defers to facts its checker never emits: {missing}"
