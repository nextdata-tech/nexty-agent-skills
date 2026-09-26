# Scenario: Generate a REST API data-product source from OpenAPI

The workspace contains `openapi.yaml`, a synthetic OpenAPI 3.0 contract for a
read-only orders endpoint. The contract declares its server, route, response
envelope and bearer scheme. Its `x-nexty-required-scopes` extension documents
the mock authorization requirement `orders:read` (the OpenAPI 3.0 bearer
security requirement has an empty scope list). It also uses the
`x-nexty-pagination` extension to make the API's cursor semantics explicit;
OpenAPI does not standardize pagination.

## Task

Read `openapi.yaml` before authoring. Use the generic REST API recipe in the
installed `nxd-generate-data-product` skill and its `reference/source-types.md`
index to locate `reference/api-source.md`. Create a Python-only local Desktop
data-product closure with:

- `spec.py`
- `models.py`
- `infra-profile.yaml`
- `transform/main.py`
- `connectivity_check.py`
- `requirements.txt`
- `README.md`
- `.gitignore`
- `SENSITIVE`

The contract has one operation, so declare exactly one explicit `orders`
resource in the `RESTAPIConfig` passed to `rest_api_resources`. Build ingestion
with dlt `RESTAPIConfig` and `rest_api_resources`. Use a module-level helper
`_orders_resources(secrets)` for only the auth dispatch, static REST config, and
REST call; return the resource list directly from that helper. Follow the API
recipe's client flow: initialize `client_config` with the profile-driven
`base_url`, read `auth_type`, assign the bearer mapping directly to
`client_config["auth"]` in the bearer branch, and raise in the `else` branch.
Then use `client_config` as the `"client"` value in the typed
`RESTAPIConfig`. Do not create a separate `auth` alias or inline a second client
mapping. In the decorated
`ingest` transform, call it exactly once as `res = _orders_resources(secrets)`
and pass `res` unchanged to the single `pipeline.run(res, ...)` call. The
resource name `orders` is the one physical model name in this fixture; do not
build a resource map, loop over resources, or rewrap/rename the list. Keep the
Desktop output contract: declare `PHYSICAL_MODELS = ("orders",)` and
`OPTIONAL_EMPTY_MODELS = ()`, use the local DuckDB output port and run-local dlt
state, and include the required post-run table allowlist check against
`duckdb.model_tables` followed by `(run_dir / ".transform-complete").touch()`.
The check must raise before the marker if the table written by the unchanged
`orders` resource does not match the port's model-table mapping; this is the
fixture-specific tripwire for the no-renaming shortcut, not a general API
recipe. Include the exact `if __name__ == "__main__": data_product.main()`
entrypoint and type the transform's `duckdb` argument as `DuckDbOutput`.

This closure targets the installed Nextdata Desktop wheel. Omit the
source-checkout import shim and any `importlib`, `sys.path`, or other dynamic
import/bootstrap logic; use direct imports from the installed packages.
Keep dlt state run-local: derive `run_dir` from `Path(duckdb.path).parent`,
place `pipelines_dir` under that directory, create it, and set only
`os.environ["DLT_DATA_DIR"]` to `str(run_dir / "dlt-data")`. Configure the
pipeline with `dlt.destinations.duckdb(credentials=duckdb.path)` and
`dataset_name=duckdb.schema`.

Use a literal one-item `resources` list in the config, with `name: "orders"`
and the path expression exactly `"path": secrets["endpoint_orders"]` inside
that resource. The profile value is already `/orders`: do not hard-code it,
alias it, normalize it, strip or join it, or derive it from another field. Do
not use `fetched_models`, a resource list comprehension, an f-string/dynamic
profile key, or a second API resource. Use the contract's server through the
flat `base_url` profile attribute; select the `results` envelope and follow
`next_cursor` through the `after` query parameter with an explicit cursor
paginator. Keep the source read-only: only the documented GET operation belongs
in the generated resource.

