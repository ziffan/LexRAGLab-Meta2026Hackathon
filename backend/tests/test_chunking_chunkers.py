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
    return next(s for s in doc.sections if s["section"] == c.section and s["start"] <= c.start and c.end <= s["end"])


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
    size, ov = FX["chunk_size_tokens"], FX["overlap_tokens"]
    step = size - ov
    expect = 0
    for s in doc.sections:
        if s["section"] in SCOPE:
            n = len(tok.offsets(doc.text[s["start"]:s["end"]]))
            expect += 0 if n == 0 else (1 if n <= size else 1 + math.ceil((n - size) / step))
    assert len(fixed) == expect  # dihitung dari rumus terpisah, bukan dari loop chunker
    assert {c.section for c in fixed} <= SCOPE
    assert max(c.tokens_local for c in fixed) <= size + 2  # hitung ulang token teks terpangkas boleh bergeser tipis di tepi


def test_fixed_boundaries_are_token_boundaries_and_overlap_is_exact(doc, tok, fixed):
    size, ov = FX["chunk_size_tokens"], FX["overlap_tokens"]
    by_sec: dict[tuple[int, int], list] = {}
    for c in fixed:
        s = _section_of(doc, c)
        by_sec.setdefault((s["start"], s["end"]), []).append(c)
    multi = 0
    for (s, e), cs in by_sec.items():
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
    assert multi >= 1, "korpus beku punya Pasal > 512 token; minimal satu section berjendela ganda"


def test_fixed_toy_hand_computed_windows_do_not_cross_sections():
    # section 1: 10 token (t0..t9); section 2: 3 token; size 4 overlap 1 -> langkah 3
    text = "t0 t1 t2 t3 t4 t5 t6 t7 t8 t9\n\nu0 u1 u2\n"
    d = make_doc(text, [("batang_tubuh", 0, 31), ("penjelasan_pasal", 31, len(text))])
    cs = chunk_fixed(d, size=4, overlap=1, tokenizer=ToyWs(), retrieval_cfg=RCFG)
    got = [(c.section, d.text[c.start:c.end]) for c in cs]
    assert got == [
        ("batang_tubuh", "t0 t1 t2 t3"), ("batang_tubuh", "t3 t4 t5 t6"), ("batang_tubuh", "t6 t7 t8 t9"),
        ("penjelasan_pasal", "u0 u1 u2"),
    ]
    assert [c.tokens_local for c in cs] == [4, 4, 4, 3]
    verify_chunks(d, cs)


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
