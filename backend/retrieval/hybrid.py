"""Hybrid: Reciprocal Rank Fusion (RRF) atas ranking dense dan BM25 (M1.3).

skor(d) = sum_over_jalur 1 / (k_rrf + rank_jalur(d)), rank mulai 1. Dokumen yang hanya ada di satu jalur
tetap masuk (kontribusi satu jalur). Seri skor dipecah `chunk_id` naik (deterministik).
"""

from __future__ import annotations

from typing import Sequence

Ranking = Sequence[tuple[str, float]]


def rrf(rankings: Sequence[Ranking], *, k_rrf: int, top_n: int | None = None) -> list[tuple[str, float]]:
    """Fusi beberapa ranking `(chunk_id, skor)` yang sudah terurut; hanya urutan yang dipakai, bukan skornya."""
    if k_rrf < 0:
        raise ValueError("k_rrf must be >= 0")
    scores: dict[str, float] = {}
    for ranking in rankings:
        for pos, (cid, _) in enumerate(ranking, start=1):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k_rrf + pos)
    out = sorted(scores.items(), key=lambda x: (-x[1], x[0]))
    return out if top_n is None else out[:top_n]
