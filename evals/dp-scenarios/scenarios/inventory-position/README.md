# Inventory position

Core-tier B5 covers a profile-backed inventory result joined to a warehouse
lookup. The generated source has two orphan warehouse identifiers and one
negative quantity. The independent reference preserves both findings so the
operator can distinguish row-level data quality from an infrastructure outage.

The package deliberately keeps credentials profile-only. The runner exposes a
local mock profile with warehouse and position endpoints; evidence must identify
that profile reference, never print the raw secret, and never use a raw bypass.
This is local mock-source E2E coverage, not evidence from a live database
session. B10 remains a chained suffix that requires a retained parent run; this
package does not count as B10 completion.
