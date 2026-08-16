# Terminal field-mapper adapter contract

Create a local NXD mapper transform using the documented public provider seam.
The evaluator supplies a synthetic provider and a per-run `nxd-desktop` MCP
server; do not use network access or a real credential.

The transform must construct `make_call(...)` with an explicit credential
policy, pass its result to `map_inputs(...)`, and preserve the callback shape
`item`, `spec`, `wire_schema`, `violations`. Treat a parsed mapping as the only
valid provider result. Do not import a provider SDK, reach into mapper transport
or ledger modules, return a raw provider message, or introspect proposal
internals.

Use the connected `nxd-desktop` MCP tools to run the supplied synthetic build
and inspect its result. Report only the sanitized machine status; never repeat
credentials or provider payloads.
