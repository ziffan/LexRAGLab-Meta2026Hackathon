"""Agregasi per butir -> GridPoint, dominasi, frontier (docs/EVAL-SPEC.md §4, §5, §9). Aritmetika eksak."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import fields, replace
from fractions import Fraction
from typing import Iterable, Mapping

from backend.grid.types import Frontier, GridPoint, Setting
from backend.metrics.aggregate import aggregate
from backend.metrics.types import GridPoint as _Contract
from backend.metrics.types import ItemMetrics


def _mean(values: list[Fraction]) -> Fraction | None:
    return sum(values, Fraction(0)) / len(values) if values else None


def aggregate_points(metrics: Iterable[ItemMetrics], settings: Mapping[str, Setting]) -> list[GridPoint]:
    """Satu GridPoint per (setting_id, split) lewat `backend.metrics.aggregate` (M1.2: rata-rata per butir
    bergold, None bila tanpa gold, `mean_retrieved_tokens` atas butir bergold saja, A8)."""
    groups: dict[tuple[str, str | None], list[ItemMetrics]] = defaultdict(list)
    for m in metrics:
        groups[(m.setting_id, m.split)].append(m)
    points = []
    for (sid, split), ms in groups.items():
        st = settings[sid]
        c = aggregate(ms, setting_id=sid, split=split, budget_tokens=st.budget_tokens)
        points.append(GridPoint(**{f: getattr(c, f) for f in _CONTRACT_FIELDS}, family=st.family,
                                n_gold=sum(1 for m in ms if m.has_gold)))
    return sorted(points, key=_point_order)


_CONTRACT_FIELDS = tuple(f.name for f in fields(_Contract))


def comparable(p: GridPoint) -> bool:
    """Titik tanpa butir bergold (nilai None) tidak ikut frontier (H-059, I-33)."""
    return p.mean_span_recall is not None and p.mean_retrieved_tokens is not None


def _point_order(p: GridPoint):
    x = p.mean_retrieved_tokens
    return (p.family, p.split or "", p.budget_tokens, x is None, x if x is not None else Fraction(0), p.setting_id)


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
        valid = [p for p in grp if comparable(p)]
        flagged = [
            replace(p, dominated=comparable(p) and any(dominates(q, p) for q in valid if q is not p)) for p in grp
        ]
        flagged.sort(key=_point_order)
        out_points.extend(flagged)
        frontiers.append(
            Frontier(
                family=key[0],
                split=key[1],
                budget_tokens=key[2],
                point_ids=tuple(p.setting_id for p in flagged if comparable(p) and not p.dominated),
                grid_run_id=grid_run_id,
            )
        )
    return out_points, frontiers
