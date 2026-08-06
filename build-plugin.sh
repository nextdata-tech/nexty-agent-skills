#!/usr/bin/env bash
# Package the Claude Code plugin into a single zip:
#   build/nexty-agent-skills-plugin-v<version>.zip
#
# Layout is the documented plugin format (https://code.claude.com/docs/en/plugins):
# the PLUGIN ROOT's contents sit at the archive root — `.claude-plugin/plugin.json`
# plus the component directories beside it, never inside `.claude-plugin/`. Here the
# components live in `src/`, which is legal because plugin.json declares the custom
# path `"skills": "./src/"` (a supported manifest field). Consumers load the zip with
# `claude --plugin-dir <zip>` or `claude --plugin-url <url>`.
#
# marketplace.json is deliberately NOT bundled. It describes a marketplace that
# CONTAINS this plugin (`source: "./"`), which is the git/marketplace install path,
# not this one. Shipping it also makes `claude plugin validate` resolve the directory
# as a marketplace and skip validating the plugin manifest entirely.
#
# This is NOT what build-skills.sh produces. That script targets Claude Desktop,
# which installs one skill per zip and caps each at 200 entries; it therefore
# prunes the bundled examples submodule down to a curated set. Claude Code
# installs the whole plugin and has no such cap, so this bundle keeps the
# submodule intact. Both can coexist in build/.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUT_DIR="$ROOT_DIR/build"
PLUGIN_JSON="$ROOT_DIR/.claude-plugin/plugin.json"
MARKETPLACE_JSON="$ROOT_DIR/.claude-plugin/marketplace.json"
# The submodule bundled into this skill. Uninitialized, it packages as an empty
# directory and the bundle ships that skill hollow — invisibly.
SUBMODULE_DIR="$ROOT_DIR/src/nxd-build-data-product/reference/nextdata-public-examples"

mkdir -p "$OUT_DIR"

json_get() { python3 -c "import json,sys;print(json.load(open(sys.argv[1]))$2)" "$1"; }

# --- Preflight: fail before writing a bundle that is quietly wrong -----------

# plugin.json is the single source of truth for the version (see AGENTS.md).
VERSION="$(json_get "$PLUGIN_JSON" "['version']")"
MARKET_VERSION="$(json_get "$MARKETPLACE_JSON" "['plugins'][0]['version']")"
if [[ "$VERSION" != "$MARKET_VERSION" ]]; then
  echo "error: marketplace.json version '$MARKET_VERSION' != plugin.json version '$VERSION'." >&2
  echo "       The two manifests must be synced in the same change." >&2
  exit 1
fi

# We package src/ by name; assert the manifest still points there.
SKILLS_PATH="$(json_get "$PLUGIN_JSON" "['skills']")"
if [[ "$SKILLS_PATH" != "./src/" ]]; then
  echo "error: plugin.json 'skills' is '$SKILLS_PATH', not './src/'." >&2
  echo "       This script packages src/ by name — update it to match." >&2
  exit 1
fi

# An uninitialized submodule is the failure mode worth guarding: the zip builds
# fine, weighs almost the same, and ships nxd-build-data-product without the
# ~290 example files its reference/examples-guide.md points at.
if [[ ! -f "$SUBMODULE_DIR/README.md" ]]; then
  echo "error: the nextdata-public-examples submodule is not initialized." >&2
  echo "       Bundling now would ship nxd-build-data-product without its examples." >&2
  echo "       Fix: git submodule update --init --recursive" >&2
  exit 1
fi

# --- Package ----------------------------------------------------------------

ZIP_PATH="$OUT_DIR/nexty-agent-skills-plugin-v${VERSION}.zip"
rm -f "$ZIP_PATH"

