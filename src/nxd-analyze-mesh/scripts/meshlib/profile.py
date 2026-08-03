"""Infra profile parsing and service classification. yaml + stdlib only.

Driver category (Storage / API / Compute / RPC / Governance) is generic
lookup data, not service-specific code. Service-type *behaviour* lives in the
`drivers/` package; this module only labels services so the caller knows
which ones are worth inspecting.
"""
import yaml

# non-secret locator attribute keys safe to display
SAFE = {"bucket", "region_name", "file_type", "account", "database", "warehouse",
        "role", "account_name", "workspace_url", "catalog", "schema", "project_id",
        "dataset_id", "bootstrap_servers", "index", "host", "port", "url"}

STORAGE = {"s3", "adls", "snowflake", "databricks/storage", "postgres", "pgvector",
           "kafka", "pinecone", "minio", "dremio", "duckdb", "redshift", "bigquery",
           "gcp/bigquery"}
COMPUTE = {"kubernetes/compute", "kubernetes/compute/streaming", "databricks/compute",
           "databricks/compute/streaming", "sagemaker", "local-python"}
RPC = {"local-python/rpc", "kubernetes/rpc"}
GOV = {"servicenow", "databricks/access-control", "databricks-contract", "mock-universal"}

CATEGORY_ORDER = ["STORAGE", "API", "COMPUTE", "RPC", "GOVERNANCE", "UNKNOWN"]


def driver_name(driver):
    """Middle segment of `nxd:<name>:<version>`; tolerate malformed values."""
    parts = driver.split(":")
    return parts[1] if len(parts) >= 3 else driver


def classify(dn):
    if dn in STORAGE:
        return "STORAGE"
    if dn == "api":
        return "API"
    if dn in COMPUTE:
        return "COMPUTE"
    if dn in RPC:
        return "RPC"
    if dn in GOV:
        return "GOVERNANCE"
    return "UNKNOWN"


def parse_services(profile_path):
    """Return (profile_name, [service dict]). Each service dict has name,
    driver, driver_name, category, locator (non-secret attrs), attrs (all)."""
    spec = yaml.safe_load(open(profile_path))
    services = []
    for svc in spec["spec"]["services"]:
        dn = driver_name(svc["driver"])
        attrs = {a["key"]: a["value"] for a in svc.get("attributes", [])}
        services.append({
            "name": svc["name"],
            "driver": svc["driver"],
            "driver_name": dn,
            "category": classify(dn),
            "locator": {k: attrs[k] for k in attrs if k in SAFE},
            "attrs": attrs,
        })
    return spec["metadata"]["name"], services
