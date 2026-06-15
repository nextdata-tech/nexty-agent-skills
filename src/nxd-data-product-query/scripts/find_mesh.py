"""Find the active mesh + bearer token from local nxd settings.

Reads ~/.nxd/meshes.json and ~/.nxd/config.yaml (see nxd-setup skill for the
file format) and ~/.nxd/tokens.json (the file `nxd login` writes).

Prints JSON: {api_url, mesh_name, token_available}. The token itself is
written only to --out (default /tmp/nxd-data-product-query/token.txt with mode
600), never to stdout — so the rest of the skill can pipe / --token-file it
into the other scripts without it leaking into chat.

Exit 0 on success. Exit 2 with a JSON list of meshes when --mesh is omitted
and multiple are configured. Exit 1 on hard error.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from nxd_api import resolve_mesh


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--mesh", help="Mesh name when multiple are configured")
    p.add_argument(
        "--out",
        default="/tmp/nxd-data-product-query/token.txt",
        help="Where to write the bearer token (mode 600). Default keeps the token off stdout.",
    )
    args = p.parse_args()

    m = resolve_mesh(args.mesh)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if m.token:
        out_path.write_text(m.token)
        os.chmod(out_path, 0o600)

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
