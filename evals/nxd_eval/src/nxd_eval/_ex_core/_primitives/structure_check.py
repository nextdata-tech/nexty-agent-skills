"""Offline, zero-creds fan-out-safety check over compiled SQL.

This is the LEVEL-1 structural discriminator between the deterministic cross-DP
compiler and the LLM-merge baseline — it runs with NO Snowflake connection.

The invariant a fan-out-safe cross-DP plan must satisfy:

  Every MANY-side FACT table (e.g. ``assays``, ``dispenses``) appears ONLY
  inside a CTE that collapses it to one row per its export key — either a
  ``GROUP BY`` (a pre-aggregation CTE) or a ``SELECT DISTINCT`` (a key-bridge
  CTE). The OUTER query (after the ``WITH`` block) must never ``JOIN`` a bare
  fact table; it may ``FROM`` a fact only as the grouped spine anchor (the
  outer query then has its own ``GROUP BY``). If every fact is collapsed before
  any join, no join can double-count by construction — across DP boundaries
  too.

The deterministic compiler is ``FANOUT_SAFE`` by construction. The naive
LLM-merge joins an un-collapsed crosswalk (or a bare fact) and trips
``FANOUT_RISK``. That separation is provable here with zero creds — it does not
depend on executing anything.

The fact-table set is derived from a mesh when one is passed (any entity whose
relationships include a MANY_TO_ONE edge toward the spine and whose own grain is
a single surrogate key is a fact); callers may also pass an explicit set. The
default is the pharma mesh's two facts so the function is useful standalone.

This module intentionally re-implements the regex parse from ``check_cross_dp``
as a importable, mesh-aware function the harness and the standalone check both
use, so the fan-out-safety definition lives in ONE place.
"""

from __future__ import annotations

import re

# The pharma MANY-per-subject facts — the default fact set. These must never
# appear un-aggregated in an outer FROM/JOIN.
PHARMA_FACT_TABLES = frozenset({"assays", "dispenses"})

# The pharma crosswalk / bridge tables — entities with a COMPOSITE grain (more
# than one key column). Used as a bare outer-FROM spine they have many rows per
# fact-join key and re-fan any aggregate joined onto them (the per-bridge-
# dimension chasm). Default = the one pharma crosswalk.
PHARMA_BRIDGE_TABLES = frozenset({"site_subjects"})

# Per-fact grain key (table -> its single surrogate grain column). A bare fact
# spine is unique ONLY on this column; an aggregate JOINed onto it on any OTHER
# column is non-unique on the join key → re-fans (the fact-spine chasm). Used by
# clause #4(a') to tell a safe 1:1 grain-key join (x02) from the double-counting
# foreign-key join (x11). Default = the pharma facts.
PHARMA_FACT_GRAIN: dict[str, str] = {"assays": "assay_id", "dispenses": "dispense_id"}

# Pure DIMENSION tables (table -> single grain key column): single-grain entities
# that are neither a MANY-side fact nor a composite-grain bridge. A fact JOINed to
# such a table ON the dimension's grain key is grain-preserving (MANY_TO_ONE, one
# matching dim row per fact row), so it does NOT over-count even when the outer
# query rolls up — this is the breadth `complete=true` / top-N "metric sliced by a
# ONE-side dimension" shape. Default = the pharma single-grain dimension tables.
PHARMA_DIM_GRAIN: dict[str, str] = {
    "subjects": "subject_id",
    "sites": "site_id",
    "products": "product_id",
}


def fact_tables_from_mesh(mesh) -> frozenset[str]:
    """Derive the MANY-side fact tables from a mesh.

    A fact = an entity whose grain is a single surrogate key AND which has a
    MANY_TO_ONE relationship toward another entity (i.e. it fans out relative to
    that parent). Falls back to the empty set for a mesh with no such entities.
    """
    facts: set[str] = set()
    for e in mesh.entities:
        if len(e.grain) != 1:
            continue
        for r in e.relationships:
            card = getattr(r.cardinality, "value", str(r.cardinality))
            if card == "many_to_one":
                facts.add(e.table)
                break
    return frozenset(facts)


