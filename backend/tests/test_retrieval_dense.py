"""M1.3 dense: cache embedding per hash, query cache, terpotong, determinisme. Encoder palsu; satu test GPU nyata."""

from __future__ import annotations

import hashlib
import os
import re

import numpy as np
import pytest

from backend.retrieval import dense

DIM = 16


class FakeEncoder:
    """Deterministik tanpa GPU: kantong kata di-hash ke 16 dimensi, dinormalisasi. Menghitung panggilan."""

    def __init__(self, max_seq_length: int = 8, revision: str = "rev1"):
        self.model, self.revision, self.max_seq_length, self.device = "fake/model", revision, max_seq_length, "cpu"
        self.encode_calls = 0
        self.texts_encoded = 0

    def encode(self, texts):
        self.encode_calls += 1
        self.texts_encoded += len(texts)
        out = np.zeros((len(texts), DIM), dtype=np.float32)
        for i, t in enumerate(texts):
            for w in re.findall(r"\w+", t.lower()):
                out[i, int(hashlib.md5(w.encode()).hexdigest(), 16) % DIM] += 1.0
            n = np.linalg.norm(out[i])
            if n:
                out[i] /= n
        return out

    def token_counts(self, texts):
        return [len(re.findall(r"\w+", t)) + 2 for t in texts]


ITEMS = [("c3", "direksi wajib meminta persetujuan RUPS"), ("c1", "RUPS tahunan diselenggarakan paling lambat enam bulan"),
         ("c2", "kekayaan perseroan dialihkan atau dijaminkan")]


def test_cache_hit_no_recompute(tmp_path):
    enc = FakeEncoder()
    a = dense.embed_chunks(enc, ITEMS, cache_dir=tmp_path)
    assert not a.cache_hit and enc.encode_calls == 1 and enc.texts_encoded == 3
    b = dense.embed_chunks(enc, list(reversed(ITEMS)), cache_dir=tmp_path)  # urutan masukan tidak memengaruhi kunci
    assert b.cache_hit and enc.encode_calls == 1
    assert b.chunk_ids == ["c1", "c2", "c3"] == a.chunk_ids
    assert np.array_equal(a.matrix, b.matrix)
    assert (tmp_path / f"{a.set_hash}.npy").exists() and (tmp_path / f"{a.set_hash}.json").exists()


def test_hash_changes_with_text_model_revision_maxlen(tmp_path):
    enc = FakeEncoder()
    h = dense.embedding_set_hash(enc, ITEMS)
    assert dense.embedding_set_hash(enc, ITEMS[:2] + [("c2", "teks lain")]) != h
    assert dense.embedding_set_hash(FakeEncoder(revision="rev2"), ITEMS) != h
    assert dense.embedding_set_hash(FakeEncoder(max_seq_length=9), ITEMS) != h
    enc2 = FakeEncoder()
    enc2.model = "other/model"
    assert dense.embedding_set_hash(enc2, ITEMS) != h
    dense.embed_chunks(enc, ITEMS, cache_dir=tmp_path)
    dense.embed_chunks(enc, ITEMS[:2], cache_dir=tmp_path)  # himpunan beda -> hitung baru
    assert enc.encode_calls == 2


def test_duplicate_chunk_id_rejected(tmp_path):
    with pytest.raises(ValueError):
        dense.embed_chunks(FakeEncoder(), [("a", "x"), ("a", "y")], cache_dir=tmp_path)


def test_truncated_count_in_metadata_and_cached(tmp_path):
    enc = FakeEncoder(max_seq_length=6)  # token_counts = kata + 2
    items = [("a", "satu dua"), ("b", "satu dua tiga empat lima"), ("c", "satu dua tiga empat")]
    es = dense.embed_chunks(enc, items, cache_dir=tmp_path)
    assert es.n_truncated == 1  # hanya b (7 > 6); c = 6 tidak terpotong
    again = dense.embed_chunks(enc, items, cache_dir=tmp_path)
    assert again.cache_hit and again.n_truncated == 1
    assert dense.embedder_info(enc, es.n_truncated) == {"name": "fake/model", "revision": "rev1", "max_seq_length": 6, "device": "cpu", "n_truncated": 1}
    assert es.meta["device"] == "cpu"


def test_query_cached_and_ranking_deterministic(tmp_path):
    enc = FakeEncoder()
    es = dense.embed_chunks(enc, ITEMS, cache_dir=tmp_path)
    calls = enc.encode_calls
    r1 = dense.rank_dense(enc, es, "RUPS tahunan", cache_dir=tmp_path)
    assert enc.encode_calls == calls + 1
    r2 = dense.rank_dense(enc, es, "RUPS tahunan", cache_dir=tmp_path)
    assert enc.encode_calls == calls + 1  # query dari cache
    assert r1 == r2 and r1[0][0] == "c1"
    assert all(r1[i][1] >= r1[i + 1][1] for i in range(len(r1) - 1))
    assert dense.rank_dense(enc, es, "RUPS tahunan", 1, cache_dir=tmp_path) == r1[:1]
    assert dense.rank_dense(enc, es, "   ", cache_dir=tmp_path) == []


def test_ties_break_by_chunk_id(tmp_path):
    enc = FakeEncoder()
    items = [("z", "sama persis"), ("a", "sama persis"), ("m", "sama persis")]
    es = dense.embed_chunks(enc, items, cache_dir=tmp_path)
    assert [c for c, _ in dense.rank_dense(enc, es, "sama persis", cache_dir=tmp_path)] == ["a", "m", "z"]


