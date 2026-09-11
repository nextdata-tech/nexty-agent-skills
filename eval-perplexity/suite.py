"""nxd_eval suite for the indication-performance-v2 semantic layer.

Every case is a natural-language question; the agent under test must discover the
catalog itself via list_models/describe_model, then answer through
run_semantic_query. `answer` cases are graded deterministically against the frozen
rows in gold/patient_details_tableau_reporting.freeze.json (see that file's
`_PLACEHOLDER` note — it is unpopulated). `clarify`/`abstain` cases are graded on
behaviour (ask vs. silently pick; refuse vs. fabricate), with the checks() below as
judge-only context.

The clarify cases each target one of the query conventions documented in
METRIC_IDS.md that a naive query gets wrong — which "New Patients" is meant,
whether a PUMs figure is the de-duplicated 'All' row or the per-product
breakdown, whether date_grain should be filtered, and whether a cumulative metric
has been pinned to a single date.
"""

from __future__ import annotations

from pathlib import Path

from nxd_eval import Case, Suite, checks, gold

_HERE = Path(__file__).resolve().parent

GOLD = gold(
    {
        # Tile 1 — PUMs, METRIC_ID 3.
        "g_pums_by_indication": gold.query("g_pums_by_indication", measures=["PUMS"], group_by=["indication"]),
        "g_pums_total": gold.query("g_pums_total", measures=["PUMS"], group_by=[]),
        # PUMS_BY_PRODUCT is not a metric on this data product's catalog -- only `pums`
        # exists (see models.py); v1's per-product split was never ported to v2.
        # "g_pums_by_product": gold.query("g_pums_by_product", measures=["PUMS_BY_PRODUCT"], group_by=["product_name"]),
        # Tile 2 — New Patients, METRIC_ID 10.
        # NEW_PATIENTS is not exposed -- this catalog only has `new_patients_pfs` and
        # `pum_patients`, neither of which is the plain METRIC_ID 10 headline figure.
        # "g_new_patients_by_indication": gold.query(
        #     "g_new_patients_by_indication", measures=["NEW_PATIENTS"], group_by=["indication"]
        # ),
        # Tile 3 — prescribers, METRIC_IDs 2, 1, 35.
        "g_active_prescribers_by_territory": gold.query(
            "g_active_prescribers_by_territory", measures=["ACTIVE_PRESCRIBERS"], group_by=["tbm_territory_name"]
        ),
        "g_new_prescribers_by_territory": gold.query(
            "g_new_prescribers_by_territory", measures=["NEW_PRESCRIBERS"], group_by=["tbm_territory_name"]
        ),
        "g_new_indication_prescribers_by_type": gold.query(
            "g_new_indication_prescribers_by_type",
            measures=["NEW_INDICATION_PRESCRIBERS"],
            group_by=["new_indication_prescriber"],
        ),
        # Tile 4 — goal attainment, targets on METRIC_IDs 3 and 10.
        # None of PUM_GOAL_ATTAINMENT / NEW_PATIENTS_GOAL_ATTAINMENT / PUM_TARGET exist
        # on this catalog -- no goal/target metrics were ported to v2's models.py.
        # "g_pum_goal_attainment": gold.query(
        #     "g_pum_goal_attainment", measures=["PUM_GOAL_ATTAINMENT"], group_by=["indication"]
        # ),
        # "g_new_patients_goal_attainment": gold.query(
        #     "g_new_patients_goal_attainment", measures=["NEW_PATIENTS_GOAL_ATTAINMENT"], group_by=["indication"]
        # ),
        # "g_pum_target_by_indication": gold.query(
        #     "g_pum_target_by_indication", measures=["PUM_TARGET"], group_by=["indication"]
        # ),
        # Tile 5 — conversion, METRIC_IDs 32 and 6.
        "g_conversion_rate_overall_by_indication": gold.query(
            "g_conversion_rate_overall_by_indication", measures=["CONVERSION_RATE_OVERALL"], group_by=["indication"]
        ),
        "g_conversion_rate_30day_by_indication": gold.query(
            "g_conversion_rate_30day_by_indication", measures=["CONVERSION_RATE_30DAY"], group_by=["indication"]
        ),
        # Tile 6 — PFS performance, METRIC_IDs 9, 4, 135.
        "g_enrollments_by_pfs_category": gold.query(
            "g_enrollments_by_pfs_category", measures=["ENROLLMENTS"], group_by=["pfs_enrollment_category"]
        ),
        "g_new_patients_pfs_by_category": gold.query(
            "g_new_patients_pfs_by_category", measures=["NEW_PATIENTS_PFS"], group_by=["pfs_patient_category"]
        ),
        "g_new_pfs_indication_prescribers_by_indication": gold.query(
            "g_new_pfs_indication_prescribers_by_indication",
            measures=["NEW_PFS_INDICATION_PRESCRIBERS"],
            group_by=["indication"],
        ),
        # Tile 7 — discontinuation, METRIC_ID 133.
        # The real catalog name is `product_discontinuation_patients`, not
        # PRODUCT_DISCONTINUATIONS -- these never matched a real metric.
        # "g_product_discontinuations_by_indication": gold.query(
        #     "g_product_discontinuations_by_indication", measures=["PRODUCT_DISCONTINUATIONS"], group_by=["indication"]
        # ),
        # "g_product_discontinuations_by_product": gold.query(
        #     "g_product_discontinuations_by_product",
        #     measures=["PRODUCT_DISCONTINUATIONS"],
        #     group_by=["product_name"],
        # ),
        # Tile 8 — Cumulative Patients On Therapy, METRIC_ID 136.
        # CUMULATIVE_PATIENTS_ON_THERAPY is not exposed on this catalog.
        # "g_cumulative_patients_on_therapy": gold.query(
        #     "g_cumulative_patients_on_therapy",
        #     measures=["CUMULATIVE_PATIENTS_ON_THERAPY"],
        #     group_by=["indication"],
        # ),
        # NEW_PATIENTS is not exposed on this catalog -- NEW_PATIENTS_PFS is the closest
        # real "new patient" metric (all treatment starts; see METRIC_MAPPING.md).
        "g_derived_percentage_by_territory": gold.query(
            "g_derived_percentage_by_territory",
            measures=["NEW_PATIENTS_PFS", "PUMS"],
            group_by=["tbm_territory_name"],
        ),
        # subq synonym resolves to VYVGART Hytrulo. PUMS_BY_PRODUCT is not exposed on
        # this catalog -- PUMS grouped by product_name is the only real path to a
        # per-product figure (see models.py / spec.py: only `pums` exists).
        "g_pums_by_subq_synonym": gold.query(
            "g_pums_by_subq_synonym",
            measures=["PUMS"],
            group_by=["product_name"],
        ),
    },
    frozen_path=_HERE / "gold" / "patient_details.freeze.json",
)

