#!/usr/bin/env python3
"""Run the indication-performance-v2 nxd_eval suite against a deployed MCP endpoint.

    python run_eval.py --mcp-url <mcp-url> --provider perplexity \\
        --epochs 5 --log-dir ./logs

    python run_eval.py --mcp-url <mcp-url> --provider anthropic \\
        --epochs 5 --log-dir ./logs

--provider selects the model backend: `perplexity` (default) routes the
agent/grader models through Perplexity's Agent API (requires
PERPLEXITY_API_KEY); `anthropic` talks to Claude directly. --agent-model/
--grader-model default per-provider (see eval_common.PROVIDER_DEFAULT_MODELS)
and can be overridden either way.

Session isolation (a fresh MCP connection per case) is on by default -- pass
--no-session-isolation to disable it (NOT recommended; see eval_common.py).

Pass --only <case-id>... to run a subset of the suite; the full 30 cases at 5
epochs is 150 agent samples, which is the expensive default.

See README.md for how to obtain --mcp-url and the required model-provider API
key(s). If the MCP endpoint requires auth, set NXD_MCP_AUTH_TOKEN to a bearer
token. Prints the path to the written .eval log; feed that path to
`python -m nxd_eval report` / `python -m nxd_eval certify`.

Only g_pums_total is frozen in gold/patient_details_tableau_reporting.freeze.json,
so every other `answer` case still scores FAIL on rows — see README.md.
"""

from __future__ import annotations

import os
from typing import Any

from suite import SUITE

from eval_common import (
    DIMENSION_METADATA_GUARD,
    MESH_SCOPE_GUARD,
    apply_common_patches,
    build_arg_parser,
    build_server_factory,
    filter_suite_to_only,
    maybe_apply_session_isolation,
    print_server_config,
    resolve_model_defaults,
    _patch_inspect_mcp_schema_compat,
    _patch_transcript_compat,
    _validate_mcp_url,
    _with_glossary_instruction,
)

# -- Perplexity-only plumbing -----------------------------------------------
#
# Perplexity retired tool-calling on the classic Sonar /chat/completions
# surface in favor of the Agent API, which speaks the OpenAI *Responses* API
# (/v1/responses) instead and can route to real Anthropic models
# (`anthropic/claude-*`). Inspect AI still creates an OpenAI-provider model
# when it sees the 'openai/' prefix, but that provider must be forced into
# responses-API mode (`responses_api=True`) to hit /v1/responses rather than
# /v1/chat/completions -- see _patch_for_agent_api().


def _setup_perplexity_via_openai() -> None:
    """Route the OpenAI client at Perplexity's Agent API."""
    api_key = os.environ.get("PERPLEXITY_API_KEY")
    if not api_key:
        raise SystemExit(
            "PERPLEXITY_API_KEY environment variable is not set. "
            "Set it before running --provider perplexity."
        )
    # The /v1 suffix matters: the openai SDK posts to f"{OPENAI_BASE_URL}/responses".
    os.environ["OPENAI_API_KEY"] = api_key
    os.environ["OPENAI_BASE_URL"] = "https://api.perplexity.ai/v1"
    print("Configured to route OpenAI client calls to Perplexity's Agent API")


def _agent_api_model(name: str) -> str:
    """Build the `openai/anthropic/<slug>` Inspect model string for a Perplexity
    Agent API model. `openai/` selects Inspect's OpenAI-compatible provider
    (which our OPENAI_BASE_URL points at Perplexity); `name` must already be
    one of Perplexity's current-generation Anthropic slugs (see
    eval_common.PROVIDER_DEFAULT_MODELS) -- it is sent verbatim as the Agent
    API's `model` field, with no legacy-name resolution.
    """
    slug = name if name.startswith("anthropic/") else f"anthropic/{name}"
    return f"openai/{slug}"


