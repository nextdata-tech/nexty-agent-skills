#!/usr/bin/env python3
"""Scaffold a semantic-layer data product (.semantic_tools() pattern).

Writes placeholder models.py, transform.py, requirements.txt FLAT at the DP root
(NOT under a transform/ subdir), and prints the spec.py wiring block the DP needs.

The four governed MCP tools (list_models, semantic_model, describe_model,
run_semantic_query) are auto-generated at pod boot by the `.semantic_tools()`
spec flag. You do NOT author registry.py, tools.py, or provision.py — the kernel
compiles per-field `__nxd_semantic__` blobs on the promised models' attributes
into typed SemanticRegistry payloads, delivers them to
`<root>/.nxd/semantic/<model>.json` at startup, and the entrypoints module reads
them back to build the four tool closures.

The compiler, dialect, and tool factory are provided by the installed
nxd.data_product wheel (module nxd.experimental.semantic) — imported, not
vendored.

Usage:
    uv run python scaffold_semantic_dp.py <target_dir>

<target_dir> is the root of the data product directory (the directory that will
contain spec.py). All modules are created as flat siblings.

The stubs serve both authoring flows: transcribing a hand-provided schema AND
the inference flow (SKILL.md "Step 1-alt"), where the vocabulary is derived
from a profiled DuckDB sample table (nxd-mesh-analyzer's profile_tabular.py in
DuckDB mode) plus the user's questions. Either way, fill the placeholders with
the derived models/dimensions/metrics/joins.

THREE WIRING CONSTRAINTS
------------------------------------------------------------------------------
1. The SEMANTIC VOCABULARY lives as per-field `__nxd_semantic__` JSON blobs on
   each model's AttributeSpec, injected via the `_annotate()` stopgap (see
   models.py stub). The kernel compiles them; you never call a SemanticRegistry
   builder by hand.

   STOPGAP — the public author API is not yet available: AttributeSpec has no public
   `.semantic_annotation()` setter, so the blob is written directly to the
   private `_metadata` dict. Replace `_annotate()` with the public API once
   it ships. The injection is isolated to models.py and clearly marked.

2. PROMISE every annotated model on the storage port so its attributes land in
   the kernel-generated manifest (and thus in `.nxd/semantic/<model>.json` at
   boot). `.semantic_tools(service=...)` does the rest — it auto-wires the 4 RPC
   tool functions + an mcp-api port. Do NOT also call data_product_rpc_output()
   yourself; semantic_tools() raises ValidationError if an RPC output already exists.

3. A `.transform(...)` SEEDS the base tables the tools query (CREATE OR REPLACE
   TABLE + write_pandas). No semantic-view DDL is needed — `run_semantic_query`
   compiles governed SQL against the base tables directly from the kernel
   payloads. The transform also writes a one-row marker for the promised marker
   model so the storage port's produce-verification passes.

Reference (canonical, deployed):
    nxd: examples/features/semantic/deployable-dp/{spec,models,transform}.py
    here: evals/query-loop/mesh/<dp>/{spec,models,transform}.py
"""

from __future__ import annotations

import sys
from pathlib import Path


REQUIREMENTS_LINES = [
    "nxd.data_product[spec]",
    "nxd.drivers[rpc]",
    "snowflake-connector-python[pandas]",
    "pandas",
    # The .semantic_tools() manifest-fallback path (_manifest_compile) parses the
    # bundled models.yaml when the kernel does not deliver .nxd/semantic/*.json
    # (the split-pod k8s/rpc topology — the MCP server pod runs no kernel).
    "pyyaml>=6.0.2",
]

