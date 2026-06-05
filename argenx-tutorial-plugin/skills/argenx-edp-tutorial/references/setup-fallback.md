# Setup fallback & discovery

Use this when the `nxd-setup` skill isn't available, or when you need to discover environment
details the tutorial assumes. **Everything here uses only the nxd CLI and the NXD REST API** —
the tools the learner actually has. No internal repos.

## If `nxd-setup` skill is present

Prefer it. Hand off: it installs `uv` + `nxd`, registers the mesh, and authenticates. Come back
to this tutorial once `nxd ls data-products` succeeds.

## If `nxd-setup` is NOT present — minimal manual setup

On the argenx VDI, do all of this **inside WSL** (see `windows-wsl.md`).

1. **Install `uv`** (manages Python):
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```
2. **Install the `nxd` CLI** — follow the platform's own setup doc:
   `https://docs.argenx.nextopia.dev/#/tutorials/cli/setup`. The installer drops `nxd` in
   `~/.local/bin`; make sure that's on PATH.
3. **Register / select the mesh** — point the CLI at the argenx environment URL and
   authenticate (browser login). The setup doc above covers the exact command for this
   environment. Confirm with:
   ```bash
   nxd ls data-products
   ```
   If that returns (even an empty list), the environment is ready.

Do not proceed with the tutorial until `nxd ls data-products` succeeds.

## Discovering what the learner can use

### Which template to scaffold from (Step 3)

```bash
nxd ls data-product-templates
```

Pick the argenx EDP template (e.g. `salesforce-snowpipe-adls-to-snowflake`). If none is
listed, the platform team hasn't published it on this environment — flag it, don't publish it
yourself.

### Which infra profile + which services (Steps 2/4)

```bash
nxd ls infra-profiles | sed 's/\x1B\[[0-9;]*m//g'
```

The CLI has no `describe infra-profile`; read services via the REST API (PAT from the mesh
config; header is `x-nextdata-token`, not `Authorization`):

```bash
# API_URL and TOKEN come from the learner's mesh config (set during setup).
curl -s -H "x-nextdata-token: $TOKEN" \
  "$API_URL/api/v1/infraprofiles/<PROFILE_NAME>/services?domain=<DOMAIN>"
```

Returns `[{name, driver, attributes}]`. **Never display `attributes`** — they hold secrets.
Use `name` (for the `service=` in inputs/outputs) and `driver` (to know if it's Snowflake, an
API, etc.).

### Which domain the learner can launch in (Step 6 permission)

The learner needs `data-product:producer` in the target domain. To check role assignments:

```bash
nxd ls role-assignments --role data-product:producer --format json
```

Match the learner's email (`nxd whoami`) against the `scope.domain` entries. If none, they
must ask a domain admin for producer access before `nxd launch` will work.

## Locating the advanced reference DP (Step 7, "exploring" path)

The full `salesforce_snowpipe_adls_to_snowflake` reference DP lives in Nextdata's private
examples — the learner likely can't browse it. Instead, point them at its concepts **through
the platform**: the published template (`nxd describe data-product-template <name>`) and the
deployed product in the catalog UI. Keep the learner inside tools they have.
