"""Pin the static release artifact contract and Pocket lifecycle ordering."""
from __future__ import annotations

from pathlib import Path
import importlib.util
import json
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT = ROOT / "src" / "nxd-dp-static-artifact"
POCKET = ROOT / "src" / "nxd-pocket-loop"
SCENARIO = ROOT / "evals" / "public" / "dp-static-artifact-lifecycle"


def test_renamed_static_skill_is_the_only_shipped_identity():
    assert ARTIFACT.is_dir()
    assert not (ROOT / "src" / ("nxd-" + "artifact")).exists()
    text = (ARTIFACT / "SKILL.md").read_text()
    assert "name: nxd-dp-static-artifact" in text
    assert "version: 0.25.1" in text
    assert "inline" not in text.lower()
    assert "\n## Catalog" not in text and "\n## Query" not in text


def test_static_artifact_fails_closed_and_validates_the_complete_contract():
    text = (ARTIFACT / "SKILL.md").read_text()
    required = (
        "current", "verified.json", "outputs", "schema: nxd-desktop-verified-v1",
        "artifact_verified", "list_data_products", "fail the whole artifact",
        "data_model", "unannotated", "complex", "roles as a set", "joins",
        "ports[].model_names", "promises", "Release provenance", "Diagnostics",
        "external_url", "infra_profile_name", "data_product", "table",
        "superseded", "requested release", "current bundle", "absent key",
        "atomic", "</script>", "U+2028", "U+2029",
    )
    for phrase in required:
        assert phrase in text, phrase
    assert "release_id" in text and "Do not accept" in text


def test_static_artifact_allows_the_bridge_only_on_missing_client_capability():
    """The bridge is a transport for capability-limited clients, not an error retry.

    Both halves matter. Dropping the first strands Cowork (no resource
    primitives, so nothing renders); dropping the second turns any resource
    error into a second attempt that dodges the diagnosis.
    """
    text = (ARTIFACT / "SKILL.md").read_text()
    for phrase in (
        "list_data_product_resources",
        "read_data_product_resource",
        "no** resource",
        "Never mix transports",
        "never on a bad answer",
    ):
        assert phrase in text, phrase

    contract = (ARTIFACT / "reference" / "contract.md").read_text()
    for phrase in ("Read transports", "one reader", "before the first read"):
        assert phrase in contract, phrase

    pitfalls = (ARTIFACT / "reference" / "pitfalls.md").read_text()
    assert "Transport fallback used as error recovery" in pitfalls

    # The lifecycle reference must no longer claim the artifact never calls a
    # tool — that was true only while the bridge did not exist.
    catalog = (POCKET / "reference" / "catalog-resources.md").read_text()
    assert "It never calls a tool" not in catalog
    assert "read_data_product_resource" in catalog


def test_bridge_fixtures_pin_transport_equivalence_and_no_bypass():
    fixtures = SCENARIO / "fixtures"
    verified = json.loads((fixtures / "verified.json").read_text())
    bridged = json.loads((fixtures / "bridge-read-verified.json").read_text())
    # The bridge carries the sealed document verbatim inside a contents block.
    assert json.loads(bridged["contents"][0]["text"]) == verified

    native_error = json.loads((fixtures / "requested-release-1.json").read_text())
    bridge_error = json.loads((fixtures / "bridge-read-release-1.json").read_text())
    for key in ("code", "message", "data"):
        assert bridge_error[key] == native_error[key], key
    assert bridge_error["code"] == -32002
    assert "kind" not in bridge_error["data"]

    checks = json.loads((SCENARIO / "checks.json").read_text())
    assert any(check["id"] == "one-read-transport" for check in checks["checks"])


def test_pocket_renders_before_describe_and_query_and_rerenders_after_rebuild():
    text = (POCKET / "SKILL.md").read_text()
    artifact = text.index("### Step 4a")
    describe = text.index("### Step 5")
    assert artifact < describe
    for phrase in ("nxd-dp-static-artifact", "list_data_products` → `resume_data_product` → artifact", "query-only exception", "query remap does not rerender", "same-workflow rebuild discards cached URIs"):
        assert phrase in text, phrase


def test_offline_fixture_checker_mechanizes_page_contract():
    verified = json.loads((SCENARIO / "fixtures" / "verified.json").read_text())
    outputs = json.loads((SCENARIO / "fixtures" / "outputs.json").read_text())
    assert "workflow" not in verified
    assert verified["release"]["workflow"] == "customer/health"
    assert isinstance(verified["data_model"], dict)
    assert verified["models"]["models"][0]["data_product"] == ""
    assert verified["models"]["models"][0]["table"] == ""
    customer_id_roles = verified["models"]["models"][0]["fields"][0]["roles"]
    assert {role["kind"] for role in customer_id_roles} == {"primary_key", "metric"}
    semantic_order_fields = verified["models"]["models"][1]["fields"]
    order_customer_id = next(
        field for field in semantic_order_fields if field["column"] == "customer_id"
    )
    assert order_customer_id["roles"][0]["kind"] == "join"
    amount = next(field for field in semantic_order_fields if field["column"] == "amount_usd")
    assert "type" not in amount
    loyalty = verified["data_model"]["models"][0]["attributes"][2]
    assert loyalty["constraints"] == {"min": "0", "nullable": False}
    amount_display = verified["data_model"]["models"][1]["attributes"][2]
    assert "decimal128" in amount_display["data_type"]
    assert outputs["outputs"]["model_names"] == ["orders"]
    assert outputs["outputs"]["models"][0]["name"] == "orders"
    assert outputs["outputs"]["ports"][0]["models"][0]["name"] == "customers"
    result = subprocess.run(
        [sys.executable, str(SCENARIO / "fixtures" / "check_static_artifact.py")],
        check=False, text=True, capture_output=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "STATIC ARTIFACT GATE PASSED" in result.stdout
    checks = (SCENARIO / "checks.json").read_text()
    assert '"nxd-dp-static-artifact"' in checks and '"nxd-pocket-loop"' in checks


def test_deterministic_checker_stays_runner_side():
    run_path = ROOT / "evals" / "run.py"
    sys.path.insert(0, str(run_path.parent))
    spec = importlib.util.spec_from_file_location("eval_runner", run_path)
    run = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = run
    try:
        spec.loader.exec_module(run)
        with tempfile.TemporaryDirectory() as tmp:
            workspace, _ = run.build_workspace(
                Path(tmp),
                run.SkillSet("no_skills", "test", []),
                SCENARIO,
            )
            assert not (workspace / "check_static_artifact.py").exists()
            assert (workspace / "verified.json").is_file()
    finally:
        sys.path.remove(str(run_path.parent))
