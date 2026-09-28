#!/usr/bin/env python3
"""Claude PreToolUse write boundary for the NEX-890 private runner session.

This script deliberately uses only the standard library so the runner can copy
it into a private per-run directory and invoke it with ``python3 -I``. It is a
policy hook, never an evidence source; the runner independently hashes the copy
and validates its own MCP/Claude streams.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import unicodedata
from pathlib import Path
from typing import Any


_PATH_READS = {"read", "glob", "grep", "notebookread"}
_NON_FILESYSTEM_TOOLS = {"skill", "task", "agent", "toolsearch", "todowrite"}
_MUTATORS = {"write", "edit", "multiedit", "notebookedit"}
_SHELL = {"bash", "bashoutput", "killshell", "monitor", "powershell"}
_PATH_KEYS = {
    "file_path", "path", "notebook_path", "notebookPath", "filename",
    "file", "target_path", "targetPath",
}

# Fixed denial reasons. The runner's preflight matches these exact strings in
# direct probes and in Claude tool results, so each must stay distinct and
# never be a substring of another.
REASON_INVALID_EVENT = "NEX-890 policy hook received an invalid event"
REASON_AMBIGUOUS_EVENT = "NEX-890 policy hook received an ambiguous tool event"
REASON_SHELL = "shell tools are disabled for NEX-890"
REASON_GLOB_OUTSIDE = "Glob pattern must stay inside the workspace"
REASON_READ_AMBIGUOUS = "read tool omitted or ambiguously specified its target path"
REASON_HOME_RELATIVE = "home-relative paths are not allowed"
REASON_READ_PROTECTED = "read target is in a protected runner path"
REASON_READ_OUTSIDE = "read target is outside the NEX-890 workspace and skill pack"
REASON_READ_CONFIG = "read target is protected Claude or MCP configuration"
REASON_UNKNOWN_TOOL = "unknown NEX-890 tool is denied by the write policy"
REASON_WRITE_AMBIGUOUS = "mutating tool omitted or ambiguously specified its target path"
REASON_WRITE_OUTSIDE = "write target is outside the NEX-890 workspace"
REASON_WRITE_PROTECTED = "write target is in a protected runner path"
REASON_WRITE_CLAUDE = "write target is in protected .claude state"
REASON_WRITE_MCP = "write target is a protected MCP configuration"
REASON_FAILED_CLOSED = "NEX-890 policy hook failed closed"
ALL_REASONS = (
    REASON_INVALID_EVENT, REASON_AMBIGUOUS_EVENT, REASON_SHELL,
    REASON_GLOB_OUTSIDE, REASON_READ_AMBIGUOUS, REASON_HOME_RELATIVE,
    REASON_READ_PROTECTED, REASON_READ_OUTSIDE, REASON_READ_CONFIG,
    REASON_UNKNOWN_TOOL, REASON_WRITE_AMBIGUOUS, REASON_WRITE_OUTSIDE,
    REASON_WRITE_PROTECTED, REASON_WRITE_CLAUDE, REASON_WRITE_MCP,
    REASON_FAILED_CLOSED,
)


def _canonical(path: Path) -> str:
    """Resolve symlinked prefixes even when the leaf does not yet exist.

    The resolved spelling keeps its case: whether two spellings name the same
    directory is a property of the filesystem, which ``_inside`` asks directly.
    """
    absolute = Path(os.path.abspath(os.fspath(path)))
    tail: list[str] = []
    cursor = absolute
    while not cursor.exists() and not cursor.is_symlink():
        parent = cursor.parent
        if parent == cursor:
            break
        tail.append(cursor.name)
        cursor = parent
    resolved = cursor.resolve(strict=True)
    for part in reversed(tail):
        resolved = resolved / part
    value = os.path.normpath(os.fspath(resolved))
    # macOS commonly exposes /tmp and /var through /private aliases. Resolve
    # these lexically too, including paths whose final components are missing,
    # but only where the host really aliases them (never on Linux).
    for prefix in ("/tmp/", "/var/"):
        if value.startswith(prefix) and _private_alias(prefix):
            value = "/private" + value
            break
    return value


def _private_alias(prefix: str) -> bool:
    """Whether ``prefix`` (``/tmp/`` or ``/var/``) resolves under ``/private``."""
    top = prefix.rstrip("/")
    return os.path.realpath(top) == "/private" + top


def _existing_ancestor(path: str) -> str:
    cursor = path
    while not os.path.lexists(cursor):
        parent = os.path.dirname(cursor)
        if parent == cursor:
            break
        cursor = parent
    return cursor


def _fold_equal(left: str, right: str) -> bool:
    """Compare one path component ignoring ASCII case only.

    Every case-insensitive filesystem folds ASCII letters; wider Unicode
    folding (``"ß"`` against ``"SS"``) differs between filesystems, so it never
    counts as a match.
    """
    return len(left) == len(right) and all(
        a == b or (a.isascii() and b.isascii() and a.lower() == b.lower())
        for a, b in zip(left, right)
    )


def _folds_case(root: str) -> bool:
    """Whether the filesystem holding ``root``'s nearest existing ancestor folds case.

    The only evidence is ``samefile`` on an ASCII case-swapped spelling of that
    directory, looked up in a parent on the same device (a mount point's name
    lives on the filesystem above it). No letter to swap, a symlinked alias, a
    mount boundary, or any error reads as case-sensitive.
    """
    directory = _existing_ancestor(root)
    parent, name = os.path.split(directory)
    alias_name = "".join(c.swapcase() if c.isascii() else c for c in name)
    if not parent or alias_name == name:
        return False
    alias = os.path.join(parent, alias_name)
    try:
        if os.stat(parent).st_dev != os.stat(directory).st_dev:
            return False
        return (
            os.path.isdir(directory)
            and not os.path.islink(alias)
            and os.path.samefile(alias, directory)
        )
    except OSError:
        return False


def _inside(path: str, root: str) -> bool:
    try:
        if os.path.commonpath((path, root)) == root:
            return True
    except ValueError:
        return False
    # A case-insensitive filesystem can reach the root through a case-variant
    # spelling, including a root that does not exist yet. Accept a variant only
    # when the filesystem proves it; a matching case fold alone is never evidence.
    root_parts = Path(root).parts
    path_parts = Path(path).parts
    if len(path_parts) < len(root_parts) or not all(
        _fold_equal(a, b) for a, b in zip(path_parts, root_parts)
    ):
        return False
    prefix = os.path.join(*path_parts[: len(root_parts)])
    variant_anchor = _existing_ancestor(prefix)
    root_anchor = _existing_ancestor(root)
    # Both spellings must exist to the same depth and meet at one directory
    # (same st_dev and st_ino), so no mount boundary separates them.
    anchor_depth = len(Path(root_anchor).parts)
    if len(Path(variant_anchor).parts) != anchor_depth:
        return False
    try:
        if not os.path.samestat(os.stat(variant_anchor), os.stat(root_anchor)):
            return False
    except OSError:
        return False
    # An existing root is settled by that identity. Otherwise the missing
    # components will be created inside root_anchor, whose filesystem must
    # prove it folds case before the variant names count as the same.
    return anchor_depth == len(root_parts) or _folds_case(root)


def _block_key(part: str) -> str:
    """Canonical caseless key for one component; used only to deny, never to allow."""
    return unicodedata.normalize(
        "NFD", unicodedata.normalize("NFD", part).casefold()
    )


def _inside_protected(path: str, root: str) -> bool:
    """Whether ``path`` falls in protected ``root``, failing closed on case.

    Filesystem identity settles an existing root. A missing root gives no such
    evidence: the nearest existing ancestor need not share the case behavior of
    entries later created inside it (per-directory casefold), so any Unicode
    caseless match of the root's components counts as protected. That can deny
    a case-different sibling while the root is absent; it never grants access.
    """
    if _inside(path, root):
        return True
    if os.path.exists(root):
        return False
    root_parts = Path(root).parts
    path_parts = Path(path).parts
    return len(path_parts) >= len(root_parts) and all(
        _block_key(a) == _block_key(b) for a, b in zip(path_parts, root_parts)
    )


def _has_part(parts: tuple[str, ...], name: str) -> bool:
    return any(part.casefold() == name for part in parts)


def _paths(value: Any) -> list[str] | None:
    found: list[str] = []

    def walk(item: Any) -> bool:
        if isinstance(item, dict):
            for key, child in item.items():
                if key in _PATH_KEYS:
                    if not isinstance(child, str) or not child:
                        return False
                    found.append(child)
                elif isinstance(child, (dict, list)) and not walk(child):
                    return False
        elif isinstance(item, list):
            for child in item:
                if not walk(child):
                    return False
        return True

    if not walk(value) or not found:
        return None
    return found


def _block(reason: str) -> int:
    sys.stderr.write(reason[:500] + "\n")
    return 2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--private-root", required=True)
    parser.add_argument("--plugin-root", action="append", default=[])
    args = parser.parse_args()
    try:
        event = json.load(sys.stdin)
        if not isinstance(event, dict):
            return _block(REASON_INVALID_EVENT)
        tool = event.get("tool_name")
        inputs = event.get("tool_input")
        if not isinstance(tool, str) or not isinstance(inputs, dict):
            return _block(REASON_AMBIGUOUS_EVENT)
        name = tool.casefold()
        if name in _SHELL:
            return _block(REASON_SHELL)
        if tool.startswith("mcp__nxd-desktop__") or name in _NON_FILESYSTEM_TOOLS:
            return 0
        workspace = _canonical(Path(args.workspace))
        protected = [_canonical(Path(args.private_root))]
        plugin_roots = [_canonical(Path(item)) for item in args.plugin_root]
        if name in _PATH_READS:
            values = _paths(inputs)
            if name == "glob":
                pattern = inputs.get("pattern")
                if isinstance(pattern, str) and (
                    Path(pattern).is_absolute()
                    or pattern.startswith("~")
                    or ".." in Path(pattern).parts
                ):
                    return _block(REASON_GLOB_OUTSIDE)
            if values is None and name in {"glob", "grep"}:
                # Claude's default path for these tools is its workspace CWD.
                values = [args.workspace]
            if not values:
                return _block(REASON_READ_AMBIGUOUS)
            for raw in values:
                if raw.startswith("~"):
                    return _block(REASON_HOME_RELATIVE)
                target = Path(raw)
                if not target.is_absolute():
                    target = Path(args.workspace) / target
                canonical = _canonical(target)
                if any(_inside_protected(canonical, root) for root in protected):
                    return _block(REASON_READ_PROTECTED)
                if not (
                    _inside(canonical, workspace)
                    or any(_inside(canonical, root) for root in plugin_roots)
                ):
                    return _block(REASON_READ_OUTSIDE)
                parts = Path(canonical).parts
                if _has_part(parts, ".claude") or _has_part(parts, ".mcp.json"):
                    return _block(REASON_READ_CONFIG)
            return 0
        if name not in _MUTATORS:
            return _block(REASON_UNKNOWN_TOOL)
        values = _paths(inputs)
        if not values:
            return _block(REASON_WRITE_AMBIGUOUS)

        protected.extend(plugin_roots)
        for raw in values:
            if raw.startswith("~"):
                return _block(REASON_HOME_RELATIVE)
            target = Path(raw)
            if not target.is_absolute():
                target = Path(args.workspace) / target
            canonical = _canonical(target)
            if not _inside(canonical, workspace):
                return _block(REASON_WRITE_OUTSIDE)
            if any(_inside_protected(canonical, root) for root in protected):
                return _block(REASON_WRITE_PROTECTED)
            parts = Path(canonical).parts
            if _has_part(parts, ".claude"):
                return _block(REASON_WRITE_CLAUDE)
            if _has_part(parts, ".mcp.json"):
                return _block(REASON_WRITE_MCP)
        return 0
    except Exception:
        return _block(REASON_FAILED_CLOSED)


if __name__ == "__main__":
    raise SystemExit(main())
