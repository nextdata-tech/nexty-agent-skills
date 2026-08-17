#!/usr/bin/env python3
"""Record and index benchmark evidence without rewriting the frozen ledger.

Measured runs create a compact JSON report in ``evals/benchmarks/records/`` and
a matching human-readable entry in ``evals/benchmarks/entries/``.  The generated
``evals/benchmarks/README.md`` is an index of those new entries.  The historical
``ledger.md`` and its pre-migration records are deliberately never read or
modified by this script.

Use ``--rebuild-index`` after hand-authoring a ``NO_EVAL`` entry, and use
``--check`` in CI to verify both entry validity and index freshness.  This file
uses only the Python standard library.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
BENCH_DIR = REPO_ROOT / "evals" / "benchmarks"
ENTRIES_DIR = BENCH_DIR / "entries"
RECORDS_DIR = BENCH_DIR / "records"
INDEX = BENCH_DIR / "README.md"
PLUGIN_MANIFEST = REPO_ROOT / ".claude-plugin" / "plugin.json"

MISSING = "—"
ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SEMVER_RE = re.compile(r"^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)$")
MAX_SLUG_LENGTH = 60
MAX_ID_LENGTH = 71  # YYYY-MM-DD- plus the historical 60-character label slug.
UNICODE_LINE_SEPARATORS = ("\u0085", "\u2028", "\u2029")
FRONTMATTER_KEYS = (
    "id", "date", "label", "plugin_version", "status", "scenarios", "record",
)
MEASURED_STATUSES = {"PASS", "FAIL", "ERROR", "MIXED"}


class BenchmarkError(ValueError):
    """A user-facing benchmark evidence validation error."""


@dataclass(frozen=True)
class Entry:
    path: Path
    frontmatter: dict[str, Any]
    body: str


def parse_report_arg(spec: str) -> tuple[str, Path]:
    """Split ``tag=path`` (or bare ``path``) into ``(tag, path)``."""
    tag, sep, path = spec.partition("=")
    if not sep:
        return "", Path(spec)
    return tag.strip(), Path(path.strip())


def validate_date(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise BenchmarkError(f"invalid date {value!r}; expected YYYY-MM-DD")
    try:
        return dt.date.fromisoformat(value).isoformat()
    except (TypeError, ValueError) as exc:
        raise BenchmarkError(f"invalid date {value!r}; expected YYYY-MM-DD") from exc


def validate_id(value: str) -> str:
    if (not isinstance(value, str) or len(value) > MAX_ID_LENGTH
            or not ID_RE.fullmatch(value)):
        raise BenchmarkError(
            f"id must be a lowercase hyphenated slug no longer than {MAX_ID_LENGTH} characters"
        )
    return value


def validate_semver(value: Any, field: str = "plugin_version") -> str:
    if not isinstance(value, str) or not SEMVER_RE.fullmatch(value):
        raise BenchmarkError(f"{field} must be a semver X.Y.Z string")
    return value


def yaml_quote(value: str) -> str:
    """Emit a YAML-safe scalar using JSON's compatible double-quoted syntax."""
    # ASCII escapes keep U+0085/U+2028/U+2029 inside a scalar. ``splitlines``
    # treats all three as line breaks, so literal output would not round-trip.
    return json.dumps(value, ensure_ascii=True)


def yaml_scalar(value: str) -> Any:
    value = value.strip()
    if value == "null":
        return None
    if value.startswith('"'):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise BenchmarkError(f"invalid quoted YAML scalar {value!r}") from exc
        if not isinstance(parsed, str):
            raise BenchmarkError("frontmatter scalar must be a string or null")
        return parsed
    if not value or value.startswith(("'", "[", "{", "- ")):
        raise BenchmarkError(f"unsupported YAML scalar {value!r}; use a quoted string")
    return value


