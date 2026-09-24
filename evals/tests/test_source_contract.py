"""Tests for the self-contained source/coverage/ratio recipe."""

from __future__ import annotations

import ast
import importlib.util
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "src" / "nxd-generate-data-product" / "scripts" / "source_contract.py"
GUIDANCE = (
    REPO_ROOT / "src" / "nxd-generate-data-product" / "SKILL.md",
    REPO_ROOT / "src" / "nxd-generate-data-product" / "reference" / "pre-capture-audit.md",
    REPO_ROOT / "src" / "nxd-generate-data-product" / "reference" / "derived-models.md",
)
DESCRIPTION_GUIDANCE = (
    REPO_ROOT / "src" / "nxd-generate-data-product" / "SKILL.md",
    REPO_ROOT / "src" / "nxd-generate-data-product" / "reference" / "nxd-spec-api.md",
    REPO_ROOT / "src" / "nxd-generate-data-product" / "reference" / "pre-capture-audit.md",
    REPO_ROOT / "src" / "nxd-generate-data-product" / "reference" / "models-example.md",
    REPO_ROOT / "src" / "nxd-generate-data-product" / "reference" / "derived-models.md",
    REPO_ROOT / "src" / "nxd-generate-data-product" / "reference" / "llm-judgments.md",
    REPO_ROOT / "src" / "nxd-generate-data-product" / "reference" / "derivation-plan.md",
)
_FENCE_RE = re.compile(r"(?ms)^```[^\n]*\n(.*?)^```\s*(?:\n|$)")
_LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)")


def _role_description_calls(tree: ast.AST) -> list[str]:
    """Return semantic role calls that put description on the role itself."""
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = node.func.id if isinstance(node.func, ast.Name) else None
        if name in {"dimension", "metric"} and any(
            keyword.arg == "description" for keyword in node.keywords
        ):
            found.append(name)
    return found


def _fenced_role_description_errors(text: str) -> list[str]:
    errors = []
    for index, match in enumerate(_FENCE_RE.finditer(text), start=1):
        body = match.group(1)
        if "# DEPRECATED" in body or not re.search(
            r"\b(?:dimension|metric)\s*\(|\bdescription\s*=", body
        ):
            continue
        parsed = None
        for candidate in (body, "{\n" + body + "\n}"):
            try:
                parsed = ast.parse(candidate)
                break
            except SyntaxError:
                continue
        if parsed is None:
            errors.append(f"fence {index}: relevant example is not parseable")
            continue
        roles = _role_description_calls(parsed)
        if roles:
            errors.append(f"fence {index}: {', '.join(roles)} carries description=")
    return errors


def _markdown_prose_blocks(text: str) -> list[tuple[str, str]]:
    """Collect inline Markdown prose, joining soft wraps but not code fences."""
    text = _FENCE_RE.sub("", text)
    blocks: list[tuple[str, str]] = []
    current: list[str] = []
    kind = "paragraph"

    def flush() -> None:
        nonlocal current
        if current:
            blocks.append((kind, " ".join(line.strip() for line in current)))
            current = []

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            flush()
        elif stripped.startswith("|"):
            flush()
            blocks.append(("table", stripped))
        elif _LIST_ITEM_RE.match(line):
            flush()
            kind = "list"
            current = [line]
        elif current and kind == "list" and line[:1].isspace():
            current.append(line)
        else:
            if current and kind == "list":
                flush()
            kind = "paragraph"
            current.append(line)
    flush()
    return blocks


def _inline_role_description(span: str) -> bool:
    """Find description= at argument depth one inside dimension()/metric()."""
    for call in re.finditer(r"\b(dimension|metric)\s*\(", span):
        depth = 1
        quote = None
        escaped = False
        index = call.end()
        while index < len(span) and depth:
            char = span[index]
            if quote:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    quote = None
                index += 1
                continue
            if char in {"'", '"'}:
                quote = char
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            elif depth == 1 and re.match(r"description\s*=", span[index:]):
                return True
            index += 1
    return False


def _inline_role_description_errors(text: str) -> list[str]:
    errors = []
    for kind, block in _markdown_prose_blocks(text):
        if kind == "table" and "deprecated" in block.lower():
            continue
        if kind == "list" and "`description=` is **deprecated**" in block:
            continue
        for span in re.findall(r"`([^`]+)`", block):
            if _inline_role_description(span):
                errors.append(f"{kind}: {span}")
    return errors


