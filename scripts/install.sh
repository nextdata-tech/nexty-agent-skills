#!/usr/bin/env bash
# install.sh — first-party installer for the Nexty AI Pro skill pack.
#
# Installs Claude Code skills into ~/.claude/skills (or a project-local
# .claude/skills) and builds an uploadable Claude Desktop/Cowork plugin ZIP.
# Desktop's local-agent-session files are app-owned state; this script does not
# edit them.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC_DIR="$ROOT/src"
PLUGIN_JSON="$ROOT/.claude-plugin/plugin.json"
DESKTOP_SUPPORT="$HOME/Library/Application Support/Claude"
PLUGIN_NAME="nexty-agent-skills"
MP_NAME="nexty"
PLUGIN_SET="all"
CODE_INSTALL_MARKER=".nexty-plugin-install.json"

SUBCMD="install"
declare -a TARGETS=()
SCOPE="global"
declare -a SKILLS=()
SKILLS_REQUESTED=0
DO_VALIDATE=1
DO_SUBMODULE=1
ASSUME_YES=0
DRY_RUN=0
VERBOSE=0
SKILL_LIST_FILE=""

cleanup_skill_list() {
  if [[ -n "${SKILL_LIST_FILE:-}" ]]; then
    rm -f "$SKILL_LIST_FILE"
  fi
}
trap cleanup_skill_list EXIT

info() { printf '\033[34m==>\033[0m %s\n' "$*" >&2; }
ok()   { printf '\033[32m✓\033[0m %s\n' "$*" >&2; }
warn() { printf '\033[33mwarn:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[31merror:\033[0m %s\n' "$*" >&2; exit 1; }
dbg()  { [[ "$VERBOSE" -eq 1 ]] && printf '    %s\n' "$*" >&2 || true; }

run() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    printf '\033[35m[dry-run]\033[0m %s\n' "$*" >&2
  else
    dbg "$*"
    eval "$*"
  fi
}

usage() {
  cat >&2 <<'EOF'
install.sh — first-party installer for the Nexty AI Pro skill pack.

Targets:
  --code     Claude Code     -> ~/.claude/skills (or ./.claude/skills with --project)
  --desktop  Claude Desktop  -> build the selected plugin ZIP for upload in Plugins
  --cowork   Claude Cowork   -> same plugin-ZIP flow as --desktop
  --all      all targets

Usage: scripts/install.sh [install|uninstall|status|help] [targets] [scope] [options]

Options:
  --uninstall            Alias for the `uninstall` subcommand
  --skills "a b c"       Restrict Claude Code to a subset of skills
  --plugin desktop|datamesh|all
                         Select the local Desktop, deployed DataMesh, or compatibility set
                         for code when --skills is absent and for Desktop/Cowork archives
  --skills and --plugin desktop|datamesh are mutually exclusive; --skills selects
                         explicit Claude Code skills, while --plugin selects a complete pack
  --no-validate          Skip scripts/validate_skills.py (not recommended)
  --no-submodule         Do not initialize the bundled examples submodule
  --zip                  Deprecated compatibility alias; ZIP is now the Desktop/Cowork path
  -y, --yes              Non-interactive compatibility flag
  --dry-run              Print actions, mutate nothing
  --verbose              Extra logging
EOF
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      install|uninstall|status|help) SUBCMD="$1" ;;
      --code)    TARGETS+=("code") ;;
      --desktop) TARGETS+=("desktop") ;;
      --cowork)  TARGETS+=("cowork") ;;
      --all)     TARGETS+=("code" "desktop" "cowork") ;;
      --project) SCOPE="project" ;;
      --global)  SCOPE="global" ;;
      --uninstall) SUBCMD="uninstall" ;;
      --skills)
        shift; [[ $# -gt 0 ]] || die "--skills needs an argument"
        SKILLS_REQUESTED=1
        # shellcheck disable=SC2206
        SKILLS=($1)
        ;;
      --plugin)
        shift; [[ $# -gt 0 ]] || die "--plugin needs an argument"
        PLUGIN_SET="$1"
        ;;
      --no-validate) DO_VALIDATE=0 ;;
      --no-submodule) DO_SUBMODULE=0 ;;
      --zip) warn "--zip is deprecated; Desktop/Cowork now always use the plugin ZIP flow" ;;
      -y|--yes) ASSUME_YES=1 ;;
      --dry-run) DRY_RUN=1 ;;
      --verbose|-v) VERBOSE=1 ;;
      -h|--help) usage; exit 0 ;;
      *) usage; die "unknown argument: $1" ;;
    esac
    shift
  done
  [[ "$SUBCMD" == "help" ]] && { usage; exit 0; }
  if [[ -z "${TARGETS[0]+set}" ]]; then
    TARGETS=("code")
  fi
  dbg "assume-yes=$ASSUME_YES"

  # Order-preserving dedupe. Uses a delimited string rather than an
  # associative array: `local -A` is bash 4+, and macOS ships bash 3.2.
  local seen=""
  local -a unique=()
  if [[ -n "${TARGETS[0]+set}" ]]; then
    for target in "${TARGETS[@]}"; do
      case "$seen" in
        *"|$target|"*) ;;
        *) unique+=("$target"); seen="$seen|$target|" ;;
      esac
    done
  fi
  if [[ -n "${unique[0]+set}" ]]; then
    TARGETS=("${unique[@]}")
  fi
}

