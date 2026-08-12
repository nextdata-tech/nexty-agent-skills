"""The api-source supervisor E2E's wiring (NEX-873 AC6/AC7).

`authenticated-api-source-build` proves a closure materializes against a
header-gated REST fixture and stops there. Nothing proved that the closure the
supervisor PUBLISHES still reaches that fixture, or that the published product
can be resumed, described and queried. `authenticated-api-source-supervisor`
closes that, and it needs three things the runner could not previously do:

1. the desktop supervisor and the HTTP fixture in the SAME cell, with the
   fixture outliving the agent run — the verifier re-serves the published
   definition, which re-materializes, which re-fetches;
2. a scenario-chosen harness verifier, since `check_job_loop.py` was a fixed
   filename; and
3. a request log the fixture writes to a FILE, since the verifier is a separate
   process and in-memory `OBSERVED` cannot cross that boundary.

The scenario itself needs a live supervisor and cannot run in CI. These tests
cover everything about it that does not: the wiring above, the verifier's own
arithmetic, and the fixture-vs-brief constants that would otherwise drift
silently into a scenario nobody runs on a PR.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

EVALS = Path(__file__).resolve().parents[1]
PUBLIC = EVALS / "public"
SUPERVISOR = PUBLIC / "authenticated-api-source-supervisor"
BUILD = PUBLIC / "authenticated-api-source-build"
STUB_PATH = BUILD / "fixtures" / "stub_beacon_api.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


sys.path.insert(0, str(EVALS))
run = _load(EVALS / "run.py", "_eval_run_for_api_e2e")
stub = _load(STUB_PATH, "_stub_for_api_e2e")
verifier = _load(SUPERVISOR / "fixtures" / "check_api_source_e2e.py",
                 "_api_source_e2e_verifier")


# ---------------------------------------------------------------------------
# The scenario resolves both runtimes
# ---------------------------------------------------------------------------


def test_scenario_opts_into_both_the_supervisor_and_the_fixture():
    """The pairing is the point: a supervisor cell that also has an upstream.

    Before this scenario the two opt-ins were mutually exclusive branches in
    run_one, so a desktop cell could not have an API to ingest from.
    """
    assert run.scenario_needs_desktop(SUPERVISOR) is not None
    assert run.scenario_needs_http_stub(SUPERVISOR) is not None


def test_the_fixture_is_borrowed_not_copied():
    """One stub, two scenarios — a copy drifts and the pair stops comparing."""
    spec = run.scenario_needs_http_stub(SUPERVISOR)
    assert spec["fixtures_from"] == "authenticated-api-source-build"
    assert not (SUPERVISOR / "fixtures" / "stub_beacon_api.py").exists(), (
        "the supervisor scenario ships its own copy of the stub; it must borrow "
        "the build scenario's via fixtures_from"
    )


def test_verifier_is_named_by_the_scenario_and_exists():
    spec = run.scenario_needs_desktop(SUPERVISOR)
    assert spec["verifier"] == "check_api_source_e2e.py"
    assert (SUPERVISOR / "fixtures" / spec["verifier"]).is_file()


def test_verifier_is_withheld_from_the_agent_workspace():
    """It computes the answer key to the brief's question 1."""
    excluded = run.SCENARIO_WORKSPACE_FIXTURE_EXCLUSIONS.get(
        "authenticated-api-source-supervisor", frozenset())
    assert "check_api_source_e2e.py" in excluded


def test_desktop_harness_fact_runs_the_named_verifier(tmp_path, monkeypatch):
    """A fixed `check_job_loop.py` would silently run the wrong scenario's checker."""
    captured: dict = {}

    class _Proc:
        returncode, stdout, stderr = 0, '{"passed": true}\n', ""

    monkeypatch.setattr(run.subprocess, "run",
                        lambda cmd, **kw: (captured.__setitem__("cmd", cmd), _Proc())[1])
    fact = run.desktop_harness_fact(
        SUPERVISOR, tmp_path, sys.executable, "beacon-uptime", tmp_path, {},
        verifier="check_api_source_e2e.py")

    assert str(SUPERVISOR / "fixtures" / "check_api_source_e2e.py") in captured["cmd"]
    assert json.loads(fact.split(": ", 1)[1])["passed"] is True


