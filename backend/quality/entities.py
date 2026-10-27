"""Entity preservation (EVAL-SPEC §7). Pola disuntik; tiap pola dipindai terpisah (A1)."""
from __future__ import annotations

import re
from typing import Iterable, Sequence

from .types import ChunkSpan

Pattern = str | re.Pattern[str]


def find_entities(text: str, patterns: Iterable[Pattern]) -> list[tuple[int, int]]:
    """Kemunculan entitas di teks dokumen (A3): per kemunculan, bukan per potongan."""
    found: list[tuple[int, int]] = []
    for p in patterns:
        rx = re.compile(p) if isinstance(p, str) else p
        for m in rx.finditer(text):
            if m.end() > m.start():
                found.append((m.start(), m.end()))
    found.sort()
    return found


def preserved(entity: tuple[int, int], chunks: Sequence[ChunkSpan]) -> bool:
    """Semantik himpunan (A2): ada satu potongan yang memuat seluruh entitas."""
    s, e = entity
    return any(c.start <= s and e <= c.end for c in chunks)


def entity_counts(
    text: str, chunks: Sequence[ChunkSpan], patterns: Iterable[Pattern]
) -> tuple[int, int]:
    """(terjaga, total) atas teks dokumen; header tidak dipindai (A4)."""
    ents = find_entities(text, patterns)
    return sum(1 for e in ents if preserved(e, chunks)), len(ents)
