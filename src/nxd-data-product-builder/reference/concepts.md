# What is Nextdata OS?

Nextdata OS is a platform for building and running autonomous data products. Nextdata OS encapsulates your entire data management, including transformation logic, infrastructure provisioning, policies-as-code, data quality, lineage, semantics and other metadata as autonomous data products, providing everything you need to produce, manage and share data, and make it useful, safe, trusted and discoverable.

It supports four main roles:

*   Producers: Anyone that wishes to share data products. Typically: Ingestion teams, data engineers and sometime non technical data stewards.
*   Consumers: Anyone who is exploring/discovering existing data products. Typically: Analysts, scientists, agents, and sometimes decision makers.
*   Governance engineers: Usually responsible for reliability and quality of data across different domains.
*   Platform engineers: responsible for shared infrastructure (e.g. storage, compute, idp services).

It has two main planes:

*   Data product plane: these are a set of data products that your teams have produced.
*   Platform plane: a layer of components to help teams manage data products.

## The power of Nextdata OS

Nextdata OS lets business domains quickly develop standard data products from existing assets, using familiar tools like Python or YAML, or taking advantage of Nextdata OS generative co-pilot capabilities. Data product creation times are typically accelerated from 3-6 months to days or hours, enabling fast bootstrapping of data mesh deployment throughout complex organizations.

# Concepts

## Autonomous data products

A long-running service that encapsulates and automates all aspects of data management, incorporating everything you need to produce, manage, govern and share data, and make it useful, safe, trusted and discoverable. Every autonomous data product can be controlled, observed and accessed via a global URL - just like a webservice.

A data product includes:

*   Semantic models: A semantic model defines a "storage agnostic" schema, descriptions, semantic links and data verifications that a data product produces for its consumers.
*   Inputs: a set of standardized APIs for orchestrating getting data into a data product from different formats and sources (e.g. Reading from Kafka, S3, ADLS, etc.) with enforcement of expectations.
*   Outputs: a set of standardized ports that allow data to be used in multiple modes and formats (SQL, object store, vector store, MCP server, stream, etc.) for different types of consumers.
*   Orchestration: All the configuration about when to run. These can be based on input data events or schedule based.
*   Transform: data product-specific code, such as harmonization, joins, using different tools, and compute platforms.
*   Standardized APIs for discovery (build-time metadata and live runtime information) and lifecycle management: controlling the lifecycle of a data product with commands such as reset, retry, run, etc.

You can define a data product by providing a specification file:

Example of a simple data product spec:

```
spec = (
    data_product(
        name="sales-influence-insights",
        domain="retail/sales",
        description="Sales Influence ...",
        version="0.1.1-dev",
        infra_profile="https://nextopia.dev/infra/ecommerce",
        source_repo_url="https://github.com/nxd/sales-influence-insights",
    )
    .transform(
        code(transform) # pointer to python transform / dbt / dbx bundle / etc.
        .compute("#/services/k8s-python-compute")
    )
    .input(
        "adls",
        data_product_input()
        .source("https://nextopia.dev/data-product/store-sales#/output/port/adls")
    )
    .output(
        data_product_output()
        .port(
            "snowflake",
            storage("#/services/demand-sales-snowflake-aws")
        )
    .control("owner", owner().user("hello@nextdata.com"))
)
```

## Mesh

A mesh refers to a single installation of Nextdata OS, which usually includes multiple domains, subdomains, and data products. Your company might have one mesh or multiple meshes. You can also have multiple meshes to manage different environments.

## Domains and subdomains

A domain represents the boundary of a business function, such as sales, logistics or customer relations. Domains can have multiple subdomains, such as sales/retail or sales/supply-chain. Each domain or subdomain can have multiple data products.

Domains provide a way to manage access controls to data products and data services. For example:

*   A platform engineer can control which roles can see which domains.
*   A platform engineer can control which producers have "launch" access to which domains.

You can see domains such as Retail and Finance

You can see subdomains such as Sales and Amazon

## Input

A set of standardized ports that defines the source of the data product. They can be external APIs, external data sets, or other data products. If a data product needs any data for transformation and serving to its users, it has to be defined as an input. You can also use inputs for:

*   Orchestration: defining data events and schedule-based triggers.
*   Defining upstream data quality rules, also known as expectations.

Example of a data product with two inputs:

```
spec = (
  data_product(...)
  .transform(...)
  .input(
      "store-sales-adls",
      data_product_input()
      .source("https://nextopia.dev/data-product/store-sales#/output/port/adls")
  )
  .input(
      "twitter",
      source_aligned_input().source("https://nextopia.dev/infra-profile/ecommerce-demo#/services/twitter-api"),
  )
  ...
  .output(...)
)
```

### Expectation

A data contract specifies what semantics a data product requires from upstream sources (i.e., preconditions or assumptions). In runtime, Nextdata validates promises and expectations, so that if a change breaks an expectation, negative impact is contained and “bad data doesn’t flow downstream”.

## Output

Set of standardized ports for getting data in multiple modes (SQL, Object store, stream, etc.) for different use cases and consumers. Individual data products can support multiple use cases through different output ports.

### Promises

A data contract specifies what semantics a data product guarantees (i.e. the commitments it makes to downstream consumers). In runtime, Nextdata validates promises and expectations, so that if a change breaks a promise, negative impact is contained and “bad data doesn’t flow downstream.”

## Policies

Policies are executable, compliance-as-code that can be enforced across a set of data products with configurable consequences (e.g. fail, warning).

## Semantic model

A semantic model defines a "storage agnostic" schema, descriptions, semantic links and data verifications that a data product produces for its consumers.

Example:

```
sales = (
  semantic_model("sales")
  .sampling(method=SamplingMethod.Random)
  .description("Measures and compares the rate ...")
  .schema(
      {
          "product_id": (
              string(),
              "Identifier for the product whose sales velocity is being measured.",
          ),
          "units_sold_last_7_days": (
              int32(),
              "Units sold last 7 days",
          ),
          ...
      }
  )
  .link(
      "product_id",
      Predicate.SameAs,
      "https://nextopia.dev/product#/models/catalog/attributes/product_code",
  )
  .verify_field("product_id", greater_than(0))
  .verify_field("sales_channel", match_regex("[a-zA-Z0-9_\-]"))
)
```

### Semantic link

A semantic link creates a relationship between different attributes across domains and data products. For example, `party_id` and `customer_id` can have a semantic link.

## Infra profile and data services

An infra profile is a set of data services that store the credentials and access information that data products use to access data. You can define them using a yaml file and use the CLI to update them in your mesh.
