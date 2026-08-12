#!/usr/bin/env python3
"""Independent verifier for the api-source supervisor E2E (NEX-873 AC6/AC7).

`authenticated-api-source-build` proves a closure MATERIALIZES against a
header-gated REST fixture. It stops there. Nothing proved that the closure the
supervisor PUBLISHES still reaches that fixture through dlt, or that the
published product can be resumed, described, and queried — the acceptance
criteria this scenario exists for.

The gap matters because publication changes what runs. The supervisor
re-materializes from an immutable definition snapshot, not from the agent's
working directory, so a closure that ingests correctly under the author's hand
can still fail once published: an endpoint left in a companion file that the
snapshot does not carry, a header assembled from a secret the profile never
declared, a base_url read from an environment the supervisor does not set.

Harness only, and withheld from the agent's workspace. `job-loop`'s verifier
also ships an `--mode agent` forcing function the agent runs against its own
live endpoint; this one does not, because it computes the exact per-team counts
a correct product must reproduce — the answer key to the brief's question 1 —
and imports runner-side modules the workspace does not have. It runs from the
pristine scenario copy after the agent exits and re-serves the published
snapshot itself, with the runner's fixture still bound to the same port, which
is a stronger claim than a liveness check the agent runs on itself.

Two things make the wire claim decidable rather than inferred:

* the fixture appends every request it receives to a log outside the workspace
  (`NXD_STUB_OBSERVATIONS`), so the verifier can see WHICH requests the
  supervisor's own materialization made and what headers they carried; and
* the log is truncated immediately before the re-serve, so the traffic it holds
  afterwards belongs to the published definition, not to the agent's earlier
  attempts.

Without the second, a closure that 403'd on every request during the re-serve
would still "pass" on the agent's successful traffic from ten minutes earlier.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "tools"))

from api_connector_gate import (  # noqa: E402
    declared_endpoints,
    find_closure,
    headers_built_from_secrets,
    no_hardcoded_url_or_path,
    profile_attributes,
    uses_rest_api_resources,
)
from desktop_supervisor import (  # noqa: E402
    CheckFailure,
    catalog_entries,
    describe,
    find_data_dir,
    definition_snapshot,
    published_runs,
    query,
    serve_snapshot,
    stop_served,
)

# The stub is borrowed from the build scenario rather than copied — see the
# `fixtures_from` key in this scenario's http_stub.json and the note in
# `http_stub_server`. Two scenarios ingesting from one fixture must serve the
# same payload, or the pair stops being comparable.
STUB_PATH = (HERE.parents[1] / "authenticated-api-source-build" / "fixtures" /
             "stub_beacon_api.py")

STUB_HOSTS = ("127.0.0.1", "localhost")
STUB_PATHS = ("/v1/checks", "/v1/monitors")

FAILURES: list[str] = []
PASSES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    (PASSES if ok else FAILURES).append(name if ok else f"{name}: {detail}".rstrip(": "))
    return ok


def load_stub():
    spec = importlib.util.spec_from_file_location("_stub_beacon_api", STUB_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Reference answers, computed from the fixture's own payload
# ---------------------------------------------------------------------------


def checks_per_team(stub) -> dict[str, int]:
    """Checks per owning team, derived from the stub — never hardcoded.

    Only monitors that EXIST get a team: the four orphaned check rows
    (monitor_ids 9101-9104) reference a monitor the directory never had, so no
    correct closure can attribute them to a named team, whatever it decides to
    do with them. That is what makes these counts EXACT per resolvable team
    rather than a floor -- the disposition the brief leaves open cannot move
    them, and a closure whose per-team totals differ has lost or invented rows.
    """
    totals: dict[str, int] = {}
    for row in stub.CHECKS:
        team = stub.TEAMS.get(row["monitor_id"])
        if team is None:
            continue
        totals[team] = totals.get(team, 0) + 1
    return totals


def observations_since_reset(stub) -> list[dict[str, Any]]:
    log = os.environ.get(stub.OBSERVATIONS_ENV, "").strip()
    if not log:
        return []
    return stub.logged_observations(Path(log))


# ---------------------------------------------------------------------------
# Selection search — the catalog is the agent's, so the names are not ours
# ---------------------------------------------------------------------------


def team_selections(measures: list[str], dimensions: list[str]) -> list[dict[str, Any]]:
    """Plausible governed selections for "check volume by owning team".

    The agent authors the semantic model, so this cannot assert on a metric
    name. It searches the catalog the product actually published for a
    team-shaped dimension and tries each measure against it. A scenario that
    demanded `check_count` by `team` would be grading the agent's vocabulary
    rather than whether the product answers the brief's question 1.
    """
    team_dims = [d for d in dimensions if "team" in d.lower()]
    if not team_dims:
        return []
    # Count-shaped measures first: the question is "how many checks", so a
    # measure whose name says count is the likeliest correct answer and trying
    # it first keeps the common case to a single query.
    ordered = sorted(measures, key=lambda m: 0 if "count" in m.lower() else 1)
    return [{"measures": [m], "dimensions": [d]} for d in team_dims for m in ordered]


def rows_as_totals(result: dict[str, Any],
                   selection: dict[str, Any]) -> dict[str, float] | None:
    """A two-column {dimension: measure} answer, or None if it is not that.

    Columns are resolved BY NAME against the selection, never by position.
    `check_job_loop.py` states the rule this follows -- "result column order is
    a catalog implementation detail, not a semantic requirement" -- and a
    positional read fails a correct product the moment the supervisor emits the
    measure first: `float()` on a team name raises, every candidate selection is
    recorded as "not a two-column answer", and the reconciliation fails for a
    reason that has nothing to do with the closure.

    Falls back to position ONLY when the names do not resolve, so a catalog that
    labels its columns differently still gets read rather than reported as
    unusable.
    """
    columns = [str(c) for c in result.get("columns", [])]
    if len(columns) != 2:
        return None
    dimension = str(selection["dimensions"][0])
    measure = str(selection["measures"][0])
    lowered = [c.lower() for c in columns]
    if dimension.lower() in lowered and measure.lower() in lowered:
        dim_index = lowered.index(dimension.lower())
        measure_index = lowered.index(measure.lower())
    else:
        dim_index, measure_index = 0, 1

    totals: dict[str, float] = {}
    for row in result.get("rows", []):
        if len(row) != 2 or row[dim_index] is None:
            continue
        try:
            totals[str(row[dim_index])] = float(row[measure_index])
        except (TypeError, ValueError):
            return None
    return totals


# ---------------------------------------------------------------------------
# harness mode
# ---------------------------------------------------------------------------


def harness_mode(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    stub = load_stub()

    # ---- the closure the agent left behind ------------------------------
    root = find_closure(workspace)
    if not check("closure:transform-exists",
                 (root / "transform" / "main.py").is_file(), str(root)):
        return report()

    ok, detail = uses_rest_api_resources(root)
    check("ingestion:rest-api-resources-used", ok, detail)
    ok, detail = no_hardcoded_url_or_path(root, STUB_HOSTS, STUB_PATHS)
    check("ingestion:no-hardcoded-url-or-path", ok, detail)

    fields, _public_flags = profile_attributes(root)
    header_keys = [k for k in fields if k.lower() == "header_user_agent"]
    check("header:declared-in-profile",
          bool(header_keys) and fields[header_keys[0]] == stub.REQUIRED_USER_AGENT,
          f"no header_user_agent = {stub.REQUIRED_USER_AGENT!r} among {sorted(fields)}")
    # Not redundant with the wire facts below, and the one static fact they
    # cannot replace: a closure with the User-Agent frozen into transform/main.py
    # sends exactly the right header, so the fixture sees a perfect request and
    # every observation-based check passes — while the closure is one profile
    # change away from 403ing everywhere.
    ok, detail = headers_built_from_secrets(root, stub.REQUIRED_USER_AGENT)
    check("header:built-from-secrets", ok, detail)
    check("closure:endpoints-in-profile", len(declared_endpoints(root)) >= 2,
          f"expected one endpoint_<model> attribute per model, found "
          f"{sorted(declared_endpoints(root))}")

    # ---- publication ----------------------------------------------------
    try:
        data_dir = find_data_dir(workspace)
        runs = published_runs(data_dir, args.workflow)
    except CheckFailure as exc:
        check("supervisor:published", False, str(exc))
        return report()
    if not check("supervisor:published", bool(runs),
                 f"no Published run for workflow {args.workflow!r} in {data_dir}"):
        return report()

    # ---- resume: re-serve the published snapshot ------------------------
    # The durable key is the definition plus the workflow id. This is the
    # fresh-session recovery path, and for an api-source closure it re-fetches
    # from the upstream, which is the whole point of running it here.
    try:
        snapshot = definition_snapshot(data_dir, str(runs[-1]["definition_id"]))
    except CheckFailure as exc:
        check("supervisor:definition-snapshot", False, str(exc))
        return report()
    check("supervisor:definition-snapshot", True)

    # Everything the fixture sees from here belongs to the re-serve. Without
    # this truncation the wire assertion below would pass on the agent's own
    # traffic from earlier in the run.
    stub.reset_observations()

    served = None
    try:
        try:
            served = serve_snapshot(snapshot, args.workflow)
        except CheckFailure as exc:
            check("supervisor:resumes-published-definition", False, str(exc))
            return report()
        check("supervisor:resumes-published-definition", True)

        # ---- the wire: did the PUBLISHED closure reach the fixture? -----
        seen = observations_since_reset(stub)
        check("wire:observations-recorded", bool(seen),
              "the fixture recorded no request during the re-serve — either the "
              "published definition never ingested, or the observation log is "
              "not wired (NXD_STUB_OBSERVATIONS)")
        authorized_with_header = [
            o for o in seen
            if o.get("user_agent") == stub.REQUIRED_USER_AGENT and o.get("authorized")
        ]
        check("wire:header-reaches-fixture-on-resume", bool(authorized_with_header),
              f"no authorized request carrying {stub.REQUIRED_USER_AGENT!r} arrived "
              f"during the re-serve; User-Agents observed: "
              f"{sorted({o.get('user_agent') for o in seen})}")
        check("wire:no-unauthorized-requests",
              all(o.get("authorized") for o in seen),
              f"{sum(1 for o in seen if not o.get('authorized'))} of {len(seen)} "
              f"requests during the re-serve were unauthenticated")

        # ---- describe ---------------------------------------------------
        try:
            described = describe(served.endpoint, served.bearer)
        except CheckFailure as exc:
            check("supervisor:describe", False, str(exc))
            return report()
        measures, dimensions = catalog_entries(described)
        check("supervisor:describe", bool(measures) and bool(dimensions),
              f"catalog published {len(measures)} measures / {len(dimensions)} "
              f"dimensions — a governed query needs at least one of each")

        # ---- governed query --------------------------------------------
        expected = checks_per_team(stub)
        selections = team_selections(measures, dimensions)
        if not selections:
            check("query:team-dimension-published", False,
                  f"no team-shaped dimension in {dimensions} — the brief's "
                  f"question 1 groups check results by owning team, so the "
                  f"product cannot answer it")
            return report()
        check("query:team-dimension-published", True)

        with tempfile.TemporaryDirectory(prefix="api-e2e-query-") as scratch:
            matched, attempts = None, []
            for selection in selections:
                try:
                    result = query(served.endpoint, served.bearer, selection,
                                   Path(scratch))
                except CheckFailure as exc:
                    attempts.append(f"{selection}: {exc}")
                    continue
                totals = rows_as_totals(result, selection)
                if totals is None:
                    attempts.append(f"{selection}: not a two-column answer")
                    continue
                if all(abs(totals.get(team, -1) - float(count)) < 1e-6
                       for team, count in expected.items()):
                    matched = selection
                    break
                attempts.append(f"{selection}: got {totals}, expected {expected}")
            check("query:checks-by-team-matches-source", matched is not None,
                  "no governed selection reproduced the fixture's own per-team "
                  f"check counts {expected}; tried: {attempts[:6]}")
    finally:
        if served is not None:
            stop_served(served)

    return report()


def report() -> int:
    """Print the report; harness mode additionally emits its facts as JSON.

    `desktop_harness_fact` parses the LAST stdout line as the fact object, so
    the human-readable lines have to come first.
    """
    for name in PASSES:
        print(f"PASS {name}")
    for name in FAILURES:
        print(f"FAIL {name}")
    print()
    print(f"{len(PASSES)} passed, {len(FAILURES)} failed")
    if not FAILURES:
        print("ALL CHECKS PASSED")
    return 1 if FAILURES else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    # Harness only, and withheld from the agent's workspace. The job-loop
    # scenario also ships an `--mode agent` forcing function the agent runs
    # against its own live endpoint; this one does not, for two reasons. It
    # imports the runner-side gate and the fixture module, neither of which
    # exists in the workspace — and it names the exact per-team counts a
    # correct product must reproduce, which in the agent's hands is the answer
    # key to the brief's question 1. The harness re-serves independently, which
    # is a stronger claim than a liveness check the agent runs on itself.
    ap.add_argument("--mode", choices=("harness",), required=True)
    ap.add_argument("--workspace", default=".")
    ap.add_argument("--workflow", default="beacon-uptime")
    args = ap.parse_args()

    code = harness_mode(args)
    # The runner reads this line, not the exit code, and a verifier that dies
    # mid-report must not look like a pass — so emit the facts last, always.
    print(json.dumps({
        "passed": not FAILURES,
        "failures": [f"FAIL {f}" for f in FAILURES],
        "passes": list(PASSES),
    }, sort_keys=True))
    return code


if __name__ == "__main__":
    sys.exit(main())
