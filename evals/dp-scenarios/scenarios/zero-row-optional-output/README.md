# Zero-row optional output

Smoke-tier scenario (`tier: smoke`, `run_order: 1`) for valid empty-resource
materialization. It checks that an optional resource can be present, valid, and
empty without causing the agent to manufacture a placeholder row or weaken the
required output contract.

## Scope

The operator asks how January went and whether anything needs attention. The
agent must build the required January result while preserving the distinction
between a valid empty optional resource and a missing or malformed resource.
The optional resource is not an error and must not be padded to make it look
non-empty.

## Conversation

The answer sheet drives a seven-turn arc through source review, anomaly
questions, confidence checks, build, query, and a plain-language takeaway.

- **Turn 5** injects the required `optional_zero_row` event and asks the agent
  to inspect the optional event records. The event must fire before the
  follow-up check is graded.
- The scripted answers identify the required five-row primary result and the
  valid empty optional resource.
- The ground-truth brief answers field-semantics and PII questions when the
  answer bank does not. It requires `customer_name`, `customer_email`, and
  `salary` to stay out of the output.

The opening message is deliberately vague and is checked for source, schema,
requiredness, resource, and row vocabulary.

## Fixture

The runner generates `dataset: zero_row_optional` with seed `29` and variant
`file-backed` for each trial:

- `primary` is required and contains exactly five January records.
- `optional_events` is optional, has a valid CSV header, and contains zero data
  rows.
- Synthetic marker values remain in the fixture so common leakage checks stay
  active.

Large fixture data is generated at run time. The committed gold files contain
the expected resource counts and requiredness diagnostics:

| Resource | Required | Expected rows |
|---|---:|---:|
| `primary` | yes | 5 |
| `optional_events` | no | 0 |

## What is actually driven

`tests/test_scenario_zero_row_optional.py` exercises file-backed materialization
and the real `optional_required_outputs` follow-up checker. It verifies that
the requiredness document is read from the named `requiredness.json` path, that
row counts use the declared row-count oracle when supplied, and that malformed,
absent, placeholder, and required-resource cases fail distinctly. It also
regenerates the fixture and checks the required plant evidence boundary.

This package's tests do not invoke a live agent, supervisor build, or governed
semantic query. They validate the artifacts and checks that a live run would
populate. Supervisor-owned build identifiers are handled by the common build
gate; resource counts are checked by this follow-up and ledger lint.

## Execution

Run the package tests from `evals/dp-scenarios/`:

```bash
uv run pytest tests/test_scenario_zero_row_optional.py -q
```

An optional local agent trial can exercise the conversation and desktop
handover:

```bash
uv run --project evals/dp-scenarios python evals/dp-scenarios/scripts/run_local_claude.py \
  --scenario zero-row-optional-output \
  --epochs 1 \
  --output-dir /tmp/dp-scenarios-zero-row-optional-output
```

Treat a result as evidence only when the required plant is observed and the
requiredness document plus resource-count evidence are examined.

## Goal

Keep `primary` required with exactly five rows, keep `optional_events` present
and valid with exactly zero rows, and preserve the requiredness declaration. A
placeholder optional row, absent optional resource, malformed CSV, or missing
required resource must fail.

## Assertions (`gates.follow-up.kind: optional_required_outputs`)

- The opening prompt does not disclose the source, schema, requiredness, or row
  details.
- The named requiredness document declares `primary` required and
  `optional_events` optional.
- Resource counts match the independent gold: five primary rows and zero
  optional rows.
- The optional CSV is present and valid. A placeholder row fails, and an absent
  or malformed resource is not treated as an empty valid resource.
- The required `optional_zero_row` plant fires before the follow-up is graded;
  an event id without fired evidence is insufficient.
- Supervisor-owned build identifiers are available for the build gate. The
  common ledger, phase, sentinel, and other applicable gates remain clean.
- Missing or malformed requiredness, count, or plant evidence is
  `not-examined`, never a silent pass.

This scenario has no scoreable semantic-query answer gold. It checks the
zero-row materialization contract, not the numerical correctness of a query.

## Limitations

- **File-backed variant only.** The pipeline-shaped non-materialization half is
  not exercised here.
- **No live agent or hosted E2E is claimed by the package tests.** They verify
  generated fixture files, evidence parsing, and deterministic checks rather
  than a completed agent build and query.
- **Requiredness is declaration-driven.** The package checks the named
  requiredness document against scenario-declared roles; it does not infer
  requiredness from whether a resource happens to contain rows.
- **The row-count oracle has precedence when supplied.** Direct closure CSVs
  are a fallback for this follow-up, not a reason to disregard an explicit
  supervisor or runner count oracle.
- **Repeatability is declared, not measured.** `scenario.yaml` declares five
  deterministic epochs and build-only Wilson certification, but the package
  tests do not run five live agent trials.
