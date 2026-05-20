"""Generic schema inference and schema-fingerprint grouping. Standard library
only — safe to import from common code and from any driver."""
import io, csv, re, json, datetime


def jdefault(o):
    """JSON serializer fallback for datetimes."""
    if isinstance(o, (datetime.datetime, datetime.date)):
        return o.isoformat()
    return str(o)


def guess_type(values):
    """Infer a column type from sample string values."""
    if not values:
        return "string"

    def is_int(v):
        try:
            int(v); return True
        except ValueError:
            return False

    def is_float(v):
        try:
            float(v); return True
        except ValueError:
            return False

    if all(is_int(v) for v in values):
        return "int"
    if all(is_float(v) for v in values):
        return "float"
    if all(v.lower() in ("true", "false") for v in values):
        return "boolean"
    if all(re.match(r"^\d{4}-\d{2}-\d{2}", v) for v in values):
        return "date"
    return "string"


def csv_schema(blob):
    """Infer a column schema from the first chunk of a CSV file."""
    rows = list(csv.reader(io.StringIO(blob.decode("utf-8", "replace"))))
    if not rows:
        return []
    header, sample = rows[0], rows[1:101]
    return [{"name": h, "type": guess_type(
                [r[i] for r in sample if i < len(r) and r[i] != ""])}
            for i, h in enumerate(header)]


def fingerprint(schema):
    """Order-sensitive tuple of column names — the grouping key."""
    return tuple(c["name"] for c in schema)


def partition_name(idx, values):
    """Name a varying path segment that *looks like a partition* — caller has
    already checked with ``is_partition_values``. Returns the partition key."""
    sample = next(iter(values))
    if (re.match(r"^\d{4}-\d{2}-\d{2}$", sample)
            or re.match(r"^\d{4}-\d{2}$", sample)
            or re.match(r"^\d{4}$", sample)):
        return "date"
    m = re.match(r"^([A-Za-z0-9_]+)=", sample)
    if m and all(re.match(rf"^{m.group(1)}=", v) for v in values):
        return m.group(1)
    if all(v.isdigit() for v in values):
        return f"id_seg{idx}"
    return f"part_seg{idx}"  # unreachable when gated by is_partition_values


def is_partition_values(values):
    """True when a varying path segment looks like partition values, not
    sibling dataset names. Recognised patterns: `key=value`, `YYYY[-MM[-DD]]`,
    all-digit shard ids. Mixed arbitrary names (e.g. ``podcast-source``,
    ``musictracks``) are treated as separate datasets, not one partitioned
    asset — caller should split along this segment instead."""
    if not values:
        return False
    if all(re.match(r"^\d{4}(-\d{2}(-\d{2})?)?$", v) for v in values):
        return True
    if all(re.match(r"^[A-Za-z0-9_]+=", v) for v in values):
        keys = {v.split("=", 1)[0] for v in values}
        if len(keys) == 1:
            return True
    if all(v.isdigit() for v in values):
        return True
    return False


def group_by_fingerprint(records):
    """Group file records into logical assets by identical (schema, format).

    Each record is a dict: {dirs: [path segments], format, schema, size, mtime}.

    Within a (schema, format) group, walk down the shared path. At each
    diverging segment, decide:

      * **Partition** (date / ``key=value`` / numeric shard) — collapse all
        values, record the partition key, keep walking.
      * **Sibling datasets** (arbitrary names like ``podcast-source`` vs
        ``musictracks``) — split the group along this segment and recurse,
        so each sibling becomes its own asset.

    This stops the matcher from merging unrelated datasets that happen to
    share a schema fingerprint under a generic prefix like ``demo/``.
    """
    groups = {}
    for r in records:
        groups.setdefault((fingerprint(r["schema"]), r["format"]), []).append(r)

    assets = []
    for (_, fmt), items in groups.items():
        assets.extend(_emit_assets(items, fmt, [], []))
    return assets