_MODELS_STUB = '''\
"""Semantic models with per-field __nxd_semantic__ annotations.

The kernel reads each promised model's `__nxd_semantic__` attribute blobs,
compiles them into a typed SemanticRegistry, and delivers the result to the DP
pod at boot as `<root>/.nxd/semantic/<model>.json`. At runtime the four MCP tools
(list_models, semantic_model, describe_model, run_semantic_query) are rebuilt
from those payloads — no registry.py / tools.py to author.

MISSING SEAM: AttributeSpec has no public setter for per-field metadata.
The blobs are injected here by writing the private `_metadata` dict directly via
`_annotate()`. This is a STOPGAP until a public
`AttributeSpec.semantic_annotation(blob)` API ships. Keep the injection isolated to
this module.

ROLE GRAMMAR (one blob per column):
  grain:     {"kind": "grain"}
  dimension: {"kind": "dimension", "name": ..., "description": ..., "type": ...,
              "pii": <bool, optional>}
  metric:    {"kind": "metric", "name": ..., "agg": "count|count_distinct|sum|avg|min|max",
              "description": ..., "boolean": <bool, optional>}
  join:      {"kind": "join", "to_model": ..., "to_column": ...,
              "cardinality": "many_to_one"}
  multi-role on one column: {"roles": [ {...}, {...} ]}
"""

import json

from nxd.spec import semantic_model
from nxd.spec._model import AttributeSpec
from nxd.spec.data_types import float64, int64, string

_SEMANTIC_KEY = "__nxd_semantic__"


def _annotate(attr: AttributeSpec, role: dict) -> AttributeSpec:
    """Inject a `__nxd_semantic__` blob into *attr*._metadata (stopgap).

    Mutates *attr* in place and returns it for chaining. Replace with the public
    `AttributeSpec.semantic_annotation()` once it ships.
    """
    attr._metadata[_SEMANTIC_KEY] = json.dumps(role, separators=(",", ":"))
    return attr


# ── <model_a> — one row per <grain_a> ────────────────────────────────────────
your_model = (
    semantic_model("<model_a>")
    .description("One row per <grain_a>.")
    .schema(
        {
            "<KEY_A>": _annotate(
                AttributeSpec(name="<KEY_A>", data_type=int64()),
                {"kind": "grain"},
            ),
            "<DIM_COL>": _annotate(
                AttributeSpec(
                    name="<DIM_COL>",
                    data_type=string(),
                    _description="<dimension description>.",
                ),
                {
                    "kind": "dimension",
                    "name": "<dim_name>",
                    "description": "<dimension description>.",
                    "type": "string",
                    # "pii": True,   # uncomment for governed PII dimensions
                },
            ),
            "<METRIC_COL>": _annotate(
                AttributeSpec(
                    name="<METRIC_COL>",
                    data_type=float64(),
                    _description="<metric description>.",
                ),
                {
                    "kind": "metric",
                    "name": "<metric_name>",
                    "agg": "sum",
                    "description": "<metric description>.",
                },
            ),
        }
    )
)

# Multi-role example: a column that is BOTH the grain AND a count metric, OR a
# join key AND a count_distinct metric. Patch the full roles list post-hoc — the
# bare {"kind": ...} shorthand has no inline multi-role form.
# _annotate(
#     your_model._attributes["<KEY_A>"],
#     {"roles": [
#         {"kind": "grain"},
#         {"kind": "metric", "name": "<entity>_count", "agg": "count",
#          "description": "Total number of <entity>."},
#     ]},
# )

# ── marker model — satisfies the storage port's produce-verification ──────────
# The kernel verifies at least one promised model is produced. This tiny table
# confirms the transform ran without promising the self-seeded query tables.
provision_marker = (
    semantic_model("<dp_name>_marker")
    .description("Marker table written by the seeding transform.")
    .schema({"MARKER_ID": int64(), "VIEW_NAME": string()})
)
'''

_TRANSFORM_STUB = '''\
"""Transform — seeds the base tables the semantic MCP tools query (self-seeded).

Two jobs, all in this DP's OWN Snowflake schema:
  1. Seed the base table(s) the tools read (CREATE OR REPLACE TABLE so re-runs
     are idempotent + write_pandas). Table names match the model names in
     models.py; create them UNQUOTED so Snowflake folds to upper-case (the
     compiler references the base tables unquoted too).
  2. Write a one-row marker into the promised marker model so the storage port's
     produce-verification passes.

NO semantic-view DDL. The auto-generated `run_semantic_query` compiles governed
SQL against the base tables directly, reading the kernel-delivered
`<root>/.nxd/semantic/<model>.json` payloads — no pre-provisioned view is required.

The param name (`snowflake`) MUST match the storage output port name; it is
injected as a typed Snowflake handle.
"""

from nxd.data_product.context import Snowflake


def transform(snowflake: Snowflake) -> None:
    import pandas as pd
    from snowflake import connector
    from snowflake.connector.pandas_tools import write_pandas

    if snowflake is None or not snowflake.schema:
        print("transform skipped — no Snowflake schema in context")
        return

    fqn = (
        f"{snowflake.database}.{snowflake.schema}."
        if snowflake.database
        else f"{snowflake.schema}."
    )

    # TODO: replace with your real seed data.
    rows = pd.DataFrame(
        [
            {"<KEY_A>": 1, "<DIM_COL>": "value-1", "<METRIC_COL>": 100.0},
            {"<KEY_A>": 2, "<DIM_COL>": "value-2", "<METRIC_COL>": 250.0},
        ]
    )

    conn = connector.connect(
        user=snowflake.user,
        account=snowflake.account,
        warehouse=snowflake.warehouse,
        role=snowflake.role,
        database=snowflake.database,
        schema=snowflake.schema,
        ocsp_fail_open=True,
        **snowflake.connector_params(),
    )
    try:
        cur = conn.cursor()
        try:
            # 1) Seed the base table(s) — name(s) match the model name(s).
            cur.execute(
                f"CREATE OR REPLACE TABLE {fqn}<model_a> "
                "(<KEY_A> NUMBER, <DIM_COL> VARCHAR, <METRIC_COL> FLOAT)"
            )
            write_pandas(
                conn, rows, "<MODEL_A>",
                database=snowflake.database, schema=snowflake.schema,
            )
            print(f"seeded {fqn}<model_a> rows={len(rows)}")

            # 2) Marker row (the promised marker model).
            managed = snowflake.full_table_name("<dp_name>_marker")
            cur.execute(f"TRUNCATE TABLE IF EXISTS {managed}")
            write_pandas(
                conn,
                pd.DataFrame([{"MARKER_ID": 1, "VIEW_NAME": "n/a"}]),
                managed.split(".")[-1].strip('"'),
                database=snowflake.database, schema=snowflake.schema,
            )
            print(f"marker written to {managed}")
        finally:
            cur.close()
    finally:
        conn.close()
'''

