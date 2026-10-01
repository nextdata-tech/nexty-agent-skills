"""Local-mesh runner opt-in, workspace boundary, and isolated NXD_HOME tests."""

from __future__ import annotations

import importlib.util
import json
import os
import ssl
import stat
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
EVALS = ROOT / "evals"


def _load_run():
    if str(EVALS) not in sys.path:
        sys.path.insert(0, str(EVALS))
    spec = importlib.util.spec_from_file_location("_local_mesh_eval_run", EVALS / "run.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("_local_mesh_eval_run", module)
    spec.loader.exec_module(module)
    return module


run = _load_run()


def _mesh_spec():
    return {
        "mesh": "local",
        "dp": "eval-provider-enrollment",
        "api_url": "https://nxd.nxd.local/api",
        "app_url": "https://nxd.nxd.local/app",
    }


def test_mesh_marker_parses_local_mesh_contract(tmp_path: Path) -> None:
    scenario = tmp_path / "scenario"
    fixtures = scenario / "fixtures"
    fixtures.mkdir(parents=True)
    (fixtures / "mesh.json").write_text(json.dumps(_mesh_spec()), encoding="utf-8")

    assert run.scenario_needs_mesh(scenario) == _mesh_spec()


@pytest.mark.parametrize(
    "marker",
    [
        {"mesh": "remote", "dp": "dp", "api_url": "https://mesh/api", "app_url": "https://mesh/app"},
        {"mesh": "local", "api_url": "https://mesh/api", "app_url": "https://mesh/app"},
    ],
)
def test_mesh_marker_rejects_unsupported_or_incomplete_shapes(tmp_path: Path, marker: dict) -> None:
    scenario = tmp_path / "scenario"
    fixtures = scenario / "fixtures"
    fixtures.mkdir(parents=True)
    (fixtures / "mesh.json").write_text(json.dumps(marker), encoding="utf-8")

    with pytest.raises(run.LocalMeshSetupError):
        run.scenario_needs_mesh(scenario)


def test_mesh_marker_is_not_copied_to_agent_workspace(tmp_path: Path) -> None:
    scenario = ROOT / "evals" / "public" / "semantic-filter-coverage"
    ws, _ = run.build_workspace(
        tmp_path,
        run.SkillSet(name="no_skills", description="", skills=[]),
        scenario,
    )

    assert (scenario / "fixtures" / "mesh.json").is_file()
    assert not (ws / "mesh.json").exists()
    assert "mesh.json" in run.workspace_fixture_exclusions(scenario.name)


def test_nxd_home_preparation_uses_only_operator_token_and_private_file(tmp_path: Path) -> None:
    nxd_home = tmp_path / "isolated-nxd-home"
    token = "nxdpat_synthetic-unit-test-token"
    run.prepare_local_mesh_nxd_home(nxd_home, _mesh_spec(), token)

    registry = json.loads((nxd_home / "meshes.json").read_text(encoding="utf-8"))
    active_config = (nxd_home / "config.yaml").read_text(encoding="utf-8")
    tokens = json.loads((nxd_home / "tokens.json").read_text(encoding="utf-8"))
    assert registry["local"]["api_url"] == "https://nxd.nxd.local/api"
    assert registry["local"]["app_url"] == "https://nxd.nxd.local/app"
    assert token not in json.dumps(registry)
    assert 'url: "https://nxd.nxd.local/api"' in active_config
    assert tokens == {"nxd.nxd.local": {"access_token": token}}
    assert stat.S_IMODE(os.stat(nxd_home / "tokens.json").st_mode) == 0o600


def test_local_gateway_url_is_derived_from_api_url() -> None:
    assert run._local_mesh_gateway_url("https://nxd.nxd.local/api") == (
        "https://nxd.nxd.local/dp/mcp/"
    )


def test_agent_environment_does_not_duplicate_operator_pat(monkeypatch, tmp_path: Path) -> None:
    token = "nxdpat_synthetic-unit-test-token"
    monkeypatch.setenv("EVAL_MESH_TOKEN", token)

    agent_env = run._local_mesh_agent_environment(tmp_path / "isolated-nxd-home")

    assert agent_env["NXD_HOME"] == str(tmp_path / "isolated-nxd-home")
    assert agent_env["EVAL_MESH_TOKEN"] == ""
    assert token not in agent_env.values()


def test_local_ca_masks_inherited_insecure_tls_flag_for_agent(monkeypatch, tmp_path: Path) -> None:
    ca_bundle = tmp_path / "local-mesh-ca.pem"
    ca_bundle.write_text("synthetic test CA path", encoding="utf-8")
    monkeypatch.setenv("NXD_MCP_INSECURE", "1")
    monkeypatch.setenv("NXD_CA_BUNDLE", str(ca_bundle))

    agent_env = run._local_mesh_agent_environment(tmp_path / "isolated-nxd-home")

    assert agent_env["NXD_MCP_INSECURE"] == ""


def test_mesh_tls_uses_ca_bundle_before_explicit_insecure_opt_out(monkeypatch, tmp_path: Path) -> None:
    ca_bundle = tmp_path / "local-mesh-ca.pem"
    ca_bundle.write_text("synthetic test CA path", encoding="utf-8")
    calls: list[dict] = []
    monkeypatch.setattr(
        ssl,
        "create_default_context",
        lambda **kwargs: calls.append(kwargs) or ("verified", kwargs),
    )
    monkeypatch.setattr(ssl, "_create_unverified_context", lambda: "unverified")
    monkeypatch.setenv("NXD_MCP_INSECURE", "1")
    monkeypatch.setenv("NXD_CA_BUNDLE", str(ca_bundle))

    assert run._local_mesh_ssl_context() == ("verified", {"cafile": str(ca_bundle)})
    assert calls == [{"cafile": str(ca_bundle)}]

    monkeypatch.delenv("NXD_CA_BUNDLE")
    assert run._local_mesh_ssl_context() == "unverified"


def test_mesh_pat_is_added_to_artifact_redaction_values(monkeypatch) -> None:
    token = "nxdpat_synthetic-unit-test-token"
    monkeypatch.setenv("EVAL_MESH_TOKEN", token)

    secrets = run._runtime_redaction_values(
        ("fixture-secret",), ("configured-marker",), _mesh_spec()
    )
    trace, metrics, leaked = run._redact_agent_artifacts(
        f"[assistant] accidental token: {token}", {"output": token}, secrets
    )

    assert secrets == ("fixture-secret", "configured-marker", token)
    assert leaked is True
    assert token not in trace
    assert token not in json.dumps(metrics)
    assert "<redacted>" in trace


def test_mesh_tls_verifies_certificates_by_default(monkeypatch) -> None:
    calls: list[dict] = []
    monkeypatch.setattr(
        ssl,
        "create_default_context",
        lambda **kwargs: calls.append(kwargs) or ("verified", kwargs),
    )
    monkeypatch.setattr(ssl, "_create_unverified_context", lambda: "unverified")
    monkeypatch.delenv("NXD_MCP_INSECURE", raising=False)
    for name in ("REQUESTS_CA_BUNDLE", "SSL_CERT_FILE", "NXD_CA_BUNDLE"):
        monkeypatch.delenv(name, raising=False)

    assert run._local_mesh_ssl_context() == ("verified", {})
    assert calls == [{}]
