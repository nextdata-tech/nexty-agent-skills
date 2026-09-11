"""Shared plumbing for the run_eval*.py CLI entrypoints.

Everything here was previously duplicated byte-for-byte across run_eval.py,
run_eval_isolated.py, and run_eval_perplexity.py: glossary-instruction
derivation, MCP URL validation, the Inspect/nxd_eval compatibility patches,
the mesh scope guard, and the argparse/server_factory scaffolding shared by
every entrypoint. Each run_eval*.py now imports from here and keeps only the
logic that's actually specific to it (Perplexity routing, session isolation).
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
from typing import Any, Callable
from urllib.parse import urlparse

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _glossary_name_from_url(url: str) -> str:
    """Derive a glossary data-product name from its URL's data-product path segment.

    Strips any '#/terms/...' fragment first, so a term-specific glossary link
    (".../data-product/nxd/indication-performance-glossary#/terms/pums") and a
    bare data-product URL (".../data-product/demo/argenx-glossary") both reduce
    to the same "<name>-<owner>" form.
    """
    base = url.split("#", 1)[0]
    parts = base.rstrip("/").split("/")
    return "-".join(reversed(parts[-2:]))


def _glossary_urls_from_models(models_tree: ast.AST) -> list[str]:
    """Find every glossary URL models.py links terms against, if any.

    models.py may call `.link(<attr>, Predicate.GlossaryTerm, "<url>")` per
    metric/dimension to attach a glossary term. This is more authoritative
    than spec.py's `_GLOSSARY` constant, which can go stale (point at a
    generic demo glossary that doesn't carry the product's real synonyms)
    while models.py's per-term links still point at the real deployed one.
    Returns URLs in first-seen order, deduplicated.
    """
    urls: list[str] = []
    for node in ast.walk(models_tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "link"
            and len(node.args) >= 3
        ):
            predicate_arg = node.args[1]
            if (
                isinstance(predicate_arg, ast.Attribute)
                and predicate_arg.attr == "GlossaryTerm"
            ):
                try:
                    url = ast.literal_eval(node.args[2])
                except (ValueError, SyntaxError):
                    continue
                if url not in urls:
                    urls.append(url)
    return urls


def _source_metadata() -> tuple[str, str, list[str]]:
    models_path = os.path.join(_PROJECT_ROOT, "models.py")
    spec_path = os.path.join(_PROJECT_ROOT, "spec.py")
    with open(models_path, encoding="utf-8") as source:
        models_tree = ast.parse(source.read(), filename=models_path)
    with open(spec_path, encoding="utf-8") as source:
        spec_tree = ast.parse(source.read(), filename=spec_path)

    model_name = next(
        ast.literal_eval(node.args[0])
        for node in ast.walk(models_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "semantic_view"
    )
    product_name = next(
        ast.literal_eval(keyword.value)
        for node in ast.walk(spec_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "data_product"
        for keyword in node.keywords
        if keyword.arg == "name"
    )
    spec_glossary_url = next(
        ast.literal_eval(node.value)
        for node in spec_tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "_GLOSSARY" for target in node.targets)
    )

    # Combine both sources: models.py's per-term links are the authoritative,
    # verified-working ones (see indication-performance-v1, where spec.py's
    # `_GLOSSARY` constant pointed at the generic argenx-glossary-demo and was
    # proven NOT to carry this product's real synonyms, e.g. no "subq" entry).
    # spec.py's constant is still included as a secondary tool in case a term
    # is only resolvable there -- deduplicated, models.py-derived names first.
    glossary_urls = _glossary_urls_from_models(models_tree)
    if spec_glossary_url not in glossary_urls:
        glossary_urls.append(spec_glossary_url)
    glossary_names = [_glossary_name_from_url(url) for url in glossary_urls]
    seen: set[str] = set()
    glossary_names = [n for n in glossary_names if not (n in seen or seen.add(n))]

    return product_name, model_name, glossary_names


_PRODUCT_NAME, _MODEL_NAME, _GLOSSARY_NAMES = _source_metadata()
_GLOSSARY_NAMES_TEXT = " and ".join(_GLOSSARY_NAMES) if len(_GLOSSARY_NAMES) <= 2 else (
    ", ".join(_GLOSSARY_NAMES[:-1]) + f", and {_GLOSSARY_NAMES[-1]}"
)

GLOSSARY_INSTRUCTION = (
    f"Do not memorize the outcome of any semantic query. "
    f"When the question contains a business term, synonym, abbreviation, or product alias "
    f"for {_PRODUCT_NAME}, there are multiple deployed glossary tools that may resolve it: "
    f"{_GLOSSARY_NAMES_TEXT}. Check ALL of them -- do not stop at the first one queried, "
    f"and do not assume the first glossary checked is authoritative just because it returned "
    f"a result. A term may be missing from one glossary and present in another; only after "
    f"checking every listed glossary tool should you query {_PRODUCT_NAME}'s {_MODEL_NAME} "
    f"model. Use the canonical glossary value as the semantic dimension value -- if more than "
    f"one glossary defines the term with different canonical values, prefer the definition "
    f"that is scoped to this specific product/data domain over a generic or unrelated one, "
    f"and say so in your answer. Select the metric whose catalog description matches the "
    f"question: product-level PUMs require PUMS_BY_PRODUCT grouped by product_name, while "
    f"the de-duplicated total uses PUMS without product grouping. If none of the glossary "
    f"tools has an unambiguous match, ask for clarification. Do not invent synonym mappings."
)


def _with_glossary_instruction(suite: Any) -> Any:
    return replace(
        suite,
        cases=[
            replace(case, question=f"{case.question}\n\n{GLOSSARY_INSTRUCTION}")
            for case in suite.cases
        ],
    )


def _validate_mcp_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.netloc.startswith("app."):
        raise SystemExit(
            "--mcp-url points at the Nextopia web app host, which serves HTML, "
            "not MCP. Use the data-plane MCP gateway from `nxd mcp config`."
        )
    if not parsed.path.rstrip("/").endswith("/mcp"):
        raise SystemExit(
            "--mcp-url should end with /mcp or /mcp/. Get the exact endpoint "
            "from `nxd mcp config`."
        )


def _normalize_nullable_types(schema: Any) -> Any:
    """Adapt JSON Schema nullable type lists for this Inspect version."""
    if isinstance(schema, list):
        return [_normalize_nullable_types(item) for item in schema]
    if not isinstance(schema, dict):
        return schema

    normalized = {
        key: _normalize_nullable_types(value)
        for key, value in schema.items()
    }
    type_value = normalized.get("type")
    if isinstance(type_value, list):
        non_null_types = [item for item in type_value if item != "null"]
        if len(non_null_types) == 1:
            normalized["type"] = non_null_types[0]
            normalized.setdefault("default", None)
        else:
            normalized.pop("type")
            normalized["anyOf"] = [{"type": item} for item in type_value]
    return normalized


def _patch_inspect_mcp_schema_compat() -> None:
    """Patch Inspect's MCP adapter to accept standard nullable JSON Schema."""
    from inspect_ai.tool._mcp import _local as mcp_local

    if getattr(mcp_local.MCPServerLocalSession, "_nxd_nullable_patch", False):
        return

    original = mcp_local.MCPServerLocalSession._tool_def_from_mcp_tool

    def patched(self: Any, mcp_tool: Any) -> Any:
        input_schema = getattr(mcp_tool, "inputSchema", None)
        if isinstance(input_schema, dict):
            normalized = _normalize_nullable_types(deepcopy(input_schema))
            if normalized != input_schema:
                mcp_tool = mcp_tool.model_copy(update={"inputSchema": normalized})
        return original(self, mcp_tool)

    mcp_local.MCPServerLocalSession._tool_def_from_mcp_tool = patched
    mcp_local.MCPServerLocalSession._nxd_nullable_patch = True


