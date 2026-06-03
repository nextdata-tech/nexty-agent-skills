#!/usr/bin/env bash
# Package each skill in src/ into a zip, excluding noise (VCS, CI, caches,
# pre-commit hooks, lockfiles, OS junk). Report file count + size per skill.
# Output zips land next to each skill dir: src/<skill>/<skill>.zip (also
# copied to repo root for convenience).
set -euo pipefail

SRC_DIR="$(cd "$(dirname "$0")" && pwd)/src"
OUT_DIR="$(cd "$(dirname "$0")" && pwd)"

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

  (
    cd "$skill_dir"
    zip -qrD "$zip_path" . "${ZIP_EXCLUDE_ARGS[@]}"
  )

  files="$(unzip -l "$zip_path" | awk 'NR>3 && $NF!~/\/$/' | wc -l | tr -d ' ')"
  dirs="$(unzip -l "$zip_path" | awk 'NR>3 && $NF~/\/$/' | wc -l | tr -d ' ')"
  total=$((files + dirs))
  size="$(du -h "$zip_path" | awk '{print $1}')"
  status="ok"
  if [[ "$total" -gt "$CAP" ]]; then status="OVER CAP ($CAP)"; fi
  printf '%-32s %6d %5d %6d %8s %s\n' "$skill" "$files" "$dirs" "$total" "$size" "$status"
done
