"""Uji peta alamat UU PT (M1.1, Tier 2): golden sample, konvensi unit M1.2, G-13, G-20, G-25.

GOLDEN SAMPLE: USULAN AGEN, MENUNGGU KONFIRMASI OPERATOR. Pasal 1, 7, 86 (batang tubuh dan Penjelasan),
102 ayat (1), 142 ayat (2), 153A, dan satu Pasal tanpa ayat (Pasal 2). Jumlah unit dan offset dikunci pada
korpus beku `a6b38ee5…` (H-045); nilai diperiksa terhadap teks, bukan disalin dari keluaran kode.
Tanpa tokenizer, tanpa jaringan, tanpa model.
"""

from __future__ import annotations

import json
from collections import Counter

import pytest

from backend import config
from backend.chunking import build_address_map

from ._chunk_util import PREFIX, U_SECTIONS, U_TEXT, make_doc, real_doc, u_doc

SEP = " › "
SCOPE = set(config.load("retrieval")["scope_sections"])


@pytest.fixture(scope="module")
def doc():
    return real_doc()


@pytest.fixture(scope="module")
def amap(doc):
    return build_address_map(doc.text, doc.sections, PREFIX, SCOPE)


def units_of(amap, pasal, section=None):
    return [u for u in amap.units if u.pasal == pasal and (section is None or u.section == section)]


# ------------------------------------------------------------------ konvensi M1.2 (peta alamat U)
def test_convention_matches_m12_toy_document_u():
    """Peta U di `docs/scenarios/M1.2.md` (A4, A5): rentang tanpa `\\n` penutup, heading Pasal ber-ayat di luar unit,
    Pasal tanpa ayat dan Penjelasan tanpa penanda termasuk heading."""
    d = u_doc()
    m = build_address_map(d.text, d.sections, PREFIX, SCOPE)
    got = {(u.start, u.end): u.address for u in m.units}
    expect = {
        (12, 24): f"{PREFIX}{SEP}Pasal 1{SEP}ayat (1)",
        (25, 37): f"{PREFIX}{SEP}Pasal 1{SEP}ayat (2)",
        (38, 50): f"{PREFIX}{SEP}Pasal 1{SEP}ayat (3)",
        (52, 76): f"{PREFIX}{SEP}Pasal 2",
        (102, 123): f"{PREFIX}{SEP}Penjelasan{SEP}Pasal 1{SEP}Ayat (1)",
        (124, 141): f"{PREFIX}{SEP}Penjelasan{SEP}Pasal 1{SEP}Ayat (2)",
        (142, 163): f"{PREFIX}{SEP}Penjelasan{SEP}Pasal 1{SEP}Ayat (3)",
        (164, 200): f"{PREFIX}{SEP}Penjelasan{SEP}Pasal 2",
    }
    assert got == expect
    assert not m.notes


# ------------------------------------------------------------------ golden sample
GOLDEN_COUNTS = {"1": 2, "7": 16, "86": 18, "102": 10, "142": 12, "153A": 4, "2": 2}  # unit batang tubuh + Penjelasan


@pytest.mark.parametrize("pasal,n", sorted(GOLDEN_COUNTS.items()))
def test_golden_unit_count(amap, pasal, n):
    assert len(units_of(amap, pasal)) == n


def _check_markers(doc, u):
    t = doc.text
    assert t[u.end - 1] not in " \n" and t[u.end] == "\n", "unit must end right before the closing \\n"
    if u.kind == "ayat":
        assert t[u.start:].startswith(f"({u.ayat}) ")
    elif u.kind == "penj_ayat":
        assert t[u.start:].startswith(f"Ayat ({u.ayat})\n")
    elif u.kind == "pasal":
        assert t[u.start:].startswith(f"### Pasal {u.pasal}\n")
    elif u.kind == "penj_pasal":
        assert t[u.start:].startswith(f"#### Penjelasan Pasal {u.pasal}\n")


@pytest.mark.parametrize("pasal", sorted(GOLDEN_COUNTS))
def test_golden_markers_and_addresses(doc, amap, pasal):
    us = units_of(amap, pasal)
    for u in us:
        _check_markers(doc, u)
    bt = [u for u in us if u.section == "batang_tubuh"]
    pj = [u for u in us if u.section == "penjelasan_pasal"]
    if bt[0].kind == "pasal":
        assert [u.address for u in bt] == [f"{PREFIX}{SEP}Pasal {pasal}"]
        assert [u.address for u in pj] == [f"{PREFIX}{SEP}Penjelasan{SEP}Pasal {pasal}"] or pj[0].kind == "penj_ayat"
    else:
        assert [u.address for u in bt] == [f"{PREFIX}{SEP}Pasal {pasal}{SEP}ayat ({i})" for i in range(1, len(bt) + 1)]
    for u in pj:
        if u.kind == "penj_ayat":
            assert u.address == f"{PREFIX}{SEP}Penjelasan{SEP}Pasal {pasal}{SEP}Ayat ({u.ayat})"


