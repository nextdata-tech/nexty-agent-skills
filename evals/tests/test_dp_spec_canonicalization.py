"""`nxd-dp-spec-canon-v1` must be stable, semantic, and idempotent.

The canonical hash is what mechanizes "once approved, the spec is frozen for
this build" — previously honour-system prose. That only works if two things
hold at once: reformatting a spec must NOT move the hash (or every re-wrap reads
as tampering), and changing a value MUST move it (or tampering reads as clean).

This file pins both directions against the worked example that ships in the
pack, plus the idempotence law for the canonical emitter.

STABILITY GUARD: the canonicalizer pins `yaml.safe_load` behaviour. A PyYAML
major bump requires re-verifying the golden hash below.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"
WORKED_EXAMPLE = REPO / "src" / "nxd-pocket-loop" / "reference" / "dp-spec.md"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import dp_diagnostics as dpd  # noqa: E402

yaml = pytest.importorskip("yaml")

# The golden hash of the worked example. If this changes, EITHER the
# canonicalizer changed (verify why) OR the worked example changed (coordinate:
# the example is owned by the reference doc, this literal by the tests).
GOLDEN_HASH = "sha256:c9d3c980caf65f457eb341223fcee37d122e7b7805aa224584a307ba5fe99231"


def _worked_example() -> str:
    """The sole fenced block whose info string is exactly ```markdown.

    Keyed on the fence, never on line numbers — the reference doc is edited in
    parallel with this test and line numbers move.
    """
    text = WORKED_EXAMPLE.read_text(encoding="utf-8")
    blocks = re.findall(r"^```markdown\n(.*?)^```", text, re.S | re.M)
    assert len(blocks) == 1, (
        f"expected exactly one ```markdown fence in {WORKED_EXAMPLE.name}, found "
        f"{len(blocks)} — the fixture must be mechanically identifiable, so this "
        "fails loudly rather than silently hashing the first one"
    )
    return blocks[0]


@pytest.fixture(scope="module")
def spec() -> str:
    return _worked_example()


def h(text: str) -> str:
    return dpd.spec_hash(text.encode("utf-8"))


def test_golden_hash(spec):
    assert h(spec) == GOLDEN_HASH


def test_worked_example_validates_clean(tmp_path, spec):
    """A hash of a spec that does not validate would pin the wrong thing."""
    sys.path.insert(0, str(SCRIPTS))
    import validate_dp_spec

    path = tmp_path / "dp-spec.md"
    path.write_text(spec, encoding="utf-8")
    report = validate_dp_spec.validate(path)
    assert report.ok, [d.code for d in report.errors]
    assert report.spec_hash == GOLDEN_HASH


# --- must NOT change the hash ----------------------------------------------

@pytest.mark.parametrize(
    "label,mutate",
    [
        ("crlf line endings", lambda s: s.replace("\n", "\r\n")),
        ("lone CR line endings", lambda s: s.replace("\n", "\r")),
        ("trailing whitespace", lambda s: s.replace("\n", "   \n")),
        ("blank-line runs", lambda s: s.replace("\n\n", "\n\n\n")),
        ("a YAML comment", lambda s: s.replace("## criteria\n", "## criteria\n\n# a note\n", 1)),
        ("0.25 written as 0.250", lambda s: s.replace("weight: 0.25", "weight: 0.250", 1)),
        ("an integral float", lambda s: s.replace("dp_spec_version: 1", "dp_spec_version: 1.0", 1)),
        ("heading case", lambda s: s.replace("## open_questions", "## Open Questions", 1)),
        ("a preamble before the first heading",
         lambda s: s.replace("---\n\n## intent", "---\n\nA drafting note.\n\n## intent", 1)),
        ("NFD instead of NFC", lambda s: __import__("unicodedata").normalize("NFD", s)),
    ],
)
def test_formatting_does_not_move_the_hash(spec, label, mutate):
    assert h(mutate(spec)) == GOLDEN_HASH, f"{label} moved the hash"


def test_mapping_key_order_does_not_move_the_hash(spec):
    reordered = spec.replace(
        "dp_spec_version: 1\nname: candidate_scoring",
        "name: candidate_scoring\ndp_spec_version: 1",
        1,
    )
    assert reordered != spec
    assert h(reordered) == GOLDEN_HASH


def test_rewrapped_block_scalar_does_not_move_the_hash(spec):
    """Re-wrapping a block scalar is not a plan change."""
    needle = "Given an Ashby job, produce a ranked, gated, auditable list of"
    assert needle in spec
    rewrapped = spec.replace(needle, "Given an Ashby job, produce a\nranked, gated, auditable list of", 1)
    assert h(rewrapped) == GOLDEN_HASH


# --- MUST change the hash ---------------------------------------------------

@pytest.mark.parametrize(
    "label,mutate",
    [
        ("a changed weight", lambda s: s.replace("weight: 0.25", "weight: 0.30", 1)),
        ("proposed -> approved", lambda s: s.replace("status: proposed", "status: approved", 1)),
        ("a removed section", lambda s: s.replace("## open_questions", "## removed_questions", 1)),
        ("a renamed model", lambda s: s.replace("scored_candidates", "scored_candidate", 1)),
    ],
)
def test_semantic_edits_move_the_hash(spec, label, mutate):
    mutated = mutate(spec)
    assert mutated != spec, f"the {label} fixture did not actually edit the spec"
    assert h(mutated) != GOLDEN_HASH, f"{label} did NOT move the hash"


