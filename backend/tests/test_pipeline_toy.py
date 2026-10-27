"""Pipeline M1 dan run grid ujung ke ujung dengan tokenizer `toy-ws` dan encoder palsu (INT-a). Tanpa GPU dan jaringan."""

from __future__ import annotations

import re

import json
from fractions import Fraction

import pytest

from backend.grid.expand import expand_grid
from backend.grid.types import GridItem
from backend.metrics.item import recall_at_k_item
from backend.metrics.types import RankedChunk
from backend.pipeline.grid_run import GridRunError, load_items, make_plan, run_family_grid, to_grid_items
from backend.pipeline.pipeline import Pipeline, SettingNotAvailable, unavailable_reason

from ._chunk_util import ToyWs, u_doc
from .pipeline_fakes import TOY_ITEMS, FakeEncoder, toy_config_dir, write_toy_butir


@pytest.fixture()
def world(tmp_path):
    doc = u_doc()
    cfg = toy_config_dir(tmp_path / "cfg")
    butir = tmp_path / "butir"
    write_toy_butir(butir, doc.clean_sha256)
    return {"doc": doc, "cfg": cfg, "butir": butir, "runs": tmp_path / "runs", "emb": tmp_path / "emb"}


def run(w, enc=None, pipeline_out=None):
    enc = enc or FakeEncoder()
    return run_family_grid("uupt", doc=w["doc"], tokenizer=ToyWs(), runs_dir=w["runs"], butir_dir=w["butir"], config_dir=w["cfg"],
                           encoder=enc, embed_cache_dir=w["emb"], pipeline_out=pipeline_out), enc


def strip_record(env):
    return {k: v for k, v in env.items() if k != "record"}


def test_end_to_end_grid_record_files_and_skips(world):
    res, enc = run(world)
    r = res.record
    assert (r["kind"], r["status"], r["cost_usd_micros"], r["packing"]) == ("grid", "ok", 0, "stop")
    assert r["tokenizer"] == {"name": "toy-ws", "version": "1"} and r["host"] == "authoritative" and r["device"] == "cpu"
    assert {k: r["embedder"][k] for k in ("name", "revision", "max_seq_length", "n_truncated")} == {
        "name": "fake-enc", "revision": "r0", "max_seq_length": 8192, "n_truncated": 0}
    assert r["usage_input_tokens"] is None and r["model"] is None and r["created_at"].endswith("Z")
    assert r["cache_key"] == res.key and res.path == world["runs"] / "grid" / f"{res.key}.json" and res.path.is_file()
    env = res.envelope
    # 36 titik G6a: hanya structure_handwritten + fixed_size dengan header B off yang berjalan
    assert len(env["settings_run"]) == 12 and len(env["skipped"]) == 24
    assert {(s["chunker"], s["header_b"]) for s in env["settings_run"]} == {("structure_handwritten", False), ("fixed_size", False)}
    reasons = {(s["chunker"], s["header_b"]): s["reason"] for s in env["skipped"]}
    assert "schema A" in reasons[("structure_schema", False)] and "header B" in reasons[("fixed_size", True)]
    assert all(s["reason"] for s in env["skipped"])
    # split tersimpan di runs/split, kontrol di held-out >= 3 (config)
    assert (world["runs"] / "split" / "split_uupt_v0001.json").is_file()
    sp = env["split"]
    assert sp["control_in_held_out"] >= 3 and len(sp["assignments"]) == 10
    # frontier per (split, anggaran) dan pilihan hanya di tune, per anggaran
    assert {(f["split"], f["budget_tokens"]) for f in env["frontiers"]} == {(s, b) for s in ("tune", "held_out") for b in (2000, 1000)}
    assert sorted(env["selections"]) == ["1000", "2000"]
    for sel in env["selections"].values():
        assert sel["tune_point"]["split"] == "tune" and (sel["held_out_point"] is None or sel["held_out_point"]["split"] == "held_out")
    assert enc.encode_calls > 0


def test_determinism_two_fresh_runs_identical(world, tmp_path):
    a, _ = run(world)
    w2 = {**world, "runs": tmp_path / "runs2", "emb": tmp_path / "emb2"}
    b, _ = run(w2)
    assert a.key == b.key
    assert strip_record(a.envelope) == strip_record(b.envelope)


