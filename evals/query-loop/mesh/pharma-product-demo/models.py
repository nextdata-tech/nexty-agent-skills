"""Models for pharma-product-demo — the PRODUCT far dimension of the mesh.

The transform seeds the real ``PRODUCTS`` table; we promise that REAL model on the
storage port (not a dummy marker), so the discover UI surfaces the actual
attributes and their glossary links. ``products`` is a FAR dimension / ONE-side
target, so it has no outgoing cross-DP reference; its attributes link to glossary
terms.
"""

from nxd.spec import Predicate, attribute, semantic_model
from nxd.spec.data_types import int64, string

# The real product-dimension model the transform seeds (table PRODUCTS).
products_model = (
    semantic_model("products")
    .description("Product dimension — one row per product (drug / therapeutic agent).")
    .schema(
        {
            "PRODUCT_ID": int64(),
            "PRODUCT_NAME": string(),
            "MODALITY": string(),
        }
    )
    # Glossary links at the model + attribute level (render in the UI).
    .link(Predicate.GlossaryTerm, "/data-product/demo/pharma-glossary-demo#/terms/product")
    .link("PRODUCT_NAME", Predicate.GlossaryTerm,
          "/data-product/demo/pharma-glossary-demo#/terms/product")
)
