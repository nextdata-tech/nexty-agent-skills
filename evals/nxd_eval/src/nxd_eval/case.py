"""Authoring model: a ``Case`` is one question, a ``Suite`` a named list of them.

A suite is what an author writes; ``Suite.to_inspect_task()`` lowers it into a
runnable Inspect ``Task`` (dataset + react solver over the MCP tools + a scorer
slot per check). The scorer *bodies* are deliberately not here — this layer
fixes the shape and the wiring; the real deterministic-EX / abstain / judge
scorers attach at the next layer.

The discriminator vocabulary (``answer`` / ``clarify`` / ``abstain``) and the
"judge-only, never shown to the agent" contract come straight from the two
canonical suites in the repo (``evals/query-loop/test_suite.json`` and a public
scenario's ``checks.json``): a case's ``why`` / ``gold_note`` are issue-miner
context and MUST stay out of the agent's view. We honor that by carrying them in
``Case.metadata`` and NEVER folding them into the Sample ``input``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    from inspect_ai import Task

# The three verdict discriminators the scorer routes on. Kept as a module
# constant so the loader, the task builder, and the (future) scorer layer all
# agree on the spelling.
ANSWER = "answer"
CLARIFY = "clarify"
ABSTAIN = "abstain"
EXPECT_VALUES = frozenset({ANSWER, CLARIFY, ABSTAIN})


@dataclass(frozen=True)
class Case:
    """One NL question plus what the agent is expected to do with it.

    ``expect`` picks the discriminator: ``answer`` cases score by
    deterministic execution-accuracy against gold rows; ``clarify`` and
    ``abstain`` cases score on the agent's *behaviour* (ask vs. silently pick;
    refuse vs. fabricate).

    ``gold_id`` links an ``answer`` case to a ``gold()`` record. ``metadata``
    holds judge-only context (``why`` / ``gold_note`` / raw check text); it is
    threaded into the Sample metadata for the scorer, never into the agent
    input.
    """

    id: str
    question: str
    expect: str  # one of EXPECT_VALUES
    gold_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.expect not in EXPECT_VALUES:
            raise ValueError(
                f"Case {self.id!r}: expect={self.expect!r} must be one of "
                f"{sorted(EXPECT_VALUES)}"
            )


@dataclass(frozen=True)
class Suite:
    """A named list of cases, plus the MCP endpoint the agent drives.

    ``target`` is the Streamable-HTTP MCP URL (the ``/<dp>/rpcs/<port>/mcp``
    shape the semantic server serves). ``gold`` is an optional
    ``{gold_id: record}`` map (from ``gold()``) used to fill Sample targets for
    ``answer`` cases. ``checks`` is the judge-only check set (from ``checks()``),
    keyed by discriminator.
    """

    name: str
    cases: list[Case]
    target: str | None = None
    gold: dict[str, dict] = field(default_factory=dict)
    checks: dict[str, list[str]] = field(default_factory=dict)

    def to_inspect_task(
        self,
        *,
        target: str | None = None,
        agent_model: str | None = None,
        grader_model: str | None = None,
        epochs: int = 1,
        epochs_reducer: str = "pass_at",
    ) -> "Task":
        """Lower this suite into a runnable Inspect ``Task``.

        Wiring only — the scorer bodies are placeholder slots at this layer.
        The MCP URL resolves from the ``target`` argument, then ``self.target``.
        """
        # Imported lazily so ``load_suite`` / authoring works without pulling in
        # the whole Inspect solver stack.
        from .task import build_task

        return build_task(
            self,
            target=target,
            agent_model=agent_model,
            grader_model=grader_model,
            epochs=epochs,
            epochs_reducer=epochs_reducer,
        )


def _case_from_raw(raw: dict[str, Any]) -> Case:
    """Parse one ``cases[]`` entry from a test_suite.json-shaped file.

    Recognizes the canonical suite shape ``{id, question, expect, why,
    gold_note}``. ``why`` / ``gold_note`` (and any extra keys) land in
    ``metadata`` as judge-only context. ``expect`` defaults to ``answer`` when
    absent (the happy-path reading).
    """
    known = {"id", "question", "expect", "gold_id"}
    metadata = {k: v for k, v in raw.items() if k not in known}
    return Case(
        id=raw["id"],
        question=raw["question"],
        expect=raw.get("expect", ANSWER),
        gold_id=raw.get("gold_id"),
        metadata=metadata,
    )


def load_suite(path: str | Path, *, target: str | None = None) -> Suite:
    """Load a ``test_suite.json``-shaped file into a ``Suite``.

    The file shape is ``{comment?, name?, cases: [{id, question, expect, ...}]}``
    (as in ``evals/query-loop/test_suite.json``). The suite name defaults to the
    file's ``name`` key, then the file stem. Judge-only fields on each case are
    preserved in ``Case.metadata``.
    """
    p = Path(path)
    doc = json.loads(p.read_text())
    cases = [_case_from_raw(c) for c in doc.get("cases", [])]
    name = doc.get("name") or p.stem
    return Suite(name=name, cases=cases, target=target)
