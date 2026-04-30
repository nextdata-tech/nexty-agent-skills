---
name: nxd-data-product-builder
description: Guide for creating, refining, and validating a Nextdata OS Python-based Data Product. Use whenever the user mentions building, scaffolding, or iterating on an `nxd` data product, references files like `spec.py`, `models.py`, or `transform.py`, or asks about Nextdata OS drivers, semantic models, or transformations. Do NOT use for generic Python data pipelines unrelated to Nextdata OS.
metadata:
  author: nextdata
  version: 0.1.1
---

# Nextdata OS Data Product Builder

## Overview
Support the design, planning, implementation, and refinement of a Nextdata OS Python-based data product through structured collaboration with the user. Rely on verified references and confirm decisions at every step.

## Communicating with the user
This skill is intended for technically proficient users who are familiar with technical terms and concepts. Minimise assumptions and seek clarity from the user throughout the workflow.

---

## Prerequisites
Before engaging with the user, set up the environment. Do **not** proceed until this is complete.

- **Runtime:** Python **3.10** with **`uv`** as the dependency manager.
    - *There is no need to check for a given Python version since `uv` will manage this for us.*
- **Dependencies:** Install the `nxd-data-product` Python package ([registry](https://registry.trynxd.com/index/)):

```
uv init --bare --python 3.10
uv venv --python 3.10
uv add nxd-data-product --index nxd=https://registry.trynxd.com/index/
```

*Critical: Do not rely on internal or assumed knowledge regarding Nextdata OS or its Python packages. Always verify usage against the locally installed version of the `nxd` Python package.*

---

## Data Product Creation Workflow

### 1. Discovery and Requirements Gathering
Start by deeply understanding the user's intent, objectives, and requirements for the proposed data product.

#### Research
Consult the following references for concepts, APIs, and best practices:

* Real-world examples of implemented data products: [reference/nextdata-public-examples](reference/nextdata-public-examples/)
* Overview of Nextdata OS concepts: [reference/concepts.md](reference/concepts.md)
* Data product structure and build process: [reference/build.md](reference/build.md)
* In-depth details of the critical `data_product()` function: [reference/data_product_spec.md](reference/data_product_spec.md)
* In-depth details of `semantic_model()`: [reference/semantic_model_spec.md](reference/semantic_model_spec.md)
* Running `transform()` locally: [reference/local_transform.md](reference/local_transform.md)
* Examples of drivers (services) used within transformations: [reference/driver_examples.md](reference/driver_examples.md)

#### Interview
Proactively gather details from the user, including edge cases. Confirm gathered information before advancing to the next stage.

1. What is the intended purpose and outcome of this data product?
2. What are the data product's expected inputs and outputs?
    1. What are the expected input and output formats?
3. What drivers (services) will this data product need to utilise?
    1. Does Nextdata OS currently support the chosen technologies?
    2. Can the user provide the names of the services and the infrastructure profile they belong to?
4. How should we approach data transformation? Are there any patterns or tooling the user would prefer?
    1. Is there any documentation or third-party information that can be provided to aid in creating the transformation (e.g. documentation websites, OpenAPI specifications)?

#### Directed Research
Based on the user's answers, perform additional research as needed, particularly if any of the following is true:

* Data will be sourced or processed via an "off-mesh" service such as an API or website.
    * Request supporting documentation, such as a reference website or OpenAPI specification.
    * Identify suitable (up-to-date, well-regarded) Python libraries that could be used.
    * Strongly suggest that the user provides example code snippets for service integration, such as a `requests.get()` call.
    * If the expected data structure is not clear from documentation or code snippets, confirm it with the user.
* Data will be "vectorised" — i.e. stored within a vector store such as pgvector.
    * Determine the preferred embedding model.
    * Decide on a chunking strategy if required.
    * Confirm any library preferences with the user.

Where the questions are very specific, guide the user by offering recommendations and examples for them to confirm.

### 2. Planning and Design
Use all gathered information to create a clear, actionable plan for the data product's implementation. Ideally the plan should be simple while still achieving the user's end goals.

Highlight critical decisions, uncertainties, and options for explicit user confirmation, including:

* The input and output drivers (services) that will be used and their configuration.
* A high-level overview of the transformation pipeline, drawing particular attention to areas where you are least certain.

Share the plan for explicit user approval before moving forward.

---

### 3. Implementation
Begin implementation once the plan is finalised. Insert "TODO" markers with clear instructions wherever any of the following are true:

* The user has not provided satisfactory information even after prompting.
* There are implementation details that would greatly benefit from manual user intervention.

#### Project Structure
Refer to [reference/build.md](reference/build.md) for guidance on structuring the data product. Focus on the key files described below — not all files are required.

#### `spec.py`
* Refer to [reference/data_product_spec.md](reference/data_product_spec.md) for details on implementing the mandatory `data_product()` function.
* Ensure the infrastructure profile is included.
* Configure each driver (service) with the appropriate URLs and settings, whether it is an input (`source()`) or an output (`storage()` etc.).
* Note: `spec.py` cannot be run locally — it requires the Nextdata OS hosted runtime.

#### `models.py`
* Refer to [reference/semantic_model_spec.md](reference/semantic_model_spec.md) for details on `semantic_model()`.
* Avoid complex types in semantic models where possible, due to compatibility limitations.

#### `transform.py`
* Refer to [reference/nextdata-public-examples](reference/nextdata-public-examples/) for multiple examples of transformations.
* Use Nextdata Contexts via explicit imports (e.g. `from nxd.core.context import context`) to pass configuration, credentials, and models for each input or output driver. Prefer explicit imports over wildcard imports.

#### Drivers
Refer to [reference/driver_examples.md](reference/driver_examples.md) for specific examples of using drivers within Nextdata OS.

#### `nxd` Library
The `nxd` library should already be installed in the virtual environment by the prerequisites step. Always refer to the locally installed version for implementation details rather than relying on prior knowledge.

#### Transformation Validation
Although the `transform(...)` function is designed to run within the Nextdata OS platform, it is worth creating an additional script that can execute it locally — this is very useful for testing. See [reference/local_transform.md](reference/local_transform.md) for an existing example. Any Python libraries required only for running the transformation locally should be added as development dependencies (e.g. `uv add --dev <package>`) so they are recorded in `pyproject.toml` without being treated as runtime dependencies of the data product.

---

### 4. Finalisation and Handover
Once implementation is complete, notify the user and reiterate any areas that need manual input or review. Clearly highlight any "TODO" entries or incomplete sections requiring the user's attention before the data product is considered finalised.