# Paths are relative to ROOT_DIR (we cd there before zipping). Only plugin.json
# from .claude-plugin/ — see the marketplace.json note in the header. README.md
# ships so an unzipped copy explains how to install itself; LICENSE if one exists.
CONTENTS=(.claude-plugin/plugin.json src README.md)
[[ -f "$ROOT_DIR/LICENSE" ]] && CONTENTS+=(LICENSE)

# VCS metadata, caches and OS junk. Unlike build-skills.sh this keeps the
# examples submodule whole — Claude Code has no per-skill entry cap.
EXCLUDES=(
  '*/.git/*'          '*/.git'
  '*/.gitmodules'
  '*/__pycache__/*'   '__pycache__/*'
  '*.pyc'             '*.pyo'
  '.DS_Store'         '*/.DS_Store'
  'Thumbs.db'         '*/Thumbs.db'
  '*/.pytest_cache/*'
  '*.zip'             '*/*.zip'
  # Field-mapper e2e proof needs an nxd monorepo checkout no consumer has; its
  # run ledgers and live-API credentials must never leave the machine. zip reads
  # the filesystem, not git, so gitignored artifacts need excluding here too.
  '*/mapper/examples/*'
  '*/mapper/runs/*'
  '*/.venv-live/*'
  '*/.env'            '*/.env.*'
)
ZIP_EXCLUDE_ARGS=()
for p in "${EXCLUDES[@]}"; do ZIP_EXCLUDE_ARGS+=("-x" "$p"); done

(
  cd "$ROOT_DIR"
  zip -qrD "$ZIP_PATH" "${CONTENTS[@]}" "${ZIP_EXCLUDE_ARGS[@]}"
)

# --- Verify what was actually written ---------------------------------------

unzip -tqq "$ZIP_PATH"   # archive integrity

# Read the manifest back out of the zip rather than trusting the input: this is
# the one check that proves the bundle a consumer unzips carries this version.
PACKED_VERSION="$(unzip -p "$ZIP_PATH" .claude-plugin/plugin.json | python3 -c 'import json,sys;print(json.load(sys.stdin)["version"])')"
if [[ "$PACKED_VERSION" != "$VERSION" ]]; then
  echo "error: packaged plugin.json reports '$PACKED_VERSION', expected '$VERSION'." >&2
  exit 1
fi

# Validate the UNPACKED artifact, not the repo: the repo root also holds
# marketplace.json, so validating there checks the marketplace manifest and never
# looks at the plugin. `claude plugin validate` cannot read a zip (it tries to
# parse the archive as JSON), hence the unpack.
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
unzip -q "$ZIP_PATH" -d "$STAGE"
if command -v claude >/dev/null 2>&1; then
  claude plugin validate "$STAGE" --strict
else
  echo "note: 'claude' CLI not found — skipped 'claude plugin validate --strict'." >&2
fi

# The manifest's custom skills path must actually resolve inside the bundle, or
# the plugin loads with zero skills and no error.
if [[ ! -d "$STAGE/src" ]] || ! ls "$STAGE"/src/*/SKILL.md >/dev/null 2>&1; then
  echo "error: packaged bundle has no src/<skill>/SKILL.md — plugin.json's" >&2
  echo "       'skills': '$SKILLS_PATH' would resolve to nothing." >&2
  exit 1
fi

entries="$(unzip -l "$ZIP_PATH" | tail -1 | awk '{print $2}')"
# String regex, not /…/ — a slash inside a character class ends an awk literal.
skills="$(unzip -l "$ZIP_PATH" | awk '$NF ~ "^src/[^/]+/SKILL[.]md$"' | wc -l | tr -d ' ')"
size="$(du -h "$ZIP_PATH" | awk '{print $1}')"

printf '%-12s %s\n' "plugin"  "nexty-agent-skills v${VERSION}"
printf '%-12s %s\n' "skills"  "$skills"
printf '%-12s %s\n' "entries" "$entries"
printf '%-12s %s\n' "size"    "$size"
echo
echo "Plugin zip written to ${ZIP_PATH}"
