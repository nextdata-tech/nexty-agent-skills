#!/usr/bin/env python3
"""Rewrite literal `for` loops into their unrolled equivalent before analysis.

The labeled-root checkers decide things like "the filesystem bucket_url is
derived from the pinned execution root, for EACH label" by static name
propagation: an assignment whose value mentions a known root name makes its
target a root name too. That reasoning only ever followed `ast.Assign` and
`ast.AnnAssign`, so a closure that binds its roots in a `for` target dropped
out of the analysis entirely:

    for source_root, model in ((orders_root, "orders"), (users_root, "users")):
        filesystem(bucket_url=str(source_root / model), file_glob="*.csv")

`source_root` never becomes a root name and `model` never resolves to a label,
so `transform-uses-pinned-root` fails a closure that is correct — and, being
DRY, arguably the better of the two spellings. That is what happened in CI on
`multi-source-labeled-roots`, whose baseline PASS was recorded against an agent
that happened to write the same thing unrolled.

The fix could have been loop-awareness in each of the six places that consume
those name sets. Instead this normalizes the INPUT: a loop over a literal
sequence is expanded into the statements it is shorthand for, which is exactly
the shape those checks already handle correctly. One transformation, and every
downstream check inherits it.

Scope, deliberately narrow — this is a checker aid, not an interpreter:

* only literal `tuple`/`list` iterables, including one hop through a name bound
  to such a literal (`PAIRS = (...)` then `for a, b in PAIRS:`);
* `zip()` of literal sequences, and `enumerate()` of one, since both are common
  ways to write the same pairing;
* loops carrying `break`/`continue` are left ALONE. Unrolling them would assert
  that every iteration's body runs, which is the one thing those statements
  deny, and a checker that reports on code the runtime may skip is worse than
  one that declines to look.

Anything else is left untouched, so an unanalyzable loop fails exactly as it
does today rather than silently passing. Expansion is existence-preserving for
the `any(...)`-style checks these checkers run: duplicating a statement cannot
turn a false into a true that the unrolled spelling would not also produce.
"""

from __future__ import annotations

import ast

__all__ = ["unroll_literal_loops"]

# A loop over a long literal would duplicate its body once per element. The real
# closures pair two labeled roots; this only exists so a pathological input
# cannot blow up the checker's memory.
MAX_UNROLLED_STATEMENTS = 512


def _literal_elements(node: ast.AST, bindings: dict[str, ast.AST]) -> list[ast.AST] | None:
    """The elements of a literal sequence, or None if this is not one.

    Follows a single hop through `bindings` so a named constant reads the same
    as the inline literal; deliberately not a fixpoint, because chasing
    rebindings starts to require knowing which assignment ran last.
    """
    if isinstance(node, ast.Name) and node.id in bindings:
        node = bindings[node.id]
    if isinstance(node, (ast.Tuple, ast.List)):
        return list(node.elts)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        if node.func.id == "zip" and node.args and not node.keywords:
            columns = [_literal_elements(arg, bindings) for arg in node.args]
            if any(column is None for column in columns):
                return None
            # zip stops at the shortest, same as the runtime.
            return [ast.Tuple(elts=list(row), ctx=ast.Load())
                    for row in zip(*columns)]
        if node.func.id == "enumerate" and len(node.args) == 1 and not node.keywords:
            elements = _literal_elements(node.args[0], bindings)
            if elements is None:
                return None
            return [ast.Tuple(elts=[ast.Constant(value=index), element],
                              ctx=ast.Load())
                    for index, element in enumerate(elements)]
    return None


def _bind(target: ast.AST, value: ast.AST) -> list[ast.stmt]:
    """Assignments binding `target` to `value` for one iteration.

    A tuple target over a tuple element is destructured element-wise, which is
    the case that matters: it is what turns `for root, label in ((r, "orders"),)`
    into `root = r` and `label = "orders"`, so the label becomes a constant the
    checks can see. Anything else is bound whole and left to the normal
    propagation rules.
    """
    if (isinstance(target, ast.Tuple) and isinstance(value, (ast.Tuple, ast.List))
            and len(target.elts) == len(value.elts)
            and not any(isinstance(element, ast.Starred) for element in target.elts)):
        bound: list[ast.stmt] = []
        for sub_target, sub_value in zip(target.elts, value.elts):
            bound.extend(_bind(sub_target, sub_value))
        return bound
    return [ast.Assign(targets=[target], value=value)]


class _Substitute(ast.NodeTransformer):
    """Replace reads of loop-bound names with the value bound this iteration."""

    def __init__(self, values: dict[str, ast.AST]) -> None:
        self.values = values

    def visit_Name(self, node: ast.Name) -> ast.AST:
        if isinstance(node.ctx, ast.Load) and node.id in self.values:
            return ast.copy_location(_reparse(self.values[node.id]), node)
        return node


def _reparse(node: ast.AST) -> ast.AST:
    return ast.parse(ast.unparse(node), mode="eval").body


