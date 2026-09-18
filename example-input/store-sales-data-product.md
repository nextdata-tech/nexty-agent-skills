# Data Product Overview
Point-of-Sale transaction data captured from retail store systems. It provides detailed insight into
real-time consumer purchases at the register, supporting analysis of channel performance, basket size,
promotions and in-store behaviour.

It should be created within the "retail/store-operations" domain and use the "ecommerce-demo"
infrastructure profile. The Nextdata instance is located at: https://nxd.demo.nextopia.dev/

Data product name should be store-sales.

The environment is "demo". Owner, steward and data-product-access controls should all be granted to
"hello@nextdata.com".

# Input
Raw POS records arrive as a CSV file on Azure Data Lake Storage. There is an NXD infrastructure profile
service called "adls" (driver: nxd:adls:2.0.0, context: AzureDataLakeStorage) holding the account,
container and service-principal credentials. Declare a single source-aligned input named "pos-raw-data"
reading that service, configured for CSV.

Put two expectations on the input. First, the ordinary model expectation on the POS model, so the
arriving file is checked against the declared schema. Second, a custom expectation called
"STORE_TRANSACTION_COMPLETENESS" that asserts the three fields the downstream analysis cannot work
without, channel, product ID and transaction timestamp, are present and non-null. Transactions missing
any of them must be rejected before processing. Implement it as a script under contracts/ that runs
against the "adls" service.

The input is declared so the mesh records the source and runs those expectations against it. It is not
the path the data travels on: this is a seed product, and the transform publishes from a POS extract
bundled inside the product itself (see Transformation). Do not give the input a container or a target
file, and do not read from it in the transform.

# Output
The data should be written back to the same "adls" service as CSV, through a single output port named
"adls" carrying one model. Do not specify a schema.

Attach two custom promises to that port, each as a script under contracts/. "FRESHNESS_PROMISE" states
that the newest transaction in the published output is less than 24 hours old and is not dated ahead of
the moment the check runs. Check both ends: a future-dated record makes the age negative, which slips
through any upper bound on its own, and future-dated sales are the specific defect the whole-day floor
in the transform exists to prevent. "POS_CHANNEL_VALIDATION"
states that the channel attribute only ever contains accepted values (store, kiosk, self-checkout).
Both receive a context for the "adls" service, declared with that service's own storage driver
(nxd:adls:2.0.0). Do not name the contract-executor driver here: the platform selects the executor
itself, and naming it hands the contract a bare context with no container or credentials.

The 24-hour budget is deliberate and must not be tightened. The transform runs every eight hours and
rebases by whole days (see Transformation), so the newest transaction is between zero and 24 hours old
whenever the pipeline is healthy, and older than that only once it has stopped running for a day. A
tighter budget, five minutes say, is a claim no eight-hourly batch product can hold: it would either
fail on every healthy run, or pass only because the platform happens to evaluate promises immediately
after the transform. Do not reach for a smaller number by anchoring the data to the current instant
instead of to midnight; that trades a real property of the data for a green check.

# Transformation
The transform is a Python script running on the "k8s-compute" service. It runs on a schedule, every
eight hours (cron "0 */8 * * *"), and also on startup so the product has data as soon as it is launched.

The POS extract lives in the ecommerce-demo repository, which sits alongside this one. Relative to the
root of this repository the path is:

    ../ecommerce-demo/data-products/ecommerce/showcase-dps/store-sales/sample/pos-sell-out.csv

It holds 23,381 transactions spanning July 2025 to August 2026, across three channels (store, kiosk,
self-checkout) and three regions (EU, US, APAC), all in USD, with roughly a quarter carrying a
promotion. Copy that file into the data product at "data/pos-sell-out.csv" and read it from there: the
data product must be self-contained, so do not reference the sibling repository from any code. If the
path does not resolve, stop and ask where the extract lives rather than generating a substitute. The
copied file is part of the deployment bundle, so it must not be excluded by .nxdignore. The transform
reads it and writes it to the "adls" output port.

