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
from collections.abc import Callable
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

    The agent reaches the semantic server one of two ways, resolved in order:

    - ``target`` — a Streamable-HTTP MCP URL (the ``/<dp>/rpcs/<port>/mcp`` shape
      the semantic server serves). Convenient, but the HTTP transport currently
      crashes on teardown (see the README "Transport" note); prefer stdio.
    - ``server_factory`` — a zero-arg callable returning a pre-built Inspect MCP
      server (e.g. ``lambda: mcp_server_stdio(command=..., args=..., env=...)``).
      This is the documented default for live runs: it drives the real server as
      a subprocess over stdio, sidestepping the HTTP teardown bug, and lets the
      caller forward credentials into the subprocess ``env``. It is a *factory*,
      not a live server, so each run (and each epoch) gets a fresh connection.

    A suite must carry exactly one of the two — a build error is raised if it has
    neither. ``gold`` is an optional ``{gold_id: record}`` map (from ``gold()``)
    used to fill Sample targets for ``answer`` cases. ``checks`` is the judge-only
    check set (from ``checks()``), keyed by discriminator.
    """

    name: str
    cases: list[Case]
    target: str | None = None
    gold: dict[str, dict] = field(default_factory=dict)
    checks: dict[str, list[str]] = field(default_factory=dict)
    # Zero-arg thunk returning an Inspect MCP server (stdio transport). Kept out
    # of equality/repr: it's runtime wiring, not part of the suite's identity, and
    # a closure is not meaningfully comparable.
    server_factory: "Callable[[], Any] | None" = field(
        default=None, compare=False, repr=False
    )

    def to_inspect_task(
        self,
        *,
        target: str | None = None,
        server_factory: "Callable[[], Any] | None" = None,
        agent_prompt: str | None = None,
        agent_model: str | None = None,
        grader_model: str | None = None,
        epochs: int = 1,
        epochs_reducer: str = "pass_at",
    ) -> "Task":
        """Lower this suite into a runnable Inspect ``Task``.

        Wiring only — the scorer bodies are placeholder slots at this layer. The
        server resolves from ``target``/``server_factory`` arguments, then the
        suite's own ``target``/``server_factory`` (see the class docstring).
        """
        # Imported lazily so ``load_suite`` / authoring works without pulling in
        # the whole Inspect solver stack.
        from .task import build_task

        return build_task(
            self,
            target=target,
            server_factory=server_factory,
            agent_prompt=agent_prompt,
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


def load_suite(
    path: str | Path,
    *,
    target: str | None = None,
    server_factory: "Callable[[], Any] | None" = None,
    gold: dict[str, dict] | None = None,
    checks: dict[str, list[str]] | None = None,
) -> Suite:
    """Load a ``test_suite.json``-shaped file into a ``Suite``.

    The file shape is ``{comment?, name?, cases: [{id, question, expect, ...}]}``
    (as in ``evals/query-loop/test_suite.json``). The suite name defaults to the
    file's ``name`` key, then the file stem. Judge-only fields on each case are
    preserved in ``Case.metadata``.

    The file carries only the *cases*. The runtime wiring — how the agent reaches
    the server (``target`` URL or ``server_factory`` stdio thunk), the gold-row
    map for ``answer`` cases, and the judge ``checks`` — is attached here by the
    caller, since it is environment-specific (a live cluster URL, a credentialed
    stdio subprocess, a frozen gold set) and does not belong in a checked-in
    suite file.
    """
    p = Path(path)
    doc = json.loads(p.read_text())
    cases = [_case_from_raw(c) for c in doc.get("cases", [])]
    name = doc.get("name") or p.stem
    return Suite(
        name=name,
        cases=cases,
        target=target,
        server_factory=server_factory,
        gold=gold or {},
        checks=checks or {},
    )
