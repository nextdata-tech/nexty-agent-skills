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
Nextdata data product, and not the k8s/mesh `nxd-add-inputs` topology.
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
resources = {r.name: r for r in rest_api_resources(config)}  # returns a LIST
```

### Paginator `type` values — copy these exactly

Omitting the paginator and letting dlt auto-detect is the default advice above,
and it is usually right. When the API needs an explicit one, the `type` value is
validated against a fixed table, and **the separator is an underscore**. Guessing
the hyphenated spelling — `page-number` — is the natural mistake and it fails
with an error that names neither the field nor the fix:

```
For `DltResource`: Path `.`: field `resources[0]` expects `callable`
(function or class instance) but got {...}
```

That message points at `resources[0]` and says "expects callable", so it reads
as a problem with how the resource list was built rather than one bad string
three levels down. Enumerated from `dlt==1.28.2`'s own `PAGINATOR_MAP`:

`auto`, `cursor`, `header_cursor`, `header_link`, `json_link`, `json_response`,
`offset`, `page_number`, `single_page`

```python
"paginator": {"type": "page_number", "base_page": 1,
              "page_param": "page", "total_path": "pages"},
```

`total_path` is the path to the page COUNT in the response envelope — with
`{"page": 1, "pages": 4, "data": [...]}` that is `"pages"`. Omit it and dlt
paginates until a page comes back empty, which is correct but costs one extra
request per resource.

Re-confirm this shape against the pinned `dlt==1.28.2` changelog before
relying on it in code — it was verified against current dlt docs, not
version-pinned documentation.

## Credential handling — read this before shipping

Same mechanism as the database connector: for CSV the committed connector
config is a non-secret path; for a REST API it necessarily includes a real
credential (bearer token, API key, or OAuth client secret). That value is
delivered by writing it into the `api-source` service's `attributes` in
`infra-profile.yaml` — the desktop supervisor's `generic-secrets` driver
reads it from there and merges it into the transform's `secrets` dict.
**`secrets` is FLAT.** The supervisor merges every service named in
`.secrets([...])` into one map. For a `generic-secrets` service the keys are
exactly the `attributes` you wrote — the service name is not among them — so an `api-source` attribute `base_url` arrives as
`secrets["base_url"]`, never `secrets["api_source"]["base_url"]`. A nested read
raises `KeyError: 'api_source'` at transform time, after the credential has
already been resolved.

- **When this closure names more than one service in `.secrets([...])`, check
  for key collisions before writing the profile.** The merge is flat, so a key
  declared by two services resolves to one value and the loser vanishes with no
  error — prefix the attribute `key` (`orders_base_url`) to separate them. Full
  rule: `reference/multi-source.md`.
- The companion file `api-source-endpoints` holds **only non-secret
  topology** — one line per model, `<model>=<endpoint path>`.
- The `api-source` service's `attributes` list carries the live payload as
  **one entry per property**, each shaped `{"key": <property>, "value":
  <live value>, "public": <bool>}` — never one attribute holding a nested
  object (see the sensitivity classification under Credential handling for the
  `public:` value per property). `base_url` is always present. When the API requires
  authentication, add `auth_type` (one of `bearer` / `http_basic` /
  `api_key` / `oauth2_client_credentials`) plus that type's own flat
  fields — never a single `auth` attribute holding the whole credential,
  since dlt's `client.auth` needs a *structured* value (e.g. `{"type":
  "bearer", "token": ...}`), not one opaque string, and some types
  (`api_key`, `oauth2_client_credentials`) carry more than one secret
  field to begin with:

  | `auth_type` | additional attributes |
  |---|---|
  | `bearer` | `auth_token` |
  | `http_basic` | `auth_username`, `auth_password` |
  | `api_key` | `auth_api_key`, `auth_key_name`, `auth_key_location` (optional, defaults to `header`) |
  | `oauth2_client_credentials` | `auth_client_id`, `auth_client_secret`, `auth_token_url` |

  Omitting `auth_type` (and its fields) entirely means
  `secrets` has no `"auth_type"` key, not an empty one. See
  the worked example below and the `auth_type` dispatch in the transform
  diff, which assembles these flat fields into the structured dict dlt
  expects.
- **`value` is always a plain string** on the transform side — dlt/Python
  types (ints, bools) are not preserved; cast in the transform if needed.
- **Mark each attribute by sensitivity.** The `public:` flag controls **only**
  `export_data_product` redaction — the transform reads every attribute via
  `secrets` regardless. Secrets and identity —
  `auth_token`, `auth_username`, `auth_password`, `auth_api_key`,
  `auth_client_id`, `auth_client_secret` — are `public: false` (redacted
  fail-closed on export). Non-secret topology/config — `base_url`, `auth_type`,
  `auth_key_name`, `auth_key_location`, `region` — is `public: true` so it
  survives an export and the recipient only refills the credentials. **Never
  mark a credential `public: true`.** If the user explicitly designates an
  attribute's sensitivity, honor their choice over this default.
- **Never fabricate a credential the user hasn't supplied**, and never
  narrate a live token/key in chat — enter it into `infra-profile.yaml`
  exactly as the user gave it, nowhere else.
- **The closure directory itself now holds a live credential in plaintext.**
  The `public:` flag only controls `export_data_product` redaction; it does not
  make `infra-profile.yaml` safe to commit, hand-zip, or hand off. Treat the
  whole closure directory as sensitive once this file carries a real token/key:
  don't commit it to a shared repo, don't hand-attach it to a ticket or chat,
  and don't reuse it as a template for a different API without clearing the old
  credential first. To share the product, use the supervisor's
  `export_data_product` tool — it strips every attribute not marked
  `public: true` fail-closed, so **never mark a credential attribute
  `public: true`** (`public: true` means "safe to ship in an export").
- **Emit `.gitignore` and `SENSITIVE` in the same step that writes the
  credential**, and `chmod 0600 infra-profile.yaml` where a shell can reach
  the closure. The trigger is structural — any `*-source` service with a
  populated `attributes` list — and Phase C fails the closure when the two
  files are missing. `database-source.md`'s **Sensitivity artifacts** section
  is the canonical definition, including the exact file bodies; it applies
  unchanged here with `Keys: <service>.attributes -> auth_token` (or whichever
  auth keys this API uses). Writing the credential and not the artifacts is an
  incomplete step, not a later cleanup.
- This shape (`key`/`value`/`public`) is verified against the supervisor's
  `yaml_schemas::infra_profile::KeyValuePairWithPublic` type and
  `SecretsHandler` construction — not inferred from a single example.

## Naming

- Infra-profile service: `api-source`, driver `nxd:generic-secrets:1.0.0`.
- Transform secrets keys: the attribute keys themselves, flat on `secrets` —
  `secrets["base_url"]` (always present) and, only when the API requires
  authentication, `secrets["auth_type"]` plus that type's own fields (see
  Credential handling). There is no `secrets["api_source"]` level.
- Companion file: `api-source-endpoints` — one line per model,
  `<model>=<endpoint path>` (non-secret topology only).

These names are for exactly **one** API source. When this closure needs two
or more APIs (or mixes an API with another connector type), label each
instance instead — see `reference/multi-source.md` for the full
`api-source-<label>` / label-prefixed attribute keys (`orders_base_url`) /
`api-source-<label>-endpoints`
pattern.

## `transform/main.py` diff from the CSV template

Same `duckdb` param/typing, `PHYSICAL_MODELS` discipline, read-back assert,
`write_disposition="replace"`, and `.transform-complete` touch as the CSV
template. Only the ingestion body changes:

```python
from dlt.sources.rest_api import rest_api_resources, RESTAPIConfig

