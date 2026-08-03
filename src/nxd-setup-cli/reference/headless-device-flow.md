# Headless OAuth device flow (sandboxed / non-persistent shells)

## Contents

- [When to use this flow](#when-to-use-this-flow)
- [Why `nxd login` fails in these environments](#why-nxd-login-fails-in-these-environments)
- [Step A: Discover the OAuth endpoints](#step-a-discover-the-oauth-endpoints)
- [Step B: Request a device code](#step-b-request-a-device-code)
- [Step C: Hand the user the approval link](#step-c-hand-the-user-the-approval-link)
- [Step D: Exchange the device code for tokens](#step-d-exchange-the-device-code-for-tokens)
- [Step E: Write tokens.json](#step-e-write-tokensjson)
- [Step F: Verify, mint a PAT, and switch to it](#step-f-verify-mint-a-pat-and-switch-to-it)
- [Dead ends — do not try these](#dead-ends--do-not-try-these)

## When to use this flow

Use this instead of Step 4's interactive `nxd login` when the shell is
**non-persistent**: each Bash/tool call runs in its own process tree and any
backgrounded process is killed the moment the call returns. This is how
sandboxed agent VMs work (e.g. the Claude desktop/Cowork sandbox, which runs
each call under `bwrap --die-with-parent --unshare-pid`, caps calls at ~45 s,
and has no browser). Cheap detection, no probing needed: if you cannot keep a
process alive across two tool calls, `nxd login` cannot work — go straight to
this flow rather than burning a login attempt.

The guiding principle: **a device code is data, not a process.** Files survive
between calls; processes do not. So persist every intermediate to a file and
never rely on a background poller.

## Why `nxd login` fails in these environments

`nxd login` prints a verification URL, then **keeps running**, polling the
token endpoint until the user approves in a browser. In a non-persistent shell
the process is dead before the user ever clicks the link — `nohup ... &` does
not help — so the approval is wasted and the device code is orphaned. The
`whoami` that follows fails with "Not logged in".

## Step A: Discover the OAuth endpoints

Never hardcode auth hosts. The OAuth server usually lives on a **third host**
(commonly `auth.<mesh-domain>`) distinct from both `app_url` and `api_url`.
Discover it per-mesh with a short, bounded debug run (the `timeout` keeps the
call inside sandbox limits; the process dying afterwards is fine — you only
need its output):

```bash
timeout 12 nxd --config <session_config> login --debug --open-browser false
```

Harvest from the debug output:

- `auth_url` — the OAuth host (e.g. `https://auth.<mesh-domain>`)
- client id (typically `nxd-cli`, served at `<auth_url>/oauth2/device/clientid`)
- device authorization URL — `<auth_url>/oauth2/device/code`
- token URL — `<auth_url>/oauth2/device/token`
- scopes — typically `offline_access openid email profile`
- `config_dir` — the directory of the `--config` file (this is where
  `tokens.json` must be written in Step E)

Optionally record the discovered `auth_url` on the mesh's registry entry so
future sessions skip this step.

## Step B: Request a device code

```bash
curl -fsS -X POST <auth_url>/oauth2/device/code \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "client_id=nxd-cli&scope=offline_access%20openid%20email%20profile" \
  | tee /tmp/nxd-device.json
```

Persist the response to a file (as above) — the next call is a separate
process and needs it. The response contains `device_code`, `user_code`,
`verification_uri`, `expires_in`, and — **non-standard** — a server-issued
`pkce_verifier`. The server generates the PKCE verifier for you; you MUST send
it back as `code_verifier` in Step D or the token exchange fails.

## Step C: Hand the user the approval link

Give the user the `verification_uri` (it already carries the user code) and
ask them to approve, **promptly**: the device code TTL is short (~300 s
observed — check `expires_in`). If the user takes too long and the exchange
returns an expired-code error, request a **new** device code (repeat Step B);
never retry an expired one.

## Step D: Exchange the device code for tokens

After the user confirms approval:

```bash
curl -fsS -X POST <auth_url>/oauth2/device/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=urn:ietf:params:oauth:grant-type:device_code&device_code=<device_code>&client_id=nxd-cli&code_verifier=<pkce_verifier>"
```

A 200 returns `access_token` (a JWT), `refresh_token`, `token_type: Bearer`,
and `expires_in` (seconds).

## Step E: Write tokens.json

The CLI reads its tokens from `tokens.json` **in the directory of the active
config file** (the `config_dir` from Step A) — NOT always `~/.nxd/`. With a
session config at `/tmp/nxd-<mesh_name>.yaml` that means `/tmp/tokens.json`.
Format — a map keyed by the auth URL:

```json
{
  "<auth_url>": {
    "access_token": "<jwt>",
    "token_type": "Bearer",
    "refresh_token": "<refresh_token>",
    "expiry": "<RFC3339 timestamp>"
  }
}
```

Set `expiry` to now + `expires_in` minus a safety margin (e.g. 60 s), as an
RFC3339 string. Write atomically (temp file, then move).

## Step F: Verify, mint a PAT, and switch to it

```bash
nxd --config <session_config> whoami
```

Do not trust exit code alone — if it prints `Not logged in`, auth is not
ready. On success, **surface the reported email to the user**: if it isn't
their own address (e.g. a shared admin account), they likely approved the
device link while signed into the wrong account.

Then immediately return to the skill's normal Step 4 tail: create a PAT,
regenerate the config with `--personal-access-token=<nxdpat_...>`, and save
the registry. The steady state is identical to the browser-login path; only
the way the first bearer token was obtained differs.

## Dead ends — do not try these

- **OAuth access token as a PAT.** `nxd create config
  --personal-access-token=<oauth access_token>` yields HTTP 401 on every call.
  The `personal_access_token` config field only accepts real `nxdpat_...`
  tokens minted by `create personal-access-token`.
- **Backgrounding `nxd login` with `nohup`/`&`.** The whole per-call process
  tree is killed when the call returns; nothing will be polling when the user
  approves.
- **Retrying an expired device code.** Request a fresh one instead.
