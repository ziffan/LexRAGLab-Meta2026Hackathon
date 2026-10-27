"""Pengemasan anggaran token (EVAL-SPEC §3). Murni; tokenizer disuntik."""

from __future__ import annotations

from typing import Sequence

from backend.metrics.types import PACKING_RULES, PackedChunk, RankedChunk, TokenizerLike


def pack(
    doc: str,
    ranked: Sequence[RankedChunk],
    budget: int,
    tokenizer: TokenizerLike,
    packing: str = "stop",
) -> list[PackedChunk]:
    """Telusuri `C` berurutan; masuk selama akumulasi <= budget. Potongan pertama yang melewati
    budget ditangani `stop` (default, A11), `skip`, atau `truncate`. Biaya = tok(header) + tok(teks)."""
    if packing not in PACKING_RULES:
        raise ValueError(f"unknown packing rule: {packing!r}")
    packed: list[PackedChunk] = []
    acc = 0
    for idx, c in enumerate(ranked, start=1):
        text = doc[c.start : c.end]
        hdr = tokenizer.count(c.header) if c.header else 0
        cost = hdr + tokenizer.count(text)
        if acc + cost <= budget:
            acc += cost
            packed.append(PackedChunk(c.start, c.end, cost, hdr, idx, False, c.chunk_id))
            continue
        if packing == "skip":
            continue
        if packing == "stop":
            break
        # truncate: sisa teks r = budget - acc - header; r <= 0 -> tidak masuk dan berhenti (A3)
        r = budget - acc - hdr
        if r <= 0:
            break
        offs = list(tokenizer.offsets(text))[:r]
        if not offs:
            break
        new_end = c.start + offs[-1][1]
        packed.append(PackedChunk(c.start, new_end, hdr + len(offs), hdr, idx, True, c.chunk_id))
        acc += hdr + len(offs)
        break
    return packed