def test_a_missing_verifier_is_an_infrastructure_error_not_a_pass(tmp_path):
    """Fail closed: a renamed verifier must not read as "nothing to check"."""
    fact = run.desktop_harness_fact(
        SUPERVISOR, tmp_path, sys.executable, "beacon-uptime", tmp_path, {},
        verifier="check_nonexistent.py")
    payload = json.loads(fact.split(": ", 1)[1])
    assert payload["passed"] is False
    assert "not found" in payload["infrastructure_error"]


# ---------------------------------------------------------------------------
# The file-backed request log
# ---------------------------------------------------------------------------


def test_two_concurrent_cells_keep_separate_logs(tmp_path):
    """Cells share a process, so the log path cannot be a process global.

    `run.py` runs cells in a ThreadPoolExecutor (default concurrency 4), and the
    ordinary A/B benchmark run puts two `http_stub_server` contexts in flight at
    once. With the path in `os.environ`, cell B's assignment redirects cell A's
    fixture traffic into B's log: A's verifier then fails
    `wire:observations-recorded` on a perfectly correct closure, and whichever
    cell exits first unsets the variable under the other.
    """
    import urllib.request

    spec = run.scenario_needs_http_stub(SUPERVISOR)
    ws_a, ws_b = tmp_path / "a", tmp_path / "b"
    ws_a.mkdir()
    ws_b.mkdir()

    with run.http_stub_server(SUPERVISOR, ws_a, spec, "claude") as (url_a, log_a), \
            run.http_stub_server(SUPERVISOR, ws_b, spec, "claude") as (url_b, log_b):
        assert log_a != log_b
        for url in (url_a, url_a, url_b):
            request = urllib.request.Request(
                f"{url}/v1/monitors",
                headers={"User-Agent": stub.REQUIRED_USER_AGENT,
                         "Authorization": f"Bearer {stub.VALID_TOKEN}"})
            urllib.request.urlopen(request, timeout=5).read()

        assert len(stub.logged_observations(log_a)) == 2, (
            "cell A's traffic did not land in cell A's log"
        )
        assert len(stub.logged_observations(log_b)) == 1, (
            "cell B's log picked up cell A's traffic"
        )


def test_the_agent_environment_never_names_the_log(tmp_path):
    """The log records the headers the agent's own failed requests carried.

    Handing the agent its path turns "diagnose an unexplained 403" — the task —
    into `cat "$NXD_STUB_OBSERVATIONS"`. Both backends build the child env from
    `os.environ`, so the runner must not put it there.
    """
    import os

    spec = run.scenario_needs_http_stub(SUPERVISOR)
    before = os.environ.get(run.STUB_OBSERVATIONS_ENV)
    with run.http_stub_server(SUPERVISOR, tmp_path, spec, "claude") as (_url, log):
        assert log is not None
        assert os.environ.get(run.STUB_OBSERVATIONS_ENV) == before, (
            "the log path reached the process environment, which both agent "
            "backends copy into the agent's own"
        )


def test_a_stub_that_cannot_start_leaves_no_log_directory(tmp_path):
    """The temp dir is created before the server; a failed start must not strand it.

    Counts the delta rather than asserting none exist: an earlier crashed run
    may have left one behind, and failing this test for that would be blaming
    the wrong thing.
    """
    import tempfile as _tempfile

    def _log_dirs() -> set[Path]:
        return set(Path(_tempfile.gettempdir()).glob("eval-stub-observations-*"))

    before = _log_dirs()
    spec = {**run.scenario_needs_http_stub(SUPERVISOR), "start": "no_such_start_fn"}
    with pytest.raises(AttributeError):
        with run.http_stub_server(SUPERVISOR, tmp_path, spec, "claude"):
            pass

    assert not (_log_dirs() - before), (
        "the log directory survived a failed start; it would then outlive the "
        "whole run"
    )


def test_stub_logs_observations_for_another_process(tmp_path, monkeypatch):
    """The verifier is a separate process; OBSERVED cannot reach it."""
    import urllib.error
    import urllib.request

    log = tmp_path / "observations.jsonl"
    monkeypatch.setenv(stub.OBSERVATIONS_ENV, str(log))
    server, port, thread = stub.start_server()
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/v1/monitors",
            headers={"User-Agent": stub.REQUIRED_USER_AGENT,
                     "Authorization": f"Bearer {stub.VALID_TOKEN}"})
        urllib.request.urlopen(request, timeout=5).read()
        # A refused request must be logged too — "the closure 403'd on every
        # request" is exactly what the verifier needs to be able to see.
        with pytest.raises(urllib.error.HTTPError):
            urllib.request.urlopen(f"http://127.0.0.1:{port}/v1/monitors", timeout=5)
    finally:
        stub.stop_server(server, thread)

    logged = stub.logged_observations(log)
    assert len(logged) == 2
    assert logged[0] == {"path": "/v1/monitors",
                         "user_agent": stub.REQUIRED_USER_AGENT, "authorized": True}
    assert logged[1]["authorized"] is False
    assert logged[1]["user_agent"] != stub.REQUIRED_USER_AGENT


