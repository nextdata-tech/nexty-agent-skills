"""Every input shape the oracles accept must actually be exercised.

The oracles in ``dp_scenarios.grading.oracles`` are deliberately permissive
about how the artifact reaches them: a counter snapshot may be a mapping or a
live server object with a ``snapshot()`` method; a capability manifest may be a
mapping, an object with ``as_dict``/``to_dict``, a JSON file path, or a
callable; a page count may be recorded as ``pages`` or ``page_count``.

Automated mutation testing (see "Mutation testing" in ``README.md``) showed that
the accepted shapes are covered by their happy mapping form and nothing else.
Every mutant inside ``counter_oracle``'s ``callable(getattr(snapshot,
"snapshot"))`` guard survived -- including ones that make the expression raise
``TypeError`` -- because no test has ever handed that oracle an object rather
than a dict.  An accepted input shape that no test reaches is a branch that can
be broken silently and, since these oracles fail *closed* into
``NOT_EXAMINED``, breaking it turns a graded scenario into an ungraded one
without turning anything red.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dp_scenarios.grading.oracles import (
    OracleState,
    capability_oracle,
    counter_oracle,
    load_fixture_manifest,
)


class _LiveCounters:
    """A stand-in for the mock REST server's counter port."""

    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload
        self.calls = 0

    def snapshot(self) -> dict[str, object]:
        self.calls += 1
        return self._payload


def test_a_counter_source_with_a_snapshot_method_is_read_through_it() -> None:
    """The live source is an object, not a dict; the oracle must call it."""

    source = _LiveCounters({"total": 3, "pages": 2})

    result = counter_oracle(source, call_ceiling=5, expected_pages=2)

    assert source.calls == 1, "the oracle did not call snapshot()"
    assert result.state is OracleState.SATISFIED
    assert result.value == {"total": 3, "pages": 2}


def test_a_counter_source_whose_snapshot_attribute_is_not_callable_is_not_called() -> None:
    """``hasattr`` alone is not enough: a data attribute named `snapshot` is data.

    Calling it would raise ``TypeError`` out of a grading oracle, which turns a
    scenario's verdict into a crash rather than a finding.
    """

    class _DataAttribute:
        snapshot = {"total": 1}

    result = counter_oracle(_DataAttribute())

    assert result.state is OracleState.VIOLATED
    assert "counters_shape_invalid" in result.codes


def test_a_counter_source_returning_none_from_snapshot_is_not_examined() -> None:
    """A server that has not started yet reports nothing, which is not a pass."""

    result = counter_oracle(_LiveCounters(None))  # type: ignore[arg-type]

    assert result.state is OracleState.NOT_EXAMINED
    assert "counters_not_examined" in result.codes


@pytest.mark.parametrize("page_key", ["pages", "page_count"])
def test_either_recorded_page_key_is_read(page_key: str) -> None:
    """Two recorders, two spellings; ignoring one silently unexamines the gate."""

    satisfied = counter_oracle({"total": 4, page_key: 2}, expected_pages=2)
    assert satisfied.state is OracleState.SATISFIED, page_key

    incomplete = counter_oracle({"total": 4, page_key: 1}, expected_pages=2)
    assert incomplete.state is OracleState.VIOLATED, page_key
    assert "pagination_incomplete" in incomplete.codes, page_key


@pytest.mark.parametrize(
    ("total", "label"),
    [(True, "bool-is-not-a-count"), (-1, "negative"), ("3", "string"), (1.5, "float")],
)
def test_a_total_that_is_not_a_count_is_a_shape_violation(total: object, label: str) -> None:
    """``True == 1`` in Python, so a bool would otherwise pass every ceiling."""

    result = counter_oracle({"total": total}, call_ceiling=10)

    assert result.state is OracleState.VIOLATED, label
    assert "counters_shape_invalid" in result.codes, label
    assert "call_ceiling_violated" not in result.codes, label


def test_a_total_exactly_on_the_ceiling_is_satisfied_and_one_over_is_not() -> None:
    """The ceiling is inclusive; an off-by-one here silently fails clean runs."""

    assert counter_oracle({"total": 5}, call_ceiling=5).state is OracleState.SATISFIED
    assert counter_oracle({"total": 6}, call_ceiling=5).state is OracleState.VIOLATED