Declare bearer auth in flat `api-source` profile attributes, dispatching from
the `auth_type` profile value and reading the credential from the private
`auth_token` attribute. Because this OpenAPI operation requires bearer auth,
reject a missing as well as any unsupported auth type. Add a non-secret
`required_scopes` profile attribute
with the exact scope strings from the contract extension; it documents the
authorization requirement and is not sent as an HTTP credential. Dispatch
bearer auth in the positive `auth_type == "bearer"` branch, reject unsupported
auth types, then build and call the REST config after the dispatch. No credential
was supplied for this scenario: use exactly the clearly marked, non-usable
profile placeholder `${ORDERS_READ_TOKEN}` (the checker allows this exact inert
marker; do not substitute another value). Mark `base_url`,
`endpoint_orders`, `auth_type`, and
`required_scopes` public; keep `auth_token` private. Do not invent a token, copy
one into generated source, or claim the closure has authenticated successfully.
Keep the profile marked sensitive and state that a real credential must be
supplied locally before a later connectivity check. The standalone
`connectivity_check.py` must accept its runtime bearer credential only through
one direct, unaliased module-level `import os`. The only supported reads are
`os.getenv("ORDERS_READ_TOKEN")`, `os.getenv("ORDERS_READ_TOKEN", "")`,
`os.getenv("ORDERS_READ_TOKEN", None)`, and those same three forms using
`os.environ.get(...)`. Refuse a missing value or the exact placeholder, and
never print or log the credential. For probe diagnostics, the only permitted
dynamic type labels are `type(value).__name__` and `type(exc).__name__`; if a
row-type label is needed, name the loop variable `value`. Do not use other
forms such as `type(v).__name__` or `type(body).__name__`; fixed diagnostic
text is preferred. The probe import allowlist is exactly:
`from __future__ import annotations`; `import json`; `import os`; `import sys`
(use only `sys.exit`); `from typing import Any`; either `import urllib.error`
or `from urllib.error import HTTPError, URLError`; and either
`import urllib.request` or `from urllib.request import Request, urlopen`. From
imports may use only the named symbols, without aliases. No other imports are
allowed. Use `os` only for the approved token read; do not call
`os.putenv`/`os.unsetenv`, seed or rewrite the variable, or access other
environment variables. Do not alias, shadow, or rebind `os`; byte or
constructed token-key forms and all other read forms are unsupported. Preserve
the inert profile placeholder and benign documentation text exactly as
`${ORDERS_READ_TOKEN}`. This runtime input is for the authoring-time probe; the
transform must not copy credentials into process environment or use
environment variables for anything except `DLT_DATA_DIR`.
Do not use `match`/`case` statements or structural pattern matching anywhere
in generated closure Python.
Keep probe auth statically auditable: any module-level helper that accepts the
credential must name that parameter `token` and receive it by the explicit
`token=token` keyword at every direct call. Do not pass it positionally,
through argument unpacking (`*args` or `**kwargs`), or by aliasing the helper;
apply the same rule when passing the token to a redaction helper.
Make every helper's token parameter keyword-only and preserve this call shape:
`_fetch(path, *, token)`; `_probe(..., *, token)` calls
`_fetch(path, token=token)`; `_redact(text, *, token)` is called as
`_redact(message, token=token)`; and the entrypoint calls
`_probe(..., token=token)`. Do not pass the token positionally or through
argument unpacking such as `*spec`.
In `README.md`, include this separate status line: Connectivity check: not run;
unverified. Also state that payload inspection was not run or verified.

This is a static generation eval. Do not install packages, run dlt, materialize
the product, execute `connectivity_check.py`, probe the endpoint, or contact an
external service. The hostname is synthetic and is not reachable. Do not
create deployment manifests or generated build outputs.

## Eval boundary

The runner checks generated artifacts structurally. Separate local unit tests
exercise the OpenAPI compiler, mock authorization and cursor pagination, but
they do not execute the agent-generated dlt code. The scenario makes no claim
that a provider connection or Desktop end-to-end build was tested.
