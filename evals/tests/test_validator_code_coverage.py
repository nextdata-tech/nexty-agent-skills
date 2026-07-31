"""The `spec.` registry and the validator's checks must stay in lockstep.

The registry table in the design note is documentation. This test is the
contract, and it runs in BOTH directions:

* every `report.error(` / `report.warn(` call site in `validate_dp_spec.py`
  passes a `code=` — a check with no code cannot reach a harness;
* every literal it passes is a key in `dp_diagnostics.CODES` filed under
  `s0_spec`;
* and the converse: every `spec.*` code in the registry is emitted by at least
  one call site. That direction is the one that catches a DROPPED check — a code
  in the registry that nothing produces means a check went missing on the way in.

One declared exemption, by exact name and never by prefix:
`spec.encoding.not_utf8` is raised at the file-read boundary and exits 2 before
a `Report` exists, so it is emitted outside the `report.error` path. Listing it
by name is what stops a second uncovered code slipping in behind it.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"
VALIDATOR = SCRIPTS / "validate_dp_spec.py"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import dp_diagnostics  # noqa: E402

# Raised at the file-read boundary, before a Report exists. The ONLY exemption.
EMITTED_OUTSIDE_REPORT = {"spec.encoding.not_utf8"}


def _report_calls() -> list[ast.Call]:
    tree = ast.parse(VALIDATOR.read_text(encoding="utf-8"))
    calls = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute):
            continue
        if func.attr not in ("error", "warn", "info"):
            continue
        if not isinstance(func.value, ast.Name) or func.value.id != "report":
            continue
        calls.append(node)
    return calls


def _code_of(call: ast.Call) -> str | None:
    for kw in call.keywords:
        if kw.arg == "code" and isinstance(kw.value, ast.Constant):
            return kw.value.value
    return None


def test_validator_has_call_sites():
    assert len(_report_calls()) > 50, "the validator lost its checks"


def test_every_call_site_passes_a_literal_code():
    missing = [
        f"{VALIDATOR.name}:{call.lineno}"
        for call in _report_calls()
        if _code_of(call) is None
    ]
    assert not missing, (
        "these report.error/warn call sites pass no literal code= — a check with "
        f"no code cannot be rendered or routed: {missing}"
    )


def test_every_emitted_code_is_registered_at_s0():
    for call in _report_calls():
        code = _code_of(call)
        entry = dp_diagnostics.CODES.get(code)
        assert entry is not None, (
            f"{VALIDATOR.name}:{call.lineno} emits unregistered code {code!r}"
        )
        assert entry["stage"] == "s0_spec", (
            f"{code!r} is emitted by the spec validator but the registry files it "
            f"under {entry['stage']!r}"
        )


def test_every_registered_spec_code_is_emitted():
    """The direction that catches a dropped check."""
    emitted = {_code_of(call) for call in _report_calls()} - {None}
    registered = {c for c in dp_diagnostics.CODES if c.startswith("spec.")}
    uncovered = registered - emitted - EMITTED_OUTSIDE_REPORT
    assert not uncovered, (
        "these spec.* codes are in the registry and nothing produces them — a "
        f"check went missing on the way in: {sorted(uncovered)}"
    )


def test_the_exemption_is_a_name_not_a_pattern():
    assert EMITTED_OUTSIDE_REPORT == {"spec.encoding.not_utf8"}
    source = VALIDATOR.read_text(encoding="utf-8")
    assert "spec.encoding.not_utf8" in source, (
        "the one exempt code must still be emitted somewhere in the validator"
    )


def test_the_two_many_to_one_codes_carry_a_reason(tmp_path):
    """Two codes have more than one call site. The discriminator is
    `evidence.reason`, a closed enum, so nobody invents a third code for a
    variant of the same failure."""
    import validate_dp_spec

    def reasons(text: str, code: str) -> set[str]:
        path = tmp_path / "dp-spec.md"
        path.write_text(text, encoding="utf-8")
        return {
            d.evidence.get("reason")
            for d in validate_dp_spec.validate(path).errors
            if d.code == code
        }

    assert reasons("no frontmatter here\n", "spec.frontmatter.unparseable") == {"missing"}
    assert reasons("---\nname: x\n", "spec.frontmatter.unparseable") == {"unterminated"}
    assert reasons("---\njust a string\n---\n", "spec.frontmatter.unparseable") == {
        "not_mapping"
    }

    head = "---\ndp_spec_version: 1\nname: x\nworkflow: x\nstatus: draft\n---\n\n"
    assert reasons(
        head + "## criteria\n\n- id: C1\n  weight: 1.0\n  scale: {min: 1.5, max: 5.5}\n",
        "spec.criteria.bad_scale",
    ) == {"non_integer"}
    assert reasons(
        head + "## criteria\n\n- id: C1\n  weight: 1.0\n  scale: {min: 5, max: 1}\n",
        "spec.criteria.bad_scale",
    ) == {"min_not_below_max"}


# --- field addressing -------------------------------------------------------

BROKEN_SPEC = """---
dp_spec_version: 1
name: candidate_scoring
workflow: candidate-scoring
status: draft
---

