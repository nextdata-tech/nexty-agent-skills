"""A script a skill tells the agent to run must survive installation.

Every install path copies ONLY `src/<skill>/` trees:

  * `scripts/install.sh --code`    -> `copy_skill_tree "$SRC_DIR/$s"`
  * `scripts/install.sh --desktop` -> `copy_skill_tree "$SRC_DIR/$s" "$cache/skills/$s"`
  * `build-skills.sh`              -> `cd "$skill_dir"; zip -qrD`
  * `.claude-plugin/plugin.json`   -> `"skills": "./src/"`

So a helper at the REPO ROOT `scripts/` ships to no install target. The pack
shipped `dp_diagnostics.py` and `validate_dp_spec.py` that way once: the agent
was told to run `lock write` and `record init`, the files were not on disk, and
self-check Phase C then hard-failed `closure.lock_missing` naming the same
missing script in its own remedy. Unit tests all passed, because they import
from the repo, not from an install.

The eval harness reproduces the same environment (it copies skill dirs into an
isolated workspace), so it cannot catch this either. Hence a plain pytest gate.

`self_check.py` is the deliberate exception and is asserted as such below: it is
copied INTO the closure and run from there, so it is delivered by the embedded
fence in `reference/self-check.md`, never by an installer.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src"

# Delivered by embedding in a reference doc, not by an installer.
# `test_self_check_sync.py` keeps the fence and the file byte-identical.
DELIVERED_BY_EMBEDDING = {"self_check.py"}

# `python3 <something>/foo.py` or a bare `scripts/foo.py` mention.
INVOCATION = re.compile(r"(?:^|[\s`(])((?:[\w<>./-]*/)?scripts/[\w-]+\.py)")


def _skill_docs() -> list[Path]:
    return sorted(p for p in SRC.rglob("*.md") if p.is_file())


def _referenced_scripts() -> dict[str, set[str]]:
    """script basename -> set of skills whose docs invoke it."""
    found: dict[str, set[str]] = {}
    for doc in _skill_docs():
        skill = doc.relative_to(SRC).parts[0]
        for match in INVOCATION.findall(doc.read_text(encoding="utf-8")):
            found.setdefault(Path(match).name, set()).add(skill)
    return found


def test_every_referenced_script_ships_inside_a_skill_tree():
    """The file the docs name must exist under some `src/<skill>/scripts/`."""
    installable = {p.name for p in SRC.rglob("scripts/*.py")}
    missing = {
        name: sorted(skills)
        for name, skills in _referenced_scripts().items()
        if name not in installable and name not in DELIVERED_BY_EMBEDDING
    }
    assert not missing, (
        "these scripts are invoked by skill docs but ship to no install target "
        f"(not under any src/<skill>/scripts/): {missing}. Move the file into a "
        "skill tree, or deliver it by embedding it in a reference doc the way "
        "self_check.py is delivered."
    )


def test_the_two_spec_scripts_live_in_the_pocket_loop_skill():
    """Pin the home explicitly — a silent move back to the root is the bug."""
    home = SRC / "nxd-pocket-loop" / "scripts"
    for name in ("dp_diagnostics.py", "validate_dp_spec.py"):
        assert (home / name).is_file(), f"{name} must ship at src/nxd-pocket-loop/scripts/"
        assert not (REPO / "scripts" / name).exists(), (
            f"{name} is back at the repo root, where no installer copies it"
        )


@pytest.mark.parametrize("name", sorted(DELIVERED_BY_EMBEDDING))
def test_the_embedded_exception_is_real(name):
    """`self_check.py` is exempt only because a fence actually carries it."""
    assert (REPO / "scripts" / name).is_file()
    fence = (SRC / "nxd-generate-dp" / "reference" / "self-check.md").read_text(encoding="utf-8")
    assert f"# {name}" in fence, (
        f"{name} is exempted from the install rule because it is embedded in "
        "reference/self-check.md. That fence is gone, so the exemption is now a hole."
    )


def test_a_cross_skill_call_names_the_owning_skill():
    """Outside nxd-pocket-loop the bare relative path would not resolve.

    The pack's existing convention (mesh-analyzer's profiler) is to qualify the
    path with the owning skill: `<nxd-mesh-analyzer>/scripts/profile_tabular.py`.
    """
    offenders = []
    for doc in _skill_docs():
        rel = doc.relative_to(SRC)
        if rel.parts[0] == "nxd-pocket-loop":
            continue  # its own scripts/ IS relative to it
        for line_no, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
            for match in INVOCATION.findall(line):
                if Path(match).name not in {"dp_diagnostics.py", "validate_dp_spec.py"}:
                    continue
                if not match.startswith("<nxd-pocket-loop>/"):
                    offenders.append(f"{rel}:{line_no}: {match}")
    assert not offenders, (
        "these call sites use a path that does not resolve from their own skill "
        f"directory; qualify them as <nxd-pocket-loop>/scripts/...: {offenders}"
    )
