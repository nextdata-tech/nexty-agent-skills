"""P0 go/no-go: prove the Inspect + MCP substrate reaches our stub server.

None of these tests need a real model provider or an API key. They exercise the
whole substrate the spike gates — transport, tool surface, AND the full
eval() -> solver -> tool call -> scorer -> .eval log chain — using Inspect's
built-in mockllm provider to stand in for the agent-under-test. A live provider
only swaps the model at the top of the same wiring; it is not needed to prove the
substrate.

What is proven:
  1. The stub semantic MCP server serves Streamable-HTTP at the production URL
     shape (/<dp>/rpcs/<port>/mcp) and answers the real seeded baseline (4).
  2. Inspect's own mcp_server_http() connects to it and enumerates the three
     tools (list_models / describe_model / run_semantic_query).
  3. The full spike_baseline() task runs end to end under mockllm: the solver
     makes a REAL run_semantic_query tool call against the stub, the includes()
     scorer marks it correct, and a non-empty .eval log lands on disk and reads
     back. This is the explicit P0 go/no-go artifact.

If (2) or (3) ever fails, the Inspect substrate is a NO-GO — say so loudly.
"""

from __future__ import annotations

import socket
import subprocess
import sys
import time
from pathlib import Path

import anyio
import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
STUB_SERVER = REPO_ROOT / "evals/nxd_eval/stub_mcp/stub_semantic_server.py"
FIXTURES = REPO_ROOT / "evals/public/pharma-mesh-query-hard/fixtures"
DP = "pharma-mesh"
RPC_PORT = "mcp-api"


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_listening(host: str, port: int, timeout: float = 15.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            if s.connect_ex((host, port)) == 0:
                return
        time.sleep(0.2)
    raise TimeoutError(f"stub server never bound {host}:{port}")


@pytest.fixture(scope="module")
def stub_url():
    host, port = "127.0.0.1", _free_port()
    proc = subprocess.Popen(
        [sys.executable, str(STUB_SERVER), str(FIXTURES), "--http",
         "--host", host, "--port", str(port), "--dp", DP, "--rpc-port", RPC_PORT],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    try:
        _wait_listening(host, port)
        yield f"http://{host}:{port}/{DP}/rpcs/{RPC_PORT}/mcp"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_mcp_client_baseline_answer(stub_url):
    """Raw MCP client: run_semantic_query returns the true seeded count (4)."""
    import json

    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    async def _run():
        async with streamablehttp_client(stub_url) as (read, write, _):
            async with ClientSession(read, write) as s:
                await s.initialize()
                tools = {t.name for t in (await s.list_tools()).tools}
                assert tools == {"list_models", "describe_model", "run_semantic_query"}
                r = await s.call_tool("run_semantic_query",
                                      {"measures": ["subject_count"]})
                payload = json.loads(r.content[0].text)
                return payload

    payload = anyio.run(_run)
    assert payload["rows"] == [{"subject_count": 4}], payload


def test_inspect_mcp_server_http_connects(stub_url):
    """THE go/no-go: Inspect's mcp_server_http enumerates our three tools."""
    from inspect_ai.tool import ToolDef, mcp_server_http

    server = mcp_server_http(name="semantic", url=stub_url, authorization=None)

    async def _run():
        async with server:
            return [ToolDef(t).name for t in await server.tools()]

    names = anyio.run(_run)
    assert set(names) == {"list_models", "describe_model", "run_semantic_query"}, (
        f"Inspect substrate NO-GO: mcp_server_http saw {names!r}"
    )


def test_spike_task_builds():
    """The runnable @task assembles (dataset + react solver + scorer)."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "spike_task", REPO_ROOT / "evals/nxd_eval/spike_task.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    t = mod.spike_baseline()
    assert len(t.dataset) == 1
    assert t.dataset[0].target == "4"


def _load_spike_task(mcp_url: str):
    """Import spike_task.py by path and build the task against a given MCP URL."""
    import importlib.util
    import os

    os.environ["NXD_EVAL_MCP_URL"] = mcp_url
    spec = importlib.util.spec_from_file_location(
        "spike_task", REPO_ROOT / "evals/nxd_eval/spike_task.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.spike_baseline()


def test_eval_log_emitted(stub_url, tmp_path):
    """THE P0 artifact: the full chain emits a real .eval log, no API key.

    Drives the runnable spike_baseline() task with Inspect's built-in mockllm
    provider — no ANTHROPIC_API_KEY, no live model. mockllm scripts two turns:
    a REAL run_semantic_query tool call against the stub (so the tool leg,
    transport, and stub executor all fire), then the react agent's submit answer.
    Asserts the includes() scorer marks it correct AND a non-empty .eval log
    lands under the log dir and reads back with the tool call recorded.
    """
    from inspect_ai import eval as inspect_eval
    from inspect_ai.log import read_eval_log
    from inspect_ai.model import ModelOutput, get_model

    task = _load_spike_task(stub_url)

    # Two scripted turns for the react() agent: call the query tool, then submit.
    mock = get_model(
        "mockllm/model",
        custom_outputs=[
            ModelOutput.for_tool_call(
                "mockllm",
                tool_name="run_semantic_query",
                tool_arguments={"measures": ["subject_count"]},
            ),
            ModelOutput.for_tool_call(
                "mockllm",
                tool_name="submit",
                tool_arguments={"answer": "There are 4 subjects in the registry."},
            ),
        ],
    )

    log_dir = tmp_path / "logs"
    logs = inspect_eval(task, model=mock, log_dir=str(log_dir), display="none")

    # A real .eval file exists on disk and is non-empty.
    eval_files = list(log_dir.glob("*.eval"))
    assert len(eval_files) == 1, f"expected one .eval log, got {eval_files!r}"
    assert eval_files[0].stat().st_size > 0, "emitted .eval log is empty"

    # It reads back as a successful run that scored CORRECT via a real tool call.
    assert logs[0].status == "success", logs[0].status
    rl = read_eval_log(str(eval_files[0]))
    assert rl.status == "success"
    assert len(rl.samples) == 1
    sample = rl.samples[0]
    assert sample.scores["includes"].value == "C", sample.scores
    tool_calls = [
        tc.function
        for m in sample.messages
        if getattr(m, "tool_calls", None)
        for tc in m.tool_calls
    ]
    assert "run_semantic_query" in tool_calls, (
        f"substrate NO-GO: agent never called the query tool; saw {tool_calls!r}"
    )
