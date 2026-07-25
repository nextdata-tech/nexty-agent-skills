---
name: nxd-setup
description: Install, configure, and authenticate the nxd CLI. Manages mesh environments so the user can work with multiple nextdata platforms across sessions. Use when setting up nxd, selecting a mesh, refreshing authentication, or producing the session config path used by other Nextdata skills.
allowed-tools:
  - Bash
  - Read
metadata:
  author: nextdata
  version: 0.22.0
---

# nxd Setup

Ensure the user's environment is ready to work with the nextdata platform. This skill manages mesh environments — named platform instances (e.g. dev, staging, prod) — so the user can register, select, and switch between them across sessions.

Mesh configurations are persisted in the user's nxd home (`~/.nxd/meshes.json` on POSIX/WSL, `$env:USERPROFILE\.nxd\meshes.json` on Windows PowerShell). Each mesh stores an **app URL**, an **API URL**, an authentication token, and an install URL. At session start, a temporary config file is generated from the registry so the CLI can target the correct platform.

> **`meshes.json` is a registry this skill maintains — the nxd CLI does not write it.** The CLI's own live state is `~/.nxd/config.yaml` (the single active mesh: `url`, `skipversioncheck`) plus `tokens.json` (bearer tokens keyed by auth host) — which lives **in the directory of the active config file**, not always `~/.nxd/`: with the default `~/.nxd/config.yaml` it is `~/.nxd/tokens.json`, but with a session config at `/tmp/nxd-<mesh_name>.yaml` it is `/tmp/tokens.json`. This skill layers `meshes.json` on top to track *multiple* named meshes and their `app_url`/`api_url` so the agent can switch between them. Treat `config.yaml` as the source of truth for what the CLI is currently pointed at, and `meshes.json` as this skill's multi-mesh address book; if it is absent, fall back to discovering meshes from `config.yaml` (Step 0 below already does this).

The host shape varies per mesh: a `trynxd.com` cloud mesh follows the `app.<sub>.trynxd.com` / `api.<sub>.trynxd.com` convention, but self-hosted or custom-domain meshes (e.g. an apex domain) may not. **Do not assume the convention** — elicit or confirm hosts with the user when they don't match (see Step 3).

This skill owns mesh selection. Its outputs are consumed by every other nxd skill:

- the active mesh's session config at `<session_config>`, resolved per OS below, and
- the mesh's `app_url`, which is the **doc base**: per-mesh docs are served at `<app_url>/docs/#/<path>` (see "Platform docs" below). Capturing `app_url` is what lets any skill build doc links for the selected mesh.

Run each step in order. Do not proceed past a failing step.

## Cross-platform command conventions

Before running commands, identify the user's shell:

| Shell | Registry path | `<session_config>` path | Install command |
|---|---|---|---|
| macOS/Linux Bash/Zsh | `~/.nxd/meshes.json` | `/tmp/nxd-<mesh_name>.yaml` | `curl -fsSL <install_url> \| bash` |
| WSL Bash/Zsh | `~/.nxd/meshes.json` inside WSL | `/tmp/nxd-<mesh_name>.yaml` inside WSL | `curl -fsSL <install_url> \| bash` |
| Windows PowerShell | `$env:USERPROFILE\.nxd\meshes.json` | `$env:TEMP\nxd-<mesh_name>.yaml` | `iwr <install_url> \| iex` |

All downstream nxd skills use `<session_config>` instead of hardcoding `/tmp`. When showing a command to a Windows PowerShell user, translate POSIX path examples to the PowerShell form above. If a customer VDI blocks native installers or shell execution, route them to WSL and clearly say the paths/config live inside WSL.

---

## Platform docs

Docs are served **per-mesh** from the active mesh's `app_url`. There is no global docs URL — resolve the host from the selected mesh (`app_url` in `~/.nxd/meshes.json`), do not hardcode it. The docs site uses docsify hash routing, so a page is:

