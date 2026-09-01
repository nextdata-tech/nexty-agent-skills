"""Load the upstream field-mapper package used by grant fixtures.

The field mapper is source-owned by the NXD checkout rather than by this eval
project.  Keeping that resolution in one place prevents the grant kit from
quietly importing a different installed NXD build.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Any


class FieldMapperUnavailable(RuntimeError):
    """The exact NXD field-mapper source is unavailable or incompatible."""


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


def load_field_mapper(*, repo_root: str | Path | None = None) -> ModuleType:
    """Return ``nxd.experimental.field_mapper`` from the declared NXD source.

    The environment variable is deliberately required.  An installed package
    may be a different checkout and would make a grant appear bound while the
    evaluated closure uses another mapper implementation.
    """

    raw_root = repo_root if repo_root is not None else os.environ.get("EVAL_NXD_REPO_ROOT")
    if not raw_root:
        raise FieldMapperUnavailable(
            "field_mapper dependency is absent from the eval environment; set "
            "EVAL_NXD_REPO_ROOT to an NXD checkout"
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


def field_mapper_module_available(*, repo_root: str | Path | None = None) -> bool:
    """Return whether the exact source-bound field-mapper API can be loaded."""

    try:
        load_field_mapper(repo_root=repo_root)
    except FieldMapperUnavailable:
        return False
    return True


__all__ = ["FieldMapperUnavailable", "field_mapper_module_available", "load_field_mapper"]
