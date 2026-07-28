"""Pin the desktop installer's copy-vs-symlink rule for the dev install path.

Lives in its own module because it guards `nxd-desktop-setup.sh` in the nxd
repo, not anything under this one. The shell predicate is asserted inline so
the test stands on its own when that repo is not reachable.
"""
from __future__ import annotations

from pathlib import Path
import os
import subprocess

def test_developer_install_copies_bins_when_build_dir_is_outside_home():
    """Symlinks into a separate volume stall the launching app in dyld.

    Keep the symlink for an in-$HOME checkout (rebuilds stay live), copy when
    the build dir is elsewhere so the runtime dir is self-contained.
    """
    # The installer lives in the nxd repo, which is a separate checkout. Assert
    # against it when it is reachable; always assert the predicate itself, which
    # is what actually encodes the fix.
    rel = "components/desktop/supervisor/scripts/nxd-desktop-setup.sh"
    for candidate in (Path(p) / rel for p in os.environ.get("NXD_REPO", "").split(os.pathsep) if p):
        if candidate.exists():
            body = candidate.read_text()
            assert "build dir is outside \\$HOME" in body
            assert 'TARGET_DEBUG_DIR#"${HOME%/}/"' in body
            break

    predicate = (
        'if [ "${HOME%/}/" != "${TARGET_DEBUG_DIR%/}/" ] && '
        '[ "${TARGET_DEBUG_DIR#"${HOME%/}/"}" = "$TARGET_DEBUG_DIR" ]; '
        'then echo COPY; else echo SYMLINK; fi'
    )
    cases = {
        "/Volumes/EXT/repo/target/debug": "COPY",
        "$HOME/projects/nxd/target/debug": "SYMLINK",
        "$HOME-evil/target/debug": "COPY",   # prefix confusion must not read as inside $HOME
    }
    for target, expected in cases.items():
        out = subprocess.run(
            ["bash", "-c", f'TARGET_DEBUG_DIR="{target}"; {predicate}'],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        assert out == expected, (target, out, expected)

