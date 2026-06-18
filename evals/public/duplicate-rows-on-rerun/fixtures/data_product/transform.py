"""Chunk knowledge-base articles, embed each chunk, write to the vector store.

Runs on a daily schedule. Run status is green every time, but the output row
count keeps growing.
"""

import uuid

from langchain_text_splitters import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer

_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
_SPLITTER = RecursiveCharacterTextSplitter(chunk_size=512, chunk_overlap=64)


def transform(articles, ctx):
    rows = []
    for article in articles:
        for chunk in _SPLITTER.split_text(article["body"]):
            rows.append(
                {
                    "chunk_id": str(uuid.uuid4()),
                    "article_id": article["article_id"],
                    "content": chunk,
                    "embedding": _MODEL.encode(chunk).tolist(),
                }
            )
    return rows
