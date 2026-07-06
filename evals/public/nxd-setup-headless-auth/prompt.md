# Scenario: nxd Setup — Headless Auth in a Sandboxed Shell

The eval runner provides artifacts from a stalled CLI-authentication session
inside a sandboxed agent VM. A first `nxd login` attempt was made and the user
already approved the device link in their own browser, yet `whoami` still
reports not-logged-in. The root cause is the sandbox process model: each shell
call is an independent process tree, so the backgrounded login poller was dead
before the approval happened and the approval was wasted. The correct recovery
is a manual OAuth device flow driven with `curl` (device code persisted to a
file, the server-issued `pkce_verifier` echoed back as `code_verifier`), then
hand-writing `tokens.json` into the config file's directory and minting a real
PAT. This scenario regression-tests the `nxd-setup` skill's
sandboxed/non-persistent-shell branch.

Task for the agent:

You are helping a user authenticate the `nxd` CLI against their company mesh
from inside a sandboxed agent environment. Read `session-constraints.md` for
the properties of the execution environment, then the `nxd-*.txt` files for
what has already happened this session. Current state: the CLI is installed
and on PATH; the session config is `/tmp/nxd-acme.yaml` (no token in it yet);
a login attempt was already made and the user says they approved the link, but
`whoami` still fails. The user is standing by in chat and can open links in
their own browser.

Produce, as your final answer:

1. A diagnosis of why the first login attempt left the CLI unauthenticated
   even though the user approved the link.
2. The exact, ordered sequence of shell commands and file writes you would run
   in this environment to reach a fully authenticated, persistent state —
   ending with a verified identity and a stored personal access token —
   clearly marking the point(s) where the user must act and any time
   limits they must respect.

Do not actually contact any network host — the hosts in the artifacts are not
reachable from here, and `nxd` is not installed in this grading workspace.
Write the plan concretely enough that each step could be pasted into the
sandbox shell as-is (placeholders only for values that come from earlier
command output).

Required artifacts from eval runner:

- `session-constraints.md` — sandbox environment properties
- `nxd-login-attempt.txt` — transcript of the failed first login attempt
- `nxd-login-help.txt` — pre-captured `nxd login --help` output
- `nxd-login-debug.txt` — pre-captured `nxd login --debug --open-browser false`
  output revealing the mesh's OAuth wiring

Success checks:

- Diagnoses the dead background poller (per-call process tree) as the failure
  cause, not a wrong URL/token.
- Does not retry interactive or backgrounded `nxd login`; switches to a manual
  curl device flow.
- Uses the auth host (a third host, distinct from app/api) from the debug
  output for the device-code and token requests.
- Persists the device-code response to a file and sends the server-issued
  `pkce_verifier` back as `code_verifier` in the token exchange.
- Tells the user to approve promptly (~300 s TTL) and re-requests a fresh code
  on expiry.
- Writes `tokens.json` into the config file's directory (`/tmp/tokens.json`)
  in the correct keyed-by-auth-url format with an RFC3339 expiry.
- Does not pass the OAuth access token as a PAT; mints an `nxdpat_...` PAT
  after `whoami` succeeds and switches the config to it.
- Verifies with `whoami` output (not exit code alone) and surfaces the
  reported identity email to the user.
