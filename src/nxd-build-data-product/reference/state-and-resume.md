# State, Resume, and Open-TODO Ledger

## Contents
- state.json
- open-todos.md
- Resume protocol
- Revisiting a completed step
- Append-a-TODO from anywhere
- Placeholder conventions
- Finalize check

A Data Product build can span multiple sessions. A user may finish discovery in
one sitting, come back later, and pick up at implementation. They may also leave
open questions ("come back to the embedding model choice"). This document defines
an optional lightweight ledger so a build can resume reliably and losslessly.

This ledger is scoped to **a single Data Product build** under
`.context/dp-build/<timestamp>/`.

## state.json

Lives at `.context/dp-build/<timestamp>/state.json`. Write it after every build
step completes and after every TODO is appended.

```json
{
  "run": {
    "id": "20260615-184500",
    "created_at": "2026-06-15T18:45:00Z",
    "updated_at": "2026-06-15T19:12:30Z",
    "workspace": "/abs/path/to/data-product-dir"
  },
  "step": "implementation",
  "completed": ["prerequisites", "discovery", "plan"],
  "in_progress": "implementation",
  "blocked_on": ["TODO #3", "TODO #5"],
  "data_product": {"name": null, "mesh": null, "infra_profile": null},
  "next_action": "Write transform.py for the curated output port."
}
```

`completed` lists steps that produced their primary artifact and were confirmed
by the user. `in_progress` is the step currently being executed. `blocked_on`
references TODO row IDs.

Step IDs (must match the build workflow in `SKILL.md`):

```
prerequisites → discovery → plan → implementation → validation → finalisation
```

## open-todos.md

Append-only log at `.context/dp-build/<timestamp>/open-todos.md`. One row per item:

```markdown
- [ ] **#3** step: `implementation` | item: embedding model choice | blocker: user unsure | added: 2026-06-15 | resolved: -
- [x] **#1** step: `discovery` | item: output service name | blocker: not handy | added: 2026-06-15 | resolved: 2026-06-16 (confirmed snowflake-prod)
```

Closed TODOs are checked off, not removed — preserves the audit trail.

`#N` is a stable ID assigned in order. Use `#N` to reference a TODO from
`state.json#/blocked_on` and from a `TODO` marker left in `spec.py`,
`models.py`, or `transform.py`.

## Resume protocol

When the build starts and `.context/dp-build/` already contains runs:

1. Read every run's `state.json`. List runs sorted by `updated_at` desc.
2. Show the user:
   ```
   Found 1 prior build:
     - 20260615-184500 — last step: implementation, 2 open TODOs
   Resume this build, or start fresh?
   ```
3. **Resume:** load `state.json` and `open-todos.md` for that run. Re-render the
   open-TODO list. Ask: "Resume from the `<in_progress>` step, or revisit an
   earlier step first?"
4. **Fresh:** create a new timestamped run dir.
5. **Branching:** if the user wants to fork (try a different transform approach,
   etc.), copy the prior run dir to a new timestamp and continue there.

## Revisiting a completed step

The user can say "go back to discovery" at any time. The skill:

1. Drops the step from `completed` (does **not** delete its artifacts).
2. Sets `in_progress` to that step, with a `revision: <N>` counter.
3. Re-renders the existing artifact and asks what to change.
4. After the user confirms the revision, re-runs downstream steps that depend on
   this output **only when the change matters** (e.g. changing an input service
   forces `spec.py` and likely `transform.py` to be revisited).

Dependency edges between steps:

```
discovery      → plan, implementation (inputs/outputs, drivers, schemas)
plan           → implementation
implementation → validation → finalisation
```

When a revision happens, surface which downstream steps will need to re-run and
ask the user to confirm before doing so.

## Append-a-TODO from anywhere

Treat any user phrasing like:

- "TODO: ..."
- "let's come back to ..."
- "I don't have ... handy"
- "skip for now"

…as a TODO append. Format the row, write to `open-todos.md`, update
`state.json#/blocked_on`, and continue with a placeholder `TODO` marker in the
relevant file. Never block on it.

## Placeholder conventions

When writing artifacts with unknown values, leave a greppable `TODO` marker,
e.g. `TODO(owner)`, `TODO(infra)`, `TODO(schema)`, `TODO(freshness)`,
`TODO(validation)`, so they are easy to find and resolve at finalisation.

## Finalize check

Before declaring the build done:

1. List every open `[ ]` row from `open-todos.md`. Show them to the user.
2. Ask: "OK to finalise with these still open?" If no, loop back.
3. Write a short `summary.md` listing: completed steps, generated artifacts,
   unresolved TODO count and list, and recommended next entry point if resumed.

A build is never hard-"closed" — the user can resume any time.
