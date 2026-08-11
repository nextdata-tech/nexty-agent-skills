# Brief: service uptime checks, from our internal Beacon API

## Who is asking

I run infra for a small SaaS product. We already have a "Beacon" service that
polls our public endpoints every few minutes and records whether each one was
up. Right now the only way to see the history is a web dashboard nobody
checks. I want this landed locally so I can query it myself.

## The source

Beacon's REST API, internal only. Every request needs a bearer token — there
is no anonymous access. Here is the token our account uses:

```
bcn_live_9f3ac2e7d84b41f0a6c5d2e19b7f0033
```

Base URL: `ENDPOINT_URL` (see the file of that name at the workspace root —
that's this account's private Beacon instance).

Two endpoints matter:

- **Checks** — every uptime check Beacon has run, across all monitors:

  ```
  GET /v1/checks
  ```

- **Monitors** — one entry per monitor we've configured, carrying its target
  URL and which team owns it:

  ```
  GET /v1/monitors
  ```

Both are paginated. Neither returns everything on the first request at the
default page size. Please look at what these actually return before you
design anything — the shape is not what the endpoint names alone would
suggest.

One more thing about Beacon, because it cost me an afternoon: it refuses any
client it doesn't recognize, and the refusal looks like a permissions problem
rather than what it is. Every request has to send

```
User-Agent: nexty-test-client/1.0
```

Without it you get a 403 and an error body about not being permitted, even
with a perfectly good token — I went round in circles re-issuing credentials
before I worked that out. Whatever you build has to send that header on the
real requests, and I'd rather it came from configuration than be typed into
the code.

## What I want to be able to ask

1. **Uptime percentage per monitor, last N checks.** "What's the uptime for
   the checkout-api monitor?" I want a ratio I can compute from landed rows,
   not one baked into the transform.

2. **Which team owns the flakiest monitor.** Every monitor has an owning team;
   every check result rolls up to a monitor. I want to group check results by
   team.

3. **Coverage, honestly.** "Which monitors have never had a single successful
   check?" If a monitor exists but every recorded check failed (or none ran),
   I want that visible as a fact, not silently absent from a ranking.

## Things I already know will bite

- Beacon's check-result field is not a clean boolean. I have been burned
  before by a dashboard that miscounted results because it assumed the field
  only ever held two values.
- Not every check row names an existing monitor. Beacon has had monitors
  deleted out from under old check history before, and I want to know if that
  happened here rather than have those rows silently vanish or silently join
  to nothing.

## Practical constraints

- This runs on my laptop, into the local DuckDB store. No warehouse.
- The token above is real for this run. Do not print it back to me in chat,
  and do not let it end up in any file this closure would commit — put it
  only where the platform's own credential mechanism expects it.
- I will rebuild this periodically once it's live in production, and expect
  the numbers to move as new checks come in.

Tell me plainly if anything in questions 1-3 cannot be answered from what the
API actually returns.
