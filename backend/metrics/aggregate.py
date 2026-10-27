"""Agregat setting (EVAL-SPEC §4, §9; DATA-CONTRACTS §10): rata-rata per butir atas butir bergold."""

from __future__ import annotations

from fractions import Fraction
from typing import Sequence

from backend.metrics.types import GridPoint, ItemMetrics


def _mean(values: Sequence[Fraction]) -> Fraction | None:
    return sum(values, Fraction(0)) / len(values) if values else None


def mean_recall_at_k(items: Sequence[ItemMetrics]) -> Fraction | None:
    """Agregat Recall@K atas butir dengan nilai non-null; tanpa itu -> None (QualityMetrics)."""
    return _mean([m.recall_at_k for m in items if m.recall_at_k is not None])


def aggregate(items: Sequence[ItemMetrics], *, setting_id: str, split: str | None, budget_tokens: int) -> GridPoint:
    gold = [m for m in items if m.has_gold]
    covered = sum(1 for m in gold if m.fully_covered)
    return GridPoint(
        setting_id=setting_id,
        split=split,
        budget_tokens=budget_tokens,
        mean_span_recall=_mean([m.span_recall for m in gold]),
        mean_token_precision=_mean([m.token_precision for m in gold if m.token_precision is not None]),
        mrr=_mean([m.reciprocal_rank for m in gold]),
        mean_retrieved_tokens=_mean([Fraction(m.retrieved_tokens) for m in gold]),
        fully_covered_count={"covered": covered, "total": len(gold)},
        no_gold_count=len(items) - len(gold),
    )
