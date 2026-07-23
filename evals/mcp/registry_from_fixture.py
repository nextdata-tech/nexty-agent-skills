"""Build a genuine ``SemanticRegistry`` from a scenario's semantic fixture.

The agent-facing catalog (``fixtures/catalog.json``) is the *logical* surface —
what ``list_models`` / ``describe_model`` return. It deliberately omits physical
grain/column names so the agent reasons about concepts, not columns.

To actually *execute* ``run_semantic_query`` we need the physical mapping: which
table, which grain column, which physical column each metric/dimension binds to.
That lives in an authoritative ``fixtures/semantic.json`` (never shown to the
agent) which this module turns into:

  * a ``SemanticRegistry`` — fed to the genuine ``compile_selection``;
  * a ``pii_columns`` map ``{table: [physical pii cols]}`` — fed to the governed
    executor so PII masking rides along exactly as in production.

Keeping logical (catalog) and physical (semantic.json) split mirrors the real
product: the MCP catalog never leaks physical column names either.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
import warnings

from nxd.experimental.semantic import Agg, Cardinality, SemanticRegistry

_AGG = {
    "COUNT": Agg.COUNT,
    "COUNT_DISTINCT": Agg.COUNT_DISTINCT,
    "SUM": Agg.SUM,
    "AVG": Agg.AVG,
    "MIN": Agg.MIN,
    "MAX": Agg.MAX,
    "EXPRESSION": Agg.EXPRESSION,
}
_CARD = {
    "one_to_one": Cardinality.ONE_TO_ONE,
    "one_to_many": Cardinality.ONE_TO_MANY,
    "many_to_one": Cardinality.MANY_TO_ONE,
    "many_to_many": Cardinality.MANY_TO_MANY,
}


def load_semantic_fixture(fixture_dir: Path) -> dict[str, Any]:
    """Read the authoritative physical mapping fixture for a scenario."""
    path = fixture_dir / "semantic.json"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} missing — an MCP scenario must ship a semantic.json physical "
            "mapping alongside catalog.json (see evals/mcp/README.md)."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def build_registry(spec: dict[str, Any]):
    """Compile a ``SemanticRegistry`` from the physical-mapping fixture.

    ``spec`` shape (see fixtures/.../semantic.json):
        {
          "models": [{"name", "table", "grain", "description"?, "data_product"?}],
                    "dimensions": [{"name","model","column","type"?,"pii"?,"description"?}],
                    # A metric may be authored either as a physical `column` name or
                    # as a SQL expression string. Fixtures may use any of these keys
                    # to carry an expression-style metric: `expr`, `expression`, or
                    # `definition` (all fall back to the same value below). Example
                    # shapes accepted here:
                    #   {"name","model","agg","column"?,"boolean"?,"description"?}
                    #   {"name","model","agg","expr"?,"boolean"?,"description"?}
                    #   {"name","model","agg","expression"?,"boolean"?,"description"?}
                    #   {"name","model","agg","definition"?,"boolean"?,"description"?}
                    "metrics": [{"name","model","agg","column"?|"expr"|"expression"|"definition"? ,"boolean"?,"description"?}],
          "joins": [{"left","right","on":[[l,r],...],"cardinality"?}]
        }
    """
    reg = SemanticRegistry()
    for m in spec.get("models", []):
        # data_product is provenance metadata for the merged (cross-DP) registry —
        # it names the member DP a model was harvested from, mirroring how the mesh
        # gateway folds member semantic_models into one registry. It does NOT change
        # the compile decision (join topology does), so single-DP fixtures omit it.
        # We deliberately do NOT forward a physical ``table``: every base table in
        # this harness lives in ONE governed schema keyed by model name, so a bare
        # name is what binds to the masked view — a qualified DB.SCHEMA.TABLE would
        # miss it.
        reg.model(
            m["name"],
            grain=m["grain"],
            description=m.get("description", ""),
            data_product=m.get("data_product", ""),
        )
    for d in spec.get("dimensions", []):
        reg.dimension(
            d["name"],
            model=d["model"],
            column=d["column"],
            type=d.get("type", "string"),
            description=d.get("description", ""),
            pii=bool(d.get("pii", False)),
        )
    for me in spec.get("metrics", []):
        agg = _AGG[me["agg"].upper()]
        # Metric definition may be authored as a physical `column` or as a
        # SQL `expr`/`expression`/`definition` string. Prefer an explicit
        # column name, but fall back to expression keys so fixtures authored
        # with expression-style metrics still compile into the registry.
        col = (
            me.get("column")
            or me.get("expr")
            or me.get("expression")
            or me.get("definition")
            or "*"
        )
        # NOTE: when a metric is authored as an expression (e.g. agg ==
        # EXPRESSION or the fixture used `expr`/`expression`/`definition`),
        # we currently pass that SQL string into the `column=` parameter of
        # `SemanticRegistry.metric`. That works only if the live
        # `SemanticRegistry` implementation accepts a SQL fragment here (some
        # implementations interpolate the column into the aggregation), and
        # will break if the registry validates `column` as a physical column
        # name. This scenario is CI-skipped (requires a real nxd compiler),
        # so callers should verify it compiles live before relying on it.
        if agg == _AGG.get("EXPRESSION") or (
            me.get("expr") or me.get("expression") or me.get("definition")
        ):
            warnings.warn(
                "Metric uses expression fallback: passing SQL expression into 'column='; "
                "confirm live SemanticRegistry accepts expression strings (CI-skipped).",
                UserWarning,
            )

        reg.metric(
            me["name"],
            model=me["model"],
            agg=agg,
            column=col,
            description=me.get("description", ""),
            boolean=bool(me.get("boolean", False)),
        )
    for j in spec.get("joins", []):
        on = tuple((pair[0], pair[1]) for pair in j["on"])
        reg.join(
            left=j["left"],
            right=j["right"],
            on=on,
            cardinality=_CARD[j.get("cardinality", "many_to_one")],
        )
    return reg.build()


def physical_tables(spec: dict[str, Any]) -> dict[str, str]:
    """Map model name -> physical table name."""
    return {m["name"]: m["table"] for m in spec.get("models", [])}


def pii_columns(spec: dict[str, Any]) -> dict[str, list[str]]:
    """Map physical table -> list of physical PII columns (for governed masking).

    Column names are LOWERCASED: the governed executor derives base columns from
    INFORMATION_SCHEMA and lowercases them, then masks any whose name is in this
    set. semantic.json authors columns in uppercase (Snowflake convention), so we
    must lowercase here or the membership test never matches and PII leaks.
    """
    tables = physical_tables(spec)
    out: dict[str, list[str]] = {}
    for d in spec.get("dimensions", []):
        if d.get("pii"):
            table = tables[d["model"]]
            out.setdefault(table, []).append(d["column"].lower())
    return out
