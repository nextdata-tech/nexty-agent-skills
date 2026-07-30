#!/usr/bin/env python3
"""Validate a dp-spec.md — the IR between user intent and a generated closure.

Deterministic only. This finds gaps a script can find with certainty: an
incomplete scale, weights that do not sum, a verdict with no mapping, a gate
with no UNKNOWN rule, a ruling with no ledger row. It does NOT judge whether a
rubric is good or whether the model plan answers the questions — that stays the
policy read-back's job.

Usage:
    python3 scripts/validate_dp_spec.py path/to/dp-spec.md
    python3 scripts/validate_dp_spec.py path/to/dp-spec.md --json

Exit codes:
    0  compilable (warnings may be present)
    1  errors — the spec cannot be compiled into a closure
    2  the file could not be read or parsed at all
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - environment guard
    print("dp-spec validation needs PyYAML: pip install pyyaml", file=sys.stderr)
    sys.exit(2)


SPEC_VERSION = 1

REQUIRED_FRONTMATTER = ("dp_spec_version", "name", "workflow", "status")
STATUS_VALUES = ("draft", "proposed", "approved")

REQUIRED_SECTIONS = ("intent", "questions", "sources", "population", "models")
KNOWN_SECTIONS = REQUIRED_SECTIONS + (
    "gates",
    "criteria",
    "verdicts",
    "judgments",
    "schedule",
    "outputs",
    "decisions",
    "open_questions",
)

MODEL_KINDS = ("base", "derived", "view", "reference")
SOURCE_TYPES = ("csv", "file", "database", "api")

DECISION_STATUS = ("confirmed", "proposed", "blocked")
DECISION_PROVENANCE = (
    "user_confirmed",
    "agent_authored",
    "source_derived",
    "deferred",
)

PRODUCED_BY = ("agent", "user", "source")
RERUNS = ("incremental", "full")
DISPOSITIONS = ("blocked", "deferred", "answered")

NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
WEIGHT_TOLERANCE = 0.001

# A credential VALUE smuggled into the spec. Key names are fine and expected;
# anything that looks like a populated secret is not.
CREDENTIAL_VALUE_RE = re.compile(
    r"\b(password|passwd|secret|api[_-]?key|token|bearer|private[_-]?key)\b\s*[:=]\s*\S+",
    re.IGNORECASE,
)
CREDENTIAL_PLACEHOLDERS = frozenset(
    {"null", "none", "~", "<redacted>", "redacted", "[]", "{}", "''", '""', "..."}
)

# Model kinds/names whose rows are an aggregate or a regrain — never append-safe,
# so `incremental: true` over them is the silent-truncation bug.
REGRAIN_HINT_RE = re.compile(
    r"\b(monthly|daily|weekly|rollup|roll-up|aggregate|aggregated|summary|"
    r"per[_ -]month|regrain|collapsed?)\b",
    re.IGNORECASE,
)


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    @property
    def ok(self) -> bool:
        return not self.errors


def split_frontmatter(text: str) -> tuple[dict, str]:
    """Return (frontmatter dict, body). Raises ValueError when absent/invalid."""
    if not text.startswith("---"):
        raise ValueError("no YAML frontmatter — the file must open with '---'")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError("unterminated YAML frontmatter — needs a closing '---'")
    loaded = yaml.safe_load(parts[1])
    if not isinstance(loaded, dict):
        raise ValueError("frontmatter is not a YAML mapping")
    return loaded, parts[2]


def split_sections(body: str) -> dict[str, str]:
    """Split the body on '## ' headings. Later duplicates overwrite earlier."""
    sections: dict[str, str] = {}
    current: str | None = None
    buf: list[str] = []
    for line in body.splitlines():
        if line.startswith("## "):
            if current is not None:
                sections[current] = "\n".join(buf).strip()
            current = line[3:].strip().lower().replace(" ", "_")
            buf = []
        elif current is not None:
            buf.append(line)
    if current is not None:
        sections[current] = "\n".join(buf).strip()
    return sections


def load_yaml_section(name: str, raw: str, report: Report):
    """Parse a section body as YAML. Prose-only sections stay strings."""
    if not raw:
        return None
    try:
        return yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        report.error(f"[{name}] not parseable as YAML: {exc}")
        return None


def as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def check_frontmatter(fm: dict, report: Report) -> None:
    for key in REQUIRED_FRONTMATTER:
        if key not in fm:
            report.error(f"[frontmatter] missing required key '{key}'")

    version = fm.get("dp_spec_version")
    if version is not None and version != SPEC_VERSION:
        report.error(
            f"[frontmatter] dp_spec_version {version!r} is not the supported "
            f"version {SPEC_VERSION}"
        )

    name = fm.get("name")
    if isinstance(name, str) and not NAME_RE.match(name):
        report.error(
            f"[frontmatter] name {name!r} must be lowercase snake_case — it "
            "becomes the data product name"
        )

    status = fm.get("status")
    if status is not None and status not in STATUS_VALUES:
        report.error(
            f"[frontmatter] status {status!r} must be one of "
            f"{', '.join(STATUS_VALUES)}"
        )


def check_sections_present(sections: dict, report: Report) -> None:
    for name in REQUIRED_SECTIONS:
        if name not in sections:
            report.error(f"missing required section '## {name}'")
        elif not sections[name]:
            report.error(f"section '## {name}' is empty")

    for name in sections:
        if name not in KNOWN_SECTIONS:
            report.warn(
                f"unknown section '## {name}' — it will not compile to any "
                "closure artifact; carry it in open_questions if it matters"
            )


def check_sources(data, report: Report) -> None:
    entries = as_list(data)
    if not entries:
        report.error("[sources] no source entries")
        return

    labels = []
    for i, src in enumerate(entries):
        where = f"[sources][{i}]"
        if not isinstance(src, dict):
            report.error(f"{where} is not a mapping")
            continue

        stype = src.get("type")
        if stype not in SOURCE_TYPES:
            report.error(
                f"{where} type {stype!r} must be one of {', '.join(SOURCE_TYPES)}"
            )
        if not src.get("location"):
            report.error(f"{where} has no 'location'")
        if not src.get("scope"):
            report.error(
                f"{where} has no 'scope' — the population filter must be stated"
            )

        label = src.get("label")
        if label is not None:
            labels.append(label)

        for key in ("credential_keys", "credentials"):
            for value in as_list(src.get(key)):
                if isinstance(value, dict):
                    report.error(
                        f"{where} {key} carries a mapping — list KEY NAMES only, "
                        "never a value; credentials land in infra-profile.yaml"
                    )

    if len(entries) > 1:
        if len(labels) != len(entries):
            report.error(
                "[sources] with 2+ sources every source needs a distinct 'label'"
            )
        elif len(set(labels)) != len(labels):
            report.error(f"[sources] duplicate labels: {sorted(labels)}")


def check_credential_leak(raw_sections: dict, report: Report) -> None:
    for name in ("sources", "schedule", "outputs"):
        raw = raw_sections.get(name, "")
        for match in CREDENTIAL_VALUE_RE.finditer(raw):
            value = match.group(0).split(":", 1)[-1].split("=", 1)[-1].strip()
            if value.lower() in CREDENTIAL_PLACEHOLDERS:
                continue
            if value.startswith("[") or value.startswith("<"):
                continue
            report.error(
                f"[{name}] looks like a credential VALUE ({match.group(0)[:40]!r}) "
                "— this file is shareable; values belong only in the generated "
                "infra-profile.yaml"
            )


def check_population(data, report: Report) -> None:
    if isinstance(data, str):
        report.warn(
            "[population] is prose — a structured 'population'/'sample_rule'/"
            "'excludes' mapping lets the sample rule land as a decision row"
        )
        return
    if not isinstance(data, dict):
        report.error("[population] is not a mapping")
        return
    if not data.get("population"):
        report.error("[population] has no 'population' — state the full row set")


def check_models(data, report: Report) -> list[dict]:
    entries = [m for m in as_list(data) if isinstance(m, dict)]
    if not entries:
        report.error("[models] no model entries")
        return []

    names = []
    for i, model in enumerate(entries):
        where = f"[models][{i}]"
        name = model.get("name")
        if not name:
            report.error(f"{where} has no 'name'")
        else:
            names.append(name)
            where = f"[models:{name}]"
            if not NAME_RE.match(str(name)):
                report.error(
                    f"{where} name must be lowercase snake_case — the naming "
                    "invariant is byte-exact across models.py, .promise, "
                    "PHYSICAL_MODELS and the physical table"
                )

        kind = model.get("kind")
        if kind not in MODEL_KINDS:
            report.error(
                f"{where} kind {kind!r} must be one of {', '.join(MODEL_KINDS)}"
            )

        if not model.get("description"):
            report.error(
                f"{where} has no 'description' — describe_models is all a later "
                "consumer sees, so an undescribed model is unusable"
            )

        # A view is query-time only: no grain, no key, no physical table.
        if kind == "view":
            continue

        if not model.get("grain"):
            report.error(
                f"{where} has no 'grain' — one sentence naming what one row is"
            )
        if not as_list(model.get("key")):
            report.error(
                f"{where} has no 'key' — every promised physical model needs a "
                "primary key, base from a source column, derived from the grain"
            )

    dupes = {n for n in names if names.count(n) > 1}
    if dupes:
        report.error(f"[models] duplicate model names: {sorted(dupes)}")

    return entries


def check_gates(data, report: Report) -> None:
    for i, gate in enumerate(as_list(data)):
        where = f"[gates][{i}]"
        if not isinstance(gate, dict):
            report.error(f"{where} is not a mapping")
            continue
        gid = gate.get("id") or gate.get("name")
        if gid:
            where = f"[gates:{gid}]"
        if not gate.get("rule"):
            report.error(f"{where} has no 'rule'")

        unknown = gate.get("unknown")
        if unknown is None:
            report.error(
                f"{where} has no 'unknown' handling — an absent gate input must "
                "land UNKNOWN, and leaving it unstated is the gap the policy "
                "read-back exists to catch"
            )
        elif str(unknown).strip().upper() == "FAIL":
            report.error(
                f"{where} maps an absent input to FAIL — absence is never a "
                "judgement; it lands UNKNOWN"
            )


def check_criteria(data, report: Report) -> list[dict]:
    entries = [c for c in as_list(data) if isinstance(c, dict)]
    if not entries:
        report.error("[criteria] section present but has no criterion entries")
        return []

    total = 0.0
    weights_ok = True

    for i, crit in enumerate(entries):
        cid = crit.get("id") or crit.get("name") or i
        where = f"[criteria:{cid}]"

        weight = crit.get("weight")
        if weight is None:
            report.error(f"{where} has no 'weight'")
            weights_ok = False
        elif not isinstance(weight, (int, float)):
            report.error(f"{where} weight {weight!r} is not a number")
            weights_ok = False
        else:
            total += float(weight)

        scale = crit.get("scale")
        if not isinstance(scale, dict) or "min" not in scale or "max" not in scale:
            report.error(f"{where} has no 'scale' with 'min' and 'max'")
            continue

        smin, smax = scale.get("min"), scale.get("max")
        if not isinstance(smin, int) or not isinstance(smax, int):
            report.error(f"{where} scale min/max must be integers")
            continue
        if smin >= smax:
            report.error(f"{where} scale min {smin} is not below max {smax}")
            continue

        anchors = crit.get("anchors")
        if not isinstance(anchors, dict) or not anchors:
            report.error(
                f"{where} has no 'anchors' — a scale with no level descriptions "
                "cannot be applied consistently"
            )
            continue

        have = {int(k) for k in anchors if str(k).lstrip("-").isdigit()}
        missing = [lvl for lvl in range(smin, smax + 1) if lvl not in have]
        if missing:
            report.error(
                f"{where} scale {smin}-{smax} has no anchor for level(s) "
                f"{missing} — this is the incomplete-scale gap: it reads as "
                "complete and is unexecutable"
            )

        extra = sorted(lvl for lvl in have if not smin <= lvl <= smax)
        if extra:
            report.error(f"{where} has anchors outside the scale: {extra}")

        prov = crit.get("provenance")
        if prov is not None and prov not in DECISION_PROVENANCE:
            report.error(
                f"{where} provenance {prov!r} must be one of "
                f"{', '.join(DECISION_PROVENANCE)}"
            )

    if weights_ok and entries:
        if abs(total - 1.0) > WEIGHT_TOLERANCE:
            report.error(
                f"[criteria] weights sum to {total:.4f}, not 1.0 — state the "
                "user's own numbers and raise the discrepancy as an open "
                "question rather than rounding it away"
            )

    return entries


def check_verdicts(data, criteria: list, report: Report) -> None:
    if data is None:
        if criteria:
            report.error(
                "[verdicts] missing while [criteria] is present — a score with "
                "no mapping to a verdict is an unresolvable gap"
            )
        return

    if not isinstance(data, dict):
        report.error("[verdicts] is not a mapping")
        return

    values = as_list(data.get("values"))
    if not values:
        report.error("[verdicts] has no 'values' — the verdict vocabulary")

    bands = [b for b in as_list(data.get("bands")) if isinstance(b, dict)]
    banded = set()
    for i, band in enumerate(bands):
        where = f"[verdicts.bands][{i}]"
        verdict = band.get("verdict")
        if not verdict:
            report.error(f"{where} has no 'verdict'")
            continue
        banded.add(verdict)
        if verdict not in values:
            report.error(
                f"{where} verdict {verdict!r} is not in the declared values list"
            )
        if band.get("min_score") is None and not band.get("rule"):
            report.error(
                f"{where} verdict {verdict!r} has neither a 'min_score' nor a "
                "'rule' — it is unreachable"
            )

    unreached = [v for v in values if v not in banded]
    if unreached and bands:
        report.error(
            f"[verdicts] no band or rule reaches {unreached} — every declared "
            "verdict must be reachable"
        )

    if not data.get("precedence") and len(bands) > 1:
        report.error(
            "[verdicts] has no 'precedence' — with gates and score bands both "
            "in play, which wins must be stated, not inferred"
        )


def check_judgments(data, fm: dict, report: Report) -> None:
    entries = [j for j in as_list(data) if isinstance(j, dict)]
    if not entries:
        report.error("[judgments] section present but has no entries")
        return

    if not fm.get("rubric_version"):
        report.error(
            "[frontmatter] judgments are present but 'rubric_version' is not "
            "set — every judgement row records the version it was judged under"
        )

    for i, j in enumerate(entries):
        where = f"[judgments][{i}]"
        model = j.get("model")
        if model:
            where = f"[judgments:{model}]"
        else:
            report.error(f"{where} has no 'model'")

        produced_by = j.get("produced_by")
        if produced_by not in PRODUCED_BY:
            report.error(
                f"{where} produced_by {produced_by!r} must be one of "
                f"{', '.join(PRODUCED_BY)}"
            )

        if produced_by == "agent" and not j.get("generator_model"):
            report.error(
                f"{where} is agent-produced but names no 'generator_model' — "
                "that identity lands in judged_by, and nothing else in the "
                "closure records which model produced the scores"
            )

        if not j.get("rubric_version"):
            report.error(f"{where} has no 'rubric_version'")

        reruns = j.get("reruns")
        if reruns is not None and reruns not in RERUNS:
            report.error(
                f"{where} reruns {reruns!r} must be one of {', '.join(RERUNS)}"
            )

        if j.get("evidence_required") is False:
            report.error(
                f"{where} sets evidence_required: false — an agent judgement "
                "without a citation into the source is unreviewable"
            )


def check_schedule(data, models: list, report: Report) -> None:
    if not isinstance(data, dict):
        report.error("[schedule] is not a mapping")
        return

    trigger = data.get("trigger")
    if trigger not in ("manual", "cron", "on_new_data"):
        report.error(
            f"[schedule] trigger {trigger!r} must be manual, cron or on_new_data"
        )
    if trigger == "cron" and not data.get("cron"):
        report.error("[schedule] trigger is cron but no 'cron' expression is set")

    if data.get("incremental") is True:
        if not data.get("cursor_field"):
            report.error(
                "[schedule] incremental: true with no 'cursor_field' — an "
                "append with no cursor is the duplicate-rows bug"
            )
        for model in models:
            name = str(model.get("name", ""))
            grain = str(model.get("grain", ""))
            if model.get("kind") == "view":
                continue
            if REGRAIN_HINT_RE.search(name) or REGRAIN_HINT_RE.search(grain):
                report.warn(
                    f"[schedule] incremental: true, but model {name!r} reads as "
                    "an aggregate or regrain — incrementality gates on EVERY "
                    "promised model being append-safe"
                )


def check_outputs(data, models: list, report: Report) -> None:
    known = {m.get("name") for m in models}
    for i, out in enumerate(as_list(data)):
        where = f"[outputs][{i}]"
        if not isinstance(out, dict):
            report.error(f"{where} is not a mapping")
            continue
        name = out.get("name")
        if not name:
            report.error(f"{where} has no 'name'")
        elif name not in known:
            report.error(
                f"{where} names {name!r}, which is not a declared model"
            )
        kind = out.get("kind")
        if kind is not None and kind not in ("semantic_port", "static_artifact"):
            report.error(
                f"{where} kind {kind!r} must be semantic_port or static_artifact"
            )


def check_decisions(data, report: Report) -> list[dict]:
    entries = [d for d in as_list(data) if isinstance(d, dict)]
    ids = []

    for i, dec in enumerate(entries):
        where = f"[decisions][{i}]"
        did = dec.get("decision_id")
        if not did:
            report.error(f"{where} has no 'decision_id'")
        else:
            ids.append(did)
            where = f"[decisions:{did}]"

        status = dec.get("status")
        if status not in DECISION_STATUS:
            report.error(
                f"{where} status {status!r} must be one of "
                f"{', '.join(DECISION_STATUS)}"
            )

        prov = dec.get("provenance")
        if prov not in DECISION_PROVENANCE:
            report.error(
                f"{where} provenance {prov!r} must be one of "
                f"{', '.join(DECISION_PROVENANCE)} — status and provenance are "
                "orthogonal and both are required on every row"
            )

        if not dec.get("ruling"):
            report.error(f"{where} has no 'ruling'")

        if status == "blocked" and dec.get("applies_to"):
            report.error(
                f"{where} is blocked but sets 'applies_to' — a blocked ruling "
                "materializes nothing"
            )
        if status != "blocked" and not dec.get("applies_to"):
            report.error(
                f"{where} has no 'applies_to' — name the models and columns it "
                "materializes in"
            )

    dupes = {d for d in ids if ids.count(d) > 1}
    if dupes:
        report.error(f"[decisions] duplicate decision_id: {sorted(dupes)}")

    return entries


def check_ruling_coverage(
    sections: dict, population, decisions: list, report: Report
) -> None:
    """Every ruling-bearing section needs a ledger row. That is the whole point
    of the ledger: a ruling filed in prose is invisible to the consumer."""
    if not decisions:
        has_ruling = any(k in sections for k in ("criteria", "verdicts", "gates"))
        sampled = isinstance(population, dict) and population.get("sample_rule")
        if has_ruling or sampled:
            report.error(
                "[decisions] missing while the spec encodes rulings (criteria, "
                "verdicts, gates or a sample rule) — every ruling lands as an "
                "nxd_decisions row, never as prose alone"
            )
        return

    blob = " ".join(
        f"{d.get('decision_id', '')} {d.get('ruling', '')} {d.get('applies_to', '')}"
        for d in decisions
    ).lower()

    for section, keyword in (
        ("criteria", "criteri"),
        ("verdicts", "verdict"),
        ("gates", "gate"),
    ):
        if section in sections and keyword not in blob:
            report.warn(
                f"[decisions] no row mentions the '{section}' rulings — confirm "
                "each is recorded, since the ledger is what a later session queries"
            )

    if isinstance(population, dict) and population.get("sample_rule"):
        if "sampl" not in blob and "population" not in blob:
            report.error(
                "[decisions] the population is sampled but no ledger row records "
                "the selection rule — which rows entered the closure is a "
                "judgement the user can disagree with"
            )


def check_open_questions(data, decisions: list, report: Report) -> None:
    dec_ids = {d.get("decision_id") for d in decisions}
    for i, q in enumerate(as_list(data)):
        where = f"[open_questions][{i}]"
        if not isinstance(q, dict):
            report.error(f"{where} is not a mapping")
            continue
        qid = q.get("id")
        if qid:
            where = f"[open_questions:{qid}]"
        if not q.get("question"):
            report.error(f"{where} has no 'question'")

        disposition = q.get("disposition")
        if disposition is not None and disposition not in DISPOSITIONS:
            report.error(
                f"{where} disposition {disposition!r} must be one of "
                f"{', '.join(DISPOSITIONS)}"
            )
        if disposition == "answered" and qid not in dec_ids:
            report.warn(
                f"{where} is answered but no decision row carries that id — an "
                "answered question should leave a ruling behind"
            )


def check_question_model_coverage(
    sections: dict, questions, models: list, report: Report
) -> None:
    """Warn-only: a question no model answers, a model no question motivates."""
    answered: set[str] = set()
    for model in models:
        answered.update(str(a) for a in as_list(model.get("answers")))

    unmotivated = [
        m.get("name")
        for m in models
        if m.get("kind") == "derived" and not as_list(m.get("answers"))
    ]
    if unmotivated:
        report.warn(
            f"[models] derived model(s) {unmotivated} name no question in "
            "'answers' — a derived model no question motivates should not be built"
        )

    q_list = as_list(questions)
    if q_list and answered:
        # Only meaningful when the spec uses q-ids; free-text questions can't be
        # matched mechanically and are the read-back's job.
        ids = {f"q{i + 1}" for i in range(len(q_list))}
        orphans = sorted(ids - answered)
        if orphans and answered & ids:
            report.warn(
                f"[questions] {orphans} are answered by no model — either a "
                "model is missing or the question is out of scope"
            )


def check_approval_consistency(fm: dict, criteria: list, report: Report) -> None:
    if fm.get("status") != "approved":
        return
    authored = [
        c.get("id") or c.get("name")
        for c in criteria
        if c.get("provenance") == "agent_authored"
    ]
    if authored:
        report.warn(
            f"[criteria] {authored} are agent_authored at status: approved — "
            "legitimate, but the read-back must have named them as yours; "
            "approval moves status, never provenance"
        )


def validate(path: Path) -> Report:
    report = Report()
    text = path.read_text(encoding="utf-8")

    try:
        fm, body = split_frontmatter(text)
    except ValueError as exc:
        report.error(str(exc))
        return report

    check_frontmatter(fm, report)

    raw_sections = split_sections(body)
    check_sections_present(raw_sections, report)
    check_credential_leak(raw_sections, report)

    parsed = {
        name: load_yaml_section(name, raw, report)
        for name, raw in raw_sections.items()
    }

    if "sources" in parsed:
        check_sources(parsed["sources"], report)

    population = parsed.get("population")
    if "population" in parsed:
        check_population(population, report)

    models = check_models(parsed.get("models"), report) if "models" in parsed else []

    if "gates" in parsed:
        check_gates(parsed["gates"], report)

    criteria = check_criteria(parsed["criteria"], report) if "criteria" in parsed else []

    if "verdicts" in parsed or criteria:
        check_verdicts(parsed.get("verdicts"), criteria, report)

    if "judgments" in parsed:
        check_judgments(parsed["judgments"], fm, report)

    if "schedule" in parsed:
        check_schedule(parsed["schedule"], models, report)

    if "outputs" in parsed:
        check_outputs(parsed["outputs"], models, report)

    decisions = (
        check_decisions(parsed["decisions"], report) if "decisions" in parsed else []
    )
    check_ruling_coverage(raw_sections, population, decisions, report)

    if "open_questions" in parsed:
        check_open_questions(parsed["open_questions"], decisions, report)

    check_question_model_coverage(
        raw_sections, parsed.get("questions"), models, report
    )
    check_approval_consistency(fm, criteria, report)

    if fm.get("status") == "approved" and report.errors:
        report.error(
            "[frontmatter] status is 'approved' while the spec has errors — an "
            "approved spec must be compilable"
        )

    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a dp-spec.md intermediate representation."
    )
    parser.add_argument("spec", type=Path, help="path to dp-spec.md")
    parser.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON"
    )
    args = parser.parse_args()

    if not args.spec.is_file():
        print(f"no such file: {args.spec}", file=sys.stderr)
        return 2

    report = validate(args.spec)

    if args.json:
        print(
            json.dumps(
                {
                    "spec": str(args.spec),
                    "ok": report.ok,
                    "errors": report.errors,
                    "warnings": report.warnings,
                },
                indent=2,
            )
        )
        return 0 if report.ok else 1

    for warning in report.warnings:
        print(f"WARN  {warning}")
    for error in report.errors:
        print(f"ERROR {error}")

    if report.ok:
        suffix = f" ({len(report.warnings)} warning(s))" if report.warnings else ""
        print(f"\ndp-spec OK — compilable{suffix}: {args.spec}")
        print("A validator pass is NOT approval. Show the spec and wait for the user.")
        return 0

    print(f"\ndp-spec FAILED — {len(report.errors)} error(s): {args.spec}")
    print("Fix them, or carry the gap as an open_questions entry, before the read-back.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
