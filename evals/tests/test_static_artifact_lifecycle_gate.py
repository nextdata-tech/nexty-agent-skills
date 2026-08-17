"""Pin the static release artifact contract and desktop lifecycle ordering."""
from __future__ import annotations

from pathlib import Path
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT = ROOT / "src" / "nxd-render-static-artifact"
JOB_LOOP = ROOT / "src" / "nxd-run-job-loop"
SCENARIO = ROOT / "evals" / "public" / "dp-static-artifact-lifecycle"


def test_desktop_reference_index_includes_catalog_resources():
    text = (JOB_LOOP / "SKILL.md").read_text()
    assert "[catalog resources](reference/catalog-resources.md)" in text


def test_renamed_static_skill_is_the_only_shipped_identity():
    assert ARTIFACT.is_dir()
    assert not (ROOT / "src" / ("nxd-" + "artifact")).exists()
    text = (ARTIFACT / "SKILL.md").read_text()
    assert "name: nxd-render-static-artifact" in text
    # Assert the lockstep invariant, not a literal — every release bumps all
    # skills together, so pinning the number here would break on each bump for
    # a reason unrelated to what this test guards.
    plugin_version = json.loads(
        (ROOT / ".claude-plugin" / "plugin.json").read_text()
    )["version"]
    assert f"version: {plugin_version}" in text
    # No inline-artifact mode: this skill writes one file. Match the phrases
    # that mean that, rather than the bare word, which would fire on innocuous
    # future mentions like `display:inline-block` or "inline styles" in the CSP
    # guidance.
    lowered = text.lower()
    for phrase in ("inline widget", "inline artifact", "inline mode", "render inline"):
        assert phrase not in lowered, phrase
    assert "\n## Catalog" not in text and "\n## Query" not in text


def test_static_artifact_fails_closed_and_validates_the_complete_contract():
    text = (ARTIFACT / "SKILL.md").read_text()
    required = (
        "current", "verified.json", "outputs", "schema: nxd-desktop-verified-v1",
        "artifact_verified", "list_data_products", "fail the whole artifact",
        "data_model", "unannotated", "complex", "roles as a set", "joins",
        "ports[].model_names", "promises", "Release provenance", "Diagnostics",
        "external_url", "infra_profile_name", "data_product", "table",
        "superseded", "requested release", "current bundle", "Key absent",
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
    catalog = (JOB_LOOP / "reference" / "catalog-resources.md").read_text()
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


def test_undeclared_joins_may_not_be_drawn_or_named():
    """An empty join registry must produce no edges and no shape claim.

    Observed: header, legend and prose all said "none declared" while the
    diagram drew dashed edges between models sharing a column name, and the
    prose then called the result "a small star". Honest captions do not
    license a picture that contradicts them.
    """
    # Prose is hard-wrapped, so match on whitespace-normalized text.
    flat = lambda p: " ".join((ARTIFACT / p).read_text().split())
    skill = flat("SKILL.md")
    contract = flat("reference/contract.md")
    pitfalls = flat("reference/pitfalls.md")

    # The rule binds the visual channel, not only the data.
    assert "Every visual channel is an assertion" in contract
    for phrase in ("no connecting lines at all", "not dashed ones", "legend"):
        assert phrase in contract, phrase
    # Shared column names are named as the specific false signal.
    assert "column name" in contract and "is not a relationship" in contract
    # Prose shape claims are banned alongside the drawing.
    for phrase in ('"a star"', "no shape to name"):
        assert phrase in contract, phrase

    # SKILL.md carries it too — the agent reads that first.
    assert "only for a declared join" in skill
    assert "shared column names are not relationships" in skill.lower()
    assert "joins: []" in skill

    assert "## Inferred relationships" in pitfalls
    assert "a diagram edge is an assertion" in pitfalls


def test_absence_states_are_distinct_and_never_a_labelled_blank():
    """null / [] / "" / absent are four states; a blank labelled cell is none of them.

    All four co-occur in one real release: identity.description is null while a
    model description is "", and registry joins is [] while per-model joins is
    null. A blank cell under a populated header asserts "unset" over a payload
    that said something more specific.
    """
    flat = lambda p: " ".join((ARTIFACT / p).read_text().split())
    skill = flat("SKILL.md")
    contract = flat("reference/contract.md")
    pitfalls = flat("reference/pitfalls.md")

    # All three glosses present verbatim, including the empty-string one.
    for gloss in ("null · not declared", "[] · none declared", '"" · empty'):
        assert gloss in skill, gloss
        assert gloss in contract, gloss

    # The decision branches on the KEY, not the value — that distinction is what
    # kept getting lost, so assert both branches rather than one sentence.
    assert "Key absent" in skill and "Key present" in skill
    assert re.search(r"leaving its cell blank", skill)
    assert "never a labelled blank" in contract
    for phrase in ("omit the whole column", "even one row has a value"):
        assert phrase in contract, phrase
    assert "## Labelled blanks" in pitfalls

    # Page must be clamped so a side panel does not scroll sideways.
    assert "never scroll horizontally" in contract
    assert "must never scroll sideways" in skill
    example = (ARTIFACT / "assets" / "artifact-example.html").read_text()
    assert "max-width: min(980px, 100%)" in example
    assert "box-sizing: border-box" in example




def test_desktop_renders_before_describe_and_query_and_rerenders_after_rebuild():
    """The render step precedes describe/query and survives the 500-line budget.

    Assert the requirements, not their phrasing: this file is hand-maintained
    against a hard line cap, so prose gets rewrapped and tightened. Pinning
    sentences here makes an editorial pass look like a regression — the same
    lesson the deterministic gate learned about heading vocabulary.
    """
    text = (JOB_LOOP / "SKILL.md").read_text()
    artifact = text.index("### Step 4a")
    describe = text.index("### Step 5")
    assert artifact < describe
    step_4a = text[artifact:describe]

    # The step invokes the artifact skill, before describe/query.
    assert "nxd-render-static-artifact" in step_4a
    assert re.search(r"before\s+`describe_models`", step_4a)
    # Both transports are named as acceptable sources for the read.
    assert "bridge tools" in step_4a
    # The three facts reported separately from the endpoint.
    for token in ("`status`", "`path`", "`publish_seq`"):
        assert token in step_4a, token
    # A failed artifact does not condemn a healthy endpoint.
    assert re.search(r"healthy\s+endpoint", step_4a)
    # A rebuild invalidates cached URIs and re-renders.
    assert "cached URIs" in step_4a

    # Reattach path routes through the artifact, and discovery stays discovery.
    assert "`list_data_products` → `resume_data_product` → artifact" in text
    assert re.search(r"discovery only", text)


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
    assert '"nxd-render-static-artifact"' in checks and '"nxd-run-job-loop"' in checks


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
