from nxd.data_product.context import VerifyResult, VerifyResultEnum


def verify(adls, models) -> VerifyResult:
    observed = read_channels(adls)
    if set(observed) - {"store", "kiosk"}:
        return VerifyResult(VerifyResultEnum.FAILED, {"result": "unexpected channel"})
    return VerifyResult(VerifyResultEnum.PASS, {"result": "ok"})
