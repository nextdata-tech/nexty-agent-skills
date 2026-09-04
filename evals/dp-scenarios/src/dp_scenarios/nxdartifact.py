"""Validation for the ``nxd-py-artifact-v1`` manifest NXD publishes.

NXD is the producer: its CI builds a Linux wheel bundle and uploads it with a
manifest describing what went in and which source trees produced it. Everything
here is consumer-side — it reads that manifest and refuses anything it cannot
account for. Nothing in this repository builds, triggers, or waits on an NXD
build; the flow is one-way by construction.

Two consumers share this module:

* ``dp_scenarios.grantkit.runtime``, which resolves the field mapper out of an
  installed artifact. Its error strings are load-bearing (tests match on them),
  so the ``label`` argument carries the environment-variable name each caller
  uses and the messages are unchanged from when they lived there.
* the semantic MCP contract check, which additionally requires the MCP
  provenance fields. Those are optional here because artifacts published before
  NXD started emitting them are still valid field-mapper artifacts — a consumer
  that needs them asks for them explicitly and gets a refusal, never a silent
  pass against an artifact that predates the provenance.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ARTIFACT_SCHEMA = "nxd-py-artifact-v1"
ARTIFACT_REPOSITORY = "nextdata-tech/nxd"
ARTIFACT_DISTRIBUTIONS = ("nxd-core", "nxd-data_product", "nxd-drivers")

#: Provenance a consumer of the semantic MCP surface needs. ``semantic_tree_sha``
#: identifies the tool factory and the shipped contract; ``rpc_tree_sha`` the MCP
#: registry and the request-model -> JSON Schema conversion behind every
#: ``inputSchema``; ``mcp_contract_sha256`` the exact contract document that
#: should be inside the wheel.
MCP_PROVENANCE_FIELDS = ("semantic_tree_sha", "rpc_tree_sha", "mcp_contract_sha256")


class ArtifactManifestError(RuntimeError):
    """The declared NXD artifact manifest is unusable."""


def read_artifact_manifest(
    path: Path,
    *,
    label: str = "EVAL_NXD_ARTIFACT_MANIFEST",
    require_mcp_provenance: bool = False,
) -> dict[str, Any]:
    """Read and validate an artifact manifest, or raise :class:`ArtifactManifestError`.

    :param label: how the caller names this manifest to a user; appears verbatim
        in every message so each consumer's diagnostics stay actionable.
    :param require_mcp_provenance: refuse a manifest with no MCP provenance
        rather than proceeding against an artifact whose semantic surface is
        unidentified.
    """
    try:
        manifest_path = path.expanduser().resolve(strict=True)
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, RuntimeError, UnicodeError, json.JSONDecodeError) as exc:
        raise ArtifactManifestError(f"{label} is unreadable: {path!s}") from exc
    if not isinstance(data, dict):
        raise ArtifactManifestError(f"{label} must contain a JSON object")
    if data.get("schema") != ARTIFACT_SCHEMA or data.get("repository") != ARTIFACT_REPOSITORY:
        raise ArtifactManifestError(f"{label} has an incompatible schema or repository")
    if not isinstance(data.get("field_mapper_tree_sha"), str) or not data["field_mapper_tree_sha"]:
        raise ArtifactManifestError(f"{label} has no field-mapper source identity")

    package_version = data.get("package_version")
    packages = data.get("packages")
    if not isinstance(package_version, str) or not package_version:
        raise ArtifactManifestError(f"{label} has no package version")
    if not isinstance(packages, dict) or any(packages.get(name) != package_version for name in ARTIFACT_DISTRIBUTIONS):
        raise ArtifactManifestError(f"{label} has inconsistent package versions")
    wheels = data.get("wheels")
    if (
        not isinstance(wheels, list)
        or not wheels
        or any(
            not isinstance(wheel, dict)
            or not isinstance(wheel.get("name"), str)
            or not isinstance(wheel.get("sha256"), str)
            for wheel in wheels
        )
    ):
        raise ArtifactManifestError(f"{label} has no valid wheel records")

    if require_mcp_provenance:
        missing = [name for name in MCP_PROVENANCE_FIELDS if not isinstance(data.get(name), str) or not data[name]]
        if missing:
            raise ArtifactManifestError(
                f"{label} carries no MCP provenance ({', '.join(missing)}); it was published "
                "by an NXD revision that predates the semantic MCP contract. Bump the pinned "
                "NXD source to a revision that publishes it rather than accepting this artifact."
            )
    return data


def verify_wheel_digests(manifest: dict[str, Any], wheels_dir: Path, *, label: str) -> None:
    """Check every wheel the manifest names against its recorded SHA-256."""
    import hashlib

    for wheel in manifest["wheels"]:
        wheel_path = wheels_dir / wheel["name"]
        if not wheel_path.is_file():
            raise ArtifactManifestError(f"{label} names {wheel['name']}, which is not in {wheels_dir}")
        digest = hashlib.sha256(wheel_path.read_bytes()).hexdigest()
        if digest != wheel["sha256"]:
            raise ArtifactManifestError(f"SHA-256 mismatch for {wheel['name']}")


__all__ = [
    "ARTIFACT_DISTRIBUTIONS",
    "ARTIFACT_REPOSITORY",
    "ARTIFACT_SCHEMA",
    "ArtifactManifestError",
    "MCP_PROVENANCE_FIELDS",
    "read_artifact_manifest",
    "verify_wheel_digests",
]