def write_frontmatter(values: dict[str, Any]) -> str:
    """Write the deliberately small, stdlib-only YAML frontmatter subset."""
    if set(values) != set(FRONTMATTER_KEYS):
        raise BenchmarkError("writer received unexpected frontmatter keys")
    lines = ["---"]
    for key in FRONTMATTER_KEYS:
        value = values[key]
        if key == "scenarios":
            if not value:
                lines.append("scenarios: []")
            else:
                lines.append("scenarios:")
                for scenario in value:
                    lines.append(f"  - {yaml_quote(scenario)}")
        elif value is None:
            lines.append(f"{key}: null")
        else:
            lines.append(f"{key}: {yaml_quote(str(value))}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Parse the restricted YAML used by benchmark entries, without PyYAML."""
    if not text.startswith("---\n"):
        raise BenchmarkError("entry must start with YAML frontmatter")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise BenchmarkError("entry frontmatter is missing its closing ---")
    raw, body = text[4:end], text[end + 5:]
    if any(separator in raw for separator in UNICODE_LINE_SEPARATORS):
        raise BenchmarkError("frontmatter must escape Unicode line separators")
    values: dict[str, Any] = {}
    lines = raw.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line or line.startswith(" ") or ":" not in line:
            raise BenchmarkError(f"malformed frontmatter line {line!r}")
        key, value = line.split(":", 1)
        if key not in FRONTMATTER_KEYS:
            raise BenchmarkError(f"unknown frontmatter field {key!r}")
        if key in values:
            raise BenchmarkError(f"duplicate frontmatter field {key!r}")
        if key == "scenarios":
            if value.strip() == "[]":
                values[key] = []
                index += 1
                continue
            if value.strip():
                raise BenchmarkError("scenarios must be a YAML list")
            scenarios: list[str] = []
            index += 1
            while index < len(lines) and lines[index].startswith("  - "):
                scenario = yaml_scalar(lines[index][4:])
                if not isinstance(scenario, str):
                    raise BenchmarkError("scenario names must be strings")
                scenarios.append(scenario)
                index += 1
            values[key] = scenarios
            continue
        values[key] = yaml_scalar(value)
        index += 1
    missing = set(FRONTMATTER_KEYS) - set(values)
    if missing:
        raise BenchmarkError("missing required frontmatter fields: " + ", ".join(sorted(missing)))
    return values, body


def escape_cell(value: Any) -> str:
    """Keep generated Markdown tables valid even when reports contain odd text."""
    text = str(value)
    return (text.replace("\\", "\\\\").replace("|", "\\|")
            .replace("\r\n", "<br>").replace("\r", "<br>").replace("\n", "<br>")
            .replace("\u0085", "<br>").replace("\u2028", "<br>").replace("\u2029", "<br>"))


def cell_rows(tag: str, report: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(report, dict):
        raise BenchmarkError("report must be a JSON object")
    results = report.get("results", [])
    if not isinstance(results, list):
        raise BenchmarkError("report results must be a list")
    rows = []
    for res in results:
        if not isinstance(res, dict):
            raise BenchmarkError("report result must be an object")
        verdict = res.get("verdict", {}) or {}
        metrics = res.get("metrics", {}) or {}
        if not isinstance(verdict, dict) or not isinstance(metrics, dict):
            raise BenchmarkError("report verdict and metrics must be objects")
        checks = verdict.get("checks", []) or []
        if not isinstance(checks, list) or any(not isinstance(check, dict) for check in checks):
            raise BenchmarkError("report verdict checks must be a list of objects")
        n_pass = sum(1 for check in checks if check.get("pass"))
        if not res.get("ok"):
            status = "ERROR"
        else:
            status = "PASS" if verdict.get("overall_pass") else "FAIL"
        cost = metrics.get("total_cost_usd")
        rows.append({
            "tag": tag or MISSING,
            "skill_set": res.get("skill_set", MISSING),
            "scenario": res.get("scenario", MISSING),
            "status": status,
            "checks": f"{n_pass}/{len(checks)}" if checks else MISSING,
            "num_turns": metrics.get("num_turns", MISSING),
            "tool_calls": metrics.get("tool_calls", MISSING),
            "output_tokens": metrics.get("output_tokens", MISSING),
            "cost_usd": f"{cost:.2f}" if isinstance(cost, (int, float)) else MISSING,
            # A desktop-path scenario can pin a model per run, so report-level
            # metadata is only a fallback.
            "agent_model": metrics.get("agent_model", report.get("agent_model", MISSING)),
        })
    return rows


_OPERATOR_PATH_RE = re.compile(r"/(?:Users|home)/[^/\s\"']+")


def redact_operator_paths(value: Any) -> Any:
    """Remove local home paths from compact evidence before it is committed."""
    if isinstance(value, str):
        return _OPERATOR_PATH_RE.sub("<operator-home>", value)
    if isinstance(value, dict):
        return {key: redact_operator_paths(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_operator_paths(item) for item in value]
    return value


def compact_report(report: dict[str, Any]) -> dict[str, Any]:
    """Strip transcripts/final answers so compact records stay reviewable."""
    slim = {key: value for key, value in report.items() if key != "results"}
    slim["results"] = []
    for res in report.get("results", []):
        result = {key: value for key, value in res.items() if key != "transcript"}
        metrics = dict(result.get("metrics", {}) or {})
        metrics.pop("final_answer", None)
        result["metrics"] = metrics
        slim["results"].append(result)
    return redact_operator_paths(slim)


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:MAX_SLUG_LENGTH] or "benchmark"


def status_for(rows: list[dict[str, Any]]) -> str:
    statuses = {row["status"] for row in rows}
    return next(iter(statuses)) if len(statuses) == 1 else "MIXED"


def table_for(rows: list[dict[str, Any]]) -> str:
    header = ("| run | skill-set | scenario | verdict | checks | turns | tool_calls | "
              "out_tokens | cost_usd | agent |\n"
              "|---|---|---|---|---|---|---|---|---|---|")
    rendered = []
    for row in rows:
        rendered.append("| " + " | ".join(escape_cell(row[key]) for key in (
            "tag", "skill_set", "scenario", "status", "checks", "num_turns",
            "tool_calls", "output_tokens", "cost_usd", "agent_model",
        )) + " |")
    return header + "\n" + "\n".join(rendered)


def entry_text(frontmatter: dict[str, Any], rows: list[dict[str, Any]], notes: str) -> str:
    record = frontmatter["record"]
    title = re.sub(r"[\r\n\u0085\u2028\u2029]+", " ", str(frontmatter["label"]))
    rendered_notes = re.sub(r"\r\n?|[\u0085\u2028\u2029]", "\n", notes.strip())
    return (
        write_frontmatter(frontmatter)
        + f"# Benchmark — {title}\n\n"
        + "## Results\n\n"
        + table_for(rows)
        + "\n\n## Notes\n\n"
        + (rendered_notes or "Measured benchmark evidence.")
        + "\n\n## Evidence\n\n"
        + f"Compact report: [`{record}`]({record})\n"
    )


def read_plugin_version() -> str:
    try:
        value = json.loads(PLUGIN_MANIFEST.read_text(encoding="utf-8")).get("version")
    except (OSError, json.JSONDecodeError) as exc:
        raise BenchmarkError(f"cannot read plugin version: {exc}") from exc
    return validate_semver(value, "plugin manifest version")


def parse_entry(path: Path) -> Entry:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise BenchmarkError(f"cannot read entry {path}: {exc}") from exc
    frontmatter, body = parse_frontmatter(text)
    return Entry(path, frontmatter, body)


def record_rows(record: dict[str, Any]) -> list[dict[str, Any]]:
    reports = record.get("reports")
    if not isinstance(reports, dict) or not reports:
        raise BenchmarkError("measured record must contain non-empty reports")
    report_tags = record.get("report_tags")
    if not isinstance(report_tags, dict) or set(report_tags) != set(reports):
        raise BenchmarkError("measured record must map every report to its display tag")
    rows: list[dict[str, Any]] = []
    for tag, report in reports.items():
        display_tag = report_tags[tag]
        if (not isinstance(tag, str) or not isinstance(display_tag, str)
                or not isinstance(report, dict)):
            raise BenchmarkError("measured record reports must map strings to objects")
        rows.extend(cell_rows(display_tag, report))
    if not rows:
        raise BenchmarkError("measured record reports contain no result cells")
    return rows


def section(body: str, heading: str) -> str:
    match = re.search(rf"^## {re.escape(heading)}[ \t]*$\n(.*?)(?=^## |\Z)", body, re.M | re.S)
    return match.group(1).strip() if match else ""


def validate_entry(entry: Entry, seen_ids: set[str] | None = None,
                   record_override: dict[str, Any] | None = None) -> Entry:
    fm = entry.frontmatter
    if set(fm) != set(FRONTMATTER_KEYS):
        raise BenchmarkError(f"{entry.path}: malformed frontmatter fields")
    identifier = validate_id(fm["id"])
    if entry.path.stem != identifier:
        raise BenchmarkError(f"{entry.path}: filename stem must equal id")
    if seen_ids is not None:
        if identifier in seen_ids:
            raise BenchmarkError(f"duplicate benchmark id {identifier!r}")
        seen_ids.add(identifier)
    validate_date(fm["date"])
    if not isinstance(fm["label"], str) or not fm["label"].strip():
        raise BenchmarkError(f"{entry.path}: label is required")
    try:
        validate_semver(fm["plugin_version"])
    except BenchmarkError as exc:
        raise BenchmarkError(f"{entry.path}: {exc}") from exc
    if not isinstance(fm["scenarios"], list) or any(not isinstance(v, str) or not v for v in fm["scenarios"]):
        raise BenchmarkError(f"{entry.path}: scenarios must be a list of names")
    if len(set(fm["scenarios"])) != len(fm["scenarios"]):
        raise BenchmarkError(f"{entry.path}: scenarios contains duplicates")
    if not entry.body.startswith("# Benchmark — ") or not section(entry.body, "Notes") or not section(entry.body, "Evidence"):
        raise BenchmarkError(f"{entry.path}: body must contain title, Notes, and Evidence")

    if fm["status"] == "NO_EVAL":
        if fm["scenarios"] or fm["record"] is not None:
            raise BenchmarkError(f"{entry.path}: NO_EVAL requires scenarios: [] and record: null")
        notes = section(entry.body, "Notes").lower()
        evidence = section(entry.body, "Evidence")
        if not ("no" in notes and any(term in notes for term in ("arm", "scenario", "eval"))):
            raise BenchmarkError(f"{entry.path}: NO_EVAL notes must explain why there is no eval arm")
        test_paths = re.findall(r"(?<![\w.-])((?:[A-Za-z0-9_.-]+/)*test_[A-Za-z0-9_.-]+\.py)(?![\w.-])", evidence)
        if not test_paths:
            raise BenchmarkError(f"{entry.path}: NO_EVAL evidence must name a carrying test file path")
        for test_path in test_paths:
            relative = Path(test_path)
            if relative.is_absolute() or any(part in {".", ".."} for part in relative.parts):
                raise BenchmarkError(f"{entry.path}: NO_EVAL test path must stay inside the repository")
            candidate = (REPO_ROOT / relative).resolve()
            try:
                candidate.relative_to(REPO_ROOT.resolve())
            except ValueError as exc:
                raise BenchmarkError(f"{entry.path}: NO_EVAL test path escapes the repository") from exc
            if not candidate.is_file():
                raise BenchmarkError(f"{entry.path}: NO_EVAL evidence names missing test file {test_path!r}")
        return entry

    if fm["status"] not in MEASURED_STATUSES:
        raise BenchmarkError(f"{entry.path}: invalid measured status {fm['status']!r}")
    expected_record = f"../records/{identifier}.json"
    if fm["record"] != expected_record:
        raise BenchmarkError(f"{entry.path}: record must be {expected_record!r}")
    record_path = entry.path.parent / fm["record"]
    if record_override is None:
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise BenchmarkError(f"{entry.path}: bad or missing record link: {exc}") from exc
    else:
        record = record_override
    if not isinstance(record, dict):
        raise BenchmarkError(f"{entry.path}: record must be a JSON object")
    for key in ("id", "date", "label", "plugin_version"):
        if record.get(key) != fm[key]:
            raise BenchmarkError(f"{entry.path}: record {key!r} does not match entry")
    if not isinstance(record.get("notes"), str):
        raise BenchmarkError(f"{entry.path}: measured record notes must be a string")
    rows = record_rows(record)
    scenarios = sorted({str(row["scenario"]) for row in rows})
    if fm["scenarios"] != scenarios:
        raise BenchmarkError(f"{entry.path}: scenarios do not match record results")
    if fm["status"] != status_for(rows):
        raise BenchmarkError(f"{entry.path}: status does not match record results")
    expected_text = entry_text(fm, rows, record["notes"])
    _, expected_body = parse_frontmatter(expected_text)
    if entry.body != expected_body:
        raise BenchmarkError(
            f"{entry.path}: measured Markdown body must be the canonical rendering of its JSON record"
        )
    return entry


def load_entries(extra: Entry | None = None, extra_record: dict[str, Any] | None = None,
                 skip_path: Path | None = None) -> list[Entry]:
    entries: list[Entry] = []
    seen_ids: set[str] = set()
    if ENTRIES_DIR.exists():
        for path in sorted(ENTRIES_DIR.glob("*.md")):
            if skip_path is not None and path == skip_path:
                continue
            entries.append(validate_entry(parse_entry(path), seen_ids))
    if extra is not None:
        entries.append(validate_entry(extra, seen_ids, extra_record))
    return entries


def index_text(entries: list[Entry]) -> str:
    """Build a deterministic, newest-first index of post-migration entries."""
    ordered = sorted(entries, key=lambda item: (item.frontmatter["date"], item.frontmatter["id"]), reverse=True)
    lines = [
        "# Benchmark entries",
        "",
        "Generated by `evals/benchmark_record.py --rebuild-index`; do not edit manually.",
        "New measured evidence lives in `entries/` with compact JSON reports in `records/`.",
        "",
        "The pre-migration append-only history is frozen in [legacy `ledger.md`](ledger.md). "
        "Its existing records remain historical evidence and are not indexed here.",
        "",
        "| Date | Label | Status | Scenarios | Entry |",
        "|---|---|---|---|---|",
    ]
    for entry in ordered:
        fm = entry.frontmatter
        scenarios = ", ".join(escape_cell(item) for item in fm["scenarios"]) or MISSING
        lines.append(
            f"| {escape_cell(fm['date'])} | {escape_cell(fm['label'])} | {fm['status']} | "
            f"{scenarios} | [`{fm['id']}`](entries/{fm['id']}.md) |"
        )
    return "\n".join(lines) + "\n"


def identical_or_fail(targets: dict[Path, str]) -> None:
    """Collision preflight for immutable identity artifacts.

    The index is intentionally regenerated whenever the entry set changes; an
    entry or compact record is immutable once its ID has been claimed.
    """
    for path, content in targets.items():
        if path == INDEX:
            continue
        if path.exists() and path.read_text(encoding="utf-8") != content:
            raise BenchmarkError(f"refusing to overwrite existing benchmark artifact {path}")


def atomic_publish(staged: Path, path: Path, content: str) -> bool:
    """Publish a fully fsynced staged artifact as whole-or-absent final bytes.

    ``link`` atomically creates the final directory entry without replacing an
    existing one.  The final path therefore never points at a file still being
    written: SIGKILL can leave the staged file or no final file, but not a
    truncated final artifact.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = content.encode("utf-8")
    try:
        if staged.read_bytes() != payload:
            raise BenchmarkError(f"staged benchmark artifact differs from intended content: {staged}")
        os.link(staged, path)
    except FileExistsError:
        try:
            existing = path.read_bytes()
        except OSError as exc:
            raise BenchmarkError(f"cannot inspect concurrent benchmark artifact {path}: {exc}") from exc
        if existing != payload:
            raise BenchmarkError(f"refusing to overwrite existing benchmark artifact {path}")
        return False
    except OSError as exc:
        raise BenchmarkError(f"cannot publish benchmark artifact {path}: {exc}") from exc
    return True


def atomic_replace(path: Path, content: str) -> None:
    """Atomically publish a regenerated index without exposing a partial file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name = ""
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=f".{path.name}.", delete=False) as handle:
            temp_name = handle.name
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except OSError as exc:
        if temp_name:
            try:
                Path(temp_name).unlink()
            except OSError:
                pass
        raise BenchmarkError(f"cannot replace benchmark index {path}: {exc}") from exc


@contextlib.contextmanager
def index_lock():
    """Serialize publication with a POSIX lock released when a process dies.

    Unlike an ``O_EXCL`` lockfile, ``flock`` is released by the kernel on a
    catchable interrupt, SIGTERM, or SIGKILL.  A small persistent publication
    marker handles the separate problem of a process dying between two final
    artifact creations.
    """
    BENCH_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = BENCH_DIR / ".benchmark-index.lock"
    fd = os.open(lock_path, os.O_WRONLY | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        recover_pending_publication()
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass
        os.close(fd)


def publication_marker() -> Path:
    return BENCH_DIR / ".benchmark-publication.json"


def staging_dir() -> Path:
    return BENCH_DIR / ".benchmark-staging"


def sha256(content: str | bytes) -> str:
    payload = content.encode("utf-8") if isinstance(content, str) else content
    return hashlib.sha256(payload).hexdigest()


def cleanup_staged(identifier: str) -> None:
    for suffix in ("entry.md", "record.json"):
        try:
            (staging_dir() / f"{identifier}.{suffix}").unlink()
        except FileNotFoundError:
            pass


def cleanup_orphan_staging() -> None:
    stage = staging_dir()
    if not stage.exists():
        return
    for path in stage.iterdir():
        if path.is_file() and (path.name.endswith(".entry.md") or path.name.endswith(".record.json")):
            try:
                path.unlink()
            except OSError as exc:
                raise BenchmarkError(f"cannot clear stale benchmark staging artifact {path}: {exc}") from exc


def load_pending_marker() -> dict[str, Any] | None:
    marker = publication_marker()
    if not marker.exists():
        return None
    try:
        value = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BenchmarkError(f"cannot recover malformed benchmark publication marker: {exc}") from exc
    if not isinstance(value, dict) or value.get("schema") != "benchmark-publication-v2":
        raise BenchmarkError("cannot recover malformed benchmark publication marker")
    identifier = value.get("id")
    validate_id(identifier)
    artifacts = value.get("artifacts")
    expected = [f"records/{identifier}.json", f"entries/{identifier}.md"]
    if not isinstance(artifacts, list) or len(artifacts) != 2:
        raise BenchmarkError("cannot recover malformed benchmark publication marker artifacts")
    paths = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise BenchmarkError("cannot recover malformed benchmark publication marker artifact")
        path, digest = artifact.get("path"), artifact.get("sha256")
        if path not in expected or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise BenchmarkError("cannot recover malformed benchmark publication marker artifact")
        paths.append(path)
    if sorted(paths) != sorted(expected):
        raise BenchmarkError("cannot recover malformed benchmark publication marker artifact paths")
    return value


def recover_pending_publication() -> None:
    """Finish or roll back the last interrupted two-artifact publication.

    SIGKILL cannot run Python cleanup.  The kernel releases ``flock`` and the
    next recorder invocation reaches this marker while holding that lock: a
    complete byte-matching pair is retained, while a partial pair is removed.
    """
    marker = load_pending_marker()
    if marker is None:
        # A SIGKILL before marker publication leaves only private staging files.
        cleanup_orphan_staging()
        return
    identifier = marker["id"]
    expected = {item["path"]: item["sha256"] for item in marker["artifacts"]}
    matching: list[Path] = []
    corrupt: list[Path] = []
    missing: list[Path] = []
    for relative, digest in expected.items():
        path = BENCH_DIR / relative
        if not path.exists():
            missing.append(path)
            continue
        try:
            actual = sha256(path.read_bytes())
        except OSError as exc:
            raise BenchmarkError(f"cannot recover benchmark artifact {path}: {exc}") from exc
        if actual != digest:
            # The v2 marker is transaction ownership.  This is a partial or
            # corrupt artifact from a killed publication, not user evidence.
            corrupt.append(path)
            continue
        matching.append(path)
    if missing or corrupt:
        for path in (*matching, *corrupt):
            try:
                path.unlink()
            except OSError as exc:
                raise BenchmarkError(f"cannot roll back interrupted benchmark artifact {path}: {exc}") from exc
    try:
        publication_marker().unlink()
    except OSError as exc:
        raise BenchmarkError(f"cannot clear recovered benchmark publication marker: {exc}") from exc
    cleanup_staged(identifier)


def publish_pair(identifier: str, record_path: Path, record_text: str,
                 entry_path: Path, entry_content: str) -> None:
    """Stage and publish one immutable JSON/Markdown pair under ``index_lock``."""
    stage = staging_dir()
    stage.mkdir(parents=True, exist_ok=True)
    stage_record = stage / f"{identifier}.record.json"
    stage_entry = stage / f"{identifier}.entry.md"
    atomic_replace(stage_record, record_text)
    atomic_replace(stage_entry, entry_content)
    marker = {
        "schema": "benchmark-publication-v2",
        "id": identifier,
        "artifacts": [
            {"path": f"records/{identifier}.json", "sha256": sha256(record_text)},
            {"path": f"entries/{identifier}.md", "sha256": sha256(entry_content)},
        ],
    }
    atomic_replace(publication_marker(), json.dumps(marker, sort_keys=True) + "\n")
    try:
        atomic_publish(stage_record, record_path, record_text)
        atomic_publish(stage_entry, entry_path, entry_content)
    except BaseException:
        # Includes KeyboardInterrupt/SystemExit.  SIGKILL is recovered by the
        # persistent marker on the next flock holder.
        recover_pending_publication()
        raise
    try:
        publication_marker().unlink()
    except OSError as exc:
        raise BenchmarkError(f"cannot finalize benchmark publication marker: {exc}") from exc
    cleanup_staged(identifier)


def measured(args: argparse.Namespace) -> int:
    date = validate_date(args.date)
    identifier = validate_id(args.identifier) if args.identifier else f"{date}-{slugify(args.label)}"
    validate_id(identifier)
    plugin_version = read_plugin_version()
    rows: list[dict[str, Any]] = []
    reports: dict[str, Any] = {}
    report_tags: dict[str, str] = {}
    for spec in args.reports:
        tag, path = parse_report_arg(spec)
        key = tag or path.name
        if key in reports:
            raise BenchmarkError(f"duplicate report tag {key!r}")
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise BenchmarkError(f"cannot read report {path}: {exc}") from exc
        if not isinstance(report, dict):
            raise BenchmarkError(f"report {path} is not a JSON object")
        rows.extend(cell_rows(tag, report))
        reports[key] = compact_report(report)
        report_tags[key] = tag
    if not rows:
        raise BenchmarkError("reports contained no result cells")
    scenarios = sorted({str(row["scenario"]) for row in rows})
    frontmatter = {
        "id": identifier, "date": date, "label": args.label,
        "plugin_version": plugin_version, "status": status_for(rows),
        "scenarios": scenarios, "record": f"../records/{identifier}.json",
    }
    record = {"id": identifier, "date": date, "label": args.label, "notes": args.notes,
              "plugin_version": plugin_version, "report_tags": report_tags, "reports": reports}
    entry_path = ENTRIES_DIR / f"{identifier}.md"
    rendered_entry = entry_text(frontmatter, rows, args.notes)
    _, body = parse_frontmatter(rendered_entry)
    entry = Entry(entry_path, frontmatter, body)
    validate_entry(entry, record_override=record)
    targets = {
        RECORDS_DIR / f"{identifier}.json": json.dumps(record, indent=2, ensure_ascii=False) + "\n",
        entry_path: rendered_entry,
    }
    identical_or_fail(targets)
    with index_lock():
        # Re-check inside the crash-released lock.  publish_pair records enough
        # state to recover a SIGKILL after either immutable final-path create.
        identical_or_fail(targets)
        publish_pair(identifier, RECORDS_DIR / f"{identifier}.json", targets[RECORDS_DIR / f"{identifier}.json"],
                     entry_path, targets[entry_path])
        existing = load_entries()
        atomic_replace(INDEX, index_text(existing))
    print(f"wrote entry to {entry_path.relative_to(REPO_ROOT)}")
    print(f"wrote record to {(RECORDS_DIR / f'{identifier}.json').relative_to(REPO_ROOT)}")
    print(f"rebuilt index at {INDEX.relative_to(REPO_ROOT)}")
    return 0


def rebuild(check: bool) -> int:
    if check:
        # Checking may need to recover a SIGKILL marker first, so it takes the
        # same crash-released lock even though it never rewrites the index.
        with index_lock():
            entries = load_entries()
            expected = index_text(entries)
            actual = INDEX.read_text(encoding="utf-8") if INDEX.exists() else ""
        if actual != expected:
            print("benchmark index is missing or stale; run --rebuild-index", file=sys.stderr)
            return 1
        print("benchmark entries and index are valid")
        return 0
    with index_lock():
        entries = load_entries()
        expected = index_text(entries)
        actual = INDEX.read_text(encoding="utf-8") if INDEX.exists() else ""
        if actual != expected:
            atomic_replace(INDEX, expected)
    print(f"rebuilt index at {INDEX.relative_to(REPO_ROOT)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--rebuild-index", action="store_true", help="Validate entries and rewrite the generated index.")
    modes.add_argument("--check", action="store_true", help="Validate entries and fail when the generated index drifts.")
    parser.add_argument("--label", help="What changed, e.g. 'nxd-setup-cli: device-flow branch'.")
    parser.add_argument("--report", action="append", dest="reports", metavar="[TAG=]PATH",
                        help="run.py --report JSON; repeatable.")
    parser.add_argument("--notes", default="", help="One or two sentences of context for the entry.")
    parser.add_argument("--date", default=dt.date.today().isoformat(), help="Entry date, YYYY-MM-DD (default: today).")
    parser.add_argument("--id", dest="identifier", help="Optional lowercase-slug identity; defaults to date plus label slug.")
    args = parser.parse_args(argv)
    try:
        if args.rebuild_index:
            return rebuild(check=False)
        if args.check:
            return rebuild(check=True)
        if not args.label or not args.reports:
            parser.error("measured records require --label and at least one --report")
        return measured(args)
    except BenchmarkError as exc:
        print(f"benchmark record error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
