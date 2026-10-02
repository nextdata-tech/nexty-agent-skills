"""Local-mesh filter-coverage scenario — arm A (bare tools) vs arm B (skill prompt).

Four analyst questions against the operator-deployed ``eval-provider-enrollment``
data product on the local dev mesh (OrbStack). Gold rows come from
``evals/public/semantic-filter-coverage/checks.json`` (PR #445): distinct
enrolled patients over ``DAILY`` rows.

Cases are phrased as the analyst's question only — no skill cue — so the bare-tools
arm (A: default ``AGENT_PROMPT``) and the skill arm (B: ``skill_prompt()``) see the
identical user turn and differ only in the system prompt.

Transport: the DP's own MCP endpoint through the ingress,
``<base>/rpcs/mcp-api/mcp``. Unlike the gateway (``/dp/mcp``) it exposes exactly the
four semantic tools (unsuffixed ``list_models`` / ``describe_model`` /
``semantic_model`` / ``run_semantic_query``) — the gateway also lists ``proxy__*``,
``glossary__*`` and other data products' ``query-system-dp-production__*`` tools,
which would contaminate a tool-use eval. Auth is the ``X-Nextdata-Token`` header
carrying a personal access token (read from ``EVAL_MESH_TOKEN``, never written
anywhere). TLS: the mesh uses a self-signed CA; point ``SSL_CERT_FILE`` at the
local cluster's CA certificate instead of disabling verification.

The gold authoring API pins measures and group-by but does not support filters;
the expected filters are therefore carried in each case's ``gold_selection``
metadata. q4 pins an ungrouped grand-total query returning zero. A grouped query
with no rows scores FAIL because this scorer has no alternative acceptable row
sets.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from inspect_ai.tool import mcp_server_http

_PKG_ROOT = Path(__file__).resolve().parent.parent  # evals/nxd_eval
sys.path.insert(0, str(_PKG_ROOT / "src"))

from nxd_eval import Case, Suite, gold, run_suite, skill_prompt  # noqa: E402

_GOLD = gold(
    {
        "q1": gold.query(
            "q1",
            measures=["enrolled_patients"],
            group_by=["product_name"],
            rows=[
                {"product_name": "ALL", "enrolled_patients": 3},
                {"product_name": "ALPHAVIR", "enrolled_patients": 2},
                {"product_name": "ALPHAVIR SC", "enrolled_patients": 1},
                {"product_name": "BETAMAB", "enrolled_patients": 1},
            ],
        ),
        "q2": gold.query(
            "q2",
            measures=["enrolled_patients"],
            group_by=["specialty_group"],
            rows=[
                {"specialty_group": "Neurology", "enrolled_patients": 8},
                {"specialty_group": "Psychiatry & Neurology", "enrolled_patients": 9},
            ],
        ),
        "q3": gold.query(
            "q3",
            measures=["enrolled_patients"],
            group_by=["region_name"],
            rows=[
                {"region_name": "NE Gulf Coast", "enrolled_patients": 7},
                {"region_name": "NE Great Lakes", "enrolled_patients": 10},
                {"region_name": "SW Desert", "enrolled_patients": 4},
            ],
        ),
        "q4": gold.query(
            "q4", measures=["enrolled_patients"], rows=[{"enrolled_patients": 0}]
        ),
    }
)

_QUESTIONS = [
    (
        "q1",
        "How many enrolled patients do we have in the Gulf Coast region for "
        "Psychiatry & Neurology providers, by product?",
        "two scope filters incl. cross-model; full stored value 'NE Gulf Coast'",
    ),
    (
        "q2",
        "Compare enrolled patients for Neurology vs Psychiatry & Neurology providers.",
        "IN comparison grouped by specialty_group",
    ),
    (
        "q3",
        "Enrolled patients by region.",
        "breakdown: region is a group, not a filter",
    ),
    (
        "q4",
        "How many enrolled patients are on BETAMAB in the SW Desert?",
        "genuine zero (both values exist, never together)",
    ),
]


def server_factory():
    """Fresh HTTP MCP server per run/epoch; mesh URL and token from environment."""
    return mcp_server_http(
        name="semantic",
        url=os.environ["NXD_EVAL_DP_URL"],
        headers={"X-Nextdata-Token": os.environ["EVAL_MESH_TOKEN"]},
        timeout=120,
        sse_read_timeout=300,
    )


def filter_coverage_suite() -> Suite:
    return Suite(
        name="local-mesh-filter-coverage",
        cases=[
            Case(
                id=cid,
                question=q,
                expect="answer",
                gold_id=cid,
                metadata={
                    "why": why,
                    "gold_selection": {
                        "measures": ["enrolled_patients"],
                        "group_by": {
                            "q1": ["product_name"],
                            "q2": ["specialty_group"],
                            "q3": ["region_name"],
                            "q4": [],
                        }[cid],
                        "filters": {
                            "q1": [
                                {
                                    "field": "region_name",
                                    "op": "=",
                                    "value": "NE Gulf Coast",
                                },
                                {
                                    "field": "specialty_group",
                                    "op": "=",
                                    "value": "Psychiatry & Neurology",
                                },
                            ],
                            "q2": [
                                {
                                    "field": "specialty_group",
                                    "op": "IN",
                                    "value": ["Neurology", "Psychiatry & Neurology"],
                                }
                            ],
                            "q3": [],
                            "q4": [
                                {
                                    "field": "product_name",
                                    "op": "=",
                                    "value": "BETAMAB",
                                },
                                {
                                    "field": "region_name",
                                    "op": "=",
                                    "value": "SW Desert",
                                },
                            ],
                        }[cid],
                    },
                },
            )
            for cid, q, why in _QUESTIONS
        ],
        gold=_GOLD,
        server_factory=server_factory,
    )


ARMS = {"A": None, "B": "skill"}  # None -> default AGENT_PROMPT


def run_arm(
    arm: str,
    *,
    agent_model: str,
    agent_model_args: dict[str, Any] | None = None,
    epochs: int = 5,
    log_dir: str = "logs/filter_coverage",
    isolate_sessions: bool = False,
) -> Path:
    """Run one arm; B's ``current_pack`` label means ``skill_prompt()`` only.

    No skill pack is installed in the agent runtime; the label records the
    skill-derived system prompt variant. ``agent_model_args`` configure the
    agent model only, not the grader, and are recorded in the eval log; never
    pass API keys through this argument.
    """
    prompt = skill_prompt() if ARMS[arm] == "skill" else None
    return run_suite(
        filter_coverage_suite(),
        variant="no_skills" if arm == "A" else "current_pack",
        agent_prompt=prompt,
        agent_model=agent_model,
        agent_model_args=agent_model_args,
        epochs=epochs,
        epochs_reducer="pass_at",
        log_dir=log_dir,
        isolate_sessions=isolate_sessions,
    )
