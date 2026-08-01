# Making the Pocket helper scripts reachable

`dp_diagnostics.py` and `validate_dp_spec.py` ship with **nxd-pocket-loop** at
`scripts/`. They are not copied into a generated closure, and a closure is not
the current directory from which to address them. A bare `scripts/...` path is
therefore invalid once the skill is installed.

## Resolve `POCKET_HELPER_DIR` once

Run this exact stdlib-only resolver before the first helper call. It emits one
absolute directory or fails; it never guesses from the workflow or closure cwd.
The three paths are the supported install surfaces: Claude Code global/project,
Cowork marketplace cache, and Claude Desktop's uploaded-skill store.

```bash
POCKET_HELPER_DIR="$(python3 - "$HOME" "$PWD" <<'PY'
from pathlib import Path
import sys

home, cwd = map(Path, sys.argv[1:])
roots = [home / ".claude" / "skills" / "nxd-pocket-loop"]
roots += [parent / ".claude" / "skills" / "nxd-pocket-loop" for parent in (cwd, *cwd.parents)]
claude = home / "Library" / "Application Support" / "Claude" / "local-agent-mode-sessions"
roots += list(claude.glob("*/*/cowork_plugins/cache/nexty/nexty-agent-skills/*/skills/nxd-pocket-loop"))
roots += list(claude.glob("skills-plugin/*/*/*/skills/nxd-pocket-loop"))
for root in roots:
    skill = root / "SKILL.md"
    if (root / "scripts/dp_diagnostics.py").is_file() and (root / "scripts/validate_dp_spec.py").is_file() and skill.is_file():
        print(root.resolve())
        break
else:
    raise SystemExit("nxd-pocket-loop helpers not found; install or upload the skill")
PY
)"
test -n "$POCKET_HELPER_DIR"
```

Pass this absolute value as `pocket_helper_dir` whenever Step 3 invokes
`nxd-generate-dp`, including a generation-subagent handoff. The generator must
use that exact path; it must not resolve a second copy.

The helpers require PyYAML, declared in
`"$POCKET_HELPER_DIR/scripts/requirements.txt"`. Run them from a Python
environment that has installed that file's requirements. For example:

```bash
python3 -m pip install -r "$POCKET_HELPER_DIR/scripts/requirements.txt"
python3 "$POCKET_HELPER_DIR/scripts/validate_dp_spec.py" <workflow>/dp-spec.md --json
python3 "$POCKET_HELPER_DIR/scripts/dp_diagnostics.py" lock verify <closure> \
  --spec <workflow>/dp-spec.md
```

The adversarial-review dispatch is deliberately different: it receives only the
closure path and verbatim request, never `pocket_helper_dir`; it verifies the
generator's recorded evidence without executing helpers.
