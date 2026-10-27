"""Operasi interval setengah terbuka `[start, end)` atas code point (DATA-CONTRACTS §1)."""

from __future__ import annotations

from typing import Iterable

Interval = tuple[int, int]


def merge(spans: Iterable[Interval]) -> list[Interval]:
    """Gabungkan interval bertumpuk atau bersentuhan; keluaran terurut. Interval kosong dibuang."""
    items = sorted((s, e) for s, e in spans if e > s)
    out: list[list[int]] = []
    for s, e in items:
        if out and s <= out[-1][1]:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return [(s, e) for s, e in out]


def size(spans: Iterable[Interval]) -> int:
    return sum(e - s for s, e in merge(spans))


def intersect(a: Iterable[Interval], b: Iterable[Interval]) -> list[Interval]:
    """Irisan dua himpunan interval (masing-masing digabung dulu)."""
    ma, mb = merge(a), merge(b)
    out: list[Interval] = []
    i = j = 0
    while i < len(ma) and j < len(mb):
        s = max(ma[i][0], mb[j][0])
        e = min(ma[i][1], mb[j][1])
        if e > s:
            out.append((s, e))
        if ma[i][1] < mb[j][1]:
            i += 1
        else:
            j += 1
    return out


def contains_all(outer: Iterable[Interval], start: int, end: int) -> bool:
    """True bila `[start, end)` seluruhnya ada di himpunan `outer` (inklusif di kedua ujung)."""
    for s, e in merge(outer):
        if s <= start and end <= e:
            return True
    return False
