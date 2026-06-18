#!/usr/bin/env python3
"""Validate the customer-facing shape of the Nexty skill pack."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
TAG_RE = re.compile(r"<[^>\n]+>")
USE_WHEN_RE = re.compile(r"\buse when\b", re.IGNORECASE)
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
MAX_DESCRIPTION_CHARS = 1024
REFERENCE_TOC_LINE_THRESHOLD = 100
REFERENCE_TOC_SCAN_LINES = 20

# Canonical Claude Code tool names a skill may list under `allowed-tools`.
# Keep in sync with the harness tool set; entries are case-sensitive.
KNOWN_TOOLS = frozenset(
    {
        "Bash",
        "Read",
        "Write",
        "Edit",
        "MultiEdit",
        "Glob",
        "Grep",
        "AskUserQuestion",
        "Agent",
        "Task",
        "TodoWrite",
        "WebFetch",
        "WebSearch",
        "NotebookEdit",
    }
)

# Canonical spelling for a skill's reference directory. The other spelling
# (`references/`) is rejected so the pack stays consistent.
CANONICAL_REFERENCE_DIR = "reference"


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _frontmatter(skill_md: Path) -> dict[str, object]:
    """Parse SKILL.md frontmatter into a flat mapping.

    Returns scalar top-level keys as strings, the `allowed-tools` block as a
    list of tool names under key ``"allowed-tools"``, and a nested
    ``metadata: version:`` value under key ``"metadata.version"``. This is a
    deliberately small hand-rolled parser (no pyyaml dependency); it handles
    only the shapes the skill pack actually uses.
    """
    text = skill_md.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError("SKILL.md must start with YAML frontmatter")
    try:
        block = text.split("---\n", 2)[1]
    except IndexError as exc:
        raise ValueError("SKILL.md frontmatter is not closed") from exc

    fields: dict[str, object] = {}
    current_list: str | None = None  # top-level key whose list items we're collecting
    current_map: str | None = None  # top-level mapping key (e.g. `metadata`) we're nested under
    for line in block.splitlines():
        if not line.strip():
            continue
        list_item = re.match(r"^[ \t]+-[ \t]+(.*\S)\s*$", line)
        if list_item and current_list is not None:
            fields.setdefault(current_list, []).append(_strip_quotes(list_item.group(1)))
            continue
        nested = re.match(r"^[ \t]+(\S[^:]*?):[ \t]*(.*)$", line)
        if nested and current_map is not None:
            fields[f"{current_map}.{nested.group(1).strip()}"] = _strip_quotes(nested.group(2))
            continue
        if line.startswith((" ", "\t", "-")) or ":" not in line:
            continue
        # A top-level key resets any list/map context.
        current_list = current_map = None
        key, value = line.split(":", 1)
        key = key.strip()
        if not value.strip():
            # Bare `key:` opens either a list (next lines are `- item`) or a
            # mapping (next lines are indented `subkey: value`).
            current_list = key
            current_map = key
            continue
        fields[key] = _strip_quotes(value)
    return fields


def _skill_dirs(src: Path) -> list[Path]:
    return sorted(p for p in src.iterdir() if p.is_dir())


def validate_skill(skill_dir: Path, max_lines: int) -> list[str]:
    errors: list[str] = []
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return [f"{skill_dir}: missing SKILL.md"]

    try:
        fields = _frontmatter(skill_md)
    except ValueError as exc:
        return [f"{skill_md}: {exc}"]

    name = fields.get("name", "")
    description = fields.get("description", "")
    allowed_tools = fields.get("allowed-tools", [])
    version = fields.get("metadata.version", "")

    if name != skill_dir.name:
        errors.append(f"{skill_md}: name {name!r} must match directory {skill_dir.name!r}")
    if not NAME_RE.fullmatch(name):
        errors.append(f"{skill_md}: invalid skill name {name!r}")
    if not description:
        errors.append(f"{skill_md}: missing description")
    elif len(description) > MAX_DESCRIPTION_CHARS:
        errors.append(
            f"{skill_md}: description has {len(description)} chars; "
            f"maximum is {MAX_DESCRIPTION_CHARS}"
        )
    elif not USE_WHEN_RE.search(description):
        errors.append(f"{skill_md}: description should include a 'Use when ...' trigger clause")
    if TAG_RE.search(description):
        errors.append(f"{skill_md}: description must not contain angle-bracket placeholders")

    if not allowed_tools:
        errors.append(f"{skill_md}: allowed-tools is missing or empty")
    else:
        unknown = [t for t in allowed_tools if t not in KNOWN_TOOLS]
        if unknown:
            errors.append(
                f"{skill_md}: unknown allowed-tools entr"
                f"{'y' if len(unknown) == 1 else 'ies'}: {', '.join(sorted(unknown))}"
            )

    if version and not SEMVER_RE.fullmatch(version):
        errors.append(f"{skill_md}: metadata.version {version!r} is not semver (X.Y.Z)")

    line_count = sum(1 for _ in skill_md.open(encoding="utf-8"))
    if line_count > max_lines:
        errors.append(f"{skill_md}: {line_count} lines exceeds {max_lines}")

    return errors


def validate_reference_dirs(root: Path) -> list[str]:
    errors: list[str] = []
    src = root / "src"
    if not src.is_dir():
        return errors
    for skill_dir in _skill_dirs(src):
        stray = skill_dir / "references"
        if stray.is_dir():
            errors.append(
                f"{stray}: use '{CANONICAL_REFERENCE_DIR}/' (singular), not 'references/'"
            )
    return errors


def validate_reference_tocs(root: Path) -> list[str]:
    errors: list[str] = []
    src = root / "src"
    reference_files = [
        *src.glob("*/reference/*.md"),
        *src.glob("*/references/*.md"),
    ]
    for reference_file in sorted(reference_files):
        if "nextdata-public-examples" in reference_file.parts:
            continue
        lines = reference_file.read_text(encoding="utf-8").splitlines()
        if len(lines) <= REFERENCE_TOC_LINE_THRESHOLD:
            continue
        preview = "\n".join(lines[:REFERENCE_TOC_SCAN_LINES])
        if "Contents" not in preview and "Table of Contents" not in preview:
            errors.append(
                f"{reference_file}: {len(lines)} lines; add a top-level Contents section "
                f"in the first {REFERENCE_TOC_SCAN_LINES} lines"
            )
    return errors


def validate_submodules(root: Path) -> list[str]:
    examples = (
        root
        / "src"
        / "nxd-data-product-builder"
        / "reference"
        / "nextdata-public-examples"
        / "data_products"
    )
    if not examples.is_dir():
        return [
            "nextdata-public-examples submodule is missing or uninitialized; "
            "run git submodule update --init --recursive"
        ]
    data_products = [p for p in examples.iterdir() if p.is_dir()]
    if not data_products:
        return ["nextdata-public-examples/data_products contains no examples"]
    return []


def validate_evals(root: Path) -> list[str]:
    skill_sets = root / "evals" / "skill-sets.yaml"
    if not skill_sets.exists():
        return ["evals/skill-sets.yaml is missing"]

    errors: list[str] = []
    for line_number, line in enumerate(skill_sets.read_text(encoding="utf-8").splitlines(), 1):
        match = re.match(r'\s+-\s+"?(src/[^"]+)"?\s*$', line)
        if not match:
            continue
        path = root / match.group(1)
        if not path.is_dir():
            errors.append(f"{skill_sets}:{line_number}: referenced skill path does not exist: {match.group(1)}")

    public_scenarios = root / "evals" / "public"
    if not public_scenarios.is_dir():
        errors.append("evals/public directory is missing")
    else:
        scenario_prompts = sorted(public_scenarios.glob("*/prompt.md"))
        if not scenario_prompts:
            errors.append("evals/public contains no prompt.md files")

    templates = root / "evals" / "templates"
    if not templates.is_dir():
        errors.append("evals/templates directory is missing")
    elif not sorted(templates.glob("*/prompt.md")):
        errors.append("evals/templates contains no prompt.md files")

    committed_private_prompts = sorted((root / "evals" / "private").glob("**/prompt.md"))
    if committed_private_prompts:
        for prompt in committed_private_prompts:
            errors.append(f"{prompt}: private eval prompts must not be committed")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--max-lines", type=int, default=500)
    parser.add_argument(
        "--skip-submodule-check",
        action="store_true",
        help="Skip validation that public example submodules are initialized",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    src = root / "src"
    errors: list[str] = []

    if not src.is_dir():
        errors.append(f"{src}: missing src directory")
    else:
        skills = _skill_dirs(src)
        if not skills:
            errors.append(f"{src}: no skill directories found")
        for skill_dir in skills:
            errors.extend(validate_skill(skill_dir, args.max_lines))

    if not args.skip_submodule_check:
        errors.extend(validate_submodules(root))
    errors.extend(validate_reference_dirs(root))
    errors.extend(validate_reference_tocs(root))
    errors.extend(validate_evals(root))

    if errors:
        print("Skill validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print("Skill validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