def test_empty_set(tmp_path):
    enc = FakeEncoder()
    es = dense.embed_chunks(enc, [], cache_dir=tmp_path)
    assert es.chunk_ids == [] and es.n_truncated == 0
    assert dense.rank_dense(enc, es, "apa saja", cache_dir=tmp_path) == []


def _gpu_ready() -> bool:
    try:
        import torch
        from backend import config
    except Exception:
        return False
    if not torch.cuda.is_available():
        return False
    d = config.load("retrieval")["dense"]
    hub = os.environ.get("HF_HUB_CACHE") or os.path.join(os.environ.get("HF_HOME") or os.path.expanduser("~/.cache/huggingface"), "hub")
    return os.path.isdir(os.path.join(hub, "models--" + d["model"].replace("/", "--"), "snapshots", d["revision"]))


@pytest.mark.gpu
@pytest.mark.skipif(not _gpu_ready(), reason="CUDA atau cache bge-m3 (revisi dipin) tidak ada")
def test_bge_m3_real_embeds_three_sentences(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    from backend import config

    enc = dense.encoder_from_config(config.load("retrieval"))
    assert enc.device.startswith("cuda") and enc.max_seq_length == 8192
    items = [("s1", "Direksi wajib meminta persetujuan RUPS untuk mengalihkan kekayaan Perseroan."),
             ("s2", "Rapat umum pemegang saham tahunan diselenggarakan paling lambat enam bulan setelah tahun buku berakhir."),
             ("s3", "Resep nasi goreng memakai bawang putih, kecap manis, dan telur.")]
    es = dense.embed_chunks(enc, items, cache_dir=tmp_path)
    assert es.matrix.shape == (3, 1024) and es.n_truncated == 0
    assert np.allclose(np.linalg.norm(es.matrix, axis=1), 1.0, atol=1e-3)
    r = dense.rank_dense(enc, es, "kapan RUPS tahunan harus diadakan", cache_dir=tmp_path)
    assert r[0][0] == "s2" and r[-1][0] == "s3"


def test_query_cache_key_includes_model_revision_maxlen(tmp_path):
    base = FakeEncoder()
    dense.embed_query(base, "RUPS tahunan", cache_dir=tmp_path)
    dense.embed_query(base, "RUPS tahunan", cache_dir=tmp_path)
    assert base.encode_calls == 1
    for other in (FakeEncoder(revision="rev2"), FakeEncoder(max_seq_length=9)):
        dense.embed_query(other, "RUPS tahunan", cache_dir=tmp_path)
        assert other.encode_calls == 1  # kunci beda -> encode ulang
    m = FakeEncoder()
    m.model = "other/model"
    dense.embed_query(m, "RUPS tahunan", cache_dir=tmp_path)
    assert m.encode_calls == 1


def test_query_cache_wrong_dim_is_rebuilt(tmp_path):
    enc = FakeEncoder()
    es = dense.embed_chunks(enc, ITEMS, cache_dir=tmp_path)
    for f in tmp_path.glob("q-*.npy"):
        f.unlink()
    dense.rank_dense(enc, es, "RUPS", cache_dir=tmp_path)
    (qf,) = tmp_path.glob("q-*.npy")
    np.save(qf, np.zeros(DIM + 3, dtype=np.float32))
    calls = enc.encode_calls
    assert dense.rank_dense(enc, es, "RUPS", cache_dir=tmp_path)
    assert enc.encode_calls == calls + 1


def test_corpus_cache_mismatched_meta_is_rebuilt(tmp_path):
    import json

    enc = FakeEncoder()
    es = dense.embed_chunks(enc, ITEMS, cache_dir=tmp_path)
    js = tmp_path / f"{es.set_hash}.json"
    meta = json.loads(js.read_text(encoding="utf-8"))
    meta["dim"] = DIM + 1
    js.write_text(json.dumps(meta), encoding="utf-8")
    again = dense.embed_chunks(enc, ITEMS, cache_dir=tmp_path)
    assert not again.cache_hit and enc.encode_calls == 2 and again.matrix.shape[1] == DIM


def test_sentence_transformer_constructor_and_encode_kwargs(monkeypatch, tmp_path):
    """Tanpa GPU: SentenceTransformer palsu menangkap kwargs. Offline, revisi dipin, max_seq_length, tanpa prefix."""
    import sentence_transformers

    seen = {}

    class FakeST:
        def __init__(self, model, **kw):
            seen["init"] = (model, kw)
            self.max_seq_length = 512
            self.tokenizer = None

        def encode(self, texts, **kw):
            seen["encoded"] = list(texts)
            seen["encode_kw"] = kw
            return np.ones((len(texts), 4), dtype=np.float32) / 2

        def get_sentence_embedding_dimension(self):
            return 4

    monkeypatch.setattr(sentence_transformers, "SentenceTransformer", FakeST)
    from backend import config

    cfg = config.load("retrieval")
    enc = dense.encoder_from_config(cfg, device="cpu")
    model, kw = seen["init"]
    assert model == "BAAI/bge-m3" and kw["revision"] == "5617a9f61b028005a4858fdac845db406aefb181"
    assert kw["local_files_only"] is True and kw["device"] == "cpu"
    assert enc._st.max_seq_length == cfg["dense"]["max_seq_length"] == 8192
    enc.encode(["kalimat satu", "kalimat dua"])
    assert seen["encoded"] == ["kalimat satu", "kalimat dua"]  # tanpa prefix
    assert seen["encode_kw"]["normalize_embeddings"] is True and seen["encode_kw"]["batch_size"] == cfg["dense"]["batch_size"]
