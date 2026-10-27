"""Uji chunker struktur dan ukuran tetap (M1.1, Tier 2): bentuk Chunk, round-trip offset, determinisme, fallback.

GOLDEN SAMPLE: disetujui operator 2026-10-27, I-36 (lihat `test_chunking_address.py`).
Tokenizer H-014 asli dipakai untuk korpus nyata (cache HF lokal, G-32); tokenizer mainan `toy-ws` untuk hitung tangan.
"""

from __future__ import annotations

import dataclasses
import math
import re

import pytest

from backend import config
from backend.chunking import (
    NO_MARKER_WARNING, ChunkOffsetError, build_address_map, chunk_document, chunk_fixed, chunk_structure, make_chunk_id,
    make_chunker_key, verify_chunks,
)
from backend.tokenizer import get_tokenizer

from ._chunk_util import PREFIX, ToyWs, make_doc, real_doc, u_doc

SEP = " › "
RCFG = config.load("retrieval")
SCOPE = set(RCFG["scope_sections"])
FX = config.load("grid")["fixed_size"]
CONTRACT_FIELDS = {"chunk_id", "doc_id", "chunker_key", "start", "end", "clean_sha256", "section", "address", "address_levels", "tokens_local", "warnings"}


@pytest.fixture(scope="module")
def doc():
    return real_doc()


@pytest.fixture(scope="module")
def tok():
    t = get_tokenizer()
    assert t.info.name == config.load("tokenizer")["primary"], "tokenizer H-014 not in the local HF cache (G-32); do not run on the o200k fallback"
    return t


@pytest.fixture(scope="module")
def structure(doc, tok):
    return chunk_structure(doc, tokenizer=tok)


@pytest.fixture(scope="module")
def fixed(doc, tok):
    return chunk_fixed(doc, tokenizer=tok)


# ------------------------------------------------------------------ bentuk Chunk (DATA-CONTRACTS §3)
def test_scope_comes_from_config_not_code():
    assert RCFG["scope_sections"] == ["batang_tubuh", "penjelasan_pasal", "penjelasan_umum"] and RCFG["version"] == 1
    assert RCFG["chunking"]["structure_version"] == 2 and RCFG["chunking"]["fixed_size_version"] == 2  # H-064, H-062


def test_structure_chunk_shape_and_counts(doc, structure):
    assert {f.name for f in dataclasses.fields(structure[0])} == CONTRACT_FIELDS
    sections = {}
    for c in structure:
        sections[c.section] = sections.get(c.section, 0) + 1
    assert sections == {"batang_tubuh": 569, "penjelasan_pasal": 500, "penjelasan_umum": 1}  # regresi atas korpus beku
    for c in structure:
        assert c.clean_sha256 == doc.clean_sha256 and c.doc_id == doc.doc_id
        assert c.warnings == [] and c.tokens_local > 0
        assert c.address_levels[0] == {"level": "peraturan", "label": PREFIX}
        assert c.address_levels[1] == {"level": "section", "label": c.section}
        assert c.chunk_id == make_chunk_id(doc.doc_id, c.start, c.end, c.chunker_key)
    assert len({c.chunk_id for c in structure}) == len(structure)
    assert len({c.address for c in structure}) == len(structure)


def test_structure_chunk_equals_unit_text_for_pasal_86_ayat_9(doc, structure):
    body = next(c for c in structure if c.address == "UU 40/2007 › Pasal 86 › ayat (9)")
    penj = next(c for c in structure if c.address == "UU 40/2007 › Penjelasan › Pasal 86 › Ayat (9)")
    assert doc.text[body.start:body.end].startswith("(9) RUPS kedua dan ketiga")
    assert doc.text[penj.start:penj.end] == "Ayat (9)\n\nCukup jelas."
    assert body.section == "batang_tubuh" and penj.section == "penjelasan_pasal"
    assert [lv["label"] for lv in body.address_levels] == [PREFIX, "batang_tubuh", "Pasal 86", "ayat (9)"]
    assert [lv["label"] for lv in penj.address_levels] == [PREFIX, "penjelasan_pasal", "Pasal 86", "Ayat (9)"]


