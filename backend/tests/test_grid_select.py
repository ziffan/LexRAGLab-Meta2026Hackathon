"""M1.4 pemilihan profil: S15-S20, S24, S10 (docs/scenarios/M1.4.md)."""

import itertools
from fractions import Fraction

import pytest

from backend.config import load
from backend.grid.frontier import aggregate_points
from backend.grid.select import SelectionNotApplicable, mode_rank_table, select_profiles
from backend.tests.grid_helpers import SIMPLICITY, const_rows, cov, ids, mk_setting, rows

TUNE10 = ids("i", 1, 10)
HELD6 = ids("h", 1, 6)


def pick(settings, metrics, simplicity=SIMPLICITY):
    st = {s.setting_id: s for s in settings}
    pts = aggregate_points(metrics, st)
    return select_profiles(pts, st, simplicity, family="uupt"), pts


def held(sid, n_full):
    return const_rows(HELD6, "held_out", sid, cov(n_full, 6))


def test_S15_held_out_never_selects_and_is_reported():
    T = mk_setting("leak-T", mode="hybrid", header=True, overlap=50)
    L = mk_setting("leak-L", mode="bm25", header=False, overlap=0)
    m = [*const_rows(TUNE10, "tune", "leak-T", [10] * 9 + [0], gold_tokens=200),
         *const_rows(HELD6, "held_out", "leak-T", [10, 10, 10, 0, 0, 0], gold_tokens=200),
         *const_rows(TUNE10, "tune", "leak-L", [10] * 7 + [0] * 3, gold_tokens=200),
         *const_rows(HELD6, "held_out", "leak-L", [10, 10, 10, 10, 10, 7], gold_tokens=200)]
    sel, _ = pick([T, L], m)
    s = sel[2000]
    assert s.setting_id == "leak-T"
    assert s.held_out_point.mean_span_recall == Fraction(1, 2)
    assert s.tune_point.mean_span_recall == Fraction(9, 10)
    # metamorfik: ganti seluruh held-out
    for t_cov, l_cov in (([10] * 6, [0] * 6), ([0] * 6, [10] * 6)):
        m2 = [x for x in m if x.split == "tune"] + const_rows(HELD6, "held_out", "leak-T", t_cov) \
            + const_rows(HELD6, "held_out", "leak-L", l_cov)
        assert pick([T, L], m2)[0][2000].setting_id == "leak-T"
    # ganti tune -> pilihan berubah
    m3 = [x for x in m if x.split == "held_out"] + const_rows(TUNE10, "tune", "leak-T", [10] * 7 + [0] * 3) \
        + const_rows(TUNE10, "tune", "leak-L", [10] * 9 + [0])
    assert pick([T, L], m3)[0][2000].setting_id == "leak-L"


def test_S16_band_and_simplicity_tiebreak_exact():
    x = mk_setting("s-x", mode="hybrid", header=True, overlap=50)
    y = mk_setting("s-y", mode="dense", header=False, overlap=50)
    z = mk_setting("s-z", mode="dense", header=False, overlap=0)
    w = mk_setting("s-w", mode="bm25", header=False, overlap=0)
    cfg = {"s-x": (8, 1500, 200), "s-y": (7, 1700, 300), "s-z": (7, 1800, 250), "s-w": (6, 900, 400)}
    held_full = {"s-x": 6, "s-w": 5, "s-y": 4, "s-z": 0}

    def build(held_map):
        m = []
        for sid, (n, tok, pg) in cfg.items():
            spec = [(10, 10 if k < n else 0, tok, pg) for k in range(10)] + [(0, 0, tok, 0)]
            m += rows(ids("i", 1, 11), "tune", sid, spec)
            m += held(sid, held_map[sid])
        return m

    sel, pts = pick([x, y, z, w], build(held_full))
    assert sel[2000].setting_id == "s-z"
    assert all(p.n_gold == 10 for p in pts if p.split == "tune")
    assert pick([x, y, z, w], build({"s-z": 6, "s-x": 0, "s-y": 1, "s-w": 2}))[0][2000].setting_id == "s-z"
    # penyebut 11 (butir tanpa gold ikut) akan memberi pita hanya {x}: ditolak oleh n_gold = 10
    st = {s.setting_id: s for s in (x, y, z, w)}
    assert select_profiles(pts, st, SIMPLICITY, family="uupt", n_tune_gold=11)[2000].setting_id == "s-x"


