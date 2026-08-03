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

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "src" / "nxd-run-job-loop" / "scripts"
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
    `evidence.reason`, a closed enum, so nobody invents another code for a
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
    # The fourth reason: frontmatter that IS delimited and IS a mapping shape but
    # does not parse. This one used to escape as a raw `yaml.ParserError` — no
    # diagnostic, no --json, no exit-code contract.
    assert reasons(
        "---\nname: [unclosed\n---\n\n## intent\n\nScore candidates.\n",
        "spec.frontmatter.unparseable",
    ) == {"unparseable"}

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


def test_declared_verdicts_without_bands_are_unreachable(tmp_path):
    """A vocabulary without a band or rule cannot produce any verdict."""
    import validate_dp_spec

    path = tmp_path / "dp-spec.md"
    path.write_text(
        BROKEN_SPEC + "\n## verdicts\n\nvalues: [ADVANCE, REJECT]\n",
        encoding="utf-8",
    )
    diagnostics = validate_dp_spec.validate(path).diagnostics
    unreachable = [d for d in diagnostics if d.code == "spec.verdict.value_unreached"]

    assert len(unreachable) == 1
    assert unreachable[0].evidence == {"found": ["ADVANCE", "REJECT"]}


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


# --- the splitters have exactly one definition ------------------------------
#
# `split_frontmatter` / `split_sections` were duplicated between the validator
# and the canonicalizer under a "must stay byte-for-byte equivalent" docstring.
# They drifted anyway: the validator's copy lost the `yaml.YAMLError` guard, so
# `name: [unclosed` produced a raw traceback instead of a field-addressed
# `spec.frontmatter.unparseable`. A comment is not an enforcement mechanism;
# these two tests are.


def test_the_validator_does_not_redefine_the_splitters():
    """One definition cannot drift from itself."""
    tree = ast.parse(VALIDATOR.read_text(encoding="utf-8"))
    defined = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for name in ("split_frontmatter", "split_sections"):
        assert name not in defined, (
            f"{name!r} is defined in validate_dp_spec.py as well as in "
            "dp_diagnostics.py. The hash must describe the same document the "
            "validator judged, and two copies is how that stops being true."
        )


def test_the_validator_uses_the_canonicalizers_splitters():
    import validate_dp_spec

    assert validate_dp_spec.split_frontmatter is dp_diagnostics.split_frontmatter
    assert validate_dp_spec.split_sections is dp_diagnostics.split_sections


def test_validator_usage_names_the_resolved_helper_directory():
    usage = VALIDATOR.read_text(encoding="utf-8").partition("Exit codes:")[0]
    assert 'python3 "$JOB_HELPER_DIR/scripts/validate_dp_spec.py"' in usage
    assert "python3 scripts/validate_dp_spec.py" not in usage