def test_second_run_same_key_computes_nothing(world):
    out1, out2 = [], []
    a, enc = run(world, pipeline_out=out1)
    calls, texts = enc.encode_calls, enc.texts_encoded
    assert out1[0].calls == 12 and calls > 0
    before = a.path.read_bytes()
    b, enc2 = run(world, enc=enc, pipeline_out=out2)
    assert b.cache_hit is True and b.record["status"] == "cached" and a.record["status"] == "ok"
    assert out2 == []  # tidak ada Pipeline dibuat: tidak ada chunking, ranking, atau pengemasan
    assert (enc.encode_calls, enc.texts_encoded) == (calls, texts)
    assert a.path.read_bytes() == before  # berkas tidak ditulis ulang
    assert strip_record(b.envelope) == strip_record(a.envelope) and b.key == a.key


def test_changed_item_query_changes_cache_key(world):
    a, _ = run(world)
    lines = (world["butir"] / "uupt.v1.jsonl").read_text(encoding="utf-8").split("\n")
    d = json.loads(lines[0])
    d["query"] = "Aaa bbb ccc"
    lines[0] = json.dumps(d, sort_keys=True)
    (world["butir"] / "uupt.v1.jsonl").write_text("\n".join(lines), encoding="utf-8", newline="\n")
    b, _ = run(world)
    assert b.key != a.key and b.cache_hit is False


def test_quality_selected_vs_baseline_uses_production_recall(world):
    res, _ = run(world)
    env = res.envelope
    by_id = {s["setting_id"]: s for s in env["settings_run"]}
    assert env["quality_comparison"]
    for c in env["quality_comparison"]:
        sel, base = by_id[c["selected_setting_id"]], by_id[c["baseline_setting_id"]]
        assert base["chunker"] == "fixed_size" and (base["retrieval_mode"], base["budget_tokens"]) == (sel["retrieval_mode"], sel["budget_tokens"])
        assert c["selected"]["k"] == 5 and c["selected"]["setting_id"] == sel["setting_id"]
        # Recall@K tersimpan = rata-rata recall_at_k per butir (ItemMetrics) atas butir bergold, semua split
        ms = [m for m in env["metrics"] if m["setting_id"] == sel["setting_id"] and m["gold_chars"] > 0]
        exp = sum((Fraction(m["parts_hit"], m["parts_total"]) for m in ms), Fraction(0)) / len(ms)
        assert c["selected"]["recall_at_k"] == pytest.approx(float(exp), abs=1e-12)
    assert len(env["quality"]) == 12


def test_pipeline_item_metrics_toy_hand_check(world):
    """Pengecekan tangan pada dokumen mainan: struktur + bm25, butir t01 'Aaa bbb' -> unit Pasal 1 ayat (1) ada di peringkat 1."""
    doc, cfg = u_doc(), None
    from backend import config as bc
    p = Pipeline(doc, tokenizer=ToyWs(), retrieval_cfg=bc.load("retrieval", world["cfg"]), grid_cfg=bc.load("grid", world["cfg"]))
    st = next(s for s in expand_grid(bc.load("grid", world["cfg"]), "uupt") if s.chunker == "structure_handwritten" and s.retrieval_mode == "bm25"
              and s.budget_tokens == 2000 and not s.header_b)
    items = to_grid_items(load_items("uupt", world["butir"])[0])
    ms = p(st, items)
    assert [m.item_id for m in ms] == [i.id for i in items]
    t01 = next(m for m in ms if m.item_id == "t01")
    assert t01.span_recall == 1 and t01.rank == 1 and t01.recall_at_k == 1
    t09 = next(m for m in ms if m.item_id == "t09")
    assert t09.gold_chars == 0 and t09.span_recall is None and t09.recall_at_k is None
    # fungsi produksi Recall@K per butir sama dengan yang dihitung pipeline
    rt = p.retrieve(st, next(i for i in items if i.id == "t06"))
    cs = p.chunk_set(st)
    ranked = [RankedChunk(cs.by_id[c].start, cs.by_id[c].end, "", c) for c, _ in rt.ranking]
    assert recall_at_k_item([(12, 24), (25, 37), (38, 50)], ranked, p.k, cs.units) == rt.metrics.recall_at_k


