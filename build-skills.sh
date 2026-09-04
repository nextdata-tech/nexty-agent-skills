#!/usr/bin/env bash
# Package each skill in src/ into a zip, excluding noise (VCS, CI, caches,
# pre-commit hooks, lockfiles, OS junk). Also assemble the uploadable plugin zips
# declared in .claude-plugin/marketplace.json. Report file count + size per
# skill. Output zips land in build/ directory: build/<skill>.zip,
# build/nexty-desktop-v<version>.zip, build/nexty-datamesh-v<version>.zip, and
# the legacy aggregate build/nexty-agent-skills-v<version>.zip.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC_DIR="$ROOT_DIR/src"
OUT_DIR="$ROOT_DIR/build"
MARKETPLACE_JSON="$ROOT_DIR/.claude-plugin/marketplace.json"
mkdir -p "$OUT_DIR"
# The directory is generated output. Clear old archives so a release or local
# rebuild cannot publish a removed skill or a pack from a previous version.
rm -f "$OUT_DIR"/*.zip

PLUGIN_VERSION="$(python3 - "$ROOT_DIR/.claude-plugin/plugin.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as fh:
    version = json.load(fh).get("version")
if not isinstance(version, str) or not version:
    raise SystemExit(".claude-plugin/plugin.json has no version")
print(version)
PY
)"
PACK_PATH="$OUT_DIR/nexty-agent-skills-v${PLUGIN_VERSION}.zip"
SKILL_ZIPS=()

# Exclusion globs (matched by `zip -x`). Patterns are relative to the skill
# root once we cd into it; '*/' covers any depth.
EXCLUDES=(
  '*/.git/*'        '.git/*'
  '*/.git'          '.git'
  '*/.github/*'     '.github/*'
  '*.gitignore'     '.gitignore'
  '*/__pycache__/*' '__pycache__/*'
  '*.pyc'           '*.pyo'
  '.DS_Store'       '*/.DS_Store'
  'Thumbs.db'       '*/Thumbs.db'
  '*/.pre-commit-hooks/*' '.pre-commit-hooks/*'
  '*/.pre-commit-config.yaml' '.pre-commit-config.yaml'
  '*/.tool-versions' '.tool-versions'
  '*/.gitignore'    '.gitignore'
  '*/.nxdignore'    '.nxdignore'
  '*/.nxdignore/*'
  '*.zip'           '*/*.zip'
  '*/uv.lock'       'uv.lock'
  # The field-mapper harness is not in this repo at all. It lives in the nxd
  # monorepo and reaches a closure as `nxd.experimental.field_mapper`, from the
  # installed nxd package. This repo carried a second copy for a while so the
  # consent-gate tests had something real to run against; two copies of
  # executable source with nothing enforcing sync drifted within a day, so the
  # tests resolve the monorepo copy instead (`evals/tests/_harness.py`) and skip
  # where it is unreachable. The exclusion below stays because zip reads the
  # filesystem rather than git: a stray local checkout under `mapper/` must
  # still not ship. `mapper/CONTRACT.md` and `mapper/samples/` DO ship: the
  # contract is the normative record of the harness's behaviour (record schemas,
  # value_status semantics, the blocking rules), and it describes the fixtures
  # case by case, so shipping the prose without the cases it cites would leave a
  # reader unable to check any claim in it. The runtime's own copy of the
  # fixtures answers "is this harness intact?"; these answer "what is this
  # harness supposed to do?", which is what a closure author needs.
  # Its e2e proof needs an nxd monorepo checkout a Desktop user cannot have,
  # and its run ledgers / live-API credentials must never leave the machine.
  # zip reads the filesystem, not git, so gitignored artifacts need excluding
  # here too.
  'mapper/field_mapper/*'  '*/mapper/field_mapper/*'
  'mapper/examples/*'  '*/mapper/examples/*'
  'mapper/runs/*'      '*/mapper/runs/*'
  '.venv-live/*'       '*/.venv-live/*'
  '.env'               '*/.env'
  '.env.*'             '*/.env.*'
  # Strip housekeeping from the bundled examples repo only
  '*/nextdata-public-examples/README.md'
  '*/nextdata-public-examples/CLAUDE.md'
  '*/nextdata-public-examples/pyproject.toml'
  '*/nextdata-public-examples/data_products/feature_matrix_table.md'
  # Strip per-DP housekeeping (not load-bearing for the spec/transform patterns)
  '*/data_products/*/README.md'
  '*/data_products/*/.python-version'
  '*/data_products/*/pyproject.toml'
  '*/data_products/*/PROVISION.md'
  '*/data_products/*/notebooks/*'
  '*/data_products/*/tests/*'
)