def _emit_assets(items, fmt, common, parts):
    """Recursive worker for group_by_fingerprint. ``common`` is the locator
    prefix accumulated so far; ``parts`` is the partition-key list."""
    dirlists = [it["dirs"] for it in items]
    depth = min(len(d) for d in dirlists)
    i = len(common)
    while i < depth:
        vals = {d[i] for d in dirlists}
        if len(vals) == 1:
            common = common + [dirlists[0][i]]
            i += 1
            continue
        if is_partition_values(vals):
            name = partition_name(i, vals)
            if name not in parts:
                parts = parts + [name]
            i += 1
            continue
        # Sibling datasets — split into one asset per value.
        out, by_val = [], {}
        for it in items:
            by_val.setdefault(it["dirs"][i], []).append(it)
        for val, sub in by_val.items():
            out.extend(_emit_assets(sub, fmt, common + [val], list(parts)))
        return out

    # A lone file is its own asset — name it by the file, not the parent
    # directory. Collapsing one CSV to its dir loses the strongest naming
    # signal we have (e.g. `product_catalog_source.csv` would silently
    # surface as `.../source-aligned-py/demo/`).
    single_file = len(items) == 1 and not parts and items[0].get("key")
    if single_file:
        locator, kind = items[0]["key"], "file"
    else:
        locator, kind = "/".join(common), "directory"
    return [{
        "locator": locator,
        "kind": kind,
        "format": fmt,
        "schema": list(items[0]["schema"]),
        "partitioned_by": parts,
        "object_count": len(items),
        "bytes": sum(it["size"] for it in items),
        "last_modified": max(it["mtime"] for it in items),
    }]


# --- Delta / Iceberg table detection --------------------------------
# A Delta or Iceberg table on file storage is ONE logical table, not the pile
# of `_delta_log/`, `metadata/`, and UUID-named data files it is made of. The
# table's own metadata is the authority for its schema and points at the
# parquet/avro data — so detect the table root and read schema from metadata.

def detect_table_roots(keys):
    """Find Delta/Iceberg table roots among object keys. Returns
    {root: {"format": "delta"|"iceberg", "metadata_keys": [...]}}."""
    roots = {}
    for k in keys:
        if "/_delta_log/" in k:
            root = k.split("/_delta_log/")[0]
            r = roots.setdefault(root, {"format": "delta", "metadata_keys": []})
            if k.endswith(".json"):
                r["metadata_keys"].append(k)
        elif "/metadata/" in k and k.endswith(".metadata.json"):
            root = k.split("/metadata/")[0]
            r = roots.setdefault(root, {"format": "iceberg", "metadata_keys": []})
            r["metadata_keys"].append(k)
    return roots


def is_under_table_root(key, roots):
    """True when an object key belongs to one of the detected table roots."""
    return any(key == r or key.startswith(r + "/") for r in roots)


def authoritative_metadata_key(root_info):
    """The metadata file to read for a table's schema: Delta commit 0,
    Iceberg's latest metadata.json."""
    mks = sorted(root_info.get("metadata_keys", []))
    if not mks:
        return None
    return mks[0] if root_info["format"] == "delta" else mks[-1]


def _spark_type(t):
    if isinstance(t, str):
        return t
    if isinstance(t, dict):
        return t.get("type", "struct")
    return "struct"


def delta_schema(commit_json_text):
    """Schema from a Delta `_delta_log` commit — the metaData action's
    `schemaString` (a JSON-encoded Spark struct)."""
    for line in commit_json_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if "metaData" in obj and obj["metaData"].get("schemaString"):
            sch = json.loads(obj["metaData"]["schemaString"])
            return [{"name": f["name"], "type": _spark_type(f["type"])}
                    for f in sch.get("fields", [])]
    return []


def iceberg_schema(metadata_json_text):
    """Schema from an Iceberg `*.metadata.json` — the current schema's fields."""
    meta = json.loads(metadata_json_text)
    schemas = meta.get("schemas")
    if schemas:
        cur = meta.get("current-schema-id", 0)
        sch = next((s for s in schemas if s.get("schema-id") == cur), schemas[-1])
    else:
        sch = meta.get("schema", {})
    return [{"name": f["name"], "type": str(f.get("type"))}
            for f in sch.get("fields", [])]
