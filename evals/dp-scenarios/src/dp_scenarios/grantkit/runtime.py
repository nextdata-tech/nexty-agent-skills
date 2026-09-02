"""Load the upstream field-mapper package used by grant fixtures.

The field mapper is source-owned by NXD rather than by this eval project. CI
uses a manifest for an NXD-produced wheel bundle; local runs may use an NXD
checkout. Keeping both resolution paths here prevents the grant kit from
quietly importing an undeclared NXD build.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import json
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Any


class FieldMapperUnavailable(RuntimeError):
    """The declared NXD field-mapper build is unavailable or incompatible."""


_ARTIFACT_SCHEMA = "nxd-py-artifact-v1"
_ARTIFACT_REPOSITORY = "nextdata-tech/nxd"
_ARTIFACT_DISTRIBUTIONS = ("nxd-core", "nxd-data_product", "nxd-drivers")


def _source_directories(repo_root: Path) -> tuple[Path, ...]:
    data_product = repo_root / "components/nxd_py/data_product"
    core = repo_root / "components/nxd_py/core"
    drivers = repo_root / "components/nxd_py/drivers"
    required = (
        data_product / "nxd/experimental/field_mapper/__init__.py",
        core / "nxd/core",
        drivers / "nxd/drivers",
    )
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FieldMapperUnavailable(
            "EVAL_NXD_REPO_ROOT is not a compatible NXD checkout; missing "
            + ", ".join(missing)
        )
    return data_product, core, drivers


def _under(path: str | None, root: Path) -> bool:
    if not path:
        return False
    try:
        Path(path).resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True


def _module_under(module: Any, root: Path) -> bool:
    paths = []
    module_file = getattr(module, "__file__", None)
    if isinstance(module_file, str):
        paths.append(module_file)
    module_paths = getattr(module, "__path__", ())
    paths.extend(str(path) for path in module_paths)
    return any(_under(path, root) for path in paths)


def _validate_module_api(module: ModuleType) -> ModuleType:
    required: dict[str, Any] = {
        "Grant": getattr(module, "Grant", None),
        "MapperSpec": getattr(module, "MapperSpec", None),
        "EvaluationProfile": getattr(module, "EvaluationProfile", None),
    }
    if not all(value is not None for value in required.values()):
        missing = ", ".join(name for name, value in required.items() if value is None)
        raise FieldMapperUnavailable(f"incompatible field_mapper API; missing {missing}")
    if not callable(getattr(required["MapperSpec"], "load", None)) or not hasattr(
        required["MapperSpec"], "mapper_spec_id"
    ):
        raise FieldMapperUnavailable("incompatible field_mapper API; MapperSpec lacks load/mapper_spec_id")
    return module


def _read_artifact_manifest(path: Path) -> dict[str, Any]:
    try:
        manifest_path = path.expanduser().resolve(strict=True)
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, RuntimeError, UnicodeError, json.JSONDecodeError) as exc:
        raise FieldMapperUnavailable(f"EVAL_NXD_ARTIFACT_MANIFEST is unreadable: {path!s}") from exc
    if not isinstance(data, dict):
        raise FieldMapperUnavailable("EVAL_NXD_ARTIFACT_MANIFEST must contain a JSON object")
    if data.get("schema") != _ARTIFACT_SCHEMA or data.get("repository") != _ARTIFACT_REPOSITORY:
        raise FieldMapperUnavailable("EVAL_NXD_ARTIFACT_MANIFEST has an incompatible schema or repository")
    if not isinstance(data.get("field_mapper_tree_sha"), str) or not data["field_mapper_tree_sha"]:
        raise FieldMapperUnavailable("EVAL_NXD_ARTIFACT_MANIFEST has no field-mapper source identity")

    package_version = data.get("package_version")
    packages = data.get("packages")
    if not isinstance(package_version, str) or not package_version:
        raise FieldMapperUnavailable("EVAL_NXD_ARTIFACT_MANIFEST has no package version")
    if not isinstance(packages, dict) or any(
        packages.get(name) != package_version for name in _ARTIFACT_DISTRIBUTIONS
    ):
        raise FieldMapperUnavailable("EVAL_NXD_ARTIFACT_MANIFEST has inconsistent package versions")
    wheels = data.get("wheels")
    if not isinstance(wheels, list) or not wheels or any(
        not isinstance(wheel, dict)
        or not isinstance(wheel.get("name"), str)
        or not isinstance(wheel.get("sha256"), str)
        for wheel in wheels
    ):
        raise FieldMapperUnavailable("EVAL_NXD_ARTIFACT_MANIFEST has no valid wheel records")
    return data


def _load_artifact_field_mapper(manifest_path: Path) -> ModuleType:
    manifest = _read_artifact_manifest(manifest_path)
    expected_versions = manifest["packages"]
    try:
        distributions = {
            name: importlib.metadata.distribution(name) for name in _ARTIFACT_DISTRIBUTIONS
        }
    except importlib.metadata.PackageNotFoundError as exc:
        raise FieldMapperUnavailable(
            "the NXD Python artifact manifest is present, but an expected distribution is not installed"
        ) from exc

    for name, distribution in distributions.items():
        if distribution.version != expected_versions[name]:
            raise FieldMapperUnavailable(
                f"installed {name} version {distribution.version!r} does not match "
                f"the NXD artifact manifest ({expected_versions[name]!r})"
            )

    data_product_root = Path(
        distributions["nxd-data_product"].locate_file("nxd")
    ).expanduser().resolve()
    expected_module_file = data_product_root / "experimental/field_mapper/__init__.py"
    if not expected_module_file.is_file():
        raise FieldMapperUnavailable(
            "the installed nxd-data_product artifact does not contain the field_mapper package"
        )

    for module_name in ("nxd", "nxd.experimental", "nxd.experimental.field_mapper"):
        existing = sys.modules.get(module_name)
        if existing is not None and not _module_under(existing, data_product_root):
            raise FieldMapperUnavailable(
                f"an incompatible installed {module_name} is already loaded; start a fresh process"
            )

    importlib.invalidate_caches()
    try:
        module = importlib.import_module("nxd.experimental.field_mapper")
    except (ImportError, ModuleNotFoundError) as exc:
        raise FieldMapperUnavailable(
            "could not import nxd.experimental.field_mapper from the installed NXD artifact"
        ) from exc
    module_file = getattr(module, "__file__", None)
    if not isinstance(module_file, str) or Path(module_file).expanduser().resolve() != expected_module_file:
        raise FieldMapperUnavailable(
            "nxd.experimental.field_mapper resolved outside the declared NXD artifact"
        )
    return _validate_module_api(module)


def load_field_mapper(*, repo_root: str | Path | None = None) -> ModuleType:
    """Return ``nxd.experimental.field_mapper`` from the declared NXD build.

    The caller must declare either an artifact manifest or an NXD checkout.
    An undeclared installed package could be a different build and would make
    a grant appear bound while the evaluated closure uses another mapper.
    """

    if repo_root is None:
        artifact_manifest = os.environ.get("EVAL_NXD_ARTIFACT_MANIFEST")
        if artifact_manifest:
            return _load_artifact_field_mapper(Path(artifact_manifest))

    raw_root = repo_root if repo_root is not None else os.environ.get("EVAL_NXD_REPO_ROOT")
    if not raw_root:
        raise FieldMapperUnavailable(
            "field_mapper dependency is absent from the eval environment; set "
            "EVAL_NXD_ARTIFACT_MANIFEST or EVAL_NXD_REPO_ROOT"
        )
    try:
        root = Path(raw_root).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise FieldMapperUnavailable(f"EVAL_NXD_REPO_ROOT is not a readable checkout: {raw_root!r}") from exc
    directories = _source_directories(root)

    for module_name in ("nxd", "nxd.experimental", "nxd.experimental.field_mapper"):
        existing = sys.modules.get(module_name)
        if existing is not None and not _module_under(existing, directories[0]):
            raise FieldMapperUnavailable(
                f"an incompatible installed {module_name} is already loaded; "
                "start a fresh process with EVAL_NXD_REPO_ROOT"
            )

    # Match the upstream fixture's source precedence: data_product wins over
    # the companion core/drivers source roots.
    for directory in reversed(directories):
        text = str(directory)
        if text in sys.path:
            sys.path.remove(text)
        sys.path.insert(0, text)
    importlib.invalidate_caches()
    try:
        module = importlib.import_module("nxd.experimental.field_mapper")
    except (ImportError, ModuleNotFoundError) as exc:
        raise FieldMapperUnavailable(
            "could not import nxd.experimental.field_mapper from "
            f"{root}: {exc}"
        ) from exc

    if not _under(getattr(module, "__file__", None), directories[0]):
        raise FieldMapperUnavailable(
            "nxd.experimental.field_mapper resolved outside EVAL_NXD_REPO_ROOT"
        )
    return _validate_module_api(module)


def field_mapper_module_available(*, repo_root: str | Path | None = None) -> bool:
    """Return whether the declared field-mapper API can be loaded."""

    try:
        load_field_mapper(repo_root=repo_root)
    except FieldMapperUnavailable:
        return False
    return True


__all__ = ["FieldMapperUnavailable", "field_mapper_module_available", "load_field_mapper"]