def test_unavailable_settings_and_single_tokenizer(world):
    from backend import config as bc
    gcfg = bc.load("grid", world["cfg"])
    settings = expand_grid(gcfg, "uupt")
    schema = next(s for s in settings if s.chunker == "structure_schema")
    hdr = next(s for s in settings if s.header_b)
    assert "schema A" in unavailable_reason(schema) and "header B" in unavailable_reason(hdr)
    p = Pipeline(u_doc(), tokenizer=ToyWs(), retrieval_cfg=bc.load("retrieval", world["cfg"]), grid_cfg=gcfg)
    with pytest.raises(SettingNotAvailable):
        p.chunk_set(schema)
    with pytest.raises(SettingNotAvailable):
        p.chunk_set(hdr)
    ok = next(s for s in settings if s.chunker == "fixed_size" and s.retrieval_mode == "bm25" and not s.header_b)
    items = [GridItem("x", "uupt", "operator", "literal", gold_spans=((12, 24),), query="Aaa")]
    assert len(p(ok, items)) == 1
    p.tok.info = type("I", (), {"name": "toy-ws", "version": "2"})()  # tokenizer berganti di tengah perbandingan
    with pytest.raises(ValueError, match="different tokenizers"):
        p(ok, items)


def test_dense_needs_encoder(world):
    from backend import config as bc
    gcfg = bc.load("grid", world["cfg"])
    st = next(s for s in expand_grid(gcfg, "uupt") if s.chunker == "fixed_size" and s.retrieval_mode == "dense" and not s.header_b)
    p = Pipeline(u_doc(), tokenizer=ToyWs(), retrieval_cfg=bc.load("retrieval", world["cfg"]), grid_cfg=gcfg)
    with pytest.raises(ValueError, match="encoder"):
        p(st, [GridItem("x", "uupt", "operator", "literal", gold_spans=((12, 24),), query="Aaa")])


def test_plan_rejects_items_for_other_clean_text(world):
    doc = u_doc()
    write_toy_butir(world["butir"], "0" * 64)
    with pytest.raises(GridRunError, match="different clean text"):
        make_plan("uupt", doc=doc, tokenizer=ToyWs(), butir_dir=world["butir"], runs_dir=world["runs"], config_dir=world["cfg"], create_split=False)


def test_make_plan_without_creating_split_writes_nothing(world):
    plan = make_plan("uupt", doc=u_doc(), tokenizer=ToyWs(), butir_dir=world["butir"], runs_dir=world["runs"], config_dir=world["cfg"],
                     create_split=False)
    assert plan.split is None and plan.key is None and not world["runs"].exists()
    assert len(plan.settings) == 36 and len(plan.runnable) == 12 and len(plan.skipped) == 24
    assert len(TOY_ITEMS) == len(plan.items)


# ---- Putaran 2 (review Tier 1 INT-a) ----
def _set_recall_scope(cfg_dir, scope):
    p = cfg_dir / "retrieval.toml"
    t = p.read_bytes().decode("utf-8")
    t2, n = re.subn(r'(?m)^recall_items = "[a-z_]+"', f'recall_items = "{scope}"', t)
    assert n == 1
    p.write_bytes(t2.encode("utf-8"))


@pytest.mark.parametrize("scope", ["all", "tune", "held_out"])
def test_quality_recall_items_scope_is_configurable_and_labelled(world, scope):
    """SHOULD-1: cakupan butir Recall@K dari config, berlabel; mutan 'selalu tune' mati karena jumlah butir berbeda."""
    _set_recall_scope(world["cfg"], scope)
    res, _ = run(world)
    env = res.envelope
    for q in env["quality"]:
        ms = [m for m in env["metrics"] if m["setting_id"] == q["setting_id"] and m["gold_chars"] > 0 and (scope == "all" or m["split"] == scope)]
        exp = sum((Fraction(m["parts_hit"], m["parts_total"]) for m in ms), Fraction(0)) / len(ms)
        assert q["items_scope"] == scope and q["recall_n_items"] == len(ms)
        assert q["recall_at_k"] == pytest.approx(float(exp), abs=1e-12)
    counts = {q["recall_n_items"] for q in env["quality"]}
    assert len(counts) == 1 and counts.pop() == {"all": 9, "tune": sum(1 for m in env["metrics"] if m["setting_id"] == env["quality"][0]["setting_id"] and m["split"] == "tune" and m["gold_chars"] > 0), "held_out": sum(1 for m in env["metrics"] if m["setting_id"] == env["quality"][0]["setting_id"] and m["split"] == "held_out" and m["gold_chars"] > 0)}[scope]
    for c in env["quality_comparison"]:
        assert c["selected"]["items_scope"] == scope and c["baseline"]["items_scope"] == scope


