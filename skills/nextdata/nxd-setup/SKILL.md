---
name: nxd-setup
description: Install, configure, and authenticate the nxd CLI. Verifies the user can connect to the nextdata platform and list data products.
metadata:
  author: nextdata
  version: 0.1.0
---

# nxd Setup

Ensure the user's environment is ready to work with the nextdata platform. Run each check in order and guide the user through any missing steps. Do not proceed past a failing step.

## Step 1: Install the nxd CLI

Check if `nxd` is installed:

```bash
nxd --version
```

If not found, instruct the user to install it:

```bash
pip install nxd.cli
```

Then verify the install succeeded by re-running `nxd --version`.

## Step 2: Configure the CLI

Check if the CLI is configured:

```bash
nxd config show
```

If not configured, walk the user through setup:

```bash
nxd config set --platform-url <their-platform-url>
```

Ask the user for their platform URL if you don't already know it.

## Step 3: Authenticate

Check if the user is logged in:

```bash
nxd auth status
```

If not authenticated, have them log in:

```bash
nxd login
```

This will open a browser for authentication. Wait for the user to confirm they've completed the login flow.

## Step 4: Verify connectivity

Confirm the CLI can reach the platform and list existing data products:

```bash
nxd ls data-products
```

If this command succeeds, the environment is ready. If it fails, help the user debug:
- Wrong platform URL → re-run `nxd config set`
- Expired token → re-run `nxd login`
- Network issues → check connectivity to the platform URL

## Done

Once all four steps pass, tell the user their environment is ready. If they came here from another skill (e.g. `nexty-bootstrap`), let them know they can proceed.
