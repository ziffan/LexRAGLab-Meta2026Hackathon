"""Grid keluarga multi-dokumen (H-086, W38 S1-S3): retrieval per akta butir, agregasi rata-rata per butir lintas akta, tanpa
split (H-054), kunci dari hash korpus keluarga; kunci UU PT tidak berubah. Dokumen dan butir SINTETIS di tmp_path (bukan butir
evaluasi, tidak di data/butir). Tokenizer toy-ws, encoder palsu; tanpa GPU, jaringan, atau Model API."""

from __future__ import annotations

import json
from dataclasses import replace
from fractions import Fraction
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api.app import Service, create_app
from backend.grid.runner import grid_cache_key
from backend.grid.types import GridItem, family_corpus_hash, item_set_hash
from backend.pipeline.grid_run import (GridRunError, make_plan, run_family_grid, summarize, to_grid_items)
from backend.pipeline.multi import MultiDocError, MultiDocPipeline
from backend.pipeline.pipeline import Pipeline

from ._chunk_util import ToyWs, make_doc, u_doc
from .pipeline_fakes import FakeEncoder, toy_config_dir, write_toy_butir
from .spark_fakes import BASE, K, budget_cfg, model_cfg

# ---- dokumen sintetis -------------------------------------------------------------------------------------------
# A: 38 karakter, token toy-ws: Pasal 1 Aaa bbb ccc. Pasal 2 Ddd eee. = 9. Satu section batang_tubuh tanpa "### Pasal",
#    jadi structure_handwritten = satu potongan (0, 37) (newline akhir di luar unit, seperti akta nyata).
# B: 17 karakter, token: Pasal 1 Fff ggg. = 4; potongan (0, 16).
A_TEXT = "Pasal 1\nAaa bbb ccc.\nPasal 2\nDdd eee.\n"
B_TEXT = "Pasal 1\nFff ggg.\n"
assert len(A_TEXT) == 38 and len(B_TEXT) == 17


def deed(doc_id: str, text: str, prefix: str):
    return replace(make_doc(text, [("batang_tubuh", 0, len(text))], prefix=prefix, doc_id=doc_id), family="akta",
                   loader_rules_version="akta-1")


# (id, doc_id, query, gold). a2 bertanya istilah yang HANYA ada di B, tapi gold-nya di A: retrieval per akta wajib mengambil A.
ITEMS = [
    ("a1", "akta-x1", "Aaa bbb", [(8, 20)]),    # "Aaa bbb ccc." -> 3 token gold
    ("a2", "akta-x1", "Fff ggg", [(29, 37)]),   # "Ddd eee."     -> 2 token gold
    ("b1", "akta-x2", "Fff", [(8, 16)]),        # "Fff ggg."     -> 2 token gold
]
BUDGET_HI, BUDGET_LO = 9, 4  # config grid mainan: 9 = panjang A persis (masuk, aturan stop), 4 = hanya B yang muat


def write_akta_butir(directory: Path, docs: dict, rows=ITEMS, version: int = 1, **override) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    lines = []
    for iid, did, q, spans in rows:
        d = {"clean_sha256": docs[did].clean_sha256, "doc_id": did, "family": "akta", "id": iid, "mode": "literal",
             "origin": "operator", "query": q, "gold_spans": [{"start": s, "end": e} for s, e in spans]}
        d.update(override.get(iid, {}))
        lines.append(json.dumps(d, sort_keys=True))
    p = directory / f"akta.v{version}.jsonl"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return p


def akta_config_dir(dest: Path) -> Path:
    cfg = toy_config_dir(dest)
    g = cfg / "grid.toml"
    t = g.read_bytes().decode("utf-8")
    assert "default_tokens = 2000" in t and "comparison_tokens = [1000]" in t
    t = t.replace("default_tokens = 2000", f"default_tokens = {BUDGET_HI}").replace("comparison_tokens = [1000]", f"comparison_tokens = [{BUDGET_LO}]")
    g.write_bytes(t.encode("utf-8"))
    return cfg


