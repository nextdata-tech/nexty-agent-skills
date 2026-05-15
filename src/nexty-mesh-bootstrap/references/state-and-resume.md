# State, Resume, and Open-TODO Ledger

The wizard is multi-session. A user may finish Phase 2 in one sitting, come back two days later, and pick up at Phase 5. They may also leave open questions ("come back to Azure DevOps repos"). This document defines the protocol so resume is reliable and lossless.

## state.json

Lives at `.context/mesh-bootstrap/<timestamp>/state.json`. Written after every phase completes and after every TODO is appended.

```json
{
  "run": {
    "id": "20260506-184500",
    "created_at": "2026-05-06T18:45:00Z",
    "updated_at": "2026-05-06T19:12:30Z",
    "workspace": "/abs/path/to/workspace"
  },
  "phase": "cloud-footprint",
  "completed": ["prepare", "domain-map"],
  "in_progress": "cloud-footprint",
  "blocked_on": ["TODO #3", "TODO #5"],
  "mesh": {"name": null, "config": null, "mode": "blueprint"},
  "next_action": "Confirm proposed infra-profile list with user."
}
```

`completed` lists phases that wrote their primary artifact and were confirmed by the user. `in_progress` is the phase currently being executed. `blocked_on` references TODO row IDs.

Phase IDs (must match exactly):

```
prepare → domain-map → cloud-footprint → identity → collect → normalize → mesh-map → candidates → drafts → validate
```

## open-todos.md

Append-only log. Format — one row per item:

```markdown
- [ ] **#3** phase: `cloud-footprint` | item: Azure DevOps repo list | blocker: not handy | added: 2026-05-06 | resolved: -
- [x] **#1** phase: `domain-map` | item: Commercial subdomains | blocker: user unsure | added: 2026-05-06 | resolved: 2026-05-08 (added US/Intl/Japan)
```

Closed TODOs are checked off, not removed — preserves the audit trail.

`#N` is a stable ID assigned in order. Use `#N` to reference a TODO from `state.json#/blocked_on` and from any artifact (e.g. `mesh-map.md` may have a "Gaps" section that lists `#3`, `#5`, `#7`).

## Resume protocol

When the wizard starts and `.context/mesh-bootstrap/` already contains runs:

1. Read every run's `state.json`. List runs sorted by `updated_at` desc.
2. Show the user:
   ```
   Found 1 prior run:
     - 20260506-184500 — last phase: cloud-footprint, 5 open TODOs
   Resume this run, or start fresh?
   ```
3. **Resume**: load `mesh-inventory.json`, `state.json`, `open-todos.md` for that run. Re-render the open-TODO list. Ask: "Resume from `<in_progress>` phase, or revisit a different phase first?"
4. **Fresh**: create a new timestamped run dir.
5. **Branching**: if the user wants to fork (try a different domain split, etc.), copy the prior run dir to a new timestamp and continue there.

## Revisiting a completed phase

The user can say "go back to domain map" at any time. The wizard:

1. Drops the phase from `completed` (does **not** delete its artifacts).
2. Sets `in_progress` to that phase, with a `revision: <N>` counter.
3. Re-renders the existing artifact and asks what to change.
4. After the user confirms the revision, re-runs downstream phases that depend on this output **only when the change matters** (e.g. renaming a domain forces Phase 7's mesh-map regen).

Dependency edges between phases:

```
domain-map  → mesh-map, candidates, identity (boundary check)
cloud-footprint → mesh-map (infra profiles), drafts (infra_profile field)
identity    → mesh-map (ownership), candidates (owner/steward)
collect     → normalize → mesh-map → candidates → drafts → validate
```

When a revision happens, the wizard surfaces which downstream phases will need to re-run and asks the user to confirm before doing so.

## Append-a-TODO from anywhere

The wizard treats any user phrasing like:

- "TODO: ..."
- "let's come back to ..."
- "I don't have ... handy"
- "skip for now"

…as a TODO append. Format the row, write to `open-todos.md`, update `state.json#/blocked_on`, continue with a placeholder. Never block on it.

## Placeholder conventions

When writing artifacts with unknown values, use these placeholders so they're greppable:

- `TODO(domains)` — Phase 2 unknown
- `TODO(cloud)` — Phase 3 unknown
- `TODO(identity)` — Phase 4 unknown
- `TODO(owner)`, `TODO(infra)`, `TODO(schema)`, `TODO(freshness)`, `TODO(validation)` — already used by Phases 6–10 and `inventory-schema.md`

## Finalize check

Before declaring the run "done" (Phase 10):

1. List every open `[ ]` row from `open-todos.md`. Show them to the user.
2. Ask: "OK to finalize with these still open?" If no, loop back.
3. Write `summary.md` listing: completed phases, generated artifacts, unresolved TODO count and list, and recommended next-session entry phase.

A run is never "closed" — the user can resume any time.
