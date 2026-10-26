"""Validasi struktur teks bersih (R8-R11) dan penentuan lima `section` (DATA-CONTRACTS §2)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .errors import CorpusError

SECTIONS = ("pembukaan", "penjelasan_umum", "batang_tubuh", "penjelasan_pasal", "pengesahan")

_ANY_HEADING = re.compile(r"^#")
_H_UMUM = "## PENJELASAN UMUM"
_H_PENGESAHAN = "## PENGESAHAN DAN PENGUNDANGAN"
_H_BAB = re.compile(r"^## BAB ([IVXL]+) — \S.*$")
_H_BAGIAN = re.compile(r"^### Bagian \S+ — \S.*$")
_H_PARAGRAF = re.compile(r"^#### Paragraf \d+ — \S.*$")
_H_PASAL = re.compile(r"^### Pasal (\d+[A-Z]?)$")
_H_PENJ = re.compile(r"^#### Penjelasan Pasal (\d+[A-Z]?)$")

AYAT = re.compile(r"^\((\d+)\)(?:\s|$)")
BUTIR = re.compile(r"^([a-z]|\d+)\.\s")
_BUTIR_END = re.compile(r";( atau| dan)?$")
_CUKUP_JELAS = re.compile(r"^\s*cukup jelas\.?\s*$", re.IGNORECASE)


def is_cukup_jelas(line: str) -> bool:
    """'Cukup jelas' tanpa bergantung pada titik (Penjelasan Pasal 153E ayat (2) tanpa titik)."""
    return bool(_CUKUP_JELAS.match(line))


def _roman(n: int) -> str:
    out = ""
    for val, sym in ((10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")):
        while n >= val:
            out += sym
            n -= val
    return out


@dataclass
class Heading:
    kind: str  # umum, bab, bagian, paragraf, pasal, penj, pengesahan
    idx: int  # indeks baris di teks bersih
    ref: str | None = None  # nomor Pasal / angka romawi BAB


def classify_headings(lines: list[tuple[str, int]]) -> list[Heading]:
    """Semua heading harus sah (R11)."""
    out: list[Heading] = []
    for i, (t, ln) in enumerate(lines):
        if not _ANY_HEADING.match(t):
            continue
        if t == _H_UMUM:
            out.append(Heading("umum", i))
        elif t == _H_PENGESAHAN:
            out.append(Heading("pengesahan", i))
        elif m := _H_BAB.match(t):
            out.append(Heading("bab", i, m.group(1)))
        elif _H_BAGIAN.match(t):
            out.append(Heading("bagian", i))
        elif _H_PARAGRAF.match(t):
            out.append(Heading("paragraf", i))
        elif m := _H_PASAL.match(t):
            out.append(Heading("pasal", i, m.group(1)))
        elif m := _H_PENJ.match(t):
            out.append(Heading("penj", i, m.group(1)))
        else:
            raise CorpusError("R11", f"heading not allowed by the frozen file format at source line {ln}: {t[:70]!r}")
    return out


def validate_structure(lines: list[tuple[str, int]], headings: list[Heading], cfg: dict[str, Any]) -> None:
    """R10, R11, R8, R9 atas teks bersih."""
    kinds = [h.kind for h in headings]
    if kinds.count("umum") != 1:
        raise CorpusError("R11", f"expected exactly one '{_H_UMUM}' heading, found {kinds.count('umum')}")
    if kinds.count("pengesahan") != 1:
        raise CorpusError("R11", f"expected exactly one '{_H_PENGESAHAN}' heading, found {kinds.count('pengesahan')}")
    babs = [h for h in headings if h.kind == "bab"]
    want = [_roman(n) for n in range(1, cfg["bab_count"] + 1)]
    if [h.ref for h in babs] != want:
        raise CorpusError("R11", f"BAB headings must be I..{want[-1]} in order ({cfg['bab_count']}), found {[h.ref for h in babs]}")
    # urutan besar: umum < BAB I ... < pengesahan; Pasal/Penjelasan di antara BAB I dan pengesahan
    if headings[0].kind != "umum" or headings[-1].kind != "pengesahan" or headings[1].kind != "bab":
        raise CorpusError("R11", "heading order must be: PENJELASAN UMUM, BAB I ..., PENGESAHAN DAN PENGUNDANGAN")
    for h in headings[1:-1]:
        if h.kind in ("umum", "pengesahan"):
            raise CorpusError("R11", f"unexpected top-level heading inside the body at source line {lines[h.idx][1]}")

    # R10: Pasal dan Penjelasan
    pasal = [h for h in headings if h.kind == "pasal"]
    penj = [h for h in headings if h.kind == "penj"]
    n_want = cfg["pasal_count"]
    for name, hs in (("### Pasal", pasal), ("#### Penjelasan Pasal", penj)):
        refs = [h.ref for h in hs]
        if len(hs) != n_want:
            raise CorpusError("R10", f"expected {n_want} '{name}' headings, found {len(hs)}")
        dup = sorted({r for r in refs if refs.count(r) > 1})
        if dup:
            raise CorpusError("R10", f"duplicate '{name}' numbers: {dup}")
    if [h.ref for h in pasal] != [h.ref for h in penj]:
        for a, b in zip(pasal, penj):
            if a.ref != b.ref:
                raise CorpusError("R10", f"Penjelasan order differs from Pasal order: Pasal {a.ref} (source line {lines[a.idx][1]}) vs Penjelasan Pasal {b.ref} (source line {lines[b.idx][1]})")
    # penjelasan harus langsung mengikuti Pasal bernomor sama (sebelum Pasal berikutnya)
    last: Heading | None = None
    seen_penj_for: set[str] = set()
    for h in headings:
        if h.kind == "pasal":
            last = h
        elif h.kind == "penj":
            if last is None or last.ref != h.ref or h.ref in seen_penj_for:
                raise CorpusError("R10", f"'Penjelasan Pasal {h.ref}' at source line {lines[h.idx][1]} does not directly follow its '### Pasal {h.ref}'")
            seen_penj_for.add(h.ref)

    # R8, R9 per badan Pasal batang tubuh
    ends = {headings[k].idx: (headings[k + 1].idx if k + 1 < len(headings) else len(lines)) for k in range(len(headings))}
    for h in pasal:
        body = [(lines[i][0], lines[i][1]) for i in range(h.idx + 1, ends[h.idx])]
        expect = 1
        prev = ""
        for t, ln in body:
            if not t:
                continue
            if m := AYAT.match(t):
                n = int(m.group(1))
                if n != expect:
                    raise CorpusError("R8", f"Pasal {h.ref}: ayat numbering broken at source line {ln}: expected ({expect}), found ({n})")
                expect += 1
            elif t[0].islower() and not BUTIR.match(t):
                if not (BUTIR.match(prev) and _BUTIR_END.search(prev)):
                    raise CorpusError("R9", f"Pasal {h.ref}: line starting with a lowercase letter at source line {ln} is not a closing sentence after a butir ending with ';', '; atau' or '; dan'")
            prev = t


def build_sections(lines: list[tuple[str, int]], headings: list[Heading], starts: list[int], total: int) -> list[dict[str, Any]]:
    """Rentang {section,start,end} yang menutup [0,total) tanpa celah/tumpang."""
    raw: list[tuple[str, int]] = [("pembukaan", 0)]
    for h in headings:
        sec = {"umum": "penjelasan_umum", "pengesahan": "pengesahan", "penj": "penjelasan_pasal"}.get(h.kind, "batang_tubuh")
        if sec != raw[-1][0]:
            raw.append((sec, starts[h.idx]))
    out = []
    for k, (sec, s) in enumerate(raw):
        e = raw[k + 1][1] if k + 1 < len(raw) else total
        out.append({"section": sec, "start": s, "end": e})
    # verifikasi penutupan
    if out[0]["start"] != 0 or out[-1]["end"] != total or any(a["end"] != b["start"] or a["start"] >= a["end"] for a, b in zip(out, out[1:])):
        raise CorpusError("R11", "internal error: section ranges do not tile the clean text")
    return out
