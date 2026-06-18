# Common Pitfalls

## Contents
- Spec / trigger issues
- Validation / auth issues
- requirements.txt issues
- Transform issues
- Data quality issues
- Infra / service issues
- Deprecated patterns
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

**Adding `soda-core-spark-df` directly**
Already included via `nxd_core[soda]`. Adding it separately causes version conflicts. Use `nxd_core[soda]` instead of plain `nxd_core`.

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
