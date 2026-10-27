"""Agregasi per butir -> GridPoint, dominasi, frontier (docs/EVAL-SPEC.md §4, §5, §9). Aritmetika eksak."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from fractions import Fraction
from typing import Iterable, Mapping

from backend.grid.types import Frontier, GridPoint, ItemMetrics, Setting


def _mean(values: list[Fraction]) -> Fraction | None:
    return sum(values, Fraction(0)) / len(values) if values else None


def aggregate_points(metrics: Iterable[ItemMetrics], settings: Mapping[str, Setting]) -> list[GridPoint]:
    """Satu GridPoint per (setting_id, split). Rata-rata per butir (bukan pooled), butir tanpa gold dikeluarkan
    dari recall dan precision; `mean_retrieved_tokens` atas semua butir split itu (A11)."""
    groups: dict[tuple[str, str | None], list[ItemMetrics]] = defaultdict(list)
    for m in metrics:
        groups[(m.setting_id, m.split)].append(m)
    points = []
    for (sid, split), ms in groups.items():
        st = settings[sid]
        gold = [m for m in ms if m.gold_chars > 0]
        recalls = [Fraction(m.covered_gold_chars, m.gold_chars) for m in gold]
        precs = [Fraction(m.gold_tokens_retrieved, m.retrieved_tokens) for m in gold if m.retrieved_tokens > 0]
        rrs = [Fraction(m.reciprocal_rank) for m in gold if m.reciprocal_rank is not None]
        points.append(
            GridPoint(
                family=st.family,
                setting_id=sid,
                split=split,
                budget_tokens=st.budget_tokens,
                mean_span_recall=_mean(recalls) if recalls else Fraction(0),
                mean_token_precision=_mean(precs),
                mrr=_mean(rrs),
                mean_retrieved_tokens=Fraction(sum(m.retrieved_tokens for m in ms), len(ms)),
                fully_covered_count=(sum(1 for m in gold if m.covered_gold_chars == m.gold_chars), len(gold)),
                n_gold=len(gold),
            )
        )
    return sorted(points, key=_point_order)


def _point_order(p: GridPoint):
    return (p.family, p.split or "", p.budget_tokens, p.mean_retrieved_tokens, p.setting_id)


def dominates(p: GridPoint, r: GridPoint) -> bool:
    px, py = Fraction(p.mean_retrieved_tokens), Fraction(p.mean_span_recall)
    rx, ry = Fraction(r.mean_retrieved_tokens), Fraction(r.mean_span_recall)
    return py >= ry and px <= rx and (py > ry or px < rx)


def compute_frontiers(points: Iterable[GridPoint], grid_run_id: str) -> tuple[list[GridPoint], list[Frontier]]:
    """Frontier per (family, split, budget_tokens). Mengembalikan titik dengan `dominated` terisi
    (urutan kanonik, bebas urutan masukan) dan daftar Frontier."""
    groups: dict[tuple, list[GridPoint]] = defaultdict(list)
    for p in points:
        groups[(p.family, p.split, p.budget_tokens)].append(p)
    out_points: list[GridPoint] = []
    frontiers: list[Frontier] = []
    for key in sorted(groups, key=lambda k: (k[0], k[1] or "", k[2])):
        grp = groups[key]
        flagged = [replace(p, dominated=any(dominates(q, p) for q in grp if q is not p)) for p in grp]
        flagged.sort(key=_point_order)
        out_points.extend(flagged)
        frontiers.append(
            Frontier(
                family=key[0],
                split=key[1],
                budget_tokens=key[2],
                point_ids=tuple(p.setting_id for p in flagged if not p.dominated),
                grid_run_id=grid_run_id,
            )
        )
    return out_points, frontiers
