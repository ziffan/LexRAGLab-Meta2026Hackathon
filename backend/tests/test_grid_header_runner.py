"""M3.2 runner dan deret: S7, S8, S10, S12, S13, S14 (docs/scenarios/M3.2.md rev. 4)."""

from dataclasses import replace
from types import SimpleNamespace

import pytest

from backend.grid.frontier import compute_frontiers
from backend.grid.headers import (FailedSetting, HeaderBinding, MemoryHeaderStore, resolve_headers, series_of)
from backend.grid.runner import MemoryGridCache, run_grid
from backend.grid.split import make_split
from backend.metrics.run_record import run_record_parts
from backend.metrics.types import ItemMetrics
from backend.pipeline import pipeline as pipeline_mod
from backend.pipeline.grid_run import pipeline_config_hash
from backend.tests.grid_helpers import SIMPLICITY, ids, make_point, mk_items
from backend.tests.header_grid_helpers import F, account, doc_of, header_records, item, make_pipe, make_store, setting, twin
from backend.tests.toy_ws import C1, C2, C3, C4, T, TOK

CH = {"c1": C1, "c2": C2, "c3": C3, "c4": C4}


# ---------- S7 ----------
def test_S7a_combined_frontier_on_and_off_series_partition():
    st = {s: setting(s, header=h) for s, h in (("A", False), ("B", False), ("C", True), ("D", True))}
    pts = [make_point("A", 100, "1/2"), make_point("B", 300, "4/5"), make_point("C", 150, "3/5"), make_point("D", 400, "4/5")]
    out, fr = compute_frontiers(pts, "k")
    assert fr[0].point_ids == ("A", "C", "B")  # token naik
    assert {p.setting_id: p.dominated for p in out} == {"A": False, "B": False, "C": False, "D": True}
    s = series_of(out, st)
    assert {p.setting_id for p in s["off"]} == {"A", "B"} and {p.setting_id for p in s["on"]} == {"C", "D"}


def test_S7b_on_dominates_off_and_identical_points_both_stay():
    st = {s: setting(s, header=h) for s, h in (("G", False), ("H", True), ("I", False), ("J", True))}
    pts = [make_point("G", 200, "3/5"), make_point("H", 150, "7/10"), make_point("I", 300, "4/5"), make_point("J", 300, "4/5")]
    out, fr = compute_frontiers(pts, "k")
    assert fr[0].point_ids == ("H", "I", "J")
    assert {p.setting_id: p.dominated for p in out} == {"G": True, "H": False, "I": False, "J": False}
    assert {p.setting_id for p in series_of(out, st)["on"]} == {"H", "J"}


# ---------- S8 ----------
BASE = {  # off: (covered/10, retrieved) pada tune
    "s1": (5, 100), "s2": (7, 200), "s3": (6, 250), "s4": (9, 400)}


class FakeHeaderPipeline:
    """Pipeline palsu: metrik dari tabel; setting header-on memeriksa store lewat `resolve_headers` sungguhan (spy di store)."""

    def __init__(self, store, binding, chunk_ids, held_out, held_s3=None):
        self.store, self.binding, self.chunk_ids, self.held_out, self.held_s3 = store, binding, chunk_ids, held_out, held_s3
        self.executed: list[str] = []

    def __call__(self, st, items):
        self.executed.append(st.setting_id)
        if st.header_b:
            chunks = [SimpleNamespace(chunk_id=c, start=i, end=i + 1) for i, c in enumerate(self.chunk_ids[st.setting_id])]
            resolve_headers(chunks, self.store, setting_id=st.setting_id, granularity=self.binding.expected_granularity(st.chunker),
                            clean_sha256="X")
        base = st.setting_id.rstrip("+")
        cov, ret = BASE[base]
        out = []
        for it in items:
            c, r = (self.held_s3 if (self.held_s3 and base == "s3" and it.id in self.held_out) else (cov, ret))
            out.append(ItemMetrics(10, c, r + (10 if st.header_b else 0), 5, item_id=it.id, setting_id=st.setting_id))
        return out


