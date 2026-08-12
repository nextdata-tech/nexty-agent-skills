---
id: 2026-08-12-worldbank-connector-gate-and-redaction
date: 2026-08-12
label: "evals: deterministic connector gate for worldbank-live + api-source secret-redaction regression (NEX-873)"
plugin_version: 0.37.0
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — evals: deterministic connector gate for worldbank-live + api-source secret-redaction regression (NEX-873)

## Notes

No scenario arm can distinguish this change, for two independent reasons, and
neither is the usual "nothing really changed".

**Nothing under `src/` changed.** No skill text, no recipe, no generated
closure shape. An agent authoring a closure before and after this change writes
the identical files; what changed is how a landed closure is GRADED and what CI
proves about the redaction the recipe already teaches. A measured arm would
differ only by agent nondeterminism.

**The scenario this hardens cannot run in CI at all.** `worldbank-live` is
`ci_skip`'d — it needs a live desktop supervisor plus outbound network to
api.worldbank.org — so its new deterministic checker never executes on a PR.
Producing a before/after number would mean spending a live supervisor run to
measure a checker rather than an agent, and the number would say nothing about
the gate's correctness: a run that passes proves the agent happened to build it
right, not that the gate rejects the shape it exists to reject.

What landed:

* `worldbank-live` gained a deterministic checker. It previously stated
  "ingestion goes through dlt's REST connector … FAIL if the transform
  hand-rolls fetching with requests/urllib" as prose only, graded by a judge
  reading a transcript. `authenticated-api-source-build` carried the same
  requirement and the measured NEX-873 benchmark
  ([`2026-08-11-api-source-custom-client-headers`](2026-08-11-api-source-custom-client-headers.md))
  showed what that is worth: BOTH arms imported `rest_api_resources` and
  fetched every row with `requests` beside it. That scenario's gate was
  tightened; worldbank-live's was not, because it had none.
* The gate moved to `evals/tools/api_connector_gate.py` and is now imported by
  both scenarios' checkers. The tightening that prompted this work landed in
  one copy; a second copy is a second thing to tighten, and the copy that gets
  missed is the one that keeps passing hand-rolled closures while reading as
  though it grades them.
* An explicitly empty `deps` in a `deterministic_check` now installs nothing
  instead of falling through to the duckdb default, so `"deps": []` on a static
  checker describes the run that actually happens.
* `affected_scenarios.py` learned that a shared checker maps to its importers.
  It selects on "a skill changed" or "a scenario directory changed", and
  `evals/tools/` is neither — so without the mapping, a future tightening of
  the very gate this entry is about would select zero scenarios and report that
  no eval was affected.

## Evidence

Two carrying test files, both new, both run by the CI gate
(`uv run … python -m pytest evals/tests -q`):

`evals/tests/test_worldbank_connector_gate.py` drives the new checker's
`main()` over synthetic closures: a clean connector closure passes; a hybrid
(connector imported, `requests` fetching beside it), a pure `urllib` loop, and
a hand-rolled loop hidden in a sibling `transform/*.py` are each rejected; a
frozen `https://api.worldbank.org` / `/v2/country` literal and a nested
`secrets["api_source"]["base_url"]` read are rejected; a closure that merely
DOCUMENTS those endpoints in a docstring while reading them from the flat
secrets map passes, as does one asserting against the `NY.GDP.MKTP.CD` code the
payload itself carries. It also pins the two scenarios to one gate
implementation by identity — not by equivalence, since two functions that agree
today satisfy any behavioral assertion and still drift on the next fix — and
pins that the checker is withheld from the agent's workspace and that every
fact the judge is told to grade from is one the checker actually emits.

`evals/tests/test_api_source_secret_redaction.py` is the NEX-873 acceptance
criterion that had no CI coverage: a credential must not reach diagnostics or
error reporting. It executes the `_redact` recipe EXTRACTED from
`reference/api-source.md` (a copy in the test would drift from the doc
silently), proves `from None` suppresses the chained original with the leaking
control arm beside it, pins that api-source.md and database-source.md really do
share the one exemption list they claim to share, and then proves both halves
on the wire against the scenario's own stub and the pinned `dlt==1.28.2`: a
real 401 through the connector never carries the bearer token, and a real
`requests` probe leaks its query-string credential *before* redaction and not
after — with `base_url` and the endpoint path still readable, since a 404 that
names neither is undiagnosable.
