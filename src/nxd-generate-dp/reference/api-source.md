# API connector: an off-mesh REST API

## Contents

- Scope
- The `RESTAPIConfig` / `rest_api_resources` shape
- Credential handling — read this before shipping
- Naming
- `transform/main.py` diff from the CSV template
- `requirements.txt`
- `spec.py` / `infra-profile.yaml` diffs
- Self-check (connectivity smoke test)

This is a sibling of the proven CSV connector documented inline in
`SKILL.md` — same closure shape (`duckdb` port, `PHYSICAL_MODELS`,
read-back assert, `.transform-complete`), no `data/` directory, no local
file export.

## Scope

An **off-mesh** REST API the user names directly — not an upstream
Nextdata data product, and not the k8s/mesh `nxd-adding-inputs` topology.
One base URL, one or more resources/endpoints, each mapped to a promised
physical model.

## The `RESTAPIConfig` / `rest_api_resources` shape

```python
from dlt.sources.rest_api import rest_api_source, rest_api_resources, RESTAPIConfig

config: RESTAPIConfig = {
    "client": {
        "base_url": <base_url>,
        "auth": <bearer | http_basic | api_key | oauth2_client_credentials>,
        # paginator: omit and let dlt auto-detect unless the user specifies one
    },
    "resources": [
        {"name": <model>, "endpoint": {"path": <endpoint path>, "params": {...}, "data_selector": <optional>}},
        ...
    ],
}
source = rest_api_resources(config)
```

Re-confirm this shape against the pinned `dlt==1.28.2` changelog before
relying on it in code — it was verified against current dlt docs, not
version-pinned documentation.

## Credential handling — read this before shipping

Same constraint as the database connector: for CSV the committed connector
config is a non-secret path; for a REST API it necessarily includes a real
credential (bearer token, API key, or OAuth client secret). This repo does
not document how the desktop supervisor's `generic-secrets` driver resolves
that value at boot.

- The companion file `api-source-endpoints` holds **only non-secret
  topology** — one line per model, `<model>=<endpoint path>`.
- The actual `base_url` + `auth` (and thus the live token/key) is delivered
  via `secrets["api_source"]` at transform run time. **Never write the live
  token into any file inside the closure directory**, never persist it in
  narration, never fabricate one.
- Confirm the real secret-delivery mechanism with whoever owns the
  supervisor's `generic-secrets` driver before relying on this path for an
  API needing a real credential.

## Naming

- Infra-profile service: `api-source`, driver `nxd:generic-secrets:1.0.0`.
- Transform secrets key: `secrets["api_source"]` — a dict with `base_url`
  and `auth` (the auth type plus its live token/key/credentials).
- Companion file: `api-source-endpoints` — one line per model,
  `<model>=<endpoint path>` (non-secret topology only).

These names are for exactly **one** API source. When this closure needs two
or more APIs (or mixes an API with another connector type), label each
instance instead — see `reference/multi-source.md` for the full
`api-source-<label>` / `api_source_<label>` / `api-source-<label>-endpoints`
pattern.

## `transform/main.py` diff from the CSV template

Same `duckdb` param/typing, `PHYSICAL_MODELS` discipline, read-back assert,
`write_disposition="replace"`, and `.transform-complete` touch as the CSV
template. Only the ingestion body changes:

```python
from dlt.sources.rest_api import rest_api_resources, RESTAPIConfig

api_secrets = secrets["api_source"]  # dict: base_url, auth
endpoint_map = _load_api_source_endpoints()  # parses the api-source-endpoints companion file

config: RESTAPIConfig = {
    "client": {"base_url": api_secrets["base_url"], "auth": api_secrets["auth"]},
    "resources": [
        {"name": model, "endpoint": {"path": endpoint_map[model]}}
        for model in PHYSICAL_MODELS
    ],
}
source = rest_api_resources(config)
readers = []
for model in PHYSICAL_MODELS:
    table_name = duckdb.model_tables[model]
    resource = source.resources[model]
    readers.append(resource.with_name(table_name))
pipeline.run(readers, write_disposition="replace")
```

Build the `RESTAPIConfig` from `secrets["api_source"]` at runtime — never
hard-code a base URL or credential in the transform source.
`_load_api_source_endpoints` is **not** a dlt or stdlib function — the author
must write it, parsing the `api-source-endpoints` companion file's
`<model>=<endpoint path>` lines into a dict. A transform that calls it
without defining it raises `NameError` at runtime.

## `requirements.txt`

Base pins unchanged. Under current dlt docs, `rest_api_resources` needs no
additional pin beyond the base `dlt[duckdb]==1.28.2` — reconfirm this holds
for the pinned `1.28.2` before relying on it. If the chosen `auth` type
(e.g. `oauth2_client_credentials`) turns out to need an extra dependency,
add it explicitly rather than assuming it's already covered.

## `spec.py` / `infra-profile.yaml` diffs

- `spec.py`: `_api = "/infra-profile/desktop-local#/services/api-source"`,
  `.secrets([_api])`. Everything else (`.promise`, `.model`,
  `.port("duckdb", ...)`, no `.semantic_tools()`) is identical to the CSV
  template.
- `infra-profile.yaml`: third service named `api-source` (same driver
  `nxd:generic-secrets:1.0.0`, same `attributes: []`). **No `data/`
  directory, no path file** — `api-source-endpoints` is the only companion
  artifact. For 2+ API sources, add one labeled service per instance instead
  — see `reference/multi-source.md`.

## Self-check (connectivity smoke test)

A REST API connector needs live credentials to dry-run at all. When
credentials are available in the authoring session: run one bounded GET per
configured resource (respecting any stated pagination/rate limit), assert a
parseable response matching the expected shape — not an exact fixture
count, since remote data isn't static. When credentials are not available
in-session, report the connectivity self-check as **not run** — do not
claim it passed. Structural checks (naming invariant, no
`.semantic_tools()`, import correctness) still run regardless.
