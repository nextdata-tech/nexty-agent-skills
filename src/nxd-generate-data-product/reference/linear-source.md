# Linear as an api-source

## Contents

- [Scope](#scope)
- [Auth is not `bearer`](#auth-is-not-bearer)
- [The infra-profile service](#the-infra-profile-service)
- [Two resources, one endpoint](#two-resources-one-endpoint)
- [Filters match EXACTLY, ignoring case only](#filters-match-exactly-ignoring-case-only)
- [Open is a state TYPE, not a state name](#open-is-a-state-type-not-a-state-name)
- [Nested list fields spawn child tables](#nested-list-fields-spawn-child-tables)
- [`priority` is mostly 0, and 0 is not "lowest"](#priority-is-mostly-0-and-0-is-not-lowest)
- [When a query returns zero rows](#when-a-query-returns-zero-rows)

Linear-specific detail for a closure built on
[api-source.md](api-source.md). Everything generic to GraphQL over the dlt REST
connector — brace-escaping the query body, cursor pagination into the request
body, a GraphQL error arriving as an HTTP 200 — lives there and is not repeated
here. Read that first; this file is only what is true of Linear in particular.

Every shape below is copied from a closure that fetched a live Linear project,
judged its open tickets and published, rather than from Linear's docs.

## Scope

Linear has **no REST surface**. Every read is `POST /graphql` against
`https://api.linear.app`, so an `endpoint_<model>` attribute is `/graphql` for
every model — the models differ by the query in the transform, not by path.
That is unusual enough to state: an author looking for per-resource paths will
not find any.

## Auth is not `bearer`

A Linear **personal API key** is sent as the raw `Authorization` header with no
`Bearer` prefix. Under the connector's `auth_type` table that is `api_key`, not
`bearer`, and the name of the header is the thing that varies:

```yaml
- key: auth_type
  value: api_key
  public: true
- key: auth_key_name
  value: Authorization        # the header Linear reads
  public: true
- key: auth_key_location
  value: header
  public: true
- key: auth_api_key
  value: lin_api_…            # the personal key
  public: false
```

Choosing `bearer` because the credential is a token sends
`Authorization: Bearer lin_api_…`, which Linear rejects. The key is created at
<https://linear.app/settings/api> → Personal API keys, is shown once, and
inherits its creator's workspace permissions — so it can read exactly what that
person can read, and no eventual scoping narrows it.

## The infra-profile service

The full attribute set from the working closure. `project_name` and `page_size`
are ordinary non-secret config, passed into the query as GraphQL variables
rather than baked into the query text:

```yaml
- name: api-source
  driver: nxd:generic-secrets:1.0.0
  attributes:
    - {key: base_url,                        value: https://api.linear.app, public: true}
    - {key: endpoint_linear_issues_landed,   value: /graphql,               public: true}
    - {key: endpoint_linear_comments_landed, value: /graphql,               public: true}
    - {key: project_name,                    value: Nexty Pocket,           public: true}
    - {key: page_size,                       value: "100",                  public: true}
    - {key: auth_type,                       value: api_key,                public: true}
    - {key: auth_key_name,                   value: Authorization,          public: true}
    - {key: auth_key_location,               value: header,                 public: true}
    - {key: auth_api_key,                    value: <the personal key>,     public: false}
```

## Two resources, one endpoint

Issues and comments are separate models with separate queries, both POSTing to
`/graphql`. Comments are reachable from the **root** `comments` query filtered
by the comment's issue, so they do not have to be fetched nested per issue —
which matters, because a nested `comments { nodes { … } }` would land as a child
table (see below) and force one request per ticket.

```graphql
query PocketComments($first: Int!, $after: String, $project: String!) {
  comments(
    first: $first
    after: $after
    filter: { issue: { project: { name: { eqIgnoreCase: $project } } } }
  ) {
    nodes { id body createdAt updatedAt user { name } issue { id identifier } }
    pageInfo { hasNextPage endCursor }
  }
}
```

Pagination is a Relay connection, so the generic cursor-in-the-body paginator
applies with `data.<root>` as the prefix:

```python
"data_selector": f"data.{root}.nodes",
"paginator": {
    "type": "cursor",
    "cursor_path": f"data.{root}.pageInfo.endCursor",
    "cursor_body_path": "variables.after",
    "has_more_path": f"data.{root}.pageInfo.hasNextPage",
},
```

## Filters match EXACTLY, ignoring case only

`eqIgnoreCase` compares the **whole** value. A project displayed as
`Nexty Pocket` is **not** matched by `pocket`:

```graphql
filter: { project: { name: { eqIgnoreCase: "pocket" } } }   # zero rows
filter: { project: { name: { eqIgnoreCase: "Nexty Pocket" } } }   # matches
```

This is the single most likely thing to go wrong, because it fails as an empty
result rather than an error: the credential is accepted, the query is valid, the
response is a well-formed `200`, and `nodes` is `[]`. Downstream that surfaces
much later as an empty promised model, and reads as a credential or connector
problem.

**Take the project name from the user verbatim and confirm it against the API
before building.** Do not lowercase it, and do not assume the informal name the
user says in conversation ("the Pocket project") is the display name.

## Open is a state TYPE, not a state name

Linear workflow states have author-defined **names** (`Todo`, `In QA`,
`In Code Review`) and a fixed **type**. The type vocabulary is closed:

| `state.type` | Open? |
|---|---|
| `backlog` | yes |
| `unstarted` | yes |
| `started` | yes |
| `completed` | no |
| `canceled` | no |

So "open tickets" is `state.type NOT IN ('completed', 'canceled')`, and it is
stable across teams that have invented different state names. Filtering on
`state.name` instead breaks the moment a team renames a column.

Fetch every state and apply open-ness **downstream**, in a derived model. The
landed model then keeps the full population queryable, and closing a ticket in
Linear cannot orphan anything derived from it.

## Nested list fields spawn child tables

`labels { nodes { name } }` is a list, and dlt lands a list as a child table
(`<model>__labels__nodes`) which appears in `data_table_names()` and fails the
read-back assert. Scalar-nested fields are fine — `state { name type }` flattens
to `state__name` / `state__type` — it is specifically **lists** that split.

Flatten list fields at the boundary, before the rows reach dlt:

```python
labels = _nested(row, "labels", "nodes") or []
"label_names": ",".join(_text(l.get("name")) for l in labels if isinstance(l, dict)),
```

The values are unchanged; only the shape moves. Say so in the model description,
because a comma-joined string is a real (if minor) loss: a label containing a
comma is no longer separable.

## `priority` is mostly 0, and 0 is not "lowest"

| value | meaning |
|---|---|
| 0 | **No priority set** |
| 1 | Urgent |
| 2 | High |
| 3 | Medium |
| 4 | Low |

Two traps. The scale runs *downward* — 1 is the most urgent, 4 the least — so
ordering by `priority` ascending puts "no priority" first. And in a real
project most tickets are `0`: in the closure this file came from, 23 of 26 open
tickets had no priority set at all.

That matters for product design, not just correctness. A data product whose
headline question is "where does our ranking disagree with Linear's priority?"
will find almost nothing to compare against. Check the distribution before
promising that answer, and model `priority = 0` as *absent* rather than as a
low rank.

## When a query returns zero rows

Ask the API what it does hold, before touching the credential — a valid key with
a wrong filter and an invalid key look nothing alike, and the API will tell you
which one you have:

```graphql
{ projects(first: 50) { nodes { name state } } }
{ teams(first: 50) { nodes { key name } } }
{ issues(first: 1) { nodes { identifier project { name } team { key } } } }
```

If those return data, the credential is fine and the filter is wrong. If they
error, the credential is the problem. A standalone probe should print this
verdict rather than a bare row count — and it must **not** report `OK` on a
zero-row response, which reads as success and sends the author looking in the
wrong place.
