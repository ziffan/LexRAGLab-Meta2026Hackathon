"""M3.2 galat header: S4 (a)(b)(c), S5, S9 (c)(d)(e) (docs/scenarios/M3.2.md rev. 4)."""

from dataclasses import replace

import pytest

from backend.grid.headers import (FailedSetting, HeaderGranularityError, HeaderInvalidError, HeaderMissingError,
                                  HeaderStaleError)
from backend.grid.runner import MemoryGridCache, run_grid
from backend.tests.grid_helpers import SIMPLICITY
from backend.tests.header_grid_helpers import F, account, doc_of, item, make_pipe, make_store, packed_ids, setting, twin
from backend.tests.test_grid_header_accounting import FX, FX_H, SA_CH, SA_H, SP_CH, SP_H, U_GOLD, CH, HDR
from backend.tests.toy_ws import T, U


def grid(pipe, settings, items=None):
    items = items or [item("i1", [(15, 20)], "a5 a6"), item("i2", [(3, 5)], "a1")]
    cache = MemoryGridCache()
    r = run_grid(settings=settings, items=items, pipeline=pipe, cache=cache, clean_sha256="X", config_hash="C",
                 split_record=None, simplicity=SIMPLICITY, family="akta", header_scope="all")
    return r, cache


def metric_ids(r):
    return {m.setting_id for m in r.metrics}


# ---------- S4 ----------


def test_S4a_missing_header_outside_P_is_error_run_continues():
    doc = doc_of(T)
    st = setting("st", header=False, budget=12)
    other = setting("other", header=False, budget=12, chunker="fixed_size", size=5, overlap=1)
    store = make_store({"c1": "H1 H2", "c2": "H3", "c3": "H4 H5 H6", **FX_H}, granularity="ayat")
    for cid, r in make_store(FX_H, granularity="fixed_size").records.items():
        store.records[cid] = r
    pipe = make_pipe(doc, [(st, CH), (other, FX)], store, granularity="ayat")
    on, other_on = twin(st), twin(other)
    with pytest.raises(HeaderMissingError) as e:
        account(pipe, on, ["c1", "c2"])  # c4 di luar C dan P tetap galat
    assert e.value.chunk_id == "c4" and "c4" in str(e.value) and on.setting_id in str(e.value)
    r, cache = grid(pipe, [st, on, other, other_on])
    assert r.failed_settings == (FailedSetting(on.setting_id, "header_missing", "c4"),)
    assert metric_ids(r) == {"st", "other", other_on.setting_id}  # tanpa GridPoint untuk setting gagal
    assert {p.setting_id for p in r.points} == metric_ids(r)
    assert not any(d.get("setting_id") == on.setting_id for d in cache.get(r.grid_run_id) if "setting_id" in d)


def test_S4b_empty_header_is_invalid_not_free():
    doc = doc_of(T)
    st = setting("st", header=False, budget=12)
    pipe = make_pipe(doc, [(st, CH)], make_store({**HDR, "c2": ""}))
    on = twin(st)
    with pytest.raises(HeaderInvalidError) as e:
        account(pipe, on, ["c1", "c2"])
    assert e.value.chunk_id == "c2" and on.setting_id in str(e.value)
    r, _ = grid(pipe, [st, on])
    assert r.failed_settings == (FailedSetting(on.setting_id, "header_invalid", "c2"),) and metric_ids(r) == {"st"}


def test_S4c_fixed_size_twin_missing_header_same_error_f4_first():
    doc = doc_of(T)
    fx = setting("fx", header=False, budget=12, chunker="fixed_size", size=5, overlap=1)
    st = setting("st", header=False, budget=12)
    hdr = {k: v for k, v in FX_H.items() if k != "f4"}
    store = make_store(hdr, granularity="fixed_size")
    store.records.update(make_store(HDR, granularity="ayat").records)
    pipe = make_pipe(doc, [(fx, FX), (st, CH)], store)
    fx_on, st_on = twin(fx), twin(st)
    r, _ = grid(pipe, [fx, fx_on, st, st_on])
    assert r.failed_settings == (FailedSetting(fx_on.setting_id, "header_missing", "f4"),)
    assert metric_ids(r) == {"fx", "st", st_on.setting_id}  # kembaran off fixed_size dan setting lain tetap jalan
    with pytest.raises(HeaderMissingError, match="f4"):
        pipe.headers_for(fx_on)


