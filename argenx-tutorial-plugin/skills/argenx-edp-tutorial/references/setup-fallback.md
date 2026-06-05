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
   `https://nxd.aks.argenx-dev.com/docs/#/tutorials/cli/setup`. The installer drops `nxd` in
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

## Making the EDP source available (Step 3, Path B)

If no argenx template is published (`nxd ls data-product-templates` shows none), the learner
must **copy the `edp/` library into their project from a reference data product** — the way the
team did when building the example. The agent usually doesn't have this source either, so this
is the most likely place to need a human hand-off. Work through it patiently:

1. **Ask the learner where their team keeps the reference EDP.** Likely sources, in order:
   - a **shared drive / OneDrive / SharePoint** folder the argenx team set up,
   - a **zip** of the `salesforce_snowpipe_adls_to_snowflake` example someone sent them,
   - an **internal repo** the learner has access to (if so, they clone it),
   - a **colleague's checkout** they can copy from.
2. **Copy just the `edp/` folder** into the new project so it sits next to `spec.py`:
   ```bash
   cp -r <reference-dp-location>/edp ./my-first-dp/
   ```
   On WSL, if the source is on the Windows side, reach it under `/mnt/c/...` (e.g.
   `cp -r /mnt/c/Users/<user>/Downloads/salesforce_snowpipe_adls_to_snowflake/edp ./my-first-dp/`).
3. **Verify it landed:** `ls my-first-dp/edp` should show `dp_specs.py`, `ingestion.py`,
   `outputs.py`, etc. If imports later fail (`from edp...`), the copy is in the wrong place or
   incomplete — re-copy the whole `edp/` directory.
4. **If the learner has no source at all:** they can't proceed with the EDP path. Flag it to
   whoever onboarded them (the argenx platform team) to either publish the template or share the
   reference `edp/`. Don't try to reconstruct `edp/` by hand — it's a real library, not
   boilerplate.

> The full reference DP (`salesforce_snowpipe_adls_to_snowflake`) also lives in Nextdata's
> private examples, which the learner usually can't browse directly. Where they *can* see its
> concepts is **through the platform**: a published template (`nxd describe
> data-product-template <name>`) and any deployed product in the catalog UI (e.g.
> `open-meteo-loader`). Keep the learner inside tools they have.
