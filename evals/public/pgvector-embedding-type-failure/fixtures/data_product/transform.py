"""Chunk support articles, embed each chunk, write to the pgvector output port."""

import uuid

from langchain_community.vectorstores.pgvector import PGVector
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer

# 384-dim embedding model.
_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
_SPLITTER = RecursiveCharacterTextSplitter(chunk_size=512, chunk_overlap=64)


def transform(articles, ctx):
    rows = []
    for article in articles:
        for chunk in _SPLITTER.split_text(article["body"]):
            vector = _MODEL.encode(chunk).tolist()
            rows.append(
                {
                    "chunk_id": str(uuid.uuid4()),
                    "article_id": article["article_id"],
                    "content": chunk,
                    "embedding": vector,
                }
            )
    return rows
