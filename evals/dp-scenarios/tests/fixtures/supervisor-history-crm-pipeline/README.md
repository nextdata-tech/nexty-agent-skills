# Supervisor history CRM fixture

## Provenance

Sanitized replay records for the `crm-pipeline` and
`crm-pipeline-current-v2` supervisor workflows. Real workflow, run, request,
definition, release, and capture identifiers are retained for the history tests.

## Retained inputs

- 93 structured MCP calls from turns that carry history evidence.
- Two run and admission records, their publication files, and matching links.
- Three capture digests used by snapshot, association, and path-policy tests.
- Two definition inventories and only the promise metadata used by export tests.
- The supervisor-facts golden file used to protect the legacy artifact writer.

## Trimmed

Agent prose, unused turns and result fields, query rows beyond one shaped sample,
unrelated artifacts and SQLite tables/rows, duplicate workflow blueprints, and
closure source bodies were removed or stubbed. Capture exclusion markers and
file names required by snapshot enumeration remain. Credential-like values and
host-specific paths were omitted.
