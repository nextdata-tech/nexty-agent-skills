"""The Linear connector reference, and the config shape it publishes.

`api-source.md` covers GraphQL over the dlt REST connector generically. What is
specific to Linear had no home until this file's subject existed, so each of
these facts was rediscovered the expensive way while building a closure that
fetched a live project and published:

* a personal key is `auth_type: api_key` with `auth_key_name: Authorization`,
  NOT `bearer` — the bearer form is rejected;
* `eqIgnoreCase` matches the whole value, so a project shown as `Nexty Pocket`
  is not matched by `pocket`, and the failure is an empty result rather than an
  error;
* open-ness is a state TYPE (`backlog`/`unstarted`/`started`), not a state name;
* list fields such as `labels { nodes { name } }` land as child tables;
* `priority` runs 1 = urgent … 4 = low with 0 meaning "not set", and 0 dominates
  real projects.

Two halves, for the same reason as `test_field_mapper_contract_drift.py`: the
doc assertions run everywhere including CI, and the one executable check needs
the pinned dlt and is skipped where it is absent.
"""

from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
REFERENCE = REPO_ROOT / "src" / "nxd-generate-data-product" / "reference"
LINEAR = REFERENCE / "linear-source.md"
API_SOURCE = REFERENCE / "api-source.md"

DLT_PIN = "dlt[duckdb]==1.28.2"
SUBPROCESS_TIMEOUT_S = 600


def _linear() -> str:
    """Whitespace-normalized: a negative assertion over raw text goes quiet the
    moment a paragraph reflows. Same reasoning as the sibling contract test."""
    return " ".join(LINEAR.read_text(encoding="utf-8").split())


# --- the doc contract -----------------------------------------------------


def test_the_reference_exists_and_is_reachable():
    assert LINEAR.is_file(), "the Linear reference must exist"
    api = API_SOURCE.read_text(encoding="utf-8")
    assert "linear-source.md" in api, (
        "nothing would ever find it: api-source.md must point at it, since that "
        "is the file an author building a REST closure actually opens"
    )
    head = "\n".join(LINEAR.read_text(encoding="utf-8").splitlines()[:20])
    assert "## Contents" in head, "progressive-disclosure references need one"


def test_auth_is_documented_as_api_key_not_bearer():
    doc = _linear()
    assert "auth_type: api_key" in doc or "`api_key`, not" in doc
    assert "auth_key_name" in doc and "Authorization" in doc
    assert "no `Bearer` prefix" in doc or "with no\n`Bearer` prefix" in _linear(), (
        "the reason api_key is right must be stated, or the next author picks "
        "bearer because the credential is a token"
    )


def test_exact_match_filter_trap_is_documented():
    doc = _linear()
    assert "eqIgnoreCase" in doc
    assert "Nexty Pocket" in doc and "pocket" in doc, (
        "show the concrete non-match; the abstract rule does not land"
    )
    assert "empty result rather than an error" in doc, (
        "the failure mode is what makes this expensive — a valid credential, a "
        "valid query, a 200, and zero rows"
    )


def test_open_is_documented_as_a_state_type():
    doc = _linear()
    for state in ("backlog", "unstarted", "started", "completed", "canceled"):
        assert state in doc, f"the closed state vocabulary must be listed: {state}"
    assert "state.name" in doc, (
        "say why type beats name — a team renaming a column must not break it"
    )


def test_list_fields_and_priority_encoding_are_documented():
    doc = _linear()
    assert "labels { nodes { name } }" in doc and "child table" in doc
    assert "state { name type }" in doc, (
        "distinguish scalar-nested (fine) from list (splits), or the rule reads "
        "as 'nesting is bad'"
    )
    # priority: the direction and the meaning of 0 are both counter-intuitive
    assert "1 is the most urgent" in doc or "Urgent" in doc
    assert "No priority set" in doc
    assert "0` as *absent*" in doc or "as *absent*" in doc


def test_zero_row_triage_is_documented():
    doc = _linear()
    assert "projects(first: 50)" in doc and "teams(first: 50)" in doc, (
        "give the queries that separate a wrong filter from a bad credential"
    )
    assert "must **not** report `OK` on a zero-row response" in doc or (
        "not** report `OK`" in doc
    ), "a probe that says OK on zero rows is how this trap gets past a human"


# --- the executable half --------------------------------------------------


def test_the_documented_config_builds_under_the_pinned_dlt():
    """The one claim whose truth lives in another package.

    The paginator paths, `cursor_body_path`, the POST body and the API-key auth
    block are published as a copyable shape; if a dlt bump stops accepting it,
    every Linear closure breaks and the doc still reads correctly. Builds the
    resource list only — no request is made, so this needs no key and no
    network beyond resolving the pin.
    """
    if not _which("uv"):
        pytest.fail(
            "uv is required to build the documented config against the pinned "
            "dlt; install uv, or run this test in CI"
        )
    program = textwrap.dedent(
        '''
        from dlt.sources.rest_api import rest_api_resources
        Q = ("query Q($first: Int!, $after: String, $project: String!) "
             "{ issues(first: $first) { nodes { id } "
             "pageInfo { hasNextPage endCursor } } }")
        cfg = {
          "client": {
              "base_url": "https://api.linear.app",
              "auth": {"type": "api_key", "name": "Authorization",
                       "api_key": "not-a-real-key", "location": "header"},
          },
          "resources": [{"name": "linear_issues_landed", "endpoint": {
              "path": "/graphql", "method": "POST",
              "json": {"query": Q.replace("{", "{{").replace("}", "}}"),
                       "variables": {"first": 100, "after": None, "project": "P"}},
              "data_selector": "data.issues.nodes",
              "paginator": {"type": "cursor",
                            "cursor_path": "data.issues.pageInfo.endCursor",
                            "cursor_body_path": "variables.after",
                            "has_more_path": "data.issues.pageInfo.hasNextPage"}}}],
        }
        print([r.name for r in rest_api_resources(cfg)])
        '''
    )
    try:
        result = subprocess.run(
            ["uv", "run", "--no-project", "--quiet", "--with", DLT_PIN,
             "python", "-c", program],
            capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        pytest.fail(f"building the config did not finish within {SUBPROCESS_TIMEOUT_S}s")
    assert result.returncode == 0, (
        f"the documented Linear config no longer builds under {DLT_PIN}: "
        f"{result.stderr[-2000:]}"
    )
    assert "linear_issues_landed" in result.stdout, (
        f"expected the resource to be built; stdout was {result.stdout!r}"
    )


def _which(binary: str) -> str | None:
    import shutil

    return shutil.which(binary)
