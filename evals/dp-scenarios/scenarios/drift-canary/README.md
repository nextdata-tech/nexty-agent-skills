# Drift canary

## Purpose

This is the preflight for the DP-scenarios suite. It checks that the installed
Nexty skill pack and the `nxd-desktop` runtime still agree before an agent is
allowed to run the conversational scenarios.

The canary is intentionally not a user conversation and does not measure model
quality. It is a deterministic compatibility check over the skill claims,
their companion files, the supervisor self-check, and one real local build.

## What is executed

The canary:

1. Extracts the quoted claims from the installed skill root and compares them
   with the committed claim hashes.
2. Runs the supervisor preflight against the kitchen-sink closure.
3. Builds that closure once when the preflight is clean.
4. Runs the declared unsupported-path negative controls and checks that they
   fail with the expected diagnostic behavior.
5. Aggregates the results into a clean, drift, or blocked verdict.

The skill root, supervisor binary, and runtime used for the check are supplied
by the runner and pinned in the trial manifest. There is no fallback to a
global skill installation.

## Assertions

- Every committed claim still exists at the declared file and line.
- The claim content hashes have not changed.
- Supported claims produce their expected structure, semantic, companion-file,
  or build findings.
- Unsupported claims remain rejected by the runtime.
- Negative controls do not accidentally pass.
- Supervisor exit status and structured report agree.
- A non-clean result blocks the rest of the tier.

## Artifacts

- `claims.json` is the committed claim baseline.
- `claims.json.approval.json` records the approved baseline hash.
- `probes.json` declares the positive and negative probe closures.
- The generated preflight/build report is retained in the run report, not in
  this package.

This canary proves compatibility of the checked surfaces. It does not prove a
full authenticated Claude Desktop conversation or a successful DP scenario.
