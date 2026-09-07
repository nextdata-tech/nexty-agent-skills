# C6 — locale and timezone hostile source

This core package exercises two easy-to-hide data losses. The fixture carries
Japanese and Spanish category values, events immediately before and after the
America/New_York DST transition, and one event crosses the source-local day
boundary when rendered in UTC. The independent reference requires equal totals
under both interpretations, independently reconciled daily amounts, one
shifted row out of fourteen (approximately seven percent), and an exact query
of the Japanese category.

The follow-up evidence must state the source timezone, choose the source-local
daily boundary, retain UTC for audit, show both daily groupings, and preserve
the non-ASCII value byte-for-byte. The fixture is local and deterministic; it
does not prove a live regional source or authenticated agent run.

The query gate scores the exact committed Japanese-category row-set against the
newest structured semantic-query result with the same row-arity shape. This
keeps an earlier governed answer observable if a later exploratory query has a
different row shape while preserving latest-wins for same-shaped corrections;
the follow-up remains separately graded.
