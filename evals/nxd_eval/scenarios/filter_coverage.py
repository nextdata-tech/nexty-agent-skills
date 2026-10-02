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
carrying a personal access token (read from ``NXD_PAT``, never written anywhere).
TLS: the mesh uses a self-signed CA; point ``SSL_CERT_FILE`` at ``nxdCA.crt``
(``shared/charts/nxd/localCerts/`` in the nxd repo) instead of disabling verification.
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

DP_URL = os.environ["NXD_EVAL_DP_URL"]

_GOLD = gold(
    {
        "q1": gold.rows(
            "q1",
            [
                {"product_name": "ALL", "enrolled_patients": 3},
                {"product_name": "ALPHAVIR", "enrolled_patients": 2},
                {"product_name": "ALPHAVIR SC", "enrolled_patients": 1},
                {"product_name": "BETAMAB", "enrolled_patients": 1},
            ],
        ),
        "q2": gold.rows(
            "q2",
            [
                {"specialty_group": "Neurology", "enrolled_patients": 8},
                {"specialty_group": "Psychiatry & Neurology", "enrolled_patients": 9},
            ],
        ),
        "q3": gold.rows(
            "q3",
            [
                {"region_name": "NE Gulf Coast", "enrolled_patients": 7},
                {"region_name": "NE Great Lakes", "enrolled_patients": 10},
                {"region_name": "SW Desert", "enrolled_patients": 4},
            ],
        ),
        "q4": gold.rows("q4", [{"enrolled_patients": 0}]),
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
    ("q3", "Enrolled patients by region.", "breakdown: region is a group, not a filter"),
    (
        "q4",
        "How many enrolled patients are on BETAMAB in the SW Desert?",
        "genuine zero (both values exist, never together)",
    ),
]


def server_factory():
    """Fresh HTTP MCP server per run/epoch; PAT from the environment only."""
    return mcp_server_http(
        name="semantic",
        url=DP_URL,
        headers={"X-Nextdata-Token": os.environ["NXD_PAT"]},
        timeout=120,
        sse_read_timeout=300,
    )


def filter_coverage_suite() -> Suite:
    return Suite(
        name="local-mesh-filter-coverage",
        cases=[
            Case(id=cid, question=q, expect="answer", gold_id=cid, metadata={"why": why})
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
    """Run one arm; ``A`` = bare tools (default prompt), ``B`` = ``skill_prompt()``."""
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
