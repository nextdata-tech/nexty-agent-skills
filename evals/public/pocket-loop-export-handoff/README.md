# Pocket loop export/handoff eval runtime

This scenario exercises the **export/handoff** half of the pocket loop: the
agent builds and serves a local product, then produces a shareable bundle with
the supervisor's export capability (`export_data_product`, surfaced on the CLI
as `nxd-desktop-supervisor export`). The verifier independently re-opens that
bundle and **rebuilds the product from it alone**, proving the handoff is
complete and self-contained.

Build the pinned desktop runtime from the NXD worktree first:

```sh
cargo build -p nxd-desktop-supervisor --bins
uv sync --directory components/desktop/supervisor/py
```

Set both runtime paths, then run:

```sh
export EVAL_POCKET_SUPERVISOR_DIR=/path/to/target/debug
export EVAL_POCKET_PYTHON=/path/to/components/desktop/supervisor/py/.venv/bin/python
python evals/run.py --scenario pocket-loop-export-handoff --skill-set candidate_pack
```

The runner preflights the committed reference closure, injects that runtime
only for this opted-in scenario (`fixtures/pocket.json`), and tears down
persistent supervisor processes. It is CI-skipped (`ci_skip` in `checks.json`)
because CI cannot provision a live desktop supervisor — run it locally or via
`workflow_dispatch`.

## Runtime surface (confirmed against the pinned runtime)

This scenario is drafted against the export tool's real contract, confirmed
against the NXD supervisor source:

1. **CLI invocation** (`ExportOptions`,
   `components/desktop/supervisor/src/bin/supervisor_main.rs`). The `export`
   subcommand takes `--definition <dir>`, `--out <path>` (optional; defaults to
   `<data-dir>/exports/`, named from the closure's content), repeatable
   `--redact SERVICE=ATTRIBUTE` pairs, and `--import-notes-file <path>` (notes
   are read from a **file**, not an argv string). `--data-dir` is a global flag.
   There is **no `--workflow` flag on `export`** — the definition directory alone
   identifies the closure. The prompt writes the notes to a file, passes
   `--import-notes-file`, and `--out export/invoice-pulse-bundle.zip`; the
   verifier also globs for any `*.zip` under the workspace as a fallback.
   The MCP tool `export_data_product` (`ExportParams`,
   `components/desktop/supervisor/src/mcp_server.rs`) takes the same shape minus
   the CLI framing: `definition`, `import_notes` (string), `redact` (map keyed by
   service name), `destination` (optional output path).
2. **Bundle layout.** `inspect_bundle` tolerates an optional single top-level
   directory and matches closure members by basename (`spec.py`, `models.py`,
   `transform/main.py`, `infra-profile.yaml`), plus `IMPORT.md` and
   `export.json`. If the runtime nests the closure differently, adjust
   `CORE_MEMBERS` / `bundle_closure_root`.

## What is and isn't covered

- **Covered mechanically:** the loop (serve/describe/governed query), that the
  bundle is a complete closure, that `IMPORT.md` and `export.json` are present
  and well-formed, and — the strongest signal — that the bundle **re-serves on
  its own and reproduces every answer** (`bundle_roundtrip_answers` all CORRECT).
- **Covered by the model judge (trace):** that the agent used the export tool
  rather than hand-zipping, passed product-specific `import_notes` only (no
  restating of the generated header), relayed the redaction report, did not
  misuse `redact`, and never narrated a bearer or credential.
- **Deliberate limitation:** the source here is a credential-free CSV export, so
  fail-closed **credential redaction** is a clean no-op and is *not* proven on
  real secret bytes. A database/REST-source variant would prove redaction
  mechanically (grep the bundle for the known secret value → absent), but it
  needs the runner to stand up the source's backend during preflight. That is a
  documented follow-up, tracked separately from this scenario.
