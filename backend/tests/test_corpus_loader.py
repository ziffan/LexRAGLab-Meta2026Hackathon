"""Uji pemuat korpus UU PT (M0.2, G2): kasus positif dan penolakan R1-R13 (DATA-CONTRACTS §2).

Uji R5-R12 berjalan atas salinan termutasi di tmp_path dengan `verify_hash=False`; berkas di data/ tidak disentuh.
Tanpa jaringan, tanpa model, tanpa tokenizer.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

import pytest

from backend import config
from backend.corpus import CorpusError, load_corpus, propose_status_rows
from backend.corpus.frontmatter import parse_frontmatter
from backend.corpus.structure import is_cukup_jelas

CFG = config.load("corpus")
ENTRY = CFG["documents"][0]
SRC = config.REPO_ROOT / ENTRY["path"]
ORIG = SRC.read_bytes().decode("utf-8")
SEP = " › "


# ---------------------------------------------------------------- helper
def write(tmp_path: Path, data: bytes | str, name: str = "korpus.md") -> Path:
    p = tmp_path / name
    p.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
    return p


def mutated(tmp_path: Path, fn: Callable[[list[str]], list[str] | None]) -> Path:
    """Salin korpus ke tmp_path setelah `fn` memutasi daftar baris (in place atau mengembalikan daftar baru)."""
    lines = ORIG.split("\n")
    res = fn(lines)
    return write(tmp_path, "\n".join(res if res is not None else lines))


def load_mut(tmp_path: Path, fn: Callable[[list[str]], list[str] | None]):
    return load_corpus(path=mutated(tmp_path, fn), verify_hash=False)


def reject(tmp_path: Path, fn: Callable[[list[str]], list[str] | None], code: str, match: str = "") -> CorpusError:
    with pytest.raises(CorpusError) as ei:
        load_mut(tmp_path, fn)
    assert ei.value.code == code, str(ei.value)
    if match:
        assert re.search(match, ei.value.message), ei.value.message
    return ei.value


def idx(lines: list[str], exact: str) -> int:
    return lines.index(exact)


def body_end(lines: list[str], start: int) -> int:
    j = start + 1
    while j < len(lines) and not lines[j].startswith("#"):
        j += 1
    return j


def first_pasal_with_ayat(lines: list[str], n: int) -> tuple[str, int, int]:
    """(nomor Pasal, indeks heading, indeks akhir badan) pertama yang punya ayat (n)."""
    for i, t in enumerate(lines):
        m = re.match(r"^### Pasal (\d+[A-Z]?)$", t)
        if m:
            e = body_end(lines, i)
            if any(re.match(rf"^\({n}\) ", x) for x in lines[i:e]):
                return m.group(1), i, e
    raise AssertionError("no such Pasal")


@pytest.fixture(scope="module")
def doc():
    return load_corpus()


# ---------------------------------------------------------------- positif
def test_positive_real_file_facts(doc):
    assert doc.doc_id == "uupt-40-2007" and doc.family == "uupt"
    assert doc.sha256 == ENTRY["sha256"]
    assert doc.loader_rules_version == CFG["loader_rules_version"]
    assert doc.tokens_local is None and doc.tokens_endpoint is None and doc.calibration_ratio is None
    assert doc.char_count == len(doc.text) and doc.text.endswith("\n") and not doc.text.endswith("\n\n")
    assert len(re.findall(r"(?m)^### Pasal ", doc.text)) == 171
    assert len(re.findall(r"(?m)^#### Penjelasan Pasal ", doc.text)) == 171
    types = [a["type"] for a in doc.annotations]
    assert types.count("footnote") == 2 and types.count("label") == 2
    assert types.count("frontmatter") == 1 and types.count("disclaimer") == 1
    assert [s["section"] for s in doc.sections][:2] == ["pembukaan", "penjelasan_umum"]
    assert {s["section"] for s in doc.sections} == {"pembukaan", "penjelasan_umum", "batang_tubuh", "penjelasan_pasal", "pengesahan"}


def test_positive_clean_text_has_no_markers(doc):
    t = doc.text
    assert "[^" not in t and "**" not in t and "\r" not in t and "﻿" not in t
    assert not re.search(r"(?m)^---$", t)
    assert not re.search(r"(?m)^(jenis|nomor|tahun|tentang|konsolidasi_dalam_satu_naskah_berdasarkan|lembaran_negara|catatan|catatan_koreksi|perubahan_pasca_pakai):", t)
    assert "\n\n\n" not in t
    assert t.startswith("UNDANG-UNDANG REPUBLIK INDONESIA\n")
    assert "Bukan naskah LN/BN" not in t  # disclaimer = metadata, bukan teks bersih
    assert "PUTUSAN MAHKAMAH KONSTITUSI NOMOR 84/PUU-XI/2013" not in t


def test_positive_sections_tile_clean_text(doc):
    s = doc.sections
    assert s[0]["start"] == 0 and s[-1]["end"] == len(doc.text)
    assert all(a["end"] == b["start"] for a, b in zip(s, s[1:]))
    assert all(x["start"] < x["end"] for x in s)
    by = {}
    for x in s:
        by[x["section"]] = by.get(x["section"], 0) + 1
    assert by["pembukaan"] == 1 and by["penjelasan_umum"] == 1 and by["pengesahan"] == 1
    assert by["batang_tubuh"] == 171 and by["penjelasan_pasal"] == 171
    # heading BAB/Bagian/Paragraf masuk batang_tubuh
    for m in re.finditer(r"(?m)^(## BAB .*|### Bagian .*|#### Paragraf .*)$", doc.text):
        if m.start() > next(x["end"] for x in s if x["section"] == "penjelasan_umum"):
            sec = next(x["section"] for x in s if x["start"] <= m.start() < x["end"])
            assert sec == "batang_tubuh", m.group(0)
    # Penjelasan Pasal N ada di penjelasan_pasal, Pasal N di batang_tubuh (G-20)
    for m in re.finditer(r"(?m)^### Pasal 86$|^#### Penjelasan Pasal 86$", doc.text):
        sec = next(x["section"] for x in s if x["start"] <= m.start() < x["end"])
        assert sec == ("batang_tubuh" if m.group(0).startswith("### ") else "penjelasan_pasal")
    pembukaan = doc.text[s[0]["start"] : s[0]["end"]]
    assert "Menetapkan:" in pembukaan and "## PENJELASAN UMUM" not in pembukaan
    assert doc.text[s[-1]["start"] :].startswith("## PENGESAHAN DAN PENGUNDANGAN")


def test_positive_annotation_offsets_anchor_in_final_text(doc):
    lab = {a["pasal"]: a for a in doc.annotations if a["type"] == "label"}
    assert doc.text[lab["86"]["offset"] :].startswith("### Pasal 86\n")
    assert doc.text[lab["142"]["offset"] :].startswith("### Pasal 142\n")
    assert lab["86"]["address"] == f"UU 40/2007{SEP}Pasal 86"
    fn = {a["n"]: a for a in doc.annotations if a["type"] == "footnote"}
    # [^1] dibuang di akhir ayat (9); [^2] dibuang sebelum "; dan" pada butir a
    assert doc.text[: fn[1]["offset"]].endswith("pengadilan negeri.") and doc.text[fn[1]["offset"] :].startswith("\n")
    assert doc.text[: fn[2]["offset"]].endswith("kurator") and doc.text[fn[2]["offset"] :].startswith("; dan\n")
    assert fn[1]["address"] == f"UU 40/2007{SEP}Pasal 86{SEP}ayat (9)"
    assert fn[2]["address"] == f"UU 40/2007{SEP}Pasal 142{SEP}ayat (2){SEP}huruf a"
    assert "84/PUU-XI/2013" in fn[1]["definition"] and "Nomor 24 Tahun 2011" in fn[2]["definition"]
    # offset ada dalam batang_tubuh
    for a in fn.values():
        sec = next(s["section"] for s in doc.sections if s["start"] <= a["offset"] < s["end"] or a["offset"] == s["end"])
        assert sec in ("batang_tubuh",)


def test_positive_line_map_points_to_source_lines(doc):
    src = ORIG.split("\n")
    clean = doc.text.split("\n")
    starts = [m[0] for m in doc.line_map]
    assert len(doc.line_map) == len(clean) - 1  # elemen terakhir '' setelah LF akhir
    pos = 0
    for k, line in enumerate(clean[:-1]):
        assert starts[k] == pos
        pos += len(line) + 1
    pend = next(s["end"] for s in doc.sections if s["section"] == "pembukaan")
    for (off, ln), line in zip(doc.line_map, clean):
        if off < pend or not line:
            continue
        orig_line = src[ln - 1]
        assert orig_line.replace("[^1]", "").replace("[^2]", "") == line


def test_positive_status_proposal_is_exactly_the_specified_set(doc):
    prop = propose_status_rows(doc)
    assert prop["proposed_by"] == "loader" and prop["approved_by_operator"] is False
    addr = [e["address"] for e in prop["entries"]]
    pp = ["1", "7", "32", "153"] + [f"153{c}" for c in "ABCDEFGHIJ"]
    assert addr == [f"UU 40/2007{SEP}Pasal {p}" for p in pp] + [
        f"UU 40/2007{SEP}Pasal 86{SEP}ayat (9)",
        f"UU 40/2007{SEP}Pasal 142{SEP}ayat (2){SEP}huruf a",
    ]
    assert len(prop["entries"]) == 16
    for e in prop["entries"][:14]:
        assert e["amended_by"] == ["Perppu 2/2022 jo. UU 6/2023"] and e["effective_from"] == "2022-12-30"
        assert e["status"] == "berlaku" and e["interpreted_by"] == []
        assert e["proposed_by"] == "loader" and e["approved_by_operator"] is False and e["doc_id"] == "uupt-40-2007"
    mk, uu = prop["entries"][14], prop["entries"][15]
    assert mk["status"] == "berlaku_bersyarat" and mk["interpreted_by"] == ["84/PUU-XI/2013"] and mk["effective_from"] == "2014-10-09"
    assert uu["status"] == "berlaku" and "24/2011" in uu["note"] and "Pasal 67" in uu["note"]
    assert "24/2011" in uu["source"] and "Pasal 67" in uu["source"] and uu["effective_from"] == "2011-11-25"
    assert prop["default_rule"] == {"status": CFG["status_default"]["status"], "effective_from": "2007-08-16"}
    for e in prop["entries"]:
        assert e["effective_from"] is None or re.fullmatch(r"\d{4}-\d{2}-\d{2}", e["effective_from"])


def test_positive_two_changed_provisions_clean_text_vs_status_row(doc):
    prop = {e["address"]: e for e in propose_status_rows(doc)["entries"]}
    # contoh 1: Pasal 153A (Perppu), teks bersih ada dan bebas penanda
    assert re.search(r"(?m)^### Pasal 153A$", doc.text)
    assert prop[f"UU 40/2007{SEP}Pasal 153A"]["amended_by"] == ["Perppu 2/2022 jo. UU 6/2023"]
    # contoh 2: Pasal 86 ayat (9), teks bersih tanpa [^1]; baris status berlaku_bersyarat
    m = re.search(r"(?m)^\(9\) RUPS kedua dan ketiga.*$", doc.text[doc.text.index("### Pasal 86\n") :])
    assert m and "[^" not in m.group(0) and m.group(0).endswith("pengadilan negeri.")
    assert prop[f"UU 40/2007{SEP}Pasal 86{SEP}ayat (9)"]["status"] == "berlaku_bersyarat"


def test_cukup_jelas_matching_independent_of_period():
    assert is_cukup_jelas("Cukup jelas.") and is_cukup_jelas("Cukup jelas") and not is_cukup_jelas("Cukup jelas sekali")
    # Penjelasan Pasal 153E ayat (2) di berkas beku tanpa titik
    assert any(is_cukup_jelas(x) and not x.endswith(".") for x in ORIG.split("\n"))


def test_frontmatter_parser_forms():
    got = parse_frontmatter([("a: x y", 2), ("b: >-", 3), ("  satu", 4), ("  dua", 5), ("c:", 6), ("  - i1", 7), ("  - i2", 8), ("d: []", 9)])
    assert got["a"]["value"] == "x y" and got["b"]["value"] == "satu dua" and got["c"]["value"] == ["i1", "i2"] and got["d"]["value"] == []
    assert got["c"]["line"] == 6
    with pytest.raises(CorpusError):
        parse_frontmatter([("a: 1", 2), ("a: 2", 3)])
    with pytest.raises(CorpusError):
        parse_frontmatter([("  bogus", 2)])


# ---------------------------------------------------------------- R1
def test_R01_missing_file(tmp_path):
    with pytest.raises(CorpusError, match="not found") as ei:
        load_corpus(path=tmp_path / "tidak-ada.md")
    assert ei.value.code == "R1" and "tidak-ada.md" in ei.value.message


def test_R01_empty_file(tmp_path):
    with pytest.raises(CorpusError, match="empty") as ei:
        load_corpus(path=write(tmp_path, b""))
    assert ei.value.code == "R1" and "korpus.md" in ei.value.message


def test_R01_not_utf8(tmp_path):
    with pytest.raises(CorpusError, match="not valid UTF-8") as ei:
        load_corpus(path=write(tmp_path, b"---\n\xff\xfe\xfa\n"), verify_hash=False)
    assert ei.value.code == "R1"


# ---------------------------------------------------------------- R2
def test_R02_foreign_hash_names_both_hashes(tmp_path):
    data = bytearray(SRC.read_bytes())
    data[100] = data[100] ^ 0x01 if data[100] < 0x7F else data[100]  # satu byte ASCII diubah
    p = write(tmp_path, bytes(data))
    with pytest.raises(CorpusError) as ei:
        load_corpus(path=p)
    e = ei.value
    assert e.code == "R2" and ENTRY["sha256"] in e.message
    import hashlib

    assert hashlib.sha256(bytes(data)).hexdigest() in e.message and "expected" in e.message


def test_R02_original_passes_with_default_hash_check():
    assert load_corpus().sha256 == ENTRY["sha256"]


# ---------------------------------------------------------------- R3
def test_R03_crlf_copy_rejected_with_first_line(tmp_path):
    p = write(tmp_path, ORIG.replace("\n", "\r\n"))
    with pytest.raises(CorpusError) as ei:
        load_corpus(path=p)  # hash default: pemeriksaan \r datang lebih dulu dan spesifik
    assert ei.value.code == "R3" and "line 1" in ei.value.message and "carriage return" in ei.value.message


def test_R03_single_cr_reports_its_line(tmp_path):
    lines = ORIG.split("\n")
    lines[6] = lines[6] + "\r"
    with pytest.raises(CorpusError) as ei:
        load_corpus(path=write(tmp_path, "\n".join(lines)), verify_hash=False)
    assert ei.value.code == "R3" and "line 7" in ei.value.message


# ---------------------------------------------------------------- R4
def test_R04_bom_rejected(tmp_path):
    with pytest.raises(CorpusError, match="BOM") as ei:
        load_corpus(path=write(tmp_path, b"\xef\xbb\xbf" + SRC.read_bytes()), verify_hash=False)
    assert ei.value.code == "R4"


# ---------------------------------------------------------------- R5
def _insert_after_pasal_ayat(extra: str):
    def fn(lines):
        _, i, e = first_pasal_with_ayat(lines, 1)
        lines.insert(i + 2, extra)  # sesudah baris kosong, sebelum ayat (1)
        lines.insert(i + 3, "")
        # ayat harus tetap berurutan: sisipan bukan ayat dan bukan huruf kecil
    return fn


@pytest.mark.parametrize(
    ("extra", "needle"),
    [
        ("---", "separator"),
        ("Teks dengan **tebal** di tengah.", "bold marker"),
        ("Sisa penanda [^x] di sini.", "footnote marker"),
        ("[^3]: definisi nyasar di tengah badan.", "footnote definition"),
        ("jenis: Undang-Undang", "frontmatter key"),
        ("catatan: sisa", "frontmatter key"),
    ],
)
def test_R05_residual_marker_in_clean_text(tmp_path, extra, needle):
    e = reject(tmp_path, _insert_after_pasal_ayat(extra), "R5", r"clean offset \d+, source line \d+")
    assert needle in e.message


def test_R05_reports_source_line_of_marker(tmp_path):
    marker_line = {}

    def fn(lines):
        _, i, _ = first_pasal_with_ayat(lines, 1)
        lines.insert(i + 2, "Teks **x**")
        lines.insert(i + 3, "")
        marker_line["n"] = i + 3  # 1-based

    e = reject(tmp_path, fn, "R5")
    assert f"source line {marker_line['n']}" in e.message


# ---------------------------------------------------------------- R6
def test_R06_reference_without_definition(tmp_path):
    reject(tmp_path, lambda L: [x for x in L if not x.startswith("[^2]:")], "R6", r"\[\^2\].*no definition")


def test_R06_definition_without_reference(tmp_path):
    def fn(lines):
        i = idx(lines, "(9) " + next(x for x in lines if x.startswith("(9) RUPS kedua dan ketiga"))[4:])
        lines[i] = lines[i].replace("[^1]", "")

    reject(tmp_path, fn, "R6", r"definition \[\^1\].*no reference")


def test_R06_count_not_two(tmp_path):
    def fn(lines):
        lines.append("")
        lines.append("[^3]: Definisi ketiga.")
        _, i, _ = first_pasal_with_ayat(lines, 1)
        j = next(k for k in range(i, len(lines)) if lines[k].startswith("(1) "))
        lines[j] += "[^3]"

    reject(tmp_path, fn, "R6", r"expected 2 footnotes, found 3")


def test_R06_missing_separator_or_junk_after_it(tmp_path):
    def fn(lines):
        lines.append("")
        lines.append("sisa teks sesudah definisi")

    reject(tmp_path, fn, "R6", r"unexpected content after the final")


# ---------------------------------------------------------------- R7
def test_R07_unknown_label(tmp_path):
    def fn(lines):
        i = idx(lines, "**PUTUSAN MAHKAMAH KONSTITUSI NOMOR 84/PUU-XI/2013**")
        lines[i] = "**PUTUSAN MAHKAMAH KONSTITUSI NOMOR 99/PUU-XX/2020**"

    reject(tmp_path, fn, "R7", r"unknown annotation label")


def test_R07_label_not_first_nonblank_line_below_pasal(tmp_path):
    def fn(lines):
        i = idx(lines, "**UNDANG-UNDANG NOMOR 24 TAHUN 2011**")
        lines[i - 1 : i + 1] = ["", "Satu baris sisipan sebelum label.", "", lines[i]]

    reject(tmp_path, fn, "R7", r"unknown annotation label|not the first non-empty line")


def test_R07_known_label_elsewhere_in_body(tmp_path):
    def fn(lines):
        _, i, e = first_pasal_with_ayat(lines, 2)
        k = _ayat_line(lines, i, e, 1)
        lines[k + 1 : k + 1] = ["", "**UNDANG-UNDANG NOMOR 24 TAHUN 2011**"]

    reject(tmp_path, fn, "R7", r"not the first non-empty line")


def test_R07_label_missing(tmp_path):
    def fn(lines):
        i = idx(lines, "**UNDANG-UNDANG NOMOR 24 TAHUN 2011**")
        del lines[i]

    e = reject(tmp_path, fn, "R7")
    assert "expected exactly one annotation label" in e.message


# ---------------------------------------------------------------- R8
def _ayat_line(lines, pasal_start, pasal_end, n):
    return next(k for k in range(pasal_start, pasal_end) if lines[k].startswith(f"({n}) "))


def test_R08_ayat_jump(tmp_path):
    info = {}

    def fn(lines):
        p, i, e = first_pasal_with_ayat(lines, 3)
        k = _ayat_line(lines, i, e, 2)
        lines[k] = lines[k].replace("(2) ", "(4) ", 1)
        info.update(p=p, n=k + 1)

    err = reject(tmp_path, fn, "R8", r"expected \(2\), found \(4\)")
    assert f"Pasal {info['p']}" in err.message and f"source line {info['n']}" in err.message


def test_R08_ayat_repeated(tmp_path):
    def fn(lines):
        _, i, e = first_pasal_with_ayat(lines, 2)
        k = _ayat_line(lines, i, e, 2)
        lines[k] = lines[k].replace("(2) ", "(1) ", 1)

    reject(tmp_path, fn, "R8", r"expected \(2\), found \(1\)")


def test_R08_does_not_start_at_one(tmp_path):
    def fn(lines):
        _, i, e = first_pasal_with_ayat(lines, 1)
        k = _ayat_line(lines, i, e, 1)
        lines[k] = lines[k].replace("(1) ", "(2) ", 1)

    reject(tmp_path, fn, "R8", r"expected \(1\), found \(2\)")


# ---------------------------------------------------------------- R9
def _first_closing_sentence(lines):
    """Indeks baris kalimat penutup rincian (huruf kecil) pertama di batang tubuh berkas beku (Pasal 102 ayat (1))."""
    in_body = False
    for k, t in enumerate(lines):
        if t.startswith("#"):
            in_body = t.startswith("### Pasal")
            continue
        if in_body and t and t[0].islower() and not re.match(r"^([a-z]|\d+)\.\s", t):
            return k
    raise AssertionError("no closing sentence in fixture")


def test_R09_real_file_has_a_valid_closing_sentence():
    lines = ORIG.split("\n")
    k = _first_closing_sentence(lines)
    prev = next(lines[j] for j in range(k - 1, -1, -1) if lines[j])
    assert re.match(r"^([a-z]|\d+)\.\s", prev) and prev.endswith(";")


@pytest.mark.parametrize("ending", [";", "; atau", "; dan"])
def test_R09_closing_sentence_accepted_after_valid_butir_endings(tmp_path, ending):
    def fn(lines):
        k = _first_closing_sentence(lines)
        j = next(j for j in range(k - 1, -1, -1) if lines[j])
        lines[j] = lines[j].rstrip(";").rstrip() + ending if not lines[j].endswith(ending) else lines[j]

    assert load_mut(tmp_path, fn).char_count > 0


@pytest.mark.parametrize("bad_ending", [".", ",", ":", ""])
def test_R09_closing_sentence_rejected_after_butir_without_semicolon(tmp_path, bad_ending):
    def fn(lines):
        k = _first_closing_sentence(lines)
        j = next(j for j in range(k - 1, -1, -1) if lines[j])
        lines[j] = lines[j].rstrip(";") + bad_ending

    reject(tmp_path, fn, "R9", r"lowercase")


def test_R09_lowercase_line_after_plain_paragraph(tmp_path):
    def fn(lines):
        _, i, e = first_pasal_with_ayat(lines, 1)
        k = _ayat_line(lines, i, e, 1)
        lines.insert(k + 1, "")
        lines.insert(k + 2, "sambungan hard-wrap yang bukan kalimat penutup.")

    reject(tmp_path, fn, "R9", r"source line \d+")


def test_R09_lowercase_line_directly_below_heading(tmp_path):
    def fn(lines):
        _, i, _ = first_pasal_with_ayat(lines, 1)
        lines.insert(i + 1, "")
        lines.insert(i + 2, "huruf kecil tepat di bawah heading")

    reject(tmp_path, fn, "R9")


# ---------------------------------------------------------------- R10
def test_R10_pasal_count_not_171(tmp_path):
    def fn(lines):
        i = idx(lines, "### Pasal 5")
        j = idx(lines, "#### Penjelasan Pasal 5")
        for k in sorted((i, j), reverse=True):
            lines[k] = "Pasal lima yang dulu heading."

    reject(tmp_path, fn, "R10", r"expected 171 '### Pasal' headings, found 170")


def test_R10_duplicate_pasal_number(tmp_path):
    def fn(lines):
        lines[idx(lines, "### Pasal 6")] = "### Pasal 5"

    reject(tmp_path, fn, "R10", r"duplicate '### Pasal' numbers: \['5'\]")


def test_R10_duplicate_penjelasan_number(tmp_path):
    def fn(lines):
        lines[idx(lines, "#### Penjelasan Pasal 6")] = "#### Penjelasan Pasal 5"

    reject(tmp_path, fn, "R10", r"duplicate '#### Penjelasan Pasal' numbers")


def test_R10_penjelasan_order_differs_from_pasal_order(tmp_path):
    def fn(lines):
        a, b = idx(lines, "#### Penjelasan Pasal 10"), idx(lines, "#### Penjelasan Pasal 11")
        lines[a], lines[b] = lines[b], lines[a]

    reject(tmp_path, fn, "R10", r"order differs")


def test_R10_penjelasan_count_not_171(tmp_path):
    def fn(lines):
        lines[idx(lines, "#### Penjelasan Pasal 7")] = "Penjelasan tujuh tanpa heading."

    reject(tmp_path, fn, "R10", r"expected 171 '#### Penjelasan Pasal' headings, found 170")


# ---------------------------------------------------------------- R11
@pytest.mark.parametrize(
    "bad",
    ["##### Sub-sub heading", "# Judul tingkat satu", "## LAMPIRAN", "### Pasal 5 bis", "#### Penjelasan Umum", "### BAB XV — LIAR", "####Paragraf 9"],
)
def test_R11_illegal_heading(tmp_path, bad):
    def fn(lines):
        _, i, e = first_pasal_with_ayat(lines, 1)
        lines.insert(i + 1, "")
        lines.insert(i + 2, bad)

    err = reject(tmp_path, fn, "R11", r"heading")
    assert "source line" in err.message or "BAB" in err.message


def test_R11_missing_bab(tmp_path):
    def fn(lines):
        i = next(k for k, t in enumerate(lines) if t.startswith("## BAB V "))
        lines[i] = "Judul BAB V dihapus."

    reject(tmp_path, fn, "R11", r"BAB headings must be")


def test_R11_heading_order(tmp_path):
    def fn(lines):
        lines.insert(idx(lines, "## BAB I — KETENTUAN UMUM") if False else next(k for k, t in enumerate(lines) if t.startswith("## BAB I ")), "## PENGESAHAN DAN PENGUNDANGAN")

    reject(tmp_path, fn, "R11")


# ---------------------------------------------------------------- R12
def test_R12_extra_frontmatter_key(tmp_path):
    def fn(lines):
        lines.insert(2, "kunci_baru: nilai")

    reject(tmp_path, fn, "R12", r"unexpected=\['kunci_baru'\]")


def test_R12_missing_frontmatter_key(tmp_path):
    def fn(lines):
        i = next(k for k, t in enumerate(lines) if t.startswith("tahun:"))
        del lines[i]

    reject(tmp_path, fn, "R12", r"missing=\['tahun'\]")


@pytest.mark.parametrize("key", ["catatan_koreksi", "perubahan_pasca_pakai"])
def test_R12_nonempty_must_be_empty_keys(tmp_path, key):
    def fn(lines):
        i = idx(lines, f"{key}: []")
        lines[i : i + 1] = [f"{key}:", "  - ada isi"]

    reject(tmp_path, fn, "R12", rf"{key}.*must be empty")


def test_R12_perppu_string_does_not_parse(tmp_path):
    def fn(lines):
        i = next(k for k, t in enumerate(lines) if t.startswith("  - Perppu No."))
        lines[i] = lines[i].replace("(berlaku 30 Desember 2022)", "(berlaku kemarin)")

    reject(tmp_path, fn, "R12", r"Perppu source string")


def test_R12_named_pasal_missing_from_file(tmp_path):
    def fn(lines):
        i = next(k for k, t in enumerate(lines) if t.startswith("  - Perppu No."))
        lines[i] = lines[i].replace("Pasal 153J)", "Pasal 153K)")

    reject(tmp_path, fn, "R12", r"names Pasal 153K")


def test_R12_changed_pasal_missing_from_file(tmp_path):
    def fn(lines):
        i = next(k for k, t in enumerate(lines) if t.startswith("  - Perppu No."))
        lines[i] = lines[i].replace("Pasal 7;", "Pasal 7777;")

    reject(tmp_path, fn, "R12", r"names Pasal 7777")


def test_R12_mk_entry_without_see_footnote_marker(tmp_path):
    def fn(lines):
        i = next(k for k, t in enumerate(lines) if t.startswith("  - Putusan Mahkamah"))
        lines[i] = lines[i].replace(" (lihat footnote)", "")

    reject(tmp_path, fn, "R12", r"MK source string")


def test_R12_disclaimer_altered(tmp_path):
    def fn(lines):
        i = next(k for k, t in enumerate(lines) if t.startswith("Bukan naskah LN/BN."))
        lines[i] = "Naskah resmi."

    reject(tmp_path, fn, "R12", r"disclaimer")


def test_R12_footnote_text_does_not_match_label(tmp_path):
    def fn(lines):
        i = next(k for k, t in enumerate(lines) if t.startswith("[^1]:"))
        lines[i] = "[^1]: Catatan tanpa nomor putusan."

    reject(tmp_path, fn, "R12", r"does not mention")


# ---------------------------------------------------------------- R13
def test_R13_determinism_two_loads(doc):
    again = load_corpus()
    assert again.clean_sha256 == doc.clean_sha256 and again.text == doc.text
    assert again.sections == doc.sections and again.annotations == doc.annotations


def test_R13_determinism_from_copy(tmp_path, doc):
    p = write(tmp_path, SRC.read_bytes())
    a = load_corpus(path=p)
    b = load_corpus(path=p)
    assert a.clean_sha256 == b.clean_sha256 == doc.clean_sha256


def test_R13_clean_hash_matches_text(doc):
    import hashlib

    assert doc.clean_sha256 == hashlib.sha256(doc.text.encode("utf-8")).hexdigest()
