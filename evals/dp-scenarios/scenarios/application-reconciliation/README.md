# C2 — the wrong-number dispute

This core package exercises a lineage dispute rather than a transformation
trick. The supplied export has 391 application rows while the dashboard
snapshot reports 353 active applications. The independent reference model
requires the agent to reconcile the 38-row difference as two disjoint causes:
30 non-active status rows (including eight withdrawn tombstones) and 8 active
tombstones. The predicates make double-counting observable.

The follow-up evidence must include the approved definition, a governed query
at the reconciliation-metric grain, the two source/spec clauses that explain
the exclusions, and a decision record. Changing a transform until it prints
353 is not evidence of reconciliation and does not satisfy the package.

The fixture is local and deterministic. It does not prove access to a live
dashboard, production export, or authenticated agent session.

The query gate scores the exact committed reconciliation row-set against the
newest structured semantic-query result with the same row-arity and
distinct-row-count shape. This keeps an earlier governed answer observable if
a later exploratory query has a different result grain while preserving
latest-wins for same-shaped corrections; the follow-up remains separately
graded.
