#!/usr/bin/env bash
# install.sh — first-party installer for the Nexty AI Pro skill pack.
#
# Installs the skills under src/<skill>/ to one or more Claude targets:
#   --code     Claude Code        -> ~/.claude/skills (global) or ./.claude/skills (--project)
#   --desktop  Claude Desktop     -> marketplace-cache injection (survives restart), or zip build+upload (--zip)
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
FORCE_ZIP=0
ACCOUNT_ID=""
DEVICE_ID=""
ASSUME_YES=0
DRY_RUN=0
VERBOSE=0

DESKTOP_SUPPORT="$HOME/Library/Application Support/Claude"
PLUGIN_NAME="nexty-agent-skills"
MP_NAME="nexty"                                  # marketplace name (matches marketplace.json)
MP_REPO="nextdata-tech/nexty-agent-skills"       # owner/name for the marketplace source

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
  --desktop  Claude Desktop  -> marketplace-cache injection (filesystem, no upload)
  --cowork   Claude Cowork   -> same local-agent-mode store as --desktop
  --all      all of the above

Usage: scripts/install.sh [install|uninstall|status|help] [targets] [scope] [options]

Targets (default --code):  --code  --desktop  --cowork  --all
Scope (Code only):         (default global ~/.claude/skills)  |  --project (./.claude/skills)

