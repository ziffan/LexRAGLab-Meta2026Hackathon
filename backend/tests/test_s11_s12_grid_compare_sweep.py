"""M3.2-effort-sweep (H-103 S3 bagian B): S12 grid ulang per effort (`grid_compare`) dan S11 kebijakan cakupan sebagian
(`mask_threshold`/`mask_ref`, hanya profil sapuan; `strict` H-101 tak berubah). Dokumen mainan, encoder palsu, tanpa Model API."""

import json

import pytest

from backend import config as bc
from backend.grid.headers import HeaderBinding
from backend.header_b.compare_store import CompareError, build_identity
from backend.pipeline import grid_compare as gc
from backend.pipeline.pipeline import Pipeline
from backend.spark import ConfigInvalid, sweep_run
from backend.spark.sweep import merge_sweep
from backend.tests._chunk_util import ToyWs
from backend.tests.pipeline_fakes import FakeEncoder

from .h101_helpers import model_b
from .sweep_b_helpers import sweep_cfg
from .test_h101_grid_compare import M, main_binding, on_ids, run_cmp, run_main, store_of, tree, w  # noqa: F401


def sident(profile, sw):
    eff = merge_sweep(M, sw)
    return build_identity(profile, eff["profiles"][profile], eff, prompt_hash="ph", max_header_tokens=40, schema_max_length_chars=190)


def run_sweep(w, store, profile="sweep_meta_medium", sw=None, **kw):
    sw = sw if sw is not None else sweep_cfg()
    return run_cmp(w, store, profile=profile, identity=sident(profile, sw), sweep_cfg=sw, **{"encoder": FakeEncoder(), **kw}) \
        if False else gc.run_compare_grid("uupt", profile=profile, model_cfg=M, doc=w["doc"], tokenizer=ToyWs(), runs_dir=w["runs"],
                                          butir_dir=w["butir"], config_dir=w["cfg"], encoder=FakeEncoder(), embed_cache_dir=w["emb"],
                                          main_headers=main_binding(w), compare_store=store, identity=sident(profile, sw),
                                          sweep_cfg=sw, **kw)


def policy_cfg(policy, pct):
    sw = sweep_cfg()
    sw["compare"] = {"coverage_policy": policy, "coverage_threshold_pct": pct}
    return sw


# ------------------------------------------------------------------------------------------------ S12
def test_s12_per_effort_envelope_paths_keys_and_records(w):
    main = run_main(w)
    before = tree(w["runs"] / "grid")
    sw = policy_cfg("strict", 100)
    r1 = run_sweep(w, store_of(w, "Cmp"), "sweep_meta_medium", sw)
    r2 = run_sweep(w, store_of(w, "Cmp"), "sweep_meta_high", sw)
    assert r1.path == w["runs"] / "grid_compare" / "sweep_meta_medium" / f"{r1.key}.json"
    assert r2.path == w["runs"] / "grid_compare" / "sweep_meta_high" / f"{r2.key}.json"
    assert r1.key != r2.key != main.key and r1.key != main.key  # kunci memuat effort
    assert tree(w["runs"] / "grid") == before  # R/grid tidak berubah (S12 a)
    twins = on_ids(main.envelope)
    for r in (r1, r2):
        env = r.envelope
        assert on_ids(env) == twins and set(env["settings_requested"]) == twins and env["selections"] == {}
        assert env["off_ref"] == {"key": main.key, "path": f"runs/grid/{main.key}.json"}
    assert r1.envelope["compare"]["effort"] == "medium" and r2.envelope["compare"]["effort"] == "high"
    rec = r1.envelope["record"]
    assert (rec["kind"], rec["provider"], rec["effort"], rec["cost_usd_micros"]) == ("grid", "meta", "medium", 0)
    assert main.envelope["record"]["provider"] is None  # rekaman grid utama tetap provider null
    assert r1.envelope["label"] == "Header B: Contributor (effort medium)"
    # idempoten: cache hit tanpa menulis ulang
    raw = r1.path.read_bytes()
    again = run_sweep(w, store_of(w, "Cmp"), "sweep_meta_medium", sw)
    assert again.cache_hit and r1.path.read_bytes() == raw