```
<app_url>/docs/#/<path>
```

Append the path **without** a `.md` extension. The paths most relevant to setup:

| Topic | Path (append to `<app_url>/docs/#/`) |
|---|---|
| CLI setup (install / env / auth) | `tutorials/cli/setup` |
| Quick start | `tutorials/guides/quick-start` |
| Create a Data Product | `tutorials/cli/create` |
| Consuming other DPs | `tutorials/guides/consumer-tutorial` |

Hand these out inline at the relevant step rather than waiting to be asked. If a deep link 404s, open the docs home (`<app_url>/docs/#/`) and navigate the sidebar, or re-confirm `app_url` from the mesh config.

---

## Step 1: Check for the nxd CLI

Check if `nxd` is installed:

```bash
nxd --version
```

If found, proceed to Step 2.

If not found, you need a mesh URL to install the CLI. Skip ahead to Step 2 to discover or register a mesh (which gives you an install URL), then come back here to install:

```bash
curl -fsSL <install_url> | bash
```

```powershell
iwr <install_url> | iex
```

Where `<install_url>` is the mesh's install URL — the real value comes from the registered mesh (Step 3 derives it). *(Example form only, not a default: `https://app.<mesh>.example.com/cli/install`.)*

On POSIX/WSL the installer places `nxd` in `~/.local/bin`, which is often **not** on PATH — export it proactively rather than debugging a "command not found" afterwards:

```bash
export PATH="$HOME/.local/bin:$PATH"   # and append the same line to the shell rc for persistence
```

Verify the install succeeded by re-running `nxd --version`.

For install/troubleshooting guidance, once `app_url` is known you can point the user at the per-mesh CLI setup docs at `<app_url>/docs/#/tutorials/cli/setup` (see "Platform docs" below).

---

## Step 2: Discover Meshes

Read the mesh registry first:

```bash
cat ~/.nxd/meshes.json 2>/dev/null || echo '{}'
```

```powershell
if (Test-Path "$env:USERPROFILE\.nxd\meshes.json") { Get-Content "$env:USERPROFILE\.nxd\meshes.json" } else { "{}" }
```

If it lists meshes, branch on the count below. If it's missing or empty (`{}`), fall back to the **nxd CLI config** before declaring no meshes:

```bash
cat ~/.nxd/config.yaml 2>/dev/null
```

```powershell
if (Test-Path "$env:USERPROFILE\.nxd\config.yaml") { Get-Content "$env:USERPROFILE\.nxd\config.yaml" }
```

`config.yaml` is the file the `nxd` binary itself reads. Two places carry mesh URLs:

- A top-level `url:` — the currently-active URL the CLI uses (commented-out alternatives often sit above it).
- A `meshes:` mapping — named URLs the user has worked with. *(Example shape only — hosts vary per mesh; do not treat these as defaults.)*

  ```yaml
  meshes:
    <mesh-a>:
      url: https://api.<mesh-a>.example.com
    <mesh-b>:
      url: https://<mesh-b>.example.org
  ```

When `meshes.json` is empty, treat the union of these (top-level `url:` named after its subdomain, plus every entry under `meshes:`) as discovered meshes for the count branches below. Tell the user where they came from:

> No `~/.nxd/meshes.json` registry yet, but I found these mesh URLs in `~/.nxd/config.yaml`: …

If `config.yaml` is also missing or has neither field set, tell the user:

> No meshes are registered yet. Let's set one up.

Go to **Step 3** to register a new mesh.

### One mesh registered

Present it for confirmation, substituting the real mesh name and API URL from the registry/config:

> I found one registered mesh: **`<mesh_name>`** (`<api_url>`). Should we use this one, or would you like to register a different mesh?

If confirmed, set it as the active mesh and proceed to **Step 4**.
If they want a different one, go to **Step 3**.

### Multiple meshes registered

