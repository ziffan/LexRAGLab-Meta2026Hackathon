"""Pencocokan substring aproksimatif (Sellers) pada tingkat code point (V1-B, docs/EVAL-SPEC.md 10).

`d_min` = jarak edit Levenshtein minimum antara kutipan dan sembarang substring teks unit. Pencarian memakai
bit-parallel Myers (bilangan bulat Python); `windows` memberi himpunan W semua substring yang berjarak tepat `d_min`
(bahan pengaman angka V3). Murni: tanpa I/O."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class FuzzyMatch:
    d_min: int
    windows: Callable[[], list[tuple[int, int]]]  # malas: dihitung hanya bila pengaman angka perlu


def _search_row(pattern: str, text: str) -> list[int]:
    """D[m][j] untuk j = 0..len(text): jarak edit minimum pola ke substring yang berakhir di j (Myers/Hyyro, Sellers)."""
    m = len(pattern)
    if m == 0:
        return [0] * (len(text) + 1)
    peq: dict[str, int] = {}
    for i, c in enumerate(pattern):
        peq[c] = peq.get(c, 0) | (1 << i)
    mask = (1 << m) - 1
    hi = 1 << (m - 1)
    pv, mv, score = mask, 0, m
    out = [score]
    for c in text:
        eq = peq.get(c, 0)
        xv = eq | mv
        xh = (((eq & pv) + pv) ^ pv) | eq
        ph = mv | (~(xh | pv) & mask)
        mh = pv & xh
        if ph & hi:
            score += 1
        elif mh & hi:
            score -= 1
        ph = (ph << 1) & mask  # baris 0 Sellers bernilai 0: tanpa carry-in
        mh = (mh << 1) & mask
        pv = mh | (~(xv | ph) & mask)
        mv = ph & xv
        out.append(score)
    return out


def search_row_naive(pattern: str, text: str) -> list[int]:
    """Pembanding lambat (DP penuh) untuk test dan kelurusan kode."""
    m = len(pattern)
    col = list(range(m + 1))
    out = [col[m]]
    for c in text:
        new = [0] * (m + 1)
        for i in range(1, m + 1):
            new[i] = min(col[i] + 1, new[i - 1] + 1, col[i - 1] + (pattern[i - 1] != c))
        col = new
        out.append(col[m])
    return out


def _starts_for_end(pattern: str, text: str, end: int, d: int) -> list[int]:
    """Semua i dengan jarak edit(pattern, text[i:end]) == d (panjang jendela di [m-d, m+d])."""
    m = len(pattern)
    kmax = min(end, m + d)
    rp, rt = pattern[::-1], text[end - kmax:end][::-1]  # kolom k = jendela sepanjang k yang berakhir di `end`
    prev = list(range(kmax + 1))  # baris 0: edit("", rt[:k]) = k
    for i in range(1, m + 1):
        cur = [i] + [0] * kmax
        pc = rp[i - 1]
        for k in range(1, kmax + 1):
            cur[k] = min(prev[k] + 1, cur[k - 1] + 1, prev[k - 1] + (pc != rt[k - 1]))
        prev = cur
    return [end - k for k in range(kmax + 1) if prev[k] == d]


def fuzzy_match(quote: str, unit_text: str) -> FuzzyMatch:
    row = _search_row(quote, unit_text)
    d_min = min(row)
    ends = [j for j, v in enumerate(row) if v == d_min]

    def windows() -> list[tuple[int, int]]:
        seen: set[tuple[int, int]] = set()
        for j in ends:
            for i in _starts_for_end(quote, unit_text, j, d_min):
                seen.add((i, j))
        return sorted(seen)

    return FuzzyMatch(d_min, windows)
