# Storage Configs Reference

## Service URL pattern

Always construct service URLs from the infra profile. Store the profile name as a constant:

```python
INFRA_PROFILE = "ecommerce-demo"

# Storage service
f"https://example.com/infra-profile/{INFRA_PROFILE}#/services/nxd-databricks-storage"

# Compute service
f"https://example.com/infra-profile/{INFRA_PROFILE}#/services/k8s-compute"
```

The `<service-name>` must match a service name returned by the infra profile API (Step 2b).

---

## `source_aligned_input()` vs `data_product_input()`

| Use | Input type | `.source()` value |
|-----|-----------|------------------|
| External storage (S3, Databricks, Snowflake, ADLS, Kafka) | `source_aligned_input()` | Infra profile service URL |
| Another data product's output port | `data_product_input()` | `https://example.com/data-product/<dp-name>/output/<port-name>` |

```python
# External storage
.input("store-sales",
    source_aligned_input()
    .source(f"https://example.com/infra-profile/{INFRA_PROFILE}#/services/nxd-databricks-storage")
    .config(databricks_config().target_table("sales", sales_model))
)

# DP-to-DP
.input("upstream",
    data_product_input()
    .source("https://example.com/data-product/upstream-dp-name/output/s3")
)
```

---

## Storage config helpers

### Databricks Unity Catalog

```python
from nxd.spec import databricks_config

databricks_config().target_table("table_name", model)
databricks_config(catalog="nxd_test", schema="my_schema").target_table("users", model)
```

### S3

```python
from nxd.spec import s3_config, SupportedFormat

s3_config(SupportedFormat.CSV).target_file("path/to/file.csv", model)
s3_config(SupportedFormat.PARQUET, bucket="my-bucket").target_file("path/output.parquet", model)
```

### Azure Data Lake Storage (ADLS)

```python
from nxd.spec import adls_config, SupportedFormat

adls_config(container="my-container").target_file("path/to/file.csv", model)
adls_config(SupportedFormat.CSV, container="my-container").target_file("path/file.csv", model)
```

### Snowflake

```python
from nxd.spec import snowflake_config

snowflake_config(schema="MY_SCHEMA").target_table("MY_TABLE", model)
```

### Kafka

```python
from nxd.spec import kafka_config

kafka_config(topic="my-topic").group_id("my-group").starting_offsets("latest")
```

### Pinecone

```python
from nxd.spec import pinecone_config

pinecone_config(index="my-index", namespace="ns", region_name="us-east-1")
```

### pgvector

```python
from nxd.spec import pg_vector_config, PgVectorType

pg_vector_config(schema="public").vector("embedding_field", PgVectorType.VECTOR)
```

---

## Transform context types by driver

| Driver | Input type | Output type | Import |
|--------|-----------|-------------|--------|
| Databricks storage | `DatabricksRead` | `DatabricksWrite` | `nxd.core.context` |
| S3 | `S3Input` | `S3Output` | `nxd.data_product.context` |
| ADLS | `AzureDataLakeStorage` | `AzureDataLakeStorage` | `nxd.data_product.context` |
| Snowflake | `Snowflake` | `Snowflake` | `nxd.data_product.context` |
| Kafka | `KafkaRead` | `KafkaWrite` | `nxd.core.context` |
| Execution metadata | `ExecutionContext` | — | `nxd.core.context` |

Prefer `nxd.core.context` imports. `nxd.data_product.context` re-exports the same types.

---

## Databricks: three connection patterns

### SQL Warehouse (simple reads/writes, no Spark)

```python
from databricks import sql as dbsql

with dbsql.connect(
    server_hostname=databricks_output.host,
    http_path=databricks_output.http_path,
    access_token=databricks_output.token,           # OAuth M2M
    # access_token=databricks_output.private_access_token,  # PAT auth
) as conn:
    with conn.cursor() as cursor:
        cursor.execute(f"CREATE OR REPLACE TABLE {output_table} AS SELECT * FROM {input_table}")
```
Requires `databricks-sql-connector` in requirements.txt.

### Spark (complex transforms, on-cluster)

```python
df = databricks_source.spark.table(databricks_source.full_table_name("users"))
df.write.format("delta").mode("overwrite").saveAsTable(databricks_output.full_table_name("users"))
```
Only available when compute driver is a Databricks cluster.

### Spark Connect (external cluster from local Python)

```python
from nxd.drivers.databricks import NxdDatabricksSession

nxd_spark = NxdDatabricksSession.connect(databricks_output)
df = nxd_spark.readStream.format("kafka").options(**kafka_input.spark_options()).load()
```

**Key distinction**: `.token` = OAuth M2M, `.private_access_token` = PAT auth. Use the right one for your workspace configuration.
