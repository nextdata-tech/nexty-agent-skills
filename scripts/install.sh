#!/usr/bin/env bash
# install.sh — first-party installer for the Nexty AI Pro skill pack.
#
# Installs the skills under src/<skill>/ to one or more Claude targets:
#   --code     Claude Code        -> ~/.claude/skills (global) or ./.claude/skills (--project)
#   --desktop  Claude Desktop     -> build zips + upload steps (default), or rpm injection (--rpm-experimental)
#   --cowork   Claude Cowork      -> same local-agent-mode mechanism as --desktop
#   --all      all of the above
#
# Pure bash + python3 for JSON (jq is not assumed). Reuses scripts/validate_skills.py
# and build-skills.sh. See README "Install" and the repo CLAUDE.md authoring contract.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC_DIR="$ROOT/src"
PLUGIN_JSON="$ROOT/.claude-plugin/plugin.json"

# ---- defaults -------------------------------------------------------------
SUBCMD="install"
declare -a TARGETS=()
SCOPE="global"          # global | project
declare -a SKILLS=()    # empty => all
DO_VALIDATE=1
DO_SUBMODULE=1
RPM_EXPERIMENTAL=0
FORCE_ZIP=0
ACCOUNT_ID=""
DEVICE_ID=""
ASSUME_YES=0
DRY_RUN=0
VERBOSE=0

DESKTOP_SUPPORT="$HOME/Library/Application Support/Claude"
PLUGIN_NAME="nexty-agent-skills"

# ---- logging --------------------------------------------------------------
info() { printf '\033[34m==>\033[0m %s\n' "$*" >&2; }
ok()   { printf '\033[32m✓\033[0m %s\n' "$*" >&2; }
warn() { printf '\033[33mwarn:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[31merror:\033[0m %s\n' "$*" >&2; exit 1; }
dbg()  { [[ "$VERBOSE" -eq 1 ]] && printf '    %s\n' "$*" >&2 || true; }

run() {  # central mutation choke point; respects --dry-run
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

Installs the skills under src/<skill>/ to one or more Claude targets:
  --code     Claude Code     -> ~/.claude/skills (global) or ./.claude/skills (--project)
  --desktop  Claude Desktop  -> build zips + upload steps (default), or rpm injection (--rpm-experimental)
  --cowork   Claude Cowork   -> same local-agent-mode mechanism as --desktop
  --all      all of the above

Usage: scripts/install.sh [install|uninstall|status|help] [targets] [scope] [options]

Targets (default --code):  --code  --desktop  --cowork  --all
Scope (Code only):         (default global ~/.claude/skills)  |  --project (./.claude/skills)

Options:
  --uninstall            Alias for the `uninstall` subcommand
  --skills "a b c"       Restrict to a subset of skills (default: all)
  --no-validate          Skip scripts/validate_skills.py (not recommended)
  --no-submodule         Don't auto-init the examples submodule
  --rpm-experimental     Desktop/Cowork: filesystem-inject into the rpm registry
                         (default is build-zip + manual upload, which is supported)
  --account-id ID        Override Desktop accountId autodiscovery
  --device-id ID         Override Desktop deviceId autodiscovery
  -y, --yes              Non-interactive (assume yes)
  --dry-run              Print actions, mutate nothing
  --verbose              Extra logging
EOF
}