def _patch_for_agent_api(max_output_tokens: int = 4096) -> None:
    """Force responses-API mode + a required max_output_tokens everywhere
    Inspect resolves a `openai/anthropic/...` model string.

    Two separate call paths need this:
    - the primary agent model, resolved inside `inspect_ai.eval()` from its
      `model_args`/`GenerateConfigArgs` kwargs;
    - model_roles (e.g. the grader), resolved by
      `inspect_ai._eval.task.task.resolve_model_roles()`, which calls
      `get_model()` directly with no model_args at all.
    Both are patched so a single `openai/anthropic/...` string works in
    either position without every caller having to know about Perplexity's
    Agent API quirks.
    """
    import inspect_ai
    import inspect_ai.model._model as _model_mod
    import inspect_ai._eval.task.task as _task_mod
    import inspect_ai.agent._react as _react_mod
    from inspect_ai.model import GenerateConfig

    def _is_agent_api_model(model: Any) -> bool:
        return isinstance(model, str) and model.startswith("openai/anthropic/")

    original_eval = inspect_ai.eval

    def patched_eval(*args: Any, **kwargs: Any) -> Any:
        model = kwargs.get("model", args[1] if len(args) > 1 else None)
        if _is_agent_api_model(model) or (
            isinstance(model, list) and any(_is_agent_api_model(m) for m in model)
        ):
            model_args = dict(kwargs.get("model_args") or {})
            model_args.setdefault("responses_api", True)
            model_args.setdefault("client_timeout", 120.0)
            kwargs["model_args"] = model_args
            kwargs.setdefault("max_tokens", max_output_tokens)
        return original_eval(*args, **kwargs)

    inspect_ai.eval = patched_eval

    original_get_model = _model_mod.get_model

    def patched_get_model(
        model: Any = None,
        *,
        role: str | None = None,
        default: Any = None,
        config: Any = GenerateConfig(),
        base_url: str | None = None,
        api_key: str | None = None,
        memoize: bool = True,
        **model_args: Any,
    ) -> Any:
        if _is_agent_api_model(model):
            model_args.setdefault("responses_api", True)
            model_args.setdefault("client_timeout", 120.0)
            if config.max_tokens is None:
                config = config.model_copy(update={"max_tokens": max_output_tokens})
        return original_get_model(
            model,
            role=role,
            default=default,
            config=config,
            base_url=base_url,
            api_key=api_key,
            memoize=memoize,
            **model_args,
        )

    _model_mod.get_model = patched_get_model
    _task_mod.get_model = patched_get_model
    _react_mod.get_model = patched_get_model


# -----------------------------------------------------------------------------


def main() -> int:
    p = build_arg_parser(__doc__)
    args = p.parse_args()
    resolve_model_defaults(args)

    _validate_mcp_url(args.mcp_url)

    if args.provider == "perplexity":
        # Perplexity's Agent API is not the judge-message-patch target (that
        # patch talks to Anthropic messages directly), so only the two
        # transport-shape patches apply here -- not apply_common_patches().
        _patch_inspect_mcp_schema_compat()
        _patch_transcript_compat()
        _setup_perplexity_via_openai()
        _patch_for_agent_api()
        agent_model = _agent_api_model(args.agent_model)
        grader_model = _agent_api_model(args.grader_model)
    else:
        apply_common_patches()
        agent_model = args.agent_model
        grader_model = args.grader_model

    # CRITICAL: apply the isolation patch (if enabled) before importing
    # run_suite, else the patch won't affect the imported function.
    maybe_apply_session_isolation(args.no_session_isolation)

    from nxd_eval import run_suite

    # run_suite() has no case filter and the task layer builds its dataset from
    # suite.cases wholesale, so subsetting means a filtered copy of the suite.
    suite = _with_glossary_instruction(SUITE)
    suite = filter_suite_to_only(suite, args.only, SUITE)

    token = os.environ.get(args.mcp_token_env)
    server_factory = build_server_factory(args, token)
    print_server_config(args, token)
    print(f"Provider: {args.provider} (agent={args.agent_model}, grader={args.grader_model})")

    from nxd_eval.solver import AGENT_PROMPT

    log_path = run_suite(
        suite,
        mcp_url=None,
        server_factory=server_factory,
        agent_prompt=AGENT_PROMPT + MESH_SCOPE_GUARD + DIMENSION_METADATA_GUARD,
        agent_model=agent_model,
        grader_model=grader_model,
        epochs=args.epochs,
        log_dir=args.log_dir,
    )
    print(log_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
