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


def _doc() -> str:
    return API_SOURCE.read_text(encoding="utf-8")


def _normalized(text: str) -> str:
    return " ".join(text.split()).casefold()


def _self_check_contract() -> str:
    """Return normalized prose from the self-check section only."""

    section = _doc().split("## Self-check (connectivity smoke test)", 1)[1]
    return _normalized(section)


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
    assert "at the closure root" in contract
    assert "beside `infra-profile.yaml` and `transform/`" in contract
    assert (
        "independent of nxd, dlt, duckdb, and the generated transform"
        in contract
    )
    assert "one bounded request per configured resource" in contract
    assert "apply the redaction rules below to every failure message" in contract


def test_payload_inspection_covers_every_resource_before_authoring():
    contract = _normalized(_doc())
    assert "enumerate **every** api resource/endpoint" in contract
    assert "inspect one real response from each one" in contract
    assert "a status code, api documentation" in contract
    assert "print a bounded, sanitized summary for **each** resource" in contract
    assert "the summary must be visible in the session output before the first closure write" in contract
    assert "values may be shown only when they are clearly non-sensitive and non-personal scalars" in contract
    assert "secret-like response fields (`token`, `secret`, `password`, `api_key`" in contract
    assert "for any personal or account data" in contract
    assert "show only the field name and type or a `<redacted>` placeholder" in contract
    assert "redact or omit authorization headers, bearer/api-key values, cookies" in contract
    assert "secret-like response fields, personal data, and full response bodies" in contract
    assert "stop with a bounded diagnostic rather than authoring a guessed schema" in contract


def test_credentials_available_require_real_probe_execution():
    contract = _self_check_contract()
    assert "execute `python3 connectivity_check.py`" in contract
    assert "before the first build" in contract
    assert "manually issued `curl`" in contract
    assert "does **not** substitute for executing the closure-local probe" in contract
    assert "when credentials are not available in-session" in contract
    assert "connectivity self-check as **not run**" in contract


def test_offline_phase_b_is_distinct_from_authenticated_probe():
    contract = _self_check_contract()
    assert "do not confuse that offline limitation" in contract
    assert "phase b of `self_check.py` cannot pass" in contract
    assert "authenticated `connectivity_check.py`" in contract
