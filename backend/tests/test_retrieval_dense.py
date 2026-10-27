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
    h = dense.chunk_set_hash(enc, ITEMS)
    assert dense.chunk_set_hash(enc, ITEMS[:2] + [("c2", "teks lain")]) != h
    assert dense.chunk_set_hash(FakeEncoder(revision="rev2"), ITEMS) != h
    assert dense.chunk_set_hash(FakeEncoder(max_seq_length=9), ITEMS) != h
    enc2 = FakeEncoder()
    enc2.model = "other/model"
    assert dense.chunk_set_hash(enc2, ITEMS) != h
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
    assert dense.embedder_info(enc, es.n_truncated) == {"name": "fake/model", "revision": "rev1", "max_seq_length": 6, "n_truncated": 1}
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
def test_bge_m3_real_embeds_three_sentences(tmp_path):
    os.environ["HF_HUB_OFFLINE"] = "1"
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
