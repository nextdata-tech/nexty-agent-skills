from nxd.experimental.semantic import Agg, Cardinality, SemanticRegistry

# DP_SAFETY — the far adverse-events fact. MANY adverse events per subject,
# reachable subject -> site_subjects -> ... only multi-hop. One model
# (adverse_events, grain ae_id) plus an N:1 join to the site_subjects
# crosswalk on subject_id (the crosswalk lives in the sibling DP_SITES DP;
# the bare-name target resolves because entity names are globally unique
# across the mesh).
#
# Confusable metric pair (intent-gate stressor): ae_count is a plain
# COUNT_DISTINCT of ae_id; serious_ae_count is a CASE-SUM over the IS_SERIOUS
# boolean flag (boolean=True), NOT a numeric SUM of a numeric column. A
# loosely-worded "adverse events" must pick ae_count; "serious adverse events"
# must pick serious_ae_count.
REGISTRY = (
    SemanticRegistry()
    # ── Model ────────────────────────────────────────────────────────────────────
    .model(
        "adverse_events",
        grain="AE_ID",
        description="One row per adverse event. MANY adverse events per subject.",
    )
    # Crosswalk hub — OWNED by DP_SITES; declared here as the N:1 join target so
    # this DP's registry compiles (the library validates join endpoints against
    # declared models). Bare name `site_subjects` is globally unique across the
    # mesh, so the cross-DP relationship resolves at the mesh layer.
    .model(
        "site_subjects",
        grain="SITE_ID, SUBJECT_ID",
        description="Site/subject crosswalk hub (owned by DP_SITES). Join target.",
        data_product="pharma-sites-demo",
    )
    # Subject spine — OWNED by pharma-subjects-demo; declared here as the
    # second-hop N:1 join target so this fact's metrics are sliceable by the
    # spine dimensions (subject_country, subject_mrn) across the mesh.
    .model(
        "subjects",
        grain="SUBJECT_ID",
        data_product="pharma-subjects-demo",
        description="Subject spine (owned by pharma-subjects-demo). Cross-DP join target.",
    )
    # ── Dimensions ───────────────────────────────────────────────────────────────
    .dimension(
        "ae_term",
        model="adverse_events",
        column="AE_TERM",
        type="string",
        description="MedDRA-style adverse-event term (e.g. headache, nausea).",
    )
    # Spine dimensions on subjects — reachable from the fact metrics via the
    # 2-hop cross-DP path (adverse_events -> site_subjects -> subjects).
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
    # ── Metrics ──────────────────────────────────────────────────────────────────
    .metric(
        "ae_count",
        model="adverse_events",
        agg=Agg.COUNT_DISTINCT,
        column="AE_ID",
        description="Number of distinct adverse events (all severities).",
    )
    .metric(
        "serious_ae_count",
        model="adverse_events",
        agg=Agg.SUM,
        column="IS_SERIOUS",
        boolean=True,
        description=(
            "Number of SERIOUS adverse events — a CASE-sum over the IS_SERIOUS "
            "boolean flag (counts rows where IS_SERIOUS is true), NOT a numeric "
            "SUM. Use only when the question asks specifically for SERIOUS events."
        ),
    )
    # ── Join: many adverse_events -> one site_subjects row (N:1) ──────────────────
    .join(
        left="adverse_events",
        right="site_subjects",
        on=(("SUBJECT_ID", "SUBJECT_ID"),),
        cardinality=Cardinality.MANY_TO_ONE,
    )
    # ── Second hop: site_subjects -> subjects (N:1) — completes the path to ────────
    # the spine so spine dimensions auto-derive as compatible with fact metrics.
    .join(
        left="site_subjects",
        right="subjects",
        on=(("SUBJECT_ID", "SUBJECT_ID"),),
        cardinality=Cardinality.MANY_TO_ONE,
    )
    .build()
)
