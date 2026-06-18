# Private Evals

Put customer-specific and commercial-demo eval scenarios here locally.

This folder is ignored by git except for this README. Do not commit customer names, schemas, transcripts, logs, credentials, proprietary requirements, or acceptance diffs to the shared skill repository.

## Runtime-only scenarios

Some scenarios cannot be graded by the headless `run.py` loop because they need
a **live runtime** the harness does not provision — e.g. a running data product
exposing MCP tools, or a real warehouse connection. The headless agent only gets
static `fixtures/`, so it has no `list_metrics` / `run_semantic_query` to call
and falls back to reconstructing answers from source files, which fails the
tool-call checks even when the underlying skill is correct.

Keep these here (local, un-shipped) and run them manually against a live mesh.
Currently parked for this reason — both are **consumer** scenarios for the
**nxd-data-product-query** skill (its §6d "Semantic-layer MCP ports"), exercising
how an agent queries a deployed semantic DP, NOT how the producer skill builds one:

- `semantic-query-nl-to-answer` — needs the four semantic MCP tools live.
- `chasm-trap-fan-out-defended` — needs a live `run_semantic_query` to return
  the mixed-grain `CompileError` the scenario grades.

The producer **build** scenario `generate-semantic-layer-dp-from-schema` stays
public under the **nxd-semantic-data-product** skill: it is pure authoring (the
agent writes the registry + wiring), graded by reading the produced files, and
passes headlessly (9/9).
