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
  traffic from earlier in the run. The path reaches the stub on its module
  instance, never through `os.environ`: cells run in a thread pool inside one
  process, so a process-global would let two concurrent cells write into one
  another's logs, and the first to exit would unset it under the other.

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

## Review findings, folded in

Code review of the PR found eight defects, all real and all fixed here. Two are
worth recording because they would have surfaced as false failures against
correct closures rather than as crashes:

* **The observation log was a process global.** `run.py` runs cells in a thread
  pool inside one process, so an ordinary A/B benchmark run (two skill sets, one
  scenario) had two stub instances sharing one `os.environ` slot. The second
  cell's assignment redirected the first cell's fixture traffic into the second
  cell's log, so the first cell's verifier failed `wire:observations-recorded`
  on a perfectly correct closure — and the first cell to exit unset the variable
  under the other. The path now reaches the stub on its module instance, which
  `http_stub_server` loads fresh per cell. The env var remains, for the verifier
  subprocess only, and is set on that call rather than process-wide: it was
  previously visible in the agent's own environment, where reading it back would
  have turned "diagnose an unexplained 403" — the task — into a lookup.
  `test_two_concurrent_cells_keep_separate_logs` fails against the old channel
  (cell A's log lands 0 of its 2 requests), verified by reverting.
* **The query reader assumed `[dimension, measure]` column order.** The
  verifier this module was factored out of refuses that assumption in as many
  words — "result column order is a catalog implementation detail, not a
  semantic requirement". Had the supervisor emitted the measure first,
  `float()` on a team name would have raised, every candidate selection would
  have been recorded as "not a two-column answer", and the reconciliation would
  have failed for a reason unrelated to the closure — on the first live run,
  which is exactly where this cell has no prior evidence. Columns now resolve by
  name against the selection, and the fake supervisor in the tests emits the
  order that would break a positional read, so every harness test inherits the
  guard.

The rest: the log directory leaked on a failed stub start; `_uses_dlt_rest`
recognized only the `from`-form import, so `import dlt.sources.rest_api as rest`
was a false accusation against a correct closure (pre-existing, but the shared
gate tripled its exposure); `serve_snapshot`'s failure path skipped the
cooperative `stop` and leaked two file handles; and three message/docstring
defects, including one that named the wrong brief question in text fed to the
judge as authoritative, and one whose failure text promised a floor where the
predicate demanded exact equality.
