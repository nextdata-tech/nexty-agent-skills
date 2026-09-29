# Terminal authenticated DLT API ingestion

## Task for the agent

Read `BRIEF.md` and use only the connected `mcp__nxd-desktop__*` tools for the
data-product lifecycle. `ENDPOINT_URL` is a runner-provided local REST fixture
input. The credential value is available only to the trusted runtime; the
public profile contains the name `NXD_EVAL_SOURCE_TOKEN`, never its value.

Build a small data product for the paginated orders API using the DLT REST
connector. Set the public `base_url` to the runner-provided URL in
`ENDPOINT_URL`, and set `endpoint_orders` to the path `/v1/orders`; do not use a
complete URL for the endpoint path or create an endpoint companion file. Put
the required public header in the API profile as described in `BRIEF.md`. The
transform must read that profile at runtime and resolve its credential through
`os.environ[secrets["credential_env"]]`. Do not put a credential value in a
profile, source, command, or output, and do not use a hand-written
requests/urllib/httpx loop. For this evaluation, the `BRIEF.md` request-window
contract is a task-specific exception to the general api-source standalone
`connectivity_check.py` step: do not create or run that probe or any other
direct HTTP helper. Make source requests only through the DLT connector during
the four workflow `validation` executions and the positive `start_run`.

Configure exactly two REST resources over `secrets["endpoint_orders"]`:
`orders` with no query parameters and `paid_orders` with the bounded source
parameter `status=paid`. For both resources, use `data_selector: "data"` and
the DLT page-number paginator with `base_page: 1`, `page_param: "page"`, and
`total_path: "pages"`; do not override the API's page size. Do not create a
second HTTP client or fetch loop.

For each resource, use a DLT response action to retain only each response's
`page`, `pages`, `total`, and the number of rows in `data`, returning the
response unchanged. After the DLT run, fail closed unless pages `1..pages`
were each observed exactly once, `pages` and `total` agree across responses,
the observed row counts sum to the envelope `total`, and the landed row count
for that resource equals the same total. Once both resources reconcile, also
fail closed unless the landed `orders` rows whose `status` is `paid` equal the
landed paid-resource row count; this is the closure's own check that the
governed paid answer matches the paid resource. Never hard-code a total or include
row values or credentials in diagnostics. The landed table must contain order
rows only; reject any landed `page`, `per_page`, `total`, or `pages` columns.

