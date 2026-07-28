# Behaviour and formats

What the surface may do on its own, and what changes between the three output
formats.

## Contents

- [Nothing calls a tool on render](#nothing-calls-a-tool-on-render)
- [Which format to emit](#which-format-to-emit)
- [Inline widget constraints](#inline-widget-constraints)
- [Self-contained artifact constraints](#self-contained-artifact-constraints)
- [Claude Design comp constraints](#claude-design-comp-constraints)
- [States](#states)
- [Microcopy](#microcopy)
- [Accessibility](#accessibility)

## Nothing calls a tool on render

Resources are free: read-only projections of pinned bytes, no lock, no boot,
idempotent and safe to poll. Tools are not: they boot processes, take locks and
mint credentials.

So a catalog and a detail view **must work entirely against resources**, and
every tool call sits behind explicit user action. Querying is a separate mode the
user enters, never something a view does to populate itself.

`artifact_status` is an advisory snapshot, not a reservation. It can change
between the call and the user's next action. Do not disable controls based on it
— keep them enabled and respond on use.

## Which format to emit

All three share **the same markup**. Only the token layer and the wrapper change.
Generate the markup once and wrap it; do not write three implementations.

| Format | When |
|---|---|
| Inline widget | The user wants it inside the conversation |
| Self-contained HTML artifact | Downloaded, shared, opened in a browser, persisted |
| Claude Design `.dc.html` comp | The design is being iterated before implementation |

The markup uses one family of token names throughout. Underneath sits a layer
that resolves them:

- **Inline** — the layer does not exist. The host supplies the tokens, and that
  is how the widget inherits the user's theme.
- **Artifact** — the layer maps the same names onto Keepframe, with its own
  theme toggle.

Going from artifact to inline means **deleting the `:root` block and nothing
else**. Emit that block as a clearly delimited, commented unit so the deletion is
mechanical. `assets/inline-example.html` carries the comment worth copying.

## Inline widget constraints

- A fragment. No `<!DOCTYPE>`, `<html>`, `<head>`, `<body>`.
- **Do not declare the token layer.** Declaring it breaks theme inheritance.
- Transparent background on the outer container; no top-level padding.
- 380 px wide on mobile. At most **two** columns in any grid.
- No `font-size` below **11 px**.
- Order: `<style>` → content → `<script>` last. Scripts run after streaming.
- **No `display:none` in the emitted HTML.** Hidden content streams invisibly.
  Emit screens stacked and visible; let JS hide the inactive ones on boot.
- Never `position:fixed`. Never nested scrolling.
- No emoji. No gradients, decorative shadows, blurs or glows.
- Only these origins load: `cdnjs.cloudflare.com`, `esm.sh`, `cdn.jsdelivr.net`,
  `unpkg.com`, `fonts.googleapis.com`, `fonts.gstatic.com`.

## Self-contained artifact constraints

- One file. CSS and JS inline, images as `data:` URIs.
- Keepframe token layer embedded, with a theme toggle.
- Google fonts can fail without network — always give system fallbacks.
- Must work opened straight from the filesystem.

## Claude Design comp constraints

- `<x-dc>` with `<helmet>` for `<link>` and `<style>`.
- `sc-if value="{{ x }}"`, `sc-for list="{{ xs }}" as="x"`.
- Logic in `<script type="text/x-dc" data-dc-script data-props="…">` with
  `class Component extends DCLogic` and a `renderVals()` method.
- The runtime does **not** implement `style-hover` — see
  [pitfalls.md](pitfalls.md).
- `support.js` requires `window.React` and `window.ReactDOM`. It is a design
  runtime, not shippable output.

## States

**Loading.** Resources are cheap and idempotent — prefer a skeleton to a spinner.
Do not block the header on `models`: `current` resolves alone and already gives
`publish_seq`.

**Redirect.** A superseded seq is not an error. The payload carries the current
URI; re-fetch and tell the user what happened.

**Truncation.** When `truncated` is set, say so. Never a silent partial set.

**Empty catalog.** Nothing has been built yet. An invitation, not an apology: a
headline naming the space, one line of body, a verb-first CTA.

## Microcopy

Voice: intelligent, warm, unvarnished. Friendliness lives in the words, not in
extra chrome.

- Sentence case everywhere. No terminal punctuation on labels or headings.
- Active voice, verb first. "Query product", not "Product querying".
- The UI speaks as the product. In errors: "your session expired", never
  "I couldn't…".
- Banned: "successfully", "please", "simply", "seamless", exclamation marks,
  emoji.
- Errors: what happened, then what to do. One sentence, no `Error:` prefix, no
  raw exception.

| Instead of | Write |
|---|---|
| "Error: no models found" | "This port declares no models" |
| "Data loaded successfully" | *(nothing — the table is the confirmation)* |
| "Click here to query" | "Query product" |
| "No products yet" | "Publish your first data product" |

## Accessibility

- Categorical badges are told apart by **label, not hue** — see
  [tokens.md](tokens.md). That removes most colour-alone dependence; the `pii`
  chip is coloured and carries text too.
- The join graph SVG takes `role="img"` and an `aria-label` describing the
  relationship in prose.
- A `<canvas>` needs `role="img"`, a descriptive `aria-label`, and fallback text
  between the tags. **Canvas cannot resolve CSS variables** — use literal values
  there and supply both themes by hand.
- Never `opacity` on text to dim it: it multiplies against the backdrop and
  drifts per surface. Use `--text-secondary` for support, `--text-muted` for
  metadata.
- Interactive elements need `:focus-visible`, not only `:hover`.