def test_reset_truncates_the_log_rather_than_removing_it(tmp_path, monkeypatch):
    """The verifier resets to mark the boundary before its own re-serve.

    Truncate, not unlink: a missing file is indistinguishable from "the stub
    never started", which would turn a clean re-serve into an infrastructure
    failure.
    """
    log = tmp_path / "observations.jsonl"
    log.write_text('{"path": "/v1/checks"}\n', encoding="utf-8")
    monkeypatch.setenv(stub.OBSERVATIONS_ENV, str(log))

    stub.reset_observations()

    assert log.is_file()
    assert stub.logged_observations(log) == []


def test_no_log_env_leaves_the_stub_in_memory_only(monkeypatch):
    """The build scenario does not opt in and must be untouched by this."""
    monkeypatch.delenv(stub.OBSERVATIONS_ENV, raising=False)
    stub.reset_observations()
    stub._record("/v1/checks", "x", True)
    assert stub.observations()[-1] == ("/v1/checks", "x", True)


def test_run_py_and_the_stub_agree_on_the_env_var():
    """Two sides that never import each other — a rename disables the log."""
    assert run.STUB_OBSERVATIONS_ENV == stub.OBSERVATIONS_ENV


def test_http_stub_server_borrows_fixtures_and_wires_the_log(tmp_path):
    """End to end through the runner's own context manager."""
    spec = run.scenario_needs_http_stub(SUPERVISOR)
    with run.http_stub_server(SUPERVISOR, tmp_path, spec, "claude") as (url, log):
        assert url.startswith("http://127.0.0.1:")
        assert (tmp_path / "ENDPOINT_URL").read_text(encoding="utf-8").strip() == url
        assert log is not None and log.is_file()
        # Outside the workspace on purpose: in it, the agent could read back the
        # headers its own failing requests carried, turning "diagnose an
        # unexplained 403" into a lookup.
        assert tmp_path not in log.parents


def test_an_unknown_fixtures_from_fails_loudly(tmp_path):
    spec = {**run.scenario_needs_http_stub(SUPERVISOR), "fixtures_from": "nope"}
    with pytest.raises(run.HttpStubSetupError, match="no such scenario"):
        with run.http_stub_server(SUPERVISOR, tmp_path, spec, "claude"):
            pass


# ---------------------------------------------------------------------------
# The verifier's own arithmetic
# ---------------------------------------------------------------------------


def test_expected_team_counts_come_from_the_fixture_not_a_constant():
    """Recompute independently: if the stub's payload changes, this moves."""
    totals = verifier.checks_per_team(stub)
    recomputed: dict[str, int] = {}
    for row in stub.CHECKS:
        team = stub.TEAMS.get(row["monitor_id"])
        if team is not None:
            recomputed[team] = recomputed.get(team, 0) + 1
    assert totals == recomputed
    assert sum(totals.values()) == len(stub.CHECKS) - 4, (
        "the four orphaned check rows reference a monitor the directory never "
        "had, so they resolve to no team"
    )
    assert set(totals) == set(stub.TEAMS.values())


def test_orphans_are_excluded_so_their_disposition_stays_the_authors_call():
    """The brief leaves the orphan ruling open; the check must not close it."""
    orphan_ids = {row["monitor_id"] for row in stub.CHECKS
                  if row["monitor_id"] not in stub.TEAMS}
    assert orphan_ids, "the fixture no longer carries orphaned check rows"
    assert sum(verifier.checks_per_team(stub).values()) < len(stub.CHECKS)


def test_selection_search_prefers_a_count_measure_and_needs_a_team_dimension():
    selections = verifier.team_selections(
        ["avg_latency_ms", "check_count"], ["team", "monitor_name"])
    assert selections[0] == {"measures": ["check_count"], "dimensions": ["team"]}
    assert all(s["dimensions"] == ["team"] for s in selections), (
        "only team-shaped dimensions answer the brief's question 1"
    )
    assert verifier.team_selections(["check_count"], ["monitor_name"]) == []