# The mesh MCP gateway multiplexes every data product on the mesh, so it re-exports
# each DP's semantic tools under a per-DP suffix — `run_semantic_query__grtmoib26y`,
# not `run_semantic_query`. nxd_eval 0.1.0 matches the bare name exactly
# (transcript.QUERY_TOOL), so it extracts NO queries from the transcript and every
# `answer` case scores INCORRECT with verdict ABSTAIN however well the agent did.
# The same mesh multiplexing means the agent's tool list can include OTHER data
# products' identically-shaped list_models/describe_model/run_semantic_query
# tools (observed: a `DP_TEST_DP` data product bleeding into an
# indication-performance session, its PUMS_BY_PRODUCT/PUMS/ENROLLMENTS/etc.
# metrics silently answering questions this data product never exposes). There
# is no per-DP token scoping available from `nxd mcp client`/`nxd create
# personal-access-token` today, so this can only be mitigated at the prompt
# layer here, not eliminated at the transport layer.
MESH_SCOPE_GUARD = (
    "\n\nThis MCP session's tool list is mesh-wide: it may include "
    "list_models/describe_model/run_semantic_query tools from OTHER, unrelated "
    "data products that happen to share this token, not just indication-performance. "
    "Before trusting ANY of these tools, call its list_models and confirm the "
    "response includes indication-performance's real models -- rpt_patient_detail, "
    "patient_details_metrics, hcp_targets, hcp_profile, hcp_journey_activity. If a "
    "tool's list_models output does not include these, it belongs to a different "
    "data product: do not use it, and do not treat any metric or value it returns "
    "(e.g. a metric literally named PUMS_BY_PRODUCT, which this data product does "
    "not expose) as an indication-performance answer."
)