def bridge_tables_from_mesh(mesh) -> frozenset[str]:
    """Derive the crosswalk/bridge tables from a mesh: any entity whose grain is
    COMPOSITE (>1 key column). Such a table is non-unique on any single key, so
    used as a bare FROM spine it re-fans aggregates joined onto a subset of its
    grain."""
    return frozenset(e.table for e in mesh.entities if len(e.grain) > 1)


def fact_grain_from_mesh(mesh) -> dict[str, str]:
    """{fact table -> its single grain key column} for every single-grain fact.

    A bare fact spine is unique only on this column; an aggregate joined onto it
    on any other column re-fans. Mirrors ``fact_tables_from_mesh``'s fact rule."""
    out: dict[str, str] = {}
    for e in mesh.entities:
        if len(e.grain) != 1:
            continue
        for r in e.relationships:
            card = getattr(r.cardinality, "value", str(r.cardinality))
            if card == "many_to_one":
                out[e.table] = e.grain[0]
                break
    return out


def dim_grain_from_mesh(mesh) -> dict[str, str]:
    """{pure-dimension table -> its single grain key column}.

    A pure dimension = a single-grain entity that is neither a MANY-side fact
    (``fact_tables_from_mesh``) nor a composite-grain bridge
    (``bridge_tables_from_mesh``). A fact JOINed to such a table on this grain key
    is grain-preserving (one dim row per fact row → no fan-out), so the breadth
    `complete=true` / top-N "metric sliced by a ONE-side dimension" plan is safe."""
    facts = fact_tables_from_mesh(mesh)
    bridges = bridge_tables_from_mesh(mesh)
    out: dict[str, str] = {}
    for e in mesh.entities:
        if len(e.grain) != 1:
            continue
        if e.table in facts or e.table in bridges:
            continue
        out[e.table] = e.grain[0]
    return out


