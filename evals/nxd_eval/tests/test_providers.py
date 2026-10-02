"""Offline tests for provider-specific model factories."""

from __future__ import annotations

import os

import pytest
from inspect_ai.model import get_model

from nxd_eval import Case, PerplexityConfigurationError, Suite, perplexity_model
from nxd_eval import providers
from nxd_eval.dependencies import check_inspect_model_dependency
from nxd_eval.task import build_task

MCP_URL = "http://127.0.0.1:8765/pharma-mesh/rpcs/mcp-api/mcp"


@pytest.mark.parametrize(
    ("model_id", "inspect_model"),
    [
        ("claude-sonnet-4-5", "openai-api/perplexity/anthropic/claude-sonnet-4-5"),
        ("anthropic/claude-sonnet-4-5", "openai-api/perplexity/anthropic/claude-sonnet-4-5"),
        ("openai/gpt-5.1", "openai-api/perplexity/openai/gpt-5.1"),
        ("google/gemini-3.1-pro", "openai-api/perplexity/google/gemini-3.1-pro"),
        ("perplexity/sonar", "openai-api/perplexity/perplexity/sonar"),
    ],
)
def test_perplexity_model_configures_responses_api_without_global_openai_env(
    monkeypatch, model_id, inspect_model
):
    captured: dict[str, object] = {}
    expected = object()

    def fake_get_model(name, **kwargs):
        captured["name"] = name
        captured.update(kwargs)
        return expected

    monkeypatch.setenv("PERPLEXITY_API_KEY", "pplx-test-key")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.setattr(providers, "require_python_module", lambda *_args: None)
    monkeypatch.setattr(providers, "get_model", fake_get_model)

    model = perplexity_model(
        model_id,
        max_output_tokens=2048,
        client_timeout=42.0,
    )

    assert model is expected
    assert captured["name"] == inspect_model
    assert captured["base_url"] == "https://api.perplexity.ai/v1"
    assert "api_key" not in captured
    assert captured["responses_api"] is True
    assert captured["timeout"] == 42.0
    assert captured["config"].max_tokens == 2048
    assert "OPENAI_API_KEY" not in os.environ
    assert "OPENAI_BASE_URL" not in os.environ


def test_perplexity_model_requires_key(monkeypatch):
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)

    with pytest.raises(PerplexityConfigurationError, match="PERPLEXITY_API_KEY"):
        perplexity_model("claude-sonnet-4-5")


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"model": ""}, "non-empty"),
        ({"model": "claude-sonnet-4-5", "max_output_tokens": 0}, "positive"),
        ({"model": "claude-sonnet-4-5", "client_timeout": 0}, "positive"),
    ],
)
def test_perplexity_model_rejects_invalid_configuration(monkeypatch, kwargs, message):
    monkeypatch.setenv("PERPLEXITY_API_KEY", "pplx-test-key")

    with pytest.raises(PerplexityConfigurationError, match=message):
        perplexity_model(**kwargs)


def test_configured_inspect_models_are_accepted_for_agent_and_grader():
    model = get_model("mockllm/model")
    suite = Suite(
        name="provider-wiring",
        cases=[Case(id="case", question="question", expect="clarify")],
        target=MCP_URL,
    )

    task = build_task(suite, agent_model=model, grader_model=model)

    assert task.model_roles == {"grader": model}


def test_dependency_preflight_skips_configured_model_objects(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(
        "nxd_eval.dependencies._find_spec",
        lambda module: calls.append(module),
    )

    check_inspect_model_dependency(object(), role="agent_model")

    assert calls == []
