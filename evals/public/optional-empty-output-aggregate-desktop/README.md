# Optional empty output and aggregate-only desktop E2E

This opt-in scenario is the live desktop companion for the optional physical
output contract. It starts with a synthetic mapper-shaped order export, asks an
agent to author a Python-only closure, and then uses the local supervisor to
publish, describe, group-query, and stop the product.

The runner-side verifier owns the ground truth. It re-serves the landed closure
from a fresh temporary state directory, checks that `reviews` remains a
catalog-visible optional model without a physical source, and verifies the
governed `COUNT(*)` result by `product_category` contains only aggregate
columns.

The scenario is intentionally `ci_skip`: CI does not provision the compatible
desktop supervisor and its Python environment. Run it locally with
`EVAL_DESKTOP_SUPERVISOR_DIR` and `EVAL_DESKTOP_PYTHON` set. Native compiler
execution is not asserted by this scenario and is a separate follow-up that
needs the compiler/runtime fixture provisioned.
