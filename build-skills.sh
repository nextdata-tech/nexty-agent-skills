#!/usr/bin/env bash
# Package each skill in src/ into a zip, excluding noise (VCS, CI, caches,
# pre-commit hooks, lockfiles, OS junk). Report file count + size per skill.
# Output zips land in the build/ directory: build/<skill>.zip.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC_DIR="$ROOT_DIR/src"
OUT_DIR="$ROOT_DIR/build"
mkdir -p "$OUT_DIR"

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
    if [[ "${#prune_args[@]}" -gt 0 ]]; then
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
done

echo
echo "Skill zips written to ${OUT_DIR}/"
