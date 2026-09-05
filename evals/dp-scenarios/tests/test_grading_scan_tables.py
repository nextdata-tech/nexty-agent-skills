"""Every entry of every scan decision table must actually decide something.

The scans in ``dp_scenarios.grading.scans`` decide by consulting literal
tables: forbidden import roots, subprocess entry points, aggregation markers,
executable tool kinds, trace-entry key aliases, spec key fallbacks.
``tests/test_grading_scans.py`` covers the scans' shapes; automated mutation
testing (see "Mutation testing" in ``README.md``) showed that it reaches two or
three entries of each table and leaves the rest inert.  Deleting ``httplib2``
from the forbidden roots, or ``bash`` from the executable kinds, or the
``groupby(`` marker from the aggregation table, changed no test's verdict --
143 surviving mutants in ``supported_path_scan`` alone.  A table entry no test
reaches is a gate that exists and never fires, which is the defect this suite
is most prone to.

These tests deliberately **restate** each table rather than importing it.  A
test that iterates the same constant the code consults moves with the code:
rename an entry and the test renames its own fixture with it, and the mutation
survives again.  The literal tables below are the specification; ``scans.py``
is the implementation, and the two are only allowed to agree on purpose.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dp_scenarios.grading.scans import (
    governed_path_scan,
    meaning_preserving_bounding_scan,
    proxy_labelling_scan,
    supported_path_scan,
)


FORBIDDEN_HTTP_ROOTS = (
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
)

SUBPROCESS_ENTRY_POINTS = ("check_call", "check_output", "popen", "run", "system", "Popen")


# ---------------------------------------------------------------------------
# supported_path_scan
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("root", FORBIDDEN_HTTP_ROOTS)
def test_every_declared_forbidden_root_is_actually_rejected(tmp_path: Path, root: str) -> None:
    """Each declared root must be caught as a plain import and through a submodule."""

    plain = tmp_path / "plain.py"
    plain.write_text(f"import {root}\n", encoding="utf-8")
    plain_result = supported_path_scan(plain)
    assert not plain_result.passed, root
    assert "supported_path_direct_http" in plain_result.codes, root

    submodule = tmp_path / "submodule.py"
    submodule.write_text(f"from {root}.sub import thing\n", encoding="utf-8")
    assert not supported_path_scan(submodule).passed, root


@pytest.mark.parametrize("root", FORBIDDEN_HTTP_ROOTS)
def test_a_module_that_merely_starts_with_a_forbidden_root_is_allowed(
    tmp_path: Path, root: str
) -> None:
    """The prefix test is on a dotted boundary, not on raw characters.

    Without the ``root + "."`` join, ``import socketserver`` reads as a direct
    HTTP import and a closure fails a scan it never violated.  Fail-closed is
    not the same as fail-always: a scan that rejects everything grades nothing.
    """

    lookalike = tmp_path / "lookalike.py"
    lookalike.write_text(f"import {root.replace('.', '_')}_helper\n", encoding="utf-8")
    assert supported_path_scan(lookalike).passed, root


@pytest.mark.parametrize(
    "source",
    [
        '__import__("httpx")',
        'import importlib\nimportlib.import_module("httpx")',
        'from importlib import import_module\nimport_module("httpx")',
        'import importlib\ngetattr(importlib, "import_module")("httpx")',
        'import importlib\ngetattr(importlib, "__import__")("httpx")',
    ],
    ids=["dunder", "attribute", "bare-name", "getattr-import-module", "getattr-dunder"],
)
def test_every_dynamic_import_form_is_rejected(tmp_path: Path, source: str) -> None:
    """A dynamic import is the obvious way around a scan that only reads import nodes."""

    module = tmp_path / "dynamic.py"
    module.write_text(source + "\n", encoding="utf-8")
    result = supported_path_scan(module)
    assert not result.passed, source
    assert "supported_path_direct_http" in result.codes, source


@pytest.mark.parametrize("module", ["os", "subprocess"])
@pytest.mark.parametrize("method", SUBPROCESS_ENTRY_POINTS)
def test_every_declared_subprocess_entry_point_is_watched_for_curl(
    tmp_path: Path, module: str, method: str
) -> None:
    """Shelling out to curl is a direct HTTP path whichever spawn call carries it."""

    shell = tmp_path / "shell.py"
    shell.write_text(
        f'import {module}\n{module}.{method}("curl https://example.test")\n', encoding="utf-8"
    )
    result = supported_path_scan(shell)
    assert not result.passed, (module, method)
    assert "supported_path_direct_http" in result.codes, (module, method)


@pytest.mark.parametrize("method", SUBPROCESS_ENTRY_POINTS)
def test_a_shell_true_subprocess_call_is_rejected_without_naming_curl(
    tmp_path: Path, method: str
) -> None:
    """``shell=True`` hides the command from the literal scan, so the flag is the finding.

    Only ``subprocess`` carries this keyword, and the paired ``shell=False``
    case pins that the finding comes from the flag rather than from the module
    name alone.
    """

    withheld = tmp_path / "shell_true.py"
    withheld.write_text(
        f"import subprocess\nsubprocess.{method}(fetch_command, shell=True)\n", encoding="utf-8"
    )
    assert not supported_path_scan(withheld).passed, method

    plain = tmp_path / "shell_false.py"
    plain.write_text(
        f"import subprocess\nsubprocess.{method}(local_command, shell=False)\n", encoding="utf-8"
    )
    assert supported_path_scan(plain).passed, method


# ---------------------------------------------------------------------------
# governed_path_scan
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "label"),
    [
        ("SELECT region, amount GROUP BY region", "group-by"),
        ("frame.groupby('region')", "pandas-groupby"),
        ("awk '{ total += $1 }' rows.csv", "awk"),
        ("total = sum(values)", "sum"),
    ],
)
@pytest.mark.parametrize("kind", ["shell", "bash", "python", "exec"])
def test_every_aggregation_marker_fires_in_every_executable_kind(
    text: str, label: str, kind: str
) -> None:
    """The marker table and the executable-kind table are both load-bearing.

    Two of the four markers and two of the four kinds were never exercised
    before this test, so either table could have lost an entry silently.
    """

    result = governed_path_scan(
        [{"turn": 3, "kind": kind, "input": text}], question_turn=2, answer_turn=4
    )
    assert not result.passed, (kind, label)
    assert "governed_path_aggregation_outside_query" in result.codes, (kind, label)


@pytest.mark.parametrize("kind", ["narration", "answer", "question", "read"])
def test_a_non_executable_kind_is_not_scanned_for_aggregation(kind: str) -> None:
    """Narration is not executable evidence; saying "group by" is not doing it."""

    assert governed_path_scan(
        [{"turn": 3, "kind": kind, "text": "I will not group by region by hand"}],
        question_turn=2,
        answer_turn=4,
    ).passed, kind


@pytest.mark.parametrize(
    "kind",
    ["query", "governed_query", "semantic_query", "nxd_query", "GOVERNED_QUERY", "my_governed_tool"],
)
def test_every_governed_kind_is_exempt_from_the_aggregation_scan(kind: str) -> None:
    """Aggregation inside a governed query is the sanctioned route, not a finding."""

    result = governed_path_scan(
        [{"turn": 3, "kind": kind, "input": "SELECT region, SUM(amount) FROM rows GROUP BY region"}],
        question_turn=2,
        answer_turn=4,
    )
    assert result.passed, kind


@pytest.mark.parametrize("kind_key", ["kind", "tool", "type"])
@pytest.mark.parametrize("text_key", ["input", "command", "code", "text"])
def test_every_trace_entry_key_alias_is_read(kind_key: str, text_key: str) -> None:
    """Traces reach this scan from several recorders, each with its own key names.

    An alias the reader does not consult turns every entry from that recorder
    into an empty kind and empty text -- a scan that examines the trace and can
    never find anything in it.
    """

    entry = {"turn": 3, kind_key: "bash", text_key: "awk '{ total += $1 }' rows.csv"}
    result = governed_path_scan([entry], question_turn=2, answer_turn=4)
    assert not result.passed, (kind_key, text_key)


def test_an_entry_outside_the_question_answer_window_is_not_scanned() -> None:
    """The window is the point: work before the question is not the answer's route.

    Both bounds are inclusive, which is what makes an aggregation *on* the
    question or answer turn a finding.
    """

    aggregation = {"turn": 1, "kind": "bash", "input": "awk '{ total += $1 }' rows.csv"}
    assert governed_path_scan([aggregation], question_turn=2, answer_turn=4).passed
    assert governed_path_scan([{**aggregation, "turn": 9}], question_turn=2, answer_turn=4).passed
    assert not governed_path_scan([{**aggregation, "turn": 2}], question_turn=2, answer_turn=4).passed
    assert not governed_path_scan([{**aggregation, "turn": 4}], question_turn=2, answer_turn=4).passed


def test_a_trace_with_no_turns_is_unexamined_rather_than_clean() -> None:
    """No bounded window means the scan could not look, which is not a pass."""

    result = governed_path_scan([{"kind": "bash", "input": "awk '{ total += $1 }' rows.csv"}])
    assert not result.passed
    assert not result.examined
    assert "governed_path_not_examined" in result.codes


# ---------------------------------------------------------------------------
# meaning_preserving_bounding_scan
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "label"),
    [
        ("SELECT * FROM source LIMIT 10", "limit"),
        ("rows.head(3)", "head"),
        ("from itertools import islice\nrows = islice(payload, 10)", "islice-from"),
        ("import itertools\nrows = itertools.islice(payload, 10)", "islice-module"),
        ("import itertools as it\nrows = it.islice(payload, 10)", "islice-aliased-module"),
        ("from itertools import islice as take\nrows = take(payload, 10)", "islice-aliased-name"),
        ("rows = payload[:10]", "slice"),
        ("rows = frame.iloc[:, :2]", "nested-slice"),
    ],
)
def test_every_bounding_form_is_rejected(source: str, label: str) -> None:
    result = meaning_preserving_bounding_scan(source)
    assert not result.passed, label
    assert "meaning_preserving_bounding" in result.codes, label


@pytest.mark.parametrize(
    ("source", "label"),
    [
        ("rows = payload[10]", "index-not-slice"),
        ("from itertools import count\nrows = list(count(0, 1))", "other-itertools-helper"),
        ("unlimited = 1\nrows.heading(3)", "substring-lookalike"),
        ("import itertools\nrows = itertools.chain(payload, extra)", "module-other-helper"),
    ],
)
def test_a_bounding_lookalike_is_not_a_finding(source: str, label: str) -> None:
    assert meaning_preserving_bounding_scan(source).passed, label


# ---------------------------------------------------------------------------
# proxy_labelling_scan
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("spec_key", ["proxy_marker", "controlled_marker"])
def test_the_controlled_marker_is_read_from_either_spec_key(spec_key: str) -> None:
    spec = {spec_key: "CONTROLLED-1", "metric": "revenue"}
    capability = {"metrics": {"revenue": "proxy"}}
    assert proxy_labelling_scan(spec, "described as CONTROLLED-1", capability).passed, spec_key


@pytest.mark.parametrize("capability_key", ["proxy_marker", "controlled_marker"])
def test_the_controlled_marker_falls_back_to_the_capability_manifest(capability_key: str) -> None:
    """The marker may be declared on either side; neither declaration may be ignored."""

    spec = {"metric": "revenue", "note": "CONTROLLED-1"}
    capability = {capability_key: "CONTROLLED-1", "metrics": {"revenue": "proxy"}}
    assert proxy_labelling_scan(spec, "described as CONTROLLED-1", capability).passed, capability_key


def test_an_absent_controlled_marker_leaves_the_scan_unexamined() -> None:
    result = proxy_labelling_scan({"metric": "revenue"}, "no marker", {"metrics": {"revenue": "proxy"}})
    assert not result.passed
    assert not result.examined
    assert "proxy_labelling_not_examined" in result.codes


@pytest.mark.parametrize("metric_key", ["metric", "metric_name", "name"])
def test_the_metric_under_test_is_read_from_every_declared_spec_key(metric_key: str) -> None:
    spec = {"proxy_marker": "CONTROLLED-1", metric_key: "revenue"}
    capability = {"metrics": {"revenue": "proxy"}}
    assert proxy_labelling_scan(spec, "described as CONTROLLED-1", capability).passed, metric_key

    unlabelled = proxy_labelling_scan(
        spec, "described as CONTROLLED-1", {"metrics": {"revenue": "measured"}}
    )
    assert not unlabelled.passed, metric_key
    assert "proxy_capability_label_missing" in unlabelled.codes, metric_key


@pytest.mark.parametrize(
    ("metrics", "label"),
    [
        ({"revenue": {}}, "mapping"),
        ([{"name": "revenue"}], "sequence-of-name"),
        ([{"metric": "revenue"}], "sequence-of-metric"),
        (["revenue"], "sequence-of-strings"),
    ],
)
def test_a_single_declared_metric_is_inferred_from_every_spec_shape(
    metrics: object, label: str
) -> None:
    """One declared metric is unambiguous, so the scan must examine it.

    Falling back to "not examined" here would report an unexamined gate for a
    spec that named its metric perfectly clearly -- the failure mode where a
    gate exists but never reaches a verdict.
    """

    spec = {"proxy_marker": "CONTROLLED-1", "metrics": metrics}
    capability = {"metrics": {"revenue": "proxy"}}
    assert proxy_labelling_scan(spec, "described as CONTROLLED-1", capability).passed, label


def test_two_declared_metrics_leave_the_scan_unexamined_rather_than_guessing() -> None:
    spec = {"proxy_marker": "CONTROLLED-1", "metrics": ["revenue", "margin"]}
    capability = {"metrics": {"revenue": "proxy", "margin": "proxy"}}
    result = proxy_labelling_scan(spec, "described as CONTROLLED-1", capability)
    assert not result.passed
    assert not result.examined
    assert "proxy_metric_not_examined" in result.codes


@pytest.mark.parametrize(
    ("marker", "catalog", "expected_code"),
    [
        ("MISSING-FROM-SPEC", "described as MISSING-FROM-SPEC", "proxy_marker_missing_from_spec"),
        ("CONTROLLED-1", "no marker here", "proxy_marker_missing_from_catalog"),
    ],
)
def test_each_marker_surface_is_reported_separately(
    marker: str, catalog: str, expected_code: str
) -> None:
    """Two surfaces, two codes: one merged code cannot say which one drifted."""

    spec = {"proxy_marker": "CONTROLLED-1", "metric": "revenue"}
    capability = {"metrics": {"revenue": "proxy"}}
    result = proxy_labelling_scan(spec, catalog, capability, marker=marker)
    assert not result.passed
    assert expected_code in result.codes


# ---------------------------------------------------------------------------
# Fail-always is as broken as fail-never
#
# `supported_path_scan` reaches `calls_curl` for every call node in the closure.
# Mutation testing found that both of its early `return False` guards could be
# flipped to `return True` -- making every ordinary function call read as a
# subprocess curl invocation, and every clean closure fail the scan -- with the
# whole suite still green. Nothing asserted that a clean closure passes.
# ---------------------------------------------------------------------------


CLEAN_CLOSURE = '''\
"""An ordinary transform closure that violates nothing."""

import json
import os.path
from collections import Counter


def load(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def summarise(rows):
    counts = Counter(row["region"] for row in rows)
    return {"regions": dict(counts), "total": len(rows)}


def run(path):
    return summarise(load(os.path.join(path, "rows.json")))
'''


def test_a_clean_closure_passes_the_supported_path_scan(tmp_path: Path) -> None:
    """A scan that rejects everything grades nothing, and reads as strict."""

    module = tmp_path / "transform.py"
    module.write_text(CLEAN_CLOSURE, encoding="utf-8")

    result = supported_path_scan(module)

    assert result.passed, result.findings
    assert result.examined
    assert result.findings == ()


def test_a_sanctioned_file_is_skipped_without_ending_the_scan(tmp_path: Path) -> None:
    """Skipping the sanctioned client must not stop the walk.

    The files are walked in sorted order, so a sanctioned name that sorts first
    would hide every violation after it if the skip ended the loop instead of
    continuing it.
    """

    client = tmp_path / "aaa_client.py"
    client.write_text("import requests\n", encoding="utf-8")
    offender = tmp_path / "zzz_transform.py"
    offender.write_text("import httpx\n", encoding="utf-8")

    result = supported_path_scan(tmp_path, sanctioned_client=client)

    assert not result.passed
    assert [finding.value for finding in result.findings] == ["httpx"]


def test_an_unparseable_file_is_a_finding_rather_than_a_crash(tmp_path: Path) -> None:
    """A closure the scan cannot read is not a closure the scan approved."""

    broken = tmp_path / "broken.py"
    broken.write_text("def (:\n", encoding="utf-8")

    result = supported_path_scan(tmp_path)

    assert not result.passed
    assert "supported_path_scan_error" in result.codes
    assert result.examined, "the file was found and read; only its syntax failed"


def test_a_dynamic_import_of_a_non_string_constant_is_not_a_crash(tmp_path: Path) -> None:
    """`__import__(5)` is nonsense, but a grading scan may not raise on nonsense."""

    module = tmp_path / "odd.py"
    module.write_text("__import__(5)\nimportlib.import_module(None)\n", encoding="utf-8")

    assert supported_path_scan(module).passed
