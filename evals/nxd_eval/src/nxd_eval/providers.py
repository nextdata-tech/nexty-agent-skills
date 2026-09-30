"""Provider-specific Inspect model factories.

The factories in this module return configured Inspect ``Model`` objects. They
are deliberately small adapters: callers still pass the returned model to
``run_suite`` just as they would any other Inspect model.
"""

from __future__ import annotations

import os

from inspect_ai.model import GenerateConfig, Model, get_model

from .dependencies import require_python_module

PERPLEXITY_API_KEY_ENV = "PERPLEXITY_API_KEY"
PERPLEXITY_BASE_URL = "https://api.perplexity.ai/v1"


class PerplexityConfigurationError(RuntimeError):
    """Raised when the Perplexity Agent API model cannot be configured."""


def perplexity_model(
    model: str,
    *,
    api_key: str | None = None,
    max_output_tokens: int = 4096,
    client_timeout: float = 120.0,
) -> Model:
    """Create an Inspect model for Perplexity's OpenAI-compatible Agent API.

    ``model`` is a Perplexity Agent API model ID, for example
    ``"anthropic/claude-sonnet-4-5"`` or ``"openai/gpt-5.1"``. The adapter
    uses Inspect's OpenAI provider, but configures its Responses API transport
    directly on the returned model. This lets the agent and optional grader
    each retain their own configuration without mutating ``OPENAI_API_KEY`` /
    ``OPENAI_BASE_URL`` or patching Inspect internals. A bare Claude slug such
    as ``"claude-sonnet-4-5"`` remains a shorthand for
    ``"anthropic/claude-sonnet-4-5"``.

    The OpenAI SDK is supplied by nxd_eval's existing ``openai`` extra. The
    API key defaults to :envvar:`PERPLEXITY_API_KEY`; pass ``api_key`` to avoid
    reading the environment (for example, when a caller owns secret loading).
    """
    if not isinstance(model, str) or not model.strip():
        raise PerplexityConfigurationError("model must be a non-empty Perplexity model ID")
    if max_output_tokens < 1:
        raise PerplexityConfigurationError("max_output_tokens must be positive")
    if client_timeout <= 0:
        raise PerplexityConfigurationError("client_timeout must be positive")

    resolved_key = api_key if api_key is not None else os.environ.get(PERPLEXITY_API_KEY_ENV)
    if not resolved_key or not resolved_key.strip():
        raise PerplexityConfigurationError(
            f"{PERPLEXITY_API_KEY_ENV} is not set. Set it or pass api_key= to perplexity_model()."
        )

    require_python_module(
        "Perplexity Agent API support",
        "openai",
        "Install it with `uv sync --project evals/nxd_eval --extra openai`.",
    )
    model_id = model.strip()
    if "/" not in model_id:
        model_id = f"anthropic/{model_id}"

    return get_model(
        f"openai/{model_id}",
        base_url=PERPLEXITY_BASE_URL,
        api_key=resolved_key,
        config=GenerateConfig(max_tokens=max_output_tokens),
        responses_api=True,
        client_timeout=client_timeout,
    )
