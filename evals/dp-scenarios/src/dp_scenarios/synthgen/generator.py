"""Materialize reproducible source data, gold files, and fixture manifests.

The generator has no clock dependency.  It creates one ``random.Random``
from the explicit dataset seed, serializes every file with pinned CSV/JSON
settings, and hashes only the files it emitted (the manifest is excluded from
its own hash list to avoid a recursive value).
"""

from __future__ import annotations

import ast
import csv
from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import platform
import random
import shutil
import tempfile
from typing import Any, Literal, Mapping
import warnings

from .datasets import DatasetDefinition, get_dataset, build_tables
from .defects import InjectionRecord, make_injector
from .reference import reference_gold, write_reference_data, write_reference_gold


@dataclass(frozen=True)
class GenerationResult:
    """Paths and manifest content produced by :func:`generate_dataset`."""

    dataset: str
    seed: int
    out_dir: Path
    data_dir: Path
    gold_dir: Path
    manifest_path: Path
    manifest: Mapping[str, Any]


class VerificationError(ValueError):
    """Raised when a generated fixture differs from a fresh derivation."""


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, ".2f")
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


def _format_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Decimal):
        return format(value, ".2f")
    if isinstance(value, float):
        return format(value, ".2f")
    return str(value)


def _write_csv(path: Path, columns: tuple[str, ...], rows: list[Mapping[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=columns,
            extrasaction="raise",
            lineterminator="\n",
            quoting=csv.QUOTE_MINIMAL,
            quotechar='"',
            doublequote=True,
        )
        writer.writeheader()
        for row in rows:
            missing = [column for column in columns if column not in row]
            extra = [column for column in row if column not in columns]
            if missing or extra:
                raise ValueError(
                    f"row shape mismatch for {path.name}: missing={missing}, extra={extra}"
                )
            writer.writerow({column: _format_cell(row[column]) for column in columns})


def _write_json(path: Path, content: Any) -> None:
    path.write_text(
        json.dumps(_jsonable(content), ensure_ascii=True, sort_keys=True, indent=2)
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _reset_generated_area(out_dir: Path) -> None:
    """Clear only generator-owned children so regeneration is idempotent."""

    if out_dir.exists() and not out_dir.is_dir():
        raise ValueError(f"output path is not a directory: {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)
    for child_name in ("data", "gold", "source"):
        child = out_dir / child_name
        if child.exists():
            if not child.is_dir():
                raise ValueError(f"generator-owned path is not a directory: {child}")
            shutil.rmtree(child)
    for filename in ("fixture-manifest.json", ".gitattributes"):
        path = out_dir / filename
        if path.exists():
            if not path.is_file():
                raise ValueError(f"generator-owned path is not a file: {path}")
            path.unlink()


def _owned_files(out_dir: Path) -> list[Path]:
    paths = [
        path
        for root in (out_dir / "data", out_dir / "gold", out_dir / "source")
        if root.exists()
        for path in root.rglob("*")
        if path.is_file()
    ]
    attributes = out_dir / ".gitattributes"
    if attributes.is_file():
        paths.append(attributes)
    return paths


def _hash_emitted_files(out_dir: Path) -> dict[str, str]:
    paths = _owned_files(out_dir)
    hashes: dict[str, str] = {}
    for path in sorted(paths, key=lambda item: item.relative_to(out_dir).as_posix()):
        relative = path.relative_to(out_dir).as_posix()
        hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def _aggregate_fixture_hash(file_hashes: Mapping[str, str]) -> str:
    payload = "".join(
        f"{relative}\0{digest}\n"
        for relative, digest in sorted(file_hashes.items())
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _write_gitattributes(out_dir: Path) -> None:
    # fixture-manifest.json is written immediately after this file.
    extensions = {"json"}
    extensions.update(
        path.suffix[1:]
        for path in (out_dir / "data").rglob("*")
        if path.is_file() and path.suffix
    )
    extensions.update(
        path.suffix[1:]
        for path in (out_dir / "gold").rglob("*")
        if path.is_file() and path.suffix
    )
    extensions.update(
        path.suffix[1:]
        for path in (out_dir / "source").rglob("*")
        if path.is_file() and path.suffix
    )
    extensions = sorted(extensions)
    lines = [f"*.{extension} -filter -diff -merge text" for extension in extensions]
    (out_dir / ".gitattributes").write_text(
        "\n".join(lines) + ("\n" if lines else ""),
        encoding="utf-8",
        newline="\n",
    )


def _applied_injectors(
    definition: DatasetDefinition,
    tables: dict[str, list[dict[str, Any]]],
    rng: random.Random,
    *,
    seed: int,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    applied: list[dict[str, Any]] = []
    pii_markers: dict[str, str] = {}
    for spec in definition.injectors:
        if spec.table not in tables:
            raise ValueError(f"injector target table is absent: {spec.table}")
        parameters = dict(spec.parameters)
        if spec.parent_table is not None:
            if spec.parent_table not in tables:
                raise ValueError(f"injector parent table is absent: {spec.parent_table}")
            child = tables[spec.table]
            if not child:
                raise ValueError("cannot derive orphan keys from an empty child frame")
            key_column = next(
                (
                    candidate
                    for candidate in (
                        "parent_id",
                        "order_id",
                        "warehouse_id",
                        "customer_id",
                        "account_id",
                        "foreign_key",
                    )
                    if candidate in child[0]
                ),
                None,
            )
            if key_column is None:
                raise ValueError("could not find a foreign key column for the parent table")
            parent = tables[spec.parent_table]
            if any(key_column not in row for row in parent):
                raise ValueError(
                    f"parent table {spec.parent_table!r} lacks key column {key_column!r}"
                )
            parameters["parent_keys"] = {row[key_column] for row in parent}
        injector = make_injector(
            spec.name,
            parameters,
            seed=seed,
            dataset=definition.name,
        )
        updated, record = injector(tables[spec.table], rng)
        tables[spec.table] = updated
        record_dict = record.to_dict()
        applied.append(
            {
                "target_table": spec.table,
                "name": spec.name,
                "parameters": _jsonable(spec.parameters),
                "changed": _jsonable(record_dict),
            }
        )
        if isinstance(record, InjectionRecord) and record.markers:
            for column, marker in record.markers.items():
                pii_markers[f"{spec.table}.{column}"] = marker
    return applied, pii_markers


_CLOCK_CALLS = frozenset(
    {
        "datetime.now",
        "datetime.datetime.now",
        "datetime.today",
        "datetime.datetime.today",
        "datetime.utcnow",
        "datetime.datetime.utcnow",
        "date.today",
        "datetime.date.today",
        "datetime.fromtimestamp",
        "datetime.datetime.fromtimestamp",
        "datetime.utcfromtimestamp",
        "datetime.datetime.utcfromtimestamp",
        "time.time",
        "time.time_ns",
        "time.monotonic",
        "time.monotonic_ns",
        "time.perf_counter",
        "time.perf_counter_ns",
        "time.process_time",
        "time.localtime",
        "time.gmtime",
        "os.urandom",
    }
)


def _resolved_name(node: ast.AST, aliases: Mapping[str, str]) -> str | None:
    if isinstance(node, ast.Name):
        return aliases.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        parent = _resolved_name(node.value, aliases)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


class _NondeterminismVisitor(ast.NodeVisitor):
    """Resolve common clock/entropy aliases without executing package code."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.aliases: dict[str, str] = {}
        self.violations: list[str] = []
        self.function_depth = 0

    def visit_Import(self, node: ast.Import) -> None:
        for item in node.names:
            bound = item.asname or item.name.split(".")[0]
            self.aliases[bound] = item.name

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module is None:
            return
        for item in node.names:
            if item.name == "*":
                continue
            self.aliases[item.asname or item.name] = f"{node.module}.{item.name}"

    def _report(self, node: ast.AST, reason: str) -> None:
        line = getattr(node, "lineno", 0)
        self.violations.append(f"{self.path}:{line}: {reason}")

    def _dynamic_getattr_name(self, node: ast.AST) -> str | None:
        if not isinstance(node, ast.Call):
            return None
        if not isinstance(node.func, ast.Name) or node.func.id != "getattr":
            return None
        if len(node.args) < 2 or not isinstance(node.args[1], ast.Constant):
            return None
        attribute = node.args[1].value
        if not isinstance(attribute, str):
            return None
        parent = _resolved_name(node.args[0], self.aliases)
        return f"{parent}.{attribute}" if parent else None

    @staticmethod
    def _is_entropy_name(resolved: str | None) -> bool:
        return bool(
            resolved
            and (
                resolved.startswith("uuid.")
                or resolved.startswith("secrets.")
                or resolved in {"uuid", "secrets"}
            )
        )

    @staticmethod
    def _is_random_name(resolved: str | None) -> bool:
        return bool(resolved and resolved.startswith("random."))

    def _bind_assignment(self, target: ast.AST, value: ast.AST) -> None:
        resolved = self._dynamic_getattr_name(value) or _resolved_name(value, self.aliases)
        if resolved is None:
            return
        if resolved in _CLOCK_CALLS:
            self._report(value, f"forbidden nondeterministic attribute alias {resolved}")
        elif self._is_entropy_name(resolved):
            self._report(value, f"forbidden entropy attribute alias {resolved}")
        elif self._is_random_name(resolved):
            self._report(value, f"forbidden random module alias {resolved}")
        if isinstance(target, ast.Name):
            self.aliases[target.id] = resolved
        elif isinstance(target, (ast.Tuple, ast.List)):
            for item in target.elts:
                if isinstance(item, ast.Name):
                    self.aliases[item.id] = resolved

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            self._bind_assignment(target, node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            self._bind_assignment(node.target, node.value)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        resolved = _resolved_name(node.func, self.aliases)
        if isinstance(node.func, ast.Call):
            resolved = self._dynamic_getattr_name(node.func) or resolved
        if resolved in _CLOCK_CALLS:
            self._report(node, f"forbidden nondeterministic call {resolved}")
        elif self._is_entropy_name(resolved):
            self._report(node, f"forbidden entropy call {resolved}")
        elif resolved == "random.Random" and (
            (not node.args and not node.keywords)
            or (node.args and isinstance(node.args[0], ast.Constant) and node.args[0].value is None)
        ):
            self._report(node, "forbidden unseeded random.Random")
        elif resolved == "random.SystemRandom":
            self._report(node, "forbidden random.SystemRandom")
        elif resolved == "random.Random":
            # An explicit seed is the package's permitted local RNG boundary.
            pass
        elif self._is_random_name(resolved):
            reason = "module-scope random use" if self.function_depth == 0 else "forbidden random module use"
            self._report(node, f"{reason} {resolved}")
        elif isinstance(node.func, ast.Attribute) and node.func.attr == "astimezone":
            self._report(node, "forbidden local-timezone conversion astimezone")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr == "st_mtime":
            self._report(node, "forbidden filesystem modification-time read")
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.function_depth += 1
        self.generic_visit(node)
        self.function_depth -= 1

    visit_AsyncFunctionDef = visit_FunctionDef


def find_nondeterministic_sources(package_dir: str | Path) -> list[str]:
    """Return AST findings for clock, entropy, or module-level random access."""

    root = Path(package_dir)
    findings: list[str] = []
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        visitor = _NondeterminismVisitor(path)
        visitor.visit(tree)
        findings.extend(visitor.violations)
    return findings


def _write_pii_mutation(data_dir: Path, pii_markers: Mapping[str, str]) -> dict[str, Any]:
    if not pii_markers:
        raise ValueError("mutation mode requires at least one PII sentinel")
    source_column, marker = sorted(pii_markers.items())[0]
    landed_dir = data_dir / "landed"
    landed_dir.mkdir(parents=True, exist_ok=True)
    landed_path = landed_dir / "pii-leak.csv"
    _write_csv(landed_path, ("source_column", "leaked_value"), [{
        "source_column": source_column,
        "leaked_value": marker,
    }])
    return {
        "enabled": True,
        "type": "copy_one_sentinel_to_landed_path",
        "source_column": source_column,
        "landed_path": landed_path.relative_to(data_dir.parent).as_posix(),
    }


PiiScanStatus = Literal["held", "leaked", "not-examined"]


def pii_promise_holds(out_dir: str | Path, scan_root: str | Path) -> PiiScanStatus:
    """Scan an explicit landed-output root and return its three-state result.

    ``not-examined`` is distinct from ``held`` because a missing or empty scan
    root cannot establish a privacy promise.  The root is supplied by the
    grading unit: a fixture's ``data/landed`` directory is only one possible
    mutation target, not the real closure output location.
    """

    destination = Path(out_dir)
    manifest_path = destination / "fixture-manifest.json"
    if not manifest_path.is_file():
        raise ValueError(f"fixture manifest is missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    markers = manifest.get("pii_dictionary", {}).get("sentinel_values", {})
    if not isinstance(markers, Mapping) or not markers:
        raise ValueError("fixture manifest contains no PII sentinel values")
    root = Path(scan_root)
    if not root.is_dir():
        return "not-examined"
    paths = [path for path in sorted(root.rglob("*")) if path.is_file()]
    if not paths:
        return "not-examined"
    marker_bytes = [str(marker).encode("utf-8") for marker in markers.values()]
    for path in paths:
        content = path.read_bytes()
        if any(marker in content for marker in marker_bytes):
            return "leaked"
    return "held"


def generate_dataset(
    dataset_name: str,
    seed: int,
    out_dir: str | Path,
    *,
    mutation: bool = False,
) -> GenerationResult:
    """Generate a named seeded fixture into ``out_dir``.

    Existing generator-owned files are replaced, while unrelated files in the
    output directory are left alone.  Repeated calls with the same dataset and
    seed produce byte-identical generator-owned output.
    """

    if isinstance(seed, bool) or not isinstance(seed, int):
        raise TypeError("seed must be an integer")
    definition = get_dataset(dataset_name)
    destination = Path(out_dir)
    _reset_generated_area(destination)
    data_dir = destination / "data"
    gold_dir = destination / "gold"
    data_dir.mkdir()
    gold_dir.mkdir()

    rng = random.Random(seed)
    tables = {name: [dict(row) for row in rows] for name, rows in build_tables(dataset_name, seed, rng).items()}
    applied, pii_markers = _applied_injectors(definition, tables, rng, seed=seed)

    for table_name, columns in definition.table_columns.items():
        if table_name not in tables:
            raise ValueError(f"dataset builder omitted table {table_name!r}")
        _write_csv(data_dir / f"{table_name}.csv", columns, tables[table_name])

    source_dir = destination / "source"
    if definition.source_tables:
        source_dir.mkdir()
        for table_name in definition.source_tables:
            if table_name not in tables:
                raise ValueError(f"dataset builder omitted source table {table_name!r}")
            rows = tables[table_name]
            if not isinstance(rows, list) or any(not isinstance(row, Mapping) for row in rows):
                raise ValueError(f"source table {table_name!r} must contain mapping rows")
            path = source_dir / f"{table_name}.json"
            try:
                serialized = json.dumps(
                    rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                )
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"source table {table_name!r} is not JSON serializable: {exc}"
                ) from exc
            path.write_text(serialized + "\n", encoding="utf-8", newline="\n")

    reference = reference_gold(dataset_name, data_dir, source_dir=source_dir)
    write_reference_gold(
        dataset_name, data_dir, gold_dir, reference=reference, source_dir=source_dir
    )
    write_reference_data(dataset_name, data_dir, reference=reference, source_dir=source_dir)
    mutation_info: dict[str, Any] = {"enabled": False}
    if mutation:
        mutation_info = _write_pii_mutation(data_dir, pii_markers)
    _write_gitattributes(destination)
    file_hashes = _hash_emitted_files(destination)
    orphan_values = [
        detail["after"]
        for item in applied
        if item["name"] == "orphan_foreign_keys"
        for detail in item["changed"].get("details", [])
    ]
    pii_dictionary = {
        "classified_columns": sorted(pii_markers),
        "sentinel_values": dict(sorted(pii_markers.items())),
        "scan_patterns": [
            "exact UTF-8 byte substring",
            "case-sensitive match under the caller-provided scan_root/**",
        ],
    }
    manifest: dict[str, Any] = {
        "format_version": 2,
        "dataset": definition.name,
        "seed": seed,
        "base_instant": definition.base_instant,
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "description": definition.description,
        "table_row_counts": {
            name: len(tables[name]) for name in sorted(definition.table_columns)
        },
        "applied_injectors": applied,
        "pii_markers": pii_markers,
        "pii_dictionary": pii_dictionary,
        "planted_orphan_values": orphan_values,
        "mutation": mutation_info,
        "file_hashes": file_hashes,
        "fixture_hash": _aggregate_fixture_hash(file_hashes),
    }
    if definition.source_tables:
        manifest["source_tables"] = {
            name: {
                "path": f"source/{name}.json",
                "row_count": len(tables[name]),
                "sha256": hashlib.sha256((source_dir / f"{name}.json").read_bytes()).hexdigest(),
            }
            for name in sorted(definition.source_tables)
        }
    manifest_path = destination / "fixture-manifest.json"
    _write_json(manifest_path, manifest)
    return GenerationResult(
        dataset=dataset_name,
        seed=seed,
        out_dir=destination,
        data_dir=data_dir,
        gold_dir=gold_dir,
        manifest_path=manifest_path,
        manifest=manifest,
    )


def generate(dataset_name: str, seed: int, out_dir: str | Path) -> GenerationResult:
    """Short alias for :func:`generate_dataset`."""

    return generate_dataset(dataset_name, seed, out_dir)


def verify_dataset(
    out_dir: str | Path,
    *,
    dataset: str | None = None,
    seed: int | None = None,
    allow_mutation: bool = False,
) -> bool:
    """Re-derive a fixture and fail if its data or gold bytes drifted."""

    destination = Path(out_dir)
    manifest_path = destination / "fixture-manifest.json"
    if not manifest_path.is_file():
        raise VerificationError(f"fixture manifest is missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual_dataset = manifest.get("dataset")
    actual_seed = manifest.get("seed")
    if dataset is not None and dataset != actual_dataset:
        raise VerificationError(f"manifest dataset is {actual_dataset!r}, expected {dataset!r}")
    if seed is not None and seed != actual_seed:
        raise VerificationError(f"manifest seed is {actual_seed!r}, expected {seed!r}")
    if manifest.get("python_version") != platform.python_version():
        warnings.warn(
            "fixture interpreter version differs from the current interpreter; "
            "byte identity is not a cross-version guarantee",
            RuntimeWarning,
            stacklevel=2,
        )
    mutation = bool((manifest.get("mutation") or {}).get("enabled"))
    if mutation and not allow_mutation:
        raise VerificationError(
            "verification refuses mutation-enabled fixtures; pass allow_mutation=True"
        )
    with tempfile.TemporaryDirectory(prefix="dp-scenarios-verify-") as temporary:
        regenerated = generate_dataset(
            str(actual_dataset), int(actual_seed), temporary, mutation=mutation
        )
        for relative in ("data", "gold", "source"):
            target_snapshot = _snapshot_tree(destination / relative)
            fresh_snapshot = _snapshot_tree(regenerated.out_dir / relative)
            if target_snapshot != fresh_snapshot:
                target_keys = set(target_snapshot)
                fresh_keys = set(fresh_snapshot)
                added = sorted(fresh_keys - target_keys)
                removed = sorted(target_keys - fresh_keys)
                changed = sorted(
                    path for path in target_keys & fresh_keys
                    if target_snapshot[path] != fresh_snapshot[path]
                )
                raise VerificationError(
                    f"{relative} differs: added={added}, removed={removed}, changed={changed}"
                )
    if actual_dataset == "grain_trap":
        data_control = json.loads(
            (destination / "data/grain_trap_control.json").read_text(encoding="utf-8")
        )
        gold_control = json.loads(
            (destination / "gold/grain_trap_control.json").read_text(encoding="utf-8")
        )
        if data_control != gold_control:
            raise VerificationError("landable and gold control totals disagree")
    return True


def _snapshot_tree(path: Path) -> dict[str, bytes]:
    if not path.is_dir():
        return {}
    return {
        item.relative_to(path).as_posix(): item.read_bytes()
        for item in sorted(path.rglob("*"))
        if item.is_file()
    }


def mutate_dataset(dataset_name: str, seed: int, out_dir: str | Path) -> GenerationResult:
    """Generate a deliberate PII leak for validating the PII oracle."""

    return generate_dataset(dataset_name, seed, out_dir, mutation=True)


generate_fixture = generate_dataset


__all__ = [
    "GenerationResult",
    "VerificationError",
    "find_nondeterministic_sources",
    "generate",
    "generate_dataset",
    "generate_fixture",
    "mutate_dataset",
    "pii_promise_holds",
    "verify_dataset",
]
