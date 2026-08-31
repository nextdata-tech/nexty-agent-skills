# DP-spec authoring and closure architecture

## Decision

The user-facing `dp-blueprint.md` is prose-first Markdown. It has strict top-level
navigation but is not a typed mini-language. The active authoring boundary is
v3. Version 1 is rejected; v2 remains only as a read-only verifier for already
approved closure evidence while those artifacts exist.

The implementation has two explicit layers:

```text
dp-blueprint.md
  → dp_spec_authoring.py structure parser + source map
  → external AI typed proposal with provenance
  → deterministic proposal validation
  → natural-language echo-back / Open Questions
  → approved source + proposal snapshots
  → generator and self-contained closure
```

The AI is an interpretation boundary, not a validator. Deterministic code
must reject an incomplete or inconsistent proposal regardless of confidence.

## User-facing Markdown contract

Top-level sections, in order, are:

`Intent`, `Questions`, `Scope`, `Terms`, `Inputs`, `Models`, `Transform`,
`Outputs`, `Decisions`, `Open Questions`.

Subheadings are stable navigation and form anchors. Section bodies accept
normal prose, lists, tables, examples, and code blocks. The parser records
source spans and normalized semantic text but does not require labelled fields.

`Terms` is inline and local. The typed proposal may contain NXD-compatible
`name`, `definition`, `synonyms`, `related_terms`, `examples`, `term_values`,
`priority`, and an NXD glossary string-to-string `tags` map, but the user writes
prose. Related terms must resolve
inside the same document; no external Glossary DP or URL is consulted.

Input expectations and Output promises are the only user-facing contract
surfaces. The compiler derives an internal executable `contracts[]` inventory
from them. Delivery is a platform-fixed internal value:
`desktop-local-duckdb-semantic-query`; it is not an author choice.

Transform contains all behavior-affecting logic, including decisions encoded
as procedures. Decisions records rationale and provenance; it never becomes a
standalone executable Policy section.

## Typed proposal boundary

The proposal envelope is `nxd-dp-spec-proposal-v3`. It contains:

- a v3 source semantic hash;
- the typed proposal payload for Intent, Questions, Scope, Terms, Inputs,
  Models, Transform, Outputs, Decisions, and Open Questions;
- the internal fixed delivery profile and compiled contract inventory;
- `explicit`, `inferred`, or `platform_fixed` provenance for each approval-
  relevant value;
- source spans for non-platform values;
- natural-language echo text and a coverage list.

The proposal is an internal compiler artifact. It is persisted for approval and
closure reproducibility, but it is not a second authoring surface.

The live proposal is persisted beside the document it interprets, at
`…/nxd-jobs/<workflow>/dp-blueprint.proposal.json`. Neither file names the
other: `workflow` plus that convention recovers the pair, the same way the lock
recovers the live document without storing a path to it. The approved copy is
byte-snapshotted into the closure and is what the lock binds.

## Approval and locks

Approval binds:

- the semantic source hash;
- the typed proposal hash;
- Terms and contract-inventory hashes;
- the settled locked-Decision inventory hash;
- locked Decision ids and their values;
- the fixed delivery-profile identity;
- the compiler/canonicalization version.

An extraction cannot overwrite a locked Decision. A conflicting source edit is
an explicit proposed change and revokes approval. Formatting-only edits can
retain approval only after re-extraction proves the typed proposal unchanged.
Blocking Open Questions prevent approval and materialization.

The v3 closure contains byte-identical `dp-blueprint.approved.md`,
`dp-blueprint.proposal.approved.json`, and a v3 lock binding both snapshots. No
closure file may refer to `../dp-blueprint.md`.

## Closure compatibility

The existing v2 lock and build-record shapes remain verifiable for existing v2
closures. New v3 closures use `nxd-dp-spec-lock-v3`, a v3 canonicalization id,
the proposal snapshot, and the same self-contained byte/hash checks. The shared
diagnostics entry point dispatches by `dp_spec_version` for hashing, validation,
lock writing, and lock verification. v1 never dispatches to either path.

Compatibility covers the on-disk **filename** as well as the shape. A closure
built before v0.38.0 carries `dp-spec.approved.md` / `dp-spec.lock.json` /
`dp-spec.proposal.approved.json`, and nothing rewrites it. Only the **lock**
needs a name fallback: `resolve_closure_lock()` prefers `dp-blueprint.lock.json`
and falls back to `dp-spec.lock.json`, and the snapshot and proposal filenames
travel inside the lock as `snapshot` and `proposal_snapshot`, so once the lock
is found a legacy closure resolves the rest of itself from its own contents.
`source_basename` is not that mechanism — it is write-only provenance and is
never dereferenced. When neither lock name is present the diagnostic reports the
current one, because a closure with no lock is a different fault from a closure
with an old one. `self_check.py` cannot import that helper (it runs inside the
closure), so it carries an inlined twin, `closure_path()`.

## Naming: the schema layer versus the artifact

`dp-blueprint` names the **artifact on disk**. `dp-spec` survives as the name of
the **schema and format layer** and is not stale there: the `nxd-dp-spec-*`
envelope ids, the `dp_spec_version` frontmatter key, the `dp_spec_*.py` modules,
the JSON-schema `title` strings, and this document. Renaming those would
invalidate every lock and proposal already written. A file that is an instance
document follows the artifact; a file that describes the format does not.

## Claude Desktop form contract

The form renders source-map paths such as
`v3:inputs[orders].text`, groups them by the fixed section order, shows the
natural-language echo first, and keeps inferred values and Open Questions
visible. Approve is separate from Propose and is disabled for validation errors
or blocking questions. Patches are stale-hash checked; the harness never
replaces the user's Markdown with a canonical typed emit.
