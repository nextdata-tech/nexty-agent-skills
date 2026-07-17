"""The scoring adapter is a faithful pass-through of the cross-DP score.py core.

These tests pin that ``nxd_eval.scoring`` re-exports score.py's deterministic-EX
functions (no local re-implementation) and that the imported guard behaves as
score.py specifies — in particular the name-aware multi-measure downgrade and
the order-blind / numeric-tolerant row-set signature.
"""

from __future__ import annotations

from nxd_eval import scoring


def test_reexports_score_py_public_surface():
    for name in (
        "score_one",
        "rows_equal_name_aware",
        "_norm_rowset",
        "matches_compiler",
        "fanout_of",
        "distinct_results",
    ):
        assert hasattr(scoring, name), f"adapter missing {name}"
        assert callable(getattr(scoring, name))


def test_score_one_pass_and_swap_fail():
    gold = [{"region": "x", "revenue": 5.0, "cost": 95.0}]
    swap = [{"region": "x", "revenue": 95.0, "cost": 5.0}]
    rec = {"question_id": "g", "rows": gold, "equality_mode": "set"}
    assert scoring.score_one({"rows": gold}, rec) == "PASS"
    # Two numeric measures swapped: the name-aware guard downgrades PASS -> FAIL.
    assert scoring.score_one({"rows": swap}, rec) == "FAIL"


def test_norm_rowset_is_order_blind_and_numeric_tolerant():
    a = [{"k": "x", "v": 3.0}, {"k": "y", "v": 4.0}]
    b = [{"k": "y", "v": 4.0000001}, {"k": "x", "v": 3.0}]  # reordered + tolerant
    assert scoring._norm_rowset(a) == scoring._norm_rowset(b)


def test_norm_rowset_tolerance_boundary_rejects_larger_gap():
    # The just-INSIDE side is covered above (1e-7). Pin the just-OUTSIDE side too,
    # so a widened or removed numeric tolerance can't silently start matching rows
    # that genuinely differ. The equality bucket edge sits below ~7e-7; a 1e-6 gap
    # must NOT collapse to the same normalized row.
    a = [{"k": "x", "v": 3.0}]
    b = [{"k": "x", "v": 3.000001}]  # 1e-6 gap — outside tolerance
    assert scoring._norm_rowset(a) != scoring._norm_rowset(b)


def test_rows_equal_name_aware_single_measure_matches():
    # One numeric measure: guard falls back to the base PoC verdict (PASS).
    gold = [{"region": "x", "revenue": 5.0}]
    got = [{"region": "x", "revenue": 5.0}]
    assert scoring.rows_equal_name_aware(got, gold, "set") is True


def test_fanout_of_none_is_na():
    assert scoring.fanout_of(None) == "N/A"
    assert scoring.fanout_of("SELECT 1") in {"FANOUT_SAFE", "FANOUT_RISK"}