The only change the transform makes is a date shift: the extract carries static transaction dates, so
the transform moves every transaction_date forward to keep the data recent. Without that shift the data
falls outside any rolling-window calculation (a "last 7 days" metric, for example) once enough time
passes. Timestamps stay in UTC and keep the "%Y-%m-%dT%H:%M:%SZ" format they arrive in.

The offset is the largest whole number of days that leaves no record dated after the moment the
transform runs:

    offset = floor((now - newest_transaction) / 1 day) * 1 day

Two properties matter and the formula delivers both. Whole days mean every transaction keeps the time of
day it carried in the extract; this product is for analysing in-store behaviour and basket size, both of
which are read by hour, so a fractional offset would rotate the whole day's shape, and a nine o'clock
rush would land at half eleven with nothing downstream showing it had moved. Flooring means nothing is
ever published as a sale that has not happened yet. Shifting to "today" instead would land the newest
record at its own clock time, around 20:50 UTC, which is later in the day than every scheduled run, so
the output would carry future-dated transactions on every run. The newest record therefore lands on
today once the run passes its clock time and on yesterday before that, and its age is always between
zero and 24 hours.

The transform therefore takes only the output port in its signature. Reading from the input would
require a container and target file the input deliberately does not declare.

Use pandas for the dataframe work, and the azure-storage-file-datalake / azure-identity client libraries
for the ADLS write. Pin pandas at or below 2.1.4.

# Models
One semantic model, named "pos-sell-out", one row per POS transaction, sampled with the Head method.
Attributes:

- pos_sell_out_id (string): unique identifier for each POS transaction
- product_id (string): product identifier
- quantity_sold (number): units sold in the transaction
- sales_value (number): total value of the transaction
- currency_code (string): currency used
- transaction_date (string): timestamp of the transaction
- store_id (string): retail store where the sale occurred
- region_id (string): region of the transaction
- channel (string): type of POS (store, kiosk, self-checkout)
- promotion_id (string): linked promotion, if applicable

transaction_date stays a string rather than a timestamp, because the file carries it as an ISO-8601
string and the transform rewrites it in the same form.

Link the business-meaning attributes to the shared "ecommerce-glossary" data product with GlossaryTerm
predicates, one link per attribute: pos_sell_out_id to "pos", product_id to "product_id", quantity_sold
to "quantity_sold", sales_value to "sales_value", transaction_date to "transaction_date", store_id to
"store_id", region_id to "sales_region", channel to "sales_channel" and promotion_id to
"promotion_id".

Verify every one of those nine term IDs against the live glossary before writing the links, and correct
this document if any of them is wrong. The glossary is queryable: the mesh MCP gateway's glossary tool
returns the term dictionary for "ecommerce-glossary-demo" keyed by exactly these IDs. A wrong ID is a
dead link and not a validation error, so nothing downstream will tell you: the attribute simply carries
no glossary meaning while appearing to. `region_id` is the worked example, having pointed at a
non-existent "region" for as long as the product has existed; the term is "sales_region".

The host in the link URL does not matter and is not worth deliberating over. The platform parses
"/data-product/<env>/<name>#/terms/<id>" into the glossary data product's full name (composed as
"<name>-<env>") and the term ID, then discards the host. Use the active mesh's app host for consistency
with the rest of the spec, and spend the attention on the term IDs instead.

# Validation
Write a local validation test that reads the bundled POS CSV and runs it through the transform logic,
checking what the floored offset actually guarantees: no record dated ahead of the run, the newest
record between zero and 24 hours old, every row keeping its time of day, relative spacing preserved,
format preserved, and the declared columns surviving. Do not assert that the newest record lands on
today; with the floored offset it lands on today only once the run passes that record's clock time,
which is later in the day than every scheduled firing, so such an assertion would fail on healthy runs.
Check the invariants at each cron firing (00:00, 08:00 and 16:00 UTC), not just at the current moment:
the bug this formula exists to prevent only appears at particular times of day. Once that passes, run
nxd validate to ensure the full data product is working as expected. Note that nxd validate does not execute the
transform, so the local test is the only thing standing between a spec that resolves and a transform
that actually runs.
