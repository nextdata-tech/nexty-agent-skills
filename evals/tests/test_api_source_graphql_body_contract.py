"""POSTed-JSON-body api-source closures: the GraphQL path (this session's build).

An API with no GET surface — GraphQL being the ordinary case — reaches dlt
through ``endpoint.method = "POST"`` and ``endpoint.json``. Three things about
that path are invisible until a live build fails, and all three were hit in one
sitting while building a Linear closure:

1. **dlt scans every string in ``json`` for its OWN placeholder expressions.**
   A GraphQL query is nothing but braces, so ``rest_api_resources`` raises
   ``ValueError: Expression ... defined in `json` is not valid`` before a single
   request is sent. The message names ``resources``, not GraphQL, so it reads as
   a malformed resource list rather than a templating collision. The fix is to
   double every brace — and, critically, dlt expands them back, so the upstream
   receives the byte-identical query.

2. **An api closure that carries its own ``data/`` tree still needs
   ``csv-source-path``.** The supervisor refuses to stage the definition without
   it (``structure/definition_files_missing``), and the finding mentions neither
   ``data/`` nor the connector type. The reference previously said an api-source
   closure ships "no companion artifact of any kind", which is true of the
   CONNECTOR and false of the closure the moment it lands reference data.

3. **Fetched models cannot live in ``BASE_MODELS``** once ``data/`` exists,
   because the self-check enforces ``BASE_MODELS == the data/ listing``.

Layer 1 asserts the doc teaches all three. Layer 2 executes the escape claim
against the pinned dlt, because that is the one assertion whose truth lives in
another package's code: if a dlt bump stopped collapsing ``{{`` back to ``{``,
every GraphQL closure would send doubled braces and the doc would still read
correctly.
"""

from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
API_SOURCE = (REPO_ROOT / "src" / "nxd-generate-data-product" / "reference" /
              "api-source.md")
DERIVED = (REPO_ROOT / "src" / "nxd-generate-data-product" / "reference" /
           "derived-models.md")

DLT_PIN = "dlt[duckdb]==1.28.2"
SUBPROCESS_TIMEOUT_S = 600


def _doc() -> str:
    return API_SOURCE.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Layer 1: the doc contract
# ---------------------------------------------------------------------------


def test_recipe_teaches_brace_escaping_for_a_posted_body():
    t = _doc()
    assert "A POST body is scanned for dlt expressions" in t, (
        "api-source.md must carry the POST-body expression-collision section"
    )
    assert 'replace("{", "{{").replace("}", "}}")' in t, (
        "the recipe must show the escape itself, not merely describe it"
    )
    assert "expand_placeholders" in t, (
        "the recipe must state that dlt collapses the doubled braces back "
        "before the request — without that an author 'fixes' the escape away"
    )
    head = "\n".join(t.splitlines()[:25])
    assert "escape every literal brace" in head, (
        "the escape section must appear in the ## Contents list"
    )


def test_recipe_warns_that_a_graphql_error_is_an_http_200():
    t = _doc()
    assert '{"errors": [...]}' in t and "200" in t, (
        "a GraphQL error arrives as HTTP 200 with data: null, so dlt raises "
        "nothing and the resource silently yields no rows"
    )


def test_recipe_documents_the_cursor_body_paginator():
    t = _doc()
    assert "cursor_body_path" in t and "has_more_path" in t, (
        "a Relay-style connection paginates through the POSTed body, not a "
        "query parameter"
    )


def test_recipe_requires_csv_source_path_when_the_closure_carries_data():
    t = _doc()
    assert "snapshot missing csv-source-path" in t, (
        "the supervisor's actual staging finding must be quoted — it names "
        "neither data/ nor the connector, so it is unsearchable otherwise"
    )
    assert "csv-source-path" in t and "still needs" in t
    assert "no companion artifact of any kind" not in t, (
        "that claim is false for an api closure carrying landed reference "
        "data; it is true of the connector only"
    )


def test_recipe_splits_fetched_models_out_of_base_models():
    t = _doc()
    assert "struct.base_models_vs_data_dirs" in t, (
        "the self-check finding must be quoted so it is searchable"
    )
    assert "API_MODELS" in t and "BASE_MODELS" in t and "DERIVED_MODELS" in t
    assert 'f"endpoint_{m}" in secrets' in t, (
        "the fetched set derives from API_MODELS once data/ exists"
    )


def test_recipe_pins_the_probe_against_cwd_and_empty_responses():
    t = _doc()
    assert "Path(__file__).resolve().parent" in t, (
        "a probe opening a bare relative path breaks when run by absolute "
        "path, which is how it is handed to a user"
    )
    assert "NO ROWS" in t, (
        "a reachable endpoint returning zero rows is a FAILED check; a probe "
        "that leads with OK gets read as a pass and the build is launched"
    )
    assert "eqIgnoreCase" in t, (
        "the worked instance of the trap: an exact-match-ignoring-case "
        "comparator does not match a longer display name"
    )


