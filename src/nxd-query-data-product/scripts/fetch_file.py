"""Download a leased presigned URL and preview / SQL-query the file with DuckDB.

The file storage driver leases a `presigned_url` credential whose `details.data`
carries one URL per model. We download it to a temp path, then either preview
the first N rows + schema or run an arbitrary SQL string against the file
loaded as a DuckDB table.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import requests


def _load_creds(path: Path) -> dict:
    doc = json.loads(path.read_text())
    connect = doc.get("connect", {})
    if connect.get("status") != "connected":
        sys.exit(f"port is not connected: status={connect.get('status')!r}")
    lc = connect["leased_credential"]
    if lc.get("type") != "presigned_url":
        sys.exit(
            f"leased credential type is {lc.get('type')!r}, expected 'presigned_url'; "
            "use query_sql.py for database ports"
        )
    return doc


def _model_url(doc: dict, model: str) -> tuple[str, str]:
    """Return (url, format) for the named model on the leased credential."""
    data = doc["connect"]["leased_credential"]["details"].get("data", {})
    urls = data.get("model_urls") or {}
    paths = data.get("model_paths") or (doc.get("location", {}).get("location", {}) or {}).get("model_paths") or {}
    if model not in urls:
        sys.exit(f"model {model!r} not in leased credential; available: {list(urls)}")
    fmt = (paths.get(model) or {}).get("format") or _format_from_path((paths.get(model) or {}).get("path", ""))
    if not fmt:
        sys.exit(f"could not infer format for model {model!r}")
    return urls[model], fmt


def _format_from_path(p: str) -> str | None:
    p = p.lower()
    for ext in ("parquet", "csv", "json", "ndjson", "avro"):
        if p.endswith("." + ext):
            return ext
    return None


def _download(url: str, dest: Path) -> None:
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with dest.open("wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 64):
                if chunk:
                    f.write(chunk)


def _duckdb_read(path: Path, fmt: str) -> str:
    if fmt == "parquet":
        return f"read_parquet('{path}')"
    if fmt == "csv":
        return f"read_csv_auto('{path}')"
    if fmt in ("json", "ndjson"):
        return f"read_json_auto('{path}')"
    sys.exit(f"unsupported format: {fmt}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--creds", required=True)
    p.add_argument("--model", required=True, help="Output model name (one of `model_names`)")
    p.add_argument("--limit", type=int, default=20, help="Rows to preview (ignored when --sql is set)")
    p.add_argument("--sql", help="Optional DuckDB SQL — use `t` as the table name")
    p.add_argument("--out", help="Where to write the JSON result (default stdout)")
    args = p.parse_args()

    import duckdb  # type: ignore

    doc = _load_creds(Path(args.creds))
    url, fmt = _model_url(doc, args.model)

    with tempfile.TemporaryDirectory(prefix="nxd-fetch-") as tmp:
        suffix = "." + fmt
        local = Path(tmp) / (urlparse(url).path.rsplit("/", 1)[-1] or "data" + suffix)
        _download(url, local)
        reader = _duckdb_read(local, fmt)
        con = duckdb.connect()
        con.execute(f"CREATE VIEW t AS SELECT * FROM {reader}")
        if args.sql:
            res = con.execute(args.sql).fetchall()
            cols = [d[0] for d in con.description]
        else:
            res = con.execute(f"SELECT * FROM t LIMIT {args.limit}").fetchall()
            cols = [d[0] for d in con.description]
        schema = con.execute("DESCRIBE t").fetchall()
        out_doc = {
            "model": args.model,
            "format": fmt,
            "schema": [{"name": s[0], "type": s[1]} for s in schema],
            "columns": cols,
            "rows": [list(r) for r in res],
        }

    payload = json.dumps(out_doc, default=str, indent=2)
    if args.out:
        Path(args.out).write_text(payload)
    else:
        print(payload)


if __name__ == "__main__":
    main()
