# Scenario: Debug Failed Data Product

The eval runner should provide logs for a data product whose platform status reports startup timeout but whose root cause may be memory pressure, dependency install failure, bad transform import, invalid service config, or policy/contract failure.

Task for the agent:

Diagnose the failure and propose the smallest safe fix.

Required artifacts from eval runner:

- `nxd describe data-product` output
- `nxd logs` output, including init logs when available
- Data-product source directory

Success checks:

- The agent gathers describe output, regular logs, and init/debug logs before guessing.
- The agent separates config errors, dependency errors, runtime transform errors, and policy failures.
- The agent uses `nxd run --retry` for retry guidance, not a nonexistent retry command.
- The agent explains whether a code change, resource change, dependency change, or policy change is needed.

