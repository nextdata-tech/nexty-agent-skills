"""Vector similarity search against pgvector or Pinecone.

Reads the leased credential blob (--creds) and an embedded query vector
(--query-vector path), runs top-k similarity, and prints the matched rows
(including the text payload if present) so the LLM can synthesise an answer.

Supports classic-RAG extensions on the pgvector backend:
  --filter '<json>'    Metadata pre-filter on langchain_metadata JSON.
                       Equality: {"project":"NXD"} -> WHERE ->>'project' = 'NXD'
                       IN-list:  {"status":["Done","Closed"]} -> IN ('Done','Closed')
  --hybrid             Run vector kNN AND Postgres FTS on --text-col, fuse with
                       RRF (k=60). Requires --query-text in addition to vector.
  --candidates N       Per-list candidate pool size for hybrid (default 50).
                       Final result trimmed to --k.
  --min-score F        Post-scoring abstain threshold. If best fused/vector score
                       < F, payload signals {"abstain": true} with empty rows so
                       the caller can say "no good match".
  --id-col NAME        Primary key column for dedup in hybrid mode
                       (default: langchain_id).
  --dedup-by FIELD     Collapse rows that share FIELD to the single best-ranked
                       row before top-k / RRF fusion. FIELD resolves to a real
                       result column if present, else to a key inside the
                       metadata JSON (default column `langchain_metadata`).
                       Generic across schemas; off by default (no dedup).
                       Use it when a logical entity is split across many near-
                       duplicate chunks (e.g. one Jira issue -> many rows) so a
                       handful of entities don't crowd out the rest of top-k.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

RRF_K = 60


def _pg_connect(doc: dict):
    import psycopg  # type: ignore

    connect = doc["connect"]
    location = (doc.get("location") or {}).get("location") or {}
    data = connect["leased_credential"]["details"].get("data") or {}
    return psycopg.connect(
        host=data.get("host") or location.get("host"),
        port=int(data.get("port") or location.get("port") or 5432),
        dbname=data.get("database") or location.get("database"),
        user=data.get("username") or data.get("user"),
        password=data.get("_password") or data.get("password"),
        sslmode=data.get("sslmode", "require"),
    )


def _resolve_table_and_vector_col(cur, doc: dict, table: str | None, vector_col: str | None) -> tuple[str, str]:
    data = doc["connect"]["leased_credential"]["details"].get("data") or {}
    location = (doc.get("location") or {}).get("location") or {}
    schema = data.get("schema") or location.get("schema") or "public"

    if not table:
        cur.execute(
            "SELECT table_name FROM information_schema.columns "
            "WHERE table_schema=%s AND data_type='USER-DEFINED' "
            "AND udt_name='vector' LIMIT 1",
            (schema,),
        )
        row = cur.fetchone()
        if not row:
            sys.exit("could not find a pgvector table — pass --table")
        table = f"{schema}.{row[0]}"

    if not vector_col:
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema=split_part(%s,'.',1) AND table_name=split_part(%s,'.',2) "
            "AND udt_name='vector' LIMIT 1",
            (table, table),
        )
        row = cur.fetchone()
        if not row:
            sys.exit("could not find a vector column — pass --vector-col")
        vector_col = str(row[0])

    return str(table), str(vector_col)


def _group_value(row: dict, dedup_by: str, metadata_col: str = "langchain_metadata") -> Any:
    """Resolve the dedup group for a row. Generic across schemas:

    1. a real result column named `dedup_by`, else
    2. a key inside the metadata JSON column (`metadata_col`), which psycopg may
       hand back as a dict or as a JSON string.
    Returns None when the field is absent (caller keeps such rows ungrouped).
    """
    if dedup_by in row and row[dedup_by] is not None:
        return row[dedup_by]
    md = row.get(metadata_col)
    if isinstance(md, str):
        try:
            md = json.loads(md)
        except (ValueError, TypeError):
            md = None
    if isinstance(md, dict):
        return md.get(dedup_by)
    return None


def _dedup_ordered(rows: list[dict], dedup_by: str, metadata_col: str = "langchain_metadata") -> list[dict]:
    """Keep the first row (best rank — caller passes pre-ordered rows) per group.

    Rows whose group value is None are never collapsed together — each is kept,
    so dedup never silently drops entities that lack the field.
    """
    seen: set = set()
    out: list[dict] = []
    for row in rows:
        g = _group_value(row, dedup_by, metadata_col)
        if g is None:
            out.append(row)
            continue
        if g in seen:
            continue
        seen.add(g)
        out.append(row)
    return out


def _build_jsonb_filter(filter_obj: dict | None, metadata_col: str = "langchain_metadata") -> tuple[str, list[Any]]:
    """Turn a filter dict into a SQL fragment + params. Returns ('', []) when empty.

    Supports equality (str/int/bool) and IN-list (list of scalars).
    """
    if not filter_obj:
        return "", []
    parts: list[str] = []
    params: list[Any] = []
    for key, val in filter_obj.items():
        if isinstance(val, list):
            placeholders = ",".join(["%s"] * len(val))
            parts.append(f"{metadata_col}->>%s IN ({placeholders})")
            params.append(key)
            params.extend(str(v) for v in val)
        else:
            parts.append(f"{metadata_col}->>%s = %s")
            params.extend([key, str(val)])
    return " AND ".join(parts), params


def _vector_only(
    cur,
    table: str,
    vector_col: str,
    vec_str: str,
    where_sql: str,
    where_params: list[Any],
    k: int,
) -> list[dict]:
    sql = f"SELECT *, {vector_col} <-> %s::vector AS distance FROM {table}"
    params: list[Any] = [vec_str]
    if where_sql:
        sql += f" WHERE {where_sql}"
        params.extend(where_params)
    sql += f" ORDER BY {vector_col} <-> %s::vector LIMIT %s"
    params.extend([vec_str, k])
    cur.execute(sql, params)
    cols = [d[0] for d in cur.description]
    drop = {vector_col}
    out: list[dict] = []
    for r in cur.fetchall():
        row = {c: r[i] for i, c in enumerate(cols) if c not in drop}
        # invert L2 distance to a 0..1-ish similarity score for downstream use
        dist = row.get("distance")
        if dist is not None:
            try:
                row["score"] = 1.0 / (1.0 + float(dist))
            except (TypeError, ValueError):
                row["score"] = None
        out.append(row)
    return out


def _fts_candidates(
    cur,
    table: str,
    text_col: str,
    query_text: str,
    where_sql: str,
    where_params: list[Any],
    candidates: int,
    fts_lang: str = "english",
) -> list[dict]:
    sql = (
        f"SELECT *, ts_rank(to_tsvector(%s, {text_col}), plainto_tsquery(%s, %s)) AS fts_rank "
        f"FROM {table} WHERE to_tsvector(%s, {text_col}) @@ plainto_tsquery(%s, %s)"
    )
    params: list[Any] = [fts_lang, fts_lang, query_text, fts_lang, fts_lang, query_text]
    if where_sql:
        sql += f" AND {where_sql}"
        params.extend(where_params)
    sql += " ORDER BY fts_rank DESC LIMIT %s"
    params.append(candidates)
    cur.execute(sql, params)
    cols = [d[0] for d in cur.description]
    return [{c: r[i] for i, c in enumerate(cols)} for r in cur.fetchall()]


def _vec_candidates(
    cur,
    table: str,
    vector_col: str,
    vec_str: str,
    where_sql: str,
    where_params: list[Any],
    candidates: int,
) -> list[dict]:
    sql = f"SELECT *, {vector_col} <-> %s::vector AS distance FROM {table}"
    params: list[Any] = [vec_str]
    if where_sql:
        sql += f" WHERE {where_sql}"
        params.extend(where_params)
    sql += f" ORDER BY {vector_col} <-> %s::vector LIMIT %s"
    params.extend([vec_str, candidates])
    cur.execute(sql, params)
    cols = [d[0] for d in cur.description]
    return [{c: r[i] for i, c in enumerate(cols)} for r in cur.fetchall()]


def _rrf_fuse(
    vec_rows: list[dict],
    fts_rows: list[dict],
    id_col: str,
    vector_col: str,
    k: int,
    dedup_by: str | None = None,
    metadata_col: str = "langchain_metadata",
) -> list[dict]:
    """Reciprocal Rank Fusion. score(doc) = sum_lists 1/(RRF_K + rank).

    The fusion key is `dedup_by`'s group value when set (so chunks of one entity
    fuse into a single result), else the `id_col` primary key. Rows whose key is
    None are dropped from fusion (no stable identity to fuse on).
    """

    def _key(row: dict) -> Any:
        if dedup_by:
            return _group_value(row, dedup_by, metadata_col)
        return row.get(id_col)

    scored: dict[Any, dict] = {}
    for rank, row in enumerate(vec_rows, start=1):
        doc_id = _key(row)
        if doc_id is None:
            continue
        entry = scored.setdefault(doc_id, {"row": row, "rrf": 0.0, "in_vec": False, "in_fts": False})
        entry["rrf"] += 1.0 / (RRF_K + rank)
        entry["in_vec"] = True
        entry["vec_rank"] = rank
        entry["distance"] = row.get("distance")
    for rank, row in enumerate(fts_rows, start=1):
        doc_id = _key(row)
        if doc_id is None:
            continue
        entry = scored.setdefault(doc_id, {"row": row, "rrf": 0.0, "in_vec": False, "in_fts": False})
        entry["rrf"] += 1.0 / (RRF_K + rank)
        entry["in_fts"] = True
        entry["fts_rank_pos"] = rank
        entry["fts_rank"] = row.get("fts_rank")

    fused = sorted(scored.values(), key=lambda e: e["rrf"], reverse=True)[:k]
    out: list[dict] = []
    for e in fused:
        row = {c: v for c, v in e["row"].items() if c != vector_col}
        row["score"] = e["rrf"]
        row["in_vector"] = e["in_vec"]
        row["in_fts"] = e["in_fts"]
        if "vec_rank" in e:
            row["vec_rank"] = e["vec_rank"]
        if "fts_rank_pos" in e:
            row["fts_rank_pos"] = e["fts_rank_pos"]
        out.append(row)
    return out


def _pgvector(
    doc: dict,
    vec: list[float],
    query_text: str | None,
    k: int,
    candidates: int,
    table: str | None,
    vector_col: str | None,
    text_col: str,
    id_col: str,
    hybrid: bool,
    filter_obj: dict | None,
    dedup_by: str | None = None,
) -> dict:
    conn = _pg_connect(doc)
    try:
        cur = conn.cursor()
        table, vector_col = _resolve_table_and_vector_col(cur, doc, table, vector_col)
        where_sql, where_params = _build_jsonb_filter(filter_obj)
        vec_str = "[" + ",".join(str(x) for x in vec) + "]"

        if hybrid:
            if not query_text:
                sys.exit("--hybrid requires --query-text")
            vec_rows = _vec_candidates(cur, table, vector_col, vec_str, where_sql, where_params, candidates)
            fts_rows = _fts_candidates(cur, table, text_col, query_text, where_sql, where_params, candidates)
            if dedup_by:
                # collapse to best-ranked row per group within each list, so RRF
                # ranks reflect distinct entities rather than duplicate chunks
                vec_rows = _dedup_ordered(vec_rows, dedup_by)
                fts_rows = _dedup_ordered(fts_rows, dedup_by)
            rows = _rrf_fuse(vec_rows, fts_rows, id_col, vector_col, k, dedup_by)
            mode = "hybrid_rrf"
        elif dedup_by:
            # pull a candidate pool (ordered by distance), collapse per group, trim to k
            pool = _vec_candidates(cur, table, vector_col, vec_str, where_sql, where_params, candidates)
            pool = _dedup_ordered(pool, dedup_by)[:k]
            rows = []
            for r in pool:
                row = {c: v for c, v in r.items() if c != vector_col}
                dist = row.get("distance")
                if dist is not None:
                    try:
                        row["score"] = 1.0 / (1.0 + float(dist))
                    except (TypeError, ValueError):
                        row["score"] = None
                rows.append(row)
            mode = "vector_only"
        else:
            rows = _vector_only(cur, table, vector_col, vec_str, where_sql, where_params, k)
            mode = "vector_only"

        return {
            "backend": "pgvector",
            "mode": mode,
            "table": table,
            "vector_col": vector_col,
            "text_col": text_col,
            "id_col": id_col,
            "dedup_by": dedup_by,
            "filter": filter_obj or None,
            "candidates_per_list": candidates if (hybrid or dedup_by) else None,
            "k": k,
            "rows": rows,
        }
    finally:
        conn.close()


def _pinecone(doc: dict, vec: list[float], k: int, namespace: str | None, filter_obj: dict | None) -> dict:
    from pinecone import Pinecone  # type: ignore

    connect = doc["connect"]
    location = (doc.get("location") or {}).get("location") or {}
    data = connect["leased_credential"]["details"].get("data") or {}

    api_key = data.get("api_key") or data.get("_api_key")
    if not api_key:
        sys.exit("no Pinecone api_key in leased credential")
    index_name = data.get("index") or location.get("index")
    if not index_name:
        sys.exit("no Pinecone index in leased credential / location")

    pc = Pinecone(api_key=api_key)
    idx = pc.Index(index_name)
    res = idx.query(
        vector=vec,
        top_k=k,
        namespace=namespace,
        include_metadata=True,
        filter=filter_obj or None,
    )
    return {
        "backend": "pinecone",
        "index": index_name,
        "namespace": namespace,
        "filter": filter_obj or None,
        "k": k,
        "rows": [
            {"id": m["id"], "score": m["score"], "metadata": m.get("metadata")}
            for m in res.get("matches", [])
        ],
    }


def _apply_min_score(result: dict, min_score: float | None) -> dict:
    if min_score is None:
        return result
    rows = result.get("rows") or []
    best = max((r.get("score") for r in rows if r.get("score") is not None), default=None)
    if best is None or best < min_score:
        result["abstain"] = True
        result["best_score"] = best
        result["min_score"] = min_score
        result["rows"] = []
    else:
        result["abstain"] = False
        result["best_score"] = best
        result["min_score"] = min_score
    return result


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--creds", required=True)
    p.add_argument("--query-vector", required=True, help="Path to JSON from embed_query.py")
    p.add_argument("--query-text", help="Original query text (required for --hybrid FTS)")
    p.add_argument("--backend", choices=("pgvector", "pinecone"), required=True)
    p.add_argument("--k", type=int, default=5)
    p.add_argument("--candidates", type=int, default=50, help="Per-list candidate pool for --hybrid (default 50)")
    p.add_argument("--table", help="pgvector: fully-qualified table name")
    p.add_argument("--vector-col", help="pgvector: vector column name")
    p.add_argument("--text-col", default="content", help="pgvector: text column (default content)")
    p.add_argument("--id-col", default="langchain_id", help="pgvector: primary-key column for hybrid dedup (default langchain_id)")
    p.add_argument("--dedup-by", help="pgvector: collapse rows sharing this field (column or metadata-JSON key) to the best-ranked one before top-k/RRF")
    p.add_argument("--namespace", help="Pinecone: namespace")
    p.add_argument("--hybrid", action="store_true", help="pgvector: fuse kNN + Postgres FTS via RRF")
    p.add_argument("--filter", help="JSON metadata filter on langchain_metadata (equality or IN-list)")
    p.add_argument("--min-score", type=float, help="Abstain threshold on best score")
    p.add_argument("--out")
    args = p.parse_args()

    doc = json.loads(Path(args.creds).read_text())
    qvec = json.loads(Path(args.query_vector).read_text())["vector"]
    filter_obj = json.loads(args.filter) if args.filter else None

    if args.backend == "pgvector":
        result: Any = _pgvector(
            doc,
            qvec,
            args.query_text,
            args.k,
            args.candidates,
            args.table,
            args.vector_col,
            args.text_col,
            args.id_col,
            args.hybrid,
            filter_obj,
            args.dedup_by,
        )
    else:
        if args.hybrid:
            sys.exit("--hybrid is only supported on pgvector today")
        result = _pinecone(doc, qvec, args.k, args.namespace, filter_obj)

    result = _apply_min_score(result, args.min_score)

    payload = json.dumps(result, default=str, indent=2)
    if args.out:
        Path(args.out).write_text(payload)
    else:
        print(payload)


if __name__ == "__main__":
    main()
