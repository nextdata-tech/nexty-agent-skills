# Making the desktop helper scripts reachable

`dp_diagnostics.py`, `validate_dp_spec.py`, and the shared
`dp_spec_v2.py` core ship with **nxd-run-job-loop** at `scripts/`. They are
not copied into a generated closure, and a closure is not the current directory
from which to address them. A bare `scripts/...` path is therefore invalid once
the skill is installed.

## Resolve `JOB_HELPER_DIR` once

Run this exact stdlib-only resolver before the first helper call. It emits one
absolute directory or fails; it never guesses from the workflow or closure cwd.
The supported install surfaces are Claude Code global/project and plugin installs,
Cowork marketplace cache, and Claude Desktop's uploaded-skill store.

```bash
JOB_HELPER_DIR="$(python3 - "$HOME" "$PWD" <<'PY'
from pathlib import Path
import sys

home, cwd = map(Path, sys.argv[1:])
roots = [home / ".claude" / "skills" / "nxd-run-job-loop"]
roots += [parent / ".claude" / "skills" / "nxd-run-job-loop" for parent in (cwd, *cwd.parents)]
plugins = home / ".claude" / "plugins"
roots += list(plugins.glob("**/src/nxd-run-job-loop"))
roots += list(plugins.glob("**/skills/nxd-run-job-loop"))
claude = home / "Library" / "Application Support" / "Claude" / "local-agent-mode-sessions"
roots += list(claude.glob("*/*/cowork_plugins/cache/nexty/nexty-agent-skills/*/skills/nxd-run-job-loop"))
roots += list(claude.glob("skills-plugin/*/*/*/skills/nxd-run-job-loop"))
for root in roots:
    skill = root / "SKILL.md"
    if ((root / "scripts/dp_diagnostics.py").is_file()
            and (root / "scripts/validate_dp_spec.py").is_file()
            and (root / "scripts/dp_spec_v2.py").is_file()
            and (root / "scripts/self_check.py").is_file()
            and skill.is_file()):
        print(root.resolve())
        break
else:
    raise SystemExit("nxd-run-job-loop helpers not found; install or upload the skill")
PY
)"
test -n "$JOB_HELPER_DIR"
```

Pass this absolute value as `job_helper_dir` whenever Step 3 invokes
`nxd-generate-data-product`, including a generation-subagent handoff. The generator must
use that exact path; it must not resolve a second copy.

The helpers require PyYAML, declared in
`"$JOB_HELPER_DIR/scripts/requirements.txt"`. Run them from a Python
environment that has installed that file's requirements. For example:

```bash
python3 -m pip install -r "$JOB_HELPER_DIR/scripts/requirements.txt"
python3 "$JOB_HELPER_DIR/scripts/validate_dp_spec.py" <workflow>/dp-spec.md --json
python3 "$JOB_HELPER_DIR/scripts/dp_diagnostics.py" lock verify <closure> \
    --spec <workflow>/dp-spec.md

# The v2 parser is the only active spec contract; the diagnostics entry point
# delegates to the same core.
python3 "$JOB_HELPER_DIR/scripts/dp_spec_v2.py" validate <workflow>/dp-spec.md
python3 "$JOB_HELPER_DIR/scripts/dp_spec_v2.py" schema
```

The adversarial-review dispatch is deliberately different: it receives only the
closure path and verbatim request, never `job_helper_dir`; it verifies the
generator's recorded evidence without executing helpers.
