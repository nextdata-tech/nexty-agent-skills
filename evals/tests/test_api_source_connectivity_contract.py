"""Pin the authenticated API connectivity-probe contract.

The offline ``self_check.py`` Phase-B limitation must not be misread as
permission to skip the separate authenticated smoke probe when credentials are
available. These text-level checks are the carrying guard for that distinction
and deliberately fail against the old, ambiguous wording.
"""

from __future__ import annotations

from pathlib import Path


API_SOURCE = (Path(__file__).parents[1] / ".." / "src" /
              "nxd-generate-data-product" / "reference" / "api-source.md").resolve()
SKILL_SOURCE = API_SOURCE.parents[1] / "SKILL.md"
MULTI_SOURCE = API_SOURCE.parents[1] / "reference" / "multi-source.md"
SOURCE_TYPES = API_SOURCE.parents[1] / "reference" / "source-types.md"


def _doc() -> str:
    return API_SOURCE.read_text(encoding="utf-8")


def _normalized(text: str) -> str:
    return " ".join(text.split()).casefold()


def _self_check_contract() -> str:
    """Return normalized prose from the self-check section only."""

    section = _doc().split("## Self-check (connectivity smoke test)", 1)[1]
    return _normalized(section)


def _payload_gate_contract() -> str:
    """Return the one canonical, top-level payload-inspection gate."""

    document = _doc()
    section = document.split("\n## Payload inspection gate — before authoring", 1)[1]
    return _normalized(section.split("\n## ", 1)[0])


def test_closure_artifacts_share_one_normalized_root():
    skill = _normalized(SKILL_SOURCE.read_text(encoding="utf-8"))
    api = _normalized(_doc().split("## Closure root", 1)[1].split("## Scope", 1)[0])

    assert "before authoring any artifact" in skill
    assert "every closure artifact must be inside `<dp-root>`" in skill
    assert "root-level artifacts are direct children" in skill
    assert "connector-specific artifacts such as `connectivity_check.py` for api sources" in skill
    for artifact in (
        "spec.py",
        "models.py",
        "transform/",
        "requirements.txt",
        "infra-profile.yaml",
        "connectivity_check.py",
        ".gitignore",
        "sensitive",
    ):
        assert artifact in skill
        assert artifact in api
    assert "normalize existing artifacts into it" in api
    assert "inside that root: root-level artifacts are direct children" in api
    assert "do not place credentials" in api
    assert "same root for the self-check, lock, and build" in api


def test_authenticated_probe_is_named_local_and_dependency_light():
    contract = _self_check_contract()
    assert "connectivity_check.py" in contract
    assert "closure-local `connectivity_check.py` written first under the gate above" in contract
    assert "one bounded request per configured resource" in contract
    assert "apply the redaction rules below to every failure message" in contract


def test_payload_inspection_covers_every_resource_before_authoring():
    contract = _payload_gate_contract()
    assert "first closure artifact after" in contract
    assert "closure-local `connectivity_check.py`" in contract
    assert "non-secret resource list, endpoint paths, expected row-array selectors" in contract
    assert "independent of nxd, dlt, duckdb, and the generated transform" in contract
    assert "one bounded, read-only request per configured resource" in contract
    assert "actual resolved base url and endpoint path" in contract
    assert "assert a parseable response matching the expected shape" in contract
    assert "print a bounded, sanitized summary for **each** resource" in contract
    assert "before it exits successfully" in contract
    assert "values may be shown only when they are clearly non-sensitive and non-personal scalars" in contract
    assert "secret-like response fields (`token`, `secret`, `password`, `api_key`" in contract
    assert "personal or account data are represented only by their field name and type" in contract
    assert "a `<redacted>` placeholder" in contract
    assert "redact or omit authorization headers, bearer/api-key values, cookies" in contract
    assert "redact or omit authorization headers, bearer/api-key values, cookies, secret query parameters, and full response bodies" in contract
    assert "a failed or uninspectable resource must produce a bounded diagnostic and stop authoring" in contract


def test_payload_gate_is_top_level_and_not_duplicated():
    document = _doc()
    assert document.count("## Payload inspection gate — before authoring") == 1
    assert "#### Payload inspection gate — before authoring" not in document
    assert "- Payload inspection gate — before authoring" in document.split("## Contents", 1)[1]
    assert "After this gate, inspect each response before authoring" not in document