def test_a_missing_page_count_is_unexamined_while_a_ceiling_breach_is_violated() -> None:
    """A run that broke a ceiling *and* lost its page count is violated, not unexamined.

    The state collapse reads "all findings are pagination_not_examined", so an
    inverted condition here would launder a real ceiling breach into "we did not
    look".
    """

    both = counter_oracle({"total": 99}, call_ceiling=5, expected_pages=2)
    assert both.state is OracleState.VIOLATED
    assert "call_ceiling_violated" in both.codes
    assert "pagination_not_examined" in both.codes

    only_pages = counter_oracle({"total": 3}, call_ceiling=5, expected_pages=2)
    assert only_pages.state is OracleState.NOT_EXAMINED


# ---------------------------------------------------------------------------
# capability_oracle / _json_from_control
# ---------------------------------------------------------------------------


MANIFEST = {"metrics": {"revenue": "proxy"}}


def test_a_capability_manifest_nested_under_its_own_key_is_unwrapped() -> None:
    """Control endpoints wrap the manifest; the oracle must look inside."""

    assert capability_oracle({"capability": MANIFEST}).state is OracleState.SATISFIED
    assert capability_oracle({"capability": MANIFEST}).value == MANIFEST


def test_a_capability_key_that_is_not_a_mapping_is_not_unwrapped() -> None:
    """Unwrapping a string would read as "metrics are absent" instead of as shape."""

    result = capability_oracle({"capability": "yes", "metrics": {"revenue": "proxy"}})

    assert result.state is OracleState.SATISFIED
    assert result.value == {"capability": "yes", "metrics": {"revenue": "proxy"}}


@pytest.mark.parametrize("method", ["as_dict", "to_dict"])
def test_a_capability_source_is_read_through_either_dict_method(method: str) -> None:
    source = type("_Source", (), {method: staticmethod(lambda: MANIFEST)})()

    assert capability_oracle(source).state is OracleState.SATISFIED, method


def test_a_callable_capability_source_is_invoked() -> None:
    assert capability_oracle(lambda: MANIFEST).state is OracleState.SATISFIED


def test_a_capability_source_on_disk_is_read_as_json(tmp_path: Path) -> None:
    path = tmp_path / "capability.json"
    path.write_text(json.dumps(MANIFEST), encoding="utf-8")

    assert capability_oracle(path).state is OracleState.SATISFIED
    assert capability_oracle(str(path)).state is OracleState.SATISFIED


def test_an_unreadable_or_malformed_capability_source_is_not_examined(tmp_path: Path) -> None:
    """The oracle swallows the exception on purpose -- into not-examined, never into a pass."""

    missing = capability_oracle(tmp_path / "absent.json")
    assert missing.state is OracleState.NOT_EXAMINED
    assert "capability_not_examined" in missing.codes

    malformed = tmp_path / "malformed.json"
    malformed.write_text("{not json", encoding="utf-8")
    assert capability_oracle(malformed).state is OracleState.NOT_EXAMINED

    def _raises() -> object:
        raise RuntimeError("control port refused the connection")

    raised = capability_oracle(_raises)
    assert raised.state is OracleState.NOT_EXAMINED
    assert any("refused" in finding.detail for finding in raised.findings)


def test_a_capability_source_that_is_json_but_not_an_object_is_not_examined(tmp_path: Path) -> None:
    path = tmp_path / "list.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")

    assert capability_oracle(path).state is OracleState.NOT_EXAMINED


def test_a_manifest_whose_metrics_are_the_wrong_shape_is_violated_not_unexamined() -> None:
    """Read-and-wrong and could-not-read are different verdicts; only one is a defect."""

    result = capability_oracle({"metrics": ["revenue"]})

    assert result.state is OracleState.VIOLATED
    assert "capability_shape_invalid" in result.codes


# ---------------------------------------------------------------------------
# load_fixture_manifest
# ---------------------------------------------------------------------------


def test_a_fixture_directory_resolves_to_its_manifest_file(tmp_path: Path) -> None:
    (tmp_path / "fixture-manifest.json").write_text('{"gold": "gold.json"}', encoding="utf-8")

    assert load_fixture_manifest(tmp_path) == {"gold": "gold.json"}
    assert load_fixture_manifest(str(tmp_path)) == {"gold": "gold.json"}
    assert load_fixture_manifest(tmp_path / "fixture-manifest.json") == {"gold": "gold.json"}