def _rebound_in(body: list[ast.stmt]) -> set[str]:
    """Names the body assigns to, which must not be substituted underneath it."""
    rebound: set[str] = set()
    for statement in body:
        for node in ast.walk(statement):
            if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
                rebound.add(node.id)
    return rebound


def _pure_bindings(bound: list[ast.stmt], body: list[ast.stmt]) -> dict[str, ast.AST]:
    """The iteration's bindings that are safe to inline into the body.

    Only constants and plain names: substituting those cannot duplicate a side
    effect, and they are what the label/root checks need to SEE. Without this
    the unrolled body still reads `bucket_url=str(source_root / model)`, where
    `model` is a name -- and a check looking for the label "orders" in that
    expression finds nothing, which is the second half of the same false
    negative.
    """
    rebound = _rebound_in(body)
    values: dict[str, ast.AST] = {}
    for statement in bound:
        if (isinstance(statement, ast.Assign) and len(statement.targets) == 1
                and isinstance(statement.targets[0], ast.Name)
                and isinstance(statement.value, (ast.Constant, ast.Name))
                and statement.targets[0].id not in rebound):
            values[statement.targets[0].id] = statement.value
    return values


# Constructs that own any `break`/`continue` beneath them, so the loop being
# considered here is not the one they belong to.
_OWN_FLOW_CONTROL = (ast.For, ast.AsyncFor, ast.While,
                     ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)


def _carries_flow_control(body: list[ast.stmt]) -> bool:
    """True if `break`/`continue` belong to THIS loop rather than a nested one.

    `ast.walk` cannot express this: it flattens the tree, so there is no way to
    stop descending into a nested loop that owns its own control flow. This
    recurses explicitly and prunes those subtrees instead.
    """
    def scan(node: ast.AST) -> bool:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.Break, ast.Continue)):
                return True
            if isinstance(child, _OWN_FLOW_CONTROL):
                continue
            if scan(child):
                return True
        return False

    return any(isinstance(statement, (ast.Break, ast.Continue))
               or (not isinstance(statement, _OWN_FLOW_CONTROL) and scan(statement))
               for statement in body)


class _Unroller(ast.NodeTransformer):
    def __init__(self) -> None:
        self.bindings: dict[str, ast.AST] = {}
        self.emitted = 0

    def visit_Module(self, node: ast.Module) -> ast.Module:
        self._collect_bindings(node)
        return self.generic_visit(node)

    def _collect_bindings(self, tree: ast.AST) -> None:
        for child in ast.walk(tree):
            if isinstance(child, ast.Assign) and len(child.targets) == 1:
                target = child.targets[0]
                if isinstance(target, ast.Name) and isinstance(child.value, (ast.Tuple, ast.List)):
                    self.bindings[target.id] = child.value

    def visit_For(self, node: ast.For) -> ast.AST | list[ast.stmt]:
        # Depth first, so a nested literal loop is expanded inside the body that
        # is about to be duplicated.
        node = self.generic_visit(node)  # type: ignore[assignment]
        if node.orelse or _carries_flow_control(node.body):
            return node
        elements = _literal_elements(node.iter, self.bindings)
        if not elements:
            return node
        if self.emitted + len(elements) * len(node.body) > MAX_UNROLLED_STATEMENTS:
            return node

        unrolled: list[ast.stmt] = []
        for element in elements:
            bound = _bind(node.target, element)
            # Each iteration gets its own copy: the checks walk the tree and
            # sharing nodes across iterations would make one iteration's
            # rewrite visible in the others.
            body = _deep_copy_body(node.body)
            values = _pure_bindings(bound, body)
            if values:
                body = [_Substitute(values).visit(statement) for statement in body]
            # The assignments are kept as well as inlined: name-based
            # propagation reaches the roots through them, and the substituted
            # copies are what the label matching reads.
            unrolled.extend(bound)
            unrolled.extend(body)
        self.emitted += len(unrolled)
        return unrolled


def _deep_copy_body(body: list[ast.stmt]) -> list[ast.stmt]:
    # ast has no public deep-copy; re-parsing the unparsed body is exact enough
    # for analysis and avoids hand-rolling a copier over every node type.
    #
    # The locations must be filled in FIRST. A nested loop has already been
    # expanded by the time the outer one is copied, so this body can contain
    # synthesized nodes, and `ast.unparse` reads `lineno` off them.
    module = ast.Module(body=body, type_ignores=[])
    ast.fix_missing_locations(module)
    return ast.parse(ast.unparse(module)).body


def unroll_literal_loops(tree: ast.Module) -> ast.Module:
    """Return `tree` with literal `for` loops expanded. Never raises.

    Falls back to the original tree if expansion fails for any reason: this
    exists to stop correct closures being failed for their loop spelling, and a
    checker that crashes on an odd input is a worse outcome than one that
    reports what it can see.
    """
    try:
        unrolled = _Unroller().visit(tree)
        ast.fix_missing_locations(unrolled)
        # Prove the result is still analyzable before handing it on.
        ast.unparse(unrolled)
        return unrolled
    except (SyntaxError, ValueError, RecursionError, AttributeError, TypeError):
        return tree
