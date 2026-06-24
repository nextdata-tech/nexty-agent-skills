"""CROSS-DP gold set, RE-AUTHORED to the LIVE pharma mesh (LOWERENVS_DB).

This is the live-mesh sibling of
``examples/t2sql-poc/gold/gold_cross_dp.py``. Same record shape
(``id`` / ``category`` / ``question`` / ``canonical_sql`` / ``equality_mode`` /
optional ``expect_abstain`` / ``is_discriminator``) — ``freeze_gold.freeze``
runs each ``canonical_sql`` through the RAW root LOWERENVS_ROLE key-pair
connection to produce ``oracle_live.json``.

WHY A SEPARATE FILE: the PoC fixture gold was authored against the seeded
DuckDB/Snowflake fixture columns (``titer_value`` / ``channel`` / ``region`` on
the crosswalk / ``therapeutic_area``). The LIVE mesh tables differ:

  subjects(SUBJECT_ID, SUBJECT_COUNTRY, SUBJECT_MRN)            PHARMA_SUBJECTS_DEMO   n=8
  site_subjects(SITE_ID, SUBJECT_ID)                           PHARMA_SITES_DEMO      n=10
  sites(SITE_ID, SITE_REGION)                                  PHARMA_SITES_DEMO      n=5  (NA/EU/APAC)
  assays(ASSAY_ID, SUBJECT_ID, ASSAY_TYPE, TITER)              PHARMA_LABS_DEMO       n=8
  dispenses(DISPENSE_ID, SUBJECT_ID, PRODUCT_ID, UNITS,
            DISPENSE_CHANNEL, PRESCRIBER_NPI)                  PHARMA_RX_DEMO         n=5
  products(PRODUCT_ID, PRODUCT_NAME, MODALITY)                 PHARMA_PRODUCT_DEMO    n=5

Key renames vs the PoC gold:
  titer_value -> TITER ; channel -> DISPENSE_CHANNEL ; therapeutic_area -> MODALITY.
  Region is NOT on the crosswalk — it lives on sites.SITE_REGION and is reached
  by joining site_subjects.SITE_ID -> sites.SITE_ID. Region values are
  NA / EU / APAC (the PoC used North America / EMEA).

All SQL is schema-qualified (LOWERENVS_DB.PHARMA_*.<table>) so the root
LOWERENVS_ROLE principal (cross-schema USAGE) can run it directly. Identifiers
are unquoted (Snowflake resolves case-insensitively); the freezer lowercases
cursor column names so oracle keys match the executor's lowercased row dicts.

LIVE DATA SHAPE (drives the truth values, verified this freeze):
  subjects: 1,2=US ; 3,4=DE ; 5=FR ; 6,7=BE ; 8=NL
  site_subjects: s2 at sites 1&2 (both NA) ; s5 at sites 3&4 (both EU)  <- multi-site fan-out
  assays/subject (sum TITER): s1=200, s2=295, s3=350, s4=150, s5=175 ; s6,7,8 none
  dispenses: s1 -> 2 rows (units 30+60, prod1&2, retail+mail-order, npi 1234567890)
             s2 -> 1 row  (30, prod1, retail, 9876543210)
             s3 -> 2 rows (90+45, prod3 x2, specialty+mail-order, 5556667770)
  products with dispenses: 1 Humira, 2 Lipitor, 3 Comirnaty
  ORPHAN products (zero dispenses): 4 Keytruda, 5 Metformin

NOT LIVE-REPRODUCIBLE:
  x11 (titer_sum per channel) NO LONGER DISCRIMINATES on live data — no subject
  has >=2 dispenses in the SAME channel (s1 retail+mail-order; s3
  specialty+mail-order are both distinct), so the fact-spine fan-out collapses
  and naive == correct. Marked ``skipped`` so the freezer records the reason
  instead of pretending it's a discriminator. (x12 per prescriber_npi DOES still
  discriminate — s1 has two dispenses under the same npi.)
"""

from __future__ import annotations

DB = "LOWERENVS_DB"
SUBJ = f"{DB}.PHARMA_SUBJECTS_DEMO.subjects"
SS = f"{DB}.PHARMA_SITES_DEMO.site_subjects"
SITES = f"{DB}.PHARMA_SITES_DEMO.sites"
ASSAYS = f"{DB}.PHARMA_LABS_DEMO.assays"
DISP = f"{DB}.PHARMA_RX_DEMO.dispenses"
PROD = f"{DB}.PHARMA_PRODUCT_DEMO.products"


