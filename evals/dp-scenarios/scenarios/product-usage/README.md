# Product usage

Full-tier B8 scenario (`tier: full`, `run_order: 15`) for a weekly
active-accounts and feature-adoption bridge over a rolling-window
product-usage-event source. It stages a single late-arrival lookback
decision after the operator observes the first publication, then ties final
query evidence to a same-workflow refresh.

**This package cannot run live yet.** `scenario.yaml` declares
`live_blocked_reason`, and `scenario.live_blocked()` / the live-dispatch entry
points (`scripts/run_local_claude.py`, `runner/cli.py --mode live`) refuse to
start it. See "Scope and limits" below for exactly what is and is not
implemented, and `/Volumes/PRO-G40/.codex/b-series-design/design-B8.md` for
the full design this package follows.

## Fixture and output

The deterministic `product_usage` fixture is a hidden JSON source with three
served states (`usage_events_v1/v2/v3` plus a paired
`usage_export_status_v1/v2/v3` control document per state), consumed the same
way `crm_pipeline_drift`'s stateful source is: via `source_tables`, moved into
the runner's private oracle before the agent sees it. This package uses only
v1 and v2; v3 (and the shared dataset's B8b short-delivery day) exist so the
fixture is ready for a future B8b package without re-deriving its counts.

Every ordinary day is 100 accounts x 3 features (`search`, `dashboard`,
`export`) x 2 events = 600 events, timestamped every 144 seconds from
midnight so the day's last event lands at 23:57:36Z. `v1` serves
2024-04-08 (with accounts 201-300 standing in for that one day) through
2024-04-21: **8,400** events. `v2` serves 2024-04-09 through 2024-04-22 with
the usual accounts 1-100, plus 30 late-arriving events dated 2024-04-19
through 2024-04-21 from 30 new accounts (ten exclusively tied to each
feature): **8,430** events. `v3` adds 2024-04-23 with only 300 of the 600
events a full day from new accounts 301-350 would produce (the fixture's
short-delivery day, for B8b): **8,130** events. `event_id` is globally stable,
so the correct v1-to-v2 read is a plain union by id: 8,400 + 8,430 - 7,800
shared ids = **9,030** landed events.

The declared output shape is `weekly_active_accounts` (`week_start`,
`active_accounts`) and `weekly_feature_adoption` (`week_start`, `feature`,
`active_accounts`), one governed model each rebuilt from the append-only
landed `usage_events`. The independently generated gold has three weekly
rows -- `(2024-04-08, 200)`, `(2024-04-15, 130)`, `(2024-04-22, 100)` -- and
nine feature-adoption rows (each feature at 200/110/100 for the same three
weeks: every account touches every feature on its day, but each week's *new*
accounts are split three ways, ten per feature, so the per-feature rise is a
third of the per-week rise). `usage_export_status` is a one-row model that
must reflect the fixture's own as-of clock and expected daily count, not the
host wall clock. Every event carries an `actor` object (`user_id`,
`display_name`, `email`) that is out of scope; a seed-derived sentinel is
confined to account `ACC-0001`'s `actor.email` in every state.

### A resolved design ambiguity

The design's fixture table says the 30 late events use "ten new accounts per
feature" without saying whether that is one shared pool of ten accounts or
three disjoint pools of ten. This package resolves it as **three disjoint
pools of ten (30 distinct new accounts)**: only that reading reproduces the
design's own stated numbers together -- an overall weekly rise of 30
(100 -> 130 accounts) alongside a per-feature rise of only 10 (100 -> 110),
which requires the per-feature pools to not overlap with each other.

## Conversation and evidence

The opening ask is one business sentence naming no source or mechanism, as
the answer-sheet loader requires. Turn 2 states the individual-person
exclusion (the design's PII-fairness requirement is delivered deterministically
here rather than left to be asked about). Source answers, on ask, describe the
usage-event and export-status exports and the account/feature/actor fields,
without ever naming "late," "window," "lookback," or `event_id` before the
plant fires. After the first observed Published run, a `back_after_lunch`
event ("I'm back the next morning; did it finish, and can you update the
numbers?") delivers the refresh request; only after that event does the
`usage_events_lookback` decision become answerable ("reread at least the
prior three calendar days, deduplicate by `event_id` against already landed
keys, retain older landed history").

The follow-up evidence contract asks for generic publication, refresh, query,
and decision references -- no decision IDs, decision values, or numeric gold.
The grader (`src/dp_scenarios/followups/product_usage.py`) ties the initial
and refreshed releases to one workflow via runner-owned supervisor history
(publication history, query history, and the approved-decision blueprint
snapshot), the same evidence class B7/`mrr_waterfall` uses; it never trusts
the agent's own evidence-artifact claims. It also scans the refreshed and
initial captures' `models.py`/`spec.py`/`transform/*.py` for the forbidden
`actor`, `actor__*`, `user_id`, `display_name`, and `email` fields.

## Scope and limits

**This package is offline-testable only.** The design's own verdict
(`design-B8.md` section 1) is that nxd's trusted readback currently rejects a
transform whose `transform_state` is stateful
(`readback/stateful_unsupported`), and workflow-v2 admission currently
enrolls only `new_build`, not a rebuild/refresh of an existing workflow
(NXD U1/U2). `scenario.yaml`'s `live_blocked_reason` and
`scenario.live_blocked()` refuse a live run until that upstream work lands;
this package's dataset, reference oracle, committed gold, and follow-up
grader are exercised only by this repository's own test suite
(`tests/test_scenario_product_usage.py`, `tests/test_followup_product_usage.py`).

Two further simplifications, both made to stay inside what is testable
without a live session or new harness infrastructure:

- **No mock REST route.** The design specifies a live `/usage/events` +
  `/usage/export_status` API profile with `occurred_after` filtering
  (design's H1 work package). That filtering, and the request-log evidence a
  live run would need to prove a filtered refresh actually happened, are out
  of scope here. This package instead uses a hidden-JSON `source_tables`
  fixture, the same mechanism `crm_pipeline_drift` and `mrr_waterfall` (CSV)
  use, and declares no `route_table`. The follow-up grader's
  `b8_filtered_refresh_unproven` finding is therefore **always present** --
  there is no runner-owned evidence a filtered reread happened, so this
  package can never report `passed: true`, live or replayed, until H1 lands.
- **No compiled output-identity promise check.** `mrr_waterfall`'s follow-up
  additionally parses an `on_verify` script's AST to confirm a real,
  non-vacuous identity check ran. This package's evidence contract stays
  simpler (release row counts, weekly/feature-adoption query rows, the
  decision ruling, and the person-field scan) since B8's own design does not
  specify that script's shape the way B7's design did.
- The `S-B8` skill change (updating `incremental-transforms.md` and
  `api-source.md` for event-time lookback via dlt endpoint params) is
  deliberately not part of this package; see the top-level task that produced
  it.

The package verifies deterministic fixture generation, package loading, and
local grading contracts. It does not establish a live product-usage API, nxd
workflow-v2 rebuild admission, or agent qualification.
