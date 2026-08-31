"""Artifact-owned grading oracles with explicit three-state outcomes.

An oracle is ``satisfied`` only after it examined the required artifact and
verified it.  Missing fixtures, unavailable control ports, and absent counter
snapshots are ``not-examined``; they are never silently treated as passing.

The capability and counter oracles are public scenario APIs and are not
implicitly invoked by the tier path.  The tier wires the marker, gold, and
control-total seams explicitly where a scenario declares them.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from urllib.request import Request, urlopen


class OracleState(str, Enum):
    """The three outcomes shared by every oracle."""

    SATISFIED = "satisfied"
    VIOLATED = "violated"
    NOT_EXAMINED = "not-examined"


OracleOutcome = OracleState


@dataclass(frozen=True, slots=True)
class OracleFinding:
    """A stable machine-readable oracle finding."""

    code: str
    detail: str = ""
    value: object = None


@dataclass(frozen=True, slots=True)
class OracleResult:
    """A three-state oracle result and its artifact-owned value."""

    state: OracleState
    value: object = None
    findings: tuple[OracleFinding, ...] = ()

    @property
    def outcome(self) -> str:
        """Return the serialized three-state outcome."""

        return self.state.value

    @property
    def status(self) -> OracleState:
        """Return the typed three-state outcome."""

        return self.state

    @property
    def passed(self) -> bool:
        """Only a satisfied oracle passes."""

        return self.state is OracleState.SATISFIED

    @property
    def examined(self) -> bool:
        """Whether the oracle actually inspected its required input."""

        return self.state is not OracleState.NOT_EXAMINED

    @property
    def codes(self) -> tuple[str, ...]:
        """Return stable finding codes."""

        return tuple(finding.code for finding in self.findings)


@dataclass(frozen=True, slots=True)
class GoldRowSet:
    """Frozen rows accepted by the deterministic-EX scorer."""

    rows: list[dict[str, object]]
    source: str


def _result(state: OracleState, value: object = None, *findings: OracleFinding) -> OracleResult:
    return OracleResult(state=state, value=value, findings=tuple(findings))


def load_fixture_manifest(fixture: str | Path | Mapping[str, object]) -> Mapping[str, object] | OracleResult:
    """Load a fixture manifest, returning a not-examined result when absent."""

    if isinstance(fixture, Mapping):
        return fixture
    path = Path(fixture)
    if path.is_dir():
        path = path / "fixture-manifest.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return _result(OracleState.NOT_EXAMINED, None, OracleFinding("fixture_manifest_not_examined", str(exc), str(path)))
    if not isinstance(data, Mapping):
        return _result(OracleState.VIOLATED, None, OracleFinding("fixture_manifest_invalid", "manifest is not an object", data))
    return data


def _gold_path(fixture: str | Path, filename: str | Path | None) -> Path:
    root = Path(fixture)
    if root.is_file():
        return root
    if filename is not None:
        candidate = Path(filename)
        return candidate if candidate.is_absolute() else root / candidate
    manifest = load_fixture_manifest(root)
    if isinstance(manifest, Mapping):
        declared = manifest.get("gold", manifest.get("gold_row_set"))
        if isinstance(declared, str):
            return root / declared
    for candidate in (root / "gold.json", root / "gold" / "answer.json"):
        if candidate.exists():
            return candidate
    return root / "gold.json"


def gold_rowset(fixture: str | Path, filename: str | Path | None = None) -> OracleResult:
    """Load and validate a frozen row-set through nxd_eval's EX scorer."""

    path = _gold_path(fixture, filename)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return _result(OracleState.NOT_EXAMINED, None, OracleFinding("gold_not_examined", str(exc), str(path)))
    if not isinstance(raw, list) or not all(isinstance(row, Mapping) for row in raw):
        return _result(OracleState.VIOLATED, None, OracleFinding("gold_shape_invalid", "gold must be a list of row objects", raw))
    rows = [dict(row) for row in raw]
    from nxd_eval.scoring import score_one

    verdict = score_one({"rows": rows, "abstained": False, "errored": False}, {"rows": rows, "equality_mode": "set"})
    if verdict != "PASS":
        return _result(OracleState.VIOLATED, None, OracleFinding("gold_scorer_rejected", f"EX scorer returned {verdict}", verdict))
    return _result(OracleState.SATISFIED, GoldRowSet(rows, str(path)))


def load_gold_rows(fixture: str | Path, filename: str | Path | None = None) -> list[dict[str, object]]:
    """Return rows only after the gold oracle is satisfied."""

    result = gold_rowset(fixture, filename)
    if not result.passed or not isinstance(result.value, GoldRowSet):
        raise ValueError(result.findings[0].detail if result.findings else "gold row-set was not examined")
    return result.value.rows


def _json_from_control(source: object) -> object:
    if isinstance(source, Mapping):
        return source
    if hasattr(source, "as_dict"):
        return source.as_dict()
    if hasattr(source, "to_dict"):
        return source.to_dict()
    if isinstance(source, (str, Path)):
        text = str(source)
        if text.startswith(("http://", "https://")):
            request = Request(text, headers={"Accept": "application/json"})
            with urlopen(request, timeout=5) as response:  # noqa: S310 - explicitly supplied control endpoint
                return json.loads(response.read().decode("utf-8"))
        path = Path(source)
        return json.loads(path.read_text(encoding="utf-8"))
    if callable(source):
        return source()
    return None


