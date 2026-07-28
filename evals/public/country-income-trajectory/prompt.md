# Scenario: World Bank GDP by income group

## Task for the agent

Build a Pocket data product that answers these three questions.

1. How has total GDP moved over time for each income group — high income,
   upper middle, lower middle, low?
2. Within a given year, how does one income group's total compare to another's?
3. Which countries sit in each income group?

The workspace holds a vendored World Bank snapshot under `data/`:

- `data/gdp/gdp.csv` — GDP in current US$ from the World Development
  Indicators, one row per country.
- `data/countries/countries.csv` — the country metadata file that ships
  alongside it.

Both files are exactly as they came out of the upstream export. Do not edit,
re-save, or re-shape them.

This is an NXD Pocket data product: local DuckDB through the `duckdb` output
port, loaded with dlt. You have the installed Nexty skills available — consult
them for the closure contract, the derivation rules, and the assert
requirements rather than inferring them from other examples on this machine.

Read the sources before you author anything. The decisions this scenario turns
on are visible in the values and in the file's physical layout, not in the
column names.

Work autonomously. No user is available to confirm a ruling, which does not
make confirmation optional — consult the skills for what to do with a ruling
you cannot get confirmed.

## Success checks

The eval grades the landed data product, not the narration of it: whether the
three questions are answerable from the semantic layer, whether the numbers a
consumer gets back mean what a consumer would assume they mean, and whether
anything the closure had to decide is visible to the next reader.
