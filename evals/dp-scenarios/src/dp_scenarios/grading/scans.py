"""Static and byte-exact route scans.

The scan invariant is fail-closed examination: every scan reports a stable code
and an empty sentinel set raises because examining no markers is not a clean
scan.  Source scans inspect mechanism, not whether a shortcut happened to
produce the expected answer.

Only the sentinel scan is wired into the tier runner.  The other four scans
remain public scenario APIs; exercising them directly does not imply that the
tier path invokes them.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
import re


@dataclass(frozen=True, slots=True)
class ScanFinding:
    """One stable scan finding."""

    code: str
    detail: str = ""
    value: object = None


@dataclass(frozen=True, slots=True)
class ScanResult:
    """Result of a scan, including whether the requested surface was read."""

    passed: bool
    code: str
    findings: tuple[ScanFinding, ...] = ()
    examined: bool = True

    @property
    def codes(self) -> tuple[str, ...]:
        return tuple(finding.code for finding in self.findings)


class _SurfaceNotExamined(ValueError):
    """Raised when a requested byte surface cannot be read."""


def _result(passed: bool, code: str, findings: Iterable[ScanFinding] = (), *, examined: bool = True) -> ScanResult:
    found = tuple(findings)
    return ScanResult(passed=passed and not found, code=code, findings=found, examined=examined)


def _python_files(closure: str | Path) -> list[Path]:
    root = Path(closure)
    if root.is_file():
        return [root] if root.suffix == ".py" else []
    return sorted(path for path in root.rglob("*.py") if path.is_file())


def _sanctioned(path: Path, sanctioned: object) -> bool:
    if sanctioned is None:
        return False
    if isinstance(sanctioned, (str, Path)):
        return path.resolve() == Path(sanctioned).resolve()
    if isinstance(sanctioned, Iterable):
        return any(_sanctioned(path, item) for item in sanctioned)
    return False


def supported_path_scan(closure: str | Path, *, sanctioned_client: object = None) -> ScanResult:
    """Reject direct HTTP/socket imports outside a sanctioned client module."""

    forbidden_roots = {
        "aiohttp",
        "curl_cffi",
        "http",
        "http.client",
        "httpcore",
        "httplib2",
        "httpx",
        "pycurl",
        "requests",
        "socket",
        "urllib",
        "urllib3",
        "websocket",
        "websockets",
    }

    def forbidden(module: str) -> bool:
        return any(module == root or module.startswith(root + ".") for root in forbidden_roots)

    def string_literals(node: ast.AST) -> list[str]:
        return [item.value for item in ast.walk(node) if isinstance(item, ast.Constant) and isinstance(item.value, str)]

    def import_call_module(node: ast.Call) -> str | None:
        function = node.func
        if isinstance(function, ast.Name) and function.id == "__import__":
            return node.args[0].value if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str) else None
        if isinstance(function, ast.Attribute) and function.attr == "import_module":
            return node.args[0].value if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str) else None
        if isinstance(function, ast.Name) and function.id == "import_module":
            return node.args[0].value if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str) else None
        if isinstance(function, ast.Call) and isinstance(function.func, ast.Name) and function.func.id == "getattr":
            names = string_literals(function)
            if len(function.args) >= 2 and isinstance(function.args[1], ast.Constant) and function.args[1].value in {"__import__", "import_module"}:
                return node.args[0].value if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str) else None
            if names and any(forbidden(name) for name in names):
                return next((name for name in names if forbidden(name)), None)
        return None

    def calls_curl(node: ast.Call) -> bool:
        function = node.func
        if not isinstance(function, ast.Attribute) or not isinstance(function.value, ast.Name):
            return False
        if function.value.id not in {"os", "subprocess"}:
            return False
        if function.attr not in {"check_call", "check_output", "popen", "run", "system", "Popen"}:
            return False
        if any("curl" in literal.lower() for literal in string_literals(node)):
            return True
        return function.value.id == "subprocess" and any(
            keyword.arg == "shell" and isinstance(keyword.value, ast.Constant) and keyword.value.value is True
            for keyword in node.keywords
        )

    findings: list[ScanFinding] = []
    files = _python_files(closure)
    for path in files:
        if _sanctioned(path, sanctioned_client):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, UnicodeError, SyntaxError) as exc:
            findings.append(ScanFinding("supported_path_scan_error", str(exc), str(path)))
            continue
        for node in ast.walk(tree):
            imported: str | None = None
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported = alias.name
                    if forbidden(imported):
                        findings.append(ScanFinding("supported_path_direct_http", f"direct HTTP import in {path.name}", imported))
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported = node.module
                if forbidden(imported):
                    findings.append(ScanFinding("supported_path_direct_http", f"direct HTTP import in {path.name}", imported))
            elif isinstance(node, ast.Call):
                imported = import_call_module(node)
                if imported is not None and forbidden(imported):
                    findings.append(ScanFinding("supported_path_direct_http", f"dynamic direct HTTP import in {path.name}", imported))
                if calls_curl(node):
                    findings.append(ScanFinding("supported_path_direct_http", f"subprocess curl call in {path.name}"))
    return _result(not findings and bool(files), "supported_path_clear", findings or ([ScanFinding("supported_path_not_examined", "closure has no Python files")] if not files else []), examined=bool(files))


def _trace_entry(entry: object) -> tuple[int | None, str, str]:
    if isinstance(entry, Mapping):
        turn = entry.get("turn")
        kind = str(entry.get("kind", entry.get("tool", entry.get("type", ""))))
        text = entry.get("input", entry.get("command", entry.get("code", entry.get("text", ""))))
        return turn if isinstance(turn, int) else None, kind, str(text)
    return None, "", str(entry)


def governed_path_scan(trace: Sequence[object], *, question_turn: int | None = None, answer_turn: int | None = None) -> ScanResult:
    """Reject aggregation in executable tools between question and answer.

    Narration is not executable evidence.  Only shell, bash, Python, and exec
    entries are inspected, while governed-query entries remain the sanctioned
    route for aggregation.
    """

    entries = [_trace_entry(entry) for entry in trace]
    turns = [turn for turn, _kind, _text in entries if turn is not None]
    lo = question_turn if question_turn is not None else (min(turns) if turns else None)
    hi = answer_turn if answer_turn is not None else (max(turns) if turns else None)
    if lo is None or hi is None:
        return _result(False, "governed_path_not_examined", [ScanFinding("governed_path_not_examined", "trace has no bounded question and answer turns")], examined=False)
    markers = (re.compile(r"\bGROUP\s+BY\b", re.I), re.compile(r"\bgroupby\s*\(", re.I), re.compile(r"\bawk\b", re.I), re.compile(r"\bsum\s*\(", re.I))
    executable_kinds = {"shell", "bash", "python", "exec"}
    findings: list[ScanFinding] = []
    for turn, kind, text in entries:
        if turn is None or not lo <= turn <= hi:
            continue
        kind_lower = kind.lower()
        governed = kind_lower in {"query", "governed_query", "semantic_query", "nxd_query"} or "governed" in kind_lower
        if governed:
            continue
        if kind_lower not in executable_kinds:
            continue
        for marker in markers:
            if marker.search(text):
                findings.append(ScanFinding("governed_path_aggregation_outside_query", f"aggregation outside governed query at turn {turn}", {"turn": turn, "text": text}))
                break
    return _result(not findings, "governed_path_clear", findings)


def meaning_preserving_bounding_scan(transform: str | Path) -> ScanResult:
    """Reject truncation operators applied in a transform/source path."""

    path = Path(transform)
    try:
        source = path.read_text(encoding="utf-8") if path.exists() else str(transform)
    except (OSError, UnicodeError) as exc:
        return _result(False, "bounding_scan_not_examined", [ScanFinding("bounding_scan_not_examined", str(exc))], examined=False)
    patterns = (
        (re.compile(r"\bLIMIT\b", re.I), "limit"),
        (re.compile(r"\bhead\s*\(", re.I), "head"),
    )
    findings = [ScanFinding("meaning_preserving_bounding", f"source bounding operator found: {name}", name) for pattern, name in patterns if pattern.search(source)]
    try:
        tree = ast.parse(source)
    except SyntaxError:
        tree = None
    if tree is not None:
        iterator_helpers = {"islice"}
        itertools_modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "itertools":
                for alias in node.names:
                    if alias.name == "islice":
                        iterator_helpers.add(alias.asname or alias.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "itertools":
                        itertools_modules.add(alias.asname or alias.name)

        def is_iterator_helper_call(node: ast.Call) -> bool:
            function = node.func
            if isinstance(function, ast.Name):
                return function.id in iterator_helpers
            return (
                isinstance(function, ast.Attribute)
                and function.attr == "islice"
                and isinstance(function.value, ast.Name)
                and function.value.id in itertools_modules
            )

        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and is_iterator_helper_call(node):
                findings.append(ScanFinding("meaning_preserving_bounding", "source bounding operator found: islice", ast.unparse(node)))
                continue
            if isinstance(node, ast.Subscript) and any(isinstance(item, ast.Slice) for item in ast.walk(node.slice)):
                findings.append(ScanFinding("meaning_preserving_bounding", "source bounding operator found: slice", ast.unparse(node)))
    return _result(not findings, "bounding_scan_clear", findings)


def _surface_bytes(surface: object) -> bytes:
    if surface is None:
        raise _SurfaceNotExamined("surface is null")
    if isinstance(surface, Path):
        path = surface
        if path.is_file():
            try:
                content = path.read_bytes()
            except (OSError, UnicodeError) as exc:
                raise _SurfaceNotExamined(str(exc)) from exc
            if not content:
                raise _SurfaceNotExamined("file is empty")
            return content
        if path.is_dir():
            chunks: list[bytes] = []
            try:
                children = sorted(path.rglob("*"))
            except OSError as exc:
                raise _SurfaceNotExamined(str(exc)) from exc
            for child in children:
                if child.is_file():
                    try:
                        chunks.append(child.read_bytes())
                    except (OSError, UnicodeError) as exc:
                        raise _SurfaceNotExamined(str(exc)) from exc
            if not chunks:
                raise _SurfaceNotExamined("directory has no readable files")
            return b"\n".join(chunks)
        raise _SurfaceNotExamined("path does not resolve to a readable file or non-empty directory")
    if isinstance(surface, bytes):
        if not surface.strip():
            raise _SurfaceNotExamined("content surface is empty")
        return surface
    if isinstance(surface, bytearray):
        content = bytes(surface)
        if not content.strip():
            raise _SurfaceNotExamined("content surface is empty")
        return content
    if isinstance(surface, str):
        if not surface.strip():
            raise _SurfaceNotExamined("content surface is empty")
        return surface.encode("utf-8")
    if isinstance(surface, (Mapping, list, tuple)):
        import json
        return json.dumps(surface, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return str(surface).encode("utf-8")


def sentinel_byte_scan(surfaces: Mapping[str, object] | Iterable[object], markers: Iterable[bytes | str]) -> ScanResult:
    """Search all supplied surfaces for exact marker bytes.

    No case folding, Unicode normalization, or input re-encoding is performed
    for byte surfaces.  Text/object surfaces are encoded only to make their
    already-supplied representation searchable.
    """

    marker_bytes = {marker if isinstance(marker, bytes) else marker.encode("utf-8") for marker in markers}
    if not marker_bytes or any(not marker for marker in marker_bytes):
        raise ValueError("sentinel marker set must be non-empty")
    surface_items = list(surfaces.items()) if isinstance(surfaces, Mapping) else [(str(index), value) for index, value in enumerate(surfaces)]
    findings: list[ScanFinding] = []
    if not surface_items:
        findings.append(ScanFinding("sentinel_surface_not_examined", "no sentinel surfaces were supplied"))
    for name, surface in surface_items:
        try:
            content = _surface_bytes(surface)
        except (_SurfaceNotExamined, OSError, UnicodeError, TypeError, ValueError) as exc:
            findings.append(ScanFinding("sentinel_surface_not_examined", f"surface {name} was not examined: {exc}", name))
            continue
        for marker in sorted(marker_bytes):
            if marker in content:
                findings.append(ScanFinding("sentinel_byte_found", f"sentinel found in {name}", {"surface": name, "marker": marker}))
    not_examined = any(finding.code == "sentinel_surface_not_examined" for finding in findings)
    return _result(not findings, "sentinel_scan_not_examined" if not_examined else "sentinel_scan_clear", findings, examined=not not_examined)


def gold_access_scan(observations: object, oracle_dir: str | Path) -> ScanResult:
    """Fail closed when structured session evidence addresses protected gold data."""

    oracle = Path(oracle_dir).resolve()
    oracle_name = oracle.name.casefold()
    turns: object = observations
    if isinstance(observations, Mapping):
        turns = observations.get("turns", observations.get("observations", observations))
    if not isinstance(turns, Sequence) or isinstance(turns, (str, bytes, bytearray)):
        return _result(False, "gold_access_not_examined", [ScanFinding("gold_access_not_examined", "structured observations are absent")], examined=False)
    findings: list[ScanFinding] = []

    def inspect_path(value: object, location: str) -> None:
        """Inspect one path-shaped value, never arbitrary file content."""

        if isinstance(value, Path):
            value = str(value)
        if not isinstance(value, str):
            return
        candidate = value.strip()
        if not candidate or ("/" not in candidate and "\\" not in candidate):
            return

        try:
            raw_path = Path(candidate).expanduser()
        except (OSError, RuntimeError, ValueError):
            raw_path = None
        if raw_path is None:
            return
        candidates = [raw_path]
        if not raw_path.is_absolute():
            # Relative tool paths are evaluated from the agent workspace.  The
            # parent fallback covers callers whose working directory is the
            # run root rather than its ``agent`` child.
            candidates.extend(
                (
                    oracle.parent / "agent" / raw_path,
                    oracle.parent / raw_path,
                )
            )
        for path in candidates:
            try:
                resolved = path.resolve()
            except (OSError, RuntimeError, ValueError):
                continue
            try:
                resolved.relative_to(oracle)
            except ValueError:
                continue
            findings.append(
                ScanFinding(
                    "gold_access_attempt",
                    "structured session evidence addressed the oracle directory",
                    {"path": location, "value": candidate},
                )
            )
            return

        # Keep the lexical fallback tied to this run's protected directory.
        # A bare ``gold`` segment is ordinary medallion-layer vocabulary and is
        # not evidence that the harness oracle was addressed.
        #
        # The fallback also only applies to a path that tries to leave the
        # agent workspace. Every candidate above already failed containment,
        # so a workspace-relative path with no upward traversal cannot reach
        # the oracle however it is spelled -- and "oracle" is an ordinary
        # source-system name, so `sources/oracle/customers.yml` would
        # otherwise take an unappealable automatic zero for authoring a file
        # about an Oracle database.
        raw_segments = candidate.replace("\\", "/").split("/")
        segments = [segment.casefold() for segment in raw_segments if segment not in {"", "."}]
        # ``..`` is matched textually, not as a whole segment: a command string
        # like ``cat ../oracle/gold/answer.json`` splits into a first segment of
        # ``cat ..``, so a segment-equality test would miss the very shape this
        # fallback exists to catch.
        escapes_workspace = raw_path.is_absolute() or ".." in candidate
        if escapes_workspace and oracle_name in segments:
            findings.append(
                ScanFinding(
                    "gold_access_attempt",
                    "structured session evidence contained a protected oracle path",
                    {"path": location, "value": candidate},
                )
            )

    def inspect_call_arguments(value: object, location: str) -> None:
        """Inspect path-bearing tool arguments while skipping prose/content."""

        path_keys = {
            "path",
            "file",
            "file_path",
            "filepath",
            "filename",
            "directory",
            "dir",
            "cwd",
            "workdir",
            "working_directory",
            "command",
            "cmd",
            "script_path",
            "input_path",
            "output_path",
            "artifact_path",
            "definition_dir",
        }
        # Prose and payload keys: scanning them is the sentinel scan's job, and
        # treating file content as a path is what made this gate fire on
        # ordinary medallion-layer names. NOTE: ``query``/``sql``/``data`` are
        # the one skip that could hide a genuine read -- SQL engines address
        # files directly, e.g. ``read_json('../oracle/gold/answer.json')``. No
        # tool on the current agent surface takes a file-capable query
        # argument (Bash's path arrives under ``command``), but adding one to
        # ``desktop_allowed_tools`` would open a real gap in an
        # automatic-zero gate.
        ignored_keys = {
            "content",
            "text",
            "body",
            "prompt",
            "message",
            "data",
            "query",
            "sql",
            "value",
            "result",
            "response",
        }
        if isinstance(value, Mapping):
            for key, item in value.items():
                key_name = str(key).casefold()
                item_location = f"{location}.{key}"
                if key_name in path_keys:
                    # Recurse rather than calling inspect_path directly: a
                    # container under a path key (``command: ["cat", "..."]``)
                    # would otherwise be dropped, while the same value under an
                    # unlisted key would be walked and caught.
                    inspect_call_arguments(item, item_location)
                elif key_name not in ignored_keys:
                    inspect_call_arguments(item, item_location)
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            for index, item in enumerate(value):
                inspect_call_arguments(item, f"{location}[{index}]")
        else:
            inspect_path(value, location)

    for index, turn in enumerate(turns):
        if isinstance(turn, Mapping):
            tool_calls = turn.get("tool_calls", ())
            if isinstance(tool_calls, Sequence) and not isinstance(tool_calls, (str, bytes, bytearray)):
                for call_index, call in enumerate(tool_calls):
                    if isinstance(call, Mapping):
                        inspect_call_arguments(
                            call.get("arguments", ()),
                            f"turns[{index}].tool_calls[{call_index}].arguments",
                        )
            files_touched = turn.get("files_touched", ())
            if isinstance(files_touched, Sequence) and not isinstance(files_touched, (str, bytes, bytearray)):
                for file_index, file in enumerate(files_touched):
                    if isinstance(file, Mapping):
                        inspect_path(
                            file.get("path"),
                            f"turns[{index}].files_touched[{file_index}].path",
                        )
    return _result(not findings, "gold_access_clear", findings)


def _metric_names_for_proxy(spec: Mapping[str, object]) -> set[str]:
    raw = spec.get("metrics")
    if isinstance(raw, Mapping):
        return {str(name) for name in raw}
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray)):
        return {
            str(item.get("name", item.get("metric"))) if isinstance(item, Mapping) else str(item)
            for item in raw
        }
    return set()


def proxy_labelling_scan(
    spec: object,
    catalog_description: str,
    capability: object,
    metric: str | None = None,
    *,
    marker: str | bytes | None = None,
    metric_name: str | None = None,
) -> ScanResult:
    """Verify a controlled proxy marker is present and capability-labelled."""

    if marker is None:
        if isinstance(spec, Mapping):
            marker = spec.get("proxy_marker", spec.get("controlled_marker"))
        if marker is None and isinstance(capability, Mapping):
            marker = capability.get("proxy_marker", capability.get("controlled_marker"))
    if not isinstance(marker, (str, bytes)) or not marker:
        return _result(False, "proxy_labelling_not_examined", [ScanFinding("proxy_labelling_not_examined", "controlled marker is absent")], examined=False)
    needle = marker if isinstance(marker, str) else marker.decode("utf-8", errors="strict")
    try:
        spec_bytes = _surface_bytes(spec)
    except (_SurfaceNotExamined, OSError, UnicodeError, TypeError, ValueError) as exc:
        return _result(False, "proxy_labelling_not_examined", [ScanFinding("proxy_labelling_not_examined", f"spec was not examined: {exc}")], examined=False)
    catalog_bytes = catalog_description.encode("utf-8")
    labels = capability.metrics if hasattr(capability, "metrics") else capability.get("metrics", {}) if isinstance(capability, Mapping) else {}
    target_metric = metric or metric_name
    if isinstance(spec, Mapping):
        for key in ("metric", "metric_name", "name"):
            if target_metric is None and isinstance(spec.get(key), str):
                target_metric = str(spec[key])
                break
        if target_metric is None:
            metric_names = _metric_names_for_proxy(spec)
            if len(metric_names) == 1:
                target_metric = next(iter(metric_names))
    if target_metric is None and isinstance(labels, Mapping) and len(labels) == 1:
        target_metric = str(next(iter(labels)))
    if target_metric is None:
        return _result(False, "proxy_labelling_not_examined", [ScanFinding("proxy_metric_not_examined", "metric under test is absent")], examined=False)
    labelled = isinstance(labels, Mapping) and labels.get(target_metric) == "proxy"
    findings: list[ScanFinding] = []
    if needle.encode("utf-8") not in spec_bytes:
        findings.append(ScanFinding("proxy_marker_missing_from_spec", "controlled marker is absent from spec", needle))
    if needle.encode("utf-8") not in catalog_bytes:
        findings.append(ScanFinding("proxy_marker_missing_from_catalog", "controlled marker is absent from catalog description", needle))
    if not labelled:
        findings.append(ScanFinding("proxy_capability_label_missing", "capability manifest has no proxy classification", needle))
    return _result(not findings, "proxy_labelling_clear", findings)


scan_supported_path = supported_path_scan
scan_governed_path = governed_path_scan
scan_bounding = meaning_preserving_bounding_scan
scan_sentinels = sentinel_byte_scan
scan_proxy_labelling = proxy_labelling_scan


__all__ = [
    "ScanFinding",
    "ScanResult",
    "supported_path_scan",
    "governed_path_scan",
    "meaning_preserving_bounding_scan",
    "sentinel_byte_scan",
    "gold_access_scan",
    "proxy_labelling_scan",
    "scan_supported_path",
    "scan_governed_path",
    "scan_bounding",
    "scan_sentinels",
    "scan_proxy_labelling",
]
