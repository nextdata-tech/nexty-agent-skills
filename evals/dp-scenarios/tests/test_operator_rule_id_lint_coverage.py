"""Structural guard against operator/lint drift on ``matched_rule_id``.

The operator (matcher.py, engine.py) is the only writer of
``matched_rule_id``; ``MATCHED_RULE_ID_RE`` in ``dp_scenarios.ledger.lint``
is a closed whitelist over the shapes it can emit. History: #400 added
``source.challenge_exhausted`` to engine.py without updating the lint regex,
and a live run whose every scored gate passed still failed the honesty hard
gate because that one row's ``matched_rule_id`` was rejected as if it were
free text.

Rather than re-list the operator's literals by hand (which is exactly the
list that drifted before), this module parses the operator's own source with
``ast`` and collects every string that can reach a ``MatchResult(...)`` or
``_Rule(...)`` rule-id argument, including f-string families. Each collected
example is asserted to be accepted by ``MATCHED_RULE_ID_RE``. If a future
change adds a new literal or f-string prefix to the operator without
extending the regex, this test fails immediately with the offending value,
instead of surfacing three hops away as a mystery ``honesty=False`` on a live
run.
"""

from __future__ import annotations

import ast
import inspect

import dp_scenarios.operator.engine as engine_mod
import dp_scenarios.operator.matcher as matcher_mod
from dp_scenarios.ledger.lint import MATCHED_RULE_ID_RE
from dp_scenarios.operator.matcher import Category

# Representative substitution values for f-string placeholders whose actual
# value is data-dependent (a fact key, a decision id, ...). The operator
# constrains these to identifier-ish text (see matcher.py/answer_sheet.py
# key validation); a couple of realistic shapes is enough to exercise the
# regex's character class without trying to enumerate every possible key.
_GENERIC_KEY_EXAMPLES = ("orders", "value_column", "review_fix_authorization")

_CATEGORY_VALUES = tuple(category.value for category in Category)


class _LiteralHarvester(ast.NodeVisitor):
    """Collect top-level string literals from an expression, skipping calls.

    Used to resolve an assignment's RHS (e.g. ``approval_rule = _fn(...) or
    "approval.request"``) to its possible literal values without picking up
    unrelated string constants nested inside a *call's* arguments -- such as
    the ``" "`` separator in ``" ".join(approval_clauses)`` in that same
    expression, which is not a candidate rule id at all. A boolean-or /
    ternary fallback literal sits as a direct sibling of the call in the
    expression tree, not inside it, so refusing to descend into ``Call``
    nodes keeps exactly the fallback literals and drops the incidental ones.
    """

    def __init__(self) -> None:
        self.found: set[str] = set()

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str):
            self.found.add(node.value)

    def visit_Call(self, node: ast.Call) -> None:
        return  # do not descend into call arguments


def _module_level_string_constants(tree: ast.Module) -> dict[str, set[str]]:
    """Map every assigned name to the string literals reachable from its RHS."""

    table: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        names = [target.id for target in node.targets if isinstance(target, ast.Name)]
        if not names:
            continue
        harvester = _LiteralHarvester()
        harvester.visit(node.value)
        if not harvester.found:
            continue
        for name in names:
            table.setdefault(name, set()).update(harvester.found)
    return table


def _guard_category(test: ast.expr) -> str | None:
    """Return the ``Category`` member name an ``if`` test pins, if any.

    Recognizes this file's one recurring guard shape,
    ``<expr>.category is Category.MEMBER``, which is how every branch keeps
    ``classified.category`` fixed for everything nested under it.
    """

    if (
        isinstance(test, ast.Compare)
        and len(test.ops) == 1
        and isinstance(test.ops[0], ast.Is)
        and len(test.comparators) == 1
    ):
        left, right = test.left, test.comparators[0]
        if (
            isinstance(left, ast.Attribute)
            and left.attr == "category"
            and isinstance(right, ast.Attribute)
            and isinstance(right.value, ast.Name)
            and right.value.id == "Category"
        ):
            return right.attr
    return None


# ``_unmatched`` in matcher.py resolves a factual category with no declared
# answer, and both of its call sites hand it ``classified`` from inside a
# ``Category.SOURCE_QUESTION`` or ``Category.STATUS_QUERY`` branch (see
# ``reply_for``). Its own body carries no local guard -- the restriction
# lives at the call sites -- so a plain lexical scan of ``_unmatched``'s body
# would (and did, before this override existed) also credit it with
# "unmatched.approval_request" and "unmatched.other", neither of which the
# operator can actually produce, and neither of which the lint whitelist
# accepts on purpose (see test_unmatched_rule_id_rejects_an_undeclared_category
# in test_ledger_lint.py). If a future change makes ``_unmatched`` reachable
# from another category, this override goes stale in the safe direction: the
# newly-reachable ``unmatched.<category>`` example is under-tested here, not
# wrongly accepted, and gate/lint regressions would still surface as a lint
# rejection on the resulting ledger row.
_UNMATCHED_METHOD_NAME = "_unmatched"
_UNMATCHED_METHOD_CATEGORIES = (Category.SOURCE_QUESTION.value, Category.STATUS_QUERY.value)


