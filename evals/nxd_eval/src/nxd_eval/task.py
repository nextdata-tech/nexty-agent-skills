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
from pathlib import Path
from typing import TYPE_CHECKING

from inspect_ai import Epochs, Task
from inspect_ai.dataset import Sample

from .case import ABSTAIN
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


def _resolve_reducer(reducer: str, k: int) -> str:
    """Compose a concrete reducer name from a family + k (``pass_at`` -> ``pass_at_3``).

    A bare k-parameterized family gets ``_{k}`` appended; an already-concrete
    name (``pass_at_2``, ``mean``, ...) is passed through unchanged.
    """
    if reducer in _K_PARAM_REDUCERS:
        return f"{reducer}_{k}"
    return reducer

if TYPE_CHECKING:  # pragma: no cover
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
    # Judge-only context (why / gold_note / raw check text) rides along for the
    # scorer; it is NOT part of the Sample input, so the agent never sees it.
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
    agent_model: str | None = None,
    grader_model: str | None = None,
    epochs: int = 1,
    epochs_reducer: str = "pass_at",
) -> Task:
    """Assemble the Inspect ``Task`` for a suite (dataset + solver + scorers).

    ``target`` (MCP URL) resolves from the argument then ``suite.target``; a
    suite with neither is a build error — the agent has nothing to drive.
    ``grader_model``, when given, wires a ``grader`` model role for the judge
    scorer. Epochs > 1 attaches an ``Epochs(k, reducer)`` policy.
    """
    mcp_url = target or suite.target
    if not mcp_url:
        raise ValueError(
            f"suite {suite.name!r}: no MCP target URL (pass target= or set "
            f"Suite.target) — the react agent has no server to drive"
        )

    dataset = [case_to_sample(c, suite) for c in suite.cases]
    solver = mcp_solver(mcp_url, model=agent_model)
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


def run_suite(
    suite: "Suite",
    *,
    variant: str = "current_pack",
    mcp_url: str | None = None,
    agent_model: str | None = None,
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

    ``variant`` (``no_skills`` / ``current_pack`` / ``candidate_pack``) selects
    the agent's skill context and is recorded on the run metadata so the report
    can pair variants on the same cases. It is validated here so a typo fails
    loudly instead of silently mislabelling a run.
    """
    if variant not in VARIANTS:
        raise ValueError(f"variant must be one of {VARIANTS}; got {variant!r}")

    # Imported here to keep the authoring/import path free of the eval runtime.
    from inspect_ai import eval as inspect_eval

    task = build_task(
        suite,
        target=mcp_url,
        agent_model=agent_model,
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
