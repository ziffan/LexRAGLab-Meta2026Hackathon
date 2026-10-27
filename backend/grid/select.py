"""Pemilihan profil di tune saja (docs/EVAL-SPEC.md §9, H-034, H-033, H-055). Held-out hanya untuk laporan."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Iterable, Mapping

from backend.grid.types import NO_SPLIT_FAMILY, GridPoint, Setting


class SelectionNotApplicable(Exception):
    """Keluarga tanpa pemilihan profil (akta, H-054)."""


@dataclass(frozen=True)
class Selection:
    family: str
    budget_tokens: int
    setting_id: str
    tune_point: GridPoint
    held_out_point: GridPoint | None  # hanya untuk laporan; tidak pernah ikut memilih


def mode_rank_table(simplicity: Mapping[str, Any], known_modes: Iterable[str] = ()) -> dict[str, int]:
    """Urutan mode, paling sederhana dulu. `mode_order` eksplisit bila ada; bila tidak,
    `single_retrieval_modes` (urutan config) lebih sederhana daripada mode lain."""
    explicit = simplicity.get("mode_order")
    if explicit:
        return {m: i for i, m in enumerate(explicit)}
    single = list(simplicity.get("single_retrieval_modes", []))
    rank = {m: i for i, m in enumerate(single)}
    for m in sorted(set(known_modes) - set(single)):
        rank[m] = len(rank)
    return rank


def simplicity_key(setting: Setting, simplicity: Mapping[str, Any], ranks: Mapping[str, int]) -> tuple:
    key = []
    for crit in simplicity["order"]:
        if crit == "header_b_off":
            key.append(1 if setting.header_b else 0)
        elif crit == "smaller_overlap":
            key.append(setting.overlap_tokens or 0)  # null dibaca 0 (A7)
        elif crit == "single_retrieval_mode":
            key.append(ranks.get(setting.retrieval_mode, len(ranks)))
        else:
            raise ValueError(f"unknown simplicity criterion: {crit!r}")
    return tuple(key)


def select_profiles(
    points: Iterable[GridPoint],
    settings: Mapping[str, Setting],
    simplicity: Mapping[str, Any],
    *,
    family: str,
    n_tune_gold: int | None = None,
) -> dict[int, Selection]:
    """Pilih per anggaran, hanya dari titik `tune`."""
    if family == NO_SPLIT_FAMILY:
        raise SelectionNotApplicable(f"family {family!r} has no profile selection (H-054)")
    points = list(points)
    margin = simplicity["tie_margin_items"]
    ranks = mode_rank_table(simplicity, (s.retrieval_mode for s in settings.values()))
    tune: dict[int, list[GridPoint]] = defaultdict(list)
    held: dict[tuple[int, str], GridPoint] = {}
    for p in points:
        if p.family != family:
            continue
        if p.split == "tune":
            if p.mean_span_recall is None:
                continue  # tanpa butir bergold: tidak bisa dipilih (H-059)
            tune[p.budget_tokens].append(p)
        elif p.split == "held_out":
            held[(p.budget_tokens, p.setting_id)] = p
    out: dict[int, Selection] = {}
    for budget in sorted(tune):
        cand = tune[budget]
        n = n_tune_gold if n_tune_gold is not None else max(p.n_gold for p in cand)
        best = max(Fraction(p.mean_span_recall) for p in cand)
        band = Fraction(margin, n) if n > 0 else Fraction(0)
        pool = [p for p in cand if Fraction(p.mean_span_recall) >= best - band]

        def order(p: GridPoint):
            prec = p.mean_token_precision
            return (
                simplicity_key(settings[p.setting_id], simplicity, ranks),
                (prec is None, -Fraction(prec) if prec is not None else Fraction(0)),
                Fraction(p.mean_retrieved_tokens),
                p.setting_id,
            )

        chosen = min(pool, key=order)
        out[budget] = Selection(family, budget, chosen.setting_id, chosen, held.get((budget, chosen.setting_id)))
    return out