def fanout_safe(
    sql: str,
    fact_tables: frozenset[str] = PHARMA_FACT_TABLES,
    bridge_tables: frozenset[str] = PHARMA_BRIDGE_TABLES,
    fact_grain: dict[str, str] | None = None,
    dim_grain: dict[str, str] | None = None,
) -> tuple[bool, str]:
    """Return (is_safe, reason) for one compiled SQL string.

    A fact table may appear only inside a CTE whose body has a GROUP BY or is a
    SELECT DISTINCT. The outer query (after the CTE block) must not FROM/JOIN a
    bare fact table — except a fact used as the grouped spine anchor.
    """
    if fact_grain is None:
        fact_grain = PHARMA_FACT_GRAIN
    if dim_grain is None:
        dim_grain = PHARMA_DIM_GRAIN

    # Split the WITH block from the outer query at the top-level SELECT that
    # follows the closing paren of the last CTE.
    m = re.match(r"(?is)^\s*WITH\s+(.*?)\)\s*SELECT\s+(.*)$", sql)
    if not m:
        cte_block, outer = "", sql
    else:
        cte_block, outer = m.group(1) + ")", "SELECT " + m.group(2)

    # 1. every CTE that reads a fact table must collapse it (GROUP BY or DISTINCT).
    for fact in fact_tables:
        for cte_m in re.finditer(
            r"(?is)\bAS\s*\((SELECT\b.*?)\)(?=\s*,\s*\w+\s+AS\s*\(|\s*$)",
            cte_block,
        ):
            body = cte_m.group(1)
            if not re.search(rf"(?i)\bFROM\s+{re.escape(fact)}\b", body):
                continue
            collapses = re.search(r"(?i)\bGROUP\s+BY\b", body) or re.search(
                r"(?i)^\s*SELECT\s+DISTINCT\b", body
            )
            if not collapses:
                return False, f"fact {fact!r} read in a CTE with no GROUP BY/DISTINCT"

    # 2. the OUTER query may FROM a fact only as a grouped spine anchor; it must
    #    never JOIN a bare fact, and a spine-fact is safe only with a GROUP BY.
    #
    # AGGREGATION GATE: a bare-fact JOIN or bare-fact spine only OVER-COUNTS when
    # the outer query ROLLS JOINed rows UP (GROUP BY + aggregate). A non-aggregating
    # query — a SELECT DISTINCT row-listing with no SUM (e.g. the governance PII
    # case, x09) — cannot over-count: extra fan-out rows are a set-dedup concern,
    # not a measure inflation. So clause #2's returns are gated on `outer_rolls_up`,
    # exactly like clauses #3/#4 below. Without this gate a DISTINCT listing that
    # merely touches a fact would be wrongly flagged FANOUT_RISK.
    outer_has_group_by = bool(re.search(r"(?i)\bGROUP\s+BY\b", outer))
    # An outer query "rolls up" when it GROUP-BYs over MORE THAN ONE relation —
    # either an explicit JOIN or an ANSI-89 comma join (``FROM a, b WHERE ...``).
    # The comma form was previously invisible to this gate (it has no JOIN
    # keyword), so a comma-joined bare fact slipped through as FANOUT_SAFE.
    outer_has_join = bool(re.search(r"(?i)\bJOIN\b", outer))
    outer_comma_join = bool(re.search(r"(?i)\bFROM\b[^()]*?,", _from_clause(outer)))
    outer_rolls_up = outer_has_group_by and (outer_has_join or outer_comma_join)

    # GRAIN-PRESERVING EXEMPTION (the breadth `complete=true` / top-N shape):
    # a single fact sliced by a ONE-side dimension is a MANY_TO_ONE join — exactly
    # one dimension row per fact row, so SUM over the fact rolls up each fact row
    # ONCE. This is fan-out SAFE even though a bare fact is JOINed in the outer
    # query. The exemption is narrow: the outer query references EXACTLY ONE fact,
    # every OTHER outer relation is a pure single-grain dimension table, and the
    # fact↔dimension join predicate is on that dimension's grain key (so it cannot
    # multiply the fact). Anything wider (two facts, a bridge, a non-grain join
    # column) falls through to the RISK checks below unchanged.
    outer_rels = _outer_relations(outer)
    outer_facts = [t for t in outer_rels if t in fact_tables]
    other_rels = [t for t in outer_rels if t not in fact_tables]
    grain_preserving_fact_dim = (
        len(outer_facts) == 1
        and bool(other_rels)
        and all(t in dim_grain for t in other_rels)
        and all(
            _fact_dim_join_on_grain(outer, outer_facts[0], dt, dim_grain[dt])
            for dt in other_rels
        )
    )

    if outer_rolls_up and not grain_preserving_fact_dim:
        for fact in fact_tables:
            if re.search(rf"(?i)\bJOIN\s+{re.escape(fact)}\b", outer):
                return False, f"fact {fact!r} JOINed un-aggregated in the outer query"
            # comma / ANSI-89 join: a known fact in a multi-relation comma FROM is
            # an un-collapsed fact too (the JOIN-keyword regex above misses it).
            if fact in _comma_relations(outer):
                return (
                    False,
                    f"fact {fact!r} comma-joined un-aggregated in the outer query",
                )
            if (
                re.search(rf"(?i)\bFROM\s+{re.escape(fact)}\b", outer)
                and not outer_has_group_by
            ):
                return (
                    False,
                    f"fact {fact!r} is the spine but the outer query has no GROUP BY",
                )

    # 2b. UN-MODELLED FACT (the fact set derived from the SQL itself). A relation
    #     that is (a) JOINed or comma-joined into a rolled-up outer query, (b) NOT
    #     a declared dimension/spine table, (c) NOT a CTE, and (d) has a column
    #     wrapped in an aggregate in the SELECT, behaves like a fact even if it
    #     isn't in `fact_tables`. A bare such relation joined before the roll-up
    #     can double-count exactly like a modelled fact — so flag it. This closes
    #     the blind spot where an un-modelled table (e.g. ``prescriptions``) joined
    #     naively was wrongly FANOUT_SAFE. Skipped under the grain-preserving
    #     fact↔dim exemption (a single fact sliced by a ONE-side dim is safe).
    if outer_rolls_up and not grain_preserving_fact_dim:
        known = (
            fact_tables | set(dim_grain) | bridge_tables | set(_cte_names(cte_block))
        )
        for rel, alias in _outer_relation_aliases(outer):
            if rel in known:
                continue
            if _alias_aggregated(outer, alias):
                return (
                    False,
                    f"un-modelled aggregated relation {rel!r} joined un-collapsed in "
                    "the outer query → behaves like a fact and can double-count",
                )

    # 3. NON-KEY-GRAIN BRIDGE FAN-OUT (the cross-DP chasm the LLM-merge trips).
    #    A SELECT-DISTINCT bridge CTE is only fan-out-safe if it is unique on the
    #    columns it is JOINed on. If the crosswalk is DISTINCT on a SUPERSET of
    #    the join key (e.g. DISTINCT (site_id, subject_id) but JOINed only on
    #    subject_id), it has many rows per join key and re-fans every aggregate
    #    CTE joined through it — exactly the naive-merge bug. The deterministic
    #    compiler collapses the crosswalk to the join key (DISTINCT subject_id),
    #    so its bridge projects exactly the key it joins on → safe.
    # AGGREGATION GATE (`outer_rolls_up`, computed above for clause #2): a
    # non-unique bridge/spine only OVER-COUNTS when the outer query rolls JOINed
    # aggregates UP (GROUP BY). A plain row-listing (no GROUP BY, e.g. the
    # governance PII case) that fans out duplicate rows is a set-dedup concern,
    # not a SUM over-count — not a fan-out RISK here.
    cte_cols = _distinct_cte_projections(cte_block)
    if outer_rolls_up:
        for cte_name, proj_cols in cte_cols.items():
            join_keys = _outer_join_keys(outer, cte_name)
            if join_keys is None:
                continue  # this DISTINCT CTE is not outer-joined (e.g. the spine)
            extra = proj_cols - join_keys
            if extra:
                return (
                    False,
                    f"DISTINCT bridge {cte_name!r} projects {sorted(extra)} beyond its "
                    f"join key {sorted(join_keys)} → fans out aggregates joined through it",
                )

    # 4. SPINE FAN-OUT (the per-bridge-dimension chasm — clause #3's mirror image).
    #    When the OUTER FROM spine is a CROSSWALK that is non-unique on the keys it
    #    joins facts on, it re-fans every aggregate joined onto it. Two shapes are
    #    unsafe (both only matter under the aggregation gate above):
    #      (a) FROM <bare crosswalk table>  — a raw multi-row-per-key table.
    #      (b) FROM <DISTINCT CTE> projecting an identity col beyond its fact-join
    #          keys (e.g. DISTINCT (site_id, subject_id, region) JOINed only on
    #          subject_id → many spine rows per subject_id → over-count).
    #    A safe spine is 1-row-per-join-key: a single-key dimension table, or a
    #    DISTINCT CTE whose projection == (fact-join keys + grouping dim).
    spine_tbl = _outer_from_relation(outer)
    if outer_rolls_up and spine_tbl is not None:
        # (a) BARE crosswalk table as the grouped spine. A composite-grain
        #     crosswalk is non-unique on any single key, so each aggregate JOINed
        #     onto it is re-fanned by its per-key multiplicity. The safe plan
        #     collapses it to a DISTINCT (join_key, grouping_dim) CTE first.
        if spine_tbl in bridge_tables:
            return (
                False,
                f"bare crosswalk {spine_tbl!r} used as the grouped spine with "
                f"aggregate JOINs → its per-key multiplicity re-fans those "
                f"aggregates (collapse it to a DISTINCT key+dim CTE first)",
            )
        # (a') BARE single-grain FACT table as the grouped spine. A fact is one row
        #     per its surrogate grain but MANY rows per any foreign key it carries
        #     (e.g. dispenses is 1/dispense_id but N/subject_id), so an aggregate
        #     CTE JOINed onto it on a FOREIGN key (not the fact's own grain key) is
        #     summed once per fact row → the silent cross-DP double-count
        #     (titer_sum per channel: spine dispenses, agg_assays joined on
        #     subject_id). A join on the fact's OWN grain key (x02: agg_dispenses
        #     joined on dispense_id) is 1:1 and SAFE — that's why we compare the
        #     spine-side join column against the fact's grain key. The safe cross-DP
        #     plan DISTINCT-collapses the fact spine to (join_key, grouping_dim)
        #     first (the compiler's step-5b spine CTE).
        if spine_tbl in fact_tables and re.search(r"(?i)\bJOIN\b", outer):
            grain_key = fact_grain.get(spine_tbl)
            spine_join_cols = set(
                re.findall(rf"(?i)\b{re.escape(spine_tbl)}\.(\w+)\b", outer)
            )
            grp_cols = set(
                re.findall(
                    rf"(?i)\b{re.escape(spine_tbl)}\.(\w+)\b",
                    _outer_group_by(outer),
                )
            )
            # columns the aggregates actually join the spine ON (exclude the
            # grouping-dim columns the spine also renders).
            foreign_join_cols = spine_join_cols - grp_cols
            if grain_key is None or any(c != grain_key for c in foreign_join_cols):
                return (
                    False,
                    f"bare fact {spine_tbl!r} used as the grouped spine with an "
                    f"aggregate JOINed on {sorted(foreign_join_cols)} (not its grain "
                    f"key {grain_key!r}) → non-unique spine sums each aggregate once "
                    f"per fact row (collapse it to a DISTINCT join_key+dim CTE first)",
                )
        # (b) DISTINCT bridge CTE as the spine, projecting an IDENTITY column
        #     beyond the keys the aggregates join on. e.g. ``p_site_subjects``
        #     DISTINCT on (site_id, subject_id, region) but facts JOINed only on
        #     subject_id → still many spine rows per subject_id → over-count. The
        #     hazard column is a projected col that is NOT a fact-join key and NOT
        #     the grouping dim. The safe spine projects only (join_key, dim).
        if spine_tbl in cte_cols:
            join_cols = set(
                re.findall(rf"(?i)\b{re.escape(spine_tbl)}\.(\w+)\b", outer)
            )
            grp_cols = set(
                re.findall(
                    rf"(?i)\b{re.escape(spine_tbl)}\.(\w+)\b", _outer_group_by(outer)
                )
            )
            hazard = cte_cols[spine_tbl] - join_cols - grp_cols
            if hazard:
                return (
                    False,
                    f"DISTINCT spine {spine_tbl!r} projects identity col(s) "
                    f"{sorted(hazard)} beyond its fact-join keys {sorted(join_cols - grp_cols)} "
                    f"and grouping cols {sorted(grp_cols)} → non-unique spine re-fans "
                    f"the aggregates joined onto it",
                )

    return True, "every fact pre-aggregated (GROUP BY / DISTINCT) before any join"


