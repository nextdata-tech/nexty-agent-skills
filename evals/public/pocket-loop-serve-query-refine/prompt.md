# Pocket Loop: serve, query, and refine a local invoice product

## Task for the agent

Build and run a local **Invoice Pulse** data product from the CSV export in
`data/`.  You have only the installed Nexty skills and the local desktop
supervisor on `PATH`; work autonomously.

The export has one subdirectory per table. Treat 2025-07-15 as today, so
"last quarter" is the half-open interval 2025-04-01 through 2025-07-01.

Use this exact loop:

1. Inspect/profile the source and infer a question-driven semantic model with
   `nxd-build-semantic-data-product`.
2. Generate a complete runnable local DuckDB + dlt closure with
   `nxd-generate-data-product` — `spec.py`, `models.py`, `infra-profile.yaml`,
   `transform/main.py`, `requirements.txt`, and the `data/` export. Do not
   hand-write `deployment-spec.yaml`, `manifest.yaml`, or `models.yaml`; the
   supervisor compiles those, including the semantic catalog, from `spec.py`
   at serve time.
3. Serve it with `nxd-desktop-supervisor serve --definition <dir> --workflow
   invoice-pulse --data-dir .pocket/state`. Require `published=yes`, then run
   `status` and `describe`. Keep the bearer out of narration and pass it only
   per command.
4. Translate each question below into a catalog-grounded governed selection,
   query the running endpoint, and answer from the returned JSON. Use a
   `--selection` JSON file when filters, ordering, or a limit are required.
   State the selected measures, dimensions, and filters before each query.

Phase A questions — answer all four before any refinement:

1. What was our total invoiced amount in Spain last quarter?
2. Which customer segment generated the most invoiced amount last quarter?
   Show every segment.
3. How many invoices are flagged overdue, by product category?
4. Who are the top three customers by total invoiced amount, highest first?

Do **not** add an average-value metric or otherwise pre-empt the following
request while building the phase-A model. After phase A is served, described,
and answered, act on this phase-B request:

5. New request: what was the average invoice value by customer segment last
   quarter?

Recognize the phase-A catalog gap, return to inference/generation, and
re-serve the **same** `invoice-pulse` workflow. Refresh the endpoint, bearer,
status, and catalog before answering the new question. Preserve the original
sum metric while adding the average metric.

Before stopping the final endpoint, run the provided forcing-function check:

```sh
python check_pocket_loop.py --mode agent --data-dir .pocket/state \
  --workflow invoice-pulse --endpoint "$LATEST_ENDPOINT" --bearer "$LATEST_BEARER"
```

It must end in `ALL CHECKS PASSED`. Then stop the supervisor with
`nxd-desktop-supervisor stop --data-dir .pocket/state`.

Phase C — recover the product in a fresh session from its durable key. The
endpoint and bearer you held are now dead (they never persist). The durable key
is the closure directory plus the `invoice-pulse` workflow id — recover from
those, not from a remembered endpoint. Re-serve the **same** workflow from the
**same** closure directory with `nxd-desktop-supervisor serve --definition <dir>
--workflow invoice-pulse --data-dir .pocket/state`, do **not** re-run inference
or generation and do **not** author a new closure. Take the fresh endpoint and
bearer that serve returns, re-run `describe`, then re-answer Phase-B question 5
to prove the recovered product still carries the average metric.

On this direct-CLI surface a re-serve is a rebuild from the closure, not a
reattach to a running instance — narrate it honestly as such. (The MCP surface
adds `list_data_products` + `resume_data_product`, which reattach to the
published artifact in seconds without regeneration; that resume-first ordering
is asserted separately by `evals/tests/test_resume_first_gate.py`.)

In your final answer, give the five answers, the latest selection behind each,
and state that the forcing-function check passed and that Phase C recovered the
product from its durable closure + workflow id without re-authoring it. Do not
include bearer tokens.

## Success checks

The eval grades the full loop: a generated closure published through the local
supervisor, catalog-grounded endpoint queries, the required filters/join/
boolean aggregation/top-N ordering, and a mechanically proven second published
generation whose first snapshot could not answer the staged average request.
