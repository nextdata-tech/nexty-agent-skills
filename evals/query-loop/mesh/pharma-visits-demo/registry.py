from nxd.experimental.semantic import Agg, Cardinality, SemanticRegistry

# Registry for DP_VISITS — fact #1 in the fresh pharma mesh (MESH_DESIGN.md).
#
# Grain: visits (visit_id). MANY visits per subject. The fact joins to the
# crosswalk hub `site_subjects` (owned by DP_SITES) by `subject_id`
# (MANY_TO_ONE), which in turn fans into the subject spine. Entity/model names
# are globally unique across the mesh so the bare-name join target resolves.
#
# CONFUSABLE PAIR (cross-grain): visit_count (how many visits, this model) vs
# subject_count (how many subjects, owned by DP_REGISTRY's `subjects` model).
# "how many visits" must resolve to visit_count here, NOT subject_count.
REGISTRY = (
    SemanticRegistry()
    # ── Models ──────────────────────────────────────────────────────────────────
    .model(
        "visits",
        grain="VISIT_ID",
        description="One row per clinical visit. MANY visits per subject.",
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
        "visit_type",
        model="visits",
        column="VISIT_TYPE",
        type="string",
        description="Type of clinical visit (e.g. screening, baseline, follow-up).",
    )
    # ── Metrics ─────────────────────────────────────────────────────────────────
    .metric(
        "visit_count",
        model="visits",
        agg=Agg.COUNT_DISTINCT,
        column="VISIT_ID",
        description="Number of distinct clinical visits (how many visits).",
    )
    .metric(
        "visit_duration_min",
        model="visits",
        agg=Agg.SUM,
        column="DURATION_MIN",
        description="Total clinical-visit duration in minutes (sum of visit durations).",
    )
    # ── Join: many visits -> one site_subject crosswalk row (N:1) ───────────────
    .join(
        left="visits",
        right="site_subjects",
        on=(("SUBJECT_ID", "SUBJECT_ID"),),
        cardinality=Cardinality.MANY_TO_ONE,
    )
    .build()
)
