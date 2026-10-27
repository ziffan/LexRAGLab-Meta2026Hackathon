"""M3.2 amplop grid dengan header B (run_family_grid, dokumen mainan U): label deret per titik, scope, failed_settings,
config_hash memuat identitas header. Tanpa Model API."""

import pytest

from backend import config as bc
from backend.grid.expand import expand_grid
from backend.grid.headers import HeaderBinding, MemoryHeaderStore, twin_key
from backend.pipeline.grid_run import load_header_binding, run_family_grid
from backend.pipeline.pipeline import Pipeline
from backend.tests._chunk_util import ToyWs, u_doc
from backend.tests.pipeline_fakes import FakeEncoder, toy_config_dir, write_toy_butir


@pytest.fixture()
def w(tmp_path):
    doc = u_doc()
    cfg = toy_config_dir(tmp_path / "cfg")
    butir = tmp_path / "butir"
    write_toy_butir(butir, doc.clean_sha256)
    return {"doc": doc, "cfg": cfg, "butir": butir, "runs": tmp_path / "runs", "emb": tmp_path / "emb"}


def full_store(w, *, drop_hand=False):
    gcfg, rcfg = bc.load("grid", w["cfg"]), bc.load("retrieval", w["cfg"])
    pipe = Pipeline(w["doc"], tokenizer=ToyWs(), retrieval_cfg=rcfg, grid_cfg=gcfg)
    store = MemoryHeaderStore({}, {"bT": w["doc"].clean_sha256})
    for s in expand_grid(gcfg, "uupt"):
        if s.header_b or s.chunker not in ("structure_handwritten", "fixed_size"):
            continue
        gran = "fixed_size" if s.chunker == "fixed_size" else "ayat"
        for c in pipe.chunk_set(s).chunks:
            if drop_hand and s.chunker == "structure_handwritten":
                continue
            store.records[c.chunk_id] = {"chunk_id": c.chunk_id, "header": f"Hdr {c.start}", "granularity": gran, "run_id": "bT"}
    return store


def go(w, binding):
    return run_family_grid("uupt", doc=w["doc"], tokenizer=ToyWs(), runs_dir=w["runs"], butir_dir=w["butir"], config_dir=w["cfg"],
                           encoder=FakeEncoder(), embed_cache_dir=w["emb"], headers=binding)


def test_default_without_binding_keeps_m1_behaviour_and_empty_failed_list(w):
    res = go(w, None)
    assert res.record["failed_settings"] == [] and all(p["header_b"] is False for p in res.envelope["points"])
    assert len(res.envelope["settings_run"]) == 12 and len(res.envelope["skipped"]) == 24


def test_frontier_only_envelope_labels_series_and_runs_only_frontier_twins(w):
    b = HeaderBinding(full_store(w), "ayat", "frontier_only", "ph", "m")
    res = go(w, b)
    env = res.envelope
    assert res.record["failed_settings"] == [] and all(isinstance(p["header_b"], bool) for p in env["points"])
    by_id = {s["setting_id"]: s for s in env["settings_run"]}
    on_ids = {i for i, s in by_id.items() if s["header_b"]}
    assert on_ids and {p["setting_id"] for p in env["points"] if p["header_b"]} == on_ids
    from backend.grid.types import Setting

    settings = {i: Setting(**x) for i, x in by_id.items()}
    tune_off = {p["setting_id"] for p in env["points"] if p["split"] == "tune" and not p["header_b"]}
    off_front = {sid for f in env["frontiers"] if f["split"] == "tune" for sid in f["point_ids"] if not by_id[sid]["header_b"]}
    # tiap kembaran on yang dieksekusi berasal dari setting off yang ada di frontier gabungan tune (frontier off hanya
    # bisa lebih besar dari irisan ini, karena titik on ikut mendominasi): batas atas = tune_off
    assert all(twin_key(settings[i]) in {twin_key(settings[j]) for j in tune_off} for i in on_ids)
    assert len(on_ids) <= len(tune_off) and off_front <= tune_off
    assert env["record"]["kind"] == "grid"
    again = go(w, b)
    assert again.cache_hit and again.envelope["record"]["failed_settings"] == []


def test_scope_all_with_incomplete_store_records_failed_settings_no_points(w):
    b = HeaderBinding(full_store(w, drop_hand=True), "ayat", "all", "ph", "m")
    res = go(w, b)
    fs = res.record["failed_settings"]
    assert fs and all(f["reason"] == "header_missing" and f["chunk_id"] for f in fs)
    by_id = {s["setting_id"]: s for s in res.envelope["settings_run"]}
    failed_ids = {f["setting_id"] for f in fs}
    assert failed_ids.isdisjoint(by_id) and failed_ids.isdisjoint({p["setting_id"] for p in res.envelope["points"]})
    assert all(by_id[i]["chunker"] == "fixed_size" for i in by_id if by_id[i]["header_b"])  # fixed_size on tetap jalan
    assert len(by_id) + len(failed_ids) == 24  # 2 chunker x 3 mode x 2 header x 2 anggaran


def test_config_hash_differs_by_scope_and_header_content(w):
    a = go(w, HeaderBinding(full_store(w), "ayat", "all", "ph", "m"))
    b = go(w, HeaderBinding(full_store(w), "ayat", "frontier_only", "ph", "m"))
    c = go(w, None)
    assert len({a.key, b.key, c.key}) == 3


def test_load_header_binding_reads_scope_from_config(w):
    b = load_header_binding(runs_dir=w["runs"])
    assert b.scope == "frontier_only" and b.granularity in ("pasal", "ayat") and b.prompt_hash and b.model


def test_dir_header_store_cross_granularity_and_run_id_path_guard(tmp_path):
    import json

    from backend.grid.headers import DirHeaderStore

    hd, runs = tmp_path / "h", tmp_path / "runs"
    for g, cid in (("ayat", "c1"), ("pasal", "c1"), ("fixed_size", "f1")):
        d = hd / g / "abcdef123456"
        d.mkdir(parents=True)
        (d / f"{cid}.json").write_text(json.dumps({"chunk_id": cid, "header": f"h-{g}", "run_id": "r1"}), encoding="utf-8")
    (runs / "spark" / "records").mkdir(parents=True)
    (runs / "spark" / "records" / "r1.json").write_text(json.dumps({"clean_sha256": "X"}), encoding="utf-8")
    (runs / "secret.json").write_text(json.dumps({"clean_sha256": "LEAK"}), encoding="utf-8")
    st = DirHeaderStore(hd, "abcdef123456" + "0" * 52, runs)
    assert st.get("c1", "ayat")["granularity"] == "ayat" and st.get("c1", "pasal")["granularity"] == "pasal"
    assert st.get("f1", "ayat")["granularity"] == "fixed_size"  # ditemukan di dir lain -> label asli (S9e)
    assert st.get("zz", "ayat") is None and st.get("../x", "ayat") is None
    assert st.run_clean_sha256("r1") == "X" and st.run_clean_sha256("../../secret") is None and st.run_clean_sha256("nope") is None
    assert st.content_hash() == DirHeaderStore(hd, "abcdef123456" + "0" * 52, runs).content_hash()
