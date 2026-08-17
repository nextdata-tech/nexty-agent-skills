# Scenario: Pin a multi-source labeled CSV closure through the desktop supervisor

The workspace contains three CSV export roots and a small model brief:

- `source-orders/` — an `orders` export with rows;
- `source-users/` — a `users` export with rows; and
- `source-archive/` — an `archive` export with headers but no rows.

<!-- The harness keeps this setup text out of the agent-facing task. It records
the evaluator-owned runtime contract without handing the no-skills arm the
artifact names or implementation recipe. The evaluator separately checks that
the transform-only labeled roots do not become labeled source-aligned inputs.
-->
The evaluator expects the closure to preserve the two non-empty roots through
the compatible supervisor and to omit the empty archive source.

## Task for the agent

Build the complete Python-only NXD desktop closure at the workspace root. Read
`BRIEF.md`, `inferred_model.json`, and all three exports before authoring. Keep
the two non-empty roots byte-for-byte and omit the empty archive source. Follow
the applicable repository guidance for the pinning contract and render the
required reopen recipe with the requirement for a supervisor with
directory-companion support.

Do not hand-write deployment-spec.yaml, manifest.yaml, or models.yaml. After
authoring, run the compatible runtime's actual pin path:

```text
nxd-desktop-supervisor create --definition <absolute-workspace-root> \
  --workflow labeled-orders-users-supervisor --data-dir .desktop/state
```

Require `published=yes`, report the result, and stop the supervisor. The
runner-side checker will build the closure again through the real supervisor
and inspect the published rows; a direct directory copy or an invented
simulation is not a substitute.

Work autonomously. No user is available to answer a delivery question.

## Success checks

This opt-in scenario is the live supervisor companion to the ordinary
structural scenario. It proves that a compatible supervisor can pin the
declared non-empty roots and that the transform opens them after pinning. The
empty label remains omitted and the closure retains the normal Python-only
desktop shape.