def test_chunker_keys_differ_and_depend_on_parameters(doc, structure, fixed, tok):
    assert structure[0].chunker_key != fixed[0].chunker_key
    other = chunk_fixed(doc, size=256, overlap=32, tokenizer=tok)
    assert other[0].chunker_key != fixed[0].chunker_key
    assert make_chunker_key("fixed_size", {"a": 1}) == make_chunker_key("fixed_size", {"a": 1})
    assert make_chunk_id("d", 0, 1, "k") != make_chunk_id("d", 0, 2, "k")


# ------------------------------------------------------------------ determinisme
def test_determinism_chunk_ids_identical_across_runs(doc, tok, structure, fixed):
    s2, f2 = chunk_structure(doc, tokenizer=tok), chunk_fixed(doc, tokenizer=tok)
    assert [c.chunk_id for c in s2] == [c.chunk_id for c in structure]
    assert [c.chunk_id for c in f2] == [c.chunk_id for c in fixed]
    assert [c.to_dict() for c in f2] == [c.to_dict() for c in fixed]


# ------------------------------------------------------------------ round-trip offset
def _section_of(doc, c):
    # H-062: fixed_size melintasi section; `Chunk.section` = section di posisi awal, jadi hanya awal yang dicocokkan
    return next(s for s in doc.sections if s["section"] == c.section and s["start"] <= c.start < s["end"])


def _scope_runs(doc):
    """Deret section dalam cakupan yang bersambung (dihitung terpisah dari chunker)."""
    runs: list[list[int]] = []
    for s in sorted(doc.sections, key=lambda x: x["start"]):
        if s["section"] in SCOPE:
            if runs and runs[-1][1] == s["start"]:
                runs[-1][1] = s["end"]
            else:
                runs.append([s["start"], s["end"]])
    return runs


@pytest.mark.parametrize("which", ["structure", "fixed"])
def test_round_trip_offsets_every_chunk(doc, request, which):
    chunks = request.getfixturevalue(which)
    verify_chunks(doc, chunks)
    for c in chunks:
        t = doc.text[c.start:c.end]
        assert t and t == t.strip()
        assert _section_of(doc, c)["section"] in SCOPE
        assert t.encode("utf-8").decode("utf-8") == t
    # identitas: setiap karakter non-spasi di section cakupan tertutup oleh minimal satu potongan, kecuali baris heading
    covered = bytearray(len(doc.text))
    for c in chunks:
        covered[c.start:c.end] = b"\x01" * (c.end - c.start)
    for s in doc.sections:
        if s["section"] not in SCOPE:
            continue
        pos = s["start"]
        for line in doc.text[s["start"]:s["end"]].split("\n"):
            if line.strip() and not any(covered[pos:pos + len(line)]):
                assert line.startswith("#"), f"{which}: uncovered text at {pos}: {line[:60]!r}"
            pos += len(line) + 1


def test_verify_rejects_altered_offsets(doc, structure):
    c = structure[10]
    with pytest.raises(ChunkOffsetError):
        verify_chunks(doc, [dataclasses.replace(c, start=c.start + 1)])  # id tidak lagi cocok
    with pytest.raises(ChunkOffsetError):
        verify_chunks(doc, [dataclasses.replace(c, clean_sha256="0" * 64)])
    bad = dataclasses.replace(c, end=len(doc.text) + 5, chunk_id=make_chunk_id(c.doc_id, c.start, len(doc.text) + 5, c.chunker_key))
    with pytest.raises(ChunkOffsetError):
        verify_chunks(doc, [bad])
    other_sec = next(s for s in doc.sections if s["section"] == "pembukaan")
    cross = dataclasses.replace(c, start=other_sec["start"] + 1, end=other_sec["start"] + 20,
                                chunk_id=make_chunk_id(c.doc_id, other_sec["start"] + 1, other_sec["start"] + 20, c.chunker_key))
    with pytest.raises(ChunkOffsetError):
        verify_chunks(doc, [cross])