def s8_world(*, store_has, fixed_s2=False, scope="frontier_only"):
    settings_off = [setting("s1", header=False, family="uupt", mode="bm25"),
                    setting("s2", header=False, family="uupt", mode="bm25", chunker="fixed_size", size=5, overlap=1) if fixed_s2
                    else setting("s2", header=False, family="uupt", mode="dense"),
                    setting("s3", header=False, family="uupt", mode="hybrid"),
                    setting("s4", header=False, family="uupt", mode="bm25", chunker="fixed_size", size=9, overlap=0)]
    on = [twin(s) for s in settings_off]
    chunk_ids = {s.setting_id: [s.setting_id.rstrip("+") + "c1", s.setting_id.rstrip("+") + "c2"] for s in on}
    gran = {s.setting_id: ("fixed_size" if s.chunker == "fixed_size" else "ayat") for s in on}
    store = MemoryHeaderStore({}, {"b1": "X"})
    for s in on:
        if s.setting_id.rstrip("+") in store_has:
            for cid in chunk_ids[s.setting_id]:
                store.records[cid] = {"chunk_id": cid, "header": "H x", "granularity": gran[s.setting_id], "run_id": "b1"}
    binding = HeaderBinding(store, "ayat", scope, "ph", "m")
    items = mk_items({("operator", "literal"): ids("i", 1, 3), ("operator", "parafrase"): ["i4"],
                      ("spark_disetujui", "literal"): ids("i", 5, 8)}, family="uupt")
    rec = make_split(items, family="uupt", seed=7, held_out_ratio=0.4, min_control=3)
    held = {i for i, sp in rec.split_of().items() if sp == "held_out"}
    return settings_off, on, store, binding, items, rec, held, chunk_ids


def run8(world, *, held_s3=None, cache=None, config_hash="C", scope=None):
    off, on, store, binding, items, rec, held, chunk_ids = world
    pipe = FakeHeaderPipeline(store, binding, chunk_ids, held, held_s3)
    r = run_grid(settings=[*off, *on], items=items, pipeline=pipe, cache=cache or MemoryGridCache(), clean_sha256="X",
                 config_hash=config_hash, split_record=rec, simplicity=SIMPLICITY, family="uupt",
                 header_scope=scope or binding.scope)
    return r, pipe


def on_points(r):
    return {p.setting_id for p in r.points if p.setting_id.endswith("+") and p.split == "tune"}


def test_S8_frontier_only_executes_twins_of_off_tune_frontier_only():
    w = s8_world(store_has={"s1", "s2", "s4"})
    r, pipe = run8(w)
    assert on_points(r) == {"s1+", "s2+", "s4+"} and r.failed_settings == ()
    assert "s3+" not in pipe.executed and not any(c.startswith("s3") for c in w[2].requests)  # spy
    off_front = [f for f in r.frontiers if f.split == "tune"]
    assert {p.setting_id for p in r.points if p.split == "tune" and not p.setting_id.endswith("+")} == {"s1", "s2", "s3", "s4"}
    assert len(off_front) == 1


def test_S8b_held_out_is_never_read_for_the_twin_set():
    w = s8_world(store_has={"s1", "s2", "s4"})
    held = w[6]
    r, pipe = run8(w, held_s3=(10, 50))  # s3 terbaik di held-out
    assert on_points(r) == {"s1+", "s2+", "s4+"} and "s3+" not in pipe.executed


def test_S8_scope_all_runs_every_twin_s3_fails_with_A4_others_run():
    w = s8_world(store_has={"s1", "s2", "s4"}, scope="all")
    r, pipe = run8(w)
    assert on_points(r) == {"s1+", "s2+", "s4+"}
    assert r.failed_settings == (FailedSetting("s3+", "header_missing", "s3c1"),)
    assert "s3+" in pipe.executed


def test_S8c_frontier_only_rerun_over_scope_all_data_does_not_leak_s3():
    w = s8_world(store_has={"s1", "s2", "s4", "s3"}, scope="all")
    cache = MemoryGridCache()
    r1, _ = run8(w, cache=cache, config_hash="C-all", scope="all")
    assert on_points(r1) == {"s1+", "s2+", "s3+", "s4+"}
    w[2].requests.clear()
    r2, pipe2 = run8(w, cache=cache, config_hash="C-fo", scope="frontier_only")
    assert on_points(r2) == {"s1+", "s2+", "s4+"} and "s3+" not in pipe2.executed
    assert not any(c.startswith("s3") for c in w[2].requests)
    assert not any(m.setting_id == "s3+" for m in r2.metrics) and "s3+" not in {sid for f in r2.frontiers for sid in f.point_ids}
    assert r2.grid_run_id != r1.grid_run_id
    r1b, _ = run8(w, cache=cache, config_hash="C-all", scope="all")  # run pertama tidak ditimpa
    assert r1b.cache_hit and on_points(r1b) == {"s1+", "s2+", "s3+", "s4+"}


