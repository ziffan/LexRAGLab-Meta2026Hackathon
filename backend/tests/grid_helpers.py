"""Pembantu test grid: data sintetis, tanpa chunker/retrieval/tokenizer sungguhan."""

from __future__ import annotations

from fractions import Fraction

from backend.grid.types import GridItem, GridPoint, ItemMetrics, Setting

SIMPLICITY = {
    "tie_margin_items": 1,
    "order": ["header_b_off", "smaller_overlap", "single_retrieval_mode"],
    "mode_order": ["hybrid", "dense", "bm25"],  # tiruan: bukan alfabetis, bukan enum
}


def mk_items(groups: dict[tuple[str, str], list[str]], family: str = "uupt") -> list[GridItem]:
    """groups: {(origin, mode): [ids]}"""
    out = []
    for (origin, mode), ids in groups.items():
        out.extend(GridItem(id=i, family=family, origin=origin, mode=mode) for i in ids)
    return out


def ids(prefix: str, a: int, b: int) -> list[str]:
    return [f"{prefix}{n}" for n in range(a, b + 1)]


def mk_setting(sid, *, mode="bm25", header=False, overlap=0, budget=2000, chunker="fixed_size",
               size=256, family="uupt") -> Setting:
    return Setting(sid, family, chunker, size if chunker == "fixed_size" else None,
                   overlap if chunker == "fixed_size" else None, None, mode, header, budget)


def rows(item_ids, split, setting_id, spec):
    """spec: list of (gold_chars, covered, retrieved_tokens, gold_tokens)."""
    return [ItemMetrics(i, setting_id, split, g, c, r, t) for i, (g, c, r, t) in zip(item_ids, spec)]


def const_rows(item_ids, split, setting_id, covered, *, gold=10, retrieved=1000, gold_tokens=200):
    return rows(item_ids, split, setting_id, [(gold, c, retrieved, gold_tokens) for c in covered])


def cov(n_full: int, n_total: int):
    return [10] * n_full + [0] * (n_total - n_full)


def make_point(sid, x, y, *, split="tune", budget=2000, family="uupt", prec=None, n_gold=10):
    return GridPoint(family, sid, split, budget, Fraction(str(y)), prec, None, Fraction(str(x)), (0, n_gold),
                     False, n_gold)
