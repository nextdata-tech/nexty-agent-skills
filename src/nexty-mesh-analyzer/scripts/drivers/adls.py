"""ADLS (Azure Data Lake Storage) driver. The only place the Azure SDKs are
imported — lazily, inside inspect()."""
import io

from meshlib.registry import Driver
from meshlib.schema import (csv_schema, group_by_fingerprint, detect_table_roots,
                            is_under_table_root, authoritative_metadata_key,
                            delta_schema, iceberg_schema)


def _inspect(attrs):
    """Read-only inventory of an ADLS storage account. Delta/Iceberg tables
    collapse to one asset each; everything else is grouped by fingerprint.
    Object keys are `<container>/<blob>` so table roots span the right scope."""
    from azure.identity import ClientSecretCredential   # lazy
    from azure.storage.blob import BlobServiceClient    # lazy

    cred = ClientSecretCredential(attrs["tenant_id"], attrs["client_id"],
                                  attrs["client_secret"])
    account = attrs["account_name"]
    # timeouts + bounded retries so a stalled blob call fails fast instead of
    # hanging the whole run
    svc = BlobServiceClient(f"https://{account}.blob.core.windows.net", cred,
                            connection_timeout=20, read_timeout=60, retry_total=3)

    # list every blob as (key=<container>/<blob>, size, mtime)
    blobs = []
    for container in svc.list_containers():
        cc = svc.get_container_client(container.name)
        for blob in cc.list_blobs():
            if blob.name.endswith("/"):
                continue
            blobs.append((f"{container.name}/{blob.name}",
                          blob.size or 0, blob.last_modified))

    def _download(key, **kw):
        container, _, path = key.partition("/")
        return svc.get_container_client(container).download_blob(path, **kw).readall()

    # Delta/Iceberg tables — one asset each, schema from the table metadata
    roots = detect_table_roots([k for k, _, _ in blobs])
    table_assets = []
    for root, info in roots.items():
        mkey = authoritative_metadata_key(info)
        schema = []
        if mkey:
            try:
                text = _download(mkey).decode("utf-8", "replace")
                schema = (delta_schema(text) if info["format"] == "delta"
                          else iceberg_schema(text))
            except Exception:
                schema = []
        members = [b for b in blobs
                   if b[0] == root or b[0].startswith(root + "/")]
        table_assets.append({
            "locator": f"adls://{account}/{root}/", "kind": "table",
            "format": info["format"], "schema": schema, "partitioned_by": [],
            "object_count": len(members),
            "bytes": sum(s for _, s, _ in members),
            "last_modified": max(m for _, _, m in members),
        })

    # everything else — schema-fingerprint grouping
    schema_cache, records = {}, []
    for key, size, mtime in blobs:
        if is_under_table_root(key, roots):
            continue
        ext = key.rsplit(".", 1)[-1].lower() if "." in key else ""
        dirs = key.split("/")[:-1]
        cache_key = ("/".join(dirs), ext)
        if cache_key not in schema_cache:
            schema_cache[cache_key] = _schema_for(_download, key, ext)
        schema, fmt = schema_cache[cache_key]
        records.append({"dirs": dirs, "format": fmt, "schema": schema,
                        "size": size, "mtime": mtime})

    assets = group_by_fingerprint(records)
    for a in assets:
        a["locator"] = f"adls://{account}/{a['locator']}/".replace("///", "//")
    return {"store": f"adls://{account}", "total_objects": len(blobs),
            "assets": table_assets + assets}


def _schema_for(download, key, ext):
    """Infer (schema, format) for a representative blob, dispatching on the
    file extension — never CSV-parse a binary file."""
    if ext == "csv":
        try:
            return csv_schema(download(key, offset=0, length=65536)), "csv"
        except Exception as e:
            return [{"name": f"<error: {e}>", "type": "error"}], "csv"
    if ext == "parquet":
        try:
            import pyarrow.parquet as pq  # lazy
            sch = pq.ParquetFile(io.BytesIO(download(key))).schema_arrow
            return ([{"name": n, "type": str(t)}
                     for n, t in zip(sch.names, sch.types)], "parquet")
        except Exception:
            return [], "parquet"
    # .avro / .json / other binary: record the format, no column schema
    return [], ext or "unknown"


DRIVER = Driver(names=["adls"], storage_kind="file", inspect=_inspect)
