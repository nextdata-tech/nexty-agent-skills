# Tokens and colour

The two-layer token architecture, the mandatory contrast corrections, and the
rule separating semantic colour from categorical colour.

## Contents

- [The two layers](#the-two-layers)
- [Keepframe values](#keepframe-values)
- [The remap](#the-remap)
- [Contrast corrections are mandatory](#contrast-corrections-are-mandatory)
- [Semantic versus categorical colour](#semantic-versus-categorical-colour)
- [Style rules](#style-rules)

## The two layers

The markup names tokens from one family only. A layer beneath resolves them —
present for a standalone artifact, absent inline where the host supplies them.
See [behaviour.md](behaviour.md) for which format gets which.

Consequence: **never write a raw hex, and never write a dark-mode override.** The
tokens flip on their own. A hardcoded colour is invisible in one theme, and an
override fights the layer that already handles it.

## Keepframe values

```css
/* Daylight */
--color-bg:#FAF8F5;         --color-surface:#FFFFFF;     --color-surface-alt:#F2EFEB;
--color-border:#E6E1DA;     --color-border-strong:#C4BDB4;
--color-text:#1C1915;       --color-text-secondary:#1C191580;  --color-text-tertiary:#1C191540;
--color-accent:#A07850;     --color-accent-subtle:#A078501A;   --color-accent-muted:#A0785033;
--color-semantic-success:#5A8F60;  --color-semantic-success-glow:#5A8F6030;
--color-semantic-warning:#C49530;  --color-semantic-warning-glow:#C4953030;
--color-semantic-error:#B85C52;    --color-destructive-subtle:#B85C5218;

/* Darkroom — [data-theme="dark"] */
--color-bg:#0E0D0C;         --color-surface:#171615;     --color-surface-alt:#1F1E1C;
--color-border:#2A2825;     --color-border-strong:#3D3A36;
--color-text:#EBE7E1;       --color-accent:#C8A882;      --color-accent-subtle:#C8A88224;
```

Typography:

```css
--font-display:'Fraunces',Georgia,serif;
--font-body:'DM Sans',system-ui,sans-serif;
--font-mono:'JetBrains Mono','SF Mono',Menlo,monospace;
/* display-sm 20 · heading-md 15 · body-md 13 · body-sm 12 · caption 11 · mono-md 11 */
```

Keepframe's `mono-sm` and `overline` stops are **10 px** and are illegal inline,
where the floor is 11. Raise them rather than inheriting.

Spacing `xxs 2 · xs 4 · sm 8 · md 12 · lg 16 · xl 20 · xxl 24`.
Radii `sm 4 · md 8 · lg 12 · card 12 · pill 999`.

## The remap

```css
--surface-0:var(--color-bg);
--surface-1:var(--color-surface-alt);   /* tile / card header */
--surface-2:var(--color-surface);
--border:var(--color-border);
--border-strong:var(--color-border-strong);
--text-primary:var(--color-text);
--bg-accent:var(--color-accent-subtle);
--bg-success:var(--color-semantic-success-glow);
--bg-warning:var(--color-semantic-warning-glow);
--bg-danger:var(--color-destructive-subtle);
--radius:var(--radius-sm);
```

## Contrast corrections are mandatory

Keepframe's text stops are alphas of the ink and **do not reach AA**. Measured:

| Token | Contrast | Verdict |
|---|---|---|
| `--color-text` (100%) | 17.51:1 | OK |
| `--color-text-secondary` (50%) | **3.29:1** | Fails AA for normal text |
| `--color-text-tertiary` (25%) | **1.71:1** | Effectively invisible |
| `--text-warning` on its glow | **2.30:1** | Unusable |
| `--text-accent` on `--bg-accent` | **3.53:1** | Fails |

This matters more than it looks. `--color-text-tertiary` is what maps to
`--text-muted`, and `--text-muted` paints the `null` slot — so without correction
the single most contract-critical element on the surface is the least legible one
on it.

Emit all four corrections, each with its comment. Never silently:

```css
/* muted text: 25% -> 65% ink.  5.31:1 daylight · 7.01:1 darkroom */
--text-muted: color-mix(in srgb, var(--color-text) 65%, transparent);

/* supporting text: 50% -> 72% ink.  4.71:1 */
--text-secondary: color-mix(in srgb, var(--color-text) 72%, transparent);

/* chip text on its own glow: mix toward the ink.  6.66 – 9.21:1 */
--text-accent:  color-mix(in srgb, var(--color-accent) 55%, var(--color-text));
--text-success: color-mix(in srgb, var(--color-semantic-success) 55%, var(--color-text));
--text-warning: color-mix(in srgb, var(--color-semantic-warning) 55%, var(--color-text));
--text-danger:  color-mix(in srgb, var(--color-semantic-error) 55%, var(--color-text));

/* categorical badge: full ink.  15.28:1 */
.badge{ color: var(--text-primary) }
```

The badge rule is a deliberate correction. An earlier draft used
`--text-secondary` there; at 3.29:1 that fails, and badges are dense repeated
text. `assets/kit.html` uses `--text-primary` and is the reference.

If `--color-text-secondary` is fixed upstream, the second correction becomes
unnecessary. Until then the artifact applies it locally.

## Semantic versus categorical colour

Role kinds — `primary_key`, `dimension`, `metric`, `join` — are **categories, not
semantics**. They go in neutral badges told apart by label (`pk`, `dim`,
`metric`, `→ model`), never by hue.

Three reasons: four saturated tints per field row is the clutter the restraint
rule exists to prevent; semantic colour loses meaning when spent, so an amber
`metric` makes a genuinely-warning `truncated` stop standing out; and colour
alone never distinguishes.

Strict reservation:

| Role | Only for |
|---|---|
| `danger` | `pii`, `release_unreadable` |
| `warning` | `truncated`, `collected` |
| `success` | `available` |
| `accent` | redirect, trust tier, the view's single primary action |

`pii` is the one genuinely semantic member of the field surface: it takes
`danger`, and it shows **everywhere the column shows**, not only in a detail view.

If neutral badges test badly for scannability, the answer is **not** to borrow
these roles. Declare a categorical ramp in a separate `--nxd-cat-*` namespace so
it cannot collide with the semantics or drift when the system updates.

## Style rules

- Borders hairline: `0.5px solid var(--border)`. No rounded corners on
  single-sided borders — a `border-left` accent takes `border-radius: 0`.
- Type weights 400 and 500 only. Never 600 or 700.
- `--font-mono` for every identifier the user might copy or type: `workflow`,
  column names, URIs, hashes.
- At most one accent-filled button per view; siblings go secondary or ghost.
- At most two floating elevations at once. A third means a dialog.
- Dense lists use bordered rows, not rounded cards.
- No gradients, decorative shadows, blurs or glows.
