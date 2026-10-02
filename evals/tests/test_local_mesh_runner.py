"""Local-mesh runner opt-in, workspace boundary, and isolated NXD_HOME tests."""

from __future__ import annotations

import importlib.util
import json
import os
import ssl
import stat
import sys
import shutil
import subprocess
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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


class _UpstreamHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
        method = body.get("method")
        if method == "notifications/initialized":
            self.send_response(202)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if method == "initialize":
            payload = {"jsonrpc": "2.0", "id": body.get("id"), "result": {"protocolVersion": "2025-06-18", "capabilities": {}, "serverInfo": {"name": "fixture", "version": "1"}}}
            self.send_response(200)
            self.send_header("Mcp-Session-Id", "upstream-session")
        elif method == "tools/list":
            payload = {"jsonrpc": "2.0", "id": body.get("id"), "result": {"tools": [{"name": "run_semantic_query", "description": "query fixture"}]}}
            self.send_response(200)
        elif method == "tools/call":
            assert self.headers.get("Mcp-Session-Id") == "upstream-session"
            assert body["params"]["name"] == "run_semantic_query"
            payload = {"jsonrpc": "2.0", "id": body.get("id"), "result": {"structuredContent": {"fixture_call": body["params"]["arguments"]}}}
            self.send_response(200)
        else:
            payload = {"jsonrpc": "2.0", "id": body.get("id"), "result": {}}
            self.send_response(200)
        raw = json.dumps(payload).encode()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, _format, *_args):
        return