# ------------------------------------------------------------------ ukuran tetap
def test_fixed_uses_grid_config_and_expected_window_count(doc, tok, fixed):
    # H-062: jumlah jendela atas deret bersambung, bukan per section (sebelumnya 348 potongan per-section)
    size, ov = FX["chunk_size_tokens"], FX["overlap_tokens"]
    step = size - ov
    expect = 0
    for s, e in _scope_runs(doc):
        n = len(tok.offsets(doc.text[s:e]))
        expect += 0 if n == 0 else (1 if n <= size else 1 + math.ceil((n - size) / step))
    assert len(fixed) == expect  # dihitung dari rumus terpisah, bukan dari loop chunker
    assert {c.section for c in fixed} <= SCOPE
    assert max(c.tokens_local for c in fixed) <= size + 2  # hitung ulang token teks terpangkas boleh bergeser tipis di tepi


def test_fixed_boundaries_are_token_boundaries_and_overlap_is_exact(doc, tok, fixed):
    size, ov = FX["chunk_size_tokens"], FX["overlap_tokens"]
    by_run: dict[tuple[int, int], list] = {}
    for c in fixed:
        r = next((s, e) for s, e in _scope_runs(doc) if s <= c.start and c.end <= e)
        by_run.setdefault(r, []).append(c)
    multi = 0
    for (s, e), cs in by_run.items():
        offs = tok.offsets(doc.text[s:e])
        starts = {s + a for a, _ in offs}
        ends = {s + b for _, b in offs}
        for c in cs:
            # awal/akhir potongan berada di batas token, lalu spasi tepi dipangkas
            a = max(x for x in starts if x <= c.start)
            b = min(x for x in ends if x >= c.end)
            assert doc.text[a:c.start].strip() == "" and doc.text[c.end:b].strip() == ""
        for k in range(1, len(cs)):
            multi += 1
            ia = max(i for i, (a, _) in enumerate(offs) if s + a <= cs[k - 1].start)
            ib = max(i for i, (a, _) in enumerate(offs) if s + a <= cs[k].start)
            assert 0 < ib - ia <= size - ov + 2, "langkah jendela = size - overlap (bergeser tipis hanya karena pangkas spasi)"
    assert multi >= 1, "korpus beku punya lebih dari satu jendela"


def test_fixed_toy_hand_computed_windows_cross_sections_H062():
    # H-062 (sebelumnya: tidak melintasi section). Section 1: t0..t9 [0,31); section 2: u0..u2 [31,len).
    # 13 token berurutan; size 4 overlap 1 -> langkah 3; jendela di indeks token 0-3, 3-6, 6-9, 9-12.
    text = "t0 t1 t2 t3 t4 t5 t6 t7 t8 t9\n\nu0 u1 u2\n"
    d = make_doc(text, [("batang_tubuh", 0, 31), ("penjelasan_pasal", 31, len(text))])
    cs = chunk_fixed(d, size=4, overlap=1, tokenizer=ToyWs(), retrieval_cfg=RCFG)
    got = [(c.section, d.text[c.start:c.end]) for c in cs]
    assert got == [
        ("batang_tubuh", "t0 t1 t2 t3"), ("batang_tubuh", "t3 t4 t5 t6"), ("batang_tubuh", "t6 t7 t8 t9"),
        ("batang_tubuh", "t9\n\nu0 u1 u2"),  # mulai di section 1, berakhir di section 2; section = posisi awal
    ]
    assert [(c.start, c.end) for c in cs] == [(0, 11), (9, 20), (18, 29), (27, 39)]
    assert [c.tokens_local for c in cs] == [4, 4, 4, 4]
    assert cs[3].address == f"{PREFIX}{SEP}Batang Tubuh – {PREFIX}{SEP}Penjelasan"  # alamat awal – alamat akhir (§3)
    verify_chunks(d, cs, SCOPE)


