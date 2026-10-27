"""Uji 1 (Exists, V5-strict) dan uji 2 (Faithful) per kutipan; fungsi murni (docs/EVAL-SPEC.md 10, H-067).

Masukan disuntikkan: peta alamat unit (alamat -> AddressUnit), daftar potongan konteks berurutan, `VerifierConfig`.
Tanpa jaringan, tanpa berkas, tanpa state modul. Panjang dan offset dalam code point; skor `fractions.Fraction`."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Callable, Mapping, Sequence

from .config import VerifierConfig
from .fuzzy import FuzzyMatch, fuzzy_match

LULUS, GAGAL = "lulus", "gagal"
NOT_RUN = "tidak_dijalankan"


@dataclass(frozen=True)
class AddressUnit:
    address: str
    start: int
    end: int  # setengah terbuka
    text: str


@dataclass(frozen=True)
class ChunkSpan:
    chunk_id: str
    start: int
    end: int


@dataclass(frozen=True)
class VerifierResult:
    answer_id: str
    citation_index: int
    exists: str
    faithful: str
    faithful_score: Fraction | None
    matched_chunk_id: str | None
    valid_on_date: str = NOT_RUN  # uji 3 di luar M2.3 (H-017)
    status_table_version: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"answer_id": self.answer_id, "citation_index": self.citation_index, "exists": self.exists,
                "faithful": self.faithful,
                "faithful_score": None if self.faithful_score is None else float(self.faithful_score),
                "valid_on_date": self.valid_on_date, "status_table_version": self.status_table_version,
                "matched_chunk_id": self.matched_chunk_id}


@dataclass(frozen=True)
class CitationVerdict:
    result: VerifierResult
    linked: tuple[int, int] | None  # rentang tertaut (V9); None bila uji 1 atau 2 gagal


Scorer = Callable[[str, str], FuzzyMatch]


def overlaps(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    """Irisan tak kosong, ujung eksklusif."""
    return a_start < b_end and b_start < a_end


def digit_runs(s: str) -> list[str]:
    """Deretan maksimal karakter `isdecimal`, urut dari awal. Titik ribuan memisah ("1.000" -> ["1", "000"])."""
    out: list[str] = []
    cur: list[str] = []
    for c in s:
        if c.isdecimal():
            cur.append(c)
        elif cur:
            out.append("".join(cur))
            cur = []
    if cur:
        out.append("".join(cur))
    return out


def _digit_guard(quote: str, text: str, windows: Sequence[tuple[int, int]]) -> bool:
    """V3-on: ADA jendela w di W (diperluas ke kiri/kanan selama ujungnya memotong deret digit) yang daftar
    digitnya sama persis dengan daftar digit kutipan."""
    want = digit_runs(quote)
    n = len(text)
    for i, j in windows:
        while 0 < i < n and text[i - 1].isdecimal() and text[i].isdecimal():
            i -= 1
        while 0 < j < n and text[j - 1].isdecimal() and text[j].isdecimal():
            j += 1
        if digit_runs(text[i:j]) == want:
            return True
    return False


def _first_overlap(chunks: Sequence[ChunkSpan], start: int, end: int) -> str | None:
    for c in chunks:
        if overlaps(c.start, c.end, start, end):
            return c.chunk_id
    return None


def verify_citation(citation: Mapping[str, Any], units: Mapping[str, AddressUnit], chunks: Sequence[ChunkSpan],
                    cfg: VerifierConfig, *, answer_id: str = "", citation_index: int = 0,
                    scorer: Scorer | None = None) -> CitationVerdict:
    score_fn = scorer or fuzzy_match
    addr, quote = citation.get("alamat"), citation.get("teks")

    def out(exists: str, faithful: str, score: Fraction | None = None, linked: tuple[int, int] | None = None):
        mid = _first_overlap(chunks, *linked) if linked is not None else None
        return CitationVerdict(VerifierResult(answer_id, citation_index, exists, faithful, score, mid), linked)

    # Uji 1: alamat sama persis dengan alamat unit; tanpa normalisasi, tanpa awalan (V5-strict).
    unit = units.get(addr) if isinstance(addr, str) else None
    if unit is None:
        return out(GAGAL, GAGAL)  # V6: uji 2 tidak dijalankan, fungsi skor tidak dipanggil
    # V8: kutipan kosong atau hanya spasi tidak dinilai setia.
    if not isinstance(quote, str) or not quote.strip():
        return out(LULUS, GAGAL)
    text = unit.text
    idx = text.find(quote)
    if idx >= 0:  # kutipan persis: skor null, V3 tidak berlaku, rentang tertaut = kemunculan pertama
        return out(LULUS, LULUS, None, (unit.start + idx, unit.start + idx + len(quote)))
    n = len(quote)
    fm = score_fn(quote, text)
    score = Fraction(n - fm.d_min, n)
    ok = score >= cfg.theta and fm.d_min <= cfg.d_max
    if ok and cfg.v3_on:
        ok = _digit_guard(quote, text, fm.windows())
    if not ok:
        return out(LULUS, GAGAL, score)
    return out(LULUS, LULUS, score, (unit.start, unit.end))  # fuzzy lulus: seluruh rentang unit (V9)


def verify_answer_detailed(answer_id: str, output: Mapping[str, Any], units: Mapping[str, AddressUnit],
                           chunks: Sequence[ChunkSpan], cfg: VerifierConfig, *,
                           scorer: Scorer | None = None) -> list[CitationVerdict]:
    """Satu verdict per kutipan, `citation_index` dari 0 berurutan, tanpa deduplikasi (D3). Tanpa kutipan -> []."""
    cites = output.get("kutipan") or []
    return [verify_citation(c, units, chunks, cfg, answer_id=answer_id, citation_index=i, scorer=scorer)
            for i, c in enumerate(cites)]


def verify_answer(answer_id: str, output: Mapping[str, Any], units: Mapping[str, AddressUnit],
                  chunks: Sequence[ChunkSpan], cfg: VerifierConfig, *, scorer: Scorer | None = None) -> list[VerifierResult]:
    return [v.result for v in verify_answer_detailed(answer_id, output, units, chunks, cfg, scorer=scorer)]