def test_unparseable_frontmatter_is_a_diagnostic_not_a_traceback(tmp_path):
    """The regression, end to end at the CLI: a stable code in valid --json, and
    the documented exit code — not a stack trace on stderr."""
    import json
    import subprocess

    path = tmp_path / "dp-spec.md"
    path.write_text("---\nname: [unclosed\n---\n\n## intent\n\nx\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(VALIDATOR), str(path), "--json"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1, result.stderr
    assert "Traceback" not in result.stderr
    payload = json.loads(result.stdout)
    assert dp_diagnostics.validate_report(payload) == []
    assert payload["spec_hash"] is None, "a spec that cannot be split has no hash"
    assert [d["code"] for d in payload["diagnostics"]] == [
        "spec.frontmatter.unparseable"
    ]
    assert payload["diagnostics"][0]["evidence"]["reason"] == "unparseable"


def test_missing_pyyaml_exits_two_without_a_spec_diagnostic(tmp_path, monkeypatch, capsys):
    """A missing dependency is an environment failure, not malformed user input."""
    import validate_dp_spec

    path = tmp_path / "dp-spec.md"
    path.write_text("---\nname: x\n---\n", encoding="utf-8")
    monkeypatch.setattr(dp_diagnostics, "yaml", None)
    monkeypatch.setattr(sys, "argv", [str(VALIDATOR), str(path), "--json"])

    assert validate_dp_spec.main() == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "environment.dependency_missing" in captured.err
    assert "spec.frontmatter.unparseable" not in captured.err
    with pytest.raises(dp_diagnostics.DependencyError) as exc:
        validate_dp_spec.validate(path)
    assert exc.value.code == "environment.dependency_missing"

DUPLICATE_PROMISES_SPEC = """---
dp_spec_version: 1
name: orders
workflow: orders
status: draft
---

## intent

Track orders.

## questions

- q1: How do totals reconcile?

## sources

- label: orders
  type: csv
  location: data/orders
  scope: |
    All rows.

## population

population: |
  All orders.
sample_rule: null
excludes: |
  Nothing.

## models

- name: orders
  kind: base
  grain: |
    One row per order line.
  key: [line_id]
  answers: [q1]
  description: |
    Order lines.

## promises

- name: dup-name
  authority: user_stated
  model: orders
  guarantee: |
    First guarantee.
  rule: |
    a == b
- name: dup-name
  authority: user_stated
  model: orders
  guarantee: |
    Second guarantee.
  rule: |
    c == d
"""


def test_duplicate_contract_name_is_addressed_to_its_own_section(tmp_path):
    """A promises-only collision must not be reported at `spec:expectations`.

    The duplicate check spans both sections deliberately — a cross-section
    collision is invisible to a per-section checker — but the finding still has
    to name where the collision IS. Addressing every duplicate to
    `spec:expectations` pointed a harness at a section this spec does not have.
    """
    import validate_dp_spec

    path = tmp_path / "dp-spec.md"
    path.write_text(DUPLICATE_PROMISES_SPEC, encoding="utf-8")
    report = validate_dp_spec.validate(path)

    dupes = [d for d in report.diagnostics
             if d.code == "spec.contract.duplicate_name"]
    assert dupes, "the duplicate name was not reported at all"
    for d in dupes:
        assert d.path.startswith("spec:promises["), d.path
        assert "expectations" not in d.path, d.path
        # The message must not name a section the document does not contain.
        assert "across expectations and promises" not in d.message, d.message
        assert d.evidence.get("found") == ["dup-name"], d.evidence

    # ONE finding per section the name appears in — not one per colliding entry.
    # Emitting a diagnostic per entry makes report.counts() report N errors for
    # one problem, all byte-identical because the path is keyed on
    # (section, name).
    assert len(dupes) == 1, [d.path for d in dupes]


def test_cross_section_duplicate_names_both_sides(tmp_path):
    """Both locations are reported, and neither message is a copy of the other.

    A collision spanning both sections has no at-fault side — a reader in
    `expectations` must see it too — so two findings is correct. They must not
    be byte-identical-but-for-the-path though: each names the OTHER section, so
    a harness rendering either one is actionable on its own.
    """
    import validate_dp_spec

    spec_text = DUPLICATE_PROMISES_SPEC.replace(
        """## promises

- name: dup-name
  authority: user_stated
  model: orders
  guarantee: |
    First guarantee.
  rule: |
    a == b
""",
        """## expectations

- name: dup-name
  authority: user_stated
  model: orders
  guarantee: |
    First guarantee.
  rule: |
    a == b

## promises
""",
    )
    path = tmp_path / "dp-spec.md"
    path.write_text(spec_text, encoding="utf-8")
    report = validate_dp_spec.validate(path)

    dupes = [d for d in report.diagnostics
             if d.code == "spec.contract.duplicate_name"]
    assert {d.path for d in dupes} == {
        "spec:expectations[dup-name].name",
        "spec:promises[dup-name].name",
    }, [d.path for d in dupes]
    assert len({d.message for d in dupes}) == 2, "the two findings are identical"
    by_path = {d.path: d.message for d in dupes}
    assert "promises" in by_path["spec:expectations[dup-name].name"]
    assert "expectations" in by_path["spec:promises[dup-name].name"]


def test_within_and_across_section_duplication_reports_both_facts(tmp_path):
    """A name can collide inside a section AND across sections at once.

    Reporting only the cross-section half let a repair pass rename one entry,
    read both findings as addressed, and still ship two copies in the other
    section.
    """
    import validate_dp_spec

    spec_text = DUPLICATE_PROMISES_SPEC.replace(
        """## promises

- name: dup-name""",
        """## expectations

- name: dup-name
  authority: user_stated
  model: orders
  guarantee: |
    Cross-section copy.
  rule: |
    e == f

## promises

- name: dup-name""",
    )
    path = tmp_path / "dp-spec.md"
    path.write_text(spec_text, encoding="utf-8")
    report = validate_dp_spec.validate(path)

    by_path = {d.path: d.message for d in report.diagnostics
               if d.code == "spec.contract.duplicate_name"}
    promises = by_path["spec:promises[dup-name].name"]
    assert "2 times in promises" in promises, promises
    assert "also appears in expectations" in promises, promises


def test_entries_with_distinct_ids_each_get_their_own_finding(tmp_path):
    """De-dup is on the RENDERED PATH, not on (section, name).

    `entry_identity` prefers `id`, so two colliding entries carrying distinct
    ids render distinct paths. Collapsing them would drop a real collision
    site — a UI would highlight one of the two and leave the reader to find the
    other by hand. Entries with no `id` render the same path and still collapse.
    """
    import validate_dp_spec

    spec_text = DUPLICATE_PROMISES_SPEC.replace(
        "- name: dup-name\n  authority: user_stated\n  model: orders\n"
        "  guarantee: |\n    First guarantee.",
        "- id: c-1\n  name: dup-name\n  authority: user_stated\n  model: orders\n"
        "  guarantee: |\n    First guarantee.",
    ).replace(
        "- name: dup-name\n  authority: user_stated\n  model: orders\n"
        "  guarantee: |\n    Second guarantee.",
        "- id: c-2\n  name: dup-name\n  authority: user_stated\n  model: orders\n"
        "  guarantee: |\n    Second guarantee.",
    )
    path = tmp_path / "dp-spec.md"
    path.write_text(spec_text, encoding="utf-8")
    report = validate_dp_spec.validate(path)

    paths = {d.path for d in report.diagnostics
             if d.code == "spec.contract.duplicate_name"}
    assert paths == {"spec:promises[c-1].name", "spec:promises[c-2].name"}, paths

