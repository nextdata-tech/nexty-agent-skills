"""Incremental transforms must be a GATED second path, never a relaxed default.

The nxd-generate-data-product default ingest lands every model with
`write_disposition="replace"` from run-local dlt state. That pair is the antidote
to the duplicate-rows-on-rerun bug class: a rerun rewrites the table instead of
appending to it, so a green rerun cannot multiply rows.

Incrementality is a genuinely different mechanism and it is easy to get
catastrophically wrong. The failure modes this gate exists to prevent:

1. `"replace"` kept while the transform yields only the delta — the table is
   rewritten to just the delta and every prior row is destroyed, with a green run
   and no error.
2. `"append"` adopted without a durable cursor — every rerun re-lands rows it
   already landed, which is the duplicate-rows bug wearing a new hat.
3. `"append"` applied to a model that is not append-safe (an aggregate, regrain,
   or dedupe) — duplicate declared-grain keys or stale arithmetic.
4. The cursor written by flat indexing on a closure that promises 2+ models —
   the kernel drops those writes SILENTLY, so the cursor never persists.
5. A model dropped from the resource list because its delta is empty, while its
   cursor advances anyway — rows nothing ever wrote are skipped forever.
6. The default table-name assert trusted as proof the write happened. Under
   `"append"` dlt rehydrates its schema from the destination, so a table landed
   by an earlier run is reported whether or not this run wrote to it.

The sanctioned route is `"append"` PLUS a kernel `transform_state` cursor,
addressed through `for_model()`, advanced only AFTER the write and a row-count
verification, while dlt's own pipeline state stays run-local and ephemeral. Two
separate mechanisms, never composed.

A live end-to-end scenario would need a real desktop supervisor, so this
plain-pytest gate pins the shipped guidance itself (no agent, no supervisor). It
asserts:

(a) the reference doc exists and teaches the `transform_state` kwarg;
(b) it states how state and rows actually behave on a failed run, WITHOUT
    claiming the rows roll back — the local DuckDB driver has no transaction;
(c) the WORKED TRANSFORM (parsed as Python, not grepped as prose) lands the data
    before it advances the cursor;
(d) it does NOT tell desktop authors to use `.when(...)` — the local Python
    compute driver discards the per-model execution payloads, so such a DAG
    silently never dispatches;
(e) it does NOT mention `NXD_TRANSFORM_STATE_SIDECAR_PATH`, which is
    Databricks-only and inert on desktop;
(f) the run-local dlt / `"replace"` invariant is STILL present in SKILL.md —
    guarding against a future edit that "fixes" incrementality by deleting the
    invariant it is supposed to coexist with;
(g) SKILL.md points at the new reference from both the transform contract and
    the invariant, so an author hunting incrementality finds the sanctioned
    route instead of improvising past the MUST;
(h) the doc gates on append-SAFETY of the output models, teaches `for_model()`
    over flat indexing, and does not present the table-name assert as proof of
    the write.

Where a rule is about EXECUTABLE shape (ordering, which accessor the copyable
artifact uses), this gate parses the worked transform's AST rather than matching
substrings — prose or a comment mentioning `pipeline.run(...)` must not be able
to satisfy an ordering check.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"

GENERATE_DP = SRC / "nxd-generate-data-product"
SKILL = GENERATE_DP / "SKILL.md"
INCREMENTAL = GENERATE_DP / "reference" / "incremental-transforms.md"
TRANSFORM_TEMPLATE = GENERATE_DP / "reference" / "transform-template.md"
SCENARIO = REPO_ROOT / "evals" / "public" / "incremental-transform-state"

REFERENCE_LINK = "reference/incremental-transforms.md"

# Databricks-only sidecar mechanism. Inert on desktop; naming it in desktop
# guidance would ship a correctness lie.
SIDECAR_ENV_VAR = "NXD_TRANSFORM_STATE_SIDECAR_PATH"

# The produce-verification marker the desktop supervisor's readiness gate polls for.
MARKER_FILENAME = ".transform-complete"

_FENCE = re.compile(r"```python\n(.*?)```", re.DOTALL)


def _strip_markdown(text: str) -> str:
    """Drop emphasis/code markers so a reintroduction that keeps the markdown
    (``**.when(**...)``) still matches the plain phrase."""
    return re.sub(r"[*`_]", "", text).lower()


def _squash(text: str) -> str:
    """Collapse whitespace so a line-wrapped phrase still matches."""
    return re.sub(r"\s+", " ", text)


def _first_index(haystack: str, needle: str) -> int:
    idx = haystack.find(needle)
    assert idx != -1, f"expected to find {needle!r} in the incremental guidance"
    return idx


def _worked_transform_source() -> str:
    """The copyable worked transform: the python fence under the final heading.

    This is the artifact an author actually pastes, so the executable-shape
    checks below run against it rather than against the whole document.
    """
    text = INCREMENTAL.read_text()
    worked = text[_first_index(text, "## Worked transform") :]
    blocks = _FENCE.findall(worked)
    assert blocks, "the worked-transform section must carry a python fence"
    return blocks[0]


def _ingest_function(tree: ast.Module) -> ast.FunctionDef:
    fns = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and any(
            isinstance(d, ast.Call)
            and isinstance(d.func, ast.Attribute)
            and d.func.attr == "on_transform"
            for d in node.decorator_list
        )
    ]
    assert len(fns) == 1, (
        "the worked transform must define exactly one @data_product.on_transform() "
        f"entrypoint, found {len(fns)}"
    )
    return fns[0]


# --- (a) the doc exists and teaches the kwarg -------------------------------


def test_reference_doc_exists_with_contents_heading():
    assert INCREMENTAL.is_file(), (
        "reference/incremental-transforms.md must exist — it is the only "
        "sanctioned incremental route"
    )
    head = "\n".join(INCREMENTAL.read_text().splitlines()[:20]).lower()
    assert "## contents" in head, (
        "reference files over 100 lines need a '## Contents' section near the top"
    )


def test_scenario_uses_the_current_skill_and_three_run_runner_oracle():
    config = json.loads((SCENARIO / "checks.json").read_text())
    assert config["skills"] == ["nxd-generate-data-product"]
    assert config["ci_skip"]
    assert len(config["turns"]) == 1
    assert config["turns"][0]["text"].startswith("The source export has just gained")
    assert config["workspace_files"] == ["data_product/transform/main.py"]
    assert config["deterministic_check"]["script"] == "check_incremental_state.py"
    assert config["deterministic_check"]["deps"] == [
        "dlt[duckdb]==1.28.2",
        "duckdb==1.5.4",
    ]
    checker = SCENARIO / "fixtures" / "check_incremental_state.py"
    assert "three times" in checker.read_text()
    assert (SCENARIO / "fixtures" / "delta" / "part-0003.csv").is_file()


def test_incremental_oracle_material_is_excluded_only_for_this_scenario(tmp_path):
    spec = importlib.util.spec_from_file_location("evals_run", REPO_ROOT / "evals" / "run.py")
    run = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.path.insert(0, str(REPO_ROOT / "evals"))
    sys.modules["evals_run"] = run
    try:
        spec.loader.exec_module(run)
    finally:
        sys.path.pop(0)
        sys.modules.pop("evals_run", None)

    assert run.SCENARIO_WORKSPACE_FIXTURE_EXCLUSIONS[SCENARIO.name] == frozenset({
        "check_incremental_state.py",
        "delta",
    })
    workspace = tmp_path / "workspace"
    target = workspace / "data_product" / "data" / "events" / "part-0003.csv"
    run._stage_incremental_delta_before_followup(SCENARIO, workspace, 1)
    assert not target.exists()
    run._stage_incremental_delta_before_followup(SCENARIO, workspace, 2)
    assert target.read_text() == (
        SCENARIO / "fixtures" / "delta" / "part-0003.csv"
    ).read_text()
    run._remove_incremental_delta_after_agent(SCENARIO, workspace)
    assert not target.exists()


def test_incremental_oracle_requires_one_cursor_key_to_follow_the_trajectory():
    checker_path = SCENARIO / "fixtures" / "check_incremental_state.py"
    spec = importlib.util.spec_from_file_location("incremental_checker", checker_path)
    checker = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["incremental_checker"] = checker
    try:
        spec.loader.exec_module(checker)
    finally:
        sys.modules.pop("incremental_checker", None)
    states = [
        {"events": {"max_event_id": 100}},
        {"events": {"max_event_id": 100}},
        {"events": {"max_event_id": 140}},
    ]
    assert checker._has_cursor_trajectory(*states)
    assert not checker._has_cursor_trajectory(
        states[0], states[1], {"events": {"max_event_id": 100}}
    )
    string_states = [
        {"events": {"max_event_id": "100"}},
        {"events": {"max_event_id": "100"}},
        {"events": {"max_event_id": "140"}},
    ]
    assert checker._has_cursor_trajectory(*string_states)


def test_teaches_the_transform_state_kwarg():
    text = INCREMENTAL.read_text()
    assert "transform_state" in text, "the doc must name the transform_state kwarg"
    # The multi-model accessors, and the first-run empty-bag rule, are the parts
    # an author most easily gets wrong.
    for token in ("for_model(", "generic()"):
        assert token in text, f"the doc must teach the {token} accessor"
    lowered = text.lower()
    assert "first run" in lowered, (
        "the doc must state that the bag is empty on the first run"
    )
    assert "json" in lowered, (
        "the doc must state the JSON-serializable-values-only constraint"
    )


# --- (b) what a failed run really does -------------------------------------


def test_states_failed_run_does_not_persist_state():
    text = _squash(_strip_markdown(INCREMENTAL.read_text()))
    # The cursor half: state is folded only when the run succeeded.
    assert "persists no state" in text or "persists nothing" in text, (
        "the doc must state that a FAILED run persists no transform_state — "
        "that is what stops a cursor advancing over a run that blew up"
    )


def test_does_not_claim_rows_roll_back_on_desktop():
    """The local DuckDB driver implements no transaction protocol.

    dlt's writes are permanent the moment ``pipeline.run(...)`` returns, while
    the state bag is only committed on success. Telling an author the two share
    fate invites 'the assert will roll it back', which is false and produces
    duplicate rows on the next run.
    """
    text = _squash(_strip_markdown(INCREMENTAL.read_text()))
    for claim in (
        "commits neither the rows nor the bag",
        "commits neither the rows nor the cursor",
        "there is no torn state",
    ):
        assert claim not in text, (
            f"the doc must not claim {claim!r} — on desktop the local DuckDB "
            "driver has no transaction, so rows written by pipeline.run(...) "
            "are permanent while the cursor is not. Rows and cursor do NOT "
            "share fate; say so instead."
        )
    # And it must state the real behavior positively, so an author designs for it.
    assert "no transaction" in text, (
        "the doc must state that the local DuckDB driver has no transaction, so "
        "an author knows a raise does not undo the rows"
    )
    assert "before" in text and "validate" in text, (
        "the doc must tell the author to validate BEFORE the write, which is the "
        "only check that costs nothing when it fails"
    )


# --- (c) write BEFORE cursor advance (checked on the AST) ------------------


def test_states_the_write_then_advance_rule_in_prose():
    lowered = _strip_markdown(INCREMENTAL.read_text())
    assert "after the write" in lowered or "write first" in lowered, (
        "the doc must state that the cursor advances only AFTER the data write"
    )
    # The counter-example must survive too: showing the wrong order side by side
    # is what makes the rule stick.
    assert "wrong" in lowered, (
        "the doc should contrast the correct ordering with the wrong ordering"
    )


def test_worked_transform_lands_data_before_advancing_cursor():
    """Checked on the PARSED worked transform, not on document text.

    A substring scan can be satisfied by prose or a comment naming
    ``pipeline.run(...)`` ahead of a code block that actually advances the
    cursor first. Walking the AST of the copyable artifact cannot be.
    """
    tree = ast.parse(_worked_transform_source(), "incremental-transforms.md:worked")
    fn = _ingest_function(tree)

    run_lines = [
        node.lineno
        for node in ast.walk(fn)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "run"
    ]
    assert run_lines, "the worked transform must call pipeline.run(...)"

    # A cursor advance is a subscript assignment into the STATE BAG — either the
    # injected kwarg itself or a handle bound from it via for_model()/generic().
    # Scope to those names so an ordinary dict write in the reader loop
    # (`row["event_id"] = ...`) is not mistaken for a cursor advance.
    bag_names = {"transform_state"} | {
        node.targets[0].id
        for node in ast.walk(fn)
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Attribute)
        and node.value.func.attr in {"for_model", "generic"}
    }
    advance_lines = [
        node.lineno
        for node in ast.walk(fn)
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Subscript)
        and isinstance(target.value, ast.Name)
        and target.value.id in bag_names
    ]
    assert advance_lines, (
        "the worked transform must advance a cursor by assigning into the state "
        f"bag (looked for subscript writes to {sorted(bag_names)})"
    )

    assert max(run_lines) < min(advance_lines), (
        "the worked transform must land the data BEFORE advancing the cursor — "
        "advancing first can commit a cursor past rows that never landed"
    )

    # The cursor advance must come after EVERY fallible operation, not merely
    # after pipeline.run(). Two more steps sit between the write and the return:
    # the row-count verification, and the produce-verification marker touch.
    # Both can raise, so both must precede the advance — otherwise a failure
    # leaves a cursor committed past a run that never completed.
    # The row-count read appears TWICE: once before the write (prior_count) and
    # once after (landed). Only the POST-write call verifies what this run landed,
    # so scope to calls after pipeline.run(...) — otherwise deleting the real
    # verification still satisfies the assertion via the pre-write read.
    last_write = max(run_lines)
    row_count_lines = [
        node.lineno
        for node in ast.walk(fn)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_table_row_count"
    ]
    post_write_verify = [line for line in row_count_lines if line > last_write]
    assert post_write_verify, (
        "the worked transform must verify the write by row count AFTER "
        "pipeline.run(...) — the table-name assert cannot detect a model that "
        "was silently not written, because dlt rehydrates its schema from the "
        "destination. A pre-write prior_count read does not satisfy this."
    )

    # Match the marker by NAME, not merely any .touch() call — the supervisor's
    # readiness gate waits for this exact filename, so touching some other path
    # is a silent wedge (the run never reports ready) that a bare attr match misses.
    touch_lines = [
        node.lineno
        for node in ast.walk(fn)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "touch"
        and any(
            isinstance(sub, ast.Constant)
            and isinstance(sub.value, str)
            and sub.value == MARKER_FILENAME
            for sub in ast.walk(node.func.value)
        )
    ]
    assert touch_lines, (
        f"the worked transform must touch the {MARKER_FILENAME} marker the "
        "supervisor's readiness gate waits for — touching any other path leaves "
        "the run silently un-ready"
    )

    # Pin the full chain pairwise, not merely "everything precedes the advance".
    # write -> post-write row-count verify -> marker touch -> cursor advance.
    assert last_write < min(post_write_verify), (
        "the row-count verification must run AFTER the data is landed"
    )
    assert max(post_write_verify) < min(touch_lines), (
        "the .transform-complete readiness marker must be touched only AFTER "
        "the write is verified — signalling readiness before verification tells "
        "the supervisor a run succeeded that may have landed nothing"
    )
    assert max(touch_lines) < min(advance_lines), (
        "the .transform-complete marker touch is fallible I/O and must run "
        "BEFORE the cursor advance — the doc's own rule is that nothing between "
        "the advance and the return may decide not to write"
    )


def test_worked_transform_uses_for_model_not_flat_indexing():
    """The copyable artifact must model the accessor that cannot fail silently.

    Flat indexing binds only while the closure declares exactly ONE model. The
    Step 3 contract makes PHYSICAL_MODELS = BASE + DERIVED, so adding a single
    derived model unbinds the handle — and the kernel then drops every flat
    write with no exception, no warning, and a green run.
    """
    source = _worked_transform_source()
    tree = ast.parse(source, "incremental-transforms.md:worked")
    fn = _ingest_function(tree)

    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "for_model"
        for node in ast.walk(fn)
    ), (
        "the worked transform must address the bag through for_model(...) — it is "
        "the copyable artifact, and flat indexing is dropped SILENTLY as soon as "
        "the closure promises a second model"
    )

    # And it must not demonstrate flat indexing ON the injected kwarg itself.
    flat = [
        node
        for node in ast.walk(fn)
        for target in (node.targets if isinstance(node, ast.Assign) else [])
        if isinstance(target, ast.Subscript)
        and isinstance(target.value, ast.Name)
        and target.value.id == "transform_state"
    ]
    assert not flat, (
        "the worked transform must not assign into transform_state[...] directly; "
        "that is the silent-drop shape. Use for_model('<name>')[...] instead"
    )


def test_worked_transform_is_valid_python():
    ast.parse(_worked_transform_source(), "incremental-transforms.md:worked")


def test_warns_against_replace_with_a_delta():
    """`"replace"` + delta destroys history on a green run — the worst outcome."""
    text = _strip_markdown(INCREMENTAL.read_text())
    assert "delta" in text, "the doc must discuss yielding only the delta"
    assert "append" in text, (
        "the doc must name write_disposition='append' as the incremental disposition"
    )
    # The specific hazard must be called out, not left inferable.
    assert "shrink" in text or "destroy" in text, (
        "the doc must state that 'replace' while yielding only a delta shrinks / "
        "destroys the table"
    )


# --- (d) + (e) desktop DO-NOTs ---------------------------------------------


def test_does_not_recommend_when_dag_on_desktop():
    text = _strip_markdown(INCREMENTAL.read_text())
    # `.when(` may appear ONLY inside an explicit prohibition. Require the
    # do-not framing at EVERY occurrence, not merely somewhere in the file:
    # a single surviving prohibition must not license a later recommendation.
    occurrences = text.count(".when(")
    if occurrences:
        prohibitions = _squash(text).count("do not use .when(")
        assert prohibitions >= 1, (
            "the doc may mention .when(...) only to forbid it on desktop — the "
            "local Python compute driver discards the per-model payloads"
        )
        # Every mention must sit in a sentence that also forbids it. Split on
        # sentence boundaries and check each fragment that names the accessor.
        for fragment in re.split(r"(?<=[.!?])\s+", _squash(text)):
            if ".when(" in fragment:
                assert (
                    "do not" in fragment
                    or "never" in fragment
                    or "cannot" in fragment
                    or "discard" in fragment
                ), (
                    "every .when(...) mention must sit in a prohibition — this "
                    f"one does not: {fragment[:160]!r}"
                )
    assert "discard" in text, (
        "the doc must explain WHY .when(...) is unusable on desktop (the local "
        "driver discards the execution payloads), not just assert it"
    )


@pytest.mark.parametrize(
    "doc",
    [SKILL, TRANSFORM_TEMPLATE],
    ids=lambda p: p.parent.name + "/" + p.name,
)
def test_no_databricks_only_sidecar_env_var(doc):
    """The sidecar must never appear as guidance in the default-path docs."""
    assert SIDECAR_ENV_VAR not in doc.read_text(), (
        f"{doc} must not reference {SIDECAR_ENV_VAR} — it is Databricks-only and "
        "does nothing on desktop"
    )


def test_incremental_doc_mentions_sidecar_only_to_forbid_it():
    """The incremental doc is the one place the name may appear — as a DO-NOT.

    Naming it in a prohibition is what stops an author who has seen it on the
    Databricks path from reaching for it here. Every occurrence must be inside a
    prohibition, so a later recommendation cannot ride along on an earlier one.
    """
    text = INCREMENTAL.read_text()
    if SIDECAR_ENV_VAR in text:
        # Collapse whitespace so a line-wrapped prohibition still matches. Run
        # the needle through the same normalizer as the haystack — it strips
        # underscores, which the env var is full of.
        lowered = _squash(_strip_markdown(text))
        needle = _strip_markdown(SIDECAR_ENV_VAR)
        assert f"do not reference {needle}" in lowered, (
            f"{SIDECAR_ENV_VAR} may appear only inside an explicit prohibition"
        )
        assert "databricks-only" in lowered, (
            "the prohibition must say the sidecar is Databricks-only"
        )
        for fragment in re.split(r"(?<=[.!?])\s+", lowered):
            if needle in fragment:
                assert "do not" in fragment or "databricks-only" in fragment, (
                    "every sidecar mention must sit in a prohibition — this one "
                    f"does not: {fragment[:160]!r}"
                )


def test_no_cron_framing_on_desktop():
    """desktop has no scheduler; runs happen because the user asks.

    Scheduler phrasing is banned as GUIDANCE. The incremental doc is allowed to
    quote it inside its own do-not, so strip the prohibition sentence first.
    """
    text = _squash(_strip_markdown(INCREMENTAL.read_text()))
    # Drop the clause that quotes the banned phrasing in order to forbid it,
    # so the ban below tests guidance rather than the prohibition itself.
    text = re.sub(r"do not write guidance.*?framing is", "", text)
    for phrase in ("each scheduled run", "every scheduled run", "nightly run"):
        assert phrase not in text, (
            f"{phrase!r} implies a scheduler desktop does not have — the correct "
            "framing is 'the next run'"
        )
    # The doc must positively state the no-cron fact, not merely avoid the words.
    assert "no cron" in text, (
        "the doc must state outright that desktop has no cron"
    )


# --- (f) the idempotency invariant survives --------------------------------


def test_replace_and_run_local_invariant_still_in_skill():
    """A future edit must not 'fix' incrementality by deleting the invariant."""
    text = SKILL.read_text()
    # The invariant bullet itself.
    assert 'write_disposition="replace"' in text, (
        "SKILL.md must still mandate write_disposition='replace' as the default — "
        "it is the antidote to duplicate-rows-on-rerun"
    )
    assert "DLT_DATA_DIR" in text and "pipelines_dir" in text, (
        "SKILL.md must still mandate run-local dlt state (pipelines_dir under the "
        "run dir + DLT_DATA_DIR)"
    )
    assert "~/.dlt" in text, (
        "SKILL.md must still forbid the shared ~/.dlt state directory"
    )
    assert ".transform-complete" in text, (
        "SKILL.md must still mandate the .transform-complete touch"
    )


def test_default_template_still_lands_with_replace():
    """The DEFAULT path artifact must not drift to append.

    The invariant lives in the template an author copies, not only in prose.
    """
    text = TRANSFORM_TEMPLATE.read_text()
    assert 'write_disposition="replace"' in text, (
        "the default transform template must still land with "
        "write_disposition='replace' — incrementality is a separate, gated path"
    )
    assert 'write_disposition="append"' not in text, (
        "the DEFAULT transform template must never land with 'append'; that "
        "belongs only in reference/incremental-transforms.md, paired with a cursor"
    )


def test_incremental_does_not_relax_run_local_dlt_state():
    """dlt state stays ephemeral; only the kernel bag is durable."""
    text = _strip_markdown(INCREMENTAL.read_text())
    assert "run-local" in text, (
        "the incremental doc must restate that dlt state stays run-local"
    )
    # The two-mechanisms framing is the load-bearing idea: composing them is the
    # silent-corruption path.
    assert "never composed" in text or "two separate" in text, (
        "the doc must state that dlt pipeline state and transform_state are two "
        "separate mechanisms, not layers of one"
    )
    assert "~/.dlt" in text, (
        "the incremental doc must still forbid ~/.dlt, so an author reading only "
        "this doc does not relax the invariant"
    )


# --- (g) SKILL.md points at the reference ----------------------------------


def test_skill_points_at_the_incremental_reference():
    text = SKILL.read_text()
    assert REFERENCE_LINK in text, (
        f"SKILL.md must link {REFERENCE_LINK} so an author hunting incrementality "
        "finds the sanctioned route"
    )
    # Two entry points: the Step 3 transform contract and the Invariants list.
    # An author who only reads the invariants must still be routed correctly.
    assert text.count(REFERENCE_LINK) >= 2, (
        "SKILL.md must point at the incremental reference from BOTH the transform "
        "contract and the run-local/replace invariant bullet"
    )


def test_invariant_bullet_itself_routes_to_the_gated_path():
    """The MUST and its sanctioned exception must live in the same bullet."""
    invariant_lines = [
        line
        for line in SKILL.read_text().splitlines()
        if "Run-local dlt state" in line
    ]
    assert invariant_lines, "the run-local dlt state invariant bullet must exist"
    bullet = invariant_lines[0]
    assert REFERENCE_LINK in bullet, (
        "the run-local/replace invariant bullet must itself point at "
        f"{REFERENCE_LINK} — an author hunting incrementality reads the MUST "
        "first and must be routed rather than left to improvise past it"
    )


def test_invariant_bullet_carries_the_silent_failure_modes():
    """Routing is not enough: the bullet must name what fails silently.

    An author who reads only the invariants list and skips the reference should
    still know that append-safety is a property of the OUTPUT models and that
    flat indexing drops the cursor.
    """
    bullet = next(
        line
        for line in SKILL.read_text().splitlines()
        if "Run-local dlt state" in line
    ).lower()
    assert "append-safe" in bullet, (
        "the invariant bullet must gate incrementality on the promised models "
        "being append-safe, not merely on the source being append-only"
    )
    assert "for_model" in bullet, (
        "the invariant bullet must name for_model() — flat indexing silently "
        "drops the cursor once a closure promises a second model"
    )


# --- (h) the newly load-bearing rules --------------------------------------


def test_gates_on_output_models_being_append_safe():
    """Append-safety is a property of the OUTPUT models, not just the source."""
    text = _squash(_strip_markdown(INCREMENTAL.read_text()))
    assert "append-safe" in text, (
        "the doc must introduce append-safety as an explicit gate on the "
        "promised models"
    )
    # The three shapes that are never append-safe must be named, or an author
    # will append to a rollup and duplicate the declared grain.
    for shape in ("aggregate", "regrain", "dedupe"):
        assert shape in text, (
            f"the doc must name {shape!r} as a model shape that is NOT "
            "append-safe — appending to one duplicates the declared grain or "
            "leaves stale arithmetic"
        )
    assert "replace" in text, (
        "the doc must offer rebuilding the non-append-safe models with "
        "'replace' as the resolution, rather than leaving the author stuck"
    )


def test_warns_flat_indexing_fails_silently():
    raw = INCREMENTAL.read_text()
    text = _squash(_strip_markdown(raw))
    assert "silent" in text, (
        "the doc must state that the flat-indexing failure is SILENT — no "
        "exception, no warning, a green run that persists nothing. An author who "
        "expects a crash will not go looking"
    )
    # Checked on the RAW text: _strip_markdown drops underscores, which this
    # identifier is full of.
    assert "for_model(" in raw, "the doc must prescribe for_model() as the fix"


def test_does_not_present_table_name_assert_as_proof_of_the_write():
    """Under append the table-name assert cannot see a missing write.

    dlt rehydrates its schema from the destination, so a table landed by an
    earlier run is reported whether or not this run wrote a row to it. The doc
    must say so and prescribe a check that CAN detect it.
    """
    text = _squash(_strip_markdown(INCREMENTAL.read_text()))
    assert "rehydrat" in text, (
        "the doc must explain that dlt rehydrates its schema from the "
        "destination — that is WHY the table-name assert cannot detect a "
        "missing write under 'append'"
    )
    assert "row count" in text or "count(*)" in text or "count rows" in text, (
        "the doc must prescribe a row-count verification, which is the check "
        "that can actually detect a model that was not written"
    )


def test_worked_transform_verifies_by_row_count():
    """The copyable artifact must carry the verification that actually works."""
    source = _worked_transform_source()
    assert "count(*)" in source.lower(), (
        "the worked transform must read back a row count — the table-name "
        "assert alone cannot detect a model that was not written under 'append'"
    )


def test_requires_every_promised_model_in_every_run():
    """Skipping an empty-delta model advances a cursor over rows nothing wrote."""
    text = _squash(_strip_markdown(INCREMENTAL.read_text()))
    assert "every promised model" in text or "every run yields every" in text, (
        "the doc must require that every promised model goes into the resource "
        "list every run, even with an empty delta — dropping one lets its cursor "
        "advance over rows no pipeline.run(...) ever saw"
    )


def test_teaches_the_module_shadowing_trap_for_readback():
    """The port param is named `duckdb` and shadows the `duckdb` module.

    A bare ``duckdb.connect(...)`` inside the transform resolves against the
    DuckDbOutput dataclass and raises AttributeError, and the first run raises
    IOException (not CatalogException) because the DB FILE does not exist yet.
    Both are guaranteed first-run crashes for an author following the recipe.
    """
    text = _squash(_strip_markdown(INCREMENTAL.read_text()))
    assert "shadow" in text, (
        "the doc must name the shadowing collision: the mandatory `duckdb` port "
        "param shadows the `duckdb` module inside the transform body"
    )
    assert "import duckdb as" in text, (
        "the doc must give the resolution — aliasing the module at import time "
        "(e.g. `import duckdb as duckdb_lib`)"
    )
    assert "ioexception" in text, (
        "the doc must state that a first-run read_only connect raises "
        "IOException (the DB file does not exist yet), not CatalogException — "
        "guarding only CatalogException leaves the first run crashing"
    )


def test_worked_transform_aliases_the_duckdb_module():
    """The copyable artifact must not reintroduce the shadowing crash."""
    source = _worked_transform_source()
    tree = ast.parse(source, "incremental-transforms.md:worked")

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "duckdb":
                    assert alias.asname, (
                        "the worked transform must import duckdb under an ALIAS "
                        "(`import duckdb as duckdb_lib`) — the port parameter is "
                        "named `duckdb` and shadows the bare module name"
                    )

    fn = _ingest_function(tree)
    args = [a.arg for a in fn.args.args]
    assert "duckdb" in args, (
        "the worked transform's port parameter must stay named `duckdb` — the "
        "local DuckDB driver requires exactly that name"
    )