def _recipe():
    spec = importlib.util.spec_from_file_location("source_contract_recipe", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_ratio_guidance_bans_reducing_row_level_metrics() -> None:
    """The docs must not turn a row-level ratio into an aggregate metric."""
    for path in GUIDANCE:
        text = path.read_text(encoding="utf-8")
        assert "row-level ratio" in text, f"{path} lost the row-level ratio rule"
        assert "Agg.AVG" in text, f"{path} lost the explicit Agg.AVG ban"
        assert "any other reduction" in text, f"{path} weakened the reduction ban"
        assert "additive numerator" in text, f"{path} lost aggregate ratio guidance"
        assert "assert_row_ratios" in text, f"{path} lost the row-grain alternative"


def test_description_guidance_uses_field_level_inheritance() -> None:
    texts = {path: path.read_text(encoding="utf-8") for path in DESCRIPTION_GUIDANCE}
    prose = "\n".join(_FENCE_RE.sub("", text) for text in texts.values())
    forbidden = (
        "write it on the semantic role",
        "put the semantic description on",
        "wrapper-only text is not reachable",
        "wrapper-only text does not make a semantic role description reachable",
        "struct.description_unreachable",
    )
    for phrase in forbidden:
        assert phrase not in prose.lower(), f"stale description rule remains: {phrase}"

    skill = texts[DESCRIPTION_GUIDANCE[0]]
    api = texts[DESCRIPTION_GUIDANCE[1]]
    audit = texts[DESCRIPTION_GUIDANCE[2]]
    skill_flat = re.sub(r"\s+", " ", skill)
    api_flat = re.sub(r"\s+", " ", api)
    audit_flat = re.sub(r"\s+", " ", audit)
    assert "the role inherits it" in skill_flat
    assert "description=` is accepted there too, and it is the placement to prefer" in api_flat
    assert "Both reach the querying agent" in api
    assert "`metric_field(description=...)`" in api
    assert "Place descriptions on the enclosing `field()` / `metric_field()`" in audit_flat


def test_fenced_examples_put_descriptions_on_wrappers_or_mark_deprecated() -> None:
    text = "".join(path.read_text(encoding="utf-8") for path in DESCRIPTION_GUIDANCE)
    errors = _fenced_role_description_errors(text)
    assert errors == []


def test_fenced_checker_parses_dict_entries_and_allows_deprecated_example() -> None:
    current = '''```python
"amount": field(number(), dimension(name="amount", description="Total.")),
```'''
    deprecated = '''```python
# DEPRECATED — compatibility example only
"amount": field(number(), dimension(name="amount", description="Total.")),
```'''
    assert _fenced_role_description_errors(current) == [
        "fence 1: dimension carries description=",
    ]
    assert _fenced_role_description_errors(deprecated) == []


def test_inline_checker_joins_soft_wraps_and_limits_exemptions() -> None:
    text = '''Paragraph with `dimension(name="x",
description="bad")` split across lines.

- List example `metric(Agg.SUM,
  description="bad")` split across lines.

| old declaration | `dimension(description="bad")` |
| note | deprecated |

- `description=` is **deprecated** on a role: `metric(description="legacy")`.
'''
    errors = _inline_role_description_errors(text)
    assert len(errors) == 3
    assert [error.split(":", 1)[0] for error in errors] == [
        "paragraph",
        "list",
        "table",
    ]


def test_live_inline_guidance_has_no_role_level_descriptions() -> None:
    for path in DESCRIPTION_GUIDANCE:
        text = path.read_text(encoding="utf-8")
        errors = _inline_role_description_errors(text)
        assert errors == [], f"{path} has stale inline guidance: {errors}"


def test_desktop_infra_guidance_keeps_exact_local_driver_ids() -> None:
    text = (REPO_ROOT / "src" / "nxd-generate-data-product" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    profile = (
        REPO_ROOT
        / "src"
        / "nxd-generate-data-product"
        / "reference"
        / "infra-profile.md"
    ).read_text(encoding="utf-8")
    normalized_text = re.sub(r"\s+", " ", text)
    drivers = {
        "duckdb": "nxd:local/duckdb/storage:0.1.0",
        "python-compute": "nxd:local/python/compute:0.1.0",
        "csv-source": "nxd:local/file/storage:0.1.0",
    }
    for service, driver_id in drivers.items():
        assert f"`{service}` = `{driver_id}`" in normalized_text
        assert re.search(
            rf"- name: {re.escape(service)}\n\s+driver: {re.escape(driver_id)}",
            profile,
        )
    assert "never shorten them to a bare local driver" in normalized_text


def test_api_source_guidance_preserves_companion_requirements() -> None:
    text = (REPO_ROOT / "src" / "nxd-generate-data-product" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    normalized_text = re.sub(r"\s+", " ", text)
    assert "the only absent companion is the endpoint map" in normalized_text
    assert "endpoint_<model>` profile attributes" in normalized_text
    assert (
        "additionally require the closure-local `connectivity_check.py` probe"
        in normalized_text
    )
    assert "make it pass before authoring" in normalized_text


def test_read_csv_rows_checks_required_and_duplicate_headers(tmp_path: Path):
    recipe = _recipe()
    source = _write(tmp_path / "source.csv", "id,name\n1,one\n")
    assert recipe.read_csv_rows(
        source, required_columns=("id",), source_name="source"
    ) == [{"id": "1", "name": "one"}]

    with pytest.raises(RuntimeError, match="missing required columns"):
        recipe.read_csv_rows(
            source, required_columns=("campaign_name",), source_name="source"
        )

    missing_value = _write(tmp_path / "missing-value.csv", "id,name\n1\n")
    with pytest.raises(RuntimeError, match="missing or blank values"):
        recipe.read_csv_rows(
            missing_value, required_columns=("id", "name"), source_name="source"
        )

    blank_value = _write(tmp_path / "blank-value.csv", "id,name\n1,   \n")
    with pytest.raises(RuntimeError, match="missing or blank values"):
        recipe.read_csv_rows(
            blank_value, required_columns=("id", "name"), source_name="source"
        )

    bom_source = tmp_path / "bom.csv"
    bom_source.write_bytes(b"\xef\xbb\xbfid,name\n1,one\n")
    assert recipe.read_csv_rows(
        bom_source, required_columns=("id", "name"), source_name="source"
    ) == [{"id": "1", "name": "one"}]

    invalid_encoding = tmp_path / "invalid-encoding.csv"
    invalid_encoding.write_bytes(b"id,name\n1,\xff\n")
    with pytest.raises(RuntimeError, match="could not read or decode"):
        recipe.read_csv_rows(
            invalid_encoding, required_columns=("id", "name"), source_name="source"
        )

    duplicate = _write(tmp_path / "duplicate.csv", "id,id\n1,one\n")
    with pytest.raises(RuntimeError, match="duplicate headers"):
        recipe.read_csv_rows(
            duplicate, required_columns=("id",), source_name="source"
        )

    with pytest.raises(ValueError, match="required_columns must not be empty"):
        recipe.read_csv_rows(source, required_columns=(), source_name="source")


def test_read_csv_rows_can_require_an_exact_header_set(tmp_path: Path):
    recipe = _recipe()
    source = _write(tmp_path / "source.csv", "id,name\n1,one\n")
    with pytest.raises(RuntimeError, match="approved header set"):
        recipe.read_csv_rows(
            source,
            required_columns=("id",),
            expected_columns=("id",),
            source_name="source",
        )


def test_coverage_summary_reports_each_side_and_rejects_unknown_ids():
    recipe = _recipe()
    summary = recipe.coverage_summary(
        [{"id": "A"}, {"id": "B"}, {"id": "C"}],
        ["A", "B"],
        id_column="id",
        source_name="spend",
    )
    assert summary == {
        "source": "spend",
        "row_count": 3,
        "matched_count": 2,
        "coverage_bps": 6667,
        "unmatched_ids": ["C"],
    }
    with pytest.raises(RuntimeError, match="not in the source"):
        recipe.coverage_summary(
            [{"id": "A"}], ["MISSING"], id_column="id", source_name="spend"
        )


def test_aggregate_ratio_uses_additive_totals_not_sum_of_row_ratios():
    recipe = _recipe()
    source = [
        {"spend_cents": "100", "conversions": "1"},
        {"spend_cents": "100", "conversions": "3"},
    ]
    recipe.assert_aggregate_ratio(
        source,
        {"cpa_cents": "50"},
        numerator_column="spend_cents",
        denominator_column="conversions",
        ratio_column="cpa_cents",
        metric_name="cpa",
    )
    with pytest.raises(RuntimeError, match="do not sum row-level ratios"):
        recipe.assert_aggregate_ratio(
            source,
            {"cpa_cents": "133"},
            numerator_column="spend_cents",
            denominator_column="conversions",
            ratio_column="cpa_cents",
            metric_name="cpa",
        )

    # Fractional rates need an explicit output quantum; the default remains
    # integer cent/unit rounding for metrics such as CPA in cent-scaled inputs.
    recipe.assert_aggregate_ratio(
        [{"conversions": "34", "visits": "1000"}],
        {"conversion_rate": "0.034"},
        numerator_column="conversions",
        denominator_column="visits",
        ratio_column="conversion_rate",
        metric_name="conversion_rate",
        quantum="0.001",
    )
    with pytest.raises(RuntimeError, match="do not sum row-level ratios"):
        recipe.assert_aggregate_ratio(
            [{"conversions": "34", "visits": "1000"}],
            {"conversion_rate": "0"},
            numerator_column="conversions",
            denominator_column="visits",
            ratio_column="conversion_rate",
            metric_name="conversion_rate",
            quantum="0.001",
        )


def test_row_ratio_assertion_covers_the_non_aggregate_path():
    recipe = _recipe()
    rows = [
        {"spend_cents": "100", "conversions": "2", "cpa_cents": "50"},
        {"spend_cents": "100", "conversions": "4", "cpa_cents": "25"},
    ]
    recipe.assert_row_ratios(
        rows,
        numerator_column="spend_cents",
        denominator_column="conversions",
        ratio_column="cpa_cents",
        metric_name="cpa",
    )
    rows[1]["cpa_cents"] = "24"
    with pytest.raises(RuntimeError, match="does not equal"):
        recipe.assert_row_ratios(
            rows,
            numerator_column="spend_cents",
            denominator_column="conversions",
            ratio_column="cpa_cents",
            metric_name="cpa",
        )

    with pytest.raises(RuntimeError, match="row 1 ratio is missing or non-numeric"):
        recipe.assert_row_ratios(
            [{"spend_cents": "100", "cpa_cents": "50"}],
            numerator_column="spend_cents",
            denominator_column="conversions",
            ratio_column="cpa_cents",
            metric_name="cpa",
        )


def test_ratio_rejects_non_positive_denominator():
    recipe = _recipe()
    with pytest.raises(RuntimeError, match="positive denominator"):
        recipe.ratio_cents(1, 0, metric_name="cpa")


def test_recipe_source_runs_after_copying_into_a_closure(tmp_path: Path):
    """The shipped recipe is executable after leaving the skill tree."""
    copied = tmp_path / "transform" / "main.py"
    copied.parent.mkdir()
    copied.write_text(SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
    spec = importlib.util.spec_from_file_location("copied_source_contract", copied)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.ratio_cents("100", "4", metric_name="cpa") == 25


def test_promise_verifiers_are_independent_and_review_sweeps_defect_classes() -> None:
    # Live B3 and B1 runs paid one reset, recapture and review cycle for each
    # sibling of the same defect. Each fresh review found one more
    # self-consistency-only verifier. The generator must author an independent
    # verifier per promised output, and the reviewer must sweep the whole class.
    def flat(*parts: str) -> str:
        return " ".join((REPO_ROOT.joinpath(*parts)).read_text(encoding="utf-8").split())

    contracts = flat("src", "nxd-generate-data-product", "reference", "custom-contracts.md")
    assert "Verify against an independent witness, one verifier per promised output." in contracts
    assert "Every output the approved blueprint promises gets its own verifier." in contracts

    review = flat("src", "nxd-review-closure", "SKILL.md")
    assert "### Sweep a defect class once you find it" in review
    assert "check every other promise, verifier, model and output in the capture for the same class in this same pass" in review


def test_metric_names_are_registry_unique_and_check_runs_before_capture() -> None:
    # A live B3 repair added `row_count` to three semantic views, following the
    # generator's own example. Spec compilation rejected the duplicates, and
    # validation surfaced only a bounded preflight code. The agent could not
    # read the finding because the skill called check_data_product optional.
    def flat(*parts: str) -> str:
        return " ".join((REPO_ROOT.joinpath(*parts)).read_text(encoding="utf-8").split())

    generator = flat("src", "nxd-generate-data-product", "SKILL.md")
    assert 'name="row_count"' not in generator
    assert 'name="<model>_row_count"' in generator
    assert "Metric names are global across the registry" in generator
    assert "call the `check_data_product` MCP tool on the authoring closure before returning it" in generator

    job_loop = flat("src", "nxd-run-job-loop", "SKILL.md")
    assert "Before every capture, including after a repair, call the `check_data_product` MCP tool" in job_loop
    assert "optional evidence only and are never execution authority" not in job_loop

    workflow = flat("src", "nxd-run-job-loop", "reference", "workflow-v2.md")
    assert "## When validation fails" in workflow
    assert "`recovery: repair_then_retry` means the retained closure has a defect you can fix" in workflow


def test_models_imports_stay_inside_nxd_spec() -> None:
    # Supervisor validation rejects nxd.core.* imports in models.py. The skills
    # told agents to import DurationUnit from nxd.core.yaml_schemas, and a live
    # B1 run paid a failed validation plus recapture and re-review to learn it.
    for relative in (
        "src/nxd-generate-data-product/SKILL.md",
        "src/nxd-build-semantic-data-product/SKILL.md",
        "src/nxd-generate-data-product/mapper/CONTRACT.md",
    ):
        text = (REPO_ROOT / relative).read_text(encoding="utf-8")
        assert "nxd.core.yaml_schemas" not in text, relative
    api = (REPO_ROOT / "src/nxd-generate-data-product/reference/nxd-spec-api.md").read_text(
        encoding="utf-8"
    )
    assert "from nxd.spec.data_types import DurationUnit" in api
    assert "never import `DurationUnit`\nfrom `nxd.core.yaml_schemas`" in api


def test_review_grades_verification_gaps_by_what_they_hide_today() -> None:
    # Live B3 reviews raised a new MEDIUM "verifier not independent enough"
    # finding every round while confirming the numbers were correct. The job
    # loop blocks on MEDIUM, so the run could never publish.
    text = " ".join(
        (REPO_ROOT / "src" / "nxd-review-closure" / "SKILL.md").read_text(encoding="utf-8").split()
    )
    assert "Grade a verification gap by what it hides today, not by what a future bug might do" in text
    assert "A LOW gap is advisory." in text
    assert "Robustness against a hypothetical future bug is never HIGH or MEDIUM on its own" in text


def test_pending_review_round_is_closed_before_reset() -> None:
    # A live B3 run published with all later reviews clear, but left an
    # earlier needs_user round with user_decision null, which failed the
    # construction review check by one point.
    text = " ".join(
        (REPO_ROOT / "src" / "nxd-run-job-loop" / "reference" / "workflow-v2.md")
        .read_text(encoding="utf-8")
        .split()
    )
    assert "Close the pending review round before resetting." in text
    assert "update that same round in `review-record.json` before calling `reset_workflow` or appending another round" in text


def test_advisory_only_review_rounds_report_clear() -> None:
    # The supervisor satisfies review only on a clear verdict with no findings.
    # A live B3 agent held publication for a single LOW advisory claim after
    # confirming every fix, because nothing said an advisory-only round is clear.
    text = " ".join(
        (REPO_ROOT / "src" / "nxd-run-job-loop" / "reference" / "workflow-v2.md")
        .read_text(encoding="utf-8")
        .split()
    )
    assert "A round whose only claims are `LOW` is clear once you resolve them." in text
    assert "Never hold publication for an advisory claim" in text
    assert "never downgrade a `HIGH` or `MEDIUM` claim to reach this path" in text
    # A live B3 agent then left proposed_effect empty on the advisory note; the
    # ledger validator rejected the round and construction could not pair it.
    assert "a non-empty `proposed_effect` that says no closure change follows" in text
    assert "The ledger validator rejects an empty `proposed_effect`" in text


def test_validation_failure_facts_are_repaired_first() -> None:
    # A live B1 agent retried a failed validation five times blind: the
    # supervisor now reports the failed contracts and exception class, and
    # check_data_product cannot reproduce a source-dependent failure.
    text = " ".join(
        (REPO_ROOT / "src" / "nxd-run-job-loop" / "reference" / "workflow-v2.md")
        .read_text(encoding="utf-8")
        .split()
    )
    assert "carries `failed_contracts` or `exception_class`, repair those first" in text
    assert "`check_data_product` does not execute against a live source" in text
