"""Tipe data grid (docs/DATA-CONTRACTS.md §4, §10). Angka rata-rata memakai Fraction (eksak)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from fractions import Fraction
from typing import Any, Iterable


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class GridItem:
    """Butir minimal yang dibutuhkan grid; isi gold ikut `item_set_hash`."""

    id: str
    family: str
    origin: str
    mode: str
    clean_sha256: str = ""
    gold_spans: tuple[tuple[int, int], ...] = ()


def item_set_hash(items: Iterable[GridItem]) -> str:
    rows = [asdict(i) for i in sorted(items, key=lambda i: i.id)]
    return sha256_hex(canonical_json(rows))


@dataclass(frozen=True)
class Setting:
    setting_id: str
    family: str
    chunker: str
    chunk_size_tokens: int | None
    overlap_tokens: int | None
    schema_version: int | None
    retrieval_mode: str
    header_b: bool
    budget_tokens: int


def setting_content(s: Setting) -> dict[str, Any]:
    d = asdict(s)
    d.pop("setting_id")
    return d


def compute_setting_id(content: dict[str, Any]) -> str:
    return sha256_hex(canonical_json(content))


@dataclass(frozen=True)
class ItemMetrics:
    """Pembilang dan penyebut integer; rasio dihitung eksak di agregasi."""

    item_id: str
    setting_id: str
    split: str | None
    gold_chars: int
    covered_gold_chars: int
    retrieved_tokens: int
    gold_tokens_retrieved: int
    reciprocal_rank: Fraction | None = None
    recall_at_k: Fraction | None = None
    retrieved_chunk_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        for k in ("reciprocal_rank", "recall_at_k"):
            if d[k] is not None:
                d[k] = str(d[k])
        d["retrieved_chunk_ids"] = list(self.retrieved_chunk_ids)
        return d

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "ItemMetrics":
        d = dict(d)
        for k in ("reciprocal_rank", "recall_at_k"):
            if d.get(k) is not None:
                d[k] = Fraction(d[k])
        d["retrieved_chunk_ids"] = tuple(d.get("retrieved_chunk_ids", ()))
        return ItemMetrics(**d)


@dataclass(frozen=True)
class GridPoint:
    """`family` dan `n_gold` adalah tambahan di atas kontrak §10 (kunci kelompok dan penyebut pita)."""

    family: str
    setting_id: str
    split: str | None
    budget_tokens: int
    mean_span_recall: Fraction
    mean_token_precision: Fraction | None
    mrr: Fraction | None
    mean_retrieved_tokens: Fraction
    fully_covered_count: tuple[int, int]
    dominated: bool = False
    n_gold: int = 0


@dataclass(frozen=True)
class Frontier:
    family: str
    split: str | None
    budget_tokens: int
    point_ids: tuple[str, ...]
    grid_run_id: str


@dataclass(frozen=True)
class Assignment:
    item_id: str
    split: str
    added_in_version: int


@dataclass(frozen=True)
class SplitRecord:
    family: str
    split_version: int
    seed: int
    held_out_ratio: float
    strata: tuple[str, ...]
    assignments: tuple[Assignment, ...]
    control_in_held_out: int

    def split_of(self) -> dict[str, str]:
        return {a.item_id: a.split for a in self.assignments}

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "split_version": self.split_version,
            "seed": self.seed,
            "held_out_ratio": self.held_out_ratio,
            "strata": list(self.strata),
            "assignments": [asdict(a) for a in self.assignments],
            "control_in_held_out": self.control_in_held_out,
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "SplitRecord":
        return SplitRecord(
            family=d["family"],
            split_version=d["split_version"],
            seed=d["seed"],
            held_out_ratio=d["held_out_ratio"],
            strata=tuple(d["strata"]),
            assignments=tuple(Assignment(**a) for a in d["assignments"]),
            control_in_held_out=d["control_in_held_out"],
        )