SELECTION = {"measures": ["check_count"], "dimensions": ["team"]}


def test_totals_reader_rejects_a_shape_it_cannot_compare():
    assert verifier.rows_as_totals(
        {"columns": ["team", "check_count"], "rows": [["payments", 9]]},
        SELECTION) == {"payments": 9.0}
    assert verifier.rows_as_totals(
        {"columns": ["team", "check_count", "extra"], "rows": []}, SELECTION) is None
    assert verifier.rows_as_totals(
        {"columns": ["team", "check_count"], "rows": [["payments", "nine"]]},
        SELECTION) is None


def test_totals_reader_resolves_columns_by_name_not_position():
    """Column order is a catalog implementation detail, not a contract.

    A positional read fails a correct product the moment the supervisor emits
    the measure first — `float("payments")` raises, the selection is recorded as
    "not a two-column answer", and the reconciliation fails for a reason that
    has nothing to do with the closure.
    """
    assert verifier.rows_as_totals(
        {"columns": ["check_count", "team"], "rows": [[9, "payments"]]},
        SELECTION) == {"payments": 9.0}
    # Case-insensitively, since a catalog may title-case its headers.
    assert verifier.rows_as_totals(
        {"columns": ["Check_Count", "Team"], "rows": [[9, "payments"]]},
        SELECTION) == {"payments": 9.0}


def test_totals_reader_falls_back_to_position_when_names_do_not_resolve():
    """Unrecognized headers should still be read, not reported as unusable."""
    assert verifier.rows_as_totals(
        {"columns": ["group", "value"], "rows": [["payments", 9]]},
        SELECTION) == {"payments": 9.0}


def test_verifier_reads_the_log_only_when_the_runner_wired_one(monkeypatch):
    monkeypatch.delenv(stub.OBSERVATIONS_ENV, raising=False)
    assert verifier.observations_since_reset(stub) == []


# ---------------------------------------------------------------------------
# harness_mode end to end, against a faked supervisor
# ---------------------------------------------------------------------------
#
# The real cell needs supervisor binaries CI does not have. What CI CAN prove is
# that the verifier decides correctly given a supervisor's answers — which is
# where the interesting logic lives: the publication lookup, the observation
# boundary that separates the re-serve's traffic from the agent's, and the
# catalog search. The supervisor's own CLI contract is not under test here; it
# is inherited verbatim from `check_job_loop.py`, which live runs exercise.

CLEAN_TRANSFORM = '''
from dlt.sources.rest_api import RESTAPIConfig, rest_api_resources

def ingest(duckdb, secrets):
    client = {"base_url": secrets["base_url"],
              "auth": {"type": secrets["auth_type"], "token": secrets["auth_token"]},
              "headers": {"User-Agent": secrets["header_user_agent"]}}
    resources = [{"name": m, "endpoint": {"path": secrets[f"endpoint_{m}"]}}
                 for m in ("monitors", "checks")]
    return {r.name: r for r in rest_api_resources({"client": client,
                                                   "resources": resources})}
'''


def _profile() -> str:
    return f"""
services:
  - name: api-source
    driver: nxd:generic-secrets:1.0.0
    attributes:
      - key: base_url
        value: http://127.0.0.1:9
        public: true
      - key: auth_type
        value: bearer
        public: true
      - key: auth_token
        value: {stub.VALID_TOKEN}
        public: false
      - key: header_user_agent
        value: {stub.REQUIRED_USER_AGENT}
        public: true
      - key: endpoint_monitors
        value: /v1/monitors
        public: true
      - key: endpoint_checks
        value: /v1/checks
        public: true
"""


