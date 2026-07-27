# World Bank GDP + country classification — vendored snapshot

## Source

World Bank, World Development Indicators — GDP (current US$), indicator
`NY.GDP.MKTP.CD`, with the country metadata file shipped alongside it.

<https://api.worldbank.org/v2/en/indicator/NY.GDP.MKTP.CD?downloadformat=csv>

Snapshot taken 2026-07-27. Upstream "Last Updated Date" recorded in the file
header is 2026-07-13.

- `gdp/gdp.csv` — 265 data rows, 66 year-columns (1960–2025), ~340 KB.
  Note: the file carries four preamble lines before the real header row.
- `countries/countries.csv` — 264 rows, ~44 KB.

Both re-exported unchanged from the upstream zip; only the filenames were
shortened (upstream names embed a build number that changes on every refresh
and would churn the scenario checksum for no semantic reason).

## Licence

CC BY 4.0. Redistribution is permitted with attribution.

Attribution: World Bank, World Development Indicators. Licensed under
CC BY 4.0 (<https://creativecommons.org/licenses/by/4.0/>).

## Why vendored rather than fetched at run time

The upstream file is regenerated periodically — the embedded build number and
the "Last Updated Date" both move. A scenario that fetched at setup would
silently change shape between runs, which defeats the point of a pinned
scenario checksum. CC BY 4.0 permits the frozen copy outright.

## Shape

`gdp.csv` is **wide**: four preamble lines, then a header of
`"Country Name","Country Code","Indicator Name","Indicator Code","1960",...,"2025"`.
Each year is its own column, so the file must be unpivoted to a
`(country, year, value)` grain before it is usable.

`countries.csv` is one row per country code:
`"Country Code","Region","IncomeGroup","SpecialNotes","TableName"`.

Both files carry a UTF-8 BOM and contain multi-line quoted fields
(`SpecialNotes` runs to several lines for some countries). Python's stdlib
`csv` handles both correctly when opened with `encoding="utf-8-sig"`; a
hand-rolled line-splitting parser will not.

## Properties this fixture is chosen to exercise

1. **Aggregate-row contamination.** `countries.csv` mixes real countries with
   regional and income aggregates. In this snapshot: **217 real countries and
   47 aggregates**. Aggregates are identifiable by an empty `Region` field —
   entries such as "Africa Eastern and Southern", "Arab World", "Caribbean
   small states", "East Asia & Pacific (excluding high income)". Summing GDP
   without excluding them counts large parts of the world several times over.
   The result looks plausible; nothing errors.

2. **Wide-to-long unpivot.** 66 year-columns must become rows. Leaving them
   wide makes any time-series metric impossible to express in the semantic
   layer.

3. **Preamble handling.** The four lines before the header are not comments in
   any format the parser recognises. They must be skipped explicitly; feeding
   the file straight to a CSV reader yields a garbage header.

4. **Income-group joins.** `IncomeGroup` is populated only for real countries
   (86 High, 59 Upper middle, 47 Lower middle, 25 Low) and empty for
   aggregates — so a naive group-by produces a spurious empty-string bucket
   that silently holds every aggregate row.

## Scope note — this snapshot supports current-classification analysis only

The corpus design called for a slowly-changing-dimension test: joining each
GDP observation to the income classification that country actually held **in
that year**. This metadata file carries only the **current** classification,
one row per country. It cannot support an as-of join on its own.

The historical series (OGHIST, income classifications by fiscal year since
1987) is a separate World Bank artifact published as `.xlsx`, and is not
vendored here. Two consequences:

- As shipped, this fixture exercises aggregate-row contamination, unpivot, and
  preamble handling — not SCD-2.
- Adding the SCD-2 dimension requires vendoring OGHIST and converting it to
  CSV **at vendoring time**. It must not be converted inside a transform:
  there is no xlsx reader in the pinned desktop venv, and reading one at
  transform time would break the byte-identical rerun invariant.
