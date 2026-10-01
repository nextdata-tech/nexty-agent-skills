"""Agent system prompts rendered from the shipped skill pack at call time.

The Inspect agent under test is a bare ``react()`` loop with the semantic MCP
tools and a system prompt. It has no Skill tool, so a client that cannot load
Agent Skills (Perplexity, a raw OpenAI-compatible endpoint, any non-Claude
runtime) only ever sees what the system prompt and the MCP surface tell it.
:func:`skill_prompt` gives that agent the querying procedure the
``nexty-datamesh`` plugin ships, so a run measures "this model, with our
instructions" rather than "this model, unaided".

The text is not written here. :func:`render_from_skills` slices it out of the
skill files under the repository's ``src/`` tree, or the embedded ``_skills``
tree in an installed wheel.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..solver import CONFIDENCE_INSTRUCTION

# Pack name -> complete skill directories embedded in the wheel.
PACKS = {
    "nexty-datamesh": (
        "nxd-query-data-product",
        "nxd-semantic-query-intent",
    ),
}

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


def _contains_pack_skills(root: Path) -> bool:
    return all((root / skill_dir).is_dir() for dirs in PACKS.values() for skill_dir in dirs)


def skills_root() -> Path:
    """Return embedded skill files, falling back to this checkout's ``src/``."""
    package_root = Path(__file__).resolve().parents[1]
    embedded = package_root / "_skills"
    if _contains_pack_skills(embedded):
        return embedded

    parents = Path(__file__).resolve().parents
    repository_src = parents[5] / "src" if len(parents) > 5 else embedded
    if _contains_pack_skills(repository_src):
        return repository_src

    expected = ", ".join(sorted({skill for dirs in PACKS.values() for skill in dirs}))
    raise FileNotFoundError(
        f"skill sources not found in {embedded} or {repository_src}; expected: {expected}"
    )


def render_from_skills(src_root: Path, pack: str = "nexty-datamesh") -> str:
    """Build ``pack``'s query prompt from its skill files in ``src_root``."""
    if pack not in PACKS:
        raise ValueError(f"unknown pack {pack!r}; expected one of {sorted(PACKS)}")
    parts = [_PREAMBLE.strip()]
    for rel, start, end in _SLICES:
        parts.append(_slice((src_root / rel).read_text(), start, end, rel))
    parts.append(CONFIDENCE_INSTRUCTION)
    return "\n\n".join(parts) + "\n"


def skill_prompt(pack: str = "nexty-datamesh") -> str:
    """Render the agent system prompt for ``pack`` from its skill files.

    Pass it as ``run_suite(..., agent_prompt=skill_prompt())``.
    """
    if pack not in PACKS:
        raise ValueError(f"unknown pack {pack!r}; expected one of {sorted(PACKS)}")
    return render_from_skills(skills_root(), pack)
