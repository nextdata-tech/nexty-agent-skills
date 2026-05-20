"""S3 service-type driver. The only place boto3 / pyarrow are imported — and
they are imported lazily, so this module is cheap to load when only the
driver's metadata (storage kind, exclusion rules) is needed."""
import io

from meshlib.registry import Driver
from meshlib.schema import (csv_schema, group_by_fingerprint, detect_table_roots,
                            is_under_table_root, authoritative_metadata_key,
                            delta_schema, iceberg_schema)


def _inspect(attrs):
    """Read-only inventory of an S3 bucket. Delta/Iceberg tables collapse to
    one asset each (schema from table metadata); everything else is grouped
    by schema fingerprint."""
    import boto3  # lazy: only needed when actually connecting

    s3 = boto3.client("s3",
                      aws_access_key_id=attrs["aws_access_key_id"],
                      aws_secret_access_key=attrs["aws_secret_access_key"],
                      region_name=attrs.get("region_name"))
    bucket = attrs["bucket"]

    objs, token = [], None
    while True:
        kw = {"Bucket": bucket, "MaxKeys": 1000}
        if token:
            kw["ContinuationToken"] = token
        resp = s3.list_objects_v2(**kw)
        objs.extend(resp.get("Contents", []))
        if not resp.get("IsTruncated"):
            break
        token = resp.get("NextContinuationToken")
    objs = [o for o in objs if not o["Key"].endswith("/")]

    # Delta/Iceberg tables — one asset each, schema from the table metadata
    roots = detect_table_roots([o["Key"] for o in objs])
    table_assets = []
    for root, info in roots.items():
        mkey = authoritative_metadata_key(info)
        schema = []
        if mkey:
            try:
                text = s3.get_object(Bucket=bucket, Key=mkey)["Body"].read() \
                    .decode("utf-8", "replace")
                schema = (delta_schema(text) if info["format"] == "delta"
                          else iceberg_schema(text))
            except Exception:
                schema = []
        members = [o for o in objs
                   if o["Key"] == root or o["Key"].startswith(root + "/")]
        table_assets.append({
            "locator": f"s3://{bucket}/{root}/", "kind": "table",
            "format": info["format"], "schema": schema, "partitioned_by": [],
            "object_count": len(members),
            "bytes": sum(m["Size"] for m in members),
            "last_modified": max(m["LastModified"] for m in members),
        })

    # everything else — schema-fingerprint grouping (one schema per directory)
    schema_cache, records = {}, []
    for o in objs:
        if is_under_table_root(o["Key"], roots):
            continue
        key = o["Key"]
        ext = key.rsplit(".", 1)[-1].lower() if "." in key else ""
        dirs = key.split("/")[:-1]
        cache_key = ("/".join(dirs), ext)
        if cache_key not in schema_cache:
            schema_cache[cache_key] = _schema_for(s3, bucket, key, ext)
        schema, fmt = schema_cache[cache_key]
        records.append({"key": key, "dirs": dirs, "format": fmt,
                        "schema": schema, "size": o["Size"],
                        "mtime": o["LastModified"]})

    assets = group_by_fingerprint(records)
    for a in assets:
        # file-kind keeps no trailing slash; directory-kind gets one.
        suffix = "" if a.get("kind") == "file" else "/"
        a["locator"] = f"s3://{bucket}/{a['locator']}{suffix}".replace("///", "//")
    return {"store": f"s3://{bucket}", "total_objects": len(objs),
            "assets": table_assets + assets}


def _schema_for(s3, bucket, key, ext):
    """Infer (schema, format) for a representative object, dispatching on
    file extension — never CSV-parse a binary file."""
    if ext == "csv":
        try:
            body = s3.get_object(Bucket=bucket, Key=key,
                                 Range="bytes=0-65535")["Body"].read()
            return csv_schema(body), "csv"
        except Exception as e:
            return [{"name": f"<error: {e}>", "type": "error"}], "csv"
    if ext == "parquet":
        try:
            import pyarrow.parquet as pq  # lazy
            body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
            sch = pq.ParquetFile(io.BytesIO(body)).schema_arrow
            return ([{"name": n, "type": str(t)}
                     for n, t in zip(sch.names, sch.types)], "parquet")
        except Exception:
            return [], "parquet"
    # .avro / .json / other binary: record the format, no column schema
    return [], ext or "unknown"


DRIVER = Driver(names=["s3"], storage_kind="file", inspect=_inspect)
