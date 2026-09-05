# CRM pipeline

This core-tier B1 package covers a CRM-shaped REST source with pagination,
bearer-token expiry, a deterministic 429 response, tombstone-safe current
records, nested owner PII, and a closed stage enum.

The route table is a real mock-source contract, and the runner hands the agent
an infra profile plus a run-local bearer credential through the declared
environment variable. The follow-up reads the agent's declared evidence JSON
artifact for complete page traversal, retry handling, redacted output, and
stage validation. `gold/crm_pipeline_output.json` is intentionally independent
of the generated fixture, because the CRM rows live in the route table.

This is local mock-source E2E coverage, not evidence from a real CRM account or
an authenticated Claude run. A live qualification still needs the route
counters, the 401/429/200 transport trace, and redacted result surfaces from
the live session.
