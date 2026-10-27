"""Antarmuka tunggal retrieval untuk gugus integrasi: `rank(mode, chunks, query, cfg=...)`.

Mode: `bm25`, `dense`, `hybrid`. Teks potongan = `doc.text[start:end]` (Chunk tidak menyimpan teks).
Pilihan kedalaman: `[hybrid].top_n` = 0 berarti seluruh ranking tiap jalur masuk fusi; hasil akhir tidak dipotong
kecuali `top_n` diberikan pemanggil (pemotongan ke K dilakukan penghitung metrik).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from .bm25 import Bm25Retriever
from .dense import EmbeddingSet, Encoder, embed_chunks, rank_dense
from .hybrid import rrf

MODES = ("bm25", "dense", "hybrid")


def chunk_texts(chunks: Sequence[Any], doc: Any) -> list[tuple[str, str]]:
    return [(c.chunk_id, doc.text[c.start:c.end]) for c in chunks]


def rank(
    mode: str,
    chunks: Sequence[Any],
    query: str,
    *,
    cfg: dict[str, Any],
    doc: Any,
    encoder: Encoder | None = None,
    embeddings: EmbeddingSet | None = None,
    cache_dir: Path | None = None,
    top_n: int | None = None,
) -> list[tuple[str, float]]:
    """Ranking `(chunk_id, skor)` menurun. `cfg` = isi `config/retrieval.toml`.

    `dense`/`hybrid` butuh `encoder` (atau `embeddings` yang sudah dihitung bersama `encoder` untuk query).
    """
    if mode not in MODES:
        raise ValueError(f"unknown retrieval mode: {mode!r}")
    items = chunk_texts(chunks, doc)
    out_n = top_n

    def bm25_rank(n: int | None) -> list[tuple[str, float]]:
        b = cfg["bm25"]
        r = Bm25Retriever(items, k1=b["k1"], b=b["b"], stemming=b["stemming"], stopwords=b["stopwords"])
        return r.rank(query, n)

    def dense_rank(n: int | None) -> list[tuple[str, float]]:
        if encoder is None:
            raise ValueError(f"mode {mode!r} needs an encoder")
        emb = embeddings if embeddings is not None else embed_chunks(encoder, items, cache_dir=cache_dir)
        return rank_dense(encoder, emb, query, n, cache_dir=cache_dir)

    if mode == "bm25":
        return bm25_rank(out_n)
    if mode == "dense":
        return dense_rank(out_n)
    h = cfg["hybrid"]
    depth = int(h["top_n"]) or None
    return rrf([dense_rank(depth), bm25_rank(depth)], k_rrf=int(h["k_rrf"]), top_n=out_n)
