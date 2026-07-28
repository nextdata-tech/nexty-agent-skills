from nxd.spec import semantic_model, string, timestamp

customer_profile = semantic_model("customer_profile").schema(
    {
        "customer_id": string(),
        "email": string(),
        "full_name": string(),
        "phone_number": string(),
        "postal_code": string(),
        "signup_ts": timestamp(),
    }
).tags(
    {
        # Attribute-level classification consumed by the sensitivity contract.
        "email": {"classification": "restricted", "handling": "tokenized"},
        "full_name": {"classification": "restricted", "handling": "masked"},
        "phone_number": {"classification": "restricted", "handling": "masked"},
        "postal_code": {"classification": "internal", "handling": "none"},
    }
)
