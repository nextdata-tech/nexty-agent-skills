"""Sensitivity contract for customer-profiles-curated.

Executed by the SensitivityCompliance policy. The policy supplies the
configured parameters; this code decides whether the data product satisfies
them.
"""

from nxd.policy import PolicyContext, PolicyResult, contract


@contract
def verify_sensitivity(ctx: PolicyContext) -> PolicyResult:
    """Fail when an attribute carrying a restricted classification is exposed
    on an output port without an approved handling tag."""
    required_level = ctx.parameters["minimum_classification"]
    allowed_tags = set(ctx.parameters["approved_handling_tags"])

    violations = []
    for port in ctx.data_product.output_ports:
        for attribute in port.attributes:
            classification = attribute.tags.get("classification")
            if classification != required_level:
                continue
            handling = attribute.tags.get("handling")
            if handling not in allowed_tags:
                violations.append(
                    f"{port.name}.{attribute.name} is classified "
                    f"{classification} but carries handling={handling!r}"
                )

    if violations:
        return PolicyResult.fail("; ".join(violations))
    return PolicyResult.ok()
