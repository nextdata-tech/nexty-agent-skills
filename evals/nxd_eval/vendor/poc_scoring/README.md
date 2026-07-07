# Vendored PoC scoring primitives

`harness/scoring.py` and `harness/structure_check.py` are copied **verbatim**
from the text-to-SQL PoC harness. They are the low-level deterministic-execution
primitives (`score_accuracy`, `rows_equal`, `_norm_rowset` building blocks,
`_NUMERIC_TOL`, fan-out `verdict`) that `evals/cross-dp-joins/harness/score.py`
loads at import time.

## Why vendored

`score.py` resolves these modules from `T2SQL_POC_ROOT` (env override) or a
hardcoded worktree path. That PoC tree is not present on every checkout, so a
bare `import score` fails. Vendoring the two stdlib-only primitive modules here
lets the eval project load `score.py` self-contained: `nxd_eval.scoring` points
`T2SQL_POC_ROOT` at this directory before loading `score.py`.

The single source of truth for "what PASS means" is still `score.py` — the eval
imports its public wrappers, never these primitives directly. This directory only
satisfies `score.py`'s own file-path import so it can run offline.

## Keeping in sync

If the PoC scoring contract changes and `score.py` is updated for it, re-copy the
two files here from the PoC harness. They are stdlib-only (`hashlib`, `re`,
`numbers`, `typing`) — no Snowflake, no network — so the offline scorer never
pulls a cloud dependency.
