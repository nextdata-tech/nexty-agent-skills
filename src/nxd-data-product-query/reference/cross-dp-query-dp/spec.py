"""spec.py — GENERIC server-side cross-DP query data product (skill reference).

A tools-only facade DP that serves ONE MCP tool, ``run_cross_dp_query`` (see
cross_dp_query.py): it takes the caller's already-harvested per-DP semantic
registries + a concept selection, compiles ONE fan-out-safe cross-schema SQL
with the shipped ``nxd.experimental.semantic`` compiler, and executes it in-pod
under the injected Snowflake handle.

This is the SERVER-SIDE home of the cross-DP compiler. It exists because the
client cannot run the join itself: the warehouse network policy blocks an
arbitrary client IP (this pod's egress is allowlisted), and a single cross-schema
SELECT needs a role with USAGE across every spanned schema (a per-DP leased
credential is single-schema-scoped). See cross_dp_query.py for the full rationale.

DEPLOY PRECONDITIONS (the only two things to change per mesh):
  1. INFRA_PROFILE — the infra-profile that owns this mesh's services.
  2. SNOWFLAKE_SERVICE — a ``storage`` service whose role has USAGE on EVERY
     member-DP schema the queries will span (the cross-DP principal). A role
     scoped to one DP's schema returns Snowflake 002003 (schema not authorized)
     the moment a query crosses a DP boundary. This is the deliberate cross-DP
     grant the design calls "the mesh-governed service identity".

The DP owns no tables and seeds no data. The ``.transform()`` is a NO-OP that
exists only to (a) bundle the cross_dp_query.py sibling via the ``**/*.py`` glob
and (b) satisfy the validator's rpc-DP wiring. The ``snowflake`` storage output
port supplies the connection handle injected into the tool by parameter name.
"""

from nxd.spec import (
    code,
    data_product,
    data_product_output,
    data_product_rpc_output,
    rpc_function,
    rpc_server,
    semantic_model,
    storage,
)
from nxd.spec._model import AttributeSpec
from nxd.spec.data_types import boolean
from nxd.spec.data_types import int64
from nxd.spec.data_types import list as list_
from nxd.spec.data_types import string
from nxd.spec.data_types import struct
from nxd.core.yaml_schemas import Field

from cross_dp_query import run_cross_dp_query
from models import marker_model

def _field(name, data_type, description=None):
    """Field with the non-obvious required args defaulted (mirrors mcp_tools)."""
    return Field(
        data_type=data_type,
        name=name,
        description=description,
        metadata=None,
        constraints=None,
        relates_to=[],
        semantic_tags=None,
    )


# ── Per-mesh configuration ───────────────────────────────────────────────────
INFRA_PROFILE = "ecommerce-demo"
SNOWFLAKE_SERVICE = "nxd-snowflake"  # role MUST have cross-schema USAGE (see docstring)
MCP_SERVICE = "mcp-api-service-k8s"
COMPUTE_SERVICE = "k8s-compute"

# ── Request / response schema for run_cross_dp_query ─────────────────────────
# Built explicitly (mirrors nxd.experimental.semantic.mcp_tools). Optional fields
# are nullable + undescribed so the RPC→pydantic converter keeps them Optional
# (a field carrying a description is rebuilt as REQUIRED); usage guidance lives
# in the TOOL description on the function instead.
_request = semantic_model(
    name="run_cross_dp_query_request",
    description=(
        "Member-DP semantic registries + a concept selection spanning them. The "
        "data product merges the registries and compiles ONE governed cross-schema "
        "SQL — you never write SQL yourself."
    ),
).schema(
    {
        # registry_payloads + measures are required; both carry a description.
        "registry_payloads": (
            list_(_field("registry_payloads", string())),
            "Each member DP's `semantic_model` payload (the payload dict's JSON "
            "string, as returned by that tool). Include every DP your question "
            "spans. Required.",
        ),
        "measures": (
            list_(_field("measures", string())),
            "Metric concept names to compute (from the included DPs). Required.",
        ),
        "dimensions": AttributeSpec(
            name="", data_type=list_(_field("dimensions", string()))
        ).constraints(nullable=True),
        "filters": AttributeSpec(
            name="",
            data_type=list_(
                _field(
                    "filters",
                    struct(
                        [
                            _field("dimension", string()),
                            _field("op", string()),
                            _field("value", string()),
                        ]
                    ),
                )
            ),
        ).constraints(nullable=True),
    }
)

