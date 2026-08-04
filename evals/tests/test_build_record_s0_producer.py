"""`record init` is the only producer of `s0_spec` — and it must actually be one.

Every other stage has an obvious producer and `s0_spec` had none. Left
unwritten it would stay `not_reached` forever, which pins the materialization
predicate at false and sticks a fully green, published product at
`in_progress`. These tests hold that hole closed:

* a fresh record's `s0_spec` is filled, never `not_reached`;
* it validates the SNAPSHOT, not the live IR — the snapshot is what the closure
  was compiled from, and the live IR having moved is `plan_moved`, not an
  `s0_spec` regression;
* a `--spec-report` computed against different bytes is a hard error, because
  ingesting it would silently certify the wrong plan;
* `record append --stage s0_spec` is rejected.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "src" / "nxd-run-job-loop" / "scripts"
DIAG = SCRIPTS / "dp_diagnostics.py"
VALIDATOR = SCRIPTS / "validate_dp_spec.py"
WORKED_EXAMPLE = REPO / "src" / "nxd-run-job-loop" / "reference" / "dp-spec.md"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import dp_diagnostics as dpd  # noqa: E402
import dp_spec_v2 as dpv2  # noqa: E402

pytest.importorskip("yaml")


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, *args], capture_output=True, text=True, cwd=str(REPO)
    )


def _proposed_spec_text() -> str:
    blocks = re.findall(
        r"^```markdown\n(.*?)^```", WORKED_EXAMPLE.read_text(encoding="utf-8"), re.S | re.M
    )
    assert len(blocks) == 1
    return blocks[0]


def _approved_spec_text() -> str:
    parsed = dpv2.parse(_proposed_spec_text())
    return dpv2.approve(parsed, base_hash=dpv2.semantic_hash(parsed))


@pytest.fixture
def workflow(tmp_path) -> dict:
    """The layout the design specifies: the IR beside, the closure below it."""
    spec = tmp_path / "dp-spec.md"
    spec.write_text(_approved_spec_text(), encoding="utf-8")
    closure = tmp_path / "closure"
    result = _run(str(DIAG), "lock", "write", str(spec), str(closure))
    assert result.returncode == 0, result.stderr
    return {
        "spec": spec,
        "closure": closure,
        "lock": closure / "dp-spec.lock.json",
        "record": closure / "build-record.json",
    }


def test_lock_write_byte_copies_the_spec(workflow):
    snapshot = workflow["closure"] / "dp-spec.approved.md"
    assert snapshot.read_bytes() == workflow["spec"].read_bytes(), (
        "the snapshot is evidence, and evidence reformatted on the way in cannot "
        "be compared"
    )
    lock = json.loads(workflow["lock"].read_text())
    assert lock["schema"] == "nxd-dp-spec-lock-v2"
    # Read the version rather than pinning it: the assertion under test is that
    # the lock records the compiler that produced it, not which release that
    # happens to be. A literal here fails every version bump for no defect.
    plugin_version = json.loads(
        (REPO / ".claude-plugin" / "plugin.json").read_text()
    )["version"]
    assert lock["compiler_version"]["plugin"] == plugin_version
    assert lock["spec_hash"] == dpd.spec_hash(workflow["spec"].read_bytes())
    assert lock["snapshot_sha256"] == dpd.raw_sha256(snapshot.read_bytes())
    assert lock["source_basename"] == "dp-spec.md"
    assert "/" not in lock["source_basename"], (
        "the lock carries no path to the live IR — a '../'-shaped string inside "
        "the closure is exactly the pointer this design removes"
    )


def test_lock_write_rejects_an_unapproved_spec_without_creating_artifacts(tmp_path):
    spec = tmp_path / "dp-spec.md"
    spec.write_text(_proposed_spec_text(), encoding="utf-8")
    closure = tmp_path / "closure"

    result = _run(str(DIAG), "lock", "write", str(spec), str(closure), "--json")

    assert result.returncode == 1
    diagnostics = json.loads(result.stdout)["diagnostics"]
    assert [d["code"] for d in diagnostics] == ["closure.lock_status_not_approved"]
    assert diagnostics[0]["evidence"] == {"expected": "approved", "found": "proposed"}
    assert not closure.exists()


def test_plugin_version_is_unknown_without_a_manifest(tmp_path):
    assert dpd._plugin_version(tmp_path) == "unknown"


def test_plugin_version_rejects_a_foreign_manifest(tmp_path):
    manifest = tmp_path / ".claude-plugin"
    manifest.mkdir()
    (manifest / "plugin.json").write_text(
        json.dumps({"name": "another-plugin", "version": "9.9.9"}),
        encoding="utf-8",
    )
    assert dpd._plugin_version(tmp_path) == "unknown"


def test_plugin_version_rejects_a_foreign_standalone_stamp(tmp_path):
    (tmp_path / dpd.PACKAGED_VERSION_STAMP).write_text(
        json.dumps({"name": "another-plugin", "version": "9.9.9"}),
        encoding="utf-8",
    )
    assert dpd._plugin_version(tmp_path) == "unknown"


def test_lock_has_no_legacy_prompt_reference_surface(workflow):
    """V2 resolves procedures through Models; it has no prompt-ref section."""
    lock = json.loads(workflow["lock"].read_text())
    assert "resolved_refs" not in lock


def test_lock_verify_passes_and_catches_a_moved_live_spec(workflow):
    ok = _run(str(DIAG), "lock", "verify", str(workflow["closure"]))
    assert ok.returncode == 0, ok.stdout + ok.stderr

    both = _run(str(DIAG), "lock", "verify", str(workflow["closure"]), "--spec", str(workflow["spec"]))
    assert both.returncode == 0, both.stdout + both.stderr

    workflow["spec"].write_text(
        _proposed_spec_text().replace("finance review", "finance audit", 1), encoding="utf-8"
    )
    moved = _run(
        str(DIAG), "lock", "verify", str(workflow["closure"]), "--spec",
        str(workflow["spec"]), "--json",
    )
    assert moved.returncode == 1
    codes = [d["code"] for d in json.loads(moved.stdout)["diagnostics"]]
    assert "closure.live_spec_diverged" in codes


def test_lock_verify_catches_an_edited_snapshot(workflow):
    snapshot = workflow["closure"] / "dp-spec.approved.md"
    snapshot.write_text(snapshot.read_text() + "\n## sneaky\n\nnothing\n", encoding="utf-8")
    result = _run(str(DIAG), "lock", "verify", str(workflow["closure"]), "--json")
    assert result.returncode == 1
    codes = [d["code"] for d in json.loads(result.stdout)["diagnostics"]]
    assert "closure.lock_snapshot_byte_mismatch" in codes
    assert "closure.spec_hash_mismatch" in codes


def test_lock_verify_does_not_require_pyyaml(workflow, capsys):
    assert dpd.main(["lock", "verify", str(workflow["closure"]), "--json"]) == 0

    captured = capsys.readouterr()
    assert json.loads(captured.out)["ok"] is True
    assert captured.err == ""


@pytest.mark.parametrize("snapshot", ("/tmp/foreign-spec.md", "../foreign-spec.md"))
def test_lock_verify_rejects_snapshot_paths_outside_the_closure(workflow, snapshot):
    lock = json.loads(workflow["lock"].read_text())
    lock["snapshot"] = snapshot
    workflow["lock"].write_text(json.dumps(lock), encoding="utf-8")

    result = _run(str(DIAG), "lock", "verify", str(workflow["closure"]), "--json")

    assert result.returncode == 1
    diagnostics = json.loads(result.stdout)["diagnostics"]
    assert [d["code"] for d in diagnostics] == ["closure.escaping_reference"]
    assert diagnostics[0]["evidence"] == {"found": snapshot}


def test_lock_verify_rejects_a_snapshot_symlink_outside_the_closure(workflow, tmp_path):
    snapshot = workflow["closure"] / "dp-spec.approved.md"
    external = tmp_path / "external-spec.md"
    external.write_bytes(snapshot.read_bytes())
    snapshot.unlink()
    snapshot.symlink_to(external)

    result = _run(str(DIAG), "lock", "verify", str(workflow["closure"]), "--json")

    assert result.returncode == 1
    diagnostics = json.loads(result.stdout)["diagnostics"]
    assert [d["code"] for d in diagnostics] == ["closure.escaping_reference"]
    assert diagnostics[0]["evidence"] == {"found": "dp-spec.approved.md"}


def test_record_init_fills_s0_spec(workflow):
    result = _run(
        str(DIAG), "record", "init", "--record", str(workflow["record"]),
        "--lock", str(workflow["lock"]),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    record = json.loads(workflow["record"].read_text())
    assert record["stages"]["s0_spec"]["status"] != "not_reached"
    assert record["stages"]["s0_spec"]["status"] in ("passed", "passed_with_warnings")
    assert record["stages"]["s0_spec"]["origin"] == "tool_computed"
    assert record["compiled_from"] == json.loads(workflow["lock"].read_text())["spec_hash"]
    assert dpd.validate_build_record(record) == []
    assert record["review_rounds"] == []
    # Every other stage is honestly `not_reached`.
    assert record["stages"]["s4_pin"]["status"] == "not_reached"


def test_record_init_validates_the_snapshot_not_the_live_ir(workflow):
    """The snapshot is what the closure was compiled from."""
    workflow["spec"].write_text("this is no longer a spec at all\n", encoding="utf-8")
    result = _run(
        str(DIAG), "record", "init", "--record", str(workflow["record"]),
        "--lock", str(workflow["lock"]),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    record = json.loads(workflow["record"].read_text())
    assert record["stages"]["s0_spec"]["status"] in ("passed", "passed_with_warnings")


def test_record_init_on_an_unparseable_snapshot_records_it(workflow):
    """The regression: `_validate_snapshot` runs the validator in-process, and a
    `yaml.YAMLError` escaping it used to take `record init` down with a raw
    traceback — no record written, nothing machine-readable.

    The fix is upstream: the split is now field-addressed, so the failure
    arrives as a diagnostic. `record init` therefore does what §2.2 says and
    RECORDS it — `s0_spec: failed`, exit 1 — rather than refusing to write.
    Recording is the point: a closure generated against a spec that does not
    validate is exactly the thing that must become visible instead of implicit.
    """
    snapshot = workflow["closure"] / "dp-spec.approved.md"
    snapshot.write_text("---\nname: [unclosed\n---\n\n## intent\n\nx\n", encoding="utf-8")

    result = _run(
        str(DIAG), "record", "init", "--record", str(workflow["record"]),
        "--lock", str(workflow["lock"]),
    )
    assert "Traceback" not in result.stderr, result.stderr
    assert result.returncode == 1, result.stdout + result.stderr

    record = json.loads(workflow["record"].read_text())
    s0 = record["stages"]["s0_spec"]
    assert s0["status"] == "failed"
    assert [d["code"] for d in s0["diagnostics"]] == ["spec.v2.invalid"]
    assert s0["diagnostics"][0]["evidence"]["validator_code"] == "spec.parse.invalid"
    assert dpd.validate_build_record(record) == []


def test_spec_report_against_different_bytes_exits_two(workflow, tmp_path):
    other = tmp_path / "other.md"
    other.write_text(_proposed_spec_text().replace("finance review", "finance audit", 1), encoding="utf-8")
    report = _run(str(VALIDATOR), str(other), "--json")
    report_path = tmp_path / "report.json"
    report_path.write_text(report.stdout, encoding="utf-8")

    result = _run(
        str(DIAG), "record", "init", "--record", str(workflow["record"]),
        "--lock", str(workflow["lock"]), "--spec-report", str(report_path),
    )
    assert result.returncode == 2, result.stdout
    assert "different spec" in result.stderr


def test_spec_report_against_the_right_bytes_is_ingested(workflow, tmp_path):
    report = _run(str(VALIDATOR), str(workflow["closure"] / "dp-spec.approved.md"), "--json")
    report_path = tmp_path / "report.json"
    report_path.write_text(report.stdout, encoding="utf-8")

    result = _run(
        str(DIAG), "record", "init", "--record", str(workflow["record"]),
        "--lock", str(workflow["lock"]), "--spec-report", str(report_path),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    record = json.loads(workflow["record"].read_text())
    assert record["stages"]["s0_spec"]["status"] in ("passed", "passed_with_warnings")


def test_record_init_redacts_external_spec_report_diagnostics(workflow, tmp_path):
    url = "postgresql://admin:url-password@db.example.internal/app"
    diagnostic = dpd.diagnostic(
        "spec.frontmatter.bad_name",
        message="invalid name",
        path="v2:frontmatter.name",
        evidence={},
    ).to_dict()
    diagnostic["message"] = f"invalid name from {url}"
    diagnostic["evidence"] = {
        "password": "bare-password",
        "nested": {
            "token": "bare-token",
            "label": "preserve this context",
        },
    }
    report = tmp_path / "spec-report.json"
    report.write_text(
        json.dumps(
            {
                "schema": "nxd-diagnostic-report-v2",
                "tool": "validate_dp_spec",
                "target": str(workflow["spec"]),
                "ok": False,
                "counts": {"error": 1, "warning": 0, "info": 0},
                "spec_hash": dpd.spec_hash(
                    (workflow["closure"] / "dp-spec.approved.md").read_bytes()
                ),
                "diagnostics": [diagnostic],
            }
        ),
        encoding="utf-8",
    )

    result = _run(
        str(DIAG), "record", "init", "--record", str(workflow["record"]),
        "--lock", str(workflow["lock"]), "--spec-report", str(report),
    )

    assert result.returncode == 1, result.stdout + result.stderr
    exported = workflow["record"].read_text(encoding="utf-8")
    for secret in ("url-password", "bare-password", "bare-token"):
        assert secret not in exported
    record = json.loads(exported)
    stored = record["stages"]["s0_spec"]["diagnostics"][0]
    assert stored["evidence"]["nested"]["label"] == "preserve this context"
    assert stored["evidence"]["password"] == "<redacted>"


def test_record_append_to_s0_spec_is_rejected(workflow, tmp_path):
    _run(
        str(DIAG), "record", "init", "--record", str(workflow["record"]),
        "--lock", str(workflow["lock"]),
    )
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps(
            {
                "schema": "nxd-diagnostic-report-v2",
                "tool": "validate_dp_spec",
                "target": "x",
                "ok": True,
                "counts": {"error": 0, "warning": 0, "info": 0},
                "spec_hash": None,
                "diagnostics": [],
            }
        ),
        encoding="utf-8",
    )
    result = _run(
        str(DIAG), "record", "append", "--record", str(workflow["record"]),
        "--stage", "s0_spec", "--from", str(report),
    )
    assert result.returncode == 2
    assert "record init is the only writer" in result.stderr


def test_record_append_rejects_a_tool_that_cannot_produce_the_stage(workflow, tmp_path):
    _run(
        str(DIAG), "record", "init", "--record", str(workflow["record"]),
        "--lock", str(workflow["lock"]),
    )
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps(
            {
                "schema": "nxd-diagnostic-report-v2",
                "tool": "self_check",
                "target": "x",
                "ok": True,
                "counts": {"error": 0, "warning": 0, "info": 0},
                "spec_hash": None,
                "diagnostics": [],
            }
        ),
        encoding="utf-8",
    )
    result = _run(
        str(DIAG), "record", "append", "--record", str(workflow["record"]),
        "--stage", "s6_run", "--from", str(report),
    )
    assert result.returncode == 2
    assert "cannot carry stage" in result.stderr


def test_a_loop_report_merges_and_the_record_stays_valid(workflow, tmp_path):
    _run(
        str(DIAG), "record", "init", "--record", str(workflow["record"]),
        "--lock", str(workflow["lock"]),
    )
    report = tmp_path / "loop.json"
    report.write_text(
        json.dumps(
            {
                "schema": "nxd-diagnostic-report-v2",
                "tool": "loop",
                "target": "build_data_product",
                "ok": False,
                "counts": {"error": 1, "warning": 0, "info": 0},
                "spec_hash": None,
                "diagnostics": [
                    dpd.diagnostic(
                        "pin.build_failed",
                        message="build returned an error with no endpoint",
                        path="tool:build_data_product.error",
                        origin="agent_observed",
                        evidence={"stdout_excerpt": "…"},
                    ).to_dict()
                ],
            }
        ),
        encoding="utf-8",
    )
    result = _run(
        str(DIAG), "record", "append", "--record", str(workflow["record"]),
        "--stage", "s4_pin", "--from", str(report),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    record = json.loads(workflow["record"].read_text())
    assert record["stages"]["s4_pin"]["status"] == "failed"
    assert record["stages"]["s4_pin"]["origin"] == "agent_observed", (
        "an agent-constructed report is visibly weaker evidence than a tool's"
    )
    assert dpd.validate_build_record(record) == []

    state = _run(str(DIAG), "materialized", "--record", str(workflow["record"]), "--json")
    assert state.returncode == 1
    assert json.loads(state.stdout)["state"] == "unsettled"


def test_record_append_redacts_incoming_diagnostic_url_credentials(workflow, tmp_path):
    _run(
        str(DIAG), "record", "init", "--record", str(workflow["record"]),
        "--lock", str(workflow["lock"]),
    )
    url = "postgresql://admin:password@db.example.internal/app"
    diagnostic = dpd.diagnostic(
        "pin.build_failed",
        message=f"build failed while connecting to {url}",
        path="tool:build_data_product.error",
        origin="agent_observed",
        evidence={
            "endpoint": url,
            "nested": ["keep this context", {"detail": f"retry {url}"}],
        },
    ).to_dict()
    # The producer normally redacts. A report received from another tool is
    # untrusted input, so record append must protect persistent output itself.
    diagnostic["message"] = f"build failed while connecting to {url}"
    diagnostic["evidence"] = {
        "endpoint": url,
        "nested": ["keep this context", {"detail": f"retry {url}"}],
    }
    report = tmp_path / "loop.json"
    report.write_text(
        json.dumps(
            {
                "schema": "nxd-diagnostic-report-v2",
                "tool": "loop",
                "target": "build_data_product",
                "ok": False,
                "counts": {"error": 1, "warning": 0, "info": 0},
                "spec_hash": None,
                "diagnostics": [diagnostic],
            }
        ),
        encoding="utf-8",
    )

    result = _run(
        str(DIAG), "record", "append", "--record", str(workflow["record"]),
        "--stage", "s4_pin", "--from", str(report),
    )

    assert result.returncode == 0, result.stdout + result.stderr
    exported = workflow["record"].read_text(encoding="utf-8")
    assert "password" not in exported
    assert "postgresql://admin:<redacted>@db.example.internal/app" in exported
    record = json.loads(exported)
    stored = record["stages"]["s4_pin"]["diagnostics"][0]
    assert stored["evidence"]["nested"][0] == "keep this context"


def test_materialized_exits_one_when_not_materialized(workflow):
    _run(
        str(DIAG), "record", "init", "--record", str(workflow["record"]),
        "--lock", str(workflow["lock"]),
    )
    result = _run(str(DIAG), "materialized", "--record", str(workflow["record"]))
    assert result.returncode == 1
    assert "state: in_progress" in result.stdout


def test_evidence_with_a_stage_is_rejected_rather_than_silently_dropped(workflow):
    """REGRESSION. `--evidence` is record-level; `--status` stamps
    `origin: agent_observed`. Pairing it with `--stage` reads like "attach this
    supervisor payload to that stage" but merged it record-level at exit 0 —
    which is how a real supervisor's diagnostic.json got dropped on the floor.
    It must now refuse and name the working route.
    """
    _run(
        str(DIAG), "record", "init", "--record", str(workflow["record"]),
        "--lock", str(workflow["lock"]),
    )
    result = _run(
        str(DIAG), "record", "append", "--record", str(workflow["record"]),
        "--stage", "s6_run", "--status", "failed",
        "--evidence", '{"supervisor_detail": "kernel host exited"}',
    )
    assert result.returncode == 2
    assert "--from" in result.stderr

    record = json.loads(workflow["record"].read_text(encoding="utf-8"))
    assert "supervisor_detail" not in (record.get("evidence") or {})


def test_record_level_evidence_without_a_stage_still_works(workflow):
    """The guard must not break the legitimate build-wide use."""
    _run(
        str(DIAG), "record", "init", "--record", str(workflow["record"]),
        "--lock", str(workflow["lock"]),
    )
    result = _run(
        str(DIAG), "record", "append", "--record", str(workflow["record"]),
        "--evidence", '{"row_counts": {"main.widget_sales": 5}}',
    )
    assert result.returncode == 0
    record = json.loads(workflow["record"].read_text(encoding="utf-8"))
    assert record["evidence"]["row_counts"] == {"main.widget_sales": 5}