Complete exactly four workflow cycles, with these unique workflow names:
`nex890-positive`, `nex890-401`, `nex890-403`, and `nex890-404`. Finish and
self-check each authoring root before capture. Put each workflow root directly
under the workspace, named with its workflow, so their common parent is the
workspace root. For each cycle, complete consent and capture, then invoke
exactly one independent synchronous child for review. Only that child may call
`mcp__nxd-desktop__read_review_input`, after successful capture and before
returning its review; the owning thread must never call it. Do not read review
input or invoke a review child during planning or for a static case.
Build the child's prompt from the canonical review block in the loaded
`nxd-run-job-loop` workflow-v2 guidance: include the exact retained paths, the
sanitized original request, the `nxd-review-closure` instruction, the
prescribed review budget and cutoff, and one `NXD_REVIEW_DISPATCH` marker.
Append the following reader rules to the child's prompt after the canonical
workflow block; do not change the canonical block. For retained capture inputs, the
reader replaces `Read`, `Glob`, and `Grep`. First `list` the exact absolute
`retained_capture_root` from capture, then `read` the exact absolute
`retained_blueprint_path`. `list` only that root or absolute paths returned
earlier as `kind=directory`; `read` only the exact blueprint path or absolute
paths returned earlier as `kind=file`. Build each returned child path by
joining its name to the absolute directory that returned it. In the root
listing, skip any entry whose name equals the basename of
`retained_blueprint_path`; read the blueprint only via its exact retained path.
Never guess paths from the skill's expected-file list or read mutable authoring
paths. Credential-shaped files omitted by runner policy are expected to be
absent and are not findings. Use only the required `path` and `operation`
arguments, make one reader call at a time, and wait for its response before
making the next. Every reader call must succeed, and at least one successful
reader call is required. The reader appends the explicit
`[runner output truncated]` marker whenever it omits lines, entries, or bytes;
treat any response carrying that marker as partial evidence and do not retry
with optional bounds. For any partial reader response, the child returns
`indeterminate` with explicitly partial claims, and the owner reports
`indeterminate`, leaves that workflow incomplete, and does not validate.
The child must not call any other MCP tool or spawn another Agent/Task. If a
reader call fails, it must return an incomplete review so the owner leaves the
cycle incomplete without reporting it.
Always pass `run_in_background: false` explicitly when invoking the child;
never omit it or start the child in the background. Wait for its successful final tool result
before reporting the review exactly once. If the child errors, times out,
returns unsuccessfully, or is still running, do not call `report_requirement`;
leave that cycle incomplete and do not replace the child.
After a clear review, read the fresh supervisor response and use its current
`expected_revision` and returned `start_requirement` action for the `validation`
requirement in exactly one `advance_workflow` call. Pass the action unchanged
with the matching workflow name and a fresh request ID; do not reconstruct or
retry it. If the review returns findings, the action is absent, or validation
returns an error, leave that cycle incomplete. Do not launch a second reviewer
or recapture that workflow. The positive cycle must also
publish, inspect the authoritative run, resume and query the published product
with a `status = paid` filter, and export it below the workspace. Query the
published `orders` model with one generic row-count measure, no grouping, and
one filter whose exact dimension is `status`, operator is `=`, and value is
`paid`. Expose the source `status` field with that exact semantic dimension
name and describe it as order status. The result is one scalar equal to the
reconciled paid-resource envelope total (16 for this fixture); `paid` is a
filter value, not a dimension or a metric name. The validation
request runs the pinned transform in a scratch kernel, and `start_run` executes
that transform for publication; keep the transform's unfiltered and
`status=paid` source pagination requests inside those two exact
request-to-response intervals. The later semantic query reads the published
local product: keep its `status = paid` filter and result bound to that MCP
call, separately from source HTTP evidence. Do not issue 4xx retries.

The three negative cycles must differ from the positive profile as follows:
`nex890-401` omits `auth_type`; `nex890-403` changes the public
`header_user_agent`; and `nex890-404` changes the public endpoint. Keep the
transform byte-identical across all four cycles. A 4xx retry violates the
contract. Positive pagination may produce multiple 200 observations.

Before the first workflow capture, create `.eval-cases` in the workspace and
put three static case roots under it at `.eval-cases/malformed-endpoint-profile`,
`.eval-cases/omitted-endpoint-profile`, and `.eval-cases/hard-coded-endpoint`.
Keep all three inside the workspace root that contains the four workflow roots.
Copy the positive profile into the first two cases: set
`endpoint_orders` to a complete URL in the malformed case, and omit only
`endpoint_orders` in the omitted case. Run exactly one `check_data_product`
preflight on each of those roots before any capture. For the hard-coded case,
put the endpoint literal in the DLT transform and run exactly one
`check_data_product` preflight before any capture; the runner must reject it by
AST inspection. This case does not need a workflow, review, or `failure.json`.
Keep credential values out of narration, generated source, profiles, tool
arguments, diagnostics, and exports. Do not invent a stop/cancel MCP method;
the runner owns process and temporary-state cleanup.

## Success checks

The checker verifies four separate workflow/root cycles, each required consent,
capture, child-review, and validation sequence, their distinct MCP requests,
the public-profile variants, status-specific wire observations, transform
identity, DLT pagination and filtering, publication, export redaction, and
cleanup. A static or hand-written HTTP loop is not an acceptable substitute for
DLT ingestion.