Present the list and let the user pick, using the real names and URLs from the registry/config:

> Available meshes:
> 1. `<mesh_name_1>` — `<api_url_1>`
> 2. `<mesh_name_2>` — `<api_url_2>`
>
> Which mesh would you like to use? Or type "new" to register a new one.

If the user picks one, set it as the active mesh and proceed to **Step 4**.
If "new", go to **Step 3**.

---

## Step 3: Register a New Mesh

Ask the user for their mesh URL (the app URL or API URL they use to reach the platform).

First, determine the **mesh kind**, because it decides whether you may derive hosts or must ask:

- **Cloud (`trynxd.com`) mesh** — hosts follow the `app.<sub>.trynxd.com` / `api.<sub>.trynxd.com` convention, differing only by the `app`/`api` prefix. Here you may derive the other host by swapping the prefix.
- **Self-hosted / custom-domain mesh** — the app and API hosts may NOT differ by just an `app`/`api` prefix (e.g. an apex domain, or a single combined host). **Do not derive — ELICIT.**

If the host doesn't clearly match the `app./api.<sub>.trynxd.com` pattern, treat it as custom-domain and ask the user directly for the missing host(s). Otherwise, derive per the table below and **confirm the derived host with the user before saving** — do not silently transform.

You need three values: `app_url`, `api_url`, and `install_url`. Derive (cloud) or elicit (custom) as follows. The example uses `<mesh>` / `example.com` placeholders — substitute the real host:

| User provides | app_url | api_url | install_url |
|---|---|---|---|
| Install URL: `https://app.<mesh>.example.com/cli/install` | Drop `/cli/install` → `https://app.<mesh>.example.com` | Swap `app.`→`api.`, drop `/cli/install` | As given |
| App URL: `https://app.<mesh>.example.com` | As given | Swap `app.`→`api.` | Append `/cli/install` to app_url |
| API URL: `https://api.<mesh>.example.com` | Swap `api.`→`app.` | As given | app_url + `/cli/install` |

For a custom-domain mesh where the swap doesn't apply, ask the user for the app host and the API host explicitly (and the install URL if it isn't `<app_url>/cli/install`).

**Capture `app_url`** — it is stored in the registry and is the per-mesh doc base (`<app_url>/docs/#/<path>`). Do not discard it.

Next, suggest a mesh name. For a cloud mesh, the subdomain is a good default (the `<sub>` in `api.<sub>.trynxd.com`); for an apex/custom domain there may be no obvious subdomain, so propose the bare host or ask the user. Ask the user to confirm or customize the name.

### Discover infra-profile, domain, and services (optional but recommended)

Setup is the natural place to surface these so downstream skills don't each re-discover them. After the config exists (below) and auth succeeds (Step 4), you can derive them and offer to record a default:

```bash
nxd --config <session_config> ls infra-profiles
nxd --config <session_config> ls data-products
```

