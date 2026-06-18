# Nexty Skill Evals

Use these scenarios to measure how fast and reliably an LLM can complete Nextdata OS data-product work with and without the skill pack.

`evals/` is a measurement harness, not customer-facing skill content. Keep shared scenarios generic. Put customer-specific, commercial-demo, or proprietary artifacts in `evals/private/`, which is ignored by git.

The target comparison is:

| Variant | Purpose |
|---|---|
| `no_skills` | Baseline: general agent with the public docs + examples, no curated skills |
| `current_pack` | Existing shipped skills |
| `candidate_pack` | Existing skills plus proposed workflow primitives |

The baseline is deliberately **not** a blind agent. Every run — baseline
included — is given the public platform docs (via `WebFetch` against
`<docs-base>`, default the public demo mesh) and a read-only copy of the
`nextdata-public-examples` repo. The only thing that varies between variants is
the curated skill set, so a measured lift is attributable to the skills, not to
withholding context from the baseline.

## Directory layout

- `public/` — generic scenarios safe to share across companies.
- `templates/` — reusable scenario templates for private/customer evals.
- `private/` — local-only scenarios with customer names, schemas, transcripts, logs, or commercial-demo material. Do not commit these.

## KPI-blocking private scenarios

The harness exists, but a customer/commercial KPI is not unblocked until the relevant private scenario has real artifacts. A commercial-demo eval should be created from `templates/artifact-required-data-product-build/` inside `evals/private/` and must not be counted until source requirements, schemas, workflow evidence, and acceptance checks are added.

Record these metrics for every run:

| Metric | Definition |
|---|---|
| `elapsed_minutes` | Wall-clock time from first action to final answer |
| `assistant_turns` | Assistant responses before completion |
| `tool_calls` | Shell/read/write/browser/API calls |
| `error_count` | Failed commands, invalid CLI flags, broken generated code, failed validation |
| `course_corrections` | Times the agent had to reverse a wrong assumption |
| `tokens` | Total token usage if the runner exposes it |
| `success` | Whether the scenario-specific checks pass |
| `variance_notes` | Differences between repeated runs of the same variant |

## Running the suite (automated)

`run.py` runs the whole loop — install a skill-set, drive a headless agent over
each scenario with its `fixtures/`, then grade the transcript with an LLM judge
against the scenario's `checks.json`. The same command runs locally and in CI.

Prerequisite: the `claude` CLI must be installed and authenticated (`claude
setup-token` or an API key). The runner sets no credentials of its own.

```sh
# List skill sets and scenarios.
python3 evals/run.py --list

# Run one scenario with one skill-set (fast iteration).
python3 evals/run.py --skill-set current_pack \
  --scenario pgvector-embedding-type-failure

# Run the full public suite across all skill-sets, write a JSON report.
python3 evals/run.py --report eval-report.json

# Cheaper smoke run.
python3 evals/run.py --skill-set current_pack \
  --agent-model sonnet --judge-model sonnet
```

`run.py` exits non-zero only on infrastructure failures (a run that could not be
graded). A graded `FAIL` is a measured signal, not a CI break — pass rates are
tracked, not gated.

### Authoring a scenario

Each scenario directory holds:

- `prompt.md` — the task shown to the agent. **Never leak the expected fix or
  known failure mode here.**
- `fixtures/` — the artifacts a real session would have: mock `nxd` CLI output
  (`*.txt`) and any source `data_product/` directory. Copied into the agent's
  workspace. These are agent-visible, so they must read like raw artifacts, not
  hints.
- `checks.json` — the structured success checks the judge grades against
  (`{"name": ..., "checks": [{"id", "check"}]}`). **Judge-only; never shown to
  the agent.** This is where expected reasoning is spelled out.

### CI

`.github/workflows/evals.yml` runs this suite, but is **disabled by default**
(manual `workflow_dispatch` only, not wired to push/PR) until a Claude
credential is provisioned in CI. Run the suite locally meanwhile.

## Running a scenario (manual reference)

The manual loop the runner automates, for reference:

1. Start from a clean checkout or temporary working directory.
2. Install the selected skill set from `skill-sets.yaml`.
3. Give the agent only the scenario prompt and artifacts named in the scenario.
4. Capture transcript, changed files, command output, and final answer.
5. Grade with the scenario's success checks.

Do not leak the expected fix or known failure modes into the agent prompt. The point is to measure whether the skills make the agent discover the right path faster.
