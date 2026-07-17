"""P1 authoring layer: round-trip a Suite to an Inspect Task and check wiring.

No model provider, no API key, no network. These tests assert the SHAPE the
authoring layer produces — the Sample lowering (input/target/metadata), the
scorer slot list, the solver, and the model-role wiring — plus the two loaders
(test_suite.json → Suite, untyped checks.json → one judge bucket). Scorer
*bodies* are placeholders at this layer and are not exercised here.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from inspect_ai._util.registry import registry_info
from nxd_eval import Case
from nxd_eval import Suite
from nxd_eval import checks
from nxd_eval import gold
from nxd_eval import load_checks_json
from nxd_eval import load_suite
from nxd_eval.scorers import ABSTAIN_INFEASIBLE
from nxd_eval.scorers import DETERMINISTIC_EX
from nxd_eval.scorers import JUDGE
from nxd_eval.scorers import SLOT_MATCH
from nxd_eval.solver import mcp_solver
from nxd_eval.task import build_task
from nxd_eval.task import case_to_sample


def _scorer_names(task) -> set[str]:
    """Stable slot names via the Inspect registry (inner fn __name__ is 'score').

    Inspect package-qualifies the registry name once nxd_eval is installed as a
    wheel (``nxd_eval/deterministic_ex``) vs. bare on a src checkout
    (``deterministic_ex``); strip the prefix so the slot assertions are
    layout-agnostic, matching report.py's prefix-tolerant scorer lookup.
    """
    return {registry_info(s).name.rsplit("/", 1)[-1] for s in task.scorer}

REPO_ROOT = Path(__file__).resolve().parents[3]
QUERY_LOOP_SUITE = REPO_ROOT / "evals/query-loop/test_suite.json"
PHARMA_CHECKS = REPO_ROOT / "evals/public/pharma-mesh-query-hard/checks.json"

MCP_URL = "http://127.0.0.1:8765/pharma-mesh/rpcs/mcp-api/mcp"


def _demo_suite() -> Suite:
    return Suite(
        name="demo",
        cases=[
            Case(id="a", question="How many subjects?", expect="answer", gold_id="g_a"),
            Case(id="b", question="how much, by type?", expect="clarify"),
            Case(id="c", question="units by prescriber", expect="abstain"),
        ],
        target=MCP_URL,
        gold=gold({"g_a": gold.rows("g_a", [{"subject_count": 4}])}),
        checks=checks(answer=["one number, equals 4"]),
    )


# --------------------------------------------------------------------------- #
# Case / Suite model
# --------------------------------------------------------------------------- #


def test_case_rejects_unknown_expect():
    with pytest.raises(ValueError):
        Case(id="x", question="q", expect="guess")


def test_expect_discriminators_accepted():
    for e in ("answer", "clarify", "abstain"):
        assert Case(id=e, question="q", expect=e).expect == e


# --------------------------------------------------------------------------- #
# Sample lowering
# --------------------------------------------------------------------------- #


def test_answer_case_lowers_gold_rows_into_target():
    suite = _demo_suite()
    sample = case_to_sample(suite.cases[0], suite)
    assert sample.id == "a"
    assert sample.input == "How many subjects?"
    # gold rows are JSON-encoded into the string target (Inspect targets are str)
    assert json.loads(sample.target) == [{"subject_count": 4}]
    assert sample.metadata["bucket"] == "answer"
    assert sample.metadata["feasible"] is True
    assert sample.metadata["cluster"] == "g_a"


def test_clarify_and_abstain_have_empty_target_and_route_flags():
    suite = _demo_suite()
    clarify = case_to_sample(suite.cases[1], suite)
    abstain = case_to_sample(suite.cases[2], suite)
    assert clarify.target == ""
    assert clarify.metadata["bucket"] == "clarify"
    assert clarify.metadata["feasible"] is True
    assert abstain.target == ""
    assert abstain.metadata["bucket"] == "abstain"
    assert abstain.metadata["feasible"] is False


def test_judge_only_metadata_never_leaks_into_agent_input():
    case = Case(
        id="a",
        question="visible question",
        expect="clarify",
        metadata={"why": "SECRET reasoning", "gold_note": "SECRET note"},
    )
    suite = Suite(name="s", cases=[case], target=MCP_URL)
    sample = case_to_sample(case, suite)
    # The agent sees ONLY the input; judge-only context rides in metadata.
    assert sample.input == "visible question"
    assert "SECRET" not in sample.input
    assert sample.metadata["why"] == "SECRET reasoning"
    assert sample.metadata["gold_note"] == "SECRET note"


# --------------------------------------------------------------------------- #
# Task round-trip: dataset + solver + scorer slots + model roles
# --------------------------------------------------------------------------- #


def test_suite_round_trips_to_task_with_full_wiring():
    suite = _demo_suite()
    task = suite.to_inspect_task()

    # dataset: one Sample per Case, in order
    assert [s.id for s in task.dataset] == ["a", "b", "c"]

    # solver is present (the react-over-MCP solver)
    assert task.solver is not None

    # scorer slots: deterministic-EX + abstain/infeasible + slot-match always;
    # judge because the suite carries checks.
    assert _scorer_names(task) == {
        DETERMINISTIC_EX,
        ABSTAIN_INFEASIBLE,
        SLOT_MATCH,
        JUDGE,
    }


def test_no_checks_suite_omits_judge_slot():
    suite = Suite(
        name="nochecks",
        cases=[Case(id="a", question="q", expect="answer", gold_id="g")],
        target=MCP_URL,
        gold=gold({"g": gold.rows("g", [{"n": 1}])}),
    )
    task = suite.to_inspect_task()
    names = _scorer_names(task)
    assert names == {DETERMINISTIC_EX, ABSTAIN_INFEASIBLE, SLOT_MATCH}
    assert JUDGE not in names


def test_grader_model_wires_model_role():
    # mockllm resolves with no provider/API key.
    task = _demo_suite().to_inspect_task(grader_model="mockllm/model")
    assert task.model_roles is not None
    assert "grader" in task.model_roles


def test_epochs_policy_attached_when_greater_than_one():
    suite = _demo_suite()
    t1 = suite.to_inspect_task(epochs=1)
    assert t1.epochs is None
    t3 = suite.to_inspect_task(epochs=3, epochs_reducer="pass_at")
    # Inspect normalizes Task.epochs to the int k and resolves the reducer.
    assert t3.epochs == 3
    assert t3.epochs_reducer is not None


def test_target_resolution_argument_overrides_suite():
    suite = Suite(name="s", cases=[Case(id="a", question="q", expect="clarify")])
    # no suite.target -> build error unless passed
    with pytest.raises(ValueError):
        build_task(suite)
    task = build_task(suite, target=MCP_URL)
    assert task.solver is not None


def test_mcp_solver_builds_over_url():
    # solver assembly should not require a running server (lazy connect).
    assert mcp_solver(MCP_URL) is not None


# --------------------------------------------------------------------------- #
# stdio transport seam (server_factory) — the teardown-safe path
# --------------------------------------------------------------------------- #


def _stub_stdio_server():
    """A lazy stdio MCP server (does not launch until used) — safe to build in a
    unit test, same as a URL server is lazy-connect."""
    from inspect_ai.tool import mcp_server_stdio

    return mcp_server_stdio(command="/bin/false", args=[])


def test_mcp_solver_accepts_prebuilt_server():
    # A pre-built server bypasses the URL path entirely; no url needed.
    assert mcp_solver(server=_stub_stdio_server()) is not None


def test_mcp_solver_requires_url_or_server():
    with pytest.raises(ValueError):
        mcp_solver()


def test_mcp_solver_prompt_override():
    # A custom prompt is accepted (mesh scenarios pass their own analyst prompt).
    assert mcp_solver(MCP_URL, prompt="custom analyst prompt") is not None


def test_build_task_accepts_server_factory_without_url():
    # A stdio server_factory satisfies the "has a server" requirement — no URL.
    suite = Suite(name="s", cases=[Case(id="a", question="q", expect="clarify")])
    task = build_task(suite, server_factory=_stub_stdio_server)
    assert task.solver is not None
    assert len(task.dataset) == 1


def test_suite_server_factory_field_satisfies_build():
    # server_factory carried on the Suite itself is enough to build (no target).
    suite = Suite(
        name="s",
        cases=[Case(id="a", question="q", expect="abstain")],
        server_factory=_stub_stdio_server,
    )
    # no target, no arg factory — must still build off the suite field.
    task = build_task(suite)
    assert task.solver is not None


def test_build_task_requires_url_or_server_factory():
    # Neither a URL nor a factory anywhere -> build error.
    suite = Suite(name="s", cases=[Case(id="a", question="q", expect="clarify")])
    with pytest.raises(ValueError):
        build_task(suite)


def test_server_factory_excluded_from_suite_equality():
    # The factory is runtime wiring, not identity: two suites differing only in
    # server_factory must compare equal (compare=False on the field).
    base = dict(name="s", cases=[Case(id="a", question="q", expect="clarify")])
    assert Suite(**base, server_factory=_stub_stdio_server) == Suite(**base)


def test_load_suite_attaches_server_factory_and_gold():
    # The loader threads runtime wiring the file doesn't carry.
    suite = load_suite(
        QUERY_LOOP_SUITE,
        server_factory=_stub_stdio_server,
        gold=gold({"g": gold.rows("g", [{"n": 1}])}),
    )
    assert suite.server_factory is _stub_stdio_server
    assert "g" in suite.gold
    # builds off the loaded factory, no target needed
    assert build_task(suite).solver is not None


# --------------------------------------------------------------------------- #
# Loaders
# --------------------------------------------------------------------------- #


def test_load_suite_reads_query_loop_shape():
    suite = load_suite(QUERY_LOOP_SUITE)
    assert len(suite.cases) == 12
    ids = [c.id for c in suite.cases]
    assert ids[0] == "q01-baseline-single-grain"
    # discriminators recognized from the real file
    assert {c.expect for c in suite.cases} == {"answer", "clarify", "abstain"}
    # judge-only fields preserved in metadata, NOT in the question
    c05 = suite.cases[4]
    assert c05.expect == "clarify"
    assert "why" in c05.metadata and "gold_note" in c05.metadata
    assert "why" not in c05.question


def test_load_suite_carries_target_when_given():
    suite = load_suite(QUERY_LOOP_SUITE, target=MCP_URL)
    assert suite.target == MCP_URL
    # and lowers to a runnable task
    task = suite.to_inspect_task()
    assert len(task.dataset) == 12


def test_checks_json_back_compat_single_judge_bucket():
    cj = load_checks_json(PHARMA_CHECKS)
    # untyped legacy checks all route to ONE judge bucket
    assert set(cj.keys()) == {JUDGE}
    assert len(cj[JUDGE]) == 10
    # each check is cited with its original id
    assert cj[JUDGE][0].startswith("discovery-and-strict-mcp:")


def test_typed_checks_builder_drops_empty_buckets():
    assert checks() == {}
    assert checks(answer=["x"]) == {"answer": ["x"]}
    assert checks(answer=[], clarify=["c"]) == {"clarify": ["c"]}


def test_dotted_check_constructors_match_flat_builder():
    assert checks.answer("a") == checks(answer=["a"])
    assert checks.clarify("c") == checks(clarify=["c"])
    assert checks.abstain("d") == checks(abstain=["d"])
    merged = checks.merge(checks.answer("a"), checks.answer("b"))
    assert merged == {"answer": ["a", "b"]}
