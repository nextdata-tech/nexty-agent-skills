"""Semantic-layer stopgap for NXD data products (NEX-620).

This package is a **stopgap** until ADR-026 lands first-class
measure/dimension support in the NXD spec and kernel. Every public name is
intentionally aligned with ADR-026 so the later kernel migration is mechanical.

ADR-026 convergence target: ``nxd.spec.measure`` / ``nxd.spec.dimension`` and a
kernel-driven Snowflake semantic-view capability (see
``docs/architecture/adrs/026-semantic-layer-first-class.md``,
ADR under review in nxd PR #6893).

Importable without the ``rpc`` extra (compiler + registry work standalone).
``build_semantic_tools`` requires the ``rpc`` extra and is guarded accordingly.
"""

from __future__ import annotations

from typing import Any

from .compiler import CompileError as CompileError
from .compiler import compile_selection as compile_selection
from .compiler import native_semantic_view_ddl as native_semantic_view_ddl
from .compiler import plain_view_ddl as plain_view_ddl
from .compiler import semantic_view_query as semantic_view_query
from .dialect import Dialect as Dialect
from .dialect import SnowflakeDialect as SnowflakeDialect
from .registry import Agg as Agg
from .registry import Cardinality as Cardinality
from .registry import CompiledRegistry as CompiledRegistry
from .registry import Dimension as Dimension
from .registry import Join as Join
from .registry import Metric as Metric
from .registry import Model as Model
from .registry import SemanticRegistry as SemanticRegistry

__all__ = [
    # registry
    "Agg",
    "Cardinality",
    "Dimension",
    "Metric",
    "Model",
    "Join",
    "SemanticRegistry",
    "CompiledRegistry",
    # compiler
    "CompileError",
    "compile_selection",
    "semantic_view_query",
    "native_semantic_view_ddl",
    "plain_view_ddl",
    # dialect
    "Dialect",
    "SnowflakeDialect",
    # rpc extra (None-sentinel when extra not installed)
    "SemanticTool",
    "build_semantic_tools",
]

# SemanticTool and build_semantic_tools are available only when the rpc extra
# is installed. They resolve to a runtime None-sentinel when the extra is
# absent; the public names are typed as Any so both mypy and pyright accept the
# import-or-None dance without a redefinition error.
try:
    from semantic import mcp_tools as _mcp_tools

    SemanticTool: Any = _mcp_tools.SemanticTool
    build_semantic_tools: Any = _mcp_tools.build_semantic_tools
except ImportError:
    # nxd.drivers.rpc / nxd.spec not available (rpc extra not installed).
    # The compiler and registry are still fully usable without it.
    SemanticTool = None
    build_semantic_tools = None