# describe_model's per-metric `compatible_dimensions` list is computed by the platform's
# join-graph registry and can be stale/incomplete relative to what run_semantic_query
# actually accepts. Observed directly: `pums` on `patient_details_metrics` reports
# compatible_dimensions: [] in describe_model, yet run_semantic_query(measures=["pums"],
# group_by=["indication"]) succeeds and returns correct grouped rows (confirmed across
# multiple real runs). Without this guard, an agent that takes the empty list at face
# value abstains on perfectly answerable questions ("PUMs cannot be sliced by indication")
# -- nondeterministically, since whether it trusts the catalog metadata over trying the
# query is a per-run judgment call, not a fixed decision. Prompted here rather than fixed
# in models.py because the metadata comes from the platform's registry computation, not
# this repo's semantic model definition.
DIMENSION_METADATA_GUARD = (
    "\n\nA metric's `compatible_dimensions` list from describe_model can be stale or "
    "incomplete -- it has been confirmed empty for a metric that a real run_semantic_query "
    "call with that dimension in group_by still answered correctly. Do not treat an empty "
    "or partial compatible_dimensions list as proof a dimension is unsupported, and do not "
    "abstain or say a grouping is impossible on that basis alone. If the question asks to "
    "group a metric by a dimension that exists elsewhere in this data product's catalog, "
    "attempt the run_semantic_query call with that measure and dimension before concluding "
    "it is infeasible. Only treat the dimension as genuinely unsupported if that actual "
    "query call itself returns a validation error naming it."
)

_QUERY_TOOL_RE = re.compile(r"^run_semantic_query(?:__.+)?$")

# Guard so _patch_transcript_compat() is idempotent. Held here rather than stamped
# onto nxd_eval.scorers so neither linter objects to writing an unknown attribute
# on a foreign module.
_TRANSCRIPT_PATCHED = False


def _canonical_tool_name(name: Any) -> Any:
    """Strip the gateway's per-DP suffix off a semantic-query tool name."""
    if isinstance(name, str) and _QUERY_TOOL_RE.match(name):
        return "run_semantic_query"
    return name


def _shim_messages(messages: list[Any]) -> list[Any]:
    """Re-present a message list with canonical tool names, for transcript.extract.

    extract() reads messages by attribute — role/function/tool_call_id/text/content
    on the message, id/function/arguments on each tool call — so plain namespaces
    are enough and stay decoupled from Inspect's message classes. Building shims
    rather than mutating leaves the real TaskState (and the written .eval log)
    carrying the true suffixed tool names.
    """
    out = []
    for msg in messages:
        calls = getattr(msg, "tool_calls", None)
        out.append(
            SimpleNamespace(
                role=getattr(msg, "role", None),
                function=_canonical_tool_name(getattr(msg, "function", None)),
                tool_call_id=getattr(msg, "tool_call_id", None),
                text=getattr(msg, "text", None),
                content=getattr(msg, "content", None),
                tool_calls=[
                    SimpleNamespace(
                        id=getattr(tc, "id", None),
                        function=_canonical_tool_name(getattr(tc, "function", None)),
                        arguments=getattr(tc, "arguments", None),
                    )
                    for tc in calls
                ]
                if calls
                else calls,
            )
        )
    return out


