#!/usr/bin/env python3
"""Validate the customer-facing shape of the Nexty skill pack."""

from __future__ import annotations

import argparse
import json
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
MARKDOWN_LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)\s]+)")


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
        / "nxd-build-data-product"
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
        errors.extend(_scenario_skill_errors(root, public_scenarios))

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


def _scenario_skill_errors(root: Path, public_scenarios: Path) -> list[str]:
    """Check every scenario declares the skills it exercises.

    CI selects which scenarios a PR runs by inverting this mapping (see
    ``evals/affected_scenarios.py``). A scenario missing `skills` is never
    selected by any code change, so it silently stops guarding its skill —
    which looks identical to "the skill has no regressions". Validating the
    field here makes that failure loud at authoring time instead.
    """
    errors: list[str] = []
    for checks_file in sorted(public_scenarios.glob("*/checks.json")):
        try:
            data = json.loads(checks_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"{checks_file}: invalid JSON: {exc}")
            continue

        skills = data.get("skills")
        if skills is None:
            errors.append(
                f"{checks_file}: missing `skills` list naming the skills this "
                f"scenario exercises (CI uses it to select affected scenarios)"
            )
            continue
        if not isinstance(skills, list) or not skills:
            errors.append(f"{checks_file}: `skills` must be a non-empty list")
            continue
        for skill in skills:
            if not isinstance(skill, str):
                errors.append(f"{checks_file}: `skills` entries must be strings")
            elif not (root / "src" / skill).is_dir():
                errors.append(
                    f"{checks_file}: `skills` names a skill that does not exist: "
                    f"src/{skill}"
                )
    return errors


def _current_pack_skills(skill_sets_text: str) -> list[str] | None:
    """Return the list of `src/<skill>` entries under the `current_pack:` key.

    Returns None if the key is absent. Hand-rolled (no pyyaml): walks lines,
    tracks the active top-level skill-set name, and collects `- "src/..."` items
    only while inside `current_pack:`'s `skills:` block.
    """
    pack: list[str] | None = None
    in_current = False
    for line in skill_sets_text.splitlines():
        set_header = re.match(r"^  ([a-zA-Z0-9_]+):\s*$", line)
        if set_header:
            in_current = set_header.group(1) == "current_pack"
            if in_current and pack is None:
                pack = []
            continue
        if in_current:
            item = re.match(r'\s+-\s+"?(src/[^"\s]+)"?\s*$', line)
            if item:
                pack = pack or []
                pack.append(item.group(1))
    return pack


def _skill_set_skills(skill_sets_text: str, set_name: str) -> list[str] | None:
    """Return the ``src/<skill>`` entries in one named skill set."""
    skills: list[str] | None = None
    active = False
    in_skills = False
    for line in skill_sets_text.splitlines():
        set_header = re.match(r"^  ([a-zA-Z0-9_]+):\s*$", line)
        if set_header:
            active = set_header.group(1) == set_name
            in_skills = False
            if active:
                skills = []
            continue
        if not active:
            continue
        if re.match(r"^    skills:\s*$", line):
            in_skills = True
            continue
        if re.match(r"^    \S[^:]*:", line):
            in_skills = False
            continue
        if in_skills:
            item = re.match(r'\s+-\s+"?(src/[^"\s]+)"?\s*$', line)
            if item and skills is not None:
                skills.append(item.group(1))
    return skills


def validate_pack_completeness(root: Path) -> list[str]:
    """Every directory under src/ must be in current_pack and the README table."""
    errors: list[str] = []
    src = root / "src"
    if not src.is_dir():
        return errors
    skill_names = [p.name for p in _skill_dirs(src)]

    skill_sets = root / "evals" / "skill-sets.yaml"
    if skill_sets.exists():
        pack = _current_pack_skills(skill_sets.read_text(encoding="utf-8"))
        if pack is None:
            errors.append(f"{skill_sets}: current_pack skill set is missing")
        else:
            listed = {p.split("/", 1)[1] for p in pack if "/" in p}
            for name in skill_names:
                if name not in listed:
                    errors.append(
                        f"{skill_sets}: skill {name!r} exists under src/ but is not in "
                        f"current_pack (the shipped pack must list every skill)"
                    )

    readme = root / "README.md"
    if readme.exists():
        readme_text = readme.read_text(encoding="utf-8")
        for name in skill_names:
            # Skills appear in the Available Skills table as `\`<name>\``.
            if f"`{name}`" not in readme_text:
                errors.append(
                    f"README.md: skill {name!r} is missing from the Available Skills table"
                )
    return errors


