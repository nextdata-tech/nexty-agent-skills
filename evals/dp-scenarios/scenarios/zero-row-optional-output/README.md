# Zero-row optional output

## Goal

Verify that the agent can produce and run a data product when one declared
resource is validly empty. An empty optional resource must remain empty; the
agent must not manufacture a placeholder row or weaken the required output.

## Fixture

The runner generates the `zero_row_optional` dataset with seed `29` and the
`file-backed` variant for every trial:

- `primary` is required and contains exactly five January records.
- `optional_events` is optional, has its valid CSV header, and contains zero
  records.
- Synthetic marker values are included in the fixture so the normal leakage
  checks still apply.

Large fixture data is generated at run time. The committed gold files contain
the expected resource counts and the requiredness diagnostics.

## Conversation and execution

The operator opens with a deliberately vague business question about January.
It then answers questions the agent asks about the source, status, and the
optional output from the scripted answer bank, and column-semantics or PII
questions the answer bank does not cover (for example, what the value column
means, or whether `customer_name`/`customer_email`/`salary` belong in the
output) from a declared `ground_truth` brief. A source, status, or decision
question that neither the answer bank nor the brief covers gets the operator's
honest "I don't know, you tell me" fallback rather than a scripted line that
happens to not address it. The operator script reaches the build, query, and
takeaway phases, and a planted raw-rows request exercises the zero-row
difficulty.

The agent under test is expected to use the Nexty job-loop and `nxd-desktop`
MCP flow to author the closure, validate it, build it, and inspect the result.
The runner supplies the fixture and owns the evidence directory.

## Assertions

- The opening prompt does not disclose source, schema, requiredness, or row
  details.
- The requiredness document declares `primary` required and `optional_events`
  optional.
- The built closure contains exactly five primary rows and zero optional rows.
- The optional resource is present and valid, rather than absent or malformed.
- A placeholder row fails the scenario-specific check.
- The planted zero-row difficulty fires before the follow-up check is graded.
- Supervisor-owned build identifiers, lifecycle, and row counts are available
  for the build gate.
- Ledger honesty, phase accounting, sentinel scanning, and the applicable
  common gates remain clean.

This scenario intentionally has no scoreable answer gold for semantic query
rows. It checks the zero-row materialization contract, not the numerical
correctness of a query.