def test_s12e_off_series_missing_and_store_missing(w):
    sw = policy_cfg("strict", 100)
    main = run_main(w)
    main.path.unlink()
    with pytest.raises(CompareError) as ei0:
        run_sweep(w, store_of(w, "Cmp"), "sweep_meta_medium", sw)
    assert ei0.value.code == "off_series_missing" and not (w["runs"] / "grid_compare").exists()
    run_main(w)
    with pytest.raises(CompareError) as ei:
        gc.run_compare_grid("uupt", profile="sweep_meta_medium", model_cfg=M, doc=w["doc"], tokenizer=ToyWs(), runs_dir=w["runs"],
                            butir_dir=w["butir"], config_dir=w["cfg"], encoder=FakeEncoder(), embed_cache_dir=w["emb"],
                            main_headers=main_binding(w), compare_store=store_of(w, "Cmp"), sweep_cfg=sw)
    assert ei.value.code == "compare_store_missing"


# ------------------------------------------------------------------------------------------------ S11
def target(w, main):
    """(setting_id twin structure_handwritten, daftar chunk_id urut dokumen)."""
    gcfg, rcfg = bc.load("grid", w["cfg"]), bc.load("retrieval", w["cfg"])
    pipe = Pipeline(w["doc"], tokenizer=ToyWs(), retrieval_cfg=rcfg, grid_cfg=gcfg, headers=main_binding(w))
    from backend.grid.types import Setting
    sd = next(s for s in main.envelope["settings_run"] if s["header_b"] and s["chunker"] == "structure_handwritten")
    st = Setting(**sd)
    return sd["setting_id"], [c.chunk_id for c in sorted(pipe.chunk_set(st).chunks, key=lambda c: (c.start, c.end, c.chunk_id))]


def drop(store, ids):
    for cid in ids:
        store.records.pop(cid, None)
    return store