def _workspace(tmp_path: Path, *, published: bool = True,
               transform: str = CLEAN_TRANSFORM) -> Path:
    import sqlite3

    closure = tmp_path / "nxd-jobs" / "beacon" / "closure"
    (closure / "transform").mkdir(parents=True)
    (closure / "transform" / "main.py").write_text(transform, encoding="utf-8")
    (closure / "infra-profile.yaml").write_text(_profile(), encoding="utf-8")

    state = tmp_path / ".desktop" / "state"
    definition = state / "definitions" / "def-1"
    definition.mkdir(parents=True)
    (definition / "spec.py").write_text("# published snapshot\n", encoding="utf-8")
    con = sqlite3.connect(state / "state.sqlite")
    con.execute("CREATE TABLE runs (run_id TEXT, workflow_id TEXT, artifact_id TEXT, "
                "definition_id TEXT, status TEXT)")
    if published:
        con.execute("INSERT INTO runs VALUES ('r1','beacon-uptime','a1','def-1','Published')")
    else:
        con.execute("INSERT INTO runs VALUES ('r1','beacon-uptime','a1','def-1','Failed')")
    con.commit()
    con.close()
    return tmp_path


class _FakeServed:
    endpoint = "http://127.0.0.1:65000/mcp"
    bearer = "fake-bearer"  # noqa: S105 - fixture


def _install_fake_supervisor(monkeypatch, log: Path, *, requests_on_resume,
                             described: dict, totals: dict | None):
    """Fake the three supervisor calls harness_mode makes.

    `requests_on_resume` is what the FIXTURE sees while the snapshot re-serves —
    written by the fake serve, exactly as the real materialization would cause.
    """
    def _serve(_snapshot, _workflow):
        with log.open("a", encoding="utf-8") as fh:
            for entry in requests_on_resume:
                fh.write(json.dumps(entry) + "\n")
        return _FakeServed()

    def _query(_endpoint, _bearer, selection, _scratch):
        if totals is None:
            raise verifier.CheckFailure("no such measure")
        measure = selection["measures"][0]
        if "count" not in measure:
            raise verifier.CheckFailure(f"{measure} is not queryable here")
        # MEASURE FIRST on purpose. Column order is a catalog implementation
        # detail, and a verifier that reads by position fails a correct product
        # for it — so the fake emits the order that would break a positional
        # read, and every harness test below inherits that guard.
        return {"columns": [measure, "team"],
                "rows": [[value, team] for team, value in totals.items()],
                "row_count": len(totals), "truncated": False, "error": ""}

    monkeypatch.setattr(verifier, "serve_snapshot", _serve)
    monkeypatch.setattr(verifier, "stop_served", lambda _served: None)
    monkeypatch.setattr(verifier, "describe", lambda _e, _b: described)
    monkeypatch.setattr(verifier, "query", _query)


CATALOG = {"models": [{"name": "checks",
                       "metrics": [{"name": "check_count"}],
                       "dimensions": [{"name": "team"}, {"name": "monitor_name"}]}]}


def _authorized(path: str) -> dict:
    return {"path": path, "user_agent": stub.REQUIRED_USER_AGENT, "authorized": True}


@pytest.fixture
def harness(tmp_path, monkeypatch):
    log = tmp_path / "observations.jsonl"
    log.write_text("", encoding="utf-8")
    monkeypatch.setenv(stub.OBSERVATIONS_ENV, str(log))

    def run_harness(*, requests_on_resume=None, described=CATALOG, totals=...,
                    published=True, transform=CLEAN_TRANSFORM):
        if totals is ...:
            totals = dict(verifier.checks_per_team(stub))
        if requests_on_resume is None:
            requests_on_resume = [_authorized("/v1/monitors"), _authorized("/v1/checks")]
        _install_fake_supervisor(monkeypatch, log, described=described,
                                 requests_on_resume=requests_on_resume, totals=totals)
        ws = _workspace(tmp_path, published=published, transform=transform)
        verifier.FAILURES.clear()
        verifier.PASSES.clear()
        import argparse as _argparse
        code = verifier.harness_mode(_argparse.Namespace(
            workspace=str(ws), workflow="beacon-uptime"))
        return code, [f.split(":", 2)[0] + ":" + f.split(":", 2)[1]
                      for f in verifier.FAILURES]

    return run_harness, log


def test_a_correct_published_product_passes_every_fact(harness):
    run_harness, _log = harness
    code, failures = run_harness()
    assert code == 0, failures
    assert "supervisor:resumes-published-definition" in verifier.PASSES
    assert "wire:header-reaches-fixture-on-resume" in verifier.PASSES
    assert "query:checks-by-team-matches-source" in verifier.PASSES


