"""Look-ahead canary: drive the eval MCP server against a fresh NXD build.

What this is
------------
The required CI job checks the pairing this repository has PINNED and NXD has
PUBLISHED. This canary checks the pairing that is COMING: NXD's newest main
artifact against this repository's current revision. A failure here is not a
broken release — it is notice that the next NXD bump will break the evals, which
is the whole point of running it nightly rather than at merge time.

It is a consumer. It reads an artifact NXD has already finished publishing; it
never triggers, waits on, or builds anything in NXD.

Deterministic by construction
-----------------------------
No model calls and no warehouse. The three checks each fail closed:

1. **Transport** — a real Streamable-HTTP MCP handshake against the server the
   scenarios use, then ``tools/list``. Catches an MCP SDK or server-shape break
   before a scenario run turns it into an unexplained agent timeout.
2. **Contract** — the served surface against the NEWEST production contract,
   with the same committed exceptions the required job uses. Catches NXD adding,
   renaming, or re-typing a tool argument.
3. **Behaviour** — two ``run_semantic_query`` calls through the genuine NXD
   compiler. An unknown measure must be REFUSED at compile time (the abstention
   the scenarios grade), and a valid selection must produce compiled SQL. The
   second call reaches the executor and is expected to fail there — no warehouse
   is configured — so the assertion is on the compiled SQL, never on rows.

The valid selection is discovered over MCP (``list_models`` then
``describe_model``) rather than hardcoded, so the canary exercises the tool chain
an agent walks and does not pin a fixture's vocabulary in two places.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import subprocess
import sys
import time
from contextlib import closing
from pathlib import Path
from typing import Any
from typing import Sequence

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from contract_check import ContractCheckError  # noqa: E402 — after the sys.path insert above
from contract_check import check  # noqa: E402
from contract_check import load_contract_document  # noqa: E402
from contract_check import load_exceptions  # noqa: E402
from contract_check import load_installed_contract  # noqa: E402
from contract_surface import DEFAULT_FIXTURES  # noqa: E402
from contract_surface import surface_from_tools  # noqa: E402

DEFAULT_DP = "canary-dp"
DEFAULT_RPC_PORT = "8080"
STARTUP_TIMEOUT_SECONDS = 90.0


class CanaryFailure(RuntimeError):
    """A canary check failed. Always fatal — there is no degraded pass."""


def _free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_listener(port: int, process: subprocess.Popen[bytes], deadline: float) -> None:
    """Block until the server accepts a connection, or fail closed.

    A server that exits during startup is reported as such rather than as a
    timeout: the two need different remedies and the log line is the only place
    an operator sees the difference.
    """
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise CanaryFailure(
                f"the semantic MCP server exited during startup with code {process.returncode}; "
                "see the captured server log above"
            )
        try:
            with closing(socket.create_connection(("127.0.0.1", port), timeout=1.0)):
                return
        except OSError:
            time.sleep(0.5)
    raise CanaryFailure(f"the semantic MCP server did not accept connections on port {port} within the startup budget")


async def _drive(url: str) -> dict[str, Any]:
    """Speak MCP over Streamable-HTTP and collect everything the checks need."""
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    async with streamablehttp_client(url) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            listed = await session.list_tools()
            tools = list(listed.tools)

            refusal = await _call(session, "run_semantic_query", {"measures": ["__nxd_canary_unknown_measure__"]})

            models = await _call(session, "list_models", {})
            model_name = _first_model(models)
            described = await _call(session, "describe_model", {"name": model_name})
            metric_name = _first_metric(described, model_name)
            compiled = await _call(session, "run_semantic_query", {"measures": [metric_name]})

    return {
        "tools": tools,
        "refusal": refusal,
        "compiled": compiled,
        "model": model_name,
        "metric": metric_name,
    }


async def _call(session: Any, name: str, arguments: dict[str, Any]) -> Any:
    """Call a tool and return its decoded payload.

    FastMCP emits a list return value as ONE text block per element, so reading
    only the first block would silently turn a three-model catalog into one
    model. Prefer ``structuredContent``, which carries the whole value under
    ``result``, and fall back to reassembling the text blocks.
    """
    result = await session.call_tool(name, arguments)
    if getattr(result, "isError", False):
        raise CanaryFailure(f"the {name!r} tool call errored at the protocol level: {result}")

    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict) and "result" in structured:
        return structured["result"]

    texts = [block.text for block in result.content if getattr(block, "type", None) == "text"]
    if not texts:
        raise CanaryFailure(f"the {name!r} tool call returned no text content")
    try:
        decoded = [json.loads(text) for text in texts]
    except json.JSONDecodeError as exc:
        raise CanaryFailure(f"the {name!r} tool call returned non-JSON text: {texts[0][:200]}") from exc
    return decoded[0] if len(decoded) == 1 else decoded


def _first_model(models: Any) -> str:
    if not isinstance(models, list) or not models:
        raise CanaryFailure("list_models returned no models; the canary cannot pick a valid selection")
    entry = models[0]
    name = entry.get("name") if isinstance(entry, dict) else None
    if not isinstance(name, str) or not name:
        raise CanaryFailure(f"the first list_models entry has no usable name: {entry!r}")
    return name


def _first_metric(described: Any, model_name: str) -> str:
    metrics = described.get("metrics") if isinstance(described, dict) else None
    if not isinstance(metrics, list) or not metrics:
        raise CanaryFailure(f"describe_model({model_name!r}) returned no metrics")
    name = metrics[0].get("name") if isinstance(metrics[0], dict) else None
    if not isinstance(name, str) or not name:
        raise CanaryFailure(f"the first metric of {model_name!r} has no usable name: {metrics[0]!r}")
    return name


def _check_behaviour(observed: dict[str, Any]) -> list[str]:
    failures: list[str] = []

    refusal = observed["refusal"]
    error = refusal.get("error") if isinstance(refusal, dict) else None
    if not isinstance(error, str) or not error.startswith("compile refused"):
        failures.append(
            "run_semantic_query accepted an unknown measure instead of refusing it at compile time; "
            f"got {refusal!r}. Scenarios grade the abstention, so a silent acceptance invalidates them."
        )

    compiled = observed["compiled"]
    sql = compiled.get("compiled_sql") if isinstance(compiled, dict) else None
    if not isinstance(sql, str) or not sql.strip():
        failures.append(
            f"run_semantic_query on the valid selection {observed['metric']!r} produced no compiled SQL; "
            f"got {compiled!r}. The genuine compiler did not run."
        )
    elif isinstance(compiled, dict) and str(compiled.get("error", "")).startswith("compile refused"):
        failures.append(f"the genuine compiler refused a selection taken from describe_model: {compiled['error']}")

    return failures


def _summary_line(key: str, value: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    line = f"- **{key}**: `{value}`"
    print(f"{key}: {value}")
    if path:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def _emit_provenance(manifest_path: Path | None) -> None:
    """Record exactly which pairing this run examined.

    The report has to name both sides — the Nexty revision and the NXD trees —
    or a failure notification cannot be acted on without opening the run.
    """
    _summary_line("nexty sha", os.environ.get("GITHUB_SHA", "unknown"))
    if manifest_path is None or not manifest_path.is_file():
        _summary_line("nxd artifact manifest", "absent")
        return
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for key in (
        "source_sha",
        "semantic_tree_sha",
        "rpc_tree_sha",
        "mcp_contract_sha256",
        "package_version",
        "workflow_run_id",
    ):
        _summary_line(f"nxd {key}", str(manifest.get(key, "absent")))


def run(
    *,
    fixtures: Path,
    contract_path: Path | None,
    manifest_path: Path | None,
    dp: str,
    rpc_port: str,
) -> int:
    _emit_provenance(manifest_path)

    exceptions = load_exceptions()
    contract = load_contract_document(contract_path) if contract_path else load_installed_contract()

    port = _free_port()
    http_path = f"/{dp}/rpcs/{rpc_port}/mcp"
    command = [
        sys.executable,
        str(HERE / "semantic_server.py"),
        str(fixtures),
        "--http",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--dp",
        dp,
        "--rpc-port",
        rpc_port,
    ]
    print(f"canary: starting {' '.join(command)}", flush=True)
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        _wait_for_listener(port, process, time.monotonic() + STARTUP_TIMEOUT_SECONDS)
        observed = asyncio.run(_drive(f"http://127.0.0.1:{port}{http_path}"))
    finally:
        process.terminate()
        try:
            output, _ = process.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            output, _ = process.communicate()
        if output:
            print("--- semantic MCP server log ---", flush=True)
            print(output.decode("utf-8", errors="replace"), flush=True)

    surface = surface_from_tools(observed["tools"])
    findings = check(contract, surface, exceptions)

    failures = [finding.render() for finding in findings]
    failures.extend(_check_behaviour(observed))

    if failures:
        print(f"canary: FAIL — {len(failures)} problem(s)", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1
    print(
        f"canary: OK — {len(surface['tools'])} tool(s) over MCP, compile refusal and "
        f"compiled SQL both observed via {observed['model']}/{observed['metric']}"
    )
    return 0


def _flatten(error: BaseException) -> list[str]:
    """Every leaf message in a (possibly nested) exception group, in order."""
    if isinstance(error, BaseExceptionGroup):
        return [message for child in error.exceptions for message in _flatten(child)]
    return [f"{type(error).__name__}: {error}"]


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nightly_canary")
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES)
    parser.add_argument(
        "--contract",
        type=Path,
        default=None,
        help="production contract path; defaults to the installed nxd-data_product's",
    )
    parser.add_argument("--manifest", type=Path, default=None, help="the NXD artifact manifest, for the run summary")
    parser.add_argument("--dp", default=DEFAULT_DP)
    parser.add_argument("--rpc-port", default=DEFAULT_RPC_PORT)
    args = parser.parse_args(argv)

    if not args.fixtures.is_dir():
        print(f"canary: no such fixture directory: {args.fixtures}", file=sys.stderr)
        return 2
    try:
        return run(
            fixtures=args.fixtures,
            contract_path=args.contract,
            manifest_path=args.manifest,
            dp=args.dp,
            rpc_port=args.rpc_port,
        )
    except (CanaryFailure, ContractCheckError) as exc:
        print(f"canary: FAIL — {exc}", file=sys.stderr)
        return 1
    except BaseExceptionGroup as group:
        # anyio wraps anything raised inside the MCP session's task group. Without
        # this the canary's own diagnostics arrive as a nested traceback and the
        # operator reads an SDK stack instead of the sentence naming the failure.
        for message in _flatten(group):
            print(f"canary: FAIL — {message}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"canary: FAIL — could not reach the semantic MCP server: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(_main())
