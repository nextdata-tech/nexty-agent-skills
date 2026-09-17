# Generated-Code Preflight

## Contents
- Purpose
- What the checker decides
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

## What the checker decides

`scripts/preflight_check.py` is standard-library only and never imports the
product, so it runs before dependencies are installed. Each check covers a fault
`nxd validate` structurally cannot see, because validate resolves services but
never executes a transform, never executes a contract, and never installs the
package.

| Check | Fault |
|---|---|
| `flat-layout` | several shipped top-level modules with neither `py-modules` nor a root `__init__.py`; `nxd launch` fails at `Installing dependencies` |
| `verify-bind` | a contract whose first parameter is not named after a declared service, input or port; arguments bind by name |
| `verify-weak` | a contract that never references `FAILED` or `WARNING`, so it can only return `PASS` and asserts nothing |
| `version-drift` | `spec.py` and `pyproject.toml` disagree on the version |
| `contract-driver` | a contract wired with the contract-executor driver, which hands it a bare `Context` |
| `surface` | an access/approval modifier or executor config no README line justifies (warns, never blocks) |

It cannot judge two things that `nxd validate` also cannot: whether a `driver=`
names the service's real driver, and whether a glossary term ID exists. Both are
by-hand items below.

## Required review

Run `python3 scripts/preflight_check.py <data_product_directory>` first: it
mechanically decides the flat-layout, verify-bind, verify-weak, version-drift and
unrequested-surface items below, and reports file and line. `surface` findings are
warnings: they ask for a written rationale, not for removal. The remaining items
need judgement.

Check at least:

- **No hidden demo values:** active mesh host, infra profile, service names,
  domain, source repo URL, owner/steward/consumer identities, and registry URL
  are real values or explicit unresolved decisions. Do not leave a demo host as
  the apparent default.
- **Import/package integrity:** `spec.py` can import its shims, shims export
  every DSL name used, `contracts/` is a package when imported as a package, and
  `.nxdignore` excludes only local-only files.
- **Flat-layout packaging guard (binary check):** count the top-level `.py`
  modules that actually ship (those `.nxdignore` does not exclude). If more than
  one ships (the usual `spec`, `models`, `nxd_spec`, `nxd_models`, `transform`
  set), the bundle MUST carry exactly one of: a `[tool.setuptools]` block in
  `pyproject.toml` whose `py-modules` lists every shipped module, or an empty
  `__init__.py` at the product root making it a package. With neither, `nxd
  launch` fails at `Installing dependencies` with `error: Multiple top-level
  modules discovered in a flat-layout`. `nxd validate` passes regardless, so
  validation is not evidence this is handled.
- **Verify substance and binding:** every `contracts/` verify function names its
  service-context parameter after the service it is wired to (`.service(
  service_name="adls", ...)` → `def verify(adls: ...)`), and every body reads the
  data and can return `VerifyResultEnum.FAILED`. A contract that returns `PASS`
  unconditionally, or takes a generic parameter name such as `input` or `ctx`, is
  a defect. Neither fault is reachable by `nxd validate`, which never executes a
  contract. See [promises-contracts.md](promises-contracts.md).
- **No unrequested surface:** every builder call in `spec.py` traces to something
  the user asked for or to a documented platform requirement. Access-control and
  approval modifiers (`.managed_access()`, `.skip_approval_flow()`,
  `.enable_public_access()`), executor `.config(...)` blocks, resource limits and
  provisioning settings change deployed behaviour and must not be invented to
  look thorough. If one is genuinely needed, say why in the README; otherwise
  leave the platform default.
- **Version coherence:** the `version` in `spec.py` and the `version` in
  `pyproject.toml` agree, or the README records why they differ.
- **Driver strings, by eye:** every `driver="nxd:...:x.y.z"` in `spec.py` matches
  what the infra profile declares for that service. Nothing checks this for you.
  `nxd validate` accepts a wrong version *and* a fabricated driver name, exiting 0
  either way, and the static checker cannot resolve a profile it may not have. A
  wrong driver string surfaces at launch or at contract-execution time, long after
  the evidence that would explain it.
- **Lazy import integrity:** `transform.py` avoids top-level imports for heavy
  runtime-only dependencies such as Spark, torch, sentence-transformers,
  langchain embedding/vector integrations, browser clients, and vendor SDKs not
  needed to build the spec. `nxd validate` imports `transform.py`.
- **Output/pgvector integrity:** if using pgvector, prefer an explicit vector
  config (declare the embedding attribute as `vector_embeddings(<dim>)`, not
  `string()`), keep one model per pgvector port, keep the
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

Do not describe a running scheduled data product, created vector table, deployed
mesh resource, or passing `nxd validate` unless the command that created or
verified it actually ran successfully.
