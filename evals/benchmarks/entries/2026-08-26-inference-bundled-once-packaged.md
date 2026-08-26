---
id: 2026-08-26-inference-bundled-once-packaged
date: 2026-08-26
label: "inference: agent-side while exploring, bundled through the seam once packaged"
plugin_version: 0.40.0
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — inference: agent-side while exploring, bundled through the seam once packaged

## Notes

No public scenario builds a closure whose answers depend on inference, so no
scenario can distinguish this change. The two job-loop scenarios that reach a
build (`job-loop-serve-query-refine`, `job-loop-export-handoff`) require a live
desktop supervisor and are `ci_skip`; neither judges anything, and the mapper
path additionally needs a consent grant, a supervisor approval interaction and
real model spend, none of which a scenario arm can supply unattended.
Manufacturing one to produce a figure would make the evidence less trustworthy,
not more.

**What changed is a preference, not a mechanism.** Every gate behaves exactly as
before: Phase E still denies a raw provider-SDK import in `transform/main.py` and
in every `contracts/**/*.py` verifier, Phase G still requires a consent grant
bound to each mapper spec by hash, and the mapper seam
(`nxd.experimental.field_mapper` via `make_call`) is still the only sanctioned
way a transform reaches a model. The 95 Phase E / Phase G tests pass unchanged
apart from the one message assertion noted below.

What was wrong was the guidance sitting on top of that mechanism. It said the
transform "never calls a model", called Phase G a "narrow exception", and told
authors to reach for the mapper *only* when the mapping must run over rows the
transform itself produces — sending every other inference case, including a
rubric applied to a bounded list, to agent-side judging that lands as CSV before
the build.

The justification given was reproducibility: agent-side rows are frozen, so a
rebuild reproduces them. That conflates two different things, and the conflation
is the defect. **Self-containment is a property of the logic, not of the values.**
A closure whose scores were produced in an earlier agent session is not
self-contained however complete its file list looks — the prompt, the reading of
the evidence and the model identity all lived outside it, and what ships is a
frozen output nobody who receives the closure can re-derive from the closure. It
had bought value-stability with the thing value-stability was for.

The rule is now two lanes, keyed on whether the product is packaged:

| | exploring | packaged |
|---|---|---|
| who judges | the orchestrating agent, in session | the transform, through the seam |
| lands as | `batch-00N.csv` written before the build | rows produced by `map_inputs` during the run |
| rerun | frozen values | values may move — **disclosed, not prevented** |
| cost | none | consent grant, supervisor approval, model spend |

Agent-side judging keeps its place and its whole recipe; it is reclassified as a
scaffold rather than the shipping shape. Judging fifty entities by hand while the
rubric is still moving costs nothing and is thrown away when the criteria change
an hour later. Once the same product ships, is handed off, or will be rebuilt,
the judging moves inside the transform so the procedure travels with the artifact,
and the movement in the values is carried by `rubric_version`, `judged_by` and
`status = proposed` rather than hidden.

**No new mechanism was added, and one was deliberately reverted.** The first pass
at this change invented a parallel `contracts/inference/*.json` declaration with
a bundled `prompt_file`, plus a conditional Phase E — before reading that the
mapper spec already *is* the bundled procedure, the grant already *is* the
declaration, Phase G already *is* the gate, and `make_call` already resolves the
credential outside the closure (explicit secrets mapping, or the opt-in
allowlisted `ANTHROPIC_API_KEY` fallback) with the user authorizing the subject
through the supervisor's client-mediated confirmation. That patch was reverted in
full. The credential rule the user restated — model credentials belong outside
the blueprint and the data product — was already the contract; it is now stated
where an author reading about inference will actually meet it.

## Evidence

- `evals/tests/test_reach_gate_phase_e.py::test_model_sdk_import_fails_on_csv_closure`
  — the carrying test. Its third assertion changed from `"never calls a model"` to
  requiring the finding name both `field_mapper` and `grant`, because the message
  was pointing authors at the wrong remedy: the denial is about the *seam*, not
  about inference as such, and an author told "a transform never calls a model"
  goes looking for a way to stop inferring rather than for the sanctioned path.
  **Verified to fail against the previous implementation** — run against the
  pre-change `self_check.py` it fails on `assert 'field_mapper' in out`, with the
  old message ("Inference belongs in the session that AUTHORS the closure") in the
  captured output.
- `python3 -m pytest evals/tests` — 940 passed, 8 skipped. The 8 skips are the
  pre-existing `NXD_REPO` / `dlt`-dependent ones, unchanged by this PR.
- Phase E and Phase G behaviour is untouched: no finding code added, removed or
  re-owned, no change to `MODEL_ROOTS`, `TRANSPORT_ROOTS`, the connector waiver,
  the verifier scan, or the Phase G grant oracle. The self-check diff is the one
  finding message, the phase banner, and the header comment explaining what the
  gate is about.
- Docs changed, all in the same direction:
  `src/nxd-generate-data-product/reference/llm-judgments.md` (§ "Where the judging
  happens" rewritten to the two lanes),
  `src/nxd-generate-data-product/reference/field-mapper.md` (§ "When to use it"
  flipped — the packaged path, not a narrow exception),
  `src/nxd-generate-data-product/reference/self-check.md` (a green Phase E is not
  a claim that the closure does not infer),
  `src/nxd-generate-data-product/SKILL.md` and
  `src/nxd-run-job-loop/SKILL.md` (invariant restated; the job-loop bullet points
  at the reference rather than restating it, keeping SKILL.md at 500 lines),
  `src/nxd-run-job-loop/reference/inference.md` (§ "Two lanes", and incremental
  judging reclassified as an exploration-lane discipline).
- `python3 scripts/validate_skills.py --root .` — passes, including the 500-line
  SKILL.md cap.
- `./build-skills.sh` — passes; every skill zip under the 200-entry Desktop cap,
  plugin pack `nexty-agent-skills-v0.40.0.zip` at 362 files.
- Version lockstep at 0.40.0 across `.claude-plugin/plugin.json`,
  `.claude-plugin/marketplace.json` and all 17 `src/*/SKILL.md`. Minor rather than
  patch: authoring guidance changed. No skill added or removed, so pack
  completeness is unaffected.
