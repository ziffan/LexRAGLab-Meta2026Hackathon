"""Agregasi pooled lintas dokumen (A6), Recall@K macro (A7), validasi K (A12 K0-a)."""
from __future__ import annotations

from fractions import Fraction
from typing import Iterable, Sequence, TypeVar

from .boundaries import boundary_counts
from .entities import Pattern, entity_counts
from .types import QualityCounts, QualityDoc, QualityMetrics

T = TypeVar("T")


def validate_k(k: int) -> int:
    """K0-a (menunggu I-31): K >= 0 diterima; negatif/bukan integer -> ValueError."""
    if isinstance(k, bool) or not isinstance(k, int):
        raise ValueError(f"K harus integer, dapat {k!r}")
    if k < 0:
        raise ValueError(f"K tidak boleh negatif: {k}")
    return k


def top_k(ranking: Sequence[T], k: int) -> list[T]:
    """K teratas dari ranking C; K melebihi panjang tidak error; K=0 -> kosong."""
    validate_k(k)
    return list(ranking[:k])


def doc_counts(
    doc: QualityDoc, patterns: Iterable[Pattern], abbreviations: Iterable[str]
) -> QualityCounts:
    pats = list(patterns)
    abbr = frozenset(abbreviations)
    en, ed = entity_counts(doc.text, doc.chunks, pats)
    bn, bd = boundary_counts(doc.text, doc.chunks, doc.structure_bounds, abbr)
    return QualityCounts(en, ed, bn, bd)


def pooled_counts(
    docs: Iterable[QualityDoc], patterns: Iterable[Pattern], abbreviations: Iterable[str]
) -> QualityCounts:
    pats, abbr = list(patterns), frozenset(abbreviations)
    total = QualityCounts(0, 0, 0, 0)
    for d in docs:
        total = total + doc_counts(d, pats, abbr)
    return total


def macro_recall(per_item: Iterable[Fraction | float | None]) -> Fraction | float | None:
    """Rata-rata atas butir ber-gold (nilai None dikeluarkan); kosong -> None (N1)."""
    vals = [v for v in per_item if v is not None]
    if not vals:
        return None
    return sum(vals[1:], vals[0]) / len(vals)


def _f(x: Fraction | float | None) -> float | None:
    return None if x is None else float(x)


def quality_metrics(
    setting_id: str,
    docs: Sequence[QualityDoc],
    k: int,
    recall_per_item: Iterable[Fraction | float | None],
    patterns: Iterable[Pattern],
    abbreviations: Iterable[str],
) -> QualityMetrics:
    """Tanpa keadaan global; setting struktur dan ukuran tetap memakai K/butir/pola sama (A11)."""
    validate_k(k)
    c = pooled_counts(docs, patterns, abbreviations)
    return QualityMetrics(
        setting_id=setting_id,
        entity_preservation=_f(c.entity_ratio),
        boundary_coherence=_f(c.bnd_ratio),
        recall_at_k=_f(macro_recall(recall_per_item)),
        k=k,
        counts=c,
    )
