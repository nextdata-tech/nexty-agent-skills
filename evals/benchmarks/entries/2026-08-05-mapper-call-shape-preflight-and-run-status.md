---
id: 2026-08-05-mapper-call-shape-preflight-and-run-status
date: 2026-08-05
label: "nxd-generate-data-product + nxd-run-job-loop: pin the mapper call shape, add a mandatory preflight, and fix failure reporting"
plugin_version: 0.35.3
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — pin the mapper call shape, add a mandatory preflight, and fix failure reporting

## Notes

Follow-up to
[2026-08-04-field-mapper-static-signal-and-usage-errors](2026-08-04-field-mapper-static-signal-and-usage-errors.md).
No public scenario builds a closure that maps fields with a model — the same
reason that entry and
[2026-08-03-field-mapper-in-nxd-package](2026-08-03-field-mapper-in-nxd-package.md)
carry no arm. Manufacturing one here would mean authoring a consent grant and
paying for live calls in CI to produce a number that measures the model, not
this change; the carrying tests below are the honest evidence.

Driven by a real Claude Desktop mapper build that failed twice, both times on
something checkable offline in under a second.

**The normative contract documented an API that never existed.** Both copies of
`mapper/CONTRACT.md` advertised `map_inputs(inputs, *, spec, deps)` in the
public-surface table. There is no `deps` argument, object, or module anywhere in
the implementation — the installed signature has always been
`map_inputs(inputs, *, spec, grant, run_dir, call, ...)`. The same table omitted
`MapperInput` entirely, though it is the type every caller must construct
first. So the one document a generated closure is meant to trust described a
call that could not run and said nothing about the constructor it needed.

The closure guessed the natural thing — one keyword per source column — and died
with `MapperInput.__init__() got an unexpected keyword argument 'document_id'`,
*before* `map_inputs` was entered: no model contacted, no spend, nothing
published. The fix is documentation plus enforcement, not a new abstraction:
building the advertised `deps` wrapper would have churned an acceptance-tested
primitive to satisfy a line no code ever honoured, and left two spellings of the
same call for generated code to choose between. The decision and its rejected
alternative are recorded in `docs/architecture/field-mapper.md`.

Both contract copies now carry the real signatures and a worked
`MapperInput(input_id=..., identity=..., fields=..., landed_text=...)`
construction, with the four slots' distinct guarantees stated — `identity` is
what the grant binds to, so a closure that dumps identity into `fields` leaves
it empty and silently unbinds every review. `reference/field-mapper.md` gained
the same example inline, since that is what a closure author actually reads.
Signature introspection is explicitly banned: a mapper that adapts to whatever
is installed converts a loud `TypeError` into a silent behavioural difference
between two runtimes.

**The runtime was missing the SDK the mapper needs.** The first failure was
`CredentialMissing`, the second was a venv with no `anthropic`. Both are
provisioning, not code. `anthropic==0.117.1` is now pinned in the Desktop
runtime dependency set and in the offline Linux bundle, with a `--verify` probe
that imports it, reports the installed version, and reports API-key presence as
a bare boolean — never the value. The pin stays out of `nxd-data-product`'s own
dependencies: the mapper is one experimental surface, and every non-mapper data
product would otherwise install an API client it never calls.

**Nothing forced the failure to be reported honestly.** The gates that passed —
credential resolution, grant validation — were reported in a way that read as
progress, while the run had in fact stopped before dispatch. Two additions
close that. `reference/mapper-preflight.md` is a new mandatory, model-free
preflight: twelve offline checks (import, SDK, key presence, spec parse,
canonical spec id, grant binding, field/class coverage, transform compile,
`MapperInput` construction, `map_inputs` signature, ceilings) with a fixed
machine-readable report and a fixed `MAPPER RUN STATUS` block emitted before and
after every attempt. It also names seven claims that must never be collapsed
into one — self-check, build dispatch, transform execution, model invocation,
publication, catalog verification, semantic query — because reporting a green
consent gate as a successful mapper run is the specific failure being fixed.

**`inspect_run` was documented as unbound.** `nxd-run-job-loop/SKILL.md` said no
step calls it and told the reader not to invent a contract for it. That was
stale: the supervisor implements it, and its own export path already tells users
to call it on a failed transform. It is lock-free, starts no runtime, and
returns a bounded, path-redacted child diagnostic. The skill now prescribes
calling it exactly once with the failed `run_id`, and
`reference/failure-handling.md` gained a section on classifying by stage rather
than by exception text, an explicit list of deterministic failures that must not
be retried unchanged (wrong call shape, missing dependency, non-binding grant,
anything in `s0_spec`–`s3_closure`), a requirement to state whether the model
was contacted, and a rule that a hand-patched closure is failed evidence rather
than proof of a fix.

## Evidence

No file in this repo executes the mapper, so the call-shape fix is carried by a
test in the nxd monorepo, where the harness lives — a new module beside the
field-mapper acceptance suite that asserts `MapperInput(document_id=...)` raises
`TypeError`, that the documented four-slot construction preserves each slot
distinctly, that `map_inputs` exposes `spec`/`grant`/`run_dir`/`call` as
keyword-only and has **no** `deps` parameter, and that the documented call runs
end to end offline through the recorded player. Two further tests hold the
safety line the first four could otherwise erode: a non-binding grant still
raises, and no derived rows are written outside the test's `tmp_path`. It fails
against the incident's shape — verified directly against the installed runtime,
which reproduces `got an unexpected keyword argument 'document_id'` — and passes
against the corrected one. As in the prior entry, the monorepo path is not
spelled out as a file reference: this repo's validator resolves Evidence paths
locally, and a cross-repo path would read as a missing file.

The provisioning half is carried by
`components/desktop/supervisor/scripts/tests/test_nxd_desktop_setup.sh` in that
same repo, extended with guards for both pins, the import probe, the actionable
remediation string, the offline wheel assertion, and a presence-only assertion
on the key probe — plus a drift check that every pin in the online setup list
also appears in the offline bundle list, since the two are installed by
different code paths. Confirmed failing against a mutant with the pin removed,
then restored.

In this repo the changed surfaces are documentation, carried by the existing
gate tests that read them: `evals/tests/test_grant_gate_phase_g.py` covers the
consent path the preflight's checks 5–8 restate, and
`evals/tests/test_no_context_doc.py` holds the reference-file conventions the
new `reference/mapper-preflight.md` must satisfy. The suite passes at 610,
`validate_skills.py` passes, and
`build-skills.sh` packages all 13 skills within the 200-entry cap —
`nxd-generate-data-product` at 103 entries with the new reference file, and
`nxd-run-job-loop` at 19. `nxd-run-job-loop/SKILL.md` is 499 lines, back under
the 500 cap after the `inspect_run` rewrite.

## What this does not prove

The corrected shape has not been exercised by a live Claude Desktop build. That
run is deliberately left outstanding rather than simulated here: the closure
from the incident was patched by hand after it failed, so re-running it would
prove nothing about the generated path, and a fresh closure generated from the
corrected source is what the next acceptance run needs. No live model call was
made anywhere in this change, and no API key was read or printed.
