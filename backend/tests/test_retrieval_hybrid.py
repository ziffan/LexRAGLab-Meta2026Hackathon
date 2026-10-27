"""M1.3 hybrid RRF dan registry `rank(mode, ...)`. Encoder palsu, tanpa GPU."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend import config
from backend.retrieval import hybrid, registry
from backend.tests.test_retrieval_dense import FakeEncoder

CFG = config.load("retrieval")


def test_rrf_formula_and_determinism():
    a = [("x", 9.0), ("y", 5.0), ("z", 1.0)]
    b = [("y", 3.0), ("w", 2.0)]
    r = hybrid.rrf([a, b], k_rrf=60)
    exp = {"x": 1 / 61, "y": 1 / 62 + 1 / 61, "z": 1 / 63, "w": 1 / 62}
    assert dict(r) == pytest.approx(exp)
    assert [c for c, _ in r] == ["y", "x", "w", "z"]
    assert r == hybrid.rrf([a, b], k_rrf=60)


def test_rrf_tie_breaks_by_chunk_id_and_top_n():
    r = hybrid.rrf([[("b", 1.0)], [("a", 1.0)]], k_rrf=60)
    assert [c for c, _ in r] == ["a", "b"] and r[0][1] == r[1][1]
    assert hybrid.rrf([[("b", 1), ("a", 1)]], k_rrf=1, top_n=1) == [("b", 0.5)]
    assert hybrid.rrf([[], []], k_rrf=60) == []
    with pytest.raises(ValueError):
        hybrid.rrf([[("a", 1)]], k_rrf=-1)


def test_rrf_k_changes_scores():
    a, b = [("x", 1.0), ("y", 1.0)], [("y", 1.0)]
    assert hybrid.rrf([a, b], k_rrf=1)[0][0] == "y"
    assert hybrid.rrf([a, b], k_rrf=1)[0][1] != hybrid.rrf([a, b], k_rrf=100)[0][1]


TEXT = ("Direksi wajib meminta persetujuan RUPS untuk mengalihkan kekayaan Perseroan. "
        "RUPS tahunan diselenggarakan paling lambat enam bulan setelah tahun buku berakhir. "
        "Komisaris mengawasi kebijakan pengurusan Perseroan.")


def _fixture():
    spans, pos = [], 0
    for i, sent in enumerate(TEXT.split(". ")):
        s = TEXT.index(sent, pos)
        spans.append(SimpleNamespace(chunk_id=f"c{i}", start=s, end=s + len(sent)))
        pos = s + len(sent)
    return SimpleNamespace(text=TEXT), spans


def test_registry_modes(tmp_path):
    doc, chunks = _fixture()
    enc = FakeEncoder()
    q = "RUPS tahunan enam bulan"
    for mode in registry.MODES:
        r = registry.rank(mode, chunks, q, cfg=CFG, doc=doc, encoder=enc, cache_dir=tmp_path)
        assert r and r[0][0] == "c1", mode
        assert r == registry.rank(mode, chunks, q, cfg=CFG, doc=doc, encoder=enc, cache_dir=tmp_path)
        assert [s for _, s in r] == sorted((s for _, s in r), reverse=True)
    calls = enc.encode_calls
    registry.rank("hybrid", chunks, q, cfg=CFG, doc=doc, encoder=enc, cache_dir=tmp_path)
    assert enc.encode_calls == calls  # potongan dan query dari cache
    assert len(registry.rank("dense", chunks, q, cfg=CFG, doc=doc, encoder=enc, cache_dir=tmp_path, top_n=2)) == 2


def test_registry_hybrid_uses_cfg_k_rrf(tmp_path):
    doc, chunks = _fixture()
    enc = FakeEncoder()
    q = "RUPS tahunan"
    base = registry.rank("hybrid", chunks, q, cfg=CFG, doc=doc, encoder=enc, cache_dir=tmp_path)
    cfg2 = {**CFG, "hybrid": {**CFG["hybrid"], "k_rrf": 1}}
    other = registry.rank("hybrid", chunks, q, cfg=cfg2, doc=doc, encoder=enc, cache_dir=tmp_path)
    assert base[0][1] != other[0][1]


def test_registry_errors(tmp_path):
    doc, chunks = _fixture()
    with pytest.raises(ValueError):
        registry.rank("splade", chunks, "q", cfg=CFG, doc=doc)
    with pytest.raises(ValueError):
        registry.rank("dense", chunks, "q", cfg=CFG, doc=doc)
    assert registry.rank("bm25", chunks, "", cfg=CFG, doc=doc) == []


def test_config_m13_keys():
    assert CFG["bm25"] == {"k1": 1.5, "b": 0.75, "stemming": True, "stopwords": True}
    d = CFG["dense"]
    assert d["model"] == "BAAI/bge-m3" and d["revision"] == "5617a9f61b028005a4858fdac845db406aefb181"
    assert d["max_seq_length"] == 8192 and d["batch_size"] > 0
    assert CFG["hybrid"]["k_rrf"] == 60 and CFG["recall"]["k"] == 5
    assert CFG["scope_sections"] and CFG["chunking"]["structure_version"] == 1
