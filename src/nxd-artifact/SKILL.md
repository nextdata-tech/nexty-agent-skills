---
name: nxd-artifact
description: Renders a published NXD data product as a visual surface — an inline widget in the conversation, a self-contained HTML artifact, or a Claude Design comp. Use when the user wants to SEE a data product rather than query it: show me this product, render the catalog, build a UI for the semantic model, make a shareable page for this release. Reads the pinned artifact through the read-only nxd:// catalog resources (current, verified.json, info, models, outputs), so it needs no running product, no credentials, and calls no tool during render. Covers the data contract those payloads guarantee — the three distinct meanings of an absent key, null versus empty, the closed role vocabulary, the per-port model list — plus the token architecture, the mandatory contrast corrections, and the verification pass an artifact must survive. For querying a product rather than displaying it, use nxd-pocket-loop.
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Glob
  - Grep
metadata:
  author: nextdata
  version: 0.24.0
---

# nxd-artifact skill

## Overview

Render a published data product from its **pinned artifact** — the manifest bytes
sealed at publish time — in a style consistent with the rest of the surface.

Two facts govern everything here.

**Most of the UI is free.** Identity, the semantic layer, ports and row counts all
come from read-only resources. No credentials, nothing booted, safe to poll. Only
*querying* needs a tool. So catalog and detail views work entirely against
resources, and every tool call sits behind explicit user action.

**Absence is information, and it means three different things.** A key missing
from an identity block means the artifact cannot know. A key missing from a
`data_model` attribute means the attribute declared nothing. A key missing from a
catalog row means the Release could not be read. Rendering them the same way
states something untrue. This is the single most common error on this surface —
[reference/contract.md](reference/contract.md) has the table.

## Before writing any code

Read [reference/pitfalls.md](reference/pitfalls.md). It is verified mistakes, not
theory: `var()` silently failing in SVG attributes, `color-mix` serialising in a
unit range that breaks naive contrast parsers, transitions poisoning measurements,
and the contract errors that survived two earlier specifications.

## The flow

1. **Decide the format.** Inline widget for something in the conversation;
   self-contained HTML for something downloaded, shared or persisted; a Claude
   Design comp when the design is still being iterated.
2. **Read the data.** `current` to resolve the release, then `info` / `models` /
   `outputs` — or `verified.json` in one call when the view needs identity,
   models and evidence together.
3. **Generate the markup once.** All three formats share it. Only the token layer
   and the wrapper differ.
4. **Wrap it.** Inline drops the `:root` block entirely and inherits the host's
   theme; a standalone artifact embeds Keepframe with a theme toggle.
5. **Verify.** Run the checklist below before calling it done.

## The format decision

All three formats use one family of token names. Beneath sits a layer that
resolves them — present for a standalone artifact, absent inline where the host
supplies it. Going from artifact to inline means deleting the `:root` block and
nothing else, so emit it as a clearly delimited, commented unit.

Per-format constraints — the 11 px inline floor, the streaming rule against
`display:none`, allowed origins, the Claude Design runtime's gaps — are in
[reference/behaviour.md](reference/behaviour.md).

## Rules that are contract, not preference

Each is verified by a test in the supervisor or measured. Full detail in
[reference/contract.md](reference/contract.md).

- **Never render an absent key** as a blank slot. No label, no dash, no "N/A".
  Which of the three absences you are looking at determines what to do instead.
- **Always render `null` and `[]` as visible, distinct slots.** Fixed glosses:
  `null · the manifest didn’t say`, `[] · none declared`. Copy them byte-for-byte
  — the apostrophe is U+2019.
- **Read `ports[].model_names`.** The top level of `outputs` is not a union
  across ports; the common shape reports it empty.
- **Treat `roles` as a set.** One column can be primary key *and* a metric.
- **Do not write an unknown-role fallback.** The vocabulary is closed and an
  unknown kind fails the read — the branch is unreachable. Render the error.
- **`list_data_products` has no human name.** It comes from `info.identity.name`.
- **Never show connection config, driver types, credentials, or the bearer
  token.** Not on this surface, and not in a URL.
- **Never call a tool during render.**
- **Always surface `truncated`.** The cap is 200 rows regardless of the requested
  limit. A silent partial set is the worst failure this surface can produce.
- **Build URIs with `encodeURIComponent`** on the workflow segment. `{seq}` is
  canonical decimal.
- **A superseded seq is a redirect, not an error** — the payload carries the
  current URI.

## Style

Token architecture, the four mandatory contrast corrections, and the rule keeping
semantic colour out of categorical badges: [reference/tokens.md](reference/tokens.md).

The corrections are not optional. Keepframe's text stops are alphas of the ink
and measure as low as 1.71:1 — and the worst of them lands on the `null` slot,
the most contract-critical element on the surface.

## Reference artifacts

`assets/` holds three working files. Diff generated output against them.

| File | What it is |
|---|---|
| `kit.html` | Every component in every state, both themes, contrast measured alongside. The visual reference |
| `artifact-example.html` | Full desktop implementation, three screens |
| `inline-example.html` | 380 px variant, same markup as the widget |

`kit.html` is the one to pin. It shows each state isolated, so a generated
artifact can be compared component by component rather than as a whole page.

## Verification

Playwright, Chromium. Kill transitions before measuring anything — see
[reference/pitfalls.md](reference/pitfalls.md).

- [ ] Contrast ≥ 4.5:1 on the `null` slot, badges, chips and banners, both themes
- [ ] No horizontal overflow at 380 px and 900 px
- [ ] Zero console errors (a font fetch failing offline does not count)
- [ ] One screen visible after boot; all screens visible during streaming
- [ ] `null` and `[]` distinguishable from each other and from a present value
- [ ] No slot where an absent key goes
- [ ] A column with two roles shows two badges
- [ ] `data_product` and `table` appear nowhere
- [ ] Port models read from `ports[]`, not the top level
- [ ] Hashes truncate on screen, copy in full
- [ ] Zero raw hex outside the token layer; zero dark-mode overrides
- [ ] No `font-size` below 11 px in the inline variant
- [ ] Nothing renders by calling a tool
