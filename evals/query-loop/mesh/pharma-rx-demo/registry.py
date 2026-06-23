"""Semantic registry for the pharma-rx-demo data product (DP_RX).

Models a single fact grain: ``dispenses`` (one row per dispense_id) — MANY
dispenses per subject. Two N:1 joins reach the spine and a far product
dimension across DP boundaries:

    dispenses ─► site_subjects (on subject_id)   [crosswalk hub]
    dispenses ─► products       (on product_id)  [far dimension]

Confusable metric pair on this model:
- ``dispense_count``  — COUNT_DISTINCT of dispense_id (how many dispenses).
- ``units_dispensed`` — SUM of units            (how much was dispensed).

Entity/model names are globally unique across the mesh so bare-name joins
(``site_subjects``, ``products``) resolve against the other DPs' registries.
"""

from nxd.experimental.semantic import Agg, Cardinality, SemanticRegistry

REGISTRY = (
    SemanticRegistry()
    # ── Model ────────────────────────────────────────────────────────────────
    .model(
        "dispenses",
        grain="DISPENSE_ID",
        description="One row per medication dispense. MANY dispenses per subject.",
    )
    # Cross-mesh join targets declared as stub models so the N:1 joins below are
    # referentially valid at build(). Their full dimension surface lives in the
    # owning DPs (DP_SITES / DP_PRODUCT); names are globally unique across the
    # mesh so bare-name joins resolve at cross-DP planning time.
    .model(
        "site_subjects",
        grain="SUBJECT_ID",
        description="Site/subject crosswalk hub (owned by DP_SITES).",
        data_product="pharma-sites-demo",
    )
    .model(
        "subjects",
        grain="SUBJECT_ID",
        data_product="pharma-subjects-demo",
        description="Subject spine (owned by pharma-subjects-demo). Cross-DP join target.",
    )
    .model(
        "products",
        grain="PRODUCT_ID",
        description="Product dimension (owned by DP_PRODUCT).",
        data_product="pharma-product-demo",
    )
    # ── Dimensions ───────────────────────────────────────────────────────────
    .dimension(
        "dispense_channel",
        model="dispenses",
        column="DISPENSE_CHANNEL",
        type="string",
        description="Channel the dispense was fulfilled through (e.g. retail, mail-order).",
    )
    .dimension(
        "prescriber_npi",
        model="dispenses",
        column="PRESCRIBER_NPI",
        type="string",
        description="National Provider Identifier of the prescribing clinician.",
        pii=True,
    )
    # Spine dimensions owned by pharma-subjects-demo, reachable via the
    # site_subjects -> subjects 2-hop join below. compatible_dimensions
    # auto-derives these as sliceable from this fact's metrics at cross-DP plan time.
    .dimension(
        "subject_country",
        model="subjects",
        column="SUBJECT_COUNTRY",
        type="string",
        description="Country of enrollment.",
    )
    .dimension(
        "subject_mrn",
        model="subjects",
        column="SUBJECT_MRN",
        type="string",
        description="Medical record number.",
        pii=True,
    )
    # ── Metrics (CONFUSABLE pair) ────────────────────────────────────────────
    .metric(
        "dispense_count",
        model="dispenses",
        agg=Agg.COUNT_DISTINCT,
        column="DISPENSE_ID",
        description="Number of distinct dispenses (how many dispenses occurred).",
    )
    .metric(
        "units_dispensed",
        model="dispenses",
        agg=Agg.SUM,
        column="UNITS",
        description="Total units dispensed (how much medication was dispensed).",
    )
    # ── Joins: dispenses is the MANY side of each N:1 ────────────────────────
    .join(
        left="dispenses",
        right="site_subjects",
        on=(("SUBJECT_ID", "SUBJECT_ID"),),
        cardinality=Cardinality.MANY_TO_ONE,
    )
    .join(
        left="site_subjects",
        right="subjects",
        on=(("SUBJECT_ID", "SUBJECT_ID"),),
        cardinality=Cardinality.MANY_TO_ONE,
    )
    .join(
        left="dispenses",
        right="products",
        on=(("PRODUCT_ID", "PRODUCT_ID"),),
        cardinality=Cardinality.MANY_TO_ONE,
    )
    .build()
)