def _outer_group_by(outer: str) -> str:
    m = re.search(r"(?is)\bGROUP\s+BY\b(.*?)(?=\bORDER\b|\bLIMIT\b|$)", outer)
    return m.group(1) if m else ""


def _outer_from_relation(outer: str) -> str | None:
    """The relation name in the outer query's FROM clause (the spine), or None."""
    m = re.search(r"(?i)\bFROM\s+(\w+)", outer)
    return m.group(1) if m else None


def _outer_relations(outer: str) -> list[str]:
    """Every base relation named after a FROM/JOIN in the outer query (the table
    token, ignoring any trailing alias). Used by the grain-preserving fact↔dim
    exemption to enumerate the outer tables."""
    return re.findall(r"(?i)\b(?:FROM|JOIN)\s+(\w+)", outer)


def _from_clause(outer: str) -> str:
    """The FROM..(end of joins) span of the outer query, up to WHERE/GROUP/ORDER/
    LIMIT. Used to detect ANSI-89 comma joins without tripping over commas in the
    SELECT list."""
    m = re.search(
        r"(?is)\bFROM\b(.*?)(?=\bWHERE\b|\bGROUP\b|\bORDER\b|\bLIMIT\b|$)", outer
    )
    return "FROM " + (m.group(1) if m else "")


