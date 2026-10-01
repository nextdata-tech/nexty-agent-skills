"""Agent system prompts derived from the shipped skill pack.

The Inspect agent under test is a bare ``react()`` loop with the semantic MCP
tools and a system prompt. It has no Skill tool, so a client that cannot load
Agent Skills (Perplexity, a raw OpenAI-compatible endpoint, any non-Claude
runtime) only ever sees what the system prompt and the MCP surface tell it.
:func:`skill_prompt` gives that agent the querying procedure the
``nexty-datamesh`` plugin ships, so a run measures "this model, with our
instructions" rather than "this model, unaided".

The text is not written here. :func:`render_from_skills` slices it out of the
skill files under ``src/`` and the result is vendored next to this module,
because the wheel is installed without the repository. A test regenerates it
from ``src/`` and fails when the vendored copy is stale; rerun
``python -m nxd_eval.skill_prompts`` from the repository root to refresh it.
"""

from __future__ import annotations

import re
from importlib import resources
from pathlib import Path

from ..solver import CONFIDENCE_INSTRUCTION

#: Pack name -> vendored prompt file in this package.
PACKS = {"nexty-datamesh": "nexty_datamesh_query.md"}

# Where each slice lives in the skill pack, relative to ``src/``. A slice runs
# from its start heading up to (not including) its end marker, so a renamed or
# moved heading fails the regeneration loudly instead of silently shrinking the
# prompt.
_SLICES = (
    (
        "nxd-query-data-product/SKILL.md",
        "#### Semantic-layer MCP ports",
        "**Cross-DP questions",
    ),
    (
        "nxd-query-data-product/SKILL.md",
        "**Intent gate (REQUIRED before `run_semantic_query`).**",
        "This adapter supplies",
    ),
    (
        "nxd-semantic-query-intent/SKILL.md",
        "# Semantic query intent validation",
        "## Additional resources",
    ),
    (
        "nxd-semantic-query-intent/reference/semantic-intent-validation.md",
        "## Purpose and boundary",
        None,
    ),
)

# The intent skill is written for an adapter that owns the conversation. In the
# harness the agent IS the adapter and no user is reachable, so these lines
# bind the skill's abstract inputs ("the verbatim question", "ask the user") to
# what the agent actually has.
_PREAMBLE = """\
You are a data analyst answering questions about a governed data product
through its semantic MCP tools: list_models, describe_model and
run_semantic_query. Answer only from rows returned by run_semantic_query, using
concept names, never raw SQL. Follow the procedure below exactly.

You are running non-interactively: no user can answer a follow-up question.
The verbatim question is the user message. Where the procedure says to ask the
user or clarify, do not execute; instead finish with the ambiguity, the real
candidate concepts, and the clarification you would need. Write the
round-trip echo in your reply before you call run_semantic_query, and check it
against the question: every constraint the question names (a region, a
specialty, a product, a time window) must appear as a filter in the selection.
After the call, confirm the returned compiled_sql applies each of those
filters. The server does not check filter values against the data, so a
filter that returns no rows may be a misspelled value rather than a true zero:
say so instead of reporting zero.
"""

_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")


def _slice(text: str, start: str, end: str | None, where: str) -> str:
    i = text.find(start)
    if i < 0:
        raise ValueError(f"{where}: start marker not found: {start!r}")
    j = len(text) if end is None else text.find(end, i)
    if j < 0:
        raise ValueError(f"{where}: end marker not found after start: {end!r}")
    # Relative links point into the skill tree, which the agent cannot read.
    return _LINK.sub(r"\1", text[i:j]).strip()


def render_from_skills(src_root: Path) -> str:
    """Build the ``nexty-datamesh`` query prompt from the skill files in ``src_root``."""
    parts = [_PREAMBLE.strip()]
    for rel, start, end in _SLICES:
        parts.append(_slice((src_root / rel).read_text(), start, end, rel))
    parts.append(CONFIDENCE_INSTRUCTION)
    return "\n\n".join(parts) + "\n"


def skill_prompt(pack: str = "nexty-datamesh") -> str:
    """Return the vendored agent system prompt for ``pack``.

    Pass it as ``run_suite(..., agent_prompt=skill_prompt())``.
    """
    if pack not in PACKS:
        raise ValueError(f"unknown pack {pack!r}; expected one of {sorted(PACKS)}")
    return resources.files(__package__).joinpath(PACKS[pack]).read_text()

