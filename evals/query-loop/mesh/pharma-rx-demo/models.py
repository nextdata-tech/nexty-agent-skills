"""Models for the pharma-rx-demo (DP_RX) semantic-layer data product.

The transform seeds the REAL ``DISPENSES`` table; we promise that REAL model on
the storage port (not a dummy marker), so the discover UI surfaces the actual
attributes, their glossary links, and the cross-DP SEMANTIC RELATIONSHIP. As the
MANY-side fact, ``dispenses`` carries outgoing cross-DP references on its foreign
keys: SUBJECT_ID -> pharma-subjects-demo/subjects, PRODUCT_ID ->
pharma-product-demo/products. Model + key attributes link to glossary terms.
"""

from nxd.spec import Predicate, attribute, semantic_model
from nxd.spec.data_types import int64, string

# The real dispense-fact model the transform seeds (table DISPENSES).
dispenses_model = (
    semantic_model("dispenses")
    .description("One row per medication dispense. MANY dispenses per subject.")
    .schema(
        {
            "DISPENSE_ID": attribute(int64(), "DISPENSE_ID", "Unique dispense identifier (grain)."),
            # Cross-DP FK -> subject spine owned by pharma-subjects-demo.
            "SUBJECT_ID": attribute(int64(), "SUBJECT_ID", "Subject the product was dispensed to.")
            .referencing(
                data_product="pharma-subjects-demo",
                model="subjects",
                attribute=["SUBJECT_ID"],
            ),
            # Cross-DP FK -> product dimension owned by pharma-product-demo.
            "PRODUCT_ID": attribute(int64(), "PRODUCT_ID", "Product that was dispensed.")
            .referencing(
                data_product="pharma-product-demo",
                model="products",
                attribute=["PRODUCT_ID"],
            ),
            "UNITS": attribute(int64(), "UNITS", "Units dispensed in this event."),
            "DISPENSE_CHANNEL": attribute(
                string(), "DISPENSE_CHANNEL", "Channel the dispense was fulfilled through (retail, mail-order, specialty)."
            ),
            # PII: National Provider Identifier of the prescribing clinician.
            "PRESCRIBER_NPI": attribute(
                string(), "PRESCRIBER_NPI", "National Provider Identifier of the prescribing clinician."
            ),
        }
    )
    # Glossary links at the model + attribute level (render in the UI).
    .link(Predicate.GlossaryTerm, "/data-product/demo/pharma-glossary-demo#/terms/dispense")
    .link("PRESCRIBER_NPI", Predicate.GlossaryTerm,
          "/data-product/demo/pharma-glossary-demo#/terms/prescriber")
    .link("PRODUCT_ID", Predicate.GlossaryTerm,
          "/data-product/demo/pharma-glossary-demo#/terms/product")
    .link("SUBJECT_ID", Predicate.GlossaryTerm,
          "/data-product/demo/pharma-glossary-demo#/terms/subject")
)
