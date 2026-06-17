# Generated-Code Preflight

## Contents
- Purpose
- Required review
- Offline spec-build check
- Validation result clarity
- README and checklist updates
- What not to claim

## Purpose

Before handing files to the user, review the generated project as if it came
from another agent. Fix what you can, and record anything unresolved in both
`README.md` and `REQUIREMENTS_CHECKLIST.md`.

This step exists because a scaffold can look complete while still containing
demo service URLs, missing packaging entries, vague runtime status, or launch
risks that only surface after the user spends time testing.

## Required review

Check at least:

- **No hidden demo values:** active mesh host, infra profile, service names,
  domain, source repo URL, owner/steward/consumer identities, and registry URL
  are real values or explicit unresolved decisions. Do not leave a demo host as
  the apparent default.
- **Import/package integrity:** `spec.py` can import its shims, shims export
  every DSL name used, `contracts/` is a package when imported as a package,
  `pyproject.toml` ships every module/package needed by `spec.py`, and
  `.nxdignore` excludes only local-only files.
- **Lazy import integrity:** `transform.py` avoids top-level imports for heavy
  runtime-only dependencies such as Spark, torch, sentence-transformers,
  langchain embedding/vector integrations, browser clients, and vendor SDKs not
  needed to build the spec. `nxd validate` imports `transform.py`.
- **Output/pgvector integrity:** if using pgvector, prefer explicit vector
  config from `storage-configs.md`, keep one model per pgvector port, keep the
  model name aligned with the intended table, and record whether the table is
  platform-provisioned or transform-created.
- **Scheduled-write idempotency:** scheduled reruns must have an idempotency
  plan: deterministic IDs/upsert, truncate-then-write, or a clearly approved
  append-only strategy. Do not catch broad database exceptions and assume
  "table exists" unless the exception is checked.
- **Dependency integrity:** `requirements.txt` contains runtime dependencies
  required by the platform; dev-only dependencies stay out of the deployment
  bundle; platform-specific wheels are either verified for the target runtime
  or called out as blockers.
- **Policy readiness:** if a mesh policy may require output promises, add a
  port-level promise or mark that missing promise as an explicit launch risk.

## Offline spec-build check

Before mesh validation, run the same package-loader path that `nxd validate`
uses to import and build the data product spec:

```bash
python - <<'PY'
from pathlib import Path
from nxd.spec.fs.package_loader import data_product_spec_from_file_at_path
data_product_spec_from_file_at_path(Path("spec.py"), Path("."))
print("offline spec-build: PASS")
PY
```

This catches broken shims, bad model imports, missing contract packages, bad
DSL chains, and heavy top-level imports without requiring mesh auth. It does
not resolve live infra-profile services or execute the transform body.

## Validation result clarity

Before handoff, make validation status impossible to misread:

- Confirm auth with `nxd --config=<session_config> whoami`; do not trust exit
  code alone if the output says `Not logged in`.
- Remember that `nxd validate` connects to the `--config` mesh and resolves
  infra-profile services. It is not purely offline/structural.
- Run `nxd validate` and capture the shell exit code immediately after it returns.
- If `--debug` output is noisy or has no final success line, also run the same
  validate command without `--debug` and capture the exit code.
- Record `PASS`, `FAIL`, or `NOT RUN` in the README, never a vague phrase like
  "validate looked okay".
- Include one line of evidence: `exit 0; no validation errors printed`,
  `Service jira-api not found`, `not authenticated`, or similar.
- Treat only the chosen target mesh as target validation evidence. Cross-mesh
  probes are discovery/debug context. If target validation later exits `0`,
  remove or demote stale cross-mesh blockers so the README does not say
  validation cannot pass when it just did.

## README and checklist updates

The README status block must reflect the preflight result:

- `Project files`: local absolute path or artifact-only handoff.
- `Local smoke test`: exact command and PASS/FAIL/NOT RUN.
- `nxd validate`: exact command, exit code, and PASS/FAIL/NOT RUN.
- `nxd launch`: normally NOT RUN unless the user explicitly approved launch.
- `Runtime resources`: CREATED, NOT CREATED, or UNKNOWN with evidence.

`REQUIREMENTS_CHECKLIST.md` must map every unresolved decision to:

- the file to edit,
- the decision needed,
- the likely failure if ignored,
- the command to re-run after fixing it.

## What not to claim

Do not describe a running scheduled Data Product, created vector table, deployed
mesh resource, or passing `nxd validate` unless the command that created or
verified it actually ran successfully.
