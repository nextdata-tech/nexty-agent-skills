# ruff: noqa: F403, F405
from nxd_spec import *

spec = (
    data_product(
        name="jira-embeddings",
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
        .source("https://app.westpac.nextopia.dev/infra-profile/ecommerce-demo#/services/jira-api")
        .model(jira_issue)
    )
    .output(
        data_product_output()
        .model(jira_issue_embedding)
        .promise(jira_issue_embedding)
        .port(
            "pgvector",
            storage("https://app.westpac.nextopia.dev/infra-profile/ecommerce-demo#/services/pgvector").config(
                pg_vector_config("public").target_table(
                    "jira_issue_embeddings", jira_issue_embedding
                )
            ),
        )
    )
    .transform(
        code(transform)
        .compute("https://app.westpac.nextopia.dev/infra-profile/ecommerce-demo#/services/k8s-compute")
        .when(scheduled("*/10 * * * *"), startup=True)
    )
    # TODO: replace placeholder users with real owner / steward / access.
    .control("owner", owner().user("hello@nextdata.com"))
    .control("steward", data_product_access().user("hello@nextdata.com"))
    .control("data-product-access", data_product_access().user("hello@nextdata.com"))
)
