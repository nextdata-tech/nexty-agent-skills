---
id: 2026-08-03-field-mapper-in-nxd-package
date: 2026-08-03
label: "nxd-generate-data-product: the field mapper reaches a closure through the nxd package"
plugin_version: 0.35.0
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — nxd-generate-data-product: the field mapper reaches a closure through the nxd package

## Notes

No public scenario builds a closure that maps fields with a model, so no
scenario can distinguish this change — the same reason
[2026-08-03-field-mapper-promoted-consent-gate](2026-08-03-field-mapper-promoted-consent-gate.md)
carries no arm. Authoring one to produce a figure would make the evidence less
trustworthy, not more.

What shipped: the harness moves out of the closure root and into the `nxd`
package the runtime already installs, at `nxd/experimental/field_mapper/`. A
closure imports `nxd.experimental.field_mapper` rather than copying a directory.
That closes the gap the previous entry recorded and could not fix: the desktop
supervisor stages only `transform/main.py` into its isolated data directory, so
a vendored `field_mapper/` was absent at execution and every mapper closure died
on `ModuleNotFoundError` after passing all three static gates.

Phase G now triggers on the dotted path. Dot-boundary matching is what keeps
that narrow — the `import nxd` and `from nxd.spec import ...` every closure
carries do not fire the gate, and neither does a sibling like
`nxd.experimental.semantic`. That was verified against the real `imported_roots`
/ `denied_hit` helpers over seven import forms rather than reasoned about.

## Evidence

`evals/tests/test_grant_gate_phase_g.py` covers the gate over the extracted
block, now staging the harness where `nxd.experimental.field_mapper` resolves so
the subprocess oracle is the real package rather than a stub.
`evals/tests/test_desktop_custom_contract_checker.py` carries the three tests
that drive the **real** `src/nxd-run-job-loop/scripts/self_check.py` end to end — deny-without-grant,
green-with-matching-grant, and the closure-root module route. The
green-with-matching-grant case is the one that pins the Phase B shadowing fix
described below; the deny cases pass with or without it, which is why a gate
that can only deny is indistinguishable from a broken one.

The acceptance suite ran **from a wheel built and installed into a clean venv**,
invoked from an unrelated working directory, so the fixtures resolved from
site-packages rather than a source tree: 13/13 fixtures behaved as declared and
all 13 spec hashes were stable. Those hashes are byte-identical to the ones the
vendored harness produced, which is the load-bearing check — a moved hash would
silently invalidate every consent grant a user has already signed. The wheel was
also inspected directly to confirm it carries all 15 modules, all 80 fixture
files, and `CONTRACT.md`.

Three defects surfaced that no test had covered, none of which was the intended
work:

Phase B builds a synthetic `nxd` module so the dry run needs no installed SDK. A
bare `ModuleType` has no `__path__`, and a module without one cannot have
submodules — so once it landed in `sys.modules` it SHADOWED the real package,
and any `nxd.<anything>` a transform imported died as `'nxd' is not a package`.
That would have hit every mapper closure Phase G had just cleared to run. It was
reproduced in four lines independent of any fixture, fixed by borrowing the real
package's search path, and the fix was then confirmed load-bearing by
neutralising it and watching `test_real_self_check_green_with_matching_grant`
fail. The closure root goes on `sys.path` before the lookup, so a closure-root
package is visible to the resolution rather than only at import.

Annotating the harness for pyright strict — 128 errors to zero, no suppressions
— turned up two more: `model_snapshot` was read on a path that could leave it
unbound, and `corroborate` was declared twice with incompatible types. A third
came from mypy after pyright was already clean: one name bound to both a
non-optional proposal and an optional lookup of the same kind. The repo gates on
mypy, pyright and ruff independently; passing one of them is not passing the
gate.

The skill zip no longer carries the harness (117 entries to 102, 396K to 252K).
A copy inside the skill is unusable once the runtime provides it, and worse, an
invitation to vendor a second one. `mapper/CONTRACT.md` and `mapper/samples/`
still ship — the contract is normative and the fixtures are what
`reference/field-mapper.md` points at.

Two changes ship here that are not the import move and are worth naming
separately, because neither is visible in the gate's diff.

`resolver.py` now exempts `EffectiveSource.HUMAN_OVERRIDE` from the model's
`min_evidence` floor, with CONTRACT §7.2 amended to match. This is a behaviour
change, not a refactor: an override carrying no evidence atoms used to raise
`BijectionError` and block the build, and now lands. A human who states a value
is the authority for it and owes no citation to the model that guessed wrong.
The carrying test is nxd-side — acceptance fixture 06 covers it, and the first
attempt at this fix narrowed the enclosing branch instead of nesting inside it,
which dropped overrides into a structural-error path and was caught by that
fixture rather than by review.

The verifier scan now denies **both** spellings. The legacy-import denial walks
`transform/**/*.py` plus a non-recursive closure root, and `contracts/` is in
neither, so a verifier carrying the retired `import field_mapper` matched
nothing anywhere once `MAPPER_ROOT` became the dotted path — coverage that the
pre-move constant had provided for free. A verifier that maps is the worst case
the gate handles: it re-decides pass/fail against a live model on every run, and
Phase E cannot see it because the harness reaches `anthropic` through a
function-local import.

The harness has two homes. The canonical copy is the one in the nxd monorepo,
where it is tested, version-stamped and packaged; this repo keeps a tree because
the consent gate's tests need a real harness to run against and this repo's CI
cannot reach the monorepo. Every `.py` file is byte-identical between them, and
the fixture root resolves in both layouts from one shared implementation. The
residual is that nothing enforces that automatically — a future edit to one tree
still has to be mirrored by hand.
