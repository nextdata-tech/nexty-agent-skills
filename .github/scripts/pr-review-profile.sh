#!/usr/bin/env bash
# Classify a pull-request diff for the Claude review workflow.
#
# The review prompt asserts pack-level invariants (version lockstep across three
# surfaces, current_pack completeness, README table rows) that can only break
# when specific files move. A diff that touches none of them does not need the
# expensive review tier. The script is intentionally conservative: any parse
# failure, unknown path, or missing revision preserves the full/xhigh review.
#
# Usage: pr-review-profile.sh <base_sha> <head_sha> [force_full]
# Emits profile/effort/reason/file_count/changed_lines to $GITHUB_OUTPUT.
set -euo pipefail

base_sha=${1:-}
head_sha=${2:-}
force_full=${3:-false}

profile=full
effort=xhigh
reason=classifier-error
file_count=0
changed_lines=0

emit_outputs() {
  [ -n "${GITHUB_OUTPUT:-}" ] || return 0
  {
    printf 'profile=%s\n' "$profile"
    printf 'effort=%s\n' "$effort"
    printf 'reason=%s\n' "$reason"
    printf 'file_count=%s\n' "$file_count"
    printf 'changed_lines=%s\n' "$changed_lines"
  } >>"$GITHUB_OUTPUT"
}

finish() {
  emit_outputs
  printf 'PR review profile: %s (Opus/%s; reason=%s; files=%s; changed_lines=%s)\n' \
    "$profile" "$effort" "$reason" "$file_count" "$changed_lines"
}

fail_closed() {
  profile=full
  effort=xhigh
  reason=classifier-error
  finish
  return 1
}

mark_full() {
  # classifier-error is terminal: never downgrade its reason to a milder one.
  [ "$profile" = full ] && [ "$reason" = classifier-error ] && return 0
  profile=full
  effort=xhigh
  reason=$1
}