def _rows_as_dicts(result: dict[str, Any] | None) -> dict[str, Any] | None:
    """Zip the tool's positional row payload into the dicts the scorer compares.

    run_semantic_query returns rows as JSON-encoded arrays with the names carried
    separately — {"columns": ["PUMS"], "rows": ["[22583.0]"]} — while the scoring
    core indexes each row by column name and raises AttributeError on a str.
    Anything that does not match that exact shape is passed through untouched, so
    a future payload change fails loudly rather than being silently remapped.
    """
    if not isinstance(result, dict):
        return result
    rows = result.get("rows")
    columns = result.get("columns")
    if not isinstance(rows, list) or not isinstance(columns, list) or not columns:
        return result

    remapped = []
    for row in rows:
        if isinstance(row, dict):
            remapped.append(row)
            continue
        if isinstance(row, str):
            try:
                row = json.loads(row)
            except ValueError:
                return result
        if not isinstance(row, list) or len(row) != len(columns):
            return result
        remapped.append(dict(zip(columns, row)))
    return {**result, "rows": remapped}


def _normalize_call(call: Any) -> Any:
    """Re-present one QueryCall with dict rows and a truthful `errored` flag.

    run_semantic_query returns `"error": ""` on success, but extract() flags a call
    as errored whenever the key holds any string — so every successful query is
    treated as a failure and last_answered_call() finds nothing to score. Only a
    non-empty error is a real one.
    """
    result = _rows_as_dicts(call.result)
    error = result.get("error") if isinstance(result, dict) else None
    errored = isinstance(error, str) and bool(error.strip())
    return replace(call, result=result, errored=errored)


def _patch_transcript_compat() -> None:
    """Make the deterministic scorers see the gateway's queries and rows.

    Three incompatibilities between nxd_eval 0.1.0 and the deployed MCP gateway,
    each of which alone makes an `answer` case score INCORRECT no matter what the
    agent did: the suffixed tool name (see _QUERY_TOOL_RE), the positional row
    payload (see _rows_as_dicts), and the empty-string success `error` (see
    _normalize_call). Patched here rather than in the installed package, alongside
    the Inspect schema patch above. Drop this once nxd_eval handles all three.
    """
    global _TRANSCRIPT_PATCHED

    from nxd_eval import scorers

    if _TRANSCRIPT_PATCHED:
        return

    original = scorers.extract

    def patched(state: Any) -> Any:
        messages = list(getattr(state, "messages", []) or [])
        tx = original(SimpleNamespace(messages=_shim_messages(messages)))
        if not tx.calls:
            return tx
        return replace(tx, calls=[_normalize_call(c) for c in tx.calls])

    scorers.extract = patched
    _TRANSCRIPT_PATCHED = True


# Guard so _patch_judge_grader_messages() is idempotent.
_JUDGE_PATCHED = False