def test_S17_axis_priority_and_null_overlap():
    p1 = mk_setting("p-1", mode="dense", header=True, overlap=0)
    p2 = mk_setting("p-2", mode="bm25", header=False, overlap=100)
    p3 = mk_setting("p-3", mode="hybrid", header=False, overlap=100)
    prec = {"p-1": 500, "p-2": 400, "p-3": 200}
    m = []
    for sid in prec:
        m += const_rows(TUNE10, "tune", sid, cov(5, 10), gold_tokens=prec[sid])
    m += held("p-2", 6) + held("p-1", 3) + held("p-3", 0)
    assert pick([p1, p2, p3], m)[0][2000].setting_id == "p-3"
    q1 = mk_setting("q-1", chunker="structure_handwritten")  # overlap null
    q2 = mk_setting("q-2", overlap=32)
    assert q1.overlap_tokens is None
    mq = const_rows(TUNE10, "tune", "q-1", cov(5, 10), gold_tokens=100) + \
        const_rows(TUNE10, "tune", "q-2", cov(5, 10), gold_tokens=500) + held("q-2", 6) + held("q-1", 0)
    assert pick([q1, q2], mq)[0][2000].setting_id == "q-1"


def test_S18_precision_then_tokens_exact():
    u1, u2 = mk_setting("u-1"), mk_setting("u-2")
    ma = rows(TUNE10, "tune", "u-1", [(10, 6 if k < 10 else 0, 1000, 300) for k in range(10)]) \
        + rows(TUNE10, "tune", "u-2", [(10, 6, 800, 200) for _ in range(10)])
    # recall sama: 6/10 tiap butir
    assert pick([u1, u2], ma + held("u-2", 6) + held("u-1", 0))[0][2000].setting_id == "u-1"
    v1, v2 = mk_setting("v-1"), mk_setting("v-2")
    j = ["j1", "j2", "j3"]
    mb = rows(j, "tune", "v-1", [(10, 10, 1000, 200), (10, 10, 1000, 200), (10, 0, 1000, 200)]) \
        + rows(j, "tune", "v-2", [(10, 10, 900, 90), (10, 10, 900, 180), (10, 0, 900, 270)])
    sel, pts = pick([v1, v2], mb + held("v-1", 6) + held("v-2", 0))
    precs = {p.setting_id: p.mean_token_precision for p in pts}
    assert precs["v-1"] == precs["v-2"] == Fraction(1, 5)
    assert sel[2000].setting_id == "v-2"


@pytest.mark.parametrize("perm", list(itertools.permutations(["s-9", "s-10", "s-2"])))
def test_S19_full_tie_smallest_id_any_order(perm):
    sts = {s: mk_setting(s) for s in perm}
    m = []
    held_map = {"s-2": 6, "s-9": 3, "s-10": 0}
    for sid in perm:
        m += const_rows(TUNE10, "tune", sid, cov(6, 10), gold_tokens=300, retrieved=1000) + held(sid, held_map[sid])
    assert pick(list(sts.values()), m)[0][2000].setting_id == "s-10"
    flipped = {"s-2": 0, "s-9": 3, "s-10": 6}
    m2 = [x for x in m if x.split == "tune"]
    for sid in perm:
        m2 += held(sid, flipped[sid])
    assert pick(list(sts.values()), m2)[0][2000].setting_id == "s-10"


def test_S20_selection_per_budget():
    spec = {("b2-a", 2000): 9, ("b2-b", 2000): 5, ("b4-a", 4000): 4, ("b4-b", 4000): 8}
    sts, m = [], []
    for (sid, b), n in spec.items():
        sts.append(mk_setting(sid, budget=b))
        m += const_rows(TUNE10, "tune", sid, cov(n, 10))
    sel, _ = pick(sts, m)
    assert {b: s.setting_id for b, s in sel.items()} == {2000: "b2-a", 4000: "b4-b"}


def test_S24_precision_per_item_not_pooled():
    r1, r2 = mk_setting("r-1"), mk_setting("r-2")
    m = rows(["d1", "d2"], "tune", "r-1", [(10, 10, 10, 10), (10, 10, 90, 1)]) \
        + rows(["d1", "d2"], "tune", "r-2", [(10, 10, 100, 10), (10, 10, 100, 30)])
    sel, pts = pick([r1, r2], m)
    p = {x.setting_id: x.mean_token_precision for x in pts}
    assert p == {"r-1": Fraction(91, 180), "r-2": Fraction(1, 5)}
    assert sel[2000].setting_id == "r-1"


