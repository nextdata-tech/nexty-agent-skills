# ruff: noqa: F403, F405
from nxd_spec import *

spec = (
    data_product(
        name="kb-articles-vectors",
        domain="Support",
        description="Embeds knowledge-base articles into a vector store for semantic search; refreshed daily.",
        version="0.1.0-dev",
        infra_profile="support-demo",
    )
    .environment("demo")
    .input(
        "articles-api",
        source_aligned_input()
        .source("https://example.com/infra-profile/support-demo#/services/articles-api")
        .expectation(articles_model),
    )
    .output(
        data_product_output()
        .model(documents_model)
        .promise(documents_model)
        .port(
            "pgvector",
            storage("https://example.com/infra-profile/support-demo#/services/pgvector")
            .config(pgvector_config().target_table("KB_DOCUMENTS", documents_model)),
        )
    )
    .transform(script("transform.py"))
    .schedule("0 6 * * *")
    .control("owner", owner().user("hello@example.com"))
)
