---
id: 2026-08-06-inspect-run-binding-documented
date: 2026-08-06
label: "nxd-run-job-loop / nxd-generate-dp: correct stale inspect_run and v2-era closure claims"
plugin_version: 0.36.2
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — nxd-run-job-loop / nxd-generate-dp: correct stale inspect_run and v2-era closure claims

## Notes

Documentation-of-record only: no agent behavior changes. The loop already called
`mcp__nxd-desktop__inspect_run` once with the failed `run_id` and classified from
that diagnostic — `SKILL.md` and `reference/failure-handling.md` have carried the
bound contract since the call-shape work. What lagged was
`reference/build-record.md`, which still described the tool as having no producer:
"The pack names a run-inspection tool once and never uses it — no schema, no
reference doc, no step, no test." Every clause of that was false, and its
`supervisor_detail` JSON example still showed `origin: "unbound"`.

No scenario can distinguish this change, because no scenario observes it. The
prose describes a binding that already existed in the arm both before and after,
so an eval run would return the identical transcript on either side.
Manufacturing a scenario to produce a number here would measure the loop's
existing use of `inspect_run`, not this correction to the doc.

The limits were deliberately preserved rather than declared closed: stage
attribution remains an agent inference (the supervisor emits no
`code`/`stage`/`severity`/`owner`), `s5_serve` stays indistinguishable from
`s4_pin`/`s6_run`/`s7_publish`, and per-attempt supervisor identity is still
genuinely `origin: "unbound"` — so that row of the origin vocabulary table stays
valid.

A second class of staleness is corrected in the same pass: docs written before
the v3 authoring cutover that still describe the v2 artifact set as the only one.
`reference/context-and-resume.md` — the doc a cold session reads to learn what
persists — described `dp-spec.lock.json` as carrying "that copy's v2 canonical
hash" and listed "the four generated record files", omitting
`dp-spec.proposal.approved.json` entirely. `dp_diagnostics.py:1702-1709` writes a
v3 lock for every new prose-first plan, and `self_check.py:1797-1896` makes that
proposal snapshot's presence and hash a **blocking** Phase C failure — so the
file a resuming session most needs was missing from the inventory, and the count
was wrong for a v3 closure. `self-check.md:104` likewise named "the shared v2
parser" where `dp_diagnostics.py:1577-1600` now dispatches on `dp_spec_version`.

No v2 mention was deleted. `dp_spec_v2.py` still ships, and every doc calling it
a legacy read-only verifier is accurate; the schema identifier strings
(`nxd-diagnostic-v2`, `nxd-build-record-v2`, `nxd-dp-spec-lock-v2`) are literal
wire-format names the code still emits. Only claims that presented the v2-era
artifact set as current were reworded.

A third pass swept the remaining superseded-entity classes across all 91
reference files and 17 SKILL.md. Two navigation defects were repaired:
`runtime-and-dependencies.md:7` listed a `Base-table transform` section that had
been renamed to `Transform and output wiring`, and `vector-rag.md` had all seven
of its `## Contents` anchors resolving to nothing, because the `Step N` sections
they target were bold paragraphs rather than headings — promoted to `###` so the
existing links resolve and the file meets the AGENTS.md Contents convention for
100+ line references. A repo-wide check now reports zero broken same-file
anchors.

The other classes in that sweep came back clean and are recorded here so the
next audit need not redo them: every documented CLI invocation of this repo's
own scripts matches its current parser (`dp_diagnostics.py`'s full
subcommand/flag surface across 14 call sites, plus the query, analyze-mesh, and
evals scripts), all 7 `mcp__nxd-desktop__*` tool names match the supervisor, no
doc names a renamed skill or a nonexistent symbol, and every documented `EVAL_*`
/ `NXD_*` / `JOB_*` env var is read somewhere in code.

## Evidence

`evals/tests/test_build_record_schema.py` pins the build-record schema and the
`origin` vocabulary the corrected example must satisfy, including
`supervisor_detail` carrying a verbatim supervisor-authored payload;
`evals/tests/test_dp_diagnostics_schema.py` pins the diagnostic contract that
`origin: supervisor_reported` must meet, and
`evals/tests/test_build_record_s0_producer.py` covers producer binding. All 104
tests across the three files pass with the corrected example.

For the v3 closure claims, `evals/tests/test_dp_spec_authoring.py` is the
carrying test: `:632` pins `lock["schema"] == "nxd-dp-spec-lock-v3"` and `:634`
pins the `dp-spec.proposal.approved.json` snapshot bytes against the lock, with
tamper cases at `:663-679` — exactly the file set and lock generation that
`context-and-resume.md` now inventories. 57 tests, all passing.
