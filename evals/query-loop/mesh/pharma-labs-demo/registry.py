from nxd.experimental.semantic import Agg, Cardinality, SemanticRegistry

# Registry for DP_LABS — fact #2 in the fresh pharma mesh (MESH_DESIGN.md).
#
# Grain: assays (assay_id). MANY assays per subject. The fact joins to the
# crosswalk hub `site_subjects` (owned by DP_SITES) by `subject_id`
# (MANY_TO_ONE), which in turn fans into the subject spine. Entity/model names
# are globally unique across the mesh so the bare-name join target resolves.
#
# Confusable metric pair: titer_sum (Σ titer) vs titer_avg (mean titer) — a
# loosely-worded "titer level" is ambiguous; the intent gate must disambiguate.
REGISTRY = (
    SemanticRegistry()
    # ── Models ──────────────────────────────────────────────────────────────────
    .model(
        "assays",
        grain="ASSAY_ID",
        description="One row per lab assay. MANY assays per subject.",
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
    # Subject spine — OWNED by DP_REGISTRY (pharma-subjects-demo). Declared here as
    # the second hop of the cross-DP path so this fact's metrics become sliceable
    # by the spine dimensions. The 2-hop JOIN resolves at the mesh layer.
    .model(
        "subjects",
        grain="SUBJECT_ID",
        data_product="pharma-subjects-demo",
        description="Subject spine (owned by pharma-subjects-demo). Cross-DP join target.",
    )
    # ── Dimensions ──────────────────────────────────────────────────────────────
    .dimension(
        "assay_type",
        model="assays",
        column="ASSAY_TYPE",
        type="string",
        description="Type of lab assay (e.g. ELISA, PCR, titration).",
    )
    # Spine dimensions — owned by pharma-subjects-demo. These become reachable
    # from this fact's metrics via the 2-hop cross-DP path (compatible_dimensions
    # auto-derives them); the compiler emits the subjects spine as the grouping
    # carrier and site_subjects as a DISTINCT bridge.
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
    # ── Metrics ─────────────────────────────────────────────────────────────────
    # CONFUSABLE PAIR — same model, same column, different aggregation.
    .metric(
        "titer_sum",
        model="assays",
        agg=Agg.SUM,
        column="TITER",
        description="Sum of measured titer across assays (total titer).",
    )
    .metric(
        "titer_avg",
        model="assays",
        agg=Agg.AVG,
        column="TITER",
        description="Average measured titer per assay (mean titer level).",
    )
    # ── Join: many assays -> one site_subject crosswalk row (N:1) ───────────────
    .join(
        left="assays",
        right="site_subjects",
        on=(("SUBJECT_ID", "SUBJECT_ID"),),
        cardinality=Cardinality.MANY_TO_ONE,
    )
    # ── Second hop: crosswalk -> subject spine (N:1) ────────────────────────────
    .join(
        left="site_subjects",
        right="subjects",
        on=(("SUBJECT_ID", "SUBJECT_ID"),),
        cardinality=Cardinality.MANY_TO_ONE,
    )
    .build()
)
