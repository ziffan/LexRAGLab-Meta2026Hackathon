"""Boundary coherence (EVAL-SPEC §7)."""
from __future__ import annotations

from typing import Collection, Iterable, Sequence

from .types import ChunkSpan


def sent(text: str, b: int, abbreviations: Collection[str]) -> bool:
    """Akhir kalimat di posisi b (end eksklusif) -- A14, diekspos untuk uji.

    text[b-1] == "." DAN (b == len(text) ATAU text[b] spasi/newline) DAN run huruf
    persis sebelum titik (batas kata) bukan singkatan. Run kosong -> bukan singkatan.
    """
    if b < 1 or b > len(text) or text[b - 1] != ".":
        return False
    if b < len(text) and text[b] not in " \n":
        return False
    i = b - 1
    while i > 0 and text[i - 1].isalpha():
        i -= 1
    word = text[i : b - 1]
    return not (word and word in abbreviations)


def is_ok(
    text: str, b: int, structure_bounds: Collection[int], abbreviations: Collection[str]
) -> bool:
    return b in structure_bounds or sent(text, b, abbreviations)


def boundaries(text: str, chunks: Iterable[ChunkSpan]) -> list[int]:
    """Bnd: satu per potongan (A9), end != akhir dokumen; tak bergantung urutan."""
    n = len(text)
    return [c.end for c in chunks if c.end != n]


def boundary_counts(
    text: str,
    chunks: Sequence[ChunkSpan],
    structure_bounds: Collection[int],
    abbreviations: Collection[str],
) -> tuple[int, int]:
    """(ok, total)."""
    bnd = boundaries(text, chunks)
    return sum(1 for b in bnd if is_ok(text, b, structure_bounds, abbreviations)), len(bnd)
