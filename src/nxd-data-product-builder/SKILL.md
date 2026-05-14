---
name: nxd-data-product-builder
description: Guide for creating, refining, and validating a Nextdata OS Python-based Data Product. Use whenever the user mentions building, scaffolding, or iterating on an `nxd` Data Product, references files like `spec.py`, `models.py`, or `transform.py`, or asks about Nextdata OS drivers, semantic models, or transformations. Do not use for generic Python data pipelines unrelated to Nextdata OS.
metadata:
  author: nextdata
  version: 0.1.1
---

# Nextdata OS Data Product Builder

## Overview
Support the design, planning, implementation, and refinement of a Nextdata OS Python-based Data Product through structured collaboration with the user. Rely on verified references and confirm decisions at every step.

This Skill is intended for technically proficient users who are familiar with technical terms and concepts. Minimise assumptions and seek clarity from the user throughout the workflow.

---

## Prerequisites
Before engaging with the user, set up the environment. Do **not** proceed until this is complete.

- **NXD CLI:** Ensure the NXD CLI is installed and the correct mesh is selected, this should be set up and verified by the "nxd-setup" Skill. *Confirm the correct mesh has been selected before continuing.*
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
Copy this checklist into your response and tick items off as you complete them:

```
Data Product Build Progress:
- [ ] 0. Prerequisites verified (NXD CLI, mesh selected, uv env, nxd-data-product installed)
- [ ] 1. Discovery complete (interview answered, references consulted)
- [ ] 2. Plan approved by user
- [ ] 3. Implementation complete (spec.py, models.py, transform.py)
- [ ] 4. Validation complete (local transform script in place, TODO markers labelled, `nxd validate` passes)
- [ ] 5. Handover summary and finalisation checklist delivered to the user
```

### 1. Discovery and Requirements Gathering
Start by deeply understanding the user's intent, objectives, and requirements for the proposed Data Product.

#### Research
Consult the following references for concepts, APIs, and best practices:

* Real-world examples of implemented Data Products: [reference/nextdata-public-examples](reference/nextdata-public-examples/)
    * Ignore the single-import rule present within examples, it does not apply to newly built Data Products.
* Information regarding best practices, preferred approaches and more: [reference/best_practices.md](reference/best_practices.md)
* Overview of Nextdata OS concepts: [reference/concepts.md](reference/concepts.md)
* Data Product structure and build process: [reference/build.md](reference/build.md)
* In-depth details of the critical `data_product()` function: [reference/data_product_spec.md](reference/data_product_spec.md)
* In-depth details of `semantic_model()`: [reference/semantic_model_spec.md](reference/semantic_model_spec.md)
* Running `transform()` locally: [reference/local_transform.md](reference/local_transform.md)
* Examples of drivers (services) used within transformations: [reference/driver_examples.md](reference/driver_examples.md)

#### Interview
Proactively gather details from the user, including edge cases. Confirm gathered information before advancing to the next stage.

1. What is the intended purpose and outcome of this Data Product?
2. What are the Data Product's expected inputs and outputs?
    1. What are the expected input and output formats?
3. What drivers (services) will this Data Product need to utilise?
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
Use all gathered information to create a clear, actionable plan for the Data Product's implementation. Ideally the plan should be simple while still achieving the user's end goals.

Highlight critical decisions, uncertainties, and options for explicit user confirmation, including:

* The input and output drivers (services) that will be used and their configuration.
* A high-level overview of the transformation pipeline, drawing particular attention to areas where you are least certain.

Share the plan for explicit user approval before moving forward.

---

### 3. Implementation
Begin implementation once the plan is finalised. Insert "TODO" markers with clear instructions wherever any of the following are true:

* The user has not provided satisfactory information even after prompting.
* There are implementation details that would greatly benefit from manual user intervention.

#### `spec.py`
* Ensure the infrastructure profile is included.
* Configure each driver (service) with the appropriate URLs and settings, whether it is an input (`source()`) or an output (`storage()` etc.).
* Note: `spec.py` cannot be run locally — it requires the Nextdata OS hosted runtime.

#### `models.py`
* Avoid complex types in semantic models where possible, due to compatibility limitations.

#### `transform.py`
* Use Nextdata Contexts via explicit imports (e.g. `from nxd.data_product.context import AzureDataLakeStorage`) to pass configuration, credentials, and models for each input or output driver. Prefer explicit imports over wildcard imports within the transformation file(s).
* Parameter names in the `transform(...)` signature must match the input and output-port names declared in `spec.py`. For example, `.input("comp_public", source_aligned_input()...)` binds to `def transform(comp_public: API, ...)`, and `.port("adls", storage(...))` binds to `adls: AzureDataLakeStorage`. Hyphens in spec names are normalised to underscores in the Python signature (e.g. `"s3-source"` → `s3_source`).

#### `nxd` Library
The `nxd` library should already be installed in the virtual environment by the prerequisites step. Always refer to the locally installed version for implementation details rather than relying on prior knowledge.

#### Transformation Validation
Although the `transform(...)` function is designed to run within the Nextdata OS platform, it is worth creating an additional script that can execute it locally — this is very useful for testing. Any Python libraries required only for running the transformation locally should be added as development dependencies (e.g. `uv add --dev <package>`) so they are recorded in `pyproject.toml` without being treated as runtime dependencies of the Data Product, *including `python-dotenv` if used*.

---

### 4. Validation
Once implementation is complete, validate the Data Product before handover. Track progress with the following checklist:

```
Validation Progress:
- [ ] Local transform script in place; imports resolve and function signatures match declared context types
- [ ] All "TODO" markers inserted and clearly labelled
- [ ] `nxd validate --config=/tmp/nxd-<mesh_name>.yaml <data_product_directory> --debug` passes
```

If `nxd validate` reports errors, read the output carefully, fix the issue in `spec.py`, `models.py`, or `transform.py`, and re-run until the command exits cleanly. Do not mark item 4 complete on the top-level checklist until validation passes.

Note: `nxd validate` checks structural correctness of the spec and parsed models — it does not execute the transform against real services. End-to-end runtime validation is performed by the user in the Finalisation step.

---

### 5. Finalisation and Handover
Once implementation is complete, deliver a handover summary to the user and include the following checklist for them to work through:

```
Finalisation (user to complete):
- [ ] Review all "TODO" markers; resolve or explicitly defer each
- [ ] Populate `.env` (or equivalent) with credentials and configuration for local execution
- [ ] Run the local transform script and confirm it completes end-to-end
- [ ] Launch the Data Product on the mesh: `nxd launch --dir <data_product_directory> --config=/tmp/nxd-<mesh_name>.yaml`
- [ ] Verify the first platform run: transform completes, outputs land at configured ports, promises/expectations pass
```

In the handover summary, call out any items needing particular attention — deferred TODOs, missing inputs, areas where assumptions were made, or sections that may require manual review.