def validate_marketplace_skill_bundles(root: Path) -> list[str]:
    """Validate the named marketplace projections against ``src/``.

    The marketplace intentionally keeps the two customer-facing bundles as
    skill-bundle plugins backed by the canonical ``src/`` tree. This prevents
    copied plugin trees from drifting while allowing shared foundation skills
    to appear in both experiences.
    """
    errors: list[str] = []
    market_path = root / ".claude-plugin" / "marketplace.json"
    if not market_path.exists():
        return [f"{market_path}: missing marketplace manifest"]
    try:
        market = json.loads(market_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"{market_path}: invalid JSON ({exc})"]

    plugins = market.get("plugins", [])
    if not isinstance(plugins, list):
        return [f"{market_path}: plugins must be a list"]
    by_name = {
        plugin.get("name"): plugin
        for plugin in plugins
        if isinstance(plugin, dict) and isinstance(plugin.get("name"), str)
    }
    src = root / "src"
    source_names = {path.name for path in _skill_dirs(src)} if src.is_dir() else set()
    named_sets: dict[str, set[str]] = {}

    for plugin_name in ("nexty-desktop", "nexty-datamesh"):
        plugin = by_name.get(plugin_name)
        if plugin is None:
            errors.append(f"{market_path}: missing {plugin_name!r} plugin entry")
            continue
        if plugin.get("source") != "./src":
            errors.append(
                f"{market_path}: {plugin_name!r} must use source './src'"
            )
        if plugin.get("strict") is not False:
            errors.append(
                f"{market_path}: {plugin_name!r} must set strict to false"
            )
        skills = plugin.get("skills")
        if not isinstance(skills, list) or not skills:
            errors.append(f"{market_path}: {plugin_name!r} must list skills")
            continue
        names: set[str] = set()
        for skill_ref in skills:
            if not isinstance(skill_ref, str) or not skill_ref.startswith("./"):
                errors.append(
                    f"{market_path}: {plugin_name!r} has invalid skill path {skill_ref!r}"
                )
                continue
            skill_name = skill_ref[2:]
            if not skill_name or "/" in skill_name or skill_name in names:
                errors.append(
                    f"{market_path}: {plugin_name!r} has duplicate or invalid skill path "
                    f"{skill_ref!r}"
                )
                continue
            names.add(skill_name)
            if skill_name not in source_names:
                errors.append(
                    f"{market_path}: {plugin_name!r} references missing skill src/{skill_name}"
                )
        named_sets[plugin_name] = names

    if len(named_sets) == 2:
        union = named_sets["nexty-desktop"] | named_sets["nexty-datamesh"]
        missing = sorted(source_names - union)
        extra = sorted(union - source_names)
        if missing:
            errors.append(
                f"{market_path}: named plugin sets omit source skills: {', '.join(missing)}"
            )
        if extra:
            errors.append(
                f"{market_path}: named plugin sets reference unknown skills: {', '.join(extra)}"
            )
    return errors


def validate_named_skill_set_alignment(root: Path) -> list[str]:
    """Keep named eval packs exactly aligned with marketplace projections."""
    errors: list[str] = []
    skill_sets_path = root / "evals" / "skill-sets.yaml"
    if not skill_sets_path.exists():
        return errors
    marketplace_sets = _marketplace_skill_sets(root)
    skill_sets_text = skill_sets_path.read_text(encoding="utf-8")
    mappings = {
        "nexty-desktop": "nexty_desktop",
        "nexty-datamesh": "nexty_datamesh",
    }
    for plugin_name, set_name in mappings.items():
        marketplace_names = marketplace_sets.get(plugin_name)
        eval_paths = _skill_set_skills(skill_sets_text, set_name)
        if marketplace_names is None:
            continue
        if eval_paths is None:
            errors.append(
                f"{skill_sets_path}: missing named skill set {set_name!r} "
                f"for marketplace plugin {plugin_name!r}"
            )
            continue
        eval_names = [path.split("/", 1)[1] for path in eval_paths if "/" in path]
        if len(eval_names) != len(set(eval_names)):
            errors.append(f"{skill_sets_path}: {set_name} contains duplicate skills")
        if set(eval_names) != marketplace_names:
            missing = sorted(marketplace_names - set(eval_names))
            extra = sorted(set(eval_names) - marketplace_names)
            details = []
            if missing:
                details.append(f"missing {', '.join(missing)}")
            if extra:
                details.append(f"extra {', '.join(extra)}")
            errors.append(
                f"{skill_sets_path}: {set_name} does not match {plugin_name} "
                f"marketplace membership ({'; '.join(details)})"
            )
    return errors


def _markdown_link_target(raw_target: str) -> str | None:
    """Return a local relative Markdown target, excluding web and anchor links."""
    target = raw_target.strip()
    if target.startswith("<") and target.endswith(">"):  # pragma: no cover - regex excludes spaces
        target = target[1:-1]
    target = target.split("#", 1)[0].split("?", 1)[0]
    if not target or target.startswith(("/", "#")):
        return None
    if "://" in target or target.startswith(("mailto:", "data:")):
        return None
    return target