def test_fixed_h062_crosses_pasal_and_section_on_u_document():
    d = u_doc()
    cs = chunk_fixed(d, size=8, overlap=2, tokenizer=ToyWs(), retrieval_cfg=RCFG)  # 40 token, langkah 6: mulai token 0,6,12,18,24,30,36
    a1, a2, a4 = (f"{PREFIX}{SEP}{x}" for x in (f"Pasal 1{SEP}ayat (1)", f"Pasal 1{SEP}ayat (2)", "Pasal 2"))
    p11, p13 = (f"{PREFIX}{SEP}Penjelasan{SEP}Pasal 1{SEP}Ayat ({n})" for n in (1, 3))
    p2 = f"{PREFIX}{SEP}Penjelasan{SEP}Pasal 2"
    assert [(c.start, c.end, c.section, c.address) for c in cs] == [
        (0, 32, "batang_tubuh", f"{a1} – {a2}"),
        (25, 61, "batang_tubuh", f"{a2} – {a4}"),     # melintasi batas Pasal 1 -> Pasal 2 (ayat (3) di antaranya: ujung saja)
        (52, 93, "batang_tubuh", f"{a4}"),            # mulai di Pasal 2 (batang), berakhir di 'Penjelasan' (section berikut)
        (78, 123, "penjelasan_pasal", p11),
        (111, 150, "penjelasan_pasal", f"{p11} – {p13}"),
        (142, 187, "penjelasan_pasal", f"{p13} – {p2}"),
        (180, 200, "penjelasan_pasal", p2),
    ]
    assert d.text[52:93].endswith("#### Penjelasan") and 52 < 78 < 93, "potongan ke-3 melintasi batas section batang_tubuh -> penjelasan_pasal"
    verify_chunks(d, cs, SCOPE)


def test_fixed_h062_does_not_cross_a_gap_of_out_of_scope_section():
    text = "a1 a2 a3 a4\n\nPEMBUKAAN LUAR CAKUPAN\n\nb1 b2 b3\n"
    i1, i2 = text.index("PEMBUKAAN"), text.index("b1")
    d = make_doc(text, [("batang_tubuh", 0, i1), ("pembukaan", i1, i2), ("penjelasan_pasal", i2, len(text))])
    cs = chunk_fixed(d, size=3, overlap=1, tokenizer=ToyWs(), retrieval_cfg=RCFG)
    # deret 1: a1..a4 -> [a1 a2 a3], [a3 a4]; deret baru setelah celah: [b1 b2 b3]
    assert [d.text[c.start:c.end] for c in cs] == ["a1 a2 a3", "a3 a4", "b1 b2 b3"]
    assert [c.section for c in cs] == ["batang_tubuh", "batang_tubuh", "penjelasan_pasal"]
    verify_chunks(d, cs, SCOPE)
    end = i2 + 2
    spanning = dataclasses.replace(cs[1], end=end, chunk_id=make_chunk_id(d.doc_id, cs[1].start, end, cs[1].chunker_key))
    with pytest.raises(ChunkOffsetError):
        verify_chunks(d, [spanning], SCOPE)  # melintasi section di luar cakupan


def test_fixed_h062_real_corpus_crossing_and_counts(doc, fixed):
    assert len(fixed) == 103  # regresi korpus beku, tokenizer H-014, 512/64 (sebelumnya 348 per section)
    in_scope = [s for s in doc.sections if s["section"] in SCOPE]
    assert _scope_runs(doc) == [[min(s["start"] for s in in_scope), max(s["end"] for s in in_scope)]], \
        "korpus nyata: tidak ada celah section di luar cakupan di antara section dalam cakupan"
    crossing = [c for c in fixed if not any(s["start"] <= c.start and c.end <= s["end"] for s in doc.sections)]
    assert crossing, "minimal satu potongan melintasi batas section"
    differing = [c for c in crossing if next(s["section"] for s in doc.sections if s["start"] <= c.end - 1 < s["end"]) != c.section]
    assert differing, "minimal satu potongan: section posisi awal berbeda dari section posisi akhir"
    assert all(" – " in c.address for c in crossing)


def test_fixed_rejects_bad_parameters():
    with pytest.raises(ValueError):
        chunk_fixed(u_doc(), size=4, overlap=4, tokenizer=ToyWs(), retrieval_cfg=RCFG)
    with pytest.raises(ValueError):
        chunk_fixed(u_doc(), size=0, overlap=0, tokenizer=ToyWs(), retrieval_cfg=RCFG)


