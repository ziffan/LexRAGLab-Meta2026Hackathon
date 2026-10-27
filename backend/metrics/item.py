"""Metrik per butir: span recall, precision token, rank, Recall@K (EVAL-SPEC §4-§6)."""

from __future__ import annotations

from fractions import Fraction
from typing import Sequence

from backend.metrics import intervals as iv
from backend.metrics.packing import pack
from backend.metrics.types import ItemMetrics, PackedChunk, RankedChunk, TokenizerLike, token_offsets

Interval = tuple[int, int]


def gold_parts(gold_spans: Sequence[Interval], units: Sequence[Interval]) -> list[Interval]:
    """Bagian-ayat (H-048): span gold digabung dulu (A1), lalu diiris dengan tiap unit peta alamat
    (masukan); irisan tak kosong menjadi satu bagian. Terurut menurut posisi."""
    g = iv.merge(gold_spans)
    parts: list[Interval] = []
    for u in sorted(units):
        parts.extend(iv.intersect(g, [u]))
    return sorted(parts)


def gold_token_set(doc: str, packed: Sequence[PackedChunk], gold: Sequence[Interval], tokenizer: TokenizerLike) -> set[Interval]:
    """Token gold unik menurut posisi (S18): tiap potongan ditokenisasi sendiri, offset mutlak (A2);
    token gold bila seluruh karakternya di G."""
    out: set[Interval] = set()
    for p in packed:
        for ts, te in token_offsets(tokenizer, doc[p.start : p.end]):
            s, e = p.start + ts, p.start + te
            if e > s and iv.contains_all(gold, s, e):
                out.add((s, e))
    return out


def recall_at_k_counts(parts: Sequence[Interval], ranked: Sequence[RankedChunk], k: int) -> tuple[int, int]:
    """(hit, total). Bagian dihitung bila seluruhnya ada di SATU potongan di C[:K] (inklusif di ujung)."""
    top = ranked[: max(k, 0)]
    hit = sum(1 for gs, ge in parts if any(c.start <= gs and ge <= c.end for c in top))
    return hit, len(parts)


def recall_at_k_from_parts(parts: Sequence[Interval], ranked: Sequence[RankedChunk], k: int) -> Fraction | None:
    """Recall@K per butir dari bagian-ayat yang sudah dipecah (EVAL-SPEC §6): `Fraction(hit, total)`;
    tanpa bagian (butir tanpa gold) -> None. Fungsi produksi yang sama dengan `ItemMetrics.recall_at_k`."""
    hit, total = recall_at_k_counts(parts, ranked, k)
    return Fraction(hit, total) if total else None


def recall_at_k_item(gold_spans: Sequence[Interval], ranked: Sequence[RankedChunk], k: int, units: Sequence[Interval]) -> Fraction | None:
    """Recall@K per butir dari span gold mentah: gabung (A1), pecah di batas unit peta alamat (H-048), lalu hitung."""
    gold = iv.merge(gold_spans)
    return recall_at_k_from_parts(gold_parts(gold, units) if gold else [], ranked, k)


def compute_item_metrics(
    doc: str,
    gold_spans: Sequence[Interval],
    ranked: Sequence[RankedChunk],
    budget: int,
    tokenizer: TokenizerLike,
    *,
    packing: str = "stop",
    k: int,
    units: Sequence[Interval],
    item_id: str = "",
    setting_id: str = "",
    split: str | None = None,
) -> ItemMetrics:
    gold = iv.merge(gold_spans)
    packed = pack(doc, ranked, budget, tokenizer, packing)
    union = iv.merge((p.start, p.end) for p in packed)
    covered = iv.size(iv.intersect(gold, union))
    retrieved = sum(p.cost for p in packed)
    gold_tokens = len(gold_token_set(doc, packed, gold, tokenizer)) if gold else 0
    rank = next((i for i, p in enumerate(packed, start=1) if iv.intersect(gold, [(p.start, p.end)])), None)
    parts = gold_parts(gold, units) if gold else []
    hit, total = recall_at_k_counts(parts, ranked, k)
    return ItemMetrics(
        gold_chars=iv.size(gold),
        covered_gold_chars=covered,
        retrieved_tokens=retrieved,
        gold_tokens_retrieved=gold_tokens,
        rank=rank,
        parts_total=total,
        parts_hit=hit,
        item_id=item_id,
        setting_id=setting_id,
        split=split,
        retrieved_chunk_ids=tuple(p.chunk_id for p in packed if p.chunk_id is not None),
    )