def _marketplace_skill_sets(root: Path) -> dict[str, set[str]]:
    market_path = root / ".claude-plugin" / "marketplace.json"
    if not market_path.exists():
        return {}
    try:
        plugins = json.loads(market_path.read_text(encoding="utf-8")).get("plugins", [])
    except (OSError, json.JSONDecodeError):
        return {}
    result: dict[str, set[str]] = {}
    for plugin in plugins:
        if not isinstance(plugin, dict):
            continue
        name = plugin.get("name")
        skills = plugin.get("skills")
        if name not in {"nexty-desktop", "nexty-datamesh"} or not isinstance(skills, list):
            continue
        result[name] = {
            skill[2:]
            for skill in skills
            if isinstance(skill, str) and skill.startswith("./") and "/" not in skill[2:]
        }
    return result


def validate_bundle_reference_closure(root: Path) -> list[str]:
    """Ensure relative skill/reference links stay inside each named bundle.

    A relative link into another ``src/<skill>`` directory is a hard package
    dependency. Plain prose may describe an optional handoff and is therefore
    intentionally not treated as a dependency by this check.
    """
    errors: list[str] = []
    src = root / "src"
    if not src.is_dir():
        return errors
    source_names = {path.name for path in _skill_dirs(src)}
    skill_sets_path = root / "evals" / "skill-sets.yaml"
    if not skill_sets_path.exists():
        return errors
    marketplace_sets = _marketplace_skill_sets(root)
    for plugin_name, bundle in marketplace_sets.items():
        bundle_names = bundle
        for skill_name in sorted(bundle_names):
            skill_dir = src / skill_name
            if not skill_dir.is_dir():
                continue
            for document in sorted(skill_dir.rglob("*.md")):
                # build-skills.sh deliberately prunes this submodule's
                # housekeeping docs from Desktop archives; they are not part
                # of the shipped reference closure to validate here.
                if "nextdata-public-examples" in document.parts:
                    continue
                text = document.read_text(encoding="utf-8")
                for match in MARKDOWN_LINK_RE.finditer(text):
                    target = _markdown_link_target(match.group(1))
                    if target is None:
                        continue
                    candidate = (document.parent / target).resolve()
                    try:
                        relative = candidate.relative_to(src.resolve())
                    except ValueError:
                        errors.append(
                            f"{document}: relative link {target!r} points outside the "
                            "source skill pack and is not a packaged source member"
                        )
                        continue
                    if not relative.parts:
                        errors.append(
                            f"{document}: relative link {target!r} points to the "
                            "source root, not a packaged source member"
                        )
                        continue
                    referenced_skill = relative.parts[0]
                    if referenced_skill not in source_names:
                        errors.append(
                            f"{document}: relative link {target!r} points to missing "
                            f"source skill src/{referenced_skill}"
                        )
                    elif referenced_skill not in bundle_names:
                        errors.append(
                            f"{document}: relative link {target!r} crosses the "
                            f"{plugin_name} bundle to src/{referenced_skill}; "
                            "add the skill to the bundle or make the handoff non-relative"
                        )
                    elif not candidate.exists():
                        errors.append(
                            f"{document}: relative link {target!r} is dangling in "
                            f"the {plugin_name} bundle"
                        )
    return errors


def validate_version_consistency(root: Path) -> list[str]:
    """plugin.json, marketplace.json, and every SKILL.md metadata.version agree."""
    errors: list[str] = []
    plugin_path = root / ".claude-plugin" / "plugin.json"
    if not plugin_path.exists():
        return [f"{plugin_path}: missing plugin manifest"]
    try:
        plugin_version = json.loads(plugin_path.read_text(encoding="utf-8"))["version"]
    except (json.JSONDecodeError, KeyError) as exc:
        return [f"{plugin_path}: cannot read version ({exc})"]

    market_path = root / ".claude-plugin" / "marketplace.json"
    if market_path.exists():
        try:
            market = json.loads(market_path.read_text(encoding="utf-8"))
            for plugin in market.get("plugins", []):
                mv = plugin.get("version")
                if mv != plugin_version:
                    errors.append(
                        f"{market_path}: plugin {plugin.get('name')!r} version {mv!r} "
                        f"does not match plugin.json {plugin_version!r}"
                    )
        except json.JSONDecodeError as exc:
            errors.append(f"{market_path}: invalid JSON ({exc})")

    src = root / "src"
    if src.is_dir():
        for skill_dir in _skill_dirs(src):
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                continue
            try:
                version = _frontmatter(skill_md).get("metadata.version", "")
            except ValueError:
                continue  # frontmatter shape errors are reported by validate_skill
            if version and version != plugin_version:
                errors.append(
                    f"{skill_md}: metadata.version {version!r} does not match plugin "
                    f"version {plugin_version!r} (skill versions are kept in lockstep)"
                )
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
    errors.extend(validate_pack_completeness(root))
    errors.extend(validate_marketplace_skill_bundles(root))
    errors.extend(validate_named_skill_set_alignment(root))
    errors.extend(validate_bundle_reference_closure(root))
    errors.extend(validate_version_consistency(root))

    if errors:
        print("Skill validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print("Skill validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