# Paths that can break a pack invariant the review prompt checks, or that carry
# the review/build machinery itself. Any of these forces the full profile.
is_invariant_path() {
  local path=$1
  case "$path" in
    # Version lockstep surfaces + pack manifests.
    .claude-plugin/*|evals/skill-sets.yaml|README.md|AGENTS.md|CLAUDE.md)
      return 0
      ;;
    # A SKILL.md carries frontmatter (name, description, allowed-tools,
    # metadata.version) — every mechanical convention lives here.
    src/*/SKILL.md)
      return 0
      ;;
    # Review, validation, packaging, and release machinery.
    .github/*|scripts/*|build-skills.sh|.gitmodules)
      return 0
      ;;
    # Eval harness logic and benchmark bookkeeping (CI runs --check on these).
    evals/*.py|evals/benchmarks/README.md|evals/benchmarks/entries/*)
      return 0
      ;;
  esac
  return 1
}

# Paths whose worst case is a prose defect: no invariant, no machinery. Anything
# not matched here is unknown and fails closed to full.
is_low_stakes_path() {
  local path=$1
  case "$path" in
    src/*/reference/*|src/*/mapper/*|src/*/scripts/*|src/*/templates/*|src/*/assets/*)
      return 0
      ;;
    docs/*|examples/*|example-input/*|example-output/*|.gitignore)
      return 0
      ;;
    evals/*)
      # evals/*.py and the benchmark index are caught by is_invariant_path first;
      # what reaches here is scenario data, fixtures, and prose.
      return 0
      ;;
  esac
  return 1
}

if [ -z "$base_sha" ] || [ -z "$head_sha" ]; then
  fail_closed
  exit 1
fi

if ! git rev-parse --verify --quiet "${base_sha}^{commit}" >/dev/null ||
  ! git rev-parse --verify --quiet "${head_sha}^{commit}" >/dev/null; then
  fail_closed
  exit 1
fi

if ! git merge-base "$base_sha" "$head_sha" >/dev/null; then
  fail_closed
  exit 1
fi

temp_dir=$(mktemp -d)
trap 'rm -rf "$temp_dir"' EXIT
names_file="$temp_dir/names"
numstat_file="$temp_dir/numstat"

if ! git diff --name-status -z "$base_sha...$head_sha" >"$names_file"; then
  fail_closed
  exit 1
fi
if ! git diff --numstat -z "$base_sha...$head_sha" >"$numstat_file"; then
  fail_closed
  exit 1
fi

# Diff collection succeeded, so start from compact and promote only on an
# explicit signal below. Any later parse failure still fails closed.
profile=compact
effort=high
reason=prose-only-change

seen_src_dirs=' '
classify_path() {
  local path=$1
  if is_invariant_path "$path"; then
    mark_full invariant-path
  elif ! is_low_stakes_path "$path"; then
    mark_full unknown-path
  fi

  # A brand-new skill directory must be added to current_pack and the README
  # table in the same PR. Adding a file under a src/ directory that does not
  # exist at the base revision is exactly that case.
  case "$path" in
    src/*/*)
      local skill_dir=${path#src/}
      skill_dir=src/${skill_dir%%/*}
      if [[ "$seen_src_dirs" != *" $skill_dir "* ]]; then
        seen_src_dirs+="$skill_dir "
        if ! git rev-parse --verify --quiet "$base_sha:$skill_dir" >/dev/null; then
          mark_full new-skill-directory
        fi
      fi
      ;;
  esac
}

while IFS= read -r -d '' record; do
  path=
  old_path=
  case "$record" in
    R[0-9][0-9][0-9]|C[0-9][0-9][0-9])
      IFS= read -r -d '' old_path || { fail_closed; exit 1; }
      IFS= read -r -d '' path || { fail_closed; exit 1; }
      ;;
    A|D|M|T|U|X|B)
      IFS= read -r -d '' path || { fail_closed; exit 1; }
      ;;
    *$'\t'*)
      status=${record%%$'\t'*}
      path=${record#*$'\t'}
      case "$status" in
        A|D|M|T|U|X|B) ;;
        R[0-9][0-9][0-9]|C[0-9][0-9][0-9])
          old_path=$path
          IFS= read -r -d '' path || { fail_closed; exit 1; }
          ;;
        *)
          fail_closed
          exit 1
          ;;
      esac
      ;;
    *)
      fail_closed
      exit 1
      ;;
  esac

  file_count=$((file_count + 1))
  # A rename out of src/<skill>/ can break pack completeness, so classify both
  # sides of the move.
  if [ -n "$old_path" ]; then
    classify_path "$old_path"
  fi
  classify_path "$path"
done <"$names_file"

while IFS= read -r -d '' record; do
  case "$record" in
    *$'\t'*$'\t'*)
      additions=${record%%$'\t'*}
      remainder=${record#*$'\t'}
      deletions=${remainder%%$'\t'*}
      path_fragment=${remainder#*$'\t'}
      ;;
    *)
      fail_closed
      exit 1
      ;;
  esac

  # Renames/copies emit an empty path fragment followed by old and new paths.
  if [ -z "$path_fragment" ]; then
    IFS= read -r -d '' _old_path || { fail_closed; exit 1; }
    IFS= read -r -d '' _new_path || { fail_closed; exit 1; }
  fi

  if [ "$additions" = '-' ] || [ "$deletions" = '-' ]; then
    mark_full binary-change
    continue
  fi
  case "$additions:$deletions" in
    *[!0-9:]*|:*)
      fail_closed
      exit 1
      ;;
  esac
  changed_lines=$((changed_lines + 10#$additions + 10#$deletions))
done <"$numstat_file"

if [ "$force_full" = true ]; then
  mark_full high-stakes-label
fi
if [ "$file_count" -gt 15 ]; then
  mark_full large-file-count
fi
if [ "$changed_lines" -gt 500 ]; then
  mark_full large-diff
fi

finish