def test_traffic_from_before_the_reset_cannot_carry_the_wire_claim(harness):
    """The reset is what makes the wire fact about the RE-SERVE.

    Without it, a published definition that 403s on every request still passes
    on the agent's successful traffic from earlier in the run — which is the
    exact failure publication introduces and this scenario exists to catch.
    """
    run_harness, log = harness
    # The agent's earlier, perfectly good traffic.
    with log.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(_authorized("/v1/monitors")) + "\n")

    forbidden = {"path": "/v1/monitors", "user_agent": "dlt/1.28.2", "authorized": False}
    code, failures = run_harness(requests_on_resume=[forbidden])

    assert code == 1
    assert "wire:header-reaches-fixture-on-resume" in failures
    assert "wire:no-unauthorized-requests" in failures


def test_a_resume_that_never_ingests_is_caught(harness):
    run_harness, _log = harness
    code, failures = run_harness(requests_on_resume=[])
    assert code == 1
    assert "wire:observations-recorded" in failures


def test_no_published_run_stops_before_re_serving(harness):
    run_harness, _log = harness
    code, failures = run_harness(published=False)
    assert code == 1
    assert "supervisor:published" in failures
    assert "supervisor:resumes-published-definition" not in verifier.PASSES


def test_a_catalog_without_a_team_dimension_fails_the_question(harness):
    run_harness, _log = harness
    code, failures = run_harness(described={
        "models": [{"name": "checks", "metrics": [{"name": "check_count"}],
                    "dimensions": [{"name": "monitor_name"}]}]})
    assert code == 1
    assert "query:team-dimension-published" in failures


def test_wrong_per_team_numbers_fail_even_with_a_healthy_endpoint(harness):
    """The served answer is reconciled against the fixture, not just returned."""
    run_harness, _log = harness
    wrong = {team: count + 1 for team, count in verifier.checks_per_team(stub).items()}
    code, failures = run_harness(totals=wrong)
    assert code == 1
    assert "query:checks-by-team-matches-source" in failures


def test_a_hand_rolled_published_closure_fails_the_architecture_facts(harness):
    run_harness, _log = harness
    code, failures = run_harness(transform='''
import requests

def ingest(duckdb, secrets):
    return requests.get(secrets["base_url"] + secrets["endpoint_checks"]).json()
''')
    assert code == 1
    assert "ingestion:rest-api-resources-used" in failures


def test_a_hardcoded_header_fails_even_when_the_wire_looks_right(harness):
    """The header must come from the profile, or the next deployment 403s."""
    run_harness, _log = harness
    profile_less = CLEAN_TRANSFORM.replace(
        'secrets["header_user_agent"]', '"nexty-test-client/1.0"')
    code, failures = run_harness(transform=profile_less)
    # The fixture still saw a perfect request, and the profile still declares
    # the attribute — so the wire facts and header:declared-in-profile all pass.
    # Only reading the source can see this one.
    assert "wire:header-reaches-fixture-on-resume" in verifier.PASSES
    assert "header:declared-in-profile" in verifier.PASSES
    assert code == 1
    assert failures == ["header:built-from-secrets"], failures


# ---------------------------------------------------------------------------
# Scenario/fixture agreement
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("scenario", ["authenticated-api-source-build",
                                      "authenticated-api-source-supervisor"])
def test_the_brief_states_the_constants_the_fixture_enforces(scenario: str):
    """A drifted brief hands the agent a token or header the stub refuses.

    The failure would read as the agent misconfiguring the credential, which is
    the most expensive possible way to discover a typo in a fixture.
    """
    brief = (PUBLIC / scenario / "fixtures" / "BRIEF.md").read_text(encoding="utf-8")
    assert stub.VALID_TOKEN in brief
    assert stub.REQUIRED_USER_AGENT in brief


def test_judge_defers_only_to_facts_the_verifier_emits():
    """"Grade FROM THAT FACT" needs the fact to exist, or the check grades absent."""
    checks = json.loads((SUPERVISOR / "checks.json").read_text(encoding="utf-8"))
    source = (SUPERVISOR / "fixtures" / "check_api_source_e2e.py").read_text(
        encoding="utf-8")
    referenced = {
        token.strip(" .,;")
        for check in checks["checks"]
        for token in check["check"].replace("\n", " ").split()
        if token.count(":") == 1 and token.split(":")[0] in {
            "ingestion", "header", "closure", "supervisor", "wire", "query"}
    }
    assert referenced, "no check defers to a verifier fact — the gate is judge-only"
    missing = sorted(f for f in referenced if f'"{f}"' not in source)
    assert not missing, f"judge defers to facts the verifier never emits: {missing}"


