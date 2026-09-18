"""Lower a ``Suite`` into a runnable Inspect ``Task``.

The mapping is 1:1 and legible:

  Case            -> Sample(input=question, target=gold rows, id=case.id,
                            metadata={bucket, cluster, feasible, ...judge-only})
  Suite.target    -> mcp_server_http(url=...) inside react(tools=[server])
  Suite.checks    -> the judge scorer slot (attached when checks exist)
  every case      -> the deterministic-EX + abstain/infeasible scorer slots

``bucket`` is the ``expect`` discriminator (answer/clarify/abstain). ``feasible``
is False for ``abstain`` cases (the question is not answerable as asked), True
otherwise — the scorer layer routes on these. ``cluster`` groups cases that
share a gold id (or the case id when ungrouped) so the paired/clustered stats in
the statistics layer have a grouping key. None of these are shown to the agent;
they ride in Sample metadata, read only by scorers and post-processing.
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING, Any

from inspect_ai import Epochs, Task
from inspect_ai.dataset import Sample

from .case import ABSTAIN
from .dependencies import check_inspect_model_dependency
from .scorers import scorers_for
from .solver import mcp_solver

# The three skill-pack variants an eval run compares. They select what skill
# context the agent-under-test runs with; the harness records the choice on the
# run so the report/regression layer can pair variants on the same cases. The
# variant does not change scoring — only the agent's starting knowledge.
VARIANTS = ("no_skills", "current_pack", "candidate_pack")

# Reducer families that take a k parameter encoded in the name (``pass_at_3``).
# The public API takes the bare family name plus ``epochs`` as k; we compose the
# concrete reducer name here so ``epochs_reducer="pass_at"`` stays ergonomic.
_K_PARAM_REDUCERS = ("pass_at", "at_least")


class MCPConnectionError(RuntimeError):
    """Raised when an HTTP MCP endpoint fails the preflight check."""


def _mcp_initialize_body() -> bytes:
    return json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "nxd_eval-preflight", "version": "1"},
            },
        }
    ).encode()


def _mcp_error_message(url: str, detail: str) -> str:
    return (
        f"MCP endpoint preflight failed for {url}: {detail}. "
        "Verify the MCP URL is reachable, points at the streamable HTTP MCP path "
        "(for example /<data-product>/rpcs/<rpc-port>/mcp), and that the auth "
        "token/header is valid."
    )


def _mcp_http_headers(authorization: str | None = None) -> dict[str, str]:
    """Headers matching Inspect's ``mcp_server_http(authorization=...)`` path."""
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if authorization is not None:
        headers["Authorization"] = f"Bearer {authorization}"
    return headers


def _jsonrpc_payloads(body: bytes, content_type: str) -> list[dict[str, Any]]:
    text = body.decode("utf-8", errors="replace").strip()
    if not text:
        return []
    payloads: list[dict[str, Any]] = []
    if "text/event-stream" in content_type:
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            data = line.removeprefix("data:").strip()
            if not data or data == "[DONE]":
                continue
            try:
                parsed = json.loads(data)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                payloads.append(parsed)
        return payloads
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return []
    return [parsed] if isinstance(parsed, dict) else []


def _initialize_protocol_version(body: bytes, content_type: str) -> str | None:
    for payload in _jsonrpc_payloads(body, content_type):
        result = payload.get("result")
        if isinstance(result, dict) and isinstance(result.get("protocolVersion"), str):
            return result["protocolVersion"]
    return None


def _read_initialize_response(resp: Any, content_type: str) -> bytes:
    if "text/event-stream" not in content_type:
        return resp.read(65536)

    chunks: list[bytes] = []
    data_lines = 0
    total_bytes = 0
    while total_bytes < 65536 and data_lines < 100:
        line = resp.readline(65536)
        if not line:
            break
        chunks.append(line)
        total_bytes += len(line)
        if not line.strip().startswith(b"data:"):
            continue
        data_lines += 1
        if _initialize_protocol_version(b"".join(chunks), content_type):
            break
    return b"".join(chunks)


def _close_mcp_session(
    url: str,
    *,
    headers: dict[str, str],
    session_id: str | None,
    timeout_s: float,
) -> None:
    if not session_id:
        return
    close_headers = dict(headers)
    close_headers["Mcp-Session-Id"] = session_id
    req = urllib.request.Request(url, method="DELETE", headers=close_headers)
    try:
        urllib.request.urlopen(req, timeout=timeout_s).close()
    except (urllib.error.URLError, OSError, TimeoutError):
        # The preflight has already learned what it needs. A server that does not
        # support DELETE should not hide the clearer initialize result.
        return


