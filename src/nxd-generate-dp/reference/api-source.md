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

Same mechanism as the database connector: for CSV the committed connector
config is a non-secret path; for a REST API it necessarily includes a real
credential (bearer token, API key, or OAuth client secret). That value is
delivered by writing it into the `api-source` service's `attributes` in
`infra-profile.yaml` — the desktop supervisor's `generic-secrets` driver
reads it from there and exposes it to the transform as `secrets["api_source"]`.

- The companion file `api-source-endpoints` holds **only non-secret
  topology** — one line per model, `<model>=<endpoint path>`.
- The `api-source` service's `attributes` list carries the live payload as
  **one entry per property**, each shaped `{"key": <property>, "value":
  <live value>, "public": false}` — never one attribute holding a nested
  object. `base_url` is always present. Add an `auth` attribute too only
  when the API requires authentication — its absence means
  `secrets["api_source"]` has no `"auth"` key, not an empty one. See the
  worked example below and the conditional `client_config` construction in
  the transform diff.
- **`value` is always a plain string** on the transform side — dlt/Python
  types (ints, bools) are not preserved; cast in the transform if needed.
- **Set `public: false` on every attribute here.** The supervisor drops any
  attribute *not* marked `public: false` before it reaches template-render
  contexts — that's the actual credential boundary, not the closure
  directory. Don't rely on the default; it's inconsistent across call sites
  in the supervisor.
- **Never fabricate a credential the user hasn't supplied**, and never
  narrate a live token/key in chat — enter it into `infra-profile.yaml`
  exactly as the user gave it, nowhere else.
- **The closure directory itself now holds a live credential in plaintext**
  — `public: false` only controls template-render exposure inside the
  supervisor, it does not make `infra-profile.yaml` safe to commit, zip, or
  hand off. Treat the whole closure directory as sensitive once this file
  carries a real token/key: don't commit it to a shared repo, don't attach
  it to a ticket or chat, and don't reuse it as a template for a different
  API without clearing the old credential first.
- This shape (`key`/`value`/`public`) is verified against the supervisor's
  `yaml_schemas::infra_profile::KeyValuePairWithPublic` type and
  `SecretsHandler` construction — not inferred from a single example.

## Naming

- Infra-profile service: `api-source`, driver `nxd:generic-secrets:1.0.0`.
- Transform secrets key: `secrets["api_source"]` — a dict with `base_url`
  (always present) and `auth` (the auth type plus its live token/key/
  credentials — present only when the API requires authentication).
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

api_secrets = secrets["api_source"]  # dict: base_url (always), auth (only if the API needs it)
endpoint_map = _load_api_source_endpoints()  # parses the api-source-endpoints companion file

client_config = {"base_url": api_secrets["base_url"]}
if "auth" in api_secrets:
    client_config["auth"] = api_secrets["auth"]

config: RESTAPIConfig = {
    "client": client_config,
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
  `nxd:generic-secrets:1.0.0`), with its `attributes` populated with the
  live payload. No-auth example (a public API needing only a base URL):

  ```yaml
    - name: api-source
      driver: nxd:generic-secrets:1.0.0
      attributes:
        - key: base_url
          value: https://aidevboard.com/api/v1
          public: false
  ```

  When the API needs authentication, add the `auth` attribute alongside
  `base_url` — never nest `base_url`/`auth` under a single attribute's
  value:

  ```yaml
    - name: api-source
      driver: nxd:generic-secrets:1.0.0
      attributes:
        - key: base_url
          value: https://aidevboard.com/api/v1
          public: false
        - key: auth
          value: <the live token/key/credentials the user supplied>
          public: false
  ```

  **No `data/` directory, no path file** — `api-source-endpoints` is the
  only companion artifact, and it stays non-secret topology only. For 2+ API
  sources, add one labeled service per instance instead (`api-source-<label>`
  / `secrets["api_source_<label>"]`) — see `reference/multi-source.md`.

## Self-check (connectivity smoke test)

A REST API connector needs live credentials to dry-run at all. When
credentials are available in the authoring session: run one bounded GET per
configured resource (respecting any stated pagination/rate limit), assert a
parseable response matching the expected shape — not an exact fixture
count, since remote data isn't static. When credentials are not available
in-session, report the connectivity self-check as **not run** — do not
claim it passed. Structural checks (naming invariant, no
`.semantic_tools()`, import correctness) still run regardless.
