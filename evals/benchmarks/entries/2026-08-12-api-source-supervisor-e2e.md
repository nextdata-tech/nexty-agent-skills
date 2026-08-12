---
id: 2026-08-12-api-source-supervisor-e2e
date: 2026-08-12
label: "evals: publish/resume/describe/query E2E for an authenticated REST closure (NEX-873 AC6/AC7)"
plugin_version: 0.37.0
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — evals: publish/resume/describe/query E2E for an authenticated REST closure (NEX-873 AC6/AC7)

## Notes

`NO_EVAL`, and the reason is worth stating precisely rather than as a formality:
**this entry adds a scenario that cannot run in CI, and it has not yet been run
live.** Nothing under `src/` changed, so there is no skill behavior to measure
either way.

NEX-873's last two acceptance criteria asked for a Desktop/Cowork E2E that
generates a fresh closure, verifies it reaches the header-required fixture
through dlt, and runs the prescribed self-check → publish → resume → describe →
governed-query path. `authenticated-api-source-build` proved only the first
half: a closure MATERIALIZES against the fixture. It never published, so
nothing covered the failure modes publication introduces on its own — an
endpoint left in a companion file the definition snapshot does not carry, a
header assembled from a secret the profile never declared, a base_url read from
an environment the supervisor does not set. Each of those ingests correctly
under the author's hand and fails once published.

`authenticated-api-source-supervisor` closes that. It needed three things the
runner could not previously do:

* **The supervisor and the HTTP fixture in one cell.** They were mutually
  exclusive branches in `run_one`, so a desktop cell could not have an upstream
  API. The fixture now wraps the whole desktop branch, so it is still bound on
  the same port when the verifier re-serves — the agent pinned that port into
  `infra-profile.yaml`, and restarting the stub in between would point the
  published definition at a closed socket, which reads as a broken closure.
* **A scenario-chosen harness verifier.** `check_job_loop.py` was a fixed
  filename; a second desktop shape had no way to bring its own.
* **A request log the fixture writes to a file.** The verifier is a separate
  process, so in-memory `OBSERVED` cannot answer "did the closure the
  supervisor materialized reach this fixture, carrying the required header?".
  The log is truncated immediately before the re-serve, so what it holds
  afterwards belongs to the published definition — without that boundary, a
  definition that 403s on every request still passes on the agent's successful
  traffic from earlier in the run.

The verifier grades: the published-run chronology in the supervisor's own state
database, a re-serve of the published snapshot from its durable key, the
fixture's observed traffic during that re-serve, the described catalog, and a
governed query whose per-team check counts are reconciled against what the
fixture itself serves — computed from the fixture's payload, never hardcoded.

**Writing the tests found a real hole in the verifier**, which is the strongest
thing this entry has to report. A closure with the User-Agent frozen into
`transform/main.py` passed every fact: it sends exactly the right header, so
the fixture sees a perfect request and every observation-based check passes,
while the closure is one profile change away from 403ing everywhere. The only
check that can see it read the source, and the only implementation of it lived
in the build scenario's checker. It moved to `evals/tools/api_connector_gate.py`
and both scenarios now emit `header:built-from-secrets` — the same
one-gate-two-scenarios argument as
[`2026-08-12-worldbank-connector-gate-and-redaction`](2026-08-12-worldbank-connector-gate-and-redaction.md),
except here the missing copy was found by a test rather than by a benchmark.

To run the cell live (supervisor binaries required, not in CI):

```sh
export EVAL_DESKTOP_SUPERVISOR_DIR=~/.nxd/bin
export EVAL_DESKTOP_PYTHON=~/.nxd/desktop-venv/bin/python
python evals/run.py --scenario authenticated-api-source-supervisor \
  --skill-set current_pack --agent-backend claude
```

## Evidence

`evals/tests/test_api_source_supervisor_e2e.py` is the carrying test file, and
it covers two layers.

The wiring: the scenario resolves both runtimes; the stub is borrowed rather
than copied and the borrower ships no copy of it; the named verifier is run and
a renamed one is an infrastructure error rather than a pass; the request log
reaches another process, records refused requests too, truncates rather than
unlinks on reset, stays outside the workspace (in it, the agent could read back
the headers its own failing requests carried, turning "diagnose an unexplained
403" into a lookup), and is off entirely for the scenario that did not opt in.

The verifier's own decisions, driven end-to-end through `harness_mode` against a
faked supervisor: a correct published product passes every fact; traffic from
before the reset cannot carry the wire claim; a resume that never ingests, a
missing published run, a catalog with no team dimension, wrong per-team numbers
from a healthy endpoint, a hand-rolled published closure, and the hardcoded
header above are each rejected, and the last is rejected by exactly one fact.

What no test here covers is the supervisor's actual CLI behavior. That contract
is inherited verbatim from `check_job_loop.py`, which live runs exercise, and it
is the part a first live run of this cell would be testing.
