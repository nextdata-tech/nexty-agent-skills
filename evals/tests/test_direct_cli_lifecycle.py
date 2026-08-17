import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).parents[2]
SKILL = ROOT / "src" / "nxd-run-job-loop" / "SKILL.md"
REFERENCE = ROOT / "src" / "nxd-run-job-loop" / "reference" / "direct-cli-lifecycle.md"
VERIFIER = ROOT / "evals" / "public" / "job-loop-serve-query-refine" / "fixtures" / "check_job_loop.py"
EXPORT_VERIFIER = ROOT / "evals" / "public" / "job-loop-export-handoff" / "fixtures" / "check_job_loop.py"
DESKTOP_SUPERVISOR = ROOT / "evals" / "tools" / "desktop_supervisor.py"


def _load_verifier():
    spec = importlib.util.spec_from_file_location("job_loop_verifier", VERIFIER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_direct_cli_lifecycle_is_bounded_and_publication_receipt_driven():
    skill = SKILL.read_text(encoding="utf-8")
    reference = REFERENCE.read_text(encoding="utf-8")
    text = f"{skill}\n{reference}"

    for required in (
        "capture the task id and the output path",
        "bounded intervals",
        "published=yes",
        "run `status` and `describe`",
        "inspect_run",
        "empty output",
        "supervisor SQLite state",
    ):
        assert required in text, f"direct CLI lifecycle guidance lost: {required}"

    # A shell spin-loop was the observed failure mode. Keep the shipped
    # procedure from accidentally reintroducing one as executable guidance.
    assert "do :; done" not in text
    assert "tail -f" in text  # it must be named as forbidden, not omitted.


def test_job_loop_verifier_resolves_content_addressed_definition_ids(tmp_path):
    verifier = _load_verifier()
    snapshot = tmp_path / "state" / "definitions" / "sha256-v1" / "abc123"
    snapshot.mkdir(parents=True)

    assert verifier.definition_path(
        tmp_path / "state", "sha256-v1:abc123"
    ) == snapshot


def test_all_resume_verifiers_resolve_content_addressed_definition_ids(tmp_path):
    shared = _load(DESKTOP_SUPERVISOR, "desktop_supervisor_definition_resolver")
    export = _load(EXPORT_VERIFIER, "export_handoff_definition_resolver")
    data_dir = tmp_path / "state"
    snapshot = data_dir / "definitions" / "sha256-v1" / "abc123"
    snapshot.mkdir(parents=True)
    (snapshot / "spec.py").write_text("# fixture\n", encoding="utf-8")

    assert shared.definition_path(data_dir, "sha256-v1:abc123") == snapshot
    assert shared.definition_snapshot(data_dir, "sha256-v1:abc123") == snapshot
    assert export.definition_path(data_dir, "sha256-v1:abc123") == snapshot