# The correct spec.py wiring block to print for the user.
SPEC_SNIPPET = """\
# ── spec.py — .semantic_tools() auto-wires the 4 MCP tools ───────────────────
from nxd.spec import code, data_product, data_product_output, storage
from transform import transform
from models import your_model, provision_marker

INFRA_PROFILE = "<infra-profile>"
SNOWFLAKE_SERVICE = "<snowflake-service>"
MCP_SERVICE = "mcp-api-service-k8s"

# Storage output port — PROMISE every annotated model so its attributes appear
# in the kernel-generated manifest models section (and thus in
# .nxd/semantic/<model>.json at boot). Plain storage(...), NO as_view: the
# transform self-seeds the base tables.
_storage = (
    data_product_output()
    .promise(provision_marker)
    .promise(your_model)
    .port("snowflake", storage(f"/infra-profile/{INFRA_PROFILE}#/services/{SNOWFLAKE_SERVICE}"))
)

spec = (
    data_product(
        name="<your-dp-name>",
        domain="<domain>",
        version="0.1.0",
        infra_profile=INFRA_PROFILE,
    )
    # Transform seeds the base tables + the marker row. No semantic-view DDL.
    .transform(
        code(transform).compute(f"/infra-profile/{INFRA_PROFILE}#/services/k8s-compute")
    )
    .output(_storage)
    # Auto-wire the 4 governed MCP tools (list_models, semantic_model,
    # describe_model, run_semantic_query) reading kernel-delivered payloads.
    # ONE line replaces the old build_semantic_tools + 4x rpc_function loop.
    .semantic_tools(service=MCP_SERVICE)
)
"""


def _write_stub(path: Path, content: str, label: str) -> None:
    if path.exists():
        print(f"  [skip] {path} already exists — not overwriting.")
        return
    path.write_text(content, encoding="utf-8")
    print(f"  [write] {path} ({label})")


def scaffold(target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    print(f"  [ok] DP root ready: {target_dir}")

    _write_stub(target_dir / "models.py", _MODELS_STUB,
                "models with __nxd_semantic__ annotations — adapt to your schema")
    _write_stub(target_dir / "transform.py", _TRANSFORM_STUB,
                "self-seeding transform stub — adapt to your rows")

    req = target_dir / "requirements.txt"
    if not req.exists():
        req.write_text("\n".join(REQUIREMENTS_LINES) + "\n", encoding="utf-8")
        print(f"  [write] {req} (dependencies)")
    else:
        print(f"  [skip] {req} already exists — add these lines if missing:")
        for line in REQUIREMENTS_LINES:
            print(f"            {line}")

    print()
    print("All modules are FLAT at the DP root (no transform/ subdir package).")
    print()
    print("spec.py wiring (.semantic_tools() — auto-generates all 4 MCP tools):")
    print()
    print(SPEC_SNIPPET)
    print(
        "See reference/scripts/templates/semantic_dp.py.tmpl for the complete "
        "models.py + transform.py + spec.py example.\n"
        "See SKILL.md for the authoritative recipe these stubs mirror."
    )


def main() -> int:
    if len(sys.argv) != 2:
        print(f"Usage: uv run python {sys.argv[0]} <target_dp_dir>", file=sys.stderr)
        return 1
    target = Path(sys.argv[1]).resolve()
    print(f"Scaffolding semantic-layer DP in: {target}")
    scaffold(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
