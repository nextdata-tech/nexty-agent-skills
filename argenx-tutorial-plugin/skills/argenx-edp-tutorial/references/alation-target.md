# Tailoring toward the Alation reference data product

This is the learner's real goal: pull data from the **Alation API**, ingest it (via the
platform's ingestion path) into **Snowflake**, and publish it as a **shared reference data
product** that other data products can build on.

**Do this as a guided diff from the tutorial DP they just built** — they already understand
every piece. Change three things: the input, the output schema, and the "share it" framing.
Keep one step at a time.

> The exact Alation service name, the ingestion API surface, and Alation object schemas are
> environment-specific. Discover them from the infra profile and confirm with the learner —
> don't invent service names or field lists. Where this doc shows a name like `alation-api`,
> treat it as a placeholder to replace with the real service from
> `setup-fallback.md` → discover services.

## 1. Swap the input

In `spec.py`, the tutorial used:

```python
inputs=[
    IngestionSource(name="salesforce-api", service="salesforce-api"),
],
```

Replace it with the Alation API service from their infra profile (discover the real name
first — see `setup-fallback.md`):

```python
inputs=[
    IngestionSource(name="alation-api", service="<alation-api-service-name>"),
],
```

The input then arrives in the transform as `alation_api` (hyphens → underscores). Same rule
they already learned.

> If the platform exposes a dedicated **ingestion** service/driver for Alation (Matej's
> ingestion APIs) rather than a generic API service, point the `service=` at that. Confirm
> which one the infra profile actually has before wiring it.

## 2. Shape the output to the Alation objects they care about

The tutorial used a toy 2-field model. Replace it with a semantic model that mirrors the
Alation objects they're pulling (e.g. data sources, schemas, tables, terms — whatever subset
they need). Build the schema *with* them from what the Alation API returns:

```python
outputs=[
    SnowflakePort(
        port_name="alation-reference",
        schema="ALATION",
        models=[
            semantic_model(
                name="alation_table",
                description="Reference metadata for tables catalogued in Alation",
            ).schema(
                {
                    # Replace with the real fields from the Alation API response,
                    # confirmed with the learner. Example shape only:
                    "id":          (int64(),  "Alation object id"),
                    "name":        (string(), "Object name"),
                    "schema_name": (string(), "Containing schema"),
                    "description": (string(), "Catalog description"),
                }
            )
        ],
    )
],
```

Teach the same concepts they already met (port, semantic model, schema) — just with their real
data. Resist over-modelling; a source-aligned reference DP should keep the data close to its
original shape.

## 3. Fill in the transform

The tutorial transform was empty. Now write the real movement: call the Alation API via the
injected input context, then write rows to the Snowflake port. Keep the parameter names matched
to the spec:

```python
from nxd.data_product.context import API, Snowflake


def transform(
    alation_api: API,            # input  (matches inputs[].name)
    alation_reference: Snowflake,  # output (matches port_name)
) -> None:
    # 1. Read from Alation through the injected API context (credentials come from the
    #    infra profile — never hard-code them).
    # 2. Shape the records to match the semantic model above (source-aligned: minimal reshaping).
    # 3. Write to the Snowflake output port.
    ...
```

> Use the platform's ingestion APIs for the actual load where available rather than
> hand-rolling Snowflake writes — confirm the supported pattern from the platform docs /
> the ingestion service the infra profile exposes.

## 4. Schedule it like a reference feed

Alation metadata changes slowly. Suggest a sensible cadence (e.g. daily `0 6 * * *`) rather
than the tutorial's every-20-minutes, and explain why: *"Reference data doesn't need to refresh
constantly — daily keeps it current without wasting runs."*

## 5. Make it shareable (the actual point)

The reason this is a *reference* DP: other data products consume its output port. After it's
deployed and producing rows:
- Show it in the catalog so the learner sees it's discoverable.
- Explain that another DP can now declare this product's output port as **its** input — that's
  what "share that data as reference for other DPs" means. They've just built a building block
  for the rest of the team.

Then validate + launch exactly as in SKILL.md *Step 6*. Celebrate: they built the thing they
actually came for.