def _comma_relations(outer: str) -> set[str]:
    """Base table names in an ANSI-89 comma FROM list (``FROM a x, b y, ...``).

    Returns the set of TABLE tokens (alias stripped) that appear as comma-separated
    relations in the FROM clause — the relations the explicit-JOIN regex misses."""
    from_clause = _from_clause(outer)
    # drop the leading "FROM " and any trailing explicit JOIN (only the comma list
    # before the first JOIN keyword is the ANSI-89 part).
    body = re.split(r"(?i)\bJOIN\b", from_clause[5:], maxsplit=1)[0]
    rels: set[str] = set()
    for seg in body.split(","):
        tok = seg.strip().split()
        if tok:
            rels.add(tok[0])
    # the first segment includes the spine; keep only comma-introduced relations
    # plus the spine (all are un-joined relations in a comma cross-product).
    return {r for r in rels if r}


def _cte_names(cte_block: str) -> list[str]:
    """Names of every CTE defined in the WITH block."""
    return re.findall(r"(?is)\b(\w+)\s+AS\s*\(", cte_block)


def _outer_relation_aliases(outer: str) -> list[tuple[str, str]]:
    """(table, alias) for every relation in the outer FROM/JOIN, including the
    ANSI-89 comma relations. Alias falls back to the table name when unaliased."""
    out: list[tuple[str, str]] = []
    # explicit FROM/JOIN <table> [AS] <alias>
    for m in re.finditer(r"(?i)\b(?:FROM|JOIN)\s+(\w+)(?:\s+(?:AS\s+)?(\w+))?", outer):
        tbl = m.group(1)
        alias = m.group(2)
        if alias and alias.upper() in (
            "ON",
            "WHERE",
            "GROUP",
            "ORDER",
            "LIMIT",
            "LEFT",
            "JOIN",
            "INNER",
        ):
            alias = None
        out.append((tbl, alias or tbl))
    # ANSI-89 comma relations: ``FROM a x, b y`` — parse the comma list for the
    # (table, alias) pairs after the first comma.
    from_body = _from_clause(outer)[5:]
    from_body = re.split(r"(?i)\bJOIN\b", from_body, maxsplit=1)[0]
    segs = from_body.split(",")
    for seg in segs[1:]:
        tok = seg.strip().split()
        if not tok:
            continue
        tbl = tok[0]
        alias = tok[1] if len(tok) > 1 else tbl
        out.append((tbl, alias))
    return out


