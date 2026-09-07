# Drift canary

The drift canary is the preflight for the DP-scenarios suite. It checks that
the pinned Nexty skill pack and the pinned `nxd-desktop` runtime still agree
before any conversational scenario spends time or model calls.

This is a deterministic compatibility check, not a user conversation and not
a measure of agent quality. Unlike the other packages, it has no
`scenario.yaml`; the canary is selected and run by the suite runner itself.

## Purpose

The canary protects the scenario results from guidance-versus-runtime drift. A
scenario can fail because an installed skill claim is stale even when the
scenario's own fixture and grading logic are correct. The canary identifies
that mismatch by checking the exact claim text, line, and expected supervisor
finding before the rest of the tier runs.

## Probe flow

The canary uses the checked-in kitchen-sink closure and three copied negative
probe closures:

1. Load `claims.json` and verify its approved baseline hash before invoking a
   process.
2. Extract the declared claims from the supplied `--skills-root`, checking
   file, line, quote, direction, and content hash.
3. Run the kitchen-sink closure through supervisor preflight and one build.
   Supported claims must produce the expected structure, companion-file,
   semantic, or build findings.
4. For each documented-unsupported probe, remove exactly its planted
   `.semantic_tools(` construct from a temporary copy. The negative control
   must fail at the declared unsupported finding, with downstream skipped
   stages treated as expected non-reachability.
5. Aggregate the probe results into `clean`, `drift`, or `blocked`. Any unknown
   supervisor/check state fails closed, and a `skip` is blocking rather than a
   pass.

The suite runner executes this canary before constructing scenario transports
or environments. A non-clean result blocks the selected tier.

## Inputs and artifacts

- `claims.json` is the committed claim matrix. It records the skill file,
  quoted line, expected finding code, direction, and content hash for every
  probe claim.
- `claims.json.approval.json` records the approved claims hash. The checking
  path verifies it and never repairs or rewrites the baseline.
- `probes.json` maps probe IDs to the closure to check and declares which probe
  is expected to build. Its negative controls identify the exact construct to
  remove.
- The kitchen-sink closure contains the companion paths, source fixtures,
  `spec.py`, transform, and infra profile required by the claims. Negative
  probes are copied to temporary directories and are not edited in place.
- The generated JSON report contains the probe reports, observed finding
  codes, build result, verdict, and any claim-level issue. It is retained by
  the tier runner rather than committed to this package.

## What is actually driven

The canary invokes the supplied supervisor against the local closure and uses
the supplied skill root. It therefore checks the runtime-facing surfaces and
the temporary negative controls for real, subject to the selected local
executables. It never starts an agent conversation, asks a model to judge
prose, or treats a scenario's final answer as evidence.

The tests cover claims extraction and approval, probe/build command handling,
unknown-state fail-closed behavior, negative-control trimming, temporary-copy
isolation, and the rule that a blocking canary prevents scenario transport
construction.

## Execution

Run the canary from the repository root with the skill pack under test:

```bash
uv run --project evals/dp-scenarios python -m dp_scenarios.canary.cli check \
  --closure evals/dp-scenarios/scenarios/drift-canary \
  --claims evals/dp-scenarios/scenarios/drift-canary/claims.json \
  --skills-root src
```

Pass `--supervisor <path>` when the `nxd-desktop-supervisor` executable is not
available through the runner's normal resolution. `--no-build` is useful for a
local diagnostic, but it deliberately returns a blocking result and is not a
tier-gate substitute.

Run the canary-focused tests from `evals/dp-scenarios/`:

```bash
uv run pytest tests/test_canary_*.py tests/test_runner_canary_isolation.py -q
```

## Goal

Return `clean` only when the approved claims still match the supplied skills,
the kitchen-sink preflight/build behaves as declared, and every unsupported
negative control fails for the expected reason. Preserve the checked-in
closure and claims baseline while probing temporary copies.

## Assertions

- The approved claims file is intact and its content hash matches the approval
  record.
- Every committed claim is found at its declared path and line with the same
  text hash.
- Supported claims produce their expected runtime finding codes, while
  documented-unsupported claims fail at the expected check.
- The negative controls do not accidentally pass, and expected downstream
  skips do not hide a different failure.
- Supervisor exit status agrees with the structured report.
- Unknown stage or check states fail closed; `skip`, missing checks, malformed
  reports, and missing claims are not clean results.
- The temporary live canary copy is isolated from the checked-in package and is
  removed after the probe returns.
- A non-clean canary blocks scenario execution before model or scenario
  transport work begins.

## Limitations

- **No agent quality claim.** A clean canary proves only compatibility of the
  checked skill/runtime surfaces. It does not prove that an agent can complete
  any scenario or produce a correct data product.
- **No authenticated Claude Desktop conversation.** The canary does not test
  login, multi-turn behavior, operator handling, or agent prose.
- **Claim coverage is explicit.** Only claims and probes recorded in
  `claims.json` and `probes.json` are checked. A skill behavior not represented
  in that matrix is outside this preflight.
- **The build is local and pinned by the runner.** A clean result does not
  validate hosted CI, a different supervisor version, or an unpinned global
  skill installation.
- **Human approval remains separate.** Updating the claims baseline requires a
  deliberate rebaseline operation; the read-only check must not silently accept
  changed skill text.
