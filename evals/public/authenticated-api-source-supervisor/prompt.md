# Scenario: publish, resume and query an authenticated REST data product

The workspace contains one brief: `BRIEF.md`. It describes a small internal
metrics service that requires a bearer token on every request — not a public,
no-auth API — and that also refuses any client whose `User-Agent` it does not
recognize.

`ENDPOINT_URL` (a file at the workspace root) names the base URL to build
against: a local stub the eval runner starts for this run, standing in for the
real service the brief describes. Treat the URL exactly as if it were the
brief's own hostname — you have no reason to know it is a stub, and nothing
about how you build the closure should depend on that fact. The service exposes
exactly the two endpoints and the one credential the brief names; there is
nothing else to discover by probing it.

## Task for the agent

Build the runnable NXD desktop data product the brief asks for, **and stand it
up as a served product**. You have only the installed Nexty skills and the
local desktop supervisor on `PATH`; work autonomously — no user is available to
confirm a ruling, which does not make the ruling optional.

The bearer token is supplied in `BRIEF.md` exactly as a user would paste it
into chat — use it as the live credential, entered into `infra-profile.yaml`,
never narrated back in chat or written into any committed source file.

Go and look at what the endpoints actually return before you design the
models, the same way you would for any connector you have not used before.
Consult the installed skills for the platform's connector, derivation and
assertion contracts rather than improvising the ingestion mechanism.

Then run the loop:

1. Generate the complete runnable closure — `spec.py`, `models.py`,
   `infra-profile.yaml`, `transform/main.py`, `requirements.txt`. Do not
   hand-write `deployment-spec.yaml`, `manifest.yaml`, or `models.yaml`; the
   supervisor compiles those, including the semantic catalog, from `spec.py` at
   serve time.
2. Run the closure's own connectivity self-check before serving. Credentials
   are available in this session, so it runs — do not report it as skipped.
3. Serve it: `nxd-desktop-supervisor serve --definition <dir> --workflow
   beacon-uptime --data-dir .desktop/state`. Require `published=yes`, then run
   `status` and `describe`. Keep the bearer out of narration and pass it only
   per command.
4. Answer the brief's question 1 — check volume by owning team — as a
   catalog-grounded governed selection against the running endpoint, and answer
   from the returned JSON. State the measures, dimensions and filters you
   selected before you query. Use a `--selection` JSON file when filters,
   ordering or a limit are required.
5. Stop the supervisor with `nxd-desktop-supervisor stop --data-dir
   .desktop/state`.
6. Recover the product the way the brief's last constraint describes: from the
   closure directory plus the `beacon-uptime` workflow id, with the endpoint
   and bearer you held now dead. Re-serve the **same** workflow from the
   **same** closure directory, take the fresh endpoint and bearer that serve
   returns, re-run `describe`, and re-answer question 1 to prove the recovered
   product still answers it. Do not re-author the closure to do this.

On this direct-CLI surface a re-serve is a rebuild from the closure, not a
reattach to a running instance — narrate it honestly as such, and note that the
rebuild re-fetches from the upstream API rather than replaying cached rows.

In your final answer, give the per-team check volumes, the selection behind
them, and state that the recovered product answered the same question without
re-authoring. Do not include bearer tokens.

## Success checks

The eval grades the full path, not the narration of it: a closure whose
ingestion goes through the platform's declared REST connector with the required
client header supplied from configuration, published through the local
supervisor, and then — independently, from the published snapshot rather than
from your working directory — resumed, described, and queried, with the answers
reconciled against what the API itself serves.
