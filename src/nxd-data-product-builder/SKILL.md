---
name: nxd-data-product-builder
description: Guide for creating a high-quality Nextdata OS Python-based Data Product. Use when users want to create a data product from scratch.
metadata:
  author: nextdata
  version: 0.0.1
---

# Nextdata OS Data Product Builder

## Overview
Create and refine a Nextdata OS Python-based Data Product with guidance and clarity provided by the user.

## Communicating with the user
The Nextdata OS Data Product Builder skill is aimed at technical users, someone who is familiar with technical terms and technology. Rely on the user for clarity and guidance, keeping assumptions to the minimum.

---

## Prerequisites
Before engaging with the user please first setup the environment, you should not progress untill this is complete.

- **Runtime**: Python **3.10**, **`uv`** for dependencies.
- **Dependencies**: `nxd-data-product` Python package ([registry](https://registry.trynxd.com/index/))

```
uv init --bare --python 3.10
uv add nxd-data-product --source nxd=https://registry.trynxd.com/index/
```

*Critical: Do not trust internal knowledge regarding Nextdata OS and its Python packages. When utilising the `nxd` Python please verify its usage with the locally installed version.*

---

## Creating a Data Product

### Deep Research and Planning
Start by understanding the user's intent and the use-case for the new data product.

#### Research
The following references have been provided so a better understanding of what a Nextdata OS Data Product and how best to approach its implementation.

* Real-world examples of implemented data products: [reference/nextdata-public-examples](reference/nextdata-public-examples/)
* Overview of Nextdata OS concepts: [reference/concepts.md](reference/concepts.md)
* High-level information regarding building data products: [reference/build.md](reference/build.md)
* In-depth details regarding the critical `data_product()` function: [reference/data_product_spec.md](reference/data_product_spec.md)
* In-depth details regarding `semantic_model()`: [reference/semantic_model_spec.md](reference/semantic_model_spec.md)
* Nextdata OS Python spec API website: [reference/python/nxd/spec.html](https://docs.westpac.nextopia.dev/reference/python/nxd/spec.html)
* An example of running the `transform()` function locally: [reference/local_transform.md](reference/local_transform.md)
* Examples of how drivers (services) can be used within transformations: [reference/driver_examples.md](reference/driver_examples.md)

#### Interview
Proactively ask questions about edge cases, encourage the user to provide as much information as possible since this will lead to better outcomes. Information gather should be confirmed with the user before proceeding to the next step.

1. What is the purpose of this data product?
2. What will be the data product's inputs and outputs?
    1. What is the expected input and output formats?
3. What drivers (services) will this data product need to utilise?
    1. Does Nextdata OS currently support the chosen technologies?
    2. Can the user provide the name of the services and infrastructure profile that they belong to.
4. How should be approach data transformation, is there any patterns or tooling the user would prefer?
    1. Is there any documentation or third party information which can be provided to aid in creating the transformation? Documentation websites, OpenAPI specifications etc.

#### Additional Research
Depending the information provided by the user additional research is extremely likely needed to be performed, particularly is any of the following is true:

* Data will be sourced or processed via an "off-mesh" service like an API, website etc.
    * Ask the user for additional documentation like a reference website, OpenAPI specification.
    * Is there any suitable (up-to-date, well regarded) Python libraries that could be used?
    * Strongly suggest to the user to provide code snippets for interacting with the service, like a `request.get()` call.
    * If not already clear from documentation or code snippets, what is the expected data structure(s)?
* Data will be "vectorised" i.e. to be stored within a vector store like pgvector.
    * What embedding model should be utilised?
    * Should data be chunked and if so, what approach should be used?
    * Is there any prefered libraries to be used?

Since the above questions can be very specific, you may guide the user by offering recommendations and examples for them to confirm.

#### Planning
With all the information gathered from researching and by asking the user various questions, you should have everything you need to plan the implementation of a Data Product. Ideally this plan should be simple but still achieve the users end goals.

Construct your implementation plan and highlight critical areas to the user who can provide corrections and, or confirmation. Critical areas you may wish to highlight include but are not limited to:

* What input and outputs drivers (services) will be used
* An overview of the transformation, drawing particular attention to areas where you are least certain

### Implementation
With a plan ready and confirmed with the users lets begin implementation.

At anypoint during implementation you are free to add "TODO" entries with relevant instructions for the user if any of the following are true:
* The user has not provided satisfactory information even after prompting.
* There are implementation details which would greatly benefit from the user manually intervening.

#### Structure
Refer to [reference/build.md](reference/build.md) for details on how to structure a data product. Focus on key files since not all files are quired.

#### `spec.py`
Refer to [reference/data_product_spec.md](reference/data_product_spec.md) for details on the critical function `data_product()` present within the `spec.py` files.

Ensure the following are present, if needed prompt the user for information:
* Infrastructure profile
* Each driver (service) has its URL set whether it is an input (`source()`) or output (`storage()` etc.)

`spec.py` can not be ran locally since they require the Nextdata OS hosted runtime.

#### `models.py`
Refer to [reference/semantic_model_spec.md](reference/semantic_model_spec.md) for details on creation of models, specifically the `semantic_model()` function.

Avoid complex types where possible due to compatibility issues.

#### `transform.py`
Refer to [reference/nextdata-public-examples](reference/nextdata-public-examples/) for multiple examples of transformations.

Remeber to utilise Nextdata Context's, `from nxd.core.context import *` to pass configuration, credentials and models for each given input or output driver (service).

### `nxd` Library
The `nxd` library should already be installed by this skill within the virtual environment, refer to that for specific implementation details.

### Drivers
Refer to [reference/driver_examples.md](reference/driver_examples.md) for specific examples of using drivers within Nextdata OS.

#### Transformation Validation
While the transformation function, `transform(...)` is designed to be ran within the Nextdata OS platform, it is likely worth creating an additional file which can execute the file locally - very useful for testing. Refer to [reference/local_transform.md](reference/local_transform.md) for an existing example.

### Evaluation
Once implementation has been completed, inform the user and like with planning highlight critical areas to the user include any parts or prompts which may need to be completed by them manually, such as "TODO" entries.
