# Vendored from

Source path (in the nxd monorepo): `components/nxd_py/data_product/nxd/experimental/semantic/`

Source commit: `3c1986488ca2ae7dbdfb8ac381237955d811542f` — Re-vendored 2026-06-19.

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
- `_predicates.py` (neutral leaf: CompileError, _lit, _ALLOWED_OPS, _render_predicate)

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

4. **registry.py** — added `.measure()` alias for `.metric()` (ADR-026 convergence
   vocabulary; allows code written against the future spec DSL to work unchanged).

5. **dialect.py** — no logic changes; import paths adjusted to relative form only.

6. **all files** — strict-pyright + mypy (3.10/3.11) type annotations added at
   commit time (parameter/return types, `cast` on filter-value iteration,
   `# pyright: ignore` only at the untyped Snowflake-connector boundary in
   `mcp_tools.py`). No runtime-behavior or public-API change; goldens unchanged.

7. **PR #6902 review fixes** (commit `587a1a26e`):
   - **compiler.py / dialect.py** — SECURITY: the native-view path
     (`dialect.native_view_query`) previously interpolated the LLM-supplied
     filter `op` after only `.upper()`, skipping the operator allowlist the
     base path enforced (predicate-injection bypass). Both paths now route
     through one `_render_predicate` / `_ALLOWED_OPS` renderer in
     `compiler.py`; invalid/injected ops raise `CompileError`. `IN`/`NOT IN`
     with a scalar value now raises an actionable `CompileError`.
   - **registry.py** — `build()` rejects SUM/AVG/MIN/MAX with `column="*"`;
     builder methods documented.
   - **dialect.py** — `view_name(registry)` promoted onto the `Dialect`
     Protocol (no more `hasattr` probe).
   - **mcp_tools.py** — `build_semantic_tools` rejects `view_name`+`dialect`
     together; tool descriptions defined once; `with conn.cursor()`.
   - ADR citations renumbered 020 → 026 (the ADR was renumbered to avoid
     collision with `020-event-store.md`; nxd PR #6893).

8. **PR #6902 second review fixes** (commit `91b2e2da2`):
   - **registry.py** — the `column="*"` build guard now includes
     `COUNT_DISTINCT` (was SUM/AVG/MIN/MAX only): `COUNT(DISTINCT *)` is
     invalid SQL, only plain `COUNT` accepts `column="*"`. Guard set hoisted
     to module-level `_AGGS_REQUIRING_COLUMN` frozenset; message + `.metric()`
     docstring corrected.
   - **_predicates.py** (new leaf) — `CompileError`, `_lit`, `_ALLOWED_OPS`,
     `_render_predicate` moved here so the dialect no longer imports from the
     compiler. `CompileError` re-exported from `compiler.py`, so the public
     path `nxd.experimental.semantic.CompileError` is identity-preserved.
   - ADR citations note the ADR is in-flight (nxd PR #6893) until merged.

9. **model-oriented tool surface** (commit `3c1986488ca2ae7dbdfb8ac381237955d811542f`):
   - **mcp_tools.py** — `list_models` + `describe_model` replace the flat
     `list_metrics` / `list_dimensions` / `describe_metric` tools (NEX-620).
     `build_semantic_tools` now returns three descriptors instead of four.
     `describe_model` returns a model's full grain, all owned metrics (each with
     their compatible dimensions), all owned dimensions, and join topology in a
     single call — eliminating the need for separate list/describe round-trips.
     `list_models` returns metric/dimension counts + join topology for each model
     to orient the caller before selecting a grain.
   - **registry.py** — `CompiledRegistry` gains `metrics_of` / `dimensions_of` /
     `joins_of` helpers backing the model-oriented tools. `joins_of`'s reach
     matches `build()`'s auto-derived `extra_dim_sets` (non-PII, MANY_TO_ONE only);
     `describe_model`'s `reaches_dimensions` documents that explicit per-metric
     `extra_dimensions` overrides may narrow the authoritative slice set.

This is a verbatim build-time snapshot. Never hand-edit the vendored files in
this skill or in any generated DP. Report bugs to the `nxd_py` monorepo and
re-vendor from the updated source.
