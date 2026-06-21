from nxd.experimental.semantic import Agg, SemanticRegistry

# Registry for DP_PRODUCT — the `products` entity (grain product_id).
#
# Role in the mesh: a FAR dimension, reachable only multi-hop (dispenses ->
# products). This DP is a ONE-side target: it has NO outgoing joins. Other DPs
# (DP_RX) declare the inbound N:1 join to `products`; here we only model the
# product entity itself so bare-name `products` resolves across the mesh.
REGISTRY = (
    SemanticRegistry()
    # ── Models ──────────────────────────────────────────────────────────────────
    .model(
        "products",
        grain="PRODUCT_ID",
        description="One row per product (drug / therapeutic agent).",
    )
    # ── Dimensions ──────────────────────────────────────────────────────────────
    .dimension(
        "product_name",
        model="products",
        column="PRODUCT_NAME",
        type="string",
        description="Human-readable product name.",
    )
    .dimension(
        "modality",
        model="products",
        column="MODALITY",
        type="string",
        description="Therapeutic modality (e.g. antibody, small_molecule, vaccine).",
    )
    # ── Metrics ─────────────────────────────────────────────────────────────────
    .metric(
        "product_count",
        model="products",
        agg=Agg.COUNT_DISTINCT,
        column="PRODUCT_ID",
        description="Distinct number of products.",
    )
    # ── Joins ───────────────────────────────────────────────────────────────────
    # NONE. `products` is a far dimension / ONE-side target — no outgoing joins.
    .build()
)
