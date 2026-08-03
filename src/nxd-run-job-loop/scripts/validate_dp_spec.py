#!/usr/bin/env python3
"""Validate a dp-spec.md — the IR between user intent and a generated closure.

Deterministic only. This finds gaps a script can find with certainty: an
incomplete scale, weights that do not sum, a verdict with no mapping, a gate
with no UNKNOWN rule, a ruling with no ledger row. It does NOT judge whether a
rubric is good or whether the model plan answers the questions — that stays the
policy read-back's job.

Every finding is FIELD-ADDRESSED: it carries a stable `code` from
`dp_diagnostics.CODES` and a `path` naming the entry it is about
(`spec:criteria[C1].anchors`). The code is what lets a harness render the right
control for the error class; the path is what lets it highlight the right field.
Both are stable — an array index is never used for an entry that has an identity,
because indices move when a list is edited and a moving path highlights the
wrong field.

The vocabularies live in `scripts/dp_diagnostics.py` and are imported here. One
definition, two consumers, no drift: what this file enforces is exactly what
`dp_diagnostics.py schema --json` tells a harness to render.

Usage:
    python3 "$JOB_HELPER_DIR/scripts/validate_dp_spec.py" path/to/dp-spec.md
    python3 "$JOB_HELPER_DIR/scripts/validate_dp_spec.py" path/to/dp-spec.md --json

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

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

try:
    import yaml
except ImportError:  # pragma: no cover - environment guard
    yaml = None

import dp_diagnostics  # noqa: E402 - after adding the local scripts directory
from dp_diagnostics import (  # noqa: E402 - after the optional-PyYAML guard, deliberately
    CONTRACT_AUTHORITY,
    CONTRACT_PHASE,
    CREDENTIAL_PLACEHOLDERS,
    CREDENTIAL_VALUE_RE,
    DECISION_PROVENANCE,
    DECISION_STATUS,
    DISPOSITIONS,
    KNOWN_SECTIONS,
    MODEL_KINDS,
    NAME_RE,
    OUTPUT_KINDS,
    PRODUCED_BY,
    REQUIRED_ENTRY_FIELDS,
    REQUIRED_FRONTMATTER,
    REQUIRED_SECTIONS,
    RERUNS,
    SCHEDULE_TRIGGERS,
    SOURCE_TYPES,
    SPEC_VERSION,
    STATUS_VALUES,
    DependencyError,
    Report,
    SpecReadError,
    entry_identity,
    spec_hash,
    spec_path,
    split_frontmatter,
    split_sections,
)

WEIGHT_TOLERANCE = 0.001

# Model kinds/names whose rows are an aggregate or a regrain — never append-safe,
# so `incremental: true` over them is the silent-truncation bug.
REGRAIN_HINT_RE = re.compile(
    r"\b(monthly|daily|weekly|rollup|roll-up|aggregate|aggregated|summary|"
    r"per[_ -]month|regrain|collapsed?)\b",
    re.IGNORECASE,
)

# A contract name selects a generated verifier file (contracts/expectations/
# <name>.py), so it is a filename, not a model identifier: lowercase-hyphenated
# rather than the snake_case NAME_RE the model sections use.
CONTRACT_NAME_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")

# A rule that still carries a placeholder is unexecutable. This is the
# RULE-PREFILL trap in contract form: the agent must ask for the number rather
# than invent one, so an unfilled threshold is an error and never a default.
UNBOUND_THRESHOLD_RE = re.compile(
    r"(<[A-Za-z_][A-Za-z0-9_ -]*>|\bTBD\b|\bTODO\b|\bXXX\b|\{\{[^}]*\}\}|"
    r"\b(some|any|appropriate|reasonable|suitable) (threshold|value|"
    r"number|limit|minimum|maximum)\b)",
    re.IGNORECASE,
)
# Deliberately NOT in that set: `NA` / `N/A`. They are real sentinel VALUES a
# rule legitimately names — `gates` documents them as non-capture sentinels the
# agent must route to `unknown` rather than fill — so matching them rejected a
# correct rule for saying the thing the spec asks it to say.


def new_report(spec: Path | None = None) -> Report:
    return Report("validate_dp_spec", target=str(spec) if spec else None)


# `split_frontmatter` and `split_sections` are IMPORTED from `dp_diagnostics`,
# never redefined here. They used to be duplicated with a "must stay
# byte-for-byte equivalent" docstring, and they drifted anyway: the copy lost
# the `yaml.YAMLError` guard, so `name: [unclosed` produced a raw traceback
# instead of a `spec.frontmatter.unparseable` diagnostic — no `--json` output,
# and the exit-code contract broken. One definition cannot drift, and the hash
# now describes exactly the document this validator judged, by construction.


def load_yaml_section(name: str, raw: str, report: Report):
    """Parse a section body as YAML. Prose-only sections stay strings."""
    if not raw:
        return None
    try:
        return yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        report.error(
            f"not parseable as YAML: {exc}",
            code="spec.section.unparseable",
            path=spec_path(name),
            evidence={"section": name},
        )
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
            report.error(
                f"missing required key {key!r}",
                code="spec.frontmatter.missing_key",
                path=spec_path("frontmatter", None, key),
                evidence={"expected": list(REQUIRED_FRONTMATTER)},
            )

    version = fm.get("dp_spec_version")
    if version is not None and version != SPEC_VERSION:
        report.error(
            f"dp_spec_version {version!r} is not the supported version {SPEC_VERSION}",
            code="spec.frontmatter.bad_version",
            path=spec_path("frontmatter", None, "dp_spec_version"),
            evidence={"expected": SPEC_VERSION, "found": version},
        )

    name = fm.get("name")
    if isinstance(name, str) and not NAME_RE.match(name):
        report.error(
            f"name {name!r} must be lowercase snake_case — it becomes the data "
            "product name",
            code="spec.frontmatter.bad_name",
            path=spec_path("frontmatter", None, "name"),
            evidence={"found": name},
        )

    status = fm.get("status")
    if status is not None and status not in STATUS_VALUES:
        report.error(
            f"status {status!r} must be one of {', '.join(STATUS_VALUES)}",
            code="spec.frontmatter.bad_status",
            path=spec_path("frontmatter", None, "status"),
            evidence={"allowed": list(STATUS_VALUES), "found": status},
        )


def check_sections_present(sections: dict, report: Report) -> None:
    for name in REQUIRED_SECTIONS:
        if name not in sections:
            report.error(
                f"missing required section '## {name}'",
                code="spec.section.missing",
                path=spec_path(name),
                evidence={"expected": list(REQUIRED_SECTIONS)},
            )
        elif not sections[name]:
            report.error(
                f"section '## {name}' is empty",
                code="spec.section.empty",
                path=spec_path(name),
            )

    for name in sections:
        if name not in KNOWN_SECTIONS:
            report.warn(
                f"unknown section '## {name}' — it will not compile to any closure "
                "artifact; carry it in open_questions if it matters",
                code="spec.section.unknown",
                path=spec_path(name),
                evidence={"allowed": list(KNOWN_SECTIONS)},
            )


def check_sources(data, report: Report) -> None:
    entries = as_list(data)
    if not entries:
        report.error(
            "no source entries",
            code="spec.source.no_entries",
            path=spec_path("sources"),
        )
        return

    labels = []
    for i, src in enumerate(entries):
        where = spec_path("sources", entry_identity(src, i))
        if not isinstance(src, dict):
            report.error(
                "is not a mapping",
                code="spec.source.not_mapping",
                path=where,
            )
            continue

        stype = src.get("type")
        if stype not in SOURCE_TYPES:
            report.error(
                f"type {stype!r} must be one of {', '.join(SOURCE_TYPES)}",
                code="spec.source.bad_type",
                path=f"{where}.type",
                evidence={"allowed": list(SOURCE_TYPES), "found": stype},
            )
        if not src.get("location"):
            report.error(
                "has no 'location'",
                code="spec.source.no_location",
                path=f"{where}.location",
            )
        if not src.get("scope"):
            report.error(
                "has no 'scope' — the population filter must be stated",
                code="spec.source.no_scope",
                path=f"{where}.scope",
            )

        label = src.get("label")
        if label is not None:
            labels.append(label)

        for key in ("credential_keys", "credentials"):
            for value in as_list(src.get(key)):
                if isinstance(value, dict):
                    # Owner is `user`, deliberately. The agent could repair this
                    # structurally, but the shape that triggers it is a mapping
                    # whose VALUE is a live secret in a shareable file. Only the
                    # user can decide whether it must now be rotated, and
                    # silently rewriting the file would erase the evidence that
                    # it leaked.
                    report.error(
                        f"{key} carries a mapping — list KEY NAMES only, never a "
                        "value; credentials land in infra-profile.yaml",
                        code="spec.source.credential_key_mapping",
                        path=f"{where}.{key}",
                    )

    if len(entries) > 1:
        if len(labels) != len(entries):
            report.error(
                "with 2+ sources every source needs a distinct 'label'",
                code="spec.source.label_missing",
                path=spec_path("sources"),
                evidence={"count": len(entries), "found": len(labels)},
            )
        elif len(set(labels)) != len(labels):
            report.error(
                f"duplicate labels: {sorted(labels)}",
                code="spec.source.label_duplicate",
                path=spec_path("sources"),
                evidence={"found": sorted(labels)},
            )


def check_credential_leak(raw_sections: dict, report: Report) -> None:
    for name in ("sources", "schedule", "outputs"):
        raw = raw_sections.get(name, "")
        for match in CREDENTIAL_VALUE_RE.finditer(raw):
            value = match.group(0).split(":", 1)[-1].split("=", 1)[-1].strip()
            if value.lower() in CREDENTIAL_PLACEHOLDERS:
                continue
            if value.startswith("[") or value.startswith("<"):
                continue
            # The message is redacted on the way out — a check that prints the
            # secret it found turns a contained file leak into a transcript leak.
            report.error(
                f"the key {match.group(1)!r} carries what looks like a credential "
                "VALUE — this file is shareable; values belong only in the "
                "generated infra-profile.yaml",
                code="spec.source.credential_value",
                path=spec_path(name),
                evidence={"found": match.group(1)},
            )


def check_population(data, report: Report) -> None:
    if isinstance(data, str):
        report.warn(
            "is prose — a structured 'population'/'sample_rule'/'excludes' "
            "mapping lets the sample rule land as a decision row",
            code="spec.population.prose",
            path=spec_path("population"),
        )
        return
    if not isinstance(data, dict):
        report.error(
            "is not a mapping",
            code="spec.population.not_mapping",
            path=spec_path("population"),
        )
        return
    if not data.get("population"):
        report.error(
            "has no 'population' — state the full row set",
            code="spec.population.missing",
            path=spec_path("population", None, "population"),
        )


def check_models(data, report: Report) -> list[dict]:
    entries = [m for m in as_list(data) if isinstance(m, dict)]
    if not entries:
        report.error(
            "no model entries",
            code="spec.model.no_entries",
            path=spec_path("models"),
        )
        return []

    names = []
    for i, model in enumerate(entries):
        where = spec_path("models", entry_identity(model, i))
        name = model.get("name")
        if not name:
            report.error(
                "has no 'name'",
                code="spec.model.no_name",
                path=f"{where}.name",
            )
        else:
            names.append(name)
            if not NAME_RE.match(str(name)):
                report.error(
                    "name must be lowercase snake_case — the naming invariant is "
                    "byte-exact across models.py, .promise, PHYSICAL_MODELS and "
                    "the physical table",
                    code="spec.model.bad_name",
                    path=f"{where}.name",
                    evidence={"found": name},
                )

        kind = model.get("kind")
        if kind not in MODEL_KINDS:
            report.error(
                f"kind {kind!r} must be one of {', '.join(MODEL_KINDS)}",
                code="spec.model.bad_kind",
                path=f"{where}.kind",
                evidence={"allowed": list(MODEL_KINDS), "found": kind},
            )

        if not model.get("description"):
            report.error(
                "has no 'description' — describe_models is all a later consumer "
                "sees, so an undescribed model is unusable",
                code="spec.model.no_description",
                path=f"{where}.description",
            )

        # A view is query-time only: no grain, no key, no physical table.
        if kind == "view":
            continue

        if not model.get("grain"):
            report.error(
                "has no 'grain' — one sentence naming what one row is",
                code="spec.model.no_grain",
                path=f"{where}.grain",
            )
        if not as_list(model.get("key")):
            report.error(
                "has no 'key' — every promised physical model needs a primary "
                "key, base from a source column, derived from the grain",
                code="spec.model.no_key",
                path=f"{where}.key",
            )

    dupes = {n for n in names if names.count(n) > 1}
    if dupes:
        report.error(
            f"duplicate model names: {sorted(dupes)}",
            code="spec.model.duplicate_name",
            path=spec_path("models"),
            evidence={"found": sorted(dupes)},
        )

    return entries


def check_contracts(section: str, data, models: list[dict], report: Report) -> list[dict]:
    """Validate `## expectations` or `## promises`.

    Both sections carry the same entry shape and differ only in the phase they
    are allowed to run at, so one checker serves both and `section` decides the
    phase. The codes are `spec.contract.*` for the same reason: a duplicate name
    is the same defect whichever section it appears in, and the path already
    says which section the reader is in.
    """
    expected_phase = "pre_transform" if section == "expectations" else "post_transform"
    model_names = {m.get("name") for m in models if isinstance(m, dict)}
    entries: list[dict] = []

    for i, contract in enumerate(as_list(data)):
        where = spec_path(section, entry_identity(contract, i))
        if not isinstance(contract, dict):
            report.error(
                "is not a mapping",
                code="spec.contract.not_mapping",
                path=where,
            )
            continue
        entries.append(contract)

        name = contract.get("name")
        if not name:
            report.error(
                "has no 'name' — the name selects the verifier file, so an "
                "unnamed contract cannot be generated",
                code="spec.contract.no_name",
                path=f"{where}.name",
            )
        else:
            if not CONTRACT_NAME_RE.match(str(name)):
                report.error(
                    f"name {name!r} is not lowercase-hyphenated",
                    code="spec.contract.bad_name",
                    path=f"{where}.name",
                    evidence={"found": name},
                )

        authority = contract.get("authority")
        if not authority:
            report.error(
                "has no 'authority' — a contract must say whether the user "
                "stated it or the agent inferred it, because only the user may "
                "weaken their own guarantee",
                code="spec.contract.no_authority",
                path=f"{where}.authority",
            )
        elif authority not in CONTRACT_AUTHORITY:
            report.error(
                f"authority {authority!r} is outside {list(CONTRACT_AUTHORITY)}",
                code="spec.contract.bad_authority",
                path=f"{where}.authority",
                evidence={"found": authority},
            )
        elif authority == "inferred":
            report.error(
                "is 'inferred' — a constraint read off the data belongs in "
                "models.py and an ordinary .promise(model), not in the spec. "
                "Only a guarantee the user stated travels as a spec contract; "
                "replaying an inference back as the user's own promise is the "
                "confusion these sections exist to prevent",
                code="spec.contract.inferred_in_spec",
                path=f"{where}.authority",
                evidence={"found": authority},
            )

        if not contract.get("guarantee"):
            report.error(
                "has no 'guarantee' — the user's own words for what they are "
                "promising, kept verbatim so a later reader can tell what was "
                "agreed from how it was implemented",
                code="spec.contract.no_guarantee",
                path=f"{where}.guarantee",
            )

        rule = contract.get("rule")
        if not rule:
            report.error(
                "has no 'rule' — the executable form of the guarantee. Without "
                "it the contract is prose and no verifier can be generated",
                code="spec.contract.no_rule",
                path=f"{where}.rule",
            )
        elif UNBOUND_THRESHOLD_RE.search(str(rule)):
            report.error(
                "names a threshold the spec never fixes — a rule with an "
                "unfilled placeholder cannot be verified. Ask for the number "
                "rather than choosing one",
                code="spec.contract.unbound_threshold",
                path=f"{where}.rule",
                evidence={"found": str(rule)[:200]},
            )

        model = contract.get("model")
        if not model:
            report.error(
                "names no 'model' — a contract with no subject cannot be "
                "attached to an input or an output",
                code="spec.contract.no_model",
                path=f"{where}.model",
            )
        elif models and str(model) not in model_names:
            report.error(
                f"names model {model!r}, which no models entry declares",
                code="spec.contract.unknown_model",
                path=f"{where}.model",
                evidence={"found": model, "declared": sorted(n for n in model_names if n)},
            )

        phase = contract.get("phase")
        if phase is None:
            continue
        if phase not in CONTRACT_PHASE:
            report.error(
                f"phase {phase!r} is outside {list(CONTRACT_PHASE)}",
                code="spec.contract.bad_phase",
                path=f"{where}.phase",
                evidence={"found": phase},
            )
        elif phase != expected_phase:
            report.error(
                f"is a {section[:-1]} declaring phase {phase!r}; an expectation "
                f"guards the input before the transform reads it and a promise "
                f"guards the output after it wrote it, so this must be "
                f"{expected_phase!r}",
                code="spec.contract.wrong_phase",
                path=f"{where}.phase",
                evidence={"found": phase, "expected": expected_phase},
            )

    return entries


def check_contract_names_unique(contracts: list[tuple[str, dict]],
                                report: Report) -> None:
    """One namespace across both contract sections.

    Deliberately not folded into `check_contracts`: a name collision between an
    expectation and a promise is invisible to a checker that sees one section at
    a time, and it is the collision that matters most — both sections generate
    into `contracts/`, so two contracts sharing a name race for one filename and
    the second silently overwrites the first.

    Takes (section, entry) pairs so each finding is FIELD-ADDRESSED to where the
    collision actually is. Reporting every duplicate at `spec:expectations`
    pointed a harness at a section a promises-only spec does not even have.
    """
    names = [str(c["name"]) for _, c in contracts if c.get("name")]
    dupes = sorted({n for n in names if names.count(n) > 1})
    for dupe in dupes:
        # One finding per (section, name) PAIR, not per entry: a three-way
        # collision inside one section would otherwise emit three
        # byte-identical diagnostics and count three errors for one problem.
        # (The rendered path goes through entry_identity, which prefers a
        # per-entry `id` when one is present.)
        sections = sorted({sec for sec, entry in contracts
                           if str(entry.get("name") or "") == dupe})
        for section in sections:
            # Identity via entry_identity, like every other contract finding:
            # it resolves the entry's identity the same way check_contracts
            # does (`id` first, then `name`), so a hand-built path is one more
            # place the addressing convention can drift.
            colliding = [e for sec, e in contracts
                         if sec == section and str(e.get("name") or "") == dupe]
            # De-dupe on the RENDERED PATH, not on (section, name). Entries
            # carrying distinct `id`s render distinct paths, so collapsing them
            # would silently drop a real collision site — a UI would highlight
            # one of two colliding entries and leave the reader to find the
            # other. Entries with no `id` all render the same path and DO
            # collapse, which is the byte-identical case the collapse is for.
            seen_paths = {}
            for candidate in colliding:
                seen_paths.setdefault(
                    f"{spec_path(section, entry_identity(candidate, 0))}.name",
                    candidate)
            # A cross-section collision is reported at BOTH locations on
            # purpose: a reader in `expectations` has to see it too, and
            # neither side is the one at fault. Each finding names the OTHER
            # section so the two are not byte-identical-but-for-the-path —
            # that is the shape the de-dup above exists to avoid.
            # ADDITIVE, not exclusive: a name can be duplicated within a
            # section AND collide across sections at once. Reporting only the
            # cross-section half let a repair pass rename one entry, read both
            # findings as addressed, and still ship two copies in the other
            # section — a wasted round trip.
            here = len(colliding)
            others = [s for s in sections if s != section]
            clauses = []
            if here > 1:
                clauses.append(f"appears {here} times in {section}")
            if others:
                clauses.append(f"also appears in {' and '.join(others)}")
            where = f" — it {' and '.join(clauses)}" if clauses else ""
            for site in sorted(seen_paths):
                report.error(
                    f"duplicate contract name {dupe!r}{where}. The name selects "
                    f"the generated verifier file, so two contracts sharing one "
                    f"name overwrite each other",
                    code="spec.contract.duplicate_name",
                    path=site,
                    evidence={"found": [dupe], "sections": sections},
                )


def check_gates(data, report: Report) -> None:
    for i, gate in enumerate(as_list(data)):
        where = spec_path("gates", entry_identity(gate, i))
        if not isinstance(gate, dict):
            report.error(
                "is not a mapping",
                code="spec.gate.not_mapping",
                path=where,
            )
            continue
        if not gate.get("rule"):
            report.error(
                "has no 'rule'",
                code="spec.gate.no_rule",
                path=f"{where}.rule",
            )

        unknown = gate.get("unknown")
        if unknown is None:
            report.error(
                "has no 'unknown' handling — an absent gate input must land "
                "UNKNOWN, and leaving it unstated is the gap the policy read-back "
                "exists to catch",
                code="spec.gate.no_unknown",
                path=f"{where}.unknown",
            )
        elif str(unknown).strip().upper() == "FAIL":
            report.error(
                "maps an absent input to FAIL — absence is never a judgement; it "
                "lands UNKNOWN",
                code="spec.gate.unknown_is_fail",
                path=f"{where}.unknown",
                evidence={"found": unknown},
            )


def check_criteria(data, report: Report) -> list[dict]:
    entries = [c for c in as_list(data) if isinstance(c, dict)]
    if not entries:
        report.error(
            "section present but has no criterion entries",
            code="spec.criteria.no_entries",
            path=spec_path("criteria"),
        )
        return []

    total = 0.0
    weights_ok = True

    for i, crit in enumerate(entries):
        where = spec_path("criteria", entry_identity(crit, i))

        weight = crit.get("weight")
        if weight is None:
            report.error(
                "has no 'weight'",
                code="spec.criteria.no_weight",
                path=f"{where}.weight",
            )
            weights_ok = False
        elif not isinstance(weight, (int, float)):
            report.error(
                f"weight {weight!r} is not a number",
                code="spec.criteria.bad_weight",
                path=f"{where}.weight",
                evidence={"found": weight},
            )
            weights_ok = False
        else:
            total += float(weight)

        scale = crit.get("scale")
        if not isinstance(scale, dict) or "min" not in scale or "max" not in scale:
            report.error(
                "has no 'scale' with 'min' and 'max'",
                code="spec.criteria.no_scale",
                path=f"{where}.scale",
            )
            continue

        smin, smax = scale.get("min"), scale.get("max")
        if not isinstance(smin, int) or not isinstance(smax, int):
            report.error(
                "scale min/max must be integers",
                code="spec.criteria.bad_scale",
                path=f"{where}.scale",
                evidence={"reason": "non_integer", "found": [smin, smax]},
            )
            continue
        if smin >= smax:
            report.error(
                f"scale min {smin} is not below max {smax}",
                code="spec.criteria.bad_scale",
                path=f"{where}.scale",
                evidence={"reason": "min_not_below_max", "found": [smin, smax]},
            )
            continue

        anchors = crit.get("anchors")
        if not isinstance(anchors, dict) or not anchors:
            report.error(
                "has no 'anchors' — a scale with no level descriptions cannot be "
                "applied consistently",
                code="spec.criteria.no_anchors",
                path=f"{where}.anchors",
            )
            continue

        have = {int(k) for k in anchors if str(k).lstrip("-").isdigit()}
        missing = [lvl for lvl in range(smin, smax + 1) if lvl not in have]
        if missing:
            report.error(
                f"scale {smin}-{smax} has no anchor for level(s) {missing} — this "
                "is the incomplete-scale gap: it reads as complete and is "
                "unexecutable",
                code="spec.criteria.incomplete_scale",
                path=f"{where}.anchors",
                evidence={"expected": list(range(smin, smax + 1)), "found": sorted(have)},
            )

        extra = sorted(lvl for lvl in have if not smin <= lvl <= smax)
        if extra:
            report.error(
                f"has anchors outside the scale: {extra}",
                code="spec.criteria.anchor_out_of_range",
                path=f"{where}.anchors",
                evidence={"expected": list(range(smin, smax + 1)), "found": extra},
            )

        prov = crit.get("provenance")
        if prov is not None and prov not in DECISION_PROVENANCE:
            report.error(
                f"provenance {prov!r} must be one of {', '.join(DECISION_PROVENANCE)}",
                code="spec.criteria.bad_provenance",
                path=f"{where}.provenance",
                evidence={"allowed": list(DECISION_PROVENANCE), "found": prov},
            )

    if weights_ok and entries:
        if abs(total - 1.0) > WEIGHT_TOLERANCE:
            report.error(
                f"weights sum to {total:.4f}, not 1.0 — state the user's own "
                "numbers and raise the discrepancy as an open question rather "
                "than rounding it away",
                code="spec.criteria.weights_unbalanced",
                path=spec_path("criteria"),
                evidence={"expected": 1.0, "actual": round(total, 6)},
            )

    return entries


def check_verdicts(data, criteria: list, report: Report) -> None:
    if data is None:
        if criteria:
            report.error(
                "missing while [criteria] is present — a score with no mapping to "
                "a verdict is an unresolvable gap",
                code="spec.verdict.missing",
                path=spec_path("verdicts"),
            )
        return

    if not isinstance(data, dict):
        report.error(
            "is not a mapping",
            code="spec.verdict.not_mapping",
            path=spec_path("verdicts"),
        )
        return

    values = as_list(data.get("values"))
    if not values:
        report.error(
            "has no 'values' — the verdict vocabulary",
            code="spec.verdict.no_values",
            path=spec_path("verdicts", None, "values"),
        )

    bands = [b for b in as_list(data.get("bands")) if isinstance(b, dict)]
    banded = set()
    for i, band in enumerate(bands):
        where = f"{spec_path('verdicts', None, 'bands')}[{entry_identity(band, i)}]"
        verdict = band.get("verdict")
        if not verdict:
            report.error(
                "has no 'verdict'",
                code="spec.verdict.band_no_verdict",
                path=f"{where}.verdict",
            )
            continue
        banded.add(verdict)
        if verdict not in values:
            report.error(
                f"verdict {verdict!r} is not in the declared values list",
                code="spec.verdict.band_unknown_verdict",
                path=f"{where}.verdict",
                evidence={"allowed": list(values), "found": verdict},
            )
        if band.get("min_score") is None and not band.get("rule"):
            report.error(
                f"verdict {verdict!r} has neither a 'min_score' nor a 'rule' — it "
                "is unreachable",
                code="spec.verdict.band_unreachable",
                path=where,
            )

    unreached = [v for v in values if v not in banded]
    if unreached:
        report.error(
            f"no band or rule reaches {unreached} — every declared verdict must "
            "be reachable",
            code="spec.verdict.value_unreached",
            path=spec_path("verdicts", None, "values"),
            evidence={"found": unreached},
        )

    if not data.get("precedence") and len(bands) > 1:
        report.error(
            "has no 'precedence' — with gates and score bands both in play, which "
            "wins must be stated, not inferred",
            code="spec.verdict.no_precedence",
            path=spec_path("verdicts", None, "precedence"),
        )


def check_judgments(data, fm: dict, report: Report) -> None:
    entries = [j for j in as_list(data) if isinstance(j, dict)]
    if not entries:
        report.error(
            "section present but has no entries",
            code="spec.judgment.no_entries",
            path=spec_path("judgments"),
        )
        return

    if not fm.get("rubric_version"):
        report.error(
            "judgments are present but 'rubric_version' is not set — every "
            "judgement row records the version it was judged under",
            code="spec.frontmatter.rubric_version_missing",
            path=spec_path("frontmatter", None, "rubric_version"),
        )

    for i, j in enumerate(entries):
        where = spec_path("judgments", entry_identity(j, i))
        if not j.get("model"):
            report.error(
                "has no 'model'",
                code="spec.judgment.no_model",
                path=f"{where}.model",
            )

        produced_by = j.get("produced_by")
        if produced_by not in PRODUCED_BY:
            report.error(
                f"produced_by {produced_by!r} must be one of {', '.join(PRODUCED_BY)}",
                code="spec.judgment.bad_produced_by",
                path=f"{where}.produced_by",
                evidence={"allowed": list(PRODUCED_BY), "found": produced_by},
            )

        if produced_by == "agent" and not j.get("generator_model"):
            report.error(
                "is agent-produced but names no 'generator_model' — that identity "
                "lands in judged_by, and nothing else in the closure records "
                "which model produced the scores",
                code="spec.judgment.no_generator_model",
                path=f"{where}.generator_model",
            )

        if not j.get("rubric_version"):
            report.error(
                "has no 'rubric_version'",
                code="spec.judgment.no_rubric_version",
                path=f"{where}.rubric_version",
            )

        reruns = j.get("reruns")
        if reruns is not None and reruns not in RERUNS:
            report.error(
                f"reruns {reruns!r} must be one of {', '.join(RERUNS)}",
                code="spec.judgment.bad_reruns",
                path=f"{where}.reruns",
                evidence={"allowed": list(RERUNS), "found": reruns},
            )

        if j.get("evidence_required") is False:
            report.error(
                "sets evidence_required: false — an agent judgement without a "
                "citation into the source is unreviewable",
                code="spec.judgment.evidence_disabled",
                path=f"{where}.evidence_required",
            )


def check_schedule(data, models: list, report: Report) -> None:
    if not isinstance(data, dict):
        report.error(
            "is not a mapping",
            code="spec.schedule.not_mapping",
            path=spec_path("schedule"),
        )
        return

    trigger = data.get("trigger")
    if trigger not in SCHEDULE_TRIGGERS:
        report.error(
            f"trigger {trigger!r} must be {', '.join(SCHEDULE_TRIGGERS)}",
            code="spec.schedule.bad_trigger",
            path=spec_path("schedule", None, "trigger"),
            evidence={"allowed": list(SCHEDULE_TRIGGERS), "found": trigger},
        )
    if trigger == "cron" and not data.get("cron"):
        report.error(
            "trigger is cron but no 'cron' expression is set",
            code="spec.schedule.no_cron",
            path=spec_path("schedule", None, "cron"),
        )

    if data.get("incremental") is True:
        if not data.get("cursor_field"):
            report.error(
                "incremental: true with no 'cursor_field' — an append with no "
                "cursor is the duplicate-rows bug",
                code="spec.schedule.no_cursor_field",
                path=spec_path("schedule", None, "cursor_field"),
            )
        for i, model in enumerate(models):
            name = str(model.get("name", ""))
            grain = str(model.get("grain", ""))
            if model.get("kind") == "view":
                continue
            if REGRAIN_HINT_RE.search(name) or REGRAIN_HINT_RE.search(grain):
                report.warn(
                    f"incremental: true, but model {name!r} reads as an aggregate "
                    "or regrain — incrementality gates on EVERY promised model "
                    "being append-safe",
                    code="spec.schedule.regrain_not_append_safe",
                    path=spec_path("models", entry_identity(model, i)),
                    evidence={"model": name},
                )


def check_outputs(data, models: list, report: Report) -> None:
    known = {m.get("name") for m in models}
    for i, out in enumerate(as_list(data)):
        where = spec_path("outputs", entry_identity(out, i))
        if not isinstance(out, dict):
            report.error(
                "is not a mapping",
                code="spec.output.not_mapping",
                path=where,
            )
            continue
        name = out.get("name")
        if not name:
            report.error(
                "has no 'name'",
                code="spec.output.no_name",
                path=f"{where}.name",
            )
        elif name not in known:
            report.error(
                f"names {name!r}, which is not a declared model",
                code="spec.output.unknown_model",
                path=f"{where}.name",
                evidence={"allowed": sorted(str(k) for k in known), "found": name},
            )
        kind = out.get("kind")
        if kind is not None and kind not in OUTPUT_KINDS:
            report.error(
                f"kind {kind!r} must be {' or '.join(OUTPUT_KINDS)}",
                code="spec.output.bad_kind",
                path=f"{where}.kind",
                evidence={"allowed": list(OUTPUT_KINDS), "found": kind},
            )


def check_decisions(data, report: Report) -> list[dict]:
    entries = [d for d in as_list(data) if isinstance(d, dict)]
    ids = []

    for i, dec in enumerate(entries):
        where = spec_path("decisions", entry_identity(dec, i))
        did = dec.get("decision_id")
        if not did:
            report.error(
                "has no 'decision_id'",
                code="spec.decision.no_id",
                path=f"{where}.decision_id",
            )
        else:
            ids.append(did)

        status = dec.get("status")
        if status not in DECISION_STATUS:
            report.error(
                f"status {status!r} must be one of {', '.join(DECISION_STATUS)}",
                code="spec.decision.bad_status",
                path=f"{where}.status",
                evidence={"allowed": list(DECISION_STATUS), "found": status},
            )

        prov = dec.get("provenance")
        if prov not in DECISION_PROVENANCE:
            report.error(
                f"provenance {prov!r} must be one of "
                f"{', '.join(DECISION_PROVENANCE)} — status and provenance are "
                "orthogonal and both are required on every row",
                code="spec.decision.bad_provenance",
                path=f"{where}.provenance",
                evidence={"allowed": list(DECISION_PROVENANCE), "found": prov},
            )

        if not dec.get("ruling"):
            report.error(
                "has no 'ruling'",
                code="spec.decision.no_ruling",
                path=f"{where}.ruling",
            )

        if status == "blocked" and dec.get("applies_to"):
            report.error(
                "is blocked but sets 'applies_to' — a blocked ruling materializes "
                "nothing",
                code="spec.decision.blocked_with_applies_to",
                path=f"{where}.applies_to",
            )
        if status != "blocked" and not dec.get("applies_to"):
            report.error(
                "has no 'applies_to' — name the models and columns it "
                "materializes in",
                code="spec.decision.no_applies_to",
                path=f"{where}.applies_to",
            )

    dupes = {d for d in ids if ids.count(d) > 1}
    if dupes:
        report.error(
            f"duplicate decision_id: {sorted(dupes)}",
            code="spec.decision.duplicate_id",
            path=spec_path("decisions"),
            evidence={"found": sorted(dupes)},
        )

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
                "missing while the spec encodes rulings (criteria, verdicts, "
                "gates or a sample rule) — every ruling lands as an nxd_decisions "
                "row, never as prose alone",
                code="spec.decision.missing_for_ruling",
                path=spec_path("decisions"),
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
            report.error(
                f"no row mentions the '{section}' rulings — record each before "
                "compiling, since the ledger is what a later session queries",
                code="spec.decision.ruling_uncovered",
                path=spec_path("decisions"),
                evidence={"section": section},
            )

    if isinstance(population, dict) and population.get("sample_rule"):
        if "sampl" not in blob and "population" not in blob:
            report.error(
                "the population is sampled but no ledger row records the "
                "selection rule — which rows entered the closure is a judgement "
                "the user can disagree with",
                code="spec.decision.sample_rule_unrecorded",
                path=spec_path("decisions"),
            )


def check_open_questions(data, decisions: list, report: Report) -> None:
    dec_ids = {d.get("decision_id") for d in decisions}
    for i, q in enumerate(as_list(data)):
        where = spec_path("open_questions", entry_identity(q, i))
        if not isinstance(q, dict):
            report.error(
                "is not a mapping",
                code="spec.open_question.not_mapping",
                path=where,
            )
            continue
        qid = q.get("id")
        if not q.get("question"):
            report.error(
                "has no 'question'",
                code="spec.open_question.no_question",
                path=f"{where}.question",
            )

        disposition = q.get("disposition")
        if disposition is not None and disposition not in DISPOSITIONS:
            report.error(
                f"disposition {disposition!r} must be one of {', '.join(DISPOSITIONS)}",
                code="spec.open_question.bad_disposition",
                path=f"{where}.disposition",
                evidence={"allowed": list(DISPOSITIONS), "found": disposition},
            )
        if disposition == "answered" and qid not in dec_ids:
            report.warn(
                "is answered but no decision row carries that id — an answered "
                "question should leave a ruling behind",
                code="spec.open_question.answered_without_decision",
                path=f"{where}.disposition",
                evidence={"found": qid},
            )


def check_question_model_coverage(
    sections: dict, questions, models: list, report: Report
) -> None:
    """Warn-only: a question no model answers, a model no question motivates."""
    answered: set[str] = set()
    for model in models:
        answered.update(str(a) for a in as_list(model.get("answers")))

    for i, model in enumerate(models):
        if model.get("kind") == "derived" and not as_list(model.get("answers")):
            report.warn(
                f"derived model {model.get('name')!r} names no question in "
                "'answers' — a derived model no question motivates should not be "
                "built",
                code="spec.model.unmotivated",
                path=f"{spec_path('models', entry_identity(model, i))}.answers",
            )

    q_list = as_list(questions)
    if q_list and answered:
        # Only meaningful when the spec uses q-ids; free-text questions can't be
        # matched mechanically and are the read-back's job.
        ids = {f"q{i + 1}" for i in range(len(q_list))}
        orphans = sorted(ids - answered)
        if orphans and answered & ids:
            report.warn(
                f"{orphans} are answered by no model — either a model is missing "
                "or the question is out of scope",
                code="spec.question.unanswered",
                path=spec_path("questions"),
                evidence={"found": orphans},
            )


def check_prefill(parsed: dict, report: Report) -> None:
    """RULE-PREFILL, made mechanical: a blank is illegal.

    The agent always pre-fills from the conversation or the user's own document;
    a rendered form is review-and-correct, never data entry. So a field the agent
    has no basis for does not appear as an empty control — it becomes an
    open_questions entry. A required field that is PRESENT AND BLANK is that
    failure caught early.
    """
    for section, fields in REQUIRED_ENTRY_FIELDS.items():
        entries = as_list(parsed.get(section))
        for i, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            where = spec_path(section, entry_identity(entry, i))
            for name in fields:
                if name not in entry:
                    continue
                if entry.get("kind") == "view" and name in ("grain", "key"):
                    continue
                value = entry[name]
                if value in (None, "", [], {}):
                    report.warn(
                        f"'{name}' is present but blank — pre-fill it from what "
                        "the user already told you, or carry it as an "
                        "open_questions entry; a blank is never the entry point",
                        code="spec.prefill.empty_required_field",
                        path=f"{where}.{name}",
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
            f"{authored} are agent_authored at status: approved — legitimate, but "
            "the read-back must have named them as yours; approval moves status, "
            "never provenance",
            code="spec.approval.agent_authored_at_approved",
            path=spec_path("criteria"),
            evidence={"found": authored},
        )


def validate(path: Path) -> Report:
    if yaml is None or dp_diagnostics.yaml is None:
        raise DependencyError(
            "environment.dependency_missing: dp-spec validation needs PyYAML: "
            "pip install pyyaml"
        )

    report = new_report(path)
    text = path.read_text(encoding="utf-8")

    try:
        report.spec_hash = spec_hash(text.encode("utf-8"))
    except Exception:
        # A spec that cannot be canonicalized has no hash yet. The frontmatter
        # diagnostics below say why; the hash is not the place to report it.
        report.spec_hash = None

    try:
        fm, body = split_frontmatter(text)
    except DependencyError:
        raise
    except SpecReadError as exc:
        # Fatal to further parsing: return the report immediately. `reason` is
        # the closed discriminator enum, so nobody invents a second code for a
        # variant of the same failure.
        report.error(
            str(exc),
            code="spec.frontmatter.unparseable",
            path=spec_path("frontmatter"),
            evidence={"reason": exc.reason},
        )
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

    contracts: list[tuple[str, dict]] = []
    for contract_section in ("expectations", "promises"):
        if contract_section in parsed:
            contracts += [
                (contract_section, entry)
                for entry in check_contracts(
                    contract_section, parsed[contract_section], models, report
                )
            ]
    check_contract_names_unique(contracts, report)

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
    check_prefill(parsed, report)
    check_approval_consistency(fm, criteria, report)

    if fm.get("status") == "approved" and report.errors:
        report.error(
            "status is 'approved' while the spec has errors — an approved spec "
            "must be compilable",
            code="spec.frontmatter.approved_with_errors",
            path=spec_path("frontmatter", None, "status"),
            evidence={"count": len(report.errors)},
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

    if yaml is None or dp_diagnostics.yaml is None:
        print(
            "environment.dependency_missing: dp-spec validation needs PyYAML: "
            "pip install pyyaml",
            file=sys.stderr,
        )
        return 2

    if not args.spec.is_file():
        print(f"no such file: {args.spec}", file=sys.stderr)
        return 2

    try:
        report = validate(args.spec)
    except UnicodeDecodeError as exc:
        # spec.encoding.not_utf8 — raised at the file-read boundary, before a
        # Report exists, so it is the one code emitted outside report.error().
        print(
            f"spec.encoding.not_utf8 {args.spec}: the file is not valid UTF-8 ({exc})",
            file=sys.stderr,
        )
        return 2

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
        return 0 if report.ok else 1

    for diag in report.warnings:
        print(f"WARN  {diag.code} {diag.path}: {diag.message}")
    for diag in report.errors:
        print(f"ERROR {diag.code} {diag.path}: {diag.message}")

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
