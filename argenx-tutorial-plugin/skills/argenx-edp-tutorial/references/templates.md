# File templates & walkthroughs

Exact contents for the files the tutorial produces, with line-by-line explanations to read
*to* the learner. Hand out one block at a time — never the whole file at once.

> Source of truth: these mirror the argenx EDP reference data product and the
> [argenx EDP guide](https://nxd.aks.argenx-dev.com/docs/#/tutorials/guides/README). If the
> scaffolded / copied files differ from what's here, **trust the actual files in the project**
> and adapt.

---

## pyproject.toml

Created in Step 2. The two things that matter: the **argenx package registry index** (so
`uv` can find the `nxd-*` libraries) and the **three Nextdata dependencies**.

```toml
[project]
name = "my-first-dp"
version = "0.1.0"
description = "My first Nextdata data product on argenx"
requires-python = ">=3.11"
dependencies = [
    "nxd-core",
    "nxd-drivers",
    "nxd-data-product",
]

[[tool.uv.index]]
name = "nxd"
url = "<argenx-package-registry-index-url>"   # confirm from nxd-setup / the team

[dependency-groups]
dev = [
    "pandas-stubs<=2.1.4",
    "pyright>=1.1.403",
    "ruff>=0.12.8",
]

[tool.ruff]
extend-exclude = ["*.pyi"]
include = ["./**/*.py"]
line-length = 120

[tool.ruff.lint]
extend-select = ["I"]

[tool.ruff.lint.isort]
force-single-line = true
```

What to say: *"This file just tells Python which Nextdata building blocks to download and
where to get them. You'll rarely touch it again."*

> The exact registry index URL is environment-specific and **must be confirmed** (from the
> `nxd-setup` flow or the argenx team) — don't invent it. If `uv sync` can't reach the index,
> see `references/troubleshooting.md`.

---

## spec.py — incremental walkthrough

Build this up in four blocks. After each, explain and confirm.

### Block 1 — the skeleton

```python
from edp.dp_specs import argenx_dp

spec = argenx_dp(
    name="my-first-dp",
    domain="my-first-dp",
    description="A simple data product using the argenx EDP framework.",
    infra_profile="<infra_profile_name>",
    version="0.1.0-dev",
    owner_email="<your-email>",
    schedule="*/20 * * * *",
)
```

Explain: *"`argenx_dp(...)` is the argenx helper that wraps all the standard conventions. We
fill in a name, who owns it, which **infra profile** (the bundle of credentials/services to
use), and how often it should run — `*/20 * * * *` means every 20 minutes."* Define **infra
profile** and **schedule (cron)** here (see `glossary.md`).

### Block 2 — inputs

```python
from edp.ingestion import IngestionSource

spec = argenx_dp(
    ...
    inputs=[
        IngestionSource(name="salesforce-api", service="salesforce-api"),
    ],
    ...
)
```

Explain: *"An **input** is where data comes from. Here we name it and point it at a service
in the infra profile. The name becomes available in the transform as `salesforce_api`
(hyphens become underscores)."* This is the line to later swap for Alation — see
`alation-target.md`.

### Block 3 — outputs

```python
from nxd.spec import semantic_model
from nxd.spec.data_types import int64, string
from edp.outputs import SnowflakePort

spec = argenx_dp(
    ...
    outputs=[
        SnowflakePort(
            port_name="example-snowflake-output",
            schema="tutorials",
            models=[
                semantic_model(
                    name="example_model",
                    description="Example model description",
                ).schema(
                    {
                        "example_str": (string(), "Example string attribute"),
                        "example_int": (int64(), "Example integer attribute"),
                    }
                )
            ],
        )
    ],
    ...
)
```

Explain: *"An **output / port** is where results land — here, a Snowflake schema. The
**semantic model** describes the shape of the data: named, typed fields. This is what makes
the product discoverable and governed instead of just a table."* Define **port**, **semantic
model**, **schema** (see `glossary.md`).

### Block 4 — wire in the transform

```python
from transform import transform

spec = argenx_dp(
    ...
    transform_fn=transform,
    ...
)
```

Explain: *"Finally we hand the product the function that does the actual work — we'll write
that next."*

---

## transform.py

Keep the first version trivial so the learner sees an end-to-end success before adding logic.

```python
from nxd.data_product.context import API, Snowflake


def transform(
    salesforce_api: API,             # input  (matches inputs[].name, hyphens -> underscores)
    example_snowflake_output: Snowflake,  # output (matches port_name, hyphens -> underscores)
) -> None:
    # Read from the input service.
    salesforce_api["domain"]

    # Reach the output destination (database/schema available here).
    example_snowflake_output.database
    example_snowflake_output.schema

    # TODO: real logic — read records, shape them, write to the output. Keep it empty
    # for the first successful deploy.
```

The **one rule** to emphasize: *"The parameter names here must exactly match the input and
output names from the spec, with hyphens turned into underscores. `salesforce-api` →
`salesforce_api`, `example-snowflake-output` → `example_snowflake_output`. If they don't
match, `nxd validate` will tell you."*

---

## Launch

```bash
nxd validate   # checks the spec before deploying
nxd launch     # deploys to argenx
```

After success: `nxd ls data-products` shows it live. See SKILL.md *Step 6*.
