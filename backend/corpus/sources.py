"""Penguraian tiga string sumber konsolidasi di frontmatter dengan pola sempit (R12)."""

from __future__ import annotations

import datetime as _dt
import re
from typing import Any

from .errors import CorpusError

_MONTHS = {
    "Januari": 1, "Februari": 2, "Maret": 3, "April": 4, "Mei": 5, "Juni": 6, "Juli": 7,
    "Agustus": 8, "September": 9, "Oktober": 10, "November": 11, "Desember": 12,
}  # fmt: skip
_DATE = r"(\d{1,2}) (" + "|".join(_MONTHS) + r") (\d{4})"

_PERPPU = re.compile(
    r"^Perppu No\. (\d+) Tahun (\d{4}) Jo\. Undang-Undang Nomor (\d+) Tahun (\d{4}) "
    r"\(berlaku " + _DATE + r"\) "
    r"\(Perubahan (Pasal \d+[A-Z]?(?:; Pasal \d+[A-Z]?)*), dan Penyisipan Pasal (\d+)([A-Z]) sampai Pasal (\d+)([A-Z])\)$"
)
_UU24 = re.compile(r"^UU No\. (\d+) Tahun (\d{4}) \(berlaku " + _DATE + r"\) \(lihat footnote\)$")
_MK = re.compile(
    r"^Putusan Mahkamah Konstitusi No\. (\d+/PUU-[IVXL]+/\d{4}) "
    r"\(Sidang Pembacaan Putusan tanggal " + _DATE + r"\) \(lihat footnote\)$"
)


def parse_id_date(day: str, month: str, year: str) -> str:
    """'16' 'Agustus' '2007' -> '2007-08-16' (ISO)."""
    return _dt.date(int(year), _MONTHS[month], int(day)).isoformat()


def parse_sources(items: list[str], line: int, cfg: dict[str, Any]) -> dict[str, Any]:
    """Urai tiga string sumber. Gagal -> CorpusError R12."""
    if len(items) != 3:
        raise CorpusError("R12", f"frontmatter 'konsolidasi_dalam_satu_naskah_berdasarkan' (line {line}) must have 3 entries, found {len(items)}")
    m = _PERPPU.match(items[0])
    if not m:
        raise CorpusError("R12", f"Perppu source string (frontmatter line {line}) does not match the narrow pattern: {items[0][:80]!r}")
    pasal_list = [p[len("Pasal "):] for p in m.group(8).split("; ")]
    n1, l1, n2, l2 = m.group(9), m.group(10), m.group(11), m.group(12)
    if n1 != n2 or l1 > l2:
        raise CorpusError("R12", f"Perppu insertion range is invalid (frontmatter line {line}): Pasal {n1}{l1} sampai Pasal {n2}{l2}")
    inserted = [f"{n1}{chr(c)}" for c in range(ord(l1), ord(l2) + 1)]
    perppu = {
        "label": f"Perppu {int(m.group(1))}/{m.group(2)} jo. UU {int(m.group(3))}/{m.group(4)}",
        "effective_from": parse_id_date(m.group(5), m.group(6), m.group(7)),
        "changed": pasal_list,
        "inserted": inserted,
    }
    m = _UU24.match(items[1])
    if not m or (m.group(1), m.group(2)) != (cfg["uu_pengubah_number"], cfg["uu_pengubah_year"]):
        raise CorpusError("R12", f"{cfg["uu_pengubah_label"]} source string (frontmatter line {line}) does not match the narrow pattern: {items[1][:80]!r}")
    uu24 = {"label": cfg["uu_pengubah_label"], "effective_from": parse_id_date(m.group(3), m.group(4), m.group(5))}
    m = _MK.match(items[2])
    if not m:
        raise CorpusError("R12", f"MK source string (frontmatter line {line}) does not match the narrow pattern: {items[2][:80]!r}")
    mk = {"number": m.group(1), "decision_date": parse_id_date(m.group(2), m.group(3), m.group(4))}
    if mk["number"] != cfg["mk_number"]:
        raise CorpusError("R12", f"MK number {mk['number']} (frontmatter line {line}) is not the accepted {cfg['mk_number']}")
    by_kind = {"perppu": perppu, "uu_pengubah": uu24, "mk": mk}
    if list(cfg["source_kinds"]) != ["perppu", "uu_pengubah", "mk"]:
        raise CorpusError("R12", f"config source_kinds {cfg['source_kinds']} is not supported by the narrow patterns")
    return by_kind