require_cmd() {
  for command_name in "$@"; do
    command -v "$command_name" >/dev/null 2>&1 || die "missing required command: $command_name"
  done
}

selected_skills() {
  if [[ -n "${SKILLS[0]+set}" ]]; then
    printf '%s\n' "${SKILLS[@]}"
  elif [[ "$PLUGIN_SET" == "all" ]]; then
    for directory in "$SRC_DIR"/*/; do basename "$directory"; done
  else
    marketplace_skill_names "$PLUGIN_SET"
  fi
}

marketplace_skill_names() {
  local plugin_name="$1"
  python3 - "$ROOT" "$ROOT/.claude-plugin/marketplace.json" "$plugin_name" <<'PY'
import json
import sys
from pathlib import Path

root, marketplace_path, plugin_name = sys.argv[1:]
with open(marketplace_path, encoding="utf-8") as fh:
    marketplace = json.load(fh)
for plugin in marketplace.get("plugins", []):
    if plugin.get("name") == f"nexty-{plugin_name}":
        if plugin.get("source") != "./src" or plugin.get("strict") is not False:
            raise SystemExit(f"nexty-{plugin_name} is not a canonical skill-bundle entry")
        skills = plugin.get("skills")
        if not isinstance(skills, list) or not skills:
            raise SystemExit(f"nexty-{plugin_name} has no skills list")
        seen = set()
        for skill in skills:
            if not isinstance(skill, str) or not skill.startswith("./"):
                raise SystemExit(f"invalid skill path in nexty-{plugin_name}: {skill!r}")
            name = skill[2:]
            if not name or "/" in name or name in seen:
                raise SystemExit(f"duplicate or invalid skill path in nexty-{plugin_name}: {skill!r}")
            if not (Path(root) / "src" / name / "SKILL.md").is_file():
                raise SystemExit(f"nexty-{plugin_name} references missing source skill: src/{name}")
            seen.add(name)
            print(name)
        break
else:
    raise SystemExit(f"marketplace entry not found: nexty-{plugin_name}")
PY
}

prepare_selected_skills() {
  [[ -n "${SKILL_LIST_FILE:-}" ]] && return 0
  SKILL_LIST_FILE="$(mktemp "${TMPDIR:-/tmp}/nexty-agent-skills-selected.XXXXXX")" \
    || die "could not create temporary selected-skill list"
  if ! selected_skills >"$SKILL_LIST_FILE"; then
    die "failed to resolve selected skills for --plugin $PLUGIN_SET"
  fi
  [[ -s "$SKILL_LIST_FILE" ]] || die "selected skill set is empty: $PLUGIN_SET"
}

validate_plugin_set() {
  case "$PLUGIN_SET" in
    all) ;;
    desktop|datamesh)
      marketplace_skill_names "$PLUGIN_SET" >/dev/null \
        || die "invalid plugin set: $PLUGIN_SET"
      ;;
    *) die "invalid plugin set: $PLUGIN_SET (expected desktop, datamesh, or all)" ;;
  esac
}

validate_skill_names() {
  if [[ "$SKILLS_REQUESTED" -eq 1 && -z "${SKILLS[0]+set}" ]]; then
    die "--skills was given but named no skills"
  fi
  [[ ${#SKILLS[@]} -gt 0 ]] || return 0
  for skill in "${SKILLS[@]}"; do
    [[ -f "$SRC_DIR/$skill/SKILL.md" ]] || die "unknown skill: $skill (see $SRC_DIR/*/)"
  done
}

