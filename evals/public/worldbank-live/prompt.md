# Scenario: Build a Pocket closure against the live World Bank API

The workspace contains a single brief:

- `BRIEF.md` — an author's request for a GDP data product built on the World
  Bank Indicators API, with the four questions they want to ask and the two
  endpoints they named.

There is **no vendored export**. There is no `data/` directory to read, no CSV,
and no sample payload. The source is the live public API, reachable from this
machine, and the closure you build must fetch from it.

## Task for the agent

Read the brief and build the runnable NXD Pocket data product it asks for,
answering the questions it lists.

The API is public — no key, no account, no credential of any kind. Do not
fabricate one and do not invent an auth mechanism it does not use.

Go and look at what the endpoints actually return before you design the models.
The brief's author is explicit that they have been burned by someone modelling
from documentation rather than from the payload, and the shape of these
responses is not what a first guess would predict.

This is an NXD Pocket data product on the local DuckDB store. You have the
installed Nexty skills available; consult them for the platform's connector,
derivation and assertion contracts before authoring, rather than inferring the
mechanism from public dlt examples elsewhere on this machine. Work
autonomously — no user is available to confirm a ruling, which does not make
the ruling optional.

Inspect the live payloads before you author anything. The traps in this
scenario are in the responses, not in this brief.

## Success checks

The eval grades the landed data product, not the narration of it: whether the
questions are answerable from the semantic layer, whether the numbers a
consumer gets back are trustworthy, and whether anything the closure had to
decide — including what it is a snapshot of — is visible to the next reader.
