from nxd.experimental.semantic import Agg, SemanticRegistry

# Registry for the SUBJECT SPINE of the fresh pharma mesh (MESH_DESIGN.md
# DP_REGISTRY). One model — `subjects`, grain SUBJECT_ID — the spine every
# fact in the mesh fans into. No joins (this DP is the spine itself; the
# crosswalk + facts live in sibling DPs and resolve `subjects` by bare name).
REGISTRY = (
    SemanticRegistry()
    # ── Models ──────────────────────────────────────────────────────────────────
    .model(
        "subjects",
        grain="SUBJECT_ID",
        description="One row per clinical-trial subject. The subject spine.",
    )
    # ── Dimensions ──────────────────────────────────────────────────────────────
    .dimension(
        "subject_country",
        model="subjects",
        column="SUBJECT_COUNTRY",
        type="string",
        description="Subject's country of enrollment.",
    )
    .dimension(
        "subject_mrn",
        model="subjects",
        column="SUBJECT_MRN",
        type="string",
        description="Subject medical record number (PII).",
        pii=True,
    )
    # ── Metrics ─────────────────────────────────────────────────────────────────
    .metric(
        "subject_count",
        model="subjects",
        agg=Agg.COUNT_DISTINCT,
        column="SUBJECT_ID",
        description="Distinct number of subjects.",
    )
    # ── Joins: none — this DP IS the spine. ─────────────────────────────────────
    .build()
)
