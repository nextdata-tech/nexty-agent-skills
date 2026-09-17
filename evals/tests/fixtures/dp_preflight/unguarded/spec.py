spec = (
    data_product(name="demo-product", version="1.0.0-dev")
    .input("pos-raw-data", source_aligned_input().source(ADLS))
    .output(
        data_product_output().port(
            "adls",
            storage(ADLS).managed_access().promise(
                custom("CHANNEL_CHECK")
                .script("contracts/channel_check.py")
                .service(service_name="adls", driver="nxd:kubernetes/contract:1.0.0")
            ),
        )
    )
)
