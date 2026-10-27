"""Retriever dense: BAAI/bge-m3 lokal (H-042), tanpa prefix, embedding dinormalisasi (cosine = dot product).

Cache embedding per hash (H-025): `cache/embeddings/<embedding_set_hash>.npy` + `<hash>.json` (urutan `chunk_id`
dan metadata). Embedding query di-cache per hash (model, revisi, max_seq_length, teks query).
Embedding hanya lokal (G-14); CLI `python -m backend.retrieval.dense --build` membangun cache korpus UU PT.
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, Sequence

import numpy as np

from backend import config as _config
from backend.chunking.model import sha256_hex

CACHE_DIR = _config.REPO_ROOT / "cache" / "embeddings"


class Encoder(Protocol):
    """Antarmuka encoder. Implementasi nyata: `SentenceTransformerEncoder`; test memakai encoder palsu."""

    model: str
    revision: str
    max_seq_length: int
    device: str

    def encode(self, texts: Sequence[str]) -> np.ndarray: ...  # (n, d) float32, ternormalisasi

    def token_counts(self, texts: Sequence[str]) -> list[int]: ...  # termasuk token khusus


class SentenceTransformerEncoder:
    """bge-m3 via sentence-transformers dari cache HF lokal (tanpa unduh)."""

    def __init__(self, model: str, revision: str, max_seq_length: int, batch_size: int, device: str | None = None):
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        import torch
        from sentence_transformers import SentenceTransformer

        self.model, self.revision, self.max_seq_length, self.batch_size = model, revision, max_seq_length, batch_size
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self._st = SentenceTransformer(model, revision=revision, device=self.device, local_files_only=True)
        self._st.max_seq_length = max_seq_length
        self._tok = self._st.tokenizer

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self._st.get_sentence_embedding_dimension()), dtype=np.float32)
        out = self._st.encode(list(texts), batch_size=self.batch_size, normalize_embeddings=True,
                              convert_to_numpy=True, show_progress_bar=False)
        return np.asarray(out, dtype=np.float32)

    def token_counts(self, texts: Sequence[str]) -> list[int]:
        # tanpa pemotongan; panjang termasuk token khusus <s> dan </s>, sama seperti yang dilihat model
        enc = self._tok(list(texts), add_special_tokens=True, truncation=False, padding=False)
        return [len(ids) for ids in enc["input_ids"]]


def encoder_from_config(cfg: dict[str, Any], device: str | None = None) -> SentenceTransformerEncoder:
    d = cfg["dense"]
    return SentenceTransformerEncoder(d["model"], d["revision"], int(d["max_seq_length"]), int(d["batch_size"]), device)


def embedder_info(enc: Encoder, n_truncated: int | None = None) -> dict[str, Any]:
    """Bentuk `RunRecord.embedder` (DATA-CONTRACTS §12); `n_truncated` ikut bila diberikan (G-22).
    `device` = perangkat encoder yang menjalankan run ini, bukan yang membangun cache."""
    info: dict[str, Any] = {"name": enc.model, "revision": enc.revision, "max_seq_length": enc.max_seq_length,
                            "device": enc.device}
    if n_truncated is not None:
        info["n_truncated"] = n_truncated
    return info


def embedding_set_hash(enc: Encoder, items: Sequence[tuple[str, str]]) -> str:
    """Hash kanonik (model, revisi, max_seq_length, daftar `(chunk_id, teks)` terurut menurut chunk_id)."""
    ordered = sorted(items, key=lambda x: x[0])
    return sha256_hex({"model": enc.model, "revision": enc.revision, "max_seq_length": enc.max_seq_length,
                       "items": [[i, t] for i, t in ordered]})


@dataclass
class EmbeddingSet:
    chunk_ids: list[str]  # urutan baris `matrix` (terurut menurut chunk_id)
    matrix: np.ndarray
    n_truncated: int
    cache_hit: bool
    set_hash: str
    path: Path
    meta: dict[str, Any] = field(default_factory=dict)


def _save_npy(path: Path, arr: np.ndarray) -> None:
    tmp = path.with_name(path.stem + ".tmp.npy")
    np.save(tmp, arr, allow_pickle=False)
    os.replace(tmp, path)


def embed_chunks(enc: Encoder, items: Sequence[tuple[str, str]], *, cache_dir: Path | None = None) -> EmbeddingSet:
    """Embedding semua potongan; dihitung sekali per `embedding_set_hash`. `items` = `(chunk_id, teks)`."""
    ids = [i for i, _ in items]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate chunk_id")
    cdir = cache_dir or CACHE_DIR
    cdir.mkdir(parents=True, exist_ok=True)
    h = embedding_set_hash(enc, items)
    npy, js = cdir / f"{h}.npy", cdir / f"{h}.json"
    ordered = sorted(items, key=lambda x: x[0])
    if npy.exists() and js.exists():
        meta = json.loads(js.read_text(encoding="utf-8"))
        mat = np.load(npy, allow_pickle=False)
        # cache rusak atau tak cocok (model, revisi, max_seq_length, dimensi, urutan): dibangun ulang, bukan dipakai
        valid = (meta.get("model") == enc.model and meta.get("revision") == enc.revision
                 and meta.get("max_seq_length") == enc.max_seq_length and mat.ndim == 2
                 and mat.shape[0] == len(ordered) and mat.shape[1] == meta.get("dim")
                 and meta["chunk_ids"] == [i for i, _ in ordered])
        if valid:
            return EmbeddingSet(meta["chunk_ids"], mat, meta["n_truncated"], True, h, npy, meta)
    texts = [t for _, t in ordered]
    lens = enc.token_counts(texts) if texts else []
    n_trunc = sum(1 for n in lens if n > enc.max_seq_length)
    mat = enc.encode(texts)
    meta = {"chunk_ids": [i for i, _ in ordered], "n_truncated": n_trunc, "model": enc.model, "revision": enc.revision,
            "max_seq_length": enc.max_seq_length, "device": enc.device,
            "dim": int(mat.shape[1]) if mat.ndim == 2 else 0}
    _save_npy(npy, mat)
    js.write_text(json.dumps(meta, ensure_ascii=False, sort_keys=True), encoding="utf-8", newline="\n")
    return EmbeddingSet(meta["chunk_ids"], mat, n_trunc, False, h, npy, meta)


def embed_query(enc: Encoder, query: str, *, cache_dir: Path | None = None, dim: int | None = None) -> np.ndarray:
    cdir = cache_dir or CACHE_DIR
    cdir.mkdir(parents=True, exist_ok=True)
    h = sha256_hex({"kind": "query", "model": enc.model, "revision": enc.revision,
                    "max_seq_length": enc.max_seq_length, "text": query})
    p = cdir / f"q-{h}.npy"
    if p.exists():
        v = np.load(p, allow_pickle=False)
        if v.ndim == 1 and (dim is None or v.shape[0] == dim):
            return v  # dimensi tak cocok: dibangun ulang
    v = enc.encode([query])[0]
    _save_npy(p, v)
    return v


def rank_dense(enc: Encoder, emb: EmbeddingSet, query: str, top_n: int | None = None, *,
               cache_dir: Path | None = None) -> list[tuple[str, float]]:
    """Ranking `(chunk_id, cosine)` menurun; seri skor -> `chunk_id` naik. Query kosong -> []."""
    if not query.strip() or not emb.chunk_ids:
        return []
    q = embed_query(enc, query, cache_dir=cache_dir, dim=int(emb.matrix.shape[1]))
    scores = emb.matrix @ q
    hits = [(cid, float(s)) for cid, s in zip(emb.chunk_ids, scores)]
    hits.sort(key=lambda x: (-x[1], x[0]))
    return hits if top_n is None else hits[:top_n]


def _main(argv: list[str]) -> int:
    import argparse

    from backend.chunking import chunk_document, load_retrieval_config
    from backend.corpus import load_corpus
    from backend.tokenizer import get_tokenizer

    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(prog="backend.retrieval.dense")
    ap.add_argument("--build", action="store_true", help="embed seluruh potongan structure_handwritten dan fixed_size UU PT")
    ap.add_argument("--chunk-size", type=int, default=512)
    ap.add_argument("--overlap", type=int, default=64)
    args = ap.parse_args(argv)
    if not args.build:
        ap.print_help()
        return 0
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    cfg = load_retrieval_config()
    doc = load_corpus()
    tok = get_tokenizer()
    enc = encoder_from_config(cfg)
    print(f"device={enc.device} model={enc.model}@{enc.revision[:8]} max_seq_length={enc.max_seq_length}")
    settings = {
        "structure_handwritten": {"chunker": "structure_handwritten"},
        "fixed_size": {"chunker": "fixed_size", "chunk_size_tokens": args.chunk_size, "overlap_tokens": args.overlap},
    }
    for name, setting in settings.items():
        chunks = chunk_document(doc, setting, tokenizer=tok, retrieval_cfg=cfg)
        items = [(c.chunk_id, doc.text[c.start:c.end]) for c in chunks]
        t0 = time.perf_counter()
        es = embed_chunks(enc, items)
        dt = time.perf_counter() - t0
        print(f"{name}: chunks={len(items)} n_truncated={es.n_truncated} cache_hit={es.cache_hit} "
              f"seconds={dt:.2f} path={es.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
