"""Pipeline `(setting, items) -> list[ItemMetrics]` untuk runner grid (`backend/grid/runner.py`).

Menyambung modul M1 tanpa mengubah semantiknya: `chunk_document` (cache per kunci chunker), `retrieval.registry.rank`,
`metrics.packing`, `metrics.item`. Satu tokenizer untuk semua setting (`ensure_single_tokenizer`). Tanpa Model API.
Header B (M3.2): tanpa `HeaderBinding` setting `header_b = true` ditolak dengan `SettingNotAvailable`; dengan binding,
header SEMUA potongan setting diperiksa (`HeaderError` bila hilang/kosong/basi/granularitas beda), biaya header =
`tok(header)` atas string header saja (masuk anggaran yang sama), indeks header-on = `header + "\n" + teks sumber`
(objek terpisah dari indeks off), offset dan gold tetap pada teks sumber.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Callable, Sequence

from backend.chunking import AddressMap, Chunk, build_address_map, chunk_document
from backend.chunking.schema_chunker import schema_identity
from backend.grid.headers import HeaderBinding, index_text, resolve_headers
from backend.grid.schemas import SchemaBinding
from backend.grid.types import GridItem, Setting, setting_content
from backend.metrics.item import compute_item_metrics
from backend.metrics.packing import pack
from backend.metrics.run_record import ensure_single_tokenizer
from backend.metrics.types import ItemMetrics, RankedChunk
from backend.retrieval.dense import EmbeddingSet, Encoder, embed_chunks
from backend.retrieval.registry import chunk_texts, rank

AVAILABLE_CHUNKERS = ("structure_handwritten", "fixed_size")  # `structure_schema` tersedia bila ada `SchemaBinding` (M3.4)


class SettingNotAvailable(Exception):
    """Setting memakai komponen yang belum ada di M1 (chunker skema, header B)."""


def unavailable_reason(s: Setting, *, headers: bool = False, schemas: SchemaBinding | None = None) -> str | None:
    """Alasan setting tidak bisa dijalankan, atau None bila bisa. `headers=True`: ada store header B (M3.2);
    `schemas`: skema A keluarga (M3.4) — `structure_schema` jalan hanya bila rekamannya ada untuk `schema_version`."""
    if s.chunker == "structure_schema":
        if schemas is None:
            return f"chunker {s.chunker} needs schema A (available from M3)"
        if schemas.resolve(s.schema_version) is None:
            want = "an active version" if s.schema_version is None else f"version {s.schema_version}"
            return f"chunker {s.chunker}: schema A record for {s.family} has no {want}"
    elif s.chunker not in AVAILABLE_CHUNKERS:
        return f"chunker {s.chunker} is unknown"
    if s.header_b and not headers:
        return "header B is available from M3"
    return None


def chunk_params(s: Setting) -> tuple:
    """Kunci cache potongan: hanya sumbu chunker (mode, anggaran, header tidak mengubah potongan)."""
    return (s.chunker, s.chunk_size_tokens, s.overlap_tokens, s.schema_version)


@dataclass
class IndexView:
    """Apa yang diindeks retriever: `chunks` beroffset di `doc.text` dan `texts` yang sesuai. Off = teks sumber persis;
    on = header + teks sumber di `doc` sintetis (offset potongan asli tidak disentuh)."""

    doc: Any
    chunks: list
    texts: list[tuple[str, str]]


@dataclass
class ChunkSet:
    chunks: list[Chunk]
    chunker_key: str
    by_id: dict[str, Chunk]
    units: list[tuple[int, int]]
    amap: AddressMap
    embeddings: EmbeddingSet | None = None
    embeddings_on: EmbeddingSet | None = None
    view_off: IndexView | None = None
    view_on: IndexView | None = None
    headers: dict[str, str] | None = None  # header tervalidasi (hanya bila lolos semua pemeriksaan)


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
                 cache_dir: Any = None, headers: HeaderBinding | None = None, schemas: SchemaBinding | None = None):
        self.doc, self.tok = doc, tokenizer
        self.headers = headers
        self.schemas = schemas
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

    def schema_record(self, s: Setting) -> Any:
        """`SchemaRecord` untuk setting `structure_schema` (None untuk chunker lain)."""
        if s.chunker != "structure_schema" or self.schemas is None:
            return None
        return self.schemas.resolve(s.schema_version)

    def params(self, s: Setting) -> tuple:
        """Kunci cache potongan = `chunk_params` + identitas skema (versi dan hash isi) bagi `structure_schema`:
        skema berubah = potongan berbeda = kunci berbeda."""
        rec = self.schema_record(s)
        if rec is None:
            return chunk_params(s)
        ident = schema_identity(rec)
        return (*chunk_params(s), ident["schema_version"], ident["schema_hash"])

    def chunk_set(self, s: Setting) -> ChunkSet:
        reason = unavailable_reason(s, headers=self.headers is not None, schemas=self.schemas)
        if reason:
            raise SettingNotAvailable(reason)
        key = self.params(s)
        cs = self._sets.get(key)
        if cs is None:
            chunks = chunk_document(self.doc, setting_content(s), tokenizer=self.tok, retrieval_cfg=self.rcfg, grid_cfg=self.gcfg,
                                    schema_record=self.schema_record(s))
            scope = set(self.rcfg["scope_sections"])
            prefix = self.doc.metadata.get("address_prefix") or self.doc.doc_id
            amap = build_address_map(self.doc.text, self.doc.sections, prefix, scope,
                                     dict(self.rcfg.get("chunking", {}).get("section_labels", {})))
            units = [(u.start, u.end) for u in amap.in_sections(scope)]
            cs = ChunkSet(chunks, chunks[0].chunker_key if chunks else "", {c.chunk_id: c for c in chunks}, units, amap)
            self._sets[key] = cs
        return cs

    def headers_for(self, s: Setting) -> dict[str, str]:
        """Header tervalidasi seluruh potongan setting header-on (`chunk_id` -> teks). Galat `HeaderError` per jenis."""
        cs = self.chunk_set(s)
        if cs.headers is None:
            assert self.headers is not None
            cs.headers = resolve_headers(cs.chunks, self.headers.store, setting_id=s.setting_id,
                                         granularity=self.headers.expected_granularity(s.chunker),
                                         clean_sha256=self.doc.clean_sha256)
        return cs.headers

    def index(self, s: Setting) -> IndexView:
        """Indeks off (teks sumber persis) dan on (header + teks sumber) adalah dua objek terpisah."""
        cs = self.chunk_set(s)
        if not s.header_b:
            if cs.view_off is None:
                cs.view_off = IndexView(self.doc, cs.chunks, chunk_texts(cs.chunks, self.doc))
            return cs.view_off
        if cs.view_on is None:
            hdr = self.headers_for(s)
            parts, chunks, pos = [], [], 0
            for c in cs.chunks:
                t = index_text(hdr[c.chunk_id], self.doc.text[c.start:c.end])
                chunks.append(SimpleNamespace(chunk_id=c.chunk_id, start=pos, end=pos + len(t)))
                parts.append(t)
                pos += len(t)
            synth = SimpleNamespace(text="".join(parts))
            cs.view_on = IndexView(synth, chunks, chunk_texts(chunks, synth))
        return cs.view_on

    def index_texts(self, s: Setting) -> list[tuple[str, str]]:
        return list(self.index(s).texts)

    def _embeddings(self, cs: ChunkSet, s: Setting) -> EmbeddingSet:
        on = s.header_b
        have = cs.embeddings_on if on else cs.embeddings
        if have is None:
            enc = self.encoder
            if enc is None:
                raise ValueError("dense/hybrid retrieval needs an encoder")
            have = embed_chunks(enc, self.index(s).texts, cache_dir=self.cache_dir)
            if on:
                cs.embeddings_on = have
            else:
                cs.embeddings = have
        return have

    def ranking(self, s: Setting, item: GridItem) -> list[tuple[str, float]]:
        cs = self.chunk_set(s)
        key = (self.params(s), s.header_b, s.retrieval_mode, item.id, item.query)
        hit = self._rank_cache.get(key)
        if hit is None:
            needs_dense = s.retrieval_mode in ("dense", "hybrid")
            view = self.index(s)
            hit = rank(s.retrieval_mode, view.chunks, item.query, cfg=self.rcfg, doc=view.doc,
                       encoder=self.encoder if needs_dense else None,
                       embeddings=self._embeddings(cs, s) if needs_dense else None, cache_dir=self.cache_dir)
            self._rank_cache[key] = hit
        return hit

    # --- inti ---
    def account(self, s: Setting, item: GridItem, ranking: Sequence[tuple[str, float]]) -> Retrieval:
        """Pengemasan dan metrik dari ranking `C` yang diberikan. Biaya header-on = tok(header) + tok(teks sumber),
        dalam anggaran `s.budget_tokens` yang sama; offset dan gold tetap pada teks sumber."""
        cs = self.chunk_set(s)
        hdr = self.headers_for(s) if s.header_b else {}
        ranked = [RankedChunk(cs.by_id[cid].start, cs.by_id[cid].end, hdr.get(cid, ""), cid) for cid, _ in ranking]
        m = compute_item_metrics(self.doc.text, item.gold_spans, ranked, s.budget_tokens, self.tok, packing=self.packing,
                                 k=self.k, units=cs.units, item_id=item.id, setting_id=s.setting_id)
        packed = pack(self.doc.text, ranked, s.budget_tokens, self.tok, self.packing)
        return Retrieval(m, list(ranking), packed, dict(ranking))

    def retrieve(self, s: Setting, item: GridItem) -> Retrieval:
        return self.account(s, item, self.ranking(s, item))

    def __call__(self, s: Setting, items: Sequence[GridItem]) -> list[ItemMetrics]:
        self.calls += 1
        self._infos.append(self.tok.info)
        ensure_single_tokenizer(self._infos)
        if s.header_b:
            self.headers_for(s)  # galat header sebelum butir pertama
        return [self.retrieve(s, it).metrics for it in items]

    # --- catatan untuk RunRecord ---
    def n_truncated(self) -> dict[str, int]:
        """Potongan yang terpotong di embedder, per kunci chunker (G-22); hanya set yang di-embed."""
        out = {cs.chunker_key: cs.embeddings.n_truncated for cs in self._sets.values() if cs.embeddings is not None}
        out.update({cs.chunker_key + "+header": cs.embeddings_on.n_truncated for cs in self._sets.values()
                    if cs.embeddings_on is not None})
        return out
