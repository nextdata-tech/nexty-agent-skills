---
name: nxd-source-aligned-data-product
description: Guided development of a Nextdata OS Data Product with "source aligned" inputs
context: fork
agent: Plan
metadata:
  author: nextdata
  version: 0.0.1
---

# Source-aligned Nextdata Data Product

Guided development of a Nextdata OS Data Product with "source aligned" inputs - `source_aligned_input()`, or in other-words, "off-mesh" datasets.

Run each steps in order. Ask questions conversationally — one step at a time. After each step, confirm the user's answers before moving on. Do not proceed past a failing step. Please do not skip any step and before making any assumptions or recommendations first get confirmation from the user.

## Step 1: Source Context

Gather context regarding the data source:

* Ask: "What are the input(s) for this Data Product? Please be as descriptive possible, what are the endpoints, tables etc."
* Ask: "Is there any documentation for this input that may be helpful? OpenAPI Specification etc."

## Step 2: Output & Transformation Context

* Ask: "Where should the resulting data be stored? As in what are Data Product's outputs?"
* Ask: "Do you have an exisiting ideal to how the output data should be structured? DDL etc."
* Ask: "Is there any additional context that may be helpful for the transformation? What embedding model to utilise, perfered libraries etc."

## Step 3: Data Product Basics

* Ask: "Please provide your instances URL e.g. https://app.demo.trynxd.com/"
* Ask: "What shall we call this Data Product?"
* Ask: "What should be the Data Product's outputs?"
* AskL "Which infrastructure profile should be used?"


## Step 4: Development Workspace Setup

Setup a Python project within a dedicated workspace, named after the data product. Utilise "uv" as the package and project manager and pin Python to version 3.10.

Install the `nxd-data-product` Python package from the registry found here: https://registry.trynxd.com/index/ since this will always be required.


## Step 5: Contruct the Data Product

Create the relevant key files for the given Data Product, if there is context missing, ambiguity or major design decisions, particularly in regards to the transformation implementation, please ask the user for clarity and, or confirmation.

### Additional resources
- For details regarding the files and structure of a Data Product, see [references/data_product_structure.md](references/data_product_structure.md)
- For high level details in implementing `data_product()` from the Python SDK, see [references/data_product_spec.md](references/data_product_spec.md)
- For high level details in implementing `semantic_model()` from the Python SDK, see [references/semantic_model_spec.md](references/semantic_model_spec.md)
- For examples of driver / service usage specifically within Nextdata and the Python SDK, see [references/driver_examples.md](references/driver_examples.md)
<!-- - For real-world examples, clone or browse the public examples repo:

  ```bash
  git clone https://github.com/nextdata-tech/nextdata-public-examples.git
  ```

  Each directory under `data_products/` is a complete data product (spec.py, transform.py, models, etc.). Use these as reference when generating files — pick the example closest to what the user is building. -->
