"""spec.py for pharma-subjects-demo — the SUBJECT SPINE of the fresh pharma mesh.

Three MCP tools (list_models, describe_model, run_semantic_query) over the
`subjects` semantic model in Snowflake, served via an RPC output port.

The four non-negotiable wiring constraints (deployable-dp README):
1. `code()` cannot extract closures — the tool callables are module-level defs
   in tools.py that delegate to the library; build_semantic_tools(REGISTRY) is
   used ONLY for each tool's request/response models + description.
2. The registry/tools siblings are bundled only because a `.transform(...)` is
   declared (the **/*.py glob runs on the transform/compute output path).
3. All modules are FLAT at the DP root; imports are flat (`from registry import
   REGISTRY`).
4. Base tables are SELF-SEEDED by the transform into this DP's own Snowflake
   schema (the template pattern — NOT the facade). The storage port is a plain
   `storage(...)` with NO `as_view` (the nxd validator HARD-REJECTS
   `.transform()` + `as_view()` together), and there is no `source_aligned_input`.
"""

from nxd.spec import (
    code,
    data_product,
    data_product_output,
    data_product_rpc_output,
    rpc_function,
    rpc_server,
    script,
    storage,
)
from nxd.experimental.semantic import build_semantic_tools
from registry import REGISTRY
from tools import list_models, describe_model, run_semantic_query
from transform import transform
from models import provision_marker

INFRA_PROFILE = "ecommerce-demo"
SNOWFLAKE_SERVICE = "nxd-snowflake"

# Build semantic tools ONLY to obtain the request/response schema descriptors +
# descriptions; the actual callables are the module-level functions from tools.py
# (which the spec builder can locate via AST — closures cannot be located).
_tools = build_semantic_tools(REGISTRY)
_tool_map = {t.name: t for t in _tools}

_rpc = data_product_rpc_output()

for _fn, _name in [
    (list_models, "list_models"),
    (describe_model, "describe_model"),
    (run_semantic_query, "run_semantic_query"),
]:
    _t = _tool_map[_name]
    _rpc = _rpc.function(
        rpc_function(code(_fn), _t.request_model, _t.response_model).description(
            _t.description
        )
    )

_rpc = _rpc.port(
    "mcp-api",
    rpc_server(f"/infra-profile/{INFRA_PROFILE}#/services/mcp-api-service-k8s")
    .enable_endpoints()
    .mcp_path("/mcp"),
)

# Storage output port named "snowflake" — its name is the transform's parameter
# name, and it supplies the Snowflake connection both the transform (to seed the
# base table + provision the view) and run_semantic_query (to read it) use.
# Plain storage(...) with NO as_view: the self-seed transform owns provisioning.
_storage = (
    data_product_output()
    .promise(provision_marker)
    .port(
        "snowflake",
        storage(f"/infra-profile/{INFRA_PROFILE}#/services/{SNOWFLAKE_SERVICE}"),
    )
)

spec = (
    data_product(
        name="pharma-subjects-demo",
        domain="pharma",
        description=(
            "Subject-spine semantic-layer data product for the fresh pharma mesh. "
            "Exposes the `subjects` model (grain SUBJECT_ID) — governed metric "
            "subject_count and dimensions subject_country + subject_mrn[PII] — via "
            "MCP so agents answer natural-language questions without raw SQL."
        ),
        version="0.1.0",
        infra_profile=INFRA_PROFILE,
        # The provision job builds a cold venv (snowflake-connector-python[pandas]
        # + pandas) before it can seed — that exceeds the default 180s batch
        # startup timeout on the local cluster, failing the launch (DP -> Failed,
        # rpc route never mounts -> /mcp 404s). Raise it so cold provision
        # completes. (Audit P1-#6.)
        provision_timeout_secs=600,
    )
    # SEED AT PROVISION TIME. The kernel runs output-port promise verification
    # BEFORE the transform, so a marker/table seeded only in the transform does
    # not exist yet at verify -> "Field MARKER_ID not found" -> DP Failed. The
    # provision function runs FIRST (before storage-driver provisioning + before
    # verify), so seeding here makes the DP green in one launch. The same code is
    # ALSO wired as .transform() so the **/*.py glob bundles registry.py/tools.py
    # into the image (constraint #2) — the body is idempotent (CREATE IF NOT
    # EXISTS + overwrite), so running it at both lifecycle points is safe.
    # SEED AT PROVISION TIME via a SELF-CONTAINED script (provision.py): the
    # kernel verifies output-port promises BEFORE the transform, so seeding in the
    # transform fails verify ("Field MARKER_ID not found"). provision() runs first.
    # script() (not code()) because the provision entrypoint is extracted into a
    # provision/ subdir whose sys.path excludes the DP root — provision.py imports
    # NO siblings, so it resolves there. (See the audit log P1-#4/#5.)
    .provision(
        script("provision.py").compute(f"/infra-profile/{INFRA_PROFILE}#/services/k8s-compute")
    )
    # A .transform() is still declared so the **/*.py glob bundles
    # registry.py / tools.py into the image (constraint #2). The body is a no-op:
    # all real seeding happens at provision time above.
    .transform(
        code(transform).compute(f"/infra-profile/{INFRA_PROFILE}#/services/k8s-compute")
    )
    .output(_storage)
    .output(_rpc)
)