Ask the user which infra-profile and domain they work in (don't assume), and note the available services/data-products for the active mesh. If the user picks defaults, you may record `infra_profile` and `domain` alongside the mesh entry in the registry (see Registry Format).

If the nxd CLI is not installed yet (Step 1 failed), install it now:

```bash
curl -fsSL <install_url> | bash
```

```powershell
iwr <install_url> | iex
```

Verify with `nxd --version`.

Create a temporary session config (without a token — we'll authenticate next):

```bash
nxd create config --url=<api_url> --config=<session_config>
```

Proceed to **Step 4** to authenticate. The token will be saved to the registry after login.

---

## Step 4: Authenticate

### Returning mesh (has token in registry)

If the mesh already has a `token` in `~/.nxd/meshes.json`, generate a config with it:

```bash
nxd create config --url=<api_url> --personal-access-token=<token> --config=<session_config>
```

Check if the token is still valid:

```bash
nxd --config <session_config> whoami
```

If `whoami` succeeds, proceed to **Step 5**.

If it fails (expired token), fall through to the login flow below.

### New mesh or expired token

**First, pick the right login path for the execution environment:**

- **Persistent shell** (Claude Code terminal, the user's own machine): use the
  interactive login below.
- **Sandboxed / non-persistent shell** (e.g. the Claude desktop/Cowork sandbox,
  where each Bash call is an independent process tree, backgrounded processes
  are killed as soon as the call returns, and there is no browser): the
  interactive `nxd login` **cannot work** — it must stay alive polling the
  token endpoint while the user approves, and nothing survives between tool
  calls. Do not attempt it (not even with `nohup`/`&`; a dead poller silently
  wastes the user's approval). Use the manual OAuth device flow in
  [`reference/headless-device-flow.md`](reference/headless-device-flow.md)
  instead, then rejoin at "Create a PAT for persistence" below. Key facts from
  that flow worth knowing up front: the OAuth server is a **third host**
  (usually `auth.<mesh-domain>`, discoverable via
  `timeout 12 nxd --config <session_config> login --debug --open-browser false`),
  the device-code endpoint returns a non-standard `pkce_verifier` that must be
  echoed back as `code_verifier`, device codes expire fast (~300 s), and
  `tokens.json` is hand-writable in the config file's directory.

**Interactive login (persistent shells only):**

```bash
nxd --config <session_config> login
```

This opens a browser for authentication. In agent contexts where the model
cannot complete the browser flow itself, hand the exact command to the user
(Claude Code users can run it as `! nxd --config <session_config> login`) and
wait for confirmation.

Verify login succeeded:

```bash
nxd --config <session_config> whoami
```

Do not trust exit code alone; if `whoami` prints `Not logged in`, auth is not
ready even if the shell exit code is `0`.

**Identity sanity-check:** surface the `whoami` email to the user. If it is not
their own address (e.g. a shared admin account), they likely approved the login
while signed into the wrong account — flag it before minting a PAT under that
identity.

> **Never pass an OAuth access token as a PAT.** `nxd create config
> --personal-access-token=<oauth access_token>` fails with HTTP 401 — the
> field only accepts real `nxdpat_...` tokens from
> `create personal-access-token`.

### Create a PAT for persistence

Create a personal access token so future sessions don't require browser login:

```bash
nxd --config <session_config> create personal-access-token --name claude-code-$(date +%s) --expires P30D
```

```powershell
nxd --config <session_config> create personal-access-token --name "claude-code-$([DateTimeOffset]::UtcNow.ToUnixTimeSeconds())" --expires P30D
```

Extract the `nxdpat_...` token from the command output.

### Save to the registry

Read the current registry, add/update the mesh entry, and write it back:

```bash
# Read current registry
cat ~/.nxd/meshes.json 2>/dev/null || echo '{}'
```

```powershell
if (Test-Path "$env:USERPROFILE\.nxd\meshes.json") { Get-Content "$env:USERPROFILE\.nxd\meshes.json" } else { "{}" }
```

Update the JSON to include the mesh entry:

```json
{
  "<mesh_name>": {
    "app_url": "<app_url>",
    "api_url": "<api_url>",
    "token": "<nxdpat_token>",
    "install_url": "<install_url>",
    "infra_profile": "<infra_profile>",
    "domain": "<domain>"
  }
}
```

`app_url` is required (it is the per-mesh doc base). `infra_profile` and `domain` are optional — include them only if the user chose defaults in Step 3.

Ensure the `~/.nxd/` directory exists and write the updated registry:

```bash
mkdir -p ~/.nxd
```

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.nxd"
```

Write the updated JSON to `~/.nxd/meshes.json`. Use atomic write patterns — write to a temp file first, then move it into place.

---

## Step 5: Verify Connectivity

Confirm the CLI can reach the platform and list data products:

```bash
nxd --config <session_config> ls data-products
```

If this succeeds, the environment is ready. To help the user understand what to do with the listed data products, point them at `<app_url>/docs/#/tutorials/guides/consumer-tutorial` (see "Platform docs").

If it fails, help the user debug:
- Wrong URL → re-run Step 3 to re-register
- Expired token → re-run Step 4 to re-authenticate
- Network issues → check connectivity to the API URL

---

## Step 6: Done

Report the active mesh configuration, using the real values for the selected mesh:

> Environment is ready!
> - **Mesh**: `<mesh_name>`
> - **App URL**: `<app_url>`
> - **API URL**: `<api_url>`
> - **User**: `<whoami email>`

**Important**: For the rest of this session, always pass `--config <session_config>` to every `nxd` command. Use the OS-specific path from "Cross-platform command conventions." This ensures all operations target the selected mesh.

Now that `app_url` is known, surface the canonical environment-ready reference: `<app_url>/docs/#/tutorials/cli/setup`. The mesh's `app_url` is also the **doc base** other skills use to build `<app_url>/docs/#/<path>` links.

If the user came here from (or is heading to) another skill, point them onward with the relevant per-mesh doc link:

- **`nxd-data-product-builder`** (build the first DP) → `<app_url>/docs/#/tutorials/cli/create`
- **MCP wiring** (mesh into an MCP client) → `<app_url>/docs/#/tutorials/guides/07-mcp`
- **Consuming data products** → `<app_url>/docs/#/tutorials/guides/consumer-tutorial`

---

## Registry Format

The mesh registry at `~/.nxd/meshes.json` on POSIX/WSL, or `$env:USERPROFILE\.nxd\meshes.json` on Windows PowerShell, stores all registered meshes:

The hosts below are **example placeholders** — real values vary per mesh (cloud meshes use `trynxd.com`, self-hosted/custom meshes do not):

```json
{
  "<mesh_name>": {
    "app_url": "https://app.<mesh_name>.example.com",
    "api_url": "https://api.<mesh_name>.example.com",
    "token": "nxdpat_...",
    "install_url": "https://app.<mesh_name>.example.com/cli/install",
    "auth_url": "https://auth.<mesh_name>.example.com",
    "infra_profile": "<infra_profile>",
    "domain": "<domain>"
  }
}
```

- `app_url` — the app/UI host; also the per-mesh **doc base** (`<app_url>/docs/#/<path>`)
- `api_url` — the platform API endpoint
- `token` — a personal access token (PAT) for authentication (30-day expiry)
- `install_url` — the URL used to install the CLI for this mesh
- `auth_url` *(optional)* — the mesh's OAuth host (a **third host**, distinct from app/api), discovered during headless login (see `reference/headless-device-flow.md`); record it so future headless sessions skip endpoint discovery
- `infra_profile` *(optional)* — the user's default infra-profile for this mesh
- `domain` *(optional)* — the user's default domain for this mesh

---

## Troubleshooting

### Token expired
Re-run Step 4. The login flow will create a new PAT and update the registry.

### Wrong mesh selected
Re-run Step 2 to pick a different mesh or register a new one.

### CLI not found after install
On POSIX/WSL, check that `~/.local/bin` is in your PATH (Step 1 exports it proactively). On Windows PowerShell, check that the installer-added nxd directory is on the user PATH, then restart the shell.

### Login "succeeds" but `whoami` says not logged in
In a sandboxed/non-persistent shell the backgrounded `nxd login` was killed before the user approved — nothing was polling the token endpoint, so the approval was wasted. Use the headless device flow (`reference/headless-device-flow.md`) instead of retrying.

### Device code expired
Device codes have a short TTL (~300 s). Request a fresh code (repeat the device-code POST); never retry an expired one.

### Registry corrupted
Delete `~/.nxd/meshes.json` on POSIX/WSL, or `$env:USERPROFILE\.nxd\meshes.json` on Windows PowerShell, and re-register meshes from scratch.