def test_every_api_inventory_requires_probe_and_names_missing_endpoint_companion():
    skill = _normalized(SKILL_SOURCE.read_text(encoding="utf-8"))
    api = _normalized(_doc())
    multi = _normalized(MULTI_SOURCE.read_text(encoding="utf-8"))
    source_types = _normalized(SOURCE_TYPES.read_text(encoding="utf-8"))

    # The source-types index owns the connector matrix; the generator skill
    # links to it instead of duplicating the table.
    assert "[source types index](reference/source-types.md) for the canonical source matrix" in skill
    assert "**connector types at a glance**" not in skill
    assert "| csv (proven, fully-inlined default below) | `csv-source` |" not in skill
    assert "| source type | service | companion artifact | detailed recipe |" in source_types
    assert "| rest api | `api-source` | `connectivity_check.py`; endpoint attributes | [api source](api-source.md) |" in source_types
    assert "for `api-source`, additionally require the closure-local `connectivity_check.py` probe; only its endpoint-map companion is absent" in skill
    assert "`connectivity_check.py` for `api-source`" in skill
    assert "for `api-source`, the endpoint-map companion is absent because its map is carried by `endpoint_<model>` profile attributes; the connectivity probe is still required" in skill

    # The source recipe and multi-source projection must agree for both the
    # single and labeled API shapes.
    assert "**required probe; no endpoint-map companion** — every api-source closure" in api
    assert "includes the closure-local `connectivity_check.py` probe" in api
    assert "one api (unchanged) | `api-source` | the attribute keys — `base_url`, `endpoint_<model>`, … | required `connectivity_check.py`; no endpoint-map companion" in multi
    assert "2+ apis, labeled | `api-source-<label>` | `<label>_<attr>` — `orders_base_url`, `orders_endpoint_<model>`, … | required closure-local `connectivity_check.py`; no endpoint-map companion" in multi


def test_missing_credentials_allow_structural_authoring_without_validation_claim():
    contract = _payload_gate_contract()
    assert "if credentials are unavailable in-session, author the probe and then continue authoring the remaining closure from the settled plan" in contract
    assert "mark **both** payload inspection and the connectivity self-check as **not run** and **unverified**" in contract
    assert "this is not source validation" in contract
    assert "is not a complete happy path" in contract
    assert "leave the closure incomplete until a later credentialed probe succeeds" in contract
    assert "do not manufacture a response summary from api docs, fixtures, or assumptions" in contract


def test_api_closure_requires_dependency_light_probe_success():
    skill = _normalized(SKILL_SOURCE.read_text(encoding="utf-8"))
    assert "write the closure-local `connectivity_check.py` first **after**" in skill
    assert "the operator's explicit approval has been relayed through `session_decision`" in skill
    assert "first post-consent closure artifact, not a pre-consent exception" in skill
    assert "payload-inspection gate described in" in skill
    assert "payload inspection and connectivity are then **not run** and **unverified**" in skill
    assert "source validation and the complete happy path must not be claimed" in skill


def test_final_closure_invariant_requires_api_connectivity_probe():
    skill = _normalized(SKILL_SOURCE.read_text(encoding="utf-8"))
    invariant = skill.split("## invariants — never violate these", 1)[1]
    assert "for `api-source`, additionally require the closure-local `connectivity_check.py` probe" in invariant
    assert "only its endpoint-map companion is absent" in invariant

    api = _normalized(_doc())
    assert "missing nxd, dlt, duckdb, or generated-transform packages do not excuse it" in api
    assert "the closure is complete only after that authenticated probe succeeds" in api
    assert "manual `curl`" in api


def test_credentials_available_require_real_probe_execution():
    contract = _self_check_contract()
    assert "closure-local `connectivity_check.py` written first under the gate above" in contract
    assert "with credentials it must run successfully before the first build" in contract
    assert "manually issued `curl`" in contract
    assert "does **not** substitute for executing the closure-local probe" in contract
    gate = _payload_gate_contract()
    assert "if credentials are unavailable in-session" in gate
    assert "connectivity self-check as **not run** and **unverified**" in gate


def test_offline_phase_b_is_distinct_from_authenticated_probe():
    contract = _self_check_contract()
    assert "do not confuse that offline limitation" in contract
    assert "phase b of `self_check.py` cannot pass" in contract
    assert "authenticated `connectivity_check.py`" in contract