# `secrets` is the FLAT merge of every service in `.secrets([...])` — read the
# attribute keys directly. There is no per-service level to index first.
endpoint_map = _load_api_source_endpoints()  # parses the api-source-endpoints companion file

client_config = {"base_url": secrets["base_url"]}
auth_type = secrets.get("auth_type")
if auth_type == "bearer":
    client_config["auth"] = {"type": "bearer", "token": secrets["auth_token"]}
elif auth_type == "http_basic":
    client_config["auth"] = {
        "type": "http_basic",
        "username": secrets["auth_username"],
        "password": secrets["auth_password"],
    }
elif auth_type == "api_key":
    client_config["auth"] = {
        "type": "api_key",
        "name": secrets["auth_key_name"],
        "api_key": secrets["auth_api_key"],
        "location": secrets.get("auth_key_location", "header"),
    }
elif auth_type == "oauth2_client_credentials":
    client_config["auth"] = {
        "type": "oauth2_client_credentials",
        "access_token_url": secrets["auth_token_url"],
        "client_id": secrets["auth_client_id"],
        "client_secret": secrets["auth_client_secret"],
    }
elif auth_type is not None:
    # Do NOT drop this branch, and do not collapse the dispatch to whichever
    # single scheme today's profile uses. An unhandled auth_type means the
    # closure cannot authenticate; raising here says so at transform time
    # instead of sending a wrong-scheme request and reading the 401 as a
    # credential problem.
    raise ValueError(
        f"unsupported auth_type {auth_type!r} in secrets — "
        f"add a branch above, or fix the infra-profile attribute"
    )