def _patch_judge_grader_messages() -> None:
    """Fix judge scorer message construction to avoid empty content arrays.

    The judge scorer constructs ChatMessageSystem and ChatMessageUser objects
    with text content, but Inspect/Anthropic SDK serialization can result in
    malformed messages with empty content arrays. This patch replaces the judge
    scorer function to ensure messages are properly formatted before grading.
    """
    global _JUDGE_PATCHED

    from nxd_eval import scorers
    from inspect_ai.scorer import Score, Scorer, Target, scorer
    from inspect_ai.solver import TaskState
    from inspect_ai.model import ChatMessageSystem, ChatMessageUser, get_model
    import zlib

    if _JUDGE_PATCHED:
        return

    from nxd_eval.scorers import (
        _JUDGE_SYSTEM, _judge_prompt, _parse_grade, _debias_order,
        _judge_retest_enabled, NOANSWER,
        extract, mean, stderr
    )

    @scorer(name="judge", metrics=[mean(), stderr()])
    def patched_judge() -> Scorer:
        """Model-graded checks scorer with safe message construction."""
        async def score(state: TaskState, target: Target) -> Score:
            meta = state.metadata or {}
            checks = list(meta.get("judge_checks", []) or [])
            if not checks:
                return Score(value=NOANSWER, metadata={"reason": "no checks for bucket"})

            tx = extract(state)
            model = get_model(role="grader", default=None) or get_model()

            base_seed = zlib.crc32(str(state.sample_id).encode()) & 0x7FFFFFFF
            prompt = _judge_prompt(str(state.input), tx, checks, order_seed=base_seed)

            # Ensure content is non-empty before sending
            system_msg = str(_JUDGE_SYSTEM).strip() or "You are a grader."
            prompt_msg = str(prompt).strip() or "Grade the response."

            try:
                result = await model.generate(
                    [
                        ChatMessageSystem(content=system_msg),
                        ChatMessageUser(content=prompt_msg),
                    ]
                )
                grade = _parse_grade(result.completion)
            except Exception as e:
                error_str = str(e)
                if "content" in error_str.lower() or "validation" in error_str.lower():
                    return Score(
                        value=NOANSWER,
                        metadata={"reason": "grader_message_error", "error": error_str[:150]}
                    )
                raise

            score_meta: dict[str, Any] = {"n_checks": len(checks), "grade_1": grade}

            if _judge_retest_enabled():
                retest_seed = base_seed ^ 0x5EED
                if _debias_order(checks, seed=retest_seed) != _debias_order(
                    checks, seed=base_seed
                ):
                    prompt2 = _judge_prompt(
                        str(state.input), tx, checks, order_seed=retest_seed
                    )
                    prompt2_msg = str(prompt2).strip() or "Grade the response."
                    try:
                        result2 = await model.generate(
                            [
                                ChatMessageSystem(content=system_msg),
                                ChatMessageUser(content=prompt2_msg),
                            ]
                        )
                        score_meta["grade_2"] = _parse_grade(result2.completion)
                    except Exception:
                        pass  # Skip retest on error

            return Score(
                value=grade,
                answer=tx.final_answer,
                explanation=result.completion[:2000],
                metadata=score_meta,
            )

        return score

    scorers.judge = patched_judge
    _JUDGE_PATCHED = True


def apply_common_patches() -> None:
    """Apply the three nxd_eval/Inspect compatibility patches every entrypoint needs."""
    _patch_inspect_mcp_schema_compat()
    _patch_transcript_compat()
    _patch_judge_grader_messages()


def maybe_apply_session_isolation(no_session_isolation: bool) -> None:
    """Patch nxd_eval.run_suite for per-case isolation, unless disabled.

    Shared by every entrypoint: without isolation, a02-pums-total fails with
    an API 400 error caused by message-history pollution from a01 (see
    session_isolation.py).
    """
    if no_session_isolation:
        return
    try:
        from session_isolation import patch_run_suite_for_isolation
        patch_run_suite_for_isolation()
        print("✓ Session isolation enabled (each test case runs with fresh MCP connection)")
    except ImportError:
        import sys
        print(
            "⚠ session_isolation module not found. "
            "Without isolation, a02-pums-total will fail with API 400 error.",
            file=sys.stderr,
        )


# Per-provider default model names, applied after argparse if the caller
# didn't pass --agent-model/--grader-model explicitly.
PROVIDER_DEFAULT_MODELS = {
    "anthropic": {"agent": "anthropic/claude-sonnet-5", "grader": "anthropic/claude-opus-4-8"},
    "perplexity": {"agent": "claude-sonnet-4-5", "grader": "claude-opus-4-5"},
}


