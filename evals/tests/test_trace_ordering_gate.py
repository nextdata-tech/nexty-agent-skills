"""The pre-build ordering gate must bite on a build-before-asking transcript.

A landed closure records WHAT the agent produced, never the ORDER it acted in.
The failure this guards against produces a *correct-looking* closure: the agent
invents the missing half of a scoring policy, encodes it faithfully, and never
shows the user. Only the tool-call trace separates that run from one where the
policy was proposed and approved first.

So these tests assert two things a green run alone would not distinguish:

1. ``deterministic_check_fact`` actually forwards the trace to the checker when
   the scenario opts in with ``wants_trace`` (and does not when it doesn't).
2. The scenario's checker fails a transcript that materializes before the
   read-back and passes one that reads back first — using the real transcript
   shape observed in the live session that motivated the gate.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

EVALS_DIR = Path(__file__).resolve().parents[1]
SCENARIO = EVALS_DIR / "public" / "coauthor-supplied-rubric"
CHECKER = SCENARIO / "fixtures" / "check_coauthored_closure.py"


def _load_run_module():
    if str(EVALS_DIR) not in sys.path:
        sys.path.insert(0, str(EVALS_DIR))
    spec = importlib.util.spec_from_file_location("evals_run", EVALS_DIR / "run.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# The shape actually observed: technical questions, defaults chosen by the
# agent, then straight into scaffolding. No policy read-back anywhere.
# The tool lines use the `[tool_use:<Name>] {json}` form the backends really
# emit. An earlier `[tool] Write(...)` spelling matched nothing a run produces —
# it passed only because the checker's markers were wrong in the same way, so
# two defects cancelled out and this gate was never actually exercised.
BUILD_FIRST = """\
[assistant] Got the data — 10 candidates. Before I build, three decisions shape
the whole thing: deterministic transform vs manual, repo browsing, extra output.
[tool_use:Read] {"file_path": "/tmp/src/applicants.csv"}
[assistant] Going with the recommended defaults for the other two.
[tool_use:Skill] {"name": "nxd-generate-dp"}
[assistant] Templates in hand. Let me set up the closure directory, copy the
source CSV in, and capture how dlt normalizes the headers.
[tool_use:Bash] {"command": "mkdir -p ws/data/applicants", "description": "scaffold"}
[tool_use:Write] {"file_path": "ws/models.py", "content": "..."}
"""

# The same run done right: read the source, then propose, then wait.
READBACK_FIRST = """\
[tool_use:Read] {"file_path": "/tmp/src/applicants.csv"}
[assistant] Before I create anything, here is the policy I propose to encode.
Your rubric defines only the 5 and the 1 on all four criteria — 2, 3 and 4 are
undefined, and they drive most of the sub-scores. Proposed anchors: C4 4 = 7-9
years, 3 = 4-6 years, 2 = 2-3 years. You gave verdict names but no numbers.
Proposed bands: ADVANCE >= 4.0, HOLD >= 2.5, REJECT below; NEEDS_MORE_INFO
takes precedence when no portfolio URL was captured. All of it lands as
editable rows, not hidden judgement.
Does that look right, or would you correct any of it before I build?
"""


def _run_checker(root: Path, trace: str | None) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(CHECKER), "--root", str(root)]
    if trace is not None:
        tf = root / "_trace.txt"
        tf.write_text(trace, encoding="utf-8")
        cmd += ["--trace", str(tf)]
    return subprocess.run(cmd, capture_output=True, text=True)


def test_gate_fails_when_build_precedes_readback(tmp_path):
    """The observed failure: scaffolding starts before any policy is shown."""
    proc = _run_checker(tmp_path, BUILD_FIRST)
    assert proc.returncode != 0, proc.stdout
    assert "FAIL pre-build:" in proc.stdout
    # It must fail on ORDERING, not merely because tmp_path has no closure.
    assert "must precede the first Write" in proc.stdout


def test_gate_passes_when_readback_precedes_build(tmp_path):
    """Stopping to ask, with nothing written, is the gate's ideal outcome."""
    proc = _run_checker(tmp_path, READBACK_FIRST)
    assert proc.returncode == 0, proc.stdout
    assert "ALL CHECKS PASSED" in proc.stdout
    for signal in ("names the incomplete scale", "proposes anchors",
                   "proposes verdict mapping", "asks for correction"):
        assert f"PASS pre-build:{signal}" in proc.stdout