def test_quality_recall_items_invalid_scope_is_an_error(world):
    _set_recall_scope(world["cfg"], "all")
    p = world["cfg"] / "retrieval.toml"
    p.write_bytes(p.read_bytes().replace(b'recall_items = "all"', b'recall_items = "bogus"'))
    with pytest.raises(GridRunError, match="recall_items"):
        run(world)


def test_tokenizer_info_enters_run_config_hash_and_key(world):
    """SHOULD-2 (M08): tokenizer versi lain -> config_hash dan kunci run lain."""
    class Tok2(ToyWs):
        info = type("I", (), {"name": "toy-ws", "version": "2"})()

    def plan(tok):
        run(world)  # membuat split
        return make_plan("uupt", doc=world["doc"], tokenizer=tok, butir_dir=world["butir"], runs_dir=world["runs"], config_dir=world["cfg"],
                         create_split=False)
    a, b = plan(ToyWs()), plan(Tok2())
    assert a.config_hash != b.config_hash and a.key != b.key and a.key is not None


def test_overlapping_gold_spans_merge_first_through_pipeline(world):
    """SHOULD-3: gold tumpang-tindih digabung dulu (A1): 2 bagian-ayat, bukan 3; recall@K 1."""
    from backend import config as bc
    gcfg = bc.load("grid", world["cfg"])
    p = Pipeline(u_doc(), tokenizer=ToyWs(), retrieval_cfg=bc.load("retrieval", world["cfg"]), grid_cfg=gcfg)
    st = next(s for s in expand_grid(gcfg, "uupt") if s.chunker == "structure_handwritten" and s.retrieval_mode == "bm25"
              and s.budget_tokens == 2000 and not s.header_b)
    it = GridItem("ov", "uupt", "operator", "literal", gold_spans=((12, 30), (20, 37)), query="Aaa bbb Ccc ddd")
    m = p(st, [it])[0]
    assert m.gold_chars == 25 and m.parts_total == 2 and m.parts_hit == 2 and m.recall_at_k == 1
    cs = p.chunk_set(st)
    ranked = [RankedChunk(cs.by_id[c].start, cs.by_id[c].end, "", c) for c, _ in p.ranking(st, it)]
    assert recall_at_k_item([(12, 30), (20, 37)], ranked, p.k, cs.units) == 1


def test_boundary_coherence_through_quality_for_uses_address_map_bounds():
    """SHOULD-4 (M22): teks tanpa titik; batas potongan struktur sah hanya karena batas unit peta alamat."""
    from backend import config as bc
    from backend.pipeline.grid_run import quality_for
    from ._chunk_util import make_doc
    text = "### Pasal 1\n(1) Aaa bbb\n(2) Ccc ddd\n\n### Pasal 2\nEee fff ggg\n"
    doc = make_doc(text, [("batang_tubuh", 0, len(text))])
    gcfg, rcfg = bc.load("grid"), bc.load("retrieval")
    p = Pipeline(doc, tokenizer=ToyWs(), retrieval_cfg=rcfg, grid_cfg=gcfg)
    sts = expand_grid({**gcfg, "fixed_size": {"chunk_size_tokens": [5], "overlap_tokens": [1]}}, "uupt")
    struct = next(s for s in sts if s.chunker == "structure_handwritten" and s.retrieval_mode == "bm25" and s.budget_tokens == 2000 and not s.header_b)
    fixed = next(s for s in sts if s.chunker == "fixed_size" and s.retrieval_mode == "bm25" and s.budget_tokens == 2000 and not s.header_b)
    qs = quality_for(p, struct, [])
    assert qs["counts"]["bnd_den"] >= 2 and qs["boundary_coherence"] == 1.0 and qs["recall_at_k"] is None
    qf = quality_for(p, fixed, [])
    assert qf["counts"]["bnd_den"] >= 1 and qf["boundary_coherence"] < 1.0


def test_run_without_items_is_an_error(world, tmp_path):
    """M20: butir kosong atau tanpa berkas -> GridRunError 'no items', tanpa tulisan di runs/."""
    for variant in ("empty", "missing"):
        d = tmp_path / variant
        d.mkdir()
        if variant == "empty":
            (d / "uupt.v1.jsonl").write_text("", encoding="utf-8")
        with pytest.raises(GridRunError, match="no items"):
            run_family_grid("uupt", doc=world["doc"], tokenizer=ToyWs(), runs_dir=world["runs"], butir_dir=d, config_dir=world["cfg"],
                            encoder=FakeEncoder(), embed_cache_dir=world["emb"])
    assert not (world["runs"] / "grid").exists()