def test_reordered_list_moves_the_hash(spec):
    """List order is semantic — criteria order, band precedence, decisions order."""
    obj = dpd.canonical_object(spec.encode("utf-8"))
    criteria = obj["sections"]["criteria"]
    assert isinstance(criteria, list) and len(criteria) > 1
    swapped = dict(obj)
    swapped["sections"] = dict(obj["sections"])
    swapped["sections"]["criteria"] = [criteria[1], criteria[0], *criteria[2:]]
    assert h(dpd.emit(swapped)) != GOLDEN_HASH


def test_changed_anchor_text_moves_the_hash(spec):
    obj = dpd.canonical_object(spec.encode("utf-8"))
    anchors = obj["sections"]["criteria"][0]["anchors"]
    key = sorted(anchors)[0]
    mutated = dpd.canonical_object(spec.encode("utf-8"))
    mutated["sections"]["criteria"][0]["anchors"][key] = "something else entirely"
    assert dpd.canonical_bytes(dpd.emit(mutated).encode("utf-8")) != dpd.canonical_bytes(
        spec.encode("utf-8")
    )


# --- the laws ---------------------------------------------------------------

def test_idempotence_law(spec):
    """canonicalize(emit(canonicalize(x))) == canonicalize(x)."""
    once = dpd.canonical_bytes(spec.encode("utf-8"))
    round_tripped = dpd.canonical_bytes(
        dpd.emit(dpd.canonical_object(spec.encode("utf-8"))).encode("utf-8")
    )
    assert round_tripped == once


def test_emitted_markdown_still_validates(tmp_path, spec):
    """The emitter writes a proposal a human reads — it must stay a valid spec."""
    import validate_dp_spec

    out = tmp_path / "emitted.md"
    out.write_text(dpd.emit(dpd.canonical_object(spec.encode("utf-8"))), encoding="utf-8")
    assert validate_dp_spec.validate(out).ok


def test_prose_with_a_colon_survives_the_round_trip():
    """A line containing ': ' must not silently reparse as a mapping."""
    src = (
        "---\ndp_spec_version: 1\nname: x\nworkflow: x\nstatus: draft\n---\n\n"
        "## intent\n\nNote: this reads like a YAML mapping and is prose.\n"
    )
    obj = dpd.canonical_object(src.encode("utf-8"))
    assert dpd.canonical_bytes(dpd.emit(obj).encode("utf-8")) == dpd.canonical_bytes(
        src.encode("utf-8")
    )


def test_duplicate_key_after_str_coercion_raises():
    """A silent drop would change the hash of a spec whose content did not."""
    src = (
        "---\ndp_spec_version: 1\nname: x\nworkflow: x\nstatus: draft\n---\n\n"
        "## population\n\npopulation:\n  1: a\n  '1': b\n"
    )
    with pytest.raises(dpd.SpecReadError) as exc:
        dpd.canonical_object(src.encode("utf-8"))
    assert "collide" in str(exc.value)


YAML_SET_SPEC = (
    "---\ndp_spec_version: 1\nname: x\nworkflow: x\nstatus: draft\n---\n\n"
    "## population\n\npopulation: !!set\n  ? alpha\n  ? bravo\n  ? charlie\n"
    "  ? delta\n  ? echo\n"
)


def test_yaml_set_canonicalizes_to_a_sorted_list():
    """A `!!set` is unordered, so unlike a list its canonical form IS sorted."""
    obj = dpd.canonical_object(YAML_SET_SPEC.encode("utf-8"))
    assert obj["sections"]["population"]["population"] == [
        "alpha", "bravo", "charlie", "delta", "echo"
    ]


def test_yaml_set_hash_is_stable_across_hash_seeds():
    """Set iteration order is PYTHONHASHSEED-randomized.

    Without a `set` branch in `_normalize`, a `!!set` fell through to
    `str(value)` and the spec hash changed on every interpreter start —
    breaking skip-if-unchanged (an untouched spec looks edited) and
    tamper-evidence (an approved hash stops matching itself). This runs the
    hash in fresh interpreters under different seeds; one distinct value is
    the whole assertion.
    """
    import json as _json
    import subprocess

    prog = (
        "import sys; sys.path.insert(0, %r)\n"
        "import dp_diagnostics as D\n"
        "print(D.spec_hash(%r.encode('utf-8')))\n"
        % (str(SCRIPTS), YAML_SET_SPEC)
    )
    seen = set()
    for seed in ("0", "1", "2", "3", "4"):
        proc = subprocess.run(
            [sys.executable, "-c", prog],
            capture_output=True, text=True, env={"PYTHONHASHSEED": seed, "PATH": "/usr/bin:/bin"},
        )
        assert proc.returncode == 0, proc.stderr
        seen.add(proc.stdout.strip())
    assert len(seen) == 1, f"hash is seed-dependent: {_json.dumps(sorted(seen))}"


def test_non_utf8_is_exit_two_material():
    with pytest.raises(dpd.SpecReadError) as exc:
        dpd.canonical_object(b"---\n\xff\xfe\n---\n")
    assert exc.value.code == "spec.encoding.not_utf8"


def test_hash_is_prefixed_sha256(spec):
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", h(spec))
