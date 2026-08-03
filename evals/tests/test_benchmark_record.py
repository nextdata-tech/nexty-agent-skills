"""Stdlib-only contract tests for the benchmark entry migration."""
from __future__ import annotations

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
