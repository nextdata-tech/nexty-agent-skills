#!/usr/bin/env bash
# install.sh — first-party installer for the Nexty AI Pro skill pack.
#
# Installs Claude Code skills into ~/.claude/skills (or a project-local
# .claude/skills) and builds one uploadable Claude Desktop/Cowork plugin ZIP.
# Desktop's local-agent-session files are app-owned state; this script does not
# edit them.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC_DIR="$ROOT/src"
PLUGIN_JSON="$ROOT/.claude-plugin/plugin.json"

SUBCMD="install"
declare -a TARGETS=()
SCOPE="global"
declare -a SKILLS=()
DO_VALIDATE=1
DO_SUBMODULE=1
ASSUME_YES=0
DRY_RUN=0
VERBOSE=0

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
  --desktop  Claude Desktop  -> build one plugin ZIP for upload in Plugins
  --cowork   Claude Cowork   -> same plugin-ZIP flow as --desktop
  --all      all targets

Usage: scripts/install.sh [install|uninstall|status|help] [targets] [scope] [options]

Options:
  --uninstall            Alias for the `uninstall` subcommand
  --skills "a b c"       Restrict Claude Code to a subset of skills (Desktop/Cowork use all)
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
        # shellcheck disable=SC2206
        SKILLS=($1)
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
  [[ ${#TARGETS[@]} -eq 0 ]] && TARGETS=("code")
  dbg "assume-yes=$ASSUME_YES"

  local -A seen=()
  local -a unique=()
  for target in "${TARGETS[@]}"; do
    [[ -n "${seen[$target]:-}" ]] || { unique+=("$target"); seen[$target]=1; }
  done
  TARGETS=("${unique[@]}")
}

require_cmd() {
  for command_name in "$@"; do
    command -v "$command_name" >/dev/null 2>&1 || die "missing required command: $command_name"
  done
}

selected_skills() {
  if [[ ${#SKILLS[@]} -gt 0 ]]; then
    printf '%s\n' "${SKILLS[@]}"
  else
    for directory in "$SRC_DIR"/*/; do basename "$directory"; done
  fi
}

validate_skill_names() {
  for skill in "${SKILLS[@]}"; do
    [[ -f "$SRC_DIR/$skill/SKILL.md" ]] || die "unknown skill: $skill (see $SRC_DIR/*/)"
  done
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

install_code() {
  local destination; destination="$(cc_dest)"
  info "installing skills -> $destination ($SCOPE)"
  run "mkdir -p '$destination'"
  while IFS= read -r skill; do
    copy_skill_tree "$SRC_DIR/$skill" "$destination/$skill"
    [[ "$skill" == "nxd-run-job-loop" ]] && write_code_version_stamp "$destination/$skill"
    ok "code: $skill"
  done < <(selected_skills)
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
  done < <(selected_skills)
  [[ -d "$destination" ]] && run "rmdir '$destination' 2>/dev/null || true"
}

status_code() {
  local destination; destination="$(cc_dest)"
  echo "Claude Code ($SCOPE): $destination"
  while IFS= read -r skill; do
    if [[ -d "$destination/$skill" ]]; then
      echo "  ✓ $skill"
    else
      echo "  · $skill (not installed)"
    fi
  done < <(selected_skills)
}

plugin_version() {
  python3 -c 'import json,sys;print(json.load(open(sys.argv[1], encoding="utf-8"))["version"])' "$PLUGIN_JSON"
}

plugin_pack_path() {
  echo "$ROOT/build/nexty-agent-skills-v$(plugin_version).zip"
}

desktop_zip() {
  [[ ${#SKILLS[@]} -eq 0 ]] || die "--skills is only supported for Claude Code; Desktop/Cowork use the complete plugin pack"
  local pack; pack="$(plugin_pack_path)"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    printf '\033[35m[dry-run]\033[0m build %s\n' "$pack" >&2
    return 0
  fi
  info "building the Claude Desktop/Cowork plugin ZIP"
  (cd "$ROOT" && bash ./build-skills.sh)
  ok "plugin pack: $pack"
  cat >&2 <<EOF

Claude Desktop / Cowork — upload this one file:
  1. Open Claude Desktop → Settings → Customize → Plugins.
  2. Choose Add plugin → Upload plugin.
  3. Upload:
     $pack
  4. Confirm the pack is enabled, fully quit/reopen Claude Desktop, and start a new Cowork task.

The ZIP is also the artifact published on the matching GitHub release.
EOF
}

desktop_uninstall() {
  cat >&2 <<'EOF'
Claude Desktop / Cowork installs are managed by Claude Desktop.
Remove “Nexty AI Pro” from Settings → Customize → Plugins, then restart Claude Desktop.
EOF
}

desktop_status() {
  local pack; pack="$(plugin_pack_path)"
  echo "Claude Desktop / Cowork: managed in Claude Desktop → Settings → Customize → Plugins"
  if [[ -f "$pack" ]]; then
    echo "  ✓ local plugin pack ready: $pack"
  else
    echo "  · local plugin pack not built (run scripts/install.sh --desktop)"
  fi
}

main() {
  parse_args "$@"
  require_cmd python3
  validate_skill_names

  local has_code=0 has_desktop=0
  for target in "${TARGETS[@]}"; do
    case "$target" in
      code) has_code=1 ;;
      desktop|cowork) has_desktop=1 ;;
      *) die "unknown target: $target" ;;
    esac
  done

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
