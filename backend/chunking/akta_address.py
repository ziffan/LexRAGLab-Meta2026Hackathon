"""Peta alamat akta dari `SchemaA` (M4.1, DATA-CONTRACTS §3): akta tidak punya parser tulisan tangan, jadi alamat
diturunkan dari penanda level pada skema yang sama dengan yang menggerakkan chunker skema. Antarmuka `AddressFn`.

Format USULAN (spec diam untuk akta; butir untuk operator, belum dikunci): `<awalan> › Pasal 3 › ayat (2) › huruf a`,
awalan = `address_prefix` dokumen di `config/corpus_akta.toml` (mis. `Akta 01`), pemisah ` › `, rentang ` – ` seperti UU PT.

Aturan (deterministik, tidak menyebut nama level tertentu):
- Tiap level punya daftar penanda (`re.finditer` pola level di seluruh teks; posisi = karakter bukan-spasi pertama sejak awal
  kecocokan). Komponen alamat = teks penanda tanpa tanda baca akhir (`.:;,`). Bila teks itu diawali kata (>= 2 huruf, mis.
  `Pasal 3`) dipakai apa adanya; selain itu (mis. `(2)`, `a.`) diawali nama level huruf kecil (`ayat (2)`, `huruf a`).
- Alamat di posisi p: daun = penanda dengan posisi terbesar <= p (seri: level `order` lebih besar); leluhur = penanda terakhir
  tiap level pada rantai `parent_order` daun sampai posisi daun. Level tanpa penanda sebelum posisi itu dilewati.
- Potongan [start, end): alamat di `start` (semua level) dan di `end-1` (hanya level rantai daun awal). Sama -> satu alamat;
  beda -> `<alamat awal> – <alamat akhir>`. Tanpa penanda sebelum `start` (potongan cadangan per section): `<awalan> › Batang Tubuh`.
"""

from __future__ import annotations

import re
from bisect import bisect_right
from typing import Any, Mapping

from backend.schema_a.schema import compile_marker

from .address_map import RANGE_SEP
from .model import SEP

_SECTION_LABELS = {"batang_tubuh": "Batang Tubuh", "penjelasan_pasal": "Penjelasan", "penjelasan_umum": "Penjelasan Umum"}


def _component(matched: str, name: str) -> str:
    first = next((ln.strip() for ln in matched.splitlines() if ln.strip()), "")
    t = first.rstrip(".:;,").strip()
    if not t:
        return name
    return t if len(re.match(r"[^\W\d_]*", t).group(0)) >= 2 else f"{name.lower()} {t}"


def schema_address_fn(doc: Any, record: Mapping[str, Any], prefix: str | None = None):
    """`AddressFn` untuk `doc` menurut `record["body"]` (SchemaRecord). Pola dikompilasi lewat `compile_marker`."""
    body = record["body"]
    text = doc.text
    pre = prefix or doc.metadata.get("address_prefix") or doc.doc_id
    parent: dict[int, int | None] = {}
    name_of: dict[int, str] = {}
    reach: dict[int, list[int]] = {}
    label: dict[int, list[str]] = {}
    for lv in body["levels"]:
        o = lv["order"]
        rx, why = compile_marker(lv["marker_pattern"])
        if rx is None:
            raise ValueError(f"level {o} ({lv['name']}): {why}")
        parent[o], name_of[o] = lv["parent_order"], lv["name"]
        seen: dict[int, str] = {}
        for m in rx.finditer(text):
            p = m.start()
            while p < len(text) and text[p].isspace():
                p += 1
            seen.setdefault(p, _component(m.group(0), lv["name"]))
        pos = sorted(seen)
        reach[o], label[o] = pos, [seen[p] for p in pos]

    def path(p: int, allowed: set[int]) -> list[tuple[int, str]]:
        best: tuple[int, int] | None = None
        for o in allowed:
            i = bisect_right(reach[o], p) - 1
            if i >= 0 and (best is None or (reach[o][i], o) > best):
                best = (reach[o][i], o)
        if best is None:
            return []
        leaf_pos, o = best
        out: list[tuple[int, str]] = []
        while o is not None:
            i = bisect_right(reach[o], leaf_pos) - 1
            if i >= 0:
                out.append((o, label[o][i]))
            o = parent.get(o)
        return out[::-1]

    def chain_orders(o: int) -> set[int]:
        out: set[int] = set()
        while o is not None and o not in out:
            out.add(o)
            o = parent.get(o)
        return out

    def render(items: list[tuple[int, str]]) -> str:
        return SEP.join([pre, *[c for _o, c in items]])

    def fn(start: int, end: int, section: str) -> tuple[str, list[dict[str, str]], list[str]]:
        head = path(start, set(reach))
        if not head:
            lab = _SECTION_LABELS.get(section, section)
            return SEP.join([pre, lab]), [{"level": "peraturan", "label": pre}, {"level": "section", "label": section}], []
        tail = path(max(start, end - 1), chain_orders(head[-1][0]))
        base = [{"level": "peraturan", "label": pre}, {"level": "section", "label": section}]
        if tail == head or not tail:
            return render(head), base + [{"level": name_of[o].lower(), "label": c} for o, c in head], []
        common: list[dict[str, str]] = []
        for (oa, ca), (ob, cb) in zip(head, tail):
            if (oa, ca) != (ob, cb):
                break
            common.append({"level": name_of[oa].lower(), "label": ca})
        return f"{render(head)}{RANGE_SEP}{render(tail)}", base + common, []
    return fn