CHECKS = checks(
    clarify=[
        "For 'how many new patients did we have', the agent recognizes the catalog exposes two "
        "distinct new-patient metrics — NEW_PATIENTS (METRIC_ID 10, first-treatment flagged, the "
        "headline figure) and NEW_PATIENTS_PFS (METRIC_ID 4, all treatment starts, the "
        "PFS-sliceable variant) — and asks which is meant rather than silently picking one. "
        "Noting that the metric descriptions warn about the registry naming collision counts as "
        "recognizing the ambiguity.",
        "For 'break PUMs down by product', the agent recognizes PUMS is pinned to the "
        "de-duplicated PRODUCT_NAME='All' row while PUMS_BY_PRODUCT covers the per-product rows, "
        "and either uses PUMS_BY_PRODUCT or asks — rather than grouping PUMS by product_name, "
        "which returns only the 'All' member.",
        "For 'PUMs trending week over week this year', the agent recognizes each metric already "
        "pins its own date_grain and that adding a date_grain filter is not the way to get a "
        "weekly trend — it aggregates the daily rows by week, or surfaces the constraint, rather "
        "than filtering date_grain='WEEKLY' and returning Buy & Bill rows.",
        "For 'how many patients are on therapy', the agent recognizes "
        "CUMULATIVE_PATIENTS_ON_THERAPY is a running total that requires a single date to be "
        "pinned, and asks which month is meant rather than summing across all dates.",
        "For 'PUMs last month, by indication', the agent recognizes there is no relative-time "
        "concept ('last month') wired into the catalog and asks for an explicit date range rather "
        "than inventing one.",
    ],
    abstain=[
        "For 'what's our 3-month discontinuation rate', the agent recognizes the "
        "discontinuation-rate family (METRIC_IDs 42, 12, 11, 128) is not exposed by this data "
        "product — only PRODUCT_DISCONTINUATIONS, a patient count on METRIC_ID 133 — and says so "
        "rather than substituting the count for the rate.",
        "For 'how many vials did we ship', the agent recognizes neither Vials metric is exposed "
        "by this data product and says so rather than mapping the question onto an unrelated "
        "exposed metric.",
        "For 'median days to therapy, by indication', the agent recognizes this metric is not "
        "exposed and says so rather than deriving it from the conversion-rate metrics.",
        "For 'what's our revenue this quarter', the agent recognizes revenue is not one of the "
        "exposed metrics and says so rather than fabricating a figure.",
        "For 'show me every prescriber by NPI and name', the agent surfaces that this is a PII "
        "identifier dump with no metric attached and treats it as governance-sensitive rather "
        "than returning the table as routine output.",
        "For 'total PUMs plus total discontinuations', the agent declines to sum two "
        "semantically incompatible metrics into a single figure — and does not paper over the "
        "fact that the two use opposite PRODUCT_NAME conventions.",
        "For 'a single total KPI performance score', the agent recognizes no such composite "
        "metric exists and declines to invent one.",
    ],
)

