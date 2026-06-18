---
name: nxd-debugging-data-products
description: Debug failed or unhealthy Nextdata OS data products. Use when diagnosing nxd validate, launch, deploy, startup timeout, dependency install, compute status, logs, init container, MCP server, policy, contract, output write, or transform runtime failures and choosing the smallest safe fix.
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - MultiEdit
  - Glob
  - Grep
  - AskUserQuestion
metadata:
  author: nextdata
  version: 0.1.1
---

# NXD Data Product Debugging

Diagnose from evidence first, then patch the smallest source, config, dependency, resource, or contract issue.

## Setup

- Confirm `nxd-setup` has selected the mesh and produced `<session_config>`.
- Resolve `<app_url>` from the active mesh registry and use docs paths:
  - `<app_url>/docs/#/dp_development/debugging`
  - `<app_url>/docs/#/tutorials/cli/create`
  - `<app_url>/docs/#/tutorials/guides/03-promises`
  - `<app_url>/docs/#/tutorials/guides/05-expectations`

## Evidence First

Run the lowest-risk reads before guessing:

```bash
nxd --config <session_config> describe data-product <dp-name> --compute-status
nxd --config <session_config> logs <dp-name> --debug-logs
nxd --config <session_config> logs <dp-name> --init --debug-logs
```

If the failure involves MCP/RPC output code:

```bash
nxd --config <session_config> logs <dp-name> --mcp --debug-logs
```

For local source and service preflight:

```bash
nxd --config <session_config> whoami
nxd validate --config <session_config> <data_product_directory> --debug
echo "nxd validate exit code: $?"
nxd --config <session_config> verify dp --dir <data_product_directory> --json
```

## Failure Triage

- Config/spec parse error: inspect `spec.py`, model imports, service URLs, infra profile names, and transform parameter names.
- Dependency install or init failure: inspect init logs, `requirements.txt`, `pyproject.toml`, `.nxdignore`, package indexes, and flat-layout packaging.
- Startup timeout: inspect init logs and runtime logs before assuming timeout. OOM can appear as startup timeout.
- Transform runtime error: reproduce with the local transform runner, then fix parsing, type conversion, chunking, output writes, or API paging.
- Output write failure: check driver context, service credentials, table/path/index names, schema settings, and promise code.
- Policy or contract failure: switch to `nxd-complying-with-failing-policy`.
- Removed semantic model: restore the deployed model name or launch a versioned product.
- `nxd validate` returns to prompt with little/no output: first check `whoami`.
  If auth says `Not logged in`, validation is NOT RUN even if exit code is 0.
  If auth is valid, rerun without `--debug` and capture the exit code. Treat
  `Service <name> not found` as an infra-profile/service mismatch, not a
  transform bug.

## Patch And Verify

1. Patch the smallest source/config surface that matches the evidence.
2. Re-run local smoke tests or contract checks.
3. Re-run `nxd validate`.
4. If the product is already deployed and only failed/skipped models need another run:

```bash
nxd --config <session_config> run <dp-name> --retry --follow
```

5. If source or deployment config changed, tell the user the launch command:

```bash
nxd launch --dir <data_product_directory> --config <session_config>
```

6. Re-read `describe data-product --compute-status` and relevant logs.

## Guardrails

- Do not jump from a generic startup timeout to a code patch without reading init and debug logs.
- Do not invent `nxd retry` or `nxd reset`; use `nxd run --retry`.
- Do not hide failed validation behind a handover checklist.
- Do not mark `nxd validate` PASS unless `whoami` confirmed auth, validate exited 0, and no validation error/traceback was printed.
- Do not print secrets from logs, profiles, or leased credentials.