# The bundled nextdata-public-examples submodule carries ~26 DPs (~280 files),
# which blows the Claude Desktop 200-entry zip cap. For packaging we keep only
# the curated set that reference/examples-guide.md actually points at; the full
# submodule stays checked out for Claude Code (which has no such cap).
# To change the curated set, edit examples-guide.md and this list together.
EXAMPLES_KEEP=(
  company_dividends competitor_growth_analysis credit_card_tx customer_purchases
  example_mcp financial_statements income_statements loans_products
  market_fraud_density product_competitiveness public_disclosures stock_history
  taxi-trip-metrics jira_issues
)

# Build an exclude for every example DP NOT in the keep list. We enumerate the
# DP dirs present in each skill's bundled submodule at package time.
examples_prune_args() {
  local skill_dir="$1" dp_root="$skill_dir/reference/nextdata-public-examples/data_products"
  [[ -d "$dp_root" ]] || return 0
  local keep_re; keep_re="^($(IFS='|'; echo "${EXAMPLES_KEEP[*]}"))$"
  for dp in "$dp_root"/*/; do
    local name; name="$(basename "$dp")"
    [[ "$name" =~ $keep_re ]] && continue
    printf '%s\0' "-x" "*/nextdata-public-examples/data_products/$name/*"
  done
}

# Build the -x argv once
ZIP_EXCLUDE_ARGS=()
for p in "${EXCLUDES[@]}"; do ZIP_EXCLUDE_ARGS+=("-x" "$p"); done

CAP=200
printf '%-32s %6s %5s %6s %8s %s\n' "skill" "files" "dirs" "total" "size" "status"
printf '%-32s %6s %5s %6s %8s %s\n' "-----" "-----" "----" "-----" "----" "------"

for skill_dir in "$SRC_DIR"/*/; do
  skill="$(basename "$skill_dir")"
  zip_path="$OUT_DIR/${skill}.zip"
  rm -f "$zip_path"

  # Per-skill prune of non-curated example DPs (no-op for skills without the submodule)
  prune_args=()
  while IFS= read -r -d '' a; do prune_args+=("$a"); done < <(examples_prune_args "$skill_dir")

  (
    cd "$skill_dir"
    zip_args=(. "${ZIP_EXCLUDE_ARGS[@]}")
    if [[ -n "${prune_args[0]+set}" ]]; then
      zip_args+=("${prune_args[@]}")
    fi
    zip -qrD "$zip_path" "${zip_args[@]}"
  )

  files="$(unzip -l "$zip_path" | awk 'NR>3 && $NF!~/\/$/' | wc -l | tr -d ' ')"
  dirs="$(unzip -l "$zip_path" | awk 'NR>3 && $NF~/\/$/' | wc -l | tr -d ' ')"
  total=$((files + dirs))
  size="$(du -h "$zip_path" | awk '{print $1}')"
  status="ok"
  if [[ "$total" -gt "$CAP" ]]; then status="OVER CAP ($CAP)"; fi
  printf '%-32s %6d %5d %6d %8s %s\n' "$skill" "$files" "$dirs" "$total" "$size" "$status"
  SKILL_ZIPS+=("$zip_path")
done

echo
echo "Skill zips written to ${OUT_DIR}/"

# The marketplace is the source of truth for plugin membership. These entries
# use Claude Code's skill-bundle form, so both plugins can project selected
# skills from the same src/ tree without maintaining duplicate source files.
skill_names_for_plugin() {
  local plugin_name="$1"
  python3 - "$MARKETPLACE_JSON" "$plugin_name" <<'PY'
import json
import sys

marketplace_path, plugin_name = sys.argv[1:]
with open(marketplace_path, encoding="utf-8") as fh:
    marketplace = json.load(fh)

for plugin in marketplace.get("plugins", []):
    if plugin.get("name") != plugin_name:
        continue
    if plugin.get("source") != "./src":
        raise SystemExit(
            f"{plugin_name}: expected marketplace source './src' for a skill-bundle plugin"
        )
    skills = plugin.get("skills")
    if not isinstance(skills, list) or not skills:
        raise SystemExit(f"{plugin_name}: marketplace entry has no skills list")
    for skill in skills:
        if not isinstance(skill, str) or not skill.startswith("./"):
            raise SystemExit(f"{plugin_name}: invalid skill path {skill!r}")
        print(skill[2:])
    break
else:
    raise SystemExit(f"marketplace entry not found: {plugin_name}")
PY
}

write_plugin_manifest() {
  local plugin_name="$1" destination="$2"
  python3 - "$ROOT_DIR/.claude-plugin/plugin.json" "$MARKETPLACE_JSON" "$plugin_name" "$destination" <<'PY'
import json
import sys

plugin_path, marketplace_path, plugin_name, destination = sys.argv[1:]
with open(plugin_path, encoding="utf-8") as fh:
    manifest = json.load(fh)
with open(marketplace_path, encoding="utf-8") as fh:
    marketplace = json.load(fh)

entry = next(
    (item for item in marketplace.get("plugins", []) if item.get("name") == plugin_name),
    None,
)
if entry is None:
    raise SystemExit(f"marketplace entry not found: {plugin_name}")

manifest["name"] = plugin_name
manifest["displayName"] = entry.get("displayName", plugin_name)
manifest["description"] = entry.get("description", manifest.get("description", ""))
manifest.pop("skills", None)
manifest.pop("$schema", None)
with open(destination, "w", encoding="utf-8") as fh:
    json.dump(manifest, fh, indent=2)
    fh.write("\n")
PY
}

build_plugin_pack() {
  local plugin_name="$1" archive_name="$2"
  local pack_staging
  pack_staging="$(mktemp -d "${TMPDIR:-/tmp}/nexty-agent-skills-pack.XXXXXX")"
  mkdir -p "$pack_staging/.claude-plugin" "$pack_staging/skills"
  write_plugin_manifest "$plugin_name" "$pack_staging/.claude-plugin/plugin.json"

  while IFS= read -r skill; do
    [[ -f "$OUT_DIR/$skill.zip" ]] || {
      echo "error: missing per-skill archive for $plugin_name: $skill" >&2
      rm -rf "$pack_staging"
      exit 1
    }
    mkdir -p "$pack_staging/skills/$skill"
    unzip -q "$OUT_DIR/$skill.zip" -d "$pack_staging/skills/$skill"
  done < <(skill_names_for_plugin "$plugin_name")

  local pack_path="$OUT_DIR/${archive_name}-v${PLUGIN_VERSION}.zip"
  rm -f "$pack_path"
  (
    cd "$pack_staging"
    zip -qrD "$pack_path" .
  )
  local pack_files pack_size
  pack_files="$(unzip -Z1 "$pack_path" | wc -l | tr -d ' ')"
  pack_size="$(du -h "$pack_path" | awk '{print $1}')"
  echo "Plugin pack: ${pack_path} (${pack_files} files, ${pack_size})"
  rm -rf "$pack_staging"
}

# Build the two new plugin projections from the same sanitized per-skill
# archives used by the compatibility aggregate below.
build_plugin_pack "nexty-desktop" "nexty-desktop"
build_plugin_pack "nexty-datamesh" "nexty-datamesh"

# Assemble the same layout that Claude Desktop/Cowork accepts as one plugin
# upload and that nxd's Desktop cache uses: ./skills/<name>/ plus
# ./.claude-plugin/plugin.json. The source plugin manifest points at ./src for
# Claude Code; Desktop auto-discovers ./skills instead, so remove that
# override (and the schema URL, which the Desktop installer does not need).
PACK_STAGING="$(mktemp -d "${TMPDIR:-/tmp}/nexty-agent-skills-pack.XXXXXX")"
trap 'rm -rf "$PACK_STAGING"' EXIT
mkdir -p "$PACK_STAGING/.claude-plugin" "$PACK_STAGING/skills"
python3 - "$ROOT_DIR/.claude-plugin/plugin.json" "$PACK_STAGING/.claude-plugin/plugin.json" <<'PY'
import json
import sys

src, dst = sys.argv[1:]
with open(src, encoding="utf-8") as fh:
    plugin = json.load(fh)
plugin.pop("skills", None)
plugin.pop("$schema", None)
with open(dst, "w", encoding="utf-8") as fh:
    json.dump(plugin, fh, indent=2)
    fh.write("\n")
PY
if [[ -n "${SKILL_ZIPS[0]+set}" ]]; then
  for zip_path in "${SKILL_ZIPS[@]}"; do
    skill="$(basename "$zip_path" .zip)"
    mkdir -p "$PACK_STAGING/skills/$skill"
    unzip -q "$zip_path" -d "$PACK_STAGING/skills/$skill"
  done
fi

rm -f "$PACK_PATH"
(
  cd "$PACK_STAGING"
  zip -qrD "$PACK_PATH" .
)
pack_files="$(unzip -Z1 "$PACK_PATH" | wc -l | tr -d ' ')"
pack_size="$(du -h "$PACK_PATH" | awk '{print $1}')"
echo "Plugin pack: ${PACK_PATH} (${pack_files} files, ${pack_size})"
