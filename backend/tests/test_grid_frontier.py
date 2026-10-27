"""M1.4 dominasi dan frontier: S11-S14, S23 (docs/scenarios/M1.4.md)."""

import random
from fractions import Fraction

from backend.grid.frontier import aggregate_points, compute_frontiers
from backend.tests.grid_helpers import const_rows, make_point, mk_setting, rows


def flags(points):
    return {p.setting_id: p.dominated for p in points}


def test_S11_dominance_weak_with_one_strict_and_identical_points():
    spec = [("a-1", 1000, "0.80"), ("a-2", 1500, "0.80"), ("a-3", 800, "0.60"), ("a-4", 1200, "0.90"),
            ("a-5", 1200, "0.85"), ("a-6", 2000, "0.90"), ("a-7", 500, "0.30"), ("a-8", 1000, "0.80")]
    pts = [make_point(s, x, y) for s, x, y in spec]
    for seed in range(5):
        shuffled = pts[:]
        random.Random(seed).shuffle(shuffled)
        out, fr = compute_frontiers(shuffled, "run")
        assert fr[0].point_ids == ("a-7", "a-3", "a-1", "a-8", "a-4")
        assert flags(out) == {"a-1": False, "a-2": True, "a-3": False, "a-4": False,
                              "a-5": True, "a-6": True, "a-7": False, "a-8": False}


def test_S12_exact_equality_not_broken_by_float():
    st = {s: mk_setting(s) for s in ("f-1", "f-2")}
    m = [*const_rows(["x1", "x2", "x3"], "tune", "f-1", [0, 0, 3], retrieved=500, gold_tokens=0),
         *const_rows(["x1", "x2", "x3"], "tune", "f-2", [1, 1, 1], retrieved=500, gold_tokens=0)]
    pts = aggregate_points(m, st)
    assert {p.mean_span_recall for p in pts} == {Fraction(1, 10)}
    _, fr = compute_frontiers(pts, "run")
    assert sorted(fr[0].point_ids) == ["f-1", "f-2"]
    assert not any(p.dominated for p in compute_frontiers(pts, "run")[0])


def test_S13_grouping_by_family_split_budget():
    pts = [make_point("g-1", 1000, "0.50", budget=2000), make_point("g-2", 900, "0.60", budget=4000),
           make_point("g-3", 800, "0.99", split="held_out", budget=2000),
           make_point("g-4", 2000, "0.90", budget=2000), make_point("g-5", 2500, "0.95", budget=4000)]
    out, fr = compute_frontiers(pts, "run")
    got = {(f.split, f.budget_tokens): list(f.point_ids) for f in fr}
    assert got == {("tune", 2000): ["g-1", "g-4"], ("tune", 4000): ["g-2", "g-5"], ("held_out", 2000): ["g-3"]}
    assert not any(p.dominated for p in out)
    assert all(f.grid_run_id == "run" and f.family == "uupt" for f in fr)


def test_S14_edge_cases():
    assert compute_frontiers([], "r") == ([], [])
    out, fr = compute_frontiers([make_point("h-0", 1000, "0.5")], "r")
    assert list(fr[0].point_ids) == ["h-0"] and not out[0].dominated
    out, fr = compute_frontiers([make_point(f"h-{i}", 1000, "0.5") for i in (1, 2, 3)], "r")
    assert list(fr[0].point_ids) == ["h-1", "h-2", "h-3"] and not any(p.dominated for p in out)


def test_S23_per_item_mean_not_pooled_and_no_gold_excluded():
    st = {s: mk_setting(s) for s in ("m-1", "m-2")}
    m = [
        *rows(["A", "B"], "tune", "m-1", [(10, 10, 500, 0), (30, 0, 500, 0)]),
        *rows(["A", "B"], "tune", "m-2", [(10, 0, 500, 0), (30, 15, 500, 0)]),
        *rows(["H1", "H2", "H3"], "held_out", "m-1", [(10, 5, 500, 0), (30, 30, 500, 0), (0, 0, 500, 0)]),
    ]
    pts = {(p.setting_id, p.split): p for p in aggregate_points(m, st)}
    assert pts[("m-1", "tune")].mean_span_recall == Fraction(1, 2)
    assert pts[("m-2", "tune")].mean_span_recall == Fraction(1, 4)
    assert pts[("m-1", "held_out")].mean_span_recall == Fraction(3, 4)
    assert pts[("m-1", "held_out")].fully_covered_count == {"covered": 1, "total": 2}
    out, fr = compute_frontiers([p for p in pts.values() if p.split == "tune"], "r")
    assert list(fr[0].point_ids) == ["m-1"]
    assert {p.setting_id: p.dominated for p in out} == {"m-1": False, "m-2": True}
