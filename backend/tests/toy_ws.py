"""Tokenizer mainan `toy-ws` versi `1` (docs/scenarios/M1.2.md "Definisi bersama") dan dokumen mainan."""

from __future__ import annotations

import re
from dataclasses import dataclass

from backend.metrics.item import compute_item_metrics
from backend.metrics.types import RankedChunk

BIG = 10**6


@dataclass(frozen=True)
class Info:
    name: str = "toy-ws"
    version: str = "1"


class ToyWs:
    info = Info()

    def count(self, text: str) -> int:
        return len(re.findall(r"\S+", text))

    def offsets(self, text: str):
        return [(m.start(), m.end()) for m in re.finditer(r"\S+", text)]


TOK = ToyWs()

T = " ".join([f"a{i}" for i in range(10)] + [f"b{i}" for i in range(10)])
T_UNITS = [(0, 59)]
assert len(T) == 59

V = "aa bb aa bb aa bb"
W = "§1 \U0001F600a bb"  # "§1 😀a bb"

U = (
    "### Pasal 1\n(1) Aaa bbb.\n(2) Ccc ddd.\n(3) Eee fff.\n\n"
    "### Pasal 2\nGgg hhh iii.\n\n"
    "#### Penjelasan Pasal 1\nAyat (1)\nCukup jelas.\nAyat (2)\nJjj kkk.\nAyat (3)\nCukup jelas.\n"
    "#### Penjelasan Pasal 2\nCukup jelas.\n"
)
U_UNITS = [(12, 24), (25, 37), (38, 50), (52, 76), (102, 123), (124, 141), (142, 163), (164, 200)]
assert len(U) == 201


def tk(i: int, j: int) -> tuple[int, int]:
    """Potongan T yang mencakup token i..j."""
    return (3 * i, 3 * j + 2)


C1, C2, C3, C4 = tk(0, 3), tk(4, 8), tk(9, 10), tk(11, 13)
assert (C1, C2, C3, C4) == ((0, 11), (12, 26), (27, 32), (33, 41))


def rc(*spans, header: str = ""):
    return [RankedChunk(s, e, header) for s, e in spans]


def run(doc, gold, spans, budget=BIG, packing="stop", k=1, units=None, header="", ranked=None):
    if ranked is None:
        ranked = rc(*spans, header=header)
    return compute_item_metrics(
        doc, gold, ranked, budget, TOK, packing=packing, k=k, units=T_UNITS if units is None else units
    )
