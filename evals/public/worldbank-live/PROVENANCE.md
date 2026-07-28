# World Bank API — live source, observed values

> **Maintainer record — deliberately outside `fixtures/`.**
> The harness copies `fixtures/` into the agent's workspace, so anything there
> is readable by the agent under test. This file names the traps and the
> expected shapes, which is exactly what the checks grade. Keep it at scenario
> level. Do not move it under `fixtures/`.

## Why this scenario has no vendored data

Every other scenario in this corpus ships a frozen snapshot so its checks can
assert exact numbers. This one deliberately does not: its whole purpose is to
exercise the REST connector path — envelope handling, pagination, a join across
two endpoints — against a source the closure must actually reach.

The cost is that `checks.json` hardcodes figures observed from a live API, and
those figures drift. This file records when they were observed so a later
maintainer can tell a genuine regression from upstream movement.

## Endpoints

    GET https://api.worldbank.org/v2/country/all/indicator/NY.GDP.MKTP.CD?format=json&per_page=<n>&page=<n>
    GET https://api.worldbank.org/v2/country?format=json&per_page=<n>&page=<n>

No credential required. CC BY 4.0 — attribution: World Bank, World Development
Indicators, <https://creativecommons.org/licenses/by/4.0/>.

## Values observed 2026-07-27, and how to re-derive each

Re-run these before concluding a check is wrong; if upstream moved, update the
check and this table together.

| Value | Observed | How to re-derive |
|---|---|---|
| indicator observations | 17,490 | envelope `total` on the indicator endpoint |
| `per_page=20000` | returns `pages: 1` | envelope `pages` at that page size |
| null-valued observations | 2,745 | count rows with `value == null` |
| `/country` entries | 295 | envelope `total` on the country endpoint |
| aggregates | 78 | `region.value == "Aggregates"` |
| real countries | 217 | 295 − 78 |
| blank `countryiso3code` rows | 330 | the five income-group roll-ups × 66 years |
| 2023 all-rows GDP sum | ~8.85e14 | sum `value` where `date == "2023"` |
| 2023 real-country GDP sum | ~1.06e14 | same, excluding aggregates |
| contamination ratio | ~8.3× | the two above |
| trailing-whitespace regions | `"Latin America & Caribbean "`, `"Sub-Saharan Africa "` | exact-match on `region.value` |
| upstream `lastupdated` | 2026-07-13 | envelope field, indicator endpoint only |

The last row matters for `context-discloses-as-of-fetch`: only the indicator
envelope carries `lastupdated`. The `/country` envelope does not, so a check
must not require it from both.

## Why no determinism gate

`deterministic_check` builds the closure twice back to back and compares landed
rows. That assumes a stable source. This source can legitimately change between
the two builds, so attaching the checker here would produce failures that mean
"upstream moved", not "the transform is non-reproducible" — see the SCOPE note
in `treasury-yield-curve/fixtures/check_determinism.py`.

The processing-logic invariant still applies to the closure; it simply is not
mechanically gated on this scenario.