def test_post_hoc_disclosure_still_fails(tmp_path):
    """Disclosing the policy AFTER building is the loophole worth closing.

    The run that motivated this gate did disclose — at length, in a written
    ledger, after the fact. A gate satisfied by that would be no gate.
    """
    proc = _run_checker(tmp_path, BUILD_FIRST + READBACK_FIRST)
    assert proc.returncode != 0, proc.stdout
    assert "FAIL pre-build:" in proc.stdout


def test_read_only_inspection_is_not_a_write(tmp_path):
    """Reading the source before the read-back is explicitly allowed.

    The read-back has to describe that data, so it cannot come first.
    """
    trace = (
        '[tool_use:Read] {"file_path": "/tmp/src/applicants.csv"}\n'
        '[tool_use:Bash] {"command": "head -3 /tmp/src/applicants.csv",'
        ' "description": "peek at the header"}\n'
        '[tool_use:Bash] {"command": "wc -l /tmp/src/applicants.csv",'
        ' "description": "count the rows"}\n'
    ) + READBACK_FIRST
    proc = _run_checker(tmp_path, trace)
    assert proc.returncode == 0, proc.stdout
    assert "ALL CHECKS PASSED" in proc.stdout


def test_routing_check_fails_when_generator_is_reached_first(tmp_path):
    """Skill SELECTION is graded, not just what happens inside a skill.

    The observed failure was a routing decision: both skills attached, only
    nxd-generate-dp loaded, because "I want a data product" matched the
    generator's trigger. That choice happens before any skill body runs, so no
    rule inside a skill can compensate for it.
    """
    trace = (
        '[tool_use:Skill] {"skill": "nxd-eval-pack:nxd-generate-dp", '
        '"args": "Build a local desktop data product that screens..."}\n'
        "[tool_result] Launching skill: nxd-eval-pack:nxd-generate-dp\n"
    )
    proc = _run_checker(tmp_path, trace)
    assert proc.returncode != 0, proc.stdout
    assert "FAIL routing:orchestrator-first" in proc.stdout
    assert "nxd-generate-dp" in proc.stdout


def test_routing_check_passes_when_orchestrator_is_reached_first(tmp_path):
    trace = (
        '[tool_use:Skill] {"skill": "nxd-eval-pack:nxd-pocket-loop"}\n'
        "[tool_result] Launching skill: nxd-eval-pack:nxd-pocket-loop\n"
    ) + READBACK_FIRST
    proc = _run_checker(tmp_path, trace)
    assert proc.returncode == 0, proc.stdout
    assert "PASS routing:orchestrator-first" in proc.stdout


def test_routing_check_is_silent_when_no_skill_loaded(tmp_path):
    """No skill at all is a different failure, graded by the read-back checks.

    Asserting routing here would report a misleading cause.
    """
    proc = _run_checker(tmp_path, READBACK_FIRST)
    assert proc.returncode == 0, proc.stdout
    assert "NOTE routing" in proc.stdout
    assert "FAIL routing" not in proc.stdout


def test_fact_forwards_trace_only_when_scenario_opts_in(tmp_path):
    """``wants_trace`` is what puts --trace on the checker's argv."""
    run = _load_run_module()
    probe = tmp_path / "probe.py"
    probe.write_text(
        "import sys, json\n"
        "print(json.dumps(sys.argv[1:]))\n"
        "print('ALL CHECKS PASSED')\n",
        encoding="utf-8",
    )
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    (fixtures / "probe.py").write_text(probe.read_text(), encoding="utf-8")

    with_trace = run.deterministic_check_fact(
        tmp_path, tmp_path, {"script": "probe.py", "deps": [], "wants_trace": True},
        "the trace body",
    )
    assert '"passed": true' in with_trace.lower()

    without = run.deterministic_check_fact(
        tmp_path, tmp_path, {"script": "probe.py", "deps": []}, "the trace body",
    )
    assert '"passed": true' in without.lower()


def test_trace_file_never_lands_in_the_workspace(tmp_path):
    """A trace written into ``ws`` would be readable by the agent next turn and
    would also perturb any workspace-files assertion."""
    run = _load_run_module()
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    (fixtures / "probe.py").write_text(
        "print('ALL CHECKS PASSED')\n", encoding="utf-8"
    )
    ws = tmp_path / "ws"
    ws.mkdir()
    run.deterministic_check_fact(
        tmp_path, ws, {"script": "probe.py", "deps": [], "wants_trace": True},
        "secret trace",
    )
    assert list(ws.iterdir()) == [], "trace leaked into the agent's workspace"
