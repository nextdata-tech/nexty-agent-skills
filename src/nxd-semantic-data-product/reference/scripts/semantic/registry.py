"""Semantic registry builder for the NXD semantic-layer stopgap (NEX-620).

This module is a **stopgap** until ADR-026 lands first-class measure/dimension
support in the NXD spec and kernel. Public names are intentionally aligned with
ADR-026 so the migration is mechanical (Agg, Cardinality, Dimension, Metric,
Model, Join map directly to the proposed spec DSL).

See: docs/architecture/adrs/026-semantic-layer-first-class.md
Convergence target: nxd.spec.measure / nxd.spec.dimension (ADR-026 first-class
support).
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from enum import Enum
from typing import Any


class Agg(str, Enum):
    """Closed aggregation vocabulary — mirrors ADR-026 § Spec DSL."""

    COUNT = "count"
    COUNT_DISTINCT = "count_distinct"
    SUM = "sum"
    AVG = "avg"
    MIN = "min"
    MAX = "max"


class Cardinality(str, Enum):
    """Join cardinality. MANY_TO_ONE is the N:1 case that makes cross-model
    dimension slicing safe (the MANY side metric grain is preserved through the
    join). ADR-026 § manifest schema."""

    ONE_TO_ONE = "one_to_one"
    ONE_TO_MANY = "one_to_many"
    MANY_TO_ONE = "many_to_one"
    MANY_TO_MANY = "many_to_many"


@dataclass(frozen=True)
class Dimension:
    """A column that an agent can group or filter by.

    ``pii=True`` marks governance targets — the query layer may mask or reject
    them depending on the caller's access level.
    """

    name: str
    model: str
    column: str
    type: str = "string"
    description: str = ""
    pii: bool = False


@dataclass(frozen=True)
class Metric:
    """A named, aggregated measure.

    ``boolean=True`` treats the column as a flag (SUM of true rows via a CASE
    expression robust to BOOLEAN/VARCHAR physical types).

    ``extra_dimensions`` is an explicit override of the auto-derived cross-model
    dimension set. Leave empty (default) to let :py:meth:`SemanticRegistry.build`
    derive it from N:1 joins. Pass an explicit tuple to override the derivation
    for a specific metric.
    """

    name: str
    model: str
    agg: Agg
    column: str = "*"
    description: str = ""
    boolean: bool = False
    extra_dimensions: tuple[str, ...] = ()


@dataclass(frozen=True)
class Model:
    """A physical table / semantic-model entity.

    ``grain`` is the column (or comma-separated columns) that uniquely identifies
    one row — the entity key. Required.
    """

    name: str
    grain: str
    description: str = ""


@dataclass(frozen=True)
class Join:
    """A documented join between two models.

    ``on`` is a tuple of ``(left_col, right_col)`` pairs (the join predicate).
    ``cardinality`` defaults to MANY_TO_ONE — the safe case that preserves the
    MANY side's grain when joining.
    """

    left: str
    right: str
    on: tuple[tuple[str, str], ...]
    cardinality: Cardinality = Cardinality.MANY_TO_ONE


# ---------------------------------------------------------------------------
# Compiled (frozen) registry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CompiledRegistry:
    """Immutable snapshot produced by :py:meth:`SemanticRegistry.build`.

    All collection attributes are plain tuples; lookup helpers delegate to them.
    """

    metrics: tuple[Metric, ...]
    dimensions: tuple[Dimension, ...]
    models: tuple[Model, ...]
    joins: tuple[Join, ...]

    # Derived per-metric cross-model dimension sets (populated by build()).
    # Maps metric name -> frozenset of dimension names reachable via N:1 joins.
    _extra_dim_sets: dict[str, frozenset[str]] = field(
        default_factory=lambda: dict[str, frozenset[str]](), compare=False, hash=False
    )

    def find_metric(self, name: str) -> Metric | None:
        return next((m for m in self.metrics if m.name == name), None)

    def find_dimension(self, name: str) -> Dimension | None:
        return next((d for d in self.dimensions if d.name == name), None)

    def model_of(self, name: str) -> Model | None:
        """Look up a Model by name."""
        return next((m for m in self.models if m.name == name), None)

    def compatible_dimensions(self, metric: Metric) -> tuple[Dimension, ...]:
        """Dimensions a metric can legally be sliced by.

        Includes all dimensions on the metric's own model plus any that are
        reachable via an N:1 join (auto-derived unless the metric carries an
        explicit ``extra_dimensions`` override). PII dimensions are included —
        the query layer decides whether to permit them.
        """
        own = tuple(d for d in self.dimensions if d.model == metric.model)

        # Use explicit extra_dimensions override when set, else auto-derived set.
        if metric.extra_dimensions:
            extra_names: frozenset[str] = frozenset(metric.extra_dimensions)
        else:
            extra_names = self._extra_dim_sets.get(metric.name, frozenset())

        extra = tuple(d for d in self.dimensions if d.name in extra_names)

        seen: set[str] = set()
        out: list[Dimension] = []
        for d in own + extra:
            if d.name not in seen:
                seen.add(d.name)
                out.append(d)
        return tuple(out)

    def pii_dimensions(self) -> tuple[Dimension, ...]:
        return tuple(d for d in self.dimensions if d.pii)

    def column_description(self, model: str, column: str, fallback: str = "") -> str:
        """Description for a physical column.

        In the generic registry, descriptions live directly on the Dimension
        dataclass (no external model reflection needed). Falls back to ``fallback``
        when no matching dimension is found.
        """
        for d in self.dimensions:
            if d.model == model and d.column.upper() == column.upper():
                return d.description or fallback
        return fallback

    def metric_description(self, metric: Metric) -> str:
        """Human description for a metric.

        For COUNT / COUNT_DISTINCT the aggregated column is an id/key whose doc
        describes the column identity, not the count — keep the curated metric
        description. For SUM/AVG/MIN/MAX the aggregated column *is* the measured
        quantity, so reuse the column's curated description. Mirrors PoC
        ``semantics.metric_description`` (NEX-620).
        """
        if metric.agg in (Agg.COUNT, Agg.COUNT_DISTINCT) or metric.column == "*":
            return metric.description
        return self.column_description(metric.model, metric.column, metric.description)


# ---------------------------------------------------------------------------
# Fluent builder
# ---------------------------------------------------------------------------


class SemanticRegistry:
    """Fluent builder for a :py:class:`CompiledRegistry`.

    Usage::

        registry = (
            SemanticRegistry()
            .model("sales_fact", grain="order_id", description="One row per order.")
            .model("product_dim", grain="product_id")
            .dimension("category", model="product_dim", column="CATEGORY")
            .metric("order_count", model="sales_fact", agg=Agg.COUNT_DISTINCT,
                    column="order_id", description="Distinct orders.")
            .join(left="sales_fact", right="product_dim",
                  on=(("product_id", "product_id"),),
                  cardinality=Cardinality.MANY_TO_ONE)
            .build()
        )

    ``build()`` auto-derives cross-model dimension reachability from N:1 joins:
    for every metric on the MANY side of a MANY_TO_ONE join, the ONE side's
    dimensions become reachable — unless the metric declares an explicit
    ``extra_dimensions`` tuple.
    """

    def __init__(self) -> None:
        self._models: list[Model] = []
        self._dimensions: list[Dimension] = []
        self._metrics: list[Metric] = []
        self._joins: list[Join] = []

    # -- builder methods -------------------------------------------------------

    def model(self, name: str, *, grain: str, description: str = "") -> SemanticRegistry:
        """Register a physical table / semantic-model entity.

        Parameters
        ----------
        name:
            Unique model name (must match the table name in the warehouse).
        grain:
            Column (or comma-separated columns) that uniquely identifies one row
            — the entity key.  Required; ``build()`` rejects an empty grain.
        description:
            Optional human-readable description surfaced in tool catalogs.
        """
        self._models.append(Model(name=name, grain=grain, description=description))
        return self

    def dimension(
        self,
        name: str,
        *,
        model: str,
        column: str,
        type: str = "string",
        description: str = "",
        pii: bool = False,
    ) -> SemanticRegistry:
        """Register a slicing / filtering axis on *model*.

        Parameters
        ----------
        name:
            Unique concept name used in ``compile_selection`` / MCP tool args.
        model:
            Name of the owning model (must be declared before ``build()``).
        column:
            Physical column name in the warehouse table.
        type:
            Logical type hint (e.g. ``"string"``, ``"boolean"``, ``"date"``).
            Informational only — not validated against the warehouse schema.
        description:
            Plain-language meaning surfaced in ``list_dimensions``.
        pii:
            When ``True`` this dimension is a governance target.  PII dimensions
            are included in ``compatible_dimensions()`` but the query layer may
            mask or reject queries that select them depending on the caller's
            access level.  PII dimensions are excluded from the
            auto-derived cross-model dimension reachability sets.
        """
        self._dimensions.append(
            Dimension(
                name=name,
                model=model,
                column=column,
                type=type,
                description=description,
                pii=pii,
            )
        )
        return self

    def metric(
        self,
        name: str,
        *,
        model: str,
        agg: Agg,
        column: str = "*",
        description: str = "",
        boolean: bool = False,
        extra_dimensions: tuple[str, ...] = (),
    ) -> SemanticRegistry:
        """Register a named, aggregated measure on *model*.

        Parameters
        ----------
        name:
            Unique concept name used in ``compile_selection`` / MCP tool args.
        model:
            Name of the owning model (must be declared before ``build()``).
        agg:
            Aggregation function.  ``Agg.COUNT`` with ``column="*"`` renders
            ``COUNT(*)``; all other aggregations (SUM, AVG, MIN, MAX) require a
            real column name — ``build()`` rejects ``column="*"`` for those aggs.
        column:
            Physical column to aggregate.  Defaults to ``"*"`` which is only
            valid for ``COUNT`` (and accepted silently for ``COUNT_DISTINCT``
            where the column is required).
        description:
            Plain-language meaning surfaced in ``list_metrics``.
        boolean:
            When ``True`` SUM uses a CASE expression robust to
            BOOLEAN/VARCHAR physical types (counts rows where the column is
            truthy).
        extra_dimensions:
            Explicit override of the auto-derived cross-model dimension set.
            Leave empty (default) to let :py:meth:`build` derive it from N:1
            joins.  Pass an explicit tuple to pin the reachable dimension set
            for this metric regardless of join topology.
        """
        self._metrics.append(
            Metric(
                name=name,
                model=model,
                agg=agg,
                column=column,
                description=description,
                boolean=boolean,
                extra_dimensions=extra_dimensions,
            )
        )
        return self

    def measure(
        self,
        name: str,
        *,
        model: str,
        agg: Agg,
        column: str = "*",
        description: str = "",
        boolean: bool = False,
        extra_dimensions: tuple[str, ...] = (),
    ) -> SemanticRegistry:
        """Alias for :py:meth:`metric` using the ADR-026-convergent verb name.

        ADR-026's spec DSL uses ``measure(name, agg, column, ...)``; this alias
        makes code written against the ADR-026 vocabulary work without changes.
        ``.metric()`` is kept for backwards compatibility.
        """
        return self.metric(
            name,
            model=model,
            agg=agg,
            column=column,
            description=description,
            boolean=boolean,
            extra_dimensions=extra_dimensions,
        )

    def join(
        self,
        *,
        left: str,
        right: str,
        on: tuple[tuple[str, str], ...],
        cardinality: Cardinality = Cardinality.MANY_TO_ONE,
    ) -> SemanticRegistry:
        """Register a join between two models.

        Parameters
        ----------
        left:
            Name of the left-hand (typically MANY-side) model.
        right:
            Name of the right-hand (typically ONE-side) model.
        on:
            Tuple of ``(left_col, right_col)`` pairs — the equi-join predicate.
        cardinality:
            Join cardinality.  ``MANY_TO_ONE`` (default) is the safe case that
            preserves the MANY side's grain and unlocks cross-model dimension
            slicing.  ``MANY_TO_MANY`` joins are recorded but not used by the
            compiler's dimension-reachability logic.
        """
        self._joins.append(Join(left=left, right=right, on=on, cardinality=cardinality))
        return self

    # -- declarative constructor -----------------------------------------------

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SemanticRegistry:
        """Construct a registry from a declarative dict.

        Expected shape::

            {
                "models": [{"name": ..., "grain": ..., "description": ...}, ...],
                "dimensions": [{"name": ..., "model": ..., "column": ...,
                                "type": ..., "description": ..., "pii": ...}, ...],
                "metrics": [{"name": ..., "model": ..., "agg": ...,
                             "column": ..., "description": ...,
                             "boolean": ...,
                             "extra_dimensions": [...]}, ...],
                "joins": [{"left": ..., "right": ...,
                           "on": [[lc, rc], ...], "cardinality": ...}, ...],
            }
        """
        builder = cls()
        for m in data.get("models", []):
            builder.model(m["name"], grain=m["grain"], description=m.get("description", ""))
        for d in data.get("dimensions", []):
            builder.dimension(
                d["name"],
                model=d["model"],
                column=d["column"],
                type=d.get("type", "string"),
                description=d.get("description", ""),
                pii=bool(d.get("pii", False)),
            )
        for mt in data.get("metrics", []):
            agg = Agg(mt["agg"]) if isinstance(mt["agg"], str) else mt["agg"]
            extra = tuple(mt.get("extra_dimensions") or ())
            builder.metric(
                mt["name"],
                model=mt["model"],
                agg=agg,
                column=mt.get("column", "*"),
                description=mt.get("description", ""),
                boolean=bool(mt.get("boolean", False)),
                extra_dimensions=extra,
            )
        for j in data.get("joins", []):
            card = (
                Cardinality(j["cardinality"])
                if isinstance(j.get("cardinality"), str)
                else j.get("cardinality", Cardinality.MANY_TO_ONE)
            )
            on = tuple(tuple(pair) for pair in j["on"])
            builder.join(left=j["left"], right=j["right"], on=on, cardinality=card)
        return builder

    # -- build -----------------------------------------------------------------

    def build(self) -> CompiledRegistry:
        """Validate and freeze the registry into a :py:class:`CompiledRegistry`.

        Validation
        ----------
        - Every metric.model and dimension.model must be a declared model.
        - Every join endpoint (left, right) must be a declared model.
        - No duplicate metric, dimension, or model names.
        - Every model must have a non-empty grain.

        Auto-derivation of extra_dimensions
        ------------------------------------
        For each metric whose ``extra_dimensions`` tuple is empty (the default),
        :py:meth:`build` inspects all MANY_TO_ONE joins where the metric's model
        is on the MANY (left) side. The ONE (right) side's non-PII dimensions are
        added to that metric's reachable set in the compiled registry.

        A metric with an explicit ``extra_dimensions`` override bypasses the
        auto-derivation entirely — the override wins verbatim.
        """
        model_names = {m.name for m in self._models}

        # ---- duplicate checks ------------------------------------------------
        for collection, label in (
            (self._models, "model"),
            (self._metrics, "metric"),
            (self._dimensions, "dimension"),
        ):
            seen: set[str] = set()
            for item in collection:
                if item.name in seen:
                    raise ValueError(
                        f"Duplicate {label} name {item.name!r}. Every {label} must "
                        "have a unique name within the registry."
                    )
                seen.add(item.name)

        # ---- grain required --------------------------------------------------
        for m in self._models:
            if not m.grain:
                raise ValueError(f"Model {m.name!r} must declare a non-empty grain (the entity key column).")

        # ---- column="*" guard for aggregations that require a real column ------
        # COUNT(*) is intentionally valid; SUM/AVG/MIN/MAX against "*" would
        # emit invalid SQL that only fails at query time — catch it here.
        _aggs_requiring_column = {Agg.SUM, Agg.AVG, Agg.MIN, Agg.MAX}
        for mt in self._metrics:
            if mt.agg in _aggs_requiring_column and mt.column == "*":
                raise ValueError(
                    f"Metric {mt.name!r} uses agg={mt.agg.value!r} with column='*'. "
                    f"{mt.agg.value.upper()} requires a real column name — pass "
                    f"column='<column>' to .metric() (e.g. column='REVENUE'). "
                    "Only COUNT and COUNT_DISTINCT accept column='*'."
                )

        # ---- referential integrity -------------------------------------------
        for d in self._dimensions:
            if d.model not in model_names:
                raise ValueError(
                    f"Dimension {d.name!r} references undeclared model {d.model!r}. "
                    f"Declared models: {sorted(model_names)}."
                )
        for mt in self._metrics:
            if mt.model not in model_names:
                raise ValueError(
                    f"Metric {mt.name!r} references undeclared model {mt.model!r}. "
                    f"Declared models: {sorted(model_names)}."
                )
        for j in self._joins:
            for endpoint, side in ((j.left, "left"), (j.right, "right")):
                if endpoint not in model_names:
                    raise ValueError(
                        f"Join {j.left!r} -> {j.right!r}: {side} endpoint "
                        f"{endpoint!r} is not a declared model. "
                        f"Declared models: {sorted(model_names)}."
                    )

        # ---- auto-derive extra_dimensions ------------------------------------
        # Build a map: model_name -> frozenset of non-PII dimension names on that model.
        dims_by_model: dict[str, frozenset[str]] = {}
        for d in self._dimensions:
            if d.model not in dims_by_model:
                dims_by_model[d.model] = frozenset()
            if not d.pii:
                dims_by_model[d.model] = dims_by_model[d.model] | {d.name}

        # For each MANY_TO_ONE join, record: many_model -> {one_model, ...}
        many_to_one_targets: dict[str, set[str]] = {}
        for j in self._joins:
            if j.cardinality == Cardinality.MANY_TO_ONE:
                many_to_one_targets.setdefault(j.left, set()).add(j.right)

        extra_dim_sets: dict[str, frozenset[str]] = {}
        for mt in self._metrics:
            if mt.extra_dimensions:
                # Explicit override — do not auto-derive.
                continue
            reachable: frozenset[str] = frozenset()
            for one_model in many_to_one_targets.get(mt.model, set()):
                reachable = reachable | dims_by_model.get(one_model, frozenset())
            if reachable:
                extra_dim_sets[mt.name] = reachable

        return CompiledRegistry(
            metrics=tuple(self._metrics),
            dimensions=tuple(self._dimensions),
            models=tuple(self._models),
            joins=tuple(self._joins),
            _extra_dim_sets=extra_dim_sets,
        )