Options:
  --uninstall            Alias for the `uninstall` subcommand
  --skills "a b c"       Restrict to a subset of skills (default: all)
  --no-validate          Skip scripts/validate_skills.py (not recommended)
  --no-submodule         Don't auto-init the examples submodule
  --zip                  Desktop/Cowork: build zips + print manual-upload steps
                         instead of the filesystem marketplace install
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
      --zip)     FORCE_ZIP=1 ;;
      --account-id) shift; [[ $# -gt 0 ]] || die "--account-id needs an argument"
                    ACCOUNT_ID="$1" ;;
      --device-id)  shift; [[ $# -gt 0 ]] || die "--device-id needs an argument"
                    DEVICE_ID="$1" ;;
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
  [[ -d "$dest" ]] && run "rmdir '$dest' 2>/dev/null || true"
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

# ---- Claude Desktop / Cowork: marketplace-cache injection -----------------
# Mechanism (proven 2026-06-30, survives restart): mimic what the "Browse
# plugins" UI writes to disk. Under <support>/local-agent-mode-sessions/
# <acct>/<dev>/cowork_plugins/ we materialize a marketplace + a plugin cache
# and register both in known_marketplaces.json + installed_plugins.json.
# Skills are auto-discovered from the cache's ./skills/ — plugin.json must NOT
# carry a "skills" key (that overrides discovery to a wrong path).
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

cowork_root() {  # echo "<cowork_plugins dir>" or empty if path can't be resolved
  local acct="$1" dev="$2"
  local base="$DESKTOP_SUPPORT/local-agent-mode-sessions"
  local a="$base/$acct/$dev/cowork_plugins"
  local b="$base/$dev/$acct/cowork_plugins"   # defensive: swapped order
  if [[ -d "$a" ]]; then echo "$a"; elif [[ -d "$b" ]]; then echo "$b"; else echo ""; fi
}

plugin_version() { python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["version"])' "$PLUGIN_JSON"; }

# Resolve account+device to a single (acct,dev) pair, or empty on ambiguity/miss.
# Prints "acct\tdev" on success. Emits guidance to stderr and returns 1 otherwise.
resolve_ids() {
  local acct dev
  acct="$(discover_account_id)"; dev="$(discover_device_id)"
  if [[ -z "$acct" ]]; then warn "could not discover accountId (pass --account-id)"; return 1; fi
  if [[ -z "$dev" ]]; then warn "could not discover deviceId (pass --device-id)"; return 1; fi
  if [[ "$(printf '%s' "$dev" | grep -c .)" -gt 1 ]]; then
    warn "multiple deviceIds found; pass --device-id ID to choose:"; printf '%s\n' "$dev" >&2
    return 1
  fi
  printf '%s\t%s\n' "$acct" "$dev"
}

# Build cache/<mp>/<plugin>/<ver>/ : .claude-plugin/plugin.json (skills key
# stripped) + skills/<name>/. Mirrors the on-disk shape Desktop expects.
build_plugin_cache() {  # build_plugin_cache <cache-dir>
  local cache="$1"
  run "rm -rf '$cache'"
  run "mkdir -p '$cache/.claude-plugin' '$cache/skills'"
  # plugin.json without the "skills" override and without $schema (match the
  # minimal shape the UI installer writes; skills auto-discovered from ./skills/).
  if [[ "$DRY_RUN" -eq 1 ]]; then
    printf '\033[35m[dry-run]\033[0m write %s/.claude-plugin/plugin.json (skills key stripped)\n' "$cache" >&2
  else
    python3 - "$PLUGIN_JSON" "$cache/.claude-plugin/plugin.json" <<'PY'
import json,sys
src,dst=sys.argv[1],sys.argv[2]
d=json.load(open(src))
d.pop("skills",None)     # let Desktop auto-discover ./skills/
d.pop("$schema",None)
json.dump(d,open(dst,"w"),indent=2)
PY
  fi
  while IFS= read -r s; do
    copy_skill_tree "$SRC_DIR/$s" "$cache/skills/$s"
  done < <(selected_skills)
}

# Add/replace the marketplace in known_marketplaces.json (atomic, backed up).
register_marketplace() {  # register_marketplace <known.json> <mp-name> <install-location>
  local f="$1" mp="$2" loc="$3"
  [[ -f "$f" ]] && run "cp '$f' '$f.nexty-bak.$(now_ms)'"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    printf '\033[35m[dry-run]\033[0m register marketplace %s in %s\n' "$mp" "$f" >&2; return 0
  fi
  python3 - "$f" "$mp" "$loc" "$MP_REPO" "$(now_iso)" <<'PY'
import json,sys,os,tempfile
f,mp,loc,repo,iso=sys.argv[1:6]
data=json.load(open(f)) if (os.path.exists(f) and os.path.getsize(f)) else {}
data[mp]={"source":{"source":"github","repo":repo},"installLocation":loc,"lastUpdated":iso}
fd,tmp=tempfile.mkstemp(dir=os.path.dirname(f) or ".")
with os.fdopen(fd,"w") as fh: json.dump(data,fh,indent=2)
os.replace(tmp,f)
PY
}

# Add/replace the installed-plugin entry (atomic, backed up). Preserves the
# original installedAt on re-install.
register_plugin() {  # register_plugin <installed.json> <plugin@mp> <cache-dir> <ver> <sha>
  local f="$1" key="$2" cache="$3" ver="$4" sha="$5"
  [[ -f "$f" ]] && run "cp '$f' '$f.nexty-bak.$(now_ms)'"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    printf '\033[35m[dry-run]\033[0m register plugin %s in %s\n' "$key" "$f" >&2; return 0
  fi
  python3 - "$f" "$key" "$cache" "$ver" "$sha" "$(now_iso)" <<'PY'
import json,sys,os,tempfile
f,key,cache,ver,sha,iso=sys.argv[1:7]
data=json.load(open(f)) if (os.path.exists(f) and os.path.getsize(f)) else {"version":2,"plugins":{}}
data.setdefault("version",2); data.setdefault("plugins",{})
prev=data["plugins"].get(key) or []
installed_at=(prev[0].get("installedAt") if prev and isinstance(prev[0],dict) else None) or iso
data["plugins"][key]=[{"scope":"user","installPath":cache,"version":ver,
                       "installedAt":installed_at,"lastUpdated":iso,"gitCommitSha":sha}]
fd,tmp=tempfile.mkstemp(dir=os.path.dirname(f) or ".")
with os.fdopen(fd,"w") as fh: json.dump(data,fh,indent=2)
os.replace(tmp,f)
PY
}

# Enable the plugin + mirror the marketplace in cowork_settings.json. Without
# the enabledPlugins entry the plugin installs but shows "Disabled" in the UI.
register_settings() {  # register_settings <cowork_settings.json> <plugin@mp> <mp-name> <enable 0|1>
  local f="$1" key="$2" mp="$3" enable="$4"
  [[ -f "$f" ]] && run "cp '$f' '$f.nexty-bak.$(now_ms)'"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    printf '\033[35m[dry-run]\033[0m set enabledPlugins[%s]=%s in %s\n' "$key" \
      "$([[ "$enable" -eq 1 ]] && echo true || echo '(remove)')" "$f" >&2
    return 0
  fi
  python3 - "$f" "$key" "$mp" "$MP_REPO" "$enable" <<'PY'
import json,sys,os,tempfile
f,key,mp,repo,enable=sys.argv[1:6]
data=json.load(open(f)) if (os.path.exists(f) and os.path.getsize(f)) else {}
ep=data.setdefault("enabledPlugins",{})
km=data.setdefault("extraKnownMarketplaces",{})
if enable=="1":
    ep[key]=True
    km[mp]={"source":{"source":"github","repo":repo}}
else:
    ep.pop(key,None)
    if not any(k.endswith("@"+mp) for k in ep): km.pop(mp,None)
fd,tmp=tempfile.mkstemp(dir=os.path.dirname(f) or ".")
with os.fdopen(fd,"w") as fh: json.dump(data,fh,indent=2)
os.replace(tmp,f)
PY
}

# Materialize the marketplace checkout (a working tree at marketplaces/<mp>/
# with the repo's marketplace.json). Echoes the HEAD sha used for gitCommitSha.
materialize_marketplace() {  # materialize_marketplace <marketplaces-dir>
  local mpdir="$1"
  run "rm -rf '$mpdir'"
  run "mkdir -p '$mpdir/.claude-plugin'"
  run "cp '$ROOT/.claude-plugin/marketplace.json' '$mpdir/.claude-plugin/marketplace.json'"
  # gitCommitSha: real repo HEAD when available, else a deterministic placeholder.
  local sha=""
  sha="$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || true)"
  [[ -n "$sha" ]] || sha="local-$(plugin_version)"
  echo "$sha"
}

install_desktop_marketplace() {
  is_macos || { warn "Desktop/Cowork install is macOS-only; skipping"; return 0; }
  local pair; pair="$(resolve_ids)" || return 0
  local acct dev; acct="${pair%%$'\t'*}"; dev="${pair##*$'\t'}"
  local cw; cw="$(cowork_root "$acct" "$dev")"
  if [[ -z "$cw" ]]; then warn "cowork_plugins dir not found for $acct/$dev"; return 0; fi

  local ver mpdir cache key sha
  ver="$(plugin_version)"
  mpdir="$cw/marketplaces/$MP_NAME"
  cache="$cw/cache/$MP_NAME/$PLUGIN_NAME/$ver"
  key="$PLUGIN_NAME@$MP_NAME"

  info "marketplace injection -> $cw ($MP_NAME / $PLUGIN_NAME $ver)"
  ensure_submodule
  sha="$(materialize_marketplace "$mpdir")"
  build_plugin_cache "$cache"
  register_marketplace "$cw/known_marketplaces.json" "$MP_NAME" "$mpdir"
  register_plugin "$cw/installed_plugins.json" "$key" "$cache" "$ver" "$sha"
  register_settings "$(dirname "$cw")/cowork_settings.json" "$key" "$MP_NAME" 1
  ok "marketplace: installed + enabled $key ($ver)"
  cat >&2 <<EOF

Claude Desktop / Cowork — installed and enabled.
  Fully quit and restart Claude Desktop (Cmd+Q, reopen) to load it.
  Skills then invoke via /<skill-name> in chat, or automatically.
  To reverse:  scripts/install.sh uninstall --desktop
EOF
}

uninstall_desktop_marketplace() {
  is_macos || return 0
  local pair; pair="$(resolve_ids)" || return 0
  local acct dev; acct="${pair%%$'\t'*}"; dev="${pair##*$'\t'}"
  local cw; cw="$(cowork_root "$acct" "$dev")"
  [[ -n "$cw" ]] || { warn "cowork_plugins dir not found; nothing to uninstall"; return 0; }

  local key="$PLUGIN_NAME@$MP_NAME"
  # Drop the installed-plugin entry (backed up).
  local inst="$cw/installed_plugins.json"
  if [[ -f "$inst" ]]; then
    run "cp '$inst' '$inst.nexty-bak.$(now_ms)'"
    if [[ "$DRY_RUN" -eq 0 ]]; then
      python3 - "$inst" "$key" <<'PY'
import json,sys,os,tempfile
f,key=sys.argv[1],sys.argv[2]
data=json.load(open(f))
data.get("plugins",{}).pop(key,None)
fd,tmp=tempfile.mkstemp(dir=os.path.dirname(f) or ".")
with os.fdopen(fd,"w") as fh: json.dump(data,fh,indent=2)
os.replace(tmp,f)
PY
    fi
  fi
  # Drop the marketplace registration only if no other plugin references it.
  local known="$cw/known_marketplaces.json"
  if [[ -f "$known" && "$DRY_RUN" -eq 0 ]]; then
    run "cp '$known' '$known.nexty-bak.$(now_ms)'"
    python3 - "$known" "$inst" "$MP_NAME" <<'PY'
import json,sys,os,tempfile
known,inst,mp=sys.argv[1],sys.argv[2],sys.argv[3]
plugins=json.load(open(inst)).get("plugins",{}) if os.path.exists(inst) else {}
still_used=any(k.endswith("@"+mp) for k in plugins)
data=json.load(open(known))
if not still_used: data.pop(mp,None)
fd,tmp=tempfile.mkstemp(dir=os.path.dirname(known) or ".")
with os.fdopen(fd,"w") as fh: json.dump(data,fh,indent=2)
os.replace(tmp,known)
PY
  elif [[ "$DRY_RUN" -eq 1 ]]; then
    printf '\033[35m[dry-run]\033[0m drop marketplace %s if unreferenced\n' "$MP_NAME" >&2
  fi
  # Disable + de-mirror in cowork_settings.json.
  register_settings "$(dirname "$cw")/cowork_settings.json" "$key" "$MP_NAME" 0
  # Remove cache + marketplace checkout dirs.
  run "rm -rf '$cw/cache/$MP_NAME/$PLUGIN_NAME'"
  run "rmdir '$cw/cache/$MP_NAME' 2>/dev/null || true"
  run "rm -rf '$cw/marketplaces/$MP_NAME'"
  ok "marketplace: removed $key — restart Claude Desktop to apply"
}

status_desktop() {
  if ! is_macos; then echo "Claude Desktop/Cowork: macOS-only (n/a here)"; return 0; fi
  local acct dev; acct="$(discover_account_id)"; dev="$(discover_device_id)"
  if [[ "$(printf '%s' "$dev" | grep -c .)" -gt 1 ]]; then
    echo "Claude Desktop/Cowork: account=${acct:-?} devices (multiple — pass --device-id):"
    while IFS= read -r d; do echo "  - $d"; done <<<"$dev"; return 0
  fi
  echo "Claude Desktop/Cowork: account=${acct:-?} device=${dev:-?}"
  local cw; cw="$(cowork_root "$acct" "$dev" 2>/dev/null || true)"
  if [[ -z "$cw" ]]; then echo "  cowork_plugins: not found"; return 0; fi
  local key="$PLUGIN_NAME@$MP_NAME"
  if [[ -f "$cw/installed_plugins.json" ]] && \
     python3 -c 'import json,sys;d=json.load(open(sys.argv[1]));sys.exit(0 if sys.argv[2] in d.get("plugins",{}) else 1)' \
       "$cw/installed_plugins.json" "$key" 2>/dev/null; then
    echo "  ✓ registered: $key"
  else
    echo "  · not registered ($key)"
  fi
  local ver; ver="$(plugin_version)"
  [[ -d "$cw/cache/$MP_NAME/$PLUGIN_NAME/$ver/skills" ]] \
    && echo "  ✓ cache: $cw/cache/$MP_NAME/$PLUGIN_NAME/$ver" \
    || echo "  · cache: absent"
  local settings; settings="$(dirname "$cw")/cowork_settings.json"
  if [[ -f "$settings" ]] && \
     python3 -c 'import json,sys;d=json.load(open(sys.argv[1]));sys.exit(0 if d.get("enabledPlugins",{}).get(sys.argv[2]) else 1)' \
       "$settings" "$key" 2>/dev/null; then
    echo "  ✓ enabled"
  else
    echo "  · disabled (toggle in Customize → Skills, or reinstall)"
  fi
}

# Dispatch a desktop/cowork target.
do_desktop_install() {
  if [[ "$FORCE_ZIP" -eq 1 ]]; then desktop_zip; else install_desktop_marketplace; fi
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
            if [[ "$FORCE_ZIP" -eq 1 ]]; then
              info "Zip-uploaded skills are removed from the Customize → Skills UI."
            else uninstall_desktop_marketplace; fi ;;
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
