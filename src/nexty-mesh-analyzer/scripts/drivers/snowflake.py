"""Snowflake service-type driver. The only place the snowflake connector is
imported (lazily). Owns the Snowflake-specific clone-table exclusion rule."""
import re

from meshlib.registry import Driver

# tables the platform clones per port, named `<table>_CLONE_<digits>`
_CLONE_RE = re.compile(r"_clone_\d+$", re.I)


def _inspect(attrs):
    """Read-only inventory of a Snowflake database via INFORMATION_SCHEMA."""
    import snowflake.connector  # lazy: only needed when actually connecting

    auth = {}
    if attrs.get("pass"):
        auth["password"] = attrs["pass"]
    elif attrs.get("pat"):
        auth["password"] = attrs["pat"]
        auth["authenticator"] = "programmatic_access_token"
    elif attrs.get("private_key_pem"):
        from cryptography.hazmat.primitives import serialization
        pk = serialization.load_pem_private_key(
            attrs["private_key_pem"].encode(), password=None)
        auth["private_key"] = pk.private_bytes(
            serialization.Encoding.DER,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption())

    conn = snowflake.connector.connect(
        user=attrs["user"], account=attrs["account"], role=attrs.get("role"),
        warehouse=attrs.get("warehouse"), database=attrs.get("database"),
        login_timeout=20, network_timeout=20, **auth)
    db = attrs["database"]
    cur = conn.cursor()
    cur.execute(f"SELECT table_schema, table_name, row_count, bytes, last_altered "
                f"FROM {db}.INFORMATION_SCHEMA.TABLES WHERE table_type='BASE TABLE'")
    tbls = cur.fetchall()
    cur.execute(f"SELECT table_schema, table_name, column_name, data_type "
                f"FROM {db}.INFORMATION_SCHEMA.COLUMNS "
                f"ORDER BY table_schema, table_name, ordinal_position")
    colmap = {}
    for sch, tbl, col, dt in cur.fetchall():
        colmap.setdefault((sch, tbl), []).append({"name": col, "type": dt})
    conn.close()

    assets = [{
        "locator": f"{db}.{sch}.{tbl}", "kind": "table", "format": "snowflake",
        "schema": colmap.get((sch, tbl), []), "partitioned_by": [],
        "row_count": rc, "bytes": by, "last_modified": alt,
    } for sch, tbl, rc, by, alt in tbls]
    return {"store": f"snowflake://{attrs['account']}/{db}", "assets": assets}


def _excluded_asset(asset_name, *_):
    """Per-source-type rule: a `<table>_CLONE_<digits>` is a platform clone.
    Receives (asset_name, locator); only the name is needed here."""
    if _CLONE_RE.search(asset_name):
        return "snowflake clone table"
    return None


DRIVER = Driver(names=["snowflake"], storage_kind="db",
                inspect=_inspect, excluded_asset=_excluded_asset)
