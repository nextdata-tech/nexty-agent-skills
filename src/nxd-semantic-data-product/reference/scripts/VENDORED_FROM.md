# Vendored from

Source path (in the nxd monorepo): `components/nxd_py/data_product/nxd/experimental/semantic/`

Source commit: `045906949` — `feat(nxd_py): experimental.semantic module — registry/compiler/dialect/MCP factory (NEX-620)` (branch `feat/nex-620-experimental-semantic`, PR nextdata-tech/nxd#6902). Re-vendored 2026-06-18.

This snapshot is byte-identical to the committed source modulo the import-root
rewrite documented below. To check for drift, diff the committed source against
these files after normalizing `from nxd.experimental.semantic.X import` →
`from .X import`.

Files vendored:
- `registry.py`
- `dialect.py`
- `compiler.py`
- `mcp_tools.py`
- `__init__.py`

Import adjustment: cross-module imports changed from
`from nxd.experimental.semantic.X import ...` to relative `from .X import ...`
so the files work as a self-contained sibling package when copied flat into a
DP's `transform/semantic/` directory. Logic is otherwise byte-identical to the source.

Changes relative to the previous vendor snapshot (`36dee1470d734b1f6c948f81b2e374177c27f644`):

1. **mcp_tools.py** — added `SemanticTool` frozen dataclass; `build_semantic_tools`
   now returns `list[SemanticTool]` (was `list` of bare callables). Each descriptor
   carries `.fn`, `.request_model`, `.response_model`, `.description` for correct
   `rpc_function` wiring in `spec.py`.

2. **compiler.py** — added star-schema fan-out guard in `_validate_selection`:
   raises `CompileError` when dimensions span more than one foreign model
   (multi-join path is not implemented; the guard surfaces an actionable error).

3. **__init__.py** — exports `SemanticTool` alongside `build_semantic_tools` in
   the `try` block; `__all__` extended accordingly.

4. **registry.py** — added `.measure()` alias for `.metric()` (ADR-020 convergence
   vocabulary; allows code written against the future spec DSL to work unchanged).

5. **dialect.py** — no logic changes; import paths adjusted to relative form only.

6. **all files** — strict-pyright + mypy (3.10/3.11) type annotations added at
   commit time (parameter/return types, `cast` on filter-value iteration,
   `# pyright: ignore` only at the untyped Snowflake-connector boundary in
   `mcp_tools.py`). No runtime-behavior or public-API change; goldens unchanged.

This is a verbatim build-time snapshot. Never hand-edit the vendored files in
this skill or in any generated DP. Report bugs to the `nxd_py` monorepo and
re-vendor from the updated source.
