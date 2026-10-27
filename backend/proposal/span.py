"""Satu-satunya fungsi validasi span (scenarios/M2.1 A1, A31). Offset code point, setengah terbuka `[start, end)`.

Dipakai W4 (usulan Spark), pemeriksaan batas `edited` W5, dan uji tingkat fungsi. Implementasi kedua dilarang.
Tanpa normalisasi apa pun (H-046): perbandingan persis."""

from __future__ import annotations

from typing import NamedTuple


class SpanCheck(NamedTuple):
    offset_found: bool
    text_matches: bool
    resolved_span: dict[str, int] | None


_FAIL = SpanCheck(False, False, None)


def _is_int(v: object) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def find_unique(document: str, needle: str) -> int | None:
    """Indeks tunggal kemunculan `needle` (termasuk yang tumpang-tindih); None bila 0 atau >= 2 kali."""
    if not needle:
        return None
    first = document.find(needle)
    if first < 0:
        return None
    return first if document.find(needle, first + 1) < 0 else None


def validate_span(document: str, teks_gold: str, start: object, end: object) -> SpanCheck:
    """(`offset_found`, `text_matches`, `resolved_span`).

    - `start` dan `end` keduanya integer: `offset_found = 0 <= start < end <= len(document)`; `text_matches` = itu DAN
      `document[start:end] == teks_gold`; `resolved_span` = `{start, end}` bila `offset_found`, selain itu None.
      Tanpa pencarian cadangan bila offset salah (A4).
    - Selain itu (keduanya None, atau hanya satu terisi: diabaikan, A3): cari `teks_gold`; tepat satu kemunculan ->
      (True, True, span itu); selain itu (False, False, None) (A2).
    - `teks_gold` kosong -> (False, False, None)."""
    if not isinstance(teks_gold, str) or not teks_gold:
        return _FAIL
    if _is_int(start) and _is_int(end):
        n = len(document)
        if not (0 <= start < end <= n):
            return _FAIL
        span = {"start": int(start), "end": int(end)}
        return SpanCheck(True, document[start:end] == teks_gold, span)
    at = find_unique(document, teks_gold)
    if at is None:
        return _FAIL
    return SpanCheck(True, True, {"start": at, "end": at + len(teks_gold)})


def span_in_bounds(document: str, start: object, end: object) -> bool:
    """Batas `edited.gold_spans` (A9): integer JSON sejati, `0 <= start < end <= len(document)` code point.
    Lewat `validate_span` supaya tidak ada implementasi batas kedua."""
    if not (_is_int(start) and _is_int(end)):
        return False
    if not (0 <= start < end <= len(document)):
        return False
    return validate_span(document, document[start:end], start, end).offset_found
