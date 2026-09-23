---
id: 2026-09-23-codex-reviewer-diagnostics
date: 2026-09-23
label: "Codex reviewer deadlines and timeout diagnostics reflect observed state"
plugin_version: 0.52.1
status: NO_EVAL
scenarios: []
record: null
---
# Benchmark — Codex reviewer timeout and reader diagnostics

## Notes

Harness-only timeout and privacy change. A 60-second timeout based on a
parent's `pendingInit` snapshot incorrectly aborted an active Codex reviewer,
so the guard was removed. A matching completed `wait` with a terminal child
result now clears the reviewer deadline, so post-review work is not blamed on
the child. Timeout details also include wait count, whether its target matched
the spawned child, an allow-listed child status, and whether child activity was
observed. Root-turn timeout details include elapsed/idle time and a value-free
reviewer phase, and the runner-owned review reader writes metadata-only trace
summaries instead of retaining paths or returned file contents. These changes
affect interruption diagnosis and trace retention, not scenario behavior or
gradable skill quality, so there is no meaningful score-based before/after
comparison. The same adapter hardening also handles Codex app-server `error`
notifications: retryable notices remain nonterminal, only exact root
thread/turn matches affect classification, terminal notices get a short grace
for the authoritative turn result, and provider payload text is not retained.
The follow-up hardening treats that grace as an idle bound while exact root
progress continues, refuses to clear retry-pending state on id-less or child
events, and suppresses raw stderr and exception text whenever it classifies as
a provider failure. Reviewer diagnostics now reset on a later spawn and clear
only the individual child whose terminal result was observed; nested HTTP status
fallbacks and root-thread preservation are covered explicitly. App-server
progress matching uses thread/turn identities from the installed protocol
schema, including the nested identity on `turn/started`; mixed reviewer waits
complete only children with their own terminal result. Safe adapter-generated
provider variants remain in diagnostics while raw stderr and exception text do
not. Each completed wait snapshot is filtered to the matching spawn before it
is translated into an Agent result, so one child's success or failure cannot
be attributed to another. A wait may supply a missing receiver id only when a
single unresolved spawn maps to a single wait target. Only a typed stdout EOF
is reported as process exit; malformed protocol frames retain their own
diagnosis even when a retryable provider notice preceded them. Receiver ids
already associated with a spawn or wait cannot be rebound to a later id-less
spawn, and multiple unresolved id-less spawns remain ungraded. Aggregate wait
status is not projected onto each child; only that child's state determines its
outcome. Raw turn-scoped notifications are filtered by exact root thread and
turn before parsing, non-retryable provider errors remain reportable even when
the terminal frame says completed, and startup/EOF diagnostics never serialize
raw provider messages or stderr. Empty terminal errors no longer become the
literal string `null`.

## Evidence

- `evals/dp-scenarios/tests/test_runner_codex_adapter.py` verifies stale
  `pendingInit` does not shorten the configured reviewer deadline, a terminal
  matching wait clears it, timeout details classify matching versus mismatched
  wait targets, diagnostics omit child identifiers and messages, app-server
  error notifications are classified without provider payload text, later root
  progress clears retry-pending state only with exact root identity, the
  terminal-error grace follows exact root activity and is capped by the parent
  deadline, provider-classified stderr is omitted while safe adapter diagnoses
  are retained, mixed multi-reviewer waits preserve unfinished child deadlines
  and keep parsed results scoped per child despite aggregate wait failures, a
  single id-less spawn can be completed only by a fresh unambiguous singleton
  wait, a mixed known/id-less wait remains scoped in deadline tracking and
  result parsing, stale receiver ids cannot clear a new review deadline, ambiguous
  id-less spawns remain ungraded, child-thread messages/tools are ignored,
  startup errors are redacted, completed terminals preserve non-retryable
  provider diagnosis, null terminal errors are omitted, malformed protocol data
  is not mislabeled as process exit, repeated reviewer spawns receive fresh
  diagnostics, nested unknown error variants use safe HTTP status, and a queued
  terminal result wins a deadline race.
- `evals/tests/test_desktop_stdio.py` verifies reader traces include safe
  operation/error/size metadata without paths or file contents.
- The latest B1 resume remains ungraded: its delegated reviewer stayed in
  `pendingInit` without child tool activity through the 300-second reviewer
  deadline, and the turn emitted no terminal result. This is not a scenario
  pass.