def test_s11_boundary_inclusive_and_below_threshold_is_header_missing(w):
    main = run_main(w)
    sid, ids = target(w, main)
    n = len(ids)
    ok_pct = (n - 1) * 100 // n  # (n-1) x 100 >= ok_pct x n (inklusif)
    assert (n - 1) * 100 >= ok_pct * n and (n - 1) * 100 < (ok_pct + 1) * n
    res = run_sweep(w, drop(store_of(w, "Cmp"), ids[:1]), "sweep_meta_medium", policy_cfg("mask_threshold", ok_pct))
    rep = res.envelope["coverage"]["settings"][sid]
    assert rep == {"chunks": n, "headered": n - 1, "coverage_bp": (n - 1) * 10000 // n, "missing": ids[:1]}
    assert res.envelope["coverage"]["policy"] == "mask_threshold" and res.envelope["coverage"]["threshold_pct"] == ok_pct
    assert sid in {p["setting_id"] for p in res.envelope["points"]}  # GridPoint dibuat
    assert not [f for f in res.envelope["failed_settings"] if f["setting_id"] == sid]
    md, _ = gc.write_report(w["runs"], "sweep_meta_medium", res.envelope)
    assert "partial header coverage" in md.read_text(encoding="utf-8")
    # di bawah ambang: tetap header_missing (chunk_id pertama yang hilang, urut dokumen), tanpa GridPoint
    w2 = w
    bad = run_sweep(w2, drop(store_of(w2, "Cmp"), ids[:1]), "sweep_meta_medium", policy_cfg("mask_threshold", ok_pct + 1))
    fs = [f for f in bad.envelope["failed_settings"] if f["setting_id"] == sid]
    assert fs == [{"setting_id": sid, "reason": "header_missing", "chunk_id": ids[0]}]
    assert sid not in {p["setting_id"] for p in bad.envelope["points"]}
    assert bad.envelope["coverage"]["settings"][sid]["coverage_bp"] == (n - 1) * 10000 // n
    assert bad.envelope["coverage"]["settings"][sid]["below_threshold"] is True


def test_s11_masked_chunk_is_indexed_as_header_off_text(w):
    run_main(w)
    gcfg, rcfg = bc.load("grid", w["cfg"]), bc.load("retrieval", w["cfg"])
    main = main_binding(w)
    from backend.grid.types import Setting
    envm = json.loads(next((w["runs"] / "grid").glob("*.json")).read_text(encoding="utf-8"))
    sd = next(s for s in envm["settings_run"] if s["header_b"] and s["chunker"] == "structure_handwritten")
    st = Setting(**sd)
    store = store_of(w, "Cmp")
    base_pipe = Pipeline(w["doc"], tokenizer=ToyWs(), retrieval_cfg=rcfg, grid_cfg=gcfg, headers=main)
    cid = sorted(base_pipe.chunk_set(st).chunks, key=lambda c: c.start)[0]
    cb = HeaderBinding(drop(store, [cid.chunk_id]), "ayat", "all", "ph", "m", coverage=("mask_threshold", 1))
    pipe = Pipeline(w["doc"], tokenizer=ToyWs(), retrieval_cfg=rcfg, grid_cfg=gcfg, headers=cb)
    view = pipe.index(st)
    first = next(c for c in view.chunks if c.chunk_id == cid.chunk_id)
    text = view.doc.text[first.start:first.end]
    assert text == w["doc"].text[cid.start:cid.end]  # teks header-OFF persis, tanpa awalan header/placeholder
    other = view.chunks[1]
    assert view.doc.text[other.start:other.end].startswith("Cmp ")  # potongan ber-header tetap memakai header pembanding
    assert pipe.coverage_report[st.setting_id]["missing"] == [cid.chunk_id]


def test_s11_policy_changes_key_and_strict_key_is_h101(w):
    main = run_main(w)
    sid, ids = target(w, main)
    k = {}
    for pol, pct in (("strict", 100), ("mask_threshold", 95), ("mask_ref", 95), ("mask_ref", 90)):
        k[(pol, pct)] = run_sweep(w, store_of(w, "Cmp"), "sweep_meta_medium", policy_cfg(pol, pct)).key
    assert len(set(k.values())) == 4  # dua kebijakan/ambang tidak saling cache-hit
    strict = run_sweep(w, store_of(w, "Cmp"), "sweep_meta_medium", policy_cfg("strict", 100)).envelope
    assert "policy" not in strict["compare"] and "settings" not in strict["coverage"]  # strict: blok compare tanpa kunci `policy`


def test_s11_mask_ref_writes_masked_contributor_reference(w):
    main = run_main(w)
    sid, ids = target(w, main)
    n = len(ids)
    res = run_sweep(w, drop(store_of(w, "Cmp"), ids[:1]), "sweep_meta_medium", policy_cfg("mask_ref", (n - 1) * 100 // n))
    assert res.ref_path is not None and res.ref_path.name.startswith("ref-") and res.ref_path.parent == res.path.parent
    ref = json.loads(res.ref_path.read_text(encoding="utf-8"))
    assert ref["label"] == "Header B: Contributor (low), masked as sweep_meta_medium" and ids[0] in ref["masked"]
    assert sid in {p["setting_id"] for p in ref["points"]}
    assert not (w["runs"] / "grid" / res.ref_path.name).exists()  # amplop utama tidak tertulis
    assert (w["runs"] / "grid" / f"{main.key}.json").exists()
    # tanpa mask_ref (mask_threshold) tidak ada berkas rujukan
    w_ = res.path.parent
    assert len(list(w_.glob("ref-*.json"))) == 1


def test_s11_non_sweep_profile_is_strict_and_never_reads_sweep_file(w, monkeypatch):
    monkeypatch.setattr(sweep_run, "load_sweep", lambda *a, **k: (_ for _ in ()).throw(AssertionError("sweep file read")))
    main = run_main(w)
    res = run_cmp(w, store_of(w, "Cmp"))  # baseten_open, strict H-101
    assert "policy" not in res.envelope["compare"] and res.ref_path is None
    assert set(res.envelope["coverage"]) == {"sources_run", "sources_not_run"}


@pytest.mark.parametrize("cfg", [
    {"coverage_policy": "mask_ref", "coverage_threshold_pct": 0},
    {"coverage_policy": "mask_ref", "coverage_threshold_pct": 101},
    {"coverage_policy": "mask_ref", "coverage_threshold_pct": "95"},
    {"coverage_policy": "mask_ref", "coverage_threshold_pct": 95.0},
    {"coverage_policy": "mask_ref", "coverage_threshold_pct": True},
    {"coverage_policy": "lain", "coverage_threshold_pct": 95},
])
def test_s11g_invalid_policy_config_is_config_invalid(cfg):
    sw = sweep_cfg()
    sw["compare"] = cfg
    with pytest.raises(ConfigInvalid):
        sweep_run.coverage_policy(sw)


def test_s11g_threshold_100_is_valid_and_default_is_strict():
    assert sweep_run.coverage_policy({"compare": {"coverage_policy": "mask_threshold", "coverage_threshold_pct": 100}}) == ("mask_threshold", 100)
    assert sweep_run.coverage_policy(None) == ("strict", 100) and sweep_run.coverage_policy({"version": 1}) == ("strict", 100)


def test_s11a_integer_arithmetic_200_chunks():
    assert sweep_run.covered(190, 200, 95) and sweep_run.coverage_bp(190, 200) == 9500
    assert not sweep_run.covered(189, 200, 95) and sweep_run.coverage_bp(189, 200) == 9450
    assert sweep_run.coverage_bp(8, 10) == 8000
