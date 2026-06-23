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
        data_product="pharma-sites-demo",
    )
    # Subject spine — OWNED by DP_REGISTRY (pharma-subjects-demo). Declared here as
    # the second-hop join target so this fact's metrics become sliceable by the
    # spine dimensions (subject_country) cross-DP at query time.
    .model(
        "subjects",
        grain="SUBJECT_ID",
        data_product="pharma-subjects-demo",
        description="Subject spine (owned by pharma-subjects-demo). Cross-DP join target.",
    )
    # ── Dimensions ──────────────────────────────────────────────────────────────
    .dimension(
        "visit_type",
        model="visits",
        column="VISIT_TYPE",
        type="string",
        description="Type of clinical visit (e.g. screening, baseline, follow-up).",
    )
    # Spine dimensions (owned by pharma-subjects-demo) — reachable from visit
    # metrics via the 2-hop cross-DP join through site_subjects.
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
    # ── Second hop: site_subjects crosswalk -> subject spine (N:1) ───────────────
    .join(
        left="site_subjects",
        right="subjects",
        on=(("SUBJECT_ID", "SUBJECT_ID"),),
        cardinality=Cardinality.MANY_TO_ONE,
    )
    .build()
)