@pytest.fixture()
def world(tmp_path):
    docs = {"akta-x1": deed("akta-x1", A_TEXT, "Akta X1"), "akta-x2": deed("akta-x2", B_TEXT, "Akta X2")}
    cfg = akta_config_dir(tmp_path / "cfg")
    butir = tmp_path / "butir"
    write_akta_butir(butir, docs)
    return {"docs": docs, "cfg": cfg, "butir": butir, "runs": tmp_path / "runs", "emb": tmp_path / "emb"}


def run(w, enc=None, docs=None, pipeline_out=None):
    enc = enc or FakeEncoder()
    return run_family_grid("akta", docs=list((docs or w["docs"]).values()), tokenizer=ToyWs(), runs_dir=w["runs"],
                           butir_dir=w["butir"], config_dir=w["cfg"], encoder=enc, embed_cache_dir=w["emb"],
                           pipeline_out=pipeline_out), enc


def point(env, chunker, mode, budget):
    by = {s["setting_id"]: s for s in env["settings_run"]}
    return next(p for p in env["points"] if by[p["setting_id"]]["chunker"] == chunker
                and by[p["setting_id"]]["retrieval_mode"] == mode and p["budget_tokens"] == budget)


def item_metrics(env, setting_id):
    return {m["item_id"]: m for m in env["metrics"] if m["setting_id"] == setting_id}


# ---- S1: angka hitung tangan -------------------------------------------------------------------------------------
def test_s1_per_deed_retrieval_hand_numbers(world):
    """structure_handwritten + dense (encoder palsu: semua potongan dokumen butir diranking).
    Anggaran 9: a1 -> potongan A (9 token) masuk: recall 1, token 9, gold 3 -> precision 3/9.
                a2 -> HANYA potongan A yang bisa diambil (per akta): recall 1, token 9, gold 2 -> 2/9.
                     (Korpus gabungan akan menaruh potongan B lebih dulu untuk "Fff ggg": recall 0.)
                b1 -> potongan B (4 token): recall 1, token 4, gold 2 -> 2/4.
      rata-rata per butir: recall (1+1+1)/3 = 1; token (9+9+4)/3 = 22/3; precision (1/3+2/9+1/2)/3 = 19/54.
    Anggaran 4: potongan A (9) tak muat -> aturan stop, kosong: a1, a2 recall 0, token 0 (precision null);
                b1 recall 1, token 4, precision 1/2.
      recall (0+0+1)/3 = 1/3; token (0+0+4)/3 = 4/3; precision atas butir ber-token saja = 1/2."""
    res, _ = run(world)
    env = res.envelope
    hi = point(env, "structure_handwritten", "dense", BUDGET_HI)
    assert hi["exact"] == {"mean_span_recall": "1/1", "mean_retrieved_tokens": "22/3", "mean_token_precision": "19/54",
                           "mrr": hi["exact"]["mrr"]}
    m = item_metrics(env, hi["setting_id"])
    assert {k: (v["covered_gold_chars"], v["gold_chars"], v["retrieved_tokens"], v["gold_tokens_retrieved"]) for k, v in m.items()} == {
        "a1": (12, 12, 9, 3), "a2": (8, 8, 9, 2), "b1": (8, 8, 4, 2)}
    a_chunk, b_chunk = m["a1"]["retrieved_chunk_ids"], m["b1"]["retrieved_chunk_ids"]
    assert len(a_chunk) == 1 and len(b_chunk) == 1 and a_chunk != b_chunk
    assert m["a2"]["retrieved_chunk_ids"] == a_chunk  # a2 tidak pernah mendapat potongan akta lain
    lo = point(env, "structure_handwritten", "dense", BUDGET_LO)
    assert (lo["exact"]["mean_span_recall"], lo["exact"]["mean_retrieved_tokens"], lo["exact"]["mean_token_precision"]) == ("1/3", "4/3", "1/2")
    m = item_metrics(env, lo["setting_id"])
    assert {k: (v["covered_gold_chars"], v["retrieved_tokens"], tuple(v["retrieved_chunk_ids"])) for k, v in m.items()} == {
        "a1": (0, 0, ()), "a2": (0, 0, ()), "b1": (8, 4, tuple(b_chunk))}