def test_recipe_reports_phase_b_as_not_runnable_rather_than_faked():
    t = _doc()
    assert "not runnable" in t and "check_data_product" in t, (
        "the self-check harness passes an empty secrets map, so Phase B "
        "cannot pass for this connector; the answer is to report that and "
        "verify with check_data_product, never to add a profile-reading "
        "fallback to the transform"
    )


def test_derived_models_pins_column_shape_and_the_resource_factory():
    t = DERIVED.read_text(encoding="utf-8")
    assert "all-None is DROPPED" in t, (
        "a column that is None in every row is silently omitted from the "
        "destination table, so a promised model's shape would depend on the "
        "data rather than on the closure"
    )
    assert "columns={" in t
    assert "use default_factory" in t, (
        "dlt reads a generator's parameters as configuration, so the obvious "
        "def _emit(rows=rows) raises before any row is yielded"
    )


# ---------------------------------------------------------------------------
# Layer 2: the wire — does the pinned dlt really round-trip the escape?
# ---------------------------------------------------------------------------


def test_pinned_dlt_expands_doubled_braces_back_to_the_original_query():
    """The one claim whose truth lives in dlt's code, not in ours.

    Runs in a subprocess against the pinned version so the pytest environment
    stays lean. It does NOT skip when dlt is absent: a silent skip here means
    every GraphQL closure ships an unverified escape.
    """
    program = textwrap.dedent(
        """
        import json
        from dlt.sources.rest_api.config_setup import (
            expand_placeholders, _find_expressions,
        )

        query = (
            "query PocketIssues($first: Int!, $after: String, $project: String!) {\\n"
            "  issues(first: $first, after: $after,\\n"
            "         filter: { project: { name: { eqIgnoreCase: $project } } }) {\\n"
            "    nodes { id identifier title }\\n"
            "    pageInfo { hasNextPage endCursor }\\n"
            "  }\\n"
            "}\\n"
        )
        escaped = query.replace("{", "{{").replace("}", "}}")

        body = {"query": escaped,
                "variables": {"first": 100, "after": None, "project": "P"}}
        expanded = expand_placeholders(body, {}, preserve_value_type=True)

        print(json.dumps({
            "expressions_in_escaped": sorted(_find_expressions({"query": escaped})),
            "expressions_in_raw": sorted(_find_expressions({"query": query})),
            "round_trips": expanded["query"] == query,
            "variables_preserved": expanded["variables"] == body["variables"],
        }))
        """
    )
    result = subprocess.run(
        ["uv", "run", "--quiet", "--with", DLT_PIN, "python", "-c", program],
        capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT_S,
    )
    assert result.returncode == 0, (
        f"probe failed: {result.stderr[-2000:]}"
    )
    out = json.loads(result.stdout.strip().splitlines()[-1])

    assert out["expressions_in_escaped"] == [], (
        "the escaped body must carry no dlt expressions — that is what stops "
        "rest_api_resources raising before the first request"
    )
    assert out["expressions_in_raw"], (
        "the UNESCAPED query must still trip the expression scanner; if this "
        "stops being true the whole section is describing a bug that is gone"
    )
    assert out["round_trips"], (
        "dlt must collapse {{ back to { before the request — if it stops, "
        "every GraphQL closure silently posts doubled braces"
    )
    assert out["variables_preserved"], (
        "non-string body values must survive expansion unchanged"
    )


# ---------------------------------------------------------------------------
# A key with only the key role is invisible to the querying agent
# ---------------------------------------------------------------------------


def test_recipe_requires_a_dimension_role_beside_every_primary_key():
    """Observed on the first served build of a Linear closure.

    Every model key was written `field(string(), primary_key())`, exactly as the
    worked example showed. The product built, published, and answered counts —
    and then could not answer "which tickets are P0/P1", because no query can
    group by a field that carries only the key role. The failure has no error:
    `describe_models` simply never lists the column, so the gap looks like a
    missing question rather than a missing role.
    """
    skill = (REPO_ROOT / "src" / "nxd-generate-data-product" /
             "SKILL.md").read_text(encoding="utf-8")
    assert "not groupable" in skill, (
        "SKILL.md must state that primary_key() alone is not groupable"
    )
    assert "Roles COMPOSE" in skill, (
        "the rule reads as mutually exclusive otherwise"
    )
    api = (REPO_ROOT / "src" / "nxd-generate-data-product" / "reference" /
           "nxd-spec-api.md").read_text(encoding="utf-8")
    assert "not groupable" in api and "no error" in api, (
        "the reference must carry why this is expensive to find: the product "
        "builds, publishes and answers counts, with no error anywhere"
    )

    example = (REPO_ROOT / "src" / "nxd-generate-data-product" / "reference" /
               "models-example.md").read_text(encoding="utf-8")
    assert 'field(string(), primary_key()),' not in example, (
        "the worked example must not show a bare key role — it is the shape "
        "authors copy"
    )
    assert "primary_key()," in example and "Group by this to name a customer" in example
