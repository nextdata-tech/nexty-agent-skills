"""nxd_eval — Inspect-based evaluation framework for the Nexty skill pack.

Public authoring API (this layer):

    Case, Suite, load_suite   — the case/suite model + a test_suite.json loader
    checks                    — judge-only check sets (flat + dotted constructors)
    gold                      — frozen-oracle gold records (rows / query forms)

``Suite.to_inspect_task()`` lowers a suite into a runnable Inspect ``Task``. The
scorer *bodies* (deterministic-EX via the ``_ex_core.score`` module this package
owns, the model judge) and the run/certify entry points attach in later layers
on top of this stable shape.
"""

from __future__ import annotations

from .case import Case, Suite, load_suite
from .certify import CertifyResult, certify
from .checks import checks, load_checks_json
from .gold import gold
from .metrics import reliability_score, wilson_accuracy
from .report import BucketCard, BucketDelta, Report
from .task import run_suite
from .stats import (
    ConfidenceInterval,
    McNemarResult,
    aurc,
    bh_fdr,
    brier,
    design_effect,
    ece,
    mcnemar_paired,
    n_eff,
    sample_size_for,
    wilson_ci,
)

__all__ = [
    "Case",
    "Suite",
    "load_suite",
    "checks",
    "load_checks_json",
    "gold",
    # statistics contract
    "ConfidenceInterval",
    "McNemarResult",
    "wilson_ci",
    "sample_size_for",
    "design_effect",
    "n_eff",
    "mcnemar_paired",
    "bh_fdr",
    "brier",
    "ece",
    "aurc",
    # inspect metric wrappers
    "wilson_accuracy",
    "reliability_score",
    # run + report + certify (the read side)
    "run_suite",
    "Report",
    "BucketCard",
    "BucketDelta",
    "certify",
    "CertifyResult",
]
