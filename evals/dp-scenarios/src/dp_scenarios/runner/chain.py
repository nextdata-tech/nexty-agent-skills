"""Runner-owned publication boundary for a chained scenario.

Only retained supervisor history can trigger the switch.  This module never
uses agent text or an operator message as publication evidence.
"""

from __future__ import annotations

import ast
import hashlib
import json
from collections.abc import Callable, Mapping
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from .supervisor_history import (
    CAPTURES_SCHEMA,
    DEFINITION_EXPORT_SCHEMA,
    PUBLICATION_SCHEMA,
    RUN_RECORDS_SCHEMA,
)

if TYPE_CHECKING:
    from ..scenario import ChainSpec
    from .environment import MockSourceHandle


CHAIN_SCHEMA = "dp-scenario-chain-v1"


def _document(root: Path, name: str, schema: str) -> Mapping[str, object] | None:
    try:
        value = json.loads((root / name).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, Mapping) and value.get("schema") == schema else None


def _items(value: object) -> list[Mapping[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _name(node: ast.AST) -> str:
    if isinstance(node, ast.Call):
        return _name(node.func)
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_name(node.value)}.{node.attr}"
    return ""


def _stage_constraint(source: bytes, stages: tuple[str, ...]) -> bool:
    """Recognize an executable five-stage rejection, never a comment/prose claim.

    A captured custom verifier may test rows directly in Python or query them
    with SQL.  Both must have an on_verify function, all official values in
    executable constants, an out-of-list predicate, and a FAILED return.
    This conservative precondition does not claim that a runtime warning was
    observed; the B11 follow-up makes the stronger final structural check.
    """

    try:
        tree = ast.parse(source)
    except (SyntaxError, UnicodeError, ValueError):
        return False
    verifiers = [
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and any("on_verify" in _name(dec) for dec in node.decorator_list)
    ]
    if not verifiers:
        return False
    for verifier in verifiers:
        nodes = list(ast.walk(verifier))
        constants = [node.value for node in nodes if isinstance(node, ast.Constant) and isinstance(node.value, str)]
        if not set(stages).issubset(set(constants) | {
            token for value in constants for token in (value.replace("'", "\"").split('"'))
        }):
            # SQL constants hold all values in one string rather than as
            # separate AST nodes.
            if not any(all(stage in value for stage in stages) for value in constants):
                continue
        out_of_list = any(
            isinstance(node, ast.Compare)
            and any(isinstance(op, ast.NotIn) for op in node.ops)
            and "stage" in ast.unparse(node.left).casefold()
            for node in nodes
        ) or any("stage" in value.casefold() and "not in" in value.casefold() for value in constants)
        failed_return = any(
            isinstance(node, ast.Return)
            and node.value is not None
            and any(_name(child) == "VerifyResultEnum.FAILED" for child in ast.walk(node.value))
            for node in nodes
        )
        if out_of_list and failed_return:
            return True
    return False


def _typed_stage_constraint(source: bytes, stages: tuple[str, ...], model_names: set[str]) -> bool:
    """Accept only a promised model whose stage field is a closed Literal."""

    try:
        tree = ast.parse(source)
    except (SyntaxError, UnicodeError, ValueError):
        return False
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name not in model_names:
            continue
        for field in node.body:
            if not isinstance(field, ast.AnnAssign) or not isinstance(field.target, ast.Name) or field.target.id != "stage":
                continue
            annotation = field.annotation
            if not isinstance(annotation, ast.Subscript) or _name(annotation.value).split(".")[-1] != "Literal":
                continue
            values = (
                annotation.slice.elts
                if isinstance(annotation.slice, ast.Tuple)
                else [annotation.slice]
            )
            if all(isinstance(value, ast.Constant) and isinstance(value.value, str) for value in values) and {
                value.value for value in values if isinstance(value, ast.Constant)
            } == set(stages):
                return True
    return False


def _captured_precondition(
    root: Path, run: Mapping[str, object], stages: tuple[str, ...]
) -> tuple[str, str]:
    digest = run.get("capture_sha256")
    definition_id = run.get("definition_id")
    if not isinstance(definition_id, str):
        return "ungraded", "drift_capture_unavailable"
    definitions = _document(root, "definition-export.json", DEFINITION_EXPORT_SCHEMA)
    if definitions is None:
        return "ungraded", "drift_capture_unavailable"
    definition = next((item for item in _items(definitions.get("definitions")) if item.get("definition_id") == definition_id), None)
    if definition is None or definition.get("inventory_valid") is not True:
        return "ungraded", "drift_capture_unavailable"
    output_promises = _items(definition.get("output_promises"))
    model_names = {
        name.split(".")[-1]
        for promise in _items(definition.get("model_promises"))
        for name in _items_or_strings(promise.get("models"))
    }
    if not output_promises and not model_names:
        return "failed", "drift_prefix_invalid"
    if not isinstance(digest, str) or not digest.startswith("sha256:"):
        return "ungraded", "drift_capture_unavailable"
    captures = _document(root, "supervisor-captures.json", CAPTURES_SCHEMA)
    if captures is None:
        return "ungraded", "drift_capture_unavailable"
    capture = next((item for item in _items(captures.get("captures")) if item.get("capture_sha256") == digest and run.get("run_id") in _items_or_strings(item.get("run_ids"))), None)
    if capture is None:
        return "ungraded", "drift_capture_unavailable"
    files = {item.get("path"): item for item in _items(capture.get("files"))}

    def captured_source(source_path: object, expected_hash: object = None) -> bytes | None:
        if not isinstance(source_path, str):
            return None
        relative = PurePosixPath(source_path)
        if (
            relative.is_absolute() or ".." in relative.parts or relative.suffix != ".py"
            or not relative.parts
            or not (
                relative.parts[0] in {"contracts", "transform"}
                or relative.parts in {("models.py",), ("spec.py",)}
            )
        ):
            return None
        entry = files.get(source_path)
        if not isinstance(entry, Mapping):
            return None
        path = root / "supervisor-captures" / digest.removeprefix("sha256:") / source_path
        try:
            content = path.read_bytes()
        except OSError:
            return None
        actual_hash = "sha256:" + hashlib.sha256(content).hexdigest()
        if actual_hash != entry.get("sha256") or (
            expected_hash is not None and actual_hash != expected_hash
        ):
            return None
        return content

    unavailable = False
    for promise in output_promises:
        if promise.get("source_hash_verified") is not True or promise.get("source_in_inventory") is not True:
            continue
        content = captured_source(promise.get("source"), promise.get("source_sha256"))
        if content is None:
            unavailable = True
            continue
        if _stage_constraint(content, stages):
            return "valid", ""
    if model_names:
        for source_path in files:
            if not isinstance(source_path, str) or not (
                source_path.startswith("transform/") or source_path in {"models.py", "spec.py"}
            ):
                continue
            content = captured_source(source_path)
            if content is None:
                unavailable = True
                continue
            if _typed_stage_constraint(content, stages, model_names):
                return "valid", ""
    if unavailable:
        return "ungraded", "drift_capture_unavailable"
    return "failed", "drift_prefix_invalid"


def _items_or_strings(value: object) -> tuple[str, ...]:
    return tuple(item for item in value if isinstance(item, str)) if isinstance(value, list) else ()


class ChainController:
    """Transition once, after a verified first publication and prefix check."""

    def __init__(
        self,
        spec: ChainSpec,
        artifact_root: Path,
        source: MockSourceHandle,
        activate_overlay: Callable[[str], None],
        skip_prefix: Callable[[int], None],
        *,
        replay_transition: Mapping[str, object] | None = None,
    ) -> None:
        self.spec = spec
        self.root = artifact_root
        self.source = source
        self.activate_overlay = activate_overlay
        self.skip_prefix = skip_prefix
        self.replay_transition = replay_transition
        self.state: dict[str, object] = {"schema": CHAIN_SCHEMA, "status": "waiting"}

    def _write(self) -> None:
        self.root.joinpath("chain-state.json").write_text(
            json.dumps(self.state, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )

    def _switch(self, turn: int, release: Mapping[str, object]) -> None:
        # Source first: no suffix message or decision can be exposed until the
        # harness-owned route has actually accepted the v2 state.
        try:
            runtime = self.source.snapshot_runtime_state()
            states = runtime.get("current_states")
            if not isinstance(states, Mapping) or states.get(self.spec.source_family) != self.spec.from_state:
                raise RuntimeError("chain source was not in its declared initial state")
            self.source.set_dataset_state(self.spec.source_family, self.spec.to_state)
        except Exception:
            self.state = {
                "schema": CHAIN_SCHEMA,
                "status": "ungraded",
                "reason": "drift_source_switch_unavailable",
                "turn": turn,
                "prefix_release": dict(release),
            }
            self._write()
            return
        self.activate_overlay(self.spec.decision_overlay)
        self.skip_prefix(self.spec.prefix_turns)
        self.state = {
            "schema": CHAIN_SCHEMA,
            "status": "switched",
            "turn": turn,
            "source_family": self.spec.source_family,
            "from_state": self.spec.from_state,
            "to_state": self.spec.to_state,
            "decision_overlay": self.spec.decision_overlay,
            "prefix_release": dict(release),
        }
        self._write()

    def observe(self, turn: int) -> None:
        if self.state["status"] != "waiting":
            return
        if self.replay_transition is not None:
            if self.replay_transition.get("turn") == turn and self.replay_transition.get("status") == "switched":
                release = self.replay_transition.get("prefix_release")
                if isinstance(release, Mapping):
                    self._switch(turn, release)
            return
        publication = _document(self.root, "publication-history.json", PUBLICATION_SCHEMA)
        runs = _document(self.root, "run-records.json", RUN_RECORDS_SCHEMA)
        if publication is None or runs is None:
            return
        candidates = _items(publication.get("releases"))
        if not candidates:
            return
        run_by_id = {item.get("run_id"): item for item in _items(runs.get("runs"))}
        for release in candidates:
            if release.get("attributed_by") not in {"built_run", "session_request"}:
                continue
            run = run_by_id.get(release.get("run_id"))
            if not isinstance(run, Mapping) or run.get("status") != "Published":
                self.state = {
                    "schema": CHAIN_SCHEMA,
                    "status": "ungraded",
                    "reason": "drift_run_publication_unavailable",
                    "turn": turn,
                }
                self._write()
                return
            if release.get("workflow_id") != run.get("workflow_id"):
                self.state = {
                    "schema": CHAIN_SCHEMA,
                    "status": "ungraded",
                    "reason": "drift_publication_identity_unavailable",
                    "turn": turn,
                }
                self._write()
                return
            identity_keys = ("workflow_id", "run_id", "publish_sequence", "artifact_id", "definition_id")
            if any(not isinstance(release.get(key), str) or not release.get(key) for key in identity_keys):
                self.state = {
                    "schema": CHAIN_SCHEMA,
                    "status": "ungraded",
                    "reason": "drift_publication_identity_unavailable",
                    "turn": turn,
                }
                self._write()
                return
            if any(run.get(key) != release.get(key) for key in ("publish_sequence", "artifact_id", "definition_id")):
                self.state = {
                    "schema": CHAIN_SCHEMA,
                    "status": "ungraded",
                    "reason": "drift_publication_identity_unavailable",
                    "turn": turn,
                }
                self._write()
                return
            status, reason = _captured_precondition(self.root, run, self.spec.stage_values)
            if status != "valid":
                self.state = {"schema": CHAIN_SCHEMA, "status": status, "reason": reason, "turn": turn, "prefix_release": dict(release)}
                self._write()
                return
            self._switch(turn, release)
            return

    def finalize(self, *, interrupted: bool = False) -> Mapping[str, object]:
        if self.state["status"] == "waiting":
            if self.replay_transition is not None and self.replay_transition.get("status") in {"failed", "ungraded"}:
                self.state = dict(self.replay_transition)
            else:
                self.state = {
                    "schema": CHAIN_SCHEMA,
                    "status": "ungraded" if interrupted else "failed",
                    "reason": "chain_environment_interrupted" if interrupted else "drift_prefix_publication_missing",
                }
            self._write()
        return self.state