def _joined_str_examples(node: ast.JoinedStr, *, category_values: tuple[str, ...]) -> set[str]:
    """Expand an f-string rule-id template into concrete example strings."""

    part_options: list[list[str]] = []
    for value in node.values:
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            part_options.append([value.value])
        elif isinstance(value, ast.FormattedValue):
            expr_source = ast.unparse(value.value)
            if "category.value" in expr_source:
                part_options.append(list(category_values))
            else:
                part_options.append(list(_GENERIC_KEY_EXAMPLES))
        else:  # pragma: no cover - defensive, no other JoinedStr part types used
            raise AssertionError(f"unhandled f-string part: {ast.dump(value)}")
    examples = {""}
    for options in part_options:
        examples = {prefix + option for prefix in examples for option in options}
    return examples


def _collect_rule_id_examples(module) -> set[str]:
    source = inspect.getsource(module)
    tree = ast.parse(source)
    constants = _module_level_string_constants(tree)
    examples: set[str] = set()
    unresolved: list[str] = []

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self._category_stack: list[str] = []
            self._function_stack: list[str] = []

        def _current_category_values(self) -> tuple[str, ...]:
            if self._category_stack:
                return (self._category_stack[-1],)
            if self._function_stack and self._function_stack[-1] == _UNMATCHED_METHOD_NAME:
                return _UNMATCHED_METHOD_CATEGORIES
            return _CATEGORY_VALUES

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self._function_stack.append(node.name)
            self.generic_visit(node)
            self._function_stack.pop()

        def visit_If(self, node: ast.If) -> None:
            member = _guard_category(node.test)
            if member is None:
                self.generic_visit(node)
                return
            self._category_stack.append(Category[member].value)
            for child in node.body:
                self.visit(child)
            self._category_stack.pop()
            for child in node.orelse:
                self.visit(child)

        def visit_Call(self, node: ast.Call) -> None:
            callee = node.func
            name = callee.id if isinstance(callee, ast.Name) else None
            if name in ("MatchResult", "_Rule"):
                arg_index = 1 if name == "MatchResult" else 0
                rule_id_node = node.args[arg_index] if len(node.args) > arg_index else None
                if rule_id_node is None:
                    for kw in node.keywords:
                        if kw.arg == "rule_id":
                            rule_id_node = kw.value
                if rule_id_node is not None:
                    examples.update(self._resolve(rule_id_node))
            self.generic_visit(node)

        def _resolve(self, node: ast.AST) -> set[str]:
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                return {node.value}
            if isinstance(node, ast.JoinedStr):
                return _joined_str_examples(node, category_values=self._current_category_values())
            if isinstance(node, ast.Name):
                if node.id in constants:
                    return set(constants[node.id])
                unresolved.append(f"Name({node.id!r})")
                return set()
            if isinstance(node, ast.Attribute) and node.attr == "rule_id":
                # ``rule.rule_id`` forwarding a bank entry's own id (see the
                # ``for rule in _RULES:`` loop): the literal is already
                # captured by the ``_Rule(...)`` construction scan above, so
                # forwarding it a second time here would be redundant, not
                # additional coverage.
                return set()
            unresolved.append(ast.dump(node))
            return set()

    Visitor().visit(tree)
    assert not unresolved, (
        f"could not statically resolve rule_id argument(s) in {module.__name__}: {unresolved}. "
        "Either make the literal directly readable by ast (no dynamic construction), "
        "or extend this test's resolver so lint coverage can still be verified."
    )
    return examples


def test_operator_rule_ids_are_lint_accepted() -> None:
    """Every rule id matcher.py/engine.py can write is accepted by the lint.

    This is the drift guard: it does not re-list the operator's literals, it
    reads them straight out of the operator's own AST.
    """

    examples = _collect_rule_id_examples(matcher_mod) | _collect_rule_id_examples(engine_mod)

    # Sanity: the scan actually found the shapes we know about, so a broken
    # scan (e.g. after a refactor changes call shapes) fails loudly here
    # instead of silently collecting zero examples and vacuously passing.
    assert "source.challenge_exhausted" in examples
    assert "review.choice_undeclared" in examples
    assert "persona.diagnostic_request" in examples
    assert "decision.request" in examples
    assert "source.question" in examples

    unmatched = sorted(
        example for example in examples if MATCHED_RULE_ID_RE.fullmatch(example) is None
    )
    assert unmatched == [], (
        "MATCHED_RULE_ID_RE rejects rule id(s) the operator can actually write: "
        f"{unmatched}. Extend the whitelist in dp_scenarios/ledger/lint.py additively "
        "(never loosen it to arbitrary text)."
    )


def test_matched_rule_id_regex_still_rejects_free_text() -> None:
    """The drift guard above must not have been satisfied by loosening the regex."""

    for free_text in ("free prose rule", "junk.source.answer.orders", "not_a_real_rule_id", ""):
        assert MATCHED_RULE_ID_RE.fullmatch(free_text) is None, free_text
