"""Inspection orchestration. Generic — dispatches each service to its driver
plugin through the injected Registry, and never imports a service SDK."""
from .profile import parse_services


def make_service_url(api_url, profile, service):
    """Infra-profile service reference for downstream skills.

    `api_url` MUST be the active mesh's api_url (resolved from
    ~/.nxd/meshes.json by the caller / SKILL.md Step 0) so the URL host is
    anchored to the mesh the profile belongs to. When given, the result is
    absolute. When empty (offline / no active mesh) the ref is left relative
    and the report must state which mesh it resolves against — there is no
    assumed default base.
    """
    ref = f"infra-profile/{profile}#/services/{service}"
    return f"{api_url.rstrip('/')}/{ref}" if api_url else ref


def inspect_services(profile_path, service_names, registry, api_url=""):
    """Inspect each named service and return {service_name: inventory}.

    An entry is an inventory dict, or {"error": ...}, or
    {"duplicate_of": ...} when a service points at an already-seen store.
    Every entry is annotated with the profile name and service URL.
    """
    profile_name, services = parse_services(profile_path)
    svc_map = {s["name"]: s for s in services}

    result = {}
    seen_stores = {}
    for name in service_names:
        if name not in svc_map:
            result[name] = {"error": "service not in profile"}
            continue
        svc = svc_map[name]
        dn = svc["driver_name"]
        inspect = registry.inspector(dn)
        if inspect is None:
            result[name] = {"error": f"no driver plugin for '{dn}' — "
                                     f"add one under drivers/"}
            continue
        try:
            inv = inspect(svc["attrs"])
        except Exception as e:
            result[name] = {"error": f"{type(e).__name__}: {e}"}
            continue
        # de-duplicate: same physical store inspected twice
        store = inv.get("store")
        if store in seen_stores:
            result[name] = {"driver": dn, "duplicate_of": seen_stores[store],
                            "store": store}
        else:
            seen_stores[store] = name
            inv["driver"] = dn
            result[name] = inv

    # annotate every entry so downstream skills can reference each service
    for name, entry in result.items():
        entry["profile"] = profile_name
        entry["service"] = name
        entry["service_url"] = make_service_url(api_url, profile_name, name)
    return result
