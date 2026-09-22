# Scenario: Build a closure against an authenticated REST API

The workspace contains one brief: `BRIEF.md`. It describes a small internal
metrics service that requires a bearer token on every request — not a public,
no-auth API.

`ENDPOINT_URL` (a file at the workspace root) names the base URL to build
against: a local stub the eval runner starts for this run, standing in for the
real service the brief describes. Treat the URL exactly as if it were the
brief's own hostname — you have no reason to know it is a stub, and nothing
about how you build the closure should depend on that fact. The service exposes
exactly the two endpoints and the one credential the brief names; there is
nothing else to discover by probing it.

## Task for the agent

Read the brief and build the runnable NXD desktop data product it asks for. The
bearer token is supplied in `BRIEF.md` exactly as a user would paste it into
chat — use it as the live credential, entered into `infra-profile.yaml`, never
narrated back in chat or written into any committed source file.

Go and look at what the endpoints actually return before you design the
models, the same way you would for any connector you have not used before.
After consent, create only the closure-local `connectivity_check.py`, run it
against both configured endpoints with the supplied runtime credential, and
read both returned payloads before writing `infra-profile.yaml`, `.gitignore`,
`SENSITIVE`, `spec.py`, `models.py`, `transform/`, or any other closure file.
The brief specifies bearer authentication; dispatch on `auth_type` and reject
unsupported modes, but do not add speculative API-key or OAuth flows.

This is an NXD desktop data product on the local DuckDB store. Consult the
installed Nexty skills for the platform's connector, derivation and assertion
contracts before authoring, rather than improvising the ingestion mechanism.
Work autonomously — no user is available to confirm a ruling, which does not
make the ruling optional.

## Success checks

The eval grades the landed closure, not the narration of it: whether the
credential reaches the request as a real `Authorization` header and never as a
literal in source, whether the connector goes through the platform's declared
REST mechanism rather than a hand-rolled HTTP loop, and whether the two
endpoints' data lands correctly including the parts of the payload a first
guess would get wrong.
