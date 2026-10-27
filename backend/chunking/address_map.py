"""Peta alamat UU PT dari parser struktur tulisan tangan atas teks bersih (DATA-CONTRACTS §2, §3).

Satu peta dipakai semua chunker (prinsip keadilan). Konvensi unit sama dengan skenario M1.2
("Peta alamat U" dan putusan A4/A5, `docs/scenarios/M1.2.md`):

- Rentang unit setengah terbuka dan tanpa `\\n` penutup (berakhir di karakter non-spasi terakhir).
- Pasal ber-ayat: heading `### Pasal n` di luar semua unit alamat (tetapi di dalam potongan struktur ayat pertama, H-064, lewat `Unit.chunk_start`); unit ayat = dari penanda `(m)` sampai sebelum
  penanda berikutnya (ayat terakhir: sampai akhir isi Pasal). Kalimat penutup rincian milik ayat (G-25).
- Pasal tanpa ayat: satu unit, TERMASUK heading.
- Penjelasan Pasal ber-penanda: unit "Ayat (m)" = baris penanda + isi sampai sebelum penanda berikutnya.
  Heading `#### Penjelasan Pasal n` di luar unit. Tanpa penanda "Ayat (m)": satu unit termasuk heading.
- Penjelasan Umum: satu unit termasuk heading `## PENJELASAN UMUM`.
- Rincian (huruf `a.`, angka `1.`) tidak membentuk unit potong; ia dicatat sebagai `children` dari unit
  untuk alamat. Rincian = satu baris butir (tanpa kalimat penutup). Angka setelah huruf pada ayat yang sama
  bersarang di bawah huruf itu.
- Penanda ayat hanya sah bila nomornya = ayat sebelumnya + 1 (mulai 1) dan teks sesudahnya tidak diawali
  huruf kecil: baris `(n)` hasil hard-wrap tidak menjadi ayat palsu (G-25).
- Section tanpa penanda struktur sama sekali: satu unit tingkat bagian (`fallback`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from backend.corpus.structure import AYAT, BUTIR

from .model import SEP

_PASAL_H = re.compile(r"^### Pasal (\d+[A-Z]?)$")
_PENJ_H = re.compile(r"^#### Penjelasan Pasal (\d+[A-Z]?)$")
_H_UMUM = "## PENJELASAN UMUM"
_PENJ_AYAT = re.compile(r"^Ayat \((\d+)\)$")
RANGE_SEP = " – "  # en dash, DATA-CONTRACTS §3

Lines = list[tuple[int, int, str]]
Levels = tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class Rincian:
    kind: str  # "huruf" | "angka"
    label: str  # "huruf a" | "angka 1"
    start: int
    end: int
    address: str
    levels: Levels


@dataclass(frozen=True)
class Unit:
    kind: str  # pasal | ayat | penj_pasal | penj_ayat | penj_umum | section
    section: str
    start: int
    end: int
    address: str
    levels: Levels
    pasal: str | None = None
    ayat: int | None = None
    fallback: bool = False
    children: tuple[Rincian, ...] = ()
    # H-064: awal POTONGAN struktur bila lebih awal dari `start` (unit pertama Pasal melebar ke heading Pasal).
    # `start`/`end` tetap unit alamat konvensi M1.2 A4 (Recall@K); hanya batas potongan yang melebar.
    chunk_start: int | None = None

    @property
    def lead(self) -> int:
        return self.start if self.chunk_start is None else self.chunk_start


def levels_to_dicts(levels: Levels) -> list[dict[str, str]]:
    return [{"level": a, "label": b} for a, b in levels]


@dataclass
class AddressMap:
    units: list[Unit]
    notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.units.sort(key=lambda u: (u.start, u.end))

    def in_sections(self, sections: set[str]) -> list[Unit]:
        return [u for u in self.units if u.section in sections]

    def overlapping(self, start: int, end: int, section: str | None = None) -> list[Unit]:
        """Unit yang beririsan tak-kosong dengan [start, end), berurutan."""
        return [u for u in self.units if u.start < end and start < u.end and (section is None or u.section == section)]

    def address_for_range(self, start: int, end: int, section: str, prefix: str, section_label: str,
                          *, across_sections: bool = False) -> tuple[str, list[dict[str, str]], list[str]]:
        """Alamat potongan [start,end) dalam `section`.

        Satu unit: alamat unit, atau rincian terdalam yang memuat seluruh potongan. Beberapa unit:
        "<alamat awal> – <alamat akhir>", levels = awalan bersama unit pertama dan terakhir.
        Tanpa irisan dengan unit mana pun: alamat tingkat bagian + peringatan.
        `across_sections` (H-062): potongan boleh melintasi section; irisan dihitung atas semua section, `section`
        (section posisi awal) hanya dipakai untuk alamat cadangan."""
        ov = self.overlapping(start, end, None if across_sections else section)
        if not ov:
            lv = [{"level": "peraturan", "label": prefix}, {"level": "section", "label": section}]
            return SEP.join([prefix, section_label]), lv, ["no address unit overlaps this chunk"]
        first, last = ov[0], ov[-1]
        if first is last:
            best = None
            for r in first.children:  # urutan dokumen; huruf lalu angka-anaknya
                if r.start <= start and end <= r.end:
                    best = r  # angka bersarang berada setelah induknya, jadi yang terakhir cocok = terdalam
            if best is not None:
                return best.address, levels_to_dicts(best.levels), []
            return first.address, levels_to_dicts(first.levels), []
        common: list[dict[str, str]] = []
        for a, b in zip(levels_to_dicts(first.levels), levels_to_dicts(last.levels)):
            if a != b:
                break
            common.append(a)
        return f"{first.address}{RANGE_SEP}{last.address}", common, []


def _iter_lines(text: str, s: int, e: int) -> Lines:
    """Baris yang mulai di [s, e): (awal, akhir tanpa \\n, isi), dipotong di e."""
    out: Lines = []
    pos = s
    while pos < e:
        nl = text.find("\n", pos, e)
        le = e if nl == -1 else nl
        out.append((pos, le, text[pos:le]))
        if nl == -1:
            break
        pos = nl + 1
    return out


def _content_end(lines: Lines) -> int | None:
    for ls, _le, t in reversed(lines):
        if t.strip():
            return ls + len(t.rstrip())
    return None


def _first_content_start(lines: Lines) -> int | None:
    for ls, _le, t in lines:
        if t.strip():
            return ls + (len(t) - len(t.lstrip()))
    return None


def _rincian(lines: Lines, base_levels: Levels, base_address: str) -> tuple[Rincian, ...]:
    out: list[Rincian] = []
    cur_huruf: Rincian | None = None
    for ls, _le, t in lines:
        m = BUTIR.match(t)
        if not m:
            continue
        tag = m.group(1)
        end = ls + len(t.rstrip())
        if tag.isalpha():
            lab = f"huruf {tag}"
            r = Rincian("huruf", lab, ls, end, f"{base_address}{SEP}{lab}", base_levels + (("huruf", lab),))
            cur_huruf = r
        else:
            lab = f"angka {tag}"
            if cur_huruf is not None:
                r = Rincian("angka", lab, ls, end, f"{cur_huruf.address}{SEP}{lab}", cur_huruf.levels + (("angka", lab),))
            else:
                r = Rincian("angka", lab, ls, end, f"{base_address}{SEP}{lab}", base_levels + (("angka", lab),))
        out.append(r)
    return tuple(out)


def _regions(lines: Lines, heading_re: re.Pattern[str]) -> list[tuple[str, Lines]]:
    """Pecah baris section atas heading yang dikenal. Heading '#' lain (mis. `### Pasal I`, BAB) hanya
    menutup region. Kembali [(nomor, baris region termasuk heading)]."""
    out: list[tuple[str, Lines]] = []
    cur: tuple[str, Lines] | None = None
    for ln in lines:
        t = ln[2]
        m = heading_re.match(t)
        if m:
            cur = (m.group(1), [ln])
            out.append(cur)
        elif t.startswith("#"):
            cur = None
        elif cur is not None:
            cur[1].append(ln)
    return out


def _batang_units(text: str, sec: dict[str, Any], prefix: str, notes: list[str]) -> list[Unit]:
    lines = _iter_lines(text, sec["start"], sec["end"])
    units: list[Unit] = []
    for pasal, region in _regions(lines, _PASAL_H):
        head, body = region[0], region[1:]
        plabel = f"Pasal {pasal}"
        base_levels: Levels = (("peraturan", prefix), ("section", "batang_tubuh"), ("pasal", plabel))
        base_addr = f"{prefix}{SEP}{plabel}"
        marks: list[int] = []  # indeks di body; nomor ayat = urutan + 1 (G-25)
        for i, (_ls, _le, t) in enumerate(body):
            m = AYAT.match(t)
            if m and int(m.group(1)) == len(marks) + 1 and not t[m.end():m.end() + 1].islower():
                marks.append(i)
        if not marks:
            end = _content_end(region)
            assert end is not None  # heading tidak kosong
            units.append(Unit("pasal", "batang_tubuh", head[0], end, base_addr, base_levels, pasal=pasal,
                              children=_rincian(body, base_levels, base_addr)))
            continue
        if _first_content_start(body[: marks[0]]) is not None:
            notes.append(f"{plabel}: text between the heading and ayat (1) is outside every unit")
        for k, i in enumerate(marks):
            j = marks[k + 1] if k + 1 < len(marks) else len(body)
            seg = body[i:j]
            end = _content_end(seg)
            assert end is not None
            lab = f"ayat ({k + 1})"
            lv = base_levels + (("ayat", lab),)
            addr = f"{base_addr}{SEP}{lab}"
            units.append(Unit("ayat", "batang_tubuh", body[i][0], end, addr, lv, pasal=pasal, ayat=k + 1,
                              children=_rincian(seg[1:], lv, addr), chunk_start=head[0] if k == 0 else None))
    return units


def _penj_units(text: str, sec: dict[str, Any], prefix: str) -> list[Unit]:
    lines = _iter_lines(text, sec["start"], sec["end"])
    units: list[Unit] = []
    for pasal, region in _regions(lines, _PENJ_H):
        head, body = region[0], region[1:]
        plabel = f"Pasal {pasal}"
        base_levels: Levels = (("peraturan", prefix), ("section", "penjelasan_pasal"), ("pasal", plabel))
        base_addr = f"{prefix}{SEP}Penjelasan{SEP}{plabel}"
        marks: list[int] = []
        for i, (_ls, _le, t) in enumerate(body):
            m = _PENJ_AYAT.match(t)
            if m and int(m.group(1)) == len(marks) + 1:
                marks.append(i)
        if not marks:
            end = _content_end(region)
            assert end is not None
            units.append(Unit("penj_pasal", "penjelasan_pasal", head[0], end, base_addr, base_levels, pasal=pasal))
            continue
        pre = body[: marks[0]]
        has_pre = _first_content_start(pre) is not None
        if has_pre:  # isi sebelum "Ayat (1)": unit tingkat Pasal (heading + isi itu)
            units.append(Unit("penj_pasal", "penjelasan_pasal", head[0], _content_end(pre) or head[1], base_addr, base_levels, pasal=pasal))
        for k, i in enumerate(marks):
            j = marks[k + 1] if k + 1 < len(marks) else len(body)
            end = _content_end(body[i:j])
            assert end is not None
            lab = f"Ayat ({k + 1})"
            units.append(Unit("penj_ayat", "penjelasan_pasal", body[i][0], end, f"{base_addr}{SEP}{lab}",
                              base_levels + (("ayat", lab),), pasal=pasal, ayat=k + 1,
                              chunk_start=head[0] if k == 0 and not has_pre else None))
    return units


PARSED_SECTIONS = ("batang_tubuh", "penjelasan_pasal", "penjelasan_umum")


def build_address_map(text: str, sections: list[dict[str, Any]], prefix: str, scope: set[str] | None = None,
                      section_labels: dict[str, str] | None = None) -> AddressMap:
    """Peta alamat atas teks bersih. `scope=None` = semua section yang punya parser."""
    labels = {"batang_tubuh": "Batang Tubuh", "penjelasan_pasal": "Penjelasan", "penjelasan_umum": "Penjelasan Umum"}
    labels.update(section_labels or {})
    notes: list[str] = []
    units: list[Unit] = []
    for sec in sections:
        name = sec["section"]
        if name not in PARSED_SECTIONS or (scope is not None and name not in scope):
            continue
        lines = _iter_lines(text, sec["start"], sec["end"])
        s0, e0 = _first_content_start(lines), _content_end(lines)
        if s0 is None or e0 is None:
            continue  # section kosong
        if name == "penjelasan_umum":
            has_head = any(t == _H_UMUM for _ls, _le, t in lines)
            addr = f"{prefix}{SEP}{labels[name]}"
            units.append(Unit("penj_umum", name, s0, e0, addr, (("peraturan", prefix), ("section", name)), fallback=not has_head))
            continue
        got = _batang_units(text, sec, prefix, notes) if name == "batang_tubuh" else _penj_units(text, sec, prefix)
        if got:
            units.extend(got)
        else:  # tanpa penanda struktur: satu unit tingkat bagian
            units.append(Unit("section", name, s0, e0, f"{prefix}{SEP}{labels[name]}", (("peraturan", prefix), ("section", name)), fallback=True))
    return AddressMap(units, notes)
