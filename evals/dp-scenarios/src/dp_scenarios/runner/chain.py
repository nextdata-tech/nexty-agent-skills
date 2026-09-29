"""Runner-owned publication boundary for a chained scenario.

Only retained supervisor history can trigger the switch.  This module never
uses agent text or an operator message as publication evidence.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
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


def _literal_stage_values(node: ast.AST) -> tuple[str, ...] | None:
    if isinstance(node, (ast.Tuple, ast.List)):
        values = node.elts
    elif (
        isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "frozenset"
        and len(node.args) == 1 and not node.keywords
        and isinstance(node.args[0], (ast.Tuple, ast.List, ast.Set))
    ):
        values = node.args[0].elts
    else:
        return None
    if not all(isinstance(value, ast.Constant) and isinstance(value.value, str) for value in values):
        return None
    return tuple(value.value for value in values if isinstance(value, ast.Constant))


def _module_stage_constants(tree: ast.Module, stages: tuple[str, ...]) -> dict[str, tuple[str, ...]]:
    constants: dict[str, tuple[str, ...]] = {}
    for statement in tree.body:
        if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
            target, value = statement.targets[0], statement.value
        elif isinstance(statement, ast.AnnAssign):
            target, value = statement.target, statement.value
        else:
            continue
        if not isinstance(target, ast.Name) or value is None:
            continue
        values = _literal_stage_values(value)
        if values is None:
            continue
        stores = [n for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id == target.id and isinstance(n.ctx, (ast.Store, ast.Del))]
        mutators = {"append", "clear", "extend", "insert", "pop", "remove", "reverse", "sort"}
        mutated = any(
            isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and isinstance(n.func.value, ast.Name) and n.func.value.id == target.id and n.func.attr in mutators
            for n in ast.walk(tree)
        ) or any(
            isinstance(n, ast.Subscript) and isinstance(n.value, ast.Name) and n.value.id == target.id
            and isinstance(n.ctx, (ast.Store, ast.Del)) for n in ast.walk(tree)
        )
        aliased_list = isinstance(value, ast.List) and any(
            isinstance(n, (ast.Assign, ast.AnnAssign))
            and isinstance(n.value, ast.Name) and n.value.id == target.id
            for n in ast.walk(tree)
        )
        if (
            len(stores) == 1 and stores[0] is target and not mutated and not aliased_list
            and len(values) == len(stages) and len(set(values)) == len(values) and set(values) == set(stages)
        ):
            constants[target.id] = values
    return constants


def _local_stage_constants(
    verifier: ast.FunctionDef | ast.AsyncFunctionDef, stages: tuple[str, ...]
) -> dict[str, tuple[str, ...]]:
    constants: dict[str, tuple[str, ...]] = {}
    for statement in verifier.body:
        if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
            target, value = statement.targets[0], statement.value
        elif isinstance(statement, ast.AnnAssign):
            target, value = statement.target, statement.value
        else:
            continue
        if not isinstance(target, ast.Name) or value is None:
            continue
        values = _literal_stage_values(value)
        if values is None:
            continue
        stores = [
            n for n in ast.walk(verifier)
            if isinstance(n, ast.Name) and n.id == target.id and isinstance(n.ctx, (ast.Store, ast.Del))
        ]
        mutators = {"append", "clear", "extend", "insert", "pop", "remove", "reverse", "sort"}
        mutated = any(
            isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and isinstance(n.func.value, ast.Name) and n.func.value.id == target.id and n.func.attr in mutators
            for n in ast.walk(verifier)
        ) or any(
            isinstance(n, ast.Subscript) and isinstance(n.value, ast.Name) and n.value.id == target.id
            and isinstance(n.ctx, (ast.Store, ast.Del)) for n in ast.walk(verifier)
        )
        aliased_list = isinstance(value, ast.List) and any(
            isinstance(n, (ast.Assign, ast.AnnAssign))
            and isinstance(n.value, ast.Name) and n.value.id == target.id
            for n in ast.walk(verifier)
        )
        if (
            len(stores) == 1 and stores[0] is target and not mutated and not aliased_list
            and len(values) == len(stages) and len(set(values)) == len(values) and set(values) == set(stages)
        ):
            constants[target.id] = values
    return constants


def _failed_return(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Return) and isinstance(node.value, ast.Call)
        and _name(node.value.func).split(".")[-1] == "VerifyResult"
        and bool(node.value.args)
        and _name(node.value.args[0]) == "VerifyResultEnum.FAILED"
    )


def _fails_directly(body: list[ast.stmt]) -> bool:
    returns = [node for stmt in body for node in ast.walk(stmt) if isinstance(node, ast.Return)]
    return len(returns) == 1 and returns[0] in body and _failed_return(returns[0])


def _stage_values(expression: ast.expr, stages: tuple[str, ...], constants: Mapping[str, tuple[str, ...]]) -> bool:
    values = _literal_stage_values(expression)
    if values is None and isinstance(expression, ast.Name):
        values = constants.get(expression.id)
    return values is not None and len(values) == len(stages) and len(set(values)) == len(values) and set(values) == set(stages)


def _python_stage_rejection(verifier: ast.AST, stages: tuple[str, ...], constants: Mapping[str, tuple[str, ...]]) -> bool:
    return any(
        isinstance(node, ast.If) and isinstance(node.test, ast.Compare)
        and len(node.test.ops) == 1 and _fails_directly(node.body)
        and "stage" in ast.unparse(node.test.left).casefold()
        and any(isinstance(op, ast.NotIn) and _stage_values(right, stages, constants)
                for op, right in zip(node.test.ops, node.test.comparators))
        for node in ast.walk(verifier)
    )


def _bound_constant(node: ast.expr, constants: Mapping[str, tuple[str, ...]]) -> str | None:
    if isinstance(node, ast.Name):
        return node.id if node.id in constants else None
    if (
        isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        and node.func.id in {"list", "tuple", "frozenset"} and len(node.args) == 1 and not node.keywords
        and isinstance(node.args[0], ast.Name) and node.args[0].id in constants
    ):
        return node.args[0].id
    return None


def _placeholder_constant(verifier: ast.AST, name: str, before_line: int) -> str | None:
    assignments = [s for s in getattr(verifier, "body", []) if isinstance(s, ast.Assign)
                   and len(s.targets) == 1 and isinstance(s.targets[0], ast.Name) and s.targets[0].id == name]
    stores = [n for n in ast.walk(verifier) if isinstance(n, ast.Name) and n.id == name and isinstance(n.ctx, (ast.Store, ast.Del))]
    if len(assignments) != 1 or len(stores) != 1 or stores[0] is not assignments[0].targets[0] or assignments[0].lineno >= before_line:
        return None
    call = assignments[0].value
    if not (
        isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and call.func.attr == "join"
        and isinstance(call.func.value, ast.Constant) and call.func.value.value in {",", ", "}
        and len(call.args) == 1 and not call.keywords and isinstance(call.args[0], ast.GeneratorExp)
    ):
        return None
    gen = call.args[0]
    if (
        isinstance(gen.elt, ast.Constant) and gen.elt.value in {"?", "%s"}
        and len(gen.generators) == 1 and not gen.generators[0].ifs
        and isinstance(gen.generators[0].iter, ast.Name)
    ):
        return gen.generators[0].iter.id
    return None


def _has_failed_rows_branch(verifier: ast.AST, rows: str) -> bool:
    def positive(node: ast.expr) -> bool:
        if isinstance(node, ast.Name):
            return node.id == rows
        if isinstance(node, ast.BoolOp):
            checks = [positive(value) for value in node.values]
            return any(checks) if isinstance(node.op, ast.Or) else all(checks)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "bool":
            return len(node.args) == 1 and isinstance(node.args[0], ast.Name) and node.args[0].id == rows
        if (
            isinstance(node, ast.Compare) and len(node.ops) == len(node.comparators) == 1
            and isinstance(node.left, ast.Call) and isinstance(node.left.func, ast.Name) and node.left.func.id == "len"
            and len(node.left.args) == 1 and isinstance(node.left.args[0], ast.Name) and node.left.args[0].id == rows
            and isinstance(node.comparators[0], ast.Constant)
            and node.comparators[0].value == 0 and isinstance(node.ops[0], (ast.Gt, ast.NotEq))
        ):
            return True
        return False

    return any(isinstance(n, ast.If) and positive(n.test) and _fails_directly(n.body) for n in ast.walk(verifier))


def _sql_stage_rejection(verifier: ast.AST, stages: tuple[str, ...], constants: Mapping[str, tuple[str, ...]]) -> bool:
    for query in (n for n in ast.walk(verifier) if isinstance(n, ast.Call) and _name(n.func).endswith(".execute")):
        if len(query.args) not in {1, 2} or query.keywords:
            continue
        expression = query.args[0]
        if isinstance(expression, ast.Constant) and isinstance(expression.value, str):
            sql, formatted = expression.value, []
        elif isinstance(expression, ast.JoinedStr):
            formatted = [n.value for n in expression.values if isinstance(n, ast.FormattedValue)]
            if any(not isinstance(n, ast.Constant) or not isinstance(n.value, str) for n in expression.values if not isinstance(n, ast.FormattedValue)):
                continue
            sql = "".join(
                n.value if isinstance(n, ast.Constant) else f"__VALUE_{formatted.index(n.value)}__"
                for n in expression.values
            )
        else:
            continue

        parameter = _bound_constant(query.args[1], constants) if len(query.args) == 2 else None
        parameter_index = None
        if formatted:
            indexes = [i for i, value in enumerate(formatted)
                       if isinstance(value, ast.Name) and parameter is not None
                       and _placeholder_constant(verifier, value.id, query.lineno) == parameter]
            if len(indexes) > 1:
                continue
            parameter_index = indexes[0] if indexes else None
            valid = True
            for i, value in enumerate(formatted):
                marker = f"__VALUE_{i}__"
                if i == parameter_index:
                    sql = sql.replace(marker, "__BOUND__")
                elif isinstance(value, ast.Name) and any(
                    isinstance(s, ast.Assign) and len(s.targets) == 1 and isinstance(s.targets[0], ast.Name)
                    and s.targets[0].id == value.id and isinstance(s.value, ast.Call)
                    and isinstance(s.value.func, ast.Attribute) and s.value.func.attr == "full_table_name"
                    and len(s.value.args) == 1 and isinstance(s.value.args[0], ast.Constant)
                    and s.value.args[0].value == "pipeline" for s in getattr(verifier, "body", [])
                ) and re.search(rf"\bFROM\s+{marker}\b", sql, re.I):
                    sql = sql.replace(marker, "pipeline")
                else:
                    valid = False
                    break
            if not valid:
                continue

        clause = re.search(r"\bstage\b\s+NOT\s+IN\s*\((?P<values>[^()]*)\)", sql, re.I | re.S)
        if clause is None:
            clause = re.search(r"NOT\s*\(\s*\bstage\b\s+IN\s*\((?P<values>[^()]*)\)\s*\)", sql, re.I | re.S)
        if clause is None:
            continue
        values = clause.group("values").strip()
        if values == "__BOUND__":
            if parameter is None or parameter_index is None or re.search(r"\?|%s", sql.replace("__BOUND__", "")):
                continue
        elif re.fullmatch(r"\s*(?:\?|%s)(?:\s*,\s*(?:\?|%s))*\s*", values):
            if parameter is None or len(re.findall(r"\?|%s", values)) != len(stages) or len(re.findall(r"\?|%s", sql)) != len(stages):
                continue
        else:
            quoted = re.findall(r"'([^']*)'|\"([^\"]*)\"", values)
            literal = tuple(a or b for a, b in quoted)
            if len(query.args) != 1 or not re.fullmatch(r"\s*(?:'[^']*'|\"[^\"]*\")(?:\s*,\s*(?:'[^']*'|\"[^\"]*\"))*\s*", values):
                continue
            if len(literal) != len(stages) or len(set(literal)) != len(literal) or set(literal) != set(stages):
                continue

        for result in ast.walk(verifier):
            if not (
                isinstance(result, ast.Assign) and len(result.targets) == 1 and isinstance(result.targets[0], ast.Name)
                and isinstance(result.value, ast.Call) and isinstance(result.value.func, ast.Attribute)
                and result.value.func.attr == "fetchall" and isinstance(result.value.func.value, ast.Call)
                and result.value.func.value is query
            ):
                continue
            rows = result.targets[0].id
            stores = [n for n in ast.walk(verifier) if isinstance(n, ast.Name) and n.id == rows and isinstance(n.ctx, (ast.Store, ast.Del))]
            mutators = {"append", "clear", "extend", "insert", "pop", "remove", "reverse", "sort"}
            mutated_rows = any(
                isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and isinstance(n.func.value, ast.Name) and n.func.value.id == rows and n.func.attr in mutators
                for n in ast.walk(verifier)
            ) or any(
                isinstance(n, ast.Subscript) and isinstance(n.value, ast.Name) and n.value.id == rows
                and isinstance(n.ctx, (ast.Store, ast.Del)) for n in ast.walk(verifier)
            )
            if len(stores) == 1 and not mutated_rows and _has_failed_rows_branch(verifier, rows):
                return True
    return False


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
    module_constants = _module_stage_constants(tree, stages)
    for verifier in verifiers:
        constants = {**module_constants, **_local_stage_constants(verifier, stages)}
        if _python_stage_rejection(verifier, stages, constants) or _sql_stage_rejection(
            verifier, stages, constants
        ):
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
