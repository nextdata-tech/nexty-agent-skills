"""`secrets` is ONE flat map, not a dict keyed by service name.

Ground truth is the supervisor, not the docs. In the desktop compute driver
(`components/shared/driver_impls/drivers/nxd-local-drivers/src/local_python_compute.rs`,
`prepare_execution_context`):

    data: secrets
        .iter()
        .flat_map(|handler| handler.values.clone().into_plain_iter())
        .collect(),          // -> serde_json::Map<String, Value>

Every `SecretsHandler`'s values — one service's `attributes`, keyed by the raw
attribute `key` — are flat-mapped into a SINGLE map. `SecretsHandler.service` is
discarded. The Python side hands that map straight to the transform
(`nxd/data_product/_tasks/args/compute_context.py`: `ImmediateInstance(compute_context.data)`).

So an `api-source` attribute `base_url` arrives as `secrets["base_url"]`. The
`secrets["api_source"]["base_url"]` shape the connector docs taught does not
exist at any layer, and a closure written that way raises `KeyError: 'api_source'`
at transform time — after the credential has already been resolved, so it fails
late and looks like a connector problem rather than a shape problem.

Two consequences this pins:

1. The credentialed connector docs (`api-source.md`, `database-source.md`) must
   read attribute keys directly off `secrets`.
2. Because the merge is flat, two labeled instances of the same type COLLIDE on
   any shared attribute key — `multi-source.md` must disambiguate in the
   attribute keys themselves, since the service name does not survive.

The eval harness is pinned too: it materializes a closure's `ingest` directly, so
if it passes a nested dict it grades the wrong contract and fails correct work.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REF = REPO_ROOT / "src" / "nxd-generate-data-product" / "reference"
API = REF / "api-source.md"
DB = REF / "database-source.md"
MULTI = REF / "multi-source.md"
GENERATE_SKILL = REPO_ROOT / "src" / "nxd-generate-data-product" / "SKILL.md"
# The sibling skill restates the connector keys, so it drifts independently.
DLT = REPO_ROOT / "src" / "nxd-run-job-loop" / "reference" / "dlt.md"
API_CHECKER = (REPO_ROOT / "evals" / "public" / "authenticated-api-source-build"
               / "fixtures" / "check_authenticated_api_source.py")

# Two ways to spell the same falsified read, and the two-step form is the one the
# old docs actually used — `api_secrets = secrets["api_source"]` followed by
# `api_secrets["base_url"]`. A pattern matching only the direct subscript passes
# against the very text this gate exists to rule out.
# Only the two `generic-secrets` connectors. `csv_source` / `file_source` are
# real, proven keys contributed by their own drivers — banning them here would
# fire on the CSV read that SKILL.md ships as its fully-inlined default.
NESTED = re.compile(
    r"""secrets\[["'](?:api|db)_source["']\]\["""      # secrets["api_source"]["…"]
    r"""|=\s*secrets\[["'](?:api|db)_source["']\]"""   # x = secrets["api_source"]
)


def _code_blocks(text: str) -> str:
    return "\n".join(re.findall(r"```python\n(.*?)```", text, re.DOTALL))


def test_connector_docs_have_no_nested_read_in_code():
    """Prose may quote the wrong shape to forbid it; copyable code may not."""
    for doc in (API, DB, MULTI, GENERATE_SKILL):
        code = _code_blocks(doc.read_text())
        assert not NESTED.search(code), (
            f"{doc.name}: a python block reads secrets nested by service name; "
            "the supervisor merges all services into one flat map"
        )


def test_api_doc_teaches_flat_reads():
    text = API.read_text()
    assert 'secrets["base_url"]' in text, (
        "api-source.md must read base_url directly off the flat secrets map"
    )
    # The falsified shape must be named as wrong, not silently dropped — an
    # author who has seen the old docs needs the correction to be explicit.
    assert 'never `secrets["api_source"]["base_url"]`' in text, (
        "api-source.md must explicitly rule out the nested read"
    )
    assert "KeyError: 'api_source'" in text, (
        "api-source.md must name the failure a nested read actually produces"
    )


def test_db_doc_teaches_flat_reads():
    text = DB.read_text()
    assert 'secrets["host"]' in text and 'secrets["password"]' in text, (
        "database-source.md must read connection fields directly off secrets"
    )
    assert 'never `secrets["db_source"]["host"]`' in text
    assert "KeyError: 'db_source'" in text


def test_multi_source_disambiguates_in_the_attribute_keys():
    text = MULTI.read_text()
    lowered = text.lower()
    # The collision only exists because the merge is flat; the doc has to say so,
    # because "give each service a distinct name" is the intuitive fix and it
    # does not work — the service name is discarded before the transform sees it.
    assert "collide" in lowered, (
        "multi-source.md must state that same-type instances collide on shared keys"
    )
    assert "prefix" in lowered, (
        "multi-source.md must direct labeling into the attribute keys"
    )
    for key in ("orders_host", "users_base_url"):
        assert key in text, f"multi-source.md must show a prefixed key like {key}"
    # The old per-service keys cannot come back as guidance.
    assert "`db_source_<label>`" not in text and "`api_source_<label>`" not in text, (
        "multi-source.md still advertises per-service secrets keys, which do not exist"
    )


def test_collision_is_taught_as_silent_and_authoring_time():
    text = MULTI.read_text()
    lowered = text.lower()
    # The danger is not that it errors — it is that it does not. A doc that says
    # "keys must be unique" without saying the loser vanishes leaves the reader
    # expecting a runtime complaint that never comes.
    assert "silently" in lowered or "silent" in lowered, (
        "multi-source.md must say a key collision fails silently"
    )
    assert "authoring-time check" in lowered, (
        "multi-source.md must place the collision check at authoring time, "
        "since nothing detects it at runtime"
    )
    # Renaming services is the intuitive fix and it does not work.
    assert "does not help" in lowered, (
        "multi-source.md must rule out renaming the services as the fix"
    )
    # Mixed-type collisions, not just two of the same type.
    assert "mixed types" in lowered, (
        "multi-source.md must cover collisions between different connector types"
    )


def test_each_credentialed_connector_doc_points_at_the_collision_rule():
    """A builder reads one connector doc, not the whole reference set."""
    for doc in (API, DB):
        text = doc.read_text()
        lowered = text.lower()
        assert "collision" in lowered, (
            f"{doc.name} must warn about key collisions across services"
        )
        assert "multi-source.md" in text, (
            f"{doc.name} must point at the full collision rule"
        )


def test_generate_skill_table_does_not_advertise_service_keyed_secrets():
    text = GENERATE_SKILL.read_text()
    # The Overview table is what a builder reads first; it must not hand back the
    # falsified keys for the two credentialed connectors.
    assert "| `db_source` |" not in text and "| `api_source` |" not in text, (
        "the connector-types table must not list per-service secrets keys for db/api"
    )


def test_no_doc_routes_labeled_instances_to_a_per_service_key():
    """The first gate checked only multi-source.md, so the same falsified keys
    survived in the two connector docs that point *at* it."""
    for doc in (API, DB, MULTI, GENERATE_SKILL, DLT):
        text = doc.read_text()
        for dead in ("api_source_<label>", "db_source_<label>"):
            assert dead not in text, (
                f"{doc.name} still routes labeled instances to secrets[\"{dead}\"], "
                "which does not exist under a flat merge"
            )


def test_worked_example_profile_prefixes_its_keys():
    """The YAML a reader copies must match the transform printed beneath it."""
    text = MULTI.read_text()
    yaml_blocks = "\n".join(re.findall(r"```yaml\n(.*?)```", text, re.DOTALL))
    assert "key: orders_host" in yaml_blocks, (
        "the two-database example's profile must carry label-prefixed keys; "
        "unprefixed, the example collides with itself and the transform's "
        "prefix-strip yields an empty dict"
    )
    assert "- key: host\n" not in yaml_blocks, (
        "the two-database example still declares a bare `host` key"
    )


def test_db_probe_redaction_is_not_a_fixed_key_list():
    """Under prefixing, ("password", "user") matches nothing — and a redactor
    that matches nothing is indistinguishable from no redactor at all."""
    code = _code_blocks(DB.read_text())
    assert 'for value in secrets.values():' in code, (
        "database-source.md's _redact must substitute every value in the flat map"
    )
    assert 'for key in ("password", "user")' not in code, (
        "database-source.md's _redact still keys on unprefixed field names, so it "
        "silently redacts nothing and a failed probe leaks the live password"
    )


def test_judge_rubrics_do_not_require_the_nested_read():
    """The deterministic checker and the judge grade the same closure. If the
    rubric still demands secrets['api_source'], corrected work passes one and
    fails the other."""
    for rel in ("authenticated-api-source-build", "worldbank-live"):
        path = REPO_ROOT / "evals" / "public" / rel / "checks.json"
        raw = path.read_text()
        for demand in ("read from secrets['api_source']", 'read from secrets[\\"api_source\\"]'):
            assert demand not in raw, (
                f"{rel}/checks.json still instructs the judge to require the "
                "nested read"
            )


def test_eval_harness_materializes_with_a_flat_secrets_dict():
    """The checker runs the closure's own ingest(); its secrets shape IS the graded
    contract. A nested dict here fails closures that follow the corrected docs."""
    text = API_CHECKER.read_text()
    assert 'ingest(duckdb=out, secrets=secrets)' in text, (
        "the api-source checker must invoke ingest with the flat secrets map"
    )
    assert 'secrets={"api_source"' not in text, (
        "the api-source checker still nests secrets under a service name"
    )