def test_the_header_check_is_the_shared_one_not_a_second_copy():
    """This is the check the E2E was missing until a test caught it.

    The supervisor verifier passed a closure with the User-Agent frozen into
    `transform/main.py`, because the only implementation of that check lived in
    the build scenario's checker. Identity, not equivalence: a second copy is
    how it went missing in the first place.
    """
    build = _load(BUILD / "fixtures" / "check_authenticated_api_source.py",
                  "_build_checker_for_header_identity")
    assert (build.gate_headers_built_from_secrets is
            verifier.headers_built_from_secrets)
    assert verifier.headers_built_from_secrets.__module__ == "api_connector_gate"


def test_touching_the_borrowed_stub_selects_both_scenarios():
    """`fixtures_from` moves the stub out of the borrower's scenario directory.

    Selection keys on "a scenario directory changed", so a change to the shared
    stub would otherwise select only the scenario that happens to own the file —
    and the borrower, whose upstream just changed under it, would not run.
    """
    affected = _load(EVALS / "affected_scenarios.py", "_affected_for_api_e2e")
    scenarios, skipped = affected.load_scenarios("public")
    result = affected.select(
        ["evals/public/authenticated-api-source-build/fixtures/stub_beacon_api.py"],
        scenarios, skipped)

    assert "authenticated-api-source-build" in result["scenarios"]
    assert "authenticated-api-source-supervisor" in result["skipped"], (
        "the borrowing scenario is ci_skip'd, but it must still be RECOGNIZED "
        "as affected rather than silently absent"
    )


def test_the_docs_scenario_counts_match_the_suite_on_disk():
    """Adding a scenario silently falsifies five hand-maintained numbers.

    `evals/README.md` and `GETTING-STARTED.md` tell a reader how much of the
    suite CI actually runs. Nothing recomputed those counts, so they drift on
    the next scenario and the docs quietly overstate coverage — the direction
    that matters, since a reader trusts "20 of 33 run" as evidence.
    """
    scenarios = [d for d in PUBLIC.iterdir() if (d / "checks.json").is_file()]
    loaded = {d.name: json.loads((d / "checks.json").read_text(encoding="utf-8"))
              for d in scenarios}
    total = len(loaded)
    skipped = sum(1 for c in loaded.values() if c.get("ci_skip"))
    deterministic = sorted(n for n, c in loaded.items() if c.get("deterministic_check"))

    readme = (EVALS / "README.md").read_text(encoding="utf-8")
    getting_started = (EVALS / "GETTING-STARTED.md").read_text(encoding="utf-8")

    assert f"{total - skipped} of {total} public scenarios" in getting_started
    assert f"The remaining {skipped} declare `ci_skip`" in getting_started
    assert f"({total - skipped} of {total}; the {skipped} `ci_skip` are excluded)" in readme
    assert f"**The {skipped} `ci_skip` scenarios never run automatically**" in readme
    assert f'"Runnable" excludes the {skipped} `ci_skip` scenarios.' in readme
    assert f"Only {len(deterministic)} of {total} public scenarios use this today" in readme
    for name in deterministic:
        assert f"`{name}`" in readme, (
            f"{name} declares a deterministic_check but README's list omits it"
        )

    # The ci_skip table tells a reader WHICH scenarios CI never runs. A skipped
    # scenario missing from it reads as covered.
    words = {13: "Thirteen", 14: "Fourteen", 15: "Fifteen", 16: "Sixteen",
             17: "Seventeen", 18: "Eighteen"}
    assert f"{words[skipped]} scenarios are currently skipped:" in readme, (
        f"README's ci_skip preamble does not say {skipped}"
    )
    for name, cfg in loaded.items():
        if cfg.get("ci_skip"):
            assert f"| `{name}` |" in readme, (
                f"{name} is ci_skip'd but absent from README's skipped table"
            )


def test_scenario_is_marked_ci_skip_with_a_reason():
    """It needs supervisor binaries CI does not provision; say so, don't fail."""
    checks = json.loads((SUPERVISOR / "checks.json").read_text(encoding="utf-8"))
    assert checks["ci_skip"]
    assert checks["desktop_verify"] is True
    for skill in checks["skills"]:
        assert (EVALS.parent / "src" / skill).is_dir(), f"unknown skill: {skill}"
