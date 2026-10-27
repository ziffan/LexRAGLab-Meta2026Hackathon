"""Pipeline `(setting, items) -> list[ItemMetrics]` untuk runner grid (`backend/grid/runner.py`).

Menyambung modul M1 tanpa mengubah semantiknya: `chunk_document` (cache per kunci chunker), `retrieval.registry.rank`,
`metrics.packing`, `metrics.item`. Satu tokenizer untuk semua setting (`ensure_single_tokenizer`). Tanpa Model API.
Header B belum ada (M3): setting `header_b = true` ditolak dengan `SettingNotAvailable`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

from backend.chunking import AddressMap, Chunk, build_address_map, chunk_document
from backend.grid.types import GridItem, Setting, setting_content
from backend.metrics.item import compute_item_metrics
from backend.metrics.packing import pack
from backend.metrics.run_record import ensure_single_tokenizer
from backend.metrics.types import ItemMetrics, RankedChunk
from backend.retrieval.dense import EmbeddingSet, Encoder, embed_chunks
from backend.retrieval.registry import chunk_texts, rank

AVAILABLE_CHUNKERS = ("structure_handwritten", "fixed_size")


class SettingNotAvailable(Exception):
    """Setting memakai komponen yang belum ada di M1 (chunker skema, header B)."""


def unavailable_reason(s: Setting) -> str | None:
    """Alasan setting tidak bisa dijalankan di M1, atau None bila bisa."""
    if s.chunker not in AVAILABLE_CHUNKERS:
        return f"chunker {s.chunker} needs schema A (available from M3)"
    if s.header_b:
        return "header B is available from M3"
    return None


def chunk_params(s: Setting) -> tuple:
    """Kunci cache potongan: hanya sumbu chunker (mode, anggaran, header tidak mengubah potongan)."""
    return (s.chunker, s.chunk_size_tokens, s.overlap_tokens, s.schema_version)


@dataclass
class ChunkSet:
    chunks: list[Chunk]
    chunker_key: str
    by_id: dict[str, Chunk]
    units: list[tuple[int, int]]
    amap: AddressMap
    embeddings: EmbeddingSet | None = None


@dataclass
class Retrieval:
    """Hasil satu (setting, butir): ranking penuh dan potongan yang masuk anggaran."""

    metrics: ItemMetrics
    ranking: list[tuple[str, float]]
    packed: list[Any]  # PackedChunk
    scores: dict[str, float] = field(default_factory=dict)


class Pipeline:
    def __init__(self, doc: Any, *, tokenizer: Any, retrieval_cfg: dict[str, Any], grid_cfg: dict[str, Any],
                 encoder: Encoder | None = None, encoder_factory: Callable[[], Encoder] | None = None,
                 cache_dir: Any = None):
        self.doc, self.tok = doc, tokenizer
        self.rcfg, self.gcfg = retrieval_cfg, grid_cfg
        self._encoder, self._encoder_factory, self.cache_dir = encoder, encoder_factory, cache_dir
        self.packing: str = grid_cfg["packing"]["rule"]
        self.k: int = int(retrieval_cfg["recall"]["k"])
        self._sets: dict[tuple, ChunkSet] = {}
        self._rank_cache: dict[tuple, list[tuple[str, float]]] = {}
        self._infos: list[Any] = []
        self.calls = 0  # jumlah panggilan pipeline (bukti nol hitung pada cache)

    # --- komponen ---
    @property
    def encoder(self) -> Encoder | None:
        if self._encoder is None and self._encoder_factory is not None:
            self._encoder = self._encoder_factory()
        return self._encoder

    @property
    def encoder_used(self) -> bool:
        return self._encoder is not None

    def chunk_set(self, s: Setting) -> ChunkSet:
        reason = unavailable_reason(s)
        if reason:
            raise SettingNotAvailable(reason)
        key = chunk_params(s)
        cs = self._sets.get(key)
        if cs is None:
            chunks = chunk_document(self.doc, setting_content(s), tokenizer=self.tok, retrieval_cfg=self.rcfg, grid_cfg=self.gcfg)
            scope = set(self.rcfg["scope_sections"])
            prefix = self.doc.metadata.get("address_prefix") or self.doc.doc_id
            amap = build_address_map(self.doc.text, self.doc.sections, prefix, scope,
                                     dict(self.rcfg.get("chunking", {}).get("section_labels", {})))
            units = [(u.start, u.end) for u in amap.in_sections(scope)]
            cs = ChunkSet(chunks, chunks[0].chunker_key if chunks else "", {c.chunk_id: c for c in chunks}, units, amap)
            self._sets[key] = cs
        return cs

    def _embeddings(self, cs: ChunkSet) -> EmbeddingSet:
        if cs.embeddings is None:
            enc = self.encoder
            if enc is None:
                raise ValueError("dense/hybrid retrieval needs an encoder")
            cs.embeddings = embed_chunks(enc, chunk_texts(cs.chunks, self.doc), cache_dir=self.cache_dir)
        return cs.embeddings

    def ranking(self, s: Setting, item: GridItem) -> list[tuple[str, float]]:
        cs = self.chunk_set(s)
        key = (chunk_params(s), s.retrieval_mode, item.id, item.query)
        hit = self._rank_cache.get(key)
        if hit is None:
            needs_dense = s.retrieval_mode in ("dense", "hybrid")
            hit = rank(s.retrieval_mode, cs.chunks, item.query, cfg=self.rcfg, doc=self.doc,
                       encoder=self.encoder if needs_dense else None,
                       embeddings=self._embeddings(cs) if needs_dense else None, cache_dir=self.cache_dir)
            self._rank_cache[key] = hit
        return hit

    # --- inti ---
    def retrieve(self, s: Setting, item: GridItem) -> Retrieval:
        cs = self.chunk_set(s)
        ranking = self.ranking(s, item)
        ranked = [RankedChunk(cs.by_id[cid].start, cs.by_id[cid].end, "", cid) for cid, _ in ranking]
        m = compute_item_metrics(self.doc.text, item.gold_spans, ranked, s.budget_tokens, self.tok, packing=self.packing,
                                 k=self.k, units=cs.units, item_id=item.id, setting_id=s.setting_id)
        packed = pack(self.doc.text, ranked, s.budget_tokens, self.tok, self.packing)
        return Retrieval(m, ranking, packed, dict(ranking))

    def __call__(self, s: Setting, items: Sequence[GridItem]) -> list[ItemMetrics]:
        self.calls += 1
        self._infos.append(self.tok.info)
        ensure_single_tokenizer(self._infos)
        return [self.retrieve(s, it).metrics for it in items]

    # --- catatan untuk RunRecord ---
    def n_truncated(self) -> dict[str, int]:
        """Potongan yang terpotong di embedder, per kunci chunker (G-22); hanya set yang di-embed."""
        return {cs.chunker_key: cs.embeddings.n_truncated for cs in self._sets.values() if cs.embeddings is not None}
