# Context and resume — reattaching to a pocket product across sessions

## Contents

- [What persists, what dies](#what-persists-what-dies)
- [Reattach playbook — resume first](#reattach-playbook--resume-first)
- [When resume is not possible — rebuild fallback](#when-resume-is-not-possible--rebuild-fallback)
- [Credential recovery for SENSITIVE closures](#credential-recovery-for-sensitive-closures)
- [Optional session ledger](#optional-session-ledger)
- [Honesty clause — what to tell the user](#honesty-clause--what-to-tell-the-user)

This is the **context** half of the pocket loop: how a later turn or a later
session recovers a product it did not build in this session. The
task-scheduling half — routing, step order, caps, fan-out — lives in
[scheduling.md](scheduling.md).

## What persists, what dies

Draw the line clearly, because the recovery path depends on it:

**Durable (survives the session):**

- The **closure directory** at `…/nxd-pocket/<workflow>/` on the file-writing
  surface — the source copy, `spec.py`, `models.py`, `transform/`, and
  `CONTEXT.md`. This is the one key a later session always has.
- The supervisor's **published catalog** — every workflow ever built and
  published on this machine, queryable without booting anything via
  `list_data_products`.
- **`CONTEXT.md`** and **`nxd_decisions`** inside the closure — the prose record
  and the machine-queryable ruling ledger.

**Ephemeral (dies with the session):**

- The **`semantic_endpoint`** and **`bearer_token`**. The bearer is minted per
  session, kept only in memory, and never persisted. A remembered endpoint
  without a live token is worthless, and no tool re-mints a token for a token you
  already hold — you re-acquire the pair by resuming.

## Reattach playbook — resume first

When the user has an existing product but no live endpoint or token — the
typical new session — **reattach, do not rebuild.** The supervisor exposes a
cross-session catalog and a fast re-serve; use them:

1. **List.** Call `mcp__nxd-desktop__list_data_products`. It boots nothing —
   no kernel, no Python runtime, no endpoint — and returns every published
   workflow with its `workflow` id, `definition_id`, `publish_seq`,
   `published_at_unix_ms`, the model tables with row counts, and an
   `artifact_status`. Call this **first** in a fresh session.
2. **Resume.** If the workflow appears with `artifact_status: available`, call
   `mcp__nxd-desktop__resume_data_product` with that `workflow` id (pass it
   verbatim). It reuses the durable published artifact and returns a fresh
   `semantic_endpoint` plus a session `bearer_token` — the same shape
   `build_data_product` returns — in seconds, with **no** regeneration. Every
   ruling encoded when the product was built is preserved.
3. **Describe, then answer.** Call `mcp__nxd-desktop__describe_models` with the
   returned endpoint/token before mapping any question — the authoritative
   measure and dimension names live there, not in the `list_data_products` table
   (those are lowercase physical `dataset.table` identities, not the semantic
   catalog). Then `run_semantic_query`.

Resuming the **same** workflow again is idempotent — it returns the same live
endpoint. Resuming or building a **different** workflow replaces the current
endpoint, so any earlier one from this session stops answering.

`resume_data_product` can return `supervisor_busy`: another session or a
detached CLI runtime owns the local runtime. Retry shortly, or run
`nxd-desktop-supervisor stop` to release a detached runtime, then resume again.

## When resume is not possible — rebuild fallback

Rebuild is the fallback, not the default. Reach for it only when the published
artifact is genuinely gone:

- `list_data_products` reports the workflow as `collected` (the published data
  was garbage-collected) or `release_unreadable` (the durable record is
  damaged — see the entry's `error` field), or
- `resume_data_product` returns `artifact_unavailable` (garbage-collected or
  failed integrity revalidation).

In those cases, rebuild from the closure with the **same** definition path and
the **same** workflow id:

```
build_data_product(definition="<abs path to the closure>", workflow="<workflow-id>")
```

Reusing the workflow id is what makes this a reopen of one product rather than
the creation of a second one. Rebuild is sound because the closure is
deterministic and embeds its own copy of the source: the rebuilt product carries
identical rulings and identical rows, including any landed decisions model. It
costs a full build — narrate it as such (see the honesty clause).

If the closure path itself is gone, say so and treat the request as a fresh
build from source — do not guess a definition path or probe the filesystem for
candidate closures.

## Credential recovery for SENSITIVE closures

If the closure carries a `SENSITIVE` marker, it reaches a live database or API
through `infra-profile.yaml`, and a rebuild (only rebuild — resume never touches
credentials) can fail two different ways with the same symptom:

- **The file is present** and the rebuild fails at connection time: the
  credential expired or rotated. Ask the user for the new value, replace the
  `value:` entry that `SENSITIVE` names, and rebuild.
- **The file is absent** — the usual case for a closure obtained as a clone or
  copy, because `.gitignore` excludes it by design. This is not a broken
  closure, and you **cannot** reconstruct the file from `SENSITIVE`: that marker
  lists only credential *key names*, while `infra-profile.yaml` also carries the
  non-secret connection topology (host, port, database, schema for a database;
  base URL for an API) and the `duckdb` / `python-compute` / `<connector>-source`
  service skeleton. Ask the user for the whole file — or for the topology plus
  their own credential — and rebuild against `nxd-generate-dp`'s
  `reference/database-source.md` / `api-source.md`. Never invent a host or a
  credential to fill the gap, and never echo a credential in chat.

## Optional session ledger

For a build that spans turns or sessions you MAY keep a lightweight ledger,
scoped to one workflow under `.context/nxd-pocket/<workflow>/`, the same way
`nxd-data-product-builder`'s `reference/state-and-resume.md` scopes a build. It
is optional — a single-turn loop needs none of it — and it holds only what the
durable catalog cannot reconstruct:

- the `workflow` id and the absolute closure path (the durable key pair),
- the last catalog you saw from `describe_models` (so a resumed session can
  detect a changed model), and
- open remap / regenerate TODOs, one row each, never blocking — mirror the
  append-a-TODO discipline in `state-and-resume.md`.

Never write the bearer token to this or any file. It is a tool parameter only.

## Honesty clause — what to tell the user

Keep the user's mental model of the runtime accurate:

- **Resume genuinely reattaches.** When you resume, say so plainly — "I found
  the product in the catalog and resumed it; here's a fresh connection." You are
  reusing the published artifact, not rebuilding it.
- **Rebuild has a real cost.** When you fall back to a rebuild, say that too —
  "The published data was collected, so I'm rebuilding it from its closure at
  `<path>`; this takes about as long as the original build." Do not present a
  rebuild as a reattach.
- **Do not promise persistence of the connection.** The endpoint and bearer die
  with the session; a later session resumes for a fresh pair. What persists is
  the closure on disk and the published catalog — say that, and say where the
  closure is.
