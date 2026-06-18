# ruff: noqa: F403, F405
from nxd_models import *

# Source: support articles pulled from an API.
articles_model = (
    semantic_model("articles_model")
    .description("Raw support articles to be embedded")
    .schema(
        {
            "article_id": (string(), "Stable source id for the article"),
            "title": (string(), "Article title"),
            "body": (string(), "Article body text"),
        }
    )
)

# Output: chunked + embedded documents written to a pgvector store.
documents_model = (
    semantic_model("documents_model")
    .description("Chunked article text with embeddings for semantic search")
    .schema(
        {
            "chunk_id": (string(), "Unique id for this chunk"),
            "article_id": (string(), "Source article id"),
            "content": (string(), "The chunk text"),
            "embedding": (string(), "Vector embedding for the chunk"),
        }
    )
)
