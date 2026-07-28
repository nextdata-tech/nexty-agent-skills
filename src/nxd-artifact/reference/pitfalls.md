# Pitfalls

Mistakes already made and verified. Read before writing code, not after a review
finds them again.

## Contents

- [Contract](#contract)
- [Rendering](#rendering)
- [Measurement](#measurement)
- [Fixtures](#fixtures)

## Contract

### One absence rule applied to three different blocks

The obvious generalisation — "a missing key means the surface cannot know" — is
true for the identity blocks and **false** for two others. In `data_model`
attributes, absence means the attribute declared nothing. In
`list_data_products`, absence means the Release could not be read, and those keys
are omitted *specifically* so a placeholder cannot be mistaken for a value.

A shared "skip absent keys" helper flattens all three into one claim. Branch on
`artifact_status` before reading identity fields from a catalog row. Full table
in [contract.md](contract.md).

### Rendering an unknown-role fallback

An earlier specification required unknown role kinds to degrade to a neutral
badge, on the theory that the vocabulary is open. It is not. Roles deserialize
through a tagged enum over four kinds; an unknown kind fails the read and the
resource errors rather than returning a partial document.

The degradation branch is therefore unreachable, untestable, and any fixture
exercising it asserts a payload the server refuses to emit. Render the read
error instead. Earlier reference artifacts carried a `cohort_tag` field
demonstrating this; it has been removed.

### Reading the top-level `model_names`

Top-level `outputs.model_names` is the output-level list, not a union across
ports. The common shape reports it **empty** with populated per-port lists, so a
UI reading only the top level says "no models" about a product that has them.

### Expecting a human name from the catalog tool

`list_data_products` returns no `name`. The human name lives in
`info.identity.name`, behind a resource read. A catalog built from the tool alone
can show only the `workflow`. Do not synthesise a display name by prettifying it.

### Treating `data_model` and `models` as the same block

`verified.json` carries both. `models` is the query registry and lists only
fields with a semantic role. `data_model` is display-only and carries every
attribute, including unannotated ones invisible to `models`. Using `models` to
render "the whole product" silently drops columns; using `data_model` to build a
query offers names the compiler does not accept.

### Assuming `data_type` is a string

It renders as the manifest carries it: a bare string for scalars, an **object**
for complex types (`{"timestamp": {"unit": "ms"}}`, list, struct, map, decimal).
String-assuming renderers break on the complex case.

### Retrying `artifact_unavailable`

It is marked not retryable. The published data was garbage-collected or failed
integrity checks; re-reading cannot fix it. Rebuild. (Contrast with a superseded
seq, which *is* a re-read — it is a redirect carrying the current URI.)

## Rendering

### `var()` does not work in SVG presentation attributes

`<rect fill="var(--surface-1)">` does not resolve — the graph comes out black on
black in dark mode. Use a CSS class or `style="fill:var(--surface-1)"`. Verified:
via a class, the node fill resolves to `rgb(31,30,28)`.

```html
<style>
.gn{fill:var(--surface-1);stroke:var(--border);stroke-width:0.5}
.gt{font-family:var(--font-mono);font-size:11px;fill:var(--text-primary)}
</style>
<svg viewBox="0 0 330 50" role="img" aria-label="orders joins customers on customer_id, many to one">
  <rect class="gn" x="1" y="12" width="100" height="26" rx="4"></rect>
  <text class="gt" x="51" y="29" text-anchor="middle">orders</text>
</svg>
```

### `style-hover` does not exist in the Claude Design runtime

A comp used it five times; `support.js` never reads the attribute, so every hover
was inert. Convert to real `:hover` when implementing, and add `:focus-visible`
— the comp had none anywhere.

### Keepframe's 10 px stops are illegal inline

`--type-mono-sm-size` and `--type-overline-size` are 10 px; the inline host floor
is 11. Join-graph SVG labels are the usual casualty.

### `display:none` during streaming

Inline content hidden in the emitted HTML streams invisibly — the user watches an
empty widget build. Emit every screen stacked and visible, and hide the inactive
ones from the boot script.

### Keepframe's text stops fail AA

25% ink measures 1.71:1. This is the most serious rendering defect and the least
visible: nobody catches it by looking, only by measuring. It lands on the `null`
slot specifically. Corrections in [tokens.md](tokens.md).

## Measurement

### CSS transitions poison contrast readings

`transition: background 500ms` on `html, body` means a measurement taken right
after a theme switch samples a mid-transition frame. It produced 1.05:1 where the
true value was 7.01:1. Kill transitions before measuring:

```js
await page.addStyleTag({content:'*{transition:none !important;animation:none !important}'});
```

### `color-mix` serialises as `color(srgb 0-1)`

Not `rgb() 0-255`. A parser assuming 0–255 reads `0.92` as nearly black, which
produced false readings twice in a row. Detect the prefix and scale:

```js
function parse(s){
  const float = s.startsWith('color(');
  const n = s.match(/[\d.]+/g).map(Number);
  return { c: float ? n.slice(0,3).map(v=>Math.round(v*255)) : n.slice(0,3),
           a: n.length>3 ? n[3] : 1 };
}
```

Composite alpha against the real opaque backdrop before computing contrast.

## Fixtures

### The `minimal-dp` fixture does not demonstrate the ports rule

Its `ports[0].model_names` is `[]` — same as the top level. So a render test
against it **cannot distinguish** a correct implementation from one reading the
wrong level. A second fixture with populated per-port models is needed before
that rule can be tested at all.

### Cases the fixture does not cover

Generate these from hand-built payloads; the fixture will not produce them:

- A port with populated `model_names`
- A `promises` block with `model` and `custom` entries
- A dimension with `pii: true`
- Products in `collected` and in `release_unreadable`
- A query result with `truncated: true`
- A workflow name containing `/`

### `compiler_id` is all zeros in fixtures

Not a meaningful hash. Do not present it as provenance, and do not branch on it.