config: RESTAPIConfig = {
    "client": client_config,
    "resources": [
        {"name": model, "endpoint": {"path": endpoint_map[model]}}
        for model in PHYSICAL_MODELS
    ],
}
# rest_api_resources returns a LIST of DltResource, not a DltSource. Verified
# against the pinned dlt==1.28.2:
#     rest_api_resources(config: RESTAPIConfig) -> List[DltResource]
# It has no `.resources` mapping, so `source.resources[model]` raises
# `AttributeError: 'list' object has no attribute 'resources'` — and it raises at
# RUN time, after the config is assembled and the credential has already been
# used, so the closure looks correct right up until it lands nothing. Index the
# list by resource name instead.
#
# `rest_api_source` DOES return a DltSource whose `.resources` mapping is real.
# Pick one and stay with it; the two names differ by one word and not by shape.
resources = {r.name: r for r in rest_api_resources(config)}
readers = []
for model in PHYSICAL_MODELS:
    table_name = duckdb.model_tables[model]
    readers.append(resources[model].with_name(table_name))
pipeline.run(readers, write_disposition="replace")
```

Build the `RESTAPIConfig` from `secrets` at runtime — never
hard-code a base URL or credential in the transform source. The `auth_type`
dispatch assembles dlt's structured `auth` dict from the flat secret
fields, the same way `_build_connection_string` in `database-source.md`
assembles a connection string from flat `db_source` fields — never pass a
flat secret value straight through as `auth`.

**Keep the dispatch, and end it with an explicit `elif auth_type is not None:
raise`.** Writing only
the branch this closure happens to need — `client_config["auth"] = {"type":
"bearer", ...}` with no `auth_type` read at all — is the natural shortcut, and
it is wrong for a reason that is invisible on the day it is written: the profile
still carries `auth_type` as an attribute, so the closure claims to be
configured by it while ignoring it. Change the profile to `http_basic` and the
transform keeps sending a bearer header built from a field that is now absent —
a `KeyError` if you are lucky, and a silent 401 loop against the wrong scheme if
you are not. The credential is the one input a closure cannot re-derive, so the
branch that reads it must fail loudly on a value it does not handle:

```python
elif auth_type is not None:
    raise ValueError(
        f"unsupported auth_type {auth_type!r} in secrets — "
        f"add a branch above, or fix the infra-profile attribute"
    )
