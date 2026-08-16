# Making the desktop helper scripts reachable

## Contents

- [Resolve `JOB_HELPER_DIR` once](#resolve-job_helper_dir-once)
- [Run the helpers](#run-the-helpers)

The helper scripts ship with **nxd-run-job-loop** at `scripts/`; most must stay in
that installed helper tree. `self_check.py` is the deliberate exception: it
imports no sibling helper, has a stdlib-only bootstrap, and is copied into the
generated closure root before it is run there with the closure's runtime
dependencies. A bare `scripts/...` path is invalid after installation, so resolve
the installed directory before calling the shared helpers or copying
`self_check.py`.

## Resolve `JOB_HELPER_DIR` once

Run this stdlib-only resolver before the first helper call. It emits one absolute
directory or fails. It only discovers installed copies; it does not create or
edit Claude app state.

```bash
JOB_HELPER_DIR="$(python3 - "$HOME" "$PWD" <<'PY'
from pathlib import Path
import sys

home, cwd = map(Path, sys.argv[1:])
roots = [home / ".claude" / "skills" / "nxd-run-job-loop"]
roots += [parent / ".claude" / "skills" / "nxd-run-job-loop" for parent in (cwd, *cwd.parents)]
plugins = home / ".claude" / "plugins"
searched = list(roots)
plugin_src = plugins / "**/src/nxd-run-job-loop"
plugin_skills = plugins / "**/skills/nxd-run-job-loop"
searched += [plugin_src, plugin_skills]
roots += list(plugins.glob("**/src/nxd-run-job-loop"))
roots += list(plugins.glob("**/skills/nxd-run-job-loop"))
for mount in (home, home / "mnt"):
    local_plugins = mount / ".local-plugins"
    cached_pattern = local_plugins / "cache/nexty/nexty-agent-skills/*/skills/nxd-run-job-loop"
    searched.append(cached_pattern)
    cached = list(local_plugins.glob("cache/nexty/nexty-agent-skills/*/skills/nxd-run-job-loop"))
    def _version_key(root):
        parts = root.parents[1].name.split(".")
        if len(parts) != 3 or not all(part.isdigit() for part in parts):
            return (-1, -1, -1)
        return tuple(int(part) for part in parts)
    roots += sorted(cached, key=_version_key, reverse=True)
claude = home / "Library" / "Application Support" / "Claude" / "local-agent-mode-sessions"
cowork_pattern = claude / "*/*/cowork_plugins/cache/nexty/nexty-agent-skills/*/skills/nxd-run-job-loop"
skills_plugin_pattern = claude / "skills-plugin/*/*/*/skills/nxd-run-job-loop"
searched += [cowork_pattern, skills_plugin_pattern]
roots += list(claude.glob("*/*/cowork_plugins/cache/nexty/nexty-agent-skills/*/skills/nxd-run-job-loop"))
roots += list(claude.glob("skills-plugin/*/*/*/skills/nxd-run-job-loop"))
for root in roots:
    skill = root / "SKILL.md"
    if ((root / "scripts/dp_diagnostics.py").is_file()
            and (root / "scripts/validate_dp_spec.py").is_file()
            and (root / "scripts/dp_spec_authoring.py").is_file()
            and (root / "scripts/dp_spec_v2.py").is_file()
            and (root / "scripts/self_check.py").is_file()
            and skill.is_file()):
        print(root.resolve())
        break
else:
    attempted = "\n".join(f"  - {root}" for root in searched)
    raise SystemExit(
        "nxd-run-job-loop helpers not found; searched these roots/patterns:\n"
        f"{attempted}\n"
        "Install or upload the skill, then retry."
    )
PY
)"
test -n "$JOB_HELPER_DIR"
```

Pass this absolute value as `job_helper_dir` whenever Step 3 invokes
`nxd-generate-data-product`, including a generation-subagent handoff. The generator must
use that exact path; it must not resolve a second copy.

## Run the helpers

The helpers require PyYAML, declared in
`"$JOB_HELPER_DIR/scripts/requirements.txt"`. Run them from a Python
environment that has installed that file's requirements. For example:

```bash
python3 -m pip install -r "$JOB_HELPER_DIR/scripts/requirements.txt"
python3 "$JOB_HELPER_DIR/scripts/validate_dp_spec.py" <workflow>/dp-spec.md --json
python3 "$JOB_HELPER_DIR/scripts/dp_diagnostics.py" lock verify <closure> \
    --spec <workflow>/dp-spec.md

# The v3 parser owns user-facing authoring. v2 remains only for verifying old
# closure evidence; v1 is rejected by both paths.
python3 "$JOB_HELPER_DIR/scripts/dp_spec_authoring.py" validate <workflow>/dp-spec.md --json

# Only when inspecting an existing v2 closure artifact:
python3 "$JOB_HELPER_DIR/scripts/dp_spec_v2.py" validate <legacy-v2-spec.md>
python3 "$JOB_HELPER_DIR/scripts/dp_spec_v2.py" schema
```

Only `self_check.py` is intended to be copied out of this tree:

```bash
cp "$JOB_HELPER_DIR/scripts/self_check.py" <closure>/self_check.py
cd <closure> && python3 self_check.py --json --record build-record.json
```

Keep `dp_diagnostics.py`, `validate_dp_spec.py`, `dp_spec_authoring.py`, and
`dp_spec_v2.py` in the resolved helper tree. The shared diagnostic and validation
path imports companion modules from that directory; copying one of those files
alone does not make it runnable from an isolated closure or execution shell.

The adversarial-review dispatch is deliberately different: it receives only the
closure path and verbatim request, never `job_helper_dir`; it verifies the
generator's recorded evidence without executing helpers.
