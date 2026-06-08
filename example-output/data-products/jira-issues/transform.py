"""Jira-issues-embeddings transform.

Retrieve all Atlassian Jira issues in project MARS via
``/rest/api/3/search/jql`` (paginated with ``nextPageToken``), concatenate
the free-text fields per issue, chunk them with
``RecursiveCharacterTextSplitter(chunk_size=512)``, embed each chunk with
sentence-transformers ``all-MiniLM-L6-v2`` (384-dim), and write through
``langchain_postgres.PGVectorStore`` into the pgvector instance. Core
fields (id, key, project, status, created, updated) ride along as
metadata.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_postgres import PGEngine, PGVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from nxd.data_product.context import API, PgVector
import requests

_logger = logging.getLogger("transform.jira_embeddings")
_logger.setLevel(logging.INFO)


_PROJECT = "NXD"
_JQL = f"project = {_PROJECT} AND updated >= -PT30D"
_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
_EMBEDDING_DIMS = 384            # all-MiniLM-L6-v2 output dim
_CHUNK_SIZE = 512
_DEFAULT_TABLE = "jira_issue_embeddings"
_OUTPUT_MODEL_NAME = "jira_issue_embedding"
_FIELDS = "summary,description,comment,status,project,created,updated"


def _fetch_all_issues(jira: API) -> list[dict[str, Any]]:
    """Page through ``/rest/api/3/search/jql`` collecting every issue.

    The endpoint returns ``nextPageToken`` whenever more results exist;
    we keep posting with that token until the field is absent. ``fields``
    is restricted to the columns we actually need so the response stays
    small."""
    base = str(jira.url).rstrip("/")
    auth = (str(jira.username), str(jira.token))
    issues: list[dict[str, Any]] = []
    next_token: str | None = None
    page = 0
    while True:
        body: dict[str, Any] = {
            "jql": _JQL,
            "fields": _FIELDS.split(","),
            "maxResults": 100,
        }
        if next_token:
            body["nextPageToken"] = next_token
        resp = requests.post(
            f"{base}/rest/api/3/search/jql", json=body, auth=auth, timeout=30
        )
        resp.raise_for_status()
        data = resp.json()
        batch = data.get("issues", [])
        issues.extend(batch)
        page += 1
        _logger.info("Fetched page %d: %d issues (total %d)", page, len(batch), len(issues))
        next_token = data.get("nextPageToken")
        if not next_token:
            break
    return issues


def _extract_text_blob(issue: dict[str, Any]) -> str:
    """Concatenate summary + description + every comment into one blob."""
    fields = issue.get("fields", {}) or {}
    parts = [fields.get("summary") or "", fields.get("description") or ""]
    comment_field = fields.get("comment") or {}
    for c in comment_field.get("comments", []) or []:
        body = c.get("body")
        if body:
            parts.append(body if isinstance(body, str) else str(body))
    return "\n\n".join(p for p in parts if p)


def _metadata(issue: dict[str, Any]) -> dict[str, Any]:
    """Core non-free-text fields kept as vector-store row metadata."""
    fields = issue.get("fields", {}) or {}
    status = (fields.get("status") or {}).get("name")
    project = (fields.get("project") or {}).get("key")
    return {
        "issue_id": issue.get("id"),
        "key": issue.get("key"),
        "project": project,
        "status": status,
        "created": fields.get("created"),
        "updated": fields.get("updated"),
    }


def _chunked_documents(issues: list[dict[str, Any]]) -> list[Document]:
    """Per-issue: chunk the free-text blob and tag each chunk with the
    issue's metadata. Returns a flat list of LangChain Documents."""
    splitter = RecursiveCharacterTextSplitter(chunk_size=_CHUNK_SIZE)
    docs: list[Document] = []
    for issue in issues:
        blob = _extract_text_blob(issue)
        if not blob.strip():
            continue
        meta = _metadata(issue)
        for chunk in splitter.split_text(blob):
            docs.append(Document(page_content=chunk, metadata=meta))
    _logger.info("Built %d chunked documents from %d issues", len(docs), len(issues))
    return docs


def _resolve_table(pgvector: PgVector) -> str:
    return (pgvector.model_tables or {}).get(_OUTPUT_MODEL_NAME, _DEFAULT_TABLE)


def transform(jira: API, pgvector: PgVector) -> None:
    """Entrypoint bound by spec.py — input port `jira` (API) ->
    output port `pgvector` (PgVector)."""
    issues = _fetch_all_issues(jira)
    docs = _chunked_documents(issues)
    if not docs:
        _logger.info("No documents to embed; nothing to write.")
        return

    table = _resolve_table(pgvector)
    schema = pgvector.schema or "public"
    _logger.info("Target table: %s.%s", schema, table)

    conn_str = (
        f"postgresql+psycopg://{pgvector.user}:{pgvector.password}"
        f"@{pgvector.host}:{pgvector.port}/{pgvector.database}"
    )
    pg_engine = PGEngine.from_connection_string(url=conn_str)

    # `init_vectorstore_table` is a no-op-style DDL on subsequent runs
    # only because the table already exists — the call will *raise* if
    # it does. Wrap so a re-run on an existing table doesn't break.
    try:
        pg_engine.init_vectorstore_table(
            vector_size=_EMBEDDING_DIMS,
            table_name=table,
            schema_name=schema,
        )
        _logger.info("Initialised vectorstore table %s.%s", schema, table)
    except Exception as exc:                                  # noqa: BLE001
        _logger.info("init_vectorstore_table skipped (likely exists): %s", exc)

    embeddings = HuggingFaceEmbeddings(model_name=_EMBEDDING_MODEL)
    store = PGVectorStore.create_sync(
        engine=pg_engine,
        embedding_service=embeddings,
        table_name=table,
        schema_name=schema,
    )
    store.add_documents(docs)
    _logger.info("Wrote %d embedded chunks to %s.%s", len(docs), schema, table)