def capability_oracle(source: object) -> OracleResult:
    """Read the capability manifest from control data or a local artifact."""

    try:
        raw = _json_from_control(source)
    except Exception as exc:  # the state is deliberately not-examined, not passing
        return _result(OracleState.NOT_EXAMINED, None, OracleFinding("capability_not_examined", str(exc)))
    if not isinstance(raw, Mapping):
        return _result(OracleState.NOT_EXAMINED, None, OracleFinding("capability_not_examined", "control source returned no mapping"))
    if "capability" in raw and isinstance(raw["capability"], Mapping):
        raw = raw["capability"]
    metrics = raw.get("metrics")
    if not isinstance(metrics, Mapping):
        return _result(OracleState.VIOLATED, None, OracleFinding("capability_shape_invalid", "capability metrics are absent"))
    return _result(OracleState.SATISFIED, dict(raw))


def counter_oracle(snapshot: object, *, call_ceiling: int | None = None, expected_pages: int | None = None) -> OracleResult:
    """Check server-owned request counters without penalizing frugal runs."""

    if hasattr(snapshot, "snapshot") and callable(getattr(snapshot, "snapshot")):
        snapshot = snapshot.snapshot()
    if snapshot is None:
        return _result(OracleState.NOT_EXAMINED, None, OracleFinding("counters_not_examined", "no server-side counter snapshot"))
    if not isinstance(snapshot, Mapping):
        return _result(OracleState.VIOLATED, None, OracleFinding("counters_shape_invalid", "counter snapshot is not a mapping"))
    if "total" not in snapshot:
        return _result(OracleState.VIOLATED, dict(snapshot), OracleFinding("counters_shape_invalid", "counter snapshot has no server-side total"))
    findings: list[OracleFinding] = []
    total = snapshot.get("total")
    if isinstance(total, bool) or not isinstance(total, int) or total < 0:
        findings.append(OracleFinding("counters_shape_invalid", "counter snapshot total must be a non-negative integer", total))
    elif call_ceiling is not None and total > call_ceiling:
        findings.append(OracleFinding("call_ceiling_violated", "server-side total exceeds declared ceiling", {"actual": total, "ceiling": call_ceiling}))
    if expected_pages is not None:
        pages = snapshot.get("pages")
        if pages is None:
            pages = snapshot.get("page_count")
        if pages is None:
            routes = snapshot.get("routes")
            if isinstance(routes, Mapping):
                populated = [
                    bucket.get("count")
                    for route, bucket in routes.items()
                    if route != "__unmatched__" and isinstance(bucket, Mapping) and "count" in bucket
                ]
                if len(populated) == 1:
                    pages = populated[0]
        if pages is None:
            findings.append(OracleFinding("pagination_not_examined", "snapshot has no page count"))
        elif pages != expected_pages:
            findings.append(OracleFinding("pagination_incomplete", "server-side page count differs", {"actual": pages, "expected": expected_pages}))
    if not findings:
        state = OracleState.SATISFIED
    elif all(finding.code == "pagination_not_examined" for finding in findings):
        state = OracleState.NOT_EXAMINED
    else:
        state = OracleState.VIOLATED
    return _result(state, dict(snapshot), *findings)


def control_total_oracle(answer: object, control_total: object) -> OracleResult:
    """Reconcile an aggregate only against the independent control total."""

    if answer is None or control_total is None:
        return _result(OracleState.NOT_EXAMINED, None, OracleFinding("control_total_not_examined", "answer or control total is absent"))
    def extract(value: object) -> object:
        if isinstance(value, Mapping):
            for key in ("control_total", "total", "value"):
                if key in value:
                    return value[key]
        if isinstance(value, list) and value and isinstance(value[0], Mapping):
            return extract(value[0])
        return value
    observed = extract(answer)
    expected = extract(control_total)
    if observed != expected:
        return _result(OracleState.VIOLATED, observed, OracleFinding("control_total_mismatch", "answer differs from independent control total", {"answer": observed, "control": expected}))
    return _result(OracleState.SATISFIED, observed)


def marker_values(manifest: Mapping[str, object]) -> frozenset[bytes]:
    """Extract exact marker bytes from both secret and PII declarations."""

    values: set[bytes] = set()
    for key in ("pii_markers", "secret_markers", "sentinel_values"):
        raw = manifest.get(key)
        if isinstance(raw, Mapping):
            raw = list(raw.values())
        if isinstance(raw, (list, tuple, set, frozenset)):
            values.update(str(value).encode("utf-8") for value in raw if isinstance(value, str) and value)
    pii = manifest.get("pii_dictionary")
    if isinstance(pii, Mapping):
        raw = pii.get("sentinel_values", pii.get("markers", ()))
        if isinstance(raw, Mapping):
            raw = list(raw.values())
        if isinstance(raw, (list, tuple, set, frozenset)):
            values.update(str(value).encode("utf-8") for value in raw if isinstance(value, str) and value)
    return frozenset(values)


load_capability = capability_oracle
read_capability = capability_oracle
capability_manifest_oracle = capability_oracle
gold_oracle = gold_rowset
load_gold = gold_rowset
counter_snapshot_oracle = counter_oracle
server_counter_oracle = counter_oracle
reconcile_control_total = control_total_oracle
control_total = control_total_oracle


__all__ = [
    "OracleState",
    "OracleOutcome",
    "OracleFinding",
    "OracleResult",
    "GoldRowSet",
    "load_fixture_manifest",
    "gold_rowset",
    "gold_oracle",
    "load_gold",
    "load_gold_rows",
    "capability_oracle",
    "capability_manifest_oracle",
    "load_capability",
    "read_capability",
    "counter_oracle",
    "counter_snapshot_oracle",
    "server_counter_oracle",
    "control_total_oracle",
    "reconcile_control_total",
    "control_total",
    "marker_values",
]
