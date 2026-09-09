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


def _doc() -> str:
    return API_SOURCE.read_text(encoding="utf-8")


def _self_check_contract() -> str:
    """Return normalized prose from the self-check section only."""

    section = _doc().split("## Self-check (connectivity smoke test)", 1)[1]
    return " ".join(section.split()).casefold()


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
