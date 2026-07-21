# Northwind data architecture (as documented by the platform team)

## Flow

Batch exports land in the `northwind-landing` S3 bucket first. A nightly job
copies each landed dataset into the `NORTHWIND_CORE` Snowflake database, where
consumers read it. S3 is upstream of Snowflake for every dataset we run.

## Environments

`prod/` is the production path prefix in the landing bucket.