def _alias_aggregated(outer: str, alias: str) -> bool:
    """True iff ``<alias>.<col>`` appears inside an aggregate call (SUM/COUNT/AVG/
    MIN/MAX) in the outer SELECT list — i.e. the relation contributes a rolled-up
    measure (so an un-collapsed bare instance of it can double-count)."""
    select_list = re.split(r"(?is)\bFROM\b", outer, maxsplit=1)[0]
    return bool(
        re.search(
            rf"(?i)\b(?:SUM|COUNT|AVG|MIN|MAX)\s*\(\s*(?:DISTINCT\s+)?{re.escape(alias)}\.",
            select_list,
        )
    )


def _fact_dim_join_on_grain(
    outer: str, fact: str, dim: str, dim_grain_key: str
) -> bool:
    """True iff the outer query's join between ``fact`` and ``dim`` is on the
    dimension's grain key (e.g. ``... ON l.product_id = r.product_id`` where
    ``product_id`` is products' grain). A MANY_TO_ONE join on the ONE-side grain
    key matches exactly one dimension row per fact row, so it cannot multiply the
    fact. Resolves the fact/dim table aliases, then checks an equality predicate
    that references the grain key on the dimension side.

    The grain key is matched by COLUMN NAME on the dimension-side alias; the
    pharma joins use the same physical column name on both sides
    (``l.product_id = r.product_id``), so a predicate that mentions
    ``<dim_alias>.<grain_key>`` (or the bare grain key) in an ``ON`` clause is the
    grain-key join. A foreign-key join on a NON-grain column (the fact-spine chasm)
    has the grain key absent from the predicate and returns False."""
    fact_alias = _relation_alias(outer, fact)
    dim_alias = _relation_alias(outer, dim)
    # collect the ON-predicate text for joins in the outer query
    on_text = " ".join(
        re.findall(
            r"(?is)\bON\b(.*?)(?=\bJOIN\b|\bWHERE\b|\bGROUP\b|\bORDER\b|\bLIMIT\b|$)",
            outer,
        )
    )
    if not on_text:
        return False
    # the grain key must appear on the dimension side of an equality predicate.
    dim_ref = rf"(?i)\b{re.escape(dim_alias)}\.{re.escape(dim_grain_key)}\b"
    if not re.search(dim_ref, on_text):
        return False
    # and the fact side of that predicate must reference the SAME grain key column
    # (pharma joins share the physical column name across the FK edge).
    fact_ref = rf"(?i)\b{re.escape(fact_alias)}\.{re.escape(dim_grain_key)}\b"
    return bool(re.search(fact_ref, on_text))


