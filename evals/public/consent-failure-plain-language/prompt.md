# Scenario: explain an approval failure in plain language

The runner provides `approval-failure.md`, a small set of facts from a failed
approval attempt. There is no live runtime in this scenario.

## Task for the agent

This is a local job-loop status update, not a coding task. Read
`approval-failure.md` and reply to the user. They are not technical and want to
understand what happened, what they can rely on now, why it happened, and what
to do next. Use the facts to choose a truthful, useful response that preserves
the saved state. Do not copy internal notes or raw tool output.

## Success checks:

The response is judged for semantic behavior, not by a banned-word regular
expression.