def test_S8d_fixed_size_twin_in_frontier_is_executed_not_skipped():
    w = s8_world(store_has={"s1", "s2", "s4"}, fixed_s2=True)
    r, pipe = run8(w)
    assert on_points(r) == {"s1+", "s2+", "s4+"} and r.failed_settings == ()
    assert any(c.startswith("s2c") for c in w[2].requests) and not any(c.startswith("s3") for c in w[2].requests)
    rall, _ = run8(s8_world(store_has={"s1", "s2", "s4"}, fixed_s2=True, scope="all"))
    assert on_points(rall) == {"s1+", "s2+", "s4+"} and [f.setting_id for f in rall.failed_settings] == ["s3+"]


def test_run_grid_rejects_unknown_scope():
    from backend.grid.runner import GridError

    w = s8_world(store_has=set())
    with pytest.raises(GridError):
        run8(w, scope="some")


# ---------- S10 ----------
def test_S10_both_series_get_identical_packing_inputs(monkeypatch):
    doc = doc_of(T)
    s = setting("s", header=False, budget=2000)
    s_on = twin(s)
    calls = []
    orig = pipeline_mod.compute_item_metrics

    def spy(text, gold, ranked, budget, tok, **kw):
        calls.append((budget, kw["packing"], tok, [c.header for c in ranked], kw["setting_id"]))
        return orig(text, gold, ranked, budget, tok, **kw)

    monkeypatch.setattr(pipeline_mod, "compute_item_metrics", spy)
    pipe = make_pipe(doc, [(s, CH)], make_store({"c1": "H1 H2", "c2": "H3", "c3": "H4 H5 H6", "c4": "H7"}), packing="skip")
    items = [item("i1", [(15, 20)], "a5"), item("i2", [(3, 5)], "a1")]
    r = run_grid(settings=[s, s_on], items=items, pipeline=pipe, cache=MemoryGridCache(), clean_sha256="X", config_hash="C",
                 split_record=None, simplicity=SIMPLICITY, family="akta", header_scope="all")
    assert s.setting_id != s_on.setting_id
    assert {(c[0], c[1], id(c[2])) for c in calls} == {(2000, "skip", id(TOK))}
    off_calls = [c for c in calls if c[4] == "s"]
    on_calls = [c for c in calls if c[4] == "s+"]
    assert len(off_calls) == len(on_calls) == 2
    assert all(h == "" for c in off_calls for h in c[3]) and all(h != "" for c in on_calls for h in c[3])
    assert {m.setting_id for m in r.metrics} == {"s", "s+"} and {m.item_id for m in r.metrics} == {"i1", "i2"}
    assert run_record_parts(TOK.info, "skip") == {"tokenizer": {"name": "toy-ws", "version": "1"}, "packing": "skip"}


# ---------- S12 ----------
def s12_world():
    doc = doc_of(T)
    s = setting("s", header=False, budget=100)
    pipe = make_pipe(doc, [(s, CH)], make_store({"c1": "H1", "c2": "ZZ H2", "c3": "H3", "c4": "H4"}))
    return doc, pipe, s, twin(s)


def test_S12_off_index_has_no_header_trace_on_index_contains_header():
    doc, pipe, off, on = s12_world()
    want_off = [(cid, T[a:b]) for cid, (a, b) in CH.items()]
    assert pipe.index_texts(off) == want_off
    on_texts = dict(pipe.index_texts(on))
    assert "ZZ" in on_texts["c2"] and "H2" in on_texts["c2"] and "a4 a5 a6 a7 a8" in on_texts["c2"]
    assert pipe.index(off) is not pipe.index(on)
    it = item("q", [], "ZZ")
    assert pipe.ranking(off, it) == []
    assert [cid for cid, _ in pipe.ranking(on, it)] == ["c2"]
    assert pipe.chunk_set(off) is pipe.chunk_set(on)  # offset dan chunk_id sama; indeks terpisah
    assert [(c.chunk_id, c.start, c.end) for c in pipe.chunk_set(on).chunks] == [(k, a, b) for k, (a, b) in CH.items()]


