from nxd.spec import data_product

spec = (
    data_product(
        name="pharma-glossary-demo",
        description=(
            "Business glossary for the pharma clinical-trial mesh. "
            "Defines canonical terms (subject, site, visit, assay, dispense, "
            "adverse event, product, prescriber, country) that tie the trial "
            "operations, lab, supply, safety, and commercial data products "
            "together."
        ),
        domain="pharma",
        version="0.7.0-dev",
        infra_profile="ecommerce-demo",
    )
    .environment("demo")
    .glossary("glossary.yaml")
)
