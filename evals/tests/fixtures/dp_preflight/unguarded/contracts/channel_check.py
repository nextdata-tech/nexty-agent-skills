from nxd.data_product.context import VerifyResult, VerifyResultEnum


def verify(input, models) -> VerifyResult:
    return VerifyResult(VerifyResultEnum.PASS, {"result": "Looks good"})
