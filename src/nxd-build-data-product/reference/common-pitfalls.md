# Common Pitfalls

## Contents
- Spec / trigger issues
- Validation / auth issues
- requirements.txt issues
- Transform issues
- Data quality issues
- Infra / service issues
- Deprecated patterns
- Glossary links
- Naming, types, imports

Known failure modes when writing nextdata data products. Check these before declaring a DP ready.

---

## Spec / trigger issues

**Schedule on `source_aligned_input()` instead of `script()`**
`.when(scheduled(...))` must go on the transform, not the input.
```python
# Wrong
source_aligned_input().when(scheduled("* * * * *"))

# Correct
.transform(script("transform/main.py").when(scheduled("* * * * *")))
```

**`snowflake_config()` called positionally binds `database`, not `schema`**
`database` is the first parameter and both are optional, so `snowflake_config("MY_SCHEMA")`
sets the database and leaves the schema unset; the driver falls back to the
data-product name for the schema. Symptom: a table appears under a schema named
after the data product in the wrong database — or, if no database by that name
exists, a driver-side "database does not exist" error naming the value you intended
as the schema.
```python
# Wrong — binds MY_SCHEMA to `database`, schema left unset
snowflake_config("MY_SCHEMA")

# Correct
snowflake_config(schema="MY_SCHEMA")
```
See
[data_product_spec.md](data_product_spec.md) (Snowflake) for the full signature.

**`updated()` takes input name, not upstream DP name**
`updated("my-input")` matches the name from `.input("my-input", ...)`. Passing the upstream DP name never fires.
```python
# Wrong — passes upstream DP name
.when(updated("upstream-dp-name"))

# Correct — passes the .input() name
.input("upstream", data_product_input().source(...))
.when(updated("upstream"))
```

**`source_aligned_input()` vs `data_product_input()` confusion**
Use `source_aligned_input()` for external storage (S3, Databricks, Snowflake, ADLS, Kafka). Use `data_product_input()` for DP-to-DP dependencies only. They have different `.source()` URL formats.

---

## Validation / auth issues

**`nxd validate` exits `0` but did not validate**
Always run `nxd --config <session_config> whoami` before validation. If
`whoami` prints `Not logged in`, treat `nxd validate` as `NOT RUN` even if the
shell exit code is `0`; re-run login, then validate again.

**`nxd validate --debug` has no friendly PASS line**
Debug output may end after launching the Python validator. If auth is confirmed,
rerun the same command without `--debug` and print the exit code. Mark
validation `PASS` only when auth is confirmed, validate exits `0`, and no
validation error or traceback is printed.

**Assuming validate is offline-only**
`nxd validate` imports the bundle locally, then connects to the mesh selected by
`--config` and resolves the infra profile/services. Missing services are target
mesh or infra-profile problems, not transform runtime problems.

---

## requirements.txt issues

**Wrong package names**
Package names use underscores, not dots. Wrong names install silently but import fails at runtime.
```
# Wrong
nxd.core
nxd.data_product[spec]

# Correct
nxd_core>=0.0.1
nxd_data_product>=0.0.1
```

**Missing required packages**
Both `nxd_core` and `nxd_data_product` are always required. Omitting either causes `ModuleNotFoundError` at runtime, even if the other is present.

**Missing `databricks-sql-connector`**
Required when using `dbsql.connect()` in transforms. Add to requirements.txt — it's not included transitively.

**Adding `soda-core-spark-df` at a mismatched version**
The `soda` extra lives on `nxd_data_product`, not `nxd_core`, and it pins `soda-core==3.5.6` (plus `soda-core-snowflake==3.5.6`). The Spark/Databricks backend is *not* bundled, so add `soda-core-spark-df` yourself — pinned to the same `==3.5.6`, or pip resolves a conflicting `soda-core`.

---

## Transform issues

**Transform parameter name mismatch**
Parameter names in `@data_product.on_transform()` must match spec input/output port names exactly, with hyphens converted to underscores.
```python
# spec: .input("store-sales-adls", ...)  .port("iceberg-on-s3", ...)
# transform:
def transform(store_sales_adls: AzureDataLakeStorage, iceberg_on_s3: S3Output) -> None:
```

**`.token` vs `.private_access_token` on DatabricksWrite**
`.token` is OAuth M2M. `.private_access_token` is PAT auth. Using the wrong one causes auth failures with misleading messages.

**Blank CSV fields become the literal string `nan` on the way out**
A default `pd.read_csv` infers dtypes and turns empty fields into `NaN`. Writing that frame back out serialises them as the text `nan`, so an optional column (`promotion_id`, `discount_code`, any nullable foreign key) silently gains a fake value in every row that was empty. Passthrough and lift-and-shift products are where this bites, because nothing downstream expects the data to have changed.
```python
# Wrong: blanks come back as "nan"
frame = pd.read_csv(path)

# Correct for a passthrough: blanks stay blank, no dtype guessing
frame = pd.read_csv(path, dtype=str, keep_default_na=False)
```
Reading everything as a string also stops pandas reformatting values it thinks are numbers: a zero-padded store code keeps its padding, and a long numeric ID does not acquire an exponent. Convert explicitly where the transform needs arithmetic. Check this against a real extract, not a hand-written sample: samples rarely carry the empty fields that trigger it.

---

## Data quality issues

**Soda `checks for` table name**
The table name in `checks for <name>` must match the actual DB table name, not the model name in the spec.
```yaml
# spec model is named "users" but DB table is "raw_users"
checks for raw_users:   # must match DB, not spec
  - row_count > 0
```

