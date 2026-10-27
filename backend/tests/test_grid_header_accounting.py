"""M3.2 akuntansi token header: S1, S2, S2b, S3, S6, S9, S11, S15 (docs/scenarios/M3.2.md rev. 4). Angka persis dari skenario."""

import pytest

from backend.grid.frontier import aggregate_points
from backend.grid.headers import HeaderInvalidError
from backend.tests.header_grid_helpers import (F, Toy2, account, doc_of, header_tokens, make_pipe, make_store, packed_ids,
                                               setting, source_tokens, twin)
from backend.tests.toy_ws import C1, C2, C3, C4, T, TOK, U

CH = {"c1": C1, "c2": C2, "c3": C3, "c4": C4}
HDR = {"c1": "H1 H2", "c2": "H3", "c3": "H4 H5 H6", "c4": "H7"}  # header baku T
GOLD = [(15, 20)]


def world(budget, *, headers=HDR, packing="stop", chunks=CH, store_kw=None, **kw):
    doc = doc_of(T)
    off = setting("s", header=False, budget=budget)
    on = twin(off)
    pipe = make_pipe(doc, [(off, chunks)], make_store(headers, **(store_kw or {})), packing=packing, **kw)
    return doc, pipe, off, on


def row(doc, rt):
    m = rt.metrics
    return (packed_ids(rt), source_tokens(rt, doc), header_tokens(rt, doc), m.retrieved_tokens,
            m.span_recall, m.token_precision, m.reciprocal_rank)


# ---------- S1 ----------
def test_S1_same_budget_header_on_carries_less_source_text():
    doc, pipe, off, on = world(11)
    c = ["c1", "c2", "c3", "c4"]
    r_off, r_on = account(pipe, off, c, GOLD), account(pipe, on, c, GOLD)
    assert row(doc, r_off) == (("c1", "c2", "c3"), 11, 0, 11, F(1), F(2, 11), F(1, 2))
    assert r_off.metrics.fully_covered is True and r_off.metrics.gold_tokens_retrieved == 2
    assert row(doc, r_on) == (("c1",), 4, 2, 6, F(0), F(0), F(0))
    assert r_on.metrics.fully_covered is False and r_on.metrics.covered_gold_chars == 0
    assert source_tokens(r_on, doc) < source_tokens(r_off, doc) and r_on.metrics.retrieved_tokens <= 11
    assert off.setting_id != on.setting_id and (off.header_b, on.header_b) == (False, True)


# ---------- S2 ----------
S2 = {  # B: (off, on); tiap sisi = (P, sumber, header, ret, span, prec, rr)
    5: ((("c1",), 4, 0, 4, F(0), F(0), F(0)), ((), 0, 0, 0, F(0), None, F(0))),
    8: ((("c1",), 4, 0, 4, F(0), F(0), F(0)), (("c1",), 4, 2, 6, F(0), F(0), F(0))),
    11: ((("c1", "c2", "c3"), 11, 0, 11, F(1), F(2, 11), F(1, 2)), (("c1",), 4, 2, 6, F(0), F(0), F(0))),
    12: ((("c1", "c2", "c3"), 11, 0, 11, F(1), F(2, 11), F(1, 2)), (("c1", "c2"), 9, 3, 12, F(1), F(1, 6), F(1, 2))),
    13: ((("c1", "c2", "c3"), 11, 0, 11, F(1), F(2, 11), F(1, 2)), (("c1", "c2"), 9, 3, 12, F(1), F(1, 6), F(1, 2))),
    16: ((("c1", "c2", "c3", "c4"), 14, 0, 14, F(1), F(1, 7), F(1, 2)), (("c1", "c2"), 9, 3, 12, F(1), F(1, 6), F(1, 2))),
    20: ((("c1", "c2", "c3", "c4"), 14, 0, 14, F(1), F(1, 7), F(1, 2)), (("c1", "c2", "c3"), 11, 6, 17, F(1), F(2, 17), F(1, 2))),
    21: ((("c1", "c2", "c3", "c4"), 14, 0, 14, F(1), F(1, 7), F(1, 2)), (("c1", "c2", "c3", "c4"), 14, 7, 21, F(1), F(2, 21), F(1, 2))),
}


