"""Find the active mesh + bearer token from local nxd settings.

Reads ~/.nxd/meshes.json and ~/.nxd/config.yaml (see nxd-setup-cli skill for the
file format) and ~/.nxd/tokens.json (the file `nxd login` writes).

Prints JSON: {api_url, mesh_name, token_available}. The token itself is
written only to --out (default under the OS temp directory with mode 600), never
to stdout — so the rest of the skill can pipe / --token-file it
into the other scripts without it leaking into chat.

app_url / docs_base: meshes.json entries carry an explicit app_url written by
the nxd-setup-cli skill; that value is used as-is. Legacy single-mesh setups with
no meshes.json registry (config.yaml url/meshes only) carry no app_url field,
so nxd_api.discover_meshes derives one from api_url the same way the platform
does (api.<sub> -> app.<sub> for multi-host meshes; <host>/app for single-host
meshes) — see `_derive_app_url` in nxd_api.py. Either way, docs_base below is
always populated when a mesh resolves, so the `<app_url>/docs/#/...` link
instructions in SKILL.md aren't a dead end on legacy setups.

Exit 0 on success. Exit 2 with a JSON list of meshes when --mesh is omitted
and multiple are configured. Exit 1 on hard error.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

from nxd_api import resolve_mesh


def _write_private(path: Path, text: str) -> None:
    """Write text to a 0600 file, created with restrictive perms from the start.

    Using os.open with mode 0o600 (instead of write_text + chmod) closes the
    window where the token file would briefly be readable by group/other under
    the active umask on a shared host.
    """
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(text)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--mesh", help="Mesh name when multiple are configured")
    p.add_argument(
        "--out",
        default=str(Path(tempfile.gettempdir()) / "nxd-query-data-product" / "token.txt"),
        help="Where to write the bearer token (mode 600). Default keeps the token off stdout.",
    )
    args = p.parse_args()

    m = resolve_mesh(args.mesh)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if m.token:
        _write_private(out_path, m.token)

    docs_base = f"{m.app_url.rstrip('/')}/docs/#/" if m.app_url else None

    print(
        json.dumps(
            {
                "mesh_name": m.name,
                "api_url": m.api_url,
                "app_url": m.app_url,
                "docs_base": docs_base,
                "source": m.source,
                "token_available": bool(m.token),
                "token_file": str(out_path) if m.token else None,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