GOLD_CROSS_DP_LIVE: list[dict] = [
    # ---------------- single-DP sanity (2) ---------------- #
    {
        "id": "x01",
        "category": "single_dp",
        "question": "how many subjects are there",
        "canonical_sql": (
            f"SELECT count(DISTINCT subject_id) AS subject_count FROM {SUBJ}"
        ),
        "equality_mode": "numeric",
    },
    {
        "id": "x02",
        "category": "single_dp",
        "question": "total units_dispensed per channel",
        "canonical_sql": (
            f"SELECT dispense_channel, sum(units) AS units_dispensed "
            f"FROM {DISP} GROUP BY dispense_channel"
        ),
        "equality_mode": "set",
    },
    # ---------------- two-DP join via crosswalk (2) ---------------- #
    {
        "id": "x03",
        "category": "two_dp_join",
        "question": "assay_count per subject_country",
        "canonical_sql": (
            f"WITH a AS (SELECT subject_id, count(DISTINCT assay_id) AS assay_count "
            f"FROM {ASSAYS} GROUP BY subject_id), "
            f"x AS (SELECT DISTINCT subject_id FROM {SS}) "
            f"SELECT s.subject_country, sum(a.assay_count) AS assay_count "
            f"FROM {SUBJ} s "
            f"LEFT JOIN x ON x.subject_id = s.subject_id "
            f"LEFT JOIN a ON a.subject_id = s.subject_id "
            f"GROUP BY s.subject_country"
        ),
        "equality_mode": "numeric",
    },
    {
        "id": "x04",
        "category": "two_dp_join",
        # RX -> SITES, grouped by region. Region lives on sites.SITE_REGION,
        # reached via site_subjects.SITE_ID. units_dispensed rolled to subject in
        # `d`, then (subject_id, site_region) DISTINCT-collapsed BEFORE the join so
        # a subject at >=2 sites in the SAME region counts once. Naive raw-spine
        # over-counts (NA 285 naive vs 255 true: subject 2 at two NA sites).
        "question": "units_dispensed per region",
        "canonical_sql": (
            f"WITH d AS (SELECT subject_id, sum(units) AS units_dispensed "
            f"FROM {DISP} GROUP BY subject_id), "
            f"sr AS (SELECT DISTINCT ss.subject_id, si.site_region "
            f"FROM {SS} ss JOIN {SITES} si ON si.site_id = ss.site_id) "
            f"SELECT sr.site_region, sum(d.units_dispensed) AS units_dispensed "
            f"FROM sr LEFT JOIN d ON d.subject_id = sr.subject_id "
            f"GROUP BY sr.site_region"
        ),
        "equality_mode": "numeric",
    },
    # ---------------- three-DP multi-hop (1) ---------------- #
    {
        "id": "x05",
        "category": "three_dp_multihop",
        "question": "titer_sum per subject_country",
        "canonical_sql": (
            f"WITH a AS (SELECT subject_id, sum(titer) AS titer_sum "
            f"FROM {ASSAYS} GROUP BY subject_id), "
            f"x AS (SELECT DISTINCT subject_id FROM {SS}) "
            f"SELECT s.subject_country, sum(a.titer_sum) AS titer_sum "
            f"FROM {SUBJ} s "
            f"LEFT JOIN x ON x.subject_id = s.subject_id "
            f"LEFT JOIN a ON a.subject_id = s.subject_id "
            f"GROUP BY s.subject_country"
        ),
        "equality_mode": "numeric",
    },
    # ---------------- four-DP far-dimension (1) ---------------- #
    {
        "id": "x06",
        "category": "four_dp_far_dim",
        # therapeutic_area -> MODALITY on the live products table. LABS titer
        # bridged to products via the dispenses (subject_id, product_id) crosswalk.
        "question": "titer_sum per modality",
        "canonical_sql": (
            f"WITH a AS (SELECT subject_id, sum(titer) AS titer_sum "
            f"FROM {ASSAYS} GROUP BY subject_id), "
            f"bd AS (SELECT DISTINCT product_id, subject_id FROM {DISP}) "
            f"SELECT p.modality, sum(a.titer_sum) AS titer_sum "
            f"FROM {PROD} p "
            f"LEFT JOIN bd ON bd.product_id = p.product_id "
            f"LEFT JOIN a ON a.subject_id = bd.subject_id "
            f"GROUP BY p.modality"
        ),
        "equality_mode": "numeric",
        "expect_abstain": ["M"],
    },
    # ---------------- CROSS-DP CHASM discriminators (2) ---------------- #
    {
        "id": "x07",
        "category": "cross_dp_fanout",
        "is_discriminator": True,
        # titer_sum (LABS, MANY/subject) + units_dispensed (RX, MANY/subject) per
        # subject_country, joined through the crosswalk. Naive double-counts BOTH.
        # LIVE: correct US (495,120) DE (500,135) FR (175,null) ; naive US (990,300).
        "question": (
            "total assay titer_sum and total units_dispensed per subject_country"
        ),
        "canonical_sql": (
            f"WITH a AS (SELECT subject_id, sum(titer) AS titer_sum "
            f"FROM {ASSAYS} GROUP BY subject_id), "
            f"d AS (SELECT subject_id, sum(units) AS units_dispensed "
            f"FROM {DISP} GROUP BY subject_id), "
            f"x AS (SELECT DISTINCT subject_id FROM {SS}) "
            f"SELECT s.subject_country, "
            f"sum(a.titer_sum) AS titer_sum, "
            f"sum(d.units_dispensed) AS units_dispensed "
            f"FROM {SUBJ} s "
            f"LEFT JOIN x ON x.subject_id = s.subject_id "
            f"LEFT JOIN a ON a.subject_id = s.subject_id "
            f"LEFT JOIN d ON d.subject_id = s.subject_id "
            f"GROUP BY s.subject_country"
        ),
        "equality_mode": "numeric",
    },
    {
        "id": "x08",
        "category": "cross_dp_fanout",
        "is_discriminator": True,
        # Per-region chasm. The grouping dim (region) lives on sites.SITE_REGION,
        # reached via the site_subjects.SITE_ID crosswalk hop. A subject enrolled
        # at >=2 sites in the SAME region (subject 2: sites 1&2 both NA) has >=2
        # crosswalk rows in that region, so a naive plan joining the RAW
        # crosswalk+sites spine SUMs that subject's facts once per site ->
        # double-counts WITHIN the region. LIVE: correct NA (titer 845, units 255);
        # naive NA (titer 1140, units 285). The correct plan DISTINCT-collapses
        # (subject_id, site_region) before joining the subject-grain facts.
        "question": "total assay titer_sum and total units_dispensed per region",
        "canonical_sql": (
            f"WITH a AS (SELECT subject_id, sum(titer) AS titer_sum "
            f"FROM {ASSAYS} GROUP BY subject_id), "
            f"d AS (SELECT subject_id, sum(units) AS units_dispensed "
            f"FROM {DISP} GROUP BY subject_id), "
            f"sr AS (SELECT DISTINCT ss.subject_id, si.site_region "
            f"FROM {SS} ss JOIN {SITES} si ON si.site_id = ss.site_id) "
            f"SELECT sr.site_region, "
            f"sum(a.titer_sum) AS titer_sum, "
            f"sum(d.units_dispensed) AS units_dispensed "
            f"FROM sr "
            f"LEFT JOIN a ON a.subject_id = sr.subject_id "
            f"LEFT JOIN d ON d.subject_id = sr.subject_id "
            f"GROUP BY sr.site_region"
        ),
        # The naive comparison plan (NOT scored — documents the discriminator):
        "naive_sql": (
            f"WITH a AS (SELECT subject_id, sum(titer) AS titer_sum "
            f"FROM {ASSAYS} GROUP BY subject_id), "
            f"d AS (SELECT subject_id, sum(units) AS units_dispensed "
            f"FROM {DISP} GROUP BY subject_id) "
            f"SELECT si.site_region, "
            f"sum(a.titer_sum) AS titer_sum, "
            f"sum(d.units_dispensed) AS units_dispensed "
            f"FROM {SS} ss JOIN {SITES} si ON si.site_id = ss.site_id "
            f"LEFT JOIN a ON a.subject_id = ss.subject_id "
            f"LEFT JOIN d ON d.subject_id = ss.subject_id "
            f"GROUP BY si.site_region"
        ),
        "equality_mode": "numeric",
    },
    # ---------------- FACT-SPINE chasm discriminators (2) ---------------- #
    {
        "id": "x11",
        "category": "cross_dp_fanout",
        "is_discriminator": True,
        # NOT LIVE-REPRODUCIBLE as a discriminator: no live subject has >=2
        # dispenses in the SAME channel, so the fact-spine fan-out collapses
        # (naive == correct, both = mail-order 550 / retail 495 / specialty 350).
        # Skipped rather than frozen as a no-op discriminator.
        "question": "titer_sum per channel",
        "canonical_sql": (
            f"WITH a AS (SELECT subject_id, sum(titer) AS titer_sum "
            f"FROM {ASSAYS} GROUP BY subject_id), "
            f"dc AS (SELECT DISTINCT subject_id, dispense_channel FROM {DISP}) "
            f"SELECT dc.dispense_channel, sum(a.titer_sum) AS titer_sum "
            f"FROM dc LEFT JOIN a ON a.subject_id = dc.subject_id "
            f"GROUP BY dc.dispense_channel"
        ),
        "equality_mode": "numeric",
        "skipped": "no live subject has >=2 dispenses in the same channel; "
        "fact-spine fan-out collapses, naive == correct (non-discriminating)",
    },
    {
        "id": "x12",
        "category": "cross_dp_fanout",
        "is_discriminator": True,
        # Fact-spine chasm grouped by prescriber_npi (a dispenses column). DOES
        # discriminate live: subject 1 has two dispenses under npi 1234567890, so
        # the naive raw-fact-spine plan sums subject 1's titer (200) twice -> 400.
        # LIVE: correct 1234567890=200, 5556667770=350, 9876543210=295;
        #       naive    1234567890=400, 5556667770=700.
        "question": "titer_sum per prescriber_npi",
        "canonical_sql": (
            f"WITH a AS (SELECT subject_id, sum(titer) AS titer_sum "
            f"FROM {ASSAYS} GROUP BY subject_id), "
            f"dn AS (SELECT DISTINCT subject_id, prescriber_npi FROM {DISP}) "
            f"SELECT dn.prescriber_npi, sum(a.titer_sum) AS titer_sum "
            f"FROM dn LEFT JOIN a ON a.subject_id = dn.subject_id "
            f"GROUP BY dn.prescriber_npi"
        ),
        "naive_sql": (
            f"WITH a AS (SELECT subject_id, sum(titer) AS titer_sum "
            f"FROM {ASSAYS} GROUP BY subject_id) "
            f"SELECT dd.prescriber_npi, sum(a.titer_sum) AS titer_sum "
            f"FROM {DISP} dd LEFT JOIN a ON a.subject_id = dd.subject_id "
            f"GROUP BY dd.prescriber_npi"
        ),
        "equality_mode": "numeric",
    },
    # ---------------- governance cross-DP (1) ---------------- #
    {
        "id": "x09",
        "category": "governance",
        "question": "list subject_mrn and prescriber_npi",
        "canonical_sql": (
            f"SELECT DISTINCT s.subject_mrn, d.prescriber_npi "
            f"FROM {SUBJ} s "
            f"JOIN {SS} ss ON ss.subject_id = s.subject_id "
            f"JOIN {DISP} d ON d.subject_id = s.subject_id"
        ),
        "equality_mode": "set",
    },
    # ---------------- long-tail window/rank (1) ---------------- #
    {
        "id": "x10",
        "category": "long_tail",
        "question": "rank subjects within each subject_country by titer_sum",
        "canonical_sql": (
            f"WITH a AS (SELECT subject_id, sum(titer) AS titer_sum "
            f"FROM {ASSAYS} GROUP BY subject_id) "
            f"SELECT s.subject_id, s.subject_country, a.titer_sum, "
            f"rank() OVER (PARTITION BY s.subject_country ORDER BY a.titer_sum DESC) "
            f"AS rnk "
            f"FROM {SUBJ} s JOIN a ON a.subject_id = s.subject_id"
        ),
        "equality_mode": "multiset",
        "expect_abstain": ["M"],
    },
    # ---------------- LEFT-JOIN completeness pair (2) ---------------- #
    {
        "id": "x13",
        "category": "left_join_complete",
        # complete=True: include products with no dispenses. LIVE orphans are
        # products 4 (Keytruda) and 5 (Metformin) -> NULL measure.
        # Truth: Humira 60, Lipitor 60, Comirnaty 135, Keytruda NULL, Metformin NULL.
        "question": (
            "total units_dispensed per product_name including products with no "
            "dispenses"
        ),
        "canonical_sql": (
            f"SELECT p.product_name, sum(d.units) AS units_dispensed "
            f"FROM {PROD} p "
            f"LEFT JOIN {DISP} d ON d.product_id = p.product_id "
            f"GROUP BY p.product_name"
        ),
        "equality_mode": "set",
        "expect_abstain": ["M"],
    },
    {
        "id": "x13b",
        "category": "left_join_inner",
        # complete=False (INNER): drop the orphan products. Truth: 3 products with
        # dispenses — Humira 60, Lipitor 60, Comirnaty 135 (Keytruda/Metformin out).
        "question": (
            "total units_dispensed per product_name only for products that have "
            "dispenses"
        ),
        "canonical_sql": (
            f"SELECT p.product_name, sum(d.units) AS units_dispensed "
            f"FROM {PROD} p "
            f"JOIN {DISP} d ON d.product_id = p.product_id "
            f"GROUP BY p.product_name"
        ),
        "equality_mode": "set",
        "expect_abstain": ["M"],
    },
    # ---------------- TOP-N / ORDER-BY + LIMIT (1) ---------------- #
    {
        "id": "x14",
        "category": "top_n",
        # LIVE TIE: Humira and Lipitor both = 60. A bare LIMIT 2 over (135,60,60)
        # is nondeterministic on the second slot, so the canonical adds a
        # deterministic secondary sort (product_name) to pin a stable oracle:
        # top 2 -> Comirnaty 135, Humira 60 (Lipitor 60 truncated by the tiebreak).
        "question": "the top 2 products by units_dispensed per product",
        "canonical_sql": (
            f"SELECT p.product_name, sum(d.units) AS units_dispensed "
            f"FROM {DISP} d "
            f"JOIN {PROD} p ON d.product_id = p.product_id "
            f"GROUP BY p.product_name "
            f"ORDER BY units_dispensed DESC, p.product_name ASC "
            f"LIMIT 2"
        ),
        "equality_mode": "multiset",
        "expect_abstain": ["M"],
    },
    # ---------------- LABEL COLUMN (1) ---------------- #
    {
        "id": "x15",
        "category": "label_column",
        # Project product_name (the label) not product_id. Complete-by-construction
        # LEFT join keeps the orphan products with NULL measure.
        # Truth: Humira 60, Lipitor 60, Comirnaty 135, Keytruda NULL, Metformin NULL.
        "question": "units_dispensed for each product label",
        "canonical_sql": (
            f"SELECT p.product_name, sum(d.units) AS units_dispensed "
            f"FROM {PROD} p "
            f"LEFT JOIN {DISP} d ON d.product_id = p.product_id "
            f"GROUP BY p.product_name"
        ),
        "equality_mode": "set",
        "expect_abstain": ["M"],
    },
    # ---------------- GRAND-TOTAL ROLLUP (1) ---------------- #
    {
        "id": "x16",
        "category": "grand_total",
        # Single scalar: every subject's titer summed once over the subject spine.
        # LIVE truth = 1170 (200+295+350+150+175; subjects 6/7/8 have no assays).
        "question": "total assay titer_sum across all data products",
        "canonical_sql": (
            f"WITH a AS (SELECT subject_id, sum(titer) AS titer_sum "
            f"FROM {ASSAYS} GROUP BY subject_id), "
            f"x AS (SELECT DISTINCT subject_id FROM {SS}) "
            f"SELECT sum(a.titer_sum) AS titer_sum "
            f"FROM {SUBJ} s "
            f"LEFT JOIN x ON x.subject_id = s.subject_id "
            f"LEFT JOIN a ON a.subject_id = s.subject_id"
        ),
        "equality_mode": "numeric",
        "expect_abstain": ["M"],
    },
    # ---------------- DIMENSION-ONLY ABSTAIN (1) ---------------- #
    {
        "id": "x17",
        "category": "dimension_only",
        "question": "list every channel across the mesh",
        "canonical_sql": (f"SELECT DISTINCT dispense_channel FROM {DISP}"),
        "equality_mode": "set",
        "expect_abstain": ["X", "M", "P"],
    },
]