def test_fixed_address_uses_same_address_map_and_range_format():
    d = u_doc()
    m = build_address_map(d.text, d.sections, PREFIX, SCOPE)
    cs = chunk_fixed(d, size=5, overlap=1, tokenizer=ToyWs(), retrieval_cfg=RCFG, amap=m)
    spanning = 0
    for c in cs:
        ov = m.overlapping(c.start, c.end, c.section)
        assert ov, c
        if len(ov) == 1:
            assert c.address == ov[0].address
        else:
            spanning += 1
            assert c.address == f"{ov[0].address} – {ov[-1].address}"
    assert spanning >= 1
    # potongan di tengah satu rincian memakai alamat rincian
    t = "### Pasal 5\n(1) Direksi wajib:\na. mengalihkan kekayaan;\nb. menjaminkan utang;\nyang penting sekali.\n"
    d2 = make_doc(t, [("batang_tubuh", 0, len(t))])
    cs2 = chunk_fixed(d2, size=3, overlap=0, tokenizer=ToyWs(), retrieval_cfg=RCFG)
    assert any(c.address.endswith("ayat (1)" + SEP + "huruf a") for c in cs2)


def test_fixed_real_corpus_address_ranges_use_en_dash(fixed):
    spans = [c for c in fixed if " – " in c.address]
    assert spans, "Pasal panjang harus menghasilkan potongan lintas unit"
    assert all(c.address.count(" – ") == 1 for c in spans)


# ------------------------------------------------------------------ fallback tanpa penanda
def test_fallback_without_structural_markers_one_chunk_per_section_with_warning():
    text = "Pembukaan.\n\nIsi batang tubuh tanpa heading apa pun.\nBaris kedua.\n\nPenjelasan tanpa heading.\n\nUmum tanpa heading.\n"
    b0, p0, u0 = text.index("Isi batang"), text.index("Penjelasan tanpa"), text.index("Umum tanpa")
    d = make_doc(text, [("pembukaan", 0, b0), ("batang_tubuh", b0, p0), ("penjelasan_pasal", p0, u0), ("penjelasan_umum", u0, len(text))])
    cs = chunk_structure(d, tokenizer=ToyWs(), retrieval_cfg=RCFG)
    assert [c.section for c in cs] == ["batang_tubuh", "penjelasan_pasal", "penjelasan_umum"]
    assert all(c.warnings == [NO_MARKER_WARNING] for c in cs)
    assert d.text[cs[0].start:cs[0].end] == "Isi batang tubuh tanpa heading apa pun.\nBaris kedua."
    assert cs[0].address == f"{PREFIX}{SEP}Batang Tubuh"
    verify_chunks(d, cs)
    via_api = chunk_document(d, {"chunker": "structure_handwritten"}, tokenizer=ToyWs(), retrieval_cfg=RCFG)
    assert [c.chunk_id for c in via_api] == [c.chunk_id for c in cs]


def test_fallback_does_not_affect_marked_sections_in_real_corpus(structure, fixed):
    assert not any(c.warnings for c in structure)
    assert not any(c.warnings for c in fixed)


def test_scope_filter_drops_sections_without_shifting_offsets(doc, tok, structure):
    cfg = {**RCFG, "scope_sections": ["batang_tubuh"]}
    only = chunk_structure(doc, tokenizer=tok, retrieval_cfg=cfg)
    assert {c.section for c in only} == {"batang_tubuh"}
    by_addr = {c.address: (c.start, c.end) for c in structure}
    assert all(by_addr[c.address] == (c.start, c.end) for c in only)
    assert only[0].chunker_key != structure[0].chunker_key


def test_g13_roman_pasal_text_does_not_crash_any_chunker():
    text = "## BAB I — UBAH\n\n### Pasal I\n\nUndang-Undang ini diubah sebagai berikut:\n\n1. Pasal 1 diubah.\n"
    d = make_doc(text, [("batang_tubuh", 0, len(text))])
    s = chunk_structure(d, tokenizer=ToyWs(), retrieval_cfg=RCFG)
    f = chunk_fixed(d, size=4, overlap=1, tokenizer=ToyWs(), retrieval_cfg=RCFG)
    assert [c.warnings for c in s] == [[NO_MARKER_WARNING]]  # Pasal I tidak dikenal: jatuh ke fallback per section
    assert f and re.search(r"Pasal I", d.text[f[0].start:f[-1].end])


