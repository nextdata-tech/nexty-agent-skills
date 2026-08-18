# dp-scenarios — multi-turn data-product scenario suite

Isolated uv project (mirrors `evals/nxd_eval/` and `evals/mcp/`). Everything runs
via `uv run --project evals/dp-scenarios …` — never bare `python`/`pip`.

The suite runs scenarios the way a BI analyst actually works — a vague first
message, corrections mid-stream, disputes after the fact — and grades the runs
mechanically, without trusting the agent's own narrative.

## Scope of this checkout: the T0 tier

T0 is the smoke tier: it runs on every skill, runtime, or generator change, takes
minutes, and spends nearly nothing on models. It contains three scenarios in a
fixed order.

1. **C1 — drift canary.** A frozen kitchen-sink closure that exercises every
   surface the installed skill texts claim to support, probed with
   `nxd-desktop-supervisor check` and one real build. A DRIFT verdict **gates the
   tier**: running the rest against known guidance-vs-runtime drift just
   re-measures the canary's finding at far higher cost.
2. **S5-smoke — zero-row optional output.** A valid resource that materializes no
   rows. Manufacturing a placeholder row fails; so does relaxing the checks that
   still guard required outputs.
3. **S6 — grain trap.** Seeded parent/child data where a naive join fans the
   parent amount out across children. Both answers are fixed numbers under the
   seed, and reconciliation is against a fixture ground-truth control total —
   internal self-consistency is not enough, because self-consistent wrong numbers
   agree with each other.

The T0 tier runs the agent under test only: no judge model, no field-mapper
provider calls, no export. It **does** serve and query, because on lean desktop a
read-only serving session is a local bearer-gated child process — no cluster, no
spend — and the governed-query gate is a mandatory conjunct of the pass rule.
Dropping it would make the grain trap ungradeable in the one tier cheap enough to
run on every change.

## Layout

| Path | Contents |
|---|---|
| `src/dp_scenarios/ledger/` | Evidence ledger, run manifest, ledger lint |
| `src/dp_scenarios/synthgen/` | Seeded fixture generator + gold reference implementation |
| `src/dp_scenarios/mockrest/` | Configurable HTTP mock source |
| `src/dp_scenarios/operator/` | Scripted multi-turn operator runner |
| `src/dp_scenarios/grading/` | Mechanical gate checks and oracles |
| `src/dp_scenarios/canary/` | C1 claims extraction and verdict matrix |
| `scenarios/` | Per-scenario fixtures, operator scripts, gold row-sets |
| `tests/` | Unit tests for the harness itself |

## Fixture hygiene

Large or hostile fixtures are **generated at harness start** from the seeded
generator, not committed. Only small hand-inspectable goldens are committed, and
every committed fixture directory carries its own `.gitattributes` exempting
parsed file types from LFS filtering — a fixture stored as an LFS pointer is
read by the parser as content, and the failure surfaces as a malformed fixture
rather than a missing one. Verify with `git check-attr filter -- <path>`
(expect `unset`) and by reading the staged blob (`git show :<path>`), never the
working tree, which looks correct either way.