# ---------- S5 ----------
def s5(clean_grid, *, store_clean="X", ids=("idP", "idQ")):
    doc = doc_of(T, clean=clean_grid)
    p = setting("P", header=False, budget=6)
    q = setting("Q", header=False, budget=6, chunker="fixed_size", size=3, overlap=0)
    pipe = make_pipe(doc, [(p, {ids[0]: (0, 11)}), (q, {ids[1]: (0, 11)})], make_store({ids[0]: "H1 H2"}, run_clean=store_clean))
    return pipe, twin(p), twin(q)


def test_S5a_header_found_by_chunk_id_cost_included():
    pipe, p_on, _ = s5("X")
    rt = account(pipe, p_on, ["idP"], [(0, 11)])
    assert rt.metrics.retrieved_tokens == 6 and packed_ids(rt) == ("idP",)


def test_S5b_other_chunker_key_does_not_borrow_header_by_span():
    pipe, _, q_on = s5("X")
    with pytest.raises(HeaderMissingError, match="idQ"):
        account(pipe, q_on, ["idQ"], [(0, 11)])


def test_S5c_stale_header_from_other_clean_text_rejected_with_both_hashes():
    pipe, p_on, _ = s5("Y", store_clean="X")
    with pytest.raises(HeaderStaleError) as e:
        account(pipe, p_on, ["idP"], [(0, 11)])
    assert "'X'" in str(e.value) and "'Y'" in str(e.value) and e.value.chunk_id == "idP"
    r, _ = grid(pipe, [replace(p_on, header_b=False, setting_id="P"), p_on])
    assert r.failed_settings == (FailedSetting("P+", "header_stale", "idP"),) and metric_ids(r) == {"P"}


def test_S5_unknown_run_record_is_stale_not_trusted():
    pipe, p_on, _ = s5("X")
    pipe.headers.store.runs.clear()
    with pytest.raises(HeaderStaleError):
        pipe.headers_for(p_on)


# ---------- S9 (c)(d)(e) ----------
def test_S9c_SA_with_pasal_store_is_missing_error():
    doc = doc_of(U)
    sa = setting("sa", header=False, budget=10)
    pipe = make_pipe(doc, [(sa, SA_CH)], make_store(SP_H, granularity="pasal"), granularity="ayat")
    with pytest.raises(HeaderMissingError):
        pipe.headers_for(twin(sa))


def test_S9d_SP_with_ayat_store_is_missing_error():
    doc = doc_of(U)
    sp = setting("sp", header=False, budget=10)
    pipe = make_pipe(doc, [(sp, SP_CH)], make_store(SA_H, granularity="ayat"), granularity="pasal")
    with pytest.raises(HeaderMissingError):
        pipe.headers_for(twin(sp))


def test_S9e_same_chunk_id_different_granularity_label_is_error_with_both_values():
    doc = doc_of(U)
    sq = setting("sq", header=False, budget=10)
    pipe = make_pipe(doc, [(sq, SA_CH)], make_store(SA_H, granularity="ayat"), granularity="pasal")
    with pytest.raises(HeaderGranularityError) as e:
        pipe.headers_for(twin(sq))
    assert "ayat" in str(e.value) and "pasal" in str(e.value)
    r, _ = grid(pipe, [sq, twin(sq)])
    assert r.failed_settings[0].reason == "granularity_mismatch" and metric_ids(r) == {"sq"}


def test_S9_header_looked_up_by_chunk_id_not_span():
    # PK2 dan PK2p berbagi span [52,76): header dipilih menurut chunk_id (teks header dipakai, bukan sekadar token)
    doc = doc_of(U)
    sa = setting("sa", header=False, budget=10)
    pipe = make_pipe(doc, [(sa, SA_CH)], make_store({**SA_H, "PK2p": "ZZ YY XX"}, granularity="ayat"), granularity="ayat")
    assert pipe.headers_for(twin(sa))["PK2p"] == "ZZ YY XX"