def _relation_alias(outer: str, table: str) -> str:
    """The alias bound to ``table`` in the outer FROM/JOIN (e.g. ``l`` for
    ``dispenses l``); falls back to the table name itself when unaliased."""
    m = re.search(rf"(?i)\b(?:FROM|JOIN)\s+{re.escape(table)}\s+(?:AS\s+)?(\w+)", outer)
    if m and m.group(1).upper() not in (
        "ON",
        "JOIN",
        "LEFT",
        "WHERE",
        "GROUP",
        "ORDER",
        "LIMIT",
    ):
        return m.group(1)
    return table


def _distinct_cte_projections(cte_block: str) -> dict[str, set[str]]:
    """Map each ``SELECT DISTINCT`` CTE name -> the set of its projected output
    column names (the trailing ``AS <name>`` of each select item)."""
    out: dict[str, set[str]] = {}
    for m in re.finditer(
        r"(?is)\b(\w+)\s+AS\s*\(\s*(SELECT\s+DISTINCT\b.*?)\)"
        r"(?=\s*,\s*\w+\s+AS\s*\(|\s*$)",
        cte_block,
    ):
        name, body = m.group(1), m.group(2)
        # strip the FROM-onward tail so we only parse the projection list
        proj = re.split(r"(?i)\bFROM\b", body, maxsplit=1)[0]
        cols = set(re.findall(r"(?i)\bAS\s+(\w+)", proj))
        if not cols:
            # no explicit aliases: take the bare trailing identifiers
            cols = {
                seg.strip().split(".")[-1]
                for seg in proj.replace("SELECT", "", 1)
                .replace("DISTINCT", "", 1)
                .split(",")
                if seg.strip()
            }
        out[name] = cols
    return out


def _outer_join_keys(outer: str, cte_name: str) -> set[str] | None:
    """The set of <cte_name>.<col> columns referenced in the outer query's JOIN
    ON predicates for ``cte_name``. Returns None if the CTE is not JOINed in the
    outer query (it may be the FROM spine, which is not a fan-out hazard)."""
    if not re.search(rf"(?i)\bJOIN\s+{re.escape(cte_name)}\b", outer):
        return None
    keys = set(re.findall(rf"(?i)\b{re.escape(cte_name)}\.(\w+)", outer))
    return keys


def verdict(
    sql: str | None,
    fact_tables: frozenset[str] = PHARMA_FACT_TABLES,
    bridge_tables: frozenset[str] = PHARMA_BRIDGE_TABLES,
    fact_grain: dict[str, str] | None = None,
    dim_grain: dict[str, str] | None = None,
) -> str:
    """FANOUT_SAFE / FANOUT_RISK / N/A — the report-facing label."""
    if not sql:
        return "N/A"
    safe, _ = fanout_safe(sql, fact_tables, bridge_tables, fact_grain, dim_grain)
    return "FANOUT_SAFE" if safe else "FANOUT_RISK"
