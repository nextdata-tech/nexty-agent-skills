"""Fail-closed behaviour of the shared NXD artifact-manifest reader.

Two consumers depend on this: the field-mapper integration (which must keep its
exact messages) and the semantic MCP contract check (which additionally demands
MCP provenance). The cases below pin both directions — that a valid manifest is
accepted, and that every way of being invalid is a refusal rather than a
degraded pass.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from dp_scenarios.nxdartifact import ArtifactManifestError
from dp_scenarios.nxdartifact import read_artifact_manifest
from dp_scenarios.nxdartifact import verify_wheel_digests

_VERSION = "0.41.200"


def _manifest(**overrides: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "schema": "nxd-py-artifact-v1",
        "repository": "nextdata-tech/nxd",
        "source_sha": "a" * 40,
        "field_mapper_tree_sha": "b" * 40,
        "semantic_tree_sha": "c" * 40,
        "rpc_tree_sha": "d" * 40,
        "mcp_contract_sha256": "e" * 64,
        "package_version": _VERSION,
        "workflow_run_id": "12345",
        "python": "3.11",
        "platform": "linux-x86_64",
        "packages": {"nxd-core": _VERSION, "nxd-data_product": _VERSION, "nxd-drivers": _VERSION},
        "wheels": [{"name": "nxd_core.whl", "sha256": "0" * 64}],
    }
    document.update(overrides)
    return document


def _write(tmp_path: Path, document: Any) -> Path:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


class TestAcceptance:
    def test_a_well_formed_manifest_is_returned(self, tmp_path: Path) -> None:
        assert read_artifact_manifest(_write(tmp_path, _manifest()))["package_version"] == _VERSION

    def test_mcp_provenance_is_optional_by_default(self, tmp_path: Path) -> None:
        """A pre-provenance artifact stays valid for the field-mapper consumer."""
        document = _manifest()
        for field in ("semantic_tree_sha", "rpc_tree_sha", "mcp_contract_sha256"):
            del document[field]
        assert read_artifact_manifest(_write(tmp_path, document))["field_mapper_tree_sha"]

    def test_mcp_provenance_is_returned_when_required_and_present(self, tmp_path: Path) -> None:
        manifest = read_artifact_manifest(_write(tmp_path, _manifest()), require_mcp_provenance=True)
        assert manifest["semantic_tree_sha"] == "c" * 40


class TestFailClosed:
    def test_an_absent_manifest_is_an_error(self, tmp_path: Path) -> None:
        with pytest.raises(ArtifactManifestError, match="unreadable"):
            read_artifact_manifest(tmp_path / "absent.json")

    def test_a_non_object_document_is_an_error(self, tmp_path: Path) -> None:
        with pytest.raises(ArtifactManifestError, match="must contain a JSON object"):
            read_artifact_manifest(_write(tmp_path, ["not", "an", "object"]))

    def test_a_foreign_repository_is_an_error(self, tmp_path: Path) -> None:
        with pytest.raises(ArtifactManifestError, match="incompatible schema or repository"):
            read_artifact_manifest(_write(tmp_path, _manifest(repository="someone/else")))

    def test_inconsistent_package_versions_are_an_error(self, tmp_path: Path) -> None:
        document = _manifest()
        document["packages"]["nxd-drivers"] = "0.0.1"
        with pytest.raises(ArtifactManifestError, match="inconsistent package versions"):
            read_artifact_manifest(_write(tmp_path, document))

    def test_a_wheel_record_without_a_digest_is_an_error(self, tmp_path: Path) -> None:
        with pytest.raises(ArtifactManifestError, match="no valid wheel records"):
            read_artifact_manifest(_write(tmp_path, _manifest(wheels=[{"name": "nxd_core.whl"}])))

    @pytest.mark.parametrize("field", ["semantic_tree_sha", "rpc_tree_sha", "mcp_contract_sha256"])
    def test_missing_mcp_provenance_is_refused_when_required(self, tmp_path: Path, field: str) -> None:
        """Each provenance field independently blocks the MCP consumer.

        Checked one field at a time on purpose: an all-or-nothing test passes
        even if the check only looks at whichever field happens to be first.
        """
        document = _manifest()
        del document[field]
        with pytest.raises(ArtifactManifestError, match=field):
            read_artifact_manifest(_write(tmp_path, document), require_mcp_provenance=True)

    def test_an_empty_provenance_string_is_refused_like_an_absent_one(self, tmp_path: Path) -> None:
        with pytest.raises(ArtifactManifestError, match="semantic_tree_sha"):
            read_artifact_manifest(_write(tmp_path, _manifest(semantic_tree_sha="")), require_mcp_provenance=True)

    def test_the_provenance_refusal_says_not_to_fall_back(self, tmp_path: Path) -> None:
        """The remedy has to be in the message, or the reflex is to loosen the check."""
        document = _manifest()
        del document["semantic_tree_sha"]
        with pytest.raises(ArtifactManifestError) as excinfo:
            read_artifact_manifest(_write(tmp_path, document), require_mcp_provenance=True)
        assert "do not" in str(excinfo.value).lower() or "rather than accepting" in str(excinfo.value)

    def test_the_label_appears_in_every_message(self, tmp_path: Path) -> None:
        """Two consumers share this reader; a generic message would misdirect one."""
        with pytest.raises(ArtifactManifestError, match="MY_LABEL"):
            read_artifact_manifest(tmp_path / "absent.json", label="MY_LABEL")
        with pytest.raises(ArtifactManifestError, match="MY_LABEL"):
            read_artifact_manifest(_write(tmp_path, _manifest(package_version="")), label="MY_LABEL")


class TestWheelDigests:
    def test_a_matching_wheel_passes(self, tmp_path: Path) -> None:
        wheels = tmp_path / "wheels"
        wheels.mkdir()
        (wheels / "nxd_core.whl").write_bytes(b"payload")
        manifest = _manifest(
            wheels=[{"name": "nxd_core.whl", "sha256": hashlib.sha256(b"payload").hexdigest()}]
        )
        verify_wheel_digests(manifest, wheels, label="test")

    def test_a_tampered_wheel_is_refused(self, tmp_path: Path) -> None:
        wheels = tmp_path / "wheels"
        wheels.mkdir()
        (wheels / "nxd_core.whl").write_bytes(b"tampered")
        manifest = _manifest(
            wheels=[{"name": "nxd_core.whl", "sha256": hashlib.sha256(b"payload").hexdigest()}]
        )
        with pytest.raises(ArtifactManifestError, match="SHA-256 mismatch"):
            verify_wheel_digests(manifest, wheels, label="test")

    def test_a_wheel_named_but_absent_is_refused(self, tmp_path: Path) -> None:
        wheels = tmp_path / "wheels"
        wheels.mkdir()
        with pytest.raises(ArtifactManifestError, match="not in"):
            verify_wheel_digests(_manifest(), wheels, label="test")
