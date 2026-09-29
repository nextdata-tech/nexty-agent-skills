"""B9 trusted mapper bridge: ceilings, ledger projection, and grant binding.

The pure-logic tests below need no NXD checkout. Real ``field_mapper.Grant``
binding is gated behind the ``field_mapper`` marker, same as
``tests/test_grantkit.py``, and skips without ``EVAL_NXD_REPO_ROOT`` or
``EVAL_NXD_ARTIFACT_MANIFEST``.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import pytest

from dp_scenarios.grantkit import FieldMapperUnavailable, GrantKitError, grant_scope
from dp_scenarios.runner import mapper_bridge


def test_ceilings_encode_the_owner_approved_dollar_limits() -> None:
    # $3 per approval / $5 total across the session, replacing the design
    # draft's flat $20 figure (design-B9.md section 7, item 1).
    assert mapper_bridge.MAX_USD_PER_APPROVAL == Decimal("3.00")
    assert mapper_bridge.MAX_USD_SESSION == Decimal("5.00")
    assert mapper_bridge.MAPPER_MODEL == "claude-sonnet-5"
    assert mapper_bridge.MAX_CALLS == 64
    assert mapper_bridge.MAX_TOKENS == 250_000


@pytest.mark.parametrize(
    "requirements,expected",
    [
        ([{"id": "consent"}, {"id": "capture"}, {"id": "review"}, {"id": "validation"}, {"id": "mapper-confirmation-v1"}], True),
        (["consent", "capture", "review", "validation", "mapper_confirmation_v1"], True),
        ([{"id": "consent"}, {"id": "capture"}, {"id": "review"}, {"id": "validation"}], False),
        ([{"id": "consent"}, {"id": "capture"}, {"id": "review"}, {"id": "validation"}, {"id": "unrelated"}], False),
        ([{"id": "consent"}, {"id": "capture"}, {"id": "review"}, {"id": "validation"}, {"id": "mapper-confirmation-v1"}, {"id": "extra"}], False),
    ],
)
def test_five_requirement_contract_check(requirements: object, expected: bool) -> None:
    assert mapper_bridge.five_requirement_contract_satisfied(requirements) is expected


def test_mapper_ledger_snapshot_projects_a_live_inspect_run_payload() -> None:
    payload = {
        "route": "in_transform",
        "approval": {"state": "approved", "os_confirmation": True},
        "usage": {"calls": 5, "tokens": 900, "usd": 0.25},
        "grant": {"bound_capture_sha256": "sha256:" + "a" * 64},
    }
    snapshot = mapper_bridge.mapper_ledger_snapshot(payload, capture_sha256="sha256:" + "z" * 64)
    assert snapshot == {
        "schema": "nxd-eval-mapper-ledger-v1",
        "route": "in_transform_map_inputs",
        "approval": {"state": "approved", "os_confirmation": True},
        "usage": {"calls": 5, "tokens": 900, "usd": 0.25},
        "grant": {"bound_capture_sha256": "sha256:" + "a" * 64},
    }


def test_mapper_ledger_snapshot_falls_back_to_the_supplied_capture_hash() -> None:
    snapshot = mapper_bridge.mapper_ledger_snapshot({}, capture_sha256="sha256:" + "f" * 64)
    assert snapshot["grant"]["bound_capture_sha256"] == "sha256:" + "f" * 64
    assert snapshot["approval"] == {"state": None, "os_confirmation": None}
    assert snapshot["usage"] == {"calls": None, "tokens": None, "usd": None}


def test_mapper_ledger_snapshot_rejects_a_non_mapping_payload() -> None:
    with pytest.raises(ValueError):
        mapper_bridge.mapper_ledger_snapshot(["not", "a", "mapping"], capture_sha256="sha256:" + "a" * 64)  # type: ignore[arg-type]


def test_write_mapper_ledger_rejects_the_wrong_schema(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        mapper_bridge.write_mapper_ledger(tmp_path, {"schema": "wrong"})


def test_write_mapper_ledger_writes_the_exact_snapshot_atomically(tmp_path: Path) -> None:
    snapshot = mapper_bridge.mapper_ledger_snapshot(
        {
            "route": "in_transform",
            "approval": {"state": "approved", "os_confirmation": True},
            "usage": {"calls": 1, "tokens": 100, "usd": 0.05},
        },
        capture_sha256="sha256:" + "a" * 64,
    )
    path = mapper_bridge.write_mapper_ledger(tmp_path, snapshot)
    assert path == tmp_path / "mapper-ledger.json"
    assert json.loads(path.read_text(encoding="utf-8")) == snapshot


def test_mapper_grant_payload_reuses_grantkit_grant_scope() -> None:
    @dataclass(frozen=True)
    class _GrantLike:
        mapper_spec_id: str = "sha256:spec"
        provider: str = "anthropic"
        model: str = "claude-sonnet-5"
        source_path: str | None = None
        max_calls: int = 64
        max_tokens: int = 250_000
        max_usd: float = 3.0

    bound = mapper_bridge.B9MapperGrant(spec=object(), grant=_GrantLike())
    payload = mapper_bridge.mapper_grant_payload(bound)
    assert payload == grant_scope(_GrantLike())
    assert payload["max_usd"] == 3.0
    assert "source_path" not in payload


@pytest.fixture
def nxd_repo_root(monkeypatch: pytest.MonkeyPatch) -> Path:
    artifact_manifest = os.environ.get("EVAL_NXD_ARTIFACT_MANIFEST")
    if artifact_manifest:
        manifest = Path(artifact_manifest)
        if not manifest.is_file():
            pytest.skip("SKIP_FIELD_MAPPER_DEPENDENCY: set EVAL_NXD_ARTIFACT_MANIFEST to an NXD artifact manifest")
        return manifest
    configured = os.environ.get("EVAL_NXD_REPO_ROOT")
    if not configured:
        pytest.skip("SKIP_FIELD_MAPPER_DEPENDENCY: set EVAL_NXD_ARTIFACT_MANIFEST or EVAL_NXD_REPO_ROOT")
    root = Path(configured)
    if not (root / "components/nxd_py/data_product/nxd/experimental/field_mapper/__init__.py").is_file():
        pytest.skip("SKIP_FIELD_MAPPER_DEPENDENCY: set EVAL_NXD_REPO_ROOT to a compatible NXD checkout")
    monkeypatch.setenv("EVAL_NXD_REPO_ROOT", str(root))
    return root


SPEC_PATH = (
    Path(__file__).resolve().parents[1]
    / "../public/terminal-field-mapper-adapter-contract/fixtures/reference-closure/contracts/mapper_spec.json"
)


@pytest.mark.field_mapper
def test_build_b9_grant_binds_to_the_captured_spec_at_owner_ceilings(nxd_repo_root: Path) -> None:
    from dp_scenarios.grantkit.runtime import load_field_mapper

    runtime = load_field_mapper()
    raw_spec = runtime.MapperSpec.load(SPEC_PATH)
    sonnet_spec = raw_spec if raw_spec.model == mapper_bridge.MAPPER_MODEL else _with_model(raw_spec, mapper_bridge.MAPPER_MODEL)
    bound = mapper_bridge.build_b9_grant(sonnet_spec)
    assert bound.grant.model == "claude-sonnet-5"
    assert bound.grant.max_calls == 64
    assert bound.grant.max_tokens == 250_000
    assert bound.grant.max_usd == 3.0
    assert bound.grant.recurring is False
    payload = mapper_bridge.mapper_grant_payload(bound)
    assert payload["model"] == "claude-sonnet-5"
    assert payload["max_usd"] == 3.0


@pytest.mark.field_mapper
def test_build_b9_grant_rejects_the_wrong_mapper_model(nxd_repo_root: Path) -> None:
    from dp_scenarios.grantkit.runtime import load_field_mapper

    runtime = load_field_mapper()
    raw_spec = runtime.MapperSpec.load(SPEC_PATH)
    if raw_spec.model == mapper_bridge.MAPPER_MODEL:
        pytest.skip("reference fixture already uses the required model; no negative case available")
    with pytest.raises(GrantKitError):
        mapper_bridge.build_b9_grant(raw_spec)


def _with_model(spec: object, model: str) -> object:
    from dataclasses import replace

    return replace(spec, model=model)
