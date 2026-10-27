"""Pipeline keluarga multi-dokumen (H-086): satu `Pipeline` per dokumen, butir diarahkan ke dokumen `doc_id`-nya.

Retrieval tiap butir hanya atas potongan dokumen butir itu, dengan anggaran `Setting.budget_tokens` per butir; metrik per
butir dihitung oleh `Pipeline` satu-dokumen yang sama (definisi M1.2 tidak berubah). Agregasi lintas dokumen terjadi di
runner (`aggregate_points`): rata-rata per butir atas semua butir keluarga, seperti keluarga satu dokumen.
Satu encoder dibagi semua dokumen (dibuat malas sekali). Tanpa Model API.
"""

from __future__ import annotations

from typing import Any, Callable, Sequence

from backend.grid.headers import HeaderBinding
from backend.grid.schemas import SchemaBinding
from backend.grid.types import GridItem, Setting
from backend.metrics.types import ItemMetrics
from backend.pipeline.pipeline import Pipeline
from backend.retrieval.dense import Encoder


class MultiDocError(Exception):
    """Butir merujuk dokumen yang tidak ada di korpus keluarga."""


class MultiDocPipeline:
    def __init__(self, docs: Sequence[Any], *, tokenizer: Any, retrieval_cfg: dict[str, Any], grid_cfg: dict[str, Any],
                 encoder: Encoder | None = None, encoder_factory: Callable[[], Encoder] | None = None,
                 cache_dir: Any = None, headers: HeaderBinding | None = None, schemas: SchemaBinding | None = None):
        ids = [d.doc_id for d in docs]
        if not ids or len(set(ids)) != len(ids):
            raise MultiDocError("a multi-document family needs at least one document and unique doc_id values")
        self.docs = sorted(docs, key=lambda d: d.doc_id)
        self.tok, self.rcfg, self.gcfg = tokenizer, retrieval_cfg, grid_cfg
        self._encoder, self._encoder_factory = encoder, encoder_factory

        def shared() -> Encoder:  # satu encoder untuk semua dokumen
            if self._encoder is None and self._encoder_factory is not None:
                self._encoder = self._encoder_factory()
            return self._encoder  # type: ignore[return-value]

        self.pipes: dict[str, Pipeline] = {
            d.doc_id: Pipeline(d, tokenizer=tokenizer, retrieval_cfg=retrieval_cfg, grid_cfg=grid_cfg, encoder=encoder,
                               encoder_factory=shared if encoder is None else None, cache_dir=cache_dir, headers=headers,
                               schemas=schemas)
            for d in self.docs}
        self.packing = grid_cfg["packing"]["rule"]
        self.k: int = int(retrieval_cfg["recall"]["k"])
        self.calls = 0

    @property
    def encoder(self) -> Encoder | None:
        return self._encoder

    @property
    def encoder_used(self) -> bool:
        return any(p.encoder_used for p in self.pipes.values())

    def pipe_for(self, item: GridItem) -> Pipeline:
        p = self.pipes.get(item.doc_id)
        if p is None:
            raise MultiDocError(f"item {item.id!r} refers to doc_id {item.doc_id!r}, which is not in the family corpus")
        return p

    def __call__(self, s: Setting, items: Sequence[GridItem]) -> list[ItemMetrics]:
        """Metrik per butir dalam urutan `items`; tiap dokumen dipanggil sekali dengan butirnya sendiri."""
        self.calls += 1
        groups: dict[str, list[GridItem]] = {}
        for it in items:
            self.pipe_for(it)
            groups.setdefault(it.doc_id, []).append(it)
        if s.header_b:  # galat header sebelum butir pertama, untuk semua dokumen yang dirujuk butir
            for doc_id in sorted(groups):
                self.pipes[doc_id].headers_for(s)
        got: dict[str, ItemMetrics] = {}
        for doc_id in sorted(groups):
            for m in self.pipes[doc_id](s, groups[doc_id]):
                got[m.item_id] = m
        return [got[it.id] for it in items]

    def n_truncated(self) -> dict[str, int]:
        """Jumlah potongan terpotong embedder per kunci chunker, dijumlah lintas dokumen."""
        out: dict[str, int] = {}
        for p in self.pipes.values():
            for k, v in p.n_truncated().items():
                out[k] = out.get(k, 0) + v
        return out