# ---- arg parsing ----------------------------------------------------------
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
      --skills)  shift; [[ $# -gt 0 ]] || die "--skills needs an argument"
                 # shellcheck disable=SC2206
                 SKILLS=($1) ;;
      --no-validate)     DO_VALIDATE=0 ;;
      --no-submodule)    DO_SUBMODULE=0 ;;
      --rpm-experimental) RPM_EXPERIMENTAL=1 ;;
      --zip)     FORCE_ZIP=1 ;;
      --account-id) shift; ACCOUNT_ID="${1:-}" ;;
      --device-id)  shift; DEVICE_ID="${1:-}" ;;
      -y|--yes)  ASSUME_YES=1 ;;
      --dry-run) DRY_RUN=1 ;;
      --verbose|-v) VERBOSE=1 ;;
      -h|--help) usage; exit 0 ;;
      *) usage; die "unknown argument: $1" ;;
    esac
    shift
  done
  [[ "$SUBCMD" == "help" ]] && { usage; exit 0; }
  # default target
  [[ ${#TARGETS[@]} -eq 0 ]] && TARGETS=("code")
  dbg "assume-yes=$ASSUME_YES"   # reserved for future interactive prompts
  # dedup targets
  local -A seen=(); local -a uniq=()
  for t in "${TARGETS[@]}"; do [[ -n "${seen[$t]:-}" ]] || { uniq+=("$t"); seen[$t]=1; }; done
  TARGETS=("${uniq[@]}")
}

# ---- helpers --------------------------------------------------------------
require_cmd() { for c in "$@"; do command -v "$c" >/dev/null 2>&1 || die "missing required command: $c"; done; }
now_ms() { python3 -c 'import time;print(int(time.time()*1000))'; }
now_iso() { python3 -c 'import datetime;print(datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00","Z"))'; }

# rsync exclude args mirroring build-skills.sh's junk filter
rsync_excludes() {
  printf -- '--exclude=%s ' \
    '.git' '.git/**' '.github' '.github/**' '.gitignore' '.gitmodules' \
    '__pycache__' '__pycache__/**' '*.pyc' '*.pyo' \
    '.DS_Store' 'Thumbs.db' '.pre-commit-config.yaml' '.pre-commit-hooks' \
    '.tool-versions' '.nxdignore' '*.zip' 'uv.lock'
}

selected_skills() {
  if [[ ${#SKILLS[@]} -gt 0 ]]; then
    printf '%s\n' "${SKILLS[@]}"
  else
    for d in "$SRC_DIR"/*/; do basename "$d"; done
  fi
}

# Validate --skills names in the MAIN shell (die from inside `< <(selected_skills)`
# would only exit the subshell, silently installing nothing).
validate_skill_names() {
  [[ ${#SKILLS[@]} -gt 0 ]] || return 0
  for s in "${SKILLS[@]}"; do
    [[ -f "$SRC_DIR/$s/SKILL.md" ]] || die "unknown skill: $s (see $SRC_DIR/*/)"
  done
}

# Read a frontmatter field (name|description) from a SKILL.md
skill_field() {  # skill_field <skill-md-path> <field>
  python3 - "$1" "$2" <<'PY'
import sys
path, field = sys.argv[1], sys.argv[2]
inside = False; val = None
with open(path, encoding="utf-8") as f:
    lines = f.readlines()
if not lines or lines[0].strip() != "---":
    sys.exit(0)
for ln in lines[1:]:
    if ln.strip() == "---":
        break
    if ln.startswith(field + ":"):
        val = ln.split(":", 1)[1].strip().strip('"').strip("'")
        break
print(val or "")
PY
}

# ---- prerequisites --------------------------------------------------------
run_validation() {
  [[ "$DO_VALIDATE" -eq 1 ]] || { warn "skipping validate_skills.py (--no-validate)"; return 0; }
  info "validating skills"
  local args=(--root "$ROOT")
  [[ "$DO_SUBMODULE" -eq 0 ]] && args+=(--skip-submodule-check)
  if ! python3 "$ROOT/scripts/validate_skills.py" "${args[@]}"; then
    die "skill validation failed — fix the errors above or pass --no-validate"
  fi
}

ensure_submodule() {
  [[ "$DO_SUBMODULE" -eq 1 ]] || return 0
  local probe="$SRC_DIR/nxd-data-product-builder/reference/nextdata-public-examples/data_products"
  if [[ -d "$probe" ]] && [[ -n "$(ls -A "$probe" 2>/dev/null)" ]]; then
    dbg "submodule already populated"
    return 0
  fi
  info "initializing examples submodule"
  run "git -C '$ROOT' submodule update --init --recursive"
  if [[ ! -d "$probe" ]] || [[ -z "$(ls -A "$probe" 2>/dev/null)" ]]; then
    warn "nxd-data-product-builder will ship without bundled examples (submodule empty)"
  fi
}

# ---- Claude Code target ---------------------------------------------------
cc_dest() {
  if [[ "$SCOPE" == "project" ]]; then echo "$PWD/.claude/skills"; else echo "$HOME/.claude/skills"; fi
}

copy_skill_tree() {  # copy_skill_tree <src-skill-dir> <dst-skill-dir>
  local src="$1" dst="$2"
  # shellcheck disable=SC2046
  run "rsync -a --delete $(rsync_excludes) '$src/' '$dst/'"
}

install_code() {
  local dest; dest="$(cc_dest)"
  info "installing skills -> $dest ($SCOPE)"
  run "mkdir -p '$dest'"
  while IFS= read -r s; do
    copy_skill_tree "$SRC_DIR/$s" "$dest/$s"
    ok "code: $s"
  done < <(selected_skills)
  info "Claude Code: skills installed. Restart Claude Code or start it in a project to use them."
}

uninstall_code() {
  local dest; dest="$(cc_dest)"
  info "removing skills from $dest"
  while IFS= read -r s; do
    if [[ -d "$dest/$s" ]]; then run "rm -rf '$dest/$s'"; ok "removed: $s"; fi
  done < <(selected_skills)
  [[ -d "$dest" ]] && rmdir "$dest" 2>/dev/null && dbg "removed empty $dest" || true
}

status_code() {
  local dest; dest="$(cc_dest)"
  echo "Claude Code ($SCOPE): $dest"
  while IFS= read -r s; do
    if [[ -d "$dest/$s" ]]; then echo "  ✓ $s"; else echo "  · $s (not installed)"; fi
  done < <(selected_skills)
}

# ---- Claude Desktop / Cowork: zip path (default, supported) ---------------
desktop_zip() {
  info "building Claude Desktop skill zips"
  run "(cd '$ROOT' && ./build-skills.sh)"
  cat >&2 <<EOF

Claude Desktop / Cowork — upload the zips:
  1. Open Claude Desktop → Settings → Customize → Skills
  2. Click + → Create skill → Upload a skill
  3. Upload each zip from: $ROOT/build/
     ($(ls "$ROOT"/build/*.zip 2>/dev/null | wc -l | tr -d ' ') zips, one per skill)
  4. Confirm each skill is enabled.
EOF
}

# ---- Claude Desktop / Cowork: rpm injection (experimental) ----------------
is_macos() { [[ "$(uname -s)" == "Darwin" ]]; }

discover_account_id() {
  [[ -n "$ACCOUNT_ID" ]] && { echo "$ACCOUNT_ID"; return 0; }
  local f="$DESKTOP_SUPPORT/cowork-enabled-cli-ops.json"
  if [[ -f "$f" ]]; then
    python3 -c 'import json,sys;print(json.load(open(sys.argv[1])).get("ownerAccountId",""))' "$f"
  fi
}

discover_device_id() {
  [[ -n "$DEVICE_ID" ]] && { echo "$DEVICE_ID"; return 0; }
  local f="$DESKTOP_SUPPORT/config.json"
  [[ -f "$f" ]] || return 0
  python3 - "$f" <<'PY'
import json,sys
c = json.load(open(sys.argv[1]))
ids = sorted({k.split(":",2)[2] for k in c if k.startswith("dxt:allowlistEnabled:")})
# single id => emit it; multiple => emit newline-joined so caller can detect ambiguity
print("\n".join(ids))
PY
}

rpm_dir() {  # echo "<rpm-dir>" or empty if path can't be resolved
  local acct="$1" dev="$2"
  local base="$DESKTOP_SUPPORT/local-agent-mode-sessions"
  local a="$base/$acct/$dev/rpm"
  local b="$base/$dev/$acct/rpm"   # defensive: swapped order
  if [[ -d "$a" ]]; then echo "$a"; elif [[ -d "$b" ]]; then echo "$b"; else echo ""; fi
}

build_plugin_dir() {  # build_plugin_dir <plugin-root>
  local proot="$1"
  run "mkdir -p '$proot/.claude-plugin' '$proot/skills'"
  run "cp '$PLUGIN_JSON' '$proot/.claude-plugin/plugin.json'"
  local manifest="$proot/manifest.json"

  # Copy each skill tree, collecting <skill>\t<name>\t<description> rows.
  local tsv; tsv="$(mktemp)"
  while IFS= read -r s; do
    copy_skill_tree "$SRC_DIR/$s" "$proot/skills/$s"
    printf '%s\t%s\t%s\n' "$s" \
      "$(skill_field "$SRC_DIR/$s/SKILL.md" name)" \
      "$(skill_field "$SRC_DIR/$s/SKILL.md" description)"
  done < <(selected_skills) > "$tsv"

  if [[ "$DRY_RUN" -eq 1 ]]; then
    printf '\033[35m[dry-run]\033[0m write %s (skills[] from frontmatter)\n' "$manifest" >&2
    rm -f "$tsv"
    return 0
  fi
  # manifest.json with skills[] mirroring the anthropic store shape (creatorType:user)
  python3 - "$manifest" "$tsv" "$(now_ms)" <<'PY'
import json,sys
manifest, tsv, ms = sys.argv[1], sys.argv[2], int(sys.argv[3])
skills=[]
with open(tsv, encoding="utf-8") as f:
    for line in f:
        parts=line.rstrip("\n").split("\t")
        if len(parts)<2: continue
        sid, nm = parts[0], parts[1]
        desc = parts[2] if len(parts)>2 else ""
        skills.append({"skillId":sid,"name":nm or sid,"description":desc,
                       "creatorType":"user","enabled":True})
json.dump({"lastUpdated":ms,"skills":skills}, open(manifest,"w"), indent=2)
PY
  rm -f "$tsv"
}

rpm_inject() {  # rpm_inject <manifest> <plugin-root> <version>
  local manifest="$1" proot="$2" ver="$3"
  run "cp '$manifest' '$manifest.nexty-bak.$(now_ms)'"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    printf '\033[35m[dry-run]\033[0m inject plugin entry into %s\n' "$manifest" >&2
    return 0
  fi
  python3 - "$manifest" "$PLUGIN_NAME" "$proot" "$ver" "$(now_iso)" "$(now_ms)" <<'PY'
import json,sys,os,tempfile
manifest,name,proot,ver,iso,ms = sys.argv[1:7]
data = json.load(open(manifest)) if os.path.getsize(manifest) else {}
plugins = data.get("plugins", [])
entry = {"name":name,"displayName":"Nexty AI Pro","version":ver,"scope":"user",
         "enabled":True,"source":"nexty-install.sh","installPath":proot,
         "installedAt":iso,"lastUpdated":iso}
for i,p in enumerate(plugins):
    if p.get("name")==name:
        entry["installedAt"]=p.get("installedAt",iso)  # preserve original install time
        plugins[i]=entry; break
else:
    plugins.append(entry)
data["plugins"]=plugins
data["lastUpdated"]=int(ms)
fd,tmp=tempfile.mkstemp(dir=os.path.dirname(manifest))
with os.fdopen(fd,"w") as f: json.dump(data,f,indent=2)
os.replace(tmp,manifest)
PY
}

install_desktop_rpm() {
  is_macos || { warn "Desktop/Cowork rpm injection is macOS-only; skipping"; return 0; }
  local acct dev
  acct="$(discover_account_id)"
  dev="$(discover_device_id)"
  if [[ -z "$acct" ]]; then warn "could not discover accountId"; desktop_zip; return 0; fi
  if [[ -z "$dev" ]]; then warn "could not discover deviceId"; desktop_zip; return 0; fi
  if [[ "$(printf '%s' "$dev" | grep -c .)" -gt 1 ]]; then
    warn "multiple deviceIds found; pass --device-id ID to choose:"; printf '%s\n' "$dev" >&2
    desktop_zip; return 0
  fi
  local rpm; rpm="$(rpm_dir "$acct" "$dev")"
  if [[ -z "$rpm" ]]; then warn "rpm registry dir not found for $acct/$dev"; desktop_zip; return 0; fi
  local manifest="$rpm/manifest.json"
  if [[ -f "$manifest" ]] && ! python3 -c 'import json,sys;json.load(open(sys.argv[1]))' "$manifest" 2>/dev/null; then
    warn "rpm manifest.json is not valid JSON; not editing"; desktop_zip; return 0
  fi
  [[ -f "$manifest" ]] || run "printf '%s' '{\"lastUpdated\":$(now_ms),\"plugins\":[]}' > '$manifest'"

  local proot="$rpm/plugins/$PLUGIN_NAME"
  local ver; ver="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["version"])' "$PLUGIN_JSON")"
  info "rpm injection -> $proot"
  ensure_submodule
  build_plugin_dir "$proot"
  rpm_inject "$manifest" "$proot" "$ver"
  ok "rpm: injected $PLUGIN_NAME ($ver)"
  cat >&2 <<EOF

⚠ Experimental: the rpm filesystem path is unverified against the running app.
  1. Fully quit and restart Claude Desktop.
  2. Open Customize → Skills and confirm the nxd-* skills appear.
  If they do NOT appear, run:  scripts/install.sh --desktop   (zip-upload, supported)
  To reverse:                  scripts/install.sh uninstall --desktop --rpm-experimental
EOF
}

uninstall_desktop_rpm() {
  is_macos || return 0
  local acct dev; acct="$(discover_account_id)"; dev="$(discover_device_id | head -1)"
  [[ -n "$acct" && -n "$dev" ]] || { warn "cannot resolve ids; nothing to uninstall"; return 0; }
  local rpm; rpm="$(rpm_dir "$acct" "$dev")"
  [[ -n "$rpm" ]] || { warn "rpm dir not found; nothing to uninstall"; return 0; }
  local manifest="$rpm/manifest.json" proot="$rpm/plugins/$PLUGIN_NAME"
  if [[ -f "$manifest" ]]; then
    run "cp '$manifest' '$manifest.nexty-bak.$(now_ms)'"
    if [[ "$DRY_RUN" -eq 0 ]]; then
      python3 - "$manifest" "$PLUGIN_NAME" "$(now_ms)" <<'PY'
import json,sys,os,tempfile
manifest,name,ms=sys.argv[1],sys.argv[2],int(sys.argv[3])
data=json.load(open(manifest))
data["plugins"]=[p for p in data.get("plugins",[]) if p.get("name")!=name]
data["lastUpdated"]=ms
fd,tmp=tempfile.mkstemp(dir=os.path.dirname(manifest))
with os.fdopen(fd,"w") as f: json.dump(data,f,indent=2)
os.replace(tmp,manifest)
PY
    fi
  fi
  [[ -d "$proot" ]] && run "rm -rf '$proot'" || true
  ok "rpm: removed $PLUGIN_NAME — restart Claude Desktop to apply"
}

status_desktop() {
  if ! is_macos; then echo "Claude Desktop/Cowork: macOS-only (n/a here)"; return 0; fi
  local acct dev; acct="$(discover_account_id)"; dev="$(discover_device_id | head -1)"
  echo "Claude Desktop/Cowork: account=${acct:-?} device=${dev:-?}"
  local rpm; rpm="$(rpm_dir "$acct" "$dev" 2>/dev/null || true)"
  if [[ -z "$rpm" ]]; then echo "  rpm registry: not found"; return 0; fi
  local proot="$rpm/plugins/$PLUGIN_NAME"
  [[ -d "$proot" ]] && echo "  ✓ plugin dir: $proot" || echo "  · plugin dir: absent"
  if [[ -f "$rpm/manifest.json" ]] && grep -q "\"$PLUGIN_NAME\"" "$rpm/manifest.json" 2>/dev/null; then
    echo "  ✓ rpm entry present"
  else
    echo "  · rpm entry absent"
  fi
  echo "  zips: $ROOT/build/ ($(ls "$ROOT"/build/*.zip 2>/dev/null | wc -l | tr -d ' ') present)"
}

# Dispatch a desktop/cowork target (default zip, rpm only when requested)
do_desktop_install() {
  if [[ "$FORCE_ZIP" -eq 1 || "$RPM_EXPERIMENTAL" -eq 0 ]]; then desktop_zip; else install_desktop_rpm; fi
}

# ---- main -----------------------------------------------------------------
main() {
  parse_args "$@"
  require_cmd python3
  validate_skill_names
  case "$SUBCMD" in
    install)
      require_cmd rsync git
      run_validation
      local did_desktop=0
      for t in "${TARGETS[@]}"; do
        case "$t" in
          code) ensure_submodule; install_code ;;
          desktop|cowork) [[ "$did_desktop" -eq 1 ]] || { do_desktop_install; did_desktop=1; } ;;
        esac
      done
      ;;
    uninstall)
      local did_desktop=0
      for t in "${TARGETS[@]}"; do
        case "$t" in
          code) uninstall_code ;;
          desktop|cowork)
            [[ "$did_desktop" -eq 1 ]] && continue; did_desktop=1
            if [[ "$RPM_EXPERIMENTAL" -eq 1 ]]; then uninstall_desktop_rpm
            else info "Desktop zip-installed skills are removed from the Customize → Skills UI."; fi ;;
        esac
      done
      ;;
    status)
      local did_desktop=0
      for t in "${TARGETS[@]}"; do
        case "$t" in
          code) status_code ;;
          desktop|cowork) [[ "$did_desktop" -eq 1 ]] || { status_desktop; did_desktop=1; } ;;
        esac
      done
      ;;
    *) usage; exit 2 ;;
  esac
}
main "$@"
