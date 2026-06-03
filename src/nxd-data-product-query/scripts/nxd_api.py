"""Shared helpers for the nxd-data-product-query skill.

Read-only client for the mesh API and per-Data-Product API. Reads bearer tokens
from disk or stdin — never accepts them on the command line — and never prints
them back.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
import yaml


NXD_DIR = Path(os.environ.get("NXD_HOME", os.path.expanduser("~/.nxd")))
MESHES_JSON = NXD_DIR / "meshes.json"
CONFIG_YAML = NXD_DIR / "config.yaml"
TOKENS_JSON = NXD_DIR / "tokens.json"


@dataclass
class Mesh:
    name: str
    api_url: str
    token: str | None
    source: str


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}


def _read_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError:
        return {}


def _name_from_url(url: str) -> str:
    host = urlparse(url).hostname or url
    parts = host.split(".")
    if parts and parts[0] in ("api", "app", "dp", "auth"):
        parts = parts[1:]
    return parts[0] if parts else host


def discover_meshes() -> list[Mesh]:
    """Find every mesh known to the local nxd config.

    Sources, in order: ~/.nxd/meshes.json (registry the nxd-setup skill writes),
    then the top-level url: + meshes: mapping in ~/.nxd/config.yaml.
    """
    out: list[Mesh] = []
    seen: set[str] = set()

    for name, entry in _read_json(MESHES_JSON).items():
        url = entry.get("api_url") or entry.get("url")
        if not url:
            continue
        out.append(Mesh(name=name, api_url=url, token=entry.get("token"), source="meshes.json"))
        seen.add(url)

    cfg = _read_yaml(CONFIG_YAML)
    top = cfg.get("url")
    if top and top not in seen:
        out.append(Mesh(name=_name_from_url(top), api_url=top, token=None, source="config.yaml (active)"))
        seen.add(top)
    for name, entry in (cfg.get("meshes") or {}).items():
        url = (entry or {}).get("url")
        if not url or url in seen:
            continue
        out.append(Mesh(name=name, api_url=url, token=None, source="config.yaml"))
        seen.add(url)

    return out


def _token_for(api_url: str) -> str | None:
    """Find a bearer token for `api_url` in ~/.nxd/tokens.json.

    `nxd login` writes tokens keyed by OAuth auth host (e.g. `auth.westpac.nextopia.dev`).
    Match against the api host's parent domain.
    """
    toks = _read_json(TOKENS_JSON)
    if not toks:
        return None
    host = urlparse(api_url).hostname or ""
    suffix = ".".join(host.split(".")[-3:])
    for key, entry in toks.items():
        if key.endswith(suffix) or suffix in key:
            return entry.get("access_token")
    return None


def resolve_mesh(name: str | None = None) -> Mesh:
    """Pick a mesh from local config. Errors out if ambiguous and no name is given."""
    meshes = discover_meshes()
    if not meshes:
        sys.exit("no mesh configured — run the nxd-setup skill first")
    if name:
        for m in meshes:
            if m.name == name:
                if not m.token:
                    m.token = _token_for(m.api_url)
                return m
        sys.exit(f"no mesh named {name!r}; available: {', '.join(m.name for m in meshes)}")
    if len(meshes) == 1:
        m = meshes[0]
        if not m.token:
            m.token = _token_for(m.api_url)
        return m
    # Ambiguous — caller must pass --mesh
    print(
        json.dumps(
            {
                "error": "ambiguous_mesh",
                "meshes": [
                    {"name": m.name, "api_url": m.api_url, "source": m.source}
                    for m in meshes
                ],
            }
        )
    )
    sys.exit(2)


def read_token(token_file: str | None) -> str:
    """Read a bearer token from a file (preferred) or stdin (fallback)."""
    if token_file:
        return Path(token_file).read_text().strip()
    if not sys.stdin.isatty():
        data = sys.stdin.read().strip()
        if data:
            return data
    sys.exit("no token: pass --token-file or pipe the token on stdin")


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def get(url: str, token: str, **kw) -> Any:
    r = requests.get(url, headers=auth_headers(token), timeout=30, **kw)
    r.raise_for_status()
    return r.json()


def post(url: str, token: str, body: dict, **kw) -> Any:
    r = requests.post(
        url,
        headers={**auth_headers(token), "Content-Type": "application/json"},
        data=json.dumps(body),
        timeout=30,
        **kw,
    )
    r.raise_for_status()
    return r.json()


def list_data_products(api_url: str, token: str) -> list[dict]:
    data = get(f"{api_url.rstrip('/')}/api/v1/data-products", token)
    return data.get("dataProducts", [])


def find_dp(api_url: str, token: str, name: str) -> dict | None:
    for dp in list_data_products(api_url, token):
        if dp.get("fullName") == name or dp.get("name") == name:
            return dp
    return None


def dp_base_url(dp: dict) -> str:
    return dp["baseUrl"].rstrip("/") + "/api"


def list_outputs(dp: dict, token: str) -> dict:
    return get(f"{dp_base_url(dp)}/v1/outputs", token)


def list_rpc_outputs(dp: dict, token: str) -> dict:
    return get(f"{dp_base_url(dp)}/v1/rpc-outputs", token)


def get_location(dp: dict, port: str, token: str) -> dict:
    return get(f"{dp_base_url(dp)}/v1/outputs/{port}/location", token)


def connect_output(dp: dict, port: str, token: str, ttl: str = "PT1H") -> dict:
    return post(f"{dp_base_url(dp)}/v1/outputs/{port}/connect", token, {"ttl": ttl})


def get_info(dp: dict, token: str) -> dict:
    return get(f"{dp_base_url(dp)}/v1/info", token)


def get_models(dp: dict, token: str) -> list[dict]:
    return get(f"{dp_base_url(dp)}/v1/models", token)