```

**`auth_type is None` is the one value that must NOT raise.** It means the
profile configures no authentication, which is why the template reads the field
with `secrets.get("auth_type")` and why `secrets` carries
`auth_type` *only when the API requires authentication* (see the attributes list
above). A bare `else: raise` fails every unauthenticated api-source closure at
transform time, with a message pointing the author at a profile attribute that is
legitimately absent — so the guard is `elif auth_type is not None`, matching the
template. Appending a bare `else:` after that `elif` is the same bug wearing a
different shape: it raises on exactly the case the `elif` exists to let through.

An `auth_type` the transform does not handle is a closure that cannot
authenticate. Discovering that as a raise at transform time beats discovering it
as an HTTP 401 whose body is someone else's error page.
`_load_api_source_endpoints` is **not** a dlt or stdlib function — the author
must write it, parsing the `api-source-endpoints` companion file's
`<model>=<endpoint path>` lines into a dict. A transform that calls it
without defining it raises `NameError` at runtime.

## `requirements.txt`

Base pins unchanged. `rest_api_resources` needs no additional pin beyond the
base `dlt[duckdb]==1.28.2` — confirmed by import against the pinned version in
the desktop runtime, not inferred from the dlt docs. If the chosen `auth_type`
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
          public: true
  ```

  When the API needs authentication, add `auth_type` plus that type's own
  flat fields alongside `base_url` — never nest a whole credential under
  one attribute's value. Bearer-token example (topology `public: true`, the
  secret `public: false`):

  ```yaml
    - name: api-source
      driver: nxd:generic-secrets:1.0.0
      attributes:
        - key: base_url
          value: https://aidevboard.com/api/v1
          public: true
        - key: auth_type
          value: bearer
          public: true
        - key: auth_token
          value: <the live bearer token the user supplied>
          public: false
  ```

  For the other three types, add that type's fields from the table in
  Credential handling instead of `auth_token` (e.g. `auth_username` +
  `auth_password` for `http_basic`) — one attribute per field, each marked
  `public:` per the sensitivity classification (secrets `false`, non-secret
  config like `auth_key_name`/`auth_key_location` `true`).

  **No `data/` directory, no path file** — `api-source-endpoints` is the
  only companion artifact, and it stays non-secret topology only. For 2+ API
  sources, add one labeled service per instance instead (`api-source-<label>`
  / label-prefixed attribute keys such as `secrets["orders_base_url"]`) —
  see `reference/multi-source.md`.

## Self-check (connectivity smoke test)

A REST API connector needs live credentials to dry-run at all. When
credentials are available in the authoring session: run one bounded GET per
configured resource (respecting any stated pagination/rate limit), assert a
parseable response matching the expected shape — not an exact fixture
count, since remote data isn't static. When credentials are not available
in-session, report the connectivity self-check as **not run** — do not
claim it passed. Structural checks (naming invariant, no
`.semantic_tools()`, import correctness) still run regardless.

**Never let a probe's traceback reach the transcript unredacted.** This is a
sharper risk than the database case: `requests` puts the full URL in
`HTTPError`/`ConnectionError` messages, so an API keyed by query string
(`?api_key=…`) or basic auth leaks the live credential into chat the moment a
probe fails — and chat is the one place the user cannot remediate. Redact by
substituting the known secret values, never by pattern-matching:

```python
def _redact(exc: BaseException, secrets: dict) -> str:
    text = str(exc)
    for value in secrets.values():            # every live value, keys vary per API
        if value:
            text = text.replace(str(value), "<redacted>")
    return text

try:
    ...  # the bounded GET
except Exception as exc:
    raise SystemExit(f"connectivity check failed: {_redact(exc, secrets)}") from None
```

`from None` is mandatory: without it Python chains the original exception as
`__context__` and re-prints it in full, defeating the redaction. The same rule
governs anything you improvise — never `print()` a request URL or a response
header dump, and never paste a raw traceback from a failed call into the
answer.