# ---- INT-a perbaikan kecil dari review (G3 SHOULD-1, NIT-1) ----

def _scope_cfg(*sections):
    cfg = dict(config.load("retrieval"))
    cfg["scope_sections"] = list(sections)
    return cfg


def test_fixed_key_changes_when_scope_sections_change():
    from backend.chunking.fixed import fixed_key
    cfg = config.load("retrieval")
    k_all = fixed_key(cfg, 512, 64, ToyWs())
    k_one = fixed_key(_scope_cfg("batang_tubuh"), 512, 64, ToyWs())
    assert k_all != k_one
    assert fixed_key(cfg, 512, 64, ToyWs()) == k_all  # deterministik


def test_structure_key_changes_when_scope_sections_change():
    from backend.chunking.structure import structure_key
    assert structure_key(config.load("retrieval"), ToyWs()) != structure_key(_scope_cfg("batang_tubuh"), ToyWs())


class _OtherTok(ToyWs):
    info = type("I", (), {"name": "toy-ws", "version": "2"})()


@pytest.mark.parametrize("name", ["structure_handwritten", "fixed_size"])
def test_tokenizer_name_and_version_enter_chunker_key_and_chunk_id(name):
    """Ganti tokenizer (versi) = chunker_key dan chunk_id berubah, walau offset potongan sama."""
    doc = u_doc()
    setting = {"chunker": name, "chunk_size_tokens": 4, "overlap_tokens": 1}
    a = chunk_document(doc, setting, tokenizer=ToyWs())
    b = chunk_document(doc, setting, tokenizer=_OtherTok())
    assert [(c.start, c.end) for c in a] == [(c.start, c.end) for c in b]
    assert {c.chunker_key for c in a}.isdisjoint({c.chunker_key for c in b})
    assert {c.chunk_id for c in a}.isdisjoint({c.chunk_id for c in b})


# ------------------------------------------------------------------ H-064: heading Pasal di potongan unit pertama
def test_structure_h064_synthetic_u_document_chunk_widens_but_unit_map_does_not():
    d = u_doc()
    cs = chunk_structure(d, tokenizer=ToyWs(), retrieval_cfg=RCFG)
    assert [(c.start, c.end) for c in cs] == [(0, 24), (25, 37), (38, 50), (52, 76), (78, 123), (124, 141), (142, 163), (164, 200)]
    assert d.text[cs[0].start:cs[0].end] == "### Pasal 1\n(1) Aaa bbb."   # ayat (1) Pasal 1 mencakup heading
    assert d.text[cs[4].start:cs[4].end].startswith("#### Penjelasan Pasal 1\nAyat (1)")  # Penjelasan ber-"Ayat (n)": sama
    m = build_address_map(d.text, d.sections, PREFIX, SCOPE)
    units = {u.address: (u.start, u.end) for u in m.units}
    assert units[f"{PREFIX}{SEP}Pasal 1{SEP}ayat (1)"] == (12, 24)  # unit A4 (peta alamat) tetap: tanpa heading
    assert units[f"{PREFIX}{SEP}Penjelasan{SEP}Pasal 1{SEP}Ayat (1)"] == (102, 123)
    assert all(c.address in units and units[c.address][1] == c.end for c in cs)  # alamat dan akhir = unit
    verify_chunks(d, cs, SCOPE)


def test_structure_h064_pasal_with_text_between_heading_and_ayat_1():
    t = "### Pasal 5\nPengantar sebelum ayat.\n(1) Isi satu.\n(2) Isi dua.\n"
    d = make_doc(t, [("batang_tubuh", 0, len(t))])
    cs = chunk_structure(d, tokenizer=ToyWs(), retrieval_cfg=RCFG)
    assert [d.text[c.start:c.end] for c in cs] == ["### Pasal 5\nPengantar sebelum ayat.\n(1) Isi satu.", "(2) Isi dua."]
    assert next(u for u in build_address_map(t, d.sections, PREFIX, SCOPE).units if u.ayat == 1).start == t.index("(1)")