def test_a_mapping_is_passed_through_untouched() -> None:
    manifest = {"gold": "gold.json"}

    assert load_fixture_manifest(manifest) is manifest


def test_an_absent_or_unparseable_manifest_is_not_examined(tmp_path: Path) -> None:
    absent = load_fixture_manifest(tmp_path)
    assert getattr(absent, "state", None) is OracleState.NOT_EXAMINED
    assert "fixture_manifest_not_examined" in getattr(absent, "codes", ())

    (tmp_path / "fixture-manifest.json").write_text("{not json", encoding="utf-8")
    malformed = load_fixture_manifest(tmp_path)
    assert getattr(malformed, "state", None) is OracleState.NOT_EXAMINED


def test_a_manifest_that_parses_to_a_non_object_is_violated(tmp_path: Path) -> None:
    """Parsed-and-wrong is a defect in the fixture, not a fixture we could not read."""

    (tmp_path / "fixture-manifest.json").write_text("[1, 2]", encoding="utf-8")

    result = load_fixture_manifest(tmp_path)

    assert getattr(result, "state", None) is OracleState.VIOLATED
    assert "fixture_manifest_invalid" in getattr(result, "codes", ())


# ---------------------------------------------------------------------------
# The control-endpoint branch
#
# `_json_from_control` fetches over HTTP when the source is a URL. No test had
# ever taken that branch, so mutation testing could rewrite the scheme prefixes,
# the Accept header, the timeout and the decoding with the suite still green --
# 26 surviving mutants in one nine-line function. The network is stubbed here
# rather than served: what needs pinning is which sources are treated as URLs
# and what is asked for, not that urllib works.
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


@pytest.fixture
def recorded_urlopen(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    """Replace urlopen so a leaked real request fails loudly instead of hanging."""

    calls: list[object] = []

    def fake_urlopen(request: object, timeout: object = None) -> _FakeResponse:
        calls.append((request, timeout))
        return _FakeResponse(json.dumps(MANIFEST).encode("utf-8"))

    monkeypatch.setattr("dp_scenarios.grading.oracles.urlopen", fake_urlopen)
    return calls


@pytest.mark.parametrize("scheme", ["http", "https"])
def test_a_control_endpoint_url_is_fetched_for_both_schemes(
    recorded_urlopen: list[object], scheme: str
) -> None:
    url = f"{scheme}://control.test/capability"

    result = capability_oracle(url)

    assert result.state is OracleState.SATISFIED, scheme
    request, timeout = recorded_urlopen[0]
    assert request.full_url == url
    assert request.headers.get("Accept") == "application/json"
    assert timeout is not None, "an unbounded control fetch can hang a graded run"


def test_a_control_endpoint_uppercase_scheme_is_not_treated_as_a_url(
    recorded_urlopen: list[object],
) -> None:
    """The prefix test is literal, so `HTTP://` reads as a filesystem path.

    Pinned rather than fixed: it is the honest description of the branch, and a
    change that starts accepting uppercase schemes should have to say so here.
    """

    result = capability_oracle("HTTP://control.test/capability")

    assert recorded_urlopen == []
    assert result.state is OracleState.NOT_EXAMINED


def test_a_control_endpoint_that_is_not_json_is_not_examined(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request: object, timeout: object = None) -> _FakeResponse:
        return _FakeResponse(b"<html>gateway timeout</html>")

    monkeypatch.setattr("dp_scenarios.grading.oracles.urlopen", fake_urlopen)

    result = capability_oracle("http://control.test/capability")

    assert result.state is OracleState.NOT_EXAMINED
    assert "capability_not_examined" in result.codes


def test_a_control_endpoint_that_refuses_the_connection_is_not_examined(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A dead control port is "we could not look", never "nothing was wrong"."""

    def fake_urlopen(request: object, timeout: object = None) -> _FakeResponse:
        raise OSError("connection refused")

    monkeypatch.setattr("dp_scenarios.grading.oracles.urlopen", fake_urlopen)

    result = capability_oracle("https://control.test/capability")

    assert result.state is OracleState.NOT_EXAMINED
    assert any("refused" in finding.detail for finding in result.findings)
