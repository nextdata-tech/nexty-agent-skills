# Terminal self-check provenance

The starter closure is already materialized in the workspace root and is the
only authored data product. The connected `nxd-desktop` MCP server is the
supported supervisor surface for this task.

## Task for the agent

Use only the connected `mcp__nxd-desktop__check_data_product` tool on the
workspace-root starter closure. Do not invoke a copied helper from a plugin
cache, an unrelated checkout, or a direct Python self-check script. Use workflow
`terminal-self-check-provenance`. Record the structured outcome, all four stage
summaries, the stable finding codes, the content-addressed `definition_id`, and
the interpreter/package provenance. Treat `skip` as unexamined, never as pass.

Then create these sibling test cases under `.eval-cases/` (copy the starter
closure first so each case is independent) and call the same MCP tool on each:

* `malformed-dp-spec`: make the actual pinned `deployment-spec.yaml` malformed
  YAML (this is the supervisor's deployment-spec artifact; do not invent a
  separate `dp-spec.md` helper).
* `missing-transform-source`: remove the declared `transform/main.py` source.
* `failed-import`: make `transform/main.py` import a module that is not present.
* `failed-transform`: keep `transform/main.py` syntactically valid but register
  the transform hook without invoking the lifecycle entrypoint, so the
  self-check can distinguish this from a missing import.
* `missing-helper`: create `helper.py` at the CASE ROOT itself (not under
  `transform/`, `contracts/`, or `data/`), make `transform/main.py` import
  `helper`, and leave that root-level helper in the authoring case. The
  supervisor pin intentionally drops that location, so the report must classify
  it as `runtime/companion_missing`, distinct from `runtime/import_failed`.

For every case report only the supervisor-derived outcome and codes. Explain
which stage ran and which stages were skipped, if any. A finding may not be
called passed when its check was skipped or the MCP response was an error.
Use the returned `definition_id` and provenance to show which pinned closure
was checked when the supervisor seals a snapshot. For a malformed structural
case, report that no snapshot was pinned and that `definition_id` is absent; do
not invent an identity for an unsealed source. Do not claim that a direct
script run is equivalent to the MCP check.

Finally, mutate a source file in the starter authoring closure and run the
supervisor check again. Report both content-addressed IDs and explain that a
changed ID is a different pinned snapshot; do not describe the second result
as the first snapshot being rechecked.

Do not use network access, real credentials, or provider SDKs. Do not print
secret-bearing tool arguments or raw provider payloads.