def test_s1_item_metrics_equal_single_document_pipeline(world):
    """Tiap butir dihitung oleh Pipeline satu-dokumen atas dokumennya (definisi M1.2 tak berubah), untuk SEMUA setting."""
    res, enc = run(world)
    env = res.envelope
    items = to_grid_items([json.loads(x) for x in (world["butir"] / "akta.v1.jsonl").read_text(encoding="utf-8").splitlines()])
    from backend import config
    rcfg, gcfg = config.load("retrieval", world["cfg"]), config.load("grid", world["cfg"])
    from backend.grid.types import Setting
    settings = [Setting(**s) for s in env["settings_run"]]
    assert len(settings) == 12
    for did, doc in world["docs"].items():
        single = Pipeline(doc, tokenizer=ToyWs(), retrieval_cfg=rcfg, grid_cfg=gcfg, encoder=enc, cache_dir=world["emb"])
        mine = [i for i in items if i.doc_id == did]
        for s in settings:
            want = {m.item_id: m for m in single(s, mine)}
            got = item_metrics(env, s.setting_id)
            for iid, m in want.items():
                g = got[iid]
                assert (g["covered_gold_chars"], g["gold_chars"], g["retrieved_tokens"], g["gold_tokens_retrieved"], g["rank"],
                        g["parts_total"], g["parts_hit"], tuple(g["retrieved_chunk_ids"])) == (
                    m.covered_gold_chars, m.gold_chars, m.retrieved_tokens, m.gold_tokens_retrieved, m.rank, m.parts_total,
                    m.parts_hit, m.retrieved_chunk_ids), (did, s.setting_id[:12], iid)


def test_s1_aggregate_is_mean_per_item_across_deeds(world):
    """GridPoint keluarga = rata-rata per butir atas semua butir semua akta (bukan rata-rata per akta)."""
    res, _ = run(world)
    env = res.envelope
    for p in env["points"]:
        ms = [m for m in env["metrics"] if m["setting_id"] == p["setting_id"]]
        assert len(ms) == 3
        exp = sum((Fraction(m["covered_gold_chars"], m["gold_chars"]) for m in ms), Fraction(0)) / 3
        assert p["exact"]["mean_span_recall"] == f"{exp.numerator}/{exp.denominator}"


