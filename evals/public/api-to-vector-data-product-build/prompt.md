# Scenario: API To Vector Data Product Build

Build a Nextdata OS Python data product from a supplied API-to-vector requirements document. The checked-in fixture may use a public SaaS-style issue-tracking example, but this scenario must remain generic and must not depend on customer-specific names, schemas, or credentials.

Constraints:

- Work in a new temporary data-product directory.
- Do not use live secrets.
- Do not launch to a real customer mesh unless the eval runner provides a sandbox mesh.
- Before writing code, create a doc-claim checklist from the source prompt.
- Preserve the source prompt's specifics, including API pagination, nested document parsing, project/date filters, custom input expectation, vector output, chunk size, embedding model, schedule, and local validation.

Expected final artifacts:

- `spec.py`
- `models.py`
- `transform.py`
- local validation or smoke-test script
- dependency file
- `.nxdignore`
- a short handover that says whether `nxd validate` was run and what happened

Success checks:

- No secrets are written into generated source files.
- Input and output service names come from the prompt, not from demo defaults.
- Transform signature names match the input and output-port declarations.
- Output promise and input expectation placement follows Nextdata conventions.
- The agent does not add a schema to the vector output when the prompt says not to.
- Any failed `nxd validate` result is debugged instead of ignored.
