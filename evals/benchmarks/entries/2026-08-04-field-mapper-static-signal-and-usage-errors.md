---
id: 2026-08-04-field-mapper-static-signal-and-usage-errors
date: 2026-08-04
label: "nxd-generate-data-product: restore the mapper's static import signal and stop verify falling back"
plugin_version: 0.35.1
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — nxd-generate-data-product: restore the mapper's static import signal and stop verify falling back

## Notes

Follow-up to
[2026-08-03-field-mapper-in-nxd-package](2026-08-03-field-mapper-in-nxd-package.md).
No public scenario builds a closure that maps fields with a model, so no
scenario can distinguish these changes — the same reason that entry carries no
arm.

Three defects, all found by review of the merged change rather than by a test.

**Phase E lost its only static view of the harness's model dependency.** The
pyright-strict pass rewrote `transport.py`'s function-local `import anthropic`
as `importlib.import_module("anthropic")`, presumably to satisfy `PLC0415`.
This repo's gates are AST walks: `imported_roots` collects `ast.Import` and
`ast.ImportFrom` nodes only, so after that rewrite `anthropic` did not appear
among transport.py's import-level names at all. A harness tree copied under
`contracts/` then reached neither gate — Phase E could not see the SDK, and
Phase G's verifier scan matches import-level package names that the harness's
own relative imports never produce. Restored to the statement form, with a
comment saying why it must stay one. Neither repo's ruff config enables
`PLC0415`, so no suppression is needed; the rule the rewrite served is not on.

**`verify` and `pins` answered for fixtures the caller did not name.** The
target resolved as `target if target.is_dir() else default_root`, so a mistyped
path silently verified the packaged samples and printed `all 13 fixture(s)
behaved as declared` with exit 0. These are the two commands whose entire job is
answering "is this harness intact?", and on a named-but-wrong path they returned
a green for something else. A named target that is not a directory is now an
exit-3 usage error; omitting the target still defaults to the packaged samples,
which is what makes the bare invocation work from any install.

**The design record still documented vendoring.** `docs/architecture/field-mapper.md`
is the file AGENTS.md designates as the mapper's design record, and it was not
touched by the move. It described the harness as "not published as a wheel …
vendored from the skill", showed a closure layout with `field_mapper/` at the
root, and gave four `python -m field_mapper` invocations. An agent reading it
built exactly the closure Phase G now hard-fails as `grant.vendored_harness` —
the one shape no grant rescues. Rewritten to the package contract, and its
"never under `contracts/`" advice re-scoped: that advice rested on Phase E
seeing `import anthropic`, which is true again only because of the first fix.

## Evidence

`evals/tests/test_grant_gate_phase_g.py` and
`evals/tests/test_desktop_custom_contract_checker.py` cover the gate, not the
harness, and pass unchanged — 609 in `evals/tests/` overall.
The harness's own acceptance suite is nxd-side; the CLI behaviour above was
verified directly — a named bad path exits 3 for both `verify` and `pins`, a
bare invocation still exits 0 with 13/13 — and the restored import was confirmed
visible to an `ast.walk` over `transport.py`, which is the property the gate
actually depends on.

The two harness files here must be mirrored into the nxd package copy, which is
the canonical one. That mirror is a paired PR against the monorepo; nothing in
this repo enforces it, which remains the standing residual.
