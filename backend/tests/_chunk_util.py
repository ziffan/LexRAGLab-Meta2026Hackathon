"""Pembantu test chunking: dokumen nyata sekali muat, dokumen sintetis, tokenizer mainan `toy-ws`."""

from __future__ import annotations

import hashlib
import re
from functools import lru_cache
from types import SimpleNamespace
from typing import Any

from backend.corpus import CorpusDoc, load_corpus

PREFIX = "UU 40/2007"


@lru_cache(maxsize=1)
def real_doc() -> CorpusDoc:
    return load_corpus()


class ToyWs:
    """Token = deretan karakter bukan-spasi (seperti `toy-ws` skenario M1.2). Bukan tokenizer H-014."""

    info = SimpleNamespace(name="toy-ws", version="1")

    def offsets(self, text: str) -> list[tuple[int, int]]:
        return [(m.start(), m.end()) for m in re.finditer(r"\S+", text)]

    def count(self, text: str) -> int:
        return len(self.offsets(text))


def make_doc(text: str, sections: list[tuple[str, int, int]], prefix: str = PREFIX, doc_id: str = "synthetic") -> CorpusDoc:
    """CorpusDoc sintetis; `sections` = [(nama, start, end)]."""
    return CorpusDoc(
        doc_id=doc_id, family="uupt", title="synthetic", path="synthetic.md", sha256="0" * 64,
        clean_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(), loader_rules_version="1", char_count=len(text),
        tokens_local=None, tokens_endpoint=None, calibration_ratio=None,
        sections=[{"section": n, "start": s, "end": e} for n, s, e in sections], annotations=[], text=text,
        metadata={"address_prefix": prefix},
    )


# Dokumen mainan U dari docs/scenarios/M1.2.md ("Dokumen mainan U", panjang 201).
U_TEXT = (
    "### Pasal 1\n(1) Aaa bbb.\n(2) Ccc ddd.\n(3) Eee fff.\n\n"
    "### Pasal 2\nGgg hhh iii.\n\n"
    "#### Penjelasan Pasal 1\nAyat (1)\nCukup jelas.\nAyat (2)\nJjj kkk.\nAyat (3)\nCukup jelas.\n"
    "#### Penjelasan Pasal 2\nCukup jelas.\n"
)
U_SECTIONS = [("batang_tubuh", 0, 78), ("penjelasan_pasal", 78, 201)]


def u_doc() -> CorpusDoc:
    assert len(U_TEXT) == 201
    return make_doc(U_TEXT, U_SECTIONS)
