# Troubleshooting

Read errors *with* the learner — map each back to the file or step that caused it. That's the
highest-teaching moment in the tutorial. Stay calm and concrete; never let an error feel like
their fault.

## `nxd` won't run at all

- **AppLocker / "this app has been blocked"** on the argenx VDI → native `nxd.exe` is blocked
  by IT policy. Switch to WSL. See `windows-wsl.md` (this is the #1 issue on argenx).
- **"`nxd` not recognized" / "command not found"** → PATH issue, not a block. Ensure
  `~/.local/bin` is on PATH or reopen the shell. See `windows-wsl.md`.
- **Mesh not configured / auth errors (401/403)** → run the `nxd-setup` skill (or
  `references/setup-fallback.md`) to register the mesh and authenticate.

## `uv sync` fails

- **Can't reach the index / 404 on packages** → the argenx registry URL in `pyproject.toml`
  may be wrong for this environment, or the mesh isn't reachable. Confirm the registry/mesh
  URL from `nxd-setup`, fix the `[[tool.uv.index]]` url, retry.
- **`uv` not found** → install per `nxd-setup` / `setup-fallback.md`. On WSL it's a one-liner.
- **Slow first run** → normal; it's downloading the Nextdata libraries once. Reassure, wait.

## `nxd ls data-product-templates` doesn't show the argenx template

The argenx EDP template is published to the mesh by the **platform team**, not the learner. If
it's absent on this environment, the learner can't scaffold from it yet — flag it to whoever
set up their environment. Do **not** walk the learner through publishing a template themselves
(it needs the reference DP and elevated steps they don't have). See `setup-fallback.md`.

## `nxd validate` errors

- **"parameter/port name mismatch"** → the `transform()` parameter names must match the spec's
  input/output names with hyphens → underscores. Open spec.py and transform.py side by side and
  line them up (`salesforce-api` ↔ `salesforce_api`). This is the most common one.
- **"unknown service" / infra-profile errors** → the `service=` in an input/output doesn't
  exist in the chosen infra profile. List services and pick a real one (see `setup-fallback.md`
  → discover services).
- **import errors from `edp...`** → the `edp/` library didn't come through with the template, or
  you're running from the wrong folder. Confirm `edp/` exists next to `spec.py` and that you're
  `cd`'d into the project. Re-scaffold from the template if needed.
- **type / schema errors in a semantic model** → a field type isn't imported or is misspelled.
  Valid types: `string()`, `int64()`, `int32()`, `float64()`, `number()`, `boolean()`,
  `date32()`, `date64()`. Check the imports block.

## `nxd launch` errors

- **Permission denied launching in a domain** → the learner needs `data-product:producer`
  access in that domain. Tell them to contact a domain admin; don't try to grant it yourself.
- **Provisioning / credential errors** → the tutorial DP shouldn't need deferred provisioning.
  If you see provisioning failures, you're likely on the *advanced* reference DP, not the
  minimal tutorial one — confirm which spec you launched.

## General approach

1. Read the full error aloud (to the learner) — don't paraphrase away the useful part.
2. Identify the file/line it points at.
3. Make the smallest fix, re-run the same command, confirm.
4. Say what the error was teaching them — turn the failure into a lesson.