validate_target_options() {
  local has_desktop=0
  if [[ -n "${TARGETS[0]+set}" ]]; then
    for target in "${TARGETS[@]}"; do
      case "$target" in
        desktop|cowork) has_desktop=1 ;;
      esac
    done
  fi
  if [[ "$has_desktop" -eq 1 && "$SKILLS_REQUESTED" -eq 1 ]]; then
    die "--skills is only supported for Claude Code; Desktop/Cowork use the selected complete plugin set"
  fi
  if [[ "$SKILLS_REQUESTED" -eq 1 && "$PLUGIN_SET" != "all" ]]; then
    die "--skills and --plugin $PLUGIN_SET are mutually exclusive; use --skills for explicit Code skills or --plugin for a complete named set"
  fi
}

run_validation() {
  [[ "$DO_VALIDATE" -eq 1 ]] || { warn "skipping validate_skills.py (--no-validate)"; return 0; }
  info "validating skills"
  local -a args=(--root "$ROOT")
  [[ "$DO_SUBMODULE" -eq 0 ]] && args+=(--skip-submodule-check)
  python3 "$ROOT/scripts/validate_skills.py" "${args[@]}" \
    || die "skill validation failed — fix the errors above or pass --no-validate"
}

ensure_submodule() {
  [[ "$DO_SUBMODULE" -eq 1 ]] || return 0
  local probe="$SRC_DIR/nxd-build-data-product/reference/nextdata-public-examples/data_products"
  if [[ -d "$probe" ]] && [[ -n "$(ls -A "$probe" 2>/dev/null)" ]]; then
    dbg "submodule already populated"
    return 0
  fi
  info "initializing examples submodule"
  run "git -C '$ROOT' submodule update --init --recursive"
  if [[ ! -d "$probe" ]] || [[ -z "$(ls -A "$probe" 2>/dev/null)" ]]; then
    warn "nxd-build-data-product will ship without bundled examples (submodule empty)"
  fi
}

rsync_excludes() {
  printf -- '--exclude=%s ' \
    '.git' '.git/**' '.github' '.github/**' '.gitignore' '.gitmodules' \
    '__pycache__' '__pycache__/**' '*.pyc' '*.pyo' \
    '.DS_Store' 'Thumbs.db' '.pre-commit-config.yaml' '.pre-commit-hooks' \
    '.tool-versions' '.nxdignore' '*.zip' 'uv.lock'
}

copy_skill_tree() {
  local source="$1" destination="$2"
  # shellcheck disable=SC2046
  run "rsync -a --delete $(rsync_excludes) '$source/' '$destination/'"
}

cc_dest() {
  if [[ "$SCOPE" == "project" ]]; then
    echo "$PWD/.claude/skills"
  else
    echo "$HOME/.claude/skills"
  fi
}