# ---------- S14 ----------
def test_S14_end_to_end_header_changes_ranking_all_the_way_to_P():
    doc, pipe, off, on = s12_world()
    items = [item("i1", [(15, 20)], "ZZ"), item("i2", [(3, 5)], "a1")]
    r = run_grid(settings=[off, on], items=items, pipeline=pipe, cache=MemoryGridCache(), clean_sha256="X", config_hash="C",
                 split_record=None, simplicity=SIMPLICITY, family="akta", header_scope="all")
    m = {(x.setting_id, x.item_id): x for x in r.metrics}
    got = {k: (v.span_recall, v.retrieved_tokens, v.token_precision, v.reciprocal_rank) for k, v in m.items()}
    assert got[("s", "i1")] == (F(0), 0, None, F(0))
    assert got[("s+", "i1")] == (F(1), 7, F(2, 7), F(1))
    assert got[("s", "i2")] == (F(1), 4, F(1, 4), F(1))
    assert got[("s+", "i2")] == (F(1), 5, F(1, 5), F(1))
    pts = {p.setting_id: p for p in r.points}
    assert (pts["s"].mean_span_recall, pts["s"].mean_retrieved_tokens) == (F(1, 2), F(2))
    assert (pts["s+"].mean_span_recall, pts["s+"].mean_retrieved_tokens) == (F(1), F(6))


# ---------- S13 ----------
class CountingPipe:
    def __init__(self):
        self.calls_on = self.calls_off = 0
        self.generation = 1

    def __call__(self, st, items):
        if st.header_b:
            self.calls_on += 1
        else:
            self.calls_off += 1
        return [ItemMetrics(10, 5, 100 * self.generation, 5, item_id=i.id, setting_id=st.setting_id) for i in items]


def test_S13_cache_key_covers_header_content_granularity_prompt_scope_not_run_id():
    cfgs = {"grid": {"x": 1}}
    info = SimpleNamespace(name="toy-ws", version="1")
    off = setting("s", header=False)
    settings = [off, twin(off)]
    items = [item("i1", [(0, 5)], "a"), item("i2", [(3, 5)], "b")]
    cache, pipe = MemoryGridCache(), CountingPipe()

    def store(content, run_id="b1"):
        return make_store(content, run_id=run_id)

    e1, e2 = {"c1": "H1 H2"}, {"c1": "H9 H8 H7"}

    def go(binding, gen):
        pipe.calls_on = pipe.calls_off = 0
        pipe.generation = gen
        r = run_grid(settings=settings, items=items, pipeline=pipe, cache=cache, clean_sha256="X",
                     config_hash=pipeline_config_hash(cfgs, info, binding), split_record=None, simplicity=SIMPLICITY,
                     family="akta", header_scope=binding.scope)
        return r, pipe.calls_on

    base = HeaderBinding(store(e1), "pasal", "all", "p1", "m")
    r1, c1 = go(base, 1)
    r2, c2 = go(base, 2)
    r3, c3 = go(HeaderBinding(store(e2), "pasal", "all", "p2", "m"), 3)
    r4, c4 = go(replace(base, granularity="ayat"), 4)
    r5, c5 = go(replace(base, scope="frontier_only"), 5)
    r6, c6 = go(base, 6)
    r7, c7 = go(HeaderBinding(store(e1, run_id="b2"), "pasal", "all", "p1", "m"), 7)
    assert c1 > 0 and c2 == 0 and r2.cache_hit and not r1.cache_hit
    assert c3 > 0 and c4 > 0 and c5 > 0
    assert c6 == 0 and r6.metrics == r1.metrics and r6.metrics != r3.metrics  # R1 tidak tertimpa
    assert c7 == 0 and r7.cache_hit  # run_id B tidak masuk kunci
    assert len({r.grid_run_id for r in (r1, r3, r4, r5)}) == 4
    # model ikut kunci
    assert pipeline_config_hash(cfgs, info, base) != pipeline_config_hash(cfgs, info, replace(base, model="m2"))
    # tanpa binding hash lama tetap sama (M1 tidak berubah)
    assert pipeline_config_hash(cfgs, info) == pipeline_config_hash(cfgs, info, None)


def test_S13_single_component_changes_each_invalidate_alone():
    cfgs, info = {"grid": {"x": 1}}, SimpleNamespace(name="toy-ws", version="1")
    h = lambda b: pipeline_config_hash(cfgs, info, b)
    base = HeaderBinding(make_store({"c1": "H1 H2"}), "pasal", "all", "p1", "m")
    assert h(base) != h(replace(base, store=make_store({"c1": "H9"})))  # hanya isi store
    assert h(base) != h(replace(base, prompt_hash="p2"))  # hanya prompt_hash
    assert h(base) == h(replace(base, store=make_store({"c1": "H1 H2"}, run_id="b2")))


def test_cache_hit_returns_same_failed_settings():
    w = s8_world(store_has={"s1", "s2", "s4"}, scope="all")
    cache = MemoryGridCache()
    r1, _ = run8(w, cache=cache)
    r2, _ = run8(w, cache=cache)
    assert r2.cache_hit and r1.failed_settings == r2.failed_settings == (FailedSetting("s3+", "header_missing", "s3c1"),)
