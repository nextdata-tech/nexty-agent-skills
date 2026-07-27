# Brief: country GDP, pulled live from the World Bank

## Who is asking

I maintain an internal macro dashboard. Right now the GDP figures behind it are
a spreadsheet somebody downloaded in 2023 and nobody has refreshed since. I want
a data product that pulls from the World Bank API directly, so a rebuild picks
up whatever the Bank has published rather than whatever was on someone's laptop.

## The source

World Bank Indicators API v2. Public, no API key, no account, no rate-limit
agreement to sign. Licensed CC BY 4.0 — attribution required, redistribution
permitted.

Two endpoints matter to me:

- **GDP observations** — GDP in current US dollars, indicator code
  `NY.GDP.MKTP.CD`, for every economy the Bank publishes:

  ```
  https://api.worldbank.org/v2/country/all/indicator/NY.GDP.MKTP.CD?format=json
  ```

- **Economy metadata** — one entry per economy the Bank tracks, carrying its
  region, income classification and lending type:

  ```
  https://api.worldbank.org/v2/country?format=json
  ```

Both accept `per_page` and `page` query parameters. Neither returns everything
on the first request at the default page size. Please go and look at what these
actually return before you design anything — I have been burned before by
someone modelling from the documentation instead of the payload.

## What I want to be able to ask

1. **GDP for one country over time.** "Show me Vietnam's GDP by year." I want a
   line I can plot, one point per year.

2. **Rank countries within a region for a given year.** "Largest economies in
   Sub-Saharan Africa in 2023." Region has to be something I can group and
   filter by, and the answer must be countries — not the World Bank's own
   regional roll-ups.

3. **Compare income groups.** "Total GDP of upper-middle-income countries versus
   high-income countries, 2023." Same requirement: real economies only.

4. **Coverage, honestly.** "Which countries are missing a GDP figure for 2023?"
   I would rather see an explicit gap than a country quietly absent from a
   ranking. If a number is missing I want to know it is missing.

## Things I already know will bite

I do not know how the API expresses these, but from the spreadsheet era I know
the data has them, so please handle them rather than discovering them later:

- The Bank publishes **aggregates** — "Sub-Saharan Africa", "World", "OECD
  members", "Low income" — in the same feed as real countries. My old
  spreadsheet summed them alongside countries and reported a world GDP roughly
  double the real one. Nothing errored; the number was just wrong. Whatever you
  build must not be able to make that mistake.

- **Missing years.** Not every country has a figure for every year. Some are
  genuinely unpublished.

## Practical constraints

- This runs on my laptop, into the local DuckDB store. No warehouse.
- I will rebuild it periodically and expect the figures to move when the Bank
  revises them — that is the entire point of pulling live rather than
  re-importing a spreadsheet.
- Attribution has to appear somewhere in the product, since the licence asks for
  it.

Please tell me plainly if anything in questions 1-4 cannot be answered from what
the API actually returns.
