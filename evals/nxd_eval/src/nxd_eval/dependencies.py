"""Dependency preflight helpers for nxd_eval runtimes."""

from __future__ import annotations

import importlib.util


class DependencyCheckError(RuntimeError):
    """Raised when a selected eval backend cannot run in this environment."""


_find_spec = importlib.util.find_spec


def require_python_module(name: str, module: str, install_hint: str) -> None:
    """Fail clearly when a required Python module is unavailable."""
    try:
        found = _find_spec(module)
    except ModuleNotFoundError:
        found = None
    if found is not None:
        return
    raise DependencyCheckError(
        f"{name} requires the Python module {module!r}, but it is not installed. "
        f"{install_hint}"
    )


_INSPECT_PROVIDER_MODULES = {
    "anthropic": (
        "anthropic",
        "Install it with `uv sync --project evals/nxd_eval --extra anthropic`.",
    ),
    "openai": (
        "openai",
        "Install it with `uv sync --project evals/nxd_eval --extra openai`.",
    ),
    "google": (
        "google.genai",
        "Install it with `uv sync --project evals/nxd_eval --extra google`.",
    ),
}


def check_inspect_model_dependency(model: str | None, *, role: str = "model") -> None:
    """Check provider SDK extras for an Inspect ``provider/model`` string.

    Unknown providers are left to Inspect, because they may be built in,
    configured through plugins, or provided by a newer Inspect release.
    """
    if not model or "/" not in model:
        return
    provider = model.split("/", 1)[0]
    requirement = _INSPECT_PROVIDER_MODULES.get(provider)
    if requirement is None:
        return
    module, hint = requirement
    require_python_module(f"{role} {model!r}", module, hint)
