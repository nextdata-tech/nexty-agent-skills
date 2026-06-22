from nxd.experimental.semantic import Agg, Cardinality, SemanticRegistry

# Registry for DP_SITES: the MANY_TO_MANY crosswalk hub of the pharma mesh.
#
#   site_subjects (grain site_id, subject_id) — the fan-out hub:
#     MANY_TO_ONE -> subjects (subject spine, lives in DP_REGISTRY)
#     MANY_TO_ONE -> sites    (site dimension, this DP)
#   sites (grain site_id) — the site dimension.
#
# Entity / model names are globally unique across the mesh so the bare-name
# joins (`subjects`, `sites`) resolve against whichever DP owns them.
REGISTRY = (
    SemanticRegistry()
    # ── Models ──────────────────────────────────────────────────────────────────
    .model(
        "site_subjects",
        grain="SITE_ID, SUBJECT_ID",
        description=(
            "Crosswalk hub: one row per (site, subject) enrollment. "
            "MANY_TO_MANY fan-out hub linking the subject spine to the site "
            "dimension — every cross-grain fact reaches the spine THROUGH this "
            "crosswalk, so DISTINCT-the-crosswalk fan-out guards apply."
        ),
    )
    .model(
        "sites",
        grain="SITE_ID",
        description="One row per clinical trial site.",
    )
    # Subject spine — OWNED by DP_REGISTRY; declared here as the N:1 join target
    # so this DP's registry compiles (the library validates join endpoints
    # against declared models). Bare name `subjects` is globally unique across
    # the mesh, so the cross-DP relationship resolves at the mesh layer.
    .model(
        "subjects",
        grain="SUBJECT_ID",
        description="Subject spine (owned by DP_REGISTRY). Join target.",
    )
    # ── Dimensions ──────────────────────────────────────────────────────────────
    .dimension(
        "site_region",
        model="sites",
        column="SITE_REGION",
        type="string",
        description="Geographic region the site belongs to.",
    )
    # ── Metrics ─────────────────────────────────────────────────────────────────
    .metric(
        "site_count",
        model="sites",
        agg=Agg.COUNT_DISTINCT,
        column="SITE_ID",
        description="Distinct number of clinical trial sites.",
    )
    # ── Joins: crosswalk fans out to the spine and the site dim (both N:1) ───────
    .join(
        left="site_subjects",
        right="subjects",
        on=(("SUBJECT_ID", "SUBJECT_ID"),),
        cardinality=Cardinality.MANY_TO_ONE,
    )
    .join(
        left="site_subjects",
        right="sites",
        on=(("SITE_ID", "SITE_ID"),),
        cardinality=Cardinality.MANY_TO_ONE,
    )
    .build()
)
