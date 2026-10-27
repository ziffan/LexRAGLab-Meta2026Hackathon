"""Pengemasan anggaran token (EVAL-SPEC §3). Murni; tokenizer disuntik."""

from __future__ import annotations

from typing import Sequence

from backend.metrics.types import PACKING_RULES, PackedChunk, RankedChunk, TokenizerLike, token_offsets


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
        offs = token_offsets(tokenizer, text)[:r]
        # biaya = count(teks terpotong) harus <= r; satu karakter bisa terbelah ke beberapa token,
        # jadi mundur satu token sampai muat. Tak ada yang muat -> tidak masuk dan berhenti (A3).
        while offs:
            new_end = c.start + offs[-1][1]
            text_cost = tokenizer.count(doc[c.start : new_end])
            if text_cost <= r:
                packed.append(PackedChunk(c.start, new_end, hdr + text_cost, hdr, idx, True, c.chunk_id))
                break
            offs.pop()
        break
    return packed