**Deprecated contract compute driver**
`nxd:local-python:1.0.0` is deprecated. Contract compute (Soda, GX) uses `nxd:kubernetes/contract:1.0.0`. No explicit `.compute()` call is needed — the platform auto-selects the correct driver.

**Missing or wrong GX / Soda extras**
GX and Soda extras must be present and on the right package. Both `nxd validate` and spec import succeed silently — the crash only happens at runtime when the promise runs.

```
# Wrong — wrong package
nxd_core[gx]
nxd_core[soda]

# Wrong — extra missing entirely (plain nxd_data_product validates fine, crashes at runtime)
nxd_data_product

# Correct
nxd_data_product[gx]
nxd_data_product[soda]
```

Always add the extra at the same time you add the promise — never rely on validate to catch it.

---

## Infra / service issues

**`nxd validate` does not check driver strings at all**
It resolves *service names* against the infra profile and stops there. A wrong driver version, and a driver name that does not exist, both validate clean:
```python
.service(service_name="adls", driver="nxd:kubernetes/contract:9.9.9")   # exit 0
.service(service_name="adls", driver="nxd:totally-made-up:1.0.0")       # exit 0
```
Rename the *service* to something bogus and validate fails immediately, which is what makes the silence about drivers easy to misread as approval. Check every `driver=` against the profile by eye. A wrong one surfaces at launch or when a contract executes, far from the edit that caused it.

**Invented service names**
Service names in `.source()` URLs must match actual names from the infra profile — read them from the chosen profile YAML, or list profiles from the active mesh with `nxd ls infra-profiles --config=<session_config>` and list a chosen profile's services with `nxd --config=<session_config> rest -u /api/v1/infraprofiles/<profile-name>/services`. Made-up names cause `service not found` errors at validate or deploy time.

**K8s compute missing `image_pull_policy` for local dev**
When running against a local cluster with locally-built images, add `"image_pull_policy": "Never"` to the compute config. Without it, k8s tries to pull from a remote registry and fails or uses a stale image.
```python
.compute(f"https://<app_url>/infra-profile/{INFRA_PROFILE}#/services/k8s-compute")  # <app_url> = active mesh app host
.config({
    "resources": {"requests": {"cpu": "0.5", "memory": "512Mi"}},
    "image_pull_policy": "Never",   # required for local dev
})
```

---

## Deprecated patterns

**Methods directly on `SourceAlignedInputSpec`**
Don't use `.schema()`, `.resource_name()`, `.target_file()`, `.target_table()` directly on a `source_aligned_input()`. Use `.config(storage_config.target_table(...))` instead.

---

## Glossary links

**A wrong glossary term ID fails silently, so verify every one**
`.link(field, Predicate.GlossaryTerm, "<host>/data-product/<env>/<glossary>#/terms/<id>")` is resolved by ID. A `<id>` that does not exist is stored verbatim and resolves to nothing: the attribute carries no glossary meaning while appearing to, and nothing reports it. `nxd validate` does not check it, launch succeeds, and the deployed product reads back the dead reference as if it were fine. Term IDs copied from an input document, a sibling product, or an attribute name are all guesses until checked against the glossary itself.

Fetch the real terms and compare before writing links. Through the mesh MCP gateway:

```bash
python3 scripts/gateway_tools.py glossary --name <glossary-dp-fullname> --token-file "$TOKEN_FILE"
```

The payload's `terms` object is keyed by exactly the IDs the links must use. A worked example from the ecommerce showcase: `region_id` linked to `#/terms/region` for as long as the product existed, and the glossary's 63 terms contain no `region` — the intended term is `sales_region`.

**The host in a glossary URL is discarded**
The platform parses `/data-product/<env>/<name>#/terms/<id>` into the glossary's full name, composed as `<name>-<env>`, plus the term ID. The host is not read, so two products pointing at different app hosts produce identical stored relationships:

```
region_id -> glossary=ecommerce-glossary-demo  termId=region
```

Use the active mesh's app host for consistency with the rest of the spec, but do not spend a decision on it, and do not diagnose a broken link by looking at the host. Check `<env>`, `<name>` and the term ID.

## Naming, types, imports

**kebab-case vs snake_case**
Data product names are kebab-case (`my-product`). Python identifiers — including semantic model variable names — are snake_case (`my_model`, `channel_sales_velocity`).

**Type constructors take zero args**
`string()`, `int64()`, `boolean()`, etc. accept no positional arguments. Descriptions attach via the schema tuple form `.schema({name: (type(), "desc")})`, never `string("desc")` — that raises `TypeError` at import time.

**Context type import location**
Import context classes (`AzureDataLakeStorage`, `Snowflake`, `S3Input`, `S3Output`, …) from `nxd.data_product.context` for transform parameter type hints. `nxd.core.context` re-exports the same types; prefer `nxd.data_product.context`.

**Import structure (centralized-imports variant)**
If using `imports_spec.py` / `imports_models.py`: `spec.py` wildcard-imports everything from `imports_spec.py`; `imports_spec.py` imports from `nxd.spec` plus local modules; `imports_models.py` imports the types used in model definitions. (With the `nxd_spec.py` / `nxd_models.py` shim variant, the same names must be re-exported via `__all__` — see best_practices.md.)

**Glossary links — model level vs product level**
`.link("field", Predicate.GlossaryTerm, url)` links a single field; `.link(Predicate.GlossaryTerm, url)` links the whole model. Both are valid; pick the level the term describes.

**Quality promises attach to the port**
Output quality checks attach via `.promise()` on the `.port(...)`, not at the output level (a port-level promise is the only one the storage driver sees). Promises can use `soda` (YAML), `gx` (Python), or `custom` (a verify function returning `VerifyResult`).
