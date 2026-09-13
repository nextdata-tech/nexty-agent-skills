# Job loop: explain a declined approval

The fixture describes a local data-product request whose approval did not
proceed. The agent must turn that state into a useful conversation update.

## Task for the agent

Read `approval-status.json` and give the user a short, friendly status update
for a non-technical audience. Explain what happened, what it means for the
requested report, and what the user can do next. This is a conversation update,
not a coding task.

## Success checks

The update should be clear about the user's choice, the work that did not start,
and the next action without exposing internal workflow details.