@pytest.mark.parametrize("b", sorted(S2))
def test_S2_budget_sweep_stop(b):
    doc, pipe, off, on = world(b)
    c = ["c1", "c2", "c3", "c4"]
    r_off, r_on = account(pipe, off, c, GOLD), account(pipe, on, c, GOLD)
    want_off, want_on = S2[b]
    assert row(doc, r_off) == want_off and row(doc, r_on) == want_on
    assert r_on.metrics.retrieved_tokens <= b and source_tokens(r_on, doc) <= source_tokens(r_off, doc)  # A8 (hanya stop)
    equal = b in (8, 21)
    assert (source_tokens(r_on, doc) == source_tokens(r_off, doc)) == equal


# ---------- S2b ----------
def test_S2b_skip_counterexample_source_tokens_on_can_exceed_off():
    doc, pipe, off, on = world(6, headers={"c4": "K1 K2 K3 K4 K5", "c1": "H1"}, packing="skip",
                                   chunks={"c1": C1, "c4": C4})
    c = ["c4", "c1"]
    r_off, r_on = account(pipe, off, c, GOLD), account(pipe, on, c, GOLD)
    assert (packed_ids(r_off), source_tokens(r_off, doc), r_off.metrics.retrieved_tokens) == (("c4",), 3, 3)
    assert (packed_ids(r_on), source_tokens(r_on, doc), header_tokens(r_on, doc), r_on.metrics.retrieved_tokens) == (("c1",), 4, 1, 5)
    assert source_tokens(r_on, doc) > source_tokens(r_off, doc) and r_on.metrics.retrieved_tokens <= 6  # tidak ada invarian di skip


# ---------- S3 ----------
def s3_world(tok=TOK, budget=12, **store_kw):
    doc = doc_of(T)
    off = setting("s", header=False, budget=budget)
    store = make_store({"c1": "H1  H2", "c2": "\nH3\n"}, **store_kw)
    store.records["c1"]["tokens_local"], store.records["c2"]["tokens_local"] = 99, 0  # basi
    store.records["c1"]["usage_input_tokens"] = 1500
    pipe = make_pipe(doc, [(off, {"c1": C1, "c2": C2})], store, tokenizer=tok)
    return doc, pipe, twin(off)


def test_S3_header_cost_from_run_tokenizer_not_tokens_local_or_usage():
    doc, pipe, on = s3_world()
    rt = account(pipe, on, ["c1", "c2"], [(0, 11)])
    m = rt.metrics
    assert packed_ids(rt) == ("c1", "c2") and m.retrieved_tokens == 12 and header_tokens(rt, doc) == 3
    assert (m.span_recall, m.gold_tokens_retrieved, m.token_precision, m.reciprocal_rank, m.fully_covered) == (F(1), 4, F(1, 3), F(1), True)


def test_S3b_second_tokenizer_and_spy_header_strings_only():
    tok = Toy2()
    doc, pipe, on = s3_world(tok=tok, budget=17)
    rt = account(pipe, on, ["c1", "c2"], [(0, 11)])
    assert packed_ids(rt) == ("c1",) and rt.metrics.retrieved_tokens == 9 and rt.metrics.span_recall == F(1)
    assert rt.metrics.reciprocal_rank == F(1)
    assert "H1  H2" in tok.calls and "\nH3\n" in tok.calls  # string header saja, tanpa strip
    assert not any(("H1  H2" in c or "\nH3\n" in c) and len(c) > 7 for c in tok.calls)  # tidak pernah header+teks