def test_s1_key_and_record_use_family_corpus_hash(world):
    res, _ = run(world)
    docs = list(world["docs"].values())
    fch = family_corpus_hash(docs)
    # hitung tangan: sha256 dari JSON kanonik [[doc_id, clean_sha256], ...] terurut doc_id
    import hashlib
    rows = sorted([d.doc_id, d.clean_sha256] for d in docs)
    assert fch == hashlib.sha256(json.dumps(rows, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
    assert family_corpus_hash(list(reversed(docs))) == fch  # urutan masukan tak berpengaruh
    plan = make_plan("akta", docs=docs, tokenizer=ToyWs(), butir_dir=world["butir"], runs_dir=world["runs"], config_dir=world["cfg"],
                     create_split=False)
    assert plan.split is None and plan.corpus_key == fch
    assert res.key == plan.key == grid_cache_key(fch, plan.config_hash, item_set_hash(plan.items), None)
    rec = res.record
    assert rec["corpus_hash"] == fch and rec["clean_sha256"] == fch and rec["loader_rules_version"] == "akta-1"
    assert rec["cache_key"] == res.key and rec["cost_usd_micros"] == 0
    env = res.envelope
    assert env["split"] is None and env["selections"] == {} and env["quality_comparison"] == []
    assert {f["split"] for f in env["frontiers"]} == {None} and {p["split"] for p in env["points"]} == {None}
    assert {m["split"] for m in env["metrics"]} == {None}
    assert env["docs"] == [{"doc_id": "akta-x1", "clean_sha256": world["docs"]["akta-x1"].clean_sha256, "loader_rules_version": "akta-1", "n_items": 2},
                           {"doc_id": "akta-x2", "clean_sha256": world["docs"]["akta-x2"].clean_sha256, "loader_rules_version": "akta-1", "n_items": 1}]
    assert not (world["runs"] / "split").exists()  # tanpa SplitRecord akta (H-054)
    assert len(env["quality"]) == 12
    assert any("split: none" in line for line in summarize(res))


def test_s1_key_changes_with_deed_text_and_doc_id(world):
    a, _ = run(world)
    docs2 = {**world["docs"], "akta-x2": deed("akta-x2", B_TEXT.replace("ggg", "hhh"), "Akta X2")}
    write_akta_butir(world["butir"], docs2, version=2)
    b, _ = run(world, docs=docs2)
    assert b.key != a.key and family_corpus_hash(docs2.values()) != family_corpus_hash(world["docs"].values())
    # doc_id ikut hash butir: butir yang sama dipindah ke dokumen lain = kunci lain
    x = GridItem("i", "akta", "operator", "literal", "h", ((0, 1),), "q", doc_id="akta-x1")
    assert item_set_hash([x]) != item_set_hash([replace(x, doc_id="akta-x2")])


def test_s1_second_run_computes_nothing(world):
    out1, out2 = [], []
    a, enc = run(world, pipeline_out=out1)
    calls = enc.encode_calls
    assert isinstance(out1[0], MultiDocPipeline) and out1[0].calls == 12 and calls > 0
    b, _ = run(world, enc=enc, pipeline_out=out2)
    assert b.cache_hit and b.record["status"] == "cached" and out2 == [] and enc.encode_calls == calls and b.key == a.key


def test_multidoc_pipeline_rejects_unknown_doc(world):
    from backend import config
    p = MultiDocPipeline(list(world["docs"].values()), tokenizer=ToyWs(), retrieval_cfg=config.load("retrieval", world["cfg"]),
                         grid_cfg=config.load("grid", world["cfg"]), encoder=FakeEncoder())
    with pytest.raises(MultiDocError, match="not in the family corpus"):
        p.pipe_for(GridItem("z", "akta", "operator", "literal", "h", (), "q", doc_id="akta-zz"))
    with pytest.raises(MultiDocError):
        MultiDocPipeline([], tokenizer=ToyWs(), retrieval_cfg={}, grid_cfg={})


# ---- kunci UU PT tidak berubah ------------------------------------------------------------------------------------
# Nilai "sebelum" dihitung dengan backend/grid/types.py versi HEAD c33bf81 (sebelum H-086) atas butir mainan TOY_ITEMS.
UUPT_TOY_ITEM_SET_HASH = "b01f5d1e30f4a1a2997e7fd5f75a50736770a98f677aaf82b5de68efaa6d81b2"


def test_uupt_item_hash_and_key_unchanged(tmp_path):
    doc = u_doc()
    butir = tmp_path / "butir"
    write_toy_butir(butir, doc.clean_sha256)  # butir UU PT juga membawa doc_id; tidak boleh ikut hash
    raw = [json.loads(x) for x in (butir / "uupt.v1.jsonl").read_text(encoding="utf-8").splitlines() if x]
    assert all(r["doc_id"] == "synthetic" for r in raw)
    items = to_grid_items(raw)
    assert all(i.doc_id == "" for i in items)
    assert item_set_hash(items) == UUPT_TOY_ITEM_SET_HASH
    cfg = toy_config_dir(tmp_path / "cfg")
    res = run_family_grid("uupt", doc=doc, tokenizer=ToyWs(), runs_dir=tmp_path / "runs", butir_dir=butir, config_dir=cfg,
                          encoder=FakeEncoder(), embed_cache_dir=tmp_path / "emb")
    plan = make_plan("uupt", doc=doc, tokenizer=ToyWs(), butir_dir=butir, runs_dir=tmp_path / "runs", config_dir=cfg, create_split=False)
    assert res.key == plan.key == grid_cache_key(doc.clean_sha256, plan.config_hash, UUPT_TOY_ITEM_SET_HASH, 1)
    assert plan.corpus_key == doc.clean_sha256 and "corpus_akta" not in plan.cfgs  # config akta tak ikut hash UU PT
    assert res.record["clean_sha256"] == doc.clean_sha256 and "docs" not in res.envelope and res.envelope["split"]["split_version"] == 1


# ---- S3: galat jelas ---------------------------------------------------------------------------------------------
def test_s3_no_approved_akta_items(world, tmp_path):
    empty = tmp_path / "kosong"
    empty.mkdir()
    with pytest.raises(GridRunError, match=r"no approved akta items"):
        run_family_grid("akta", docs=list(world["docs"].values()), tokenizer=ToyWs(), runs_dir=world["runs"], butir_dir=empty,
                        config_dir=world["cfg"], encoder=FakeEncoder())
    assert not (world["runs"] / "grid").exists()


@pytest.mark.parametrize("override, pattern", [
    ({"a2": {"clean_sha256": "0" * 64}}, r"item 'a2' was written against a different clean text than document 'akta-x1'"),
    ({"b1": {"doc_id": "akta-x1"}}, r"item 'b1' was written against a different clean text than document 'akta-x1'"),
    ({"b1": {"doc_id": "akta-99"}}, r"item 'b1' refers to doc_id 'akta-99', which is not in the akta corpus"),
    ({"b1": {"id": "a1"}}, r"duplicate item id 'a1'"),
])
def test_s3_rejects_item_not_matching_its_deed(world, override, pattern):
    write_akta_butir(world["butir"], world["docs"], version=2, **override)
    with pytest.raises(GridRunError, match=pattern):
        run(world)
    assert not (world["runs"] / "grid").exists()


def test_s2_requires_doc_list_and_rejects_unknown_family(world):
    with pytest.raises(GridRunError, match="needs its document list"):
        run_family_grid("akta", tokenizer=ToyWs(), runs_dir=world["runs"], butir_dir=world["butir"], config_dir=world["cfg"])
    with pytest.raises(GridRunError, match="not available"):
        run_family_grid("xyz", doc=u_doc(), tokenizer=ToyWs(), runs_dir=world["runs"], butir_dir=world["butir"], config_dir=world["cfg"])


# ---- S2: W1 akta lewat Service ------------------------------------------------------------------------------------
def _client(world, butir, monkeypatch):
    svc = Service(config_dir=world["cfg"], butir_dir=butir, tokenizer=ToyWs(), runs_dir=world["runs"], encoder=FakeEncoder(),
                  embed_cache_dir=world["emb"])
    monkeypatch.setattr(svc, "family_docs", lambda family: list(world["docs"].values()) if family == "akta" else [])
    app = create_app(svc, env={"MUSE_API_KEY": K, "MUSE_BASE_URL": BASE}, model_config=model_cfg(), budget_config=budget_cfg())
    return TestClient(app, raise_server_exceptions=False)


def test_s2_w1_runs_akta_grid_then_cached(world, monkeypatch):
    c = _client(world, world["butir"], monkeypatch)
    r1 = c.post("/api/families/akta/grid/run", json={})
    assert r1.status_code == 200, r1.text
    rec = r1.json()
    assert rec["status"] == "ok" and rec["corpus_hash"] == family_corpus_hash(world["docs"].values())
    r2 = c.post("/api/families/akta/grid/run", json={})
    assert r2.status_code == 200 and r2.json()["status"] == "cached" and r2.json()["cache_key"] == rec["cache_key"]
    env = json.loads((world["runs"] / "grid" / f"{rec['cache_key']}.json").read_text(encoding="utf-8"))
    assert env["family"] == "akta" and env["split"] is None and env["selections"] == {}


def test_s2_w1_akta_without_items_is_clear_422(world, monkeypatch, tmp_path):
    empty = tmp_path / "kosong"
    empty.mkdir()
    r = _client(world, empty, monkeypatch).post("/api/families/akta/grid/run", json={})
    assert r.status_code == 422 and "no approved akta items" in r.text
