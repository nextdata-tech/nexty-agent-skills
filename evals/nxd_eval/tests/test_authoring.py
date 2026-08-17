"""P1 authoring layer: round-trip a Suite to an Inspect Task and check wiring.

No model provider, no API key, no network. These tests assert the SHAPE the
authoring layer produces — the Sample lowering (input/target/metadata), the
scorer slot list, the solver, and the model-role wiring — plus the two loaders
(test_suite.json → Suite, untyped checks.json → one judge bucket). Scorer
*bodies* are placeholders at this layer and are not exercised here.
"""

from __future__ import annotations

import json
import socket
import threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer

import pytest
from inspect_ai._util.registry import registry_info
from nxd_eval import Case
from nxd_eval import Suite
from nxd_eval import checks
from nxd_eval import gold
from nxd_eval import load_checks_json
from nxd_eval import load_suite
from nxd_eval.dependencies import DependencyCheckError
from nxd_eval.dependencies import check_inspect_model_dependency
from nxd_eval.scorers import ABSTAIN_INFEASIBLE
from nxd_eval.scorers import DETERMINISTIC_EX
from nxd_eval.scorers import JUDGE
from nxd_eval.scorers import SLOT_MATCH
from nxd_eval.task import MCPConnectionError
from nxd_eval.solver import mcp_solver
from nxd_eval.task import build_task
from nxd_eval.task import case_to_sample
from nxd_eval.task import preflight_mcp_http_endpoint
from nxd_eval.task import run_suite


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


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class _StatusHandler(BaseHTTPRequestHandler):
    status = 200
    body = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"protocolVersion": "2024-11-05", "capabilities": {}},
        }
    ).encode()
    content_type = "application/json"
    seen_headers = None
    delete_count = 0

    def do_POST(self):  # noqa: N802 - stdlib callback name
        type(self).seen_headers = dict(self.headers)
        self.send_response(self.status)
        self.send_header("Content-Type", self.content_type)
        self.send_header("Mcp-Session-Id", "test-session")
        self.send_header("Content-Length", str(len(self.body)))
        self.end_headers()
        self.wfile.write(self.body)

    def do_DELETE(self):  # noqa: N802 - stdlib callback name
        type(self).delete_count += 1
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):  # noqa: A002 - stdlib signature
        return


@pytest.fixture
def http_status_server():
    servers = []

    def _start(status: int, **attrs) -> tuple[str, type[_StatusHandler]]:
        handler = type(
            f"Status{status}Handler",
            (_StatusHandler,),
            {"status": status, **attrs},
        )
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        servers.append((server, thread))
        port = server.server_address[1]
        return f"http://127.0.0.1:{port}/dp/rpcs/mcp-api/mcp", handler

    yield _start

    for server, thread in servers:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


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


def test_mcp_preflight_accepts_reachable_endpoint(http_status_server):
    url, handler = http_status_server(200)

    preflight_mcp_http_endpoint(url, timeout_s=1)

    assert handler.delete_count == 1


def test_mcp_preflight_sends_same_bearer_auth_as_inspect(http_status_server):
    url, handler = http_status_server(200)

    preflight_mcp_http_endpoint(url, authorization="raw-token", timeout_s=1)

    assert handler.seen_headers["Authorization"] == "Bearer raw-token"


def test_mcp_preflight_allows_sse_keepalives_before_initialize(http_status_server):
    payload = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"protocolVersion": "2024-11-05", "capabilities": {}},
        }
    )
    body = ("\n".join([": ping"] * 120) + f"\nevent: message\ndata: {payload}\n\n").encode()
    url, _handler = http_status_server(
        200,
        body=body,
        content_type="text/event-stream",
    )

    preflight_mcp_http_endpoint(url, timeout_s=1)


def test_mcp_preflight_rejects_malformed_200_response(http_status_server):
    url, _handler = http_status_server(200, body=b"{}")

    with pytest.raises(MCPConnectionError, match="malformed MCP initialize response"):
        preflight_mcp_http_endpoint(url, timeout_s=1)


@pytest.mark.parametrize(
    ("status", "needle"),
    [(401, "HTTP 401"), (404, "HTTP 404"), (500, "HTTP 500")],
)
def test_mcp_preflight_reports_clear_http_status(http_status_server, status, needle):
    with pytest.raises(MCPConnectionError, match=needle) as excinfo:
        url, _handler = http_status_server(status)
        preflight_mcp_http_endpoint(url, timeout_s=1)

    message = str(excinfo.value)
    assert "MCP endpoint preflight failed" in message
    assert "/dp/rpcs/mcp-api/mcp" in message
    assert "auth token/header" in message


def test_mcp_preflight_reports_clear_connection_failure():
    url = f"http://127.0.0.1:{_free_port()}/dp/rpcs/mcp-api/mcp"

    with pytest.raises(MCPConnectionError, match="connection refused") as excinfo:
        preflight_mcp_http_endpoint(url, timeout_s=1)

    assert "MCP endpoint preflight failed" in str(excinfo.value)


def test_run_suite_preflights_http_mcp_before_eval(http_status_server, tmp_path):
    suite = Suite(
        name="s",
        cases=[Case(id="a", question="q", expect="clarify")],
    )

    with pytest.raises(MCPConnectionError, match="HTTP 404"):
        url, _handler = http_status_server(404)
        run_suite(
            suite,
            mcp_url=url,
            agent_model="mockllm/model",
            log_dir=tmp_path,
        )


def test_inspect_model_dependency_check_reports_missing_extra(monkeypatch):
    monkeypatch.setattr(
        "nxd_eval.dependencies._find_spec",
        lambda _module: None,
    )

    with pytest.raises(DependencyCheckError) as excinfo:
        check_inspect_model_dependency("openai/gpt-4o", role="agent_model")

    message = str(excinfo.value)
    assert "agent_model 'openai/gpt-4o'" in message
    assert "'openai'" in message
    assert "--extra openai" in message


def test_inspect_model_dependency_check_ignores_unknown_or_mock_providers(monkeypatch):
    calls = []

    def _fake_find_spec(module):
        calls.append(module)
        return None

    monkeypatch.setattr(
        "nxd_eval.dependencies._find_spec",
        _fake_find_spec,
    )

    check_inspect_model_dependency("mockllm/model", role="agent_model")
    check_inspect_model_dependency("custom-provider/model", role="agent_model")
    check_inspect_model_dependency(None, role="agent_model")

    assert calls == []


def test_run_suite_checks_model_backend_before_mcp(http_status_server, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "nxd_eval.dependencies._find_spec",
        lambda _module: None,
    )
    suite = Suite(
        name="s",
        cases=[Case(id="a", question="q", expect="clarify")],
    )

    with pytest.raises(DependencyCheckError, match="--extra openai"):
        url, _handler = http_status_server(404)
        run_suite(
            suite,
            mcp_url=url,
            agent_model="openai/gpt-4o",
            log_dir=tmp_path,
        )


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
