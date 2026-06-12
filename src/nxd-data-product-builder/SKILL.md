---
name: nxd-data-product-builder
description: Guide for creating, refining, and validating a Nextdata OS Python-based Data Product. Two discovery modes — interactive interview, or spec-from-document (e.g. a candidate in a `mesh-assets-PROFILE.md` report produced by `nexty-mesh-analyzer`). Use whenever the user mentions building, scaffolding, or iterating on an `nxd` Data Product, references files like `spec.py`, `models.py`, or `transform.py`, or asks about Nextdata OS drivers, semantic models, or transformations. Do not use for generic Python data pipelines unrelated to Nextdata OS.
metadata:
  author: nextdata
  version: 0.2.1
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
- [ ] 1. Discovery complete (interview answered OR spec-from-document extracted; infra profile located; references consulted)
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
* Debugging a deployed Data Product (symptom → root cause → fix): [reference/troubleshooting.md](reference/troubleshooting.md)

#### Discovery Source — interview or spec-from-document
Decide once, up front, how the Data Product's requirements will be sourced. Ask the user which mode applies:

* **Interactive interview** (default) — work through the questions in **Interview** below.
* **Spec-from-document** — the user points at one or more documents that already describe the Data Product. The canonical case is a candidate `#N` in a `mesh-assets-<profile>.md` report produced by the **`nexty-mesh-analyzer`** skill, paired with its companion `mesh-assets-<profile>-models.md` for input/output schemas. Phrases like *"build the data product described by #41 in mesh-assets-daff.md"* trigger this branch.

If spec-from-document is chosen, follow **Spec-from-Document** below in place of Interview. Either branch must end with the same outputs: the candidate's purpose, inputs/outputs (with locations, services, formats), drivers, and any transformation notes. Confirm the extracted answers with the user before moving on to step 2.

#### Spec-from-Document
For each document path the user supplies (file path or `http(s)://` URL), read it and extract the requirements that would otherwise come from Interview. Where the document is missing an answer, fall back to asking the user just that question.

**Mesh-assets report — the primary supported format.** A `mesh-assets-<profile>.md` lists candidates grouped by domain, each numbered (`#### 41. \`<name>\``). Each candidate carries:

- *Suggested data product name* — use as the Data Product name unless the user overrides.
- *Domain*, *Infra profile*.
- *Classification* — `source-aligned` or `transformed` (with confidence). Source-aligned + file→database typically means lift-and-shift with minimal logic; transformed means real reshaping.
- *Input data source* — `location`, `service`, `service URL`. The service name maps to a service in the infra profile (see Infra Profile Lookup below).
- *Output data source* — same three fields.
- *Evidence* — schema jaccard, shared tokens, lineage signals. Read this — high jaccard + source-aligned says the transform is essentially a passthrough; a long shared-token list hints at columns to forward verbatim.

Pair the report with its companion `mesh-assets-<profile>-models.md`. That file has one section per candidate (matched by number) with full input and output schemas as `| column | type |` tables. Use these to seed `models.py` semantic models.

If the user refers to a candidate by number (`#41`) or by name (`top-playlists`), locate that block in both files and read it. If the user gives only the report file with no candidate selector, present the candidates grouped by domain and ask which one to build.

Other document shapes — plain markdown or text describing a Data Product — are supported best-effort: read the document, extract whatever maps onto the Interview questions, then ask the user to fill any gaps.

#### Infra Profile Lookup
Both discovery branches need to know the infra profile file to wire services into `spec.py`. Locate it the same way `nexty-mesh-analyzer` does, then confirm with the user.

Search, in order:

1. Customer extension paths — `./.nxd/skills/nxd-data-product-builder/` and `~/.nxd/skills/nxd-data-product-builder/`.
2. Working tree — `infra-profiles/*.yaml`, `infra-profiles/*.yml`, `*.yaml`, `*.yml`.

For each candidate file, confirm with `Grep` that it has `kind: Profile` and `apiVersion: infra.nextdata.com/...` near the top. Resolve **pointer files** — a file whose contents are filesystem path(s) or URI(s), one per line — by following each pointer (read file paths, fetch `http(s)://` URIs).

Present every match and let the user pick one, or paste a path / URI directly. When the discovery source is a mesh-assets report, prefer the profile whose `metadata.name` matches the candidate's *Infra profile* field.

**Credentials.** The chosen profile holds live secrets in plaintext. Treat it the same way `nexty-mesh-analyzer` does:

- Never echo a secret value to chat or display it on a command line.
- When the builder needs service attributes (URLs, account names, bucket names) to populate `spec.py`, read them out of the profile and put them in `spec.py` — but pull credential values (passwords, access keys, tokens, client secrets, PEM blocks) into `.env` placeholders instead, with a `TODO` marker.
- The local transform script reads credentials from the environment, never from `spec.py`.

#### Interview
Use this branch when discovery source is **interactive interview**. Proactively gather details from the user, including edge cases. Confirm gathered information before advancing to the next stage.

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
* Ensure the infrastructure profile is included (by name — `infra_profile="<name>"`).
* Configure each driver (service) with the appropriate URLs and settings, whether it is an input (`source()`) or an output (`storage()` etc.).
* Service URLs are full and inlined: `https://<mesh>/infra-profile/<profile>#/services/<service>` — used as-is in `.source(...)`, `storage(...)`, `.compute(...)`. Do not abstract behind a helper.
* Read the chosen infra profile YAML to discover the correct service names; the compute service name in particular varies between profiles (`k8s-compute`, `k8s-executor`, a Databricks compute, etc.).
* Project-local `nxd_spec.py` and `nxd_models.py` shim modules are required — the wildcard imports in `spec.py` / `models.py` resolve through these. See `reference/best_practices.md` for the template.
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

If the launched Data Product fails or behaves unexpectedly, work through
[reference/troubleshooting.md](reference/troubleshooting.md) — it maps the
platform's error messages (which are often misleading, e.g. OOM reported as
"startup timeout") to root causes and fixes.

In the handover summary, call out any items needing particular attention — deferred TODOs, missing inputs, areas where assumptions were made, or sections that may require manual review.