_response = semantic_model(
    name="run_cross_dp_query_response",
    description="The compiled cross-DP SQL and its governed result rows.",
).schema(
    {
        "compiled_sql": AttributeSpec(name="", data_type=string()).constraints(nullable=True),
        "row_count": AttributeSpec(name="", data_type=int64()).constraints(nullable=True),
        "truncated": AttributeSpec(name="", data_type=boolean()).constraints(nullable=True),
        "columns": AttributeSpec(
            name="", data_type=list_(_field("columns", string()))
        ).constraints(nullable=True),
        "rows": AttributeSpec(
            name="", data_type=list_(_field("rows", string()))
        ).constraints(nullable=True),
        "error": AttributeSpec(name="", data_type=string()).constraints(nullable=True),
    }
)

_TOOL_DESCRIPTION = (
    "Answer a question that spans MULTIPLE data products with ONE governed, "
    "fan-out-safe cross-schema SQL — the deterministic cross-DP compiler, run "
    "server-side. Call `semantic_model` on each DP your question touches, then "
    "pass every payload in `registry_payloads` along with the `measures` (and "
    "optional `dimensions` / `filters`) you want. The compiler pre-aggregates each "
    "measure at its model's grain before any join, so a measure spanning a 1:N "
    "cross-DP relationship is NOT double-counted; an unreachable / mixed-grain "
    "selection returns an error rather than a wrong number."
)

# ── RPC output port ──────────────────────────────────────────────────────────
_rpc = (
    data_product_rpc_output()
    .function(
        rpc_function(code(run_cross_dp_query), _request, _response).description(
            _TOOL_DESCRIPTION
        )
    )
    .port(
        "mcp-api",
        rpc_server(f"/infra-profile/{INFRA_PROFILE}#/services/{MCP_SERVICE}")
        .enable_endpoints()
        .mcp_path("/mcp"),
    )
)

# ── Storage output port ──────────────────────────────────────────────────────
# Named "snowflake" to match the tool's + transform's parameter name, so the rpc
# framework injects this port's Snowflake handle. The handle's role is the
# cross-DP principal (the deploy precondition).
#
# Attaches the marker model via `.model(...)`, NOT `.promise(...)`: `.model()`
# DECLARES a model on the port (satisfying the validator's every-port-needs-a-
# model rule) WITHOUT a production/verification contract. So nothing is seeded
# and the no-op transform writes nothing — this DP owns no data. `.promise()`
# would instead require the kernel to verify a produced table after the
# transform, which we deliberately avoid.
_storage = (
    data_product_output()
    .model(marker_model)
    .port(
        "snowflake",
        storage(f"/infra-profile/{INFRA_PROFILE}#/services/{SNOWFLAKE_SERVICE}")
        .model(marker_model),
    )
)

spec = (
    data_product(
        name="cross-dp-query-demo",
        domain="platform",
        description=(
            "Server-side cross-DP query compiler. Serves one MCP tool, "
            "run_cross_dp_query, that merges caller-supplied member-DP semantic "
            "registries into one registry, compiles a single fan-out-safe "
            "cross-schema SQL, and executes it in-pod under a cross-DP-scoped role. "
            "Generic: works for any mesh whose member schemas the configured role "
            "can read. Dynamic: the member set is a tool argument, so no redeploy is "
            "needed when the mesh changes."
        ),
        version="1.0.0-dev",
        infra_profile=INFRA_PROFILE,
    )
    .environment("demo")
    .output(_storage)
    .output(_rpc)
)
