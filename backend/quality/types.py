"""Tipe M1.5. Offset code point, setengah terbuka [start, end)."""
from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from typing import Collection


@dataclass(frozen=True)
class ChunkSpan:
    """Potongan: rentang offset dan teks header B (tidak pernah dipindai)."""

    start: int
    end: int
    hdr: str = ""


@dataclass(frozen=True)
class QualityDoc:
    """Satu dokumen: teks, potongan (urutan bebas), dan batas struktur S."""

    text: str
    chunks: tuple[ChunkSpan, ...]
    structure_bounds: frozenset[int] = field(default_factory=frozenset)


@dataclass(frozen=True)
class QualityCounts:
    """Hitungan mentah integer (A13). Penyebut nol -> rasio None (A5 N1)."""

    entity_num: int
    entity_den: int
    bnd_num: int
    bnd_den: int

    @property
    def entity_ratio(self) -> Fraction | None:
        return Fraction(self.entity_num, self.entity_den) if self.entity_den else None

    @property
    def bnd_ratio(self) -> Fraction | None:
        return Fraction(self.bnd_num, self.bnd_den) if self.bnd_den else None

    def __add__(self, other: "QualityCounts") -> "QualityCounts":
        return QualityCounts(
            self.entity_num + other.entity_num,
            self.entity_den + other.entity_den,
            self.bnd_num + other.bnd_num,
            self.bnd_den + other.bnd_den,
        )


@dataclass(frozen=True)
class QualityMetrics:
    """DATA-CONTRACTS §10 (H-059): tiga field number | null."""

    setting_id: str
    entity_preservation: float | None
    boundary_coherence: float | None
    recall_at_k: float | None
    k: int
    counts: QualityCounts | None = None


Bounds = Collection[int]
