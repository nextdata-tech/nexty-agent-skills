# Reopening a pocket data product in a later session

## Contents

- [Why reopening is hard](#why-reopening-is-hard)
- [The durable home](#the-durable-home)
- [The reopen playbook](#the-reopen-playbook)
- [Why reopen-by-rebuild is sound](#why-reopen-by-rebuild-is-sound)
- [Honesty clause — what you must tell the user](#honesty-clause--what-you-must-tell-the-user)
- [What this does not do](#what-this-does-not-do)

## Why reopening is hard

The supervisor MCP exposes exactly three tools: `build_data_product`,
`describe_models`, and `run_semantic_query`. There is **no** list, status,
resume, or rediscovery tool. The bearer token is minted per session and is
never persisted.

Two consequences follow, and both are permanent facts of the current runtime:

- A later session **cannot enumerate** products built by an earlier one. If you
  do not already hold an endpoint and bearer, there is no call that will find a
  running instance.
- A bearer from a previous session is worthless. Even a remembered endpoint
  cannot be queried without a token, and no tool mints one for an existing
  instance.

So a product built into a temp directory and never written down is, for
practical purposes, gone the moment the session ends — the closure may still
exist on disk, but nothing in the loop can point back to it.

## The durable home

Prevention is the real fix. When generating a closure (Step 3):

- Write it to a **durable, user-visible path** on the file-writing surface —
  never a temp, scratch, or session-scoped directory.
- Name the directory by the **workflow id**: `…/nxd-pocket/<workflow>/`. This
  keeps the definition path and the workflow id — the two arguments a reopen
  needs — recoverable from each other, and makes an accidental second product
  visible as a second directory.
- **State the path in the handoff.** Say it in narration, plainly, as the thing
  to keep. It is the only key to this product a later session has.

Which base directory is legal is already governed by the host-visible absolute
path rules in Step 1 and the invariants — this convention constrains the
directory *name*, not the root. Do not invent a host root.

## The reopen playbook

When the user has an existing product but no endpoint or token:

1. **Locate the closure.** Use the path from the earlier handoff. If the user
   does not have it, ask for it directly ("where was the product written?").
   Do not probe the filesystem hunting for candidate closures, and do not
   assume a path from a prior task.
2. **Rebuild.** Call `build_data_product` with the **same** definition path and
   the **same** workflow id. Reusing the workflow id is what makes this a
   reopen of one product rather than the creation of a second one — the
   "one workflow id per data product" invariant still binds.
   - **If the closure has a `SENSITIVE` marker**, it reaches a live database or
     API through `infra-profile.yaml`. Two different failures wear the same
     symptom, and they need different fixes:
     - **The file is present** and the rebuild fails at connection time: the
       credential has expired or rotated. Ask the user for the new value,
       replace the `value:` entry `SENSITIVE` names, and rebuild.
     - **The file is absent** — the usual case for a closure obtained as a
       clone or copy, because `.gitignore` excludes it by design. This is not a
       broken closure, and you **cannot** reconstruct the file from `SENSITIVE`:
       that marker deliberately lists only credential *key names*, while
       `infra-profile.yaml` also carries the non-secret connection topology
       (host, port, database, schema for a database; base URL for an API) and
       the `duckdb` / `python-compute` / `<connector>-source` service skeleton.
       Ask the user for the whole file — or for the topology plus their own
       credential, rebuilding it against
       `nxd-generate-dp's reference/database-source.md` / `api-source.md`.
       Never invent a host or a credential to fill the gap, and never echo a
       credential in chat.
3. **Take the new connection.** The returned `semantic_endpoint` and
   `bearer_token` are the connection for this session. The old ones stay dead.
4. **Re-describe, then answer.** Call `describe_models` before mapping any
   question. Never map against a remembered catalog.

If the closure path is gone entirely, say so and treat the request as a fresh
build from source — do not guess at a definition path.

## Why reopen-by-rebuild is sound

Rebuilding reproduces the *same* product, not a similar one:

- The generated transform is **deterministic** — no `now()`, sorted globs,
  byte-identical reruns.
- The closure **embeds its own copy of the source data**, so the rebuild reads
  exactly the bytes the first build read.

Therefore the rebuilt product carries identical rulings and identical rows,
including any landed decisions model. Governance encoded during Teach survives
the reopen — which is the whole point: a ruling encoded once is still inherited
by every later Ask, even across a session boundary.

## Honesty clause — what you must tell the user

Reopen-by-rebuild is a **mitigation with a real cost**, not a fix for the
underlying gap. Narrate it accordingly:

- **Say you are rebuilding.** "I don't have a live connection to that product,
  so I'm rebuilding it from its closure at `<path>` — this takes about as long
  as the original build."
- **Never present it as attaching to a running product.** You are not
  reconnecting, resuming, or reattaching.
- **Never claim the previous instance was found.** It was not; no tool can find
  it. If an earlier instance is still running, the rebuild does not adopt it.
- **Do not promise persistence.** Do not tell the user the product will still
  be reachable next session, or that the token will keep working. It will not.
  What persists is the closure on disk — say that, and say where it is.

Being straight about the cost is what keeps the user's model of the system
accurate. A user who thinks products persist will not write the path down.

## What this does not do

This playbook does not make the runtime remember anything. Genuine
rediscovery — a list/status tool, a persisted or re-mintable bearer, attaching
to an already-running instance — is runtime work tracked outside this skill and
is **out of scope here**. Do not describe that gap as solved, and do not
promise the behaviour in narration. Until the runtime changes, the durable path
plus a rebuild is the entire story.