write_code_version_stamp() {
  local destination="$1" stamp="$1/.nexty-plugin-version.json"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    printf '\033[35m[dry-run]\033[0m write %s from plugin.json\n' "$stamp" >&2
    return 0
  fi
  python3 - "$PLUGIN_JSON" "$stamp" <<'PY'
import json
import sys

src, dst = sys.argv[1:]
with open(src, encoding="utf-8") as fh:
    plugin = json.load(fh)
if plugin.get("name") != "nexty-agent-skills" or not isinstance(plugin.get("version"), str):
    raise SystemExit("plugin.json does not carry the authoritative Nexty version")
with open(dst, "w", encoding="utf-8") as fh:
    json.dump({"name": plugin["name"], "version": plugin["version"]}, fh)
    fh.write("\n")
PY
}

read_managed_code_skills() {
  local marker="$1"
  python3 - "$marker" <<'PY'
import json
import re
import sys

path = sys.argv[1]
try:
    with open(path, encoding="utf-8") as fh:
        marker = json.load(fh)
except (OSError, UnicodeError, json.JSONDecodeError) as exc:
    raise SystemExit(f"cannot read managed skill marker {path}: {exc}")

if not isinstance(marker, dict):
    raise SystemExit("managed skill marker is not a JSON object")
if marker.get("name") != "nexty-agent-skills":
    raise SystemExit(f"managed skill marker has unexpected name: {marker.get('name')!r}")
skills = marker.get("skills")
if not isinstance(skills, list) or not skills:
    raise SystemExit("managed skill marker has no skills list")
pattern = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
for field in ("skills", "projection_skills", "extra_skills"):
    values = marker.get(field)
    if values is None:
        continue
    if not isinstance(values, list):
        raise SystemExit(f"managed skill marker field {field!r} is not a list")
    seen = set()
    for skill in values:
        if not isinstance(skill, str) or not pattern.fullmatch(skill) or skill in seen:
            raise SystemExit(f"managed skill marker has an invalid skill: {skill!r}")
        seen.add(skill)
plugin_set = marker.get("plugin_set", "all")
if plugin_set not in {"all", "desktop", "datamesh", "custom"}:
    raise SystemExit(f"managed skill marker has an invalid plugin set: {plugin_set!r}")
for skill in skills:
    print(skill)
PY
}