def test_S3c_tab_is_separator_and_empty_headers_are_invalid():
    doc = doc_of(T)
    off = setting("s", header=False, budget=12)
    on = twin(off)
    pipe = make_pipe(doc, [(off, {"c1": C1})], make_store({"c1": "H1\tH2"}))
    assert header_tokens(account(pipe, on, ["c1"]), doc) == 2
    for bad in ("", "  \n", "\t"):
        pipe = make_pipe(doc, [(off, {"c1": C1})], make_store({"c1": bad}))
        with pytest.raises(HeaderInvalidError) as e:
            pipe.headers_for(on)
        assert e.value.chunk_id == "c1" and on.setting_id in str(e.value)


# ---------- S6 ----------
def test_S6_gold_and_offsets_stay_on_source_text_even_if_header_repeats_words():
    doc = doc_of(T)
    off = setting("s", header=False, budget=8)
    on = twin(off)
    pipe = make_pipe(doc, [(off, {"c": (6, 17)})], make_store({"c": "a4 a5 a2 a3"}))
    rt = account(pipe, on, ["c"], [(9, 14), (18, 20)])
    m = rt.metrics
    assert (rt.packed[0].start, rt.packed[0].end) == (6, 17)
    assert (pipe.chunk_set(on).by_id["c"].start, pipe.chunk_set(on).by_id["c"].end) == (6, 17)
    assert (m.gold_chars, m.covered_gold_chars, m.span_recall, m.gold_tokens_retrieved, m.retrieved_tokens) == (7, 5, F(5, 7), 2, 8)
    assert (m.token_precision, m.reciprocal_rank, m.fully_covered) == (F(1, 4), F(1), False)


# ---------- S9 ----------
def u_pipe(chunks, headers, *, gran_store, gran_cfg, chunker_key="kA"):
    doc = doc_of(U)
    s = setting("sx", header=False, budget=10)
    pipe = make_pipe(doc, [(s, chunks)], make_store(headers, granularity=gran_store), granularity=gran_cfg)
    return doc, pipe, s


SP_CH = {"PK1": (0, 50), "PK2": (52, 76)}
SP_H = {"PK1": "HP1a HP1b HP1c", "PK2": "HP2a HP2b"}
SA_CH = {"a1": (0, 24), "a2": (25, 37), "a3": (38, 50), "PK2p": (52, 76)}
SA_H = {"a1": "HA1a HA1b", "a2": "HA2a HA2b HA2c HA2d HA2e", "a3": "HA3a HA3b", "PK2p": "HP2a HP2b"}
U_GOLD = [(38, 50)]


@pytest.mark.parametrize("b,want", [
    (10, ((), 0, 0, 0, F(0), None, F(0))),
    (20, (("PK1",), 12, 3, 15, F(1), F(1, 5), F(1))),
])
def test_S9_pasal_header_per_chunk_id(b, want):
    doc, pipe, s = u_pipe(SP_CH, SP_H, gran_store="pasal", gran_cfg="pasal")
    from dataclasses import replace
    on = twin(replace(s, budget_tokens=b))
    assert row(doc, account(pipe, on, ["PK1", "PK2"], U_GOLD)) == want


@pytest.mark.parametrize("b,want", [
    (10, (("a3",), 3, 2, 5, F(1), F(3, 5), F(1))),
    (13, (("a3", "a1"), 9, 4, 13, F(1), F(3, 13), F(1))),
    (21, (("a3", "a1", "a2"), 12, 9, 21, F(1), F(1, 7), F(1))),
])
def test_S9_ayat_header_per_chunk_id_first_chunk_contains_pasal_heading(b, want):
    doc, pipe, s = u_pipe(SA_CH, SA_H, gran_store="ayat", gran_cfg="ayat")
    from dataclasses import replace
    on = twin(replace(s, budget_tokens=b))
    assert row(doc, account(pipe, on, ["a3", "a1", "a2", "PK2p"], U_GOLD)) == want
    assert pipe.chunk_set(on).by_id["a1"].start == 0  # batas potongan, bukan unit alamat (H-064)


