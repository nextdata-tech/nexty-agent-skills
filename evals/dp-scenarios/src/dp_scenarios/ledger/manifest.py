"""Typed run identity and machine-stable fixture identity.

The manifest is the immutable identity of one scenario trial.  It records the
scenario, tier, trial, model and prompt inputs, supervisor/runtime versions,
fixture inputs, and execution budget; omitting any of those values would make
two runs indistinguishable after the fact.  ``not-applicable`` is accepted only
for fields explicitly waived by the tier, so an absent dependency cannot be
confused with a dependency that was meant to participate but failed to load.

Fixture hashing walks directory entries without following symlinks.  It hashes
normalized relative names, entry kinds, whether any executable bit is set,
link targets, file bytes, and directory entries, while excluding dotfiles and
``__pycache__``.  Thus ``0o755`` and ``0o700`` intentionally hash alike.  The
identity is independent of absolute paths, inode metadata, mtimes, locale, and
symlink targets outside the fixture tree; absolute symlink targets are
rejected rather than embedded in the identity.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path, PureWindowsPath
from typing import ClassVar


# The first twelve fields are the original run identity contract.  The
# remaining fields make scenario, tier, trial, drift, prompt, calibration, and
# fixture provenance explicit.  run_id is included so row identity can be
# checked against row zero rather than inferred from a row chosen by a caller.
MANIFEST_FIELDS = (
    "agent_model_id",
    "agent_sampling_params",
    "judge_model_id",
    "judge_prompt_hash",
    "skill_pack_version",
    "supervisor_version",
    "nxd_data_product_wheel_version",
    "fixture_dir_hash",
    "mock_api_version",
    "operator_script_hash",
    "turn_budget",
    "grant_fixture_hash",
    "scenario_id",
    "tier",
    "trial_index",
    "canary_claims_hash",
    "persona_paraphrase_prompt_hash",
    "judge_calibration_set_hash",
    "fixture_seed",
    "fixture_base_instant",
    "run_id",
    "supervisor_binary_path",
    "session_root",
    "session_config_path",
    "session_config_sha256",
    "session_trace_path",
    "session_server_result_path",
    "runtime_knobs",
    "validation_mode",
)

MANIFEST_RECORD_TYPE = "run_manifest"
NOT_APPLICABLE = "not-applicable"


def _default_runtime_knobs() -> dict[str, object]:
    """Return the explicit all-off pin used by direct manifest constructors."""

    return {
        "schema_version": 1,
        "transform_window": {"enabled": False},
        "broker_fault": {"enabled": False, "active_attempt": 1, "active_fault": "none"},
        "workflow_switch": {"enabled": False},
    }


def default_runtime_knobs() -> dict[str, object]:
    """Return a fresh all-off pin for legacy report adapters."""

    return _default_runtime_knobs()

# These fields describe the live desktop substrate.  They are required for a
# live manifest; replay has an explicit, tier-keyed waiver below because it
# intentionally does not reacquire the substrate.
DESKTOP_SESSION_FIELDS = frozenset(
    {
        "supervisor_binary_path",
        "session_root",
        "session_config_path",
        "session_config_sha256",
        "session_trace_path",
        "session_server_result_path",
    }
)

REPLAY_SESSION_PATH_FIELDS = frozenset(
    {
        "session_root",
        "session_config_path",
        "session_trace_path",
        "session_server_result_path",
    }
)

# Validation mode records how the run was established.  It is persisted for
# later validation, but is metadata rather than a property under test and must
# never create a statistical pairing axis.
COMPARABILITY_EXCLUDED_FIELDS = REPLAY_SESSION_PATH_FIELDS | frozenset({"validation_mode"})

# Tiers are named for what they are: the smoke tier runs on every change, the
# core tier weekly, the full tier per release.  The smoke and core tiers are
# implemented here, and each waives the pins for surfaces it never exercises.
# Keep T0 as an alias for persisted manifests produced by the original smoke
# tier; both spellings use the same waiver policy.
_SMOKE_TIER_WAIVERS = frozenset(
    {
        "judge_model_id",
        "judge_prompt_hash",
        "judge_calibration_set_hash",
        "grant_fixture_hash",
        "persona_paraphrase_prompt_hash",
    }
)
# The core tier is documented as "all LLM-free except B1's fixture" (note 10),
# so it waives the same judge/calibration/grant/paraphrase surfaces the smoke
# tier does.  A scenario that does need those pins simply does not waive
# itself out of supplying them; the waiver only permits ``not-applicable``.
_CORE_TIER_WAIVERS = _SMOKE_TIER_WAIVERS
TIER_WAIVERS: dict[str, frozenset[str]] = {
    "smoke": _SMOKE_TIER_WAIVERS,
    "T0": _SMOKE_TIER_WAIVERS,
    "core": _CORE_TIER_WAIVERS,
}

REPLAY_TIER_WAIVERS: dict[str, frozenset[str]] = {
    tier: waivers | DESKTOP_SESSION_FIELDS for tier, waivers in TIER_WAIVERS.items()
}


class ManifestError(ValueError):
    """Raised when a manifest is incomplete, mistyped, or not tier-valid."""

    def __init__(
        self,
        message: str,
        *,
        field: str | None = None,
        value: object = None,
        code: str = "invalid_manifest",
    ) -> None:
        super().__init__(message)
        self.field = field
        self.value = value
        self.code = code


class Comparability(str, Enum):
    """The three outcomes needed by repeated-trial and paired statistics."""

    IDENTICAL = "IDENTICAL"
    SINGLE_FIELD = "SINGLE_FIELD"
    MULTI_FIELD = "MULTI_FIELD"


@dataclass(frozen=True, slots=True)
class ComparabilityResult:
    """Field differences plus their three-way statistical classification."""

    differing_fields: set[str]
    kind: Comparability


@dataclass(frozen=True, slots=True)
class Manifest:
    """Complete, typed row-zero identity for one scenario trial.

    ``turn_budget`` is recorded as run identity; enforcement belongs to the
    operator engine that drives the trial.
    """

    agent_model_id: str
    agent_sampling_params: Mapping[str, object]
    judge_model_id: str
    judge_prompt_hash: str
    skill_pack_version: str
    supervisor_version: str
    nxd_data_product_wheel_version: str
    fixture_dir_hash: str
    mock_api_version: str
    operator_script_hash: str
    turn_budget: int
    grant_fixture_hash: str
    scenario_id: str
    tier: str
    trial_index: int
    canary_claims_hash: str
    persona_paraphrase_prompt_hash: str
    judge_calibration_set_hash: str
    fixture_seed: int
    fixture_base_instant: str
    run_id: str
    supervisor_binary_path: str = NOT_APPLICABLE
    session_root: str = NOT_APPLICABLE
    session_config_path: str = NOT_APPLICABLE
    session_config_sha256: str = NOT_APPLICABLE
    session_trace_path: str = NOT_APPLICABLE
    session_server_result_path: str = NOT_APPLICABLE
    # Every run carries an explicit off/on record for the supervisor knobs.
    # The default is the canonical all-off pin for callers that construct a
    # replay manifest directly; RunEnvironment always supplies its own value.
    runtime_knobs: Mapping[str, object] = field(
        default_factory=_default_runtime_knobs
    )
    # Persist this distinction.  A stored live manifest must still require
    # desktop identity when a later validator reads it without the substrate.
    validation_mode: str = "replay"

    fields: ClassVar[tuple[str, ...]] = MANIFEST_FIELDS

    def __post_init__(self) -> None:
        string_fields = (
            "agent_model_id",
            "judge_model_id",
            "judge_prompt_hash",
            "skill_pack_version",
            "supervisor_version",
            "nxd_data_product_wheel_version",
            "fixture_dir_hash",
            "mock_api_version",
            "operator_script_hash",
            "grant_fixture_hash",
            "scenario_id",
            "tier",
            "canary_claims_hash",
            "persona_paraphrase_prompt_hash",
            "judge_calibration_set_hash",
            "fixture_base_instant",
            "run_id",
            "supervisor_binary_path",
            "session_root",
            "session_config_path",
            "session_config_sha256",
            "session_trace_path",
            "session_server_result_path",
        )
        for field_name in string_fields:
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise ManifestError(
                    f"manifest field {field_name} must be a non-empty string",
                    field=field_name,
                    value=value,
                )

        if not isinstance(self.agent_sampling_params, Mapping) or not self.agent_sampling_params:
            raise ManifestError(
                "manifest field agent_sampling_params must be a non-empty mapping",
                field="agent_sampling_params",
                value=self.agent_sampling_params,
            )
        if not isinstance(self.runtime_knobs, Mapping) or not self.runtime_knobs:
            raise ManifestError(
                "manifest field runtime_knobs must be a non-empty mapping",
                field="runtime_knobs",
                value=self.runtime_knobs,
            )
        object.__setattr__(self, "runtime_knobs", dict(self.runtime_knobs))
        if isinstance(self.turn_budget, bool) or not isinstance(self.turn_budget, int) or self.turn_budget < 1:
            raise ManifestError(
                "manifest field turn_budget must be an integer of at least 1",
                field="turn_budget",
                value=self.turn_budget,
            )
        if isinstance(self.trial_index, bool) or not isinstance(self.trial_index, int) or self.trial_index < 0:
            raise ManifestError(
                "manifest field trial_index must be a non-negative integer",
                field="trial_index",
                value=self.trial_index,
            )
        if isinstance(self.fixture_seed, bool) or not isinstance(self.fixture_seed, int) or self.fixture_seed < 0:
            raise ManifestError(
                "manifest field fixture_seed must be a non-negative integer",
                field="fixture_seed",
                value=self.fixture_seed,
            )

        if self.tier not in TIER_WAIVERS:
            raise ManifestError(
                f"unknown tier {self.tier!r}",
                field="tier",
                value=self.tier,
            )
        if self.validation_mode not in {"live", "replay"}:
            raise ManifestError(
                f"unknown manifest validation mode {self.validation_mode!r}",
                field="validation_mode",
                value=self.validation_mode,
            )
        waivers_by_tier = TIER_WAIVERS if self.validation_mode == "live" else REPLAY_TIER_WAIVERS
        waivers = waivers_by_tier[self.tier]
        for field_name in self.fields:
            if getattr(self, field_name) == NOT_APPLICABLE and field_name not in waivers:
                raise ManifestError(
                    f"not-applicable is not permitted for manifest field {field_name} in tier {self.tier}",
                    field=field_name,
                    value=NOT_APPLICABLE,
                    code="sentinel_not_permitted_for_tier",
                )

        try:
            json.dumps(self.to_dict(), ensure_ascii=False)
        except (TypeError, ValueError) as exc:
            raise ManifestError(f"manifest contains a non-JSON value: {exc}") from exc

    def to_dict(self) -> dict[str, object]:
        """Return all manifest fields in their declared order."""

        return {field_name: getattr(self, field_name) for field_name in self.fields}

    def to_record(self) -> dict[str, object]:
        """Return the canonical manifest record before storage adds its anchor."""

        return {"record_type": MANIFEST_RECORD_TYPE, "manifest": self.to_dict()}

    @classmethod
    def from_mapping(cls, value: Mapping[str, object], *, replay: bool | None = False) -> "Manifest":
        """Construct a manifest, preserving a persisted mode when requested.

        ``replay=None`` is for stored artifacts: it uses the mode written into
        the manifest and falls back to replay for pre-mode artifacts.  The
        boolean forms retain the caller's explicit strict/live or tolerant/
        replay parsing choice for in-memory values.
        """

        if not isinstance(value, Mapping):
            raise ManifestError("manifest must be a JSON object", value=value)
        unknown = set(value) - set(cls.fields)
        if unknown:
            names = ", ".join(sorted(str(name) for name in unknown))
            raise ManifestError(f"manifest has unknown field(s): {names}", field=names, value=unknown)
        if replay is None:
            if "validation_mode" in value:
                persisted_mode = value["validation_mode"]
            else:
                has_live_identity = any(
                    field_name in value and value[field_name] != NOT_APPLICABLE
                    for field_name in DESKTOP_SESSION_FIELDS
                )
                persisted_mode = "live" if has_live_identity else "replay"
            validation_mode = persisted_mode
        else:
            validation_mode = "replay" if replay else "live"
        if not isinstance(validation_mode, str):
            raise ManifestError(
                "manifest field validation_mode must be a string",
                field="validation_mode",
                value=validation_mode,
            )
        # runtime_knobs is never defaulted on parse.  A run whose active knobs
        # are unknown cannot be compared with any other run, so an omitted pin
        # is a parse failure rather than an assumption that nothing was on.
        missing = [
            field_name
            for field_name in cls.fields
            if field_name not in value
            and field_name != "validation_mode"
            and (validation_mode == "live" or field_name not in DESKTOP_SESSION_FIELDS)
        ]
        if missing:
            raise ManifestError(
                "manifest is missing field(s): " + ", ".join(missing),
                field=missing[0],
                value=None,
            )
        values = {
            field_name: value.get(field_name, NOT_APPLICABLE)
            for field_name in cls.fields
        }
        values["validation_mode"] = validation_mode
        return cls(
            **values,
        )  # type: ignore[arg-type]

    @classmethod
    def from_record(cls, value: object, *, replay: bool | None = False) -> "Manifest":
        """Parse a canonical manifest record for validation."""

        if not isinstance(value, Mapping):
            raise ManifestError("manifest record must be a JSON object", value=value)
        marker = value.get("record_type", value.get("type"))
        nested = value.get("manifest")
        if marker in {MANIFEST_RECORD_TYPE, "manifest"}:
            if nested is not None and not isinstance(nested, Mapping):
                raise ManifestError("manifest record's manifest value must be an object", field="manifest", value=nested)
            return cls.from_mapping(
                nested if isinstance(nested, Mapping) else value,
                replay=replay,
            )
        if isinstance(nested, Mapping):
            return cls.from_mapping(nested, replay=replay)
        raise ManifestError("row zero is not a manifest record", field="record_type", value=marker)

    def comparable_to(self, other: "Manifest") -> ComparabilityResult:
        """Return exact differences and the three-way comparison outcome."""

        if not isinstance(other, Manifest):
            raise TypeError("manifest comparison requires another Manifest")
        differing = {
            field_name
            for field_name in self.fields
            if field_name not in COMPARABILITY_EXCLUDED_FIELDS
            and getattr(self, field_name) != getattr(other, field_name)
        }
        if not differing:
            kind = Comparability.IDENTICAL
        elif len(differing) == 1:
            kind = Comparability.SINGLE_FIELD
        else:
            kind = Comparability.MULTI_FIELD
        return ComparabilityResult(differing_fields=differing, kind=kind)


def fixture_dir_hash(directory: str | Path) -> str:
    """Return a deterministic hash of a fixture tree without following links.

    Executability records only whether any owner, group, or other execute bit
    is set; it does not preserve the exact permission mask.
    """

    root = Path(directory)
    if not root.is_dir():
        raise ManifestError(f"fixture directory does not exist or is not a directory: {root}")

    entries: list[tuple[str, str, int, bytes]] = []

    def visit(current: Path, relative_parts: tuple[str, ...]) -> None:
        try:
            children = list(os.scandir(current))
        except OSError as exc:
            raise ManifestError(f"could not read fixture directory {current}: {exc}") from exc
        for child in children:
            name = child.name
            if name.startswith(".") or name == "__pycache__":
                continue
            parts = relative_parts + (name,)
            if any(part.startswith(".") or part == "__pycache__" for part in parts):
                continue
            normalized_path = unicodedata.normalize("NFC", "/".join(parts))
            mode = child.stat(follow_symlinks=False).st_mode
            if stat.S_ISLNK(mode):
                link_target = os.readlink(child.path)
                if os.path.isabs(link_target) or PureWindowsPath(link_target).is_absolute():
                    raise ManifestError(
                        f"fixture tree contains an absolute symlink target: {child.path}"
                    )
                target = link_target.encode("utf-8")
                entries.append((normalized_path, "symlink", 0, target))
            elif stat.S_ISDIR(mode):
                entries.append((normalized_path, "directory", 0, b""))
                visit(Path(child.path), parts)
            elif stat.S_ISREG(mode):
                executable = 1 if (mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)) else 0
                try:
                    content = Path(child.path).read_bytes()
                except OSError as exc:
                    raise ManifestError(f"could not read fixture file {child.path}: {exc}") from exc
                entries.append((normalized_path, "file", executable, content))
            else:
                raise ManifestError(f"unsupported fixture entry type: {child.path}")

    visit(root, ())
    names = [entry[0] for entry in entries]
    if len(names) != len(set(names)):
        raise ManifestError("fixture tree contains paths that collide after NFC normalization")

    digest = hashlib.sha256()
    for relative, kind, executable, content in sorted(entries, key=lambda item: item[0]):
        path_bytes = relative.encode("utf-8")
        kind_bytes = kind.encode("ascii")
        for part in (kind_bytes, path_bytes, bytes([executable]), content):
            digest.update(len(part).to_bytes(8, "big"))
            digest.update(part)
    return digest.hexdigest()
