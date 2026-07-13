"""Shared helpers for the nxd-data-product-query skill.

Read-only client for the mesh API and per-Data-Product API. Reads bearer tokens
from disk or stdin — never accepts them on the command line — and never prints
them back.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import time
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
    app_url: str | None = None
    install_url: str | None = None


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


def _derive_app_url(api_url: str) -> str:
    """Derive an app/UI URL from an api_url when no registry entry has one.

    Mirrors the nxd-setup skill's cloud-mesh convention (``api.<sub>.<domain>``
    -> swap the ``api`` label for ``app``) for multi-host meshes. Single-host
    meshes (e.g. the local ``nxd.nxd.local`` cluster, or any host with no
    ``api`` label to swap) serve app + API on the same host, so fall back to
    ``<scheme>://<host>/app``.

    This is only used for the ``config.yaml`` fallback path — ``meshes.json``
    entries carry an explicit ``app_url`` written by the nxd-setup skill and
    that value always wins (see ``discover_meshes``).

    >>> _derive_app_url("https://api.acme.example.com")
    'https://app.acme.example.com'
    >>> _derive_app_url("https://nxd.nxd.local/api")
    'https://nxd.nxd.local/app'
    >>> _derive_app_url("https://nxd.nxd.local")
    'https://nxd.nxd.local/app'
    """
    parsed = urlparse(api_url)
    host = parsed.hostname or ""
    scheme = parsed.scheme or "https"
    labels = host.split(".")
    if labels and labels[0] == "api" and len(labels) > 1:
        app_host = ".".join(["app"] + labels[1:])
        port = f":{parsed.port}" if parsed.port else ""
        return f"{scheme}://{app_host}{port}"
    # Single-host mesh: same host, /app path. netloc excludes the path, so a
    # trailing /api on the api_url can't leak into .../api/app.
    netloc = parsed.netloc or host
    return f"{scheme}://{netloc}/app"


def _name_from_url(url: str) -> str:
    """Last-resort mesh name from a URL host.

    Only used for ``config.yaml`` entries that carry no explicit key/name.
    The authoritative mesh name is the ``meshes.json`` key — prefer that.
    This strips a leading service label (api/app/dp/auth) when present and
    returns the next label; it is a heuristic, not a contract.
    """
    host = urlparse(url).hostname or url
    parts = host.split(".")
    if len(parts) > 1 and parts[0] in ("api", "app", "dp", "auth"):
        parts = parts[1:]
    return parts[0] if parts else host


def discover_meshes() -> list[Mesh]:
    """Find every mesh known to the local nxd config.

    Sources, in order: ~/.nxd/meshes.json (registry the nxd-setup skill writes),
    then the top-level url: + meshes: mapping in ~/.nxd/config.yaml.

    Mesh name comes from the meshes.json key (authoritative). app_url /
    install_url come from the registry entry when present. For config.yaml-only
    entries (no meshes.json registry, or an entry meshes.json doesn't cover),
    app_url is derived from api_url via ``_derive_app_url`` so the
    ``<app_url>/docs/#/...`` links every skill builds still resolve on legacy
    single-mesh setups — it's a heuristic, not a substitute for the recorded
    registry value.
    """
    out: list[Mesh] = []
    seen: set[str] = set()

    for name, entry in _read_json(MESHES_JSON).items():
        url = entry.get("api_url") or entry.get("url")
        if not url:
            continue
        out.append(
            Mesh(
                name=name,
                api_url=url,
                token=entry.get("token"),
                source="meshes.json",
                app_url=entry.get("app_url"),
                install_url=entry.get("install_url") or entry.get("auth_url"),
            )
        )
        seen.add(url)

    cfg = _read_yaml(CONFIG_YAML)
    top = cfg.get("url")
    if top and top not in seen:
        out.append(
            Mesh(
                name=_name_from_url(top),
                api_url=top,
                token=None,
                source="config.yaml (active)",
                app_url=_derive_app_url(top),
            )
        )
        seen.add(top)
    for name, entry in (cfg.get("meshes") or {}).items():
        url = (entry or {}).get("url")
        if not url or url in seen:
            continue
        out.append(Mesh(name=name, api_url=url, token=None, source="config.yaml", app_url=_derive_app_url(url)))
        seen.add(url)

    return out


def _jwt_exp(token: str) -> int | None:
    """Decode a JWT's ``exp`` claim without verifying the signature.

    Returns the Unix timestamp from the payload's ``exp`` field, or ``None``
    if `token` isn't a 3-part JWT, the payload isn't valid base64/JSON, or
    there's no ``exp`` claim. No signature check — we only need the expiry
    for local freshness comparison, never for trust decisions.

    >>> import base64, json
    >>> def _mk(exp):
    ...     payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).rstrip(b"=")
    ...     return "hdr." + payload.decode() + ".sig"
    >>> _jwt_exp(_mk(1234567890))
    1234567890
    >>> _jwt_exp("not-a-jwt") is None
    True
    """
    parts = token.split(".")
    if len(parts) != 3:
        return None
    payload = parts[1]
    padded = payload + "=" * (-len(payload) % 4)
    try:
        data = json.loads(base64.urlsafe_b64decode(padded))
    except (ValueError, json.JSONDecodeError):
        return None
    exp = data.get("exp")
    return int(exp) if isinstance(exp, (int, float)) else None


def _entry_expiry(entry: dict) -> int | None:
    """Best-effort expiry (Unix seconds) for a tokens.json entry.

    Prefers an explicit stored expiry field (``expires_at`` / ``expiry`` /
    ``exp``), else decodes the ``access_token`` JWT's ``exp`` claim.

    >>> _entry_expiry({"expires_at": 100})
    100
    >>> _entry_expiry({"access_token": "x"}) is None
    True
    """
    for key in ("expires_at", "expiry", "exp"):
        val = entry.get(key)
        if isinstance(val, (int, float)):
            return int(val)
    tok = entry.get("access_token")
    if tok:
        return _jwt_exp(tok)
    return None


def _pick_freshest(matches: list[tuple[str, dict]]) -> dict | None:
    """Among candidate ``(key, entry)`` tokens.json matches, prefer the
    unexpired one; among several unexpired (or several expired, if that's
    all there is) prefer the one with the LATEST expiry. Entries with no
    decodable expiry sort last within their bucket (treated as unknown, not
    preferred over a token we can confirm is still valid).

    Single-match behavior is unchanged: with exactly one match, it is
    returned regardless of expiry.

    >>> import time
    >>> now = time.time()
    >>> stale = ("nxd.nxd.local", {"access_token": "stale", "expires_at": now - 10})
    >>> fresh = ("https://nxd.nxd.local/auth", {"access_token": "fresh", "expires_at": now + 1000})
    >>> _pick_freshest([stale, fresh])["access_token"]
    'fresh'
    >>> _pick_freshest([fresh])["access_token"]
    'fresh'
    """
    if len(matches) == 1:
        return matches[0][1]
    if not matches:
        return None

    now = time.time()

    def sort_key(item: tuple[str, dict]) -> tuple[int, float]:
        _, entry = item
        exp = _entry_expiry(entry)
        if exp is None:
            # Unknown expiry: neither confirmed fresh nor confirmed stale.
            # Rank after any token we can confirm is still valid.
            return (1, 0.0)
        if exp <= now:
            # Expired: rank last, but prefer the least-stale (highest exp)
            # among expired — negate so min() picks the largest exp.
            return (2, -exp)
        # Unexpired: rank first, prefer the longest remaining lifetime —
        # negate so min() picks the largest (latest) exp.
        return (0, -exp)

    best = min(matches, key=sort_key)
    return best[1]


def _token_for(api_url: str, mesh: "Mesh | None" = None) -> str | None:
    """Find a bearer token for `api_url` in ~/.nxd/tokens.json.

    `nxd login` writes tokens keyed by the OAuth auth host (e.g.
    `auth.<mesh>.<domain>`). Prefer the auth/install host carried by the mesh
    registry entry (install_url / auth_url) — that is the authoritative source.
    Only when the registry has no such field do we fall back to a domain-suffix
    match against the api host (which assumes auth and api share a parent
    domain — a heuristic that breaks for 2- or 4-label mesh domains).

    A single key match is returned as-is (unchanged behavior). When MULTIPLE
    keys match the same fallback suffix — e.g. a stale ``nxd.nxd.local`` entry
    alongside a fresh ``https://nxd.nxd.local/auth`` entry from a re-login —
    picking the first dict-iteration match handed out whichever token
    happened to be written first, including an expired one, causing a
    downstream 401. Now every match's expiry is inspected (stored expiry
    field, else the JWT ``exp`` claim, decoded without verification) and the
    unexpired / latest-expiring match wins.
    """
    toks = _read_json(TOKENS_JSON)
    if not toks:
        return None

    # Preferred: match the auth/install host from the mesh registry entry.
    auth_host = None
    if mesh is not None:
        auth_ref = mesh.install_url
        if auth_ref:
            auth_host = urlparse(auth_ref).hostname or auth_ref
    if auth_host:
        matches = [
            (key, entry)
            for key, entry in toks.items()
            if key == auth_host or key.endswith(auth_host) or auth_host in key
        ]
        picked = _pick_freshest(matches)
        if picked is not None:
            return picked.get("access_token")

    # Fallback heuristic: api host's parent domain (last 3 labels).
    host = urlparse(api_url).hostname or ""
    suffix = ".".join(host.split(".")[-3:])
    matches = [
        (key, entry)
        for key, entry in toks.items()
        if key.endswith(suffix) or suffix in key
    ]
    picked = _pick_freshest(matches)
    return picked.get("access_token") if picked is not None else None


def resolve_mesh(name: str | None = None) -> Mesh:
    """Pick a mesh from local config. Errors out if ambiguous and no name is given."""
    meshes = discover_meshes()
    if not meshes:
        sys.exit("no mesh configured — run the nxd-setup skill first")
    if name:
        for m in meshes:
            if m.name == name:
                if not m.token:
                    m.token = _token_for(m.api_url, m)
                return m
        sys.exit(f"no mesh named {name!r}; available: {', '.join(m.name for m in meshes)}")
    if len(meshes) == 1:
        m = meshes[0]
        if not m.token:
            m.token = _token_for(m.api_url, m)
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