def test_S10_akta_has_no_selection():
    st = {"k": mk_setting("k", family="akta")}
    pts = aggregate_points(const_rows(ids("k", 1, 5), None, "k", cov(3, 5)), st)
    assert all(p.split is None for p in pts)
    with pytest.raises(SelectionNotApplicable):
        select_profiles(pts, st, SIMPLICITY, family="akta")


def test_real_config_simplicity_order_is_readable():
    cfg = load("grid")["simplicity"]
    ranks = mode_rank_table(cfg, ["dense", "bm25", "hybrid"])
    assert ranks["bm25"] < ranks["dense"] < ranks["hybrid"]
    assert cfg["tie_margin_items"] == 1


def test_S19_final_tiebreak_setting_id_direct_on_select_unsorted():
    from backend.tests.grid_helpers import make_point
    sts = {s: mk_setting(s) for s in ("s-9", "s-10", "s-2")}
    for perm in itertools.permutations(sts):
        pts = [make_point(s, 900, "0.6", prec=Fraction(3, 10)) for s in perm]
        assert list(select_profiles(pts, sts, SIMPLICITY, family="uupt")[2000].setting_id for _ in [0]) == ["s-10"]


def test_real_config_mode_order_comes_from_single_retrieval_modes():
    cfg = dict(load("grid")["simplicity"])
    assert mode_rank_table(cfg, ["dense", "bm25", "hybrid"]) == {"bm25": 0, "dense": 1, "hybrid": 2}
    rev = {**cfg, "single_retrieval_modes": ["dense", "bm25"]}
    assert mode_rank_table(rev, ["dense", "bm25", "hybrid"]) == {"dense": 0, "bm25": 1, "hybrid": 2}
    from backend.tests.grid_helpers import make_point
    sts = {"d": mk_setting("d", mode="dense"), "b": mk_setting("b", mode="bm25")}
    pts = [make_point("d", 900, "0.6", prec=Fraction(3, 10)), make_point("b", 900, "0.6", prec=Fraction(3, 10))]
    assert select_profiles(pts, sts, cfg, family="uupt")[2000].setting_id == "b"
    assert select_profiles(pts, sts, rev, family="uupt")[2000].setting_id == "d"


def test_no_gold_group_is_none_not_frontier_not_selectable():
    from backend.grid.frontier import compute_frontiers
    a, b = mk_setting("a"), mk_setting("b")
    m = const_rows(TUNE10, "tune", "a", cov(5, 10)) + rows(["n1", "n2"], "tune", "b", [(0, 0, 500, 0)] * 2)
    pts = aggregate_points(m, {"a": a, "b": b})
    pb = next(p for p in pts if p.setting_id == "b")
    assert pb.mean_span_recall is None and pb.mrr is None and pb.mean_token_precision is None
    assert pb.mean_retrieved_tokens is None and pb.fully_covered_count == {"covered": 0, "total": 0}
    out, fr = compute_frontiers(pts, "r")
    assert list(fr[0].point_ids) == ["a"] and not any(p.dominated for p in out)
    assert select_profiles(pts, {"a": a, "b": b}, SIMPLICITY, family="uupt")[2000].setting_id == "a"
    only_b = [p for p in pts if p.setting_id == "b"]
    assert select_profiles(only_b, {"b": b}, SIMPLICITY, family="uupt") == {}


def test_mean_retrieved_tokens_over_gold_items_only():
    a = mk_setting("a")
    m = rows(["g1", "g2", "n1"], "tune", "a", [(10, 5, 100, 10), (10, 5, 300, 10), (0, 0, 9999, 0)])
    assert aggregate_points(m, {"a": a})[0].mean_retrieved_tokens == 200


def test_contract_output_excludes_internal_fields():
    a = mk_setting("a")
    p = aggregate_points(const_rows(TUNE10, "tune", "a", cov(5, 10)), {"a": a})[0]
    d = p.to_dict()
    assert "family" not in d and "n_gold" not in d and d["fully_covered_count"] == {"covered": 5, "total": 10}
