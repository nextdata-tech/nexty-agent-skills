# Job loop: build a local product, then export it for a teammate

## Task for the agent

Build and run a local **Invoice Pulse** data product from the CSV export in
`data/`, answer two questions from it, and then **export the product so a
teammate can rebuild it on their own machine**. You have only the installed
Nexty skills and the local desktop supervisor on `PATH`; work autonomously.

The export has one subdirectory per table. Treat 2025-07-15 as today, so
"last quarter" is the half-open interval 2025-04-01 through 2025-07-01.

Use this loop:

1. Inspect/profile the source and infer a question-driven semantic model with
   `nxd-build-semantic-data-product`.
2. Generate a complete runnable local DuckDB + dlt closure with
   `nxd-generate-data-product` — `spec.py`, `models.py`, `infra-profile.yaml`,
   `transform/main.py`, `requirements.txt`, and the `data/`
   export. Do not hand-write `deployment-spec.yaml`, `manifest.yaml`, or
   `models.yaml`; the supervisor compiles those from `spec.py` at serve time.
   Land the closure at a durable directory you name and state.
3. Serve it with `nxd-desktop-supervisor serve --definition <dir> --workflow
   invoice-pulse --data-dir .desktop/state`. Require `published=yes`, then run
   `status` and `describe`. Keep the bearer out of narration and pass it only
   per command.
4. Translate each question below into a catalog-grounded governed selection,
   query the running endpoint, and answer from the returned JSON. State the
   selected measures, dimensions, and filters before each query.

Questions — answer both:

1. What was our total invoiced amount in Spain last quarter?
2. Which customer segment generated the most invoiced amount last quarter?
   Show every segment.

### Then: export the product for a teammate

Your teammate Dana wants to rebuild this product on her own laptop. Hand it off
the sanctioned way — **do not hand-zip or copy the closure directory yourself.**
Use the supervisor's export tool to produce the shareable bundle. The tool reads
the import notes from a file, so write them to a file first, then export:

```sh
nxd-desktop-supervisor export --definition <your closure dir> \
  --data-dir .desktop/state \
  --out export/invoice-pulse-bundle.zip \
  --import-notes-file <your notes file>
```

Requirements for the export:

- Write the bundle to `export/invoice-pulse-bundle.zip` under the working
  directory.
- `--import-notes-file` is required — decide what belongs in those notes.
- Report what the tool tells you about the bundle — where it landed and what it
  did (or did not) redact.

### Verify the handoff, then clean up

Run the provided forcing-function check, which opens the bundle and confirms it
is a complete, rebuildable handoff:

```sh
python check_job_loop.py --mode agent --data-dir .desktop/state \
  --workflow invoice-pulse --endpoint "$LATEST_ENDPOINT" --bearer "$LATEST_BEARER" \
  --bundle export/invoice-pulse-bundle.zip
```

It must end in `ALL CHECKS PASSED`. Then stop the supervisor with
`nxd-desktop-supervisor stop --data-dir .desktop/state`.

In your final answer, give the two answers with the selection behind each,
state that you exported the bundle to `export/invoice-pulse-bundle.zip` for
Dana, summarize the redaction report, and state that the forcing-function check
passed. Do not include bearer tokens.

## Success checks

The eval grades: a generated closure published through the local supervisor,
catalog-grounded endpoint queries, and a bundle produced by the supervisor's
export tool that is a complete, self-contained, rebuildable handoff — its
closure re-serves from the bundle alone and reproduces the same answers.
