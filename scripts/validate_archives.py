#!/usr/bin/env python3
"""Validate the named plugin archives produced by ``build-skills.sh``."""

from __future__ import annotations

import argparse
import json
import posixpath
import re
import sys
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile


MARKDOWN_LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)\s]+)")
NAMED_PLUGINS = {
    "nexty-desktop": "nexty-desktop",
    "nexty-datamesh": "nexty-datamesh",
    "nexty-agent-skills": "nexty-agent-skills",
}


def _marketplace_skills(root: Path, plugin_name: str) -> list[str]:
    path = root / ".claude-plugin" / "marketplace.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    entry = next(plugin for plugin in data["plugins"] if plugin.get("name") == plugin_name)
    return [skill[2:] for skill in entry["skills"]]


def _expected_skills(root: Path, plugin_name: str) -> list[str]:
    if plugin_name != "nexty-agent-skills":
        return sorted(_marketplace_skills(root, plugin_name))
    return sorted(path.name for path in (root / "src").iterdir() if path.is_dir())


def _local_target(raw_target: str) -> str | None:
    target = raw_target.strip()
    target = target.split("#", 1)[0].split("?", 1)[0]
    if not target or target.startswith(("/", "#")):
        return None
    if "://" in target or target.startswith(("mailto:", "data:")):
        return None
    return target


def _validate_archive(
    archive: Path, plugin_name: str, expected_skills: list[str], version: str
) -> list[str]:
    errors: list[str] = []
    if not archive.is_file():
        return [f"{archive}: archive is missing"]

    try:
        with ZipFile(archive) as zip_file:
            members = zip_file.infolist()
            names = [member.filename for member in members]
            name_set = set(names)
            if len(names) != len(name_set):
                errors.append(f"{archive}: archive contains duplicate members")
            bad_names = [
                name
                for name in names
                if name.startswith("/")
                or "\\" in name
                or ".." in PurePosixPath(name).parts
            ]
            if bad_names:
                errors.append(f"{archive}: unsafe archive member paths: {bad_names}")
            nested = [name for name in names if name.lower().endswith(".zip")]
            if nested:
                errors.append(f"{archive}: nested ZIP members are not allowed: {nested}")

            allowed = {
                name
                for name in names
                if name == ".claude-plugin/plugin.json" or name.startswith("skills/")
            }
            unexpected = sorted(name_set - allowed)
            if unexpected:
                errors.append(f"{archive}: unexpected top-level members: {unexpected}")

            manifest_name = ".claude-plugin/plugin.json"
            if manifest_name not in name_set:
                errors.append(f"{archive}: missing {manifest_name}")
            else:
                try:
                    manifest = json.loads(zip_file.read(manifest_name))
                except (UnicodeError, json.JSONDecodeError) as exc:
                    errors.append(f"{archive}: invalid plugin manifest: {exc}")
                    manifest = {}
                if manifest.get("name") != plugin_name:
                    errors.append(
                        f"{archive}: manifest name {manifest.get('name')!r} "
                        f"does not match {plugin_name!r}"
                    )
                if manifest.get("version") != version:
                    errors.append(
                        f"{archive}: manifest version {manifest.get('version')!r} "
                        f"does not match {version!r}"
                    )
                if "skills" in manifest:
                    errors.append(f"{archive}: Desktop plugin manifest must omit `skills`")

            shipped_skills = sorted(
                {
                    PurePosixPath(name).parts[1]
                    for name in names
                    if name.startswith("skills/") and len(PurePosixPath(name).parts) > 2
                }
            )
            expected = sorted(expected_skills)
            if shipped_skills != expected:
                errors.append(
                    f"{archive}: shipped skills {shipped_skills} do not match "
                    f"expected {expected}"
                )
            for skill in expected:
                skill_md = f"skills/{skill}/SKILL.md"
                if skill_md not in name_set:
                    errors.append(f"{archive}: missing packaged {skill_md}")

            # Validate relative links against the archive itself. This repeats
            # the source closure check at the release boundary, after pruning
            # and staging have transformed the filesystem into a ZIP.
            for name in names:
                if not name.endswith(".md") or not name.startswith("skills/"):
                    continue
                document = PurePosixPath(name)
                try:
                    text = zip_file.read(name).decode("utf-8")
                except (KeyError, UnicodeError) as exc:
                    errors.append(f"{archive}: cannot read {name}: {exc}")
                    continue
                for match in MARKDOWN_LINK_RE.finditer(text):
                    target = _local_target(match.group(1))
                    if target is None:
                        continue
                    candidate = posixpath.normpath(
                        posixpath.join(str(document.parent), target)
                    )
                    if not candidate.startswith("skills/"):
                        continue
                    parts = PurePosixPath(candidate).parts
                    if len(parts) < 2:
                        continue
                    referenced_skill = parts[1]
                    if referenced_skill not in expected:
                        errors.append(
                            f"{archive}: {name}: relative link {target!r} points to "
                            f"unshipped skill {referenced_skill!r}"
                        )
                    elif candidate not in name_set and not any(
                        name.startswith(candidate.rstrip("/") + "/") for name in name_set
                    ):
                        errors.append(
                            f"{archive}: {name}: relative link {target!r} is dangling"
                        )
    except (BadZipFile, OSError) as exc:
        errors.append(f"{archive}: unreadable ZIP: {exc}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    try:
        plugin_version = json.loads(
            (root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
        )["version"]
        expected = {
            name: _expected_skills(root, name) for name in NAMED_PLUGINS
        }
    except (KeyError, OSError, TypeError, json.JSONDecodeError, StopIteration) as exc:
        print(f"Archive validation failed: cannot read manifests: {exc}", file=sys.stderr)
        return 1

    errors: list[str] = []
    for stem, plugin_name in NAMED_PLUGINS.items():
        archive = root / "build" / f"{stem}-v{plugin_version}.zip"
        errors.extend(_validate_archive(archive, plugin_name, expected[plugin_name], plugin_version))
    if errors:
        print("Archive validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("Plugin archive validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