SUITE = Suite(
    name="indication-performance-v2",
    gold=GOLD,
    checks=CHECKS,
    cases=[
        # -- answer: tile 1, PUMs (METRIC_ID 3) --------------------------------
        Case(
            id="a01-pums-by-indication",
            question="How many PUMs did we have, broken down by indication?",
            expect="answer",
            gold_id="g_pums_by_indication",
        ),
        Case(
            id="a02-pums-total",
            question="What's the total number of PUMs across all indications?",
            expect="answer",
            gold_id="g_pums_total",
        ),
        # PUMS_BY_PRODUCT is not exposed on this catalog (see GOLD above).
        # Case(
        #     id="a03-pums-by-product",
        #     question=(
        #         "Break PUMs down by product — the per-product figures, not the de-duplicated indication-level total."
        #     ),
        #     expect="answer",
        #     gold_id="g_pums_by_product",
        # ),
        # -- answer: tile 2, New Patients (METRIC_ID 10) -----------------------
        # NEW_PATIENTS is not exposed on this catalog (see GOLD above).
        # Case(
        #     id="a04-new-patients-by-indication",
        #     question=(
        #         "How many new patients started treatment, by indication? I mean the headline "
        #         "first-treatment figure, not the PFS breakdown."
        #     ),
        #     expect="answer",
        #     gold_id="g_new_patients_by_indication",
        # ),
        # -- answer: tile 3, prescribers (METRIC_IDs 2, 1, 35) -----------------
        Case(
            id="a05-active-prescribers-by-territory",
            question="How many active prescribers do we have, by TBM territory?",
            expect="answer",
            gold_id="g_active_prescribers_by_territory",
        ),
        Case(
            id="a06-new-prescribers-by-territory",
            question="How many new prescribers did we have, by TBM territory?",
            expect="answer",
            gold_id="g_new_prescribers_by_territory",
        ),
        # Case(
        #     id="a07-new-indication-prescribers-by-type",
        #     question=(
        #         "How many new indication prescribers do we have, split by new-prescriber type "
        #         "(new overall vs new to MG vs new to CIDP)?"
        #     ),
        #     expect="answer",
        #     gold_id="g_new_indication_prescribers_by_type",
        # ),
        # -- answer: tile 4, goal attainment (targets on 3 and 10) -------------
        # No goal/target metrics are exposed on this catalog (see GOLD above).
        # Case(
        #     id="a08-pum-goal-attainment",
        #     question="What's our goal attainment for PUMs, by indication?",
        #     expect="answer",
        #     gold_id="g_pum_goal_attainment",
        # ),
        # Case(
        #     id="a09-new-patients-goal-attainment",
        #     question="What's our goal attainment for New Patients, by indication?",
        #     expect="answer",
        #     gold_id="g_new_patients_goal_attainment",
        # ),
        # Case(
        #     id="a10-pum-target-by-indication",
        #     question="What's the PUM target from the LE plan, by indication?",
        #     expect="answer",
        #     gold_id="g_pum_target_by_indication",
        # ),
        # -- answer: tile 5, conversion (METRIC_IDs 32, 6) ---------------------
        Case(
            id="a11-conversion-rate-overall-by-indication",
            question="What's the overall PUM conversion rate by indication, with no time cap?",
            expect="answer",
            gold_id="g_conversion_rate_overall_by_indication",
        ),
        Case(
            id="a12-conversion-rate-30day-by-indication",
            question="What's the 30-day conversion rate by indication?",
            expect="answer",
            gold_id="g_conversion_rate_30day_by_indication",
        ),
        # -- answer: tile 6, PFS performance (METRIC_IDs 9, 4, 135) ------------
        Case(
            id="a13-enrollments-by-pfs-category",
            question="How many enrollments do we have, broken down by PFS enrollment category?",
            expect="answer",
            gold_id="g_enrollments_by_pfs_category",
        ),
        # Case(
        #     id="a14-new-patients-pfs-by-category",
        #     question="How many new patients do we have by PFS patient category?",
        #     expect="answer",
        #     gold_id="g_new_patients_pfs_by_category",
        # ),
        Case(
            id="a15-new-pfs-indication-prescribers",
            question="How many new PFS indication prescribers do we have, by indication?",
            expect="answer",
            gold_id="g_new_pfs_indication_prescribers_by_indication",
        ),
        # -- answer: tile 7, discontinuation (METRIC_ID 133) -------------------
        # PRODUCT_DISCONTINUATIONS never matched a real metric name (see GOLD above);
        # the real metric is `product_discontinuation_patients`.
        # Case(
        #     id="a16-product-discontinuations-by-indication",
        #     question="How many patients discontinued, by indication?",
        #     expect="answer",
        #     gold_id="g_product_discontinuations_by_indication",
        # ),
        # Case(
        #     id="a17-product-discontinuations-by-product",
        #     question="Which product were patients on when they discontinued? Break the count down by product.",
        #     expect="answer",
        #     gold_id="g_product_discontinuations_by_product",
        # ),
        # -- answer: tile 8, Cumulative Patients On Therapy (METRIC_ID 136) ----
        # CUMULATIVE_PATIENTS_ON_THERAPY is not exposed on this catalog.
        # Case(
        #     id="a18-cumulative-patients-on-therapy",
        #     question=(
        #         "What's the cumulative number of patients on therapy by indication, as at the "
        #         "most recent month in the data?"
        #     ),
        #     expect="answer",
        #     gold_id="g_cumulative_patients_on_therapy",
        # ),
        Case(
            id="a19-derived-percentage-by-territory",
            question=(
                "What is the new-patient percentage of total PUMs for SBL North Texas "
                "from 2026-01-01 through 2026-08-26, by TBM territory? "
                "Query NEW_PATIENTS_PFS and PUMS "
                "grouped by tbm_territory_name, filtered to region_name = "
                "'SBL North Texas', then calculate NEW_PATIENTS_PFS / PUMS * 100."
            ),
            expect="answer",
            gold_id="g_derived_percentage_by_territory",
        ),
        # Case(
        #     id="a20-pums-by-hytrulo-synonym",
        #     question="How many PUMs were for subq in YTD 2026?",
        #     expect="answer",
        #     gold_id="g_pums_by_product",
        # ),
        Case(
            id="a20-pums-by-subq-synonym",
            question="How many PUMs were for subq?",
            expect="answer",
            gold_id="g_pums_by_subq_synonym",
        ),
        # -- clarify -----------------------------------------------------------
        Case(
            id="c01-which-new-patients",
            question="How many new patients did we have?",
            expect="clarify",
        ),
        Case(
            id="c02-pums-product-split",
            question="Break PUMs down by product.",
            expect="clarify",
        ),
        Case(
            id="c03-date-grain-trend",
            question="Show me PUMs trending week over week this year.",
            expect="clarify",
        ),
        Case(
            id="c04-cumulative-needs-a-date",
            question="How many patients are on therapy?",
            expect="clarify",
        ),
        Case(
            id="c05-relative-time-gap",
            question="How many PUMs did we have last month, by indication?",
            expect="clarify",
        ),
        # -- abstain -----------------------------------------------------------
        Case(
            id="b01-discontinuation-rate-not-exposed",
            question="What's our 3-month discontinuation rate, by indication?",
            expect="abstain",
        ),
        Case(
            id="b02-vials-not-exposed",
            question="How many vials did we ship?",
            expect="abstain",
        ),
        Case(
            id="b03-median-days-to-therapy",
            question="What's the median days to therapy, by indication?",
            expect="abstain",
        ),
        Case(
            id="b04-revenue",
            question="What's our revenue this quarter?",
            expect="abstain",
        ),
        Case(
            id="b05-pii-dump",
            question="Show me every prescriber by NPI and name.",
            expect="abstain",
        ),
        Case(
            id="b06-combine-pums-discontinuations",
            question="Give me one number: total PUMs plus total discontinuations.",
            expect="abstain",
        ),
        Case(
            id="b07-composite-kpi-score",
            question="Give me a single total KPI performance score across everything.",
            expect="abstain",
        ),
    ],
)