def preflight_mcp_http_endpoint(
    url: str,
    *,
    authorization: str | None = None,
    timeout_s: float = 10.0,
) -> None:
    """Fail fast with a clear error before Inspect starts a model run.

    ``mcp_server_http`` connects lazily, so bad URLs or tokens otherwise surface
    deep in an eval loop. The preflight performs a JSON-RPC initialize request,
    checks for a protocol version in the response, and best-effort closes the
    session when the server returns a session id.
    """
    headers = _mcp_http_headers(authorization)

    req = urllib.request.Request(
        url,
        data=_mcp_initialize_body(),
        method="POST",
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            status = getattr(resp, "status", None) or resp.getcode()
            if 200 <= status < 300:
                content_type = resp.headers.get("Content-Type", "")
                body = _read_initialize_response(resp, content_type)
                session_id = resp.headers.get("Mcp-Session-Id")
                if _initialize_protocol_version(body, content_type):
                    _close_mcp_session(
                        url,
                        headers=headers,
                        session_id=session_id,
                        timeout_s=timeout_s,
                    )
                    return
                raise MCPConnectionError(
                    _mcp_error_message(
                        url,
                        "malformed MCP initialize response: missing "
                        "result.protocolVersion",
                    )
                )
            reason = getattr(resp, "reason", "") or "unexpected response"
            raise MCPConnectionError(
                _mcp_error_message(url, f"HTTP {status} {reason}".strip())
            )
    except urllib.error.HTTPError as exc:
        reason = exc.reason or "HTTP error"
        raise MCPConnectionError(
            _mcp_error_message(url, f"HTTP {exc.code} {reason}".strip())
        ) from exc
    except urllib.error.URLError as exc:
        reason = exc.reason
        if isinstance(reason, TimeoutError):
            detail = f"timed out after {timeout_s:g}s"
        elif isinstance(reason, ConnectionRefusedError):
            detail = "connection refused"
        elif isinstance(reason, socket.gaierror):
            detail = f"DNS lookup failed ({reason})"
        else:
            detail = str(reason) or exc.__class__.__name__
        raise MCPConnectionError(_mcp_error_message(url, detail)) from exc
    except TimeoutError as exc:
        raise MCPConnectionError(
            _mcp_error_message(url, f"timed out after {timeout_s:g}s")
        ) from exc
    except OSError as exc:
        raise MCPConnectionError(_mcp_error_message(url, str(exc))) from exc


def _resolve_reducer(reducer: str, k: int) -> str:
    """Compose a concrete reducer name from a family + k (``pass_at`` -> ``pass_at_3``).

    A bare k-parameterized family gets ``_{k}`` appended; an already-concrete
    name (``pass_at_2``, ``mean``, ...) is passed through unchanged.
    """
    if reducer in _K_PARAM_REDUCERS:
        return f"{reducer}_{k}"
    return reducer

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Callable

    from .case import Case, Suite


def _sample_target(case: "Case", suite: "Suite") -> str:
    """The Sample target: gold rows for an ``answer`` case, else empty.

    Inspect targets are strings, so the gold row-set is JSON-encoded here and
    the deterministic-EX scorer decodes it back to rows. ``clarify`` /
    ``abstain`` cases have no row target (they score on behaviour), so their
    target is the empty string.
    """
    if case.gold_id and case.gold_id in suite.gold:
        rows = suite.gold[case.gold_id].get("rows")
        if rows is not None:
            return json.dumps(rows)
    return ""


def _sample_metadata(case: "Case", suite: "Suite") -> dict:
    """Sample metadata: routing keys + judge-only context, never agent-visible."""
    meta = {
        "bucket": case.expect,
        "cluster": case.gold_id or case.id,
        "feasible": case.expect != ABSTAIN,
        # The judge grades a sample against its bucket's check list (from the
        # suite's checks()/checks.json). An untyped checks.json lowers all
        # criteria to a catch-all "judge" bucket (graded against every sample);
        # typed checks() route per bucket. Union both so either shape works.
        # Carried here for the judge scorer; NEVER part of the agent-visible input.
        "judge_checks": list(suite.checks.get(case.expect, []))
        + list(suite.checks.get("judge", [])),
    }
    # The intended slot selection for slot_match, read off the gold record the
    # case points at. scorers._gold_selection reads this exact shape back out.
    if case.gold_id and case.gold_id in suite.gold:
        rec = suite.gold[case.gold_id]
        meta["gold_selection"] = {
            "measures": list(rec.get("measures") or []),
            "group_by": list(rec.get("group_by") or []),
            "filters": list(rec.get("filters") or []),
        }
    # Judge-only context (why / gold_note / raw check text) rides along for the
    # scorer; it is NOT part of the Sample input, so the agent never sees it.
    # Placed last so a case can still override the derived gold_selection.
    meta.update(case.metadata)
    return meta


def case_to_sample(case: "Case", suite: "Suite") -> Sample:
    """Lower one ``Case`` into an Inspect ``Sample`` (agent sees ONLY the input)."""
    return Sample(
        id=case.id,
        input=case.question,
        target=_sample_target(case, suite),
        metadata=_sample_metadata(case, suite),
    )


def build_task(
    suite: "Suite",
    *,
    target: str | None = None,
    server_factory: "Callable[[], Any] | None" = None,
    agent_prompt: str | None = None,
    agent_model: str | None = None,
    authorization: str | None = None,
    grader_model: str | None = None,
    epochs: int = 1,
    epochs_reducer: str = "pass_at",
) -> Task:
    """Assemble the Inspect ``Task`` for a suite (dataset + solver + scorers).

    The agent's server resolves from ``server_factory`` (a zero-arg thunk
    returning a pre-built Inspect MCP server, e.g. ``mcp_server_stdio(...)``) then
    ``target`` (an MCP URL), falling back to the suite's own ``server_factory`` /
    ``target``. A suite with none of these is a build error — the agent has
    nothing to drive. ``agent_prompt`` overrides the default agent system prompt.
    ``authorization`` is forwarded to the HTTP MCP server when a URL transport is
    used. ``grader_model``, when given, wires a ``grader`` model role for the
    judge scorer. Epochs > 1 attaches an ``Epochs(k, reducer)`` policy.
    """
    factory = server_factory or suite.server_factory
    mcp_url = target or suite.target
    if factory is None and not mcp_url:
        raise ValueError(
            f"suite {suite.name!r}: no MCP server (pass server_factory= / target= "
            f"or set Suite.server_factory / Suite.target) — the react agent has "
            f"no server to drive"
        )

    dataset = [case_to_sample(c, suite) for c in suite.cases]
    # A stdio server_factory wins over a URL: it is the teardown-safe transport
    # (see solver.py / the README "Transport" note). Build a fresh server per run.
    server = factory() if factory is not None else None
    solver = mcp_solver(
        mcp_url,
        server=server,
        prompt=agent_prompt,
        model=agent_model,
        authorization=authorization,
    )
    scorer = scorers_for(suite)

    model_roles = {"grader": grader_model} if grader_model else None
    epochs_policy = (
        Epochs(epochs, _resolve_reducer(epochs_reducer, epochs))
        if epochs and epochs > 1
        else None
    )

    return Task(
        dataset=dataset,
        solver=solver,
        scorer=scorer,
        model_roles=model_roles,
        epochs=epochs_policy,
        display_name=suite.name,
    )


def _run_suite_once(
    suite: "Suite",
    *,
    variant: str = "current_pack",
    mcp_url: str | None = None,
    server_factory: "Callable[[], Any] | None" = None,
    agent_prompt: str | None = None,
    agent_model: str | None = None,
    authorization: str | None = None,
    grader_model: str | None = None,
    epochs: int = 1,
    epochs_reducer: str = "pass_at",
    log_dir: str | Path = "./logs",
    display: str = "none",
) -> Path:
    """Run a suite end to end and return the path to the ``.eval`` log.

    Lowers ``suite`` into an Inspect ``Task``, runs ``inspect_ai.eval`` against
    ``agent_model`` (with an optional ``grader`` model role for the judge slot
    and an ``Epochs(k, reducer)`` policy), and returns the written log's path for
    :class:`nxd_eval.report.Report` / :func:`nxd_eval.certify.certify` to read.

    The agent's server is chosen by ``server_factory`` (a zero-arg thunk building
    a pre-built stdio MCP server — the teardown-safe default) then ``mcp_url``,
    falling back to the suite's own wiring. ``agent_prompt`` overrides the agent
    system prompt. URL transports are preflighted before Inspect starts the eval
    so bad paths, auth, and reachability failures raise :class:`MCPConnectionError`
    with the HTTP status or network failure.

    ``variant`` (``no_skills`` / ``current_pack`` / ``candidate_pack``) **labels**
    the run on its metadata so the report can pair variants on the same cases. It
    is validated here so a typo fails loudly instead of silently mislabelling a
    run. It does NOT select the agent's skill context: nothing below installs or
    removes skills, so the caller must arrange that before calling. Passing two
    different variants without doing so runs the identical agent twice and makes
    any resulting lift number meaningless.
    """
    if variant not in VARIANTS:
        raise ValueError(f"variant must be one of {VARIANTS}; got {variant!r}")

    # Imported here to keep the authoring/import path free of the eval runtime.
    from inspect_ai import eval as inspect_eval

    check_inspect_model_dependency(agent_model, role="agent_model")
    check_inspect_model_dependency(grader_model, role="grader_model")

    factory = server_factory or suite.server_factory
    target = mcp_url or suite.target
    if factory is None and target:
        preflight_mcp_http_endpoint(target, authorization=authorization)

    task = build_task(
        suite,
        target=mcp_url,
        server_factory=server_factory,
        agent_prompt=agent_prompt,
        agent_model=agent_model,
        authorization=authorization,
        grader_model=grader_model,
        epochs=epochs,
        epochs_reducer=epochs_reducer,
    )

    logs = inspect_eval(
        task,
        model=agent_model,
        log_dir=str(log_dir),
        display=display,
        metadata={"variant": variant, "suite": suite.name},
    )
    if not logs:
        raise RuntimeError(f"suite {suite.name!r}: eval() returned no logs")
    location = getattr(logs[0], "location", None)
    if not location:
        raise RuntimeError(
            f"suite {suite.name!r}: eval log has no on-disk location to read back"
        )
    return Path(location)


def run_suite(
    suite: "Suite",
    *,
    variant: str = "current_pack",
    mcp_url: str | None = None,
    server_factory: "Callable[[], Any] | None" = None,
    agent_prompt: str | None = None,
    agent_model: str | None = None,
    authorization: str | None = None,
    grader_model: str | None = None,
    epochs: int = 1,
    epochs_reducer: str = "pass_at",
    log_dir: str | Path = "./logs",
    display: str = "none",
    isolate_sessions: bool = False,
) -> Path:
    """Run a suite and return its ``.eval`` log.

    Set ``isolate_sessions=True`` for stateful MCP servers. Each case then runs
    as its own Inspect task (and therefore gets a fresh MCP connection); their
    logs are collated atomically into the one path returned here.
    """
    if isolate_sessions:
        # Validate suite-wide configuration outside the per-case error boundary.
        # A missing provider package or unreachable endpoint is a setup error,
        # not one failed case repeated N times.
        if variant not in VARIANTS:
            raise ValueError(f"variant must be one of {VARIANTS}; got {variant!r}")
        check_inspect_model_dependency(agent_model, role="agent_model")
        check_inspect_model_dependency(grader_model, role="grader_model")
        factory = server_factory or suite.server_factory
        target = mcp_url or suite.target
        if factory is None and not target:
            raise ValueError(
                f"suite {suite.name!r}: no MCP server (pass server_factory= / target= "
                f"or set Suite.server_factory / Suite.target) — the react agent has "
                "no server to drive"
            )
        if factory is None:
            preflight_mcp_http_endpoint(target, authorization=authorization)

        from .session_isolation import run_suite_isolated

        return run_suite_isolated(
            suite,
            run_one=_run_suite_once,
            variant=variant,
            mcp_url=mcp_url,
            server_factory=server_factory,
            agent_prompt=agent_prompt,
            agent_model=agent_model,
            authorization=authorization,
            grader_model=grader_model,
            epochs=epochs,
            epochs_reducer=epochs_reducer,
            log_dir=log_dir,
            display=display,
        )
    return _run_suite_once(
        suite,
        variant=variant,
        mcp_url=mcp_url,
        server_factory=server_factory,
        agent_prompt=agent_prompt,
        agent_model=agent_model,
        authorization=authorization,
        grader_model=grader_model,
        epochs=epochs,
        epochs_reducer=epochs_reducer,
        log_dir=log_dir,
        display=display,
    )