migrate_legacy_code_skills() {
  local destination="$1" marker="$1/$CODE_INSTALL_MARKER"
  [[ -f "$marker" ]] && return 0
  # Releases before the managed marker stamped only the job-loop skill. Use
  # that sentinel to identify an installer-owned tree, while leaving arbitrary
  # user-authored directories alone.
  local legacy_stamp="$destination/nxd-run-job-loop/.nexty-plugin-version.json"
  [[ -f "$legacy_stamp" ]] || return 0
  [[ "$SKILLS_REQUESTED" -eq 0 ]] || return 0
  [[ "$PLUGIN_SET" == "desktop" || "$PLUGIN_SET" == "datamesh" ]] || return 0
  local skill_dir skill
  for skill_dir in "$SRC_DIR"/*/; do
    [[ -d "$skill_dir" ]] || continue
    skill="$(basename "$skill_dir")"
    if [[ -d "$destination/$skill" ]]; then
      run "rm -rf '$destination/$skill'"
      ok "migrated legacy managed skill: $skill"
    fi
  done
}

remove_previous_managed_code_skills() {
  local destination="$1" marker="$1/$CODE_INSTALL_MARKER" managed
  [[ -f "$marker" ]] || return 0
  if ! managed="$(python3 - "$marker" "$SKILL_LIST_FILE" <<'PY'
import json
import re
import sys

marker_path, selected_path = sys.argv[1:]
pattern = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
with open(marker_path, encoding="utf-8") as fh:
    marker = json.load(fh)
if not isinstance(marker, dict) or marker.get("name") != "nexty-agent-skills":
    raise SystemExit("invalid managed skill marker")

def checked(field, required=False):
    values = marker.get(field)
    if values is None and not required:
        return []
    if not isinstance(values, list) or (required and not values):
        raise SystemExit(f"invalid managed skill marker field: {field}")
    if any(not isinstance(value, str) or not pattern.fullmatch(value) for value in values):
        raise SystemExit(f"invalid managed skill marker field: {field}")
    if len(values) != len(set(values)):
        raise SystemExit(f"duplicate managed skill marker field: {field}")
    return values

managed = checked("skills", required=True)
with open(selected_path, encoding="utf-8") as fh:
    selected = [line.strip() for line in fh if line.strip()]
if any(not pattern.fullmatch(skill) for skill in selected):
    raise SystemExit("invalid selected skill")

if "projection_skills" in marker or "extra_skills" in marker:
    extras = checked("extra_skills")
else:
    extras = managed if marker.get("plugin_set", "all") == "custom" else []
desired = set(selected) | set(extras)
for skill in managed:
    if skill not in desired:
        print(skill)
PY
)"; then
    die "refusing to replace skills: managed marker is invalid: $marker"
  fi
  while IFS= read -r skill; do
    [[ -n "$skill" ]] || continue
    if [[ -d "$destination/$skill" ]]; then
      run "rm -rf '$destination/$skill'"
      ok "removed managed skill: $skill"
    fi
  done <<<"$managed"
}

write_code_install_marker() {
  local destination="$1" marker="$destination/$CODE_INSTALL_MARKER"
  [[ "$DRY_RUN" -eq 1 ]] && {
    printf '\033[35m[dry-run]\033[0m write %s for %s\n' "$marker" "$PLUGIN_SET" >&2
    return 0
  }
  python3 - "$PLUGIN_JSON" "$SKILL_LIST_FILE" "$marker" "$PLUGIN_SET" "$SKILLS_REQUESTED" <<'PY'
import json
import os
import sys

plugin_path, skill_list_path, marker_path, plugin_set, requested = sys.argv[1:]
with open(plugin_path, encoding="utf-8") as fh:
    plugin = json.load(fh)
with open(skill_list_path, encoding="utf-8") as fh:
    selected = [line.strip() for line in fh if line.strip()]

previous = {}
if os.path.isfile(marker_path):
    with open(marker_path, encoding="utf-8") as fh:
        previous = json.load(fh)

previous_skills = previous.get("skills", [])
if "projection_skills" in previous or "extra_skills" in previous:
    projection = list(previous.get("projection_skills", []))
    extras = list(previous.get("extra_skills", []))
elif previous.get("plugin_set", "all") == "custom":
    projection = []
    extras = list(previous_skills)
else:
    projection = list(previous_skills)
    extras = []

if requested == "1":
    for skill in selected:
        if skill not in projection and skill not in extras:
            extras.append(skill)
else:
    projection = selected

skills = []
for skill in projection + extras:
    if skill not in skills:
        skills.append(skill)

with open(marker_path, "w", encoding="utf-8") as fh:
    json.dump(
        {
            "name": "nexty-agent-skills",
            "version": plugin.get("version"),
            "plugin_set": "custom" if requested == "1" else plugin_set,
            "skills": skills,
            "projection_skills": projection,
            "extra_skills": extras,
        },
        fh,
        indent=2,
    )
    fh.write("\n")
PY
}

use_managed_code_marker_if_present() {
  local destination="$1" marker="$1/$CODE_INSTALL_MARKER"
  [[ -f "$marker" ]] || return 0
  [[ -n "${SKILL_LIST_FILE:-}" ]] || die "internal error: no skill list file for managed marker"
  if ! read_managed_code_skills "$marker" >"$SKILL_LIST_FILE"; then
    die "refusing to act on skills: managed marker is invalid: $marker"
  fi
}

update_code_install_marker_after_explicit_uninstall() {
  local destination="$1" marker="$destination/$CODE_INSTALL_MARKER"
  [[ -f "$marker" ]] || return 0
  if [[ "$DRY_RUN" -eq 1 ]]; then
    printf '\033[35m[dry-run]\033[0m update %s after explicit uninstall\n' "$marker" >&2
    return 0
  fi
  if ! read_managed_code_skills "$marker" >/dev/null; then
    die "refusing to update skills: managed marker is invalid: $marker"
  fi
  python3 - "$marker" "$SKILL_LIST_FILE" <<'PY'
import json
import os
import sys

marker_path, skill_list_path = sys.argv[1:]
with open(marker_path, encoding="utf-8") as fh:
    marker = json.load(fh)
with open(skill_list_path, encoding="utf-8") as fh:
    removed = {line.strip() for line in fh if line.strip()}

if "projection_skills" in marker or "extra_skills" in marker:
    projection = [skill for skill in marker.get("projection_skills", []) if skill not in removed]
    extras = [skill for skill in marker.get("extra_skills", []) if skill not in removed]
elif marker.get("plugin_set", "all") == "custom":
    projection = []
    extras = [skill for skill in marker["skills"] if skill not in removed]
else:
    projection = [skill for skill in marker["skills"] if skill not in removed]
    extras = []
remaining = []
for skill in projection + extras:
    if skill not in remaining:
        remaining.append(skill)
if remaining:
    marker["skills"] = remaining
    marker["projection_skills"] = projection
    marker["extra_skills"] = extras
    marker["plugin_set"] = "custom"
    with open(marker_path, "w", encoding="utf-8") as fh:
        json.dump(marker, fh, indent=2)
        fh.write("\n")
else:
    os.unlink(marker_path)
PY
}

install_code() {
  local destination; destination="$(cc_dest)"
  info "installing skills -> $destination ($SCOPE)"
  run "mkdir -p '$destination'"
  if [[ "$SKILLS_REQUESTED" -eq 1 && -f "$destination/$CODE_INSTALL_MARKER" ]]; then
    if ! read_managed_code_skills "$destination/$CODE_INSTALL_MARKER" >/dev/null; then
      die "refusing to extend skills: managed marker is invalid: $destination/$CODE_INSTALL_MARKER"
    fi
  fi
  if [[ "$SKILLS_REQUESTED" -eq 0 ]]; then
    migrate_legacy_code_skills "$destination"
    remove_previous_managed_code_skills "$destination"
  fi
  while IFS= read -r skill; do
    copy_skill_tree "$SRC_DIR/$skill" "$destination/$skill"
    [[ "$skill" == "nxd-run-job-loop" ]] && write_code_version_stamp "$destination/$skill"
    ok "code: $skill"
  done < "$SKILL_LIST_FILE"
  write_code_install_marker "$destination"
  info "Claude Code: skills installed. Restart Claude Code or start it in a project to use them."
}

uninstall_code() {
  local destination; destination="$(cc_dest)"
  info "removing skills from $destination"
  while IFS= read -r skill; do
    if [[ -d "$destination/$skill" ]]; then
      run "rm -rf '$destination/$skill'"
      ok "removed: $skill"
    fi
  done < "$SKILL_LIST_FILE"
  if [[ "$SKILLS_REQUESTED" -eq 1 ]]; then
    update_code_install_marker_after_explicit_uninstall "$destination"
  elif [[ -f "$destination/$CODE_INSTALL_MARKER" ]]; then
    run "rm -f '$destination/$CODE_INSTALL_MARKER'"
  fi
  [[ -d "$destination" ]] && run "rmdir '$destination' 2>/dev/null || true"
}

status_code() {
  local destination; destination="$(cc_dest)"
  if [[ "$SKILLS_REQUESTED" -eq 0 ]]; then
    use_managed_code_marker_if_present "$destination"
  fi
  echo "Claude Code ($SCOPE): $destination"
  while IFS= read -r skill; do
    if [[ -d "$destination/$skill" ]]; then
      echo "  ✓ $skill"
    else
      echo "  · $skill (not installed)"
    fi
  done < "$SKILL_LIST_FILE"
}

plugin_version() {
  python3 -c 'import json,sys;print(json.load(open(sys.argv[1], encoding="utf-8"))["version"])' "$PLUGIN_JSON"
}

plugin_pack_path() {
  local stem
  case "$PLUGIN_SET" in
    all) stem="nexty-agent-skills" ;;
    desktop) stem="nexty-desktop" ;;
    datamesh) stem="nexty-datamesh" ;;
  esac
  echo "$ROOT/build/${stem}-v$(plugin_version).zip"
}

desktop_zip() {
  [[ "$SKILLS_REQUESTED" -eq 0 ]] || die "--skills is only supported for Claude Code; Desktop/Cowork use the selected complete plugin set"
  local pack; pack="$(plugin_pack_path)"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    printf '\033[35m[dry-run]\033[0m build %s\n' "$pack" >&2
    return 0
  fi
  info "building the Claude Desktop/Cowork plugin ZIP ($PLUGIN_SET)"
  (cd "$ROOT" && bash ./build-skills.sh)
  [[ -f "$pack" ]] || die "build completed without the expected plugin pack: $pack"
  ok "plugin pack: $pack"
  cat >&2 <<EOF

Claude Desktop / Cowork — upload this one file:
  1. Open Claude Desktop → Settings → Customize → Plugins.
  2. Choose Add plugin → Upload plugin.
  3. Upload this plugin set:
     $pack
  4. Confirm it is enabled, fully quit/reopen Claude Desktop, and start a new Cowork task.

The ZIP is also the artifact published on the matching GitHub release.
EOF
}

desktop_uninstall() {
  cat >&2 <<'EOF'
Claude Desktop / Cowork installs are managed by Claude Desktop.
Remove the selected Nexty plugin (Nexty Desktop, Nexty DataMesh, or the compatibility
Nexty AI Pro bundle) from Settings → Customize → Plugins, then restart Claude Desktop.
EOF
  report_legacy_desktop_state
}

legacy_desktop_state_hits() {
  local -a support_roots=("$DESKTOP_SUPPORT")
  [[ -n "${APPDATA:-}" ]] && support_roots+=("$APPDATA/Claude")
  [[ -n "${LOCALAPPDATA:-}" ]] && support_roots+=("$LOCALAPPDATA/Claude")
  python3 - "$MP_NAME" "$PLUGIN_NAME" "nexty-desktop" "nexty-datamesh" -- "${support_roots[@]}" <<'PY'
from pathlib import Path
import json
import sys

marketplace_name = sys.argv[1]
plugin_names = sys.argv[2:5]
separator = sys.argv.index("--")
support_roots = sys.argv[separator + 1:]
plugin_keys = {f"{name}@{marketplace_name}" for name in plugin_names}
hits = set()


def emit(kind, path):
    hits.add((kind, str(path)))


def read_json(path):
    try:
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            raise ValueError("top-level JSON value is not an object")
        return data, None
    except (OSError, UnicodeError, ValueError) as exc:
        return None, exc


def safe_is_dir(path):
    try:
        return path.is_dir()
    except OSError:
        emit("legacy-format unreadable directory", path)
        return False


def safe_is_file(path):
    try:
        return path.is_file()
    except OSError:
        emit("legacy-format unreadable file", path)
        return False


def child_directories(path):
    try:
        entries = list(path.iterdir())
    except OSError:
        emit("legacy-format unreadable directory", path)
        return []
    children = []
    for child in entries:
        try:
            if child.is_dir():
                children.append(child)
        except OSError:
            emit("legacy-format unreadable directory", child)
    return sorted(children, key=str)


def report_registration(data, field, key, path, kind):
    container = data.get(field, {})
    if not isinstance(container, dict):
        emit(f"legacy-format unreadable {path.name}", path)
        return
    if key in container:
        emit(kind, path)


for support_root in support_roots:
    root = Path(support_root) / "local-agent-mode-sessions"
    if not safe_is_dir(root):
        continue
    # A session pair is app-owned state. Enumerate every pair rather than
    # guessing the account/device selected by an old installer.
    for account in child_directories(root):
        for pair in child_directories(account):
            cowork_plugins = pair / "cowork_plugins"
            settings = pair / "cowork_settings.json"
            if safe_is_file(settings):
                data, error = read_json(settings)
                if error is not None:
                    emit("legacy-format unreadable cowork_settings.json", settings)
                else:
                    for plugin_key in plugin_keys:
                        report_registration(
                            data,
                            "enabledPlugins",
                            plugin_key,
                            settings,
                            "legacy-format enabledPlugins registration",
                        )
            if not safe_is_dir(cowork_plugins):
                continue

            installed = cowork_plugins / "installed_plugins.json"
            if safe_is_file(installed):
                data, error = read_json(installed)
                if error is not None:
                    emit("legacy-format unreadable installed_plugins.json", installed)
                else:
                    for plugin_key in plugin_keys:
                        report_registration(
                            data,
                            "plugins",
                            plugin_key,
                            installed,
                            "legacy-format installed_plugins registration",
                        )

            known = cowork_plugins / "known_marketplaces.json"
            if safe_is_file(known):
                data, error = read_json(known)
                if error is not None:
                    emit("legacy-format unreadable known_marketplaces.json", known)
                elif marketplace_name in data:
                    emit("legacy-format known_marketplaces registration", known)

            for plugin_name in plugin_names:
                cache = cowork_plugins / "cache" / marketplace_name / plugin_name
                if safe_is_dir(cache):
                    versions = child_directories(cache)
                    if versions:
                        for version in versions:
                            emit("legacy-format cache artifact", version)
                    else:
                        emit("legacy-format cache artifact", cache)

            marketplace = cowork_plugins / "marketplaces" / marketplace_name
            if safe_is_dir(marketplace):
                emit("legacy-format marketplace artifact", marketplace)

for kind, path in sorted(hits):
    print(f"{kind}: {path}")
PY
}

report_legacy_desktop_state() {
  local hits; hits="$(legacy_desktop_state_hits)"
  [[ -n "$hits" ]] || return 0
  echo "Legacy-format Claude app-state evidence detected (read-only; left untouched):" >&2
  while IFS= read -r hit; do
    echo "  $hit" >&2
  done <<<"$hits"
  echo "  Claude Desktop/Cowork owns this state; this command does not edit or delete it." >&2
}

desktop_status() {
  local pack; pack="$(plugin_pack_path)"
  echo "Claude Desktop / Cowork: managed in Claude Desktop → Settings → Customize → Plugins"
  if [[ -f "$pack" ]]; then
    echo "  ✓ local plugin pack ready: $pack"
  else
    echo "  · local plugin pack not built (run scripts/install.sh --desktop)"
  fi
  report_legacy_desktop_state
}

main() {
  parse_args "$@"
  require_cmd python3
  validate_plugin_set

  local has_code=0 has_desktop=0
  if [[ -n "${TARGETS[0]+set}" ]]; then
    for target in "${TARGETS[@]}"; do
      case "$target" in
        code) has_code=1 ;;
        desktop|cowork) has_desktop=1 ;;
        *) die "unknown target: $target" ;;
      esac
    done
  fi
  validate_target_options
  validate_skill_names
  if [[ "$has_code" -eq 1 ]]; then
    prepare_selected_skills
    if [[ "$SUBCMD" != "install" && "$SKILLS_REQUESTED" -eq 0 ]]; then
      use_managed_code_marker_if_present "$(cc_dest)"
    fi
  fi

  case "$SUBCMD" in
    install)
      require_cmd rsync git zip unzip
      # Validation requires the examples submodule when it is enabled, so
      # initialize it before validating rather than after a failed validation.
      if [[ "$has_code" -eq 1 || "$has_desktop" -eq 1 ]]; then
        ensure_submodule
      fi
      run_validation
      if [[ "$has_code" -eq 1 ]]; then
        install_code
      fi
      if [[ "$has_desktop" -eq 1 ]]; then
        desktop_zip
      fi
      ;;
    uninstall)
      if [[ "$has_code" -eq 1 ]]; then
        uninstall_code
      fi
      if [[ "$has_desktop" -eq 1 ]]; then
        desktop_uninstall
      fi
      ;;
    status)
      if [[ "$has_code" -eq 1 ]]; then
        status_code
      fi
      if [[ "$has_desktop" -eq 1 ]]; then
        desktop_status
      fi
      ;;
    *) usage; exit 2 ;;
  esac
}

main "$@"
