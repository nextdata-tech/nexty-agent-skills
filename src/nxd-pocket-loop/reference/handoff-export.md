# Exporting a pocket data product for another person

## Contents

- [Export vs. reopen](#export-vs-reopen)
- [The call](#the-call)
- [Fail-closed redaction — why you don't hunt for secrets](#fail-closed-redaction--why-you-dont-hunt-for-secrets)
- [Writing `import_notes`](#writing-import_notes)
- [Read the result](#read-the-result)
- [What the recipient gets, and how they import it](#what-the-recipient-gets-and-how-they-import-it)
- [Honesty clause](#honesty-clause)

## Export vs. reopen

Portability has two halves, and they use different tools:

- **Reopen** (`reference/context-and-resume.md`) is the *inbound* half: get a
  product you already own back in a later session, on the **same host, same
  user**. It is resume-first — `list_data_products` → `resume_data_product` —
  falling back to a `build_data_product` rebuild only when the published artifact
  is gone.
- **Export** (this file) is the *outbound* half: hand a product to **another
  person or another machine**. It is a single call to
  `mcp__nxd-desktop__export_data_product` that produces a shareable zip.

`export_data_product` is **read-only**: it takes no lock, boots nothing, and
never modifies the definition directory. It is safe to run on a product that is
currently built and served — exporting does not disturb the running instance.

## The call

```
mcp__nxd-desktop__export_data_product(
    definition   = "<abs path to the closure — the SAME path you built from>",
    import_notes = "<required; see below>",
    redact       = { "<service>": ["<attr>", ...] }   # optional; rarely needed
)
```

- `definition` is the closure's durable, host-visible absolute path — the one
  stated in the handoff and named by the workflow id (`…/nxd-pocket/<workflow>/`).
  It is the same path `build_data_product` takes.
- `import_notes` is **required**.
- `redact` is optional and, for a pocket closure, effectively never needed — see
  the next section.

## Fail-closed redaction — why you don't hunt for secrets

The tool strips credentials **fail-closed**: **every** infra-profile attribute
that is not explicitly marked `public: true` has its value replaced with a
placeholder automatically, without being named. You do not enumerate secrets,
and you do not need to know which attributes are sensitive — anything not proven
public is redacted by default.

`nxd-generate-dp` marks **every** connector attribute `public: false` (see
`nxd-generate-dp`'s `reference/database-source.md` and `reference/api-source.md`).
So for a pocket-generated closure the default already redacts the entire
connection payload — host, port, database, schema, user, password, base URL,
token. Nothing in a pocket closure is `public: true`.

Two consequences:

- **`redact` is effectively never needed here.** The `redact` map only strips
  values that *are* marked `public: true`; it is keyed by infra-profile **service
  name**. Since no pocket-closure attribute is `public: true`, there is nothing
  for it to do. Never reach for `redact` to strip a secret — the fail-closed
  default already did.
- **Never mark a credential `public: true`.** `public: true` means "safe to
  ship in an export." Marking a credential public would leak it into the bundle.

## Writing `import_notes`

`import_notes` is appended **below** a generated header. That header already
lists which credentials the recipient must refill and the exact rebuild
commands — so **do not repeat those**. Put only product-specific context the
recipient needs and the header cannot know:

- What the data is and what the product answers.
- Any ruling or derived-model caveat worth flagging (the `CONTEXT.md` inside the
  closure carries the full contract; `import_notes` can point at it).
- Who to ask, or where the live source lives, if the recipient must supply their
  own credential.

Keep it to the product's story. The mechanics of refilling and rebuilding are
the header's job.

## Read the result

The call returns:

- **Everything it redacted** — relay this to the user so they can confirm the
  bundle carries no live credential.
- **A separate report of any misspelled service or attribute in `redact`.** This
  is reported *apart* from the redaction list precisely so a typo is never
  mistaken for a clean run. If you passed a `redact` map and a name was
  misspelled, the value you meant to strip was **not** stripped — fix the name
  and re-export before handing the bundle off.

## What the recipient gets, and how they import it

The zip contains the whole closure — `spec.py`, `models.py`, `transform/main.py`,
`requirements.txt`, `CONTEXT.md`, the sample-data export, and
`infra-profile.yaml` with credentials replaced by placeholders — plus the
generated `IMPORT.md` and a machine-readable `export.json`.

**Importing is reopen-by-rebuild with the recipient's own credential.** The
recipient unzips, refills the credentials the `IMPORT.md` header names (a
file/CSV closure needs none), then runs `build_data_product` with the closure's
path and a workflow id — the rebuild fallback in
`reference/context-and-resume.md`. Because the closure
embeds its own copy of the source data and the transform is deterministic, the
rebuilt product carries identical rulings and rows — a file/CSV export rebuilds
to the same numbers with no credential step at all.

This is the guided version of `context-and-resume.md`'s "file is absent —
closure obtained as a clone or copy" credential-recovery branch: instead of a
bare missing `infra-profile.yaml`, the
recipient gets placeholder values in place and a header naming exactly what to
refill.

## Honesty clause

- **A live-source product will not connect until the recipient refills the
  credentials** the header lists. Say so in the handoff; the export deliberately
  ships no live secret.
- **The export does not transfer a running instance or a bearer token.** The
  recipient stands up their own instance by rebuilding; the token is minted per
  session and never travels in the bundle.