def test_golden_offsets_locked(doc, amap):
    got = {u.address: (u.start, u.end) for u in amap.units}
    assert got[f"{PREFIX}{SEP}Pasal 86{SEP}ayat (9)"] == (117805, 118167)
    assert got[f"{PREFIX}{SEP}Penjelasan{SEP}Pasal 86{SEP}Ayat (9)"] == (119414, 119436)
    assert got[f"{PREFIX}{SEP}Pasal 102{SEP}ayat (1)"] == (141974, 142283)
    assert got[f"{PREFIX}{SEP}Pasal 153A{SEP}ayat (1)"] == (202082, 202177)
    assert doc.text[119414:119436] == "Ayat (9)\n\nCukup jelas."
    assert doc.text[117805:117825] == "(9) RUPS kedua dan k"


def test_pasal_without_ayat_includes_heading(doc, amap):
    (u,) = units_of(amap, "2", "batang_tubuh")
    assert u.kind == "pasal" and doc.text[u.start:].startswith("### Pasal 2\n")
    (p1,) = units_of(amap, "1", "batang_tubuh")
    assert p1.kind == "pasal" and len(p1.children) == 16 and all(r.kind == "angka" for r in p1.children)
    assert p1.children[0].address == f"{PREFIX}{SEP}Pasal 1{SEP}angka 1"
    assert doc.text[p1.children[0].start:].startswith("1. Perseroan Terbatas")


def test_pasal_142_ayat_2(doc, amap):
    u = next(u for u in units_of(amap, "142", "batang_tubuh") if u.ayat == 2)
    assert u.address == f"{PREFIX}{SEP}Pasal 142{SEP}ayat (2)"
    assert [r.address for r in u.children] == [f"{u.address}{SEP}huruf a", f"{u.address}{SEP}huruf b"]
    assert doc.text[u.children[0].start:].startswith("a. ")
    assert doc.text[u.start:].startswith("(2) Dalam hal terjadi ")


# ------------------------------------------------------------------ G-20
def test_g20_pasal_86_body_vs_penjelasan_have_different_addresses(amap):
    body = next(u for u in units_of(amap, "86", "batang_tubuh") if u.ayat == 9)
    penj = next(u for u in units_of(amap, "86", "penjelasan_pasal") if u.ayat == 9)
    assert body.address == "UU 40/2007 › Pasal 86 › ayat (9)"
    assert penj.address == "UU 40/2007 › Penjelasan › Pasal 86 › Ayat (9)"
    assert body.address != penj.address and body.section != penj.section
    assert len({u.address for u in amap.units}) == len(amap.units), "alamat harus unik di seluruh dokumen"


# ------------------------------------------------------------------ G-25: kalimat penutup rincian
def test_g25_pasal_102_ayat_1_closing_sentence_belongs_to_ayat(doc, amap):
    u = next(u for u in units_of(amap, "102", "batang_tubuh") if u.ayat == 1)
    closing = "yang merupakan lebih dari 50% (lima puluh persen)"
    ci = doc.text.index(closing, u.start)
    assert u.start < ci < u.end, "kalimat penutup harus di dalam unit ayat (1)"
    ha, hb = u.children
    assert (ha.label, hb.label) == ("huruf a", "huruf b")
    assert doc.text[hb.start:hb.end] == "b. menjadikan jaminan utang kekayaan Perseroan;"
    assert hb.end <= ci, "kalimat penutup tidak boleh masuk huruf terakhir"
    assert doc.text[u.end - 14:u.end] == " maupun tidak."
    assert hb.address == f"{PREFIX}{SEP}Pasal 102{SEP}ayat (1){SEP}huruf b"


def test_g25_wrapped_line_starting_with_paren_is_not_a_new_ayat():
    """Baris hard-wrap `(2) yang ...` (huruf kecil sesudah penanda) dan nomor di luar urutan bukan ayat baru."""
    text = "### Pasal 5\n\n(1) Ketentuan ayat\n(2) yang terpotong bukan ayat baru.\n\n(2) Ayat dua yang asli.\n"
    d = make_doc(text, [("batang_tubuh", 0, len(text))])
    m = build_address_map(d.text, d.sections, PREFIX)
    us = [u for u in m.units if u.section == "batang_tubuh"]
    assert [u.ayat for u in us] == [1, 2]
    assert d.text[us[0].start:us[0].end] == "(1) Ketentuan ayat\n(2) yang terpotong bukan ayat baru."  # baris (2) pertama masih ayat (1)? tidak: nomor 2 = 1 + 1


