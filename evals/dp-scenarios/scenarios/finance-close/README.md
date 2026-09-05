# Finance close

Core-tier B2 covers month-end close reconciliation with comma-formatted
amounts, parenthesized negatives, and a missing weekend FX rate. The reference
model converts only rows with an available rate, reconciles in EUR cents, and
keeps the excluded row visible as a warning.

The operator first chooses an exclusion policy for the missing weekend rate and
later reverses it. The later decision supersedes the earlier one, but it cannot
turn an unconverted value into EUR. The package exposes a local mock close
endpoint and grades the agent's evidence JSON artifact against independently
regenerated reference files.

This is local mock-source E2E coverage, not evidence from a real finance
system or an authenticated agent run.