def _serve(handler):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _load_fake_gateway():
    path = EVALS / "mcp" / "fake_mesh_gateway.py"
    spec = importlib.util.spec_from_file_location("_eval_fake_mesh_gateway", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


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


def test_local_mesh_runtime_scopes_tmpdir_to_the_cell(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("EVAL_MESH_TOKEN", "nxdpat_synthetic-unit-test-token")
    monkeypatch.setattr(run, "list_local_mesh_tools", lambda *_args: [])
    monkeypatch.setattr(run, "_check_local_mesh_tools", lambda *_args: None)

    with run.local_mesh_runtime(_mesh_spec(), tmp_path) as env:
        assert Path(env["TMPDIR"]) == tmp_path / "tmp"
        assert Path(env["TMPDIR"]).is_dir()


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


def test_mcp_http_allows_only_opted_in_loopback_http(monkeypatch) -> None:
    path = ROOT / "src" / "nxd-query-data-product" / "scripts" / "mcp_http.py"
    spec = importlib.util.spec_from_file_location("_eval_mcp_http", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    monkeypatch.setenv("NXD_MCP_ALLOW_HTTP_LOCALHOST", "1")
    assert module.normalise_endpoint("http://127.0.0.1:8765/dp/mcp") == "http://127.0.0.1:8765/dp/mcp/"
    assert module.normalise_endpoint("http://example.test/dp/mcp") == "https://example.test/dp/mcp/"
    assert module.normalise_endpoint("http://localhost:8765/dp/mcp") == "https://localhost:8765/dp/mcp/"
    assert module.normalise_endpoint("http://[::1]:8765/dp/mcp") == "http://[::1]:8765/dp/mcp/"

    monkeypatch.delenv("NXD_MCP_ALLOW_HTTP_LOCALHOST")
    assert module.normalise_endpoint("http://127.0.0.1:8765/dp/mcp") == "https://127.0.0.1:8765/dp/mcp/"


def test_semantic_gateway_auth_namespaces_and_forwards_and_resolves_mesh(tmp_path: Path) -> None:
    gateway_module = _load_fake_gateway()
    Gateway, make_handler = gateway_module.Gateway, gateway_module.make_handler

    upstream, upstream_thread = _serve(_UpstreamHandler)
    token = "nxdpat_gateway-test-token"
    gateway = Gateway(f"http://127.0.0.1:{upstream.server_port}/dp/rpcs/mcp-api/mcp/", token, "fixture-dp")
    proxy, proxy_thread = _serve(make_handler(gateway, "/dp/mcp/"))
    try:
        endpoint = f"http://127.0.0.1:{proxy.server_port}/dp/mcp/"
        # Missing and wrong PATs are rejected before forwarding.
        for headers, expected in (({}, 401), ({"X-Nextdata-Token": "wrong"}, 403)):
            request = urllib.request.Request(endpoint, data=b"{}", headers=headers, method="POST")
            with pytest.raises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(request, timeout=3)
            assert error.value.code == expected
            assert error.value.read() == b""

        nxd_home = tmp_path / "nxd-home"
        mesh_spec = {
            "mesh": "local", "dp": "fixture-dp",
            "api_url": f"http://127.0.0.1:{proxy.server_port}/api",
            "app_url": f"http://127.0.0.1:{proxy.server_port}/app",
        }
        run.prepare_local_mesh_nxd_home(nxd_home, mesh_spec, token)
        agent_env = run._local_mesh_agent_environment(nxd_home)
        assert token not in agent_env.values()
        assert agent_env["NXD_HOME"] == str(nxd_home)

        scripts = ROOT / "src" / "nxd-query-data-product" / "scripts"
        env = {**os.environ, **agent_env, "NXD_MCP_ALLOW_HTTP_LOCALHOST": "1", "PYTHONPATH": str(scripts)}
        found = subprocess.run(
            [sys.executable, str(scripts / "find_mesh.py"), "--mesh", "local"],
            env=env, text=True, capture_output=True, check=True, timeout=10,
        )
        discovery = json.loads(found.stdout)
        assert discovery["api_url"] == mesh_spec["api_url"]
        assert discovery["mesh_name"] == "local"
        assert discovery["token_available"] is True

        token_file = tmp_path / "token.txt"
        token_file.write_text(token, encoding="utf-8")
        tools = subprocess.run(
            [sys.executable, str(scripts / "gateway_tools.py"), "tools", "--dp", "fixture-dp",
             "--token-file", str(token_file)],
            env=env, text=True, capture_output=True, check=True, timeout=10,
        )
        grouped = json.loads(tools.stdout)
        listed = next(iter(grouped["per_dp_tool_groups"].values()))[0]
        assert listed["wire_name"].startswith("run_semantic_query__")
        suffix = listed["wire_name"].rsplit("__", 1)[1]
        assert len(suffix) == 10
        assert all(character in "abcdefghijklmnopqrstuvwxyz234567" for character in suffix)
        assert listed["description"].startswith("(data product: fixture-dp, port: mcp-api)")

        output = tmp_path / "call.json"
        called = subprocess.run(
            [sys.executable, str(scripts / "mcp_call.py"), "--endpoint", endpoint,
             "--tool", listed["wire_name"], "--args", '{"measures":["m"]}',
             "--token-file", str(token_file), "--out", str(output)],
            env=env, text=True, capture_output=True, check=True, timeout=10,
        )
        assert json.loads(output.read_text(encoding="utf-8")) == {
            "fixture_call": {"measures": ["m"]}
        }
        unknown = subprocess.run(
            [sys.executable, str(scripts / "mcp_call.py"), "--endpoint", endpoint,
             "--tool", "unknown_tool__aaaaaaaaaa", "--token-file", str(token_file),
             "--out", str(tmp_path / "unknown.json")],
            env=env, text=True, capture_output=True, timeout=10,
        )
        assert unknown.returncode != 0
        assert "MCP error -32601" in unknown.stderr
    finally:
        proxy.shutdown()
        upstream.shutdown()
        proxy.server_close()
        upstream.server_close()
        proxy_thread.join(timeout=2)
        upstream_thread.join(timeout=2)


def test_semantic_server_gateway_tools_smoke_without_snowflake(
    tmp_path: Path,
) -> None:
    command, base_args = run._mcp_python()
    if shutil.which(command) is None and not Path(command).is_file():
        pytest.skip(f"matched semantic MCP interpreter is unavailable: {command}")
    interpreter = [command, *base_args]
    interpreter_probe = subprocess.run(
        [*interpreter, "-c", "import sys; print(sys.executable)"],
        cwd=run.MCP_DIR, text=True, capture_output=True, timeout=30,
    )
    if interpreter_probe.returncode and command == "uv" and "No version is set for command uv" in interpreter_probe.stderr:
        pytest.skip("uv has no selected runtime in this checkout; set EVAL_MCP_PYTHON or configure uv")
    if interpreter_probe.returncode:
        pytest.fail(f"matched semantic MCP interpreter could not start: {interpreter_probe.stderr.strip()[-500:]}")
    nxd_available = subprocess.run(
        [*interpreter, "-c", "import nxd.experimental.semantic"],
        cwd=run.MCP_DIR, text=True, capture_output=True, timeout=30,
    )
    missing_root_nxd = (
        nxd_available.returncode != 0
        and "No module named 'nxd'" in nxd_available.stderr
    )
    explicit_interpreter = bool(os.environ.get("EVAL_MCP_PYTHON", "").strip())
    if missing_root_nxd and not explicit_interpreter:
        pytest.skip(
            "default semantic MCP interpreter lacks the private nxd wheel; "
            "install the matched wheel set or set EVAL_MCP_PYTHON to run this smoke test"
        )
    if nxd_available.returncode:
        pytest.fail(
            "semantic MCP interpreter is present but nxd.experimental.semantic "
            f"is unavailable: {nxd_available.stderr.strip()[-500:]}"
        )
    available = subprocess.run(
        [*interpreter, "-c", "import mcp, snowflake.connector, typing_extensions"],
        cwd=run.MCP_DIR, text=True, capture_output=True, timeout=30,
    )
    if available.returncode:
        pytest.fail(
            "matched semantic MCP interpreter is present but its declared server "
            f"dependencies are unavailable: {available.stderr.strip()[-500:]}"
        )
    scenario = ROOT / "evals" / "public" / "semantic-intent-validation"
    mcp_spec = run.scenario_needs_mcp(scenario)
    token = "nxdpat_semantic-smoke-test-token"
    scripts = ROOT / "src" / "nxd-query-data-product" / "scripts"
    token_file = tmp_path / "gateway-token.txt"
    token_file.write_text(token, encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(scripts)}
    with run.semantic_http_server(scenario, mcp_spec, token, tmp_path) as (endpoint, env_over):
        assert Path(env_over["TMPDIR"]) == tmp_path / "tmp"
        script_env = {**env, **env_over}

        def run_script(script: str, *args: str) -> subprocess.CompletedProcess:
            return subprocess.run(
                [*interpreter, str(scripts / script), *args], env=script_env,
                cwd=run.MCP_DIR, text=True, capture_output=True, check=True, timeout=30,
            )

        listed = json.loads(run_script(
            "gateway_tools.py", "list-dps", "--endpoint", endpoint,
            "--token-file", str(token_file),
        ).stdout)
        assert isinstance(listed["data_products"], str)
        listed_products = json.loads(listed["data_products"])
        assert listed["count"] == listed["total_count"] == 1
        assert listed_products == [{
            "name": mcp_spec["dp"], "domain": None, "description": None,
            "status": None, "endpoint": None, "access_stats": None,
            "promise_stats": None,
        }]

        details = json.loads(run_script(
            "gateway_tools.py", "details", "--dp", mcp_spec["dp"], "--models",
            "--endpoint", endpoint, "--token-file", str(token_file),
        ).stdout)
        assert details["data_products"][0]["fullName"] == mcp_spec["dp"]
        assert details["data_products"][0]["name"] == mcp_spec["dp"]
        semantic_models = details["data_products"][0]["semanticModels"]
        assert semantic_models["models"]
        assert semantic_models["dataProductGlossaryLinks"] is None

        details_without_models = json.loads(run_script(
            "gateway_tools.py", "details", "--dp", mcp_spec["dp"],
            "--endpoint", endpoint, "--token-file", str(token_file),
        ).stdout)
        assert "semanticModels" not in details_without_models["data_products"][0]

        unknown_details = json.loads(run_script(
            "gateway_tools.py", "details", "--dp", "unknown-dp", "--models",
            "--endpoint", endpoint, "--token-file", str(token_file),
        ).stdout)
        assert unknown_details == {"data_products": []}

        grouped = json.loads(run_script(
            "gateway_tools.py", "tools", "--dp", mcp_spec["dp"],
            "--endpoint", endpoint, "--token-file", str(token_file),
        ).stdout)
        groups = grouped["per_dp_tool_groups"]
        listed_tools = [tool for group in groups.values() for tool in group]
        semantic_tools = {tool["function"] for tool in listed_tools}
        assert semantic_tools >= {"list_models", "describe_model", "run_semantic_query"}
        assert all(f"port: {mcp_spec['rpc_port']}" in tool["description"] for tool in listed_tools)

        list_models = next(tool["wire_name"] for tool in listed_tools if tool["function"] == "list_models")
        output = tmp_path / "list-models.json"
        called = json.loads(run_script(
            "mcp_call.py", "--endpoint", endpoint, "--tool", list_models,
            "--token-file", str(token_file), "--out", str(output),
        ).stdout)
        assert called["is_error"] is False
        assert json.loads(output.read_text(encoding="utf-8"))


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
