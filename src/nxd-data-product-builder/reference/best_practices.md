# Best Practices

## Specification

* Usage of the infrastructure profile names, `infra_profile="ecommerce"`, is preferred over URLs `infra_profile="https://nextopia.dev/infra/ecommerce"`

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
