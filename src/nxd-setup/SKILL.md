---
name: nxd-setup
description: Install, configure, and authenticate the nxd CLI. Manages mesh environments so the user can work with multiple nextdata platforms across sessions.
allowed-tools:
  - Bash
  - Read
metadata:
  author: nextdata
  version: 0.2.0
---

# nxd Setup

Ensure the user's environment is ready to work with the nextdata platform. This skill manages mesh environments — named platform instances (e.g. dev, staging, prod) — so the user can register, select, and switch between them across sessions.

Mesh configurations are persisted in `~/.nxd/meshes.json`. Each mesh stores an API URL, authentication token, and install URL. At session start, a temporary config file is generated from the registry so the CLI can target the correct platform.

Run each step in order. Do not proceed past a failing step.

---

## Step 1: Check for the nxd CLI

Check if `nxd` is installed:

```bash
nxd --version
```

If found, proceed to Step 2.

If not found, you need a mesh URL to install the CLI. Skip ahead to Step 2 to discover or register a mesh (which gives you an install URL), then come back here to install:

```bash
curl -sL <install_url> | bash
```

Where `<install_url>` is the mesh's install URL (e.g. `https://app.demo.trynxd.com/cli/install`). Verify the install succeeded by re-running `nxd --version`.

---

## Step 2: Discover Meshes

Read the mesh registry first:

```bash
cat ~/.nxd/meshes.json 2>/dev/null || echo '{}'
```

If it lists meshes, branch on the count below. If it's missing or empty (`{}`), fall back to the **nxd CLI config** before declaring no meshes:

```bash
cat ~/.nxd/config.yaml 2>/dev/null
```

`config.yaml` is the file the `nxd` binary itself reads. Two places carry mesh URLs:

- A top-level `url:` — the currently-active URL the CLI uses (commented-out alternatives often sit above it).
- A `meshes:` mapping — named URLs the user has worked with, e.g.:

  ```yaml
  meshes:
    dev:
      url: https://dev.trynxd.com
    demo:
      url: https://api.demo.trynxd.com
  ```

When `meshes.json` is empty, treat the union of these (top-level `url:` named after its subdomain, plus every entry under `meshes:`) as discovered meshes for the count branches below. Tell the user where they came from:

> No `~/.nxd/meshes.json` registry yet, but I found these mesh URLs in `~/.nxd/config.yaml`: …

If `config.yaml` is also missing or has neither field set, tell the user:

> No meshes are registered yet. Let's set one up.

Go to **Step 3** to register a new mesh.

### One mesh registered

Present it for confirmation:

