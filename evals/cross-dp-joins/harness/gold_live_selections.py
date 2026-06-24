"""Live-matrix wiring: per-question compiler_selection + strategy-id abstain remap.

This module is the SEAM between the frozen live gold (``gold_cross_dp_live.py`` +
``oracle_live.json``) and the two strategies actually run in the definitive
matrix:

  - "A"      — the deployed server-side compiler DP (``strategy_compiler_dp``).
               It needs a ``compiler_selection`` = {measures, dimensions, dps}
               authored as a FAITHFUL translation of each NL question into the
               live mesh's semantic vocabulary (the metric/dimension names the
               member DPs actually export — harvested from their semantic_model).
  - "strict" — the sonnet strict-MCP agent (``agent_driver``). It abstains on
               questions outside the semantic grammar (window/rank, top-N,
               dimension-only, no-aggregate list).

WHY A SEPARATE FILE (not edits to gold_cross_dp_live.py): the gold file is the
input to ``freeze_live.py`` — touching it risks perturbing ``oracle_live.json``.
The selections + abstain remap are SCORING-time wiring, not gold, so they live
here. ``gold_cross_dp_live.py`` stays byte-frozen against its oracle.

------------------------------------------------------------------------------
The live mesh semantic vocabulary (harvested 2026-06-23 from each DP's
semantic_model tool — the EXACT names the compiler accepts):

  metrics:    titer_sum, titer_avg            (pharma-labs-demo)
              dispense_count, units_dispensed (pharma-rx-demo)
              subject_count                   (pharma-subjects-demo)
              site_count                      (pharma-sites-demo)
              product_count                   (pharma-product-demo)
  dimensions: assay_type, subject_country, subject_mrn   (labs)
              dispense_channel, prescriber_npi           (rx)
              site_region                                (sites)
              product_name, modality                     (product)

NOTE the EXPRESSIVENESS CEILING this exposes (honest, not gamed):
  - x03 asks ``assay_count`` per country — there is NO assay-count metric in the
    mesh (labs exports titer_sum/titer_avg, not a row count). Strategy A CANNOT
    express it -> the compiler errors loud ("unknown metric 'assay_count'").
    We still author the faithful dims so A's ERROR is recorded, not hidden.
  - x09 (list mrn+npi) and x17 (list channels) carry NO aggregate. The compiler
    requires >=1 metric ("No measures selected") -> ERROR. Faithful: measures=[].
  - x10 (rank within country) and x14 (top-2) need window / ORDER+LIMIT shaping
    the measure/dimension compiler does not emit. A produces the un-ranked /
    un-limited rollup -> FAIL on rows (the honest "valid-but-wrong" for A).

The ``dps`` list per question is the MINIMAL set whose payloads carry the
referenced metric+dimension (plus the subjects/sites bridge when the dimension
lives on a different DP than the metric). Passing only the needed DPs keeps the
compiler's "known metrics" list tight so an unknown-metric error is precise.
"""

from __future__ import annotations

# All member DPs (fullName stems) — the bridge DPs (subjects, sites) are included
# whenever a metric must be rolled up to a dimension that lives on another DP.
_SUBJ = "pharma-subjects-demo"
_SITES = "pharma-sites-demo"
_LABS = "pharma-labs-demo"
_RX = "pharma-rx-demo"
_PROD = "pharma-product-demo"


