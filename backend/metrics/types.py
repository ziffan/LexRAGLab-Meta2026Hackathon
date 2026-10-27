"""Bentuk data kalkulator: masukan potongan, keluaran ItemMetrics dan GridPoint (DATA-CONTRACTS §10)."""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any, Protocol, Sequence

PACKING_RULES = ("stop", "skip", "truncate")


class TokenizerLike(Protocol):
    """Antarmuka `backend.tokenizer.LocalTokenizer`: `count` dan `offsets` (offset relatif teks masukan)."""

    def count(self, text: str) -> int: ...

    def offsets(self, text: str) -> Sequence[tuple[int, int]]: ...


class OffsetsUnavailableError(RuntimeError):
    """Tokenizer tanpa `offsets` (fallback o200k): metrik presisi dan truncate tidak bisa dihitung."""


def token_offsets(tokenizer: TokenizerLike, text: str) -> list[tuple[int, int]]:
    try:
        return list(tokenizer.offsets(text))
    except NotImplementedError as exc:
        raise OffsetsUnavailableError(
            "tokenizer has no token offsets (HF H-014 tokenizer missing from the local cache, fallback "
            "o200k in use); precision and truncate need the HF tokenizer, see docs/GOTCHAS.md G-32"
        ) from exc


@dataclass(frozen=True)
class RankedChunk:
    """Satu potongan dalam ranking `C`: offset `[start, end)` di teks bersih, header B opsional."""

    start: int
    end: int
    header: str = ""
    chunk_id: str | None = None


@dataclass(frozen=True)
class PackedChunk:
    """Potongan di `P` setelah pengemasan. `start/end` sudah disesuaikan bila dipotong (truncate)."""

    start: int
    end: int
    cost: int
    header_cost: int
    rank_in_c: int  # mulai 1
    truncated: bool = False
    chunk_id: str | None = None


def _ratio(num: int, den: int) -> Fraction | None:
    return Fraction(num, den) if den > 0 else None


def _f(x: Fraction | None) -> float | None:
    return None if x is None else float(x)


@dataclass(frozen=True)
class ItemMetrics:
    """Pembilang/penyebut integer disimpan; rasio diturunkan eksak (Fraction)."""

    gold_chars: int
    covered_gold_chars: int
    retrieved_tokens: int
    gold_tokens_retrieved: int
    rank: int | None = None  # peringkat (mulai 1) di P; None = tidak ada yang beririsan
    parts_total: int = 0  # |parts(q)|
    parts_hit: int = 0
    item_id: str = ""
    setting_id: str = ""
    split: str | None = None
    retrieved_chunk_ids: tuple[str, ...] = field(default_factory=tuple)
    # H-090 P7 (hanya akta; None = tidak dilaporkan, UU PT): karakter gold (setelah digabung) di luar semua unit peta alamat.
    gold_chars_outside_units: int | None = None

    @property
    def has_gold(self) -> bool:
        return self.gold_chars > 0

    @property
    def span_recall(self) -> Fraction | None:
        return _ratio(self.covered_gold_chars, self.gold_chars)

    @property
    def token_precision(self) -> Fraction | None:
        if not self.has_gold:
            return None
        return _ratio(self.gold_tokens_retrieved, self.retrieved_tokens)

    @property
    def reciprocal_rank(self) -> Fraction | None:
        if not self.has_gold:
            return None
        return Fraction(1, self.rank) if self.rank else Fraction(0)

    @property
    def recall_at_k(self) -> Fraction | None:
        if not self.has_gold:
            return None
        return _ratio(self.parts_hit, self.parts_total)

    @property
    def fully_covered(self) -> bool | None:
        if not self.has_gold:
            return None
        return self.covered_gold_chars == self.gold_chars

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "setting_id": self.setting_id,
            "split": self.split,
            "gold_chars": self.gold_chars,
            "covered_gold_chars": self.covered_gold_chars,
            "span_recall": _f(self.span_recall),
            "retrieved_tokens": self.retrieved_tokens,
            "gold_tokens_retrieved": self.gold_tokens_retrieved,
            "token_precision": _f(self.token_precision),
            "reciprocal_rank": _f(self.reciprocal_rank),
            "rank": self.rank,
            "recall_at_k": _f(self.recall_at_k),
            "parts_hit": self.parts_hit,
            "parts_total": self.parts_total,
            "fully_covered": self.fully_covered,
            "retrieved_chunk_ids": list(self.retrieved_chunk_ids),
        }


@dataclass(frozen=True)
class GridPoint:
    setting_id: str
    split: str | None
    budget_tokens: int
    mean_span_recall: Fraction | None  # None bila tidak ada butir bergold (temuan: kontrak bertipe number)
    mean_token_precision: Fraction | None  # A7, A7b
    mrr: Fraction | None
    mean_retrieved_tokens: Fraction | None
    fully_covered_count: dict[str, int]  # {"covered": x, "total": y}
    no_gold_count: int
    dominated: bool = False  # diisi tahap frontier, bukan di sini

    def to_dict(self) -> dict[str, Any]:
        return {
            "setting_id": self.setting_id,
            "split": self.split,
            "budget_tokens": self.budget_tokens,
            "mean_span_recall": _f(self.mean_span_recall),
            "mean_token_precision": _f(self.mean_token_precision),
            "mrr": _f(self.mrr),
            "mean_retrieved_tokens": _f(self.mean_retrieved_tokens),
            "fully_covered_count": dict(self.fully_covered_count),
            "no_gold_count": self.no_gold_count,
            "dominated": self.dominated,
        }
