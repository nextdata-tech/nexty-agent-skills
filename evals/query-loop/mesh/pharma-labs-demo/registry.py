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
    )
    # ── Dimensions ──────────────────────────────────────────────────────────────
    .dimension(
        "assay_type",
        model="assays",
        column="ASSAY_TYPE",
        type="string",
        description="Type of lab assay (e.g. ELISA, PCR, titration).",
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
    .build()
)