> I found one registered mesh: **demo** (https://api.demo.trynxd.com). Should we use this one, or would you like to register a different mesh?

If confirmed, set it as the active mesh and proceed to **Step 4**.
If they want a different one, go to **Step 3**.

### Multiple meshes registered

Present the list and let the user pick:

> Available meshes:
> 1. demo — https://api.demo.trynxd.com
> 2. staging — https://api.trynxd.com
>
> Which mesh would you like to use? Or type "new" to register a new one.

If the user picks one, set it as the active mesh and proceed to **Step 4**.
If "new", go to **Step 3**.

---

## Step 3: Register a New Mesh

Ask the user for their mesh URL. Accept any of these formats and derive the API URL and install URL:

| User provides | API URL | Install URL |
|---|---|---|
| Install URL: `https://app.demo.trynxd.com/cli/install` | Replace `app.` with `api.`, drop `/cli/install` → `https://api.demo.trynxd.com` | As given |
| App URL: `https://app.demo.trynxd.com` | Replace `app.` with `api.` → `https://api.demo.trynxd.com` | Append `/cli/install` → `https://app.demo.trynxd.com/cli/install` |
| API URL: `https://api.demo.trynxd.com` | As given | Replace `api.` with `app.`, append `/cli/install` → `https://app.demo.trynxd.com/cli/install` |

Next, suggest a mesh name from the URL subdomain (e.g. `demo` from `api.demo.trynxd.com`). Ask the user to confirm or customize the name.

If the nxd CLI is not installed yet (Step 1 failed), install it now:

```bash
curl -sL <install_url> | bash
```

Verify with `nxd --version`.

Create a temporary session config (without a token — we'll authenticate next):

```bash
nxd create config --url=<api_url> --config=/tmp/nxd-<mesh_name>.yaml
```

Proceed to **Step 4** to authenticate. The token will be saved to the registry after login.

---

## Step 4: Authenticate

### Returning mesh (has token in registry)

If the mesh already has a `token` in `~/.nxd/meshes.json`, generate a config with it:

```bash
nxd create config --url=<api_url> --personal-access-token=<token> --config=/tmp/nxd-<mesh_name>.yaml
```

Check if the token is still valid:

```bash
nxd --config /tmp/nxd-<mesh_name>.yaml whoami
```

If `whoami` succeeds, proceed to **Step 5**.

If it fails (expired token), fall through to the login flow below.

### New mesh or expired token

Run browser-based login:

```bash
nxd --config /tmp/nxd-<mesh_name>.yaml login
```

This opens a browser for authentication. Tell the user to complete the login flow in their browser, then wait for them to confirm.

Verify login succeeded:

```bash
nxd --config /tmp/nxd-<mesh_name>.yaml whoami
```

### Create a PAT for persistence

Create a personal access token so future sessions don't require browser login:

```bash
nxd --config /tmp/nxd-<mesh_name>.yaml create personal-access-token --name claude-code-$(date +%s) --expires P30D
```

Extract the `nxdpat_...` token from the command output.

### Save to the registry

Read the current registry, add/update the mesh entry, and write it back:

```bash
# Read current registry
cat ~/.nxd/meshes.json 2>/dev/null || echo '{}'
```

Update the JSON to include the mesh entry:

```json
{
  "<mesh_name>": {
    "api_url": "<api_url>",
    "token": "<nxdpat_token>",
    "install_url": "<install_url>"
  }
}
```

Ensure the `~/.nxd/` directory exists and write the updated registry:

```bash
mkdir -p ~/.nxd
```

Write the updated JSON to `~/.nxd/meshes.json`. Use atomic write patterns — write to a temp file first, then move it into place.

---

## Step 5: Verify Connectivity

Confirm the CLI can reach the platform and list data products:

```bash
nxd --config /tmp/nxd-<mesh_name>.yaml ls data-products
```

If this succeeds, the environment is ready.

If it fails, help the user debug:
- Wrong URL → re-run Step 3 to re-register
- Expired token → re-run Step 4 to re-authenticate
- Network issues → check connectivity to the API URL

---

## Step 6: Done

Report the active mesh configuration:

> Environment is ready!
> - **Mesh**: demo
> - **API URL**: https://api.demo.trynxd.com
> - **User**: user@example.com

**Important**: For the rest of this session, always pass `--config /tmp/nxd-<mesh_name>.yaml` to every `nxd` command. This ensures all operations target the selected mesh.

If the user came here from another skill (e.g. `nexty-bootstrap`), let them know they can proceed.

---

## Registry Format

The mesh registry at `~/.nxd/meshes.json` stores all registered meshes:

```json
{
  "mesh-name": {
    "api_url": "https://api.mesh-name.trynxd.com",
    "token": "nxdpat_...",
    "install_url": "https://app.mesh-name.trynxd.com/cli/install"
  }
}
```

- `api_url` — the platform API endpoint
- `token` — a personal access token (PAT) for authentication (30-day expiry)
- `install_url` — the URL used to install the CLI for this mesh

---

## Troubleshooting

### Token expired
Re-run Step 4. The login flow will create a new PAT and update the registry.

### Wrong mesh selected
Re-run Step 2 to pick a different mesh or register a new one.

### CLI not found after install
Check that `~/.local/bin` is in your PATH. The install script places the binary there by default.

### Registry corrupted
Delete `~/.nxd/meshes.json` and re-register meshes from scratch.
