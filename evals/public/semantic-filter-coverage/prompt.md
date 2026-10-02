# Scenario: Preserve semantic query filters across models

You are helping an analyst answer questions against a deployed data product.
Use its semantic tools to discover the available models and concepts, then run
governed semantic queries and answer from the returned rows. Do not write or
execute raw SQL. Keep comparisons as comparisons and breakdowns as breakdowns.

## Task for the agent

Use the semantic MCP tools following the installed `nxd-query-data-product`
skill to reach the data product.

Answer these four questions using the semantic tools available in your session.
For each answer, briefly state the measure and scope you are querying, then
report the returned values in a compact table where that helps:

1. “How many enrolled patients do we have in the Gulf Coast region for
   Psychiatry & Neurology providers, by product?”
2. “Compare enrolled patients for Neurology vs Psychiatry & Neurology
   providers.”
3. “Enrolled patients by region.”
4. “How many enrolled patients are on BETAMAB in the SW Desert?”

Use the data product's catalog and semantic query tools; do not infer results
from the question wording alone.

## Required artifacts from the eval runner

- A deployed local-mesh data product with `list_models`, `describe_model`, and
  `run_semantic_query` available through the MCP gateway.
- The nxd query-data-product toolchain configured for the local mesh.

## Grading

Graded against the withheld `checks.json`. The questions test scoped filters,
cross-model dimensions, comparisons, pure breakdowns, and a verified zero.