# question_id -> compiler_selection (measures, dimensions, dps).
# A faithful NL->semantic translation. Where the mesh has no metric for the
# question's aggregate, measures reflect that honestly (empty or a wrong-but-
# closest metric is NEVER substituted — we let A error rather than game it).
COMPILER_SELECTIONS: dict[str, dict] = {
    # single-DP sanity
    "x01": {"measures": ["subject_count"], "dimensions": [], "dps": [_SUBJ]},
    "x02": {"measures": ["units_dispensed"], "dimensions": ["dispense_channel"], "dps": [_RX]},
    # two-DP join via crosswalk
    # x03 assay_count: NO such metric in the mesh -> A errors (expressiveness ceiling).
    "x03": {"measures": ["assay_count"], "dimensions": ["subject_country"],
            "dps": [_LABS, _SUBJ, _SITES]},
    "x04": {"measures": ["units_dispensed"], "dimensions": ["site_region"],
            "dps": [_RX, _SUBJ, _SITES]},
    # three-DP multi-hop
    "x05": {"measures": ["titer_sum"], "dimensions": ["subject_country"],
            "dps": [_LABS, _SUBJ, _SITES]},
    # four-DP far dimension. The compiler routes the subject spine through
    # site_subjects, so the sites DP (which exports it) MUST be harvested even
    # though the question never groups by region — else "Object 'SITE_SUBJECTS'
    # does not exist". Faithful: adding the bridge DP gives the compiler the
    # payloads it needs, it does not change the question.
    "x06": {"measures": ["titer_sum"], "dimensions": ["modality"],
            "dps": [_LABS, _RX, _PROD, _SUBJ, _SITES]},
    # cross-DP chasm discriminators
    "x07": {"measures": ["titer_sum", "units_dispensed"], "dimensions": ["subject_country"],
            "dps": [_LABS, _RX, _SUBJ, _SITES]},
    "x08": {"measures": ["titer_sum", "units_dispensed"], "dimensions": ["site_region"],
            "dps": [_LABS, _RX, _SUBJ, _SITES]},
    # fact-spine chasm
    "x12": {"measures": ["titer_sum"], "dimensions": ["prescriber_npi"],
            "dps": [_LABS, _RX, _SUBJ]},
    # governance list (no aggregate) -> A errors (>=1 metric required)
    "x09": {"measures": [], "dimensions": ["subject_mrn", "prescriber_npi"],
            "dps": [_SUBJ, _RX]},
    # long-tail window/rank: A emits the un-ranked rollup (no window) -> wrong shape.
    # Needs the sites bridge DP (subject-spine routing) to compile at all.
    "x10": {"measures": ["titer_sum"], "dimensions": ["subject_country"],
            "dps": [_LABS, _SUBJ, _SITES]},
    # left-join completeness pair
    "x13": {"measures": ["units_dispensed"], "dimensions": ["product_name"],
            "dps": [_RX, _PROD]},
    "x13b": {"measures": ["units_dispensed"], "dimensions": ["product_name"],
             "dps": [_RX, _PROD]},
    # top-N: A emits the full rollup (no ORDER+LIMIT) -> wrong shape
    "x14": {"measures": ["units_dispensed"], "dimensions": ["product_name"],
            "dps": [_RX, _PROD]},
    # label column
    "x15": {"measures": ["units_dispensed"], "dimensions": ["product_name"],
            "dps": [_RX, _PROD]},
    # grand-total rollup
    "x16": {"measures": ["titer_sum"], "dimensions": [], "dps": [_LABS, _SUBJ, _SITES]},
    # dimension-only (no aggregate) -> A errors (>=1 metric required)
    "x17": {"measures": [], "dimensions": ["dispense_channel"], "dps": [_RX]},
}


# The frozen gold's ``expect_abstain`` lists reference the PoC approach ids
# (M = LLM-merge baseline, X = cross-DP compiler, P = strict-MCP plan-validated).
# The LIVE matrix runs strategy ids "A" (compiler-DP, the live analog of X) and
# "strict" (the sonnet strict agent, the live analog of P). So a gold record that
# expects the PoC strict/long-tail decline (any of M/X/P) translates to: the LIVE
# "strict" strategy is expected to abstain here. We DO NOT make "A" expected-to-
# abstain on anything — the compiler never abstains by contract (it errors), so an
# A abstain is impossible and an A error/over-reach must score on its own merits.
#
# Mapping rule: if a gold record lists ANY PoC abstain id, the live "strict"
# strategy inherits an expected-abstain. (Every long-tail/dimension-only record
# in the live gold lists "M"; x17 additionally lists X/M/P.)
_POC_ABSTAIN_IDS = frozenset({"M", "X", "P"})


def live_expects_abstain(poc_expect_abstain: list[str] | None) -> dict[str, bool]:
    """Translate a gold record's PoC expect_abstain list to live strategy ids.

    Returns {"strict": True} when the PoC record expected ANY approach to decline
    (the question is outside the strict semantic grammar); else {} (no strategy is
    expected to abstain).
    """
    ids = set(poc_expect_abstain or [])
    return {"strict": True} if ids & _POC_ABSTAIN_IDS else {}
