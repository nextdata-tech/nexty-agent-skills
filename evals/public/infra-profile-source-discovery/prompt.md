# Scenario: Discover Source-Aligned Candidates from an Infra Profile (offline)

A platform engineer wants a shortlist of candidate source-aligned data products
for the `northwind-prod` infra profile before their team starts building. The
services in the profile are on a private network that this session cannot reach,
so a colleague has already collected read-only evidence by hand (an S3 listing
with parquet schema fingerprints, Snowflake `SHOW`/`DESCRIBE` output, and the
platform team's architecture note). No mesh is selected in this session and the
`nxd` CLI cannot reach any host.

The profile deliberately contains services that are not data sources, several
credentials pointing at one store, and scratch/demo assets left over from
onboarding — a report that treats all of them as candidates is not usable.

## Task for the agent

Our team is about to start building data products against the `northwind-prod`
infra profile, and I need a candidate shortlist first.

You have the profile at `infra-profiles/northwind-prod.yaml`, plus hand-collected
read-only evidence in `evidence/`:

- `evidence/s3-landing-listing.txt` — object listing plus parquet schema fingerprints
- `evidence/snowflake-show-output.txt` — `SHOW` / `DESCRIBE` / row-count output
- `evidence/data-architecture-note.md` — our platform team's architecture write-up

We also keep environment-specific notes for tooling in the usual places on this
machine; use whatever you find.

This machine has no network route to any of those services and no mesh is
configured, so work entirely from the files above — do not try to connect.

Write your findings to `mesh-assets-northwind-prod.md` in the working directory.
For each candidate data product I need the suggested name, its domain, which
infra-profile service is the input and which is the output, the concrete asset
locators on both sides, whether it is source-aligned or transformed, and your
confidence with the evidence behind it. Tell me plainly which services in the
profile you did not treat as data sources and why.

Everything you want me to look at has to be in that file — I read the report,
not our chat.

## Required artifacts from eval runner

- `infra-profiles/northwind-prod.yaml` — the infra profile (provided).
- `evidence/s3-landing-listing.txt`, `evidence/snowflake-show-output.txt`,
  `evidence/data-architecture-note.md` — offline evidence (provided).

## Success checks

See `checks.json`. The scenario exercises: driver-based classification of
data-bearing vs non-data-bearing services, duplicate-store de-duplication
inferred from shared `account`/`database` attributes, the exclusion rules
(clone tables, `hello*`/personal scratch, demo paths, bucket root), dropping a
service that sits outside every declared architecture flow, grounding every
reported asset in the collected evidence rather than inventing tables,
searching beyond the enumerated evidence files (the domain vocabulary sits in
`nxd-config/skills/nxd-mesh-analyzer/glossary.md`, a customer-extension-path
mirror the prompt never names) instead of filing under `other`, surfacing
ambiguous picks as open questions in the report, and not echoing profile
secrets.

The domain vocabulary and the duplicate-credential, platform-metadata, and
scratch/demo verdicts are deliberately NOT stated in the architecture note —
each must be inferred from profile attributes, flow scoping, or listing
evidence, or found by searching the customer extension path.
