# ruff: noqa: F403, F405
from nxd_spec import *

spec = (
    data_product(
        name="jira",
        description="Atlassian Jira issues (project NXD) retrieved via "
        "the REST API, with free-text fields (summary, description, "
        "comments) chunked, embedded with sentence-transformers "
        "`all-MiniLM-L6-v2`, and persisted to pgvector for semantic "
        "search. Other core fields ride along as metadata.",
        domain="engineering",
        version="1.0.1-dev",
        infra_profile="ecommerce-demo",
    )
    .environment("demo")
    .input(
        "jira",
        source_aligned_input()
        .source("https://app.demo.nextopia.dev/infra-profile/ecommerce-demo#/services/jira-api")
        .model(jira_issue)
        .expectation(jira_issue)
        .expectation(
            custom("Jira API Freshness")
            .verify(code(api_source_freshness.verify))
            .description(
                "Jira API must be reachable and returning recent social signal data within the expected freshness window"
            )
        ),
    )
    .output(
        data_product_output()
        .model(jira_issue)
        .port(
            "pgvector",
            storage("https://app.demo.nextopia.dev/infra-profile/ecommerce-demo#/services/pgvector").config(
                pg_vector_config("public").target_table(
                    "jira_issue_embeddings", jira_issue_embedding
                )
            ).model(jira_issue_embedding),
        ).promise(jira_issue_embeddings)
    )
    .transform(
        code(transform)
        .compute("https://app.demo.nextopia.dev/infra-profile/ecommerce-demo#/services/k8s-compute")
        .when(scheduled("*/10 * * * *"), startup=True)
    )
    # TODO: replace placeholder users with real owner / steward / access.
    .control("owner", owner().user("hello@nextdata.com"))
    .control("steward", data_product_access().user("hello@nextdata.com"))
    .control("data-product-access", data_product_access().user("hello@nextdata.com"))
)