# ---------- S11 ----------
def test_S11_series_aggregate_through_calculator_header_adds_to_x_axis():
    doc, pipe, off, on = world(11)
    from backend.tests.header_grid_helpers import item

    items = [(item("i1", [(15, 20)]), ["c1", "c2", "c3", "c4"]), (item("i2", [(0, 5)]), ["c1", "c2", "c3", "c4"]),
             (item("i3", []), ["c3", "c4", "c2"])]
    pts = {}
    for s in (off, on):
        ms = [pipe.account(s, it, [(c, 1.0) for c in cs]).metrics for it, cs in items]
        assert ms[2].gold_chars == 0
        pts[s.header_b] = (ms, aggregate_points(ms, {s.setting_id: s})[0])
    assert (pts[False][0][2].retrieved_tokens, pts[True][0][2].retrieved_tokens) == (10, 9)  # i3 tidak ikut rata-rata (A12)
    p_off, p_on = pts[False][1], pts[True][1]
    assert (p_off.mean_span_recall, p_off.mean_retrieved_tokens, p_off.fully_covered_count) == (F(1), F(11), {"covered": 2, "total": 2})
    assert (p_on.mean_span_recall, p_on.mean_retrieved_tokens, p_on.fully_covered_count) == (F(1, 2), F(6), {"covered": 1, "total": 2})
    assert p_on.no_gold_count == 1


# ---------- S15 ----------
FX = {"f1": (0, 14), "f2": (12, 26), "f3": (24, 38), "f4": (36, 50), "f5": (48, 59)}
FX_H = {"f1": "F1 F2", "f2": "F3", "f3": "F4 F5 F6", "f4": "F7", "f5": "F8 F9"}
S15 = {
    5: ((("f2",), 5, 0, 5, F(2, 5)), ((), 0, 0, 0, None)),
    6: ((("f2",), 5, 0, 5, F(2, 5)), (("f2",), 5, 1, 6, F(1, 3))),
    10: ((("f2", "f1"), 10, 0, 10, F(1, 5)), (("f2",), 5, 1, 6, F(1, 3))),
    13: ((("f2", "f1"), 10, 0, 10, F(1, 5)), (("f2", "f1"), 10, 3, 13, F(2, 13))),
}


@pytest.mark.parametrize("b", sorted(S15))
def test_S15_fixed_size_twin_same_accounting(b):
    doc = doc_of(T)
    off = setting("fx", header=False, budget=b, chunker="fixed_size", size=5, overlap=1)
    on = twin(off)
    pipe = make_pipe(doc, [(off, FX)], make_store(FX_H, granularity="fixed_size"))
    c = ["f2", "f1", "f3", "f4", "f5"]
    for s, want in ((off, S15[b][0]), (on, S15[b][1])):
        rt = account(pipe, s, c, GOLD)
        got = (packed_ids(rt), source_tokens(rt, doc), header_tokens(rt, doc), rt.metrics.retrieved_tokens, rt.metrics.token_precision)
        assert got == want
        if "f2" in want[0]:
            assert (rt.metrics.span_recall, rt.metrics.gold_tokens_retrieved, rt.metrics.reciprocal_rank) == (F(1), 2, F(1))
            assert (rt.packed[0].start, rt.packed[0].end) == FX["f2"]  # offset tidak bergeser
    r_off, r_on = account(pipe, off, c, GOLD), account(pipe, on, c, GOLD)
    assert source_tokens(r_on, doc) <= source_tokens(r_off, doc)  # A8


def test_S15_mutant_header_f2_five_tokens_changes_result():
    doc = doc_of(T)
    on = twin(setting("fx", header=False, budget=6, chunker="fixed_size", size=5, overlap=1))
    pipe = make_pipe(doc, [(on, FX)], make_store({**FX_H, "f2": "X1 X2 X3 X4 X5"}, granularity="fixed_size"))
    assert packed_ids(account(pipe, on, ["f2", "f1"], GOLD)) == ()