def test_structure_h064_real_corpus_first_chunk_of_pasal_has_heading(doc, structure):
    by_addr = {c.address: c for c in structure}
    p86 = by_addr[f"{PREFIX}{SEP}Pasal 86{SEP}ayat (1)"]
    assert doc.text[p86.start:p86.end].startswith("### Pasal 86\n")
    p1 = by_addr[f"{PREFIX}{SEP}Pasal 1"]  # Pasal tanpa ayat: unit tunggal sudah termasuk heading
    assert doc.text[p1.start:p1.end].startswith("### Pasal 1\n")
    assert doc.text[by_addr[f"{PREFIX}{SEP}Pasal 86{SEP}ayat (2)"].start:].startswith("(2) ")  # ayat berikut tidak melebar
    amap = build_address_map(doc.text, doc.sections, PREFIX, SCOPE)
    u86 = next(u for u in amap.units if u.address == f"{PREFIX}{SEP}Pasal 86{SEP}ayat (1)")
    assert doc.text[u86.start:].startswith("(1) ") and (u86.start, u86.end) != (p86.start, p86.end) and u86.end == p86.end
    # tiap Pasal batang tubuh: chunk pertama mulai di heading '### Pasal n'
    first_of: dict[str, object] = {}
    for c in structure:
        if c.section == "batang_tubuh":
            first_of.setdefault(c.address_levels[2]["label"], c)
    assert first_of and all(doc.text[c.start:].startswith(f"### {lab}\n") for lab, c in first_of.items())
    # Penjelasan ber-"Ayat (n)" tanpa isi pembuka: chunk 'Ayat (1)' mulai di '#### Penjelasan Pasal n'
    p86p = by_addr[f"{PREFIX}{SEP}Penjelasan{SEP}Pasal 86{SEP}Ayat (1)"]
    assert doc.text[p86p.start:].startswith("#### Penjelasan Pasal 86\n")


def test_structure_h064_no_overlap_round_trip_and_uncovered_chars(doc, structure):
    ordered = sorted(structure, key=lambda c: (c.start, c.end))
    assert all(a.end <= b.start for a, b in zip(ordered, ordered[1:])), "potongan struktur tidak saling tumpang"
    verify_chunks(doc, structure, SCOPE)
    covered = bytearray(len(doc.text))
    for c in structure:
        covered[c.start:c.end] = b"\x01" * (c.end - c.start)
    unc = sum(1 for s in doc.sections if s["section"] in SCOPE for i in range(s["start"], s["end"]) if not doc.text[i].isspace() and not covered[i])
    assert unc == 1074  # karakter bukan-spasi dalam cakupan di luar potongan struktur; sebelum H-064: 4725 (diukur di HEAD sebelumnya)


def test_structure_h064_penjelasan_with_opening_text_ayat_1_does_not_start_at_heading():
    # Penjelasan Pasal dengan isi pembuka sebelum "Ayat (1)": unit tingkat-Pasal (heading + pembuka) sudah memuat heading,
    # jadi chunk Ayat (1) TIDAK boleh melebar ke heading (akan tumpang-tindih). Mematikan mutan M7 (cabang `not has_pre`).
    t = "#### Penjelasan Pasal 3\nUraian pembuka.\nAyat (1)\nCukup jelas.\nAyat (2)\nJjj kkk.\n"
    d = make_doc(t, [("penjelasan_pasal", 0, len(t))])
    cs = chunk_structure(d, tokenizer=ToyWs(), retrieval_cfg=RCFG)
    assert [d.text[c.start:c.end] for c in cs] == [
        "#### Penjelasan Pasal 3\nUraian pembuka.", "Ayat (1)\nCukup jelas.", "Ayat (2)\nJjj kkk.",
    ]
    assert cs[0].address == f"{PREFIX}{SEP}Penjelasan{SEP}Pasal 3"
    assert cs[1].address.endswith("Ayat (1)") and cs[1].start == t.index("Ayat (1)")
    assert all(a.end <= b.start for a, b in zip(cs, cs[1:])), "tanpa tumpang-tindih"
    verify_chunks(d, cs, SCOPE)
