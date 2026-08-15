import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).parents[2]
SKILL = ROOT / "src" / "nxd-run-job-loop" / "SKILL.md"
REFERENCE = ROOT / "src" / "nxd-run-job-loop" / "reference" / "direct-cli-lifecycle.md"
VERIFIER = ROOT / "evals" / "public" / "job-loop-serve-query-refine" / "fixtures" / "check_job_loop.py"


def _load_verifier():
    spec = importlib.util.spec_from_file_location("job_loop_verifier", VERIFIER)
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