# ------------------------------------------------------------------ G-13
def test_g13_roman_pasal_I_does_not_fail_and_is_not_recognised():
    """Perilaku: `### Pasal I` (UU pengubah) bukan heading Pasal yang dikenal (hanya `\\d+[A-Z]?`). Ia menutup
    region Pasal sebelumnya dan isinya tidak masuk unit mana pun; tanpa heading dikenal, section jatuh ke
    unit tingkat bagian (fallback). Tidak ada exception. Dukungan UU pengubah tidak dibangun (H-046)."""
    text = "### Pasal I\n\n(1) Ketentuan berubah.\n\n(2) Lainnya.\n"
    d = make_doc(text, [("batang_tubuh", 0, len(text))])
    m = build_address_map(d.text, d.sections, PREFIX)
    assert [u.kind for u in m.units] == ["section"] and m.units[0].fallback

    text2 = "### Pasal 1\n\n(1) Satu.\n\n### Pasal I\n\n(1) Romawi.\n"
    d2 = make_doc(text2, [("batang_tubuh", 0, len(text2))])
    m2 = build_address_map(d2.text, d2.sections, PREFIX)
    assert [u.address for u in m2.units] == [f"{PREFIX}{SEP}Pasal 1{SEP}ayat (1)"]  # isi Pasal I di luar unit


# ------------------------------------------------------------------ struktur penuh korpus
def test_real_corpus_full_coverage_and_no_notes(doc, amap):
    assert amap.notes == []
    assert Counter(u.kind for u in amap.units) == {"ayat": 540, "penj_ayat": 431, "penj_pasal": 69, "pasal": 29, "penj_umum": 1}
    assert len({u.pasal for u in amap.units if u.section == "batang_tubuh"}) == 171
    assert len({u.pasal for u in amap.units if u.section == "penjelasan_pasal"}) == 171
    prev_end = -1
    for u in amap.units:  # terurut dan tidak tumpang-tindih
        assert u.start >= prev_end and u.start < u.end
        prev_end = u.end
        sec = next(s for s in doc.sections if s["section"] == u.section and s["start"] <= u.start and u.end <= s["end"])
        assert sec
        for r in u.children:
            assert u.start < r.start < r.end <= u.end
    # tak ada isi yang jatuh di luar unit: sisa teks dalam section cakupan hanya spasi atau baris heading
    covered = [False] * len(doc.text)
    for u in amap.units:
        for i in range(u.start, u.end):
            covered[i] = True
    for s in doc.sections:
        if s["section"] not in SCOPE:
            continue
        pos = s["start"]
        for line in doc.text[s["start"]:s["end"]].split("\n"):
            if line.strip() and not any(covered[pos:pos + len(line)]):
                assert line.startswith("#"), f"isi di luar unit pada offset {pos}: {line[:60]!r}"
            pos += len(line) + 1


def test_section_without_markers_gets_a_single_fallback_unit():
    text = "Pembukaan teks.\n\nIsi bebas tanpa heading.\n\nLagi.\n\nPenjelasan bebas.\n"
    b0, p0 = text.index("Isi bebas"), text.index("Penjelasan bebas")
    d = make_doc(text, [("pembukaan", 0, b0), ("batang_tubuh", b0, p0), ("penjelasan_pasal", p0, len(text))])
    m = build_address_map(d.text, d.sections, PREFIX)
    assert [(u.section, u.fallback) for u in m.units] == [("batang_tubuh", True), ("penjelasan_pasal", True)]
    assert d.text[m.units[0].start:m.units[0].end] == "Isi bebas tanpa heading.\n\nLagi."


def test_gold_vs_unit_boundaries_report_runs_without_asserting(doc, amap):
    """Bukan assert keras (brief G3): tabel butir kontrol dihasilkan oleh `gold_boundary_table` untuk laporan."""
    rows = gold_boundary_table(doc, amap)
    assert len(rows) >= 9


def gold_boundary_table(doc, amap):
    """Untuk tiap gold span di `data/butir/uupt.v1.jsonl`: apakah awal/akhir jatuh di batas unit (awal/akhir unit ayat)."""
    path = config.REPO_ROOT / "data" / "butir" / "uupt.v1.jsonl"
    starts = {u.start: u for u in amap.units}
    ends = {u.end: u for u in amap.units}
    rows = []
    for line in path.read_bytes().decode("utf-8").splitlines():
        if not line.strip():
            continue
        it = json.loads(line)
        if not it["gold_spans"]:
            rows.append((it["id"], None, None, None, "no gold"))
            continue
        for sp in it["gold_spans"]:
            s, e = sp["start"], sp["end"]
            us = amap.overlapping(s, e)
            rows.append((it["id"], (s, e), starts[s].address if s in starts else None, ends[e].address if e in ends else None,
                         f"{len(us)} unit(s): {us[0].address if us else '-'}{' .. ' + us[-1].address if len(us) > 1 else ''}"))
    return rows

