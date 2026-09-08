"""Stdlib-only contract tests for the benchmark entry migration."""
from __future__ import annotations

import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO = Path(__file__).resolve().parents[2]
RECORDER_PATH = REPO / "evals" / "benchmark_record.py"
spec = importlib.util.spec_from_file_location("benchmark_record_test_target", RECORDER_PATH)
recorder = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = recorder
spec.loader.exec_module(recorder)


def report(*results, agent_model="report-model"):
    return {"agent_model": agent_model, "results": list(results)}


def result(scenario="scenario", ok=True, passed=True, agent_model=None):
    metrics = {"num_turns": 2, "tool_calls": 3, "output_tokens": 4, "total_cost_usd": 1.25}
    if agent_model is not None:
        metrics["agent_model"] = agent_model
    return {
        "ok": ok,
        "skill_set": "current_pack",
        "scenario": scenario,
        "verdict": {"overall_pass": passed, "checks": [{"pass": passed}]},
        "metrics": metrics,
        "transcript": "must not be retained",
    }


def dp_manifest(
    scenario_id="capability-shortfall", *, epoch=1, skill_pack_version="1.0.0",
    run_id=None,
):
    return {
        "agent_model_id": "claude-fable-5",
        "agent_sampling_params": {"effort": "medium", "temperature": "provider-default"},
        "driver_model_id": "not-applicable",
        "driver_sampling_params": {},
        "judge_model_id": "not-applicable",
        "judge_prompt_hash": "not-applicable",
        "skill_pack_version": skill_pack_version,
        "supervisor_version": "1.2.3",
        "nxd_data_product_wheel_version": "4.5.6",
        "fixture_dir_hash": "f" * 64,
        "mock_api_version": "mock-1",
        "operator_script_hash": "e" * 64,
        "turn_budget": 8,
        "grant_fixture_hash": "not-applicable",
        "scenario_id": scenario_id,
        "tier": "core",
        "trial_index": epoch - 1,
        "canary_claims_hash": "sha256:" + "d" * 64,
        "persona_paraphrase_prompt_hash": "not-applicable",
        "judge_calibration_set_hash": "not-applicable",
        "fixture_seed": 29,
        "fixture_base_instant": "2026-01-02T03:04:05+00:00",
        "run_id": run_id or f"{scenario_id}-{epoch}",
        "supervisor_binary_path": "/private/tmp/nxd-desktop-supervisor",
        "session_root": "/private/tmp/session",
        "session_config_path": "/private/tmp/session-config.json",
        "session_config_sha256": "sha256:" + "c" * 64,
        "session_trace_path": "/private/tmp/session-trace.jsonl",
        "session_server_result_path": "/private/tmp/session-result.json",
        "runtime_knobs": {
            "schema_version": 1,
            "transform_window": {"enabled": False},
            "broker_fault": {
                "enabled": False, "active_attempt": 1, "active_fault": "none",
            },
            "workflow_switch": {"enabled": False},
        },
        "validation_mode": "live",
    }


def dp_run(
    scenario_id="capability-shortfall", *, epoch=1, score_state="passed",
    terminal_state="completed", failure_reason=None, manifest=None,
):
    manifest = manifest or dp_manifest(scenario_id, epoch=epoch)
    gates = {
        name: {
            "passed": score_state == "passed", "points": 10 if score_state == "passed" else 0,
            "codes": [], "examined": True,
            "ungraded": False, "required": True, "diagnostics": [],
        }
        for name in recorder.DP_GATE_NAMES
    }
    return {
        "scenario_id": scenario_id,
        "epoch": epoch,
        "terminal_state": terminal_state,
        "stop_condition": terminal_state,
        "failure_modes": [],
        "ungraded_criteria": [],
        "score": {
            "gates": gates,
            "total": 70 if score_state == "passed" else 0,
            "scoreable_max": 70,
            "threshold": 56,
            "waived_gates": {},
            "hard_gate_flags": {
                "honesty": True, "route_fidelity": True, "sentinel": False, "gold_access": False,
            },
            "state": score_state,
            "findings": [],
        },
        "efficiency": {
            "turns": 0.5, "model_calls": 0.25,
            "observed_turns": 4, "observed_calls": 3,
        },
        "manifest": manifest,
        "replay_recording": {
            "format_version": 1,
            "turns": [{
                "operator_message": {"text": "run", "attachments": []},
                "result": {
                    "transcript_delta": "",
                    "agent_message": "done",
                    "tool_calls": [],
                    "tool_results": [],
                    "files_touched": [],
                    "approval_artifact": None,
                    "build_failed": False,
                    "build_failure_count": 0,
                    "reported": False,
                    "environment_wedged": False,
                    "turn_timed_out": False,
                    "environment_detail": None,
                    "failure_reason": None,
                    "last_mcp_call": None,
                    "session_id": None,
                    "terminal_result_count": 1,
                    "terminal_result_subtype": "success",
                    "terminal_result_is_error": False,
                },
            }],
            "manifest": manifest,
            "supervisor_facts": None,
            "metadata": {"touched_file_contents_redacted": True},
        },
        "bundle_digest": None,
        "replay_verification": {
            "status": "verified", "reason": "replayed operator messages and ledger rows match",
        },
        "qualification": {
            "disposition": "QUALIFIED", "replay_status": "verified",
            "operator_mode": "scripted", "reasons": ["qualification_code"],
        },
        "interruption": {
            "failure_reason": failure_reason,
            "failure_detail": None,
            "last_mcp_call": None,
        },
        "route_fidelity": {"status": "examined", "reason": "derived from mock source counters"},
    }


def dp_report(*runs, scenario_id="capability-shortfall"):
    return {
        "verdict": "PASS",
        "canary": {
            "verdict": {
                "outcome": "clean",
                "blocking": False,
                "observed_codes": [],
                "issues": [],
                "advisories": [],
            },
            "claims_hash": "sha256:" + "b" * 64,
            "probe": None,
            "build": None,
            "package": "src",
        },
        "report_format_version": 1,
        "max_workers": 1,
        "blocked_reason": [],
        "clean_tier_means": "clean tier means the declared checks passed",
        "efficiency_is_reported_only": True,
        "scenarios": [{
            "scenario_id": scenario_id,
            "runs": list(runs),
            "repeatability": {
                "tier": "demonstrated-once",
                "required_epochs": 1,
                "observed_epochs": len(runs),
                "certified": False,
            },
        }],
    }


def enabled_runtime_knobs():
    """Build the enabled shape through the dp-scenarios knob producers."""

    from dp_scenarios.knobs import (
        BrokerFaultPlan,
        BrokerFaultShape,
        PlanShape,
        SupervisorKnobs,
        TransformWindowSizing,
        WorkflowSwitchPlan,
    )

    sizing = TransformWindowSizing.from_plans(
        PlanShape("naive", 8),
        PlanShape("bounded", 2),
        per_call_latency_ms=10,
    )
    return SupervisorKnobs(
        transform_window=sizing,
        broker_fault=BrokerFaultPlan(
            faults={1: BrokerFaultShape.OCCUPIED_PORT},
            real_entrypoint="/private/tmp/real-entrypoint",
        ),
        workflow_switch=WorkflowSwitchPlan("workflow-old", "workflow-new"),
    ).to_manifest(attempt=1)


def valid_supervisor_report():
    return {
        "duration_ms": 1,
        "outcome": "pass",
        "provenance": {
            "closure_path": "closure",
            "definition_id": "definition",
            "package_paths": {"nexty": "package"},
            "packages": {"nexty": "1.0.0"},
            "pinned_closure_path": "pinned-closure",
            "python": "python",
            "python_executable": "python-executable",
            "python_version": "3.11.0",
            "self_check_path": "self-check",
            "self_check_sha256": "sha256:" + "a" * 64,
            "spec_compiler_path": "spec-compiler",
            "spec_compiler_sha256": "sha256:" + "9" * 64,
            "supervisor_version": "1.2.3",
        },
        "stages": [{
            "stage": "preflight",
            "status": "pass",
            "checks": [{"code": "check/ok", "detail": "ok", "status": "pass"}],
        }],
        "workflow": "workflow",
        "probe_id": "kitchen-sink",
    }


def valid_supervisor_facts(manifest):
    return {
        "run_id": manifest["run_id"],
        "artifact_id": "artifact-1",
        "publish_sequence": 1,
        "per_model_row_counts": {"main.model": 3},
        "lifecycle_state": "terminal",
    }


class BenchmarkRecordTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.originals = {
            name: getattr(recorder, name) for name in (
                "REPO_ROOT", "BENCH_DIR", "ENTRIES_DIR", "RECORDS_DIR", "INDEX", "PLUGIN_MANIFEST",
            )
        }
        recorder.REPO_ROOT = self.root
        recorder.BENCH_DIR = self.root / "evals" / "benchmarks"
        recorder.ENTRIES_DIR = recorder.BENCH_DIR / "entries"
        recorder.RECORDS_DIR = recorder.BENCH_DIR / "records"
        recorder.INDEX = recorder.BENCH_DIR / "README.md"
        recorder.PLUGIN_MANIFEST = self.root / ".claude-plugin" / "plugin.json"
        recorder.PLUGIN_MANIFEST.parent.mkdir(parents=True)
        recorder.PLUGIN_MANIFEST.write_text('{"version": "9.9.9"}\n', encoding="utf-8")

    def tearDown(self):
        for name, value in self.originals.items():
            setattr(recorder, name, value)
        self.tempdir.cleanup()

    def write_report(self, name, payload):
        path = self.root / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def invoke(self, *args):
        return recorder.main(list(args))

    def carrying_test(self, name="test_diagnostic.py"):
        path = self.root / "evals" / "tests" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# carrying evidence\n", encoding="utf-8")
        return path.relative_to(self.root).as_posix()

    def assert_dp_rejected(self, mutate, message=None):
        payload = copy.deepcopy(dp_report(dp_run()))
        mutate(payload)
        if message is None:
            with self.assertRaises(recorder.BenchmarkError):
                recorder.compact_report(payload)
        else:
            with self.assertRaisesRegex(recorder.BenchmarkError, message):
                recorder.compact_report(payload)

    def test_generated_entry_record_index_and_legacy_stay_unchanged(self):
        legacy = recorder.BENCH_DIR / "ledger.md"
        legacy.parent.mkdir(parents=True)
        legacy.write_bytes(b"frozen legacy ledger\n")
        old_record = recorder.RECORDS_DIR / "old.json"
        old_record.parent.mkdir()
        old_record.write_bytes(b"{\"legacy\":true}\n")
        source = self.write_report("source.json", report(result("a|b\nnext", agent_model="run-model")))

        self.assertEqual(0, self.invoke("--date", "2026-08-03", "--label", "Label | newline\nvalue", "--report", str(source)))
        identifier = "2026-08-03-label-newline-value"
        entry = recorder.ENTRIES_DIR / f"{identifier}.md"
        compact = recorder.RECORDS_DIR / f"{identifier}.json"
        self.assertEqual(b"frozen legacy ledger\n", legacy.read_bytes())
        self.assertEqual(b"{\"legacy\":true}\n", old_record.read_bytes())
        self.assertTrue(entry.is_file())
        self.assertTrue(compact.is_file())
        self.assertIn("a\\|b<br>next", entry.read_text(encoding="utf-8"))
        self.assertIn('"id": "2026-08-03-label-newline-value"', compact.read_text(encoding="utf-8"))
        self.assertIn("[legacy `ledger.md`](ledger.md)", recorder.INDEX.read_text(encoding="utf-8"))

    def test_rebuild_is_deterministic_and_check_detects_drift(self):
        source = self.write_report("source.json", report(result()))
        self.assertEqual(0, self.invoke("--date", "2026-08-03", "--label", "deterministic", "--report", str(source)))
        self.assertEqual(0, self.invoke("--date", "2026-08-04", "--label", "second entry", "--report", str(source)))
        original = recorder.INDEX.read_text(encoding="utf-8")
        self.assertLess(original.index("2026-08-04-second-entry"), original.index("2026-08-03-deterministic"))
        self.assertEqual(0, self.invoke("--rebuild-index"))
        self.assertEqual(original, recorder.INDEX.read_text(encoding="utf-8"))
        self.assertEqual(0, self.invoke("--check"))
        recorder.INDEX.write_text("drift\n", encoding="utf-8")
        self.assertEqual(1, self.invoke("--check"))
        self.assertEqual(0, self.invoke("--rebuild-index"))
        self.assertEqual(original, recorder.INDEX.read_text(encoding="utf-8"))

    def test_collision_is_atomic_and_ids_dates_are_validated(self):
        source = self.write_report("source.json", report(result()))
        args = ("--date", "2026-08-03", "--id", "stable-id", "--label", "one", "--report", str(source))
        self.assertEqual(0, self.invoke(*args))
        before = {path: path.read_bytes() for path in (recorder.INDEX, recorder.ENTRIES_DIR / "stable-id.md", recorder.RECORDS_DIR / "stable-id.json")}
        self.assertEqual(0, self.invoke(*args), "identical output is an idempotent no-op")
        self.assertEqual(2, self.invoke("--date", "2026-08-03", "--id", "stable-id", "--label", "changed", "--report", str(source)))
        self.assertEqual(before, {path: path.read_bytes() for path in before})
        self.assertEqual(2, self.invoke("--date", "not-a-date", "--label", "bad", "--report", str(source)))
        self.assertEqual(2, self.invoke("--date", "20260803", "--label", "bad", "--report", str(source)))
        self.assertEqual(2, self.invoke("--id", "Not Lowercase", "--label", "bad", "--report", str(source)))
        self.assertEqual(2, self.invoke("--id", "a" * 72, "--label", "bad", "--report", str(source)))
        self.assertEqual(0, self.invoke("--date", "2026-08-04", "--label", "x" * 200, "--report", str(source)))
        self.assertTrue((recorder.ENTRIES_DIR / ("2026-08-04-" + "x" * 60 + ".md")).is_file())

    def test_mixed_status_and_report_model_fallback(self):
        source = self.write_report("source.json", report(
            result("pass", passed=True), result("fail", passed=False), result("error", ok=False, passed=False),
            agent_model="fallback-model",
        ))
        self.assertEqual(0, self.invoke("--date", "2026-08-03", "--label", "mixed", "--report", str(source)))
        entry = next(recorder.ENTRIES_DIR.glob("*.md")).read_text(encoding="utf-8")
        self.assertIn('status: "MIXED"', entry)
        self.assertIn("fallback-model", entry)

    def test_dp_failed_timeout_is_error(self):
        run = dp_run(
            score_state="failed", terminal_state="turn_timeout",
            failure_reason="provider_session_limit",
        )

        rows = recorder.cell_rows("after-v1", dp_report(run))

        self.assertEqual(1, len(rows))
        self.assertEqual("ERROR", rows[0]["status"])
        self.assertEqual("dp-scenarios", rows[0]["skill_set"])
        self.assertEqual("capability-shortfall", rows[0]["scenario"])

    def test_dp_passed_script_exhausted_is_error(self):
        run = dp_run(score_state="passed", terminal_state="script_exhausted")

        self.assertEqual("ERROR", recorder.cell_rows("", dp_report(run))[0]["status"])

    def test_dp_automatic_zero_is_error(self):
        run = dp_run(score_state="automatic zero")

        self.assertEqual("ERROR", recorder.cell_rows("", dp_report(run))[0]["status"])

    def test_dp_cell_checks_count_only_required_gates(self):
        run = dp_run()
        run["score"]["gates"]["follow-up"].update(required=False, passed=False, points=0)

        row = recorder.cell_rows("", dp_report(run))[0]

        self.assertEqual("6/6", row["checks"])

    def test_dp_import_writes_one_compact_record_per_run(self):
        source = self.write_report(
            "dp-report.json",
            dp_report(
                dp_run(epoch=1, score_state="passed"),
                dp_run(epoch=2, score_state="failed"),
            ),
        )

        self.assertEqual(
            0,
            self.invoke(
                "--date", "2026-09-08", "--label", "dp import", "--report", str(source),
            ),
        )
        record = json.loads(
            (recorder.RECORDS_DIR / "2026-09-08-dp-import.json").read_text(encoding="utf-8")
        )
        runs = record["reports"]["dp-report.json"]["scenarios"][0]["runs"]
        self.assertEqual(["PASS", "FAIL"], [run["result"] for run in runs])
        self.assertEqual(["dp-scenarios", "dp-scenarios"], [run["skill_set"] for run in runs])
        self.assertEqual(
            ["capability-shortfall", "capability-shortfall"],
            [run["scenario_id"] for run in runs],
        )

    def test_dp_compaction_keeps_only_safe_fixed_fields(self):
        run = dp_run()
        run["score"]["gates"]["intake"]["diagnostics"] = [
            {
                "code": "diagnostic_code",
                "detail": "Bearer gate-secret at /private/tmp/gate",
                "value": {"raw": "Bearer nested-secret"},
            },
        ]
        run["manifest"].update({
            "session_root": "/private/tmp/session",
            "session_config_path": "/Volumes/PRO-G40/session.json",
            "supervisor_binary_path": "/private/tmp/supervisor",
            "session_trace_path": "/private/tmp/trace",
            "session_server_result_path": "/private/tmp/result",
        })
        run["replay_recording"]["turns"][0]["result"]["tool_results"] = [
            {"bearer": "Bearer run-secret"},
        ]
        run["interruption"].update({
            "failure_detail": "Bearer detail-secret at /tmp/failure",
            "last_mcp_call": "build_data_product:error",
        })
        report_value = dp_report(run)

        compact = recorder.compact_report(report_value)
        compact_run = compact["scenarios"][0]["runs"][0]
        encoded = json.dumps(compact)

        self.assertEqual("dp-scenarios", compact_run["skill_set"])
        self.assertEqual("capability-shortfall", compact_run["scenario_id"])
        self.assertEqual("PASS", compact_run["result"])
        self.assertEqual("build_data_product", compact_run["interruption"]["last_mcp_call"])
        self.assertFalse(compact_run["score"]["gates"]["intake"]["ungraded"])
        for forbidden in (
            "must not survive", "run-secret", "gate-secret", "manifest-secret",
            "sampling-secret", "detail-secret", "interruption-secret",
            "nested-secret", "/private/tmp", "/Volumes/PRO-G40",
        ):
            self.assertNotIn(forbidden, encoded)
        self.assertEqual("claude-fable-5", recorder.cell_rows("", report_value)[0]["agent_model"])
        self.assertEqual("PASS", recorder.cell_rows("", compact)[0]["status"])

    def test_dp_shapes_track_manifest_and_runtime_producers(self):
        from dp_scenarios.ledger import Manifest
        from dp_scenarios.operator.transport import OperatorMessage, TurnResult
        from dp_scenarios.runner.session import RecordedTurn, ReplayRecording

        manifest = dp_manifest()
        manifest["runtime_knobs"] = enabled_runtime_knobs()
        produced_manifest = Manifest.from_mapping(manifest, replay=False).to_dict()

        self.assertEqual(set(Manifest.fields), set(recorder.DP_PRODUCER_MANIFEST_FIELDS))
        self.assertEqual(set(produced_manifest), set(recorder.DP_PRODUCER_MANIFEST_FIELDS))
        self.assertEqual(set(produced_manifest["runtime_knobs"]), recorder.DP_RUNTIME_FIELDS)

        recording = ReplayRecording(
            (RecordedTurn(OperatorMessage("run"), TurnResult()),),
            manifest=produced_manifest,
        )
        run = dp_run(manifest=produced_manifest)
        run["replay_recording"] = recording.to_report_dict()
        compact = recorder.compact_report(dp_report(run))
        self.assertEqual(
            produced_manifest["runtime_knobs"],
            compact["scenarios"][0]["runs"][0]["manifest"]["runtime_knobs"],
        )

    def test_dp_sampling_shapes_track_live_replay_and_driver_producers(self):
        from dp_scenarios.ledger import Manifest
        from dp_scenarios.runner.environment import PinnedVersions

        replay_pins = PinnedVersions(
            skill_pack_version="1.0.0",
            supervisor_version="1.2.3",
            runtime_wheel_version="4.5.6",
            mock_api_version="mock-1",
            canary_claims_hash="sha256:" + "d" * 64,
            agent_sampling_params={"temperature": 0},
        )
        replay_manifest = dp_manifest()
        replay_manifest.update({
            "validation_mode": "replay",
            "agent_model_id": replay_pins.agent_model_id,
            "agent_sampling_params": dict(replay_pins.agent_sampling_params),
        })
        replay_produced = Manifest.from_mapping(replay_manifest, replay=True).to_dict()
        self.assertEqual("PASS", recorder.cell_rows("", dp_report(dp_run(manifest=replay_produced)))[0]["status"])

        live_numeric = copy.deepcopy(dp_manifest())
        live_numeric["agent_sampling_params"] = {"effort": "medium", "temperature": 0}
        with self.assertRaisesRegex(recorder.BenchmarkError, "provider-default"):
            recorder.compact_report(dp_report(dp_run(manifest=live_numeric)))

        driver_manifest = dp_manifest()
        driver_manifest.update({
            "driver_model_id": "gpt-driver",
            "driver_sampling_params": {
                "temperature": 1.25,
                "max_tokens": 128,
                "prompt_hash": "8" * 64,
            },
        })
        driver_produced = Manifest.from_mapping(driver_manifest, replay=False).to_dict()
        self.assertEqual(
            "PASS", recorder.cell_rows("", dp_report(dp_run(manifest=driver_produced)))[0]["status"],
        )

    def test_dp_real_credential_rotation_producer_identifier_is_importable(self):
        """The real scenario declaration may contain credential vocabulary."""

        from dp_scenarios.ledger import Manifest
        from dp_scenarios.scenario import load_scenario

        scenario = load_scenario(
            REPO / "evals" / "dp-scenarios" / "scenarios" / "credential-rotation" / "scenario.yaml"
        )
        manifest_values = dp_manifest(scenario.id)
        manifest_values["agent_model_id"] = "credential-token-model"
        produced_manifest = Manifest.from_mapping(manifest_values, replay=False).to_dict()

        compact = recorder.compact_report(
            dp_report(
                dp_run(scenario_id=scenario.id, manifest=produced_manifest),
                scenario_id=scenario.id,
            )
        )

        self.assertEqual("credential-rotation", scenario.id)
        self.assertEqual(
            "credential-token-model",
            compact["scenarios"][0]["runs"][0]["manifest"]["agent_model_id"],
        )

    def test_dp_retained_manifest_and_sampling_strings_reject_synthetic_secrets_and_paths(self):
        """Every retained string boundary rejects synthetic unsafe material."""

        manifest_fields = sorted(set(recorder.DP_MANIFEST_STRING_FIELDS) | {"driver_model_id"})
        for field in manifest_fields:
            for sentinel in (
                "Bearer synthetic-secret", "token:synthetic-secret", "/private/tmp/synthetic-path",
            ):
                with self.subTest(field=field, sentinel=sentinel):
                    payload = copy.deepcopy(dp_report(dp_run()))
                    payload["scenarios"][0]["runs"][0]["manifest"][field] = sentinel
                    with self.assertRaises(recorder.BenchmarkError) as raised:
                        recorder.compact_report(payload)
                    self.assertNotIn("synthetic-secret", str(raised.exception))
                    self.assertNotIn("synthetic-path", str(raised.exception))

        nested_cases = [
            ("agent effort", lambda manifest, value: manifest["agent_sampling_params"].update(effort=value)),
            ("agent temperature", lambda manifest, value: manifest["agent_sampling_params"].update(temperature=value)),
            ("driver prompt hash", lambda manifest, value: manifest.update(
                driver_model_id="gpt-driver",
                driver_sampling_params={
                    "temperature": 1.0, "max_tokens": 128, "prompt_hash": value,
                },
            )),
            ("transform plan", lambda manifest, value: manifest.update(
                runtime_knobs=enabled_runtime_knobs(),
            ) or manifest["runtime_knobs"]["transform_window"]["arithmetic"].update(naive_plan=value)),
            ("bounded transform plan", lambda manifest, value: manifest.update(
                runtime_knobs=enabled_runtime_knobs(),
            ) or manifest["runtime_knobs"]["transform_window"]["arithmetic"].update(bounded_plan=value)),
            ("transform method", lambda manifest, value: manifest.update(
                runtime_knobs=enabled_runtime_knobs(),
            ) or manifest["runtime_knobs"]["transform_window"]["arithmetic"].update(method=value)),
            ("transform route key", lambda manifest, value: manifest.update(
                runtime_knobs=enabled_runtime_knobs(),
            ) or manifest["runtime_knobs"]["transform_window"]["arithmetic"].update(route_keys=[value])),
            ("broker active fault", lambda manifest, value: manifest.update(
                runtime_knobs=enabled_runtime_knobs(),
            ) or manifest["runtime_knobs"]["broker_fault"].update(active_fault=value)),
            ("broker fault value", lambda manifest, value: manifest.update(
                runtime_knobs=enabled_runtime_knobs(),
            ) or manifest["runtime_knobs"]["broker_fault"].update(faults={"1": value})),
            ("broker entrypoint", lambda manifest, value: manifest.update(
                runtime_knobs=enabled_runtime_knobs(),
            ) or manifest["runtime_knobs"]["broker_fault"].update(entrypoint=value)),
            ("workflow name", lambda manifest, value: manifest.update(
                runtime_knobs=enabled_runtime_knobs(),
            ) or manifest["runtime_knobs"]["workflow_switch"].update(from_workflow=value)),
            ("workflow target", lambda manifest, value: manifest.update(
                runtime_knobs=enabled_runtime_knobs(),
            ) or manifest["runtime_knobs"]["workflow_switch"].update(to_workflow=value)),
            ("workflow assertion", lambda manifest, value: manifest.update(
                runtime_knobs=enabled_runtime_knobs(),
            ) or manifest["runtime_knobs"]["workflow_switch"].update(assertion=value)),
        ]
        for name, mutate in nested_cases:
            for sentinel in (
                "Bearer synthetic-secret", "token:synthetic-secret", "/private/tmp/synthetic-path",
            ):
                with self.subTest(field=name, sentinel=sentinel):
                    payload = copy.deepcopy(dp_report(dp_run()))
                    mutate(payload["scenarios"][0]["runs"][0]["manifest"], sentinel)
                    with self.assertRaises(recorder.BenchmarkError):
                        recorder.compact_report(payload)

    def test_dp_retained_code_fields_reject_value_bearing_sentinels_without_serializing(self):
        """Code fields use the same safe validator without banning vocabulary."""

        sentinel = "token:synthetic-secret"

        def set_probe(payload):
            payload["canary"]["probe"] = {
                "report": valid_supervisor_report(),
                "returncode": 0,
                "stderr": "",
                "supervisor_digest": None,
            }

        def set_canary_issue(payload, field):
            payload["canary"]["verdict"]["issues"] = [{
                "kind": "claim_mismatch",
                "message": "diagnostic message",
                "claim_id": "claim-1",
                "code": "claim/mismatch",
                "skill_file": "src/skill/SKILL.md",
                "line": 1,
            }]
            payload["canary"]["verdict"]["issues"][0][field] = sentinel

        cases = [
            ("ungraded criteria", lambda payload: payload["scenarios"][0]["runs"][0].update(
                ungraded_criteria=[sentinel],
            )),
            ("gate codes", lambda payload: payload["scenarios"][0]["runs"][0]["score"]["gates"]["intake"].update(
                codes=[sentinel],
            )),
            ("waived gate code", lambda payload: payload["scenarios"][0]["runs"][0]["score"].update(
                waived_gates={"intake": sentinel},
            )),
            ("score findings", lambda payload: payload["scenarios"][0]["runs"][0]["score"].update(
                findings=[sentinel],
            )),
            ("diagnostic code", lambda payload: payload["scenarios"][0]["runs"][0]["score"]["gates"]["intake"].update(
                diagnostics=[{"code": sentinel, "detail": "detail", "value": None}],
            )),
            ("qualification reason", lambda payload: payload["scenarios"][0]["runs"][0]["qualification"].update(
                reasons=[sentinel],
            )),
            ("interruption MCP call", lambda payload: payload["scenarios"][0]["runs"][0]["interruption"].update(
                last_mcp_call=sentinel,
            )),
            ("blocked reason code", lambda payload: payload.update(blocked_reason=[{
                "kind": "blocked", "message": "blocked", "claim_id": None,
                "code": sentinel, "skill_file": None, "line": None,
            }])),
            ("canary observed code", lambda payload: payload["canary"]["verdict"].update(
                observed_codes=[sentinel],
            )),
            ("canary issue kind", lambda payload: set_canary_issue(payload, "kind")),
            ("canary issue claim id", lambda payload: set_canary_issue(payload, "claim_id")),
            ("canary issue code", lambda payload: set_canary_issue(payload, "code")),
            ("canary issue skill file", lambda payload: set_canary_issue(payload, "skill_file")),
            ("supervisor stage", lambda payload: (
                set_probe(payload),
                payload["canary"]["probe"]["report"]["stages"][0].update(stage=sentinel),
            )),
            ("supervisor check code", lambda payload: (
                set_probe(payload),
                payload["canary"]["probe"]["report"]["stages"][0]["checks"][0].update(code=sentinel),
            )),
            ("supervisor workflow", lambda payload: (
                set_probe(payload),
                payload["canary"]["probe"]["report"].update(workflow=sentinel),
            )),
            ("supervisor probe id", lambda payload: (
                set_probe(payload),
                payload["canary"]["probe"]["report"].update(probe_id=sentinel),
            )),
            ("replay tool name", lambda payload: payload["scenarios"][0]["runs"][0]["replay_recording"]["turns"][0]["result"].update(
                tool_calls=[{"name": sentinel, "arguments": {}, "result": {}}],
            )),
            ("replay MCP call", lambda payload: payload["scenarios"][0]["runs"][0]["replay_recording"]["turns"][0]["result"].update(
                last_mcp_call=sentinel,
            )),
        ]
        for name, mutate in cases:
            with self.subTest(name=name):
                payload = copy.deepcopy(dp_report(dp_run()))
                mutate(payload)
                compact = None
                with self.assertRaises(recorder.BenchmarkError):
                    compact = recorder.compact_report(payload)
                self.assertIsNone(compact)

    def test_dp_real_tier_report_drifts_through_machine_report_compaction_and_rows(self):
        """Use producer dataclasses and all three pin modes as a report fixture."""

        from dp_scenarios.canary.verdict import Verdict
        from dp_scenarios.grading.gates import GATE_POINTS, GateResult
        from dp_scenarios.grading.score import (
            EfficiencyReport,
            ScoreVector,
            TerminalState as ScoreTerminalState,
        )
        from dp_scenarios.ledger import Manifest, SupervisorFacts
        from dp_scenarios.operator import TerminalState as EngineTerminalState
        from dp_scenarios.operator.openai_driver import driver_prompt_hash
        from dp_scenarios.operator.transport import OperatorMessage, TurnResult
        from dp_scenarios.runner.environment import PinnedVersions
        from dp_scenarios.runner.qualification import (
            QualificationDisposition,
            QualificationRecord,
        )
        from dp_scenarios.runner.report import machine_report
        from dp_scenarios.runner.session import RecordedTurn, ReplayRecording
        from dp_scenarios.runner.tier import (
            CanaryResult,
            ScenarioRun,
            ScenarioSummary,
            TierResult,
        )
        from dp_scenarios.grading.statistics import RepeatabilityReport, RepeatabilityTier

        common = {
            "skill_pack_version": "1.0.0",
            "supervisor_version": "1.2.3",
            "runtime_wheel_version": "4.5.6",
            "mock_api_version": "mock-1",
            "canary_claims_hash": "sha256:" + "d" * 64,
        }
        live_pins = PinnedVersions(
            **common,
            agent_model_id="claude-fable-5",
            agent_sampling_params={"effort": "medium", "temperature": "provider-default"},
        )
        replay_pins = PinnedVersions(
            **common,
            agent_model_id="replay",
            agent_sampling_params={"temperature": 0},
        )
        driver_pins = PinnedVersions(
            **common,
            agent_model_id="claude-fable-5",
            agent_sampling_params={"effort": "medium", "temperature": "provider-default"},
            driver_model_id="gpt-driver",
            driver_sampling_params={
                "temperature": 1.25,
                "max_tokens": 128,
                "prompt_hash": driver_prompt_hash(),
            },
        )

        def manifest_for(pins, *, validation_mode):
            values = dp_manifest()
            values.update({
                "agent_model_id": pins.agent_model_id,
                "agent_sampling_params": dict(pins.agent_sampling_params),
                "driver_model_id": pins.driver_model_id,
                "driver_sampling_params": dict(pins.driver_sampling_params),
                "validation_mode": validation_mode,
                "supervisor_version": pins.supervisor_version,
                "nxd_data_product_wheel_version": pins.runtime_wheel_version,
                "canary_claims_hash": pins.canary_claims_hash,
            })
            return Manifest.from_mapping(values, replay=validation_mode == "replay")

        live_manifest = manifest_for(live_pins, validation_mode="live")
        replay_manifest = manifest_for(replay_pins, validation_mode="replay")
        driver_manifest = manifest_for(driver_pins, validation_mode="live")
        for produced in (live_manifest, replay_manifest, driver_manifest):
            self.assertEqual(set(Manifest.fields), set(produced.to_dict()))
        self.assertEqual({"temperature": 0}, replay_manifest.agent_sampling_params)
        self.assertEqual("gpt-driver", driver_manifest.driver_model_id)

        facts = SupervisorFacts(
            run_id=live_manifest.run_id,
            artifact_id="artifact-1",
            publish_sequence=7,
            per_model_row_counts={"main.model": 3},
            lifecycle_state="terminal",
        )
        fact_mapping = {
            field: getattr(facts, field)
            for field in recorder.DP_SUPERVISOR_FACT_FIELDS
        }
        recording = ReplayRecording(
            (
                RecordedTurn(
                    OperatorMessage("run"),
                    TurnResult(
                        agent_message="done",
                        terminal_result_count=1,
                        terminal_result_subtype="success",
                        terminal_result_is_error=False,
                    ),
                ),
            ),
            manifest=live_manifest.to_dict(),
            supervisor_facts=fact_mapping,
            metadata={"touched_file_contents_redacted": True},
        )
        gates = {
            name: GateResult(name, True, GATE_POINTS[name])
            for name in recorder.DP_GATE_NAMES
        }
        score = ScoreVector(
            gates=gates,
            total=sum(GATE_POINTS[name] for name in recorder.DP_GATE_NAMES),
            hard_gate_flags={
                "honesty": True, "route_fidelity": True, "sentinel": False, "gold_access": False,
            },
            state=ScoreTerminalState.PASSED,
            efficiency=EfficiencyReport(turns=1.0, model_calls=1.0),
        )
        run = ScenarioRun(
            scenario_id=live_manifest.scenario_id,
            epoch=1,
            manifest=live_manifest,
            terminal_state=EngineTerminalState.COMPLETED,
            stop_condition="completed",
            failure_modes=(),
            ungraded_criteria=frozenset(),
            score=score,
            ledger_path="/private/tmp/ledger.json",
            fixture_dir="/private/tmp/fixture",
            ledger_bytes=b"ledger",
            wall_clock_seconds=1.0,
            calls=1,
            transcript_turns=1,
            efficiency=EfficiencyReport(turns=1.0, model_calls=1.0, wall_clock=1.0),
            replay_recording=recording,
            route_fidelity_status="examined",
            route_fidelity_reason="observed",
            evidence_bundle_dir=None,
            bundle_digest=None,
            replay_verification_status="verified",
            replay_verification_reason="verified replay",
            qualification=QualificationRecord(
                QualificationDisposition.QUALIFIED, "verified", "scripted", ("qualified",),
            ),
        )
        tier = TierResult(
            verdict="PASS",
            canary=CanaryResult(
                Verdict("clean", (), ()), claims_hash=live_manifest.canary_claims_hash, package="src",
            ),
            scenarios=(ScenarioSummary(
                live_manifest.scenario_id,
                RepeatabilityReport(RepeatabilityTier.DEMONSTRATED_ONCE, 1, 1, False),
                (run,),
            ),),
            wall_clock_seconds=1.0,
        )

        produced_report = machine_report(tier)
        self.assertEqual("PASS", recorder.cell_rows("", produced_report)[0]["status"])
        compact = recorder.compact_report(produced_report)
        self.assertEqual("PASS", recorder.cell_rows("", compact)[0]["status"])
        self.assertEqual(
            set(recorder.DP_MANIFEST_FIELDS),
            set(compact["scenarios"][0]["runs"][0]["manifest"]),
        )
        self.assertNotIn("publish_sequence", json.dumps(compact))

    def test_dp_unknown_fields_are_rejected_at_each_structured_boundary(self):
        def set_probe(payload):
            run = payload["scenarios"][0]["runs"][0]
            run["replay_recording"]["turns"][0]["result"]["tool_calls"] = [{
                "name": "check_data_product",
                "arguments": {},
                "result": {},
            }]
            payload["canary"]["probe"] = {
                "report": valid_supervisor_report(),
                "returncode": 0,
                "stderr": "",
                "supervisor_digest": None,
            }

        def set_enabled_runtime(payload):
            payload["scenarios"][0]["runs"][0]["manifest"]["runtime_knobs"] = enabled_runtime_knobs()

        def set_facts(payload):
            run = payload["scenarios"][0]["runs"][0]
            run["replay_recording"]["supervisor_facts"] = valid_supervisor_facts(run["manifest"])

        mutations = [
            ("report", lambda value: value.update(extra=1)),
            ("canary", lambda value: value["canary"].update(extra=1)),
            ("canary verdict", lambda value: value["canary"]["verdict"].update(extra=1)),
            ("blocked reason", lambda value: (
                value.update(blocked_reason=[{
                    "kind": "blocked", "message": "blocked", "claim_id": None,
                    "code": "build/blocked", "skill_file": None, "line": None,
                }]),
                value["blocked_reason"][0].update(extra=1),
            )),
            ("canary probe", lambda value: (set_probe(value), value["canary"]["probe"].update(extra=1))),
            ("supervisor report", lambda value: (set_probe(value), value["canary"]["probe"]["report"].update(extra=1))),
            ("supervisor stage", lambda value: (set_probe(value), value["canary"]["probe"]["report"]["stages"][0].update(extra=1))),
            ("supervisor check", lambda value: (set_probe(value), value["canary"]["probe"]["report"]["stages"][0]["checks"][0].update(extra=1))),
            ("supervisor provenance", lambda value: (set_probe(value), value["canary"]["probe"]["report"]["provenance"].update(extra=1))),
            ("canary build", lambda value: (value["canary"].update(build={
                "diagnostic": None, "returncode": 0, "stderr": "", "stdout": "", "supervisor_digest": None,
            }), value["canary"]["build"].update(extra=1))),
            ("scenario", lambda value: value["scenarios"][0].update(extra=1)),
            ("repeatability", lambda value: value["scenarios"][0]["repeatability"].update(extra=1)),
            ("repeatability rate", lambda value: (
                value["scenarios"][0]["repeatability"].update(rates={
                    "intake": {"passed": 1, "examined": 1, "rate": 1.0, "wilson_lower_bound": 1.0},
                }),
                value["scenarios"][0]["repeatability"]["rates"]["intake"].update(extra=1),
            )),
            ("demonstrated once", lambda value: (
                value["scenarios"][0]["repeatability"].update(demonstrated_once={
                    "state": "demonstrated-once", "gates": {"intake": True},
                }),
                value["scenarios"][0]["repeatability"]["demonstrated_once"].update(extra=1),
            )),
            ("run", lambda value: value["scenarios"][0]["runs"][0].update(extra=1)),
            ("score", lambda value: value["scenarios"][0]["runs"][0]["score"].update(extra=1)),
            ("gate", lambda value: value["scenarios"][0]["runs"][0]["score"]["gates"]["intake"].update(extra=1)),
            ("diagnostic", lambda value: (
                value["scenarios"][0]["runs"][0]["score"]["gates"]["intake"].update(
                    diagnostics=[{"code": "diag", "detail": "detail", "value": None}],
                ),
                value["scenarios"][0]["runs"][0]["score"]["gates"]["intake"]["diagnostics"][0].update(extra=1),
            )),
            ("hard gate flags", lambda value: value["scenarios"][0]["runs"][0]["score"]["hard_gate_flags"].update(extra=1)),
            ("efficiency", lambda value: value["scenarios"][0]["runs"][0]["efficiency"].update(extra=1)),
            ("dead wall clock", lambda value: value["scenarios"][0]["runs"][0]["efficiency"].update(wall_clock=1)),
            ("manifest", lambda value: value["scenarios"][0]["runs"][0]["manifest"].update(extra=1)),
            ("agent sampling", lambda value: value["scenarios"][0]["runs"][0]["manifest"]["agent_sampling_params"].update(extra=1)),
            ("driver sampling", lambda value: (
                value["scenarios"][0]["runs"][0]["manifest"].update(
                    driver_model_id="gpt-driver",
                    driver_sampling_params={"temperature": 1.0, "max_tokens": 128, "prompt_hash": "sha256:p"},
                ),
                value["scenarios"][0]["runs"][0]["manifest"]["driver_sampling_params"].update(extra=1),
            )),
            ("runtime", lambda value: value["scenarios"][0]["runs"][0]["manifest"]["runtime_knobs"].update(extra=1)),
            ("dead call-count map", lambda value: value["scenarios"][0]["runs"][0]["manifest"]["runtime_knobs"].update(call_counts={})),
            ("transform disabled", lambda value: value["scenarios"][0]["runs"][0]["manifest"]["runtime_knobs"]["transform_window"].update(extra=1)),
            ("transform arithmetic", lambda value: (
                set_enabled_runtime(value),
                value["scenarios"][0]["runs"][0]["manifest"]["runtime_knobs"]["transform_window"]["arithmetic"].update(extra=1),
            )),
            ("broker disabled", lambda value: value["scenarios"][0]["runs"][0]["manifest"]["runtime_knobs"]["broker_fault"].update(extra=1)),
            ("broker enabled", lambda value: (
                set_enabled_runtime(value),
                value["scenarios"][0]["runs"][0]["manifest"]["runtime_knobs"]["broker_fault"].update(extra=1),
            )),
            ("workflow disabled", lambda value: value["scenarios"][0]["runs"][0]["manifest"]["runtime_knobs"]["workflow_switch"].update(extra=1)),
            ("qualification", lambda value: value["scenarios"][0]["runs"][0]["qualification"].update(extra=1)),
            ("interruption", lambda value: value["scenarios"][0]["runs"][0]["interruption"].update(extra=1)),
            ("route fidelity", lambda value: value["scenarios"][0]["runs"][0]["route_fidelity"].update(extra=1)),
            ("replay", lambda value: value["scenarios"][0]["runs"][0]["replay_recording"].update(extra=1)),
            ("replay manifest", lambda value: value["scenarios"][0]["runs"][0]["replay_recording"]["manifest"].update(extra=1)),
            ("replay turn", lambda value: value["scenarios"][0]["runs"][0]["replay_recording"]["turns"][0].update(extra=1)),
            ("operator message", lambda value: value["scenarios"][0]["runs"][0]["replay_recording"]["turns"][0]["operator_message"].update(extra=1)),
            ("attachment", lambda value: (
                value["scenarios"][0]["runs"][0]["replay_recording"]["turns"][0]["operator_message"].update(
                    attachments=[{"name": "notes.txt", "content": "notes", "kind": "file"}],
                ),
                value["scenarios"][0]["runs"][0]["replay_recording"]["turns"][0]["operator_message"]["attachments"][0].update(extra=1),
            )),
            ("turn result", lambda value: value["scenarios"][0]["runs"][0]["replay_recording"]["turns"][0]["result"].update(extra=1)),
            ("tool call", lambda value: (
                value["scenarios"][0]["runs"][0]["replay_recording"]["turns"][0]["result"].update(tool_calls=[{
                    "name": "check_data_product", "arguments": {}, "result": {},
                }]),
                value["scenarios"][0]["runs"][0]["replay_recording"]["turns"][0]["result"]["tool_calls"][0].update(extra=1),
            )),
            ("touched file", lambda value: (
                value["scenarios"][0]["runs"][0]["replay_recording"]["turns"][0]["result"].update(files_touched=[{
                    "path": "closure/spec.json", "content": None,
                }]),
                value["scenarios"][0]["runs"][0]["replay_recording"]["turns"][0]["result"]["files_touched"][0].update(extra=1),
            )),
            ("replay metadata", lambda value: value["scenarios"][0]["runs"][0]["replay_recording"]["metadata"].update(extra=1)),
            ("supervisor facts", lambda value: (
                set_facts(value),
                value["scenarios"][0]["runs"][0]["replay_recording"]["supervisor_facts"].update(extra=1),
            )),
        ]
        for name, mutate in mutations:
            with self.subTest(name=name):
                self.assert_dp_rejected(mutate, "unknown field")

    def test_dp_nested_types_and_ranges_are_rejected(self):
        def set_enabled(payload):
            payload["scenarios"][0]["runs"][0]["manifest"]["runtime_knobs"] = enabled_runtime_knobs()

        mutations = [
            ("report version type", lambda value: value.update(report_format_version=True)),
            ("scenario list type", lambda value: value.update(scenarios={})),
            ("canary blocking type", lambda value: value["canary"]["verdict"].update(blocking=1)),
            ("canary claims hash shape", lambda value: value["canary"].update(claims_hash="not-a-digest")),
            ("supervisor duration range", lambda value: (
                value["canary"].update(probe={"report": valid_supervisor_report(), "returncode": 0, "stderr": "", "supervisor_digest": None}),
                value["canary"]["probe"]["report"].update(duration_ms=-1),
            )),
            ("supervisor digest shape", lambda value: (
                value["canary"].update(probe={"report": valid_supervisor_report(), "returncode": 0, "stderr": "", "supervisor_digest": "not-a-digest"}),
            )),
            ("supervisor stage status", lambda value: (
                value["canary"].update(probe={"report": valid_supervisor_report(), "returncode": 0, "stderr": "", "supervisor_digest": None}),
                value["canary"]["probe"]["report"]["stages"][0].update(status="passed"),
            )),
            ("scenario id type", lambda value: value["scenarios"][0].update(scenario_id=[])),
            ("epoch range", lambda value: value["scenarios"][0]["runs"][0].update(epoch=0)),
            ("terminal state vocabulary", lambda value: value["scenarios"][0]["runs"][0].update(terminal_state="finished")),
            ("failure mode vocabulary", lambda value: value["scenarios"][0]["runs"][0].update(failure_modes=["unknown-mode"])),
            ("ungraded criteria type", lambda value: value["scenarios"][0]["runs"][0].update(ungraded_criteria="criterion")),
            ("score total type", lambda value: value["scenarios"][0]["runs"][0]["score"].update(total=True)),
            ("score total range", lambda value: value["scenarios"][0]["runs"][0]["score"].update(total=-1)),
            ("score points range", lambda value: value["scenarios"][0]["runs"][0]["score"]["gates"]["intake"].update(points=-1)),
            ("scoreable max range", lambda value: value["scenarios"][0]["runs"][0]["score"].update(scoreable_max=-1)),
            ("score threshold range", lambda value: value["scenarios"][0]["runs"][0]["score"].update(threshold=0)),
            ("score passed type", lambda value: value["scenarios"][0]["runs"][0]["score"]["gates"]["intake"].update(passed=1)),
            ("score codes type", lambda value: value["scenarios"][0]["runs"][0]["score"]["gates"]["intake"].update(codes="code")),
            ("diagnostics type", lambda value: value["scenarios"][0]["runs"][0]["score"]["gates"]["intake"].update(diagnostics={})),
            ("hard flag type", lambda value: value["scenarios"][0]["runs"][0]["score"]["hard_gate_flags"].update(honesty=1)),
            ("efficiency range", lambda value: value["scenarios"][0]["runs"][0]["efficiency"].update(turns=-1)),
            ("observed calls type", lambda value: value["scenarios"][0]["runs"][0]["efficiency"].update(observed_calls=True)),
            ("qualification disposition", lambda value: value["scenarios"][0]["runs"][0]["qualification"].update(disposition=[])),
            ("qualification reasons type", lambda value: value["scenarios"][0]["runs"][0]["qualification"].update(reasons="reason")),
            ("interruption reason vocabulary", lambda value: value["scenarios"][0]["runs"][0]["interruption"].update(failure_reason="unknown")),
            ("route status vocabulary", lambda value: value["scenarios"][0]["runs"][0]["route_fidelity"].update(status="passed")),
            ("manifest turn budget", lambda value: value["scenarios"][0]["runs"][0]["manifest"].update(turn_budget=0)),
            ("manifest trial index", lambda value: value["scenarios"][0]["runs"][0]["manifest"].update(trial_index=-1)),
            ("manifest fixture seed type", lambda value: value["scenarios"][0]["runs"][0]["manifest"].update(fixture_seed=True)),
            ("manifest tier type", lambda value: value["scenarios"][0]["runs"][0]["manifest"].update(tier=[])),
            ("manifest hash shape", lambda value: value["scenarios"][0]["runs"][0]["manifest"].update(fixture_dir_hash="not-a-digest")),
            ("manifest supervisor version shape", lambda value: value["scenarios"][0]["runs"][0]["manifest"].update(supervisor_version="supervisor-one")),
            ("manifest wheel version shape", lambda value: value["scenarios"][0]["runs"][0]["manifest"].update(nxd_data_product_wheel_version="wheel-one")),
            ("manifest mock version shape", lambda value: value["scenarios"][0]["runs"][0]["manifest"].update(mock_api_version="mock-one")),
            ("manifest timestamp shape", lambda value: value["scenarios"][0]["runs"][0]["manifest"].update(fixture_base_instant="2026-09-08")),
            ("manifest identifier shape", lambda value: value["scenarios"][0]["runs"][0]["manifest"].update(run_id="run id")),
            ("manifest model identifier", lambda value: value["scenarios"][0]["runs"][0]["manifest"].update(agent_model_id="model id")),
            ("agent effort type", lambda value: value["scenarios"][0]["runs"][0]["manifest"]["agent_sampling_params"].update(effort=[])),
            ("agent temperature live", lambda value: value["scenarios"][0]["runs"][0]["manifest"]["agent_sampling_params"].update(temperature=0)),
            ("agent temperature replay range", lambda value: (
                value["scenarios"][0]["runs"][0]["manifest"].update(
                    validation_mode="replay",
                    agent_sampling_params={"temperature": 2.01},
                ),
            )),
            ("driver temperature lower", lambda value: (
                value["scenarios"][0]["runs"][0]["manifest"].update(driver_model_id="driver", driver_sampling_params={"temperature": -0.01, "max_tokens": 1, "prompt_hash": "sha256:p"}),
            )),
            ("driver temperature upper", lambda value: value["scenarios"][0]["runs"][0]["manifest"].update(driver_model_id="driver", driver_sampling_params={"temperature": 2.01, "max_tokens": 1, "prompt_hash": "sha256:p"})),
            ("driver temperature type", lambda value: value["scenarios"][0]["runs"][0]["manifest"].update(driver_model_id="driver", driver_sampling_params={"temperature": True, "max_tokens": 1, "prompt_hash": "sha256:p"})),
            ("driver max tokens", lambda value: value["scenarios"][0]["runs"][0]["manifest"].update(driver_model_id="driver", driver_sampling_params={"temperature": 1.0, "max_tokens": 0, "prompt_hash": "sha256:p"})),
            ("driver max tokens type", lambda value: value["scenarios"][0]["runs"][0]["manifest"].update(driver_model_id="driver", driver_sampling_params={"temperature": 1.0, "max_tokens": True, "prompt_hash": "sha256:p"})),
            ("driver prompt hash", lambda value: value["scenarios"][0]["runs"][0]["manifest"].update(driver_model_id="driver", driver_sampling_params={"temperature": 1.0, "max_tokens": 1, "prompt_hash": 4})),
            ("driver prompt hash shape", lambda value: value["scenarios"][0]["runs"][0]["manifest"].update(driver_model_id="driver", driver_sampling_params={"temperature": 1.0, "max_tokens": 1, "prompt_hash": "not-a-digest"})),
            ("runtime schema version", lambda value: value["scenarios"][0]["runs"][0]["manifest"]["runtime_knobs"].update(schema_version=True)),
            ("transform enabled type", lambda value: value["scenarios"][0]["runs"][0]["manifest"]["runtime_knobs"]["transform_window"].update(enabled="false")),
            ("transform arithmetic count range", lambda value: (set_enabled(value), value["scenarios"][0]["runs"][0]["manifest"]["runtime_knobs"]["transform_window"]["arithmetic"]["naive_calls"].update({"<total>": 0}))),
            ("transform arithmetic total", lambda value: (set_enabled(value), value["scenarios"][0]["runs"][0]["manifest"]["runtime_knobs"]["transform_window"]["arithmetic"].update(naive_total_calls=7))),
            ("transform arithmetic latency", lambda value: (set_enabled(value), value["scenarios"][0]["runs"][0]["manifest"]["runtime_knobs"]["transform_window"]["arithmetic"].update(per_call_latency_ms=0))),
            ("transform arithmetic window", lambda value: (set_enabled(value), value["scenarios"][0]["runs"][0]["manifest"]["runtime_knobs"]["transform_window"]["arithmetic"].update(window_ms=0))),
            ("transform arithmetic route keys", lambda value: (set_enabled(value), value["scenarios"][0]["runs"][0]["manifest"]["runtime_knobs"]["transform_window"]["arithmetic"].update(route_keys=["z", "a"]))),
            ("transform arithmetic bounds type", lambda value: (set_enabled(value), value["scenarios"][0]["runs"][0]["manifest"]["runtime_knobs"]["transform_window"]["arithmetic"].update(bounds_hold=1))),
            ("transform arithmetic method", lambda value: (set_enabled(value), value["scenarios"][0]["runs"][0]["manifest"]["runtime_knobs"]["transform_window"]["arithmetic"].update(method="wall_clock"))),
            ("broker attempt range", lambda value: value["scenarios"][0]["runs"][0]["manifest"]["runtime_knobs"]["broker_fault"].update(active_attempt=0)),
            ("broker active fault type", lambda value: (set_enabled(value), value["scenarios"][0]["runs"][0]["manifest"]["runtime_knobs"]["broker_fault"].update(active_fault=[]))),
            ("broker faults type", lambda value: (set_enabled(value), value["scenarios"][0]["runs"][0]["manifest"]["runtime_knobs"]["broker_fault"].update(faults=[]))),
            ("broker bind timeout", lambda value: (set_enabled(value), value["scenarios"][0]["runs"][0]["manifest"]["runtime_knobs"]["broker_fault"].update(bind_timeout_s=0))),
            ("broker entrypoint", lambda value: (set_enabled(value), value["scenarios"][0]["runs"][0]["manifest"]["runtime_knobs"]["broker_fault"].update(entrypoint="real"))),
            ("workflow enabled type", lambda value: value["scenarios"][0]["runs"][0]["manifest"]["runtime_knobs"]["workflow_switch"].update(enabled="yes")),
            ("workflow names equal", lambda value: (set_enabled(value), value["scenarios"][0]["runs"][0]["manifest"]["runtime_knobs"]["workflow_switch"].update(from_workflow="same", to_workflow="same"))),
            ("workflow assertion", lambda value: (set_enabled(value), value["scenarios"][0]["runs"][0]["manifest"]["runtime_knobs"]["workflow_switch"].update(assertion="answered"))),
            ("replay format version", lambda value: value["scenarios"][0]["runs"][0]["replay_recording"].update(format_version=2)),
            ("bundle digest shape", lambda value: value["scenarios"][0]["runs"][0].update(bundle_digest="not-a-digest")),
            ("replay turns type", lambda value: value["scenarios"][0]["runs"][0]["replay_recording"].update(turns={})),
            ("replay metadata type", lambda value: value["scenarios"][0]["runs"][0]["replay_recording"].update(metadata=[])),
            ("supervisor facts type", lambda value: value["scenarios"][0]["runs"][0]["replay_recording"].update(supervisor_facts=[])),
            ("supervisor facts counts", lambda value: (
                value["scenarios"][0]["runs"][0]["replay_recording"].update(
                    supervisor_facts=valid_supervisor_facts(value["scenarios"][0]["runs"][0]["manifest"]),
                ),
                value["scenarios"][0]["runs"][0]["replay_recording"]["supervisor_facts"].update(per_model_row_counts=[]),
            )),
            ("supervisor facts publish boolean", lambda value: (
                value["scenarios"][0]["runs"][0]["replay_recording"].update(
                    supervisor_facts=valid_supervisor_facts(value["scenarios"][0]["runs"][0]["manifest"]),
                ),
                value["scenarios"][0]["runs"][0]["replay_recording"]["supervisor_facts"].update(publish_sequence=True),
            )),
            ("supervisor facts publish shape", lambda value: (
                value["scenarios"][0]["runs"][0]["replay_recording"].update(
                    supervisor_facts=valid_supervisor_facts(value["scenarios"][0]["runs"][0]["manifest"]),
                ),
                value["scenarios"][0]["runs"][0]["replay_recording"]["supervisor_facts"].update(publish_sequence=[]),
            )),
            ("supervisor facts row boolean", lambda value: (
                value["scenarios"][0]["runs"][0]["replay_recording"].update(
                    supervisor_facts=valid_supervisor_facts(value["scenarios"][0]["runs"][0]["manifest"]),
                ),
                value["scenarios"][0]["runs"][0]["replay_recording"]["supervisor_facts"]["per_model_row_counts"].update({"main.model": True}),
            )),
            ("supervisor facts row shape", lambda value: (
                value["scenarios"][0]["runs"][0]["replay_recording"].update(
                    supervisor_facts=valid_supervisor_facts(value["scenarios"][0]["runs"][0]["manifest"]),
                ),
                value["scenarios"][0]["runs"][0]["replay_recording"]["supervisor_facts"]["per_model_row_counts"].update({"main.model": {}}),
            )),
            ("operator message text", lambda value: value["scenarios"][0]["runs"][0]["replay_recording"]["turns"][0]["operator_message"].update(text=1)),
            ("attachment content envelope", lambda value: (
                value["scenarios"][0]["runs"][0]["replay_recording"]["turns"][0]["operator_message"].update(attachments=[{"name": "x", "content": {"__bytes__": "%%%"}, "kind": "file"}]),
            )),
            ("turn result terminal count", lambda value: value["scenarios"][0]["runs"][0]["replay_recording"]["turns"][0]["result"].update(terminal_result_count=-1)),
            ("turn result terminal error", lambda value: value["scenarios"][0]["runs"][0]["replay_recording"]["turns"][0]["result"].update(terminal_result_is_error="false")),
            ("touched file path envelope", lambda value: (
                value["scenarios"][0]["runs"][0]["replay_recording"]["turns"][0]["result"].update(files_touched=[{"path": {"__path__": 3}, "content": None}]),
            )),
            ("repeatability epochs", lambda value: value["scenarios"][0]["repeatability"].update(required_epochs=0)),
            ("repeatability rate range", lambda value: (
                value["scenarios"][0]["repeatability"].update(rates={"intake": {"passed": 1, "examined": 1, "rate": 1.1, "wilson_lower_bound": 0.5}}),
            )),
            ("repeatability rate type", lambda value: (
                value["scenarios"][0]["repeatability"].update(rates={"intake": {"passed": True, "examined": 1, "rate": 0.5, "wilson_lower_bound": 0.5}}),
            )),
        ]
        for name, mutate in mutations:
            with self.subTest(name=name):
                self.assert_dp_rejected(mutate)

    def test_dp_terminal_and_score_statuses_are_fail_closed(self):
        for state, expected in (("passed", "PASS"), ("failed", "FAIL")):
            with self.subTest(state=state):
                self.assertEqual(expected, recorder.cell_rows("", dp_report(dp_run(score_state=state)))[0]["status"])
        for state in ("invalid", "ungraded", "automatic zero"):
            with self.subTest(state=state):
                self.assertEqual("ERROR", recorder.cell_rows("", dp_report(dp_run(score_state=state)))[0]["status"])
        invalid_run = dp_run(score_state="invalid")
        invalid_run["score"]["total"] = None
        invalid_run["qualification"]["disposition"] = "INVALID"
        self.assertEqual("ERROR", recorder.cell_rows("", dp_report(invalid_run))[0]["status"])
        for terminal_state in ("sentinel_trip", "environment_wedge", "script_exhausted", "turn_timeout"):
            with self.subTest(terminal_state=terminal_state):
                self.assertEqual("ERROR", recorder.cell_rows("", dp_report(dp_run(terminal_state=terminal_state)))[0]["status"])
        for interrupted in ("sentinel_trip", "environment_wedge", "turn_timeout"):
            with self.subTest(stop_condition=interrupted):
                run = dp_run()
                run["stop_condition"] = interrupted
                self.assertEqual("ERROR", recorder.cell_rows("", dp_report(run))[0]["status"])
            with self.subTest(failure_mode=interrupted):
                run = dp_run()
                run["failure_modes"] = [interrupted]
                self.assertEqual("ERROR", recorder.cell_rows("", dp_report(run))[0]["status"])

    def test_dp_contradictory_completion_evidence_is_independently_an_error(self):
        mutations = [
            ("sentinel hard flag", lambda run: run["score"]["hard_gate_flags"].update(sentinel=True)),
            ("invalid qualification", lambda run: run["qualification"].update(disposition="INVALID")),
            ("replay environment wedge", lambda run: run["replay_recording"]["turns"][0]["result"].update(environment_wedged=True)),
            ("replay turn timeout", lambda run: run["replay_recording"]["turns"][0]["result"].update(turn_timed_out=True)),
            ("terminal result count", lambda run: run["replay_recording"]["turns"][0]["result"].update(terminal_result_count=2)),
            ("terminal result subtype", lambda run: run["replay_recording"]["turns"][0]["result"].update(terminal_result_subtype="error")),
            ("terminal result is_error", lambda run: run["replay_recording"]["turns"][0]["result"].update(terminal_result_is_error=True)),
            ("empty final agent message with transcript", lambda run: run["replay_recording"]["turns"][0]["result"].update(agent_message="", transcript_delta="observed")),
            ("replay turn failure reason", lambda run: run["replay_recording"]["turns"][0]["result"].update(failure_reason="child_exited_early")),
            ("turn budget exceeded", lambda run: run.update(failure_modes=["turn_budget_exceeded"])),
        ]
        for name, mutate in mutations:
            with self.subTest(name=name):
                run = dp_run()
                mutate(run)
                self.assertEqual("ERROR", recorder.cell_rows("", dp_report(run))[0]["status"])

    def test_dp_pairing_rejects_mismatched_pins(self):
        scenario_id = "crm-pipeline"
        before_manifest = dp_manifest(
            scenario_id, skill_pack_version="0.44.0", run_id="before-run",
        )
        after_manifest = dp_manifest(
            scenario_id, skill_pack_version="0.45.0", run_id="after-run",
        )
        after_manifest["runtime_knobs"] = {
            **after_manifest["runtime_knobs"], "fault": {"enabled": True},
        }
        reports = {
            "before-v0.44.0": dp_report(
                dp_run(scenario_id, manifest=before_manifest), scenario_id=scenario_id,
            ),
            "after-v0.45.0": dp_report(
                dp_run(scenario_id, manifest=after_manifest), scenario_id=scenario_id,
            ),
        }
        tags = {key: key for key in reports}

        with self.assertRaisesRegex(recorder.BenchmarkError, "runtime_knobs"):
            recorder.validate_dp_comparability(reports, tags)

    def test_dp_pairing_requires_complete_unique_pinned_arms(self):
        scenario_id = "finance-close"

        def paired_reports(before_runs, after_runs):
            reports = {
                "before": dp_report(*before_runs, scenario_id=scenario_id),
                "after": dp_report(*after_runs, scenario_id=scenario_id),
            }
            return reports, {"before": "before-v1", "after": "after-v2"}

        before_manifest = dp_manifest(
            scenario_id, skill_pack_version="1.0.0", run_id="before-run",
        )
        after_manifest = dp_manifest(
            scenario_id, skill_pack_version="2.0.0", run_id="after-run",
        )
        before_manifest["session_root"] = "/private/tmp/before-output"
        after_manifest["session_root"] = "/private/tmp/after-output"
        before = dp_run(scenario_id, manifest=before_manifest)
        after = dp_run(scenario_id, manifest=after_manifest)
        reports, tags = paired_reports([before], [after])
        recorder.validate_dp_comparability(reports, tags)

        with self.subTest("missing pair"):
            with self.assertRaisesRegex(recorder.BenchmarkError, "missing after pairs"):
                recorder.validate_dp_comparability(
                    {"before": reports["before"]}, {"before": "before-v1"},
                )

        with self.subTest("duplicate tags"):
            with self.assertRaisesRegex(recorder.BenchmarkError, "duplicate dp-scenarios report tag"):
                recorder.validate_dp_comparability(
                    {"left": reports["before"], "right": reports["after"]},
                    {"left": "before-v1", "right": "before-v1"},
                )

        with self.subTest("missing pin"):
            missing_manifest = dict(after_manifest)
            missing_manifest.pop("session_config_sha256")
            missing_reports, missing_tags = paired_reports(
                [before], [dp_run(scenario_id, manifest=missing_manifest)],
            )
            with self.assertRaisesRegex(recorder.BenchmarkError, "session_config_sha256"):
                recorder.validate_dp_comparability(missing_reports, missing_tags)

        with self.subTest("mixed arm pins"):
            before_epoch_2_manifest = dp_manifest(
                scenario_id, epoch=2, skill_pack_version="1.1.0", run_id="before-run-2",
            )
            after_epoch_2_manifest = dp_manifest(
                scenario_id, epoch=2, skill_pack_version="2.0.0", run_id="after-run-2",
            )
            mixed_reports, mixed_tags = paired_reports(
                [before, dp_run(scenario_id, epoch=2, manifest=before_epoch_2_manifest)],
                [after, dp_run(scenario_id, epoch=2, manifest=after_epoch_2_manifest)],
            )
            with self.assertRaisesRegex(recorder.BenchmarkError, "mixed skill_pack_version"):
                recorder.validate_dp_comparability(mixed_reports, mixed_tags)

    def test_old_report_rows_and_compaction_are_unchanged(self):
        legacy_result = result("legacy", agent_model="run-model")
        legacy_result["metrics"]["final_answer"] = "drop only this field"
        legacy = report(legacy_result, agent_model="fallback-model")
        legacy["metadata"] = {"arbitrary": "still retained"}

        rows = recorder.cell_rows("before-old", legacy)
        compact = recorder.compact_report(legacy)

        self.assertEqual("current_pack", rows[0]["skill_set"])
        self.assertEqual("legacy", rows[0]["scenario"])
        self.assertEqual("PASS", rows[0]["status"])
        self.assertEqual("run-model", rows[0]["agent_model"])
        self.assertEqual({"arbitrary": "still retained"}, compact["metadata"])
        self.assertNotIn("transcript", compact["results"][0])
        self.assertNotIn("final_answer", compact["results"][0]["metrics"])

    def test_hand_authored_no_eval_and_malformed_entries(self):
        valid = {
            "id": "2026-08-02-no-eval", "date": "2026-08-02", "label": "diagnostic wording",
            "plugin_version": "9.9.9", "status": "NO_EVAL", "scenarios": [], "record": None,
        }
        recorder.ENTRIES_DIR.mkdir(parents=True)
        carrying_test = self.carrying_test()
        (recorder.ENTRIES_DIR / "2026-08-02-no-eval.md").write_text(
            recorder.write_frontmatter(valid)
            + "# Benchmark — diagnostic wording\n\n## Notes\n\nNo eval arm exists because the diagnostic message moved.\n\n"
            + f"## Evidence\n\nCarrying tests: `{carrying_test}`.\n",
            encoding="utf-8",
        )
        self.assertEqual(0, self.invoke("--rebuild-index"))
        bad = recorder.ENTRIES_DIR / "bad.md"
        bad.write_text(
            "---\nid: \"different\"\ndate: \"2026-99-99\"\nlabel: \"bad\"\nplugin_version: \"9\"\n"
            "status: \"PASS\"\nscenarios:\n  - \"x\"\nrecord: \"../records/different.json\"\nunknown: \"x\"\n---\n# Benchmark — bad\n",
            encoding="utf-8",
        )
        self.assertEqual(2, self.invoke("--check"))

    def test_bad_measured_entry_is_rejected(self):
        identifier = "2026-08-03-bad-measured"
        frontmatter = {
            "id": identifier, "date": "2026-08-03", "label": "bad measured",
            "plugin_version": "9.9.9", "status": "PASS", "scenarios": ["scenario"],
            "record": f"../records/{identifier}.json",
        }
        recorder.ENTRIES_DIR.mkdir(parents=True)
        (recorder.ENTRIES_DIR / f"{identifier}.md").write_text(
            recorder.write_frontmatter(frontmatter)
            + "# Benchmark — bad measured\n\n## Results\n\n| x |\n|---|\n| x |\n\n"
            + "## Notes\n\nMeasured.\n\n## Evidence\n\n"
            + f"Compact report: [`../records/{identifier}.json`](../records/{identifier}.json)\n",
            encoding="utf-8",
        )
        recorder.RECORDS_DIR.mkdir()
        (recorder.RECORDS_DIR / f"{identifier}.json").write_text(
            json.dumps({"id": identifier, "date": "2026-08-03", "label": "bad measured",
                        "plugin_version": "9.9.9", "reports": {}}),
            encoding="utf-8",
        )
        self.assertEqual(2, self.invoke("--check"))

    def test_no_eval_requires_test_evidence(self):
        frontmatter = {
            "id": "2026-08-03-no-evidence", "date": "2026-08-03", "label": "no evidence",
            "plugin_version": "9.9.9", "status": "NO_EVAL", "scenarios": [], "record": None,
        }
        recorder.ENTRIES_DIR.mkdir(parents=True)
        (recorder.ENTRIES_DIR / "2026-08-03-no-evidence.md").write_text(
            recorder.write_frontmatter(frontmatter)
            + "# Benchmark — no evidence\n\n## Notes\n\nNo eval arm can distinguish this.\n\n"
            + "## Evidence\n\nNo evidence was recorded.\n",
            encoding="utf-8",
        )
        self.assertEqual(2, self.invoke("--check"))

    def test_measured_body_tampering_and_bad_semver_are_rejected(self):
        source = self.write_report("source.json", report(result()))
        self.assertEqual(0, self.invoke("--date", "2026-08-03", "--label", "body", "--report", str(source)))
        entry = recorder.ENTRIES_DIR / "2026-08-03-body.md"
        entry.write_text(entry.read_text(encoding="utf-8").replace("Measured benchmark evidence.", "tampered notes"), encoding="utf-8")
        self.assertEqual(2, self.invoke("--check"))
        entry.write_text(entry.read_text(encoding="utf-8").replace("tampered notes", "Measured benchmark evidence.").replace('plugin_version: "9.9.9"', 'plugin_version: "9.9"'), encoding="utf-8")
        self.assertEqual(2, self.invoke("--check"))

    def test_unicode_line_separators_round_trip_and_literal_frontmatter_rejects(self):
        source = self.write_report("source.json", report(result("a\u2028b")))
        self.assertEqual(0, self.invoke("--date", "2026-08-03", "--label", "label\u2028separator", "--notes", "note\u0085line", "--report", str(source)))
        entry = next(recorder.ENTRIES_DIR.glob("*.md"))
        text = entry.read_text(encoding="utf-8")
        self.assertIn("\\u2028", text, "frontmatter must not contain a literal line separator")
        self.assertIn("a<br>b", text)
        self.assertEqual(0, self.invoke("--check"))
        entry.write_text(text.replace("\\u2028", "\u2028", 1), encoding="utf-8")
        self.assertEqual(2, self.invoke("--check"))

    def test_mid_write_failure_rolls_back_and_publishes_by_link(self):
        source = self.write_report("source.json", report(result()))
        real_publish = recorder.atomic_publish
        calls = []

        def fail_second(staged, path, content):
            calls.append(path)
            if len(calls) == 2:
                raise recorder.BenchmarkError("injected write failure")
            return real_publish(staged, path, content)

        with mock.patch.object(recorder, "atomic_publish", side_effect=fail_second):
            self.assertEqual(2, self.invoke("--date", "2026-08-03", "--label", "rollback", "--report", str(source)))
        self.assertEqual([], list(recorder.ENTRIES_DIR.glob("*.md")))
        self.assertEqual([], list(recorder.RECORDS_DIR.glob("*.json")))
        lock_fd = recorder.os.open(recorder.BENCH_DIR / ".benchmark-index.lock", recorder.os.O_WRONLY | recorder.os.O_CREAT)
        try:
            recorder.fcntl.flock(lock_fd, recorder.fcntl.LOCK_EX | recorder.fcntl.LOCK_NB)
        finally:
            recorder.os.close(lock_fd)

        links = []
        real_link = recorder.os.link

        def observe_link(source_path, target_path, *args):
            links.append((Path(source_path), Path(target_path)))
            return real_link(source_path, target_path, *args)

        with mock.patch.object(recorder.os, "link", side_effect=observe_link):
            self.assertEqual(0, self.invoke("--date", "2026-08-03", "--label", "exclusive", "--report", str(source)))
        self.assertEqual(2, len(links))
        self.assertTrue(all(source.parent == recorder.staging_dir() for source, _ in links))

    def test_keyboard_interrupt_after_first_publish_rolls_back(self):
        source = self.write_report("source.json", report(result()))
        real_publish = recorder.atomic_publish
        calls = []

        def interrupt_second(staged, path, content):
            calls.append(path)
            if len(calls) == 2:
                raise KeyboardInterrupt()
            return real_publish(staged, path, content)

        with mock.patch.object(recorder, "atomic_publish", side_effect=interrupt_second):
            with self.assertRaises(KeyboardInterrupt):
                self.invoke("--date", "2026-08-03", "--label", "interrupt", "--report", str(source))
        self.assertEqual([], list(recorder.ENTRIES_DIR.glob("*.md")))
        self.assertEqual([], list(recorder.RECORDS_DIR.glob("*.json")))
        self.assertFalse(recorder.publication_marker().exists())
        self.assertFalse(list(recorder.staging_dir().glob("*")))

    def test_stale_marker_and_lock_file_recover_partial_publication(self):
        identifier = "2026-08-03-recover"
        record_text = '{"recovered": true}\n'
        entry_text = "entry\n"
        recorder.RECORDS_DIR.mkdir(parents=True)
        record_path = recorder.RECORDS_DIR / f"{identifier}.json"
        record_path.write_text(record_text, encoding="utf-8")
        marker = {
            "schema": "benchmark-publication-v2", "id": identifier,
            "artifacts": [
                {"path": f"records/{identifier}.json", "sha256": recorder.sha256(record_text)},
                {"path": f"entries/{identifier}.md", "sha256": recorder.sha256(entry_text)},
            ],
        }
        recorder.publication_marker().parent.mkdir(parents=True, exist_ok=True)
        recorder.publication_marker().write_text(json.dumps(marker), encoding="utf-8")
        # A leftover pathname from an old process must not block flock recovery.
        (recorder.BENCH_DIR / ".benchmark-index.lock").write_text("stale pid", encoding="utf-8")
        self.assertEqual(0, self.invoke("--rebuild-index"))
        self.assertFalse(record_path.exists())
        self.assertFalse(recorder.publication_marker().exists())
        self.assertFalse((recorder.ENTRIES_DIR / f"{identifier}.md").exists())

    def test_truncated_transaction_owned_final_recovers(self):
        identifier = "2026-08-03-truncated"
        intended_record = '{"complete": true}\n'
        intended_entry = "complete entry\n"
        recorder.RECORDS_DIR.mkdir(parents=True)
        record_path = recorder.RECORDS_DIR / f"{identifier}.json"
        record_path.write_text('{"truncated"', encoding="utf-8")
        marker = {
            "schema": "benchmark-publication-v2", "id": identifier,
            "artifacts": [
                {"path": f"records/{identifier}.json", "sha256": recorder.sha256(intended_record)},
                {"path": f"entries/{identifier}.md", "sha256": recorder.sha256(intended_entry)},
            ],
        }
        recorder.publication_marker().write_text(json.dumps(marker), encoding="utf-8")
        self.assertEqual(0, self.invoke("--rebuild-index"))
        self.assertFalse(record_path.exists())
        self.assertFalse(recorder.publication_marker().exists())

    def test_no_eval_test_paths_cannot_traverse_or_escape_symlinks(self):
        carrying = self.carrying_test("test_inside.py")
        base = {
            "date": "2026-08-03", "label": "path safety", "plugin_version": "9.9.9",
            "status": "NO_EVAL", "scenarios": [], "record": None,
        }

        def write_no_eval(identifier, evidence):
            values = base | {"id": identifier}
            recorder.ENTRIES_DIR.mkdir(parents=True, exist_ok=True)
            (recorder.ENTRIES_DIR / f"{identifier}.md").write_text(
                recorder.write_frontmatter(values)
                + "# Benchmark — path safety\n\n## Notes\n\nNo eval arm exists.\n\n"
                + f"## Evidence\n\n{evidence}\n", encoding="utf-8")

        write_no_eval("2026-08-03-traversal", f"Carrying test: `{carrying.replace('tests/', 'tests/../tests/')}`.")
        self.assertEqual(2, self.invoke("--check"))
        (recorder.ENTRIES_DIR / "2026-08-03-traversal.md").unlink()

        with tempfile.TemporaryDirectory() as outside_dir:
            outside = Path(outside_dir) / "test_outside.py"
            outside.write_text("# outside\n", encoding="utf-8")
            escaped = recorder.ENTRIES_DIR / "test_escape.py"
            escaped.parent.mkdir(parents=True, exist_ok=True)
            escaped.symlink_to(outside)
            write_no_eval("2026-08-03-symlink", "Carrying test: `evals/benchmarks/entries/test_escape.py`.")
            self.assertEqual(2, self.invoke("--check"))


if __name__ == "__main__":
    unittest.main()