## intent

Score candidates.

## questions

- Who is best?

## sources

- label: ashby
  type: csv
  location: data/a.csv
  scope: one job

## population

population: every applicant

## models

- name: scored_candidates
  kind: derived
  description: one row per candidate
  grain: one candidate
  answers: [q1]

## criteria

- id: C1
  weight: 1.0
  scale: {min: 1, max: 5}
  anchors: {1: low, 5: high}
"""


def test_diagnostics_are_addressed_by_identity_not_index(tmp_path):
    """An array index moves when a list is edited, and a moving path is a UI that
    highlights the wrong field."""
    import validate_dp_spec

    path = tmp_path / "dp-spec.md"
    path.write_text(BROKEN_SPEC, encoding="utf-8")
    report = validate_dp_spec.validate(path)
    addressed = {(d.code, d.path) for d in report.diagnostics}

    assert ("spec.model.no_key", "spec:models[scored_candidates].key") in addressed
    assert (
        "spec.criteria.incomplete_scale",
        "spec:criteria[C1].anchors",
    ) in addressed
    assert ("spec.verdict.missing", "spec:verdicts") in addressed
    for code, spec_ref in addressed:
        assert spec_ref == "" or spec_ref.startswith("spec:"), (code, spec_ref)


def test_the_json_envelope_is_the_shared_report_shape(tmp_path):
    import validate_dp_spec

    path = tmp_path / "dp-spec.md"
    path.write_text(BROKEN_SPEC, encoding="utf-8")
    payload = validate_dp_spec.validate(path).to_dict()

    assert payload["schema"] == "nxd-diagnostic-report-v1"
    assert payload["tool"] == "validate_dp_spec"
    assert payload["spec_hash"].startswith("sha256:")
    assert payload["ok"] is False
    assert dp_diagnostics.validate_report(payload) == []
    # The old {spec, ok, errors[], warnings[]} shape is removed, not deprecated.
    assert "errors" not in payload and "warnings" not in payload


def test_every_diagnostic_carries_a_control_for_the_harness(tmp_path):
    """`control` is what lets a harness render an anchors editor for an
    incomplete scale and a number field for a bad weight."""
    import validate_dp_spec

    path = tmp_path / "dp-spec.md"
    path.write_text(BROKEN_SPEC, encoding="utf-8")
    for diag in validate_dp_spec.validate(path).diagnostics:
        entry = dp_diagnostics.CODES[diag.code]
        assert entry["control"] in dp_diagnostics.CONTROLS
    assert dp_diagnostics.CODES["spec.criteria.incomplete_scale"]["control"] == "mapping"
    assert dp_diagnostics.CODES["spec.criteria.bad_weight"]["control"] == "number"


def test_severity_matches_the_registry():
    """`report.warn` may relax an error downward; it may never raise a warning."""
    for call in _report_calls():
        code = _code_of(call)
        entry = dp_diagnostics.CODES[code]
        if call.func.attr == "error":
            assert entry["severity"] == "error", (
                f"{code!r} is registry severity {entry['severity']!r} but is "
                "emitted through report.error — a producer may relax downward, "
                "never raise"
            )
