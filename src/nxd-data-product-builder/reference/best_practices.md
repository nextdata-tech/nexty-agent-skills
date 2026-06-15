# Best Practices

## Specification

* Usage of the infrastructure profile **name**, `infra_profile="<profile>"` (the profile chosen in discovery — e.g. a name returned by `nxd ls infra-profiles` against the active mesh), is preferred over the URL form `infra_profile="https://<app_url>/infra/<profile>"`. The profile name is elicited/derived, never a hardcoded demo name.
* **Service URLs in `.source(...)`, `.compute(...)`, `storage(...)` are full URLs, inlined.** Use the literal `https://<app_url>/infra-profile/<profile>#/services/<service>` at each call site rather than constructing them through a private helper. `<app_url>` resolves to the **active mesh's `app_url`** from mesh config (`~/.nxd/meshes.json`; see SKILL.md Prerequisites) — it is not a placeholder you leave literal or fill with a demo host. Keeping the URLs inline makes the spec greppable, mirrors the pattern in `nextdata-public-examples`, and avoids hiding the per-service binding behind indirection.
* **The compute service name is profile-specific — read the infra profile first.** Different profiles ship different names (`k8s-compute` in some, `k8s-executor` in others, plus Databricks/SageMaker variants). Don't assume; open the infra-profile YAML and pick the service whose `driver` classifies as Compute.
* **`spec.py` and `models.py` use `from nxd_spec import *` / `from nxd_models import *` — and those are project-local shim modules**, not packages from the `nxd` install. Create `nxd_spec.py` and `nxd_models.py` alongside `spec.py`, re-export every name the spec/models files use, and list each in `__all__`:

  ```python
  # nxd_models.py
  from nxd.spec import semantic_model
  from nxd.spec.data_types import string, date

  __all__ = ["semantic_model", "string", "date"]
  ```

  ```python
  # nxd_spec.py
  from models import amazon_sales
  from nxd.spec import (SupportedFormat, code, data_product, data_product_access,
                        data_product_output, owner, s3_config, snowflake_config,
                        source_aligned_input, storage)
  from nxd.spec.conditions import scheduled
  from transform import transform

  __all__ = ["SupportedFormat", "amazon_sales", "code", "data_product",
             "data_product_access", "data_product_output", "owner",
             "s3_config", "scheduled", "snowflake_config", "source_aligned_input",
             "storage", "transform"]
  ```

  Without these shims, `nxd validate` fails with `TypeError: 'StubModule' object is not iterable`.

## Transformation

* `@data_product.on_transform()` should be avoided when creating Python based Data Products. *Thus the usage of `.transform(code(transform_fn))` is also preferred within `spec.py` file(s)*.
* Usage of `nxd.data_product.context` is preferred over `nxd.core.context` when importing context classes.
* Most `with_*` functions have been deprecated, however they could still be present in examples. Ensure there isn't a suitable replacement prior to using them.
* Different context classes may have different attribute names which achieve the same purpose i.e. `AzureDataLakeStorage().model_paths` and `S3Output().model_output_paths`. Ensure context class attributes are valid when implementing them.

## Models

* Usage of `semantic_model().schema()` is preferred over `semantic_model(attributes=...)`.
* Usage of `semantic_model(name=...)` is preferred over `semantic_model("name")`, *as seen in "nextdata-public-examples"*.

## Contracts

* `@data_product.on_verify()` should be avoided when creating Python based Data Products. *Thus the usage of `.verify(code(verify_fn))` is also preferred within `spec.py` file(s)*.
    * ```python
      # example spec.py
      from contracts import example_contract 

      ...
      .port(...).promise(
          custom("example_contract").verify(
              code(example_contract.verify)
          )
          .model(example_model)
      )
      ...
      ```
    * ```python
      # example_contract.py
      from nxd.data_product.context import AzureDataLakeStorage
      from nxd.data_product.context import Model
      from nxd.data_product.context import VerifyResult
      from nxd.data_product.context import VerifyResultEnum


      def verify(
          adls: AzureDataLakeStorage,
          models: dict[str, Model],
      ) -> VerifyResult:

        result_enum = VerifyResultEnum.PASS
        ...


        return VerifyResult(
          result=result_enum,
          context={
              "additional_information": ...
          },
        )
      ```