def build_arg_parser(description: str) -> argparse.ArgumentParser:
    """Build the CLI argument parser shared by every run_eval*.py entrypoint.

    Callers may still add script-specific arguments to the returned parser
    before calling parse_args(). --agent-model/--grader-model default to
    None here; resolve_model_defaults() fills in the right provider default
    once --provider is known.
    """
    p = argparse.ArgumentParser(description=description)
    p.add_argument("--mcp-url", required=True, help="indication-performance-v2 semantic MCP URL")
    p.add_argument(
        "--provider",
        choices=("anthropic", "perplexity"),
        default="perplexity",
        help="model provider to run the agent/grader through (default: perplexity)",
    )
    p.add_argument(
        "--mcp-token-env",
        default="NXD_MCP_AUTH_TOKEN",
        help="environment variable containing the MCP bearer token, if required",
    )
    p.add_argument(
        "--mcp-transport",
        choices=("stdio", "http"),
        default="stdio",
        help="MCP transport to use; stdio wraps `nxd mcp client` and is the default",
    )
    p.add_argument(
        "--mcp-execution",
        choices=("local", "remote"),
        default="remote",
        help="HTTP-only: where Inspect executes MCP calls",
    )
    p.add_argument("--nxd-command", default="nxd", help="nxd executable for stdio MCP transport")
    p.add_argument(
        "--agent-model",
        default=None,
        help="defaults to anthropic/claude-sonnet-5 or claude-sonnet-4-5, per --provider",
    )
    p.add_argument(
        "--grader-model",
        default=None,
        help="defaults to anthropic/claude-opus-4-8 or claude-opus-4-5, per --provider",
    )
    p.add_argument("--epochs", type=int, default=5)
    p.add_argument("--log-dir", default="./logs")
    p.add_argument(
        "--only",
        nargs="*",
        metavar="CASE_ID",
        help="run only these case ids (default: the whole suite)",
    )
    p.add_argument(
        "--no-session-isolation",
        action="store_true",
        help=(
            "disable isolated sessions per test (NOT RECOMMENDED; causes a02 API 400 "
            "error and reverts to nxd_eval's default of stopping the suite on the "
            "first case that errors or fails)"
        ),
    )
    return p


def resolve_model_defaults(args: argparse.Namespace) -> None:
    """Fill in --agent-model/--grader-model from PROVIDER_DEFAULT_MODELS if unset.

    Mutates `args` in place so callers can just read args.agent_model /
    args.grader_model afterwards.
    """
    defaults = PROVIDER_DEFAULT_MODELS[args.provider]
    if args.agent_model is None:
        args.agent_model = defaults["agent"]
    if args.grader_model is None:
        args.grader_model = defaults["grader"]


def filter_suite_to_only(suite: Any, only: list[str] | None, full_suite: Any) -> Any:
    """Narrow `suite` to the `--only` case ids, validating against `full_suite`.

    `full_suite` is the unfiltered SUITE (used for the "available ids" error
    message), since `suite` here may already carry the glossary-instruction
    rewrite applied on top of it.
    """
    if not only:
        return suite
    wanted = set(only)
    keep = [c for c in suite.cases if c.id in wanted]
    if not keep:
        raise SystemExit(
            "--only matched no cases. Available ids:\n  "
            + "\n  ".join(c.id for c in full_suite.cases)
        )
    missing = wanted - {c.id for c in keep}
    if missing:
        raise SystemExit(f"--only: no such case id(s): {', '.join(sorted(missing))}")
    suite = replace(suite, cases=keep)
    print(f"Running {len(keep)} of {len(full_suite.cases)} cases: {', '.join(c.id for c in keep)}")
    return suite


def build_server_factory(args: argparse.Namespace, token: str | None) -> Callable[[], Any]:
    """Build the MCP server_factory for the transport args select, stdio or http."""
    if args.mcp_transport == "stdio":
        if not token:
            raise SystemExit(
                f"{args.mcp_token_env} is not set. Generate a PAT with "
                "`nxd create personal-access-token`, then export it before running."
            )
        from inspect_ai.tool import mcp_server_stdio

        parsed = urlparse(args.mcp_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}/dp"
        server_args = [
            "--skip-version-check",
            "mcp",
            "client",
            "--base-url",
            base_url,
            "--token",
            token,
        ]

        return lambda: mcp_server_stdio(
            name="semantic",
            command=args.nxd_command,
            args=server_args,
        )

    from inspect_ai.tool import mcp_server_http

    return lambda: mcp_server_http(
        name="semantic",
        url=args.mcp_url,
        authorization=token,
        execution=args.mcp_execution,
    )


def print_server_config(args: argparse.Namespace, token: str | None) -> None:
    print(
        f"Configured MCP server: {args.mcp_url} "
        f"(transport={args.mcp_transport}, execution={args.mcp_execution}, "
        f"token_env={args.mcp_token_env}, "
        f"token_set={bool(token)})"
    )
